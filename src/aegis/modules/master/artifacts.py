from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from aegis.modules.master.models import (
    ExecutionHandoffPackage,
    MasterArtifactRef,
    RequirementConversation,
    RequirementDocument,
    RequirementReviewDocument,
)


def _json_dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _sha256_files(paths: list[Path], package_dir: Path) -> str:
    hasher = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        hasher.update(str(path.relative_to(package_dir)).encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _model_payload(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


class MasterArtifactStore:
    def __init__(self, project_root: str | Path, run_ref: str):
        self.project_root = Path(project_root)
        self.root = self.project_root / ".aegis" / "runtime" / "master" / run_ref

    def write_intake(self, conversation: RequirementConversation) -> MasterArtifactRef:
        return self._write_package(
            kind="requirement_intake",
            artifact_id=conversation.conversation_id,
            primary_name="intake-summary.md",
            primary_text=self._render_intake(conversation),
            machine_name="intake.json",
            machine_payload=_model_payload(conversation),
            readme_purpose="PM intake closure package.",
            reading_order=["intake-summary.md", "intake.json"],
        )

    def read_intake(self, artifact_ref: MasterArtifactRef) -> RequirementConversation:
        return RequirementConversation.model_validate(self._read_json(artifact_ref))

    def write_requirement(self, document: RequirementDocument) -> MasterArtifactRef:
        return self._write_package(
            kind="requirement_document",
            artifact_id=document.document_id,
            primary_name="requirement.md",
            primary_text=self._render_requirement(document),
            machine_name="requirement.json",
            machine_payload=_model_payload(document),
            readme_purpose="User-approved requirement document package.",
            reading_order=["requirement.md", "requirement.json"],
        )

    def read_requirement(self, artifact_ref: MasterArtifactRef) -> RequirementDocument:
        return RequirementDocument.model_validate(self._read_json(artifact_ref))

    def write_review(self, review: RequirementReviewDocument) -> MasterArtifactRef:
        return self._write_package(
            kind="requirement_review",
            artifact_id=review.document_id,
            primary_name="review.md",
            primary_text=self._render_review(review),
            machine_name="review.json",
            machine_payload=_model_payload(review),
            readme_purpose="Independent requirement review package.",
            reading_order=["review.md", "review.json"],
        )

    def read_review(self, artifact_ref: MasterArtifactRef) -> RequirementReviewDocument:
        return RequirementReviewDocument.model_validate(self._read_json(artifact_ref))

    def write_handoff(self, handoff: ExecutionHandoffPackage) -> MasterArtifactRef:
        return self._write_package(
            kind="execution_handoff",
            artifact_id=handoff.handoff_id,
            primary_name="execution-handoff.md",
            primary_text=self._render_handoff(handoff),
            machine_name="execution-handoff.json",
            machine_payload=_model_payload(handoff),
            readme_purpose="Execution handoff package.",
            reading_order=["execution-handoff.md", "execution-handoff.json"],
        )

    def read_handoff(self, artifact_ref: MasterArtifactRef) -> ExecutionHandoffPackage:
        return ExecutionHandoffPackage.model_validate(self._read_json(artifact_ref))

    def _write_package(
        self,
        *,
        kind: str,
        artifact_id: str,
        primary_name: str,
        primary_text: str,
        machine_name: str,
        machine_payload: dict[str, Any],
        readme_purpose: str,
        reading_order: list[str],
    ) -> MasterArtifactRef:
        package_dir = self.root / kind / artifact_id
        primary_path = package_dir / primary_name
        machine_path = package_dir / machine_name
        readme_path = package_dir / "README.md"
        _write_text(primary_path, primary_text)
        _write_text(machine_path, _json_dump(machine_payload))
        readme = self._render_readme(
            purpose=readme_purpose,
            primary_name=primary_name,
            machine_name=machine_name,
            reading_order=reading_order,
        )
        _write_text(readme_path, readme)
        sha256 = _sha256_files([readme_path, primary_path, machine_path], package_dir)
        return MasterArtifactRef(
            artifact_id=artifact_id,
            kind=kind,  # type: ignore[arg-type]
            package_dir=str(package_dir),
            readme_path=str(readme_path),
            primary_document_path=str(primary_path),
            machine_data_path=str(machine_path),
            sha256=sha256,
        )

    @staticmethod
    def _read_json(artifact_ref: MasterArtifactRef) -> dict[str, Any]:
        return json.loads(Path(artifact_ref.machine_data_path).read_text(encoding="utf-8"))

    @staticmethod
    def _render_readme(
        *,
        purpose: str,
        primary_name: str,
        machine_name: str,
        reading_order: list[str],
    ) -> str:
        ordered = "\n".join(f"{index}. `{name}`" for index, name in enumerate(reading_order, 1))
        return "\n".join(
            [
                "# Master Module Artifact Package",
                "",
                f"Purpose: {purpose}",
                "",
                "Read this file first. It names the package contents and reading order.",
                "",
                "## Files",
                "",
                f"- `{primary_name}`: human-readable professional artifact.",
                f"- `{machine_name}`: machine-readable schema payload.",
                "",
                "## Reading Order",
                "",
                ordered,
                "",
            ]
        )

    @staticmethod
    def _render_intake(conversation: RequirementConversation) -> str:
        tech = ", ".join(conversation.technical_path_requests) or "None"
        deliverables = ", ".join(conversation.deliverable_requests) or "Not specified"
        return "\n".join(
            [
                "# PM Intake Closure",
                "",
                f"Purpose: {conversation.purpose}",
                f"Technical path requests: {tech}",
                f"Deliverable requests: {deliverables}",
                "",
                "Unsupported technical path requests remain preferences until evidence is supplied.",
                "",
            ]
        )

    @staticmethod
    def _render_requirement(document: RequirementDocument) -> str:
        constraints = "\n".join(
            f"- {item.text} [{item.admission}]: {item.reason}" for item in document.constraints
        ) or "- None"
        criteria = "\n".join(f"- {item}" for item in document.success_criteria) or "- None"
        assumptions = "\n".join(f"- {item}" for item in document.assumptions) or "- None"
        excluded = (
            "\n".join(f"- {item}" for item in document.excluded_subjective_preferences)
            or "- None"
        )
        return "\n".join(
            [
                "# Requirement Document",
                "",
                f"Objective: {document.objective}",
                "",
                "## Constraint Admission",
                "",
                constraints,
                "",
                "## Success Criteria",
                "",
                criteria,
                "",
                "## Assumptions",
                "",
                assumptions,
                "",
                "## Preferences Not Admitted As Hard Constraints",
                "",
                excluded,
                "",
            ]
        )

    @staticmethod
    def _render_review(review: RequirementReviewDocument) -> str:
        findings = "\n".join(
            f"- {item.requirement_item}: {item.decision}. {item.why}" for item in review.findings
        ) or "- None"
        debates = "\n".join(
            f"- {item.issue_id}: {item.status}. {item.question}" for item in review.debate_issues
        ) or "- None"
        return "\n".join(
            [
                "# Requirement Review",
                "",
                f"Conclusion: {review.conclusion}",
                "",
                "## Findings",
                "",
                findings,
                "",
                "## Debate Issues",
                "",
                debates,
                "",
            ]
        )

    @staticmethod
    def _render_handoff(handoff: ExecutionHandoffPackage) -> str:
        accepted = "\n".join(f"- {item}" for item in handoff.accepted_constraints) or "- None"
        rejected = "\n".join(f"- {item}" for item in handoff.rejected_constraints) or "- None"
        risks = "\n".join(f"- {item}" for item in handoff.risks) or "- None"
        limits = "\n".join(f"- {item}" for item in handoff.open_limits) or "- None"
        return "\n".join(
            [
                "# Execution Handoff",
                "",
                f"Status: {handoff.status}",
                "",
                "## Accepted Constraints",
                "",
                accepted,
                "",
                "## Rejected Constraints",
                "",
                rejected,
                "",
                "## Risks",
                "",
                risks,
                "",
                "## Open Limits",
                "",
                limits,
                "",
            ]
        )
