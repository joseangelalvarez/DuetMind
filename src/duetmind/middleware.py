from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from duetmind.models import AgentId, CompactAgentMessage


def _micro_model_repair(candidate: str) -> str:
    """Optional ephemeral repair hook via DUETMIND_JSON_REPAIR_CMD executable."""
    command = os.getenv("DUETMIND_JSON_REPAIR_CMD", "").strip()
    if not command:
        return candidate
    try:
        completed = subprocess.run(
            [command],
            input=candidate,
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except Exception:
        return candidate
    repaired = (completed.stdout or "").strip()
    return repaired if repaired else candidate


def _extract_json_block(raw_text: str) -> str:
    start = raw_text.find("{")
    if start == -1:
        stripped = raw_text.strip()
        if stripped.startswith("{"):
            return stripped
        raise ValueError("payload sin estructura JSON")

    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(raw_text)):
        char = raw_text[idx]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return raw_text[start : idx + 1]
    return raw_text[start:].strip()


def _repair_truncation(candidate: str) -> str:
    txt = candidate.rstrip(". ")
    open_curly = txt.count("{") - txt.count("}")
    open_square = txt.count("[") - txt.count("]")
    if open_square > 0:
        txt += "]" * open_square
    if open_curly > 0:
        txt += "}" * open_curly
    return txt


def _sanitize_json(candidate: str) -> str:
    sanitized = re.sub(r"'([^'\\]*(?:\\.[^'\\]*)*)'\s*:", r'"\1":', candidate)
    sanitized = re.sub(r":\s*'([^'\\]*(?:\\.[^'\\]*)*)'", r': "\1"', sanitized)
    sanitized = re.sub(r"\\([^\"\\/bfnrtu])", r"\1", sanitized)
    return sanitized


def _build_sentinel_compact_message(
    *,
    phase_id: int,
    iteration: int,
    agent_id: AgentId | None,
) -> CompactAgentMessage:
    emitter = agent_id if agent_id is not None else AgentId.A
    return CompactAgentMessage.model_validate(
        {
            "fase_id": max(1, phase_id),
            "iteracion": max(1, iteration),
            "emisor": emitter,
            "grafo_estado": {"sentinel": "parse_failure"},
            "alertas": [
                {
                    "componente_id": "middleware",
                    "invariante_violada": "layered_parse_failure",
                    "gravedad_score": 3,
                    "es_bloqueante": True,
                }
            ],
            "confianza": 0.0,
            "telemetria": {
                "vram_actual_gb": 0.0,
                "tiempo_ejecucion_ms": 0,
                "tokens_consumidos": 0,
                "timeout_flag": False,
                "oom_flag": False,
            },
        }
    )


def parse_with_layered_repair(
    raw_text: str,
    target_schema: type[BaseModel],
    *,
    phase_id: int = 0,
    iteration: int = 0,
    agent_id: AgentId | None = None,
    layer3_repairer: Callable[[str], str] | None = None,
) -> BaseModel:
    # Layer 1: direct parse
    try:
        candidate = _extract_json_block(raw_text)
    except Exception:
        candidate = ""

    try:
        return target_schema.model_validate_json(candidate)
    except (ValidationError, ValueError, json.JSONDecodeError):
        pass

    # Layer 2: local heuristic repair
    try:
        repaired = _repair_truncation(candidate)
        return target_schema.model_validate_json(repaired)
    except (ValidationError, ValueError, json.JSONDecodeError):
        pass

    # Layer 3: optional micro-model repair, then lightweight sanitize fallback.
    repairer = layer3_repairer if callable(layer3_repairer) else _micro_model_repair
    try:
        micro_repaired = repairer(candidate)
        return target_schema.model_validate_json(micro_repaired)
    except (ValidationError, ValueError, json.JSONDecodeError):
        pass

    try:
        sanitized = _sanitize_json(candidate)
        return target_schema.model_validate_json(sanitized)
    except (ValidationError, ValueError, json.JSONDecodeError):
        pass

    # Layer 4: sentinel fallback must not throw.
    if target_schema is CompactAgentMessage:
        return _build_sentinel_compact_message(
            phase_id=phase_id,
            iteration=iteration,
            agent_id=agent_id,
        )

    return target_schema.model_construct()


def structural_delta_ratio(prev_state: dict[str, Any], new_state: dict[str, Any]) -> float:
    if not prev_state and not new_state:
        return 0.0

    prev_items = {key: json.dumps(value, sort_keys=True, separators=(",", ":")) for key, value in prev_state.items()}
    new_items = {key: json.dumps(value, sort_keys=True, separators=(",", ":")) for key, value in new_state.items()}

    all_keys = set(prev_items) | set(new_items)
    if not all_keys:
        return 0.0

    changed = sum(1 for key in all_keys if prev_items.get(key) != new_items.get(key))
    return changed / len(all_keys)
