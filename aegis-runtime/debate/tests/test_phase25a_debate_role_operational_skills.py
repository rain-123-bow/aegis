from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from aegis_debate_runtime.operational_skill import validate_debate_skill_run


def _skill_ref(skill_id: str, version: str = "v0.1") -> dict:
    return {"skill_id": skill_id, "skill_version": version}


def _state(stance_id: str) -> dict:
    return {
        "stance_id": stance_id,
        "claim": f"claim {stance_id}",
        "why": f"why {stance_id}",
        "evidence": [{"type": "test", "ref": f"{stance_id}.md", "relevance": "demo"}],
        "scope": "demo scope",
        "assumptions": ["demo assumption"],
        "depends_on": [],
        "rejected_attacks": [],
        "accepted_weaknesses": [],
        "scope_narrowing_history": [],
        "invalidation_conditions": ["input changes"],
        "risk_if_wrong": "wrong decision",
        "route_priority": [{"id": stance_id, "route_grade": "A", "reason": "core stance"}],
        "expand_priority": [{"id": stance_id, "expand_grade": "A", "reason": "core stance"}],
        "status": "active",
    }


def _worker_output(stance_id: str, **overrides) -> dict:
    payload = {
        "worker_id": f"worker-{stance_id}",
        "role_id": "debate_worker",
        "stance_id": stance_id,
        "skill_ref": _skill_ref("DEBATE_WORKER_OPERATIONAL_SKILL"),
        "skill_received": True,
        "skill_applied": True,
        "stance_binding_verified": True,
        "exactly_one_stance": True,
        "worker_local_causal_state": _state(stance_id),
        "turn_results": [
            {
                "turn_type": "defend",
                "claim": f"claim {stance_id}",
                "why": f"why {stance_id}",
                "new_information": True,
            }
        ],
        "final_adjudication_attempted": False,
        "global_truth_claimed": False,
        "persistent_identity_requested": False,
    }
    payload.update(overrides)
    return payload


