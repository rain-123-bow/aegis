from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from aegis.modules.execution.models import (
    ArtifactRef as ExecutionArtifactRef,
    ExecutionBlocker,
    ExecutionBoundaryFlags,
    ExecutionOutputPackage,
)
from aegis.modules.final_review.graph import run_deterministic_final_review_subgraph
from aegis.modules.final_review.models import FinalReviewInputPackage, FinalReviewOutputPackage
from aegis.modules.test.models import (
    ArtifactRef as AegisTestArtifactRef,
    ArtifactSchemaCheckItem,
    ArtifactSchemaValidationResult,
    StateBoundaryResult,
    TestBoundaryFlags,
    TestInputValidation,
    TestOutputPackage,
)


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_project(root: Path) -> Path:
    (root / "code").mkdir(parents=True)
    (root / "knowledge").mkdir()
    (root / "causal").mkdir()
    write_file(root / "code" / "feature.py", "def answer():\n    return 42\n")
    return root


def execution_ref(path: Path, artifact_type: str) -> ExecutionArtifactRef:
    if not path.exists():
        write_file(path, artifact_type + "\n")
    readme = path if path.name == "README.md" else path.parent / "README.md"
    if not readme.exists():
        write_file(readme, "Read this first.\n")
    return ExecutionArtifactRef(
        artifact_id=f"{artifact_type}-1",
        artifact_type=artifact_type,
        path=str(path),
        readme_path=str(readme),
        sha256=sha256_file(path),
        created_by_node="unit_test",
    )


def make_test_artifact_ref(path: Path, artifact_type: str) -> AegisTestArtifactRef:
    if not path.exists():
        write_file(path, artifact_type + "\n")
    readme = path if path.name == "README.md" else path.parent / "README.md"
    if not readme.exists():
        write_file(readme, "Read this first.\n")
    return AegisTestArtifactRef(
        artifact_id=f"{artifact_type}-1",
        artifact_type=artifact_type,
        path=str(path),
        readme_path=str(readme),
        sha256=sha256_file(path),
        created_by_node="unit_test",
    )


def write_requirement_packages(project: Path) -> tuple[Path, Path]:
    requirement_dir = project / ".aegis" / "artifacts" / "master" / "requirement"
    review_dir = project / ".aegis" / "artifacts" / "master" / "requirement_review"
    write_file(requirement_dir / "README.md", "Requirement package.\n")
    write_file(requirement_dir / "requirement.md", "# Requirement\n\nReturn 42.\n")
    requirement_index = {
        "requirements": [
            {
                "requirement_id": "REQ-001",
                "description": "Return 42.",
                "hard": True,
                "status": "accepted",
            }
        ]
    }
    write_file(requirement_dir / "requirements.json", json.dumps(requirement_index, indent=2) + "\n")
    write_file(review_dir / "README.md", "Requirement review package.\n")
    write_file(review_dir / "review.md", "# Requirement Review\n\nAccepted.\n")
    write_file(review_dir / "requirement_review.json", json.dumps({"status": "accepted"}) + "\n")
    return requirement_dir, review_dir


