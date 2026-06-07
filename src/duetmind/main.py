from __future__ import annotations

import argparse
import json

from duetmind.analysis import assess_go_no_go
from duetmind.agents import build_default_agents, build_provider_agents
from duetmind.distribution import DistributionPlatform, build_distribution_manifest, prepare_distribution_staging, write_distribution_manifest
from duetmind.pipeline import PipelineRunner
from duetmind.orchestrator import Orchestrator
from duetmind.server import serve_audit_api
from duetmind.storage import Storage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DuetMind bootstrap orchestrator")
    parser.add_argument("--phase", type=int, default=1)
    parser.add_argument(
        "--intent",
        type=str,
        default="Construir sistema multiagente hibrido con bajo costo operativo",
    )
    parser.add_argument("--db", type=str, default="duetmind.db")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--run-all", action="store_true")
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--history-phase", type=int, default=None)
    parser.add_argument("--history-env", type=str, default=None)
    parser.add_argument("--history-json", action="store_true")
    parser.add_argument("--export-history", type=str, default=None)
    parser.add_argument("--export-bundle", type=str, default=None)
    parser.add_argument("--telemetry-summary", action="store_true")
    parser.add_argument("--go-no-go", action="store_true")
    parser.add_argument("--export-distribution-manifest", type=str, default=None)
    parser.add_argument("--prepare-distribution", type=str, default=None)
    parser.add_argument(
        "--distribution-platform",
        type=str,
        choices=("windows", "linux"),
        default="windows",
    )
    parser.add_argument("--serve-http", action="store_true")
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--api-key", type=str, default=None)
    parser.add_argument(
        "--agent-mode",
        type=str,
        choices=("mock", "provider"),
        default="mock",
        help="Select mock agents or provider-backed agents.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    distribution_platform = DistributionPlatform(args.distribution_platform)
    distribution_manifest = build_distribution_manifest(distribution_platform)

    if args.export_distribution_manifest:
        write_distribution_manifest(args.export_distribution_manifest, distribution_manifest)
        print(f"exported_distribution_manifest={args.export_distribution_manifest}")
        return

    if args.prepare_distribution:
        staging_root = prepare_distribution_staging(args.prepare_distribution, distribution_manifest)
        print(f"prepared_distribution={staging_root}")
        return

    storage = Storage(args.db)
    if args.agent_mode == "provider":
        agent_a, agent_b = build_provider_agents()
    else:
        agent_a, agent_b = build_default_agents()
    orch = Orchestrator(storage, agent_a=agent_a, agent_b=agent_b)

    print("=== DuetMind Result ===")

    if args.export_history:
        storage.export_phase_results_json(
            args.export_history,
            phase_id=args.history_phase,
            environment=args.history_env,
        )
        print(f"exported={args.export_history}")
        return

    if args.export_bundle:
        storage.export_audit_bundle_json(
            args.export_bundle,
            phase_id=args.history_phase,
            environment=args.history_env,
        )
        print(f"exported_bundle={args.export_bundle}")
        return

    if args.history:
        rows = storage.list_phase_results(phase_id=args.history_phase, environment=args.history_env)
        if args.history_json:
            print(json.dumps(rows, indent=2, sort_keys=True))
            return
        for row in rows:
            print(
                f"phase={row['phase_id']} env={row['environment']} tier={row['model_tier']} "
                f"signal={row['signal']} score={row['score']:.3f} reason={row['reason']}"
            )
        if not rows:
            print("history=empty")
        return

    if args.telemetry_summary:
        rows = storage.telemetry_summary(phase_id=args.history_phase)
        print(json.dumps(rows, indent=2, sort_keys=True))
        return

    if args.go_no_go:
        rows = storage.list_phase_results(phase_id=args.history_phase, environment=args.history_env)
        assessment = assess_go_no_go(rows)
        print(json.dumps(assessment.__dict__, indent=2, sort_keys=True))
        return

    if args.serve_http:
        print(f"serving_http=http://{args.host}:{args.port}")
        serve_audit_api(storage, host=args.host, port=args.port, api_key=args.api_key)
        return

    if args.run_all:
        runner = PipelineRunner(orch)
        result = runner.run(args.intent)
        for phase_spec, phase_result in result.phase_results:
            print(
                f"phase={phase_spec.phase_id} env={phase_spec.environment} signal={phase_result.signal.value} "
                f"score={phase_result.score:.3f} reason={phase_result.reason}"
            )
        print(f"final_signal={result.final_signal}")
        assessment = assess_go_no_go(storage.list_phase_results())
        print(json.dumps(assessment.__dict__, indent=2, sort_keys=True))
        print("phase_results_persisted=yes")
    else:
        result = orch.run_phase(args.phase, args.intent)
        print(f"phase={args.phase}")
        print(f"signal={result.signal.value}")
        print(f"score={result.score:.3f}")
        print(f"reason={result.reason}")


if __name__ == "__main__":
    main()
