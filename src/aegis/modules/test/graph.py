"""LangGraph builder and deterministic Test Subgraph v2 runtime."""

from __future__ import annotations

import platform
import json
import sys
import time
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from aegis.modules.test.artifacts import TestArtifactWriter
from aegis.modules.test.changeset import diff_code_tree, scan_code_tree, tree_hash
from aegis.modules.test.command_safety import analyze_test_command
from aegis.modules.test.input_validation import validate_execution_handoff
from aegis.modules.test.models import (
    ArtifactRef,
    ArtifactSchemaCheckItem,
    ArtifactSchemaValidationResult,
    EnvironmentProvenance,
    EvidenceMatrix,
    EvidenceMatrixItem,
    FixtureProvenance,
    PlanReviewScorecard,
    SkipReason,
    SourceProvenance,
    StateBoundaryResult,
    TestBlocker,
    TestBoundaryFlags,
    TestDependencyGraph,
    TestFailureClassification,
    TestInputPackage,
    TestNode,
    TestNodeExecutionRecord,
    TestNodeResult,
    TestOutputPackage,
    TestPlan,
    TestPlanReviewIssue,
    TestProjectBinding,
    TestRunManifest,
    TestStatus,
    TestWritePolicy,
)
from aegis.modules.test.path_io import path_exists, read_text, write_text as write_path_text
from aegis.modules.test.store_binding import bind_test_project


class TestGraphState(TypedDict, total=False):
    """JSON-safe state for Test Subgraph v2."""

    input_package: dict[str, Any]
    binding: dict[str, Any]
    input_validation: dict[str, Any]
    input_validation_ref: dict[str, Any]
    source_provenance_ref: dict[str, Any]
    fixture_provenance_ref: dict[str, Any]
    environment_provenance_ref: dict[str, Any]
    write_policy_ref: dict[str, Any]
    plan: dict[str, Any]
    approved_test_plan_ref: dict[str, Any]
    plan_review_scorecard: dict[str, Any]
    plan_review_ref: dict[str, Any]
    dependency_graph_ref: dict[str, Any]
    before_code_snapshot: dict[str, str]
    command_safety_refs: list[dict[str, Any]]
    execution_records: list[dict[str, Any]]
    test_execution_manifest_ref: dict[str, Any]
    changeset: dict[str, Any]
    changeset_ref: dict[str, Any]
    completeness_check_ref: dict[str, Any]
    evidence_matrix: dict[str, Any]
    evidence_check_ref: dict[str, Any]
    artifact_schema_result: dict[str, Any]
    artifact_schema_check_ref: dict[str, Any]
    final_test_report_ref: dict[str, Any]
    evidence_index_ref: dict[str, Any]
    state_boundary_results_ref: dict[str, Any]
    output_package: dict[str, Any]
    terminal_status: str
    blocker: dict[str, Any]


def build_test_subgraph():
    """Build the standalone deterministic Test Subgraph."""

    builder = StateGraph(TestGraphState)
    builder.add_node("input_validation", _input_validation_node)
    builder.add_node("test_plan_draft", _test_plan_draft_node)
    builder.add_node("test_plan_review", _test_plan_review_node)
    builder.add_node("test_execution", _test_execution_node)
    builder.add_node("code_tree_diff_check", _code_tree_diff_check_node)
    builder.add_node("completeness_check", _completeness_check_node)
    builder.add_node("evidence_check", _evidence_check_node)
    builder.add_node("artifact_schema_check", _artifact_schema_check_node)
    builder.add_node("report_processor", _report_processor_node)
    builder.add_node("closeout", _closeout_node)
    builder.add_edge(START, "input_validation")
    builder.add_conditional_edges(
        "input_validation",
        _route_continue_or_close,
        {"continue": "test_plan_draft", "closeout": "closeout"},
    )
    builder.add_edge("test_plan_draft", "test_plan_review")
    builder.add_conditional_edges(
        "test_plan_review",
        _route_continue_or_close,
        {"continue": "test_execution", "closeout": "closeout"},
    )
    builder.add_edge("test_execution", "code_tree_diff_check")
    builder.add_conditional_edges(
        "code_tree_diff_check",
        _route_continue_or_close,
        {"continue": "completeness_check", "closeout": "report_processor"},
    )
    builder.add_conditional_edges(
        "completeness_check",
        _route_continue_or_close,
        {"continue": "evidence_check", "closeout": "report_processor"},
    )
    builder.add_conditional_edges(
        "evidence_check",
        _route_after_evidence,
        {"schema": "artifact_schema_check", "report": "report_processor"},
    )
    builder.add_conditional_edges(
        "artifact_schema_check",
        _route_continue_or_report,
        {"continue": "report_processor", "report": "report_processor"},
    )
    builder.add_edge("report_processor", "closeout")
    builder.add_edge("closeout", END)
    return builder.compile()


def run_deterministic_test_subgraph(package: TestInputPackage) -> TestOutputPackage:
    """Run the deterministic Test Subgraph and return its terminal package."""

    result = build_test_subgraph().invoke({"input_package": package.model_dump(mode="json")})
    return TestOutputPackage.model_validate(result["output_package"])


