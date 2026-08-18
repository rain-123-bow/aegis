from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


CHECKPOINT_RELATIVE_PATH = Path("project_state/checkpoints.sqlite3")
RESERVATION_TABLE = "aegis_run_reservations"
ACCOUNTABILITY_TABLE = "aegis_project_accountability"
_TOKEN_PATTERN = re.compile(r"[0-9a-f]{32}")
_PROJECT_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


class RunStateIntegrityError(RuntimeError):
    pass


def transition_run_state_reservation(
    runtime_root: str | Path,
    run_id: str,
    current_state: dict[str, object],
    current_encoded_state: bytes,
    transition: Callable[[], tuple[dict[str, object], bytes, Any]],
) -> Any:
    """Serialize an authorized terminal annotation with its artifact writes.

    ``transition`` executes while the authoritative SQLite row is locked.  Its
    external artifact writes therefore occur only after the supplied old state
    has been proven current.  The final UPDATE also compares the old digest, so
    a stale or concurrent caller cannot overwrite a completed transition.
    """
    runtime = Path(runtime_root).resolve()
    token, artifact, status = _validate_state_identity(
        runtime, run_id, current_state, current_encoded_state
    )
    database = runtime / CHECKPOINT_RELATIVE_PATH
    try:
        connection = sqlite3.connect(database, timeout=30, isolation_level=None)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                f"""
                SELECT reservation_token, artifact_path, state_sha256,
                       state_status, state_blob
                FROM {RESERVATION_TABLE}
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            old_digest = hashlib.sha256(current_encoded_state).hexdigest()
            if row is None or row[0] != token:
                raise RunStateIntegrityError("run reservation identity mismatch")
            if Path(str(row[1])).resolve() != artifact:
                raise RunStateIntegrityError("run reservation artifact path changed")
            stored_blob = _blob_bytes(row[4])
            if (
                row[2] != old_digest
                or row[3] != status
                or stored_blob != current_encoded_state
            ):
                raise RunStateIntegrityError(
                    "authoritative run state changed before annotation"
                )

            new_state, new_encoded_state, result = transition()
            _validate_transition(
                runtime,
                run_id,
                current_state,
                new_state,
                new_encoded_state,
            )
            new_status = str(new_state["status"])
            cursor = connection.execute(
                f"""
                UPDATE {RESERVATION_TABLE}
                SET state_sha256 = ?, state_status = ?, state_updated_at_utc = ?,
                    state_blob = ?
                WHERE run_id = ? AND reservation_token = ? AND state_sha256 = ?
                """,
                (
                    hashlib.sha256(new_encoded_state).hexdigest(),
                    new_status,
                    _utc_now_text(),
                    new_encoded_state,
                    run_id,
                    token,
                    old_digest,
                ),
            )
            if cursor.rowcount != 1:
                raise RunStateIntegrityError(
                    "run reservation compare-and-swap did not commit"
                )
            _synchronize_accountability_marker(connection, run_id, new_state)
            connection.execute("COMMIT")
            return result
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
    except RunStateIntegrityError:
        raise
    except sqlite3.Error as error:
        raise RunStateIntegrityError(
            f"cannot transition run-state reservation: {error}"
        ) from error


def _validate_state_identity(
    runtime: Path,
    run_id: str,
    state: dict[str, object],
    encoded_state: bytes,
) -> tuple[str, Path, str]:
    token = state.get("reservation_token")
    if not isinstance(token, str) or _TOKEN_PATTERN.fullmatch(token) is None:
        raise RunStateIntegrityError("run state reservation token is invalid")
    artifact_raw = state.get("artifact_path")
    status = state.get("status")
    if not isinstance(artifact_raw, str) or not isinstance(status, str):
        raise RunStateIntegrityError("run state reservation fields are invalid")
    artifact = Path(artifact_raw).resolve()
    expected_artifact = (runtime / "runs" / run_id / "artifacts").resolve()
    if artifact != expected_artifact:
        raise RunStateIntegrityError("run state artifact path is not run-scoped")
    try:
        decoded = json.loads(encoded_state.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise RunStateIntegrityError("run state bytes are invalid JSON") from error
    if decoded != state:
        raise RunStateIntegrityError("run state bytes do not encode the supplied state")
    if state.get("run_id") != run_id:
        raise RunStateIntegrityError("run state identity mismatch")
    return token, artifact, status


def _validate_transition(
    runtime: Path,
    run_id: str,
    old_state: dict[str, object],
    new_state: dict[str, object],
    new_encoded_state: bytes,
) -> None:
    _validate_state_identity(runtime, run_id, new_state, new_encoded_state)
    old_review = old_state.get("master_review_status")
    new_review = new_state.get("master_review_status")
    changed = {
        key
        for key in set(old_state) | set(new_state)
        if old_state.get(key) != new_state.get(key)
        or (key in old_state) != (key in new_state)
    }
    if old_review == "PENDING" and new_review in {"CONFIRMED", "DISPUTED"}:
        expected = {"master_review_status", "master_review_confirmation"}
    elif old_review == "REQUIRES_USER_REASON" and new_review == "USER_REASON_RECORDED":
        expected = {"master_review_status", "mutation_reason_record"}
    else:
        raise RunStateIntegrityError("run-state annotation transition is unauthorized")
    if changed != expected:
        raise RunStateIntegrityError(
            "run-state annotation changed fields outside its authority"
        )


def _synchronize_accountability_marker(
    connection: sqlite3.Connection,
    run_id: str,
    state: dict[str, object],
) -> None:
    project_id_hex = state.get("project_id_hex")
    if (
        not isinstance(project_id_hex, str)
        or _PROJECT_ID_PATTERN.fullmatch(project_id_hex) is None
    ):
        return
    if state.get("master_review_status") != "USER_REASON_RECORDED":
        return
    marker = {
        "schema": "aegis.project_accountability_marker.v2",
        "project_id_hex": project_id_hex,
        "run_id": run_id,
        "status": "USER_REASON_RECORDED",
        "mutation_reason_record": state.get("mutation_reason_record"),
    }
    connection.execute(
        f"""
        INSERT INTO {ACCOUNTABILITY_TABLE}(
            project_id_hex, run_id, marker_json, updated_at_utc
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(project_id_hex) DO UPDATE SET
            run_id = excluded.run_id,
            marker_json = excluded.marker_json,
            updated_at_utc = excluded.updated_at_utc
        """,
        (
            project_id_hex,
            run_id,
            json.dumps(marker, ensure_ascii=False, sort_keys=True),
            _utc_now_text(),
        ),
    )


def _blob_bytes(value: object) -> bytes | None:
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    return None


def _utc_now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
