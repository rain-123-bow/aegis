from __future__ import annotations

import json
from pathlib import Path

from aegis_execution_runtime.operational_skill import validate_execution_skill_run

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = REPO_ROOT / "aegis-master-kit" / "organization" / "departments" / "execution"


def valid_run() -> dict:
    return {
        "skill_ref": {"skill_id": "EXECUTION_LEADER_OPERATIONAL_SKILL", "skill_version": "v0.3"},
        "model_policy_authority": "MODEL_REASONING_BUDGET_POLICY.yaml",
        "execution_request": {
            "request_id": "REQ-1",
            "task_id": "TASK-1",
            "source": "master",
            "aegis_work_branch": "feature/aegis-task",
            "scope": "demo scope",
        },
        "contract_first_check": {"frozen_contract_required": False, "frozen_contract_present": False},
        "split_decision": {"valid": True, "invalid_split_patterns_present": []},
        "groups": [
            {"group_id": "G1", "subtask_id": "s1", "responsibility_scope": "one file"},
        ],
        "group_branch_proofs": [
            {
                "group_id": "G1",
                "subtask_id": "s1",
                "workspace_path": "work/G1",
                "repository_url": "https://example/repo.git",
                "aegis_work_branch": "feature/aegis-task",
                "base_commit": "a" * 40,
                "group_work_branch": "aegis/TASK-1/G1",
                "branch_created_by": "execution_leader",
                "branch_derives_from_base_commit": True,
                "branch_is_orphan": False,
                "branch_is_unborn": False,
                "allowed_paths": ["src/a.py"],
                "local_success_criteria": ["pytest tests/test_a.py"],
            }
        ],
        "child_agent_creation_proofs": [
            {
                "created_by": "execution_leader",
                "creation_mechanism": "real nested-codex MCP",
                "agent_id": "front-G1",
                "role_id": "execution_front_agent",
                "group_id": "G1",
                "subtask_id": "s1",
                "thread_id": "thread-front-G1",
                "requested_model": "gpt-5.5",
                "policy_model": "gpt-5.5",
                "requested_reasoning_effort": "high",
                "policy_reasoning_budget": "high",
                "fallback_used": False,
                "fallback_reason": None,
                "fallback_evidence_refs": [],
                "skill_id": "EXECUTION_FRONT_AGENT_OPERATIONAL_SKILL",
                "skill_version": "v0.3",
                "proof_statement": "created Front",
                "created_at_utc": "2026-05-21T00:00:00Z",
                "proof_json_ref": "front-proof.json",
                "proof_sha256": "1" * 64,
            },
            {
                "created_by": "execution_leader",
                "creation_mechanism": "real nested-codex MCP",
                "agent_id": "back-G1",
                "role_id": "execution_back_agent",
                "group_id": "G1",
                "subtask_id": "s1",
                "thread_id": "thread-back-G1",
                "requested_model": "gpt-5.5",
                "policy_model": "gpt-5.5",
                "requested_reasoning_effort": "high",
                "policy_reasoning_budget": "high",
                "fallback_used": False,
                "fallback_reason": None,
                "fallback_evidence_refs": [],
                "skill_id": "EXECUTION_BACK_AGENT_OPERATIONAL_SKILL",
                "skill_version": "v0.3",
                "proof_statement": "created Back",
                "created_at_utc": "2026-05-21T00:00:00Z",
                "proof_json_ref": "back-proof.json",
                "proof_sha256": "2" * 64,
            },
        ],
        "front_outputs": [
            {
                "agent_id": "front-G1",
                "role_id": "execution_front_agent",
                "thread_id": "thread-front-G1",
                "child_agent_creation_proof_ref": "front-proof.json",
                "skill_ref": {"skill_id": "EXECUTION_FRONT_AGENT_OPERATIONAL_SKILL", "skill_version": "v0.3"},
                "skill_received": True,
                "skill_applied": True,
                "group_id": "G1",
                "subtask_id": "s1",
                "group_workspace": "work/G1",
                "group_work_branch": "aegis/TASK-1/G1",
                "base_commit": "a" * 40,
                "commit_sha": "b" * 40,
                "branch_diff_ref": "diff-G1.patch",
                "group_branch_proof_ref": "group-branch-proof-G1.json",
                "implementation_summary": "changed src/a.py",
                "touched_files": ["src/a.py"],
                "local_test_evidence": [{"command": "pytest", "result": "pass", "evidence_ref": "pytest.log"}],
                "group_causal_fork": {
                    "statement": "G1 implemented s1",
                    "why": "assigned scope",
                    "evidence": ["pytest.log"],
                    "scope": "G1",
                    "assumptions": ["base unchanged"],
                    "status": "causal_candidate",
                },
                "known_limits": [],
                "self_approved": False,
                "global_causal_truth_claimed": False,
            }
        ],
        "back_reviews": [
            {
                "agent_id": "back-G1",
                "role_id": "execution_back_agent",
                "thread_id": "thread-back-G1",
                "child_agent_creation_proof_ref": "back-proof.json",
                "skill_ref": {"skill_id": "EXECUTION_BACK_AGENT_OPERATIONAL_SKILL", "skill_version": "v0.3"},
                "skill_received": True,
                "skill_applied": True,
                "group_id": "G1",
                "subtask_id": "s1",
                "reviewed_front_agent_id": "front-G1",
                "audit_workspace": "audit/G1",
                "same_workspace_exception_used": False,
                "reviewed_branch": "aegis/TASK-1/G1",
                "reviewed_commit_sha": "b" * 40,
                "base_commit": "a" * 40,
                "branch_proof_checked": True,
                "branch_derives_from_base_commit": True,
                "branch_is_orphan": False,
                "branch_is_unborn": False,
                "branch_diff_checked": True,
                "touched_files_checked": True,
                "local_test_evidence_checked": True,
                "contract_checked": True,
                "first_principles_checked": True,
                "scope_checked": True,
                "risk_checked": True,
                "review_decision": "accept",
                "review_summary": "accepted",
                "blocking_objections": [],
                "evidence_checked": ["diff-G1.patch", "pytest.log"],
                "risk_notes": [],
                "implementation_modified_by_back": False,
                "no_new_commit_by_back": True,
            }
        ],
        "leader_integration": {
            "created_by": "execution_leader",
            "integration_branch": "aegis/TASK-1/integration",
            "base_commit": "a" * 40,
            "derives_from_base_commit": True,
            "accepted_group_branches": [{"group_id": "G1", "group_work_branch": "aegis/TASK-1/G1"}],
        },
        "integration_conflicts": [],
        "test_handoff_package": {
            "integration_branch": "aegis/TASK-1/integration",
            "no_remote_push": True,
            "no_pr_created": True,
            "no_release": True,
        },
        "execution_causal_handoff": {
            "statement": "Execution produced integration branch",
            "why": "front/back/integration closed",
            "evidence": ["diff-G1.patch"],
            "scope": "TASK-1",
            "assumptions": ["tests pass"],
            "status": "causal_candidate",
            "global_causal_truth_merge_performed": False,
        },
        "boundaries": {
            "remote_push_performed": False,
            "pull_request_created": False,
            "remote_merge_performed": False,
            "release_performed": False,
            "global_causal_truth_merge_performed": False,
        },
    }