def _input_validation_node(state: TestGraphState) -> TestGraphState:
    package = TestInputPackage.model_validate(state["input_package"])
    binding = bind_test_project(package.project_root, run_id=package.run_id, code_root=package.code_root)
    writer = TestArtifactWriter(binding)
    _write_artifact_readmes(writer)
    validation = validate_execution_handoff(
        execution_handoff_dir=package.execution_handoff_dir,
        execution_output_package_path=package.execution_output_package_path,
        writer=writer,
    )
    input_validation_ref = writer.file_ref(
        writer.artifact_dir("input") / "test_input_validation.json",
        "test_input_validation",
        created_by_node="input_validation",
    )
    source_ref, fixture_ref, environment_ref = _write_provenance(package, binding, writer)
    update: TestGraphState = {
        "binding": binding.model_dump(mode="json"),
        "input_validation": validation.model_dump(mode="json"),
        "input_validation_ref": input_validation_ref.model_dump(mode="json"),
        "source_provenance_ref": source_ref.model_dump(mode="json"),
        "fixture_provenance_ref": fixture_ref.model_dump(mode="json"),
        "environment_provenance_ref": environment_ref.model_dump(mode="json"),
    }
    if validation.status == "blocked":
        update["terminal_status"] = "blocked"
        update["blocker"] = validation.blocker.model_dump(mode="json") if validation.blocker else {}
    _write_node_result(writer, "input_validation", [input_validation_ref], {"validation": validation})
    return update


def _test_plan_draft_node(state: TestGraphState) -> TestGraphState:
    if _is_terminal(state):
        return {}
    package, binding, writer = _runtime_parts(state)
    plan_dir = writer.artifact_dir("test_plan")
    writer.write_text(
        plan_dir / "README.md",
        "Test plan package. Read approved_test_plan.md, then test_dependency_graph.json.\n",
        "test_plan_readme",
    )
    write_policy = TestWritePolicy(
        policy_id=f"{package.run_id}-write-policy",
        test_run_dir=str(binding.test_artifact_root),
        allowed_temp_roots=[str(binding.test_artifact_root / "tmp")],
        forbidden_roots=[
            str(binding.code_root),
            binding.knowledge_store_root,
            binding.causal_store_root,
        ],
    )
    write_policy_ref = writer.write_json(
        plan_dir / "test_write_policy.json",
        write_policy,
        "test_write_policy",
    )
    commands = package.deterministic_test_commands or ["aegis:pass"]
    nodes = [
        TestNode(
            test_id=f"test_{index + 1:02d}",
            purpose=f"Execute deterministic test command {index + 1}.",
            preconditions=["Execution handoff is validated."],
            command_or_operation=command,
            expected_result="passed",
            evidence_required=["command", "stdout", "stderr", "exit_code", "evidence"],
            depends_on=[],
            consumes_outputs_from=[],
            can_rerun_independently=True,
            write_policy_ref=write_policy_ref,
        )
        for index, command in enumerate(commands)
    ]
    dependency_graph = TestDependencyGraph(nodes=[node.test_id for node in nodes], edges=[])
    graph_ref = writer.write_json(
        plan_dir / "test_dependency_graph.json",
        dependency_graph,
        "test_dependency_graph",
    )
    coverage_ref = writer.write_json(
        plan_dir / "coverage_matrix.json",
        [{"test_id": node.test_id, "covers": ["execution_to_test_handoff"]} for node in nodes],
        "coverage_matrix",
    )
    evidence_requirements_ref = writer.write_json(
        plan_dir / "evidence_requirements.json",
        {node.test_id: node.evidence_required for node in nodes},
        "evidence_requirements",
    )
    plan = TestPlan(
        plan_id=f"{package.run_id}-plan",
        source_handoff_dir=str(package.execution_handoff_dir),
        test_nodes=nodes,
        dependency_graph_ref=graph_ref,
        coverage_matrix_ref=coverage_ref,
        evidence_requirements_ref=evidence_requirements_ref,
    )
    writer.write_text(
        plan_dir / "draft_test_plan.md",
        "# Draft Test Plan\n\nDeterministic test plan generated from Execution handoff refs.\n",
        "draft_test_plan",
    )
    approved_ref = writer.write_text(
        plan_dir / "approved_test_plan.md",
        "# Approved Test Plan\n\n" + "\n".join(f"- {node.test_id}: `{node.command_or_operation}`" for node in nodes) + "\n",
        "approved_test_plan",
    )
    writer.write_json(plan_dir / "approved_test_plan.json", plan, "approved_test_plan_json")
    _write_node_result(writer, "test_plan_draft", [approved_ref], {"plan": plan})
    return {
        "write_policy_ref": write_policy_ref.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
        "approved_test_plan_ref": approved_ref.model_dump(mode="json"),
        "dependency_graph_ref": graph_ref.model_dump(mode="json"),
    }


