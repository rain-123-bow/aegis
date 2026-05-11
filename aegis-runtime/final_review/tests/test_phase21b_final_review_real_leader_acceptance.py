from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegis_final_review_runtime.real_leader import (
    ACCEPTANCE_STATUS,
    RealFinalReviewLeaderError,
    audit_final_review_leader_output,
    audit_final_review_leader_proof,
    build_final_review_leader_creation_request,
    expected_final_review_leader_from_creation_request,
    load_final_review_leader_policy,
    write_json,
)


def _policy_text(*, model: str = "gpt-5.5", reasoning_budget: str = "extra_high", fallback: str = "false") -> str:
    return f"""
policy_id: model_reasoning_budget_policy
version: v0.1
profiles:
  final_review_leader:
    role_id: final_review_leader
    model: {model}
    reasoning_budget: {reasoning_budget}
    fallback_allowed: {fallback}
    dynamic_adjustment_allowed: false
deferred_profiles: []
""".lstrip()


def _phase21a_summary() -> dict:
    return {
        "acceptance_status": "accepted_final_review_handoff_validation_closure",
        "phase_boundary": "final_review_handoff_validation_not_real_final_review_leader",
        "handoff_kind": "test_real_worker_result",
        "source_status": "ready_for_final_review",
        "request_id": "phase21a-final-review-handoff-validation-001",
        "decision": "accept_for_master_with_scope_limit",
        "target": "master",
        "output_route": "final_review -> master",
        "real_final_review_leader_created": False,
        "final_review_worker_created": False,
        "production_final_review_lifecycle_closure": False,
        "production_release_review_closure": False,
        "global_causal_truth_mutation": False,
    }


def _phase21a_result() -> dict:
    return {
        "final_review_result_id": "final-review-result-phase21a",
        "request_id": "phase21a-final-review-handoff-validation-001",
        "decision": "accept_for_master_with_scope_limit",
        "target": "master",
        "why": "Phase 21A handoff is reviewable with explicit scope limits.",
        "final_code_ref": "sandbox:aegis/phase19b/integration-001@386c2f5",
        "implementation_candidate_ref": "sandbox:aegis/phase19b/integration-001@386c2f5",
        "tested_candidate_ref": "sandbox:aegis/phase19b/integration-001@386c2f5",
        "reviewed_refs": {
            "execution_final_report_ref": "phase19b:final_execution_candidate.json",
            "execution_causal_chain_ref": "phase19b:execution_causal_chain.json",
            "test_final_report_ref": "phase20b:final_test_result_phase20b.json",
            "test_plan_ref": "phase20b:validation_package.json",
            "test_route_report_refs": ["phase20b:route.sandbox_pytest", "phase20b:route.changed_files_scope"],
            "test_evidence_refs": ["phase20b:test_worker_proof_audit_summary.json"],
            "reproducibility_set_ref": "phase20b:reproducibility_set",
            "artifact_manifest_ref": "phase20b:artifact_manifest",
            "debate_refs": [],
        },
        "accepted_scope": ["Phase 20B passed routes only"],
        "blocked_scope": ["production Test lifecycle"],
        "known_limits": ["This is real Test Worker closure, not production Test lifecycle closure."],
        "missing_evidence": [],
        "governance_blockers": [],
        "resource_policy": {
            "policy_ref": "MODEL_REASONING_BUDGET_POLICY.yaml",
            "required_profile": "final_review_leader",
            "resolved_profile": "final_review_leader",
            "reasoning_budget": "maximum",
            "fallback_used": False,
            "status": "satisfied",
        },
        "causal_boundary": "Final Review output is a recommendation to Master; it is not global causal truth.",
        "recommended_master_action": "Proceed to Phase 21B real Final Review Leader acceptance.",
        "status": "final_review_recommendation",
        "created_at": "2026-05-11T00:00:00+00:00",
    }


def _proof_for(expected: dict) -> dict:
    return {
        "agent_id": expected["agent_id"],
        "role_id": "final_review_leader",
        "created_by": "master",
        "creation_mechanism": "mcp__nested_codex__.codex",
        "requested_model": "gpt-5.5",
        "policy_model": "gpt-5.5",
        "requested_reasoning_effort": "extra_high",
        "policy_reasoning_budget": "extra_high",
        "topology_scope": "top_level_master_domain",
        "run_id": expected["run_id"],
        "created_at_utc": "2026-05-11T00:00:00Z",
        "proof_statement": "Master created exactly one real Final Review Leader for Phase 21B.",
    }