def write_execution_output(
    project: Path,
    *,
    status: str = "completed",
    next_stage: str = "test_subgraph",
    changed_hash: str | None = None,
    requirement_mapping_status: str = "satisfied",
    requirement_id: str = "REQ-001",
    requirement_mapping_dir: Path | None = None,
    include_full_code_manifest: bool = True,
) -> Path:
    root = project / ".aegis" / "artifacts" / "execution" / "execution-run" / "output"
    write_file(root / "README.md", "Execution output.\n")
    code_file = project / "code" / "feature.py"
    expected_hash = changed_hash or sha256_file(code_file)
    changeset = {
        "run_id": "execution-run",
        "changed_files": [
            {
                "path": "feature.py",
                "sha256_after": expected_hash,
                "change_type": "modified",
                "within_code_root": True,
            }
        ],
        "status": "accepted",
    }
    if include_full_code_manifest:
        changeset["code_manifest"] = {
            "files": [
                {
                    "path": item.relative_to(project / "code").as_posix(),
                    "sha256": sha256_file(item),
                }
                for item in sorted((project / "code").glob("**/*"))
                if item.is_file()
            ]
        }
    write_file(root / "changeset.json", json.dumps(changeset, indent=2) + "\n")
    write_file(root / "causal_candidate.json", json.dumps({"status": "causal_candidate"}) + "\n")
    requirement_mapping = {
        "requirements": [
            {
                "requirement_id": requirement_id,
                "status": requirement_mapping_status,
                "evidence_refs": ["simple_test.json"],
            }
        ]
    }
    mapping_root = requirement_mapping_dir or root
    write_file(mapping_root / "requirement_mapping.json", json.dumps(requirement_mapping, indent=2) + "\n")
    evidence_index = {
        "requirement_mapping_ref": execution_ref(
            mapping_root / "requirement_mapping.json",
            "requirement_mapping",
        ).model_dump(mode="json")
    }
    write_file(root / "evidence_index.json", json.dumps(evidence_index, indent=2) + "\n")
    output = ExecutionOutputPackage(
        run_id="execution-run",
        status=status,  # type: ignore[arg-type]
        phase="completed" if status == "completed" else "blocked",
        master_handoff_ref=execution_ref(root / "master_handoff.md", "master_handoff"),
        input_validation_ref=execution_ref(root / "input_validation.json", "input_validation"),
        implementation_artifact_ref=execution_ref(root / "implementation.md", "implementation")
        if status == "completed"
        else None,
        implementation_changeset_ref=execution_ref(root / "changeset.json", "changeset")
        if status == "completed"
        else None,
        simple_test_evidence_ref=execution_ref(root / "simple_test.json", "simple_test")
        if status == "completed"
        else None,
        execution_causal_candidate_ref=execution_ref(root / "causal_candidate.json", "causal_candidate")
        if status == "completed"
        else None,
        boundary=ExecutionBoundaryFlags(),
        next_stage=next_stage,  # type: ignore[arg-type]
        evidence_index_ref=execution_ref(root / "evidence_index.json", "evidence_index"),
        blocker=ExecutionBlocker(
            label="missing_required_evidence",
            reason="Synthetic blocked execution output for Final Review contract test.",
            next_action="master",
        )
        if status != "completed"
        else None,
    )
    output_path = root / "execution_output_package.json"
    write_file(output_path, output.model_dump_json(indent=2) + "\n")
    return output_path


