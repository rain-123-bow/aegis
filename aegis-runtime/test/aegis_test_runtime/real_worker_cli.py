from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .real_workers import (
    TestWorkerCreationRequest,
    audit_test_worker_outputs,
    audit_test_worker_proofs,
    build_test_worker_creation_requests,
    create_test_workers_via_mcp,
    expected_workers_from_creation_requests,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 20B real Test Worker utilities.")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare-requests", help="Prepare real Test Worker creation requests.")
    prepare.add_argument("--policy", required=True, help="Path to MODEL_REASONING_BUDGET_POLICY.yaml.")
    prepare.add_argument("--validation-package", required=True, help="Phase 20A validation report/final result or handoff JSON.")
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--output-dir", required=True)
    prepare.add_argument("--proof-dir", help="Defaults to <output-dir>/test_worker_proofs.")
    prepare.add_argument("--worker-output-dir", help="Defaults to <output-dir>/test_worker_outputs.")

    create = sub.add_parser("create-real", help="Create real Test Workers through a standardized stdio MCP tool.")
    create.add_argument("--requests", required=True)
    create.add_argument("--mcp-command", required=True)
    create.add_argument("--mcp-tool", required=True)
    create.add_argument("--output", required=True)
    create.add_argument("--timeout-seconds", type=float, default=90.0)

    audit_proofs = sub.add_parser("audit-proofs", help="Strictly audit Test Worker proof files.")
    audit_proofs.add_argument("--expected", required=True)
    audit_proofs.add_argument("--proof-dir", required=True)
    audit_proofs.add_argument("--output")

    audit_outputs = sub.add_parser("audit-outputs", help="Strictly audit Test Worker output files.")
    audit_outputs.add_argument("--expected", required=True)
    audit_outputs.add_argument("--worker-output-dir", required=True)
    audit_outputs.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)

    if args.command == "prepare-requests":
        validation_package = _read_json(args.validation_package)
        output_dir = Path(args.output_dir)
        proof_dir = Path(args.proof_dir) if args.proof_dir else output_dir / "test_worker_proofs"
        worker_output_dir = Path(args.worker_output_dir) if args.worker_output_dir else output_dir / "test_worker_outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        proof_dir.mkdir(parents=True, exist_ok=True)
        worker_output_dir.mkdir(parents=True, exist_ok=True)
        requests = build_test_worker_creation_requests(
            policy_path=args.policy,
            validation_package=validation_package,
            run_id=args.run_id,
            proof_dir=proof_dir,
            output_dir=worker_output_dir,
        )
        request_payload = [item.to_dict() for item in requests]
        expected = expected_workers_from_creation_requests(requests)
        _write_json(output_dir / "test_worker_creation_requests.json", request_payload)
        _write_json(output_dir / "expected_test_worker_proofs.json", expected)
        _write_json(output_dir / "expected_test_worker_outputs.json", expected)
        prompt_dir = output_dir / "test_worker_prompts"
        prompt_dir.mkdir(exist_ok=True)
        for item in requests:
            (prompt_dir / f"{item.agent_id}.md").write_text(item.instructions, encoding="utf-8")
        _print({"status": "prepared", "run_id": args.run_id, "worker_count": len(requests), "output_dir": str(output_dir)})
        return

    if args.command == "create-real":
        request_dicts = _read_json(args.requests)
        requests = [TestWorkerCreationRequest(**item) for item in request_dicts]
        responses = create_test_workers_via_mcp(
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
        summary = audit_test_worker_proofs(proof_dir=args.proof_dir, expected_workers=expected)
        if args.output:
            _write_json(args.output, summary)
        _print(summary)
        return

    if args.command == "audit-outputs":
        expected = _read_json(args.expected)
        summary = audit_test_worker_outputs(output_dir=args.worker_output_dir, expected_workers=expected)
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
