from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from aegis_master_runtime.operational_skill import validate_master_operational_cycle


def _cycle(**overrides):
    payload = {
        "skill_ref": {"skill_id": "MASTER_OPERATIONAL_WORKFLOW_SKILL", "skill_version": "v0.3"},
        "cycle_id": "cycle-001",
        "master_role_id": "master",
        "user_input_classification": "new_task_request",
        "requires_task": True,
        "requires_archive_event": True,
        "requires_knowledge_candidate": False,
        "requires_causal_candidate": False,
        "requires_department_dispatch": True,
        "requires_commit_gate": False,
        "task_boundary": {
            "decision": "create",
            "reasoning_summary": "The user request maps to one commit-bound task.",
            "final_archive_task_ids": ["TASK-001"],
            "existing_archived_tasks_merged": False,
            "aggregation_after_archive": False,
            "commit_candidate_task_id": None,
            "commit_candidate_count": 0,
            "split_commit_count": 0,
        },
        "model_policy_resolution": [
            {
                "role_id": "master",
                "requested_model": "gpt-5.5",
                "resolved_model": "gpt-5.5",
                "requested_reasoning_budget": "extra_high",
                "resolved_reasoning_budget": "extra_high",
                "policy_reasoning_budget": "extra_high",
                "model_attestation_status": "requested_policy_only",
                "fallback_used": False,
                "fallback_reason": None,
                "fallback_evidence_refs": [],
            },
            {
                "role_id": "execution_leader",
                "requested_model": "gpt-5.5",
                "resolved_model": "gpt-5.5",
                "requested_reasoning_budget": "high",
                "resolved_reasoning_budget": "high",
                "policy_reasoning_budget": "high",
                "model_attestation_status": "requested_policy_only",
                "fallback_used": False,
                "fallback_reason": None,
                "fallback_evidence_refs": [],
            },
        ],
        "archive_event_candidates": [
            {
                "candidate_type": "archive_event_candidate",
                "event_type": "task_requested",
                "task_id": "TASK-001",
                "actor": "developer",
                "occurred_at": "2026-05-19T00:00:00Z",
                "scope": "phase24a-test",
                "evidence_refs": ["chat:cycle-001"],
            }
        ],
        "knowledge_candidates": [],
        "causal_candidates": [],
        "department_dispatch": {
            "target_department": "execution",
            "master_created_top_level_leader_only": True,
            "master_created_internal_worker": False,
            "model_policy_checked": True,
        },
        "supervision": {
            "nested_codex_timeout_state": "none",
            "thread_id_recorded": False,
            "recovery_attempted": False,
            "launcher_timeout_treated_as_agent_failed": False,
        },
        "commit_gate": {
            "commit_candidate_requested": False,
            "exactly_one_archive_task_per_commit": False,
            "developer_authorization_required": True,
            "remote_push_performed": False,
            "pr_created": False,
            "remote_merge_performed": False,
            "release_performed": False,
        },
        "responsibility_boundary": {
            "developer_retains_remote_push": True,
            "developer_retains_main_merge": True,
            "developer_retains_release": True,
            "developer_retains_external_signoff": True,
        },
        "production_master_autonomy_claimed": False,
        "global_causal_truth_merge_performed": False,
    }
    payload.update(overrides)
    return payload


def _result(**overrides):
    return validate_master_operational_cycle(_cycle(**overrides))


def test_valid_new_task_cycle_is_accepted() -> None:
    result = _result()
    assert result.status == "validated"
    assert result.decision == "accepted_master_operational_workflow_skill_enforcement"
    assert result.archive_event_candidate_count == 1


def test_missing_skill_ref_rejected() -> None:
    result = _result(skill_ref={"skill_id": "old", "skill_version": "v0"})
    assert result.status == "rejected"
    assert any(item["field"] == "skill_ref" for item in result.violations)


