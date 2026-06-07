import tempfile
import unittest
from pathlib import Path

from duetmind.agents import MockAgentAdapter, ProviderAgentAdapter
from duetmind.orchestrator import Orchestrator
from duetmind.pipeline import PipelineRunner, PhaseSpec
from duetmind.storage import Storage


class TestPipeline(unittest.TestCase):
    def test_default_agent_resolver_is_hybrid(self) -> None:
        cloud_phase = PhaseSpec(1, "Concepcion", "cloud", 4, "advanced")
        local_phase = PhaseSpec(5, "Arquitectura", "local", 4, "quantized")

        cloud_agents = PipelineRunner._default_agent_resolver(cloud_phase)
        local_agents = PipelineRunner._default_agent_resolver(local_phase)

        self.assertIsInstance(cloud_agents[0], ProviderAgentAdapter)
        self.assertIsInstance(cloud_agents[1], ProviderAgentAdapter)
        self.assertIsInstance(local_agents[0], MockAgentAdapter)
        self.assertIsInstance(local_agents[1], MockAgentAdapter)

    def test_run_all_pipeline_returns_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            storage = Storage(db_path)
            orch = Orchestrator(storage)
            runner = PipelineRunner(orch)
            result = runner.run("Construir sistema multiagente hibrido con bajo costo operativo")

            self.assertGreaterEqual(len(result.phase_results), 1)
            self.assertTrue(result.final_signal)


if __name__ == "__main__":
    unittest.main()
