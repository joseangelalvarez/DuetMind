from __future__ import annotations

import json
from typing import Protocol

from duetmind.middleware import structural_delta_ratio
from duetmind.models import CompactAgentMessage, ControlSignal, EvalResult
from duetmind.providers import InferenceProvider, ProviderRequest
from duetmind.scoring import compute_score, jensen_shannon_distance


class ModeratorAdapter(Protocol):
    def arbitrate(
        self,
        a: CompactAgentMessage,
        b: CompactAgentMessage,
        phase_id: int,
        iteration: int,
        tokens_fase: int,
        token_budget: int,
    ) -> EvalResult: ...


class HeuristicModerator:
    """Deterministic moderator that scores agreement/stability/risk."""

    def __init__(
        self,
        *,
        score_freeze_threshold: float = 7.5,
        score_converge_threshold: float = 6.0,
    ) -> None:
        self.score_freeze_threshold = score_freeze_threshold
        self.score_converge_threshold = score_converge_threshold

    @staticmethod
    def _graph_text(graph: dict[str, str]) -> str:
        return " ".join(f"{k}={v}" for k, v in sorted(graph.items()))

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return text.lower().split()

    @staticmethod
    def _risk_from_alerts(a: CompactAgentMessage, b: CompactAgentMessage) -> tuple[float, int]:
        all_alerts = [*a.alertas, *b.alertas]
        blockers = sum(1 for alert in all_alerts if alert.es_bloqueante)
        risk = 1.0 - (blockers / (blockers + 1))
        return risk, blockers

    def arbitrate(
        self,
        a: CompactAgentMessage,
        b: CompactAgentMessage,
        phase_id: int,
        iteration: int,
        tokens_fase: int,
        token_budget: int,
    ) -> EvalResult:
        a_tokens = self._tokenize(self._graph_text(a.grafo_estado))
        b_tokens = self._tokenize(self._graph_text(b.grafo_estado))
        jsd = jensen_shannon_distance(a_tokens, b_tokens)
        agreement = max(0.0, 1.0 - jsd)
        stability = max(0.0, 1.0 - structural_delta_ratio(a.grafo_estado, b.grafo_estado))
        risk, blocking_alerts = self._risk_from_alerts(a, b)
        score = compute_score(
            agreement,
            stability,
            risk,
            a.confianza,
            b.confianza,
            tokens_fase,
            token_budget,
        )

        if score >= self.score_freeze_threshold:
            signal = ControlSignal.FREEZE_ADVANCE
        elif score >= self.score_converge_threshold:
            signal = ControlSignal.CONVERGE_CONDITIONAL
        else:
            signal = ControlSignal.ROLLBACK

        return EvalResult(
            score=score,
            signal=signal,
            reason="score_eval",
            bloqueantes=blocking_alerts,
        )


class ProviderModerator:
    """LLM-backed moderator. Falls back to deterministic moderation on parse errors."""

    def __init__(self, provider: InferenceProvider) -> None:
        self.provider = provider
        self.fallback = HeuristicModerator()

    def arbitrate(
        self,
        a: CompactAgentMessage,
        b: CompactAgentMessage,
        phase_id: int,
        iteration: int,
        tokens_fase: int,
        token_budget: int,
    ) -> EvalResult:
        payload = {
            "phase_id": phase_id,
            "iteration": iteration,
            "tokens_fase": tokens_fase,
            "token_budget": token_budget,
            "a_msg": a.model_dump(mode="json"),
            "b_msg": b.model_dump(mode="json"),
        }
        request = ProviderRequest(
            phase_id=phase_id,
            iteration=iteration,
            role="M",
            prompt_text=json.dumps(payload, sort_keys=True),
        )
        response = self.provider.complete(request)
        try:
            parsed = json.loads(response.raw_text)
            signal = ControlSignal(str(parsed.get("signal", ControlSignal.ROLLBACK.value)))
            return EvalResult(
                score=float(parsed.get("score", 0.0)),
                signal=signal,
                reason=str(parsed.get("reason", "provider_moderator")),
                bloqueantes=int(parsed.get("bloqueantes", 0)),
            )
        except Exception:
            fallback = self.fallback.arbitrate(a, b, phase_id, iteration, tokens_fase, token_budget)
            return EvalResult(
                score=fallback.score,
                signal=fallback.signal,
                reason="provider_moderator_fallback",
                bloqueantes=fallback.bloqueantes,
            )