from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import content_id
from .materialization import (
    build_property_materialization_bundle,
    validate_property_envelope,
)
from .verdict_facts import materialize_fact_collections


MATERIALIZER_ID = "MATERIALIZER-VERDICT-RUNNER-INPUT-V1"
INPUT_BINDING_ID = "BINDING-VERDICT-FUNCTION-1-V1"

_NODE_BY_PHASE = {
    "PLAN_AUTHOR": "A",
    "PLAN_REVIEW": "B",
    "TEST_EXECUTION": "C",
    "RESULT_REVIEW": "D",
    "REPORT_DRAFT": "E",
    "FINAL_REVIEW": "F",
    "CANCEL_CONTROL": "KERNEL_CANCEL_COORDINATOR",
    "TERMINAL_EVALUATION": None,
}
_TEST_PLAN_ID = "sha256:" + "32" * 32
_EXECUTION_CONTRACT_ID = "sha256:" + "33" * 32
_D_REVIEW_ID = "sha256:" + "44" * 32
_REPORT_CANDIDATE_ID = "sha256:" + "45" * 32
_REPORT_BASIS_ID = "sha256:" + "46" * 32
_FINAL_REVIEW_ID = "sha256:" + "47" * 32
_FINAL_BASIS_ID = "sha256:" + "48" * 32


def _phase_chain(phase: str) -> tuple[Any, Any, Any, Any, Any, bool]:
    if phase in {
        "PLAN_AUTHOR",
        "PLAN_REVIEW",
        "TEST_EXECUTION",
        "RESULT_REVIEW",
        "CANCEL_CONTROL",
    }:
        return None, None, None, None, None, False
    if phase == "REPORT_DRAFT":
        return _D_REVIEW_ID, None, None, None, None, False
    if phase == "FINAL_REVIEW":
        return (
            _D_REVIEW_ID,
            _REPORT_CANDIDATE_ID,
            _REPORT_BASIS_ID,
            None,
            None,
            False,
        )
    return (
        _D_REVIEW_ID,
        _REPORT_CANDIDATE_ID,
        _REPORT_BASIS_ID,
        _FINAL_REVIEW_ID,
        _FINAL_BASIS_ID,
        True,
    )


def _verdict_candidate(assignment: dict[str, Any]) -> dict[str, Any]:
    phase = assignment["workflow_phase"]
    (
        d_review_id,
        report_candidate_id,
        report_basis_id,
        final_review_id,
        final_basis_id,
        final_completed,
    ) = _phase_chain(phase)
    facts = materialize_fact_collections(
        assignment["fact_mask"],
        cancel_state=assignment["cancel_state"],
        owner_role="A",
        origin_role="B",
        source_baseline_id="sha256:" + "30" * 32,
        test_plan_revision_id=_TEST_PLAN_ID,
        execution_contract_id=_EXECUTION_CONTRACT_ID,
    )
    policy = {
        "schema_version": "SafetyStopPolicy.v1",
        "source_test_plan_revision_id": _TEST_PLAN_ID,
        "case_policies": [
            {
                "case_id": case_id,
                "objective_stop_conditions": [
                    "Stop only for objective evidence integrity risk."
                ],
            }
            for case_id in facts["approved_case_ids"]
        ],
    }
    return {
        "schema_version": "VerdictInput.v1",
        "execution_contract_id": _EXECUTION_CONTRACT_ID,
        "test_plan_revision_id": _TEST_PLAN_ID,
        "workflow_phase": phase,
        "current_node": _NODE_BY_PHASE[phase],
        "d_review_snapshot_id": d_review_id,
        "report_candidate_id": report_candidate_id,
        "report_candidate_basis_id": report_basis_id,
        "final_review_id": final_review_id,
        "final_review_basis_id": final_basis_id,
        "final_review_completed": final_completed,
        "safety_stop_policy": policy,
        "safety_stop_policy_hash": content_id(policy),
        "approved_case_ids": facts["approved_case_ids"],
        "required_case_ids": facts["required_case_ids"],
        "optional_case_ids": [],
        "d_accepted_required_case_ids": facts[
            "d_accepted_required_case_ids"
        ],
        "d_accepted_optional_case_ids": [],
        "missing_required_case_ids": facts["missing_required_case_ids"],
        "open_required_environment_gap_case_ids": facts[
            "open_required_environment_gap_case_ids"
        ],
        "required_process_blocked_case_ids": facts[
            "required_process_blocked_case_ids"
        ],
        "open_optional_environment_gap_case_ids": [],
        "optional_process_issue_case_ids": [],
        "safety_stopped_case_ids": [],
        "cancelled_case_ids": [],
        "unclassified_missing_case_ids": facts[
            "unclassified_missing_case_ids"
        ],
        "workflow_integrity": (
            assignment["workflow_integrity"]
            if _assignment_is_schema_compatible(assignment)
            else "INVALID"
        ),
        "evidence_state": assignment["evidence_state"],
        "coverage_state": assignment["coverage_state"],
        "report_state": assignment["report_state"],
        "cancel_state": assignment["cancel_state"],
        "active_or_unverifiable_action_ids": facts[
            "active_or_unverifiable_action_ids"
        ],
        "active_or_unverifiable_actions": facts[
            "active_or_unverifiable_actions"
        ],
        "active_external_jobs": facts["active_external_jobs"],
        "unknown_side_effects": facts["unknown_side_effects"],
        "open_process_blockers": facts["open_process_blockers"],
        "open_upstream_defect_ids": facts["open_upstream_defect_ids"],
        "stagnation_state": facts["stagnation_state"],
        "product_findings": facts["product_findings"],
        "environment_gaps": facts["environment_gaps"],
    }


def _assignment_is_schema_compatible(
    assignment: dict[str, Any],
) -> bool:
    if assignment["workflow_integrity"] != "VALID":
        return True
    mask = int(assignment["fact_mask"].removeprefix("FACT-MASK-"))
    phase = assignment["workflow_phase"]
    report = assignment["report_state"]
    cancel = assignment["cancel_state"]
    if mask & (1 << 4):
        return False
    if mask & (1 << 3) and not mask & (1 << 2):
        return False
    if phase == "CANCEL_CONTROL" and cancel == "NOT_REQUESTED":
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


def materialize_verdict_bundle(
    envelope: dict[str, Any],
    *,
    suite: dict[str, Any],
    schema_dir: str | Path,
) -> dict[str, Any]:
    validate_property_envelope(envelope, suite, schema_dir=schema_dir)
    candidate = _verdict_candidate(envelope["assignment"])
    runner_input = {
        "schema_version": "EvaluationRunnerInput.v1",
        "runner_contract_id": suite["sut_runner_contract_id"],
        "input_binding_id": INPUT_BINDING_ID,
        "case_id": envelope["case_id"],
        "subject": candidate,
        "context_objects": [],
        "fixture_refs": [],
        "mutation": None,
        "observed_state": None,
    }
    return build_property_materialization_bundle(
        envelope,
        runner_input,
        [],
        schema_dir=schema_dir,
        bound_subject_schema_name="verdict_input.v1.schema.json",
    )
