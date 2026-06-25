"""Execution-to-Test handoff validation."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

from pydantic import ValidationError

from aegis.modules.execution.models import ExecutionOutputPackage, ExecutionToTestHandoff
from aegis.modules.test.artifacts import TestArtifactWriter
from aegis.modules.test.models import ArtifactRef, TestBlocker, TestInputValidation
from aegis.modules.test.path_io import (
    path_exists,
    path_is_dir,
    path_is_file,
    read_bytes,
    read_text,
    same_path,
)


def validate_execution_handoff(
    *,
    execution_handoff_dir: str | Path,
    execution_output_package_path: str | Path,
    writer: TestArtifactWriter,
) -> TestInputValidation:
    """Validate Execution output before any Test planning or execution."""

    handoff_dir = Path(execution_handoff_dir).resolve()
    output_path = Path(execution_output_package_path).resolve()
    root = writer.artifact_dir("input")
    writer.write_text(root / "README.md", "Test input validation artifacts.\n", "input_readme")

    readme_valid = path_exists(handoff_dir / "README.md")
    handoff_path = handoff_dir / "execution_to_test_handoff.json"
    handoff_valid = False
    required_refs_valid = False
    output_status_valid = False
    output_next_stage_valid = False
    boundary_flags_valid = False
    hash_verified = False
    reasons: list[str] = []

    handoff_ref = _safe_ref(handoff_dir, "execution_handoff", "execution")
    output_ref = _safe_ref(output_path, "execution_output_package", "execution")

    handoff_payload: ExecutionToTestHandoff | None = None
    if not readme_valid:
        reasons.append("missing README.md in execution handoff")
    try:
        handoff_payload = ExecutionToTestHandoff.model_validate_json(
            read_text(handoff_path)
        )
        handoff_valid = True
    except (OSError, ValidationError, json.JSONDecodeError) as exc:
        reasons.append(f"invalid execution_to_test_handoff.json: {exc}")

    output_payload: ExecutionOutputPackage | None = None
    try:
        output_payload = ExecutionOutputPackage.model_validate_json(
            read_text(output_path)
        )
    except (OSError, ValidationError, json.JSONDecodeError) as exc:
        reasons.append(f"invalid execution_output_package.json: {exc}")

    if handoff_payload is not None:
        required_refs_valid = _required_refs_exist(handoff_payload)
        if not required_refs_valid:
            reasons.append("one or more required execution handoff refs are missing")

    if output_payload is not None:
        output_status_valid = output_payload.status == "completed"
        output_next_stage_valid = output_payload.next_stage == "test_subgraph"
        boundary_flags_valid = (
            not output_payload.boundary.wrote_archive_truth
            and not output_payload.boundary.wrote_knowledge_truth
            and not output_payload.boundary.wrote_causal_truth
            and not output_payload.boundary.remote_published
        )
        if not output_status_valid:
            reasons.append("ExecutionOutputPackage.status is not completed")
        if not output_next_stage_valid:
            reasons.append("ExecutionOutputPackage.next_stage is not test_subgraph")
        if not boundary_flags_valid:
            reasons.append("ExecutionOutputPackage boundary flags are invalid")
        if handoff_payload is not None and output_payload.execution_to_test_handoff_ref is not None:
            hash_verified = same_path(output_payload.execution_to_test_handoff_ref.path, handoff_path)
        else:
            hash_verified = False
        if not hash_verified:
            reasons.append("ExecutionOutputPackage handoff ref does not match input handoff")

    status = "accepted" if not reasons else "blocked"
    blocker = None
    if reasons:
        blocker = TestBlocker(
            label="input_invalid",
            reason="; ".join(reasons),
            evidence_refs=[str(handoff_dir), str(output_path)],
            next_action="execution",
            retry_allowed=True,
        )

    validation = TestInputValidation(
        execution_handoff_ref=handoff_ref,
        execution_output_package_ref=output_ref,
        readme_valid=readme_valid,
        handoff_json_valid=handoff_valid,
        output_status_valid=output_status_valid,
        output_next_stage_valid=output_next_stage_valid,
        boundary_flags_valid=boundary_flags_valid,
        required_refs_valid=required_refs_valid,
        hash_verified=hash_verified,
        status=status,
        blocker=blocker,
    )
    writer.write_json(root / "test_input_validation.json", validation, "test_input_validation")
    writer.write_json(
        root / "execution_handoff_hash_report.json",
        {
            "status": "verified" if hash_verified else "not_verified",
            "execution_handoff_dir": str(handoff_dir),
            "execution_output_package_path": str(output_path),
            "reasons": reasons,
        },
        "execution_handoff_hash_report",
    )
    return validation


def _required_refs_exist(handoff: ExecutionToTestHandoff) -> bool:
    refs = [
        handoff.implementation_artifact_ref,
        handoff.implementation_changeset_ref,
        handoff.changed_files_ref,
        handoff.simple_test_evidence_ref,
        handoff.known_limits_ref,
        handoff.execution_causal_candidate_ref,
        handoff.approved_review_ref,
        handoff.requirement_mapping_ref,
    ]
    return all(path_exists(ref.path) for ref in refs)


def _safe_ref(path: Path, artifact_type: str, created_by_node: str) -> ArtifactRef:
    readme = path / "README.md" if path_is_dir(path) else path.parent / "README.md"
    sha = "0" * 64
    if path_exists(path) and path_is_file(path):
        sha = hashlib.sha256(read_bytes(path)).hexdigest()
    elif path_exists(path) and path_is_dir(path) and path_exists(readme):
        sha = hashlib.sha256(read_bytes(readme)).hexdigest()
    return ArtifactRef(
        artifact_id=f"{artifact_type}-{path.name}",
        artifact_type=artifact_type,
        path=str(path),
        readme_path=str(readme),
        sha256=sha,
        created_by_node=created_by_node,
    )
