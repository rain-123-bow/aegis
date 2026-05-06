from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest


DEFAULT_PROOF_DIR = Path(r"C:\Users\playm\Downloads\agents_test")

EXPECTED_PROOFS = {
    "debate_leader_proof.json": {
        "agent_id": "debate",
        "role_id": "debate_leader",
        "policy_reasoning_budget": "high",
        "requested_reasoning_effort": "high",
    },
    "execution_leader_proof.json": {
        "agent_id": "execution",
        "role_id": "execution_leader",
        "policy_reasoning_budget": "high",
        "requested_reasoning_effort": "high",
    },
    "test_leader_proof.json": {
        "agent_id": "test",
        "role_id": "test_leader",
        "policy_reasoning_budget": "high",
        "requested_reasoning_effort": "high",
    },
    "final_review_leader_proof.json": {
        "agent_id": "final_review",
        "role_id": "final_review_leader",
        "policy_reasoning_budget": "extra_high",
        "requested_reasoning_effort": "xhigh",
    },
}


def _proof_dir() -> Path:
    return Path(os.environ.get("AEGIS_NESTED_CODEX_AGENT_PROOF_DIR", str(DEFAULT_PROOF_DIR)))


def test_real_nested_codex_top_level_agent_proofs_are_auditable():
    proof_dir = _proof_dir()
    if not proof_dir.is_dir():
        pytest.skip(f"nested-codex proof directory does not exist: {proof_dir}")

    hashes: dict[str, str] = {}
    for file_name, expected in EXPECTED_PROOFS.items():
        proof_path = proof_dir / file_name
        assert proof_path.is_file(), f"missing proof file: {proof_path}"

        file_bytes = proof_path.read_bytes()
        hashes[file_name] = hashlib.sha256(file_bytes).hexdigest()
        proof = json.loads(file_bytes.decode("utf-8"))

        assert proof["agent_id"] == expected["agent_id"]
        assert proof["role_id"] == expected["role_id"]
        assert proof["created_by"] == "master"

        mechanism = proof.get("creation_mechanism", "")
        assert "real nested-codex MCP" in mechanism or "mcp__nested_codex__.codex" in mechanism

        assert proof["requested_model"] == "gpt-5.5"
        assert proof["policy_model"] == "gpt-5.5"
        assert proof["requested_model"] == proof["policy_model"]
        assert proof["topology_scope"] == "top_level_master_domain"
        assert proof["policy_reasoning_budget"] == expected["policy_reasoning_budget"]
        assert proof["requested_reasoning_effort"] == expected["requested_reasoning_effort"]

        if expected["agent_id"] == "final_review":
            assert proof["requested_reasoning_effort"] == "xhigh"
            assert proof["policy_reasoning_budget"] == "extra_high"
            assert "extra_high" in proof.get("reasoning_budget_mapping_note", "")

        assert isinstance(proof.get("proof_statement"), str) and proof["proof_statement"].strip()
        timestamp = proof.get("created_at_utc") or proof.get("timestamp")
        assert isinstance(timestamp, str) and timestamp.strip()

    assert set(hashes) == set(EXPECTED_PROOFS)
    print(json.dumps(hashes, indent=2, sort_keys=True))
