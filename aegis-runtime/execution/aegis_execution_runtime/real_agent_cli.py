from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .real_agents import (
    ExecutionAgentCreationRequest,
    audit_execution_agent_outputs,
    audit_execution_agent_proofs,
    build_execution_agent_creation_requests,
    create_agents_via_mcp,
    expected_agents_from_creation_requests,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 19B real Execution Front/Back agent utilities.")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare-requests", help="Prepare real Front/Back creation requests from an execution package.")
    prepare.add_argument("--policy", required=True, help="Path to MODEL_REASONING_BUDGET_POLICY.yaml.")
    prepare.add_argument("--execution-package", required=True, help="Phase 19A execution_git_topology_report.json or handoff JSON.")
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--output-dir", required=True)
    prepare.add_argument("--proof-dir", help="Defaults to <output-dir>/agent_proofs.")
    prepare.add_argument("--agent-output-dir", help="Defaults to <output-dir>/agent_outputs.")

    create = sub.add_parser("create-real", help="Create real agents through a standardized stdio MCP tool.")
    create.add_argument("--requests", required=True)
    create.add_argument("--mcp-command", required=True)
    create.add_argument("--mcp-tool", required=True)
    create.add_argument("--output", required=True)
    create.add_argument("--timeout-seconds", type=float, default=90.0)

    audit_proofs = sub.add_parser("audit-proofs", help="Strictly audit Front/Back proof files.")
    audit_proofs.add_argument("--expected", required=True)
    audit_proofs.add_argument("--proof-dir", required=True)
    audit_proofs.add_argument("--output")

    audit_outputs = sub.add_parser("audit-outputs", help="Strictly audit Front/Back output files.")
    audit_outputs.add_argument("--expected", required=True)
    audit_outputs.add_argument("--agent-output-dir", required=True)
    audit_outputs.add_argument("--output")

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)

    if args.command == "prepare-requests":
        execution_package = _read_json(args.execution_package)
        output_dir = Path(args.output_dir)
        proof_dir = Path(args.proof_dir) if args.proof_dir else output_dir / "agent_proofs"
        agent_output_dir = Path(args.agent_output_dir) if args.agent_output_dir else output_dir / "agent_outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        proof_dir.mkdir(parents=True, exist_ok=True)
        agent_output_dir.mkdir(parents=True, exist_ok=True)

        requests = build_execution_agent_creation_requests(
            policy_path=args.policy,
            execution_package=execution_package,
            run_id=args.run_id,
            proof_dir=proof_dir,
            output_dir=agent_output_dir,
        )
        request_payload = [item.to_dict() for item in requests]
        expected = expected_agents_from_creation_requests(requests)

        _write_json(output_dir / "execution_agent_creation_requests.json", request_payload)
        _write_json(output_dir / "expected_execution_agent_proofs.json", expected)
        _write_json(output_dir / "expected_execution_agent_outputs.json", expected)

        prompt_dir = output_dir / "agent_prompts"
        prompt_dir.mkdir(exist_ok=True)
        for item in requests:
            (prompt_dir / f"{item.agent_id}.md").write_text(item.instructions, encoding="utf-8")

        _print({"status": "prepared", "run_id": args.run_id, "agent_count": len(requests), "output_dir": str(output_dir)})
        return

    if args.command == "create-real":
        request_dicts = _read_json(args.requests)
        requests = [ExecutionAgentCreationRequest(**item) for item in request_dicts]
        responses = create_agents_via_mcp(
            requests=requests,
            mcp_command=args.mcp_command,
            mcp_tool=args.mcp_tool,
            timeout_seconds=args.timeout_seconds,
        )
        payload = [item.to_dict() for item in responses]
        _write_json(args.output, payload)
        _print({"status": "created", "agent_count": len(payload), "output": args.output})
        return

    if args.command == "audit-proofs":
        expected = _read_json(args.expected)
        summary = audit_execution_agent_proofs(proof_dir=args.proof_dir, expected_agents=expected)
        if args.output:
            _write_json(args.output, summary)
        _print(summary)
        return

    if args.command == "audit-outputs":
        expected = _read_json(args.expected)
        summary = audit_execution_agent_outputs(output_dir=args.agent_output_dir, expected_agents=expected)
        if args.output:
            _write_json(args.output, summary)
        _print(summary)
        return

    raise SystemExit(f"unknown command: {args.command}")


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str | Path, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
