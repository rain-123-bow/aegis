from __future__ import annotations

import argparse
import json
from pathlib import Path

from .leader_bootstrap import MasterTopLevelRuntime
from .mcp_client import NestedCodexMcpClient, RecordingNestedCodexClient
from .operational_skill import validate_master_operational_cycle_file


def _run(runtime: MasterTopLevelRuntime) -> dict:
    report = runtime.bootstrap()
    return report.to_dict()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aegis Master top-level runtime and operational skill validation.")
    sub = parser.add_subparsers(dest="command", required=True)

    real = sub.add_parser("validate-real", help="Call a real nested-codex MCP server and create top-level leaders.")
    real.add_argument("--policy", required=True, help="Path to MODEL_REASONING_BUDGET_POLICY.yaml.")
    real.add_argument("--router-state", required=True, help="Router JSON state path.")
    real.add_argument("--output-dir", required=True, help="Private output directory for bootstrap report.")
    real.add_argument("--mcp-command", required=True, help='Command to start nested-codex MCP server, e.g. "codex mcp-server".')
    real.add_argument("--mcp-tool", required=True, help="MCP tool name that creates a nested-codex agent.")
    real.add_argument("--timeout-seconds", type=float, default=90.0)

    test = sub.add_parser("validate-recording", help="Test-only local validation with recording client.")
    test.add_argument("--policy", required=True)
    test.add_argument("--router-state", required=True)
    test.add_argument("--output-dir", required=True)

    skill = sub.add_parser("validate-operational-skill", help="Validate one Master operational cycle against MASTER_OPERATIONAL_WORKFLOW_SKILL.")
    skill.add_argument("--cycle", required=True, help="Path to Master operational cycle JSON.")
    skill.add_argument("--skill", help="Optional path to MASTER_OPERATIONAL_WORKFLOW_SKILL.md.")
    skill.add_argument("--output", help="Optional output path for validation result JSON.")

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)

    if args.command == "validate-real":
        with NestedCodexMcpClient(args.mcp_command, args.mcp_tool, timeout_seconds=args.timeout_seconds) as client:
            runtime = MasterTopLevelRuntime(
                policy_path=args.policy,
                nested_codex_client=client,
                private_root=args.output_dir,
                router_state_path=args.router_state,
            )
            report = _run(runtime)
        print(
            json.dumps(
                {
                    "report_id": report["report_id"],
                    "status": report["status"],
                    "policy_version": report["policy_version"],
                    "created_agent_count": report["audit"]["created_agent_count"],
                    "route_checks": len(report["route_checks"]),
                    "report_path": str(Path(args.output_dir) / "top_level_bootstrap_report.json"),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.command == "validate-recording":
        runtime = MasterTopLevelRuntime(
            policy_path=args.policy,
            nested_codex_client=RecordingNestedCodexClient(),
            private_root=args.output_dir,
            router_state_path=args.router_state,
        )
        report = _run(runtime)
        print(
            json.dumps(
                {
                    "report_id": report["report_id"],
                    "status": report["status"],
                    "policy_version": report["policy_version"],
                    "created_agent_count": report["audit"]["created_agent_count"],
                    "route_checks": len(report["route_checks"]),
                    "report_path": str(Path(args.output_dir) / "top_level_bootstrap_report.json"),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.command == "validate-operational-skill":
        result = validate_master_operational_cycle_file(args.cycle, skill_path=args.skill).to_dict()
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return

    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
