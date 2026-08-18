from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aegis_test_support import write_test_execution_request
from test_execution_request import (
    TestExecutionRequestError,
    hold_test_execution_inputs,
    validate_test_execution_request,
)


class TestExecutionRequestTests(unittest.TestCase):
    def make_request(self, root: Path) -> tuple[Path, Path, Path]:
        project = root / "project"
        artifacts = root / "artifacts"
        (project / "src").mkdir(parents=True)
        (project / "src" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
        artifacts.mkdir()
        request = write_test_execution_request(
            project,
            artifacts,
            project_id_hex="12" * 16,
            workflow_run_id="run-1",
            attempt_id="attempt-0001",
        )
        return project, artifacts, request

    def validate(self, project: Path, artifacts: Path, request: Path):
        plan = artifacts / "APPROVED_TEST_PLAN.md"
        import hashlib

        return validate_test_execution_request(
            request,
            project_root=project,
            artifact_root=artifacts,
            project_id_hex="12" * 16,
            workflow_run_id="run-1",
            attempt_id="attempt-0001",
            approved_test_plan_sha256=hashlib.sha256(plan.read_bytes()).hexdigest(),
            approved_test_plan_path=plan,
        )

    def test_request_must_equal_the_reviewer_approved_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, artifacts, request = self.make_request(Path(directory))
            validated = self.validate(project, artifacts, request)
            self.assertRegex(validated.execution_policy_sha256, r"^[0-9a-f]{64}$")

            payload = json.loads(request.read_text(encoding="utf-8"))
            payload["tests"][0]["timeout_seconds"] += 1
            request.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                TestExecutionRequestError, "reviewer-approved execution policy"
            ):
                self.validate(project, artifacts, request)

    def test_shell_and_inline_python_are_rejected_even_when_approved(self) -> None:
        for command in (
            [str(Path(sys._base_executable).resolve()), "-c", "print('x')"],
            [str(Path("C:/Windows/System32/cmd.exe")), "/c", "echo x"],
        ):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as directory:
                project, artifacts, request = self.make_request(Path(directory))
                plan = artifacts / "APPROVED_TEST_PLAN.md"
                payload = json.loads(request.read_text(encoding="utf-8"))
                executable = Path(command[0])
                if not executable.is_file():
                    self.skipTest(f"executable unavailable: {executable}")
                content = executable.read_bytes()
                import hashlib

                payload["tests"][0]["command"] = command
                payload["tests"][0]["executable"] = {
                    "path": str(executable.resolve()),
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
                policy = {
                    "schema": "aegis.test_execution_policy.v2",
                    "tests": payload["tests"],
                }
                plan.write_text(
                    "# plan\n<!-- AEGIS_TEST_EXECUTION_POLICY_BEGIN -->\n"
                    + json.dumps(policy)
                    + "\n<!-- AEGIS_TEST_EXECUTION_POLICY_END -->\n",
                    encoding="utf-8",
                )
                payload["approved_test_plan_sha256"] = hashlib.sha256(
                    plan.read_bytes()
                ).hexdigest()
                request.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(
                    TestExecutionRequestError, "forbidden shell|inline or module"
                ):
                    self.validate(project, artifacts, request)

    @unittest.skipUnless(sys.platform == "win32", "share-lock acceptance is Windows-only")
    def test_validated_test_input_cannot_be_replaced_while_execution_lock_is_held(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, artifacts, request = self.make_request(Path(directory))
            validated = self.validate(project, artifacts, request)
            test = validated.payload["tests"][0]
            input_path = Path(test["test_inputs"][0]["path"])
            original = input_path.read_bytes()
            with hold_test_execution_inputs(
                test,
                project_root=project,
                artifact_root=artifacts,
            ):
                with self.assertRaises(OSError):
                    input_path.write_bytes(original + b"# changed\n")
            self.assertEqual(input_path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
