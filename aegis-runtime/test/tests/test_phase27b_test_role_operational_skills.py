from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from aegis_test_runtime.operational_skill import (
    LEADER_SKILL_ID,
    WORKER_SKILL_ID,
    SKILL_VERSION,
    validate_test_skill_run,
)


def _skill_ref(skill_id: str) -> dict[str, str]:
    return {"skill_id": skill_id, "skill_version": SKILL_VERSION}


def _valid_run() -> dict:
    return {
        "skill_ref": _skill_ref(LEADER_SKILL_ID),
        "test_request": {
            "request_id": "REQ-27B",
            "source": "execution",
            "objective": "Validate the integrated candidate.",
            "scope": "changed files",
            "base_branch": "main",
            "integration_branch": "aegis/test/integration",
            "implementation_candidate_ref": "candidate-ref",
            "final_code_ref": "commit-abc",
            "changed_files": ["src/example.py"],
            "ownership_map": {"src/example.py": "group-1"},
            "local_test_evidence": ["front-local-test.json"],
            "back_review_summaries": ["back-review.json"],
            "expected_test_focus": ["pytest"],
            "success_criteria": ["all checks pass"],
            "forbidden_actions": ["remote push", "release"],
        },
        "governance_check": {"performed": True, "blocked": False},
        "test_plan": {
            "plan_id": "PLAN-27B",
            "request_id": "REQ-27B",
            "routes": [
                {
                    "route_id": "route.sandbox_pytest",
                    "mandatory": True,
                    "scope": ["src/example.py"],
                    "method": "pytest",
                }
            ],
        },
        "worker_creation_requests": [
            {
                "agent_id": "worker-1",
                "role_id": "test_worker",
                "run_id": "RUN-27B",
                "route_id": "route.sandbox_pytest",
                "worker_skill_ref": _skill_ref(WORKER_SKILL_ID),
                "creation_mechanism": "mcp__nested_codex__.codex",
                "thread_id": "thread-1",
                "requested_model": "gpt-5.5",
                "policy_model": "gpt-5.5",
                "requested_reasoning_effort": "high",
                "policy_reasoning_budget": "high",
                "fallback_used": False,
                "fallback_reason": None,
                "fallback_evidence_refs": [],
                "proof_path": "worker_proofs/worker-1_proof.json",
                "output_path": "worker_outputs/worker-1_output.json",
            }
        ],
        "worker_supervision_records": [
            {
                "run_id": "RUN-27B",
                "route_id": "route.sandbox_pytest",
                "worker_id": "worker-1",
                "role_id": "test_worker",
                "creation_mechanism": "mcp__nested_codex__.codex",
                "thread_id": "thread-1",
                "launcher_status": "creation_returned",
                "child_status": "result_recovered",
                "recovery_attempted": False,
                "result_recovered": True,
                "proof_status": "present",
                "output_status": "present",
                "duplicate_worker_created_for_same_route": False,
            }
        ],
        "worker_proofs": [
            {
                "agent_id": "worker-1",
                "role_id": "test_worker",
                "created_by": "test_leader",
                "creation_mechanism": "mcp__nested_codex__.codex",
                "requested_model": "gpt-5.5",
                "policy_model": "gpt-5.5",
                "requested_reasoning_effort": "high",
                "policy_reasoning_budget": "high",
                "fallback_used": False,
                "fallback_reason": None,
                "fallback_evidence_refs": [],
                "topology_scope": "test_route_local_domain",
                "run_id": "RUN-27B",
                "route_id": "route.sandbox_pytest",
                "thread_id": "thread-1",
                "proof_path": "worker_proofs/worker-1_proof.json",
                "proof_sha256": "abc123",
                "skill_ref": _skill_ref(WORKER_SKILL_ID),
                "skill_received": True,
                "skill_applied": True,
                "created_at_utc": "2026-05-24T00:00:00Z",
                "proof_statement": "I am a route-bound Test Worker.",
            }
        ],
        "worker_outputs": [
            {
                "agent_id": "worker-1",
                "role_id": "test_worker",
                "run_id": "RUN-27B",
                "route_id": "route.sandbox_pytest",
                "thread_id": "thread-1",
                "proof_ref": "worker_proofs/worker-1_proof.json",
                "skill_ref": _skill_ref(WORKER_SKILL_ID),
                "skill_received": True,
                "skill_applied": True,
                "route_scope": ["src/example.py"],
                "command_evidence": [
                    {
                        "command": "pytest -vv",
                        "exit_code": 0,
                        "stdout_ref": "stdout.txt",
                        "stderr_ref": "stderr.txt",
                    }
                ],
                "observations": ["pytest passed"],
                "evidence_refs": ["stdout.txt"],
                "test_data_refs": ["worker_report.json"],
                "covered_scope": ["src/example.py"],
                "uncovered_scope": [],
                "route_result": "passed",
                "failure_signatures": [],
                "owner_hint": {"owner_type": "none"},
                "blocker_kind": None,
                "blocker_scope": None,
                "why": "Assigned route checks passed.",
                "assumptions": ["sandbox candidate is representative"],
                "material_conditions": ["commit-abc"],
                "status": "test_worker_report_candidate",
                "causal_status": "scoped_evidence_candidate",
                "implementation_code_modified": False,
                "remote_push_performed": False,
                "pull_request_created": False,
                "remote_merge_performed": False,
                "release_performed": False,
                "deployment_performed": False,
                "global_causal_truth_claimed": False,
            }
        ],
        "final_test_result": {
            "result": "passed",
            "feedback_kind": "success",
            "next_route": "final_review",
            "covered_scope": ["src/example.py"],
            "uncovered_scope": [],
            "evidence_refs": ["stdout.txt"],
            "test_data_refs": ["worker_report.json"],
            "reproducibility_set_ref": "reproducibility_set.json",
            "artifact_manifest_ref": "artifact_manifest.json",
            "global_causal_truth_merge_performed": False,
        },
        "reproducibility_set": {
            "test_plan_ref": "test_plan.json",
            "input_refs": {"integration_branch": "aegis/test/integration"},
            "evidence_refs": ["stdout.txt"],
        },
        "artifact_manifest": {
            "artifacts": [
                {
                    "path_or_uri": "stdout.txt",
                    "artifact_type": "stdout",
                    "producer": "test_worker",
                    "semantic_role": "evidence",
                }
            ]
        },
        "boundaries": {
            "remote_push_performed": False,
            "pull_request_created": False,
            "remote_merge_performed": False,
            "release_performed": False,
            "deployment_performed": False,
            "external_signoff_performed": False,
            "production_store_write_performed": False,
            "global_causal_truth_merge_performed": False,
        },
    }


