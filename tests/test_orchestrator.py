import tempfile
import unittest
from pathlib import Path

from duetmind.models import ControlSignal
from duetmind.orchestrator import Orchestrator
from duetmind.storage import Storage


class TestOrchestrator(unittest.TestCase):
    def test_demo_phase_converges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            storage = Storage(db_path)
            orch = Orchestrator(storage)
            result = orch.run_phase(1, "Construir sistema multiagente hibrido con bajo costo operativo")

            self.assertIn(result.signal, {ControlSignal.FREEZE_ADVANCE, ControlSignal.CONVERGE_CONDITIONAL})
            self.assertGreaterEqual(result.score, 7.0)

            snapshot = storage.get_snapshot(1)
            self.assertIsNotNone(snapshot)
            self.assertIn("phase_1_iter_1", snapshot)


if __name__ == "__main__":
    unittest.main()
