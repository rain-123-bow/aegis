from __future__ import annotations

import json
from pathlib import Path

from aegis_causal_review import validate_review_file, validate_review_request


def _candidate(**overrides):
    base = {
        "candidate_id": "C0001",
        "accepted_status": "causal_candidate",
        "statement": "Three-store admission must remain Master-owned.",
        "why": "Three-store writes are global governance state changes and ordinary agents must not mutate canonical stores.",
        "scope": "Aegis Phase 22A/22B",
        "assumptions": ["Phase 22B reviews candidates but does not write stores"],
        "evidence": ["aegis-master-kit/master/THREE_STORE_ADMISSION_POLICY.md"],
        "source_origin": "master_unique_conclusion",
    }
    base.update(overrides)
    return base


def _request(**overrides):
    base = {
        "causal_candidate": _candidate(),
        "knowledge_context": [
            {
                "id": "K0001",
                "statement": "Archive, Knowledge, and Causal stores are separate.",
                "scope": "Aegis",
                "evidence": ["aegis-master-kit/master/BUSINESS_STATE_BOUNDARY.md"],
            }
        ],
        "causal_context": [
            {
                "id": "F0001",
                "statement": "Master owns global governance boundaries.",
                "scope": "Aegis",
                "status": "active",
            }
        ],
        "master_confidence": {
            "type": "test_evidence_backed",
            "value": "passed",
            "evidence_refs": ["pytest:phase22b causal review test suite"],
        },
        "review_policy": {"statistical_confidence_threshold": 0.95},
    }
    base.update(overrides)
    return base


def test_test_evidence_backed_master_unique_candidate_stages_merge_candidate() -> None:
    decision = validate_review_request(_request())

    payload = decision.to_dict()
    assert decision.decision == "stage_canonical_merge_candidate"
    assert decision.accepted_status == "canonical_merge_candidate"
    assert decision.required_next_step == "phase22c_causal_store_persistence"
    assert payload["canonical_global_merge_performed"] is False
    assert payload["production_store_write_performed"] is False
    assert payload["causal_store_write_performed"] is False
    assert payload["knowledge_context_used"] == ["K0001"]
    assert payload["causal_context_used"] == ["F0001"]
    assert payload["master_confidence"]["type"] == "test_evidence_backed"
    assert payload["master_confidence"]["evidence_refs"] == ["pytest:phase22b causal review test suite"]


def test_statistical_high_confidence_stages_merge_candidate_when_data_backed() -> None:
    decision = validate_review_request(
        _request(
            master_confidence={
                "type": "statistical",
                "value": 0.98,
                "evidence_refs": ["experiment:latency-benchmark-n100"],
            },
            review_policy={"statistical_confidence_threshold": 0.95},
        )
    )

    payload = decision.to_dict()
    assert decision.decision == "stage_canonical_merge_candidate"
    assert payload["master_confidence"]["type"] == "statistical"
    assert payload["master_confidence"]["value"] == 0.98
    assert payload["master_confidence"]["evidence_refs"] == ["experiment:latency-benchmark-n100"]


def test_contract_proven_confidence_stages_merge_candidate_when_evidence_refs_exist() -> None:
    decision = validate_review_request(
        _request(
            master_confidence={
                "type": "contract_proven",
                "value": "proven",
                "evidence_refs": ["aegis-master-kit/master/MASTER_CAUSAL_REVIEW_GOVERNANCE_POLICY.md"],
            }
        )
    )

    payload = decision.to_dict()
    assert decision.decision == "stage_canonical_merge_candidate"
    assert payload["master_confidence"]["type"] == "contract_proven"


def test_deterministic_proof_confidence_stages_merge_candidate_when_verified() -> None:
    decision = validate_review_request(
        _request(
            master_confidence={
                "type": "deterministic_proof",
                "value": "verified",
                "evidence_refs": ["static:topology-diff-no-router-change"],
            }
        )
    )

    assert decision.decision == "stage_canonical_merge_candidate"


def test_static_analysis_backed_confidence_stages_merge_candidate_when_evidence_refs_exist() -> None:
    decision = validate_review_request(
        _request(
            master_confidence={
                "type": "static_analysis_backed",
                "value": "passed",
                "evidence_refs": ["grep:no-State-Admission-Department"],
            }
        )
    )

    assert decision.decision == "stage_canonical_merge_candidate"


def test_high_confidence_type_without_evidence_refs_is_not_decisive() -> None:
    decision = validate_review_request(
        _request(
            master_confidence={
                "type": "contract_proven",
                "value": "proven"
            },
            alternatives=[],
        )
    )

    assert decision.decision == "needs_more_evidence"
    assert "high-confidence support" in decision.why


def test_heuristic_uncertainty_requires_developer_decision_package() -> None:
    decision = validate_review_request(
        _request(
            master_confidence={"type": "heuristic", "value": 0.62},
            alternatives=[
                {
                    "id": "A",
                    "conclusion": "Stage candidate under current scope.",
                    "probability": 0.62,
                    "probability_type": "heuristic",
                    "risk_if_wrong": "Future agents may over-trust a weak causal premise.",
                },
                {
                    "id": "B",
                    "conclusion": "Reject until more evidence exists.",
                    "probability": 0.38,
                    "probability_type": "heuristic",
                    "risk_if_wrong": "Progress may be delayed.",
                },
            ],
            master_recommendation="Prefer rejection until stronger evidence exists.",
        )
    )

    payload = decision.to_dict()
    assert decision.decision == "developer_decision_required"
    assert payload["developer_decision_required"] is True
    assert payload["developer_owns_decisive_responsibility"] is True
    assert payload["archive_event_candidate_required"] is True
    assert payload["archive_event_candidate"]["event_type"] == "developer_decision_required"
    assert payload["canonical_global_merge_performed"] is False


