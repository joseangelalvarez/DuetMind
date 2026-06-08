from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class SmokeSummary:
    health_ok: bool
    run_all_final_signal: str
    go_no_go_decision: str
    phase_results_count: int
    telemetry_count: int
    snapshots_count: int
    ledger_count: int


def _http_get_json(url: str, timeout: float = 60.0) -> object:
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_post_json(url: str, payload: dict[str, object], timeout: float = 120.0) -> object:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def run_smoke_e2e(base_url: str, *, intent: str, agent_mode: str = "mock") -> SmokeSummary:
    health = _http_get_json(f"{base_url}/health")
    health_ok = bool(isinstance(health, dict) and health.get("status") == "ok")

    run_all = _http_post_json(
        f"{base_url}/run-all",
        {
            "intent": intent,
            "agent_mode": agent_mode,
        },
    )
    go_no_go = _http_get_json(f"{base_url}/go-no-go")
    bundle = _http_get_json(f"{base_url}/bundle")

    return SmokeSummary(
        health_ok=health_ok,
        run_all_final_signal=str(run_all.get("final_signal", "")) if isinstance(run_all, dict) else "",
        go_no_go_decision=str(go_no_go.get("decision", "")) if isinstance(go_no_go, dict) else "",
        phase_results_count=len(bundle.get("phase_results", [])) if isinstance(bundle, dict) else 0,
        telemetry_count=len(bundle.get("telemetry", [])) if isinstance(bundle, dict) else 0,
        snapshots_count=len(bundle.get("snapshots", [])) if isinstance(bundle, dict) else 0,
        ledger_count=len(bundle.get("ledger", [])) if isinstance(bundle, dict) else 0,
    )
