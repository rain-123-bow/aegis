from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegis_test_runtime.real_workers import (
    RealTestWorkerError,
    audit_test_worker_outputs,
    audit_test_worker_proofs,
    build_test_worker_creation_requests,
    expected_workers_from_creation_requests,
    load_test_worker_policy,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _validation_package(tmp_path: Path) -> dict:
    return {
        "run_id": "phase20b-test-run",
        "status": "accepted_test_handoff_validation_closure",
        "test_result": "passed",
        "target_repo": str(tmp_path / "sandbox"),
        "integration_branch": "aegis/phase19b/integration-001",
        "integration_commit": "a" * 40,
        "changed_files": ["tests/test_example.py"],
        "test_routes": [
            {
                "route_id": "route.sandbox_pytest",
                "route_type": "command",
                "mandatory": True,
                "scope": ["tests/test_example.py"],
                "method": "local_pytest",
                "commands": ["pytest"],
                "expected_result": "passed",
            }
        ],
    }


def test_test_worker_profile_is_gpt_5_5_high_and_not_deferred():
    policy_path = REPO_ROOT / "MODEL_REASONING_BUDGET_POLICY.yaml"
    profile = load_test_worker_policy(policy_path)
    assert profile.model == "gpt-5.5"
    assert profile.reasoning_budget == "high"
    assert profile.fallback_allowed is False
    assert profile.dynamic_adjustment_allowed is False
    assert "  - test_worker" not in policy_path.read_text(encoding="utf-8")


def test_prepare_requests_creates_one_test_worker_per_route(tmp_path: Path):
    requests = build_test_worker_creation_requests(
        policy_path=REPO_ROOT / "MODEL_REASONING_BUDGET_POLICY.yaml",
        validation_package=_validation_package(tmp_path),
        run_id="phase20b-test-run",
        proof_dir=tmp_path / "proofs",
        output_dir=tmp_path / "outputs",
    )
    assert len(requests) == 1
    request = requests[0]
    assert request.role_id == "test_worker"
    assert request.parent_agent_id == "test_leader"
    assert request.scope == "test_route_local_domain"
    assert request.model == "gpt-5.5"
    assert request.reasoning_budget == "high"
    assert request.route_id == "route.sandbox_pytest"


def test_strict_test_worker_proof_audit_fails_when_missing(tmp_path: Path):
    requests = build_test_worker_creation_requests(
        policy_path=REPO_ROOT / "MODEL_REASONING_BUDGET_POLICY.yaml",
        validation_package=_validation_package(tmp_path),
        run_id="phase20b-test-run",
        proof_dir=tmp_path / "proofs",
        output_dir=tmp_path / "outputs",
    )
    expected = expected_workers_from_creation_requests(requests)
    (tmp_path / "proofs").mkdir()
    with pytest.raises(RealTestWorkerError):
        audit_test_worker_proofs(proof_dir=tmp_path / "proofs", expected_workers=expected)


def test_strict_test_worker_output_audit_rejects_completed_status(tmp_path: Path):
    requests = build_test_worker_creation_requests(
        policy_path=REPO_ROOT / "MODEL_REASONING_BUDGET_POLICY.yaml",
        validation_package=_validation_package(tmp_path),
        run_id="phase20b-test-run",
        proof_dir=tmp_path / "proofs",
        output_dir=tmp_path / "outputs",
    )
    expected = expected_workers_from_creation_requests(requests)
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    item = expected[0]
    output = _valid_output(item)
    output["status"] = "completed"
    Path(item["output_path"]).write_text(json.dumps(output), encoding="utf-8")
    with pytest.raises(RealTestWorkerError, match="status"):
        audit_test_worker_outputs(output_dir=output_dir, expected_workers=expected)


def test_strict_test_worker_proof_and_output_audit_accepts_complete_material(tmp_path: Path):
    requests = build_test_worker_creation_requests(
        policy_path=REPO_ROOT / "MODEL_REASONING_BUDGET_POLICY.yaml",
        validation_package=_validation_package(tmp_path),
        run_id="phase20b-test-run",
        proof_dir=tmp_path / "proofs",
        output_dir=tmp_path / "outputs",
    )
    expected = expected_workers_from_creation_requests(requests)
    proof_dir = tmp_path / "proofs"
    output_dir = tmp_path / "outputs"
    proof_dir.mkdir()
    output_dir.mkdir()
    for item in expected:
        Path(item["proof_path"]).write_text(json.dumps(_valid_proof(item)), encoding="utf-8")
        Path(item["output_path"]).write_text(json.dumps(_valid_output(item)), encoding="utf-8")

    proof_summary = audit_test_worker_proofs(proof_dir=proof_dir, expected_workers=expected)
    output_summary = audit_test_worker_outputs(output_dir=output_dir, expected_workers=expected)

    assert proof_summary["status"] == "passed"
    assert proof_summary["audited_count"] == 1
    assert output_summary["status"] == "passed"
    assert output_summary["audited_count"] == 1


def _valid_proof(item: dict) -> dict:
    return {
        "agent_id": item["agent_id"],
        "role_id": "test_worker",
        "created_by": "test_leader",
        "creation_mechanism": "real nested-codex MCP mcp__nested_codex__.codex call",
        "requested_model": "gpt-5.5",
        "policy_model": "gpt-5.5",
        "requested_reasoning_effort": "high",
        "policy_reasoning_budget": "high",
        "topology_scope": "test_route_local_domain",
        "run_id": "phase20b-test-run",
        "route_id": item["route_id"],
        "created_at_utc": "2026-05-11T00:00:00Z",
        "proof_statement": "real Test Worker proof",
    }


def _valid_output(item: dict) -> dict:
    return {
        "agent_id": item["agent_id"],
        "role_id": "test_worker",
        "run_id": "phase20b-test-run",
        "route_id": item["route_id"],
        "route_result": "passed",
        "command_evidence": [{"command": "pytest", "exit_code": 0, "stdout_ref": "stdout.txt", "stderr_ref": "stderr.txt"}],
        "observations": ["pytest passed"],
        "evidence_refs": ["stdout.txt"],
        "test_data_refs": ["worker_report.json"],
        "covered_scope": ["tests/test_example.py"],
        "uncovered_scope": [],
        "owner_hint": {"owner_type": "none"},
        "status": "test_worker_report_candidate",
        "causal_status": "scoped_evidence_candidate",
    }
