from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from reasoning_ledger_provenance import (  # noqa: E402
    ReasoningLedgerProvenanceError,
    _verify_embedding_provenance,
    export_live_reasoning_ledger_snapshot,
    verify_context_pack_against_live_snapshot,
)
from reasoning_ledger.models import canonical_embedding_sha256  # noqa: E402
from reasoning_ledger.schema import authority_schema_signature  # noqa: E402


class ReasoningLedgerProvenanceTests(unittest.TestCase):
    def test_embedding_provenance_rehashes_the_exported_vector(self) -> None:
        vector = [0.1, -0.2, 0.3]
        embedding_sha256 = canonical_embedding_sha256(vector, dimensions=3)
        generator = {"kind": "external-command", "executable_sha256": "ab" * 32}
        receipt = {
            "schema": "aegis.embedding_generation_receipt.v1",
            "project_id": "11" * 16,
            "statement_id": "fact-1",
            "revision": 1,
            "profile_id": "profile-1",
            "profile_content_sha256": "aa" * 32,
            "provider": "provider",
            "model": "model",
            "model_version": "1",
            "embedded_text_sha256": "bb" * 32,
            "embedding_sha256": embedding_sha256,
            "embedding_encoding": "ieee754-binary32-big-endian-zero-normalized-v1",
            "generator_identity": generator,
        }
        receipt_sha256 = hashlib.sha256(
            json.dumps(
                receipt,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        snapshot = {
            "embedding_profiles": [
                {
                    "profile_id": "profile-1",
                    "content_sha256": "aa" * 32,
                    "provider": "provider",
                    "model": "model",
                    "model_version": "1",
                    "dimensions": 3,
                }
            ],
            "embedding_index": [
                {
                    "project_id": "11" * 16,
                    "statement_id": "fact-1",
                    "revision": 1,
                    "profile_id": "profile-1",
                    "embedding": "[0.1,-0.2,0.3]",
                    "embedded_text_sha256": "bb" * 32,
                    "embedding_sha256": embedding_sha256,
                    "generator_identity": generator,
                    "generation_receipt": receipt,
                    "generation_receipt_sha256": receipt_sha256,
                    "created_at": "2026-08-20T00:00:00Z",
                }
            ],
        }
        pack = {
            "retrieval": {
                "mode": "hybrid_exact",
                "embedding_source": "command",
                "trace": {
                    "embedding_profile_id": "profile-1",
                    "semantic_candidates": [],
                    "embedding_query_receipt": {
                        "schema": "aegis.query_embedding_receipt.v1",
                        "profile_id": "profile-1",
                        "source": "command",
                        "embedding_sha256": embedding_sha256,
                        "generator_identity": {
                            "kind": "external-command"
                        },
                    },
                }
            }
        }
        _verify_embedding_provenance(pack, snapshot)
        snapshot["embedding_index"][0]["embedding"] = "[0.1,-0.2,0.4]"
        with self.assertRaisesRegex(
            ReasoningLedgerProvenanceError,
            "generation receipt differs",
        ):
            _verify_embedding_provenance(pack, snapshot)

    def test_live_export_rejects_unsupported_project_contract_before_database_access(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_root = Path(temp)
            config_path = project_root / "config" / "reasoning_ledger.json"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                json.dumps(
                    {
                        "project_id": "11" * 16,
                        "ledger": {
                            "backend": "postgresql_pgvector",
                            "dsn_env": "UNSET_TEST_LEDGER_DSN",
                            "schema": "reasoning_ledger",
                            "artifact_root": ".aegis/reasoning_ledger/artifacts",
                            "embedding_dimensions": 3,
                            "authority_schema_version": 1,
                            "project_anchor_sha256": None,
                            "approximate_vector_index": False,
                            "minimum_postgresql_major": 16,
                            "minimum_pgvector_version": "0.8.0",
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ReasoningLedgerProvenanceError,
                "configuration is invalid",
            ):
                export_live_reasoning_ledger_snapshot(
                    project_root,
                    project_id_hex="11" * 16,
                )

    def test_pack_authority_rows_and_hash_must_come_from_live_snapshot(self) -> None:
        revision = {
            "statement_id": "fact-1",
            "revision": 1,
            "content": "A",
            "evidence_ids": ["evidence-1"],
        }
        evidence = {"evidence_id": "evidence-1", "sha256": "aa" * 32}
        snapshot = {
            "schema": "aegis.reasoning_ledger.snapshot.v5",
            "project_id": "11" * 16,
            "database_contract": self._database_contract(),
            "statements": [{"statement_id": "fact-1"}],
            "revisions": [revision],
            "evidence_descriptors": [evidence],
            "relations": [],
            "events": [{"event_id": 7}],
            "current_projection": [{"statement_id": "fact-1", "revision": 1}],
            "embedding_profiles": [],
            "embedding_index": [],
        }
        encoded = json.dumps(
            snapshot,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        pack = {
            "ledger": {
                "revision": 7,
                "snapshot_sha256": hashlib.sha256(encoded).hexdigest(),
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
            "evidence_descriptors": [evidence],
            "retrieval": {
                "mode": "lexical_exact",
                "embedding_source": "none",
                "include_causes": True,
                "trace": {
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
                },
            },
        }
        proof = verify_context_pack_against_live_snapshot(pack, snapshot)
        self.assertEqual(proof.encoded, encoded)

        forged = json.loads(json.dumps(pack))
        forged["candidates"][0]["revision"]["content"] = "forged"
        with self.assertRaisesRegex(
            ReasoningLedgerProvenanceError, "absent or differs"
        ):
            verify_context_pack_against_live_snapshot(forged, snapshot)

        bad_database = json.loads(json.dumps(snapshot))
        bad_database["database_contract"]["pgvector_version"] = "0.7.4"
        with self.assertRaisesRegex(
            ReasoningLedgerProvenanceError,
            "database contract",
        ):
            verify_context_pack_against_live_snapshot(pack, bad_database)

        bad_anchor = json.loads(json.dumps(snapshot))
        bad_anchor["database_contract"]["project_anchor"]["database_oid"] += 1
        with self.assertRaisesRegex(
            ReasoningLedgerProvenanceError,
            "project anchor",
        ):
            verify_context_pack_against_live_snapshot(pack, bad_anchor)

    def test_pack_cannot_omit_reachable_causal_revision(self) -> None:
        evidence = {"evidence_id": "evidence-1", "sha256": "aa" * 32}
        cause = {
            "statement_id": "fact-cause",
            "revision": 1,
            "content": "cause",
            "evidence_ids": ["evidence-1"],
        }
        effect = {
            "statement_id": "claim-effect",
            "revision": 1,
            "content": "effect",
            "evidence_ids": ["evidence-1"],
        }
        relation = {
            "relation_id": "relation-cause-effect",
            "from_statement_id": "fact-cause",
            "from_revision": 1,
            "to_statement_id": "claim-effect",
            "to_revision": 1,
            "relation_type": "CAUSES",
            "evidence_ids": ["evidence-1"],
        }
        snapshot = {
            "schema": "aegis.reasoning_ledger.snapshot.v5",
            "project_id": "11" * 16,
            "database_contract": self._database_contract(),
            "statements": [],
            "revisions": [cause, effect],
            "evidence_descriptors": [evidence],
            "relations": [relation],
            "events": [{"event_id": 1}],
            "current_projection": [],
            "embedding_profiles": [],
            "embedding_index": [],
        }
        encoded = json.dumps(
            snapshot,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        pack = {
            "ledger": {
                "revision": 1,
                "snapshot_sha256": hashlib.sha256(encoded).hexdigest(),
            },
            "candidates": [
                {
                    "revision": effect,
                    "sources": ["LEXICAL"],
                    "lexical_rank": 1.0,
                    "semantic_distance": None,
                }
            ],
            "causal_revisions": [],
            "relations": [],
            "conflicts": [],
            "evidence_descriptors": [evidence],
            "retrieval": {
                "mode": "lexical_exact",
                "embedding_source": "none",
                "include_causes": True,
                "trace": {
                    "semantic_candidates": [],
                    "embedding_profile_id": None,
                    "embedding_query_receipt": None,
                    "causal_relations": ["CAUSES"],
                    "max_causal_depth": 8,
                },
            },
        }
        with self.assertRaisesRegex(
            ReasoningLedgerProvenanceError,
            "omits or invents",
        ):
            verify_context_pack_against_live_snapshot(pack, snapshot)

    @staticmethod
    def _database_contract() -> dict[str, object]:
        anchor = {
            "schema": "aegis.reasoning_ledger.project_anchor.v1",
            "project_id": "11" * 16,
            "cluster_system_identifier": "123456789",
            "database_oid": 16384,
            "database_name": "aegis",
            "schema_name": "reasoning_ledger",
        }
        anchor_sha256 = hashlib.sha256(
            json.dumps(
                anchor,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return {
            "database": "aegis",
            "user": "aegis",
            "postgresql_major": 16,
            "postgresql_version_num": 160004,
            "pgvector_version": "0.8.0",
            "pgvector_schema": "public",
            "schema": "reasoning_ledger",
            "schema_version": 3,
            "embedding_dimensions": 3,
            "schema_contract_signature": authority_schema_signature(
                schema="reasoning_ledger",
                embedding_dimensions=3,
            ),
            "catalog_signature": "cd" * 32,
            "project_anchor": {
                **anchor,
                "anchor_sha256": anchor_sha256,
                "created_at": "2026-08-20T00:00:00Z",
            },
        }


if __name__ == "__main__":
    unittest.main()
