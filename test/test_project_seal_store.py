from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import project_seal_store


class ProjectSealStoreTests(unittest.TestCase):
    def make_project(self, root: Path, content: str = "VALUE = 1\n") -> Path:
        project = root / "project"
        source = project / "src" / "module.py"
        source.parent.mkdir(parents=True)
        source.write_text(content, encoding="utf-8")
        return project

    def test_initial_record_is_persisted_and_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))

            record = project_seal_store.record_project_seal(
                project,
                git_head_before_record="a" * 40,
                project_id=bytes(range(16)),
                run_id=bytes(range(16, 32)),
            )

            self.assertEqual(record.sequence, 0)
            self.assertEqual(record.previous_seal, bytes(32))
            self.assertTrue(record.expected_seal.startswith("ASC1:"))
            self.assertEqual(
                project_seal_store.verify_expected_project_seal(project),
                record,
            )

    def test_append_extends_one_chain_after_authorized_source_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            first = project_seal_store.record_project_seal(
                project,
                git_head_before_record="a" * 40,
                project_id=bytes(range(16)),
                run_id=bytes(range(16, 32)),
            )
            (project / "src" / "module.py").write_text(
                "VALUE = 2\n", encoding="utf-8"
            )

            second = project_seal_store.record_project_seal(
                project,
                git_head_before_record="b" * 40,
            )
            chain = project_seal_store.load_project_seal_chain(project)

            self.assertEqual([item.sequence for item in chain.records], [0, 1])
            self.assertEqual(second.previous_seal.hex(), first.expected_seal[5:])
            self.assertEqual(second.project_id, first.project_id)
            self.assertEqual(second.run_id, first.run_id)
            self.assertEqual(
                project_seal_store.verify_expected_project_seal(project),
                second,
            )

    def test_source_change_after_record_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            project_seal_store.record_project_seal(
                project,
                git_head_before_record="a" * 40,
                project_id=bytes(range(16)),
                run_id=bytes(range(16, 32)),
            )
            (project / "src" / "module.py").write_text(
                "VALUE = 999\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(
                project_seal_store.ProjectSealMismatchError,
                "does not match",
            ):
                project_seal_store.verify_expected_project_seal(project)

    def test_broken_chain_is_rejected_before_seal_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            project_seal_store.record_project_seal(
                project,
                git_head_before_record="a" * 40,
                project_id=bytes(range(16)),
                run_id=bytes(range(16, 32)),
            )
            (project / "src" / "module.py").write_text(
                "VALUE = 2\n", encoding="utf-8"
            )
            project_seal_store.record_project_seal(
                project,
                git_head_before_record="b" * 40,
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


if __name__ == "__main__":
    unittest.main()
