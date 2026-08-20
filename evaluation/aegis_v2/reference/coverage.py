from __future__ import annotations

import itertools
from functools import lru_cache
from typing import Any


_CONDITIONS = (
    "CANCEL_REQUESTED",
    "CANCEL_ACTIVE",
    "CANCEL_QUIESCENT",
    "INTEGRITY",
    "UNKNOWN_UPSTREAM",
    "BLOCKER_STAGNATION",
    "BLOCKER",
    "EVIDENCE_INVALID",
    "PHASE_ROUTE",
    "TERMINAL_EF_INVALID",
    "REQUIRED_ENV_GAP",
    "FINDING",
    "PASS",
    "FALLBACK",
)


def _condition_truths(
    cancel_state: str,
    workflow_integrity: str,
    evidence_state: str,
    coverage_state: str,
    report_state: str,
    workflow_phase: str,
    mask: int,
) -> tuple[str, ...]:
    unknown_or_upstream = bool(mask & 0b0000011)
    blocker = bool(mask & 0b0000100)
    stagnation = bool(mask & 0b0001000)
    unclassified = bool(mask & 0b0010000)
    environment_gap = bool(mask & 0b0100000)
    finding = bool(mask & 0b1000000)
    truth = {
        "CANCEL_REQUESTED": cancel_state in {"REQUESTED", "QUIESCING"},
        "CANCEL_ACTIVE": cancel_state == "TERMINATED_WITH_ACTIVE_WORK",
        "CANCEL_QUIESCENT": cancel_state == "QUIESCENT",
        "INTEGRITY": workflow_integrity in {"INVALID", "UNKNOWN"},
        "UNKNOWN_UPSTREAM": unknown_or_upstream,
        "BLOCKER_STAGNATION": blocker and stagnation,
        "BLOCKER": blocker,
        "EVIDENCE_INVALID": (
            evidence_state in {"INVALID", "STALE"} or unclassified
        ),
        "PHASE_ROUTE": workflow_phase
        in {
            "PLAN_AUTHOR",
            "PLAN_REVIEW",
            "TEST_EXECUTION",
            "RESULT_REVIEW",
            "REPORT_DRAFT",
            "FINAL_REVIEW",
        },
        "TERMINAL_EF_INVALID": (
            workflow_phase == "TERMINAL_EVALUATION"
            and report_state != "APPROVED"
        ),
        "REQUIRED_ENV_GAP": (
            workflow_phase == "TERMINAL_EVALUATION"
            and report_state == "APPROVED"
            and environment_gap
        ),
        "FINDING": (
            workflow_phase == "TERMINAL_EVALUATION"
            and report_state == "APPROVED"
            and finding
            and coverage_state
            in {"COMPLETE", "PARTIAL_SAFETY_POLICY"}
        ),
        "PASS": (
            workflow_phase == "TERMINAL_EVALUATION"
            and report_state == "APPROVED"
            and evidence_state == "COMPLETE"
            and coverage_state == "COMPLETE"
            and not finding
            and not environment_gap
        ),
    }
    truth["FALLBACK"] = not any(truth.values())
    return tuple(name for name in _CONDITIONS if truth[name])


@lru_cache(maxsize=1)
def build_coverage_accounting() -> dict[str, Any]:
    cancel_states = (
        "NOT_REQUESTED",
        "REQUESTED",
        "QUIESCING",
        "QUIESCENT",
        "TERMINATED_WITH_ACTIVE_WORK",
    )
    workflow_integrities = ("VALID", "INVALID", "UNKNOWN")
    evidence_states = ("COMPLETE", "PARTIAL", "INVALID", "STALE")
    coverage_states = (
        "COMPLETE",
        "PARTIAL_SAFETY_POLICY",
        "INCOMPLETE",
    )
    report_states = ("NOT_READY", "REWORK", "APPROVED")
    workflow_phases = (
        "PLAN_AUTHOR",
        "PLAN_REVIEW",
        "TEST_EXECUTION",
        "RESULT_REVIEW",
        "REPORT_DRAFT",
        "FINAL_REVIEW",
        "CANCEL_CONTROL",
        "TERMINAL_EVALUATION",
    )
    reachable_pairs: set[tuple[str, str]] = set()
    pair_witnesses: dict[str, dict[str, Any]] = {}
    verdict_count = 0
    for values in itertools.product(
        cancel_states,
        workflow_integrities,
        evidence_states,
        coverage_states,
        report_states,
        workflow_phases,
        range(128),
    ):
        verdict_count += 1
        active = _condition_truths(*values)
        for pair in itertools.combinations(active, 2):
            ordered = tuple(
                sorted(pair, key=_CONDITIONS.index)
            )
            if ordered not in reachable_pairs:
                pair_witnesses["+".join(ordered)] = {
                    "cancel_state": values[0],
                    "workflow_integrity": values[1],
                    "evidence_state": values[2],
                    "coverage_state": values[3],
                    "report_state": values[4],
                    "workflow_phase": values[5],
                    "fact_mask": f"FACT-MASK-{values[6]:03d}",
                }
            reachable_pairs.add(ordered)

    all_pairs = set(itertools.combinations(_CONDITIONS, 2))
    incompatible_pairs = all_pairs - reachable_pairs
    closure_denominator = 3 * 6 * 2 * 2 * 2
    valid_closure_cases = 3 * 6
    return {
        "schema_version": "ReferenceCoverageAccounting.v1",
        "enumeration_method": "EXACT_CARTESIAN_ASSIGNMENT_ENUMERATION",
        "verdict_assignment_denominator": verdict_count,
        "closure_assignment_denominator": closure_denominator,
        "priority_condition_count": len(_CONDITIONS),
        "priority_pair_denominator": len(all_pairs),
        "priority_pair_reachable": len(reachable_pairs),
        "priority_pair_contract_incompatible": len(incompatible_pairs),
        "reachable_pair_witnesses": {
            key: pair_witnesses[key] for key in sorted(pair_witnesses)
        },
        "contract_incompatible_pairs": [
            "+".join(pair)
            for pair in sorted(
                incompatible_pairs,
                key=lambda pair: (
                    _CONDITIONS.index(pair[0]),
                    _CONDITIONS.index(pair[1]),
                ),
            )
        ],
        "valid_closure_cases": valid_closure_cases,
        "invalid_closure_cases": (
            closure_denominator - valid_closure_cases
        ),
        "ef_chain_cases": (
            verdict_count * 3 // len(workflow_phases)
        ),
        "cancellation_cases": (
            verdict_count * 4 // len(cancel_states)
        ),
    }