def test_task_like_input_without_archive_event_rejected() -> None:
    result = _result(archive_event_candidates=[])
    assert result.status == "rejected"
    assert any(item["field"] == "archive_event_candidates" for item in result.violations)


def test_unclassified_user_input_rejected() -> None:
    result = _result(user_input_classification="unclassified")
    assert result.status == "rejected"
    assert any(item["field"] == "user_input_classification" for item in result.violations)


def test_task_like_input_without_task_boundary_rejected() -> None:
    result = _result(task_boundary=None)
    assert result.status == "rejected"
    assert any(item["field"] == "task_boundary" for item in result.violations)


def test_stable_fact_without_knowledge_candidate_rejected() -> None:
    result = _result(requires_knowledge_candidate=True, knowledge_candidates=[])
    assert result.status == "rejected"
    assert any(item["field"] == "knowledge_candidates" for item in result.violations)


def test_causal_claim_without_causal_candidate_rejected() -> None:
    result = _result(requires_causal_candidate=True, causal_candidates=[])
    assert result.status == "rejected"
    assert any(item["field"] == "causal_candidates" for item in result.violations)


def test_existing_archived_task_merge_rejected() -> None:
    cycle = _cycle()
    cycle["task_boundary"]["decision"] = "aggregate"
    cycle["task_boundary"]["existing_archived_tasks_merged"] = True
    result = validate_master_operational_cycle(cycle)
    assert result.status == "rejected"
    assert any(item["field"] == "task_boundary.existing_archived_tasks_merged" for item in result.violations)


def test_aggregation_after_archive_rejected() -> None:
    cycle = _cycle()
    cycle["task_boundary"]["decision"] = "aggregate"
    cycle["task_boundary"]["aggregation_after_archive"] = True
    result = validate_master_operational_cycle(cycle)
    assert result.status == "rejected"
    assert any(item["field"] == "task_boundary.aggregation_after_archive" for item in result.violations)


def test_pre_archive_aggregation_to_one_task_is_valid() -> None:
    cycle = _cycle()
    cycle["user_input_classification"] = "task_update"
    cycle["task_boundary"].update({
        "decision": "aggregate",
        "reasoning_summary": "Two not-yet-archived requests form one commit-bound task.",
        "final_archive_task_ids": ["TASK-AGG-001"],
        "existing_archived_tasks_merged": False,
        "aggregation_after_archive": False,
    })
    cycle["archive_event_candidates"][0]["task_id"] = "TASK-AGG-001"
    result = validate_master_operational_cycle(cycle)
    assert result.status == "validated"


def test_split_requires_multiple_final_archive_tasks() -> None:
    cycle = _cycle()
    cycle["task_boundary"]["decision"] = "split"
    cycle["task_boundary"]["final_archive_task_ids"] = ["TASK-ONLY"]
    result = validate_master_operational_cycle(cycle)
    assert result.status == "rejected"
    assert any(item["field"] == "task_boundary.final_archive_task_ids" for item in result.violations)


def test_split_into_multiple_commit_tasks_is_valid() -> None:
    cycle = _cycle()
    cycle["task_boundary"].update({
        "decision": "split",
        "reasoning_summary": "The user request has two independent commit boundaries.",
        "final_archive_task_ids": ["TASK-A", "TASK-B"],
        "commit_candidate_count": 2,
        "split_commit_count": 2,
    })
    cycle["archive_event_candidates"] = [
        {"candidate_type": "archive_event_candidate", "event_type": "task_split", "task_id": "TASK-A", "actor": "master", "occurred_at": "2026-05-19T00:00:00Z", "scope": "phase24a-test", "evidence_refs": ["chat:split"]},
        {"candidate_type": "archive_event_candidate", "event_type": "task_split", "task_id": "TASK-B", "actor": "master", "occurred_at": "2026-05-19T00:00:00Z", "scope": "phase24a-test", "evidence_refs": ["chat:split"]},
    ]
    result = validate_master_operational_cycle(cycle)
    assert result.status == "validated"


