from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .real_leader import (
    FinalReviewLeaderCreationRequest,
    audit_final_review_leader_output,
    audit_final_review_leader_proof,
    build_final_review_leader_creation_request,
    create_final_review_leader_via_mcp,
    expected_final_review_leader_from_creation_request,
    load_json_object,
    write_json,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 21B real Final Review Leader utilities.")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare-request", help="Prepare the real Final Review Leader creation request.")
    prepare.add_argument("--policy", required=True, help="Path to MODEL_REASONING_BUDGET_POLICY.yaml.")
    prepare.add_argument("--phase21a-summary", required=True, help="Path to Phase 21A handoff-validation summary JSON.")
    prepare.add_argument("--phase21a-result", required=True, help="Path to Phase 21A final_review_result JSON.")
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--output-dir", required=True)
    prepare.add_argument("--proof-dir", help="Defaults to <output-dir>/final_review_leader_proofs.")
    prepare.add_argument("--leader-output-dir", help="Defaults to <output-dir>/final_review_leader_outputs.")

    create = sub.add_parser("create-real", help="Create the real Final Review Leader through a standardized stdio MCP tool.")
    create.add_argument("--request", required=True)
    create.add_argument("--mcp-command", required=True)
    create.add_argument("--mcp-tool", required=True)
    create.add_argument("--output", required=True)
    create.add_argument("--timeout-seconds", type=float, default=120.0)

    audit_proof = sub.add_parser("audit-proof", help="Strictly audit the Final Review Leader proof file.")
    audit_proof.add_argument("--expected", required=True)
    audit_proof.add_argument("--proof-dir", required=True)
    audit_proof.add_argument("--output")

    audit_output = sub.add_parser("audit-output", help="Strictly audit the Final Review Leader output file.")
    audit_output.add_argument("--expected", required=True)
    audit_output.add_argument("--leader-output-dir", required=True)
    audit_output.add_argument("--output")

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)

    if args.command == "prepare-request":
        output_dir = Path(args.output_dir)
        proof_dir = Path(args.proof_dir) if args.proof_dir else output_dir / "final_review_leader_proofs"
        leader_output_dir = Path(args.leader_output_dir) if args.leader_output_dir else output_dir / "final_review_leader_outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        proof_dir.mkdir(parents=True, exist_ok=True)
        leader_output_dir.mkdir(parents=True, exist_ok=True)

        request = build_final_review_leader_creation_request(
            policy_path=args.policy,
            phase21a_summary=load_json_object(args.phase21a_summary),
            phase21a_result=load_json_object(args.phase21a_result),
            run_id=args.run_id,
            proof_dir=proof_dir,
            output_dir=leader_output_dir,
        )
        expected = expected_final_review_leader_from_creation_request(request)
        request_path = output_dir / "final_review_leader_creation_request.json"
        expected_proof_path = output_dir / "expected_final_review_leader_proof.json"
        expected_output_path = output_dir / "expected_final_review_leader_output.json"
        prompt_path = output_dir / "final_review_leader_prompt.md"

        write_json(request_path, request.to_dict())
        write_json(expected_proof_path, expected)
        write_json(expected_output_path, expected)
        prompt_path.write_text(request.instructions, encoding="utf-8")
        _print(
            {
                "status": "prepared",
                "run_id": args.run_id,
                "leader_count": 1,
                "request": str(request_path),
                "expected_proof": str(expected_proof_path),
                "expected_output": str(expected_output_path),
                "prompt": str(prompt_path),
            }
        )
        return

    if args.command == "create-real":
        request_dict = load_json_object(args.request)
        request = FinalReviewLeaderCreationRequest(**request_dict)
        response = create_final_review_leader_via_mcp(
            request=request,
            mcp_command=args.mcp_command,
            mcp_tool=args.mcp_tool,
            timeout_seconds=args.timeout_seconds,
        )
        write_json(args.output, response.to_dict())
        _print({"status": "created", "leader_count": 1, "output": args.output})
        return

    if args.command == "audit-proof":
        expected = _read_json_list(args.expected)
        summary = audit_final_review_leader_proof(proof_dir=args.proof_dir, expected_leaders=expected)
        if args.output:
            write_json(args.output, summary)
        _print(summary)
        return

    if args.command == "audit-output":
        expected = _read_json_list(args.expected)
        summary = audit_final_review_leader_output(output_dir=args.leader_output_dir, expected_leaders=expected)
        if args.output:
            write_json(args.output, summary)
        _print(summary)
        return

    raise SystemExit(f"unknown command: {args.command}")


def _read_json_list(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise SystemExit(f"expected a JSON list of objects: {path}")
    return payload


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
