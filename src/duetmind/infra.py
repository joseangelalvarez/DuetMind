from __future__ import annotations

import multiprocessing
import os
import socket
import subprocess
from dataclasses import dataclass


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

    def start_daemon(self, name: str, command: list[str], *, env: dict[str, str] | None = None) -> DaemonProcess:
        if name in self._daemons and self._daemons[name].poll() is None:
            process = self._daemons[name]
            return DaemonProcess(name=name, port=-1, pid=int(process.pid or -1))

        port = self.reserve_port()
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        merged_env["DUETMIND_ASSIGNED_PORT"] = str(port)

        process = subprocess.Popen(command, env=merged_env)
        self._daemons[name] = process
        return DaemonProcess(name=name, port=port, pid=int(process.pid or -1))

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