def test_gpt54_fallback_with_same_budget_and_evidence_is_valid() -> None:
    cycle = _cycle()
    cycle["model_policy_resolution"][0].update({
        "requested_model": "gpt-5.5",
        "resolved_model": "gpt-5.4",
        "requested_reasoning_budget": "extra_high",
        "resolved_reasoning_budget": "extra_high",
        "policy_reasoning_budget": "extra_high",
        "fallback_used": True,
        "fallback_reason": "gpt-5.5 unavailable for this call",
        "fallback_evidence_refs": ["tool_error:model_unavailable"],
    })
    result = validate_master_operational_cycle(cycle)
    assert result.status == "validated"


def test_behavioral_model_attestation_can_validate_requested_profile_consistency() -> None:
    cycle = _cycle()
    cycle["model_policy_resolution"][1]["model_attestation_status"] = "behaviorally_attested"
    cycle["behavioral_model_attestation"] = [
        {
            "agent_id": "execution",
            "role_id": "execution_leader",
            "thread_id": "thread-execution-001",
            "requested_model": "gpt-5.5",
            "policy_model": "gpt-5.5",
            "requested_reasoning_budget": "high",
            "policy_reasoning_budget": "high",
            "model_attestation_status": "behaviorally_attested",
            "behavioral_attestation_status": "behavior_consistent_with_requested_profile",
            "challenge_id": "aegis-model-behavioral-attestation-v1",
            "challenge_prompt_ref": "aegis-runtime/master/NESTED_CODEX_BEHAVIORAL_ATTESTATION_CHALLENGE.md",
            "rubric_ref": "aegis-runtime/master/NESTED_CODEX_BEHAVIORAL_ATTESTATION_CHALLENGE.md#rubric",
            "started_at_utc": "2026-06-02T00:00:00Z",
            "completed_at_utc": "2026-06-02T00:00:30Z",
            "elapsed_ms": 30000,
            "answer_quality_score": 0.86,
            "minimum_quality_score": 0.75,
            "failed_constraints": [],
        }
    ]
    result = validate_master_operational_cycle(cycle)
    assert result.status == "validated"


def test_behavioral_model_attestation_must_not_claim_tool_attested() -> None:
    cycle = _cycle()
    cycle["behavioral_model_attestation"] = [
        {
            "agent_id": "execution",
            "role_id": "execution_leader",
            "thread_id": "thread-execution-001",
            "requested_model": "gpt-5.5",
            "policy_model": "gpt-5.5",
            "requested_reasoning_budget": "high",
            "policy_reasoning_budget": "high",
            "model_attestation_status": "tool_attested",
            "behavioral_attestation_status": "behavior_consistent_with_requested_profile",
            "challenge_id": "aegis-model-behavioral-attestation-v1",
            "challenge_prompt_ref": "aegis-runtime/master/NESTED_CODEX_BEHAVIORAL_ATTESTATION_CHALLENGE.md",
            "rubric_ref": "aegis-runtime/master/NESTED_CODEX_BEHAVIORAL_ATTESTATION_CHALLENGE.md#rubric",
            "started_at_utc": "2026-06-02T00:00:00Z",
            "completed_at_utc": "2026-06-02T00:00:30Z",
            "elapsed_ms": 30000,
            "answer_quality_score": 0.86,
            "minimum_quality_score": 0.75,
            "failed_constraints": [],
        }
    ]
    result = validate_master_operational_cycle(cycle)
    assert result.status == "rejected"
    assert any(
        item["field"] == "behavioral_model_attestation[0].model_attestation_status"
        for item in result.violations
    )


