from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import project_seal_store
import runtime_behavior_scope
from aegis_test_support import (
    refresh_test_runtime_scope_approvals,
    write_test_runtime_scope_policy,
)


class ProjectSealStoreTests(unittest.TestCase):
    @staticmethod
    def write_canonical_json(path: Path, value: object) -> None:
        path.write_text(
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

    def refresh_scope_decision(self, project: Path) -> None:
        refresh_test_runtime_scope_approvals(project)

    def git(self, project: Path, *arguments: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(project), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if completed.returncode != 0:
            self.fail(f"git {' '.join(arguments)} failed: {completed.stderr}")
        return completed.stdout.strip()

    def commit_all(self, project: Path, message: str) -> str:
        self.git(project, "add", "--all")
        self.git(
            project,
            "-c",
            "user.name=Aegis Test",
            "-c",
            "user.email=aegis@example.invalid",
            "commit",
            "-m",
            message,
        )
        return self.git(project, "rev-parse", "HEAD")

    def make_project(self, root: Path, content: str = "VALUE = 1\n") -> Path:
        project = root / "project"
        source = project / "src" / "module.py"
        source.parent.mkdir(parents=True)
        source.write_text(content, encoding="utf-8")
        write_test_runtime_scope_policy(project)
        self.git(project, "init")
        self.git(project, "config", "core.autocrlf", "false")
        self.commit_all(project, "initial")
        return project

    def test_initial_record_is_persisted_and_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            head = self.git(project, "rev-parse", "HEAD")

            record = project_seal_store.record_project_seal(
                project,
                git_head_before_record=head,
                project_id=bytes(range(16)),
                seal_chain_id=bytes(range(16, 32)),
            )

            self.assertEqual(record.sequence, 0)
            self.assertEqual(record.previous_seal, bytes(32))
            self.assertTrue(record.expected_seal.startswith("ASC1:"))
            self.assertEqual(
                project_seal_store.verify_expected_project_seal(project),
                record,
            )

    def test_hostile_git_environment_cannot_redirect_seal_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.make_project(root)
            head = self.git(project, "rev-parse", "HEAD")
            hostile_repository = root / "attacker.git"

            with patch.dict(
                os.environ,
                {
                    "GIT_DIR": str(hostile_repository),
                    "GIT_WORK_TREE": str(root / "attacker-worktree"),
                    "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "core.gitProxy",
                    "GIT_CONFIG_VALUE_0": "attacker-command",
                    "GIT_EXEC_PATH": str(root / "attacker-exec-path"),
                },
            ):
                record = project_seal_store.record_project_seal(
                    project,
                    git_head_before_record=head,
                    project_id=bytes(range(16)),
                    seal_chain_id=bytes(range(16, 32)),
                )

            self.assertEqual(record.git_head_before_record, head)

    def test_record_rejects_uncommitted_replacement_approval_chain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            head = self.git(project, "rev-parse", "HEAD")
            review = project / runtime_behavior_scope.SCOPE_REVIEW_RELATIVE_PATH
            review.write_text("# New internally consistent review\n\nPASS\n", encoding="utf-8")
            self.refresh_scope_decision(project)
            with self.assertRaisesRegex(project_seal_store.ProjectSealStoreError, "approval"):
                project_seal_store.record_project_seal(
                    project, git_head_before_record=head, project_id=bytes(range(16)),
                )

    def test_record_rejects_ignored_approval_artifacts_absent_from_head(self) -> None:
        for relative in (
            runtime_behavior_scope.SCOPE_REVIEW_RELATIVE_PATH,
            runtime_behavior_scope.SCOPE_REVIEW_RESULT_RELATIVE_PATH,
            runtime_behavior_scope.SCOPE_USER_CONFIRMATION_RELATIVE_PATH,
            runtime_behavior_scope.SCOPE_DECISION_RELATIVE_PATH,
        ):
            with self.subTest(path=relative), tempfile.TemporaryDirectory() as directory:
                project = self.make_project(Path(directory))
                self.git(project, "rm", "--cached", "--", relative.as_posix())
                (project / ".gitignore").write_text(relative.as_posix() + "\n", encoding="utf-8")
                head = self.commit_all(project, "omit one approval artifact")
                self.assertTrue((project / relative).is_file())
                self.assertEqual(self.git(project, "status", "--porcelain"), "")
                with self.assertRaisesRegex(project_seal_store.ProjectSealStoreError, "approval"):
                    project_seal_store.record_project_seal(
                        project, git_head_before_record=head, project_id=bytes(range(16)),
                    )

    def test_record_revalidates_approval_after_control_locks_are_acquired(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            review = project / runtime_behavior_scope.SCOPE_REVIEW_RELATIVE_PATH
            valid_review = review.read_bytes()
            invalid_review = b"# Committed report B without descriptor refresh\n"
            review.write_bytes(invalid_review)
            head = self.commit_all(project, "commit inconsistent report B")
            review.write_bytes(valid_review)
            verify = project_seal_store._verify_scope_matches_git_commit

            def swap_then_verify(*args, **kwargs):
                if not kwargs.get("git_runtime_lock_held", False):
                    review.write_bytes(invalid_review)
                    self.assertEqual(self.git(project, "rev-parse", "HEAD"), head)
                    self.assertEqual(self.git(project, "status", "--porcelain"), "")
                return verify(*args, **kwargs)

            with patch.object(
                project_seal_store, "_verify_scope_matches_git_commit",
                side_effect=swap_then_verify,
            ):
                with self.assertRaisesRegex(
                    project_seal_store.ProjectSealStoreError, "approval.*locked",
                ):
                    project_seal_store.record_project_seal(
                        project, git_head_before_record=head, project_id=bytes(range(16)),
                    )
            self.assertFalse((project / project_seal_store.SEAL_RECORD_RELATIVE_PATH).exists())

    def test_git_must_match_the_user_confirmed_trust_pin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            policy_path = project / runtime_behavior_scope.SCOPE_POLICY_RELATIVE_PATH
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["external_tools"]["git_sha256"] = "00" * 32
            self.write_canonical_json(policy_path, policy)
            self.refresh_scope_decision(project)
            head = self.commit_all(project, "wrong git pin")

            with self.assertRaisesRegex(
                project_seal_store.ProjectSealStoreError,
                "Git executable differs",
            ):
                project_seal_store.record_project_seal(
                    project,
                    git_head_before_record=head,
                    project_id=bytes(range(16)),
                    seal_chain_id=bytes(range(16, 32)),
                )

    def test_append_extends_one_chain_after_authorized_source_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            first_head = self.git(project, "rev-parse", "HEAD")
            first = project_seal_store.record_project_seal(
                project,
                git_head_before_record=first_head,
                project_id=bytes(range(16)),
                seal_chain_id=bytes(range(16, 32)),
            )
            (project / "src" / "module.py").write_text(
                "VALUE = 2\n", encoding="utf-8"
            )
            second_head = self.commit_all(project, "change runtime")

            second = project_seal_store.record_project_seal(
                project,
                git_head_before_record=second_head,
            )
            chain = project_seal_store.load_project_seal_chain(project)

            self.assertEqual([item.sequence for item in chain.records], [0, 1])
            self.assertEqual(second.previous_seal.hex(), first.expected_seal[5:])
            self.assertEqual(second.project_id, first.project_id)
            self.assertEqual(second.seal_chain_id, first.seal_chain_id)
            self.assertEqual(
                project_seal_store.verify_expected_project_seal(project),
                second,
            )

    def test_source_change_after_record_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            head = self.git(project, "rev-parse", "HEAD")
            project_seal_store.record_project_seal(
                project,
                git_head_before_record=head,
                project_id=bytes(range(16)),
                seal_chain_id=bytes(range(16, 32)),
            )
            (project / "src" / "module.py").write_text(
                "VALUE = 999\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(
                project_seal_store.ProjectSealMismatchError,
                "does not match",
            ):
                project_seal_store.verify_expected_project_seal(project)

    def test_replacing_complete_scope_approval_chain_invalidates_old_seal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            head = self.git(project, "rev-parse", "HEAD")
            original = project_seal_store.record_project_seal(
                project,
                git_head_before_record=head,
                project_id=bytes(range(16)),
                seal_chain_id=bytes(range(16, 32)),
            )
            review_path = project / runtime_behavior_scope.SCOPE_REVIEW_RELATIVE_PATH
            review_path.write_text(
                "# Runtime scope review\n\nPASS\n\nReplacement review.\n",
                encoding="utf-8",
            )
            self.refresh_scope_decision(project)

            with self.assertRaisesRegex(
                project_seal_store.ProjectSealMismatchError,
                "approval decision",
            ):
                project_seal_store.verify_expected_project_seal(project)
            self.assertTrue(original.expected_seal.startswith("ASC1:"))

    def test_broken_chain_is_rejected_before_seal_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            first_head = self.git(project, "rev-parse", "HEAD")
            project_seal_store.record_project_seal(
                project,
                git_head_before_record=first_head,
                project_id=bytes(range(16)),
                seal_chain_id=bytes(range(16, 32)),
            )
            (project / "src" / "module.py").write_text(
                "VALUE = 2\n", encoding="utf-8"
            )
            second_head = self.commit_all(project, "change runtime")
            project_seal_store.record_project_seal(
                project,
                git_head_before_record=second_head,
            )
            path = project / project_seal_store.SEAL_RECORD_RELATIVE_PATH
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["records"][1]["previous_seal_hex"] = "0" * 64
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(
                project_seal_store.ProjectSealStoreError,
                "previous seal",
            ):
                project_seal_store.verify_expected_project_seal(project)

    def test_scope_policy_change_requires_higher_version_and_new_seal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            first_head = self.git(project, "rev-parse", "HEAD")
            first = project_seal_store.record_project_seal(
                project,
                git_head_before_record=first_head,
                project_id=bytes(range(16)),
                seal_chain_id=bytes(range(16, 32)),
            )
            policy_path = project / runtime_behavior_scope.SCOPE_POLICY_RELATIVE_PATH
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["force_include_files"] = ["src/module.py"]
            self.write_canonical_json(policy_path, policy)
            self.refresh_scope_decision(project)
            unchanged_version_head = self.commit_all(project, "change policy")

            with self.assertRaisesRegex(
                project_seal_store.ProjectSealStoreError,
                "higher version",
            ):
                project_seal_store.record_project_seal(
                    project,
                    git_head_before_record=unchanged_version_head,
                )

            policy["version"] = 2
            self.write_canonical_json(policy_path, policy)
            self.refresh_scope_decision(project)
            second_head = self.commit_all(project, "raise policy version")
            second = project_seal_store.record_project_seal(
                project,
                git_head_before_record=second_head,
            )

            self.assertEqual(second.scope_policy_version, 2)
            self.assertNotEqual(first.scope_policy_sha256, second.scope_policy_sha256)
            self.assertNotEqual(first.expected_seal, second.expected_seal)

    def test_record_rejects_dirty_runtime_scope_and_false_caller_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            head = self.git(project, "rev-parse", "HEAD")
            (project / "src" / "module.py").write_text(
                "VALUE = 9\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                project_seal_store.ProjectSealStoreError,
                "uncommitted paths",
            ):
                project_seal_store.record_project_seal(
                    project,
                    git_head_before_record=head,
                    project_id=bytes(range(16)),
                    seal_chain_id=bytes(range(16, 32)),
                )

            self.git(project, "restore", "src/module.py")
            with self.assertRaisesRegex(
                project_seal_store.ProjectSealStoreError,
                "does not match the repository HEAD",
            ):
                project_seal_store.record_project_seal(
                    project,
                    git_head_before_record="a" * 40,
                    project_id=bytes(range(16)),
                    seal_chain_id=bytes(range(16, 32)),
                )

    def test_concurrent_append_preserves_every_chain_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            head = self.git(project, "rev-parse", "HEAD")
            project_seal_store.record_project_seal(
                project,
                git_head_before_record=head,
                project_id=bytes(range(16)),
                seal_chain_id=bytes(range(16, 32)),
            )
            barrier = threading.Barrier(2)
            errors: list[BaseException] = []

            def append() -> None:
                try:
                    barrier.wait(timeout=5)
                    project_seal_store.record_project_seal(
                        project,
                        git_head_before_record=head,
                    )
                except BaseException as error:  # pragma: no cover - surfaced below
                    errors.append(error)

            threads = [threading.Thread(target=append) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=15)

            self.assertFalse(errors)
            chain = project_seal_store.load_project_seal_chain(project)
            self.assertEqual([record.sequence for record in chain.records], [0, 1, 2])

    def test_assume_unchanged_cannot_hide_runtime_bytes_from_git_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            head = self.git(project, "rev-parse", "HEAD")
            self.git(project, "update-index", "--assume-unchanged", "src/module.py")
            (project / "src" / "module.py").write_text(
                "VALUE = 999\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(
                project_seal_store.ProjectSealStoreError,
                "bytes differ from repository HEAD",
            ):
                project_seal_store.record_project_seal(
                    project,
                    git_head_before_record=head,
                    project_id=bytes(range(16)),
                    seal_chain_id=bytes(range(16, 32)),
                )


if __name__ == "__main__":
    unittest.main()
