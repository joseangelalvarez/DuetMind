from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from duetmind.middleware import parse_with_layered_repair
from duetmind.models import AgentId, CompactAgentMessage, TelemetryCycle
from duetmind.providers import InferenceProvider, ProviderRequest
from duetmind.prompts import PromptLibrary


@dataclass(frozen=True)
class AgentProfile:
    name: str
    role: str
    base_confidence: float
    tokens_per_call: int
    latency_ms: int
    proposal_suffix: str


class AgentAdapter(Protocol):
    def generate(
        self,
        phase_id: int,
        iteration: int,
        prev_graph: dict[str, str],
        user_intent: str,
    ) -> CompactAgentMessage: ...


class MockAgentAdapter:
    def __init__(self, agent_id: AgentId, profile: AgentProfile) -> None:
        self.agent_id = agent_id
        self.profile = profile

    def generate(
        self,
        phase_id: int,
        iteration: int,
        prev_graph: dict[str, str],
        user_intent: str,
    ) -> CompactAgentMessage:
        graph = dict(prev_graph)
        graph[f"phase_{phase_id}_iter_{iteration}"] = self.profile.proposal_suffix
        graph[f"phase_{phase_id}_iter_{iteration}_{self.agent_id.value}"] = self.profile.proposal_suffix
        graph["intent_anchor"] = user_intent
        return CompactAgentMessage(
            fase_id=phase_id,
            iteracion=iteration,
            emisor=self.agent_id,
            grafo_estado=graph,
            confianza=self.profile.base_confidence,
            alertas=[],
            telemetria=TelemetryCycle(
                tiempo_ejecucion_ms=self.profile.latency_ms,
                tokens_consumidos=self.profile.tokens_per_call,
            ),
        )


class ProviderAgentAdapter:
    def __init__(
        self,
        agent_id: AgentId,
        profile: AgentProfile,
        provider: InferenceProvider,
        prompt_library: PromptLibrary | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.profile = profile
        self.provider = provider
        self.prompt_library = prompt_library or PromptLibrary()

    def generate(
        self,
        phase_id: int,
        iteration: int,
        prev_graph: dict[str, str],
        user_intent: str,
    ) -> CompactAgentMessage:
        prompt_text = self.prompt_library.render(phase_id, user_intent)
        request = ProviderRequest(
            phase_id=phase_id,
            iteration=iteration,
            role=self.agent_id.value,
            prompt_text=prompt_text,
        )
        response = self.provider.complete(request)
        message = parse_with_layered_repair(response.raw_text, CompactAgentMessage)
        if message.emisor != self.agent_id:
            message.emisor = self.agent_id
        if not message.grafo_estado:
            message.grafo_estado = dict(prev_graph)
        message.grafo_estado.setdefault("intent_anchor", user_intent)
        return message


def build_default_agents() -> tuple[MockAgentAdapter, MockAgentAdapter]:
    agent_a = MockAgentAdapter(
        AgentId.A,
        AgentProfile(
            name="Pragmatic_YAGNI_Engineer",
            role="pragmatic",
            base_confidence=0.78,
            tokens_per_call=420,
            latency_ms=900,
            proposal_suffix="proposal_yagni",
        ),
    )
    agent_b = MockAgentAdapter(
        AgentId.B,
        AgentProfile(
            name="Enterprise_Architect_Security_Auditor",
            role="enterprise",
            base_confidence=0.81,
            tokens_per_call=390,
            latency_ms=850,
            proposal_suffix="audit_zero_trust",
        ),
    )
    return agent_a, agent_b


def build_provider_agents() -> tuple[ProviderAgentAdapter, ProviderAgentAdapter]:
    from duetmind.providers import StaticInferenceProvider

    provider_a = StaticInferenceProvider("local-static-a", "proposal_yagni")
    provider_b = StaticInferenceProvider("local-static-b", "audit_zero_trust")
    prompt_library = PromptLibrary()
    agent_a = ProviderAgentAdapter(
        AgentId.A,
        AgentProfile(
            name="Pragmatic_YAGNI_Engineer",
            role="pragmatic",
            base_confidence=0.78,
            tokens_per_call=420,
            latency_ms=900,
            proposal_suffix="proposal_yagni",
        ),
        provider_a,
        prompt_library,
    )
    agent_b = ProviderAgentAdapter(
        AgentId.B,
        AgentProfile(
            name="Enterprise_Architect_Security_Auditor",
            role="enterprise",
            base_confidence=0.81,
            tokens_per_call=390,
            latency_ms=850,
            proposal_suffix="audit_zero_trust",
        ),
        provider_b,
        prompt_library,
    )
    return agent_a, agent_b