def write_test_output(
    project: Path,
    *,
    status: str = "passed",
    next_stage: str = "final_review",
    schema_status: str = "passed",
    state_status: str = "passed",
    test_changeset_hash: str | None = None,
    evidence_matrix_status: str = "complete",
    skipped_without_valid_reason: bool = False,
) -> Path:
    root = project / ".aegis" / "artifacts" / "test" / "test-run" / "final_report"
    index = root.parent / "index"
    write_file(root / "README.md", "Test final report.\n")
    write_file(index / "README.md", "Test index.\n")
    artifact_schema = ArtifactSchemaValidationResult(
        status=schema_status,  # type: ignore[arg-type]
        checked_artifacts=[
            ArtifactSchemaCheckItem(
                artifact_ref=make_test_artifact_ref(root / "final_test_report.md", "final_test_report"),
                schema_name="final_test_report",
                required=True,
                status=schema_status,  # type: ignore[arg-type]
                failure_reason="schema failed" if schema_status == "failed" else None,
            )
        ],
        failures=["schema failed"] if schema_status == "failed" else [],
    )
    write_file(
        root / "artifact_schema_validation_results.json",
        artifact_schema.model_dump_json(indent=2) + "\n",
    )
    state_boundary = StateBoundaryResult(
        serialized_state_size_bytes=1200,
        artifact_refs_only=True,
        status=state_status,  # type: ignore[arg-type]
        long_text_fields_detected=["$.bad"] if state_status == "failed" else [],
    )
    write_file(index / "state_boundary_results.json", state_boundary.model_dump_json(indent=2) + "\n")
    code_file = project / "code" / "feature.py"
    test_changeset = {
        "status": "clean",
        "changed_files": [
            {
                "path": "feature.py",
                "sha256_after": test_changeset_hash or sha256_file(code_file),
                "within_code_root": True,
            }
        ],
    }
    write_file(index / "test_run_changeset.json", json.dumps(test_changeset, indent=2) + "\n")
    node_records = [
        {
            "test_id": "T-001",
            "status": "skipped" if skipped_without_valid_reason else "passed",
            "skip_reason": None,
        }
    ]
    write_file(index / "test_node_execution_records.jsonl", "".join(json.dumps(row) + "\n" for row in node_records))
    evidence_index = {
        "changeset_ref": make_test_artifact_ref(
            project
            / ".aegis"
            / "artifacts"
            / "execution"
            / "execution-run"
            / "output"
            / "changeset.json",
            "changeset",
        ).model_dump(mode="json"),
        "test_run_changeset_ref": make_test_artifact_ref(index / "test_run_changeset.json", "test_run_changeset").model_dump(mode="json"),
        "test_node_execution_records_ref": make_test_artifact_ref(
            index / "test_node_execution_records.jsonl", "test_node_execution_records"
        ).model_dump(mode="json"),
        "evidence_matrix": {"status": evidence_matrix_status},
    }
    write_file(index / "evidence_index.json", json.dumps(evidence_index, indent=2) + "\n")
    input_validation = TestInputValidation(
        execution_handoff_ref=make_test_artifact_ref(root / "execution_handoff.json", "execution_handoff"),
        execution_output_package_ref=make_test_artifact_ref(
            project / ".aegis" / "artifacts" / "execution" / "execution-run" / "output" / "execution_output_package.json",
            "execution_output_package",
        ),
        readme_valid=True,
        handoff_json_valid=True,
        output_status_valid=True,
        output_next_stage_valid=True,
        boundary_flags_valid=True,
        required_refs_valid=True,
        hash_verified=True,
        status="accepted",
    )
    write_file(root / "input_validation.json", input_validation.model_dump_json(indent=2) + "\n")
    output = TestOutputPackage(
        run_id="test-run",
        status=status,  # type: ignore[arg-type]
        input_validation_ref=make_test_artifact_ref(root / "input_validation.json", "input_validation"),
        approved_test_plan_ref=make_test_artifact_ref(root / "approved_test_plan.json", "approved_test_plan"),
        test_execution_manifest_ref=make_test_artifact_ref(root / "test_execution_manifest.json", "test_execution_manifest"),
        completeness_check_ref=make_test_artifact_ref(root / "completeness_check.json", "completeness_check"),
        evidence_check_ref=make_test_artifact_ref(root / "evidence_check.json", "evidence_check"),
        artifact_schema_check_ref=make_test_artifact_ref(
            root / "artifact_schema_validation_results.json", "artifact_schema"
        ),
        final_test_report_ref=make_test_artifact_ref(root / "final_test_report.md", "final_test_report"),
        state_boundary_results_ref=make_test_artifact_ref(index / "state_boundary_results.json", "state_boundary"),
        boundary=TestBoundaryFlags(),
        next_stage=next_stage,  # type: ignore[arg-type]
        evidence_index_ref=make_test_artifact_ref(index / "evidence_index.json", "evidence_index"),
    )
    output_path = root / "test_output_package.json"
    write_file(output_path, output.model_dump_json(indent=2) + "\n")
    return output_path


def write_causal_context(project: Path, payload: dict) -> Path:
    path = project / ".aegis" / "artifacts" / "context" / "causal_context.json"
    write_file(path, json.dumps(payload, indent=2) + "\n")
    return path


def final_review_input(
    project: Path,
    requirement_dir: Path,
    review_dir: Path,
    execution_output_path: Path,
    test_output_path: Path,
    *,
    knowledge_context_path: Path | None = None,
    causal_context_path: Path | None = None,
) -> FinalReviewInputPackage:
    return FinalReviewInputPackage(
        run_id="final-review-run",
        project_root=project,
        code_root=project / "code",
        requirement_package_dir=requirement_dir,
        requirement_review_package_dir=review_dir,
        execution_output_package_path=execution_output_path,
        test_output_package_path=test_output_path,
        knowledge_context_path=knowledge_context_path,
        causal_context_path=causal_context_path,
    )


def test_final_review_accepts_clean_passed_handoff(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    test_output = write_test_output(project)

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )

    assert output.status == "accepted"
    assert output.decision == "accept_for_master_closeout"
    assert output.next_stage == "master_closeout"
    assert output.threat_checklist_matrix_ref is not None
    assert output.state_boundary_results_ref is not None


def test_final_review_blocks_execution_output_not_completed(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project, status="blocked", next_stage="master")
    test_output = write_test_output(project)

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )

    assert output.status == "blocked"
    assert output.decision == "governance_blocker"
    assert output.blocker == "execution_not_completed"


