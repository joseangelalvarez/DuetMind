from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from typing import Callable

from duetmind.agents import AgentAdapter, build_default_agents, build_provider_agents
from duetmind.prompts import PromptLibrary
from duetmind.models import EvalResult
from duetmind.orchestrator import Orchestrator


@dataclass(frozen=True)
class PhaseSpec:
    phase_id: int
    name: str
    environment: str
    max_iterations: int
    model_tier: str
    agent_mode: str = "auto"


DEFAULT_PHASE_SCHEDULE: list[PhaseSpec] = [
    PhaseSpec(1, "Concepcion", "cloud", 4, "advanced"),
    PhaseSpec(2, "Concepcion", "cloud", 4, "advanced"),
    PhaseSpec(3, "Concepcion", "cloud", 4, "advanced"),
    PhaseSpec(4, "Concepcion", "cloud", 4, "advanced"),
    PhaseSpec(5, "Arquitectura", "local", 4, "quantized"),
    PhaseSpec(6, "Arquitectura", "local", 4, "quantized"),
    PhaseSpec(7, "Arquitectura", "local", 4, "quantized"),
    PhaseSpec(8, "Arquitectura", "local", 4, "quantized"),
    PhaseSpec(9, "Arquitectura", "local", 4, "quantized"),
    PhaseSpec(10, "Cierre", "cloud", 4, "audit"),
    PhaseSpec(11, "Cierre", "cloud", 4, "audit"),
    PhaseSpec(12, "Cierre", "cloud", 4, "audit"),
]


@dataclass
class PipelineResult:
    phase_results: list[tuple[PhaseSpec, EvalResult]]

    @property
    def final_signal(self) -> str:
        if not self.phase_results:
            return "EMPTY"
        return self.phase_results[-1][1].signal.value


class PipelineRunner:
    def __init__(
        self,
        orchestrator: Orchestrator,
        schedule: list[PhaseSpec] | None = None,
        agent_resolver: Callable[[PhaseSpec], tuple[AgentAdapter, AgentAdapter]] | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.schedule = schedule or DEFAULT_PHASE_SCHEDULE
        self.prompt_library = PromptLibrary()
        self.agent_resolver = agent_resolver or self._default_agent_resolver

    @staticmethod
    def _default_agent_resolver(phase: PhaseSpec) -> tuple[AgentAdapter, AgentAdapter]:
        if phase.agent_mode == "provider":
            return build_provider_agents()
        if phase.agent_mode == "mock":
            return build_default_agents()
        if phase.environment == "cloud":
            return build_provider_agents()
        return build_default_agents()

    def run(self, intent: str) -> PipelineResult:
        results: list[tuple[PhaseSpec, EvalResult]] = []
        for phase in self.schedule:
            agent_a, agent_b = self.agent_resolver(phase)
            phase_orchestrator = Orchestrator(
                self.orchestrator.storage,
                config=replace(self.orchestrator.config, imax=phase.max_iterations),
                agent_a=agent_a,
                agent_b=agent_b,
            )
            result = phase_orchestrator.run_phase(phase.phase_id, intent)
            results.append((phase, result))
            self.orchestrator.storage.save_phase_result(
                phase.phase_id,
                phase.name,
                phase.environment,
                phase.model_tier,
                result.signal.value,
                result.score,
                result.reason,
            )
            if result.signal.value in {"ESCALAR_A_HUMANO", "REINICIAR_DESDE_PROMPT_3"}:
                break
        return PipelineResult(results)
