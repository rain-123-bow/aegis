from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from runtime_identity import (
    RuntimeIdentityError,
    _installed_distribution_versions,
    _stable_file_identity,
    _verify_tracerelay_source_identity,
    git_runtime_manifest,
    hold_verified_git_runtime,
)


class ProductionRuntimeIdentityTests(unittest.TestCase):
    def test_runtime_file_identity_ignores_windows_change_time_metadata(self) -> None:
        first = SimpleNamespace(
            device=1,
            inode=2,
            size=3,
            modified_ns=4,
            changed_ns=5,
        )
        second = SimpleNamespace(
            device=1,
            inode=2,
            size=3,
            modified_ns=4,
            changed_ns=6,
        )

        self.assertEqual(_stable_file_identity(first), _stable_file_identity(second))
        self.assertNotIn("changed_ns", _stable_file_identity(first))

    def test_installed_distribution_versions_survive_json_round_trip(self) -> None:
        distributions = (
            SimpleNamespace(metadata={"Name": "Zulu"}, name="zulu", version="2"),
            SimpleNamespace(metadata={"Name": "alpha"}, name="alpha", version="1"),
        )
        with patch(
            "runtime_identity.importlib.metadata.distributions",
            return_value=distributions,
        ):
            versions = _installed_distribution_versions()

        self.assertEqual(versions, [["alpha", "1"], ["Zulu", "2"]])
        self.assertEqual(versions, json.loads(json.dumps(versions)))


class TraceRelaySdkSnapshotTests(unittest.TestCase):
    def prepare_snapshot(self, temporary_directory: str) -> tuple[Path, Path]:
        temporary_root = Path(temporary_directory)
        project = temporary_root / "project"
        component = project / "third_party" / "TraceRelay"
        shutil.copytree(PROJECT_ROOT / "third_party" / "TraceRelay", component)
        installed = temporary_root / "installed" / "tracerelay"
        shutil.copytree(component / "src" / "tracerelay", installed)
        return project, installed

    def test_installed_source_exactly_matches_verified_sdk_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, installed = self.prepare_snapshot(directory)

            added: list[tuple[Path, str, int | None, str | None]] = []

            def add(
                path: Path,
                source: str,
                expected_size: int | None = None,
                expected_sha256: str | None = None,
            ) -> None:
                added.append(
                    (Path(path), source, expected_size, expected_sha256)
                )

            distribution = SimpleNamespace(
                metadata={"Name": "TraceRelay"},
                files=(Path("tracerelay/__init__.py"),),
                locate_file=lambda relative: installed.parent / relative,
            )
            with patch(
                "runtime_identity.importlib.metadata.distributions",
                return_value=(distribution,),
            ):
                identity = _verify_tracerelay_source_identity(
                    project,
                    add,
                )

            self.assertEqual(identity["installed_package_root"], str(installed))
            self.assertEqual(
                sum(
                    source == "tracerelay_installed_source"
                    for _, source, _, _ in added
                ),
                11,
            )

    def test_installed_source_rejects_any_extra_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project, installed = self.prepare_snapshot(directory)
            (installed / "shadow.py").write_text("VALUE = 1\n", encoding="utf-8")
            with (
                patch(
                    "runtime_identity.importlib.metadata.distributions",
                    return_value=(
                        SimpleNamespace(
                            metadata={"Name": "TraceRelay"},
                            files=(Path("tracerelay/__init__.py"),),
                            locate_file=lambda relative: installed.parent / relative,
                        ),
                    ),
                ),
                self.assertRaisesRegex(
                    RuntimeIdentityError, "file set differs"
                ),
            ):
                _verify_tracerelay_source_identity(project, lambda *_args: None)


@unittest.skipUnless(os.name == "nt", "Windows share-lock contract")
class VerifiedGitRuntimeLockTests(unittest.TestCase):
    def test_runtime_manifest_ignores_windows_path_case_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            git_root = Path(directory) / "Git"
            launcher = git_root / "cmd" / "git.exe"
            launcher.parent.mkdir(parents=True)
            launcher.write_bytes(b"launcher-v1")

            lower_files, lower_sha256 = git_runtime_manifest(launcher)
            upper_files, upper_sha256 = git_runtime_manifest(
                launcher.with_name("git.EXE")
            )

            self.assertEqual(lower_files, upper_files)
            self.assertEqual(lower_sha256, upper_sha256)

    def test_runtime_files_cannot_change_until_locked_session_exits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            git_root = Path(directory) / "Git"
            launcher = git_root / "cmd" / "git.exe"
            helper = git_root / "mingw64" / "bin" / "helper.dll"
            ssh = git_root / "usr" / "bin" / "ssh.exe"
            launcher.parent.mkdir(parents=True)
            helper.parent.mkdir(parents=True)
            ssh.parent.mkdir(parents=True)
            launcher.write_bytes(b"launcher-v1")
            helper.write_bytes(b"helper-v1")
            ssh.write_bytes(b"ssh-v1")
            _files, runtime_sha256 = git_runtime_manifest(launcher)

            with hold_verified_git_runtime(
                launcher,
                expected_launcher_sha256=hashlib.sha256(
                    launcher.read_bytes()
                ).hexdigest(),
                expected_runtime_sha256=runtime_sha256,
            ) as locked_git:
                self.assertEqual(Path(locked_git), launcher)
                with self.assertRaises(OSError):
                    helper.write_bytes(b"helper-v2")
                with self.assertRaises(OSError):
                    ssh.write_bytes(b"ssh-v2")

            helper.write_bytes(b"helper-v2")
            self.assertEqual(helper.read_bytes(), b"helper-v2")


if __name__ == "__main__":
    unittest.main()