def _test_plan_review_node(state: TestGraphState) -> TestGraphState:
    if _is_terminal(state):
        return {}
    _package, _binding, writer = _runtime_parts(state)
    plan = TestPlan.model_validate(state["plan"])
    review_dir = writer.artifact_dir("test_plan")
    baseline_ref = writer.write_json(
        review_dir / "plan_review_baseline.json",
        {
            "score_threshold": 95,
            "error_blocks": True,
            "warning_blocks": False,
            "source": "Test Subgraph v2 contract",
        },
        "plan_review_baseline",
    )
    issues: list[TestPlanReviewIssue] = []
    if not plan.test_nodes:
        issues.append(
            TestPlanReviewIssue(
                issue_id="plan-empty",
                severity="error",
                explanation="Plan has no test nodes.",
                blocking=True,
            )
        )
    scorecard_report_ref = writer.write_text(
        review_dir / "plan_review_report.md",
        "Plan approved: bounded deterministic commands with explicit evidence requirements.\n",
        "plan_review_report",
    )
    scorecard = PlanReviewScorecard(
        decision="approved" if not issues else "blocked",
        score=98 if not issues else 0,
        dimensions={
            "coverage_of_changes": 98,
            "accepted_constraints": 98,
            "known_limits": 98,
            "risk_coverage": 98,
            "evidence_requirements": 98,
            "regression_coverage": 98,
            "scope_control": 98,
            "command_safety": 98,
        },
        error_count=sum(1 for issue in issues if issue.severity == "error"),
        warning_count=0,
        suggestion_count=0,
        issues=issues,
        baseline_criteria_ref=baseline_ref,
        review_report_ref=scorecard_report_ref,
    )
    scorecard_ref = writer.write_json(
        review_dir / "plan_review_scorecard.json",
        scorecard,
        "plan_review_scorecard",
    )
    writer.write_json(review_dir / "plan_review_issues.json", issues, "plan_review_issues")
    _write_node_result(writer, "test_plan_review", [scorecard_ref], {"scorecard": scorecard})
    update: TestGraphState = {
        "plan_review_scorecard": scorecard.model_dump(mode="json"),
        "plan_review_ref": scorecard_ref.model_dump(mode="json"),
    }
    if scorecard.decision != "approved":
        blocker = TestBlocker(
            label="test_plan_not_approvable",
            reason="Test plan review did not approve the plan.",
            evidence_refs=[scorecard_ref.path],
            next_action="execution",
            retry_allowed=True,
        )
        update["terminal_status"] = "blocked"
        update["blocker"] = blocker.model_dump(mode="json")
    return update


def _test_execution_node(state: TestGraphState) -> TestGraphState:
    if _is_terminal(state):
        return {}
    _package, binding, writer = _runtime_parts(state)
    plan = TestPlan.model_validate(state["plan"])
    write_policy = _load_json_model(
        ArtifactRef.model_validate(state["write_policy_ref"]),
        TestWritePolicy,
    )
    before = scan_code_tree(binding.code_root)
    execution_dir = writer.artifact_dir("execution")
    writer.write_text(
        execution_dir / "README.md",
        "Test execution package. Read test_execution_manifest.json first.\n",
        "execution_readme",
    )
    command_safety_rows: list[dict[str, Any]] = []
    records: list[TestNodeExecutionRecord] = []
    command_safety_refs: list[ArtifactRef] = []
    for node in plan.test_nodes:
        safety = analyze_test_command(
            test_id=node.test_id,
            command=node.command_or_operation,
            cwd=binding.code_root,
            write_policy=write_policy,
            write_policy_ref=ArtifactRef.model_validate(state["write_policy_ref"]),
        )
        safety_ref = writer.write_json(
            execution_dir / "commands" / node.test_id / "command_safety.json",
            safety,
            "command_safety",
        )
        command_ref = writer.write_text(
            execution_dir / "commands" / node.test_id / "command.txt",
            node.command_or_operation + "\n",
            "command",
        )
        record = _execute_node(node, safety, safety_ref, command_ref, binding, writer)
        records.append(record)
        command_safety_refs.append(safety_ref)
        command_safety_rows.append(safety.model_dump(mode="json"))
    safety_log_ref = writer.write_jsonl(
        execution_dir / "command_safety_analysis.jsonl",
        command_safety_rows,
        "command_safety_log",
    )
    record_ref = writer.write_jsonl(
        execution_dir / "test_node_execution_records.jsonl",
        [record.model_dump(mode="json") for record in records],
        "test_node_execution_records",
    )
    manifest_ref = writer.write_json(
        execution_dir / "test_execution_manifest.json",
        {
            "run_id": _package.run_id,
            "record_count": len(records),
            "records_ref": record_ref.model_dump(mode="json"),
            "records": [record.model_dump(mode="json") for record in records],
        },
        "test_execution_manifest",
    )
    writer.write_text(
        execution_dir / "raw_test_report.md",
        "# Raw Test Report\n\nExecutor raw report is non-authoritative.\n\nResult: passed\n",
        "raw_test_report",
    )
    _write_node_result(writer, "test_execution", [manifest_ref, safety_log_ref], {})
    return {
        "before_code_snapshot": before,
        "command_safety_refs": [item.model_dump(mode="json") for item in command_safety_refs],
        "execution_records": [record.model_dump(mode="json") for record in records],
        "test_execution_manifest_ref": manifest_ref.model_dump(mode="json"),
    }


