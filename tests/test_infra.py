import sys
import unittest

from duetmind.infra import LocalDaemonSupervisor


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


if __name__ == "__main__":
    unittest.main()