def _assert_rejected(run: dict, field_prefix: str) -> None:
    result = validate_test_skill_run(run)
    assert result.status == "rejected"
    assert any(v["field"].startswith(field_prefix) or field_prefix in v["field"] for v in result.violations), result.to_dict()


def test_valid_run_is_accepted() -> None:
    result = validate_test_skill_run(_valid_run())
    assert result.status == "validated"
    assert result.decision == "accepted_test_role_skill_runtime_validation"


def test_missing_leader_skill_ref_rejects() -> None:
    run = _valid_run()
    run["skill_ref"] = {}
    _assert_rejected(run, "skill_ref")


def test_missing_worker_skill_ref_on_creation_rejects() -> None:
    run = _valid_run()
    run["worker_creation_requests"][0].pop("worker_skill_ref")
    _assert_rejected(run, "worker_creation_requests.worker_skill_ref")


def test_missing_worker_skill_ref_on_proof_rejects() -> None:
    run = _valid_run()
    run["worker_proofs"][0].pop("skill_ref")
    _assert_rejected(run, "worker_proofs.skill_ref")


def test_missing_worker_skill_ref_on_output_rejects() -> None:
    run = _valid_run()
    run["worker_outputs"][0].pop("skill_ref")
    _assert_rejected(run, "worker_outputs.skill_ref")


def test_missing_creation_thread_id_rejects() -> None:
    run = _valid_run()
    run["worker_creation_requests"][0]["thread_id"] = ""
    _assert_rejected(run, "worker_creation_requests.thread_id")


def test_missing_proof_thread_id_rejects() -> None:
    run = _valid_run()
    run["worker_proofs"][0]["thread_id"] = ""
    _assert_rejected(run, "worker_proofs.thread_id")


def test_output_thread_id_mismatch_rejects() -> None:
    run = _valid_run()
    run["worker_outputs"][0]["thread_id"] = "different-thread"
    _assert_rejected(run, "worker_outputs.thread_id")


def test_launcher_timeout_treated_as_worker_failure_rejects() -> None:
    run = _valid_run()
    run["worker_supervision_records"][0]["launcher_status"] = "launcher_timeout"
    run["worker_supervision_records"][0]["child_status"] = "failed"
    run["worker_supervision_records"][0]["recovery_attempted"] = True
    _assert_rejected(run, "worker_supervision_records.launcher_status")


def test_launcher_timeout_without_recovery_rejects() -> None:
    run = _valid_run()
    run["worker_supervision_records"][0]["launcher_status"] = "launcher_timeout"
    run["worker_supervision_records"][0]["recovery_attempted"] = False
    _assert_rejected(run, "worker_supervision_records.recovery_attempted")


