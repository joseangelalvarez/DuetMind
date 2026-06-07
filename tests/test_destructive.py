import tempfile
import unittest
from collections import deque
from pathlib import Path

from duetmind.middleware import parse_with_layered_repair
from duetmind.moderator import HeuristicModerator
from duetmind.models import AgentId, CompactAgentMessage, ControlSignal, DefensiveAlert, EvalResult, TelemetryCycle
from duetmind.orchestrator import Orchestrator, RuntimeConfig
from duetmind.pipeline import PhaseSpec, PipelineRunner
from duetmind.storage import Storage


class StaticAgent:
    def __init__(self, agent_id: AgentId, graph: dict[str, str], confidence: float = 0.8, oom_flag: bool = False) -> None:
        self.agent_id = agent_id
        self.graph = graph
        self.confidence = confidence
        self.oom_flag = oom_flag

    def generate(self, phase_id: int, iteration: int, prev_graph: dict[str, str], user_intent: str) -> CompactAgentMessage:
        return CompactAgentMessage(
            fase_id=phase_id,
            iteracion=iteration,
            emisor=self.agent_id,
            grafo_estado=dict(self.graph),
            confianza=self.confidence,
            alertas=[],
            telemetria=TelemetryCycle(
                tiempo_ejecucion_ms=100,
                tokens_consumidos=10,
                timeout_flag=False,
                oom_flag=self.oom_flag,
            ),
        )


class FixedSemanticAgent:
    def __init__(self, agent_id: AgentId, semantic: str) -> None:
        self.agent_id = agent_id
        self.semantic = semantic

    def generate(self, phase_id: int, iteration: int, prev_graph: dict[str, str], user_intent: str) -> CompactAgentMessage:
        return CompactAgentMessage(
            fase_id=phase_id,
            iteracion=iteration,
            emisor=self.agent_id,
            grafo_estado={"semantic": self.semantic},
            confianza=0.8,
            alertas=[],
            telemetria=TelemetryCycle(
                tiempo_ejecucion_ms=50,
                tokens_consumidos=10,
                timeout_flag=False,
                oom_flag=False,
            ),
        )


class RollbackModerator:
    def arbitrate(self, a, b, phase_id, iteration, tokens_fase, token_budget):
        return EvalResult(score=0.1, signal=ControlSignal.ROLLBACK, reason="forced_rollback", bloqueantes=0)


def msg(agent_id: AgentId, semantic: str, confidence: float = 0.8) -> CompactAgentMessage:
    return CompactAgentMessage(
        fase_id=1,
        iteracion=1,
        emisor=agent_id,
        grafo_estado={"semantic": semantic},
        confianza=confidence,
        alertas=[
            DefensiveAlert(
                componente_id="test",
                invariante_violada="none",
                gravedad_score=1,
                es_bloqueante=False,
            )
        ],
        telemetria=TelemetryCycle(tiempo_ejecucion_ms=50, tokens_consumidos=10),
    )


