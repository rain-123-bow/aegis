from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from engineering_input_manifest import (
    EngineeringInputManifestError,
    validate_engineering_input_manifest,
)


class EngineeringInputManifestTests(unittest.TestCase):
    def _write_manifest(self, root: Path) -> Path:
        requirements = root / "docs" / "REQUIREMENTS.md"
        plan = root / "docs" / "IMPLEMENTATION_PLAN.md"
        requirements.parent.mkdir()
        requirements.write_text("requirement\n", encoding="utf-8")
        plan.write_text("plan\n", encoding="utf-8")

        def descriptor(kind: str, path: Path) -> dict[str, object]:
            content = path.read_bytes()
            return {
                "kind": kind,
                "path": str(path.resolve()),
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }

        manifest = root / "ENGINEERING_INPUT_MANIFEST.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema": "aegis.engineering_input_manifest.v1",
                    "project_id_hex": "11" * 16,
                    "created_at_utc": datetime.now(UTC).isoformat().replace(
                        "+00:00", "Z"
                    ),
                    "documents": [
                        descriptor("REQUIREMENTS", requirements),
                        descriptor("IMPLEMENTATION_PLAN", plan),
                    ],
                }
            ),
            encoding="utf-8",
        )
        return manifest

    def test_accepts_exact_requirement_and_implementation_plan_descriptors(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = self._write_manifest(root)
            validated = validate_engineering_input_manifest(
                manifest,
                project_root=root,
                project_id_hex="11" * 16,
            )
            self.assertEqual(validated.path, manifest.resolve())
            self.assertEqual(len(validated.documents_sha256), 64)

    def test_rejects_document_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = self._write_manifest(root)
            (root / "docs" / "REQUIREMENTS.md").write_text(
                "changed\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                EngineeringInputManifestError, "does not match its descriptor"
            ):
                validate_engineering_input_manifest(
                    manifest,
                    project_root=root,
                    project_id_hex="11" * 16,
                )

    def test_rejects_missing_required_kind(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = self._write_manifest(root)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["documents"] = payload["documents"][:1]
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                EngineeringInputManifestError, "missing required kinds"
            ):
                validate_engineering_input_manifest(
                    manifest,
                    project_root=root,
                    project_id_hex="11" * 16,
                )


if __name__ == "__main__":
    unittest.main()
