from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from aegis.modules.execution.artifacts import ExecutionArtifactWriter
from aegis.modules.execution.input_validation import validate_master_handoff
from aegis.modules.execution.models import ArtifactRef
from aegis.modules.execution.path_policy import ExecutionPathPolicyError
from aegis.modules.execution.store_binding import bind_execution_project


def make_project(root: Path) -> Path:
    (root / "code").mkdir(parents=True)
    (root / "archive").mkdir()
    (root / "knowledge").mkdir()
    (root / "causal").mkdir()
    return root


def write_valid_handoff(root: Path) -> Path:
    handoff = root / ".aegis" / "artifacts" / "master_handoff" / "handoff-1"
    handoff.mkdir(parents=True)
    (handoff / "README.md").write_text("Read this first.\n", encoding="utf-8", newline="\n")
    (handoff / "requirement_document.md").write_text("Requirement.\n", encoding="utf-8", newline="\n")
    (handoff / "requirement_review_document.md").write_text(
        "Review.\n", encoding="utf-8", newline="\n"
    )
    (handoff / "accepted_constraints.json").write_text("[]\n", encoding="utf-8", newline="\n")
    (handoff / "rejected_constraints.json").write_text("[]\n", encoding="utf-8", newline="\n")
    (handoff / "evidence_refs.json").write_text("[]\n", encoding="utf-8", newline="\n")
    (handoff / "known_limits.md").write_text("None.\n", encoding="utf-8", newline="\n")
    return handoff


def test_artifact_writer_requires_readme_and_blocks_code_root_write(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    binding = bind_execution_project(project, run_id="run-1")
    writer = ExecutionArtifactWriter(binding)
    artifact_dir = writer.artifact_dir("output")
    readme_ref = writer.write_text(artifact_dir / "README.md", "Output package.\n", "output_readme")

    assert ArtifactRef.model_validate(readme_ref.model_dump())

    with pytest.raises(ExecutionPathPolicyError, match="must not write runtime artifacts under code_root"):
        writer.write_text(project / "code" / "bad.txt", "bad\n", "bad")


def test_input_validation_blocks_missing_requirement_document(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    handoff = write_valid_handoff(project)
    (handoff / "requirement_document.md").unlink()
    binding = bind_execution_project(project, run_id="run-1")
    writer = ExecutionArtifactWriter(binding)

    validation = validate_master_handoff(
        master_handoff_path=handoff,
        master_handoff_ref=None,
        writer=writer,
    )

    assert validation.status == "blocked"
    assert validation.blocker is not None
    assert validation.blocker.label == "missing_required_evidence"


def test_input_validation_accepts_complete_handoff(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    handoff = write_valid_handoff(project)
    binding = bind_execution_project(project, run_id="run-1")
    writer = ExecutionArtifactWriter(binding)

    validation = validate_master_handoff(
        master_handoff_path=handoff,
        master_handoff_ref=None,
        writer=writer,
    )

    assert validation.status == "accepted"
    assert validation.required_files_present is True
    assert validation.hashes_valid is True


def test_input_validation_blocks_hash_mismatch_manifest(tmp_path: Path) -> None:
    project = make_project(tmp_path / "project")
    handoff = write_valid_handoff(project)
    manifest = {
        "files": [
            {
                "name": "requirement_document.md",
                "sha256": hashlib.sha256(
                    (handoff / "requirement_document.md").read_bytes()
                ).hexdigest(),
            },
            {
                "name": "accepted_constraints.json",
                "sha256": hashlib.sha256((handoff / "accepted_constraints.json").read_bytes()).hexdigest(),
            },
        ]
    }
    (handoff / "handoff_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (handoff / "accepted_constraints.json").write_text(
        "[{\"changed\": true}]\n",
        encoding="utf-8",
        newline="\n",
    )
    binding = bind_execution_project(project, run_id="run-1")
    writer = ExecutionArtifactWriter(binding)

    validation = validate_master_handoff(
        master_handoff_path=handoff,
        master_handoff_ref=None,
        writer=writer,
    )

    assert validation.status == "blocked"
    assert validation.hashes_valid is False
    assert validation.blocker is not None
    assert validation.blocker.label == "artifact_integrity_error"
