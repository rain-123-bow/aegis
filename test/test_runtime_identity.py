from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from runtime_identity import git_runtime_manifest, hold_verified_git_runtime


@unittest.skipUnless(os.name == "nt", "Windows share-lock contract")
class VerifiedGitRuntimeLockTests(unittest.TestCase):
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
