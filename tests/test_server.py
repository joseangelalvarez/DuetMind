import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from duetmind.orchestrator import Orchestrator
from duetmind.pipeline import PipelineRunner
from duetmind.server import create_audit_server
from duetmind.storage import Storage


class TestServer(unittest.TestCase):
    def test_audit_server_exposes_history_and_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            storage = Storage(db_path)
            orch = Orchestrator(storage)
            runner = PipelineRunner(orch)
            runner.run("Construir sistema multiagente hibrido con bajo costo operativo")

            server = create_audit_server(storage, host="127.0.0.1", port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                port = server.server_address[1]
                time.sleep(0.1)

                with urlopen(f"http://127.0.0.1:{port}/health") as response:
                    health = json.loads(response.read().decode("utf-8"))
                self.assertEqual(health["status"], "ok")

                with urlopen(f"http://127.0.0.1:{port}/history") as response:
                    history = json.loads(response.read().decode("utf-8"))
                self.assertGreaterEqual(len(history), 1)

                with urlopen(f"http://127.0.0.1:{port}/bundle") as response:
                    bundle = json.loads(response.read().decode("utf-8"))
                self.assertIn("phase_results", bundle)
                self.assertIn("telemetry", bundle)
                self.assertIn("snapshots", bundle)
                self.assertIn("ledger", bundle)

                with urlopen(f"http://127.0.0.1:{port}/go-no-go") as response:
                    go_no_go = json.loads(response.read().decode("utf-8"))
                self.assertIn("decision", go_no_go)
                self.assertIn(go_no_go["decision"], {"GO", "NO_GO"})

                run_phase_request = Request(
                    f"http://127.0.0.1:{port}/run-phase",
                    data=json.dumps({"phase_id": 1, "intent": "demo", "agent_mode": "mock"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(run_phase_request) as response:
                    run_phase = json.loads(response.read().decode("utf-8"))
                self.assertEqual(run_phase["phase_id"], 1)
                self.assertIn("signal", run_phase)

                run_all_request = Request(
                    f"http://127.0.0.1:{port}/run-all",
                    data=json.dumps({"intent": "demo", "agent_mode": "mock"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(run_all_request) as response:
                    run_all = json.loads(response.read().decode("utf-8"))
                self.assertIn("final_signal", run_all)
                self.assertIn("phase_results", run_all)
                self.assertIn("go_no_go", run_all)
                self.assertIn(run_all["go_no_go"]["decision"], {"GO", "NO_GO"})

                bundle_path = Path(tmp) / "audit.json"
                export_bundle_request = Request(
                    f"http://127.0.0.1:{port}/export-bundle",
                    data=json.dumps({"path": str(bundle_path)}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(export_bundle_request) as response:
                    export_bundle = json.loads(response.read().decode("utf-8"))
                self.assertEqual(export_bundle["exported_bundle"], str(bundle_path))
                self.assertTrue(bundle_path.exists())
                with bundle_path.open("r", encoding="utf-8") as handle:
                    saved_bundle = json.load(handle)
                self.assertIn("ledger", saved_bundle)

                custom_schedule_request = Request(
                    f"http://127.0.0.1:{port}/run-all",
                    data=json.dumps(
                        {
                            "intent": "demo",
                            "agent_mode": "mock",
                            "schedule": [
                                {
                                    "phase_id": 1,
                                    "name": "CustomConcepcion",
                                    "environment": "local",
                                    "max_iterations": 1,
                                    "model_tier": "custom",
                                    "agent_mode": "provider",
                                }
                            ],
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(custom_schedule_request) as response:
                    custom_run_all = json.loads(response.read().decode("utf-8"))
                self.assertEqual(len(custom_run_all["phase_results"]), 1)
                self.assertEqual(custom_run_all["phase_results"][0]["environment"], "local")
                self.assertEqual(custom_run_all["phase_results"][0]["agent_mode"], "provider")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_api_key_protection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            storage = Storage(db_path)
            server = create_audit_server(storage, host="127.0.0.1", port=0, api_key="secret-key")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                port = server.server_address[1]
                time.sleep(0.1)

                with urlopen(f"http://127.0.0.1:{port}/health") as response:
                    health = json.loads(response.read().decode("utf-8"))
                self.assertEqual(health["status"], "ok")

                with self.assertRaises(HTTPError):
                    urlopen(f"http://127.0.0.1:{port}/history")

                protected_request = Request(
                    f"http://127.0.0.1:{port}/history",
                    headers={"X-API-Key": "secret-key"},
                )
                with urlopen(protected_request) as response:
                    history = json.loads(response.read().decode("utf-8"))
                self.assertIsInstance(history, list)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