def test_final_review_requests_test_evidence_when_test_schema_failed(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    test_output = write_test_output(project, schema_status="failed")

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )

    assert output.status == "blocked"
    assert output.decision == "request_more_test_evidence"
    assert output.blocker == "test_artifact_schema_failed"


def test_final_review_rejects_code_surface_hash_mismatch(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project, changed_hash="f" * 64)
    test_output = write_test_output(project)

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )

    assert output.status == "rejected"
    assert output.decision == "reject_to_execution"
    assert output.blocker == "code_surface_mismatch"


def test_final_review_rejects_critical_threat(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    write_file(
        project / "code" / "feature.py",
        "import os\n\ndef answer(user_input):\n    return os.system(user_input)\n",
    )
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    test_output = write_test_output(project)

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )

    assert output.status == "rejected"
    assert output.decision == "reject_to_execution"
    assert output.blocker == "critical_threat"


def test_final_review_routes_active_causal_conflict_to_master(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    test_output = write_test_output(project)
    causal_context = write_causal_context(
        project,
        {
            "causal_refs": [
                {
                    "causal_ref": "causal-1",
                    "status": "active",
                    "conflict_materiality": "blocker",
                    "assessment_reason": "Implementation conflicts with active route decision.",
                }
            ]
        },
    )

    output = run_deterministic_final_review_subgraph(
        final_review_input(
            project,
            requirement_dir,
            review_dir,
            execution_output,
            test_output,
            causal_context_path=causal_context,
        )
    )

    assert output.status == "blocked"
    assert output.decision == "causal_conflict_detected"
    assert output.next_stage == "master"


def test_final_review_records_candidate_conflict_without_treating_it_as_truth(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    test_output = write_test_output(project)
    causal_context = write_causal_context(
        project,
        {
            "causal_refs": [
                {
                    "causal_ref": "candidate-1",
                    "status": "candidate",
                    "conflict_materiality": "blocker",
                    "assessment_reason": "Candidate disagrees, but is not admitted truth.",
                }
            ]
        },
    )

    output = run_deterministic_final_review_subgraph(
        final_review_input(
            project,
            requirement_dir,
            review_dir,
            execution_output,
            test_output,
            causal_context_path=causal_context,
        )
    )

    assert output.status == "accepted"
    assert output.decision == "accept_for_master_closeout"


def test_final_review_blocks_artifact_ref_outside_allowed_roots(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    outside = tmp_path / "outside.txt"
    write_file(outside, "outside artifact\n")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    payload = json.loads(execution_output.read_text(encoding="utf-8"))
    payload["implementation_artifact_ref"] = execution_ref(outside, "outside").model_dump(mode="json")
    write_file(execution_output, json.dumps(payload, indent=2) + "\n")
    test_output = write_test_output(project)

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )

    assert output.status == "blocked"
    assert output.decision == "governance_blocker"
    assert output.blocker == "artifact_root_escape"


def test_final_review_blocks_missing_material_context(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    test_output = write_test_output(project)
    knowledge_context = project / ".aegis" / "artifacts" / "context" / "knowledge_context.json"
    write_file(
        knowledge_context,
        json.dumps(
            {
                "store_availability": "missing",
                "requirement_context_sufficient": False,
                "missing_context_items": [{"item": "accepted platform constraint", "material": True}],
            },
            indent=2,
        )
        + "\n",
    )

    package = final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    package = package.model_copy(update={"knowledge_context_path": knowledge_context})
    output = run_deterministic_final_review_subgraph(package)

    assert output.status == "blocked"
    assert output.decision == "governance_blocker"
    assert output.blocker == "context_unavailable"


def test_final_review_rejects_unsatisfied_hard_requirement(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project, requirement_mapping_status="not_satisfied")
    test_output = write_test_output(project)

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )

    assert output.status == "rejected"
    assert output.decision == "reject_to_execution"
    assert output.blocker == "hard_requirement_mismatch"


def test_final_review_rejects_test_changeset_hash_mismatch(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    test_output = write_test_output(project, test_changeset_hash="0" * 64)

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )

    assert output.status == "rejected"
    assert output.decision == "reject_to_execution"
    assert output.blocker == "code_surface_mismatch"


def test_final_review_threat_checklist_covers_required_surface(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    test_output = write_test_output(project)

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )
    matrix = json.loads(Path(output.threat_checklist_matrix_ref.path).read_text(encoding="utf-8"))
    checklist_ids = {item["checklist_id"] for item in matrix["items"]}

    assert checklist_ids == {
        "THREAT-001-shell-command-execution",
        "THREAT-002-path-input-handling",
        "THREAT-003-file-delete-move-overwrite-recursive-scan",
        "THREAT-004-secret-read-or-logging",
        "THREAT-005-network-or-remote-publication",
        "THREAT-006-truth-store-write",
        "THREAT-007-governance-bypass",
        "THREAT-008-unbounded-resource-or-concurrency",
        "THREAT-009-raw-report-trust",
        "THREAT-010-unadmitted-dependency-or-platform-assumption",
    }
    assert matrix["all_items_answered"] is True


def test_final_review_blocks_own_state_boundary_failure(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    test_output = write_test_output(project)
    package = final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    package = package.model_copy(update={"max_serialized_state_bytes": 1})

    output = run_deterministic_final_review_subgraph(package)

    assert output.status == "blocked"
    assert output.decision == "governance_blocker"
    assert output.blocker == "schema_validation_failed"


def test_final_review_blocks_missing_requirements_json_without_crashing(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    (requirement_dir / "requirements.json").unlink()
    execution_output = write_execution_output(project)
    test_output = write_test_output(project)

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )

    assert output.status == "blocked"
    assert output.decision == "governance_blocker"
    assert output.blocker == "missing_required_artifact"


def test_final_review_blocks_invalid_requirements_json_without_crashing(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    write_file(requirement_dir / "requirements.json", "{not-json\n")
    execution_output = write_execution_output(project)
    test_output = write_test_output(project)

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )

    assert output.status == "blocked"
    assert output.decision == "governance_blocker"
    assert output.blocker == "schema_validation_failed"


def test_final_review_uses_explicit_requirement_mapping_ref_not_changeset_directory(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    mapping_dir = project / ".aegis" / "artifacts" / "execution" / "execution-run" / "mapping"
    execution_output = write_execution_output(project, requirement_mapping_dir=mapping_dir)
    guessed_mapping = project / ".aegis" / "artifacts" / "execution" / "execution-run" / "output" / "requirement_mapping.json"
    assert not guessed_mapping.exists()
    test_output = write_test_output(project)

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )

    assert output.status == "accepted"
    assert output.decision == "accept_for_master_closeout"


def test_final_review_rejects_unexpected_current_code_change(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    test_output = write_test_output(project)
    write_file(project / "code" / "unexpected.py", "def unexpected():\n    return True\n")

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )

    assert output.status == "rejected"
    assert output.decision == "reject_to_execution"
    assert output.blocker == "code_surface_mismatch"


def test_final_review_changed_files_only_mode_does_not_mark_existing_files_unexpected(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    write_file(project / "code" / "stable.py", "def stable():\n    return 'unchanged'\n")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project, include_full_code_manifest=False)
    test_output = write_test_output(project)

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )
    consistency = json.loads(Path(output.code_surface_consistency_ref.path).read_text(encoding="utf-8"))

    assert output.status == "accepted"
    assert output.decision == "accept_for_master_closeout"
    assert consistency["comparison_mode"] == "changed_files_only"
    assert consistency["unexpected_current_changes"] == []


def test_final_review_full_manifest_mode_detects_unexpected_current_change(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project, include_full_code_manifest=True)
    test_output = write_test_output(project)
    write_file(project / "code" / "unexpected_after_manifest.py", "VALUE = 1\n")

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )
    consistency = json.loads(Path(output.code_surface_consistency_ref.path).read_text(encoding="utf-8"))

    assert output.status == "rejected"
    assert output.decision == "reject_to_execution"
    assert consistency["comparison_mode"] == "full_manifest"
    assert consistency["unexpected_current_changes"] == ["unexpected_after_manifest.py"]


@pytest.mark.parametrize(
    ("source", "expected_checklist_id"),
    [
        ("from pathlib import Path\nPath('causal/fact.json').write_text('truth_written')\n", "THREAT-006-truth-store-write"),
        ("import requests\nrequests.post('https://example.com')\n", "THREAT-005-network-or-remote-publication"),
        ("skip_review = True\n", "THREAT-007-governance-bypass"),
        ("password = 'secret'\nprint(password)\n", "THREAT-004-secret-read-or-logging"),
        ("import shutil\nshutil.rmtree('/tmp/x')\n", "THREAT-003-file-delete-move-overwrite-recursive-scan"),
    ],
)
def test_final_review_blocks_non_shell_high_risk_threats(
    tmp_path: Path,
    source: str,
    expected_checklist_id: str,
) -> None:
    project = make_project(tmp_path / "project")
    write_file(project / "code" / "feature.py", source)
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    test_output = write_test_output(project)

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )
    matrix = json.loads(Path(output.threat_checklist_matrix_ref.path).read_text(encoding="utf-8"))
    threat_item = next(item for item in matrix["items"] if item["checklist_id"] == expected_checklist_id)

    assert output.status == "rejected"
    assert output.decision == "reject_to_execution"
    assert output.blocker == "critical_threat"
    assert threat_item["status"] == "yes"
    assert threat_item["blocker"] is True


