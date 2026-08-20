from __future__ import annotations

import re
from typing import Any


_ACTION_ID = "019fa1ff-8282-7000-8000-000000000101"
_OPENED_EVENT_ID = "019fa1ff-8282-7000-8000-000000000102"
_ATTEMPT_ID = "019fa1ff-8282-7000-8000-000000000103"
_SOURCE_GENERATION_ID = "019fa1ff-8282-7502-89ba-000000000502"
_ROLE_NAMES = {
    "A": "TEST_PLAN_AUTHOR",
    "B": "TEST_PLAN_REVIEWER",
    "C": "TEST_EXECUTOR",
    "D": "TEST_RESULT_REVIEWER",
    "E": "TEST_REPORT_WRITER",
    "F": "FINAL_REVIEWER",
}


def _mask(mask_name: str) -> int:
    match = re.fullmatch(r"FACT-MASK-(\d{3})", mask_name)
    if match is None:
        raise ValueError(f"invalid fact mask: {mask_name!r}")
    value = int(match.group(1))
    if not 0 <= value < 128:
        raise ValueError(f"fact mask outside domain: {mask_name!r}")
    return value


def _identity(slot: str, role: str, suffix: str) -> dict[str, Any]:
    return {
        "role_slot_id": slot,
        "role": role,
        "source_generation_id": _SOURCE_GENERATION_ID,
        "instance_revision": 1,
        "agent_handle": f"agent-{slot.lower()}-rev-1",
        "handle_source": "THREAD_SPAWN_AGENT_PATH",
        "thread_id": f"THREAD-{slot}-{suffix}",
        "session_id": f"SESSION-{slot}-{suffix}",
    }


def _blocker(
    owner_role: str,
    origin_role: str,
    source_baseline_id: str,
    test_plan_revision_id: str,
    execution_contract_id: str,
) -> dict[str, Any]:
    return {
        "schema_version": "BlockerRecord.v1",
        "blocker_id": "PROPERTY-BLOCKER-001",
        "fact_type": "PROCESS_BLOCKER",
        "blocker_kind": "PLAN_PROCESS",
        "origin_role": origin_role,
        "owner_role": owner_role,
        "severity": "P1",
        "claim": "A required process condition is not satisfied.",
        "violated_requirement": "REQUIREMENT-PROPERTY-001",
        "evidence_refs": ["EVIDENCE-BLOCKER-OPEN"],
        "required_closure_evidence": [
            "Owner correction bytes.",
            "Independent reviewer verification bytes.",
        ],
        "prohibited_substitutes": [
            "Owner self-assertion.",
            "Numeric confidence.",
        ],
        "affected_artifacts": [
            {
                "artifact_id": "ARTIFACT-PROPERTY-PLAN",
                "run_relative_path": "artifacts/property/plan.json",
                "sha256": "ab" * 32,
            }
        ],
        "affected_case_ids": ["CASE-BLOCKER-001"],
        "source_baseline_id": source_baseline_id,
        "test_plan_revision_id": test_plan_revision_id,
        "execution_contract_id": execution_contract_id,
        "opened_attempt_id": _ATTEMPT_ID,
        "opened_event_id": _OPENED_EVENT_ID,
        "stage_rank": "ABCDEF".index(owner_role) + 1,
        "gate_effect": "BLOCKING",
        "status": "OPEN",
        "source_report_defect": None,
        "closure_events": [],
    }


