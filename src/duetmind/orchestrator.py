from __future__ import annotations

import concurrent.futures
from collections import deque
from dataclasses import dataclass

from duetmind.agents import AgentAdapter, build_default_agents
from duetmind.exceptions import IntegrityViolationError
from duetmind.fsm import CollisionInputs, FsmEvent, FsmState, resolve_collision_priority, resolve_phase_transition
from duetmind.middleware import structural_delta_ratio
from duetmind.moderator import HeuristicModerator, ModeratorAdapter
from duetmind.models import AgentId, CompactAgentMessage, ControlSignal, DefensiveAlert, EvalInput, EvalResult, TelemetryCycle
from duetmind.scoring import compute_score, cosine_distance_from_token_sets, jaccard_similarity, jensen_shannon_distance
from duetmind.storage import Storage


@dataclass
class RuntimeConfig:
    imax: int = 4
    max_phase_id: int = 12
    tmax_ms: int = 45000
    ds_critical: float = 0.35
    loop_jaccard_threshold: float = 0.92
    loop_detection_window: int = 3
    delta_score_epsilon: float = 0.02
    semantic_delta_threshold: float = 0.01
    token_budget_per_phase: int = 12000
    score_freeze_threshold: float = 7.5
    score_converge_threshold: float = 6.0


