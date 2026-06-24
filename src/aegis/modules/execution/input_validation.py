"""Master handoff validation for Execution Subgraph v2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from aegis.modules.execution.artifacts import ExecutionArtifactWriter
from aegis.modules.execution.models import (
    ArtifactRef,
    ExecutionBlocker,
    ExecutionInputValidation,
)


REQUIRED_HANDOFF_FILES = [
    "README.md",
    "requirement_document.md",
    "requirement_review_document.md",
    "accepted_constraints.json",
    "rejected_constraints.json",
    "evidence_refs.json",
    "known_limits.md",
]


def validate_master_handoff(
    *,
    master_handoff_path: str | Path,
    master_handoff_ref: ArtifactRef | None,
    writer: ExecutionArtifactWriter,
) -> ExecutionInputValidation:
    """Validate Master handoff before any Execution business logic runs."""

    handoff_path = Path(master_handoff_path).resolve()
    manifest: dict[str, object] = {"handoff_path": str(handoff_path), "files": []}
    missing = [name for name in REQUIRED_HANDOFF_FILES if not (handoff_path / name).exists()]
    json_validity = {
        "accepted_constraints_valid": _json_list_valid(handoff_path / "accepted_constraints.json"),
        "rejected_constraints_valid": _json_list_valid(handoff_path / "rejected_constraints.json"),
        "evidence_refs_valid": _json_list_valid(handoff_path / "evidence_refs.json"),
    }
    readme_valid = (handoff_path / "README.md").exists()
    required_present = not missing
    hash_report = _verify_hash_manifest(handoff_path)
    hashes_valid = hash_report["status"] != "mismatch"
    valid = required_present and readme_valid and all(json_validity.values()) and hashes_valid

    handoff_ref = master_handoff_ref or _folder_ref(handoff_path)
    blocker = None
    if not valid:
        reasons = []
        if missing:
            reasons.append(f"missing files: {', '.join(missing)}")
        for key, value in json_validity.items():
            if not value:
                reasons.append(key)
        if not hashes_valid:
            reasons.append("handoff hash manifest mismatch")
        blocker = ExecutionBlocker(
            label="artifact_integrity_error" if not hashes_valid else "missing_required_evidence",
            reason="; ".join(reasons) or "invalid master handoff",
            evidence_refs=[str(handoff_path)],
            next_action="master",
            parent_route_label="master",
            retry_allowed=True,
        )

    for file_name in REQUIRED_HANDOFF_FILES:
        path = handoff_path / file_name
        manifest["files"].append({"name": file_name, "exists": path.exists()})

    validation = ExecutionInputValidation(
        master_handoff_ref=handoff_ref,
        required_files_present=required_present,
        readme_valid=readme_valid,
        hashes_valid=hashes_valid,
        accepted_constraints_valid=json_validity["accepted_constraints_valid"],
        rejected_constraints_valid=json_validity["rejected_constraints_valid"],
        evidence_refs_valid=json_validity["evidence_refs_valid"],
        requirement_review_valid=(handoff_path / "requirement_review_document.md").exists(),
        status="accepted" if valid else "blocked",
        blocker=blocker,
    )
    root = writer.artifact_dir("input_validation")
    writer.write_text(root / "README.md", "Execution input validation artifact.\n", "input_readme")
    writer.write_json(root / "handoff_file_manifest.json", manifest, "handoff_manifest")
    writer.write_json(root / "execution_input_validation.json", validation, "input_validation")
    writer.write_json(root / "hash_verification_report.json", hash_report, "hash_report")
    writer.write_text(root / "hash_verification_report.md", _hash_report_markdown(hash_report), "hash_report")
    return validation


def _json_list_valid(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return isinstance(value, list)


def _folder_ref(path: Path) -> ArtifactRef:
    readme = path / "README.md"
    sha = "0" * 64
    if readme.exists():
        import hashlib

        sha = hashlib.sha256(readme.read_bytes()).hexdigest()
    return ArtifactRef(
        artifact_id=f"master-handoff-{path.name}",
        artifact_type="master_handoff",
        path=str(path),
        readme_path=str(readme),
        sha256=sha,
        created_by_node="master",
    )


def _verify_hash_manifest(handoff_path: Path) -> dict[str, object]:
    manifest_path = handoff_path / "handoff_manifest.json"
    if not manifest_path.exists():
        return {"status": "not_provided", "manifest_path": str(manifest_path), "checks": []}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "status": "mismatch",
            "manifest_path": str(manifest_path),
            "error": f"invalid JSON: {exc}",
            "checks": [],
        }
    expected = _extract_expected_hashes(manifest)
    checks: list[dict[str, object]] = []
    status = "matched"
    for name, expected_sha in sorted(expected.items()):
        path = handoff_path / name
        exists = path.exists()
        actual_sha = _sha256_file(path) if exists else None
        matched = exists and actual_sha == expected_sha
        if not matched:
            status = "mismatch"
        checks.append(
            {
                "name": name,
                "exists": exists,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "matched": matched,
            }
        )
    if not expected:
        status = "mismatch"
    return {"status": status, "manifest_path": str(manifest_path), "checks": checks}


def _extract_expected_hashes(manifest: object) -> dict[str, str]:
    if isinstance(manifest, dict) and isinstance(manifest.get("files"), list):
        output: dict[str, str] = {}
        for item in manifest["files"]:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("path")
            sha = item.get("sha256")
            if isinstance(name, str) and isinstance(sha, str) and _looks_like_sha256(sha):
                output[name.replace("\\", "/")] = sha
        return output
    if isinstance(manifest, dict):
        return {
            str(name).replace("\\", "/"): sha
            for name, sha in manifest.items()
            if isinstance(sha, str) and _looks_like_sha256(sha)
        }
    return {}


def _hash_report_markdown(report: dict[str, object]) -> str:
    lines = ["# Handoff Hash Verification", "", f"- status: `{report['status']}`", ""]
    for check in report.get("checks", []):
        if not isinstance(check, dict):
            continue
        lines.append(
            "- "
            f"{check.get('name')}: matched={check.get('matched')} "
            f"expected={check.get('expected_sha256')} actual={check.get('actual_sha256')}"
        )
    return "\n".join(lines) + "\n"


def _looks_like_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdefABCDEF" for char in value)


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