def _valid_run(**overrides) -> dict:
    payload = {
        "run_id": "DR-001",
        "skill_ref": _skill_ref("DEBATE_LEADER_OPERATIONAL_SKILL"),
        "admission": {"decision": "accept_for_debate", "why": "two defensible stances exist"},
        "stances": [
            {"stance_id": "S1", "claim": "Use A", "scope": "demo", "assumptions": ["A is feasible"]},
            {"stance_id": "S2", "claim": "Use B", "scope": "demo", "assumptions": ["B is feasible"]},
        ],
        "worker_creation_requests": [
            {
                "worker_id": "worker-S1",
                "role_id": "debate_worker",
                "stance_id": "S1",
                "worker_skill_ref": _skill_ref("DEBATE_WORKER_OPERATIONAL_SKILL"),
                "stance_bound": True,
                "one_stance_only": True,
            },
            {
                "worker_id": "worker-S2",
                "role_id": "debate_worker",
                "stance_id": "S2",
                "worker_skill_ref": _skill_ref("DEBATE_WORKER_OPERATIONAL_SKILL"),
                "stance_bound": True,
                "one_stance_only": True,
            },
        ],
        "worker_outputs": [_worker_output("S1"), _worker_output("S2")],
        "adjudicator_causal_state": {
            "candidate_positions": [
                {"stance_id": "S1", "claim": "Use A", "current_status": "selected_candidate"},
                {"stance_id": "S2", "claim": "Use B", "current_status": "rejected"},
            ],
            "selected_candidate": {"stance_id": "S1", "why_currently_strongest": "better evidence"},
            "rejected_candidates": [{"stance_id": "S2", "decisive_failure": "higher risk", "reopen_if": "new evidence"}],
            "scoped_candidates": [],
            "unresolved_conflicts": [],
            "decisive_evidence": [{"type": "test", "ref": "evidence.md", "relevance": "supports S1"}],
            "missing_evidence": [],
            "risk_ranking": [{"stance_id": "S1", "risk_if_wrong": "low", "risk_grade": "low"}],
            "route_priority": [{"id": "S1", "route_grade": "A", "reason": "selected"}],
            "expand_priority": [{"id": "S1", "expand_grade": "A", "reason": "selected"}],
            "stop_reason": "S1 causally stronger",
            "developer_decision_required": False,
            "developer_decision_reason": None,
        },
        "final_report": {
            "adjudication_decision": "accept_one",
            "developer_decision_required": False,
            "rejected_alternatives": [{"stance_id": "S2", "why_rejected": "higher risk", "decisive_failure": "risk", "reopen_if": "new evidence"}],
            "causal_result": {
                "statement": "Use A in demo scope.",
                "why": "S1 has stronger evidence and lower risk.",
                "evidence": [{"type": "test", "ref": "evidence.md", "relevance": "supports S1"}],
                "scope": "demo",
                "assumptions": ["A remains feasible"],
                "depends_on": [],
                "invalidates": [],
                "supersedes": [],
                "risk_if_wrong": "low",
                "invalidation_conditions": ["new evidence contradicts S1"],
                "next_action": {"target": "master", "recommendation": "stage causal candidate"},
                "confidence": "medium",
                "status": "causal_candidate",
            },
            "causal_chain": {
                "chain_id": "chain-demo-001",
                "source_request_id": "REQ-1",
                "decision_problem": "Choose A or B",
                "selected_stance_id": "S1",
                "nodes": [
                    {
                        "id": "N1",
                        "type": "stance_claim",
                        "stance_id": "S1",
                        "worker_id": "worker-S1",
                        "statement": "Use A.",
                        "why": "A has stronger evidence in this demo scope.",
                        "evidence_refs": ["evidence.md"],
                        "assumptions": ["A remains feasible"],
                        "scope": "demo",
                        "confidence": "medium",
                    },
                    {
                        "id": "N2",
                        "type": "selection_reason",
                        "stance_id": "S1",
                        "worker_id": "worker-S1",
                        "statement": "S1 is selected.",
                        "why": "S1 has lower risk than S2.",
                        "evidence_refs": ["evidence.md"],
                        "assumptions": ["risk comparison is valid"],
                        "scope": "demo",
                        "confidence": "medium",
                    },
                    {
                        "id": "N3",
                        "type": "alternative_rejection",
                        "stance_id": "S2",
                        "worker_id": "worker-S2",
                        "statement": "S2 is rejected.",
                        "why": "S2 has higher risk in this demo scope.",
                        "evidence_refs": ["evidence.md"],
                        "assumptions": ["risk comparison is valid"],
                        "scope": "demo",
                        "confidence": "medium",
                    },
                    {
                        "id": "N4",
                        "type": "invalidation_condition",
                        "stance_id": "S1",
                        "worker_id": None,
                        "statement": "New evidence contradicts S1.",
                        "why": "Contradictory evidence would reopen the selected path.",
                        "evidence_refs": ["evidence.md"],
                        "assumptions": ["future evidence may change"],
                        "scope": "demo",
                        "confidence": "medium",
                    },
                ],
                "edges": [
                    {"id": "E1", "from": "N1", "to": "N2", "relation": "supports_selection", "why": "S1 claim supports the selection reason."},
                    {"id": "E2", "from": "N3", "to": "N2", "relation": "supports_selection", "why": "Rejecting S2 strengthens S1 selection."},
                    {"id": "E3", "from": "N4", "to": "N2", "relation": "reopens_if", "why": "N4 would reopen the selected decision."},
                ],
                "selected_path": ["N1", "N2"],
                "rejected_paths": [{"stance_id": "S2", "rejection_node_ids": ["N3"], "decisive_edge_ids": ["E2"]}],
                "unresolved_questions": [],
                "invalidation_entrypoints": [{"condition_node_id": "N4", "reopens_node_ids": ["N2"]}],
            },
            "global_causal_truth_merge_performed": False,
        },
        "causal_package": {
            "files": [
                "README.md",
                "final_report.json",
                "adjudicator_causal_state.json",
                "worker_states/worker-S1.json",
                "worker_states/worker-S2.json",
                "worker_proofs/worker-S1_proof.json",
                "worker_proofs/worker-S2_proof.json",
                "transcript_digest.json",
                "evidence_manifest.json",
            ]
        },
        "cleanup": {"temporary_workers_released_or_marked_for_cleanup": True},
        "boundaries": {
            "global_causal_truth_merge_performed": False,
            "production_store_write_performed": False,
            "remote_push_performed": False,
            "pull_request_created": False,
            "remote_merge_performed": False,
            "release_performed": False,
        },
    }
    payload.update(overrides)
    return payload


