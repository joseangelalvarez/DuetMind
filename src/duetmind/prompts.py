from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PhasePromptTemplate:
    phase_id: int
    name: str
    objective: str
    constraints: tuple[str, ...]

    def render(self, intent: str) -> str:
        constraint_text = "\n".join(f"- {item}" for item in self.constraints)
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
            1: PhasePromptTemplate(1, "Concepcion", "Definir el problema y alcance inicial", ("maximal clarity", "no overengineering")),
            2: PhasePromptTemplate(2, "Concepcion", "Proponer modelo conceptual base", ("structured output", "no final decisions")),
            3: PhasePromptTemplate(3, "Concepcion", "Criticar el modelo conceptual", ("identify gaps", "no rewrite")),
            4: PhasePromptTemplate(4, "Concepcion", "Refinar arquitectura conceptual", ("preserve invariants", "minimize ambiguity")),
            5: PhasePromptTemplate(5, "Arquitectura", "Incorporar restricciones fisicas", ("local first", "quantized where possible")),
            6: PhasePromptTemplate(6, "Arquitectura", "Optimizar protocolos y contratos", ("compact JSON", "schema strict")),
            7: PhasePromptTemplate(7, "Arquitectura", "Validar middleware y storage", ("no free text", "deterministic repair")),
            8: PhasePromptTemplate(8, "Arquitectura", "Detectar deriva y loops", ("math first", "rollback on critical drift")),
            9: PhasePromptTemplate(9, "Arquitectura", "Preparar score y guardrails", ("token budget", "cost aware")),
            10: PhasePromptTemplate(10, "Cierre", "Auditar excelencia tecnica", ("0-10 rubric", "blockers matter")),
            11: PhasePromptTemplate(11, "Cierre", "Converger la version final", ("deterministic signal", "traceability")),
            12: PhasePromptTemplate(12, "Cierre", "Congelar y emitir handoff", ("semantic changelog", "backward compatibility")),
        }

    def for_phase(self, phase_id: int) -> PhasePromptTemplate:
        return self.templates[phase_id]

    def render(self, phase_id: int, intent: str) -> str:
        return self.for_phase(phase_id).render(intent)
