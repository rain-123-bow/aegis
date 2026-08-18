from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from path_security import (
    PathSecurityError,
    is_within,
    lexical_absolute,
    read_regular_file,
    require_no_reparse,
    same_path,
)


FINAL_REVIEW_VERDICT_SCHEMA = "aegis.final_review_verdict.v1"
FINAL_REVIEW_VERDICT_NAME = "FINAL_REVIEW_VERDICT.json"

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_TOP_LEVEL_FIELDS = {
    "schema",
    "workflow_run_id",
    "verdict",
    "conclusion",
    "reasons",
    "evidence_index",
}
_EVIDENCE_FIELDS = {"evidence_id", "path", "size", "sha256"}
_NONBLANK_EVIDENCE_IDS = {"test-report", "final-review"}


class FinalReviewVerdictError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ValidatedFinalReviewVerdict:
    path: Path
    sha256: str
    verdict: str
    evidence_ids: tuple[str, ...]


def validate_final_review_verdict(
    verdict_path: str | Path,
    *,
    project_root: str | Path,
    artifact_root: str | Path,
    workflow_run_id: str,
    expected_status: bool,
    required_evidence: Sequence[Mapping[str, object]] = (),
) -> ValidatedFinalReviewVerdict:
    project = lexical_absolute(project_root)
    artifacts = lexical_absolute(artifact_root)
    path = lexical_absolute(verdict_path)
    expected_path = artifacts / FINAL_REVIEW_VERDICT_NAME
    if not same_path(path, expected_path):
        raise FinalReviewVerdictError(
            f"final review verdict must use the fixed path: {expected_path}"
        )
    try:
        require_no_reparse(artifacts, artifacts, label="artifact root")
        require_no_reparse(artifacts, path, label="final review verdict")
    except PathSecurityError as error:
        raise FinalReviewVerdictError(str(error)) from error
    raw, payload = _read_json(path)
    if not isinstance(payload, dict) or set(payload) != _TOP_LEVEL_FIELDS:
        raise FinalReviewVerdictError("final review verdict has invalid fields")
    if payload["schema"] != FINAL_REVIEW_VERDICT_SCHEMA:
        raise FinalReviewVerdictError("final review verdict has an unsupported schema")
    if payload["workflow_run_id"] != workflow_run_id:
        raise FinalReviewVerdictError("final review verdict run identity does not match")
    expected_verdict = "PASS" if expected_status else "FAIL"
    if payload["verdict"] != expected_verdict:
        raise FinalReviewVerdictError(
            "final review verdict does not match the F node status"
        )
    if not isinstance(payload["conclusion"], str) or not payload["conclusion"].strip():
        raise FinalReviewVerdictError("final review verdict has no conclusion")
    reasons = payload["reasons"]
    if (
        not isinstance(reasons, list)
        or not reasons
        or not all(isinstance(item, str) and item.strip() for item in reasons)
    ):
        raise FinalReviewVerdictError("final review verdict has no explicit reasons")
    evidence = payload["evidence_index"]
    if not isinstance(evidence, list) or not evidence:
        raise FinalReviewVerdictError("final review verdict has no evidence index")
    evidence_ids: list[str] = []
    evidence_paths: list[Path] = []
    for index, item in enumerate(evidence):
        if not isinstance(item, dict) or set(item) != _EVIDENCE_FIELDS:
            raise FinalReviewVerdictError(
                f"final review evidence {index} has invalid fields"
            )
        evidence_id = item["evidence_id"]
        if not isinstance(evidence_id, str) or not evidence_id:
            raise FinalReviewVerdictError(
                f"final review evidence {index} has an invalid ID"
            )
        evidence_ids.append(evidence_id)
        evidence_path, evidence_content = _validate_descriptor(
            item,
            index=index,
            allowed_roots=(project, artifacts),
        )
        if evidence_id in _NONBLANK_EVIDENCE_IDS and not evidence_content.strip():
            raise FinalReviewVerdictError(
                f"final review evidence is blank: {evidence_id}"
            )
        evidence_paths.append(evidence_path)
    if len(set(evidence_ids)) != len(evidence_ids):
        raise FinalReviewVerdictError("final review evidence IDs are not unique")
    if len(set(evidence_paths)) != len(evidence_paths):
        raise FinalReviewVerdictError("final review evidence paths are not unique")
    if (artifacts / "FINAL_REVIEW.md").resolve() not in evidence_paths:
        raise FinalReviewVerdictError(
            "final review evidence index does not include FINAL_REVIEW.md"
        )
    evidence_by_id = {
        str(item["evidence_id"]): item
        for item in evidence
        if isinstance(item, dict)
    }
    required_ids: set[str] = set()
    for index, required in enumerate(required_evidence):
        required_item = dict(required)
        if set(required_item) != _EVIDENCE_FIELDS:
            raise FinalReviewVerdictError(
                f"required final review evidence {index} has invalid fields"
            )
        required_id = required_item.get("evidence_id")
        if not isinstance(required_id, str) or not required_id:
            raise FinalReviewVerdictError(
                f"required final review evidence {index} has an invalid ID"
            )
        if required_id in required_ids:
            raise FinalReviewVerdictError(
                "required final review evidence IDs are not unique"
            )
        required_ids.add(required_id)
        _required_path, required_content = _validate_descriptor(
            required_item,
            index=index,
            allowed_roots=(project, artifacts),
        )
        if required_id in _NONBLANK_EVIDENCE_IDS and not required_content.strip():
            raise FinalReviewVerdictError(
                f"required final review evidence is blank: {required_id}"
            )
        actual_item = evidence_by_id.get(required_id)
        if actual_item is None:
            raise FinalReviewVerdictError(
                f"final review verdict is missing required evidence: {required_id}"
            )
        if actual_item != required_item:
            raise FinalReviewVerdictError(
                f"final review required evidence descriptor changed: {required_id}"
            )
    return ValidatedFinalReviewVerdict(
        path=path,
        sha256=hashlib.sha256(raw).hexdigest(),
        verdict=expected_verdict,
        evidence_ids=tuple(evidence_ids),
    )


