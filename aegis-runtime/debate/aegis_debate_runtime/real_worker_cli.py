from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from .mailbucket_package import write_debate_result_mailbucket_package
from .real_nested_codex import (
    audit_debate_worker_proofs,
    build_debate_worker_creation_requests,
    create_workers_via_mcp,
    expected_workers_from_creation_requests,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Strict real nested-Codex Debate Worker utilities.")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare-requests", help="Prepare one real worker creation request per candidate stance.")
    prepare.add_argument("--policy", required=True, help="Path to MODEL_REASONING_BUDGET_POLICY.yaml.")
    prepare.add_argument("--request", required=True, help="Path to Debate request JSON.")
    prepare.add_argument("--output-dir", required=True, help="Output directory for requests and expected proof manifest.")
    prepare.add_argument("--run-id", help="Optional fixed debate run id.")
    prepare.add_argument("--proof-dir", help="Optional proof directory. Defaults to <output-dir>/worker_proofs.")

    create = sub.add_parser("create-real", help="Create real nested-Codex workers through a standardized stdio MCP tool.")
    create.add_argument("--requests", required=True, help="Path to worker_creation_requests.json.")
    create.add_argument("--mcp-command", required=True, help='Command to start MCP server, e.g. "codex mcp-server".')
    create.add_argument("--mcp-tool", required=True, help="MCP tool name that creates a nested-Codex agent.")
    create.add_argument("--output", required=True, help="Path to write creation responses JSON.")
    create.add_argument("--timeout-seconds", type=float, default=90.0)

    audit = sub.add_parser("audit-proofs", help="Strictly audit real Debate Worker proof files. Missing proof fails.")
    audit.add_argument("--expected", required=True, help="Path to expected_worker_proofs.json.")
    audit.add_argument("--proof-dir", required=True, help="Directory containing worker proof JSON files.")
    audit.add_argument("--output", help="Optional path for audit summary JSON.")

    package = sub.add_parser("package-mailbucket", help="Write a Debate result mailbucket causal package.")
    package.add_argument("--final-report", required=True)
    package.add_argument("--adjudicator-state", required=True)
    package.add_argument("--worker-states", required=True, help="Directory containing worker state JSON files.")
    package.add_argument("--worker-proofs", help="Directory containing worker proof JSON files.")
    package.add_argument("--output-dir", required=True)

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    if args.command == "prepare-requests":
        request_data = _read_json(args.request)
        run_id = args.run_id or f"debate-run-{uuid4().hex}"
        output_dir = Path(args.output_dir)
        proof_dir = Path(args.proof_dir) if args.proof_dir else output_dir / "worker_proofs"
        output_dir.mkdir(parents=True, exist_ok=True)
        proof_dir.mkdir(parents=True, exist_ok=True)
        requests = build_debate_worker_creation_requests(
            policy_path=args.policy,
            debate_request=request_data,
            run_id=run_id,
            proof_dir=proof_dir,
        )
        request_payload = [item.to_dict() for item in requests]
        expected = expected_workers_from_creation_requests(requests)
        _write_json(output_dir / "worker_creation_requests.json", request_payload)
        _write_json(output_dir / "expected_worker_proofs.json", expected)
        prompt_dir = output_dir / "worker_prompts"
        prompt_dir.mkdir(exist_ok=True)
        for item in requests:
            (prompt_dir / f"{item.worker_id}.md").write_text(item.instructions, encoding="utf-8")
        _print({"status": "prepared", "run_id": run_id, "worker_count": len(requests), "output_dir": str(output_dir)})
        return

    if args.command == "create-real":
        request_dicts = _read_json(args.requests)
        from .real_nested_codex import DebateWorkerCreationRequest

        requests = [DebateWorkerCreationRequest(**item) for item in request_dicts]
        responses = create_workers_via_mcp(
            requests=requests,
            mcp_command=args.mcp_command,
            mcp_tool=args.mcp_tool,
            timeout_seconds=args.timeout_seconds,
        )
        payload = [item.to_dict() for item in responses]
        _write_json(args.output, payload)
        _print({"status": "created", "worker_count": len(payload), "output": args.output})
        return

    if args.command == "audit-proofs":
        expected = _read_json(args.expected)
        summary = audit_debate_worker_proofs(proof_dir=args.proof_dir, expected_workers=expected)
        if args.output:
            _write_json(args.output, summary)
        _print(summary)
        return

    if args.command == "package-mailbucket":
        final_report = _read_json(args.final_report)
        adjudicator_state = _read_json(args.adjudicator_state)
        worker_states = [_read_json(path) for path in sorted(Path(args.worker_states).glob("*.json"))]
        worker_proof_paths = None
        if args.worker_proofs:
            worker_proof_paths = sorted(Path(args.worker_proofs).glob("*_proof.json"))
        summary = write_debate_result_mailbucket_package(
            output_dir=args.output_dir,
            final_report=final_report,
            adjudicator_causal_state=adjudicator_state,
            worker_states=worker_states,
            worker_proof_paths=worker_proof_paths,
        )
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
