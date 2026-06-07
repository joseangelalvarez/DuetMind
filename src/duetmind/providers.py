from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderRequest:
    phase_id: int
    iteration: int
    role: str
    prompt_text: str


@dataclass(frozen=True)
class ProviderResponse:
    raw_text: str
    provider_name: str


class InferenceProvider(Protocol):
    def complete(self, request: ProviderRequest) -> ProviderResponse: ...


class StaticInferenceProvider:
    def __init__(self, provider_name: str, suffix: str) -> None:
        self.provider_name = provider_name
        self.suffix = suffix

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        agent_id = request.role if request.role in {"A", "B", "M"} else "A"
        payload = {
            "fase_id": request.phase_id,
            "iteracion": request.iteration,
            "emisor": agent_id,
            "grafo_estado": {
                "provider": self.provider_name,
                "role": request.role,
                "suffix": self.suffix,
                "status": "ok",
            },
            "alertas": [],
            "confianza": 0.8,
            "telemetria": {
                "vram_actual_gb": 0.0,
                "tiempo_ejecucion_ms": 100,
                "tokens_consumidos": 64,
                "timeout_flag": False,
                "oom_flag": False,
            },
        }
        raw_text = json.dumps(payload, sort_keys=True)
        return ProviderResponse(raw_text=raw_text, provider_name=self.provider_name)
