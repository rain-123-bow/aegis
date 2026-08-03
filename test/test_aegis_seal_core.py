from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import aegis_seal_core


class AegisSealCoreIntegrationTests(unittest.TestCase):
    def test_bundled_binary_matches_pinned_release(self) -> None:
        executable = aegis_seal_core.verify_bundled_executable()

        self.assertEqual(
            executable,
            PROJECT_ROOT
            / "third_party"
            / "AegisSealCore"
            / "windows-x64"
            / "aegis-seal.exe",
        )
        self.assertEqual(
            aegis_seal_core.BUNDLED_SHA256,
            "256b71015465a7a57b648753834583e095383d77d88d2140e5e970a174375023",
        )

    def test_aegis_can_compute_and_verify_project_sources(self) -> None:
        context = aegis_seal_core.SealContext(
            project_id=bytes(range(0x10, 0x20)),
            run_id=bytes(range(0x40, 0x50)),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            (project_root / "src" / "__pycache__").mkdir(parents=True)
            (project_root / "include").mkdir()
            (project_root / "src" / "main.cpp").write_bytes(b"int main")
            (project_root / "include" / "main.hpp").write_bytes(b"#pragma")
            (project_root / "src" / "__pycache__" / "ignored.pyc").write_bytes(
                b"generated"
            )

            seal = aegis_seal_core.compute_project_seal(project_root, context)

            self.assertEqual(
                seal,
                "ASC1:0cb65a29352e00e8370541f18b04c4f88d881eb93e193a0be9cdcf40763cf00e",
            )
            self.assertTrue(
                aegis_seal_core.verify_project_seal(project_root, context, seal)
            )
            self.assertFalse(
                aegis_seal_core.verify_project_seal(
                    project_root, context, "ASC1:" + "0" * 64
                )
            )

    def test_invalid_chain_context_is_rejected_before_process_start(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "positive sequence requires a previous seal"
        ):
            aegis_seal_core.SealContext(
                project_id=bytes(16),
                run_id=bytes(16),
                sequence=1,
            )

    def test_modified_bundled_binary_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            modified = Path(temporary_directory) / "aegis-seal.exe"
            shutil.copyfile(aegis_seal_core.BUNDLED_EXECUTABLE, modified)
            contents = bytearray(modified.read_bytes())
            contents[-1] ^= 0x01
            modified.write_bytes(contents)

            with self.assertRaisesRegex(
                aegis_seal_core.AegisSealError, "SHA-256 mismatch"
            ):
                aegis_seal_core.verify_bundled_executable(modified)


if __name__ == "__main__":
    unittest.main()
