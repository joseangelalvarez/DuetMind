import tempfile
import threading
import time
import unittest
from pathlib import Path

from duetmind.smoke import run_smoke_e2e
from duetmind.storage import Storage
from duetmind.server import create_audit_server


class TestSmoke(unittest.TestCase):
    def test_run_smoke_e2e_returns_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "smoke.db")
            server = create_audit_server(storage, host="127.0.0.1", port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                time.sleep(0.1)
                port = server.server_address[1]
                summary = run_smoke_e2e(
                    f"http://127.0.0.1:{port}",
                    intent="Smoke test intent",
                    agent_mode="mock",
                )
                self.assertTrue(summary.health_ok)
                self.assertTrue(summary.run_all_final_signal)
                self.assertIn(summary.go_no_go_decision, {"GO", "GO_CONDICIONAL", "NO_GO"})
                self.assertGreaterEqual(summary.phase_results_count, 1)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                storage.close()


if __name__ == "__main__":
    unittest.main()
