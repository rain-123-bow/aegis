from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable

from final_review_verdict import (
    FinalReviewVerdictError,
    validate_final_review_verdict,
)
from run_state_integrity import synchronize_run_state_reservation
from path_security import (
    PathSecurityError,
    is_within,
    lexical_absolute,
    read_regular_file,
    require_no_reparse,
)


FINAL_CONFIRMATION_SCHEMA = "aegis.master_final_review_confirmation.v1"
_RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class FinalReviewConfirmationError(RuntimeError):
    pass


def record_final_review_confirmation(
    runtime_root: str | Path,
    run_id: str,
    *,
    decision: str,
    master_review_path: str | Path,
    evidence_paths: Iterable[str | Path],
) -> dict[str, Any]:
    if _RUN_ID_PATTERN.fullmatch(run_id) is None or ".." in run_id:
        raise ValueError("run_id contains unsupported path characters")
    if decision not in {"CONFIRMED", "DISPUTED"}:
        raise ValueError("decision must be CONFIRMED or DISPUTED")
    state_path = (
        Path(runtime_root).resolve() / "runs" / run_id / "RUN_STATE.json"
    ).resolve()
    projected_state_bytes, projected_state = _read_json_object(state_path, "run state")
    if projected_state.get("reservation_token") is not None:
        from aegis_runtime import load_run_state
        state = load_run_state(runtime_root, run_id)
        state_bytes = _canonical_json(state)
    else:
        state = projected_state
        state_bytes = projected_state_bytes
    if state.get("schema") != "aegis.run_state.v10" or state.get("run_id") != run_id:
        raise FinalReviewConfirmationError("run state identity or schema is invalid")
    graph_state = state.get("graph_state")
    if (
        state.get("status") != "terminated"
        or not isinstance(graph_state, dict)
        or graph_state.get("current_node") != "F"
        or graph_state.get("status") is not False
        or state.get("master_review_status") != "PENDING"
    ):
        raise FinalReviewConfirmationError(
            "only a terminal F failure awaiting Master review can be confirmed"
        )
    artifact_raw = state.get("artifact_path")
    if not isinstance(artifact_raw, str) or not artifact_raw:
        raise FinalReviewConfirmationError("run state has no artifact path")
    artifact_root = Path(artifact_raw).resolve()
    expected_artifact = (state_path.parent / "artifacts").resolve()
    if artifact_root != expected_artifact:
        raise FinalReviewConfirmationError("run state artifact path is invalid")

    project_raw = state.get("project_root")
    if not isinstance(project_raw, str) or not project_raw:
        raise FinalReviewConfirmationError("run state has no project root")
    project_root = Path(project_raw).resolve()
    final_review_path = artifact_root / "FINAL_REVIEW.md"
    attempts = state.get("execution_attempts")
    final_attempt = (
        attempts[-1]
        if isinstance(attempts, list) and attempts and isinstance(attempts[-1], dict)
        else None
    )
    verdict_path = artifact_root / "FINAL_REVIEW_VERDICT.json"
    if (
        final_attempt is None
        or final_attempt.get("node") != "F"
        or final_attempt.get("status") != "completed"
        or final_attempt.get("final_review_verdict") != "FAIL"
        or final_attempt.get("final_review_verdict_path") != str(verdict_path)
    ):
        raise FinalReviewConfirmationError(
            "terminal F failure has no sealed FAIL verdict"
        )
    verdict = _descriptor(
        verdict_path,
        allowed_root=artifact_root,
        label="F verdict",
    )
    if verdict["sha256"] != final_attempt.get("final_review_verdict_sha256"):
        raise FinalReviewConfirmationError("sealed F verdict hash does not match run state")
    try:
        validated_verdict = validate_final_review_verdict(
            verdict_path,
            project_root=project_root,
            artifact_root=artifact_root,
            workflow_run_id=run_id,
            expected_status=False,
        )
    except FinalReviewVerdictError as error:
        raise FinalReviewConfirmationError(
            f"sealed F verdict evidence is invalid: {error}"
        ) from error
    if list(validated_verdict.evidence_ids) != final_attempt.get(
        "final_review_evidence_ids"
    ):
        raise FinalReviewConfirmationError(
            "sealed F verdict evidence IDs do not match run state"
        )
    final_review = _descriptor(
        final_review_path,
        allowed_root=artifact_root,
        label="F final review",
    )
    master_source = Path(master_review_path).resolve()
    master_bytes = _read_required_file(master_source, "Master review")
    sealed_master_path = artifact_root / "MASTER_FINAL_REVIEW.md"
    if sealed_master_path.exists():
        if sealed_master_path.read_bytes() != master_bytes:
            raise FinalReviewConfirmationError(
                "sealed Master final review already exists with different content"
            )
    else:
        _atomic_write_bytes(sealed_master_path, master_bytes)
    master_review = _descriptor(
        sealed_master_path,
        allowed_root=artifact_root,
        label="sealed Master review",
    )

    evidence: list[dict[str, object]] = []
    seen: set[Path] = set()
    for raw_path in evidence_paths:
        path = Path(os.path.abspath(Path(raw_path)))
        if path in seen:
            raise FinalReviewConfirmationError(
                "Master confirmation evidence index contains a duplicate path"
            )
        seen.add(path)
        evidence.append(
            _descriptor(path, allowed_root=artifact_root, label="confirmation evidence")
        )
    if final_review_path not in seen:
        evidence.insert(0, final_review)
    if verdict_path not in seen:
        evidence.insert(1, verdict)
    if not evidence:
        raise FinalReviewConfirmationError(
            "Master confirmation requires a non-empty evidence index"
        )

    confirmation_path = artifact_root / "MASTER_FINAL_REVIEW_CONFIRMATION.json"
    payload = {
        "schema": FINAL_CONFIRMATION_SCHEMA,
        "run_id": run_id,
        "decision": decision,
        "reviewed_run_state_sha256": hashlib.sha256(state_bytes).hexdigest(),
        "final_review": final_review,
        "master_review": master_review,
        "evidence_index": evidence,
    }
    encoded = _canonical_json(payload)
    if confirmation_path.exists():
        if confirmation_path.read_bytes() != encoded:
            raise FinalReviewConfirmationError(
                "Master final-review confirmation is already recorded"
            )
    else:
        _atomic_write_bytes(confirmation_path, encoded)
    confirmation = _descriptor(
        confirmation_path,
        allowed_root=artifact_root,
        label="Master final-review confirmation",
    )
    state["master_review_status"] = decision
    state["master_review_confirmation"] = confirmation
    encoded_state = _canonical_json(state)
    synchronize_run_state_reservation(
        Path(runtime_root).resolve(), run_id, state, encoded_state
    )
    _atomic_write_bytes(state_path, encoded_state)
    return payload


