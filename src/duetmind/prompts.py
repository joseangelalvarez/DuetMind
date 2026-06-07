from __future__ import annotations

from dataclasses import dataclass

from duetmind.models import AgentId


@dataclass(frozen=True)
class PhasePromptTemplate:
    phase_id: int
    name: str
    objective: str
    constraints_a: tuple[str, ...]
    constraints_b: tuple[str, ...]

    def render(self, intent: str, agent_id: AgentId | None = None) -> str:
        if agent_id == AgentId.B:
            constraints = self.constraints_b
        else:
            constraints = self.constraints_a
        constraint_text = "\n".join(f"- {item}" for item in constraints)
        return (
            f"PHASE_ID={self.phase_id}\n"
            f"PHASE_NAME={self.name}\n"
            f"OBJECTIVE={self.objective}\n"
            f"USER_INTENT={intent}\n"
            f"CONSTRAINTS:\n{constraint_text}\n"
            f"OUTPUT_POLICY=JSON_COMPACT_ONLY"
        )


class PromptLibrary:
    def __init__(self) -> None:
        self.templates: dict[int, PhasePromptTemplate] = {
            1: PhasePromptTemplate(
                1,
                "Concepcion",
                "Definir el problema y alcance inicial",
                ("maximal clarity", "no overengineering"),
                ("threat model first", "question weak assumptions"),
            ),
            2: PhasePromptTemplate(
                2,
                "Concepcion",
                "Proponer modelo conceptual base",
                ("structured output", "no final decisions"),
                ("enforce controls", "minimize attack surface"),
            ),
            3: PhasePromptTemplate(
                3,
                "Concepcion",
                "Criticar el modelo conceptual",
                ("identify gaps", "no rewrite"),
                ("identify exploit paths", "insist on evidence"),
            ),
            4: PhasePromptTemplate(
                4,
                "Concepcion",
                "Refinar arquitectura conceptual",
                ("preserve invariants", "minimize ambiguity"),
                ("audit invariants", "trace every risk"),
            ),
            5: PhasePromptTemplate(
                5,
                "Arquitectura",
                "Incorporar restricciones fisicas",
                ("local first", "quantized where possible"),
                ("validate deployment boundaries", "zero trust defaults"),
            ),
            6: PhasePromptTemplate(
                6,
                "Arquitectura",
                "Optimizar protocolos y contratos",
                ("compact JSON", "schema strict"),
                ("explicit policy checks", "hard fail on contract drift"),
            ),
            7: PhasePromptTemplate(
                7,
                "Arquitectura",
                "Validar middleware y storage",
                ("no free text", "deterministic repair"),
                ("integrity by default", "log every anomaly"),
            ),
            8: PhasePromptTemplate(
                8,
                "Arquitectura",
                "Detectar deriva y loops",
                ("math first", "rollback on critical drift"),
                ("detect stealth regressions", "conservative arbitration"),
            ),
            9: PhasePromptTemplate(
                9,
                "Arquitectura",
                "Preparar score y guardrails",
                ("token budget", "cost aware"),
                ("safety budget", "auditability over speed"),
            ),
            10: PhasePromptTemplate(
                10,
                "Cierre",
                "Auditar excelencia tecnica",
                ("0-10 rubric", "blockers matter"),
                ("escalate unresolved blockers", "document residual risk"),
            ),
            11: PhasePromptTemplate(
                11,
                "Cierre",
                "Converger la version final",
                ("deterministic signal", "traceability"),
                ("evidence-backed sign-off", "no hidden assumptions"),
            ),
            12: PhasePromptTemplate(
                12,
                "Cierre",
                "Congelar y emitir handoff",
                ("semantic changelog", "backward compatibility"),
                ("security handoff", "compliance-ready artifacts"),
            ),
        }

    def for_phase(self, phase_id: int) -> PhasePromptTemplate:
        return self.templates[phase_id]

    def render(self, phase_id: int, intent: str, agent_id: AgentId | None = None) -> str:
        return self.for_phase(phase_id).render(intent, agent_id)