def _execute_node(
    node: TestNode,
    safety: Any,
    safety_ref: ArtifactRef,
    command_ref: ArtifactRef,
    binding: TestProjectBinding,
    writer: TestArtifactWriter,
) -> TestNodeExecutionRecord:
    command_dir = writer.artifact_dir("execution") / "commands" / node.test_id
    started = time.perf_counter()
    stdout = ""
    stderr = ""
    exit_code = 0
    status = "passed"
    skip_reason = None
    produced: list[ArtifactRef] = []
    if safety.blocked:
        status = "blocked"
        exit_code = 1
        stderr = safety.reason or "command blocked"
    elif node.command_or_operation == "aegis:pass":
        stdout = f"{node.test_id} passed.\n"
    elif node.command_or_operation == "aegis:fail":
        status = "failed"
        exit_code = 1
        stderr = f"{node.test_id} failed by deterministic command.\n"
    elif node.command_or_operation == "aegis:skip approved":
        status = "skipped"
        skip_reason = SkipReason(
            skip_type="approved_conditional_skip",
            reason="Approved conditional skip from plan.",
            approved_by_plan=True,
            evidence_refs=[],
        )
        stdout = "Approved conditional skip.\n"
    elif node.command_or_operation == "aegis:skip environment":
        status = "skipped"
        skip_reason = SkipReason(
            skip_type="environment_skip",
            reason="Required local environment is unavailable.",
            approved_by_plan=False,
            evidence_refs=[],
        )
        stderr = "Environment unavailable.\n"
    elif node.command_or_operation == "aegis:timeout":
        status = "timeout"
        exit_code = 124
        stderr = "Deterministic timeout.\n"
    elif node.command_or_operation.startswith("aegis:hidden_code_mutation "):
        rel = node.command_or_operation.removeprefix("aegis:hidden_code_mutation ").strip()
        target = (binding.code_root / rel).resolve()
        write_path_text(target, "hidden test side effect\n")
        stdout = "Command reported read-only success.\n"
    else:
        status = "blocked"
        exit_code = 1
        stderr = "Unsupported deterministic command.\n"
    duration_ms = max(0, int((time.perf_counter() - started) * 1000))
    stdout_ref = writer.write_text(command_dir / "stdout.txt", stdout, "stdout")
    stderr_ref = writer.write_text(command_dir / "stderr.txt", stderr, "stderr")
    exit_ref = writer.write_text(command_dir / "exit_code.txt", str(exit_code) + "\n", "exit_code")
    duration_ref = writer.write_text(command_dir / "duration_ms.txt", str(duration_ms) + "\n", "duration_ms")
    evidence_ref = writer.write_json(
        command_dir / "evidence.json",
        {
            "test_id": node.test_id,
            "status": status,
            "exit_code": exit_code,
            "stdout_ref": stdout_ref.model_dump(mode="json"),
            "stderr_ref": stderr_ref.model_dump(mode="json"),
        },
        "test_execution_evidence",
    )
    return TestNodeExecutionRecord(
        test_id=node.test_id,
        execution_attempt=1,
        command_safety_ref=safety_ref,
        command_ref=command_ref,
        stdout_ref=stdout_ref,
        stderr_ref=stderr_ref,
        exit_code_ref=exit_ref,
        duration_ms_ref=duration_ref,
        started_at_utc=str(time.time()),
        ended_at_utc=str(time.time()),
        status=status,  # type: ignore[arg-type]
        skip_reason=skip_reason,
        evidence_ref=evidence_ref,
        produced_artifact_refs=produced,
    )


def _code_tree_diff_check_node(state: TestGraphState) -> TestGraphState:
    if not state.get("execution_records"):
        return {}
    _package, binding, writer = _runtime_parts(state)
    before = dict(state.get("before_code_snapshot") or {})
    after = scan_code_tree(binding.code_root)
    changeset = diff_code_tree(before, after)
    execution_dir = writer.artifact_dir("execution")
    writer.write_json(execution_dir / "before_code_tree_manifest.json", before, "before_tree")
    writer.write_json(execution_dir / "after_code_tree_manifest.json", after, "after_tree")
    changeset_ref = writer.write_json(
        execution_dir / "test_run_changeset.json",
        changeset,
        "test_run_changeset",
    )
    _write_node_result(writer, "code_tree_diff_check", [changeset_ref], {"changeset": changeset})
    update: TestGraphState = {
        "changeset": changeset.model_dump(mode="json"),
        "changeset_ref": changeset_ref.model_dump(mode="json"),
    }
    if changeset.status == "blocked":
        blocker = TestBlocker(
            label="code_mutation_detected",
            reason="Test execution modified code_root.",
            evidence_refs=[changeset_ref.path],
            next_action="execution",
            retry_allowed=True,
        )
        update["terminal_status"] = "blocked"
        update["blocker"] = blocker.model_dump(mode="json")
    return update


def _completeness_check_node(state: TestGraphState) -> TestGraphState:
    if _is_terminal(state):
        return {}
    _package, _binding, writer = _runtime_parts(state)
    plan = TestPlan.model_validate(state["plan"])
    records = [TestNodeExecutionRecord.model_validate(item) for item in state["execution_records"]]
    completeness_dir = writer.artifact_dir("completeness_check")
    writer.write_text(completeness_dir / "README.md", "Completeness check artifacts.\n", "readme")
    missing: list[str] = []
    try:
        TestNodeExecutionRecord.validate_manifest_records(plan, records)
    except ValueError:
        record_ids = {record.test_id for record in records}
        missing.extend(node.test_id for node in plan.test_nodes if node.test_id not in record_ids)
    missing.extend(
        record.test_id
        for record in records
        if record.skip_reason and record.skip_reason.skip_type == "executor_omission"
    )
    report_ref = writer.write_text(
        completeness_dir / "completeness_check_report.md",
        "Complete.\n" if not missing else "Missing steps: " + ", ".join(missing) + "\n",
        "completeness_check_report",
    )
    writer.write_json(completeness_dir / "missing_steps.json", missing, "missing_steps")
    writer.write_json(
        completeness_dir / "completeness_rework_rounds.json",
        {"round": 0, "max": _package.max_completeness_rework_rounds},
        "completeness_rework_rounds",
    )
    update: TestGraphState = {"completeness_check_ref": report_ref.model_dump(mode="json")}
    if missing:
        blocker = TestBlocker(
            label="test_execution_incomplete",
            reason="Approved test plan was not fully executed.",
            evidence_refs=[report_ref.path],
            next_action="execution",
            retry_allowed=True,
        )
        update["terminal_status"] = "blocked"
        update["blocker"] = blocker.model_dump(mode="json")
    return update