def _validate(payload: dict):
    return validate_execution_skill_run(
        payload,
        leader_skill_path=SKILL_ROOT / "EXECUTION_LEADER_OPERATIONAL_SKILL.md",
        front_skill_path=SKILL_ROOT / "EXECUTION_FRONT_AGENT_OPERATIONAL_SKILL.md",
        back_skill_path=SKILL_ROOT / "EXECUTION_BACK_AGENT_OPERATIONAL_SKILL.md",
    )


def test_valid_execution_role_skill_run_accepts():
    result = _validate(valid_run()).to_dict()
    assert result["status"] == "validated"
    assert result["decision"] == "accepted_execution_role_skill_enforcement"
    assert result["violations"] == []


def test_missing_child_creation_proof_rejects():
    payload = valid_run()
    payload["child_agent_creation_proofs"] = payload["child_agent_creation_proofs"][:1]
    result = _validate(payload).to_dict()
    assert result["status"] == "rejected"
    assert any("Missing Back creation proof" in v["reason"] for v in result["violations"])


def test_front_thread_id_null_rejects_final_acceptance():
    payload = valid_run()
    payload["front_outputs"][0]["thread_id"] = None
    result = _validate(payload).to_dict()
    assert result["status"] == "rejected"
    assert any(v["field"] == "front_outputs.thread_id" for v in result["violations"])


def test_front_child_agent_creation_proof_ref_missing_rejects():
    payload = valid_run()
    payload["front_outputs"][0].pop("child_agent_creation_proof_ref")
    result = _validate(payload).to_dict()
    assert result["status"] == "rejected"
    assert any(v["field"] == "front_outputs.child_agent_creation_proof_ref" for v in result["violations"])


