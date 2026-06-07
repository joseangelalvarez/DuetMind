from __future__ import annotations

from dataclasses import dataclass

from duetmind.models import ControlSignal


GO_SIGNALS = {
    ControlSignal.FREEZE_ADVANCE.value,
    ControlSignal.CONVERGE_CONDITIONAL.value,
}

BLOCKING_SIGNALS = {
    ControlSignal.ABORT.value,
    ControlSignal.RESET_FROM_PROMPT_3.value,
    ControlSignal.CLOUD_ESC.value,
}


@dataclass(frozen=True)
class GoNoGoAssessment:
    decision: str
    can_analyze: bool
    coverage: float
    average_score: float
    minimum_score: float
    final_signal: str
    blocking_signals: list[str]
    reasons: list[str]


def assess_go_no_go(
    phase_results: list[dict[str, str | float | int]],
    expected_phases: int = 12,
    min_average_score: float = 7.5,
    min_final_score: float = 7.0,
) -> GoNoGoAssessment:
    if not phase_results:
        return GoNoGoAssessment(
            decision="NO_GO",
            can_analyze=False,
            coverage=0.0,
            average_score=0.0,
            minimum_score=0.0,
            final_signal="EMPTY",
            blocking_signals=[],
            reasons=["no_phase_results"],
        )

    scores = [float(row["score"]) for row in phase_results]
    signals = [str(row["signal"]) for row in phase_results]
    blocking_signals = [signal for signal in signals if signal in BLOCKING_SIGNALS]
    final_signal = signals[-1]
    average_score = sum(scores) / len(scores)
    minimum_score = min(scores)
    coverage = len(phase_results) / max(1, expected_phases)

    reasons: list[str] = []
    blocking_issue = bool(blocking_signals)
    quality_issue = average_score < min_average_score or minimum_score < min_final_score
    signal_issue = final_signal not in GO_SIGNALS
    incomplete_coverage = coverage < 1.0

    if blocking_issue:
        reasons.append("blocking_signal_detected")
    if incomplete_coverage:
        reasons.append("incomplete_phase_coverage")
    if average_score < min_average_score:
        reasons.append("average_score_below_threshold")
    if minimum_score < min_final_score:
        reasons.append("minimum_score_below_threshold")
    if signal_issue:
        reasons.append("final_signal_not_go")

    if blocking_issue or quality_issue or signal_issue:
        decision = "NO_GO"
    elif incomplete_coverage:
        decision = "GO_CONDICIONAL"
    else:
        decision = "GO"

    return GoNoGoAssessment(
        decision=decision,
        can_analyze=True,
        coverage=coverage,
        average_score=average_score,
        minimum_score=minimum_score,
        final_signal=final_signal,
        blocking_signals=blocking_signals,
        reasons=reasons,
    )