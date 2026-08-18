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
    def write_policy(self, project: Path, **changes: object) -> Path:
        review_path = project / runtime_behavior_scope.SCOPE_REVIEW_RELATIVE_PATH
        statement_path = project / runtime_behavior_scope.SCOPE_USER_STATEMENT_RELATIVE_PATH
        review_path.parent.mkdir(parents=True, exist_ok=True)
        statement_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text("# Review\n\nPASS\n", encoding="utf-8")
        statement_path.write_text("User confirmed scope.\n", encoding="utf-8")
        review = review_path.read_bytes()
        statement = statement_path.read_bytes()
        payload: dict[str, object] = {
            "schema": "aegis.runtime_behavior_scope.v2",
            "project_id_hex": "12" * 16,
            "version": 1,
            "status": "user_confirmed",
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
            "review": {
                "verdict": "PASS",
                "report_sha256": hashlib.sha256(review).hexdigest(),
            },
            "user_confirmation": {
                "confirmation_id": "decision-runtime-scope-1",
                "statement_sha256": hashlib.sha256(statement).hexdigest(),
            },
        }
        payload.update(changes)
        path = project / runtime_behavior_scope.SCOPE_POLICY_RELATIVE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        policy_sha = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        decision_path = project / runtime_behavior_scope.SCOPE_DECISION_RELATIVE_PATH
        decision_path.write_text(
            json.dumps(
                {
                    "schema": "aegis.runtime_behavior_scope_decision.v2",
                    "project_id_hex": payload["project_id_hex"],
                    "decision": "APPROVED",
                    "policy_sha256": policy_sha,
                    "review": {
                        "path": runtime_behavior_scope.SCOPE_REVIEW_RELATIVE_PATH.as_posix(),
                        "size": len(review),
                        "sha256": hashlib.sha256(review).hexdigest(),
                    },
                    "user_confirmation": {
                        "confirmation_id": payload["user_confirmation"]["confirmation_id"],
                        "path": runtime_behavior_scope.SCOPE_USER_STATEMENT_RELATIVE_PATH.as_posix(),
                        "size": len(statement),
                        "sha256": hashlib.sha256(statement).hexdigest(),
                    },
                }
            ),
            encoding="utf-8",
        )
        return path

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
            self.assertRegex(resolved.manifest_sha256, r"^[0-9a-f]{64}$")
            self.assertEqual(
                [path for path, _content in resolved.seal_entries()][-2:],
                [
                    "aegis-meta/runtime-behavior-scope-policy.sha256",
                    "aegis-meta/runtime-behavior-scope-manifest.sha256",
                ],
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
            self.write_policy(project, status="proposed")
            with self.assertRaisesRegex(
                runtime_behavior_scope.RuntimeBehaviorScopeError,
                "user-confirmed",
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
