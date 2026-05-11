from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegis_final_review_runtime.phase21a_handoff import (
    ACCEPTANCE_STATUS,
    Phase21AHandoffValidationError,
    build_final_review_request_from_phase21a_handoff,
    run_phase21a_handoff_validation,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _canonical_phase20b_handoff() -> dict:
    return {
        "handoff_kind": "test_real_worker_result",
        "target": "final_review",
        "status": "ready_for_final_review",
        "request_id": "phase21a-final-review-handoff-validation-001",
        "final_test_result": {
            "result": "passed",
            "status": "scoped_test_conclusion",
            "causal_status": "causal_candidate",
            "next_route": "final_review",
        },
        "proof_audit_status": "passed",
        "output_audit_status": "passed",
        "route_results": {
            "route.sandbox_pytest": "passed",
            "route.changed_files_scope": "passed",
        },
        "integration_branch": "aegis/phase19b/integration-001",
        "integration_commit": "386c2f5e1cb54991f1c4f720fa96ed98fa3b3ec4",
        "final_code_ref": "sandbox:aegis/phase19b/integration-001@386c2f5e1cb54991f1c4f720fa96ed98fa3b3ec4",
        "implementation_candidate_ref": "sandbox:aegis/phase19b/integration-001@386c2f5e1cb54991f1c4f720fa96ed98fa3b3ec4",
        "tested_candidate_ref": "sandbox:aegis/phase19b/integration-001@386c2f5e1cb54991f1c4f720fa96ed98fa3b3ec4",
        "reviewed_refs": {
            "execution_final_report_ref": "phase19b:final_execution_candidate.json",
            "execution_causal_chain_ref": "phase19b:execution_causal_chain.json",
            "test_final_report_ref": "phase20b:final_test_result_phase20b.json",
            "test_plan_ref": "phase20b:validation_package.json",
            "test_route_report_refs": [
                "phase20b:route.sandbox_pytest",
                "phase20b:route.changed_files_scope",
            ],
            "test_evidence_refs": [
                "phase20b:test_worker_proof_audit_summary.json",
                "phase20b:test_worker_output_audit_summary.json",
                "phase20b:worker_work_evidence",
            ],
            "reproducibility_set_ref": "phase20b:reproducibility_set",
            "artifact_manifest_ref": "phase20b:artifact_manifest",
            "debate_refs": [],
        },
        "task_scope": ["Phase 19B/20B sandbox integration candidate"],
        "accepted_scope": ["routes route.sandbox_pytest and route.changed_files_scope passed"],
        "blocked_scope": [],
        "known_limits": [],
        "missing_evidence": [],
        "governance_blockers": [],
        "production_test_lifecycle_closure": False,
        "remote_push_performed": False,
        "pr_created": False,
        "production_merge_performed": False,
        "release_performed": False,
        "production_signoff_performed": False,
        "global_causal_truth_mutation": False,
    }


def test_phase21a_builds_final_review_request_from_phase20b_handoff() -> None:
    request = build_final_review_request_from_phase21a_handoff(_canonical_phase20b_handoff())

    assert request["request_id"] == "phase21a-final-review-handoff-validation-001"
    assert request["source"] == "test"
    assert request["resource_policy"]["required_profile"] == "final_review_leader"
    assert request["resource_policy"]["status"] == "satisfied"
    package = request["final_review_input_package"]
    assert package["final_code_ref"] == package["implementation_candidate_ref"] == package["tested_candidate_ref"]
    assert package["reviewed_refs"]["test_route_report_refs"] == [
        "phase20b:route.sandbox_pytest",
        "phase20b:route.changed_files_scope",
    ]


def test_phase21a_runs_handoff_validation_and_produces_master_recommendation(tmp_path: Path) -> None:
    handoff_path = _write_json(tmp_path / "final_review_handoff_package_phase20b.json", _canonical_phase20b_handoff())
    summary = run_phase21a_handoff_validation(handoff_path, tmp_path / "outputs")

    assert summary["acceptance_status"] == ACCEPTANCE_STATUS
    assert summary["phase_boundary"] == "final_review_handoff_validation_not_real_final_review_leader"
    assert summary["decision"] == "accept_for_master"
    assert summary["target"] == "master"
    assert summary["output_route"] == "final_review -> master"
    assert summary["real_final_review_leader_created"] is False
    assert summary["final_review_worker_created"] is False
    assert summary["production_final_review_lifecycle_closure"] is False
    assert summary["global_causal_truth_mutation"] is False

    result = json.loads(Path(summary["result_artifact"]).read_text(encoding="utf-8"))
    assert result["decision"] == "accept_for_master"
    assert result["status"] == "final_review_recommendation"
    assert result["causal_boundary"] == "Final Review output is a recommendation to Master; it is not global causal truth."
    assert result["known_limits"] == []
    assert result["missing_evidence"] == []


def test_phase21a_preserves_resource_policy_precedence(tmp_path: Path) -> None:
    handoff = _canonical_phase20b_handoff()
    handoff["resource_policy"] = {
        "policy_ref": "MODEL_REASONING_BUDGET_POLICY.yaml",
        "required_profile": "final_review_leader",
        "resolved_profile": "",
        "reasoning_budget": "unknown",
        "fallback_used": False,
        "status": "missing",
    }
    handoff_path = _write_json(tmp_path / "handoff.json", handoff)

    summary = run_phase21a_handoff_validation(handoff_path, tmp_path / "outputs")
    assert summary["acceptance_status"] == "blocked_resource_policy"
    assert summary["decision"] == "blocked_resource_policy"
    result = json.loads(Path(summary["result_artifact"]).read_text(encoding="utf-8"))
    assert result["decision"] == "blocked_resource_policy"
    assert result["target"] == "master"
    assert result["resource_policy"]["status"] == "missing"


@pytest.mark.parametrize(
    "field,value,error_fragment",
    [
        ("handoff_kind", "ordinary_test_result", "handoff_kind"),
        ("target", "execution", "target"),
        ("status", "draft", "status"),
        ("final_test_result", "failed", "final_test_result"),
        ("proof_audit_status", "failed", "proof_audit_status"),
        ("output_audit_status", "failed", "output_audit_status"),
        ("remote_push_performed", True, "remote_push_performed"),
        ("global_causal_truth_mutation", True, "global_causal_truth_mutation"),
    ],
)
def test_phase21a_rejects_invalid_handoff_gate(field: str, value: object, error_fragment: str) -> None:
    handoff = _canonical_phase20b_handoff()
    handoff[field] = value

    with pytest.raises(Phase21AHandoffValidationError, match=error_fragment):
        build_final_review_request_from_phase21a_handoff(handoff)


def test_phase21a_rejects_failed_route_result() -> None:
    handoff = _canonical_phase20b_handoff()
    handoff["route_results"]["route.changed_files_scope"] = "failed"

    with pytest.raises(Phase21AHandoffValidationError, match="route_results"):
        build_final_review_request_from_phase21a_handoff(handoff)


def test_phase21a_accepts_real_phase20b_list_route_results() -> None:
    handoff = _canonical_phase20b_handoff()
    handoff.pop("proof_audit_status")
    handoff.pop("output_audit_status")
    handoff.pop("reviewed_refs")
    handoff["route_results"] = [
        {
            "route_id": "route.sandbox_pytest",
            "worker_id": "test_worker__phase20b-test-real-workers-001__route_sandbox_pytest",
            "route_result": "passed",
        },
        {
            "route_id": "route.changed_files_scope",
            "worker_id": "test_worker__phase20b-test-real-workers-001__route_changed_files_scope",
            "route_result": "passed",
        },
    ]

    request = build_final_review_request_from_phase21a_handoff(handoff)

    assert request["final_review_input_package"]["reviewed_refs"]["test_route_report_refs"] == [
        "phase20b:route_result:route.changed_files_scope",
        "phase20b:route_result:route.sandbox_pytest",
    ]


def test_phase21a_accepts_embedded_final_review_request(tmp_path: Path) -> None:
    handoff = _canonical_phase20b_handoff()
    request = build_final_review_request_from_phase21a_handoff(handoff)
    handoff = {
        "handoff_kind": "test_real_worker_result",
        "target": "final_review",
        "status": "ready_for_final_review",
        "final_test_result": "passed",
        "proof_audit_status": "passed",
        "output_audit_status": "passed",
        "route_results": {"route.sandbox_pytest": "passed"},
        "remote_push_performed": False,
        "pr_created": False,
        "production_merge_performed": False,
        "release_performed": False,
        "production_signoff_performed": False,
        "global_causal_truth_mutation": False,
        "final_review_request": request,
    }
    handoff_path = _write_json(tmp_path / "embedded_request_handoff.json", handoff)

    summary = run_phase21a_handoff_validation(handoff_path, tmp_path / "outputs")
    assert summary["acceptance_status"] == ACCEPTANCE_STATUS
    assert summary["decision"] == "accept_for_master"