def test_valid_debate_skill_run_passes() -> None:
    result = validate_debate_skill_run(_valid_run()).to_dict()
    assert result["status"] == "validated"
    assert result["decision"] == "accepted_debate_role_skill_enforcement"
    assert result["stance_count"] == 2
    assert result["worker_skill_installation_verified"] is True
    assert result["worker_skill_outputs_verified"] is True


def test_missing_leader_skill_ref_rejected() -> None:
    run = _valid_run(skill_ref={"skill_id": "WRONG", "skill_version": "v0.1"})
    result = validate_debate_skill_run(run)
    assert result.status == "rejected"
    assert any(v["field"] == "skill_ref" for v in result.violations)


def test_accept_with_single_stance_rejected() -> None:
    run = _valid_run(stances=[{"stance_id": "S1", "claim": "Use A", "scope": "demo", "assumptions": ["A"]}])
    run["worker_creation_requests"] = [run["worker_creation_requests"][0]]
    run["worker_outputs"] = [run["worker_outputs"][0]]
    result = validate_debate_skill_run(run)
    assert result.status == "rejected"
    assert any(v["field"] == "stances" for v in result.violations)


def test_worker_creation_without_worker_skill_ref_rejected() -> None:
    run = _valid_run()
    run["worker_creation_requests"][0].pop("worker_skill_ref")
    result = validate_debate_skill_run(run)
    assert result.status == "rejected"
    assert any(v["field"] == "worker_creation_requests.worker_skill_ref" for v in result.violations)


def test_missing_worker_for_stance_rejected() -> None:
    run = _valid_run()
    run["worker_creation_requests"] = [run["worker_creation_requests"][0]]
    result = validate_debate_skill_run(run)
    assert result.status == "rejected"
    assert any("Missing Worker creation" in v["reason"] for v in result.violations)


def test_worker_output_without_skill_ref_rejected() -> None:
    run = _valid_run()
    run["worker_outputs"][0].pop("skill_ref")
    result = validate_debate_skill_run(run)
    assert result.status == "rejected"
    assert any(v["field"] == "worker_outputs.skill_ref" for v in result.violations)


def test_worker_missing_local_causal_state_rejected() -> None:
    run = _valid_run()
    run["worker_outputs"][0].pop("worker_local_causal_state")
    result = validate_debate_skill_run(run)
    assert result.status == "rejected"
    assert any(v["field"] == "worker_outputs.worker_local_causal_state" for v in result.violations)


def test_worker_missing_route_priority_rejected() -> None:
    run = _valid_run()
    run["worker_outputs"][0]["worker_local_causal_state"].pop("route_priority")
    result = validate_debate_skill_run(run)
    assert result.status == "rejected"
    assert any("route_priority" in v["field"] for v in result.violations)


def test_worker_final_adjudication_attempt_rejected() -> None:
    run = _valid_run()
    run["worker_outputs"][0]["final_adjudication_attempted"] = True
    result = validate_debate_skill_run(run)
    assert result.status == "rejected"
    assert any(v["field"] == "worker_outputs.final_adjudication_attempted" for v in result.violations)