def test_final_review_accepts_with_scope_limits_for_warning_only_threat(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    write_file(project / "code" / "feature.py", "import platform\nplatform.system()\n")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    test_output = write_test_output(project)

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )

    assert output.status == "accepted_with_scope_limits"
    assert output.decision == "accept_with_scope_limits"
    assert output.next_stage == "master_closeout"
    assert output.scope_limits


def test_final_review_classifies_absent_context_as_not_requested_without_defaulting_available(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    test_output = write_test_output(project)

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )
    context = json.loads(Path(output.context_resolution_ref.path).read_text(encoding="utf-8"))

    assert context["store_availability"] == {"knowledge": "not_requested", "causal": "not_requested"}
    assert output.status == "accepted"


def test_final_review_blocks_explicit_missing_context_without_materiality_clearance(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    test_output = write_test_output(project)
    knowledge_context = project / ".aegis" / "artifacts" / "context" / "knowledge_context.json"
    write_file(
        knowledge_context,
        json.dumps(
            {
                "store_availability": "missing",
                "missing_context_items": [
                    {
                        "item": "project hard constraint context unavailable",
                        "material": True,
                    }
                ],
            },
            indent=2,
        )
        + "\n",
    )

    output = run_deterministic_final_review_subgraph(
        final_review_input(
            project,
            requirement_dir,
            review_dir,
            execution_output,
            test_output,
            knowledge_context_path=knowledge_context,
        )
    )
    context = json.loads(Path(output.context_resolution_ref.path).read_text(encoding="utf-8"))

    assert context["store_availability"]["knowledge"] == "missing"
    assert output.status == "blocked"
    assert output.decision == "governance_blocker"
    assert output.blocker == "context_unavailable"


def test_final_review_artifact_hash_manifest_excludes_self_mutating_outputs(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    test_output = write_test_output(project)

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )
    rows = json.loads(Path(output.artifact_hashes_ref.path).read_text(encoding="utf-8"))
    paths = {row["path"] for row in rows}

    assert "index/artifact_hashes.json" not in paths
    assert "final_report/final_review_output_package.json" not in paths
    final_output_hash = Path(output.final_review_run_dir) / "index" / "final_review_output_package.sha256"
    assert final_output_hash.exists()
    assert final_output_hash.read_text(encoding="utf-8").strip() == sha256_file(Path(output.final_review_report_ref.path).parent / "final_review_output_package.json")


def test_final_review_schema_validation_records_model_validation(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    test_output = write_test_output(project)

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )
    schema_validation = json.loads(Path(output.artifact_schema_validation_ref.path).read_text(encoding="utf-8"))
    checked = {item["schema_name"]: item["status"] for item in schema_validation["checked_artifacts"]}

    assert schema_validation["status"] == "passed"
    assert checked["FinalReviewOutputPackage"] == "passed"
    assert checked["FinalReviewDecisionTrace"] == "passed"
    assert checked["ThreatChecklistMatrix"] == "passed"
    assert checked["evidence_index"] == "passed"
    assert checked["artifact_hashes"] == "passed"
    assert checked["tool_action_plan"] == "passed"
    assert checked["tool_execution_records"] == "passed"
    assert checked["denied_actions"] == "passed"


def test_final_review_tool_audit_records_read_path_hashes_and_intent(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    test_output = write_test_output(project)

    output = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )
    audit_dir = Path(output.tool_audit_ref.path).parent
    records = [
        json.loads(line)
        for line in (audit_dir / "tool_execution_records.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert records
    assert all(row["intent"] == "final_review_evidence_read" for row in records)
    assert all(row["side_effect_level"] == "read_only" for row in records)
    assert all(row["result_sha256"] for row in records)


def test_final_review_tool_audit_records_denied_prohibited_action_fixtures(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    test_output = write_test_output(project)

    package_payload = final_review_input(
        project, requirement_dir, review_dir, execution_output, test_output
    ).model_dump(mode="python")
    package_payload["prohibited_action_attempts"] = [
        {
            "attempted_action": "run_tests_from_final_review",
            "requested_tool": "pytest",
            "reason": "Final Review must consume Test evidence instead of running tests.",
            "risk_class": "test_execution",
            "affected_artifact_refs": [str(test_output)],
        },
        {
            "attempted_action": "modify_project_code_from_final_review",
            "requested_tool": "write_file",
            "reason": "Final Review must review code, not modify code.",
            "risk_class": "code_mutation",
            "affected_artifact_refs": [str(project / "code" / "feature.py")],
        },
        {
            "attempted_action": "publish_remote_result_from_final_review",
            "requested_tool": "network_publish",
            "reason": "Final Review must not perform remote publication.",
            "risk_class": "external_side_effect",
            "affected_artifact_refs": [],
        },
    ]
    package = FinalReviewInputPackage.model_validate(package_payload)

    output = run_deterministic_final_review_subgraph(package)
    denied = json.loads(Path(output.tool_audit_ref.path).read_text(encoding="utf-8"))

    assert {row["attempted_action"] for row in denied} == {
        "run_tests_from_final_review",
        "modify_project_code_from_final_review",
        "publish_remote_result_from_final_review",
    }
    assert all(row["denial_decision"] == "denied" for row in denied)
    assert all(row["requested_tool"] for row in denied)
    assert all(row["reason"] for row in denied)
    assert all(row["risk_class"] for row in denied)
    assert all(isinstance(row["affected_artifact_refs"], list) for row in denied)


def test_final_review_same_run_id_different_input_uses_distinct_run_dir(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    test_output = write_test_output(project)

    first = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )

    changed_execution_output = write_execution_output(project, requirement_mapping_status="not_satisfied")
    second = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, changed_execution_output, test_output)
    )

    assert second.final_review_run_dir != first.final_review_run_dir
    assert second.decision == "reject_to_execution"
    assert second.blocker == "hard_requirement_mismatch"


def test_final_review_same_run_id_changed_code_surface_uses_distinct_run_dir(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    requirement_dir, review_dir = write_requirement_packages(project)
    execution_output = write_execution_output(project)
    test_output = write_test_output(project)

    first = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )

    write_file(project / "code" / "feature.py", "def answer():\n    return 43\n")
    second = run_deterministic_final_review_subgraph(
        final_review_input(project, requirement_dir, review_dir, execution_output, test_output)
    )

    assert second.final_review_run_dir != first.final_review_run_dir
    assert second.decision == "reject_to_execution"
    assert second.blocker == "code_surface_mismatch"


def test_final_review_output_package_rejects_inconsistent_decision_status() -> None:
    base_ref = {
        "artifact_id": "a",
        "artifact_type": "t",
        "path": "p",
        "readme_path": "r",
        "sha256": "0" * 64,
        "created_by_node": "unit_test",
    }
    payload = {
        "run_id": "run",
        "status": "accepted",
        "decision": "request_more_test_evidence",
        "next_stage": "test",
        "final_review_run_dir": "run-dir",
        "input_validation_ref": base_ref,
        "context_resolution_ref": base_ref,
        "code_surface_manifest_ref": base_ref,
        "requirement_alignment_ref": base_ref,
        "threat_findings_ref": base_ref,
        "code_quality_findings_ref": base_ref,
        "evidence_review_ref": base_ref,
        "causal_consistency_ref": base_ref,
        "threat_checklist_matrix_ref": base_ref,
        "code_surface_consistency_ref": base_ref,
        "decision_precedence_trace_ref": base_ref,
        "final_review_report_ref": base_ref,
        "decision_ref": base_ref,
        "next_route_ref": base_ref,
        "run_manifest_ref": base_ref,
        "evidence_index_ref": base_ref,
        "artifact_hashes_ref": base_ref,
        "artifact_schema_validation_ref": base_ref,
        "state_boundary_results_ref": base_ref,
        "tool_audit_ref": base_ref,
    }

    with pytest.raises(ValidationError):
        FinalReviewOutputPackage.model_validate(payload)