def _validate_descriptor(
    item: dict[str, Any],
    *,
    index: int,
    allowed_roots: tuple[Path, ...],
) -> tuple[Path, bytes]:
    raw_path = item["path"]
    if not isinstance(raw_path, str) or not raw_path:
        raise FinalReviewVerdictError(
            f"final review evidence {index} has an invalid path"
        )
    raw_evidence_path = Path(raw_path)
    if not raw_evidence_path.is_absolute():
        raise FinalReviewVerdictError(
            f"final review evidence {index} path is not absolute"
        )
    path = lexical_absolute(raw_evidence_path)
    if not any(is_within(path, root) for root in allowed_roots):
        raise FinalReviewVerdictError(
            f"final review evidence {index} is outside allowed roots"
        )
    containing_root = next(root for root in allowed_roots if is_within(path, root))
    try:
        content, _identity = read_regular_file(
            path,
            allowed_root=containing_root,
            label=f"final review evidence {index}",
        )
    except PathSecurityError as error:
        raise FinalReviewVerdictError(str(error)) from error
    size = item["size"]
    sha256 = item["sha256"]
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise FinalReviewVerdictError(
            f"final review evidence {index} has an invalid size"
        )
    if not isinstance(sha256, str) or _SHA256_PATTERN.fullmatch(sha256) is None:
        raise FinalReviewVerdictError(
            f"final review evidence {index} has an invalid SHA-256"
        )
    if len(content) != size or hashlib.sha256(content).hexdigest() != sha256:
        raise FinalReviewVerdictError(
            f"final review evidence {index} does not match its descriptor"
        )
    return path, content


def _read_json(path: Path) -> tuple[bytes, Any]:
    try:
        raw, _identity = read_regular_file(
            path,
            allowed_root=path.parent,
            label="final review verdict",
        )
        payload = json.loads(raw.decode("utf-8", errors="strict"))
    except (OSError, PathSecurityError, UnicodeError, json.JSONDecodeError) as error:
        raise FinalReviewVerdictError(
            f"cannot read final review verdict: {path}: {error}"
        ) from error
    return raw, payload