def _output_for(expected: dict) -> dict:
    result = _phase21a_result()
    return {
        "agent_id": expected["agent_id"],
        "role_id": "final_review_leader",
        "run_id": expected["run_id"],
        "source_phase": "phase21a_final_review_handoff_validation",
        "phase21a_summary_ref": "phase21a_handoff_validation_summary.json",
        "phase21a_result_ref": "phase21a_final_review_result.json",
        "final_review_result": result,
        "final_decision": result["decision"],
        "output_route": "final_review -> master",
        "reviewed_refs": result["reviewed_refs"],
        "evidence_refs": ["phase21a_handoff_validation_summary.json", "phase21a_final_review_result.json"],
        "recommendation_scope": result["accepted_scope"],
        "known_limits": result["known_limits"],
        "blocked_scope": result["blocked_scope"],
        "status": "final_review_leader_report_candidate",
        "causal_status": "final_review_recommendation_candidate",
        "real_final_review_leader_created": True,
        "final_review_worker_created": False,
        "production_final_review_lifecycle_closure": False,
        "production_release_review_closure": False,
        "remote_push_performed": False,
        "pr_created": False,
        "production_merge_performed": False,
        "release_performed": False,
        "production_signoff_performed": False,
        "global_causal_truth_mutation": False,
    }


def test_load_final_review_leader_policy_requires_extra_high(tmp_path: Path) -> None:
    policy = tmp_path / "MODEL_REASONING_BUDGET_POLICY.yaml"
    policy.write_text(_policy_text(), encoding="utf-8")

    profile = load_final_review_leader_policy(policy)

    assert profile.role_id == "final_review_leader"
    assert profile.model == "gpt-5.5"
    assert profile.reasoning_budget == "extra_high"
    assert profile.fallback_allowed is False


@pytest.mark.parametrize(
    "policy_text,error_fragment",
    [
        (_policy_text(model="gpt-5.4"), "model"),
        (_policy_text(reasoning_budget="high"), "reasoning_budget"),
        (_policy_text(fallback="true"), "fallback"),
    ],
)
def test_load_final_review_leader_policy_rejects_downgrade(tmp_path: Path, policy_text: str, error_fragment: str) -> None:
    policy = tmp_path / "MODEL_REASONING_BUDGET_POLICY.yaml"
    policy.write_text(policy_text, encoding="utf-8")

    with pytest.raises(RealFinalReviewLeaderError, match=error_fragment):
        load_final_review_leader_policy(policy)


def test_build_final_review_leader_creation_request(tmp_path: Path) -> None:
    policy = tmp_path / "MODEL_REASONING_BUDGET_POLICY.yaml"
    policy.write_text(_policy_text(), encoding="utf-8")

    request = build_final_review_leader_creation_request(
        policy_path=policy,
        phase21a_summary=_phase21a_summary(),
        phase21a_result=_phase21a_result(),
        run_id="phase21b-final-review-real-leader-001",
        proof_dir=tmp_path / "proofs",
        output_dir=tmp_path / "outputs",
    )

    assert request.agent_id == "final_review_leader__phase21b-final-review-real-leader-001"
    assert request.role_id == "final_review_leader"
    assert request.parent_agent_id == "master"
    assert request.scope == "top_level_master_domain"
    assert request.model == "gpt-5.5"
    assert request.reasoning_budget == "extra_high"
    assert "Do not create Final Review Workers" in request.instructions
    expected = expected_final_review_leader_from_creation_request(request)
    assert len(expected) == 1
    assert expected[0]["role_id"] == "final_review_leader"


def test_build_request_rejects_invalid_phase21a_summary(tmp_path: Path) -> None:
    policy = tmp_path / "MODEL_REASONING_BUDGET_POLICY.yaml"
    policy.write_text(_policy_text(), encoding="utf-8")
    summary = _phase21a_summary()
    summary["real_final_review_leader_created"] = True

    with pytest.raises(RealFinalReviewLeaderError, match="Phase 21A"):
        build_final_review_leader_creation_request(
            policy_path=policy,
            phase21a_summary=summary,
            phase21a_result=_phase21a_result(),
            run_id="phase21b-final-review-real-leader-001",
            proof_dir=tmp_path / "proofs",
            output_dir=tmp_path / "outputs",
        )


