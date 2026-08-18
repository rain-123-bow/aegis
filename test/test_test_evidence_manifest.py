from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import test_evidence_manifest


class TestEvidenceManifestTests(unittest.TestCase):
    def descriptor(self, path: Path) -> dict[str, object]:
        content = path.read_bytes()
        return {
            "path": str(path.resolve()),
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    def write_manifest(
        self,
        project: Path,
        artifacts: Path,
        *,
        session_ids: list[str] | None = None,
    ) -> Path:
        source = project / "test" / "check_runtime.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("assert True\n", encoding="utf-8")
        plan = artifacts / "APPROVED_TEST_PLAN.md"
        evidence_root = artifacts / "evidence" / "attempt-0001" / "test-0001"
        stdout = evidence_root / "stdout.txt"
        stderr = evidence_root / "stderr.txt"
        receipt = evidence_root / "execution_receipt.json"
        stdout.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text("# approved\n", encoding="utf-8")
        stdout.write_text("PASS\n", encoding="utf-8")
        stderr.write_text("", encoding="utf-8")
        started = datetime.now(UTC)
        finished = started + timedelta(seconds=1)
        executable = Path(sys._base_executable).resolve()
        record = {
            "test_id": "T-001",
            "requirement_ids": ["R-001"],
            "command": [str(executable), "test/check_runtime.py"],
            "executable": self.descriptor(executable),
            "execution_policy_sha256": "4" * 64,
            "cwd": str(project.resolve()),
            "environment": {
                "os": "Windows",
                "python": "3.13.7",
            },
            "started_at_utc": started.isoformat().replace("+00:00", "Z"),
            "finished_at_utc": finished.isoformat().replace("+00:00", "Z"),
            "exit_code": 0,
            "test_inputs": [self.descriptor(source)],
            "stdout": self.descriptor(stdout),
            "stderr": self.descriptor(stderr),
            "tracerelay_session_ids": session_ids or ["session-c"],
        }
        receipt_payload = {
            "schema": "aegis.test_execution_receipt.v3",
            "trusted_runner": "aegis.coordinator.windows_job.v1",
            "request_sha256": "3" * 64,
            "execution_policy_sha256": record["execution_policy_sha256"],
            "test_id": record["test_id"],
            "command": record["command"],
            "executable": record["executable"],
            "cwd": record["cwd"],
            "environment": record["environment"],
            "started_at_utc": record["started_at_utc"],
            "finished_at_utc": record["finished_at_utc"],
            "exit_code": record["exit_code"],
            "timed_out": False,
            "runner_pid": 123,
            "coordinator_pid": 456,
            "test_inputs": record["test_inputs"],
            "stdout": record["stdout"],
            "stderr": record["stderr"],
        }
        receipt.write_text(json.dumps(receipt_payload), encoding="utf-8")
        record["raw_results"] = [self.descriptor(receipt)]
        record["execution_receipt"] = self.descriptor(receipt)
        payload = {
            "schema": "aegis.test_evidence_manifest.v2",
            "project_id_hex": "12" * 16,
            "workflow_run_id": "run-1",
            "attempt_id": "attempt-0001",
            "approved_test_plan": self.descriptor(plan),
            "created_at_utc": finished.isoformat().replace("+00:00", "Z"),
            "records": [record],
        }
        path = artifacts / "test_evidence_manifest.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_valid_manifest_binds_test_inputs_outputs_and_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            artifacts = root / "artifacts"
            project.mkdir()
            artifacts.mkdir()
            path = self.write_manifest(project, artifacts)

            validated = test_evidence_manifest.validate_test_evidence_manifest(
                path,
                project_root=project,
                artifact_root=artifacts,
                project_id_hex="12" * 16,
                workflow_run_id="run-1",
                attempt_id="attempt-0001",
                allowed_tracerelay_session_ids={"session-c"},
            )

            self.assertEqual(validated.path, path.resolve())
            self.assertRegex(validated.sha256, r"^[0-9a-f]{64}$")
            self.assertEqual(validated.test_ids, ("T-001",))

    def test_changed_evidence_or_test_input_is_rejected(self) -> None:
        for relative in (
            "evidence/attempt-0001/test-0001/stdout.txt",
            "../project/test/check_runtime.py",
        ):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                project = root / "project"
                artifacts = root / "artifacts"
                project.mkdir()
                artifacts.mkdir()
                path = self.write_manifest(project, artifacts)
                (artifacts / relative).resolve().write_text(
                    "changed\n", encoding="utf-8"
                )

                with self.assertRaisesRegex(
                    test_evidence_manifest.TestEvidenceManifestError,
                    "(?:size|hash) mismatch",
                ):
                    test_evidence_manifest.validate_test_evidence_manifest(
                        path,
                        project_root=project,
                        artifact_root=artifacts,
                        project_id_hex="12" * 16,
                        workflow_run_id="run-1",
                        attempt_id="attempt-0001",
                        allowed_tracerelay_session_ids={"session-c"},
                    )

    def test_evidence_outside_artifact_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            artifacts = root / "artifacts"
            project.mkdir()
            artifacts.mkdir()
            path = self.write_manifest(project, artifacts)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["records"][0]["stdout"] = payload["records"][0][
                "test_inputs"
            ][0]
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(
                test_evidence_manifest.TestEvidenceManifestError,
                "artifact root",
            ):
                test_evidence_manifest.validate_test_evidence_manifest(
                    path,
                    project_root=project,
                    artifact_root=artifacts,
                    project_id_hex="12" * 16,
                    workflow_run_id="run-1",
                    attempt_id="attempt-0001",
                    allowed_tracerelay_session_ids={"session-c"},
                )

    def test_unknown_tracerelay_session_or_wrong_identity_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            artifacts = root / "artifacts"
            project.mkdir()
            artifacts.mkdir()
            path = self.write_manifest(project, artifacts, session_ids=["unknown"])

            with self.assertRaisesRegex(
                test_evidence_manifest.TestEvidenceManifestError,
                "TraceRelay",
            ):
                test_evidence_manifest.validate_test_evidence_manifest(
                    path,
                    project_root=project,
                    artifact_root=artifacts,
                    project_id_hex="12" * 16,
                    workflow_run_id="run-1",
                    attempt_id="attempt-0001",
                    allowed_tracerelay_session_ids={"session-c"},
                )

            with self.assertRaisesRegex(
                test_evidence_manifest.TestEvidenceManifestError,
                "project identity",
            ):
                test_evidence_manifest.validate_test_evidence_manifest(
                    path,
                    project_root=project,
                    artifact_root=artifacts,
                    project_id_hex="ab" * 16,
                    workflow_run_id="run-1",
                    attempt_id="attempt-0001",
                    allowed_tracerelay_session_ids={"unknown"},
                )


if __name__ == "__main__":
    unittest.main()
