from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FsmState(str, Enum):
    INIT = "FASE_INICIALIZADA"
    DEBATE = "DEBATE_ACTIVO"
    EVAL = "EVALUACION_CONSENSO"
    ROLLBACK = "ROLLBACK_EJECUTADO"
    CLOUD_ESC = "ESCALADO_NUBE_EMERGENCIA"
    FREEZE = "FASE_CONGELADA"
    RESET = "REINICIO"
    ABORT = "ESCALA"


class FsmEvent(str, Enum):
    PHASE_END = "phase_end"


@dataclass
class TransitionDecision:
    next_state: FsmState
    reason: str


@dataclass
class CollisionInputs:
    timeout_or_oom: bool = False
    integrity_violation: bool = False
    ds_critical: bool = False
    loop_flag: bool = False


def resolve_collision_priority(ci: CollisionInputs) -> TransitionDecision | None:
    if ci.timeout_or_oom:
        return TransitionDecision(FsmState.CLOUD_ESC, "fallo_fisico_critico")
    if ci.integrity_violation:
        return TransitionDecision(FsmState.ABORT, "violacion_integridad_grafo")
    if ci.ds_critical:
        return TransitionDecision(FsmState.RESET, "deriva_semantica_critica")
    if ci.loop_flag:
        return TransitionDecision(FsmState.ROLLBACK, "estancamiento_circular")
    return None


def resolve_phase_transition(state: FsmState, event: FsmEvent) -> FsmState | None:
    # FREEZE is terminal only for the current phase; system-level execution returns to INIT.
    if state == FsmState.FREEZE and event == FsmEvent.PHASE_END:
        return FsmState.INIT
    return None
