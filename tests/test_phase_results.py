import os
import json
import tempfile
import unittest
from pathlib import Path

from duetmind.orchestrator import Orchestrator
from duetmind.pipeline import PipelineRunner
from duetmind.storage import Storage


class TestPhaseResults(unittest.TestCase):
    def test_phase_result_persistence(self) -> None:
        fd, db_name = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            db_path = Path(db_name)
            storage = Storage(db_path)
            orch = Orchestrator(storage)
            runner = PipelineRunner(orch)
            runner.run("Construir sistema multiagente hibrido con bajo costo operativo")

            rows = storage.list_phase_results()

            self.assertGreaterEqual(len(rows), 1)
            self.assertEqual(rows[0]["phase_id"], 1)
            self.assertIn("signal", rows[0])

            filtered = storage.list_phase_results(phase_id=1)
            self.assertEqual(len(filtered), 1)
            self.assertEqual(filtered[0]["phase_id"], 1)

            export_path = Path(tmp_path := tempfile.mkdtemp()) / "history.json"
            storage.export_phase_results_json(export_path)
            with export_path.open("r", encoding="utf-8") as handle:
                exported = json.load(handle)
            self.assertGreaterEqual(len(exported), 1)
            self.assertEqual(exported[0]["phase_id"], 1)

            telemetry_rows = storage.telemetry_summary()
            self.assertIsInstance(telemetry_rows, list)

            snapshot_manifest = {"phase_1_iter_1": "proposal_yagni", "intent_anchor": "demo"}
            storage.save_snapshot(1, snapshot_manifest)

            bundle_path = Path(tempfile.mkdtemp()) / "bundle.json"
            storage.export_audit_bundle_json(bundle_path)
            with bundle_path.open("r", encoding="utf-8") as handle:
                bundle = json.load(handle)
            self.assertIn("phase_results", bundle)
            self.assertIn("telemetry", bundle)
            self.assertIn("snapshots", bundle)
            self.assertGreaterEqual(len(bundle["snapshots"]), 1)
            storage.close()
        finally:
            if os.path.exists(db_name):
                os.remove(db_name)


if __name__ == "__main__":
    unittest.main()
