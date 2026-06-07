from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from duetmind.analysis import assess_go_no_go
from duetmind.agents import build_default_agents, build_provider_agents
from duetmind.orchestrator import Orchestrator
from duetmind.pipeline import PhaseSpec, PipelineRunner
from duetmind.storage import Storage


def build_audit_handler(storage: Storage, api_key: str | None = None) -> type[BaseHTTPRequestHandler]:
    def _build_schedule(payload: dict[str, object], default_agent_mode: str) -> list[PhaseSpec] | None:
        raw_schedule = payload.get("schedule")
        if raw_schedule is None:
            return None
        if not isinstance(raw_schedule, list):
            raise ValueError("schedule must be a list")

        schedule: list[PhaseSpec] = []
        for item in raw_schedule:
            if not isinstance(item, dict):
                raise ValueError("schedule items must be objects")
            schedule.append(
                PhaseSpec(
                    phase_id=int(item.get("phase_id", 1)),
                    name=str(item.get("name", "Custom")),
                    environment=str(item.get("environment", "mock")),
                    max_iterations=int(item.get("max_iterations", 4)),
                    model_tier=str(item.get("model_tier", "custom")),
                    agent_mode=str(item.get("agent_mode", default_agent_mode)),
                )
            )
        return schedule

    class AuditHandler(BaseHTTPRequestHandler):
        def _is_authorized(self) -> bool:
            if api_key is None:
                return True
            header_key = self.headers.get("X-API-Key")
            return header_key == api_key

        def _write_json(self, status_code: int, payload: object) -> None:
            body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _require_auth(self) -> bool:
            if self._is_authorized():
                return True
            self._write_json(401, {"error": "unauthorized"})
            return False

        def _query_value(self, query: dict[str, list[str]], key: str) -> str | None:
            values = query.get(key)
            return values[0] if values else None

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if self.path != "/health" and not self._require_auth():
                return
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            phase_id_value = self._query_value(query, "phase_id")
            env_value = self._query_value(query, "environment")

            phase_id = int(phase_id_value) if phase_id_value is not None else None

            if parsed.path == "/health":
                self._write_json(200, {"status": "ok"})
                return

            if parsed.path in {"/history", "/phase-results"}:
                rows = storage.list_phase_results(phase_id=phase_id, environment=env_value)
                self._write_json(200, rows)
                return

            if parsed.path == "/telemetry":
                rows = storage.telemetry_summary(phase_id=phase_id)
                self._write_json(200, rows)
                return

            if parsed.path == "/snapshots":
                rows = storage.list_snapshots(phase_id=phase_id)
                self._write_json(200, rows)
                return

            if parsed.path == "/bundle":
                bundle = {
                    "phase_results": storage.list_phase_results(phase_id=phase_id, environment=env_value),
                    "telemetry": storage.telemetry_summary(phase_id=phase_id),
                    "snapshots": storage.list_snapshots(phase_id=phase_id),
                    "ledger": storage.list_ledger_blocks(phase_id=phase_id),
                }
                self._write_json(200, bundle)
                return

            if parsed.path == "/go-no-go":
                rows = storage.list_phase_results(phase_id=phase_id, environment=env_value)
                assessment = assess_go_no_go(rows)
                self._write_json(200, assessment.__dict__)
                return

            self._write_json(404, {"error": "not_found", "path": parsed.path})

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if not self._require_auth():
                return
            parsed = urlparse(self.path)
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length).decode("utf-8") if content_length else "{}"
            payload = json.loads(body or "{}")

            agent_mode = payload.get("agent_mode", "mock")
            if agent_mode == "provider":
                agent_a, agent_b = build_provider_agents()
            else:
                agent_a, agent_b = build_default_agents()

            orch = Orchestrator(storage, agent_a=agent_a, agent_b=agent_b)

            if parsed.path == "/run-phase":
                phase_id = int(payload.get("phase_id", 1))
                intent = str(payload.get("intent", "Construir sistema multiagente hibrido con bajo costo operativo"))
                result = orch.run_phase(phase_id, intent)
                self._write_json(
                    200,
                    {
                        "phase_id": phase_id,
                        "signal": result.signal.value,
                        "score": result.score,
                        "reason": result.reason,
                    },
                )
                return

            if parsed.path == "/run-all":
                intent = str(payload.get("intent", "Construir sistema multiagente hibrido con bajo costo operativo"))
                schedule = _build_schedule(payload, str(agent_mode))
                runner = PipelineRunner(orch, schedule=schedule)
                result = runner.run(intent)
                assessment = assess_go_no_go(storage.list_phase_results())
                self._write_json(
                    200,
                    {
                        "final_signal": result.final_signal,
                        "go_no_go": assessment.__dict__,
                        "phase_results": [
                            {
                                "phase_id": phase_spec.phase_id,
                                "environment": phase_spec.environment,
                                "agent_mode": phase_spec.agent_mode,
                                "signal": phase_result.signal.value,
                                "score": phase_result.score,
                                "reason": phase_result.reason,
                            }
                            for phase_spec, phase_result in result.phase_results
                        ],
                    },
                )
                return

            if parsed.path == "/export-bundle":
                export_path = str(payload.get("path", "audit-bundle.json"))
                phase_id = payload.get("phase_id")
                environment = payload.get("environment")
                phase_id_value = int(phase_id) if phase_id is not None else None
                storage.export_audit_bundle_json(
                    export_path,
                    phase_id=phase_id_value,
                    environment=environment,
                )
                self._write_json(
                    200,
                    {
                        "exported_bundle": export_path,
                        "phase_id": phase_id_value,
                        "environment": environment,
                    },
                )
                return

            self._write_json(404, {"error": "not_found", "path": parsed.path})

        def log_message(self, format: str, *args) -> None:  # noqa: A003, N802
            return

    return AuditHandler


def create_audit_server(
    storage: Storage,
    host: str = "127.0.0.1",
    port: int = 8000,
    api_key: str | None = None,
) -> ThreadingHTTPServer:
    handler = build_audit_handler(storage, api_key=api_key)
    return ThreadingHTTPServer((host, port), handler)


def serve_audit_api(
    storage: Storage,
    host: str = "127.0.0.1",
    port: int = 8000,
    api_key: str | None = None,
) -> None:
    server = create_audit_server(storage, host=host, port=port, api_key=api_key)
    try:
        server.serve_forever()
    finally:
        server.server_close()