def materialize_fact_collections(
    mask_name: str,
    *,
    cancel_state: str,
    owner_role: str,
    origin_role: str,
    source_baseline_id: str,
    test_plan_revision_id: str,
    execution_contract_id: str,
) -> dict[str, Any]:
    mask = _mask(mask_name)
    has = lambda bit: bool(mask & (1 << bit))
    blocker = (
        _blocker(
            owner_role,
            origin_role,
            source_baseline_id,
            test_plan_revision_id,
            execution_contract_id,
        )
        if has(2)
        else None
    )
    blocker_case_ids = ["CASE-BLOCKER-001"] if has(2) else []
    unclassified_case_ids = ["CASE-UNCLASSIFIED-001"] if has(4) else []
    gap_case_ids = ["CASE-GAP-001"] if has(5) else []
    finding_case_ids = ["CASE-FINDING-001"] if has(6) else []
    required = sorted(
        blocker_case_ids
        + unclassified_case_ids
        + gap_case_ids
        + finding_case_ids
    )
    missing = sorted(
        blocker_case_ids + unclassified_case_ids + gap_case_ids
    )
    active = (
        [
            {
                "action_id": _ACTION_ID,
                "registry_snapshot_id": "sha256:" + "61" * 32,
                "target_identity": _identity(
                    "C", _ROLE_NAMES["C"], "c" * 2
                ),
                "last_state": "IN_PROGRESS",
                "possible_side_effects": ["External mutation may remain active."],
                "external_job_ids": [],
                "follow_up_method": "Inspect the immutable action receipt stream.",
                "evidence_refs": ["EVIDENCE-ACTION-ACTIVE"],
                "last_observed_at_utc": "2026-07-27T08:00:00Z",
                "last_observed_event_id": _OPENED_EVENT_ID,
            }
        ]
        if cancel_state == "TERMINATED_WITH_ACTIVE_WORK"
        else []
    )
    unknown_side_effects = (
        [
            {
                "side_effect_id": "SIDE-EFFECT-PROPERTY-001",
                "action_id": _ACTION_ID,
                "operation": "WRITE_EXTERNAL_STATE",
                "location": "external://property/target",
                "last_known_state": "UNKNOWN",
                "possible_side_effects": ["One write may have committed."],
                "owner": _identity("C", "TEST_EXECUTOR", "c" * 2),
                "follow_up_method": "Inspect the external audit log.",
                "evidence_refs": ["EVIDENCE-SIDE-EFFECT-001"],
                "opened_event_id": _OPENED_EVENT_ID,
            }
        ]
        if has(0)
        else []
    )
    environment_gaps = (
        [
            {
                "schema_version": "EnvironmentGap.v1",
                "gap_id": "GAP-PROPERTY-001",
                "fact_type": "ENVIRONMENT_GAP",
                "case_id": "CASE-GAP-001",
                "claim": "Required execution environment is unavailable.",
                "environment_component": "ENVIRONMENT-PROPERTY-001",
                "unavailable_evidence": ["Real-device execution evidence."],
                "resolution": "OPEN",
                "opening_evidence_refs": ["EVIDENCE-GAP-OPEN"],
                "resolution_evidence_refs": [],
                "producer_identity": _identity(
                    "C", "TEST_EXECUTOR", "c" * 2
                ),
                "reviewer_identity": _identity(
                    "D", "TEST_RESULT_REVIEWER", "d" * 2
                ),
                "source_baseline_id": source_baseline_id,
                "test_plan_revision_id": test_plan_revision_id,
                "execution_contract_id": execution_contract_id,
                "opened_attempt_id": _ATTEMPT_ID,
                "opened_event_id": _OPENED_EVENT_ID,
                "resolved_event_id": None,
            }
        ]
        if has(5)
        else []
    )
    product_findings = (
        [
            {
                "schema_version": "ProductFinding.v1",
                "finding_id": "FINDING-PROPERTY-001",
                "fact_type": "PRODUCT_FINDING",
                "case_id": "CASE-FINDING-001",
                "requirement_id": "REQUIREMENT-PROPERTY-001",
                "severity": "P1",
                "claim": "Observed behavior violates the requirement.",
                "expected_behavior": "The required behavior is observed.",
                "observed_behavior": "The required behavior is absent.",
                "verification_state": "CONFIRMED",
                "evidence_refs": ["EVIDENCE-FINDING-001"],
                "producer_identity": _identity(
                    "C", "TEST_EXECUTOR", "c" * 2
                ),
                "verification_identity": _identity(
                    "D", "TEST_RESULT_REVIEWER", "d" * 2
                ),
                "source_baseline_id": source_baseline_id,
                "test_plan_revision_id": test_plan_revision_id,
                "execution_contract_id": execution_contract_id,
                "opened_attempt_id": _ATTEMPT_ID,
                "opened_event_id": _OPENED_EVENT_ID,
                "verification_event_id": (
                    "019fa1ff-8282-7000-8000-000000000104"
                ),
            }
        ]
        if has(6)
        else []
    )
    return {
        "approved_case_ids": required,
        "required_case_ids": required,
        "d_accepted_required_case_ids": finding_case_ids,
        "missing_required_case_ids": missing,
        "open_required_environment_gap_case_ids": (
            gap_case_ids
        ),
        "required_process_blocked_case_ids": (
            blocker_case_ids
        ),
        "unclassified_missing_case_ids": (
            unclassified_case_ids
        ),
        "active_or_unverifiable_action_ids": (
            [_ACTION_ID] if active else []
        ),
        "active_or_unverifiable_actions": active,
        "active_external_jobs": [],
        "unknown_side_effects": unknown_side_effects,
        "open_process_blockers": [blocker] if blocker else [],
        "open_upstream_defect_ids": (
            ["UPSTREAM-DEFECT-PROPERTY-001"] if has(1) else []
        ),
        "stagnation_state": "CONFIRMED" if has(3) else "NONE",
        "product_findings": product_findings,
        "environment_gaps": environment_gaps,
    }
