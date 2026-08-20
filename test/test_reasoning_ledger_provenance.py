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
    export_live_reasoning_ledger_snapshot,
    verify_context_pack_against_live_snapshot,
)


class ReasoningLedgerProvenanceTests(unittest.TestCase):
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
        revision = {"statement_id": "fact-1", "revision": 1, "content": "A"}
        evidence = {"evidence_id": "evidence-1", "sha256": "aa" * 32}
        relation = {"relation_id": "relation-1", "reason": "evidence supports A"}
        snapshot = {
            "schema": "aegis.reasoning_ledger.snapshot.v2",
            "project_id": "11" * 16,
            "statements": [{"statement_id": "fact-1"}],
            "revisions": [revision],
            "evidence_descriptors": [evidence],
            "relations": [relation],
            "events": [{"event_id": 7}],
            "current_projection": [{"statement_id": "fact-1", "revision": 1}],
            "embedding_profiles": [],
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
            "relations": [relation],
            "conflicts": [],
            "evidence_descriptors": [evidence],
        }
        proof = verify_context_pack_against_live_snapshot(pack, snapshot)
        self.assertEqual(proof.encoded, encoded)

        forged = json.loads(json.dumps(pack))
        forged["candidates"][0]["revision"]["content"] = "forged"
        with self.assertRaisesRegex(
            ReasoningLedgerProvenanceError, "absent or differs"
        ):
            verify_context_pack_against_live_snapshot(forged, snapshot)


if __name__ == "__main__":
    unittest.main()
