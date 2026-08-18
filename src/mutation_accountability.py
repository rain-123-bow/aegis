from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from run_state_integrity import synchronize_run_state_reservation


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
    projected_state = _read_json_object(state_path, "run state")
    if projected_state.get("reservation_token") is not None:
        from aegis_runtime import load_run_state
        state = load_run_state(runtime_root, run_id)
    else:
        state = projected_state
    if (
        state.get("schema") != "aegis.run_state.v10"
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
    payload = {
        "schema": MUTATION_REASON_SCHEMA,
        "run_id": run_id,
        "user_confirmation_id": user_confirmation_id,
        "reason": reason_descriptor,
        "recorded_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    _atomic_write_bytes(record_path, _canonical_json(payload))
    state["master_review_status"] = "USER_REASON_RECORDED"
    state["mutation_reason_record"] = _descriptor(record_path)
    encoded_state = _canonical_json(state)
    synchronize_run_state_reservation(
        Path(runtime_root).resolve(), run_id, state, encoded_state
    )
    _atomic_write_bytes(state_path, encoded_state)
    return payload


def _descriptor(path: Path) -> dict[str, object]:
    content = _read_required_file(path, "accountability artifact")
    return {
        "path": str(path.resolve()),
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    raw = _read_required_file(path, label)
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise MutationAccountabilityError(f"{label} is invalid JSON") from error
    if not isinstance(value, dict):
        raise MutationAccountabilityError(f"{label} must be a JSON object")
    return value


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
