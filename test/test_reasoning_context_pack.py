from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from reasoning_context_pack import (
    ReasoningContextPackError,
    validate_reasoning_context_pack,
)


class ReasoningContextPackTests(unittest.TestCase):
    def _write_pack(self, root: Path, **changes: object) -> tuple[Path, Path, Path]:
        project = root / "project"
        artifacts = root / "artifacts"
        evidence = project / ".aegis" / "reasoning_ledger" / "artifacts" / "facts" / "fact.md"
        evidence.parent.mkdir(parents=True)
        evidence.write_text("objective fact\n", encoding="utf-8")
        artifacts.mkdir()
        evidence_bytes = evidence.read_bytes()
        payload: dict[str, object] = {
            "schema": "aegis.reasoning_context_pack.v1",
            "project_id_hex": "11" * 16,
            "task_id": "task-runtime-hardening",
            "agent_role": "AEGIS_WORKFLOW",
            "query": "requirements implementation scope causality refutations environment warnings",
            "generated_at_utc": "2026-08-17T00:00:00Z",
            "bindings": {
                "project_seal": "ASC1:" + "22" * 32,
                "engineering_documents_sha256": "33" * 32,
            },
            "ledger": {"revision": 7, "snapshot_sha256": "44" * 32},
            "retrieval": {
                "mode": "semantic_search",
                "embedding_source": "codex-gpt",
                "scope": {"task": "runtime-hardening"},
                "limit": 12,
                "include_causes": True,
            },
            "coverage": {
                "requirements": True,
                "implementation_plan": True,
                "runtime_scope": True,
                "code_causality": True,
                "known_refutations": True,
                "environment_facts": True,
                "pending_warnings": True,
            },
            "items": [
                {
                    "id": "fact.runtime.objective",
                    "project_id": "11" * 16,
                    "type": "fact",
                    "status": "active",
                    "scope": {"task": "runtime-hardening"},
                    "content": "Objective fact.",
                    "artifact_path": ".aegis/reasoning_ledger/artifacts/facts/fact.md",
                    "source": "evidence",
                    "evidence_path": ".aegis/reasoning_ledger/artifacts/facts/fact.md",
                    "confidence": 1.0,
                    "level": 0,
                    "version": 1,
                    "metadata": {},
                    "created_by": "master",
                    "created_at": "2026-08-17T00:00:00Z",
                    "updated_at": "2026-08-17T00:00:00Z",
                }
            ],
            "cause_items": [],
            "edges": [],
            "warnings": [],
            "required_artifact_paths": [
                ".aegis/reasoning_ledger/artifacts/facts/fact.md"
            ],
            "evidence_index": [
                {
                    "path": str(evidence),
                    "size": len(evidence_bytes),
                    "sha256": hashlib.sha256(evidence_bytes).hexdigest(),
                }
            ],
        }
        payload.update(changes)
        path = root / "context-pack.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path, project, artifacts

    def test_accepts_complete_pack_bound_to_run_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path, project, artifacts = self._write_pack(Path(temp))
            result = validate_reasoning_context_pack(
                path,
                project_root=project,
                artifact_root=artifacts,
                project_id_hex="11" * 16,
                project_seal="ASC1:" + "22" * 32,
                engineering_documents_sha256="33" * 32,
            )
            self.assertEqual(result.task_id, "task-runtime-hardening")
            self.assertEqual(result.ledger_revision, 7)

    def test_rejects_arbitrary_json_without_context_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            artifacts = root / "artifacts"
            project.mkdir()
            artifacts.mkdir()
            path = root / "context-pack.json"
            path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ReasoningContextPackError, "fields|schema"):
                validate_reasoning_context_pack(
                    path,
                    project_root=project,
                    artifact_root=artifacts,
                    project_id_hex="11" * 16,
                    project_seal="ASC1:" + "22" * 32,
                    engineering_documents_sha256="33" * 32,
                )

    def test_rejects_pack_bound_to_different_seal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path, project, artifacts = self._write_pack(Path(temp))
            with self.assertRaisesRegex(ReasoningContextPackError, "project seal"):
                validate_reasoning_context_pack(
                    path,
                    project_root=project,
                    artifact_root=artifacts,
                    project_id_hex="11" * 16,
                    project_seal="ASC1:" + "55" * 32,
                    engineering_documents_sha256="33" * 32,
                )


if __name__ == "__main__":
    unittest.main()
