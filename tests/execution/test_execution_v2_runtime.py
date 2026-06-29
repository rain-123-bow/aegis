from __future__ import annotations

from pathlib import Path

from aegis.modules.execution.graph import run_deterministic_execution
from aegis.modules.execution.models import ExecutionInputPackage, ExecutionOutputPackage


def make_project(root: Path) -> Path:
    (root / "code").mkdir(parents=True)
    (root / "knowledge").mkdir()
    (root / "causal").mkdir()
    return root


def write_valid_handoff(root: Path) -> Path:
    handoff = root / ".aegis" / "artifacts" / "master_handoff" / "handoff-1"
    handoff.mkdir(parents=True)
    (handoff / "README.md").write_text("Read this first.\n", encoding="utf-8", newline="\n")
    (handoff / "requirement_document.md").write_text(
        "Implement a local text summary helper.\n", encoding="utf-8", newline="\n"
    )
    (handoff / "requirement_review_document.md").write_text(
        "Requirement is accepted.\n", encoding="utf-8", newline="\n"
    )
    (handoff / "accepted_constraints.json").write_text("[]\n", encoding="utf-8", newline="\n")
    (handoff / "rejected_constraints.json").write_text("[]\n", encoding="utf-8", newline="\n")
    (handoff / "evidence_refs.json").write_text("[]\n", encoding="utf-8", newline="\n")
    (handoff / "known_limits.md").write_text("None.\n", encoding="utf-8", newline="\n")
    return handoff