class Orchestrator:
    def __init__(
        self,
        storage: Storage,
        config: RuntimeConfig | None = None,
        agent_a: AgentAdapter | None = None,
        agent_b: AgentAdapter | None = None,
        moderator: ModeratorAdapter | None = None,
    ) -> None:
        self.storage = storage
        self.config = config or RuntimeConfig()
        default_a, default_b = build_default_agents()
        self.agent_a = agent_a or default_a
        self.agent_b = agent_b or default_b
        self.moderator = moderator or HeuristicModerator(
            score_freeze_threshold=self.config.score_freeze_threshold,
            score_converge_threshold=self.config.score_converge_threshold,
        )

    @staticmethod
    def _graph_text(graph: dict[str, str]) -> str:
        return " ".join(f"{k}={v}" for k, v in sorted(graph.items()))

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return text.lower().split()

    @staticmethod
    def _semantic_values(graph: dict[str, str]) -> str:
        structural_prefixes = ("phase_", "intent_anchor", "__")
        values = [v for k, v in graph.items() if not any(k.startswith(prefix) for prefix in structural_prefixes)]
        if values:
            return " ".join(values)
        return " ".join(graph.values())

    @staticmethod
    def _risk_from_alerts(a: CompactAgentMessage, b: CompactAgentMessage) -> tuple[float, int]:
        all_alerts = [*a.alertas, *b.alertas]
        blockers = sum(1 for alert in all_alerts if alert.es_bloqueante)
        risk = 1.0 - (blockers / (blockers + 1))
        return risk, blockers

    @staticmethod
    def _build_eval_input(
        a_msg: CompactAgentMessage,
        b_msg: CompactAgentMessage,
        ds: float,
        loop_flag: bool,
        tokens_fase: int,
        token_budget_per_phase: int,
    ) -> EvalInput:
        a_tokens = Orchestrator._tokenize(Orchestrator._graph_text(a_msg.grafo_estado))
        b_tokens = Orchestrator._tokenize(Orchestrator._graph_text(b_msg.grafo_estado))
        return EvalInput(
            a_msg=a_msg,
            b_msg=b_msg,
            ds=ds,
            loop_flag=loop_flag,
            jsd=jensen_shannon_distance(a_tokens, b_tokens),
            tokens_fase=tokens_fase,
            presupuesto_tokens_fase=token_budget_per_phase,
        )

    @staticmethod
    def _make_sentinel_message(
        phase_id: int,
        iteration: int,
        agent_id: AgentId,
        *,
        sentinel_reason: str = "agent_exception",
        timeout_flag: bool = False,
    ) -> CompactAgentMessage:
        return CompactAgentMessage(
            fase_id=phase_id,
            iteracion=iteration,
            emisor=agent_id,
            grafo_estado={"sentinel": sentinel_reason},
            alertas=[
                DefensiveAlert(
                    componente_id="agent_runtime",
                    invariante_violada=sentinel_reason,
                    gravedad_score=3,
                    es_bloqueante=True,
                )
            ],
            confianza=0.0,
            telemetria=TelemetryCycle(
                vram_actual_gb=0.0,
                tiempo_ejecucion_ms=0,
                tokens_consumidos=0,
                timeout_flag=timeout_flag,
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
        timeout_s = self.config.tmax_ms / 1000.0
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(agent.generate, phase_id, iteration, prev_graph, user_intent)
                return future.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError:
            self.storage.append_telemetry(
                phase_id,
                iteration,
                "AGENT_TIMEOUT",
                None,
                "provider_timeout",
            )
            return self._make_sentinel_message(
                phase_id,
                iteration,
                agent_id,
                sentinel_reason="agent_timeout",
                timeout_flag=True,
            )
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
        eval_input: EvalInput,
    ) -> EvalResult:
        if eval_input.ds > self.config.ds_critical:
            return EvalResult(
                score=0.0,
                signal=ControlSignal.RESET_FROM_PROMPT_3,
                reason="short_circuit_ds_critical",
                bloqueantes=1,
            )

        if eval_input.loop_flag:
            return EvalResult(
                score=0.0,
                signal=ControlSignal.ABORT,
                reason="short_circuit_loop_flag",
                bloqueantes=1,
            )

        if (
            eval_input.a_msg.grafo_estado.get("sentinel") is not None
            or eval_input.b_msg.grafo_estado.get("sentinel") is not None
        ):
            return EvalResult(
                score=0.0,
                signal=ControlSignal.ROLLBACK,
                reason="short_circuit_sentinel",
                bloqueantes=1,
            )
        return self.moderator.arbitrate(
            eval_input.a_msg,
            eval_input.b_msg,
            eval_input.a_msg.fase_id,
            eval_input.a_msg.iteracion,
            eval_input.tokens_fase,
            eval_input.presupuesto_tokens_fase,
        )

    @staticmethod
    def _loop_detected(
        current_tokens: set[str],
        token_history: deque[set[str]],
        loop_jaccard_threshold: float,
        score_was_computed: bool,
        previous_score_available: bool,
        last_score: float,
        prev_last_score: float,
        delta_score_epsilon: float,
    ) -> bool:
        periodic_loop = any(
            jaccard_similarity(current_tokens, past_tokens) > loop_jaccard_threshold
            for past_tokens in token_history
        )
        return (
            periodic_loop
            and score_was_computed
            and previous_score_available
            and abs(last_score - prev_last_score) <= delta_score_epsilon
        )

    def run_phase(self, phase_id: int, user_intent: str, *, require_prerequisite: bool = True) -> EvalResult:
        if phase_id < 1 or phase_id > self.config.max_phase_id:
            return EvalResult(
                score=0.0,
                signal=ControlSignal.ABORT,
                reason="phase_id_out_of_bounds",
                bloqueantes=1,
            )
        if phase_id > 1 and require_prerequisite and not self.storage.has_go_snapshot(phase_id - 1):
            return EvalResult(
                score=0.0,
                signal=ControlSignal.ABORT,
                reason="missing_prerequisite_snapshot",
                bloqueantes=1,
            )
        state = FsmState.INIT
        prev_snapshot = self.storage.get_snapshot(phase_id - 1) or {"intent": user_intent}
        prev_snapshot.setdefault("intent", user_intent)
        prev_graph = prev_snapshot
        token_history: deque[set[str]] = deque(maxlen=max(1, self.config.loop_detection_window))
        last_score = 0.0
        prev_last_score = 0.0
        score_was_computed = False
        previous_score_available = False
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
                or a_msg.telemetria.timeout_flag
                or b_msg.telemetria.timeout_flag
                or a_msg.telemetria.oom_flag
                or b_msg.telemetria.oom_flag
            )

            try:
                self.storage.assert_integrity(a_msg.grafo_estado)
                integrity_ok = True
            except IntegrityViolationError:
                integrity_ok = False

            current_tokens = set(a_graph_text.lower().split())
            loop_flag = self._loop_detected(
                current_tokens,
                token_history,
                self.config.loop_jaccard_threshold,
                score_was_computed,
                previous_score_available,
                last_score,
                prev_last_score,
                self.config.delta_score_epsilon,
            )

            is_sentinel = a_msg.grafo_estado.get("sentinel") is not None
            if is_sentinel:
                semantic_text = ""
                ds = 0.0
            else:
                semantic_text = self._semantic_values(a_msg.grafo_estado)
                ds = cosine_distance_from_token_sets(semantic_text, user_intent)

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
            eval_input = self._build_eval_input(
                a_msg,
                b_msg,
                ds,
                loop_flag,
                tokens_fase,
                self.config.token_budget_per_phase,
            )
            eval_result = self._evaluate(eval_input)
            self.storage.append_telemetry(
                phase_id,
                iteration,
                state.value,
                eval_result.score,
                eval_result.reason,
            )

            if eval_result.signal in (ControlSignal.FREEZE_ADVANCE, ControlSignal.CONVERGE_CONDITIONAL):
                self.storage.save_snapshot(phase_id, a_msg.grafo_estado, signal=eval_result.signal.value)
                self.storage.append_ledger(phase_id, a_msg.grafo_estado)
                self.storage.append_telemetry(
                    phase_id,
                    iteration,
                    FsmState.FREEZE.value,
                    eval_result.score,
                    eval_result.signal.value,
                )
                next_state = resolve_phase_transition(FsmState.FREEZE, FsmEvent.PHASE_END)
                if next_state is not None:
                    self.storage.append_telemetry(
                        phase_id,
                        iteration,
                        next_state.value,
                        eval_result.score,
                        FsmEvent.PHASE_END.value,
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

            if score_was_computed:
                prev_last_score = last_score
                previous_score_available = True
            last_score = eval_result.score
            score_was_computed = True
            token_history.append(current_tokens)
            prev_graph = a_msg.grafo_estado

        return EvalResult(
            score=last_score,
            signal=ControlSignal.ROLLBACK,
            reason="imax_reached",
            bloqueantes=1,
        )
