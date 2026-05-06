from __future__ import annotations

from aegis_final_review_runtime import FinalReviewLeader


def _request(kind: str = "accept") -> dict:
    resource = {
        "policy_ref": "policy:root-model-budget",
        "required_profile": "final_review_leader",
        "resolved_profile": "final_review_leader",
        "reasoning_budget": "maximum",
        "fallback_used": False,
        "status": "satisfied",
    }
    package = {
        "task_scope": ["declared_scope"],
        "final_code_ref": "candidate:final",
        "implementation_candidate_ref": "candidate:final",
        "tested_candidate_ref": "candidate:final",
        "reviewed_refs": {
            "execution_final_report_ref": "exec:final-report",
            "execution_causal_chain_ref": "exec:causal-candidate",
            "test_final_report_ref": "test:final-report",
            "test_plan_ref": "test:plan",
            "test_route_report_refs": ["test:route-report"],
            "test_evidence_refs": ["test:evidence"],
            "reproducibility_set_ref": "test:reproducibility",
            "artifact_manifest_ref": "test:artifact-manifest",
            "debate_refs": [],
        },
        "accepted_scope": ["declared_scope"],
        "blocked_scope": [],
        "known_limits": [],
        "missing_evidence": [],
        "governance_blockers": [],
        "material_conditions": ["deterministic demo candidate snapshot"],
        "assumptions": ["demo input refs are durable"],
        "execution_defects": [],
        "test_evidence_deficiencies": [],
        "evidence_contradictions": [],
        "object_mapping_evidence": [],
        "debate_used": False,
    }
    if kind == "resource_missing":
        resource["status"] = "missing"
        package["reviewed_refs"]["test_evidence_refs"] = []
    elif kind == "scope_limit":
        package["known_limits"] = ["compatibility scope not tested"]
        package["blocked_scope"] = ["compatibility_scope"]
    elif kind == "object_mismatch":
        package["final_code_ref"] = "candidate:final-b"
    elif kind == "object_mapping":
        package["final_code_ref"] = "candidate:final-b"
        package["object_mapping_evidence"] = ["candidate:final-b is material equivalent to candidate:final"]
    elif kind == "test_deficiency":
        package["reviewed_refs"]["test_route_report_refs"] = []
        package["reviewed_refs"]["test_evidence_refs"] = []
        package["reviewed_refs"]["reproducibility_set_ref"] = ""
        package["reviewed_refs"]["artifact_manifest_ref"] = ""
        package["test_evidence_deficiencies"] = ["missing Test route report", "missing reproducibility set"]
    elif kind == "governance":
        package["governance_blockers"] = ["release authority boundary unresolved"]
    elif kind == "missing_debate":
        package["debate_used"] = True
        package["reviewed_refs"]["debate_refs"] = []
    return {
        "request_id": f"final-review-{kind}",
        "source": "test",
        "resource_policy": resource,
        "final_review_input_package": package,
    }


def test_resource_policy_failure_has_highest_precedence(tmp_path):
    leader = FinalReviewLeader(tmp_path)

    result = leader.run(_request("resource_missing")).to_dict()

    assert result["decision"] == "blocked_resource_policy"
    assert result["target"] == "master"
    assert result["resource_policy"]["status"] == "missing"
    assert result["missing_evidence"] == []


def test_accept_for_master_requires_no_limits_and_satisfied_policy(tmp_path):
    leader = FinalReviewLeader(tmp_path)

    result = leader.run(_request()).to_dict()

    assert result["decision"] == "accept_for_master"
    assert result["target"] == "master"
    assert result["known_limits"] == []
    assert result["blocked_scope"] == []
    assert result["missing_evidence"] == []
    assert result["resource_policy"]["status"] == "satisfied"
    assert result["causal_boundary"].startswith("Final Review output is a recommendation")


def test_known_limits_force_scope_limited_acceptance(tmp_path):
    leader = FinalReviewLeader(tmp_path)

    result = leader.run(_request("scope_limit")).to_dict()

    assert result["decision"] == "accept_for_master_with_scope_limit"
    assert result["target"] == "master"
    assert result["known_limits"]
    assert result["blocked_scope"]


def test_object_mismatch_rejects_to_execution_via_master(tmp_path):
    leader = FinalReviewLeader(tmp_path)

    result = leader.run(_request("object_mismatch")).to_dict()

    assert result["decision"] == "reject_to_execution_via_master"
    assert result["target"] == "master"
    assert "final-to-tested object mapping" in result["missing_evidence"]


def test_object_mapping_allows_review_to_continue(tmp_path):
    leader = FinalReviewLeader(tmp_path)

    result = leader.run(_request("object_mapping")).to_dict()

    assert result["decision"] == "accept_for_master"


def test_test_evidence_deficiency_requests_test_expansion_via_master(tmp_path):
    leader = FinalReviewLeader(tmp_path)

    result = leader.run(_request("test_deficiency")).to_dict()

    assert result["decision"] == "request_test_expansion_via_master"
    assert result["target"] == "master"


def test_governance_blocker_goes_to_master(tmp_path):
    leader = FinalReviewLeader(tmp_path)

    result = leader.run(_request("governance")).to_dict()

    assert result["decision"] == "governance_blocker_to_master"
    assert result["target"] == "master"
    assert result["governance_blockers"]


def test_missing_debate_reference_requests_more_evidence(tmp_path):
    leader = FinalReviewLeader(tmp_path)

    result = leader.run(_request("missing_debate")).to_dict()

    assert result["decision"] == "request_more_evidence_via_master"
    assert "reviewed_refs.debate_refs" in result["missing_evidence"]
