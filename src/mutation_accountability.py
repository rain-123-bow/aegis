from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from run_state_integrity import (
    RunStateIntegrityError,
    transition_run_state_reservation,
)
from runtime_contracts import RUN_STATE_SCHEMA


MUTATION_REASON_SCHEMA = "aegis.frozen_input_mutation_reason.v1"
_RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class MutationAccountabilityError(RuntimeError):
    pass


def record_frozen_input_mutation_reason(
    runtime_root: str | Path,
    run_id: str,
    *,
    reason_path: str | Path,
    user_confirmation_id: str,
) -> dict[str, Any]:
    if _RUN_ID_PATTERN.fullmatch(run_id) is None or ".." in run_id:
        raise ValueError("run_id contains unsupported path characters")
    if not isinstance(user_confirmation_id, str) or not user_confirmation_id.strip():
        raise ValueError("user_confirmation_id must not be empty")
    state_path = (
        Path(runtime_root).resolve() / "runs" / run_id / "RUN_STATE.json"
    ).resolve()
    try:
        from aegis_runtime import load_run_state

        state = load_run_state(runtime_root, run_id)
    except (OSError, RuntimeError, ValueError) as error:
        raise MutationAccountabilityError(
            f"cannot load authoritative run state: {error}"
        ) from error
    if (
        state.get("schema") != RUN_STATE_SCHEMA
        or state.get("run_id") != run_id
        or state.get("status") != "terminated"
        or state.get("termination_reason_code") != "FROZEN_INPUT_MUTATION"
        or state.get("master_review_status") != "REQUIRES_USER_REASON"
    ):
        raise MutationAccountabilityError(
            "run is not awaiting a user reason for frozen-input mutation"
        )
    artifact_raw = state.get("artifact_path")
    if not isinstance(artifact_raw, str) or not artifact_raw:
        raise MutationAccountabilityError("run state has no artifact path")
    artifacts = Path(artifact_raw).resolve()
    if artifacts != (state_path.parent / "artifacts").resolve():
        raise MutationAccountabilityError("run state artifact path is invalid")
    reason_bytes = _read_required_file(Path(reason_path).resolve(), "user reason")
    current_encoded_state = _canonical_json(state)

    def commit_transition() -> tuple[dict[str, object], bytes, dict[str, Any]]:
        sealed_reason_path = artifacts / "FROZEN_INPUT_MUTATION_REASON.md"
        if sealed_reason_path.exists():
            if sealed_reason_path.read_bytes() != reason_bytes:
                raise MutationAccountabilityError(
                    "a different frozen-input mutation reason is already sealed"
                )
        else:
            _atomic_write_bytes(sealed_reason_path, reason_bytes)
        reason_descriptor = _descriptor(sealed_reason_path)
        record_path = artifacts / "FROZEN_INPUT_MUTATION_REASON.json"
        if record_path.exists():
            payload = _load_existing_record(
                record_path,
                run_id=run_id,
                user_confirmation_id=user_confirmation_id,
                reason_descriptor=reason_descriptor,
            )
        else:
            payload = {
                "schema": MUTATION_REASON_SCHEMA,
                "run_id": run_id,
                "user_confirmation_id": user_confirmation_id,
                "reason": reason_descriptor,
                "recorded_at_utc": datetime.now(UTC)
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z"),
            }
            _atomic_write_bytes(record_path, _canonical_json(payload))
        new_state = dict(state)
        new_state["master_review_status"] = "USER_REASON_RECORDED"
        new_state["mutation_reason_record"] = _descriptor(record_path)
        encoded_state = _canonical_json(new_state)
        return new_state, encoded_state, payload

    try:
        payload = transition_run_state_reservation(
            Path(runtime_root).resolve(),
            run_id,
            state,
            current_encoded_state,
            commit_transition,
        )
    except RunStateIntegrityError as error:
        raise MutationAccountabilityError(str(error)) from error
    new_state = dict(state)
    new_state["master_review_status"] = "USER_REASON_RECORDED"
    new_state["mutation_reason_record"] = _descriptor(
        artifacts / "FROZEN_INPUT_MUTATION_REASON.json"
    )
    encoded_state = _canonical_json(new_state)
    _atomic_write_bytes(state_path, encoded_state)
    return payload


def _load_existing_record(
    path: Path,
    *,
    run_id: str,
    user_confirmation_id: str,
    reason_descriptor: dict[str, object],
) -> dict[str, Any]:
    try:
        payload = json.loads(
            _read_required_file(path, "mutation accountability record").decode(
                "utf-8", errors="strict"
            )
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise MutationAccountabilityError(
            "existing frozen-input mutation record is invalid JSON"
        ) from error
    if (
        not isinstance(payload, dict)
        or set(payload)
        != {
            "schema",
            "run_id",
            "user_confirmation_id",
            "reason",
            "recorded_at_utc",
        }
        or payload.get("schema") != MUTATION_REASON_SCHEMA
        or payload.get("run_id") != run_id
        or payload.get("user_confirmation_id") != user_confirmation_id
        or payload.get("reason") != reason_descriptor
        or not isinstance(payload.get("recorded_at_utc"), str)
        or not str(payload["recorded_at_utc"]).strip()
    ):
        raise MutationAccountabilityError(
            "existing frozen-input mutation record does not match this confirmation"
        )
    return payload


def _descriptor(path: Path) -> dict[str, object]:
    content = _read_required_file(path, "accountability artifact")
    return {
        "path": str(path.resolve()),
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _read_required_file(path: Path, label: str) -> bytes:
    try:
        if not path.is_file():
            raise MutationAccountabilityError(f"{label} is missing: {path}")
        value = path.read_bytes()
    except MutationAccountabilityError:
        raise
    except OSError as error:
        raise MutationAccountabilityError(f"cannot read {label}: {error}") from error
    if not value:
        raise MutationAccountabilityError(f"{label} is empty")
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