def test_behavioral_model_attestation_rejects_low_score_or_failed_constraints() -> None:
    cycle = _cycle()
    cycle["behavioral_model_attestation"] = [
        {
            "agent_id": "execution",
            "role_id": "execution_leader",
            "thread_id": "thread-execution-001",
            "requested_model": "gpt-5.5",
            "policy_model": "gpt-5.5",
            "requested_reasoning_budget": "high",
            "policy_reasoning_budget": "high",
            "model_attestation_status": "behaviorally_attested",
            "behavioral_attestation_status": "behavior_consistent_with_requested_profile",
            "challenge_id": "aegis-model-behavioral-attestation-v1",
            "challenge_prompt_ref": "aegis-runtime/master/NESTED_CODEX_BEHAVIORAL_ATTESTATION_CHALLENGE.md",
            "rubric_ref": "aegis-runtime/master/NESTED_CODEX_BEHAVIORAL_ATTESTATION_CHALLENGE.md#rubric",
            "started_at_utc": "2026-06-02T00:00:00Z",
            "completed_at_utc": "2026-06-02T00:00:30Z",
            "elapsed_ms": 30000,
            "answer_quality_score": 0.50,
            "minimum_quality_score": 0.75,
            "failed_constraints": ["claimed_behaviorally_attested_equals_tool_attested"],
        }
    ]
    result = validate_master_operational_cycle(cycle)
    assert result.status == "rejected"
    assert any(
        item["field"] == "behavioral_model_attestation[0].answer_quality_score"
        for item in result.violations
    )
    assert any(
        item["field"] == "behavioral_model_attestation[0].failed_constraints"
        for item in result.violations
    )


def test_model_below_gpt54_rejected() -> None:
    cycle = _cycle()
    cycle["model_policy_resolution"][0]["resolved_model"] = "gpt-5"
    result = validate_master_operational_cycle(cycle)
    assert result.status == "rejected"
    assert any("gpt-5.4" in item["reason"] for item in result.violations)


def test_budget_downgrade_rejected() -> None:
    cycle = _cycle()
    cycle["model_policy_resolution"][0].update({
        "resolved_model": "gpt-5.4",
        "resolved_reasoning_budget": "high",
        "policy_reasoning_budget": "extra_high",
        "fallback_used": True,
        "fallback_reason": "gpt-5.5 unavailable",
        "fallback_evidence_refs": ["tool_error:model_unavailable"],
    })
    result = validate_master_operational_cycle(cycle)
    assert result.status == "rejected"
    assert any("budget" in item["field"] or "budget" in item["reason"] for item in result.violations)


def test_provider_default_model_rejected() -> None:
    cycle = _cycle()
    cycle["model_policy_resolution"][0]["requested_model"] = ""
    result = validate_master_operational_cycle(cycle)
    assert result.status == "rejected"
    assert any(item["field"].endswith("requested_model") for item in result.violations)


def test_master_direct_internal_worker_creation_rejected() -> None:
    cycle = _cycle()
    cycle["department_dispatch"]["master_created_internal_worker"] = True
    result = validate_master_operational_cycle(cycle)
    assert result.status == "rejected"
    assert any(item["field"] == "department_dispatch.master_created_internal_worker" for item in result.violations)


def test_dispatch_without_model_policy_check_rejected() -> None:
    cycle = _cycle()
    cycle["department_dispatch"]["model_policy_checked"] = False
    result = validate_master_operational_cycle(cycle)
    assert result.status == "rejected"
    assert any(item["field"] == "department_dispatch.model_policy_checked" for item in result.violations)


def test_missing_topology_edge_runtime_use_rejected() -> None:
    cycle = _cycle()
    cycle["topology_patch_request"] = {
        "requested_edge": "test -> master",
        "classification": "reject_runtime_route_request",
        "runtime_route_attempted": True,
        "edge_active": False,
        "evidence_refs": ["topology:master_top_level_v1.yaml"],
    }
    result = validate_master_operational_cycle(cycle)
    assert result.status == "rejected"
    assert any(item["field"] == "topology_patch_request.runtime_route_attempted" for item in result.violations)


