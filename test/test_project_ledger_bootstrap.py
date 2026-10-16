from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from reasoning_ledger.project import (  # noqa: E402
    ProjectLedgerConfig,
    bootstrap_project_ledger,
)


class ProjectLedgerBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.arguments = {
            "project_id": "portable_project",
            "dsn_env": "PORTABLE_TEST_LEDGER_DSN",
            "schema": "portable_ledger",
            "embedding_dimensions": 7,
        }
        self.anchor = "ab" * 32

    def make_existing_project(self, root: Path | None = None) -> ProjectLedgerConfig:
        root = root or self.root
        config = bootstrap_project_ledger(root, **self.arguments).config
        data = config.to_json_data()
        data["ledger"]["project_anchor_sha256"] = self.anchor
        # Deliberately retain valid, non-default JSON formatting across relocation.
        config.config_path.write_bytes(
            (json.dumps(data, indent=4) + "\r\n").encode("utf-8")
        )
        ledger_root = root / ".aegis" / "reasoning_ledger"
        (ledger_root / "README.md").write_bytes(b"# Local ledger notes\r\nKeep me.\r\n")
        (ledger_root / "artifacts" / "evidence" / "existing.bin").write_bytes(
            b"existing project-owned evidence\x00\xff"
        )
        return ProjectLedgerConfig.load(root)

    def snapshot(self, root: Path) -> dict[str, bytes | None]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
            for path in root.rglob("*")
        }

    def test_new_project_creates_valid_config_migration_and_layout(self) -> None:
        root = self.root / "new_project"
        result = bootstrap_project_ledger(root, **self.arguments)

        self.assertEqual(ProjectLedgerConfig.load(root), result.config)
        for name, value in self.arguments.items():
            with self.subTest(field=name):
                self.assertEqual(getattr(result.config, name), value)
        self.assertIsNone(result.config.project_anchor_sha256)
        self.assertEqual(
            result.config.migration_path.read_bytes(),
            (result.migration_sql + "\n").encode("utf-8"),
        )
        ledger_root = root / ".aegis" / "reasoning_ledger"
        for relative in (
            "exports", "migrations", "artifacts/requirements", "artifacts/facts",
            "artifacts/rules", "artifacts/claims", "artifacts/evidence", "artifacts/reviews",
        ):
            with self.subTest(directory=relative):
                self.assertTrue((ledger_root / relative).is_dir())
        self.assertIn("Reasoning Ledger", (ledger_root / "README.md").read_text("utf-8"))
        self.assertTrue(all(path.exists() for path in result.created_paths))

    def test_identical_bootstrap_preserves_config_bytes(self) -> None:
        config = self.make_existing_project()
        original = config.config_path.read_bytes()

        bootstrap_project_ledger(self.root, **self.arguments)

        self.assertEqual(config.config_path.read_bytes(), original)

    def test_identical_bootstrap_retains_existing_anchor_in_result_and_on_disk(self) -> None:
        self.make_existing_project()

        result = bootstrap_project_ledger(self.root, **self.arguments)

        with self.subTest(location="returned configuration"):
            self.assertEqual(result.config.project_anchor_sha256, self.anchor)
        with self.subTest(location="saved configuration"):
            self.assertEqual(ProjectLedgerConfig.load(self.root).project_anchor_sha256, self.anchor)

    def test_identical_bootstrap_preserves_custom_ledger_readme(self) -> None:
        self.make_existing_project()
        readme = self.root / ".aegis" / "reasoning_ledger" / "README.md"
        original = readme.read_bytes()

        bootstrap_project_ledger(self.root, **self.arguments)

        self.assertEqual(readme.read_bytes(), original)

    def test_conflicting_parameters_are_rejected_without_changing_project(self) -> None:
        for field, conflicting_value in (
            ("project_id", "another_project"),
            ("dsn_env", "ANOTHER_LEDGER_DSN"),
            ("schema", "another_ledger"),
            ("embedding_dimensions", 11),
        ):
            with self.subTest(field=field):
                root = self.root / field
                self.make_existing_project(root)
                before = self.snapshot(root)
                arguments = {**self.arguments, field: conflicting_value}
                try:
                    with self.assertRaises(ValueError):
                        bootstrap_project_ledger(root, **arguments)
                finally:
                    self.assertEqual(self.snapshot(root), before)

    def test_conflicting_migration_is_rejected_without_changing_project(self) -> None:
        config = self.make_existing_project()
        config.migration_path.write_bytes(b"-- Existing migration must not be replaced.\r\n")
        before = self.snapshot(self.root)

        try:
            with self.assertRaises(ValueError):
                bootstrap_project_ledger(self.root, **self.arguments)
        finally:
            self.assertEqual(self.snapshot(self.root), before)


if __name__ == "__main__":
    unittest.main()