def test_deterministic_execution_writes_terminal_output_package(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    handoff = write_valid_handoff(project)
    package = ExecutionInputPackage(
        run_id="run-terminal",
        project_root=project,
        code_root=project / "code",
        master_handoff_path=handoff,
    )

    output = run_deterministic_execution(package)

    assert isinstance(output, ExecutionOutputPackage)
    assert output.status == "completed"
    assert output.next_stage == "test_subgraph"
    assert output.implementation_artifact_ref is not None
    assert output.implementation_changeset_ref is not None
    assert output.simple_test_evidence_ref is not None
    assert output.execution_to_test_handoff_ref is not None
    assert output.boundary.wrote_causal_truth is False
    assert Path(output.evidence_index_ref.path).exists()


def test_deterministic_execution_blocks_incomplete_handoff(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    handoff = write_valid_handoff(project)
    (handoff / "README.md").unlink()
    package = ExecutionInputPackage(
        run_id="run-blocked",
        project_root=project,
        code_root=project / "code",
        master_handoff_path=handoff,
    )

    output = run_deterministic_execution(package)

    assert output.status == "blocked"
    assert output.next_stage == "master"
    assert output.blocker is not None


def test_review_changes_required_revises_plan_before_implementation(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    handoff = write_valid_handoff(project)
    package = ExecutionInputPackage(
        run_id="run-review-loop",
        project_root=project,
        code_root=project / "code",
        master_handoff_path=handoff,
        deterministic_review_sequence=[
            {
                "decision": "changes_required",
                "score": 80,
                "error_count": 1,
                "blocking_error": True,
                "explanation": "Plan needs a concrete validation path.",
                "required_change": "Add simple local validation evidence.",
            },
            {
                "decision": "approved",
                "score": 96,
                "warning_count": 1,
                "explanation": "Revised plan is bounded and testable.",
            },
        ],
    )

    output = run_deterministic_execution(package)

    assert output.status == "completed"
    assert output.next_stage == "test_subgraph"
    assert (project / "code" / "execution_result.txt").exists()
    round_2_plan = (
        project
        / ".aegis"
        / "artifacts"
        / "execution"
        / "run-review-loop"
        / "plans"
        / "round_02"
        / "implementation_plan.md"
    )
    assert round_2_plan.exists()


def test_review_request_debate_blocks_implementation_and_routes_to_debate(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    handoff = write_valid_handoff(project)
    package = ExecutionInputPackage(
        run_id="run-review-debate",
        project_root=project,
        code_root=project / "code",
        master_handoff_path=handoff,
        deterministic_review_sequence=[
            {
                "decision": "request_debate",
                "score": 70,
                "error_count": 1,
                "blocking_error": True,
                "explanation": "Two valid implementation plans remain non-dominated.",
                "required_change": "Request Debate adjudication before implementation.",
            }
        ],
    )

    output = run_deterministic_execution(package)

    assert output.status == "request_debate"
    assert output.next_stage == "debate"
    assert output.blocker is not None
    assert output.blocker.label == "requires_debate"
    assert not (project / "code" / "execution_result.txt").exists()


def test_max_review_rounds_blocks_without_implementation(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    handoff = write_valid_handoff(project)
    package = ExecutionInputPackage(
        run_id="run-max-rounds",
        project_root=project,
        code_root=project / "code",
        master_handoff_path=handoff,
        max_review_rounds=1,
        deterministic_review_sequence=[
            {
                "decision": "changes_required",
                "score": 80,
                "error_count": 1,
                "blocking_error": True,
                "explanation": "Still missing an implementation boundary.",
                "required_change": "Repair the plan.",
            }
        ],
    )

    output = run_deterministic_execution(package)

    assert output.status == "blocked"
    assert output.blocker is not None
    assert output.blocker.label == "max_review_rounds_exceeded"
    assert not (project / "code" / "execution_result.txt").exists()


def test_risky_planned_command_blocks_before_implementation(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    handoff = write_valid_handoff(project)
    package = ExecutionInputPackage(
        run_id="run-risky-command",
        project_root=project,
        code_root=project / "code",
        master_handoff_path=handoff,
        planned_shell_commands=["git push origin HEAD"],
    )

    output = run_deterministic_execution(package)

    assert output.status == "blocked"
    assert output.blocker is not None
    assert output.blocker.label == "unsafe_tool_request"
    assert not (project / "code" / "execution_result.txt").exists()


def test_simple_test_failure_blocks_completed_output(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    handoff = write_valid_handoff(project)
    package = ExecutionInputPackage(
        run_id="run-simple-test-failure",
        project_root=project,
        code_root=project / "code",
        master_handoff_path=handoff,
        simple_test_plan=[
            {
                "command_id": "missing-file-check",
                "command": "aegis:non_empty_file missing.txt",
                "timeout_seconds": 10,
                "allowed_by_approved_plan": True,
            }
        ],
    )

    output = run_deterministic_execution(package)

    assert output.status == "blocked"
    assert output.blocker is not None
    assert output.blocker.label == "missing_required_evidence"


def test_unapproved_simple_test_command_blocks_before_completion(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    handoff = write_valid_handoff(project)
    package = ExecutionInputPackage(
        run_id="run-unapproved-test-command",
        project_root=project,
        code_root=project / "code",
        master_handoff_path=handoff,
        simple_test_plan=[
            {
                "command_id": "unapproved-check",
                "command": "aegis:non_empty_file execution_result.txt",
                "timeout_seconds": 10,
                "allowed_by_approved_plan": False,
            }
        ],
    )

    output = run_deterministic_execution(package)

    assert output.status == "blocked"
    assert output.blocker is not None
    assert output.blocker.label == "unsafe_tool_request"


def test_simple_test_timeout_blocks_completed_output(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    handoff = write_valid_handoff(project)
    package = ExecutionInputPackage(
        run_id="run-simple-test-timeout",
        project_root=project,
        code_root=project / "code",
        master_handoff_path=handoff,
        simple_test_plan=[
            {
                "command_id": "timeout-check",
                "command": "aegis:sleep 2",
                "timeout_seconds": 1,
                "allowed_by_approved_plan": True,
            }
        ],
    )

    output = run_deterministic_execution(package)

    assert output.status == "blocked"
    assert output.blocker is not None
    assert output.blocker.label == "missing_required_evidence"
