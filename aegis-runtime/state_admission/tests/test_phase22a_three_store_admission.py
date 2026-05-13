from __future__ import annotations

import json
from pathlib import Path

from aegis_state_admission import validate_candidate, validate_candidate_file


def test_archive_candidate_is_accepted_as_history_not_truth() -> None:
    decision = validate_candidate(
        {
            "candidate_type": "archive",
            "task_id": "T0001",
            "event_type": "task_requested",
            "actor": "developer",
            "occurred_at": "2026-05-12T00:00:00Z",
            "artifact_refs": ["runtime_test_reports/demo.md"],
            "scope": "task T0001",
        }
    )

    payload = decision.to_dict()
    assert payload["decision"] == "accept_archive_candidate"
    assert payload["accepted_status"] == "archive_candidate"
    assert payload["global_causal_truth_mutation"] is False
    assert payload["ordinary_agent_direct_write_allowed"] is False


def test_archive_rejects_truth_claim() -> None:
    decision = validate_candidate(
        {
            "candidate_type": "archive",
            "task_id": "T0002",
            "event_type": "developer_claimed_solution",
            "actor": "developer",
            "occurred_at": "2026-05-12T00:00:00Z",
            "artifact_refs": ["chat:claim"],
            "truth_status": "global_truth",
        }
    )

    assert decision.decision == "reject_wrong_store"
    assert decision.accepted_status == "rejected"


def test_knowledge_candidate_accepts_sourced_static_fact() -> None:
    decision = validate_candidate(
        {
            "candidate_type": "knowledge",
            "statement": "The target sandbox repository is rain-123-bow/aegis-execution-sandbox.",
            "scope": "Aegis Phase 19A/19B sandbox execution",
            "version_context": "v0.1.0-alpha",
            "evidence": [{"type": "report", "ref": "runtime_test_reports/PHASE_19B_EXECUTION_REAL_FRONT_BACK_AGENT_FULL_ACCEPTANCE_REPORT.md"}],
            "master_verified": True,
        }
    )

    assert decision.decision == "accept_knowledge_candidate"
    assert decision.accepted_status == "knowledge_candidate"


def test_knowledge_rejects_causal_shape() -> None:
    decision = validate_candidate(
        {
            "candidate_type": "knowledge",
            "statement": "Because Test Worker proof audit passed, the current release is production ready.",
            "scope": "invalid overclaim",
            "version_context": "v0.1.0-alpha",
            "evidence": ["runtime_test_reports/PHASE_20B_TEST_REAL_WORKER_FULL_ACCEPTANCE_REPORT.md"],
            "master_verified": True,
        }
    )

    assert decision.decision == "reject_wrong_store"
    assert decision.required_next_step == "route_to_causal_admission_if_causal_structure_is_intended"


def test_developer_assertion_needs_more_evidence_for_knowledge() -> None:
    decision = validate_candidate(
        {
            "candidate_type": "knowledge",
            "statement": "The customer requires production deployment today.",
            "scope": "release planning",
            "version_context": "v0.1.0-alpha",
            "evidence": ["chat:developer-claim"],
            "claim_status": "developer_asserted",
        }
    )

    assert decision.decision == "needs_more_evidence"
    assert decision.required_next_step == "master_verify_claim_or_record_assertion_in_archive"


def test_causal_rejects_bare_conclusion() -> None:
    decision = validate_candidate(
        {
            "candidate_type": "causal",
            "statement": "Phase 1 is complete.",
            "scope": "Aegis Phase 1",
            "source_origin": "master_unique_conclusion",
            "assumptions": ["all four departments passed acceptance"],
            "evidence": ["README.md"],
        }
    )

    assert decision.decision == "reject_insufficient_evidence"
    assert "why" in decision.why


def test_debate_leader_causal_candidate_is_staged_only_after_structural_review() -> None:
    decision = validate_candidate(
        {
            "candidate_type": "causal",
            "statement": "State admission must remain Master-owned in Phase 22A.",
            "why": "Three-store mutation is a global governance decision and ordinary agents must not write canonical state.",
            "scope": "Aegis Phase 22A",
            "assumptions": ["Phase 22A does not implement production storage"],
            "evidence": ["aegis-master-kit/master/BUSINESS_STATE_BOUNDARY.md"],
            "source_origin": "debate_leader_adjudication",
            "route_priority": "A",
            "expand_priority": "B",
        }
    )

    assert decision.decision == "stage_causal_candidate"
    assert decision.accepted_status == "causal_candidate"
    assert decision.required_next_step == "future_high_budget_causal_review_before_global_merge"
    assert decision.global_causal_truth_mutation is False
    payload = decision.to_dict()
    assert payload["candidate_admission_only"] is True
    assert payload["canonical_global_merge_allowed"] is False
    assert payload["store_write_performed"] is False
    assert "not canonical/global causal truth" in payload["why"]


