from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError


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
    sanitized = candidate.replace("'", '"')
    sanitized = re.sub(r"\\([^\"\\/bfnrtu])", r"\1", sanitized)
    return sanitized


def parse_with_layered_repair(raw_text: str, target_schema: type[BaseModel]) -> BaseModel:
    # Layer 1: direct parse
    candidate = _extract_json_block(raw_text)
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

    # Layer 3: lightweight sanitize fallback (still local in bootstrap)
    sanitized = _sanitize_json(candidate)
    return target_schema.model_validate_json(sanitized)


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