def _evidence_check_node(state: TestGraphState) -> TestGraphState:
    if _is_terminal(state):
        return {}
    _package, _binding, writer = _runtime_parts(state)
    plan = TestPlan.model_validate(state["plan"])
    records = [TestNodeExecutionRecord.model_validate(item) for item in state["execution_records"]]
    evidence_dir = writer.artifact_dir("evidence_check")
    writer.write_text(evidence_dir / "README.md", "Evidence check artifacts.\n", "readme")
    items: list[EvidenceMatrixItem] = []
    for record in records:
        node = next(item for item in plan.test_nodes if item.test_id == record.test_id)
        evidence_complete = _record_has_complete_evidence(record)
        items.append(
            EvidenceMatrixItem(
                test_id=record.test_id,
                plan_ref=plan.plan_id,
                command_or_operation_ref=record.command_ref,
                stdout_ref=record.stdout_ref,
                stderr_ref=record.stderr_ref,
                artifact_refs=[record.evidence_ref],
                expected_result=node.expected_result,
                actual_result=record.status,
                verdict=record.status,
                verdict_reason=f"Deterministic record status: {record.status}",
                skip_reason=record.skip_reason,
                evidence_complete=evidence_complete,
            )
        )
    matrix_status = "complete" if all(item.evidence_complete for item in items) else "gap"
    matrix = EvidenceMatrix(
        test_ids=[node.test_id for node in plan.test_nodes],
        items=items,
        status=matrix_status,  # type: ignore[arg-type]
    )
    matrix_ref = writer.write_json(evidence_dir / "evidence_matrix.json", matrix, "evidence_matrix")
    report_ref = writer.write_text(
        evidence_dir / "evidence_check_report.md",
        _evidence_report_text(matrix),
        "evidence_check_report",
    )
    writer.write_json(
        evidence_dir / "minimal_retest_request.json",
        {
            "status": "not_required" if matrix_status == "complete" else "required",
            "gap_test_ids": [item.test_id for item in items if not item.evidence_complete],
        },
        "minimal_retest_request",
    )
    writer.write_json(
        evidence_dir / "evidence_retest_rounds.json",
        {"round": 0, "max": _package.max_evidence_retest_rounds},
        "evidence_retest_rounds",
    )
    update: TestGraphState = {
        "evidence_matrix": matrix.model_dump(mode="json"),
        "evidence_check_ref": report_ref.model_dump(mode="json"),
    }
    environment_skips = [
        item
        for item in matrix.items
        if item.skip_reason and item.skip_reason.skip_type == "environment_skip"
    ]
    if environment_skips:
        blocker = TestBlocker(
            label="test_environment_unavailable",
            reason="Environment skip prevents evidence closure.",
            evidence_refs=[matrix_ref.path],
            next_action="developer_input",
            retry_allowed=True,
        )
        update["terminal_status"] = "blocked"
        update["blocker"] = blocker.model_dump(mode="json")
    elif any(item.verdict == "blocked" for item in matrix.items):
        blocker = TestBlocker(
            label="unsafe_test_command",
            reason="At least one test command was blocked by command safety.",
            evidence_refs=[matrix_ref.path],
            next_action="developer_input",
            retry_allowed=True,
        )
        update["terminal_status"] = "blocked"
        update["blocker"] = blocker.model_dump(mode="json")
    elif any(item.verdict in {"failed", "timeout", "blocked"} for item in matrix.items):
        update["terminal_status"] = "failed"
    return update


def _artifact_schema_check_node(state: TestGraphState) -> TestGraphState:
    _package, _binding, writer = _runtime_parts(state)
    final_dir = writer.artifact_dir("final_report")
    writer.write_text(final_dir / "README.md", "Final report artifacts.\n", "readme")
    required_refs = [
        ArtifactRef.model_validate(state["input_validation_ref"]),
        ArtifactRef.model_validate(state["approved_test_plan_ref"]),
        ArtifactRef.model_validate(state["test_execution_manifest_ref"]),
        ArtifactRef.model_validate(state["completeness_check_ref"]),
        ArtifactRef.model_validate(state["evidence_check_ref"]),
        ArtifactRef.model_validate(state["changeset_ref"]),
        ArtifactRef.model_validate(state["source_provenance_ref"]),
        ArtifactRef.model_validate(state["fixture_provenance_ref"]),
        ArtifactRef.model_validate(state["environment_provenance_ref"]),
    ]
    items = [
        ArtifactSchemaCheckItem(
            artifact_ref=artifact_ref,
            schema_name=artifact_ref.artifact_type,
            required=True,
            status="passed" if path_exists(artifact_ref.path) else "failed",
            failure_reason=None if path_exists(artifact_ref.path) else "missing artifact",
        )
        for artifact_ref in required_refs
    ]
    failures = [item.failure_reason or item.schema_name for item in items if item.status != "passed"]
    result = ArtifactSchemaValidationResult(
        status="failed" if failures else "passed",
        checked_artifacts=items,
        failures=failures,
    )
    result_ref = writer.write_json(
        final_dir / "artifact_schema_validation_results.json",
        result,
        "artifact_schema_validation_results",
    )
    update: TestGraphState = {
        "artifact_schema_result": result.model_dump(mode="json"),
        "artifact_schema_check_ref": result_ref.model_dump(mode="json"),
    }
    if result.status == "failed":
        blocker = TestBlocker(
            label="artifact_schema_invalid",
            reason="Required artifact schema validation failed.",
            evidence_refs=[result_ref.path],
            next_action="blocked_closeout",
            retry_allowed=False,
        )
        update["terminal_status"] = "blocked"
        update["blocker"] = blocker.model_dump(mode="json")
    return update


