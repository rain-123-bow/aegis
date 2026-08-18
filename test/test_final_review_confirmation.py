from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from final_review_confirmation import (
    FinalReviewConfirmationError,
    record_final_review_confirmation,
)


class FinalReviewConfirmationTests(unittest.TestCase):
    def _write_failed_run(self, root: Path) -> tuple[Path, Path, Path]:
        runtime = root / "runtime"
        run_root = runtime / "runs" / "run-fail"
        artifacts = run_root / "artifacts"
        artifacts.mkdir(parents=True)
        final_review = artifacts / "FINAL_REVIEW.md"
        final_review.write_text("# FAIL\nEvidence: evidence/proof.txt\n", encoding="utf-8")
        review_bytes = final_review.read_bytes()
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
        proof = artifacts / "evidence" / "proof.txt"
        proof.parent.mkdir()
        proof.write_text("proof\n", encoding="utf-8")
        state = {
            "schema": "aegis.run_state.v10",
            "run_id": "run-fail",
            "status": "terminated",
            "artifact_path": str(artifacts.resolve()),
            "project_root": str((root / "project").resolve()),
            "graph_state": {"current_node": "F", "status": False},
            "master_review_status": "PENDING",
            "delivery_eligible": False,
            "execution_attempts": [
                {
                    "node": "F",
                    "status": "completed",
                    "final_review_verdict": "FAIL",
                    "final_review_verdict_path": str(verdict.resolve()),
                    "final_review_verdict_sha256": hashlib.sha256(
                        verdict_bytes
                    ).hexdigest(),
                    "final_review_evidence_ids": ["final-review"],
                }
            ],
        }
        (root / "project").mkdir()
        (run_root / "RUN_STATE.json").write_text(
            json.dumps(state) + "\n", encoding="utf-8"
        )
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
            runtime, master_review, proof = self._write_failed_run(Path(temp))
            state_path = runtime / "runs" / "run-fail" / "RUN_STATE.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["graph_state"]["current_node"] = "E"
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


if __name__ == "__main__":
    unittest.main()
