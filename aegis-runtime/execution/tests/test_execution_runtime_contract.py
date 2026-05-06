from __future__ import annotations

from pathlib import Path

import pytest

from aegis_execution_runtime import ExecutionLeader
from aegis_execution_runtime.models import ExecutionContractError, ExecutionRequest, ExecutionRunState, FinalExecutionReport


def _request() -> dict:
    return {
        "request_id": "unit-execution-001",
        "sender": "master",
        "objective": "Implement two independent fixture outputs.",
        "scope": "unit fixture project",
        "constraints": ["contract-first execution", "final output remains causal_candidate"],
        "applicable_contracts": ["EXECUTION_LEADER_CONTRACT.md"],
        "success_criteria": ["both files integrated", "test feedback processed"],
        "forbidden_actions": ["remote push", "main merge", "release"],
        "base_branch": "v0.1.0-alpha",
        "candidate_plans": [
            {
                "plan_id": "P1",
                "claim": "Use direct split-integrate-test plan.",
                "why": "It is contract-valid and non-dominated.",
                "valid_under_contracts": True,
                "dominated": False,
                "strengths": ["traceable"],
                "weaknesses": ["demo only"],
                "evidence": ["P1"],
            },
            {
                "plan_id": "P2",
                "claim": "Use one unstructured worker.",
                "why": "It is simpler but dominated.",
                "valid_under_contracts": True,
                "dominated": True,
                "strengths": ["simple"],
                "weaknesses": ["weak ownership"],
                "evidence": ["P2"],
            },
        ],
        "subtasks": [
            {
                "subtask_id": "S1",
                "responsibility": "Create A.",
                "owned_files_or_modules": ["a.txt"],
                "input_contract": "A input",
                "output_contract": "A output",
                "dependencies": [],
                "independence_reason": "A owns a distinct file.",
                "local_success_criteria": ["a.txt exists"],
                "expected_branch": "execution/unit/G1/a",
                "merge_risk": "low",
                "feedback_mapping_rule": "a.txt -> G1",
                "file_changes": [{"path": "a.txt", "content": "A\n", "change_type": "add", "why_changed": "A"}],
            },
            {
                "subtask_id": "S2",
                "responsibility": "Create B.",
                "owned_files_or_modules": ["b.txt"],
                "input_contract": "B input",
                "output_contract": "B output",
                "dependencies": ["S1"],
                "independence_reason": "B owns a distinct file after S1 interface is fixed.",
                "local_success_criteria": ["b.txt exists"],
                "expected_branch": "execution/unit/G2/b",
                "merge_risk": "low",
                "feedback_mapping_rule": "b.txt -> G2",
                "file_changes": [{"path": "b.txt", "content": "B\n", "change_type": "add", "why_changed": "B"}],
            },
        ],
    }


def test_vague_task_returns_request_more_context(tmp_path):
    leader = ExecutionLeader(tmp_path)
    report = leader.start_run({"request_id": "vague", "sender": "master", "objective": "", "scope": ""})

    assert isinstance(report, FinalExecutionReport)
    assert report.decision == "request_more_context"
    assert report.final_status == "needs_context"
    assert report.execution_causal_chain["status"] == "causal_candidate"


def test_request_test_measurement_precedes_debate(tmp_path):
    payload = _request()
    payload["requires_measurement"] = True
    payload["required_measurements"] = ["benchmark latency for P1 vs P3"]
    payload["candidate_plans"].append(
        {
            "plan_id": "P3",
            "claim": "Use alternate valid plan.",
            "why": "May improve performance but evidence is missing.",
            "valid_under_contracts": True,
            "dominated": False,
            "strengths": ["possible performance"],
            "weaknesses": ["missing benchmark"],
            "evidence": ["P3"],
        }
    )
    leader = ExecutionLeader(tmp_path)

    report = leader.start_run(payload)

    assert isinstance(report, FinalExecutionReport)
    assert report.decision == "request_test_measurement"
    assert report.next_action["target"] == "test"


def test_multiple_non_dominated_plans_request_debate(tmp_path):
    payload = _request()
    payload["candidate_plans"].append(
        {
            "plan_id": "P3",
            "claim": "Use alternate valid ownership split.",
            "why": "Valid but has different risk trade-offs.",
            "valid_under_contracts": True,
            "dominated": False,
            "strengths": ["different ownership"],
            "weaknesses": ["more integration cost"],
            "evidence": ["P3"],
        }
    )
    leader = ExecutionLeader(tmp_path)

    report = leader.start_run(payload)

    assert isinstance(report, FinalExecutionReport)
    assert report.decision == "request_debate"
    assert report.next_action["target"] == "debate"


def test_invalid_split_same_file_is_rejected(tmp_path):
    payload = _request()
    payload["subtasks"][1]["file_changes"][0]["path"] = "a.txt"
    leader = ExecutionLeader(tmp_path)

    with pytest.raises(ExecutionContractError):
        leader.start_run(payload)


def test_execution_group_rework_success_release_and_causal_chain(tmp_path):
    leader = ExecutionLeader(tmp_path)
    state = leader.start_run(_request())
    assert isinstance(state, ExecutionRunState)
    assert state.decision == "send_implementation_candidate_to_test"
    assert [group.status for group in state.groups] == ["UNDER_TEST", "UNDER_TEST"]

    state = leader.handle_test_feedback(
        state,
        {
            "feedback_id": "failure-001",
            "result": "failed",
            "evidence_refs": ["log:missing-b"],
            "covered_scope": ["b fixture"],
            "owner_type": "group",
            "owner_id": "G2",
            "required_fix": "Add missing rework note.",
            "why": "Test found missing output in G2 scope.",
        },
    )
    assert isinstance(state, ExecutionRunState)
    assert state.group_by_id("G2").rework_history
    assert state.status == "WAITING_FOR_TEST"

    report = leader.handle_test_feedback(
        state,
        {
            "feedback_id": "success-001",
            "result": "passed",
            "evidence_refs": ["log:all-pass"],
            "covered_scope": ["all fixture scope"],
            "owner_type": "none",
            "why": "All demo checks passed.",
        },
    )
    assert isinstance(report, FinalExecutionReport)
    data = report.to_dict()
    assert data["decision"] == "submit_causal_fork_to_master"
    assert data["final_status"] == "test_passed"
    assert all(group["status"] == "RELEASED" for group in data["group_records"])
    assert data["execution_causal_chain"]["nodes"]
    assert data["execution_causal_chain"]["edges"]
    assert data["execution_causal_chain"]["status"] == "causal_candidate"
    assert Path(data["artifact_paths"]["final_report"]).is_file()
