from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import Request, urlopen
from dataclasses import dataclass
from typing import Callable, Protocol


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


TransportFn = Callable[[str, dict[str, object], float], dict[str, object]]


def _default_http_transport(url: str, payload: dict[str, object], timeout_s: float) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


class OllamaInferenceProvider:
    def __init__(
        self,
        *,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        provider_name: str = "ollama",
        timeout_s: float = 45.0,
        fallback_suffix: str = "provider_unavailable",
        transport: TransportFn | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.provider_name = provider_name
        self.timeout_s = timeout_s
        self.fallback_suffix = fallback_suffix
        self.transport = transport or _default_http_transport

    @staticmethod
    def _build_prompt(request: ProviderRequest) -> str:
        return (
            "Responde SOLO con JSON valido para CompactAgentMessage. "
            "No incluyas markdown ni texto adicional. "
            "Debe incluir: fase_id, iteracion, emisor, grafo_estado, alertas, confianza, telemetria.\n"
            f"Entrada:\n{request.prompt_text}"
        )

    def _fallback_message(self, request: ProviderRequest) -> ProviderResponse:
        agent_id = request.role if request.role in {"A", "B", "M"} else "A"
        payload = {
            "fase_id": request.phase_id,
            "iteracion": request.iteration,
            "emisor": agent_id,
            "grafo_estado": {
                "provider": self.provider_name,
                "role": request.role,
                "suffix": self.fallback_suffix,
                "status": "fallback",
            },
            "alertas": [],
            "confianza": 0.4,
            "telemetria": {
                "vram_actual_gb": 0.0,
                "tiempo_ejecucion_ms": 0,
                "tokens_consumidos": 0,
                "timeout_flag": False,
                "oom_flag": False,
            },
        }
        return ProviderResponse(raw_text=json.dumps(payload, sort_keys=True), provider_name=f"{self.provider_name}:fallback")

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        payload: dict[str, object] = {
            "model": self.model,
            "prompt": self._build_prompt(request),
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
        }

        try:
            data = self.transport(f"{self.base_url}/api/generate", payload, self.timeout_s)
            raw_text = str(data.get("response", "")).strip()
            if not raw_text:
                return self._fallback_message(request)
            return ProviderResponse(raw_text=raw_text, provider_name=self.provider_name)
        except (URLError, TimeoutError, ValueError, KeyError):
            return self._fallback_message(request)
        except Exception:
            return self._fallback_message(request)


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
