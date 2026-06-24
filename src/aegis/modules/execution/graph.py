"""LangGraph builder and deterministic Execution Subgraph v2 runtime."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from aegis.modules.execution.artifacts import ExecutionArtifactWriter
from aegis.modules.execution.changeset import (
    diff_code_tree_snapshots,
    scan_code_tree,
    validate_implementation_changeset,
)
from aegis.modules.execution.input_validation import validate_master_handoff
from aegis.modules.execution.models import (
    ArtifactRef,
    DeterministicReviewOutcome,
    ExecutionBoundaryFlags,
    ExecutionCausalCandidate,
    ExecutionCausalCandidateNode,
    ExecutionCausalCandidateWriteResult,
    ExecutionCausalDependencyGroup,
    ExecutionInputPackage,
    ExecutionInputValidation,
    ExecutionNodeResult,
    ExecutionOutputPackage,
    ExecutionToTestHandoff,
    ExpectedFileChange,
    ImplementationChangeSet,
    ReviewBaseline,
    ReviewIssue,
    ReviewScorecard,
    SimpleTestCommandSpec,
    SimpleTestCommandEvidence,
    SimpleTestEvidence,
)
from aegis.modules.execution.store_binding import bind_execution_project
from aegis.modules.execution.tool_policy import analyze_shell_command


class ExecutionGraphState(TypedDict, total=False):
    """JSON-safe state for Execution Subgraph v2."""

    input_package: dict[str, Any]
    binding: dict[str, Any]
    input_validation: dict[str, Any]
    input_validation_ref: dict[str, Any]
    review_baseline: dict[str, Any]
    review_baseline_ref: dict[str, Any]
    plan_ref: dict[str, Any]
    expected_changes: list[dict[str, Any]]
    expected_changes_ref: dict[str, Any]
    requirement_mapping_ref: dict[str, Any]
    review_scorecard: dict[str, Any]
    review_ref: dict[str, Any]
    approved_review_ref: dict[str, Any]
    review_round: int
    approval_decision: str
    implementation_artifact_ref: dict[str, Any]
    implementation_changeset_ref: dict[str, Any]
    changed_files_ref: dict[str, Any]
    known_limits_ref: dict[str, Any]
    simple_test_evidence_ref: dict[str, Any]
    causal_candidate_ref: dict[str, Any]
    causal_candidate_write_result_ref: dict[str, Any]
    execution_to_test_handoff_ref: dict[str, Any]
    output_package: dict[str, Any]
    blocker: dict[str, Any]
    terminal_status: str


def build_execution_subgraph():
    """Build the standalone deterministic Execution Subgraph."""

    builder = StateGraph(ExecutionGraphState)
    builder.add_node("input_validation", _input_validation_node)
    builder.add_node("review_baseline", _review_baseline_node)
    builder.add_node("planning", _planning_node)
    builder.add_node("review", _review_node)
    builder.add_node("approval_gate", _approval_gate_node)
    builder.add_node("implementation_write_gate", _implementation_write_gate_node)
    builder.add_node("implement", _implement_node)
    builder.add_node("simple_tests", _simple_tests_node)
    builder.add_node("candidate_build", _candidate_build_node)
    builder.add_node("closeout", _closeout_node)
    builder.add_edge(START, "input_validation")
    builder.add_conditional_edges(
        "input_validation",
        _route_after_input_validation,
        {"continue": "review_baseline", "closeout": "closeout"},
    )
    builder.add_edge("review_baseline", "planning")
    builder.add_edge("planning", "review")
    builder.add_edge("review", "approval_gate")
    builder.add_conditional_edges(
        "approval_gate",
        _route_after_approval_gate,
        {"implement": "implementation_write_gate", "revise": "planning", "closeout": "closeout"},
    )
    builder.add_conditional_edges(
        "implementation_write_gate",
        _route_after_write_gate,
        {"implement": "implement", "closeout": "closeout"},
    )
    builder.add_edge("implement", "simple_tests")
    builder.add_conditional_edges(
        "simple_tests",
        _route_after_simple_tests,
        {"candidate": "candidate_build", "closeout": "closeout"},
    )
    builder.add_edge("candidate_build", "closeout")
    builder.add_edge("closeout", END)
    return builder.compile()


def run_deterministic_execution(package: ExecutionInputPackage) -> ExecutionOutputPackage:
    """Run the deterministic Execution Subgraph and return its output package."""

    result = build_execution_subgraph().invoke({"input_package": package.model_dump(mode="json")})
    return ExecutionOutputPackage.model_validate(result["output_package"])


def _input_validation_node(state: ExecutionGraphState) -> ExecutionGraphState:
    package = ExecutionInputPackage.model_validate(state["input_package"])
    binding = bind_execution_project(
        package.project_root,
        run_id=package.run_id,
        code_root=package.code_root,
    )
    writer = ExecutionArtifactWriter(binding)
    validation = validate_master_handoff(
        master_handoff_path=package.master_handoff_path,
        master_handoff_ref=None,
        writer=writer,
    )
    validation_ref = writer.file_ref(
        writer.artifact_dir("input_validation") / "execution_input_validation.json",
        "input_validation",
        created_by_node="input_validation",
    )
    _write_node_result(writer, "input_validation", [validation_ref], {"input_validation": validation})
    update: ExecutionGraphState = {
        "binding": binding.model_dump(mode="json"),
        "input_validation": validation.model_dump(mode="json"),
        "input_validation_ref": validation_ref.model_dump(mode="json"),
    }
    if validation.status == "blocked":
        update["terminal_status"] = "blocked"
        update["blocker"] = validation.blocker.model_dump(mode="json") if validation.blocker else {}
    return update


def _review_baseline_node(state: ExecutionGraphState) -> ExecutionGraphState:
    if _is_terminal(state):
        return {}
    package, _binding, writer = _runtime_parts(state)
    baseline_dir = writer.artifact_dir("review_baseline")
    writer.write_text(baseline_dir / "README.md", "Review baseline artifact.\n", "baseline_readme")
    understanding = writer.write_text(
        baseline_dir / "independent_requirement_understanding.md",
        "The Review Node independently reads the Master handoff before reviewing plans.\n",
        "requirement_understanding",
    )
    criteria = writer.write_json(
        baseline_dir / "review_criteria.json",
        {
            "score_threshold": 95,
            "error_blocks": True,
            "warning_blocks": False,
            "source_handoff": str(package.master_handoff_path),
        },
        "review_criteria",
    )
    hard_constraints = writer.write_json(
        baseline_dir / "hard_constraints_summary.json",
        [],
        "hard_constraints_summary",
    )
    non_goals = writer.write_text(
        baseline_dir / "non_goals_summary.md",
        "No out-of-scope implementation may be required by Review.\n",
        "non_goals_summary",
    )
    baseline = ReviewBaseline(
        baseline_id=f"{package.run_id}-review-baseline",
        requirement_understanding_ref=understanding,
        review_criteria_ref=criteria,
        hard_constraints_summary_ref=hard_constraints,
        non_goals_summary_ref=non_goals,
    )
    baseline_ref = writer.write_json(
        baseline_dir / "review_baseline.json",
        baseline,
        "review_baseline",
    )
    _write_node_result(writer, "review_baseline", [baseline_ref], {"review_baseline": baseline})
    return {
        "review_baseline": baseline.model_dump(mode="json"),
        "review_baseline_ref": baseline_ref.model_dump(mode="json"),
    }


def _planning_node(state: ExecutionGraphState) -> ExecutionGraphState:
    if _is_terminal(state):
        return {}
    package, _binding, writer = _runtime_parts(state)
    round_number = int(state.get("review_round", 1) or 1)
    plan_dir = writer.artifact_dir(f"plans/round_{round_number:02d}")
    writer.write_text(plan_dir / "README.md", "Execution plan artifact. Read implementation_plan.md first.\n", "plan_readme")
    plan_ref = writer.write_text(
        plan_dir / "implementation_plan.md",
        (
            "# Implementation Plan\n\n"
            "Implement a deterministic local artifact under code_root after review approval.\n"
            "No remote publication, no truth-store mutation, no Front/Back/Group creation.\n"
            f"\nReview round: {round_number}.\n"
        ),
        "implementation_plan",
    )
    requirement_mapping_ref = writer.write_json(
        plan_dir / "requirement_mapping.json",
        [{"requirement_ref": "REQ-1", "plan_ref": "PLAN-1"}],
        "requirement_mapping",
    )
    writer.write_text(plan_dir / "risk_assessment.md", "No external side effects.\n", "risk_assessment")
    writer.write_json(
        plan_dir / "tool_plan.json",
        [{"tool": "local_file_write", "side_effect": "local_write"}],
        "tool_plan",
    )
    expected = [
        ExpectedFileChange(
            change_id="chg-implementation-result",
            path="execution_result.txt",
            allowed_change_types=["added", "modified"],
            requirement_refs=["REQ-1"],
            rationale="Write deterministic execution result artifact into code_root.",
        )
    ]
    expected_ref = writer.write_json(
        plan_dir / "expected_file_changes.json",
        [item.model_dump(mode="json") for item in expected],
        "expected_file_changes",
    )
    writer.write_text(
        plan_dir / "expected_file_changes.md",
        "- execution_result.txt: deterministic execution result.\n",
        "expected_file_changes_md",
    )
    writer.write_text(
        plan_dir / "simple_test_plan.md",
        "Verify execution_result.txt exists and is non-empty.\n",
        "simple_test_plan",
    )
    _write_node_result(writer, "planning", [plan_ref, expected_ref], {"plan_ref": plan_ref})
    return {
        "review_round": round_number,
        "plan_ref": plan_ref.model_dump(mode="json"),
        "expected_changes": [item.model_dump(mode="json") for item in expected],
        "expected_changes_ref": expected_ref.model_dump(mode="json"),
        "requirement_mapping_ref": requirement_mapping_ref.model_dump(mode="json"),
    }


def _review_node(state: ExecutionGraphState) -> ExecutionGraphState:
    if _is_terminal(state):
        return {}
    package, _binding, writer = _runtime_parts(state)
    baseline_ref = ArtifactRef.model_validate(state["review_baseline_ref"])
    round_number = int(state.get("review_round", 1) or 1)
    review_dir = writer.artifact_dir(f"reviews/round_{round_number:02d}")
    writer.write_text(review_dir / "README.md", "Review artifact. Read scorecard.json first.\n", "review_readme")
    outcome = _review_outcome_for_round(package, round_number)
    writer.write_text(
        review_dir / "review_opinion.md",
        outcome.explanation + "\n",
        "review_opinion",
    )
    writer.write_text(
        review_dir / "blocking_errors.md",
        ("Blocking error present.\n" if outcome.error_count else "None.\n"),
        "blocking_errors",
    )
    writer.write_text(
        review_dir / "warnings.md",
        ("Warning recorded.\n" if outcome.warning_count else "None.\n"),
        "warnings",
    )
    writer.write_text(
        review_dir / "required_changes.md",
        (outcome.required_change or "None.") + "\n",
        "required_changes",
    )
    review_ref = writer.file_ref(review_dir / "review_opinion.md", "review", created_by_node="review")
    blocking_issues: list[ReviewIssue] = []
    if outcome.error_count:
        blocking_issues.append(
            ReviewIssue(
                issue_id=f"review-round-{round_number}-error",
                severity="error",
                requirement_refs=["REQ-1"],
                evidence_refs=[str(package.master_handoff_path)],
                explanation=outcome.explanation,
                required_change=outcome.required_change,
                blocking=True,
            )
        )
    non_blocking_issues: list[ReviewIssue] = []
    if outcome.warning_count:
        non_blocking_issues.append(
            ReviewIssue(
                issue_id=f"review-round-{round_number}-warning",
                severity="warning",
                requirement_refs=["REQ-1"],
                evidence_refs=[str(package.master_handoff_path)],
                explanation=outcome.explanation,
                required_change=outcome.required_change,
                blocking=False,
            )
        )
    scorecard = ReviewScorecard(
        decision=outcome.decision,
        score=outcome.score,
        dimensions={
            "requirements": 20,
            "constraints": 20,
            "first_principles": 15,
            "simplicity": 15,
            "maintainability": 10,
            "testability": 10,
            "risk": 4,
            "tool_side_effects": 4,
        },
        error_count=outcome.error_count,
        warning_count=outcome.warning_count,
        suggestion_count=outcome.suggestion_count,
        blocking_issues=blocking_issues,
        non_blocking_issues=non_blocking_issues,
        baseline_ref=baseline_ref,
        review_artifact_ref=review_ref,
    )
    scorecard_ref = writer.write_json(review_dir / "scorecard.json", scorecard, "scorecard")
    _write_node_result(writer, "review", [scorecard_ref], {"review_scorecard": scorecard})
    return {
        "review_scorecard": scorecard.model_dump(mode="json"),
        "review_ref": review_ref.model_dump(mode="json"),
    }


def _approval_gate_node(state: ExecutionGraphState) -> ExecutionGraphState:
    if _is_terminal(state):
        return {}
    _package, _binding, writer = _runtime_parts(state)
    scorecard = ReviewScorecard.model_validate(state["review_scorecard"])
    package = ExecutionInputPackage.model_validate(state["input_package"])
    round_number = int(state.get("review_round", 1) or 1)
    if scorecard.decision == "request_debate":
        return {
            "terminal_status": "request_debate",
            "approval_decision": "closeout",
            "blocker": {
                "label": "requires_debate",
                "reason": "review requested Debate before implementation",
                "evidence_refs": [scorecard.review_artifact_ref.path],
                "next_action": "debate",
                "parent_route_label": "execution",
                "retry_allowed": True,
            },
        }
    if scorecard.decision == "blocked":
        return {
            "terminal_status": "blocked",
            "approval_decision": "closeout",
            "blocker": {
                "label": "plan_not_approved",
                "reason": "review blocked the plan",
                "next_action": "master",
                "parent_route_label": "master",
                "retry_allowed": True,
            },
        }
    if scorecard.decision == "changes_required":
        if round_number >= package.max_review_rounds:
            return {
                "terminal_status": "blocked",
                "approval_decision": "closeout",
                "blocker": {
                    "label": "max_review_rounds_exceeded",
                    "reason": "review still requires changes after max_review_rounds",
                    "evidence_refs": [scorecard.review_artifact_ref.path],
                    "next_action": "master",
                    "parent_route_label": "master",
                    "retry_allowed": True,
                },
            }
        return {
            "review_round": round_number + 1,
            "approval_decision": "revise",
        }
    approval_dir = writer.artifact_dir("approval/round_01")
    writer.write_text(approval_dir / "README.md", "Approved review artifact.\n", "approval_readme")
    approval_ref = writer.write_text(
        approval_dir / "approval.md",
        "Plan approved. Execution Node may enter implementation mode.\n",
        "approval",
    )
    writer.write_json(approval_dir / "scorecard.json", scorecard, "approval_scorecard")
    writer.write_text(approval_dir / "accepted_warnings.md", "None.\n", "accepted_warnings")
    writer.write_text(
        approval_dir / "implementation_conditions.md",
        "Stay within expected_file_changes.json and code_root.\n",
        "implementation_conditions",
    )
    _write_node_result(writer, "approval_gate", [approval_ref], {"approved_review_ref": approval_ref})
    return {
        "approval_decision": "approved",
        "approved_review_ref": approval_ref.model_dump(mode="json"),
    }


def _implementation_write_gate_node(state: ExecutionGraphState) -> ExecutionGraphState:
    if _is_terminal(state):
        return {}
    _package, _binding, writer = _runtime_parts(state)
    package = ExecutionInputPackage.model_validate(state["input_package"])
    planned_commands = package.planned_shell_commands or ["python -m pytest"]
    commands = [
        analyze_shell_command(
            f"cmd-{index + 1}",
            command,
            cwd=str(_binding_path(state, "code_root")),
            project_root=str(_binding_path(state, "project_root")),
            allowed_by_approved_plan=True,
        )
        for index, command in enumerate(planned_commands)
    ]
    gate_dir = writer.artifact_dir("tool_audit")
    writer.write_text(gate_dir / "README.md", "Tool governance and command safety artifacts.\n", "tool_audit_readme")
    command_ref = writer.write_json(
        gate_dir / "command_safety_analysis.jsonl",
        [command.model_dump(mode="json") for command in commands],
        "command_safety",
    )
    writer.write_json(
        gate_dir / "tool_action_plan.json",
        [{"action_id": "write-local-result", "side_effect_level": "local_write"}],
        "tool_action_plan",
    )
    writer.write_json(gate_dir / "tool_execution_records.jsonl", [], "tool_execution_records")
    blocked = [
        command.model_dump(mode="json")
        for command in commands
        if command.requires_interrupt or not command.allowed_by_approved_plan
    ]
    writer.write_json(gate_dir / "blocked_actions.json", blocked, "blocked_actions")
    _write_node_result(writer, "implementation_write_gate", [command_ref], {"commands": commands})
    if blocked:
        return {
            "terminal_status": "blocked",
            "blocker": {
                "label": "unsafe_tool_request",
                "reason": "planned command requires interrupt or is outside approved plan",
                "evidence_refs": [str(gate_dir / "blocked_actions.json")],
                "next_action": "developer_input",
                "parent_route_label": "execution",
                "retry_allowed": True,
            },
        }
    return {}


def _implement_node(state: ExecutionGraphState) -> ExecutionGraphState:
    if _is_terminal(state):
        return {}
    package, binding, writer = _runtime_parts(state)
    code_root = Path(binding["code_root"]).resolve()
    before_snapshot = scan_code_tree(code_root)
    before_hash = _tree_hash(code_root)
    target = code_root / "execution_result.txt"
    target.write_text(
        f"Execution result for {package.run_id}.\n",
        encoding="utf-8",
        newline="\n",
    )
    after_snapshot = scan_code_tree(code_root)
    after_hash = _tree_hash(code_root)
    plan_ref = ArtifactRef.model_validate(state["plan_ref"])
    expected_ref = ArtifactRef.model_validate(state["expected_changes_ref"])
    changeset = ImplementationChangeSet(
        run_id=package.run_id,
        approved_plan_ref=plan_ref,
        expected_file_changes_ref=expected_ref,
        before_tree_hash=before_hash,
        after_tree_hash=after_hash,
        changed_files=diff_code_tree_snapshots(before_snapshot, after_snapshot),
    )
    expected = [ExpectedFileChange.model_validate(item) for item in state["expected_changes"]]
    changeset = validate_implementation_changeset(changeset, expected)
    implementation_dir = writer.artifact_dir("implementation")
    writer.write_text(implementation_dir / "README.md", "Implementation artifact.\n", "implementation_readme")
    writer.write_text(implementation_dir / "before_tree_hash.txt", before_hash + "\n", "before_tree_hash")
    writer.write_text(implementation_dir / "after_tree_hash.txt", after_hash + "\n", "after_tree_hash")
    changeset_ref = writer.write_json(
        implementation_dir / "implementation_changeset.json",
        changeset,
        "implementation_changeset",
    )
    writer.write_json(
        implementation_dir / "expected_file_changes.json",
        state["expected_changes"],
        "implementation_expected_changes",
    )
    writer.write_json(
        implementation_dir / "pre_scan_manifest.json",
        before_snapshot,
        "pre_scan_manifest",
    )
    writer.write_json(
        implementation_dir / "post_scan_manifest.json",
        after_snapshot,
        "post_scan_manifest",
    )
    writer.write_json(
        implementation_dir / "diff_scanner_results.json",
        changeset.model_dump(mode="json")["changed_files"],
        "diff_scanner_results",
    )
    writer.write_json(
        implementation_dir / "implementation_failure_policy.json",
        {
            "on_failure": "preserve_dirty_tree_for_debug",
            "retry_allowed": True,
            "max_in_plan_repair_attempts": 1,
            "dirty_tree_status": "clean",
        },
        "implementation_failure_policy",
    )
    writer.write_json(
        implementation_dir / "dirty_tree_status.json",
        {"dirty_tree_status": "clean"},
        "dirty_tree_status",
    )
    writer.write_json(
        implementation_dir / "unexpected_changes.json",
        changeset.unexpected_changes,
        "unexpected_changes",
    )
    writer.write_json(
        implementation_dir / "forbidden_changes.json",
        changeset.forbidden_changes,
        "forbidden_changes",
    )
    output_dir = writer.artifact_dir("output")
    writer.write_text(output_dir / "README.md", "Execution output artifact.\n", "output_readme")
    implementation_ref = writer.write_text(
        output_dir / "implementation_summary.md",
        "Deterministic implementation completed under approved plan.\n",
        "implementation_summary",
    )
    changed_files_ref = writer.write_json(
        output_dir / "changed_files.json",
        changeset.model_dump(mode="json")["changed_files"],
        "changed_files",
    )
    known_limits_ref = writer.write_text(output_dir / "known_limits.md", "None.\n", "known_limits")
    _write_node_result(
        writer,
        "implement",
        [implementation_ref, changeset_ref],
        {"implementation_changeset": changeset},
    )
    return {
        "implementation_artifact_ref": implementation_ref.model_dump(mode="json"),
        "implementation_changeset_ref": changeset_ref.model_dump(mode="json"),
        "changed_files_ref": changed_files_ref.model_dump(mode="json"),
        "known_limits_ref": known_limits_ref.model_dump(mode="json"),
    }


def _simple_tests_node(state: ExecutionGraphState) -> ExecutionGraphState:
    if _is_terminal(state):
        return {}
    package, binding, writer = _runtime_parts(state)
    tests_dir = writer.artifact_dir("tests")
    writer.write_text(tests_dir / "README.md", "Simple local test evidence.\n", "tests_readme")
    specs = package.simple_test_plan or [
        SimpleTestCommandSpec(
            command_id="simple-file-exists",
            command="aegis:non_empty_file execution_result.txt",
            timeout_seconds=10,
            allowed_by_approved_plan=True,
        )
    ]
    commands = [
        _run_simple_test_command(spec, tests_dir, Path(binding["code_root"]).resolve(), writer)
        for spec in specs
    ]
    failed = [
        command
        for command in commands
        if command.status != "passed" or command.exit_code != 0
    ]
    unapproved = [spec for spec in specs if not spec.allowed_by_approved_plan]
    summary_status = "passed" if not failed and not unapproved else "failed"
    failure_reason = None
    if unapproved:
        failure_reason = "simple test command was not declared in the approved plan"
    elif failed:
        failure_reason = "one or more simple test commands failed or timed out"
    evidence = SimpleTestEvidence(
        run_id=package.run_id,
        test_plan_ref=ArtifactRef.model_validate(state["plan_ref"]),
        commands=commands,
        summary_status=summary_status,
        failure_reason=failure_reason,
    )
    evidence_ref = writer.write_json(
        tests_dir / "simple_test_evidence.json",
        evidence,
        "simple_test_evidence",
    )
    _write_node_result(writer, "simple_tests", [evidence_ref], {"simple_test_evidence": evidence})
    if summary_status != "passed":
        label = "unsafe_tool_request" if unapproved else "missing_required_evidence"
        return {
            "simple_test_evidence_ref": evidence_ref.model_dump(mode="json"),
            "terminal_status": "blocked",
            "blocker": {
                "label": label,
                "reason": failure_reason or "simple tests failed",
                "evidence_refs": [evidence_ref.path],
                "next_action": "master",
                "parent_route_label": "execution",
                "retry_allowed": True,
            },
        }
    return {"simple_test_evidence_ref": evidence_ref.model_dump(mode="json")}


def _candidate_build_node(state: ExecutionGraphState) -> ExecutionGraphState:
    if _is_terminal(state):
        return {}
    package, _binding, writer = _runtime_parts(state)
    candidate_dir = writer.artifact_dir("causal_candidate")
    writer.write_text(candidate_dir / "README.md", "Execution causal candidate artifact.\n", "candidate_readme")
    implementation_ref = ArtifactRef.model_validate(state["implementation_artifact_ref"])
    candidate = ExecutionCausalCandidate(
        candidate_id=f"{package.run_id}-execution-causal-candidate",
        source_run_id=package.run_id,
        source_artifact_ref=implementation_ref,
        proposed_nodes=[
            ExecutionCausalCandidateNode(
                local_node_ref="execution-completed",
                minimal_semantic_content="Approved Execution plan produced a local implementation artifact.",
                semantic_summary="Execution implementation completed under approved plan.",
                semantic_keys=["execution", "approved_plan", "implementation"],
                dependency_groups=[
                    ExecutionCausalDependencyGroup(
                        group_id="execution-plan-approval",
                        knowledge_refs=[],
                        evidence_refs=[implementation_ref.path],
                        conditions=["approved_review_ref exists"],
                        assumptions=["simple deterministic runtime"],
                        scope="ExecutionSubgraph deterministic implementation",
                        confidence="medium",
                        invalidation_conditions=["approved plan is invalidated"],
                    )
                ],
            )
        ],
    )
    candidate_ref = writer.write_json(
        candidate_dir / "execution_causal_candidate.json",
        candidate,
        "execution_causal_candidate",
    )
    write_result = ExecutionCausalCandidateWriteResult(
        package_candidate_id=candidate.candidate_id,
        artifact_ref=candidate_ref,
        write_status="artifact_only",
    )
    write_result_ref = writer.write_json(
        candidate_dir / "execution_causal_candidate_write_result.json",
        write_result,
        "execution_causal_candidate_write_result",
    )
    writer.write_json(
        candidate_dir / "causal_candidate_mapping_report.json",
        {"status": "artifact_only", "candidate_id": candidate.candidate_id},
        "causal_candidate_mapping_report",
    )
    _write_node_result(writer, "candidate_build", [candidate_ref, write_result_ref], {})
    return {
        "causal_candidate_ref": candidate_ref.model_dump(mode="json"),
        "causal_candidate_write_result_ref": write_result_ref.model_dump(mode="json"),
    }


def _closeout_node(state: ExecutionGraphState) -> ExecutionGraphState:
    package, _binding, writer = _runtime_parts(state)
    validation = ExecutionInputValidation.model_validate(state["input_validation"])
    input_validation_ref = ArtifactRef.model_validate(state["input_validation_ref"])
    output_dir = writer.artifact_dir("output")
    writer.write_text(output_dir / "README.md", "Execution output package.\n", "output_readme")

    if validation.status == "blocked" or state.get("terminal_status") in {"blocked", "request_debate"}:
        blocker_payload = state.get("blocker")
        blocker = validation.blocker
        if blocker_payload:
            from aegis.modules.execution.models import ExecutionBlocker

            blocker = ExecutionBlocker.model_validate(blocker_payload)
        status = "request_debate" if state.get("terminal_status") == "request_debate" else "blocked"
        next_stage = "debate" if status == "request_debate" else "master"
        evidence_index_ref = writer.write_json(
            output_dir / "evidence_index.json",
            {"input_validation_ref": input_validation_ref.model_dump(mode="json")},
            "evidence_index",
        )
        output = ExecutionOutputPackage(
            run_id=package.run_id,
            status=status,
            phase="blocked",
            master_handoff_ref=validation.master_handoff_ref,
            input_validation_ref=input_validation_ref,
            blocker=blocker,
            boundary=ExecutionBoundaryFlags(),
            next_stage=next_stage,
            evidence_index_ref=evidence_index_ref,
        )
        output_ref = writer.write_json(
            output_dir / "execution_output_package.json",
            output,
            "execution_output_package",
        )
        _write_node_result(writer, "closeout", [output_ref], {"output_package": output})
        return {"output_package": output.model_dump(mode="json")}

    implementation_ref = ArtifactRef.model_validate(state["implementation_artifact_ref"])
    changeset_ref = ArtifactRef.model_validate(state["implementation_changeset_ref"])
    changed_files_ref = ArtifactRef.model_validate(state["changed_files_ref"])
    simple_test_ref = ArtifactRef.model_validate(state["simple_test_evidence_ref"])
    known_limits_ref = ArtifactRef.model_validate(state["known_limits_ref"])
    candidate_ref = ArtifactRef.model_validate(state["causal_candidate_ref"])
    approved_review_ref = ArtifactRef.model_validate(state["approved_review_ref"])
    requirement_mapping_ref = ArtifactRef.model_validate(state["requirement_mapping_ref"])
    handoff = ExecutionToTestHandoff(
        run_id=package.run_id,
        implementation_artifact_ref=implementation_ref,
        implementation_changeset_ref=changeset_ref,
        changed_files_ref=changed_files_ref,
        simple_test_evidence_ref=simple_test_ref,
        known_limits_ref=known_limits_ref,
        execution_causal_candidate_ref=candidate_ref,
        approved_review_ref=approved_review_ref,
        requirement_mapping_ref=requirement_mapping_ref,
    )
    handoff_dir = writer.artifact_dir("handoff_to_test")
    writer.write_text(handoff_dir / "README.md", "Execution to Test handoff.\n", "handoff_readme")
    handoff_ref = writer.write_json(
        handoff_dir / "execution_to_test_handoff.json",
        handoff,
        "execution_to_test_handoff",
    )
    evidence_index_ref = writer.write_json(
        output_dir / "evidence_index.json",
        {
            "implementation_artifact_ref": implementation_ref.model_dump(mode="json"),
            "implementation_changeset_ref": changeset_ref.model_dump(mode="json"),
            "simple_test_evidence_ref": simple_test_ref.model_dump(mode="json"),
            "execution_causal_candidate_ref": candidate_ref.model_dump(mode="json"),
        },
        "evidence_index",
    )
    output = ExecutionOutputPackage(
        run_id=package.run_id,
        status="completed",
        phase="completed",
        master_handoff_ref=validation.master_handoff_ref,
        input_validation_ref=input_validation_ref,
        review_baseline_ref=ArtifactRef.model_validate(state["review_baseline_ref"]),
        approved_review_ref=approved_review_ref,
        implementation_artifact_ref=implementation_ref,
        implementation_changeset_ref=changeset_ref,
        simple_test_evidence_ref=simple_test_ref,
        execution_causal_candidate_ref=candidate_ref,
        execution_causal_candidate_write_result_ref=ArtifactRef.model_validate(
            state["causal_candidate_write_result_ref"]
        ),
        known_limits_ref=known_limits_ref,
        boundary=ExecutionBoundaryFlags(),
        next_stage="test_subgraph",
        execution_to_test_handoff_ref=handoff_ref,
        evidence_index_ref=evidence_index_ref,
    )
    output_ref = writer.write_json(
        output_dir / "execution_output_package.json",
        output,
        "execution_output_package",
    )
    _write_node_result(writer, "closeout", [output_ref, handoff_ref], {"output_package": output})
    return {
        "execution_to_test_handoff_ref": handoff_ref.model_dump(mode="json"),
        "output_package": output.model_dump(mode="json"),
    }


def _runtime_parts(state: ExecutionGraphState):
    package = ExecutionInputPackage.model_validate(state["input_package"])
    binding = state.get("binding")
    if binding is None:
        actual = bind_execution_project(
            package.project_root,
            run_id=package.run_id,
            code_root=package.code_root,
        )
        binding = actual.model_dump(mode="json")
    else:
        actual = bind_execution_project(
            binding["project_root"],
            run_id=package.run_id,
            code_root=binding["code_root"],
        )
    return package, binding, ExecutionArtifactWriter(actual)


def _is_terminal(state: ExecutionGraphState) -> bool:
    return bool(state.get("terminal_status"))


def _route_after_input_validation(state: ExecutionGraphState) -> str:
    if _is_terminal(state):
        return "closeout"
    return "continue"


def _route_after_approval_gate(state: ExecutionGraphState) -> str:
    if _is_terminal(state):
        return "closeout"
    if state.get("approval_decision") == "revise":
        return "revise"
    return "implement"


def _route_after_write_gate(state: ExecutionGraphState) -> str:
    if _is_terminal(state):
        return "closeout"
    return "implement"


def _route_after_simple_tests(state: ExecutionGraphState) -> str:
    if _is_terminal(state):
        return "closeout"
    return "candidate"


def _binding_path(state: ExecutionGraphState, key: str) -> Path:
    return Path(state["binding"][key])


def _write_node_result(
    writer: ExecutionArtifactWriter,
    node_name: str,
    artifacts: list[ArtifactRef],
    updated: dict[str, Any],
) -> ArtifactRef:
    node_dir = writer.artifact_dir("node_results")
    writer.write_text(node_dir / "README.md", "Execution node result artifacts.\n", "node_results_readme")
    result = ExecutionNodeResult(
        node_name=node_name,
        status="ok",
        updated_state_fields={key: _jsonable(value) for key, value in updated.items()},
        artifact_refs=artifacts,
    )
    return writer.write_json(
        node_dir / f"{node_name}_result.json",
        result,
        f"{node_name}_result",
    )


def _review_outcome_for_round(
    package: ExecutionInputPackage,
    round_number: int,
) -> DeterministicReviewOutcome:
    if package.deterministic_review_sequence:
        index = min(round_number - 1, len(package.deterministic_review_sequence) - 1)
        return package.deterministic_review_sequence[index]
    return DeterministicReviewOutcome(
        decision="approved",
        score=98,
        error_count=0,
        warning_count=0,
        suggestion_count=0,
        explanation="Approved. The plan is simple, bounded, testable, and has no error-level issue.",
    )


def _run_simple_test_command(
    spec: SimpleTestCommandSpec,
    tests_dir: Path,
    code_root: Path,
    writer: ExecutionArtifactWriter,
) -> SimpleTestCommandEvidence:
    started = time.perf_counter()
    stdout = ""
    stderr = ""
    exit_code = 0
    status = "passed"
    command = spec.command.strip()

    if not spec.allowed_by_approved_plan:
        exit_code = 1
        status = "skipped"
        stderr = "Command is not declared in the approved simple test plan.\n"
    elif command.startswith("aegis:non_empty_file "):
        rel = command.removeprefix("aegis:non_empty_file ").strip()
        target = (code_root / rel).resolve()
        if target != code_root and code_root not in target.parents:
            exit_code = 1
            status = "failed"
            stderr = "Target path is outside code_root.\n"
        elif target.exists() and target.is_file() and target.stat().st_size > 0:
            stdout = f"{rel} exists and is non-empty.\n"
        else:
            exit_code = 1
            status = "failed"
            stderr = f"{rel} is missing or empty.\n"
    elif command.startswith("aegis:file_exists "):
        rel = command.removeprefix("aegis:file_exists ").strip()
        target = (code_root / rel).resolve()
        if target != code_root and code_root not in target.parents:
            exit_code = 1
            status = "failed"
            stderr = "Target path is outside code_root.\n"
        elif target.exists() and target.is_file():
            stdout = f"{rel} exists.\n"
        else:
            exit_code = 1
            status = "failed"
            stderr = f"{rel} is missing.\n"
    elif command.startswith("aegis:sleep "):
        seconds = int(command.removeprefix("aegis:sleep ").strip())
        if seconds > spec.timeout_seconds:
            exit_code = 124
            status = "timeout"
            stderr = f"Command exceeded timeout_seconds={spec.timeout_seconds}.\n"
        else:
            time.sleep(seconds)
            stdout = f"Slept {seconds} seconds.\n"
    else:
        exit_code = 1
        status = "skipped"
        stderr = "Unsupported simple test command.\n"

    duration_ms = max(0, int((time.perf_counter() - started) * 1000))
    stdout_ref = writer.write_text(
        tests_dir / "stdout" / f"{spec.command_id}.txt",
        stdout,
        "stdout",
    )
    stderr_ref = writer.write_text(
        tests_dir / "stderr" / f"{spec.command_id}.txt",
        stderr,
        "stderr",
    )
    return SimpleTestCommandEvidence(
        command_id=spec.command_id,
        command=spec.command,
        cwd=str(code_root),
        timeout_seconds=spec.timeout_seconds,
        exit_code=exit_code,
        stdout_ref=stdout_ref,
        stderr_ref=stderr_ref,
        duration_ms=duration_ms,
        status=status,
    )


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _tree_hash(root: Path) -> str:
    hasher = hashlib.sha256()
    if not root.exists():
        return hasher.hexdigest()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel = path.relative_to(root).as_posix()
        hasher.update(rel.encode("utf-8"))
        hasher.update(_sha256_file(path).encode("ascii"))
    return hasher.hexdigest()
