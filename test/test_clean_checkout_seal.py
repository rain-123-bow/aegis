from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEAL_PATH = Path(".aegis/reasoning_ledger/artifacts/facts/project-seal.json")


class CleanCheckoutSealTests(unittest.TestCase):
    def test_clean_checkout_requires_local_seal_provisioning(self) -> None:
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
            ignored = subprocess.run(
                ["git", "check-ignore", "--no-index", str(SEAL_PATH)],
                cwd=checkout,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertFalse(seal_path.exists())
            self.assertNotEqual(
                verification.returncode,
                0,
                msg="a clean checkout must not contain a locally issued project Seal",
            )
            self.assertIn("project-seal.json", verification.stderr)
            self.assertEqual(ignored.returncode, 0)
            self.assertEqual(status, "")


if __name__ == "__main__":
    unittest.main()
