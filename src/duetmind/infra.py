from __future__ import annotations

import multiprocessing
import os
import socket
import subprocess
from dataclasses import dataclass
from time import sleep
from urllib.error import URLError
from urllib.request import urlopen


def _ephemeral_subprocess_worker(command: list[str], env: dict[str, str], timeout_s: float) -> int:
    completed = subprocess.run(command, env=env, capture_output=True, text=True, timeout=timeout_s, check=False)
    return int(completed.returncode)


def _ephemeral_subprocess_queue_worker(
    command: list[str],
    env: dict[str, str],
    timeout_s: float,
    result_queue: multiprocessing.Queue[int],
) -> None:
    code = _ephemeral_subprocess_worker(command, env, timeout_s)
    result_queue.put(code)


@dataclass(frozen=True)
class DaemonProcess:
    name: str
    port: int
    pid: int


@dataclass(frozen=True)
class DaemonSpec:
    name: str
    command: list[str]
    health_url_template: str | None = None
    startup_timeout_s: float = 10.0
    restart_limit: int = 1
    env: dict[str, str] | None = None


@dataclass(frozen=True)
class DaemonHealth:
    healthy: bool
    status_code: int | None = None
    reason: str = ""


@dataclass(frozen=True)
class ManagedDaemon:
    process: DaemonProcess
    health: DaemonHealth
    restart_count: int
    last_exit_code: int | None = None


class LocalDaemonSupervisor:
    """Supervisor for local daemons plus ephemeral wrapper tasks."""

    def __init__(self) -> None:
        self._daemons: dict[str, subprocess.Popen[str]] = {}

    @staticmethod
    def reserve_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen(1)
            return int(sock.getsockname()[1])

    @staticmethod
    def check_health(health_url: str, *, timeout_s: float = 1.0) -> DaemonHealth:
        try:
            with urlopen(health_url, timeout=timeout_s) as response:
                status_code = int(getattr(response, "status", 200))
                return DaemonHealth(healthy=200 <= status_code < 300, status_code=status_code, reason="http")
        except URLError as exc:
            return DaemonHealth(healthy=False, reason=str(exc.reason) if hasattr(exc, "reason") else "unreachable")
        except Exception as exc:  # noqa: BLE001 - infrastructure guardrail
            return DaemonHealth(healthy=False, reason=str(exc)[:128])

    def _start_process(
        self,
        name: str,
        command: list[str],
        *,
        env: dict[str, str] | None = None,
        port: int | None = None,
    ) -> subprocess.Popen[str]:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        if port is None:
            port = self.reserve_port()
        merged_env["DUETMIND_ASSIGNED_PORT"] = str(port)
        process = subprocess.Popen(command, env=merged_env)
        self._daemons[name] = process
        return process

    def start_daemon(self, name: str, command: list[str], *, env: dict[str, str] | None = None) -> DaemonProcess:
        if name in self._daemons and self._daemons[name].poll() is None:
            process = self._daemons[name]
            return DaemonProcess(name=name, port=-1, pid=int(process.pid or -1))

        port = self.reserve_port()
        process = self._start_process(name, command, env=env, port=port)
        return DaemonProcess(name=name, port=port, pid=int(process.pid or -1))

    def start_managed_daemon(self, spec: DaemonSpec) -> ManagedDaemon:
        port = self.reserve_port()
        health_url = spec.health_url_template.format(port=port) if spec.health_url_template else ""
        restart_count = 0
        last_exit_code: int | None = None

        while True:
            process = self._start_process(spec.name, spec.command, env=spec.env, port=port)
            process_info = DaemonProcess(name=spec.name, port=port, pid=int(process.pid or -1))

            health = DaemonHealth(healthy=True, reason="no_health_check")
            if health_url:
                deadline = spec.startup_timeout_s
                elapsed = 0.0
                health = DaemonHealth(healthy=False, reason="startup_timeout")
                while elapsed < deadline:
                    if process.poll() is not None:
                        last_exit_code = int(process.returncode or 0)
                        health = DaemonHealth(healthy=False, reason="process_exited_early", status_code=last_exit_code)
                        break
                    current = self.check_health(health_url, timeout_s=1.0)
                    if current.healthy:
                        health = current
                        break
                    sleep(0.1)
                    elapsed += 0.1

            if health.healthy:
                return ManagedDaemon(process=process_info, health=health, restart_count=restart_count, last_exit_code=last_exit_code)

            self.stop_daemon(spec.name)
            restart_count += 1
            if restart_count > spec.restart_limit:
                return ManagedDaemon(process=process_info, health=health, restart_count=restart_count - 1, last_exit_code=last_exit_code)

    def stop_daemon(self, name: str, *, timeout_s: float = 3.0) -> bool:
        process = self._daemons.get(name)
        if process is None:
            return False
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=timeout_s)
        self._daemons.pop(name, None)
        return True

    def stop_all(self) -> None:
        for name in list(self._daemons.keys()):
            self.stop_daemon(name)

    @staticmethod
    def dispatch_ephemeral(command: list[str], *, timeout_s: float = 10.0, env: dict[str, str] | None = None) -> int:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        ctx = multiprocessing.get_context("spawn")
        result_queue: multiprocessing.Queue[int] = ctx.Queue(maxsize=1)
        process = ctx.Process(
            target=_ephemeral_subprocess_queue_worker,
            args=(command, merged_env, timeout_s, result_queue),
        )
        process.start()
        process.join(timeout=timeout_s + 1.0)
        if process.is_alive():
            process.terminate()
            process.join(timeout=1.0)
            return 124

        if result_queue.empty():
            return 1
        return int(result_queue.get())

    def start_daemon_stack(self, specs: list[DaemonSpec]) -> list[ManagedDaemon]:
        managed: list[ManagedDaemon] = []
        for spec in specs:
            managed.append(self.start_managed_daemon(spec))
        return managed