def _descriptor(path: Path, *, allowed_root: Path, label: str) -> dict[str, object]:
    try:
        root = lexical_absolute(allowed_root)
        lexical_path = lexical_absolute(path)
        if not is_within(lexical_path, root):
            raise FinalReviewConfirmationError(
                f"{label} is outside the run artifact root"
            )
        require_no_reparse(root, lexical_path, label=label)
        content, _identity = read_regular_file(
            lexical_path,
            allowed_root=root,
            label=label,
        )
    except PathSecurityError as error:
        raise FinalReviewConfirmationError(
            str(error)
        ) from error
    return {
        "path": str(lexical_path),
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _read_json_object(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    raw = _read_required_file(path, label)
    try:
        payload = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise FinalReviewConfirmationError(f"{label} is invalid JSON") from error
    if not isinstance(payload, dict):
        raise FinalReviewConfirmationError(f"{label} must be a JSON object")
    return raw, payload


def _read_required_file(path: Path, label: str) -> bytes:
    try:
        if not path.is_file():
            raise FinalReviewConfirmationError(f"{label} is missing: {path}")
        value = path.read_bytes()
    except FinalReviewConfirmationError:
        raise
    except OSError as error:
        raise FinalReviewConfirmationError(f"cannot read {label}: {error}") from error
    if not value:
        raise FinalReviewConfirmationError(f"{label} is empty")
    return value


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