def test_master_unique_conclusion_is_staged_not_merged() -> None:
    decision = validate_candidate(
        {
            "candidate_type": "causal",
            "statement": "Three-store admission must remain Master-owned in Phase 22A.",
            "why": "Three-store writes are global governance state changes and ordinary agents must not mutate canonical stores.",
            "scope": "Aegis Phase 22A",
            "assumptions": ["Phase 22A implements admission governance, not production storage"],
            "evidence": ["aegis-master-kit/master/BUSINESS_STATE_BOUNDARY.md"],
            "source_origin": "master_unique_conclusion",
        }
    )

    payload = decision.to_dict()
    assert decision.decision == "stage_causal_candidate"
    assert decision.accepted_status == "causal_candidate"
    assert decision.required_next_step == "future_high_budget_causal_review_before_global_merge"
    assert payload["candidate_admission_only"] is True
    assert payload["canonical_global_merge_allowed"] is False
    assert payload["store_write_performed"] is False
    assert payload["global_causal_truth_mutation"] is False


def test_debate_leader_incomplete_causal_chain_needs_more_evidence_before_staging() -> None:
    decision = validate_candidate(
        {
            "candidate_type": "causal",
            "statement": "This Debate Leader conclusion is incomplete.",
            "why": "It lacks evidence and assumptions.",
            "scope": "Aegis Phase 22A",
            "source_origin": "debate_leader_adjudication",
        }
    )

    assert decision.decision == "reject_insufficient_evidence"
    assert decision.accepted_status == "rejected"
    assert "missing required field" in decision.why


def test_debate_worker_local_causal_is_rejected() -> None:
    decision = validate_candidate(
        {
            "candidate_type": "causal",
            "statement": "Local stance hypothesis.",
            "why": "A worker used this during debate.",
            "scope": "local debate stance",
            "assumptions": ["local only"],
            "evidence": ["worker_state.json"],
            "source_origin": "debate_worker_local",
        }
    )

    assert decision.decision == "reject_local_only_causal"


def test_causal_direct_global_write_is_rejected() -> None:
    decision = validate_candidate(
        {
            "candidate_type": "causal",
            "statement": "Write me as active truth.",
            "why": "Invalid direct write attempt.",
            "scope": "invalid",
            "assumptions": ["none"],
            "evidence": ["bad.json"],
            "source_origin": "master_unique_conclusion",
            "global_causal_truth_mutation": True,
        }
    )

    assert decision.decision == "reject_direct_global_write"
    assert decision.production_storage_mutation is False
    payload = decision.to_dict()
    assert payload["candidate_admission_only"] is True
    assert payload["canonical_global_merge_allowed"] is False
    assert payload["store_write_performed"] is False
    assert payload["global_causal_truth_mutation"] is False
    assert payload["production_storage_mutation"] is False


def test_execution_leader_non_unique_path_routes_to_debate() -> None:
    decision = validate_candidate(
        {
            "candidate_type": "causal",
            "statement": "Implementation path A is best.",
            "why": "There are several viable paths but A looks simpler.",
            "scope": "Execution planning",
            "assumptions": ["two or more plans exist"],
            "evidence": ["execution_plan.json"],
            "source_origin": "execution_leader_directional_reasoning",
            "implementation_path_unique": False,
        }
    )

    assert decision.decision == "needs_debate"


def test_cli_validates_candidate_file(tmp_path: Path) -> None:
    path = tmp_path / "candidate.json"
    path.write_text(
        json.dumps(
            {
                "candidate_type": "archive",
                "task_id": "TCLI",
                "event_type": "result_recorded",
                "actor": "master",
                "occurred_at": "2026-05-12T00:00:00Z",
                "artifact_refs": ["artifact:result"],
            }
        ),
        encoding="utf-8",
    )

    decision = validate_candidate_file(path)
    assert decision.decision == "accept_archive_candidate"
