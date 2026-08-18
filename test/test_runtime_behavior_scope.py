from __future__ import annotations

import json
import hashlib
import sys
import tempfile
import unittest
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import runtime_behavior_scope
from runtime_identity import git_runtime_manifest


_TEST_GIT = Path(shutil.which("git") or "")
_TEST_GIT_RUNTIME_SHA256 = git_runtime_manifest(_TEST_GIT)[1]


class RuntimeBehaviorScopeTests(unittest.TestCase):
    def write_policy(
        self,
        project: Path,
        *,
        review_verdict: str = "PASS",
        review_scope_sha256: str | None = None,
        confirmation_scope_sha256: str | None = None,
        confirmation_review_sha256: str | None = None,
        confirmation_decision: str = "CONFIRMED",
        **changes: object,
    ) -> Path:
        review_path = project / runtime_behavior_scope.SCOPE_REVIEW_RELATIVE_PATH
        review_result_path = (
            project / runtime_behavior_scope.SCOPE_REVIEW_RESULT_RELATIVE_PATH
        )
        confirmation_path = (
            project / runtime_behavior_scope.SCOPE_USER_CONFIRMATION_RELATIVE_PATH
        )
        review_path.parent.mkdir(parents=True, exist_ok=True)
        confirmation_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(
            f"# Review\n\nVerdict: {review_verdict}\n", encoding="utf-8"
        )
        review = review_path.read_bytes()
        payload: dict[str, object] = {
            "schema": "aegis.runtime_behavior_scope_definition.v1",
            "project_id_hex": "12" * 16,
            "version": 1,
            "include_roots": ["src", "config"],
            "include_files": ["pyproject.toml"],
            "exclude_roots": ["test", "demo"],
            "exclude_files": ["config/local-only.json"],
            "force_include_files": ["test/production_fixture.json"],
            "external_tools": {
                "git_sha256": hashlib.sha256(
                    Path(shutil.which("git") or "").read_bytes()
                ).hexdigest(),
                "git_runtime_sha256": _TEST_GIT_RUNTIME_SHA256,
            },
            "runtime_authority_id": "ab" * 16,
        }
        payload.update(changes)
        path = project / runtime_behavior_scope.SCOPE_POLICY_RELATIVE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        policy_bytes = self.canonical_json(payload)
        path.write_bytes(policy_bytes)
        policy_sha = hashlib.sha256(policy_bytes).hexdigest()
        review_result = {
            "schema": "aegis.runtime_behavior_scope_review.v1",
            "review_id": "unit-review-1",
            "project_id_hex": payload["project_id_hex"],
            "scope_definition_sha256": review_scope_sha256 or policy_sha,
            "verdict": review_verdict,
            "report": self.descriptor(
                runtime_behavior_scope.SCOPE_REVIEW_RELATIVE_PATH, review
            ),
        }
        review_result_bytes = self.canonical_json(review_result)
        review_result_path.write_bytes(review_result_bytes)
        review_result_descriptor = self.descriptor(
            runtime_behavior_scope.SCOPE_REVIEW_RESULT_RELATIVE_PATH,
            review_result_bytes,
        )
        if confirmation_review_sha256 is not None:
            review_result_descriptor["sha256"] = confirmation_review_sha256
        confirmation = {
            "schema": "aegis.runtime_behavior_scope_user_confirmation.v1",
            "confirmation_id": "decision-runtime-scope-1",
            "project_id_hex": payload["project_id_hex"],
            "scope_definition_sha256": confirmation_scope_sha256 or policy_sha,
            "review_result": review_result_descriptor,
            "decision": confirmation_decision,
            "statement": "User confirmed this exact scope and PASS review.",
        }
        confirmation_bytes = self.canonical_json(confirmation)
        confirmation_path.write_bytes(confirmation_bytes)
        decision_path = project / runtime_behavior_scope.SCOPE_DECISION_RELATIVE_PATH
        decision_path.write_bytes(
            self.canonical_json(
                {
                    "schema": "aegis.runtime_behavior_scope_decision.v3",
                    "project_id_hex": payload["project_id_hex"],
                    "decision": "APPROVED",
                    "scope_definition": self.descriptor(
                        runtime_behavior_scope.SCOPE_POLICY_RELATIVE_PATH,
                        policy_bytes,
                    ),
                    "review_result": self.descriptor(
                        runtime_behavior_scope.SCOPE_REVIEW_RESULT_RELATIVE_PATH,
                        review_result_bytes,
                    ),
                    "user_confirmation": {
                        **self.descriptor(
                            runtime_behavior_scope.SCOPE_USER_CONFIRMATION_RELATIVE_PATH,
                            confirmation_bytes,
                        ),
                        "confirmation_id": "decision-runtime-scope-1",
                    },
                }
            )
        )
        return path

    @staticmethod
    def canonical_json(value: object) -> bytes:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @staticmethod
    def descriptor(path: Path, content: bytes) -> dict[str, object]:
        return {
            "path": path.as_posix(),
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    def make_project(self, root: Path) -> Path:
        project = root / "project"
        files = {
            "src/main.py": b"print('runtime')\n",
            "config/runtime.json": b"{}\n",
            "config/local-only.json": b"{}\n",
            "pyproject.toml": b"[project]\n",
            "test/unit_test.py": b"assert True\n",
            "test/production_fixture.json": b"{\"required\": true}\n",
            "demo/example.py": b"print('demo')\n",
        }
        for relative, content in files.items():
            path = project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.write_policy(project)
        return project

    def test_resolves_exact_runtime_files_and_binds_policy_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))

            resolved = runtime_behavior_scope.resolve_runtime_behavior_scope(
                project, bytes.fromhex("12" * 16)
            )

            self.assertEqual(
                [entry.path for entry in resolved.entries],
                [
                    "config/runtime.json",
                    "pyproject.toml",
                    "src/main.py",
                    "test/production_fixture.json",
                ],
            )
            self.assertRegex(resolved.policy_sha256, r"^[0-9a-f]{64}$")
            self.assertRegex(resolved.decision_sha256, r"^[0-9a-f]{64}$")
            self.assertRegex(resolved.manifest_sha256, r"^[0-9a-f]{64}$")
            self.assertEqual(
                [path for path, _content in resolved.seal_entries()][-3:],
                [
                    "aegis-meta/runtime-behavior-scope-policy.sha256",
                    "aegis-meta/runtime-behavior-scope-decision.sha256",
                    "aegis-meta/runtime-behavior-scope-manifest.sha256",
                ],
            )

    def test_definition_can_be_reviewed_before_approval_artifacts_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            for relative in (
                runtime_behavior_scope.SCOPE_REVIEW_RELATIVE_PATH,
                runtime_behavior_scope.SCOPE_REVIEW_RESULT_RELATIVE_PATH,
                runtime_behavior_scope.SCOPE_USER_CONFIRMATION_RELATIVE_PATH,
                runtime_behavior_scope.SCOPE_DECISION_RELATIVE_PATH,
            ):
                (project / relative).unlink()

            resolved = (
                runtime_behavior_scope.resolve_runtime_behavior_scope_definition(
                    project, bytes.fromhex("12" * 16)
                )
            )

            self.assertEqual(resolved.project_id_hex, "12" * 16)
            with self.assertRaisesRegex(
                runtime_behavior_scope.RuntimeBehaviorScopeError,
                "approval decision",
            ):
                resolved.seal_entries()
            with self.assertRaises(runtime_behavior_scope.RuntimeBehaviorScopeError):
                runtime_behavior_scope.resolve_runtime_behavior_scope(
                    project, bytes.fromhex("12" * 16)
                )

    def test_include_files_rejects_a_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            self.write_policy(project, include_files=["src"])

            with self.assertRaisesRegex(
                runtime_behavior_scope.RuntimeBehaviorScopeError,
                "explicit file.*directory",
            ):
                runtime_behavior_scope.resolve_runtime_behavior_scope(
                    project, bytes.fromhex("12" * 16)
                )

    def test_excluded_include_files_still_rejects_a_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            self.write_policy(
                project,
                include_files=["src"],
                exclude_roots=["src", "test", "demo"],
            )

            with self.assertRaisesRegex(
                runtime_behavior_scope.RuntimeBehaviorScopeError,
                "explicit file.*directory",
            ):
                runtime_behavior_scope.resolve_runtime_behavior_scope(
                    project, bytes.fromhex("12" * 16)
                )

    def test_force_include_files_rejects_a_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            self.write_policy(project, force_include_files=["test"])

            with self.assertRaisesRegex(
                runtime_behavior_scope.RuntimeBehaviorScopeError,
                "explicit file.*directory",
            ):
                runtime_behavior_scope.resolve_runtime_behavior_scope(
                    project, bytes.fromhex("12" * 16)
                )

    def test_content_change_changes_resolved_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            before = runtime_behavior_scope.resolve_runtime_behavior_scope(
                project, bytes.fromhex("12" * 16)
            )
            (project / "config/runtime.json").write_bytes(b'{"changed":true}\n')

            after = runtime_behavior_scope.resolve_runtime_behavior_scope(
                project, bytes.fromhex("12" * 16)
            )

            self.assertNotEqual(before.manifest_sha256, after.manifest_sha256)

    def test_unapproved_or_wrong_project_policy_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            (
                project
                / runtime_behavior_scope.SCOPE_USER_CONFIRMATION_RELATIVE_PATH
            ).unlink()
            with self.assertRaisesRegex(
                runtime_behavior_scope.RuntimeBehaviorScopeError,
                "user confirmation",
            ):
                runtime_behavior_scope.resolve_runtime_behavior_scope(
                    project, bytes.fromhex("12" * 16)
                )

            self.write_policy(project, project_id_hex="ab" * 16)
            with self.assertRaisesRegex(
                runtime_behavior_scope.RuntimeBehaviorScopeError,
                "project identity",
            ):
                runtime_behavior_scope.resolve_runtime_behavior_scope(
                    project, bytes.fromhex("12" * 16)
                )

    def test_policy_cannot_self_report_pass_over_a_fail_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            self.write_policy(project, review_verdict="FAIL")

            with self.assertRaisesRegex(
                runtime_behavior_scope.RuntimeBehaviorScopeError,
                "review.*did not pass",
            ):
                runtime_behavior_scope.resolve_runtime_behavior_scope(
                    project, bytes.fromhex("12" * 16)
                )

    def test_review_and_confirmation_must_bind_the_exact_definition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            self.write_policy(project, review_scope_sha256="00" * 32)
            with self.assertRaisesRegex(
                runtime_behavior_scope.RuntimeBehaviorScopeError,
                "review result does not bind the definition",
            ):
                runtime_behavior_scope.resolve_runtime_behavior_scope(
                    project, bytes.fromhex("12" * 16)
                )

            self.write_policy(project, confirmation_scope_sha256="00" * 32)
            with self.assertRaisesRegex(
                runtime_behavior_scope.RuntimeBehaviorScopeError,
                "user confirmation does not bind",
            ):
                runtime_behavior_scope.resolve_runtime_behavior_scope(
                    project, bytes.fromhex("12" * 16)
                )

    def test_confirmation_must_bind_review_and_be_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            self.write_policy(project, confirmation_review_sha256="00" * 32)
            with self.assertRaisesRegex(
                runtime_behavior_scope.RuntimeBehaviorScopeError,
                "user confirmation does not bind",
            ):
                runtime_behavior_scope.resolve_runtime_behavior_scope(
                    project, bytes.fromhex("12" * 16)
                )

            self.write_policy(project, confirmation_decision="REJECTED")
            with self.assertRaisesRegex(
                runtime_behavior_scope.RuntimeBehaviorScopeError,
                "not CONFIRMED",
            ):
                runtime_behavior_scope.resolve_runtime_behavior_scope(
                    project, bytes.fromhex("12" * 16)
                )

    def test_missing_or_symlinked_selected_input_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            self.write_policy(project, include_files=["missing.toml"])
            with self.assertRaisesRegex(
                runtime_behavior_scope.RuntimeBehaviorScopeError, "missing"
            ):
                runtime_behavior_scope.resolve_runtime_behavior_scope(
                    project, bytes.fromhex("12" * 16)
                )

    def test_policy_cannot_select_reasoning_ledger_as_runtime_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            self.write_policy(project, include_roots=[".aegis"])
            with self.assertRaisesRegex(
                runtime_behavior_scope.RuntimeBehaviorScopeError,
                "reasoning ledger",
            ):
                runtime_behavior_scope.resolve_runtime_behavior_scope(
                    project, bytes.fromhex("12" * 16)
                )

    def test_policy_cannot_select_reasoning_ledger_with_different_case(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            self.write_policy(project, include_roots=[".AEGIS"])
            with self.assertRaisesRegex(
                runtime_behavior_scope.RuntimeBehaviorScopeError,
                "reasoning ledger",
            ):
                runtime_behavior_scope.resolve_runtime_behavior_scope(
                    project, bytes.fromhex("12" * 16)
                )

    def test_excluded_bytecode_cache_under_production_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            cache = project / "src" / "__pycache__" / "hidden.pyc"
            cache.parent.mkdir()
            cache.write_bytes(b"untrusted-bytecode")
            self.write_policy(project, exclude_roots=["src/__pycache__", "test", "demo"])

            with self.assertRaisesRegex(
                runtime_behavior_scope.RuntimeBehaviorScopeError,
                "executable Python bytecode cache",
            ):
                runtime_behavior_scope.resolve_runtime_behavior_scope(
                    project, bytes.fromhex("12" * 16)
                )


if __name__ == "__main__":
    unittest.main()
