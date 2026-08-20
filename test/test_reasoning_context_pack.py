from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from reasoning_context_pack import (  # noqa: E402
    ReasoningContextPackError,
    validate_reasoning_context_pack,
)
from reasoning_ledger.context_pack import write_context_pack  # noqa: E402
from reasoning_ledger.models import (  # noqa: E402
    AuthorityContextPack,
    CandidateHit,
    LedgerEvidence,
    LedgerStatementRevision,
)


def canonical_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class ReasoningContextPackTests(unittest.TestCase):
    def _write_pack(self, root: Path, **changes: object) -> tuple[Path, Path, Path]:
        project = root / "project"
        artifacts = root / "artifacts"
        evidence = (
            project
            / ".aegis"
            / "reasoning_ledger"
            / "artifacts"
            / "facts"
            / "fact.md"
        )
        evidence.parent.mkdir(parents=True)
        evidence.write_text("objective fact\n", encoding="utf-8")
        artifacts.mkdir()
        content = evidence.read_bytes()
        captured = "2026-08-20T00:00:00Z"
        evidence_descriptor = {
            "project_id": "11" * 16,
            "evidence_id": "evidence.fact.runtime",
            "path": ".aegis/reasoning_ledger/artifacts/facts/fact.md",
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "captured_at": captured,
            "scope": {"task": "runtime-hardening"},
            "content_sha256": "bb" * 32,
            "created_at": captured,
        }
        revision = {
            "project_id": "11" * 16,
            "statement_id": "fact.runtime.objective",
            "revision": 1,
            "statement_type": "FACT",
            "content": "Objective fact.",
            "structured_conditions": {},
            "validity": "ACTIVE",
            "current_validity": "ACTIVE",
            "scope": {"task": "runtime-hardening"},
            "confidence": 1.0,
            "content_sha256": "cc" * 32,
            "created_at": captured,
            "evidence_ids": ["evidence.fact.runtime"],
        }
        payload: dict[str, object] = {
            "schema": "aegis.reasoning_context_pack.v3",
            "project_id_hex": "11" * 16,
            "task_id": "task-runtime-hardening",
            "agent_role": "AEGIS_WORKFLOW",
            "query": "requirements scope causality refutations environment warnings",
            "generated_at_utc": captured,
            "bindings": {
                "project_seal": "ASC1:" + "22" * 32,
                "engineering_documents_sha256": "33" * 32,
            },
            "ledger": {"revision": 7, "snapshot_sha256": "44" * 32},
            "retrieval": {
                "mode": "lexical_exact",
                "embedding_source": "none",
                "scope": {"task": "runtime-hardening"},
                "limit": 12,
                "include_causes": True,
                "trace": {
                    "hard_filters": {
                        "project_id": "11" * 16,
                        "scope": {"task": "runtime-hardening"},
                        "validities": ["ACTIVE", "STALE"],
                        "statement_types": [],
                        "created_after": None,
                        "created_before": None,
                    },
                    "lexical_candidates": ["fact.runtime.objective@1"],
                    "semantic_candidates": [],
                    "embedding_profile_id": None,
                    "embedding_query_receipt": None,
                    "causal_relations": [
                        "SUPPORTS",
                        "ASSUMES",
                        "CAUSES",
                        "ENABLES",
                        "REQUIRES",
                    ],
                    "max_causal_depth": 8,
                    "limit": 12,
                },
            },
            "candidates": [
                {
                    "revision": revision,
                    "sources": ["LEXICAL"],
                    "lexical_rank": 1.0,
                    "semantic_distance": None,
                }
            ],
            "causal_revisions": [],
            "relations": [],
            "conflicts": [],
            "warnings": [],
            "evidence_descriptors": [evidence_descriptor],
            "evidence_index": [
                {
                    "evidence_id": "evidence.fact.runtime",
                    "path": str(evidence),
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            ],
        }
        payload.update(changes)
        payload["canonical_payload_sha256"] = hashlib.sha256(
            canonical_bytes(payload)
        ).hexdigest()
        path = root / "context-pack.json"
        path.write_bytes(canonical_bytes(payload) + b"\n")
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
            self.assertNotIn("coverage", result.payload)
            self.assertNotIn(
                "created_by",
                result.payload["candidates"][0]["revision"],
            )
            self.assertNotIn(
                "created_by",
                result.payload["evidence_descriptors"][0],
            )
            self.assertNotIn(
                "source_identity",
                result.payload["evidence_descriptors"][0],
            )

    def test_rejects_retrieval_mode_without_matching_query_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path, project, artifacts = self._write_pack(Path(temp))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["retrieval"]["mode"] = "hybrid_exact"
            payload.pop("canonical_payload_sha256")
            payload["canonical_payload_sha256"] = hashlib.sha256(
                canonical_bytes(payload)
            ).hexdigest()
            path.write_bytes(canonical_bytes(payload) + b"\n")

            with self.assertRaisesRegex(
                ReasoningContextPackError,
                "retrieval mode differs",
            ):
                validate_reasoning_context_pack(
                    path,
                    project_root=project,
                    artifact_root=artifacts,
                    project_id_hex="11" * 16,
                    project_seal="ASC1:" + "22" * 32,
                    engineering_documents_sha256="33" * 32,
                )

    def test_generated_context_pack_is_accepted_by_runtime_validator(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            artifacts = root / "artifacts"
            evidence_path = project / "evidence" / "fact.md"
            evidence_path.parent.mkdir(parents=True)
            evidence_path.write_text("objective fact\n", encoding="utf-8")
            artifacts.mkdir()
            content = evidence_path.read_bytes()
            captured = "2026-08-20T00:00:00Z"
            project_id = "11" * 16
            evidence = LedgerEvidence(
                project_id=project_id,
                evidence_id="evidence.fact.runtime",
                path="evidence/fact.md",
                size=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                source_identity={"kind": "git_blob", "oid": "aa" * 20},
                captured_at=captured,
                scope={"task": "runtime-hardening"},
                content_sha256="bb" * 32,
                created_by="master",
                created_at=captured,
            )
            revision = LedgerStatementRevision(
                project_id=project_id,
                statement_id="fact.runtime.objective",
                revision=1,
                statement_type="FACT",
                content="Objective fact.",
                structured_conditions={},
                validity="ACTIVE",
                current_validity="ACTIVE",
                scope={"task": "runtime-hardening"},
                confidence=1.0,
                content_sha256="cc" * 32,
                created_by="master",
                created_at=captured,
                evidence_ids=(evidence.evidence_id,),
            )
            trace = {
                "hard_filters": {
                    "project_id": project_id,
                    "scope": {"task": "runtime-hardening"},
                    "validities": ["ACTIVE", "STALE"],
                    "statement_types": [],
                    "created_after": None,
                    "created_before": None,
                },
                "lexical_candidates": ["fact.runtime.objective@1"],
                "semantic_candidates": [],
                "embedding_profile_id": None,
                "embedding_query_receipt": None,
                "causal_relations": [
                    "SUPPORTS",
                    "ASSUMES",
                    "CAUSES",
                    "ENABLES",
                    "REQUIRES",
                ],
                "max_causal_depth": 8,
                "limit": 12,
            }
            pack = AuthorityContextPack(
                project_id=project_id,
                task_id="task-runtime-hardening",
                agent_role="AEGIS_WORKFLOW",
                query="requirements scope causality refutations environment warnings",
                candidates=(CandidateHit(revision=revision, sources=("LEXICAL",), lexical_rank=1.0),),
                causal_revisions=(),
                relations=(),
                conflicts=(),
                warnings=(),
                evidence_descriptors=(evidence,),
                retrieval_trace=trace,
            )
            markdown_path = artifacts / "REASONING_LEDGER_CONTEXT_PACK.md"
            json_path = artifacts / "REASONING_LEDGER_CONTEXT_PACK.json"
            write_context_pack(
                pack,
                markdown_path,
                json_output_path=json_path,
                project_seal="ASC1:" + "22" * 32,
                engineering_documents_sha256="33" * 32,
                ledger_revision=7,
                ledger_snapshot_sha256="44" * 32,
                retrieval_scope={"task": "runtime-hardening"},
                limit=12,
                include_causes=True,
                project_root=project,
            )

            result = validate_reasoning_context_pack(
                json_path,
                project_root=project,
                artifact_root=artifacts,
                project_id_hex=project_id,
                project_seal="ASC1:" + "22" * 32,
                engineering_documents_sha256="33" * 32,
            )
            self.assertEqual(result.task_id, "task-runtime-hardening")
            self.assertTrue(markdown_path.exists())
            self.assertEqual(result.payload["retrieval"]["mode"], "lexical_exact")

    def test_single_relevant_statement_is_not_mislabeled_as_complete_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path, project, artifacts = self._write_pack(Path(temp))
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("coverage", payload)
            self.assertEqual(len(payload["candidates"]), 1)
            validate_reasoning_context_pack(
                path,
                project_root=project,
                artifact_root=artifacts,
                project_id_hex="11" * 16,
                project_seal="ASC1:" + "22" * 32,
                engineering_documents_sha256="33" * 32,
            )

    def test_accepts_zero_hit_pack_from_empty_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path, project, artifacts = self._write_pack(Path(temp))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["candidates"] = []
            payload["causal_revisions"] = []
            payload["relations"] = []
            payload["conflicts"] = []
            payload["evidence_descriptors"] = []
            payload["evidence_index"] = []
            payload["retrieval"]["trace"]["lexical_candidates"] = []
            payload["retrieval"]["trace"]["semantic_candidates"] = []
            payload.pop("canonical_payload_sha256")
            payload["canonical_payload_sha256"] = hashlib.sha256(
                canonical_bytes(payload)
            ).hexdigest()
            path.write_bytes(canonical_bytes(payload) + b"\n")

            result = validate_reasoning_context_pack(
                path,
                project_root=project,
                artifact_root=artifacts,
                project_id_hex="11" * 16,
                project_seal="ASC1:" + "22" * 32,
                engineering_documents_sha256="33" * 32,
            )
            self.assertEqual(result.payload["candidates"], [])
            self.assertEqual(result.payload["evidence_descriptors"], [])

    def test_rejects_nested_self_declared_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path, project, artifacts = self._write_pack(Path(temp))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["retrieval"]["scope"] = {
                "task": {
                    "authority": {"required_permissions": ["secret"]}
                }
            }
            payload.pop("canonical_payload_sha256")
            payload["canonical_payload_sha256"] = hashlib.sha256(
                canonical_bytes(payload)
            ).hexdigest()
            path.write_bytes(canonical_bytes(payload) + b"\n")

            with self.assertRaisesRegex(
                ReasoningContextPackError,
                "permission|scope",
            ):
                validate_reasoning_context_pack(
                    path,
                    project_root=project,
                    artifact_root=artifacts,
                    project_id_hex="11" * 16,
                    project_seal="ASC1:" + "22" * 32,
                    engineering_documents_sha256="33" * 32,
                )

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

    def test_rejects_tampered_canonical_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path, project, artifacts = self._write_pack(Path(temp))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["query"] = "tampered"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ReasoningContextPackError, "canonical payload"):
                validate_reasoning_context_pack(
                    path,
                    project_root=project,
                    artifact_root=artifacts,
                    project_id_hex="11" * 16,
                    project_seal="ASC1:" + "22" * 32,
                    engineering_documents_sha256="33" * 32,
                )


if __name__ == "__main__":
    unittest.main()
