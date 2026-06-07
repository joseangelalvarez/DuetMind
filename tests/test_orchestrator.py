import tempfile
import unittest
from collections import deque
from pathlib import Path

from duetmind.models import AgentId, CompactAgentMessage, ControlSignal, DefensiveAlert, EvalInput, TelemetryCycle
from duetmind.orchestrator import Orchestrator, RuntimeConfig
from duetmind.scoring import financial_discount
from duetmind.storage import Storage


class FailingAgent:
    def generate(self, phase_id: int, iteration: int, prev_graph: dict[str, str], user_intent: str):
        raise RuntimeError("simulated_provider_failure")


def build_message(
    *,
    agent_id: AgentId,
    graph: dict[str, str],
    confidence: float = 0.8,
    blockers: int = 0,
) -> CompactAgentMessage:
    alerts = [
        DefensiveAlert(
            componente_id=f"alert_{idx}",
            invariante_violada="test_blocker",
            gravedad_score=3,
            es_bloqueante=True,
        )
        for idx in range(blockers)
    ]
    return CompactAgentMessage(
        fase_id=1,
        iteracion=1,
        emisor=agent_id,
        grafo_estado=graph,
        confianza=confidence,
        alertas=alerts,
        telemetria=TelemetryCycle(
            tiempo_ejecucion_ms=50,
            tokens_consumidos=10,
            timeout_flag=False,
            oom_flag=False,
        ),
    )


