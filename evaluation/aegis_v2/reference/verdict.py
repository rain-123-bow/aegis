from __future__ import annotations

import copy
import re
from typing import Any

from .canonical import verify_self_hash, with_self_hash


FACT_MASK_BITS = {
    "UNKNOWN_SIDE_EFFECT": 0,
    "UPSTREAM_DEFECT": 1,
    "BLOCKING_PROCESS_BLOCKER": 2,
    "STAGNATION_CONFIRMED": 3,
    "UNCLASSIFIED_MISSING_CASE": 4,
    "OPEN_REQUIRED_ENVIRONMENT_GAP": 5,
    "CONFIRMED_PRODUCT_FINDING": 6,
}

PHASE_ROUTES = {
    "PLAN_AUTHOR": ("A", "RULE:PHASE_PLAN_AUTHOR"),
    "PLAN_REVIEW": ("B", "RULE:PHASE_PLAN_REVIEW"),
    "TEST_EXECUTION": ("C", "RULE:PHASE_TEST_EXECUTION"),
    "RESULT_REVIEW": ("D", "RULE:PHASE_RESULT_REVIEW"),
    "REPORT_DRAFT": ("E", "RULE:PHASE_REPORT_DRAFT"),
    "FINAL_REVIEW": ("F", "RULE:PHASE_FINAL_REVIEW"),
}

STANDARD_ASSERTIONS = sorted(
    [
        "ASSERT-EXACT-GRAPH-DECISION-BYTES",
        "ASSERT-HIGHER-PRIORITY-CONDITION-WINS",
        "ASSERT-IDENTICAL-INPUT-IDENTICAL-OUTPUT",
    ]
)


def decode_fact_mask(mask_name: str) -> frozenset[str]:
    match = re.fullmatch(r"FACT-MASK-(\d{3})", mask_name)
    if match is None:
        raise ValueError(f"invalid fact mask: {mask_name!r}")
    mask = int(match.group(1))
    if not 0 <= mask < 128:
        raise ValueError(f"fact mask outside seven-bit domain: {mask_name!r}")
    return frozenset(
        name for name, bit in FACT_MASK_BITS.items() if mask & (1 << bit)
    )


