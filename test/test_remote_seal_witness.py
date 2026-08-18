from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import remote_seal_witness
from project_seal_store import StoredProjectSeal


class FakeGitRunner:
    def __init__(self, witness: dict[str, object], head: str) -> None:
        self.witness = witness
        self.head = head
        self.commands: list[list[str]] = []
        self.options: list[dict[str, object]] = []

    def __call__(self, command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        self.options.append(dict(options))
        if "init" in command:
            return subprocess.CompletedProcess(command, 0, "", "")
        if "fetch" in command:
            return subprocess.CompletedProcess(command, 0, "", "")
        if "cat-file" in command:
            return subprocess.CompletedProcess(
                command, 0, json.dumps(self.witness), ""
            )
        raise AssertionError(f"unexpected git command: {command}")


class RemoteSealWitnessTests(unittest.TestCase):
    def make_seal(self) -> StoredProjectSeal:
        return StoredProjectSeal(
            project_id=bytes(range(16)),
            seal_chain_id=bytes(range(16, 32)),
            sequence=3,
            previous_seal=bytes.fromhex("11" * 32),
            expected_seal="ASC1:" + "22" * 32,
            created_at_utc="2026-08-17T00:00:00Z",
            git_head_before_record="b" * 40,
            scope_policy_version=2,
            scope_policy_sha256="33" * 32,
            resolved_manifest_sha256="44" * 32,
            runtime_authority_id="55" * 16,
        )

    def write_config(self, project: Path) -> None:
        path = project / "config" / "seal_witness.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        identity_path = project / "test-ssh-identity"
        identity_path.write_bytes(b"unit-test-private-key")
        path.write_text(
            json.dumps(
                {
                    "schema": "aegis.remote_seal_witness_config.v3",
                    "repository_url": "ssh://git@github.com/example/aegis.git",
                    "protected_ref": "refs/heads/aegis-seal-witness",
                    "ssh_identity": {
                        "path": str(identity_path.resolve()),
                        "sha256": hashlib.sha256(
                            identity_path.read_bytes()
                        ).hexdigest(),
                    },
                }
            ),
            encoding="utf-8",
        )
        (project / "config" / "git_ssh_known_hosts").write_text(
            "github.com ssh-ed25519 "
            "AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl\n",
            encoding="utf-8",
        )

    def witness(self, seal: StoredProjectSeal, head: str) -> dict[str, object]:
        return {
            "schema": "aegis.remote_seal_witness.v2",
            "project_id_hex": seal.project_id.hex(),
            "seal_chain_id_hex": seal.seal_chain_id.hex(),
            "sequence": seal.sequence,
            "expected_seal": seal.expected_seal,
            "scope_policy_sha256": seal.scope_policy_sha256,
            "resolved_manifest_sha256": seal.resolved_manifest_sha256,
            "git_commit": head,
            "runtime_authority_id": seal.runtime_authority_id,
        }

    def test_fetches_protected_ref_and_matches_local_head_and_seal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.write_config(project)
            seal = self.make_seal()
            head = "b" * 40
            runner = FakeGitRunner(self.witness(seal, head), head)

            @contextmanager
            def locked_git(*args: object, **kwargs: object):
                del args, kwargs
                yield shutil.which("git") or "git"

            with patch.object(
                remote_seal_witness,
                "hold_verified_project_git_runtime",
                locked_git,
            ):
                result = remote_seal_witness.verify_remote_project_seal_witness(
                    project, seal, runner=runner
                )

            self.assertEqual(result.git_commit, head)
            self.assertEqual(
                result.repository_url,
                "ssh://git@github.com/example/aegis.git",
            )
            self.assertEqual(len(runner.commands), 3)
            self.assertIn("fetch", runner.commands[1])
            self.assertIn(
                "ssh://git@github.com/example/aegis.git", runner.commands[1]
            )
            self.assertNotIn("origin", runner.commands[1])
            self.assertTrue(
                any(
                    item.startswith("refs/heads/aegis-seal-witness:")
                    for item in runner.commands[1]
                )
            )
            for options in runner.options:
                environment = options["env"]
                self.assertIsInstance(environment, dict)
                self.assertNotIn("GIT_DIR", environment)

    def test_remote_unavailable_or_stale_witness_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.write_config(project)
            seal = self.make_seal()
            head = "b" * 40
            stale = self.witness(seal, "c" * 40)
            runner = FakeGitRunner(stale, head)
            with self.assertRaisesRegex(
                remote_seal_witness.RemoteSealWitnessError,
                "commit bound to the local seal",
            ):
                remote_seal_witness.verify_remote_project_seal_witness(
                    project, seal, runner=runner, git_runtime_lock_held=True
                )

            def unavailable(
                command: list[str], **options: object
            ) -> subprocess.CompletedProcess[str]:
                del options
                if "init" in command:
                    return subprocess.CompletedProcess(command, 0, "", "")
                return subprocess.CompletedProcess(command, 1, "", "offline")

            with self.assertRaisesRegex(
                remote_seal_witness.RemoteSealWitnessError,
                "fetch",
            ):
                remote_seal_witness.verify_remote_project_seal_witness(
                    project,
                    seal,
                    runner=unavailable,
                    git_runtime_lock_held=True,
                )

    def test_rejects_witness_when_seal_was_recorded_for_another_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.write_config(project)
            seal = self.make_seal()
            object.__setattr__(seal, "git_head_before_record", "a" * 40)
            head = "b" * 40
            runner = FakeGitRunner(self.witness(seal, head), head)

            with self.assertRaisesRegex(
                remote_seal_witness.RemoteSealWitnessError,
                "commit bound to the local seal",
            ):
                remote_seal_witness.verify_remote_project_seal_witness(
                    project, seal, runner=runner, git_runtime_lock_held=True
                )

    def test_runtime_authority_initialization_requires_proven_ref_absence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.write_config(project)
            absence_calls: list[tuple[list[str], dict[str, object]]] = []
            hostile_profile = project / "hostile-profile"
            hostile_ssh = hostile_profile / ".ssh"
            hostile_ssh.mkdir(parents=True)
            (hostile_ssh / "id_ed25519_sk").write_bytes(b"hostile-sk-key")

            def absent(command: list[str], **options: object):
                absence_calls.append((command, dict(options)))
                return subprocess.CompletedProcess(command, 2, "", "")

            with patch.dict(
                os.environ,
                {
                    "GIT_DIR": str(project / "attacker.git"),
                    "GIT_SSH_COMMAND": "attacker-ssh",
                    "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "url.ssh://attacker/.insteadOf",
                    "GIT_CONFIG_VALUE_0": "ssh://git@github.com/",
                    "HOME": str(hostile_profile),
                    "USERPROFILE": str(hostile_profile),
                },
            ):
                remote_seal_witness.assert_remote_witness_not_published(
                    project,
                    runner=absent,
                    git_executable=shutil.which("git") or "git",
                    git_runtime_lock_held=True,
                )
            absence_command, absence_options = absence_calls[0]
            self.assertIn(
                "ssh://git@github.com/example/aegis.git", absence_command
            )
            trusted_environment = absence_options["env"]
            self.assertIsInstance(trusted_environment, dict)
            for hostile_name in (
                "GIT_DIR",
                "GIT_CONFIG_COUNT",
                "GIT_CONFIG_KEY_0",
                "GIT_CONFIG_VALUE_0",
            ):
                self.assertNotIn(hostile_name, trusted_environment)
            self.assertNotEqual(
                trusted_environment.get("GIT_SSH_COMMAND"), "attacker-ssh"
            )
            self.assertNotEqual(
                trusted_environment.get("HOME"), str(hostile_profile)
            )
            self.assertNotEqual(
                trusted_environment.get("USERPROFILE"), str(hostile_profile)
            )
            ssh_command = trusted_environment["GIT_SSH_COMMAND"]
            self.assertIn("IdentityFile=none", ssh_command)
            self.assertIn("SecurityKeyProvider=none", ssh_command)
            self.assertNotIn("id_ed25519_sk", ssh_command)

            def published(command: list[str], **options: object):
                del options
                return subprocess.CompletedProcess(
                    command,
                    0,
                    "a" * 40 + "\trefs/heads/aegis-seal-witness\n",
                    "",
                )

            with self.assertRaisesRegex(
                remote_seal_witness.RemoteSealWitnessError,
                "already witnessed",
            ):
                remote_seal_witness.assert_remote_witness_not_published(
                    project,
                    runner=published,
                    git_executable=shutil.which("git") or "git",
                    git_runtime_lock_held=True,
                )

    def test_remote_alias_and_mismatched_host_key_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.write_config(project)
            config_path = project / "config" / "seal_witness.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config.pop("repository_url")
            config["remote"] = "origin"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            with self.assertRaisesRegex(
                remote_seal_witness.RemoteSealWitnessError,
                "invalid fields",
            ):
                remote_seal_witness.assert_remote_witness_not_published(
                    project,
                    runner=lambda *args, **kwargs: None,
                    git_executable=shutil.which("git") or "git",
                    git_runtime_lock_held=True,
                )

            self.write_config(project)
            (project / "config" / "git_ssh_known_hosts").write_text(
                "attacker.example ssh-ed25519 "
                "AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                remote_seal_witness.RemoteSealWitnessError,
                "canonical repository host",
            ):
                remote_seal_witness.assert_remote_witness_not_published(
                    project,
                    runner=lambda *args, **kwargs: None,
                    git_executable=shutil.which("git") or "git",
                    git_runtime_lock_held=True,
                )

            self.write_config(project)
            (project / "test-ssh-identity").write_bytes(b"changed-key")
            with self.assertRaisesRegex(
                remote_seal_witness.RemoteSealWitnessError,
                "identity file differs",
            ):
                remote_seal_witness.assert_remote_witness_not_published(
                    project,
                    runner=lambda *args, **kwargs: None,
                    git_executable=shutil.which("git") or "git",
                    git_runtime_lock_held=True,
                )


if __name__ == "__main__":
    unittest.main()