def test_audit_final_review_leader_proof_passes(tmp_path: Path) -> None:
    expected = [
        {
            "agent_id": "final_review_leader__phase21b",
            "role_id": "final_review_leader",
            "run_id": "phase21b",
            "policy_model": "gpt-5.5",
            "policy_reasoning_budget": "extra_high",
            "proof_path": str(tmp_path / "proofs" / "final_review_leader__phase21b_proof.json"),
            "output_path": str(tmp_path / "outputs" / "final_review_leader__phase21b_output.json"),
        }
    ]
    proof_dir = tmp_path / "proofs"
    proof_dir.mkdir()
    write_json(expected[0]["proof_path"], _proof_for(expected[0]))

    summary = audit_final_review_leader_proof(proof_dir=proof_dir, expected_leaders=expected)

    assert summary["status"] == "passed"
    assert summary["audited_count"] == 1


def test_audit_final_review_leader_proof_rejects_worker_creator(tmp_path: Path) -> None:
    expected = [
        {
            "agent_id": "final_review_leader__phase21b",
            "role_id": "final_review_leader",
            "run_id": "phase21b",
            "policy_model": "gpt-5.5",
            "policy_reasoning_budget": "extra_high",
            "proof_path": str(tmp_path / "proofs" / "final_review_leader__phase21b_proof.json"),
            "output_path": str(tmp_path / "outputs" / "final_review_leader__phase21b_output.json"),
        }
    ]
    proof_dir = tmp_path / "proofs"
    proof_dir.mkdir()
    proof = _proof_for(expected[0])
    proof["created_by"] = "final_review"
    write_json(expected[0]["proof_path"], proof)

    with pytest.raises(RealFinalReviewLeaderError, match="Master"):
        audit_final_review_leader_proof(proof_dir=proof_dir, expected_leaders=expected)


def test_audit_final_review_leader_output_passes(tmp_path: Path) -> None:
    expected = [
        {
            "agent_id": "final_review_leader__phase21b",
            "role_id": "final_review_leader",
            "run_id": "phase21b",
            "policy_model": "gpt-5.5",
            "policy_reasoning_budget": "extra_high",
            "proof_path": str(tmp_path / "proofs" / "final_review_leader__phase21b_proof.json"),
            "output_path": str(tmp_path / "outputs" / "final_review_leader__phase21b_output.json"),
        }
    ]
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    write_json(expected[0]["output_path"], _output_for(expected[0]))

    summary = audit_final_review_leader_output(output_dir=output_dir, expected_leaders=expected)

    assert summary["status"] == "passed"
    assert summary["audited_count"] == 1
    assert summary["leaders"][0]["decision"] == "accept_for_master_with_scope_limit"


@pytest.mark.parametrize(
    "mutate,error_fragment",
    [
        (lambda payload: payload.update({"final_review_worker_created": True}), "final_review_worker_created"),
        (lambda payload: payload.update({"global_causal_truth_mutation": True}), "global_causal_truth_mutation"),
        (lambda payload: payload.update({"output_route": "final_review -> execution"}), "route"),
        (lambda payload: payload["final_review_result"].update({"target": "execution"}), "target"),
        (lambda payload: payload["final_review_result"].update({"causal_boundary": "global causal truth"}), "causal boundary"),
    ],
)
def test_audit_final_review_leader_output_rejects_boundary_violations(
    tmp_path: Path, mutate, error_fragment: str
) -> None:
    expected = [
        {
            "agent_id": "final_review_leader__phase21b",
            "role_id": "final_review_leader",
            "run_id": "phase21b",
            "policy_model": "gpt-5.5",
            "policy_reasoning_budget": "extra_high",
            "proof_path": str(tmp_path / "proofs" / "final_review_leader__phase21b_proof.json"),
            "output_path": str(tmp_path / "outputs" / "final_review_leader__phase21b_output.json"),
        }
    ]
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    payload = _output_for(expected[0])
    mutate(payload)
    write_json(expected[0]["output_path"], payload)

    with pytest.raises(RealFinalReviewLeaderError, match=error_fragment):
        audit_final_review_leader_output(output_dir=output_dir, expected_leaders=expected)


def test_acceptance_status_constant() -> None:
    assert ACCEPTANCE_STATUS == "accepted_real_final_review_leader_closure"
