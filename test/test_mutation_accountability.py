from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from mutation_accountability import record_frozen_input_mutation_reason
from run_state_integrity import (
    RunStateIntegrityError,
    transition_run_state_reservation,
)


class MutationAccountabilityTests(unittest.TestCase):
    def test_records_user_reason_without_changing_terminal_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = root / "runtime"
            run_root = runtime / "runs" / "run-mutated"
            artifacts = run_root / "artifacts"
            artifacts.mkdir(parents=True)
            state = {
                "schema": "aegis.run_state.v13",
                "run_id": "run-mutated",
                "reservation_token": "b" * 32,
                "status": "terminated",
                "artifact_path": str(artifacts.resolve()),
                "termination_reason_code": "FROZEN_INPUT_MUTATION",
                "master_review_status": "REQUIRES_USER_REASON",
                "delivery_eligible": False,
            }
            state_path = run_root / "RUN_STATE.json"
            state_bytes = (
                json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode("utf-8")
            state_path.write_bytes(state_bytes)
            database = runtime / "project_state" / "checkpoints.sqlite3"
            database.parent.mkdir(parents=True)
            connection = sqlite3.connect(database)
            try:
                connection.execute(
                    """
                    CREATE TABLE aegis_run_reservations (
                        run_id TEXT PRIMARY KEY,
                        reservation_token TEXT NOT NULL UNIQUE,
                        artifact_path TEXT NOT NULL,
                        created_at_utc TEXT NOT NULL,
                        state_sha256 TEXT,
                        state_status TEXT,
                        state_updated_at_utc TEXT,
                        state_blob BLOB
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO aegis_run_reservations
                        (run_id, reservation_token, artifact_path, created_at_utc,
                         state_sha256, state_status, state_updated_at_utc, state_blob)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "run-mutated",
                        "b" * 32,
                        str(artifacts.resolve()),
                        "2026-08-18T00:00:00Z",
                        hashlib.sha256(state_bytes).hexdigest(),
                        "terminated",
                        "2026-08-18T00:00:00Z",
                        state_bytes,
                    ),
                )
                connection.commit()
            finally:
                connection.close()
            reason = root / "reason.md"
            reason.write_text("The user changed requirement R1 during node C.\n", encoding="utf-8")

            record_frozen_input_mutation_reason(
                runtime,
                "run-mutated",
                reason_path=reason,
                user_confirmation_id="user-confirmation-17",
            )

            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["master_review_status"], "USER_REASON_RECORDED")
            self.assertFalse(saved["delivery_eligible"])
            self.assertTrue(Path(saved["mutation_reason_record"]["path"]).is_file())

            stale_callback_ran = False

            def stale_transition() -> tuple[dict[str, object], bytes, None]:
                nonlocal stale_callback_ran
                stale_callback_ran = True
                return state, state_bytes, None

            with self.assertRaisesRegex(
                RunStateIntegrityError,
                "changed before annotation",
            ):
                transition_run_state_reservation(
                    runtime,
                    "run-mutated",
                    state,
                    state_bytes,
                    stale_transition,
                )
            self.assertFalse(stale_callback_ran)


if __name__ == "__main__":
    unittest.main()
