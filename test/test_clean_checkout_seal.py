from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEAL_PATH = Path(".aegis/reasoning_ledger/artifacts/facts/project-seal.json")


class CleanCheckoutSealTests(unittest.TestCase):
    def test_committed_seal_verifies_in_clean_windows_checkout(self) -> None:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout.strip()
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--no-local",
                    "--no-checkout",
                    str(PROJECT_ROOT),
                    str(checkout),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            subprocess.run(
                ["git", "config", "core.autocrlf", "true"],
                cwd=checkout,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            subprocess.run(
                ["git", "checkout", "--detach", head],
                cwd=checkout,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            seal_path = checkout / SEAL_PATH
            before = hashlib.sha256(seal_path.read_bytes()).hexdigest()
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(checkout / "src")
            verification = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    (
                        "from pathlib import Path; "
                        "from project_seal_store import verify_expected_project_seal; "
                        "print(verify_expected_project_seal(Path.cwd()).expected_seal)"
                    ),
                ],
                cwd=checkout,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=checkout,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            ).stdout

            self.assertEqual(
                verification.returncode,
                0,
                msg=f"stdout={verification.stdout!r} stderr={verification.stderr!r}",
            )
            self.assertRegex(verification.stdout.strip(), r"^ASC1:[0-9a-f]{64}$")
            self.assertEqual(hashlib.sha256(seal_path.read_bytes()).hexdigest(), before)
            self.assertEqual(status, "")


if __name__ == "__main__":
    unittest.main()
