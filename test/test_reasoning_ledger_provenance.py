from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from reasoning_ledger_provenance import (
    ReasoningLedgerProvenanceError,
    verify_context_pack_against_live_snapshot,
)


class ReasoningLedgerProvenanceTests(unittest.TestCase):
    def test_pack_items_and_hash_must_come_from_live_snapshot(self) -> None:
        item = {"id": "fact-1", "content": "A"}
        snapshot = {"items": [item], "edges": [], "events": [{"id": 7}]}
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
            "items": [item],
            "cause_items": [],
            "edges": [],
        }
        proof = verify_context_pack_against_live_snapshot(pack, snapshot)
        self.assertEqual(proof.encoded, encoded)

        forged = json.loads(json.dumps(pack))
        forged["items"][0]["content"] = "forged"
        with self.assertRaisesRegex(
            ReasoningLedgerProvenanceError, "absent or differs"
        ):
            verify_context_pack_against_live_snapshot(forged, snapshot)


if __name__ == "__main__":
    unittest.main()