class TestDestructive(unittest.TestCase):
    def test_llm_no_json_output(self) -> None:
        parsed = parse_with_layered_repair("plain text without braces", CompactAgentMessage, phase_id=1, iteration=1)
        self.assertEqual(parsed.confianza, 0.0)
        self.assertTrue(parsed.alertas[0].es_bloqueante)

    def test_llm_truncated_json(self) -> None:
        raw = '{"fase_id": 1, "emisor": "A", "iteracion": 1, "grafo_estado": {"x":"y"}...'
        parsed = parse_with_layered_repair(raw, CompactAgentMessage, phase_id=1, iteration=1, agent_id=AgentId.A)
        self.assertIsInstance(parsed, CompactAgentMessage)

    def test_llm_max_confidence_injection(self) -> None:
        moderator = HeuristicModerator()
        a = msg(AgentId.A, "alpha alpha alpha", confidence=0.99)
        b = msg(AgentId.B, "omega omega omega", confidence=0.99)
        result = moderator.arbitrate(a, b, phase_id=1, iteration=1, tokens_fase=20, token_budget=100)
        self.assertNotEqual(result.signal, ControlSignal.FREEZE_ADVANCE)

    def test_cloud_esc_stops_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            orch = Orchestrator(storage)
            schedule = [
                PhaseSpec(1, "P1", "local", 1, "x"),
                PhaseSpec(2, "P2", "local", 1, "x"),
                PhaseSpec(3, "P3", "local", 1, "x"),
            ]

            def resolver(phase: PhaseSpec):
                if phase.phase_id == 3:
                    return (
                        StaticAgent(AgentId.A, {"semantic": "demo"}, oom_flag=True),
                        StaticAgent(AgentId.B, {"semantic": "demo"}),
                    )
                return (
                    StaticAgent(AgentId.A, {"semantic": "demo"}),
                    StaticAgent(AgentId.B, {"semantic": "demo"}),
                )

            runner = PipelineRunner(orch, schedule=schedule, agent_resolver=resolver)
            result = runner.run("demo")

            self.assertEqual(len(result.phase_results), 3)
            self.assertEqual(result.final_signal, ControlSignal.CLOUD_ESC.value)
            storage.close()

    def test_run_phase_out_of_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            orch = Orchestrator(storage)
            result = orch.run_phase(8, "demo", require_prerequisite=True)
            self.assertEqual(result.signal, ControlSignal.ABORT)
            self.assertEqual(result.reason, "missing_prerequisite_snapshot")
            storage.close()

    def test_cross_run_no_integrity_abort(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            run_a = Storage(db, run_id="run-a")
            run_a.append_ledger(1, {"architecture": "intent_a"})
            run_b = Storage(db, run_id="run-b")
            self.assertTrue(run_b.verify_integrity({"architecture": "intent_b"}))
            run_a.close()
            run_b.close()

    def test_rollback_cascade_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            orch = Orchestrator(
                storage,
                agent_a=FixedSemanticAgent(AgentId.A, "demo"),
                agent_b=FixedSemanticAgent(AgentId.B, "demo"),
                moderator=RollbackModerator(),
            )
            try:
                result = orch.run_phase(1, "demo")
                self.assertEqual(result.signal, ControlSignal.ABORT)
                self.assertEqual(result.reason, "rollback_limit")
            finally:
                storage.close()

    def test_imax_reached_no_snapshot_saved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            orch = Orchestrator(
                storage,
                config=RuntimeConfig(imax=2),
                agent_a=FixedSemanticAgent(AgentId.A, "demo"),
                agent_b=FixedSemanticAgent(AgentId.B, "demo"),
                moderator=RollbackModerator(),
            )
            try:
                result = orch.run_phase(1, "demo")
                self.assertEqual(result.reason, "imax_reached")
                self.assertIsNone(storage.get_snapshot(1))

                phase_2_result = orch.run_phase(2, "demo", require_prerequisite=False)
                self.assertIsNotNone(phase_2_result)
            finally:
                storage.close()

    def test_jsd_one_prevents_freeze(self) -> None:
        moderator = HeuristicModerator()
        a = msg(AgentId.A, "alpha", confidence=0.99)
        b = msg(AgentId.B, "beta", confidence=0.99)
        result = moderator.arbitrate(a, b, phase_id=1, iteration=1, tokens_fase=20, token_budget=100)
        self.assertNotEqual(result.signal, ControlSignal.FREEZE_ADVANCE)

    def test_loop_period_3_detected(self) -> None:
        history = deque([{"a"}, {"b"}, {"c"}], maxlen=3)
        loop_flag = Orchestrator._loop_detected(
            current_tokens={"a"},
            token_history=history,
            loop_jaccard_threshold=0.92,
            score_was_computed=True,
            previous_score_available=True,
            last_score=0.5,
            prev_last_score=0.5,
            delta_score_epsilon=0.02,
        )
        self.assertTrue(loop_flag)


if __name__ == "__main__":
    unittest.main()
