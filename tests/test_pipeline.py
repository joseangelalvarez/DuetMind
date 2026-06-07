import tempfile
import unittest
from pathlib import Path

from duetmind.agents import MockAgentAdapter, ProviderAgentAdapter
from duetmind.models import AgentId, CompactAgentMessage, ControlSignal, TelemetryCycle
from duetmind.orchestrator import Orchestrator
from duetmind.pipeline import PipelineRunner, PhaseSpec
from duetmind.storage import Storage


class StaticAgent:
    def __init__(
        self,
        *,
        agent_id: AgentId,
        graph: dict[str, str],
        confidence: float = 0.8,
        exec_ms: int = 100,
        oom_flag: bool = False,
    ) -> None:
        self.agent_id = agent_id
        self.graph = graph
        self.confidence = confidence
        self.exec_ms = exec_ms
        self.oom_flag = oom_flag

    def generate(
        self,
        phase_id: int,
        iteration: int,
        prev_graph: dict[str, str],
        user_intent: str,
    ) -> CompactAgentMessage:
        return CompactAgentMessage(
            fase_id=phase_id,
            iteracion=iteration,
            emisor=self.agent_id,
            grafo_estado=dict(self.graph),
            confianza=self.confidence,
            alertas=[],
            telemetria=TelemetryCycle(
                tiempo_ejecucion_ms=self.exec_ms,
                tokens_consumidos=10,
                timeout_flag=False,
                oom_flag=self.oom_flag,
            ),
        )


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
            storage.close()

    def test_cloud_esc_terminates_pipeline_at_phase_N(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            orch = Orchestrator(storage)
            schedule = [
                PhaseSpec(1, "Custom", "local", 1, "x"),
                PhaseSpec(2, "Custom", "local", 1, "x"),
            ]

            def resolver(_: PhaseSpec):
                return (
                    StaticAgent(agent_id=AgentId.A, graph={"x": "a"}, oom_flag=True),
                    StaticAgent(agent_id=AgentId.B, graph={"x": "a"}),
                )

            runner = PipelineRunner(orch, schedule=schedule, agent_resolver=resolver)
            result = runner.run("demo")

            self.assertEqual(len(result.phase_results), 1)
            self.assertEqual(result.final_signal, ControlSignal.CLOUD_ESC.value)
            storage.close()

    def test_abort_terminates_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            storage.append_ledger(0, {"locked_component": "v1"})
            orch = Orchestrator(storage)
            schedule = [
                PhaseSpec(1, "Custom", "local", 1, "x"),
                PhaseSpec(2, "Custom", "local", 1, "x"),
            ]

            def resolver(_: PhaseSpec):
                return (
                    StaticAgent(agent_id=AgentId.A, graph={"locked_component": "v2"}),
                    StaticAgent(agent_id=AgentId.B, graph={"locked_component": "v2"}),
                )

            runner = PipelineRunner(orch, schedule=schedule, agent_resolver=resolver)
            result = runner.run("demo")

            self.assertEqual(len(result.phase_results), 1)
            self.assertEqual(result.final_signal, ControlSignal.ABORT.value)
            storage.close()

    def test_reset_terminates_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            orch = Orchestrator(storage)
            schedule = [
                PhaseSpec(1, "Custom", "local", 1, "x"),
                PhaseSpec(2, "Custom", "local", 1, "x"),
            ]

            def resolver(_: PhaseSpec):
                return (
                    StaticAgent(agent_id=AgentId.A, graph={"semantic": "unrelated_tokens_foo_bar"}),
                    StaticAgent(agent_id=AgentId.B, graph={"semantic": "unrelated_tokens_foo_bar"}),
                )

            runner = PipelineRunner(orch, schedule=schedule, agent_resolver=resolver)
            result = runner.run("completely different intent words")

            self.assertEqual(len(result.phase_results), 1)
            self.assertEqual(result.final_signal, ControlSignal.RESET_FROM_PROMPT_3.value)
            storage.close()

    def test_converge_conditional_does_not_terminate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            orch = Orchestrator(storage)
            schedule = [
                PhaseSpec(1, "Custom", "local", 1, "x"),
                PhaseSpec(2, "Custom", "local", 1, "x"),
            ]

            def resolver(_: PhaseSpec):
                return (
                    StaticAgent(agent_id=AgentId.A, graph={"intent": "demo"}, confidence=0.8),
                    StaticAgent(agent_id=AgentId.B, graph={"intent": "demo"}, confidence=0.8),
                )

            runner = PipelineRunner(orch, schedule=schedule, agent_resolver=resolver)
            try:
                result = runner.run("intent=demo")

                self.assertEqual(len(result.phase_results), 2)
                self.assertNotIn(result.final_signal, {ControlSignal.ABORT.value, ControlSignal.RESET_FROM_PROMPT_3.value, ControlSignal.CLOUD_ESC.value})
            finally:
                storage.close()


if __name__ == "__main__":
    unittest.main()
