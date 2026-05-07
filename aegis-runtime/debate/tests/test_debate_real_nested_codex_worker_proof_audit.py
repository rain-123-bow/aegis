from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegis_debate_runtime.real_nested_codex import RealNestedCodexDebateWorkerError, audit_debate_worker_proofs


def _valid_worker_proof(worker_id: str = "debate_worker__run__S1", stance_id: str = "S1") -> dict[str, object]:
    return {
        "agent_id": worker_id,
        "worker_id": worker_id,
        "stance_id": stance_id,
        "role_id": "debate_worker",
        "created_by": "debate_leader",
        "creation_mechanism": "real nested-codex MCP call",
        "requested_model": "gpt-5.5",
        "policy_model": "gpt-5.5",
        "requested_reasoning_effort": "high",
        "policy_reasoning_budget": "high",
        "topology_scope": "debate_run_local_domain",
        "run_id": "run",
        "created_at_utc": "2026-05-06T00:00:00Z",
        "proof_statement": "I was created as a real stance-bound Debate Worker.",
        "worker_local_causal_state": {
            "stance_id": stance_id,
            "claim": "A",
            "why": "B",
            "route_priority": [{"id": "claim", "route_grade": "A", "reason": "core"}],
            "expand_priority": [{"id": "claim", "expand_grade": "A", "reason": "core"}],
        },
    }


def test_strict_real_worker_proof_audit_fails_when_proof_is_missing(tmp_path: Path):
    expected = [{"worker_id": "debate_worker__run__S1", "stance_id": "S1"}]

    with pytest.raises(RealNestedCodexDebateWorkerError, match="missing real Debate Worker proof"):
        audit_debate_worker_proofs(proof_dir=tmp_path, expected_workers=expected)


def test_strict_real_worker_proof_audit_accepts_complete_proof(tmp_path: Path):
    proof_path = tmp_path / "debate_worker__run__S1_proof.json"
    proof_path.write_text(json.dumps(_valid_worker_proof()), encoding="utf-8")

    summary = audit_debate_worker_proofs(
        proof_dir=tmp_path,
        expected_workers=[{"worker_id": "debate_worker__run__S1", "stance_id": "S1"}],
    )

    assert summary["status"] == "passed"
    assert summary["audited_count"] == 1
    assert summary["workers"][0]["sha256"]


def test_strict_real_worker_proof_audit_accepts_relative_proof_path_inside_proof_dir_without_double_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    proof_dir = tmp_path / "worker_proofs"
    proof_dir.mkdir()
    proof_path = proof_dir / "debate_worker__run__S1_proof.json"
    proof_path.write_text(json.dumps(_valid_worker_proof()), encoding="utf-8")

    expected = [
        {
            "worker_id": "debate_worker__run__S1",
            "stance_id": "S1",
            "proof_path": str(proof_path.relative_to(tmp_path)),
        }
    ]

    monkeypatch.chdir(tmp_path)
    summary = audit_debate_worker_proofs(proof_dir=Path("worker_proofs"), expected_workers=expected)

    assert summary["status"] == "passed"
    assert summary["audited_count"] == 1
    assert summary["workers"][0]["proof_path"] == str(Path("worker_proofs") / proof_path.name)


def test_strict_real_worker_proof_audit_accepts_simple_relative_proof_file_name_under_proof_dir(tmp_path: Path):
    proof_path = tmp_path / "debate_worker__run__S1_proof.json"
    proof_path.write_text(json.dumps(_valid_worker_proof()), encoding="utf-8")

    summary = audit_debate_worker_proofs(
        proof_dir=tmp_path,
        expected_workers=[
            {
                "worker_id": "debate_worker__run__S1",
                "stance_id": "S1",
                "proof_path": proof_path.name,
            }
        ],
    )

    assert summary["status"] == "passed"
    assert summary["audited_count"] == 1


def test_strict_real_worker_proof_audit_accepts_absolute_proof_path(tmp_path: Path):
    proof_path = tmp_path / "debate_worker__run__S1_proof.json"
    proof_path.write_text(json.dumps(_valid_worker_proof()), encoding="utf-8")
    proof_dir = tmp_path / "empty_proof_dir"
    proof_dir.mkdir()

    summary = audit_debate_worker_proofs(
        proof_dir=proof_dir,
        expected_workers=[
            {
                "worker_id": "debate_worker__run__S1",
                "stance_id": "S1",
                "proof_path": str(proof_path),
            }
        ],
    )

    assert summary["status"] == "passed"
    assert summary["audited_count"] == 1
