from __future__ import annotations

import argparse
import json
from pathlib import Path

from .leader import ExecutionLeader
from .models import ExecutionRunState, FinalExecutionReport


def _default_failure_feedback(owner_id: str) -> dict:
    return {
        "feedback_id": "demo-test-failure-001",
        "result": "failed",
        "evidence_refs": ["demo-test-log:missing-summary"],
        "covered_scope": ["demo fixture output"],
        "owner_type": "group",
        "owner_id": owner_id,
        "required_fix": "Add missing final summary / rework note required by simulated Test feedback.",
        "why": "The first candidate intentionally exercises evidence-backed failure mapping and rework.",
    }


def _default_success_feedback() -> dict:
    return {
        "feedback_id": "demo-test-success-001",
        "result": "passed",
        "evidence_refs": ["demo-test-log:all-checks-passed"],
        "covered_scope": ["all demo subtasks", "integration candidate"],
        "owner_type": "none",
        "why": "The reworked integration candidate passed the simulated Test scope.",
    }


def run_demo(request_path: Path, output_dir: Path | None = None) -> dict:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    leader = ExecutionLeader(output_dir)
    state_or_report = leader.start_run(request)
    if isinstance(state_or_report, FinalExecutionReport):
        return state_or_report.to_dict()
    if not isinstance(state_or_report, ExecutionRunState):
        raise RuntimeError("unexpected Execution runtime result")

    target_group = state_or_report.groups[-1].group_id
    state_or_report = leader.handle_test_feedback(state_or_report, _default_failure_feedback(target_group))
    if isinstance(state_or_report, FinalExecutionReport):
        return state_or_report.to_dict()
    final_report = leader.handle_test_feedback(state_or_report, _default_success_feedback())
    if not isinstance(final_report, FinalExecutionReport):
        raise RuntimeError("demo did not reach final report")
    return final_report.to_dict()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Aegis Execution Department demo runtime.")
    parser.add_argument("--request", required=True, help="Path to an execution request JSON file.")
    parser.add_argument("--output-dir", default=None, help="Optional private runtime output directory.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    result = run_demo(Path(args.request), Path(args.output_dir) if args.output_dir else None)
    print(
        json.dumps(
            {
                "run_id": result["run_id"],
                "decision": result["decision"],
                "final_status": result["final_status"],
                "chain_id": result["execution_causal_chain"]["chain_id"],
                "final_report_path": result["artifact_paths"]["final_report"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
