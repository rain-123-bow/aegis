from __future__ import annotations

from aegis_governance_runtime import RuntimeCheck, load_default_skill_registry, validate_artifact
from aegis_governance_runtime.skill_registry import default_registry_snapshot


def test_default_registry_contains_all_phase31a_roles():
    registry = load_default_skill_registry()
    assert registry.roles() == (
        "debate_leader",
        "debate_worker",
        "execution_back_agent",
        "execution_front_agent",
        "execution_leader",
        "final_review_leader",
        "master",
        "test_leader",
        "test_worker",
    )
    assert registry.require_role("master").authority == "runtime_hard_gate"


def test_master_cannot_create_department_internal_worker():
    decision = RuntimeCheck().check(
        {
            "actor_role": "master",
            "action": "create_test_worker",
        }
    )
    assert decision.status == "rejected"
    assert any(item.code in {"denied_action", "action_not_allowed"} for item in decision.violations)


def test_execution_front_requires_group_branch_proof_before_write():
    decision = RuntimeCheck().check(
        {
            "actor_role": "execution_front_agent",
            "action": "modify_allowed_files",
            "write_path": "workspaces/execution/front/group-a/src/main.py",
        }
    )
    assert decision.status == "rejected"
    assert any(item.code == "missing_required_artifact" for item in decision.violations)


def test_execution_front_write_path_is_capability_bounded():
    decision = RuntimeCheck().check(
        {
            "actor_role": "execution_front_agent",
            "action": "modify_allowed_files",
            "artifact_refs": ["group_branch_proof"],
            "write_path": "README.md",
        }
    )
    assert decision.status == "rejected"
    assert any(item.code == "write_path_outside_capability" for item in decision.violations)


def test_execution_front_allowed_write_with_required_artifact():
    decision = RuntimeCheck().check(
        {
            "actor_role": "execution_front_agent",
            "action": "modify_allowed_files",
            "artifact_refs": ["group_branch_proof"],
            "write_path": "workspaces/execution/front/group-a/src/main.py",
        }
    )
    assert decision.status == "allowed"


def test_state_machine_blocks_execution_front_creation_before_branch_state():
    decision = RuntimeCheck().check(
        {
            "actor_role": "execution_leader",
            "action": "create_execution_front_agent",
            "current_state": "execution_request_received",
            "artifact_refs": ["group_branch_proof"],
        }
    )
    assert decision.status == "rejected"
    assert any(item.code == "state_transition_not_allowed" for item in decision.violations)


def test_final_review_leader_cannot_create_worker():
    decision = RuntimeCheck().check(
        {
            "actor_role": "final_review_leader",
            "action": "create_worker",
        }
    )
    assert decision.status == "rejected"
    assert any(item.code in {"denied_action", "action_not_allowed"} for item in decision.violations)


def test_artifact_contract_blocks_incomplete_group_branch_proof():
    snapshot = default_registry_snapshot()
    contract = next(item for item in snapshot.artifact_contracts if item.contract_id == "group_branch_proof")
    violations = validate_artifact(
        contract,
        {
            "group_id": "group-a",
            "base_commit": "abc123",
            "branch_derives_from_base_commit": True,
            "branch_is_orphan": False,
            "branch_is_unborn": False,
        },
    )
    assert any(item.field == "group_work_branch" for item in violations)
    assert any(item.field == "allowed_paths" for item in violations)


def test_runtime_check_can_validate_artifact_payload_inline():
    decision = RuntimeCheck().check(
        {
            "actor_role": "master",
            "action": "create_commit_candidate",
            "artifact_refs": ["commit_gate_candidate"],
            "payload": {
                "artifact_contract_id": "commit_gate_candidate",
                "artifact_payload": {
                    "task_id": "TASK-1",
                    "decision": "ready_for_developer_authorization",
                    "exactly_one_task_bound": True,
                    "remote_push_performed": False,
                    "pr_created": False,
                    "remote_merge_performed": False,
                    "release_performed": False,
                },
            },
        }
    )
    assert decision.status == "allowed"
