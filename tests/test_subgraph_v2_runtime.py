from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegis.modules.execution.models import (
    ArtifactRef as ExecutionArtifactRef,
    ExecutionBoundaryFlags,
    ExecutionBlocker,
    ExecutionOutputPackage,
    ExecutionToTestHandoff,
)
from aegis.modules.test.artifacts import TestArtifactWriter as RuntimeTestArtifactWriter
from aegis.modules.test.graph import run_deterministic_test_subgraph
from aegis.modules.test.models import (
    ArtifactRef,
    ArtifactSchemaCheckItem,
    ArtifactSchemaValidationResult,
    EvidenceMatrixItem,
    FixtureProvenance,
    PlanReviewScorecard,
    SkipReason,
    SourceProvenance,
    StateBoundaryResult,
    TestInputPackage,
    TestNode,
    TestNodeExecutionRecord,
    TestPlan,
    TestPlanReviewIssue,
)
from aegis.modules.test.path_io import fs_path, mkdir, path_exists
from aegis.modules.test.store_binding import bind_test_project
from aegis.modules.test.retest import select_minimal_retest_nodes
from aegis.modules.test.validators import validate_real_agent_behavior


def write_file(path: Path, content: str) -> None:
    mkdir(path.parent)
    with open(fs_path(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def make_project(root: Path) -> Path:
    mkdir(root / "code")
    mkdir(root / "knowledge")
    mkdir(root / "causal")
    return root


def ref(path: Path, kind: str = "artifact") -> ArtifactRef:
    mkdir(path.parent)
    if not path_exists(path):
        write_file(path, "artifact\n")
    readme = path if path.name == "README.md" else path.parent / "README.md"
    if not path_exists(readme):
        write_file(readme, "Read this first.\n")
    return ArtifactRef(
        artifact_id=f"{kind}-1",
        artifact_type=kind,
        path=str(path),
        readme_path=str(readme),
        sha256="0" * 64,
        created_by_node="unit_test",
    )


def execution_ref(path: Path, kind: str = "artifact") -> ExecutionArtifactRef:
    mkdir(path.parent)
    if not path_exists(path):
        write_file(path, "artifact\n")
    readme = path if path.name == "README.md" else path.parent / "README.md"
    if not path_exists(readme):
        write_file(readme, "Read this first.\n")
    return ExecutionArtifactRef(
        artifact_id=f"{kind}-1",
        artifact_type=kind,
        path=str(path),
        readme_path=str(readme),
        sha256="0" * 64,
        created_by_node="unit_test",
    )


def write_execution_handoff(project: Path, *, status: str = "completed") -> tuple[Path, Path]:
    root = project / ".aegis" / "artifacts" / "execution" / "execution-run" / "handoff_to_test"
    mkdir(root)
    write_file(root / "README.md", "Execution to Test handoff.\n")
    output_root = root.parent / "output"
    mkdir(output_root)
    write_file(output_root / "README.md", "Execution output.\n")
    handoff = ExecutionToTestHandoff(
        run_id="execution-run",
        implementation_artifact_ref=execution_ref(output_root / "implementation.md", "implementation"),
        implementation_changeset_ref=execution_ref(output_root / "changeset.json", "changeset"),
        changed_files_ref=execution_ref(output_root / "changed_files.json", "changed_files"),
        simple_test_evidence_ref=execution_ref(output_root / "simple_test.json", "simple_test"),
        known_limits_ref=execution_ref(output_root / "known_limits.md", "known_limits"),
        execution_causal_candidate_ref=execution_ref(output_root / "causal_candidate.json", "causal"),
        approved_review_ref=execution_ref(output_root / "approved_review.md", "approved_review"),
        requirement_mapping_ref=execution_ref(output_root / "requirement_mapping.json", "mapping"),
    )
    write_file(root / "execution_to_test_handoff.json", handoff.model_dump_json(indent=2) + "\n")
    output = ExecutionOutputPackage(
        run_id="execution-run",
        status=status,  # type: ignore[arg-type]
        phase="completed" if status == "completed" else "blocked",
        master_handoff_ref=execution_ref(output_root / "master_handoff.md", "master_handoff"),
        input_validation_ref=execution_ref(output_root / "input_validation.json", "input"),
        implementation_artifact_ref=handoff.implementation_artifact_ref if status == "completed" else None,
        implementation_changeset_ref=handoff.implementation_changeset_ref if status == "completed" else None,
        simple_test_evidence_ref=handoff.simple_test_evidence_ref if status == "completed" else None,
        boundary=ExecutionBoundaryFlags(),
        blocker=ExecutionBlocker(
            label="missing_required_evidence",
            reason="synthetic blocked execution output",
            next_action="master",
        )
        if status == "blocked"
        else None,
        next_stage="test_subgraph" if status == "completed" else "master",
        execution_to_test_handoff_ref=execution_ref(
            root / "execution_to_test_handoff.json", "handoff"
        )
        if status == "completed"
        else None,
        evidence_index_ref=execution_ref(output_root / "evidence_index.json", "evidence_index"),
    )
    output_path = output_root / "execution_output_package.json"
    write_file(output_path, output.model_dump_json(indent=2) + "\n")
    return root, output_path


def package(project: Path, handoff_dir: Path, output_path: Path, **kwargs: object) -> TestInputPackage:
    return TestInputPackage(
        run_id="test-run",
        project_root=project,
        code_root=project / "code",
        execution_handoff_dir=handoff_dir,
        execution_output_package_path=output_path,
        **kwargs,
    )


def test_scorecard_warning_only_score_95_must_approve() -> None:
    with pytest.raises(ValueError, match="warning-only scorecards with score >= 95 must approve"):
        PlanReviewScorecard(
            decision="changes_required",
            score=96,
            dimensions={"coverage": 96},
            error_count=0,
            warning_count=1,
            suggestion_count=0,
            issues=[
                TestPlanReviewIssue(
                    issue_id="warn-1",
                    severity="warning",
                    test_plan_refs=["plan"],
                    handoff_refs=["handoff"],
                    explanation="Non-blocking issue.",
                    blocking=False,
                )
            ],
            baseline_criteria_ref=ref(Path("C:/tmp/baseline.txt"), "baseline"),
            review_report_ref=ref(Path("C:/tmp/review.txt"), "review"),
        )


def test_skipped_verdict_requires_skip_reason() -> None:
    with pytest.raises(ValueError, match="skipped verdict requires skip_reason"):
        EvidenceMatrixItem(
            test_id="t1",
            plan_ref="plan",
            artifact_refs=[],
            expected_result="pass",
            actual_result="skipped",
            verdict="skipped",
            verdict_reason="skipped",
            evidence_complete=False,
        )


def test_executor_omission_skip_is_not_evidence_complete() -> None:
    with pytest.raises(ValueError, match="executor_omission cannot be evidence_complete"):
        EvidenceMatrixItem(
            test_id="t1",
            plan_ref="plan",
            artifact_refs=[],
            expected_result="pass",
            actual_result="skipped",
            verdict="skipped",
            verdict_reason="executor omitted the node",
            skip_reason=SkipReason(
                skip_type="executor_omission",
                reason="not run",
                approved_by_plan=False,
                evidence_refs=[],
            ),
            evidence_complete=True,
        )


def test_artifact_schema_required_failure_blocks() -> None:
    result = ArtifactSchemaValidationResult(
        status="failed",
        checked_artifacts=[
            ArtifactSchemaCheckItem(
                artifact_ref=ref(Path("C:/tmp/required.json"), "required"),
                schema_name="required-schema",
                required=True,
                status="failed",
                failure_reason="missing field",
            )
        ],
        failures=["required-schema missing field"],
    )

    assert result.status == "failed"

    with pytest.raises(ValueError, match="required artifact schema failures require status=failed"):
        ArtifactSchemaValidationResult(
            status="passed",
            checked_artifacts=result.checked_artifacts,
            failures=[],
        )


def test_write_policy_forbids_code_and_store_roots(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    handoff, output_path = write_execution_handoff(project)
    output = run_deterministic_test_subgraph(
        package(
            project,
            handoff,
            output_path,
            deterministic_test_commands=["aegis:write_code hidden_side_effect.txt"],
        )
    )

    assert output.status == "blocked"
    assert output.blocker is not None
    assert output.blocker.label in {"unsafe_test_command", "code_mutation_detected"}
    assert output.failure_classification == "command_safety_block"


def test_artifact_writer_accepts_long_evidence_paths_without_code_root_write(
    tmp_path: Path,
) -> None:
    long_root = tmp_path / ("project_" + "x" * 48)
    project = make_project(long_root)
    binding = bind_test_project(project, run_id="test-run-" + "y" * 48)
    writer = RuntimeTestArtifactWriter(binding)

    deep_relative_path = Path(
        "very"
    ) / ("deep_" + "z" * 48) / ("evidence_" + "q" * 48) / "path"
    target = writer.artifact_dir(deep_relative_path) / "result.txt"
    assert len(str(target.resolve())) > 260

    artifact_ref = writer.write_text(
        target,
        "evidence\n",
        "long_path_evidence",
    )

    assert Path(artifact_ref.path).exists()
    with pytest.raises(ValueError, match="must not write Test runtime artifacts under code_root"):
        writer.write_text(project / "code" / "bad.txt", "bad\n", "bad")


def test_hidden_code_mutation_is_detected_under_long_execution_handoff_path(
    tmp_path: Path,
) -> None:
    project = make_project(
        tmp_path / ("project_" + "x" * 80) / ("nested_" + "y" * 80)
    )
    handoff, output_path = write_execution_handoff(project)
    assert len(str((handoff / "execution_to_test_handoff.json").resolve())) > 260

    output = run_deterministic_test_subgraph(
        package(
            project,
            handoff,
            output_path,
            deterministic_test_commands=["aegis:hidden_code_mutation hidden.txt"],
        )
    )

    assert output.status == "blocked"
    assert output.blocker is not None
    assert output.blocker.label == "code_mutation_detected"
    assert output.failure_classification == "code_mutation_detected"


def test_invalid_execution_output_blocks_before_plan(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    handoff, output_path = write_execution_handoff(project, status="blocked")

    output = run_deterministic_test_subgraph(package(project, handoff, output_path))

    assert output.status == "blocked"
    assert output.blocker is not None
    assert output.blocker.label == "input_invalid"
    assert output.failure_classification == "input_invalid"
    assert output.approved_test_plan_ref is None


def test_successful_test_subgraph_writes_output_package_and_provenance(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    handoff, output_path = write_execution_handoff(project)

    output = run_deterministic_test_subgraph(package(project, handoff, output_path))

    assert output.status == "passed"
    assert output.next_stage == "final_review"
    assert output.approved_test_plan_ref is not None
    assert output.test_execution_manifest_ref is not None
    assert output.evidence_check_ref is not None
    assert output.artifact_schema_check_ref is not None
    assert output.final_test_report_ref is not None
    assert output.state_boundary_results_ref is not None
    assert output.failure_classification is None
    output_dir = Path(output.final_test_report_ref.path).parents[1]
    source_provenance = SourceProvenance.model_validate_json(
        (output_dir / "index" / "source_provenance.json").read_text(encoding="utf-8")
    )
    fixture_provenance = FixtureProvenance.model_validate_json(
        (output_dir / "index" / "fixture_provenance.json").read_text(encoding="utf-8")
    )
    state_boundary = StateBoundaryResult.model_validate_json(
        (output_dir / "index" / "state_boundary_results.json").read_text(encoding="utf-8")
    )
    evidence_index = json.loads((output_dir / "index" / "evidence_index.json").read_text(encoding="utf-8"))
    assert (output_dir / "index" / "environment_provenance.json").exists()
    assert Path(source_provenance.source_manifest_ref.path).exists()
    assert source_provenance.source_file_count == 0
    assert fixture_provenance.fixture_manifest_hash != "0" * 64
    assert fixture_provenance.fixture_roots
    assert fixture_provenance.fixture_artifact_refs
    assert state_boundary.status == "passed"
    assert state_boundary.long_text_fields_detected == []
    assert evidence_index["state_boundary_results_ref"]["artifact_type"] == "state_boundary_results"


def test_raw_report_cannot_override_failed_evidence(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    handoff, output_path = write_execution_handoff(project)

    output = run_deterministic_test_subgraph(
        package(project, handoff, output_path, deterministic_test_commands=["aegis:fail"])
    )

    assert output.status == "failed"
    assert output.next_stage == "execution"
    assert output.failure_classification == "test_failure"
    assert output.final_test_report_ref is not None
    report_text = Path(output.final_test_report_ref.path).read_text(encoding="utf-8")
    assert "failed" in report_text


def test_environment_skip_blocks_or_routes_for_input(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    handoff, output_path = write_execution_handoff(project)

    output = run_deterministic_test_subgraph(
        package(project, handoff, output_path, deterministic_test_commands=["aegis:skip environment"])
    )

    assert output.status == "blocked"
    assert output.blocker is not None
    assert output.blocker.next_action == "developer_input"


def test_execution_manifest_requires_test_node_records(tmp_path: Path) -> None:
    plan = TestPlan(
        plan_id="plan-1",
        source_handoff_dir=str(tmp_path),
        test_nodes=[
            TestNode(
                test_id="t1",
                purpose="prove record requirement",
                preconditions=[],
                command_or_operation="aegis:pass",
                expected_result="passed",
                evidence_required=["stdout"],
                depends_on=[],
                consumes_outputs_from=[],
                can_rerun_independently=True,
                write_policy_ref=ref(tmp_path / "write_policy.json", "write_policy"),
            )
        ],
        dependency_graph_ref=ref(tmp_path / "graph.json", "graph"),
        coverage_matrix_ref=ref(tmp_path / "coverage.json", "coverage"),
        evidence_requirements_ref=ref(tmp_path / "evidence.json", "evidence"),
    )

    with pytest.raises(ValueError, match="every test node requires execution record"):
        TestNodeExecutionRecord.validate_manifest_records(plan, [])


def test_state_and_message_payloads_only_carry_refs(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    handoff, output_path = write_execution_handoff(project)

    output = run_deterministic_test_subgraph(package(project, handoff, output_path))

    payload = json.loads(output.model_dump_json())
    serialized = json.dumps(payload, ensure_ascii=True)
    assert len(serialized.encode("utf-8")) < 65_536
    assert "raw_test_report.md contents" not in serialized


def test_minimal_retest_selects_dependency_closure(tmp_path: Path) -> None:
    from aegis.modules.test.models import TestDependencyEdge, TestDependencyGraph

    graph = TestDependencyGraph(
        nodes=["setup", "atomic", "integration", "consumer"],
        edges=[
            TestDependencyEdge(
                from_test_id="setup",
                to_test_id="integration",
                dependency_type="environment_setup",
            ),
            TestDependencyEdge(
                from_test_id="atomic",
                to_test_id="integration",
                dependency_type="precondition",
            ),
            TestDependencyEdge(
                from_test_id="integration",
                to_test_id="consumer",
                dependency_type="artifact_consumer",
            ),
        ],
    )

    request = select_minimal_retest_nodes(
        request_id="retest-1",
        target_gap_ids=["integration"],
        dependency_graph=graph,
        dependency_graph_ref=ref(tmp_path / "dependency_graph.json", "graph"),
        still_valid_evidence_nodes={"atomic"},
    )

    assert request.selected_nodes == ["consumer", "integration", "setup"]
    assert request.excluded_nodes == ["atomic"]


def test_minimal_retest_cycle_without_break_rule_blocks(tmp_path: Path) -> None:
    from aegis.modules.test.models import TestDependencyGraph

    graph = TestDependencyGraph(nodes=["a", "b"], cycles_detected=[["a", "b"]])

    with pytest.raises(ValueError, match="cycle without break rule"):
        select_minimal_retest_nodes(
            request_id="retest-cycle",
            target_gap_ids=["a"],
            dependency_graph=graph,
            dependency_graph_ref=ref(tmp_path / "dependency_graph.json", "graph"),
        )


def test_real_agent_validator_catches_role_violations(tmp_path: Path) -> None:
    behavior_ref = ref(tmp_path / "behavior.json", "behavior")

    result = validate_real_agent_behavior(
        role="report_processor",
        behavior_artifact=behavior_ref,
        observed_actions=["read_evidence_matrix", "override_failed_evidence"],
    )

    assert result.status == "failed"
    assert result.policy_violations == ["override_failed_evidence"]