def test_topology_patch_investigation_does_not_activate_edge() -> None:
    cycle = _cycle()
    cycle["topology_patch_request"] = {
        "requested_edge": "test -> master",
        "classification": "admit_topology_patch_investigation",
        "runtime_route_attempted": False,
        "edge_active": False,
        "evidence_refs": ["topology:master_top_level_v1.yaml"],
    }
    result = validate_master_operational_cycle(cycle)
    assert result.status == "validated"


def test_topology_patch_task_requires_authorization_and_evidence() -> None:
    cycle = _cycle()
    cycle["topology_patch_request"] = {
        "requested_edge": "test -> master",
        "classification": "admit_topology_patch_task",
        "runtime_route_attempted": False,
        "edge_active": False,
        "developer_authorization": False,
        "evidence_refs": [],
    }
    result = validate_master_operational_cycle(cycle)
    assert result.status == "rejected"
    assert any(item["field"] == "topology_patch_request.developer_authorization" for item in result.violations)
    assert any(item["field"] == "topology_patch_request.evidence_refs" for item in result.violations)


def test_launcher_timeout_requires_thread_id_and_recovery() -> None:
    cycle = _cycle()
    cycle["supervision"].update({
        "nested_codex_timeout_state": "launcher_timeout",
        "thread_id_recorded": False,
        "recovery_attempted": False,
    })
    result = validate_master_operational_cycle(cycle)
    assert result.status == "rejected"
    assert any(item["field"] == "supervision.thread_id_recorded" for item in result.violations)
    assert any(item["field"] == "supervision.recovery_attempted" for item in result.violations)


def test_launcher_timeout_recovery_state_valid() -> None:
    cycle = _cycle()
    cycle["supervision"].update({
        "nested_codex_timeout_state": "launcher_timeout",
        "thread_id_recorded": True,
        "recovery_attempted": True,
    })
    result = validate_master_operational_cycle(cycle)
    assert result.status == "validated"


def test_commit_candidate_requires_exactly_one_archive_task() -> None:
    cycle = _cycle(requires_commit_gate=True)
    cycle["commit_gate"].update({
        "commit_candidate_requested": True,
        "exactly_one_archive_task_per_commit": False,
    })
    result = validate_master_operational_cycle(cycle)
    assert result.status == "rejected"
    assert any(item["field"] == "commit_gate.exactly_one_archive_task_per_commit" for item in result.violations)


def test_master_remote_push_rejected() -> None:
    cycle = _cycle()
    cycle["commit_gate"]["remote_push_performed"] = True
    result = validate_master_operational_cycle(cycle)
    assert result.status == "rejected"
    assert any(item["field"] == "commit_gate.remote_push_performed" for item in result.violations)


def test_missing_developer_responsibility_retention_rejected() -> None:
    cycle = _cycle()
    cycle["responsibility_boundary"]["developer_retains_release"] = False
    result = validate_master_operational_cycle(cycle)
    assert result.status == "rejected"
    assert any(item["field"] == "responsibility_boundary.developer_retains_release" for item in result.violations)


def test_skill_file_marker_validation(tmp_path: Path) -> None:
    skill = tmp_path / "MASTER_OPERATIONAL_WORKFLOW_SKILL.md"
    skill.write_text(
        "# MASTER_OPERATIONAL_WORKFLOW_SKILL v0.3\n\n"
        "Every user message triggers Master Intake\n"
        "Task identity is commit-bound\n"
        "Reasoning budget must not downgrade\n"
        "Models below `gpt-5.4` are forbidden\n",
        encoding="utf-8",
    )
    result = validate_master_operational_cycle(_cycle(), skill_path=skill)
    assert result.status == "validated"


def test_cli_validates_cycle_file(tmp_path: Path) -> None:
    cycle_path = tmp_path / "cycle.json"
    output_path = tmp_path / "result.json"
    cycle_path.write_text(json.dumps(_cycle()), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "aegis_master_runtime.cli",
            "validate-operational-skill",
            "--cycle",
            str(cycle_path),
            "--output",
            str(output_path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "accepted_master_operational_workflow_skill_enforcement" in completed.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "validated"