def _report_processor_node(state: TestGraphState) -> TestGraphState:
    package, _binding, writer = _runtime_parts(state)
    final_dir = writer.artifact_dir("final_report")
    writer.write_text(final_dir / "README.md", "Final report package. Read final_test_report.md first.\n", "readme")
    evidence_matrix = (
        EvidenceMatrix.model_validate(state["evidence_matrix"]) if state.get("evidence_matrix") else None
    )
    terminal = state.get("terminal_status")
    status = "passed"
    next_stage = "final_review"
    failure_classification = None
    if terminal == "blocked":
        status = "blocked"
        blocker = TestBlocker.model_validate(state["blocker"])
        next_stage = blocker.next_action
        failure_classification = _BLOCKER_CLASSIFICATIONS[blocker.label]
    elif terminal == "failed" or (
        evidence_matrix and any(item.verdict in {"failed", "timeout", "blocked"} for item in evidence_matrix.items)
    ):
        status = "failed"
        next_stage = "execution"
        failure_classification = "test_failed"
    report_ref = writer.write_text(
        final_dir / "final_test_report.md",
        _final_report_text(status, failure_classification, evidence_matrix),
        "final_test_report",
    )
    writer.write_json(
        final_dir / "test_result_summary.json",
        {"status": status, "failure_classification": failure_classification},
        "test_result_summary",
    )
    writer.write_json(final_dir / "next_route.json", {"next_stage": next_stage}, "next_route")
    update: TestGraphState = {"final_test_report_ref": report_ref.model_dump(mode="json")}
    if state.get("artifact_schema_check_ref") is None and status == "passed":
        # Defensive path; normal passed flow always runs artifact_schema_check first.
        blocker = TestBlocker(
            label="artifact_schema_invalid",
            reason="Artifact schema check did not run before passed report.",
            next_action="blocked_closeout",
            retry_allowed=False,
        )
        update["terminal_status"] = "blocked"
        update["blocker"] = blocker.model_dump(mode="json")
    return update


def _closeout_node(state: TestGraphState) -> TestGraphState:
    package, _binding, writer = _runtime_parts(state)
    output_dir = writer.artifact_dir("final_report")
    state_boundary_ref = _write_state_boundary_results(state, writer)
    index_state = dict(state)
    index_state["state_boundary_results_ref"] = state_boundary_ref.model_dump(mode="json")
    evidence_index_ref = writer.write_json(
        writer.artifact_dir("index") / "evidence_index.json",
        _evidence_index_payload(index_state),
        "evidence_index",
    )
    status = _output_status(state)
    next_stage = _output_next_stage(state, status)
    blocker = TestBlocker.model_validate(state["blocker"]) if state.get("blocker") else None
    failure_classification = _failure_classification(state, status)
    output = TestOutputPackage(
        run_id=package.run_id,
        status=status,
        input_validation_ref=ArtifactRef.model_validate(state["input_validation_ref"]),
        approved_test_plan_ref=_maybe_ref(state.get("approved_test_plan_ref")),
        test_execution_manifest_ref=_maybe_ref(state.get("test_execution_manifest_ref")),
        completeness_check_ref=_maybe_ref(state.get("completeness_check_ref")),
        evidence_check_ref=_maybe_ref(state.get("evidence_check_ref")),
        artifact_schema_check_ref=_maybe_ref(state.get("artifact_schema_check_ref")),
        final_test_report_ref=_maybe_ref(state.get("final_test_report_ref")),
        state_boundary_results_ref=state_boundary_ref,
        blocker=blocker,
        failure_classification=failure_classification,
        boundary=TestBoundaryFlags(),
        next_stage=next_stage,
        evidence_index_ref=evidence_index_ref,
    )
    output_ref = writer.write_json(
        output_dir / "test_output_package.json",
        output,
        "test_output_package",
    )
    _write_run_manifest(state, output.status, writer)
    _write_node_result(writer, "closeout", [output_ref], {"output_package": output})
    return {"output_package": output.model_dump(mode="json")}


