from __future__ import annotations

from dataclasses import dataclass

from duetmind.agents import AgentAdapter, build_default_agents
from duetmind.fsm import CollisionInputs, FsmState, resolve_collision_priority
from duetmind.middleware import structural_delta_ratio
from duetmind.models import AgentId, CompactAgentMessage, ControlSignal, DefensiveAlert, EvalResult, TelemetryCycle
from duetmind.scoring import compute_score, cosine_distance_from_token_sets, jaccard_similarity
from duetmind.storage import Storage


@dataclass
class RuntimeConfig:
    imax: int = 4
    tmax_ms: int = 45000
    ds_critical: float = 0.35
    loop_jaccard_threshold: float = 0.92
    delta_score_epsilon: float = 0.02
    semantic_delta_threshold: float = 0.01
    token_budget_per_phase: int = 12000


class Orchestrator:
    def __init__(
        self,
        storage: Storage,
        config: RuntimeConfig | None = None,
        agent_a: AgentAdapter | None = None,
        agent_b: AgentAdapter | None = None,
    ) -> None:
        self.storage = storage
        self.config = config or RuntimeConfig()
        default_a, default_b = build_default_agents()
        self.agent_a = agent_a or default_a
        self.agent_b = agent_b or default_b

    @staticmethod
    def _graph_text(graph: dict[str, str]) -> str:
        return " ".join(f"{k}={v}" for k, v in sorted(graph.items()))

    @staticmethod
    def _make_sentinel_message(phase_id: int, iteration: int, agent_id: AgentId) -> CompactAgentMessage:
        return CompactAgentMessage(
            fase_id=phase_id,
            iteracion=iteration,
            emisor=agent_id,
            grafo_estado={"sentinel": "agent_exception"},
            alertas=[
                DefensiveAlert(
                    componente_id="agent_runtime",
                    invariante_violada="agent_exception",
                    gravedad_score=3,
                    es_bloqueante=True,
                )
            ],
            confianza=0.0,
            telemetria=TelemetryCycle(
                vram_actual_gb=0.0,
                tiempo_ejecucion_ms=0,
                tokens_consumidos=0,
                timeout_flag=False,
                oom_flag=False,
            ),
        )

    def _safe_generate(
        self,
        agent: AgentAdapter,
        phase_id: int,
        iteration: int,
        prev_graph: dict[str, str],
        user_intent: str,
        agent_id: AgentId,
    ) -> CompactAgentMessage:
        try:
            return agent.generate(phase_id, iteration, prev_graph, user_intent)
        except Exception as exc:  # noqa: BLE001 - guardrail against infra failures
            self.storage.append_telemetry(
                phase_id,
                iteration,
                "AGENT_EXCEPTION",
                None,
                str(exc)[:256],
            )
            return self._make_sentinel_message(phase_id, iteration, agent_id)

    def _evaluate(
        self,
        a: CompactAgentMessage,
        b: CompactAgentMessage,
        ds: float,
        loop_flag: bool,
        tokens_fase: int,
    ) -> EvalResult:
        if ds > self.config.ds_critical:
            return EvalResult(
                score=0.0,
                signal=ControlSignal.RESET_FROM_PROMPT_3,
                reason="short_circuit_ds_critical",
                bloqueantes=1,
            )

        if loop_flag:
            return EvalResult(
                score=0.0,
                signal=ControlSignal.ABORT,
                reason="short_circuit_loop_flag",
                bloqueantes=1,
            )

        blocking_alerts = sum(1 for alert in (*a.alertas, *b.alertas) if alert.es_bloqueante)
        if blocking_alerts > 0:
            return EvalResult(
                score=0.0,
                signal=ControlSignal.ROLLBACK,
                reason="blocking_alert",
                bloqueantes=blocking_alerts,
            )

        agreement = 1.0
        stability = 0.9
        risk = 0.9
        score = compute_score(
            agreement,
            stability,
            risk,
            a.confianza,
            b.confianza,
            tokens_fase,
            self.config.token_budget_per_phase,
        )

        if score >= 8.5:
            signal = ControlSignal.FREEZE_ADVANCE
        elif score >= 7.0:
            signal = ControlSignal.CONVERGE_CONDITIONAL
        else:
            signal = ControlSignal.ROLLBACK

        return EvalResult(score=score, signal=signal, reason="score_eval", bloqueantes=0)

    def run_phase(self, phase_id: int, user_intent: str) -> EvalResult:
        state = FsmState.INIT
        prev_snapshot = self.storage.get_snapshot(phase_id - 1) or {"intent": user_intent}
        prev_snapshot.setdefault("intent", user_intent)
        prev_graph = prev_snapshot
        prev_prev_tokens: set[str] = set()
        prev_tokens: set[str] = set(self._graph_text(prev_graph).lower().split())
        last_score = 0.0
        tokens_fase = 0
        rollback_count = 0

        for iteration in range(1, self.config.imax + 1):
            state = FsmState.DEBATE
            a_msg = self._safe_generate(
                self.agent_a,
                phase_id,
                iteration,
                prev_graph,
                user_intent,
                AgentId.A,
            )

            delta = structural_delta_ratio(prev_graph, a_msg.grafo_estado)
            if delta < self.config.semantic_delta_threshold:
                b_msg = self._safe_generate(
                    self.agent_b,
                    phase_id,
                    iteration,
                    prev_graph,
                    user_intent,
                    AgentId.B,
                )
            else:
                b_msg = self._safe_generate(
                    self.agent_b,
                    phase_id,
                    iteration,
                    a_msg.grafo_estado,
                    user_intent,
                    AgentId.B,
                )

            tokens_fase += a_msg.telemetria.tokens_consumidos + b_msg.telemetria.tokens_consumidos
            a_graph_text = self._graph_text(a_msg.grafo_estado)

            timeout_or_oom = (
                a_msg.telemetria.tiempo_ejecucion_ms > self.config.tmax_ms
                or b_msg.telemetria.tiempo_ejecucion_ms > self.config.tmax_ms
                or a_msg.telemetria.oom_flag
                or b_msg.telemetria.oom_flag
            )

            integrity_ok = self.storage.verify_integrity(a_msg.grafo_estado)

            current_tokens = set(a_graph_text.lower().split())
            loop_jaccard = jaccard_similarity(current_tokens, prev_prev_tokens) if prev_prev_tokens else 0.0
            loop_flag = loop_jaccard > self.config.loop_jaccard_threshold and abs(last_score - 0.0) <= self.config.delta_score_epsilon

            ds = cosine_distance_from_token_sets(a_graph_text, user_intent)

            collision = resolve_collision_priority(
                CollisionInputs(
                    timeout_or_oom=timeout_or_oom,
                    integrity_violation=not integrity_ok,
                    ds_critical=ds > self.config.ds_critical,
                    loop_flag=loop_flag,
                )
            )
            if collision is not None:
                state = collision.next_state
                self.storage.append_telemetry(phase_id, iteration, state.value, None, collision.reason)
                if state == FsmState.ROLLBACK:
                    rollback_count += 1
                    if rollback_count >= 3:
                        self.storage.append_telemetry(
                            phase_id, iteration, FsmState.ABORT.value, None, "rollback_limit"
                        )
                        return EvalResult(
                            score=0.0,
                            signal=ControlSignal.ABORT,
                            reason="rollback_limit",
                            bloqueantes=1,
                        )
                    continue
                if state in (FsmState.CLOUD_ESC, FsmState.RESET, FsmState.ABORT):
                    mapping = {
                        FsmState.CLOUD_ESC: ControlSignal.CLOUD_ESC,
                        FsmState.RESET: ControlSignal.RESET_FROM_PROMPT_3,
                        FsmState.ABORT: ControlSignal.ABORT,
                    }
                    return EvalResult(score=0.0, signal=mapping[state], reason=collision.reason, bloqueantes=1)

            state = FsmState.EVAL
            eval_result = self._evaluate(a_msg, b_msg, ds, loop_flag, tokens_fase)
            self.storage.append_telemetry(
                phase_id,
                iteration,
                state.value,
                eval_result.score,
                eval_result.reason,
            )

            if eval_result.signal in (ControlSignal.FREEZE_ADVANCE, ControlSignal.CONVERGE_CONDITIONAL):
                self.storage.save_snapshot(phase_id, a_msg.grafo_estado)
                self.storage.append_ledger(phase_id, a_msg.grafo_estado)
                self.storage.append_telemetry(
                    phase_id,
                    iteration,
                    FsmState.FREEZE.value,
                    eval_result.score,
                    eval_result.signal.value,
                )
                return eval_result

            if eval_result.signal == ControlSignal.ROLLBACK:
                rollback_count += 1
                self.storage.append_telemetry(
                    phase_id,
                    iteration,
                    FsmState.ROLLBACK.value,
                    eval_result.score,
                    "score_below_threshold",
                )
                if rollback_count >= 3:
                    return EvalResult(
                        score=eval_result.score,
                        signal=ControlSignal.ABORT,
                        reason="rollback_limit",
                        bloqueantes=1,
                    )

            last_score = eval_result.score
            prev_prev_tokens = prev_tokens
            prev_tokens = current_tokens
            prev_graph = a_msg.grafo_estado

        return EvalResult(
            score=last_score,
            signal=ControlSignal.ROLLBACK,
            reason="imax_reached",
            bloqueantes=1,
        )
