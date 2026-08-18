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
            "eb2d5ce90c8cfa08b30bb37287486a42521ef18ce80ac1ac765461994fd59301",
        )

    def test_aegis_can_compute_and_verify_project_sources(self) -> None:
        context = aegis_seal_core.SealContext(
            project_id=bytes(range(0x10, 0x20)),
            seal_chain_id=bytes(range(0x40, 0x50)),
        )
        entries = [
            ("CMakeLists.txt", b"cmake"),
            ("config/runtime.json", b"{}"),
            ("src/main.cpp", b"int main"),
        ]

        seal = aegis_seal_core.compute_project_seal(context, entries)

        self.assertRegex(seal, r"^ASC1:[0-9a-f]{64}$")
        self.assertTrue(
            aegis_seal_core.verify_project_seal(context, entries, seal)
        )
        self.assertFalse(
            aegis_seal_core.verify_project_seal(
                context, entries, "ASC1:" + "0" * 64
            )
        )

    def test_invalid_chain_context_is_rejected_before_process_start(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "positive sequence requires a previous seal"
        ):
            aegis_seal_core.SealContext(
                project_id=bytes(16),
                seal_chain_id=bytes(16),
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
