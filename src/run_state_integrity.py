from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


CHECKPOINT_RELATIVE_PATH = Path("project_state/checkpoints.sqlite3")
RESERVATION_TABLE = "aegis_run_reservations"
ACCOUNTABILITY_TABLE = "aegis_project_accountability"


class RunStateIntegrityError(RuntimeError):
    pass


def synchronize_run_state_reservation(
    runtime_root: str | Path,
    run_id: str,
    state: dict[str, object],
    encoded_state: bytes,
) -> None:
    """Update the reservation digest after an authorized terminal-state annotation.

    Unit fixtures without a reservation token remain supported. Production states
    with a token must have a matching reservation row and fixed artifact path.
    """
    token = state.get("reservation_token")
    if token is None:
        return
    if not isinstance(token, str) or len(token) != 32:
        raise RunStateIntegrityError("run state reservation token is invalid")
    artifact = state.get("artifact_path")
    status = state.get("status")
    if not isinstance(artifact, str) or not isinstance(status, str):
        raise RunStateIntegrityError("run state reservation fields are invalid")
    runtime = Path(runtime_root).resolve()
    expected_artifact = (runtime / "runs" / run_id / "artifacts").resolve()
    if Path(artifact).resolve() != expected_artifact:
        raise RunStateIntegrityError("run state artifact path is not run-scoped")
    database = runtime / CHECKPOINT_RELATIVE_PATH
    try:
        connection = sqlite3.connect(database, timeout=30, isolation_level=None)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                f"""
                SELECT reservation_token, artifact_path
                FROM {RESERVATION_TABLE}
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if row is None or row[0] != token:
                raise RunStateIntegrityError("run reservation identity mismatch")
            if Path(str(row[1])).resolve() != expected_artifact:
                raise RunStateIntegrityError("run reservation artifact path changed")
            connection.execute(
                f"""
                UPDATE {RESERVATION_TABLE}
                SET state_sha256 = ?, state_status = ?, state_updated_at_utc = ?,
                    state_blob = ?
                WHERE run_id = ? AND reservation_token = ?
                """,
                (
                    hashlib.sha256(encoded_state).hexdigest(),
                    status,
                    datetime.now(UTC).isoformat(timespec="microseconds").replace(
                        "+00:00", "Z"
                    ),
                    encoded_state,
                    run_id,
                    token,
                ),
            )
            if connection.total_changes < 1:
                raise RunStateIntegrityError("run reservation update did not commit")
            project_id_hex = state.get("project_id_hex")
            if isinstance(project_id_hex, str) and state.get(
                "master_review_status"
            ) == "USER_REASON_RECORDED":
                connection.execute(
                    f"DELETE FROM {ACCOUNTABILITY_TABLE} WHERE project_id_hex = ? AND run_id = ?",
                    (project_id_hex, run_id),
                )
            connection.execute("COMMIT")
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
            f"cannot synchronize run-state reservation: {error}"
        ) from error
