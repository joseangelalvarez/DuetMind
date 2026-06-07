from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class AgentId(str, Enum):
    A = "A"
    B = "B"
    M = "M"


class ControlSignal(str, Enum):
    FREEZE_ADVANCE = "CONGELAR_Y_AVANZAR"
    CONVERGE_CONDITIONAL = "CONVERGE_CONDICIONADO"
    ROLLBACK = "ROLLBACK"
    RESET_FROM_PROMPT_3 = "REINICIAR_DESDE_PROMPT_3"
    ABORT = "ESCALAR_A_HUMANO"
    CLOUD_ESC = "ESCALADO_NUBE_EMERGENCIA"


class TelemetryCycle(BaseModel):
    vram_actual_gb: float = Field(default=0.0, ge=0)
    tiempo_ejecucion_ms: int = Field(default=0, ge=0)
    tokens_consumidos: int = Field(default=0, ge=0)
    timeout_flag: bool = False
    oom_flag: bool = False


class DefensiveAlert(BaseModel):
    componente_id: str
    invariante_violada: Optional[str] = None
    gravedad_score: int = Field(ge=1, le=3)
    es_bloqueante: bool = False


class CompactAgentMessage(BaseModel):
    fase_id: int = Field(ge=1, le=12)
    iteracion: int = Field(ge=1)
    emisor: AgentId
    grafo_estado: Dict[str, str]
    alertas: List[DefensiveAlert] = Field(default_factory=list)
    confianza: float = Field(ge=0.0, le=1.0)
    telemetria: TelemetryCycle


class EvalInput(BaseModel):
    a_msg: CompactAgentMessage
    b_msg: CompactAgentMessage
    ds: float = Field(ge=0.0)
    loop_flag: bool = False
    jsd: float = Field(ge=0.0)
    tokens_fase: int = Field(ge=0)
    presupuesto_tokens_fase: int = Field(ge=1)


class EvalResult(BaseModel):
    score: float
    signal: ControlSignal
    reason: str
    bloqueantes: int = 0