def test_worker_global_truth_claim_rejected() -> None:
    run = _valid_run()
    run["worker_outputs"][0]["global_truth_claimed"] = True
    result = validate_debate_skill_run(run)
    assert result.status == "rejected"
    assert any(v["field"] == "worker_outputs.global_truth_claimed" for v in result.violations)


def test_missing_adjudicator_state_rejected() -> None:
    run = _valid_run()
    run.pop("adjudicator_causal_state")
    result = validate_debate_skill_run(run)
    assert result.status == "rejected"
    assert any(v["field"] == "adjudicator_causal_state" for v in result.violations)


def test_developer_decision_required_must_be_preserved() -> None:
    run = _valid_run()
    run["adjudicator_causal_state"]["developer_decision_required"] = True
    run["adjudicator_causal_state"]["developer_decision_reason"] = "causal_equipoise"
    run["final_report"]["developer_decision_required"] = False
    result = validate_debate_skill_run(run)
    assert result.status == "rejected"
    assert any(v["field"] == "final_report.developer_decision_required" for v in result.violations)



def test_missing_causal_chain_rejected() -> None:
    run = _valid_run()
    run["final_report"].pop("causal_chain")
    result = validate_debate_skill_run(run)
    assert result.status == "rejected"
    assert any(v["field"] == "final_report.causal_chain" for v in result.violations)


def test_malformed_causal_chain_rejected() -> None:
    run = _valid_run()
    run["final_report"]["causal_chain"]["nodes"] = []
    result = validate_debate_skill_run(run)
    assert result.status == "rejected"
    assert any(v["field"] == "final_report.causal_chain.nodes" for v in result.violations)

def test_missing_causal_package_file_rejected() -> None:
    run = _valid_run()
    run["causal_package"]["files"].remove("final_report.json")
    result = validate_debate_skill_run(run)
    assert result.status == "rejected"
    assert any(v["field"] == "causal_package.files" for v in result.violations)


def test_cleanup_missing_rejected() -> None:
    run = _valid_run(cleanup={"temporary_workers_released_or_marked_for_cleanup": False})
    result = validate_debate_skill_run(run)
    assert result.status == "rejected"
    assert any(v["field"] == "cleanup.temporary_workers_released_or_marked_for_cleanup" for v in result.violations)


def test_global_causal_truth_merge_flag_rejected() -> None:
    run = _valid_run(boundaries={"global_causal_truth_merge_performed": True})
    result = validate_debate_skill_run(run)
    assert result.status == "rejected"
    assert any(v["field"] == "global_causal_truth_merge_performed" for v in result.violations)


def test_rejected_admission_must_not_create_workers() -> None:
    run = _valid_run(admission={"decision": "reject_no_debate_needed"})
    result = validate_debate_skill_run(run)
    assert result.status == "rejected"
    assert any(v["field"] == "worker_creation_requests" for v in result.violations)


def test_cli_writes_validation_result(tmp_path: Path) -> None:
    run_path = tmp_path / "run.json"
    out_path = tmp_path / "result.json"
    run_path.write_text(json.dumps(_valid_run()), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "aegis_debate_runtime.operational_skill",
            "validate",
            "--run",
            str(run_path),
            "--output",
            str(out_path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "accepted_debate_role_skill_enforcement" in completed.stdout
    assert json.loads(out_path.read_text(encoding="utf-8"))["status"] == "validated"


def test_superseded_role_contracts_removed() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    debate_root = repo_root / "aegis-master-kit" / "organization" / "departments" / "debate"
    removed = [
        "DEBATE_LEADER_CONTRACT.md",
        "DEBATE_WORKER_CONTRACT.md",
        "DEBATE_WORKER_CAUSAL_STATE_CONTRACT.md",
        "DEBATE_ADJUDICATOR_CAUSAL_STATE_CONTRACT.md",
        "ADJUDICATION_AND_CAUSAL_OUTPUT_RULES.md",
    ]
    for name in removed:
        assert not (debate_root / name).exists(), f"superseded contract still exists: {name}"