def _write_provenance(
    package: TestInputPackage,
    binding: TestProjectBinding,
    writer: TestArtifactWriter,
) -> tuple[ArtifactRef, ArtifactRef, ArtifactRef]:
    index = writer.artifact_dir("index")
    writer.write_text(index / "README.md", "Run index artifacts.\n", "index_readme")
    code_snapshot = scan_code_tree(binding.code_root)
    handoff_hash = tree_hash(scan_code_tree(package.execution_handoff_dir))
    source_manifest_ref = writer.write_json(
        index / "source_manifest.json",
        {
            "code_root": str(binding.code_root),
            "file_count": len(code_snapshot),
            "tree_hash": tree_hash(code_snapshot),
            "files": code_snapshot,
        },
        "source_manifest",
    )
    source = SourceProvenance(
        source_snapshot_hash=tree_hash(code_snapshot),
        source_manifest_ref=source_manifest_ref,
        source_file_count=len(code_snapshot),
        execution_handoff_hash=handoff_hash,
        code_root=str(binding.code_root),
    )
    source_ref = writer.write_json(index / "source_provenance.json", source, "source_provenance")
    fixture_manifest_ref = writer.write_json(
        index / "fixture_manifest.json",
        {
            "execution_handoff_dir": str(package.execution_handoff_dir),
            "execution_handoff_tree_hash": handoff_hash,
            "execution_output_package_path": str(package.execution_output_package_path),
            "project_store_roots": {
                "knowledge": binding.knowledge_store_root,
                "causal": binding.causal_store_root,
            },
        },
        "fixture_manifest",
    )
    fixture = FixtureProvenance(
        fixture_manifest_hash=fixture_manifest_ref.sha256,
        fixture_roots=[
            str(package.execution_handoff_dir),
            binding.knowledge_store_root,
            binding.causal_store_root,
        ],
        fixture_artifact_refs=[fixture_manifest_ref],
    )
    fixture_ref = writer.write_json(index / "fixture_provenance.json", fixture, "fixture_provenance")
    environment = EnvironmentProvenance(
        os_name=platform.system(),
        os_version=platform.version(),
        python_version=sys.version.split()[0],
        command_root=str(binding.code_root),
        environment_hash=f"{platform.system()}-{sys.version.split()[0]}",
    )
    environment_ref = writer.write_json(
        index / "environment_provenance.json",
        environment,
        "environment_provenance",
    )
    return source_ref, fixture_ref, environment_ref


def _write_state_boundary_results(state: TestGraphState, writer: TestArtifactWriter) -> ArtifactRef:
    index = writer.artifact_dir("index")
    state_payload = _jsonable(state)
    serialized = _canonical_json(state_payload)
    long_text_fields = _find_long_text_fields(state_payload)
    result = StateBoundaryResult(
        serialized_state_size_bytes=len(serialized.encode("utf-8")),
        long_text_fields_detected=long_text_fields,
        stdout_in_state="Command reported read-only success." in serialized,
        stderr_in_state="failed by deterministic command." in serialized,
        large_json_in_state=len(serialized.encode("utf-8")) > 65_536,
        artifact_refs_only=not long_text_fields,
        status="failed"
        if len(serialized.encode("utf-8")) > 65_536 or long_text_fields
        else "passed",
    )
    return writer.write_json(index / "state_boundary_results.json", result, "state_boundary_results")


def _write_run_manifest(state: TestGraphState, status: str, writer: TestArtifactWriter) -> ArtifactRef:
    package = TestInputPackage.model_validate(state["input_package"])
    manifest = TestRunManifest(
        run_id=package.run_id,
        source_execution_run_id="execution-run",
        input_handoff_hash=ArtifactRef.model_validate(state["input_validation_ref"]).sha256,
        source_provenance_hash=ArtifactRef.model_validate(state["source_provenance_ref"]).sha256,
        fixture_provenance_hash=ArtifactRef.model_validate(state["fixture_provenance_ref"]).sha256,
        environment_provenance_hash=ArtifactRef.model_validate(state["environment_provenance_ref"]).sha256,
        approved_plan_hash=_maybe_ref(state.get("approved_test_plan_ref")).sha256
        if state.get("approved_test_plan_ref")
        else None,
        execution_manifest_hash=_maybe_ref(state.get("test_execution_manifest_ref")).sha256
        if state.get("test_execution_manifest_ref")
        else None,
        completeness_report_hash=_maybe_ref(state.get("completeness_check_ref")).sha256
        if state.get("completeness_check_ref")
        else None,
        evidence_report_hash=_maybe_ref(state.get("evidence_check_ref")).sha256
        if state.get("evidence_check_ref")
        else None,
        final_report_hash=_maybe_ref(state.get("final_test_report_ref")).sha256
        if state.get("final_test_report_ref")
        else None,
        current_terminal_status=status,
    )
    return writer.write_json(writer.artifact_dir("index") / "run_manifest.json", manifest, "run_manifest")


def _record_has_complete_evidence(record: TestNodeExecutionRecord) -> bool:
    if record.status == "skipped" and record.skip_reason:
        return record.skip_reason.skip_type == "approved_conditional_skip"
    return all([record.command_ref, record.stdout_ref, record.stderr_ref, record.exit_code_ref, record.evidence_ref])


def _evidence_report_text(matrix: EvidenceMatrix) -> str:
    lines = ["# Evidence Check", "", f"- status: `{matrix.status}`", ""]
    for item in matrix.items:
        lines.append(
            f"- {item.test_id}: verdict={item.verdict} evidence_complete={item.evidence_complete}"
        )
    return "\n".join(lines) + "\n"


