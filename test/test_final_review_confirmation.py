from __future__ import annotations

import json
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from final_review_confirmation import (
    FinalReviewConfirmationError,
    record_final_review_confirmation,
)
from aegis_runtime import RuntimeStateError, load_run_state


class FinalReviewConfirmationTests(unittest.TestCase):
    def _write_failed_run(
        self, root: Path, *, current_node: str = "F"
    ) -> tuple[Path, Path, Path]:
        runtime = root / "runtime"
        run_root = runtime / "runs" / "run-fail"
        artifacts = run_root / "artifacts"
        artifacts.mkdir(parents=True)
        final_review = artifacts / "FINAL_REVIEW.md"
        final_review.write_text("# FAIL\nEvidence: evidence/proof.txt\n", encoding="utf-8")
        review_bytes = final_review.read_bytes()
        proof = artifacts / "evidence" / "proof.txt"
        proof.parent.mkdir()
        proof.write_text("proof\n", encoding="utf-8")
        proof_bytes = proof.read_bytes()
        required_evidence = [
            {
                "evidence_id": "proof",
                "path": str(proof.resolve()),
                "size": len(proof_bytes),
                "sha256": hashlib.sha256(proof_bytes).hexdigest(),
            }
        ]
        input_manifest = artifacts / "FINAL_REVIEW_INPUT_MANIFEST.json"
        input_manifest.write_bytes(
            (
                json.dumps(
                {
                    "schema": "aegis.final_review_input_manifest.v2",
                    "workflow_run_id": "run-fail",
                    "final_attempt": {
                        "attempt_id": "attempt-0001",
                        "job_id": "run-fail:execution:attempt-0001",
                        "input_sha256": "1" * 64,
                    },
                    "frozen_runtime_manifest": {},
                    "engineering_input_manifest": {},
                    "reasoning_context_pack": {},
                    "authorities": {
                        "schema": "aegis.run_authority_evidence.v1",
                        "workflow_run_id": "run-fail",
                        "project_seal": {},
                        "project_seal_record": {
                            "path": str(proof.resolve()),
                            "size": len(proof_bytes),
                            "sha256": hashlib.sha256(proof_bytes).hexdigest(),
                        },
                        "remote_witness_required": False,
                        "remote_witness": None,
                        "tracerelay_observed_identity_required": False,
                        "tracerelay_runtime": {},
                    },
                    "planning": {"rounds": [], "reuse": None, "turns": []},
                    "execution": {
                        "attempts": [],
                        "turns": [],
                        "evidence_sessions": [],
                    },
                    "required_evidence": required_evidence,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        )
        input_manifest_bytes = input_manifest.read_bytes()
        verdict = artifacts / "FINAL_REVIEW_VERDICT.json"
        verdict.write_text(
            json.dumps(
                {
                    "schema": "aegis.final_review_verdict.v1",
                    "workflow_run_id": "run-fail",
                    "verdict": "FAIL",
                    "conclusion": "Failed.",
                    "reasons": ["Proof is insufficient."],
                    "evidence_index": [
                        *required_evidence,
                        {
                            "evidence_id": "final-review-input-manifest",
                            "path": str(input_manifest.resolve()),
                            "size": len(input_manifest_bytes),
                            "sha256": hashlib.sha256(
                                input_manifest_bytes
                            ).hexdigest(),
                        },
                        {
                            "evidence_id": "final-review",
                            "path": str(final_review.resolve()),
                            "size": len(review_bytes),
                            "sha256": hashlib.sha256(review_bytes).hexdigest(),
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        verdict_bytes = verdict.read_bytes()
        state = {
            "schema": "aegis.run_state.v14",
            "run_id": "run-fail",
            "reservation_token": "a" * 32,
            "status": "terminated",
            "artifact_path": str(artifacts.resolve()),
            "project_root": str((root / "project").resolve()),
            "graph_state": {"current_node": current_node, "status": False},
            "master_review_status": "PENDING",
            "delivery_eligible": False,
            "execution_attempts": [
                {
                    "attempt_id": "attempt-0001",
                    "job_id": "run-fail:execution:attempt-0001",
                    "input_sha256": "1" * 64,
                    "node": "F",
                    "status": "completed",
                    "final_review_verdict": "FAIL",
                    "final_review_verdict_path": str(verdict.resolve()),
                    "final_review_verdict_sha256": hashlib.sha256(
                        verdict_bytes
                    ).hexdigest(),
                    "final_review_input_manifest_path": str(input_manifest.resolve()),
                    "final_review_input_manifest_sha256": hashlib.sha256(
                        input_manifest_bytes
                    ).hexdigest(),
                    "final_review_required_evidence_ids": ["proof"],
                    "final_review_evidence_ids": [
                        "proof",
                        "final-review-input-manifest",
                        "final-review",
                    ],
                }
            ],
        }
        (root / "project").mkdir()
        state_bytes = (
            json.dumps(
                state,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        (run_root / "RUN_STATE.json").write_bytes(state_bytes)
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
                    "run-fail",
                    "a" * 32,
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
        master_review = root / "master-review.md"
        master_review.write_text("# Confirmed\nThe evidence supports F.\n", encoding="utf-8")
        return runtime, master_review, proof

    def test_records_master_confirmation_and_evidence_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime, master_review, proof = self._write_failed_run(Path(temp))
            payload = record_final_review_confirmation(
                runtime,
                "run-fail",
                decision="CONFIRMED",
                master_review_path=master_review,
                evidence_paths=[proof],
            )
            state = json.loads(
                (runtime / "runs" / "run-fail" / "RUN_STATE.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(payload["decision"], "CONFIRMED")
            self.assertEqual(state["master_review_status"], "CONFIRMED")
            self.assertEqual(len(payload["evidence_index"]), 3)
            self.assertTrue(
                Path(state["master_review_confirmation"]["path"]).is_file()
            )
            self.assertFalse(state["delivery_eligible"])

    def test_rejects_non_f_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime, master_review, proof = self._write_failed_run(
                Path(temp), current_node="E"
            )
            state_path = runtime / "runs" / "run-fail" / "RUN_STATE.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["graph_state"]["current_node"] = "F"
            state.pop("reservation_token")
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaisesRegex(
                FinalReviewConfirmationError, "terminal F failure"
            ):
                record_final_review_confirmation(
                    runtime,
                    "run-fail",
                    decision="CONFIRMED",
                    master_review_path=master_review,
                    evidence_paths=[proof],
                )

    def test_rejects_final_review_changed_after_f_verdict_was_sealed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime, master_review, proof = self._write_failed_run(root)
            final_review = (
                runtime
                / "runs"
                / "run-fail"
                / "artifacts"
                / "FINAL_REVIEW.md"
            )
            final_review.write_text("# Replaced review\n", encoding="utf-8")

            with self.assertRaisesRegex(
                FinalReviewConfirmationError,
                "verdict|evidence|descriptor",
            ):
                record_final_review_confirmation(
                    runtime,
                    "run-fail",
                    decision="CONFIRMED",
                    master_review_path=master_review,
                    evidence_paths=[proof],
                )

    def test_confirmed_state_rejects_deleted_confirmation_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime, master_review, proof = self._write_failed_run(Path(temp))
            record_final_review_confirmation(
                runtime,
                "run-fail",
                decision="CONFIRMED",
                master_review_path=master_review,
                evidence_paths=[proof],
            )
            confirmation = (
                runtime
                / "runs"
                / "run-fail"
                / "artifacts"
                / "MASTER_FINAL_REVIEW_CONFIRMATION.json"
            )
            confirmation.unlink()

            with self.assertRaisesRegex(
                RuntimeStateError, "Master final-review confirmation"
            ):
                load_run_state(runtime, "run-fail")


if __name__ == "__main__":
    unittest.main()