def test_back_thread_id_mismatch_rejects():
    payload = valid_run()
    payload["back_reviews"][0]["thread_id"] = "wrong-thread"
    result = _validate(payload).to_dict()
    assert result["status"] == "rejected"
    assert any(v["field"] == "back_reviews.thread_id" for v in result["violations"])


def test_back_child_agent_creation_proof_ref_missing_rejects():
    payload = valid_run()
    payload["back_reviews"][0].pop("child_agent_creation_proof_ref")
    result = _validate(payload).to_dict()
    assert result["status"] == "rejected"
    assert any(v["field"] == "back_reviews.child_agent_creation_proof_ref" for v in result["violations"])


def test_model_policy_authority_missing_rejects():
    payload = valid_run()
    payload["model_policy_authority"] = "skill_file"
    result = _validate(payload).to_dict()
    assert result["status"] == "rejected"
    assert any(v["field"] == "model_policy_authority" for v in result["violations"])


def test_model_mismatch_in_creation_proof_rejects():
    payload = valid_run()
    payload["child_agent_creation_proofs"][0]["requested_model"] = "gpt-5"
    result = _validate(payload).to_dict()
    assert result["status"] == "rejected"
    assert any(v["field"] == "child_agent_creation_proofs.model" for v in result["violations"])


def test_group_branch_orphan_rejects():
    payload = valid_run()
    payload["group_branch_proofs"][0]["branch_is_orphan"] = True
    result = _validate(payload).to_dict()
    assert result["status"] == "rejected"
    assert any(v["field"] == "group_branch_proofs.branch_state" for v in result["violations"])


def test_front_direct_baseline_work_rejects():
    payload = valid_run()
    payload["front_outputs"][0]["worked_on_aegis_work_branch"] = True
    result = _validate(payload).to_dict()
    assert result["status"] == "rejected"
    assert any(v["field"] == "front_outputs.boundary" for v in result["violations"])


def test_back_same_workspace_without_safe_exception_rejects():
    payload = valid_run()
    review = payload["back_reviews"][0]
    review["same_workspace_exception_used"] = True
    review["same_workspace_exception"] = {
        "approved_by": "execution_leader",
        "reason": "resource limited",
        "exception_record_ref": "EXC-1.json",
        "read_only_review_mode": False,
        "implementation_modified_by_back": False,
        "no_new_commit_by_back": True,
    }
    result = _validate(payload).to_dict()
    assert result["status"] == "rejected"
    assert any(v["field"] == "back_reviews.same_workspace_exception" for v in result["violations"])


def test_back_same_workspace_without_exception_flag_rejects():
    payload = valid_run()
    payload["back_reviews"][0]["audit_workspace"] = payload["group_branch_proofs"][0]["workspace_path"]
    payload["back_reviews"][0]["same_workspace_exception_used"] = False
    result = _validate(payload).to_dict()
    assert result["status"] == "rejected"
    assert any(v["field"] == "back_reviews.audit_workspace" for v in result["violations"])


def test_back_review_without_diff_check_rejects():
    payload = valid_run()
    payload["back_reviews"][0]["branch_diff_checked"] = False
    result = _validate(payload).to_dict()
    assert result["status"] == "rejected"
    assert any(v["field"] == "back_reviews.branch_diff_checked" for v in result["violations"])


def test_back_reviewed_commit_must_match_front_commit():
    payload = valid_run()
    payload["back_reviews"][0]["reviewed_commit_sha"] = "c" * 40
    result = _validate(payload).to_dict()
    assert result["status"] == "rejected"
    assert any(v["field"] == "back_reviews.reviewed_commit_sha" for v in result["violations"])


def test_back_evidence_checked_must_include_front_branch_diff():
    payload = valid_run()
    payload["back_reviews"][0]["evidence_checked"] = ["pytest.log"]
    result = _validate(payload).to_dict()
    assert result["status"] == "rejected"
    assert any(v["field"] == "back_reviews.evidence_checked" for v in result["violations"])


def test_back_review_boolean_checks_must_be_true():
    required_true_fields = [
        "branch_proof_checked",
        "branch_diff_checked",
        "touched_files_checked",
        "local_test_evidence_checked",
        "contract_checked",
        "first_principles_checked",
        "scope_checked",
        "risk_checked",
    ]
    for field in required_true_fields:
        payload = valid_run()
        payload["back_reviews"][0][field] = False
        result = _validate(payload).to_dict()
        assert result["status"] == "rejected", field
        assert any(v["field"] == f"back_reviews.{field}" for v in result["violations"]), field


