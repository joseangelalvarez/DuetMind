from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any

from pydantic import BaseModel, ValidationError


def _extract_json_block(raw_text: str) -> str:
    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if match:
        return match.group(0)
    stripped = raw_text.strip()
    if stripped.startswith("{"):
        return stripped
    raise ValueError("payload sin estructura JSON")


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
    prev_txt = json.dumps(prev_state, sort_keys=True, separators=(",", ":"))
    new_txt = json.dumps(new_state, sort_keys=True, separators=(",", ":"))
    return 1.0 - SequenceMatcher(None, prev_txt, new_txt).ratio()
