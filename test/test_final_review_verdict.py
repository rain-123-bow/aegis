from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from final_review_verdict import (
    FinalReviewVerdictError,
    validate_final_review_verdict,
)


class FinalReviewVerdictTests(unittest.TestCase):
    def _write(self, root: Path, *, verdict: str = "FAIL") -> Path:
        project = root / "project"
        artifacts = root / "artifacts"
        project.mkdir()
        artifacts.mkdir()
        review = artifacts / "FINAL_REVIEW.md"
        review.write_text("# Review\n", encoding="utf-8")
        content = review.read_bytes()
        verdict_path = artifacts / "FINAL_REVIEW_VERDICT.json"
        verdict_path.write_text(
            json.dumps(
                {
                    "schema": "aegis.final_review_verdict.v1",
                    "workflow_run_id": "run-1",
                    "verdict": verdict,
                    "conclusion": "Engineering review failed.",
                    "reasons": ["Evidence does not close requirement R1."],
                    "evidence_index": [
                        {
                            "evidence_id": "final-review",
                            "path": str(review.resolve()),
                            "size": len(content),
                            "sha256": hashlib.sha256(content).hexdigest(),
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return verdict_path

    def test_accepts_explicit_failure_with_evidence_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self._write(root)
            result = validate_final_review_verdict(
                path,
                project_root=root / "project",
                artifact_root=root / "artifacts",
                workflow_run_id="run-1",
                expected_status=False,
            )
            self.assertEqual(result.verdict, "FAIL")

    def test_rejects_status_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self._write(root)
            with self.assertRaisesRegex(FinalReviewVerdictError, "does not match"):
                validate_final_review_verdict(
                    path,
                    project_root=root / "project",
                    artifact_root=root / "artifacts",
                    workflow_run_id="run-1",
                    expected_status=True,
                )

    def test_rejects_fixed_verdict_path_that_is_a_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = self._write(root)
            external = root / "external-verdict.json"
            external.write_bytes(original.read_bytes())
            original.unlink()
            try:
                original.symlink_to(external)
            except OSError as error:
                self.skipTest(f"file symlinks are unavailable: {error}")

            with self.assertRaisesRegex(FinalReviewVerdictError, "symlink|reparse"):
                validate_final_review_verdict(
                    original,
                    project_root=root / "project",
                    artifact_root=root / "artifacts",
                    workflow_run_id="run-1",
                    expected_status=False,
                )

    @unittest.skipUnless(os.name == "nt", "directory junctions are Windows-only")
    def test_rejects_artifact_root_that_is_a_directory_junction(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            project.mkdir()
            external = root / "external-artifacts"
            external.mkdir()
            review = external / "FINAL_REVIEW.md"
            review.write_text("# Review\n", encoding="utf-8")
            review_bytes = review.read_bytes()
            verdict = external / "FINAL_REVIEW_VERDICT.json"
            verdict.write_text(
                json.dumps(
                    {
                        "schema": "aegis.final_review_verdict.v1",
                        "workflow_run_id": "run-1",
                        "verdict": "FAIL",
                        "conclusion": "Failed.",
                        "reasons": ["Evidence is insufficient."],
                        "evidence_index": [
                            {
                                "evidence_id": "final-review",
                                "path": str(review),
                                "size": len(review_bytes),
                                "sha256": hashlib.sha256(review_bytes).hexdigest(),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            artifacts = root / "artifacts"
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(artifacts), str(external)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                self.skipTest(f"cannot create directory junction: {result.stderr}")
            try:
                with self.assertRaisesRegex(FinalReviewVerdictError, "reparse"):
                    validate_final_review_verdict(
                        artifacts / "FINAL_REVIEW_VERDICT.json",
                        project_root=project,
                        artifact_root=artifacts,
                        workflow_run_id="run-1",
                        expected_status=False,
                    )
            finally:
                os.rmdir(artifacts)


if __name__ == "__main__":
    unittest.main()
