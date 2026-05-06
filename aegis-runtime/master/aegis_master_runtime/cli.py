from __future__ import annotations

import argparse
import json
from pathlib import Path

from .leader_bootstrap import MasterTopLevelRuntime
from .mcp_client import NestedCodexMcpClient, RecordingNestedCodexClient


def _run(runtime: MasterTopLevelRuntime) -> dict:
    report = runtime.bootstrap()
    return report.to_dict()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aegis Master top-level nested-Codex bootstrap runtime.")
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
    elif args.command == "validate-recording":
        runtime = MasterTopLevelRuntime(
            policy_path=args.policy,
            nested_codex_client=RecordingNestedCodexClient(),
            private_root=args.output_dir,
            router_state_path=args.router_state,
        )
        report = _run(runtime)
    else:
        raise SystemExit(f"unknown command: {args.command}")

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


if __name__ == "__main__":
    main()
