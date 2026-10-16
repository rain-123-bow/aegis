from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import project_seal_store
import remote_seal_witness
from path_security import StablePathSpec, hold_paths_stable
from runtime_identity import RuntimeIdentityError, trusted_git_environment


class WitnessIdentityLocationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="aegis-witness-location-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = self.root / "project"
        (self.project / "config").mkdir(parents=True)
        self.identity = self.root / "用户 keys" / "id_ed25519"
        self.identity.parent.mkdir()
        self.identity.write_bytes(b"test identity, not a real credential")
        self.payload = {
            "schema": "aegis.remote_seal_witness_config.v4",
            "repository_url": "ssh://git@github.com/example/project.git",
            "protected_ref": "refs/heads/aegis-seal-witness",
            "ssh_identity": {
                "path_env": "AEGIS_WITNESS_IDENTITY_FILE",
                "sha256": hashlib.sha256(self.identity.read_bytes()).hexdigest(),
            },
        }
        self.config = self.project / "config" / "seal_witness.json"
        self.write_config()

    def write_config(self) -> None:
        self.config.write_text(json.dumps(self.payload), encoding="utf-8")

    def assert_rejected(self) -> None:
        with self.assertRaises(remote_seal_witness.RemoteSealWitnessError):
            remote_seal_witness._load_witness_config(self.project)
        with self.assertRaises(project_seal_store.ProjectSealStoreError):
            project_seal_store._sealed_ssh_identity_spec(self.project)

    def test_v4_reads_and_locks_the_same_explicit_local_path(self) -> None:
        before = self.config.read_bytes()
        for name in ("identity one", "迁移后的身份"):
            identity = self.root / name
            identity.write_bytes(self.identity.read_bytes())
            with patch.dict(os.environ, {"AEGIS_WITNESS_IDENTITY_FILE": str(identity)}):
                _, _, selected, digest = remote_seal_witness._load_witness_config(self.project)
                locked = project_seal_store._sealed_ssh_identity_spec(self.project)
            self.assertEqual(selected, identity)
            self.assertEqual(locked.path, selected)
            self.assertEqual(digest, self.payload["ssh_identity"]["sha256"])
        self.assertEqual(self.config.read_bytes(), before)

    def test_v3_absolute_descriptor_remains_supported(self) -> None:
        self.payload["schema"] = "aegis.remote_seal_witness_config.v3"
        self.payload["ssh_identity"].pop("path_env")
        self.payload["ssh_identity"]["path"] = str(self.identity)
        self.write_config()
        _, _, selected, _ = remote_seal_witness._load_witness_config(self.project)
        self.assertEqual(selected, self.identity)
        self.assertEqual(project_seal_store._sealed_ssh_identity_spec(self.project).path, selected)

    def test_v4_requires_a_present_absolute_unexpanded_path(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assert_rejected()
        for invalid in ("", "id_ed25519", "~/.ssh/id_ed25519", "%USERPROFILE%/key", "bad\x00path"):
            with self.subTest(value=invalid), patch.object(
                os, "environ", {"AEGIS_WITNESS_IDENTITY_FILE": invalid}
            ):
                self.assert_rejected()

    def test_v4_rejects_invalid_environment_name_and_ambiguous_fields(self) -> None:
        for invalid in ("", "lowercase", "PATH=secret", "A\x00B", 123):
            self.payload["ssh_identity"]["path_env"] = invalid
            self.write_config()
            with self.subTest(name=invalid):
                self.assert_rejected()
        self.payload["ssh_identity"]["path_env"] = "AEGIS_WITNESS_IDENTITY_FILE"
        self.payload["ssh_identity"]["path"] = str(self.identity)
        self.write_config()
        self.assert_rejected()

    def test_wrong_identity_digest_still_fails_before_transport(self) -> None:
        with patch.dict(os.environ, {"AEGIS_WITNESS_IDENTITY_FILE": str(self.identity)}):
            _, _, selected, digest = remote_seal_witness._load_witness_config(self.project)
        self.identity.write_bytes(b"unapproved replacement")
        known_hosts = self.project / "config" / "known_hosts"
        known_hosts.write_text("test fixture\n", encoding="ascii")
        git = shutil.which("git")
        self.assertIsNotNone(git)
        with self.assertRaisesRegex(RuntimeIdentityError, "differs from the sealed transport descriptor"):
            trusted_git_environment(
                git, ssh_known_hosts=known_hosts,
                ssh_identity_file=selected, expected_ssh_identity_sha256=digest,
            )

    def test_transport_locks_its_resolved_identity_after_environment_changes(self) -> None:
        from test_remote_seal_witness import FakeGitRunner, RemoteSealWitnessTests

        support = RemoteSealWitnessTests()
        seal = support.make_seal()
        second = self.root / "second-identity"
        second.write_bytes(self.identity.read_bytes())
        shutil.copyfile(
            Path(__file__).resolve().parents[1] / "config" / "git_ssh_known_hosts",
            self.project / "config" / "git_ssh_known_hosts",
        )

        @contextmanager
        def outer_repository_lock(*_args, **_kwargs):
            spec = StablePathSpec(self.identity, self.root, "outer identity")
            with hold_paths_stable((spec,)):
                os.environ["AEGIS_WITNESS_IDENTITY_FILE"] = str(second)
                yield shutil.which("git")

        for operation in ("verify", "absence"):
            checked = []
            fake_git = FakeGitRunner(support.witness(seal, seal.git_head_before_record), seal.git_head_before_record)

            def runner(command, **options):
                # A real Windows sharing violation proves the transport identity,
                # rather than the earlier environment selection, stays locked.
                with self.assertRaises(PermissionError):
                    second.write_bytes(b"replacement during transport")
                checked.append(command)
                if operation == "absence":
                    import subprocess
                    return subprocess.CompletedProcess(command, 2, "", "")
                return fake_git(command, **options)

            with (
                self.subTest(operation=operation),
                patch.dict(os.environ, {"AEGIS_WITNESS_IDENTITY_FILE": str(self.identity)}),
                patch.object(remote_seal_witness, "hold_verified_project_git_runtime", outer_repository_lock),
            ):
                if operation == "verify":
                    remote_seal_witness.verify_remote_project_seal_witness(self.project, seal, runner=runner)
                else:
                    remote_seal_witness.assert_remote_witness_not_published(self.project, runner=runner)
                self.assertTrue(checked)
            self.assertEqual(second.read_bytes(), self.identity.read_bytes())

    def test_v4_rejects_malformed_digest_without_resolving_transport(self) -> None:
        for invalid in (None, "", "g" * 64, "A" * 64, 123):
            self.payload["ssh_identity"]["sha256"] = invalid
            self.write_config()
            with self.subTest(digest=invalid), patch.dict(
                os.environ, {"AEGIS_WITNESS_IDENTITY_FILE": str(self.identity)}
            ):
                self.assert_rejected()


if __name__ == "__main__":
    unittest.main()