def _reference_result(
    rank: int,
    condition: str,
    outcome: str,
    decision: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    return {
        "algorithm_id": "ORACLE-VERDICT-PRIORITY-TABLE-V1",
        "priority_rank": rank,
        "priority_condition": condition,
        "outcome": outcome,
        "decision": decision,
        "reason_ids": [reason],
        "assertion_ids": STANDARD_ASSERTIONS,
    }


def _assignment_is_schema_compatible(
    assignment: dict[str, Any],
) -> bool:
    if assignment["workflow_integrity"] != "VALID":
        return True
    facts = decode_fact_mask(assignment["fact_mask"])
    phase = assignment["workflow_phase"]
    report = assignment["report_state"]
    if "UNCLASSIFIED_MISSING_CASE" in facts:
        return False
    if (
        "STAGNATION_CONFIRMED" in facts
        and "BLOCKING_PROCESS_BLOCKER" not in facts
    ):
        return False
    if (
        phase == "CANCEL_CONTROL"
        and assignment["cancel_state"] == "NOT_REQUESTED"
    ):
        return False
    if phase in {
        "PLAN_AUTHOR",
        "PLAN_REVIEW",
        "TEST_EXECUTION",
        "RESULT_REVIEW",
    }:
        return report == "NOT_READY"
    if phase == "REPORT_DRAFT":
        return report in {"NOT_READY", "REWORK"}
    if phase == "FINAL_REVIEW":
        return report == "NOT_READY"
    if phase == "TERMINAL_EVALUATION":
        return report == "APPROVED"
    return report != "APPROVED"


def evaluate_verdict_assignment(assignment: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the abstract frozen Cartesian domain without consulting SUT."""

    assignment = copy.deepcopy(assignment)
    if not _assignment_is_schema_compatible(assignment):
        assignment["workflow_integrity"] = "INVALID"
    facts = decode_fact_mask(assignment["fact_mask"])
    cancel_state = assignment["cancel_state"]

    if cancel_state in {"REQUESTED", "QUIESCING"}:
        suffix = "REQUESTED" if cancel_state == "REQUESTED" else "QUIESCING"
        return _reference_result(
            1,
            "CANCEL-REQUESTED",
            "ROUTE",
            {
                "kind": "ROUTE",
                "target_node": "KERNEL_CANCEL_COORDINATOR",
                "reason_ids": [f"RULE:CANCEL_{suffix}"],
            },
            f"REASON-PRIORITY-CANCEL-{suffix}",
        )
    if cancel_state == "TERMINATED_WITH_ACTIVE_WORK":
        return _reference_result(
            2,
            "CANCEL-ACTIVE",
            "TERMINAL",
            {
                "kind": "TERMINAL",
                "verdict": "CANCELLED_WITH_ACTIVE_EXTERNAL_WORK",
            },
            "REASON-PRIORITY-CANCEL-ACTIVE",
        )
    if cancel_state == "QUIESCENT":
        return _reference_result(
            3,
            "CANCEL-QUIESCENT",
            "TERMINAL",
            {"kind": "TERMINAL", "verdict": "CANCELLED_BY_USER"},
            "REASON-PRIORITY-CANCEL-QUIESCENT",
        )
    if assignment["workflow_integrity"] in {"INVALID", "UNKNOWN"}:
        return _reference_result(
            4,
            "INTEGRITY",
            "TERMINAL",
            {"kind": "TERMINAL", "verdict": "INTERNAL_INTEGRITY_ERROR"},
            "REASON-PRIORITY-INTEGRITY",
        )
    if facts & {"UNKNOWN_SIDE_EFFECT", "UPSTREAM_DEFECT"}:
        return _reference_result(
            5,
            "UNKNOWN-UPSTREAM",
            "TERMINAL",
            {"kind": "TERMINAL", "verdict": "NEEDS_MASTER_USER_DISCUSSION"},
            "REASON-PRIORITY-UNKNOWN-UPSTREAM",
        )
    if {
        "BLOCKING_PROCESS_BLOCKER",
        "STAGNATION_CONFIRMED",
    }.issubset(facts):
        return _reference_result(
            6,
            "BLOCKER-STAGNATION",
            "TERMINAL",
            {"kind": "TERMINAL", "verdict": "NEEDS_MASTER_USER_DISCUSSION"},
            "REASON-PRIORITY-BLOCKER-STAGNATION",
        )
    if "BLOCKING_PROCESS_BLOCKER" in facts:
        return _reference_result(
            7,
            "BLOCKER",
            "ROUTE",
            {
                "kind": "ROUTE",
                "target_node": "A",
                "reason_ids": [
                    "RULE:BLOCKING_PROCESS_BLOCKER",
                    "FACT:BLOCKER:PROPERTY-BLOCKER-001",
                ],
            },
            "REASON-PRIORITY-BLOCKER",
        )
    if assignment["evidence_state"] in {
        "INVALID",
        "STALE",
    } or "UNCLASSIFIED_MISSING_CASE" in facts:
        return _reference_result(
            8,
            "EVIDENCE-INVALID",
            "TERMINAL",
            {"kind": "TERMINAL", "verdict": "INTERNAL_INTEGRITY_ERROR"},
            "REASON-PRIORITY-EVIDENCE-INVALID",
        )
    phase = assignment["workflow_phase"]
    if phase in PHASE_ROUTES:
        target, rule = PHASE_ROUTES[phase]
        return _reference_result(
            9,
            "PHASE-ROUTE",
            "ROUTE",
            {"kind": "ROUTE", "target_node": target, "reason_ids": [rule]},
            "REASON-PRIORITY-PHASE-ROUTE",
        )
    if phase == "TERMINAL_EVALUATION" and assignment["report_state"] != "APPROVED":
        return _reference_result(
            10,
            "TERMINAL-EF-INVALID",
            "TERMINAL",
            {"kind": "TERMINAL", "verdict": "INTERNAL_INTEGRITY_ERROR"},
            "REASON-PRIORITY-TERMINAL-EF-INVALID",
        )
    if (
        phase == "TERMINAL_EVALUATION"
        and assignment["report_state"] == "APPROVED"
        and "OPEN_REQUIRED_ENVIRONMENT_GAP" in facts
    ):
        return _reference_result(
            11,
            "REQUIRED-ENV-GAP",
            "TERMINAL",
            {"kind": "TERMINAL", "verdict": "BLOCKED_ENVIRONMENT"},
            "REASON-PRIORITY-REQUIRED-ENV-GAP",
        )
    if (
        phase == "TERMINAL_EVALUATION"
        and assignment["report_state"] == "APPROVED"
        and "CONFIRMED_PRODUCT_FINDING" in facts
        and assignment["coverage_state"]
        in {"COMPLETE", "PARTIAL_SAFETY_POLICY"}
    ):
        return _reference_result(
            12,
            "FINDING",
            "TERMINAL",
            {"kind": "TERMINAL", "verdict": "FAIL_PRODUCT"},
            "REASON-PRIORITY-FINDING",
        )
    if (
        phase == "TERMINAL_EVALUATION"
        and assignment["report_state"] == "APPROVED"
        and assignment["evidence_state"] == "COMPLETE"
        and assignment["coverage_state"] == "COMPLETE"
        and "CONFIRMED_PRODUCT_FINDING" not in facts
        and "OPEN_REQUIRED_ENVIRONMENT_GAP" not in facts
    ):
        return _reference_result(
            13,
            "PASS",
            "TERMINAL",
            {"kind": "TERMINAL", "verdict": "PASS"},
            "REASON-PRIORITY-PASS",
        )
    return _reference_result(
        14,
        "FALLBACK",
        "TERMINAL",
        {"kind": "TERMINAL", "verdict": "NEEDS_MASTER_USER_DISCUSSION"},
        "REASON-PRIORITY-FALLBACK",
    )


def evaluate_verdict_input(subject: dict[str, Any]) -> dict[str, Any]:
    """Apply the same priority table to a complete VerdictInput preimage."""

    blocking = [
        blocker
        for blocker in subject.get("open_process_blockers", [])
        if blocker.get("gate_effect") == "BLOCKING"
    ]
    winning = (
        min(
            blocking,
            key=lambda blocker: (
                blocker["stage_rank"],
                blocker["opened_event_id"],
                blocker["blocker_id"],
            ),
        )
        if blocking
        else None
    )
    facts = {
        "UNKNOWN_SIDE_EFFECT"
        for _ in subject.get("unknown_side_effects", [])
    }
    if subject.get("open_upstream_defect_ids"):
        facts.add("UPSTREAM_DEFECT")
    if winning is not None:
        facts.add("BLOCKING_PROCESS_BLOCKER")
    if subject.get("stagnation_state") == "CONFIRMED":
        facts.add("STAGNATION_CONFIRMED")
    if subject.get("unclassified_missing_case_ids"):
        facts.add("UNCLASSIFIED_MISSING_CASE")
    if subject.get("open_required_environment_gap_case_ids"):
        facts.add("OPEN_REQUIRED_ENVIRONMENT_GAP")
    if any(
        finding.get("verification_state") == "CONFIRMED"
        for finding in subject.get("product_findings", [])
    ):
        facts.add("CONFIRMED_PRODUCT_FINDING")

    mask = sum(1 << FACT_MASK_BITS[fact] for fact in facts)
    assignment = {
        "cancel_state": subject["cancel_state"],
        "workflow_integrity": subject["workflow_integrity"],
        "evidence_state": subject["evidence_state"],
        "coverage_state": subject["coverage_state"],
        "report_state": subject["report_state"],
        "workflow_phase": subject["workflow_phase"],
        "fact_mask": f"FACT-MASK-{mask:03d}",
    }
    result = evaluate_verdict_assignment(assignment)

    if result["priority_rank"] == 7 and winning is not None:
        result = dict(result)
        result["decision"] = {
            "kind": "ROUTE",
            "target_node": winning["owner_role"],
            "reason_ids": [
                "RULE:BLOCKING_PROCESS_BLOCKER",
                f"FACT:BLOCKER:{winning['blocker_id']}",
            ],
        }
    if (
        subject["workflow_phase"] == "TERMINAL_EVALUATION"
        and result["priority_rank"] >= 10
    ):
        basis_fields = (
            "d_review_snapshot_id",
            "report_candidate_id",
            "report_candidate_basis_id",
            "final_review_id",
            "final_review_basis_id",
        )
        if (
            not subject.get("final_review_completed")
            or subject.get("report_state") != "APPROVED"
            or any(subject.get(field) is None for field in basis_fields)
        ):
            result = _reference_result(
                10,
                "TERMINAL-EF-INVALID",
                "TERMINAL",
                {"kind": "TERMINAL", "verdict": "INTERNAL_INTEGRITY_ERROR"},
                "REASON-PRIORITY-TERMINAL-EF-INVALID",
            )
    return result


def verdict_sut_decision(assignment: dict[str, Any]) -> dict[str, Any]:
    """Return only the context-free SUT decision expected on stdout."""

    reference = evaluate_verdict_assignment(assignment)
    return with_self_hash(
        {
            "schema_version": "SutDecision.v1",
            "outcome": reference["outcome"],
            "decision": reference["decision"],
            "reason_ids": reference["reason_ids"],
            "assertion_ids": reference["assertion_ids"],
        },
        "sut_decision_sha256",
    )


def expected_verdict_record(
    envelope: dict[str, Any],
    *,
    sut_output_artifact_raw_sha256: str,
    oracle_source_manifest_entry_sha256: str,
) -> dict[str, Any]:
    """Assemble an isolated record after the SUT artifact is immutable."""

    if not verify_self_hash(
        envelope, "envelope_sha256", prefix=True
    ):
        raise ValueError("property envelope self-hash mismatch")
    for label, digest in (
        (
            "sut_output_artifact_raw_sha256",
            sut_output_artifact_raw_sha256,
        ),
        (
            "oracle_source_manifest_entry_sha256",
            oracle_source_manifest_entry_sha256,
        ),
    ):
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError(f"{label} must be lowercase SHA-256")
    decision = verdict_sut_decision(
        copy.deepcopy(envelope["assignment"])
    )
    record = {
        "schema_version": "PropertyExpectedRecord.v1",
        "suite_id": envelope["suite_id"],
        "ordinal": envelope["ordinal"],
        "instance_id": envelope["instance_id"],
        "case_id": envelope["case_id"],
        "envelope_sha256": envelope["envelope_sha256"],
        "oracle_algorithm_id": "ORACLE-VERDICT-PRIORITY-TABLE-V1",
        "oracle_source_manifest_entry_sha256": (
            oracle_source_manifest_entry_sha256
        ),
        "generated_after_sut_output_freeze": True,
        "sut_output_artifact_raw_sha256": (
            sut_output_artifact_raw_sha256
        ),
        "expected": decision,
    }
    return with_self_hash(record, "record_sha256", prefix=True)
