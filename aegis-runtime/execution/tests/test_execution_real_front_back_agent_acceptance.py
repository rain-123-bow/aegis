from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegis_execution_runtime.real_agents import (
    RealExecutionAgentError,
    audit_execution_agent_outputs,
    audit_execution_agent_proofs,
    build_execution_agent_creation_requests,
    expected_agents_from_creation_requests,
    load_execution_agent_policies,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def _execution_package(tmp_path: Path) -> dict:
    return {
        "run_id": "phase19b-test-run",
        "status": "accepted_execution_git_topology_closure",
        "target_repo": str(tmp_path / "sandbox"),
        "integration_branch": "aegis/phase19a/integration",
        "integration_commit": "a" * 40,
        "group_records": [
            {
                "group_id": "G1",
                "subtask_id": "docs",
                "branch_name": "aegis/G1",
                "commit_sha": "b" * 40,
                "touched_files": ["docs/a.md"],
                "responsibility": "docs update",
            },
            {
                "group_id": "G2",
                "subtask_id": "tests",
                "branch_name": "aegis/G2",
                "commit_sha": "c" * 40,
                "touched_files": ["tests/test_a.py"],
                "responsibility": "test update",
            },
        ],
    }


def test_execution_front_back_profiles_are_gpt_5_5_high_and_not_deferred():
    policy_path = REPO_ROOT / "MODEL_REASONING_BUDGET_POLICY.yaml"
    profiles = load_execution_agent_policies(policy_path)

    assert profiles["execution_front_agent"].model == "gpt-5.5"
    assert profiles["execution_front_agent"].reasoning_budget == "high"
    assert profiles["execution_front_agent"].fallback_allowed is False
    assert profiles["execution_back_agent"].model == "gpt-5.5"
    assert profiles["execution_back_agent"].reasoning_budget == "high"
    assert profiles["execution_back_agent"].fallback_allowed is False

    text = policy_path.read_text(encoding="utf-8")
    assert "  - execution_front_agent" not in text
    assert "  - execution_back_agent" not in text


def test_prepare_requests_creates_one_front_and_one_back_per_group(tmp_path: Path):
    requests = build_execution_agent_creation_requests(
        policy_path=REPO_ROOT / "MODEL_REASONING_BUDGET_POLICY.yaml",
        execution_package=_execution_package(tmp_path),
        run_id="phase19b-test-run",
        proof_dir=tmp_path / "proofs",
        output_dir=tmp_path / "outputs",
    )

    assert len(requests) == 4
    roles = [item.role_id for item in requests]
    assert roles.count("execution_front_agent") == 2
    assert roles.count("execution_back_agent") == 2

    for item in requests:
        assert item.parent_agent_id == "execution_leader"
        assert item.scope == "execution_group_local_domain"
        assert item.model == "gpt-5.5"
        assert item.reasoning_budget == "high"
        assert "Master" not in item.parent_agent_id


def test_strict_real_execution_agent_proof_audit_fails_when_missing(tmp_path: Path):
    requests = build_execution_agent_creation_requests(
        policy_path=REPO_ROOT / "MODEL_REASONING_BUDGET_POLICY.yaml",
        execution_package=_execution_package(tmp_path),
        run_id="phase19b-test-run",
        proof_dir=tmp_path / "proofs",
        output_dir=tmp_path / "outputs",
    )
    expected = expected_agents_from_creation_requests(requests)
    (tmp_path / "proofs").mkdir()

    with pytest.raises(RealExecutionAgentError):
        audit_execution_agent_proofs(proof_dir=tmp_path / "proofs", expected_agents=expected)


def _expected_agents(tmp_path: Path) -> list[dict]:
    requests = build_execution_agent_creation_requests(
        policy_path=REPO_ROOT / "MODEL_REASONING_BUDGET_POLICY.yaml",
        execution_package=_execution_package(tmp_path),
        run_id="phase19b-test-run",
        proof_dir=tmp_path / "proofs",
        output_dir=tmp_path / "outputs",
    )
    return expected_agents_from_creation_requests(requests)


def _front_output(item: dict, *, status: str = "front_output_candidate") -> dict:
    return {
        "agent_id": item["agent_id"],
        "role_id": item["role_id"],
        "group_id": item["group_id"],
        "subtask_id": item["subtask_id"],
        "implementation_summary": "implemented group task",
        "touched_files": ["x.py"],
        "local_test_evidence": [{"command": "pytest", "result": "pass", "evidence_ref": "local"}],
        "group_causal_fork": {
            "statement": "group changed x",
            "why": "assigned task",
            "evidence": ["local"],
            "scope": item["group_id"],
            "assumptions": ["sandbox"],
            "status": "causal_candidate",
        },
        "known_limits": ["test material"],
        "status": status,
    }


def _back_output(item: dict, *, status: str = "review_candidate") -> dict:
    return {
        "agent_id": item["agent_id"],
        "role_id": item["role_id"],
        "group_id": item["group_id"],
        "subtask_id": item["subtask_id"],
        "reviewed_front_agent_id": f"execution_front__phase19b-test-run__{item['group_id']}",
        "review_decision": "accept",
        "review_summary": "reviewed evidence",
        "blocking_objections": [],
        "evidence_checked": ["local"],
        "risk_notes": [],
        "status": status,
    }


def _write_complete_outputs(expected: list[dict], *, front_status: str = "front_output_candidate", back_status: str = "review_candidate") -> None:
    for item in expected:
        output = _front_output(item, status=front_status) if item["role_id"] == "execution_front_agent" else _back_output(item, status=back_status)
        Path(item["output_path"]).write_text(json.dumps(output), encoding="utf-8")


def test_strict_output_audit_rejects_front_completed_status(tmp_path: Path):
    expected = _expected_agents(tmp_path)
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    _write_complete_outputs(expected, front_status="completed")

    with pytest.raises(RealExecutionAgentError, match="front output status"):
        audit_execution_agent_outputs(output_dir=output_dir, expected_agents=expected)


def test_strict_output_audit_rejects_back_completed_status(tmp_path: Path):
    expected = _expected_agents(tmp_path)
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    _write_complete_outputs(expected, back_status="completed")

    with pytest.raises(RealExecutionAgentError, match="back review status"):
        audit_execution_agent_outputs(output_dir=output_dir, expected_agents=expected)


def test_strict_real_execution_agent_proof_and_output_audit_accepts_complete_material(tmp_path: Path):
    requests = build_execution_agent_creation_requests(
        policy_path=REPO_ROOT / "MODEL_REASONING_BUDGET_POLICY.yaml",
        execution_package=_execution_package(tmp_path),
        run_id="phase19b-test-run",
        proof_dir=tmp_path / "proofs",
        output_dir=tmp_path / "outputs",
    )
    expected = expected_agents_from_creation_requests(requests)
    proof_dir = tmp_path / "proofs"
    output_dir = tmp_path / "outputs"
    proof_dir.mkdir()
    output_dir.mkdir()

    for item in expected:
        proof = {
            "agent_id": item["agent_id"],
            "role_id": item["role_id"],
            "created_by": "execution_leader",
            "creation_mechanism": "real nested-codex MCP mcp__nested_codex__.codex call",
            "requested_model": "gpt-5.5",
            "policy_model": "gpt-5.5",
            "requested_reasoning_effort": "high",
            "policy_reasoning_budget": "high",
            "topology_scope": "execution_group_local_domain",
            "run_id": "phase19b-test-run",
            "group_id": item["group_id"],
            "subtask_id": item["subtask_id"],
            "created_at_utc": "2026-05-07T00:00:00Z",
            "proof_statement": "real execution agent proof",
        }
        Path(item["proof_path"]).write_text(json.dumps(proof), encoding="utf-8")

        if item["role_id"] == "execution_front_agent":
            output = {
                "agent_id": item["agent_id"],
                "role_id": item["role_id"],
                "group_id": item["group_id"],
                "subtask_id": item["subtask_id"],
                "implementation_summary": "implemented group task",
                "touched_files": ["x.py"],
                "local_test_evidence": [{"command": "pytest", "result": "pass", "evidence_ref": "local"}],
                "group_causal_fork": {
                    "statement": "group changed x",
                    "why": "assigned task",
                    "evidence": ["local"],
                    "scope": item["group_id"],
                    "assumptions": ["sandbox"],
                    "status": "causal_candidate",
                },
                "known_limits": ["test material"],
                "status": "front_output_candidate",
            }
        else:
            output = {
                "agent_id": item["agent_id"],
                "role_id": item["role_id"],
                "group_id": item["group_id"],
                "subtask_id": item["subtask_id"],
                "reviewed_front_agent_id": f"execution_front__phase19b-test-run__{item['group_id']}",
                "review_decision": "accept",
                "review_summary": "reviewed evidence",
                "blocking_objections": [],
                "evidence_checked": ["local"],
                "risk_notes": [],
                "status": "review_candidate",
            }
        Path(item["output_path"]).write_text(json.dumps(output), encoding="utf-8")

    proof_summary = audit_execution_agent_proofs(proof_dir=proof_dir, expected_agents=expected)
    output_summary = audit_execution_agent_outputs(output_dir=output_dir, expected_agents=expected)

    assert proof_summary["status"] == "passed"
    assert proof_summary["audited_count"] == 4
    assert output_summary["status"] == "passed"
    assert output_summary["audited_count"] == 4
