from __future__ import annotations

from pathlib import Path

from aegis_test_runtime import TestLeader


def _request() -> dict:
    return {
        "request_id": "unit-test-runtime-001",
        "source": "execution",
        "objective": "Validate integrated execution candidate.",
        "scope": "docs and fixture output",
        "base_branch": "v0.1.0-alpha",
        "integration_branch": "execution/router-demo/integration",
        "implementation_candidate_ref": "artifact:implementation_candidate.json",
        "final_code_ref": "branch:execution/router-demo/integration",
        "changed_files": ["docs/execution_overview.md", "fixtures/execution_output.txt"],
        "ownership_map": {
            "docs/execution_overview.md": "G1",
            "fixtures/execution_output.txt": "G2",
        },
        "local_test_evidence": ["G1:local-test", "G2:local-test"],
        "back_review_summaries": ["G1:back-review", "G2:back-review"],
        "known_risks": ["fixture output may miss final summary"],
        "expected_test_focus": ["overview exists", "fixture output includes final summary"],
        "success_criteria": ["overview exists", "fixture output includes final summary"],
        "forbidden_actions": ["remote push", "main merge", "release", "bypass_branch_protection"],
        "evidence_refs": ["execution-final-candidate"],
        "candidate_files": {
            "docs/execution_overview.md": "# Execution overview\n",
            "fixtures/execution_output.txt": "status=reworked\nfinal summary: ready\n",
        },
        "requested_actions": [],
    }


def test_missing_handoff_context_returns_request_more_context(tmp_path):
    leader = TestLeader(tmp_path)

    report = leader.run({"request_id": "missing", "source": "execution", "objective": "", "scope": ""}).to_dict()

    assert report["result"] == "request_more_context"
    assert report["feedback_kind"] == "missing_context"
    assert report["next_route"] == "execution"
    assert Path(report["artifact_paths"]["final_report"]).is_file()


def test_passed_candidate_goes_to_final_review_and_retains_reproducibility(tmp_path):
    leader = TestLeader(tmp_path)

    report = leader.run(_request()).to_dict()

    assert report["result"] == "passed"
    assert report["next_route"] == "final_review"
    assert report["decision"] == "send_result_to_final_review"
    assert report["covered_scope"] == ["docs/execution_overview.md", "fixtures/execution_output.txt"]
    assert not report["uncovered_scope"]
    assert Path(report["reproducibility_set_ref"]).is_file()
    assert Path(report["artifact_manifest_ref"]).is_file()
    assert report["causal_boundary"].startswith("Test result is evidence")


def test_failure_routes_to_execution_with_group_owner_hint(tmp_path):
    payload = _request()
    payload["candidate_files"]["fixtures/execution_output.txt"] = "status=initial-candidate\n"
    leader = TestLeader(tmp_path)

    report = leader.run(payload).to_dict()

    assert report["result"] == "failed"
    assert report["feedback_kind"] == "failure"
    assert report["next_route"] == "execution"
    assert report["owner_hint"] == {"owner_type": "group", "owner_id": "G2"}
    assert any(signature.startswith("missing_pattern:fixtures/execution_output.txt") for signature in report["failure_signatures"])


def test_proven_failure_with_ambiguous_owner_remains_failed(tmp_path):
    payload = _request()
    payload["route_specs"] = [
        {
            "route_id": "route.cross_group_behavior",
            "route_type": "integration",
            "mandatory": True,
            "scope": ["docs/execution_overview.md", "fixtures/execution_output.txt"],
            "required_files": ["docs/execution_overview.md", "fixtures/execution_output.txt"],
            "expected_patterns": {"fixtures/execution_output.txt": "final summary"},
            "failure_owner_files": ["docs/execution_overview.md", "fixtures/execution_output.txt"],
            "inspection_steps": ["Validate cross-group final summary behavior."],
        }
    ]
    payload["candidate_files"]["fixtures/execution_output.txt"] = "status=initial-candidate\n"
    leader = TestLeader(tmp_path)

    report = leader.run(payload).to_dict()

    assert report["result"] == "failed"
    assert report["owner_hint"]["owner_type"] == "ambiguous"
    assert report["next_route"] == "execution"


def test_governance_blocker_is_blocked_and_can_go_to_final_review(tmp_path):
    payload = _request()
    payload["requested_actions"] = ["bypass_branch_protection"]
    payload["governance_review_required"] = True
    leader = TestLeader(tmp_path)

    report = leader.run(payload).to_dict()

    assert report["result"] == "blocked"
    assert report["feedback_kind"] == "governance_blocker"
    assert report["blocker_kind"] == "governance"
    assert report["requires_governance_review"] is True
    assert report["next_route"] == "final_review"


def test_mandatory_inconclusive_route_prevents_pass(tmp_path):
    payload = _request()
    payload["route_specs"] = [
        {
            "route_id": "route.unstable",
            "route_type": "environment",
            "mandatory": True,
            "scope": ["fixtures/execution_output.txt"],
            "simulate_result": "inconclusive",
            "inspection_steps": ["Attempt unstable route."],
        }
    ]
    leader = TestLeader(tmp_path)

    report = leader.run(payload).to_dict()

    assert report["result"] == "inconclusive"
    assert report["next_route"] == "execution"
    assert report["decision"] == "send_feedback_to_execution"
