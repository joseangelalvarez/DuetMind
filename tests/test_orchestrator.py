import tempfile
import unittest
from pathlib import Path

from duetmind.models import ControlSignal
from duetmind.orchestrator import Orchestrator
from duetmind.storage import Storage


class FailingAgent:
    def generate(self, phase_id: int, iteration: int, prev_graph: dict[str, str], user_intent: str):
        raise RuntimeError("simulated_provider_failure")


class TestOrchestrator(unittest.TestCase):
    def test_demo_phase_converges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            storage = Storage(db_path)
            orch = Orchestrator(storage)
            result = orch.run_phase(1, "Construir sistema multiagente hibrido con bajo costo operativo")

            self.assertIn(result.signal.value, {"CONGELAR_Y_AVANZAR", "CONVERGE_CONDICIONADO", "ROLLBACK", "ESCALAR_A_HUMANO"})
            self.assertGreaterEqual(result.score, 7.0)

            snapshot = storage.get_snapshot(1)
            self.assertIsNotNone(snapshot)
            self.assertIn("phase_1_iter_1", snapshot)
            storage.close()

    def test_agent_exception_returns_sentinel_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            orch = Orchestrator(storage, agent_a=FailingAgent(), agent_b=FailingAgent())

            result = orch.run_phase(1, "demo")

            self.assertIsNotNone(result)
            self.assertNotEqual(result.signal, ControlSignal.FREEZE_ADVANCE)
            storage.close()

    def test_agent_exception_logged_to_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            orch = Orchestrator(storage, agent_a=FailingAgent(), agent_b=FailingAgent())

            orch.run_phase(1, "demo")
            summary = storage.telemetry_summary(phase_id=1)

            self.assertTrue(any(row["state"] == "AGENT_EXCEPTION" for row in summary))
            storage.close()

    def test_sentinel_triggers_rollback_not_freeze(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            orch = Orchestrator(storage, agent_a=FailingAgent(), agent_b=FailingAgent())
            try:
                result = orch.run_phase(1, "demo")

                self.assertIn(
                    result.signal,
                    {ControlSignal.ROLLBACK, ControlSignal.ABORT, ControlSignal.RESET_FROM_PROMPT_3},
                )
                self.assertNotIn(result.signal, {ControlSignal.FREEZE_ADVANCE, ControlSignal.CONVERGE_CONDITIONAL})
            finally:
                storage.close()


if __name__ == "__main__":
    unittest.main()
