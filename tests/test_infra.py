import sys
import tempfile
import unittest
from pathlib import Path

from duetmind.infra import DaemonSpec, LocalDaemonSupervisor


class TestInfra(unittest.TestCase):
    def test_reserve_port_returns_valid_user_port(self) -> None:
        port = LocalDaemonSupervisor.reserve_port()
        self.assertGreaterEqual(port, 1024)
        self.assertLessEqual(port, 65535)

    def test_dispatch_ephemeral_runs_and_exits(self) -> None:
        code = LocalDaemonSupervisor.dispatch_ephemeral(
            [sys.executable, "-c", "print('ok')"],
            timeout_s=5.0,
        )
        self.assertEqual(code, 0)

    def test_start_and_stop_daemon(self) -> None:
        supervisor = LocalDaemonSupervisor()
        process = supervisor.start_daemon(
            "sleepy",
            [sys.executable, "-c", "import time; time.sleep(30)"],
        )
        self.assertGreater(process.pid, 0)
        stopped = supervisor.stop_daemon("sleepy")
        self.assertTrue(stopped)

    def test_start_managed_daemon_restarts_until_healthy(self) -> None:
        script = (
            "import os, sys, time; "
            "from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer; "
            "marker = os.environ['DUETMIND_MARKER']; "
            "port = int(os.environ['DUETMIND_ASSIGNED_PORT']); "
            "\nif not os.path.exists(marker):\n"
            "    open(marker, 'w').close(); sys.exit(3)\n"
            "class H(BaseHTTPRequestHandler):\n"
            "    def do_GET(self):\n"
            "        if self.path == '/health':\n"
            "            self.send_response(200); self.end_headers(); self.wfile.write(b'{\"status\":\"ok\"}')\n"
            "        else:\n"
            "            self.send_response(404); self.end_headers()\n"
            "    def log_message(self, *args):\n"
            "        return\n"
            "server = ThreadingHTTPServer(('127.0.0.1', port), H); server.serve_forever()"
        )

        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "restart-marker.txt"
            supervisor = LocalDaemonSupervisor()
            managed = supervisor.start_managed_daemon(
                DaemonSpec(
                    name="demo-daemon",
                    command=[sys.executable, "-c", script],
                    health_url_template="http://127.0.0.1:{port}/health",
                    startup_timeout_s=5.0,
                    restart_limit=1,
                    env={"DUETMIND_MARKER": str(marker)},
                )
            )

            self.assertTrue(managed.health.healthy)
            self.assertGreaterEqual(managed.restart_count, 0)
            self.assertTrue(marker.exists())
            stopped = supervisor.stop_daemon("demo-daemon")
            self.assertTrue(stopped)

    def test_check_health_reports_failure_for_unreachable_endpoint(self) -> None:
        health = LocalDaemonSupervisor.check_health("http://127.0.0.1:9/health", timeout_s=0.2)
        self.assertFalse(health.healthy)


if __name__ == "__main__":
    unittest.main()