def test_child_creation_proof_requires_fallback_audit_fields():
    payload = valid_run()
    payload["child_agent_creation_proofs"][0].pop("fallback_used")
    result = _validate(payload).to_dict()
    assert result["status"] == "rejected"
    assert any(v["field"] == "child_agent_creation_proofs.fallback_used" for v in result["violations"])


def test_child_creation_proof_fallback_used_requires_evidence():
    payload = valid_run()
    proof = payload["child_agent_creation_proofs"][0]
    proof["requested_model"] = "gpt-5.4"
    proof["policy_model"] = "gpt-5.4"
    proof["fallback_used"] = True
    proof["fallback_reason"] = ""
    proof["fallback_evidence_refs"] = []
    result = _validate(payload).to_dict()
    assert result["status"] == "rejected"
    assert any(v["field"] == "child_agent_creation_proofs.fallback_reason" for v in result["violations"])
    assert any(v["field"] == "child_agent_creation_proofs.fallback_evidence_refs" for v in result["violations"])


def test_integration_without_all_groups_rejects():
    payload = valid_run()
    payload["groups"].append({"group_id": "G2", "subtask_id": "s2", "responsibility_scope": "second"})
    result = _validate(payload).to_dict()
    assert result["status"] == "rejected"
    assert any("G2" in v["reason"] for v in result["violations"])


def test_remote_push_boundary_rejects():
    payload = valid_run()
    payload["boundaries"]["remote_push_performed"] = True
    result = _validate(payload).to_dict()
    assert result["status"] == "rejected"
    assert any(v["field"] == "remote_push_performed" for v in result["violations"])


def test_front_output_remote_push_rejects():
    payload = valid_run()
    payload["front_outputs"][0]["remote_push_performed"] = True
    result = _validate(payload).to_dict()
    assert result["status"] == "rejected"
    assert any(v["field"] == "front_outputs.remote_push_performed" for v in result["violations"])


def test_front_output_global_causal_truth_claim_rejects():
    payload = valid_run()
    payload["front_outputs"][0]["global_causal_truth_claimed"] = True
    result = _validate(payload).to_dict()
    assert result["status"] == "rejected"
    assert any(v["field"] == "front_outputs.global_causal_truth_claimed" for v in result["violations"])


def test_back_output_forbidden_true_fields_reject():
    forbidden_fields = [
        "remote_push_performed",
        "pull_request_created",
        "remote_merge_performed",
        "release_performed",
        "deployment_performed",
        "external_signoff_performed",
        "global_causal_truth_merge_performed",
        "production_store_write_performed",
        "global_causal_truth_claimed",
    ]
    for field in forbidden_fields:
        payload = valid_run()
        payload["back_reviews"][0][field] = True
        result = _validate(payload).to_dict()
        assert result["status"] == "rejected", field
        assert any(v["field"] == f"back_reviews.{field}" for v in result["violations"]), field


def test_skill_files_have_expected_ids():
    for name, skill_id in [
        ("EXECUTION_LEADER_OPERATIONAL_SKILL.md", "EXECUTION_LEADER_OPERATIONAL_SKILL"),
        ("EXECUTION_FRONT_AGENT_OPERATIONAL_SKILL.md", "EXECUTION_FRONT_AGENT_OPERATIONAL_SKILL"),
        ("EXECUTION_BACK_AGENT_OPERATIONAL_SKILL.md", "EXECUTION_BACK_AGENT_OPERATIONAL_SKILL"),
    ]:
        text = (SKILL_ROOT / name).read_text(encoding="utf-8")
        assert f"skill_id: {skill_id}" in text
        assert "skill_version: v0.3" in text


def test_front_and_back_skills_require_thread_identity():
    front_text = (SKILL_ROOT / "EXECUTION_FRONT_AGENT_OPERATIONAL_SKILL.md").read_text(encoding="utf-8")
    back_text = (SKILL_ROOT / "EXECUTION_BACK_AGENT_OPERATIONAL_SKILL.md").read_text(encoding="utf-8")
    assert "thread_id" in front_text
    assert "Launcher timeout alone is not Front failure" in front_text
    assert "thread_id" in back_text
    assert "Launcher timeout alone is not Back failure" in back_text


def test_leader_skill_requires_child_creation_proof_and_audit_workspace():
    text = (SKILL_ROOT / "EXECUTION_LEADER_OPERATIONAL_SKILL.md").read_text(encoding="utf-8")
    assert "group_branch_proof" in text
    assert "Agent lifecycle judgment is keyed by `thread_id`" in text
    assert "audit_workspace_required_by_default" in text
    assert "conflict_policy" in text