def _final_report_text(
    status: str,
    failure_classification: str | None,
    matrix: EvidenceMatrix | None,
) -> str:
    lines = ["# Final Test Report", "", f"- status: `{status}`"]
    if failure_classification:
        lines.append(f"- failure_classification: `{failure_classification}`")
    lines.append("")
    lines.append("Authoritative conclusion comes from evidence matrix, schema checks, provenance, and code diff.")
    if matrix:
        for item in matrix.items:
            lines.append(f"- {item.test_id}: {item.verdict}")
    return "\n".join(lines) + "\n"


def _evidence_index_payload(state: TestGraphState) -> dict[str, Any]:
    keys = [
        "input_validation_ref",
        "approved_test_plan_ref",
        "test_execution_manifest_ref",
        "completeness_check_ref",
        "evidence_check_ref",
        "artifact_schema_check_ref",
        "final_test_report_ref",
        "source_provenance_ref",
        "fixture_provenance_ref",
        "environment_provenance_ref",
        "changeset_ref",
        "state_boundary_results_ref",
    ]
    return {key: state[key] for key in keys if key in state}


def _output_status(state: TestGraphState) -> TestStatus:
    if state.get("terminal_status") == "blocked":
        return "blocked"
    if state.get("terminal_status") == "failed":
        return "failed"
    return "passed"


def _output_next_stage(state: TestGraphState, status: str) -> str:
    if status == "passed":
        return "final_review"
    if status == "failed":
        return "execution"
    blocker = TestBlocker.model_validate(state["blocker"])
    return blocker.next_action


_BLOCKER_CLASSIFICATIONS: dict[str, TestFailureClassification] = {
    "input_invalid": "input_invalid",
    "test_plan_not_approvable": "test_plan_not_approvable",
    "unsafe_test_command": "command_safety_block",
    "test_environment_unavailable": "environment_unavailable",
    "test_execution_incomplete": "process_incomplete",
    "evidence_not_closable": "evidence_gap",
    "code_mutation_detected": "code_mutation_detected",
    "artifact_schema_invalid": "artifact_schema_invalid",
    "round_limit_exceeded": "round_limit_exceeded",
}


def _failure_classification(
    state: TestGraphState,
    status: str,
) -> TestFailureClassification | None:
    if status == "passed":
        return None
    if state.get("blocker"):
        blocker = TestBlocker.model_validate(state["blocker"])
        return _BLOCKER_CLASSIFICATIONS[blocker.label]
    matrix = EvidenceMatrix.model_validate(state["evidence_matrix"]) if state.get("evidence_matrix") else None
    if matrix and any(item.verdict == "timeout" for item in matrix.items):
        return "test_timeout"
    return "test_failure"


def _route_continue_or_close(state: TestGraphState) -> str:
    return "closeout" if _is_terminal(state) else "continue"


def _route_continue_or_report(state: TestGraphState) -> str:
    return "report" if _is_terminal(state) else "continue"


def _route_after_evidence(state: TestGraphState) -> str:
    return "schema" if not _is_terminal(state) else "report"


def _is_terminal(state: TestGraphState) -> bool:
    return bool(state.get("terminal_status"))


def _runtime_parts(state: TestGraphState) -> tuple[TestInputPackage, TestProjectBinding, TestArtifactWriter]:
    package = TestInputPackage.model_validate(state["input_package"])
    binding_payload = state.get("binding")
    if binding_payload:
        binding = bind_test_project(
            binding_payload["project_root"],
            run_id=package.run_id,
            code_root=binding_payload["code_root"],
        )
    else:
        binding = bind_test_project(package.project_root, run_id=package.run_id, code_root=package.code_root)
    return package, binding, TestArtifactWriter(binding)


def _load_json_model(ref: ArtifactRef, model: type[Any]) -> Any:
    return model.model_validate_json(read_text(ref.path))


def _maybe_ref(payload: Any) -> ArtifactRef | None:
    if payload is None:
        return None
    return ArtifactRef.model_validate(payload)


def _write_artifact_readmes(writer: TestArtifactWriter) -> None:
    root = writer.binding.test_artifact_root
    writer.write_text(
        root / "README.md",
        "Test run artifact root. Read input/README.md, test_plan/README.md, execution/README.md, "
        "evidence_check/README.md, final_report/README.md, then index/README.md.\n",
        "test_run_readme",
    )


def _write_node_result(
    writer: TestArtifactWriter,
    node_name: str,
    artifacts: list[ArtifactRef],
    updated: dict[str, Any],
) -> ArtifactRef:
    node_dir = writer.artifact_dir("node_results")
    writer.write_text(node_dir / "README.md", "Test node result artifacts.\n", "node_results_readme")
    result = TestNodeResult(
        node_name=node_name,
        status="ok",
        updated_state_fields={key: _jsonable(value) for key, value in updated.items()},
        artifact_refs=artifacts,
    )
    return writer.write_json(node_dir / f"{node_name}_result.json", result, f"{node_name}_result")


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _find_long_text_fields(value: Any, *, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, str):
        if len(value.encode("utf-8")) > 2048:
            findings.append(path)
        return findings
    if isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(_find_long_text_fields(item, path=f"{path}[{index}]"))
        return findings
    if isinstance(value, dict):
        for key, item in value.items():
            findings.extend(_find_long_text_fields(item, path=f"{path}.{key}"))
    return findings