def test_heuristic_without_alternatives_needs_more_evidence() -> None:
    decision = validate_review_request(
        _request(
            master_confidence={"type": "heuristic", "value": 0.7},
            alternatives=[],
        )
    )

    assert decision.decision == "needs_more_evidence"
    assert decision.accepted_status == "needs_more_evidence"


def test_conflict_with_existing_causal_requires_developer_or_debate() -> None:
    decision = validate_review_request(
        _request(
            master_confidence={"type": "heuristic", "value": 0.55},
            causal_context=[
                {
                    "id": "F0099",
                    "statement": "Existing active causal fact conflicts with candidate.",
                    "scope": "Aegis Phase 22B",
                    "status": "active",
                    "conflicts_with_candidate": True,
                }
            ],
            alternatives=[
                {
                    "id": "A",
                    "conclusion": "Candidate supersedes F0099.",
                    "probability": 0.55,
                    "probability_type": "heuristic",
                    "risk_if_wrong": "Invalidates a useful old premise.",
                },
                {
                    "id": "B",
                    "conclusion": "Keep F0099 and reject candidate.",
                    "probability": 0.45,
                    "probability_type": "heuristic",
                    "risk_if_wrong": "Preserves stale reasoning.",
                },
            ],
        )
    )

    assert decision.decision == "developer_decision_required"
    assert "F0099" in decision.conflicts


def test_conflict_without_alternatives_routes_to_debate() -> None:
    decision = validate_review_request(
        _request(
            causal_context=[
                {
                    "id": "F0099",
                    "statement": "Existing active causal fact conflicts with candidate.",
                    "scope": "Aegis Phase 22B",
                    "status": "active",
                    "conflicts_with_candidate": True,
                }
            ],
            alternatives=[],
        )
    )

    assert decision.decision == "needs_debate"


def test_scope_overclaim_can_stage_scope_limited_candidate_with_high_confidence() -> None:
    decision = validate_review_request(
        _request(
            causal_candidate=_candidate(
                scope="global production all projects",
                scope_overclaim=True,
                proposed_scope_limit="Aegis Phase 22B only",
            )
        )
    )

    assert decision.decision == "stage_scope_limited_merge_candidate"
    assert decision.accepted_status == "scope_limited_merge_candidate"
    assert decision.scope == "Aegis Phase 22B only"


def test_scope_overclaim_without_limit_is_rejected() -> None:
    decision = validate_review_request(
        _request(
            causal_candidate=_candidate(
                scope="global production all projects",
                scope_overclaim=True,
            )
        )
    )

    assert decision.decision == "reject_candidate"


def test_supersession_requires_loaded_existing_causal_fact() -> None:
    decision = validate_review_request(
        _request(causal_candidate=_candidate(supersedes=["F_DOES_NOT_EXIST"]))
    )

    assert decision.decision == "needs_more_evidence"
    assert "supersedes references" in decision.why


def test_high_confidence_supersession_stages_candidate_when_reference_loaded() -> None:
    decision = validate_review_request(
        _request(causal_candidate=_candidate(supersedes=["F0001"]))
    )

    assert decision.decision == "stage_supersession_candidate"
    assert decision.accepted_status == "supersession_candidate"
    assert decision.supersedes == ["F0001"]
    assert decision.causal_store_write_performed is False


def test_high_confidence_invalidation_stages_candidate_when_reference_loaded() -> None:
    decision = validate_review_request(
        _request(causal_candidate=_candidate(invalidates=["F0001"]))
    )

    assert decision.decision == "stage_invalidation_candidate"
    assert decision.accepted_status == "invalidation_candidate"
    assert decision.invalidates == ["F0001"]


def test_direct_global_merge_attempt_is_rejected() -> None:
    decision = validate_review_request(
        _request(canonical_global_merge_performed=True)
    )

    payload = decision.to_dict()
    assert decision.decision == "reject_direct_merge_or_store_write"
    assert payload["canonical_global_merge_performed"] is False
    assert payload["production_store_write_performed"] is False
    assert payload["causal_store_write_performed"] is False


def test_missing_knowledge_context_needs_more_evidence() -> None:
    decision = validate_review_request(_request(knowledge_context=[]))

    assert decision.decision == "needs_more_evidence"
    assert "Knowledge context" in decision.why


def test_empty_causal_context_requires_absence_reason() -> None:
    decision = validate_review_request(_request(causal_context=[]))

    assert decision.decision == "needs_more_evidence"
    assert "existing Causal context" in decision.why


def test_empty_causal_context_with_absence_reason_can_pass() -> None:
    decision = validate_review_request(
        _request(causal_context=[], causal_context_absence_reason="No relevant existing causal fact exists.")
    )

    assert decision.decision == "stage_canonical_merge_candidate"


def test_multiple_plausible_paths_routes_to_debate() -> None:
    decision = validate_review_request(_request(multiple_plausible_paths=True))

    assert decision.decision == "needs_debate"


def test_unstaged_candidate_is_rejected() -> None:
    decision = validate_review_request(
        _request(causal_candidate=_candidate(accepted_status="active_global_truth"))
    )

    assert decision.decision == "reject_candidate"
    assert decision.required_next_step == "run_phase22a_structural_admission_first"


def test_cli_validates_review_file(tmp_path: Path) -> None:
    path = tmp_path / "review.json"
    path.write_text(json.dumps(_request()), encoding="utf-8")

    decision = validate_review_file(path)
    assert decision.decision == "stage_canonical_merge_candidate"