def test_duplicate_worker_due_launcher_timeout_rejects() -> None:
    run = _valid_run()
    run["worker_supervision_records"][0]["duplicate_worker_created_for_same_route"] = True
    _assert_rejected(run, "worker_supervision_records.duplicate_worker_created_for_same_route")


def test_missing_requested_reasoning_effort_rejects_even_with_legacy_field() -> None:
    run = _valid_run()
    for section in ("worker_creation_requests", "worker_proofs"):
        run[section][0]["requested_reasoning_budget"] = "high"
        run[section][0].pop("requested_reasoning_effort")
    _assert_rejected(run, "requested_reasoning_effort")


def test_requested_reasoning_budget_adapter_accepts_legacy_field() -> None:
    run = _valid_run()
    run["compatibility_adapters"] = [
        {"from": "requested_reasoning_budget", "to": "requested_reasoning_effort", "enabled": True}
    ]
    for section in ("worker_creation_requests", "worker_proofs"):
        run[section][0]["requested_reasoning_budget"] = "high"
        run[section][0].pop("requested_reasoning_effort")
    result = validate_test_skill_run(run)
    assert result.status == "validated", result.to_dict()


def test_reasoning_mismatch_rejects() -> None:
    run = _valid_run()
    run["worker_creation_requests"][0]["requested_reasoning_effort"] = "medium"
    _assert_rejected(run, "worker_creation_requests.requested_reasoning_effort")


def test_fallback_used_when_profile_forbids_fallback_rejects() -> None:
    run = _valid_run()
    run["worker_creation_requests"][0]["fallback_used"] = True
    run["worker_creation_requests"][0]["fallback_reason"] = "gpt-5.5 unavailable"
    run["worker_creation_requests"][0]["fallback_evidence_refs"] = ["resource-report"]
    _assert_rejected(run, "worker_creation_requests.fallback_used")


def test_unaccepted_creation_mechanism_rejects() -> None:
    run = _valid_run()
    run["worker_creation_requests"][0]["creation_mechanism"] = "equivalent"
    _assert_rejected(run, "worker_creation_requests.creation_mechanism")


def test_output_missing_command_evidence_rejects() -> None:
    run = _valid_run()
    run["worker_outputs"][0].pop("command_evidence")
    _assert_rejected(run, "worker_outputs.command_evidence")


def test_commands_run_only_without_adapter_rejects() -> None:
    run = _valid_run()
    run["worker_outputs"][0]["commands_run"] = run["worker_outputs"][0].pop("command_evidence")
    _assert_rejected(run, "worker_outputs.command_evidence")


def test_commands_run_adapter_accepts_legacy_field() -> None:
    run = _valid_run()
    run["compatibility_adapters"] = [
        {"from_field": "commands_run", "to_field": "command_evidence", "enabled": True}
    ]
    run["worker_outputs"][0]["commands_run"] = run["worker_outputs"][0].pop("command_evidence")
    result = validate_test_skill_run(run)
    assert result.status == "validated", result.to_dict()


def test_worker_output_with_multiple_route_ids_rejects() -> None:
    run = _valid_run()
    run["worker_outputs"][0]["route_ids"] = ["route.sandbox_pytest", "route.other"]
    _assert_rejected(run, "worker_outputs.route_ids")


def test_worker_modified_code_rejects() -> None:
    run = _valid_run()
    run["worker_outputs"][0]["implementation_code_modified"] = True
    _assert_rejected(run, "worker_outputs.implementation_code_modified")


def test_worker_decides_whole_candidate_rejects() -> None:
    run = _valid_run()
    run["worker_outputs"][0]["whole_candidate_result_decided"] = True
    _assert_rejected(run, "worker_outputs.whole_candidate_result")


def test_failed_route_without_evidence_rejects() -> None:
    run = _valid_run()
    output = run["worker_outputs"][0]
    output["route_result"] = "failed"
    output["evidence_refs"] = []
    output["failure_signatures"] = []
    run["final_test_result"]["result"] = "failed"
    run["final_test_result"]["feedback_kind"] = "failure"
    run["final_test_result"]["next_route"] = "execution"
    _assert_rejected(run, "worker_outputs.failure_signatures")


def test_passed_route_with_skipped_mandatory_checks_rejects() -> None:
    run = _valid_run()
    run["worker_outputs"][0]["mandatory_checks_skipped"] = True
    _assert_rejected(run, "worker_outputs.mandatory_checks_skipped")