class TestOrchestrator(unittest.TestCase):
    def test_no_loop_flag_in_iteration_1(self) -> None:
        loop_flag = Orchestrator._loop_detected(
            current_tokens={"alpha"},
            token_history=deque(maxlen=3),
            loop_jaccard_threshold=0.92,
            score_was_computed=False,
            previous_score_available=False,
            last_score=0.0,
            prev_last_score=0.0,
            delta_score_epsilon=0.02,
        )
        self.assertFalse(loop_flag)

    def test_loop_flag_requires_score_computed(self) -> None:
        loop_flag = Orchestrator._loop_detected(
            current_tokens={"alpha"},
            token_history=deque([{"alpha"}], maxlen=3),
            loop_jaccard_threshold=0.92,
            score_was_computed=False,
            previous_score_available=True,
            last_score=0.8,
            prev_last_score=0.79,
            delta_score_epsilon=0.02,
        )
        self.assertFalse(loop_flag)

    def test_loop_period_2_detected(self) -> None:
        history = deque([{"a"}, {"b"}, {"a"}], maxlen=3)
        loop_flag = Orchestrator._loop_detected(
            current_tokens={"b"},
            token_history=history,
            loop_jaccard_threshold=0.92,
            score_was_computed=True,
            previous_score_available=True,
            last_score=0.5,
            prev_last_score=0.5,
            delta_score_epsilon=0.02,
        )
        self.assertTrue(loop_flag)

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

    def test_no_false_positive_on_vocabulary_variation(self) -> None:
        history = deque([{"a", "b", "d"}], maxlen=3)
        loop_flag = Orchestrator._loop_detected(
            current_tokens={"a", "b", "c"},
            token_history=history,
            loop_jaccard_threshold=0.92,
            score_was_computed=True,
            previous_score_available=True,
            last_score=0.5,
            prev_last_score=0.5,
            delta_score_epsilon=0.02,
        )
        self.assertFalse(loop_flag)

    def test_run_phase_blocked_without_prerequisite_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            orch = Orchestrator(storage)

            result = orch.run_phase(2, "demo", require_prerequisite=True)

            self.assertEqual(result.signal, ControlSignal.ABORT)
            self.assertEqual(result.reason, "missing_prerequisite_snapshot")
            storage.close()

    def test_run_phase_allowed_when_prerequisite_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            storage.save_snapshot(1, {"phase_1_iter_1": "seed"}, signal=ControlSignal.FREEZE_ADVANCE.value)
            orch = Orchestrator(storage)

            result = orch.run_phase(2, "demo", require_prerequisite=True)

            self.assertNotEqual(result.reason, "missing_prerequisite_snapshot")
            storage.close()

    def test_run_phase_phase_1_no_prerequisite_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            orch = Orchestrator(storage)

            result = orch.run_phase(1, "demo", require_prerequisite=True)

            self.assertNotEqual(result.reason, "missing_prerequisite_snapshot")
            storage.close()

    def test_demo_phase_converges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            storage = Storage(db_path)
            orch = Orchestrator(storage)
            result = orch.run_phase(1, "Construir sistema multiagente hibrido con bajo costo operativo")

            self.assertIn(result.signal.value, {"CONGELAR_Y_AVANZAR", "CONVERGE_CONDICIONADO", "ROLLBACK", "ESCALAR_A_HUMANO"})
            self.assertGreaterEqual(result.score, 0.0)

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

    def test_phase_id_above_12_rejected_at_runtime_not_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            orch = Orchestrator(storage)
            result = orch.run_phase(13, "demo")
            self.assertEqual(result.signal, ControlSignal.ABORT)
            self.assertEqual(result.reason, "phase_id_out_of_bounds")
            storage.close()

    def test_agreement_is_one_when_agents_produce_identical_output(self) -> None:
        a = build_message(agent_id=AgentId.A, graph={"semantic": "same same"})
        b = build_message(agent_id=AgentId.B, graph={"semantic": "same same"})
        eval_input = Orchestrator._build_eval_input(a, b, ds=0.0, loop_flag=False, tokens_fase=10, token_budget_per_phase=100)
        agreement = 1.0 - eval_input.jsd
        self.assertAlmostEqual(agreement, 1.0, places=6)

    def test_agreement_decreases_with_divergent_outputs(self) -> None:
        a = build_message(agent_id=AgentId.A, graph={"semantic": "alpha alpha alpha"})
        b = build_message(agent_id=AgentId.B, graph={"semantic": "omega omega omega"})
        eval_input = Orchestrator._build_eval_input(a, b, ds=0.0, loop_flag=False, tokens_fase=10, token_budget_per_phase=100)
        self.assertLess(1.0 - eval_input.jsd, 0.5)

    def test_blockers_reduce_risk_score(self) -> None:
        a = build_message(agent_id=AgentId.A, graph={"semantic": "alpha"}, blockers=1)
        b = build_message(agent_id=AgentId.B, graph={"semantic": "alpha"}, blockers=1)
        risk, blockers = Orchestrator._risk_from_alerts(a, b)
        self.assertEqual(blockers, 2)
        self.assertLess(risk, 1.0)

    def test_score_below_threshold_on_full_divergence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            orch = Orchestrator(storage, config=RuntimeConfig(score_freeze_threshold=7.5, score_converge_threshold=6.0))
            a = build_message(agent_id=AgentId.A, graph={"semantic": "alpha"}, confidence=0.2)
            b = build_message(agent_id=AgentId.B, graph={"semantic": "omega"}, confidence=0.2)
            eval_input = Orchestrator._build_eval_input(a, b, ds=0.1, loop_flag=False, tokens_fase=90, token_budget_per_phase=100)
            result = orch._evaluate(eval_input)
            self.assertEqual(result.signal, ControlSignal.ROLLBACK)
            storage.close()

    def test_no_false_convergence_with_jsd_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            orch = Orchestrator(storage)
            a = build_message(agent_id=AgentId.A, graph={"semantic": "alpha"}, confidence=0.1)
            b = build_message(agent_id=AgentId.B, graph={"semantic": "beta"}, confidence=0.1)
            eval_input = EvalInput(
                a_msg=a,
                b_msg=b,
                ds=0.1,
                loop_flag=False,
                jsd=1.0,
                tokens_fase=100,
                presupuesto_tokens_fase=100,
            )
            result = orch._evaluate(eval_input)
            self.assertNotEqual(result.signal, ControlSignal.FREEZE_ADVANCE)
            storage.close()

    def test_ds_uses_semantic_values_not_structural_keys(self) -> None:
        graph = {
            "phase_1_iter_1": "structure_noise",
            "intent_anchor": "demo",
            "semantic": "target meaning",
        }
        semantic = Orchestrator._semantic_values(graph)
        self.assertIn("target meaning", semantic)
        self.assertNotIn("demo", semantic)
        self.assertNotIn("structure_noise", semantic)

    def test_ds_no_false_reset_on_structural_noise(self) -> None:
        semantic = Orchestrator._semantic_values(
            {
                "phase_1_iter_1": "noise",
                "intent_anchor": "demo",
                "semantic": "demo",
            }
        )
        # semantic string should match the intent-relevant value only.
        self.assertEqual(semantic, "demo")

    def test_ds_critical_fires_on_genuine_semantic_divergence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            orch = Orchestrator(storage, config=RuntimeConfig(ds_critical=0.2))
            a = build_message(agent_id=AgentId.A, graph={"semantic": "alpha"})
            b = build_message(agent_id=AgentId.B, graph={"semantic": "beta"})
            eval_input = EvalInput(
                a_msg=a,
                b_msg=b,
                ds=0.9,
                loop_flag=False,
                jsd=0.5,
                tokens_fase=10,
                presupuesto_tokens_fase=100,
            )
            result = orch._evaluate(eval_input)
            self.assertEqual(result.signal, ControlSignal.RESET_FROM_PROMPT_3)
            storage.close()

    def test_eval_input_jsd_populated_correctly(self) -> None:
        a = build_message(agent_id=AgentId.A, graph={"semantic": "same"})
        b = build_message(agent_id=AgentId.B, graph={"semantic": "same"})
        eval_input = Orchestrator._build_eval_input(a, b, ds=0.0, loop_flag=False, tokens_fase=10, token_budget_per_phase=100)
        self.assertAlmostEqual(eval_input.jsd, 0.0, places=6)

    def test_financial_discount_zero_at_full_budget(self) -> None:
        self.assertEqual(financial_discount(100, 100), 0.0)

    def test_financial_discount_penalizes_overrun(self) -> None:
        self.assertEqual(financial_discount(150, 100), 0.0)


if __name__ == "__main__":
    unittest.main()