def test_failed_route_cannot_aggregate_to_inconclusive() -> None:
    run = _valid_run()
    output = run["worker_outputs"][0]
    output["route_result"] = "failed"
    output["failure_signatures"] = ["assertion_failed"]
    output["owner_hint"] = {"owner_type": "ambiguous"}
    run["final_test_result"]["result"] = "inconclusive"
    run["final_test_result"]["feedback_kind"] = "inconclusive"
    run["final_test_result"]["next_route"] = "execution"
    _assert_rejected(run, "final_test_result.result")


def test_passed_with_scope_limit_with_failed_mandatory_route_rejects() -> None:
    run = _valid_run()
    output = run["worker_outputs"][0]
    output["route_result"] = "failed"
    output["failure_signatures"] = ["assertion_failed"]
    run["final_test_result"]["result"] = "passed_with_scope_limit"
    run["final_test_result"]["next_route"] = "final_review"
    run["final_test_result"]["uncovered_scope"] = ["src/example.py"]
    _assert_rejected(run, "final_test_result.result")


def test_passed_hiding_uncovered_scope_rejects() -> None:
    run = _valid_run()
    run["final_test_result"]["uncovered_scope"] = ["src/example.py"]
    _assert_rejected(run, "final_test_result.result")


def test_direct_master_route_rejects() -> None:
    run = _valid_run()
    run["final_test_result"]["next_route"] = "master"
    _assert_rejected(run, "final_test_result.next_route")


def test_global_truth_flag_rejects() -> None:
    run = _valid_run()
    run["boundaries"]["global_causal_truth_merge_performed"] = True
    _assert_rejected(run, "global_causal_truth_merge_performed")


def test_missing_reproducibility_set_rejects() -> None:
    run = _valid_run()
    run.pop("reproducibility_set")
    run["final_test_result"].pop("reproducibility_set_ref")
    _assert_rejected(run, "reproducibility_set")


def test_missing_artifact_manifest_rejects() -> None:
    run = _valid_run()
    run.pop("artifact_manifest")
    run["final_test_result"].pop("artifact_manifest_ref")
    _assert_rejected(run, "artifact_manifest")


def test_governance_blocker_routes_to_final_review_when_review_required() -> None:
    run = _valid_run()
    run["worker_outputs"][0]["route_result"] = "blocked"
    run["worker_outputs"][0]["blocker_kind"] = "governance"
    run["worker_outputs"][0]["blocker_scope"] = "release authority"
    run["final_test_result"]["result"] = "blocked"
    run["final_test_result"]["next_route"] = "final_review"
    run["final_test_result"]["blocker_kind"] = "governance"
    run["final_test_result"]["requires_governance_review"] = True
    result = validate_test_skill_run(run)
    assert result.status == "validated", result.to_dict()


def test_ordinary_blocked_routes_to_execution() -> None:
    run = _valid_run()
    run["worker_outputs"][0]["route_result"] = "blocked"
    run["worker_outputs"][0]["blocker_kind"] = "environment"
    run["worker_outputs"][0]["blocker_scope"] = "missing dependency"
    run["final_test_result"]["result"] = "blocked"
    run["final_test_result"]["next_route"] = "execution"
    run["final_test_result"]["blocker_kind"] = "environment"
    result = validate_test_skill_run(run)
    assert result.status == "validated", result.to_dict()


def test_missing_worker_for_route_rejects() -> None:
    run = _valid_run()
    run["worker_creation_requests"] = []
    _assert_rejected(run, "worker_creation_requests")


def test_skill_file_marker_validation(tmp_path: Path) -> None:
    leader = tmp_path / "leader.md"
    worker = tmp_path / "worker.md"
    enforcement = tmp_path / "enforcement.md"
    leader.write_text("skill_id: TEST_LEADER_OPERATIONAL_SKILL\nskill_version: v0.1\nthread_id is the Worker lifecycle identity key\nlauncher_timeout\nrequested_reasoning_effort\ncommand_evidence\n", encoding="utf-8")
    worker.write_text("skill_id: TEST_WORKER_OPERATIONAL_SKILL\nskill_version: v0.1\nthread_id is the lifecycle identity key\nrequested_reasoning_effort\ncommand_evidence\ntest_worker_report_candidate\n", encoding="utf-8")
    enforcement.write_text("TEST_LEADER_WORKER_SKILL_ENFORCEMENT_CONTRACT\nlauncher_timeout != worker_failed\nthread_id is the Worker lifecycle identity key\nrequested_reasoning_effort\ncommand_evidence\n", encoding="utf-8")
    result = validate_test_skill_run(
        _valid_run(),
        leader_skill_path=leader,
        worker_skill_path=worker,
        enforcement_contract_path=enforcement,
    )
    assert result.status == "validated", result.to_dict()
