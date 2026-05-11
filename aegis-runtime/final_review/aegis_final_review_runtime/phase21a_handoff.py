from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from .leader import FinalReviewLeader
from .models import FinalReviewContractError, FinalReviewRequest


class Phase21AHandoffValidationError(ValueError):
    """Raised when a Phase 21A handoff package is not acceptable."""


ACCEPTANCE_STATUS = "accepted_final_review_handoff_validation_closure"
HANDOFF_KIND = "test_real_worker_result"
HANDOFF_TARGET = "final_review"
HANDOFF_READY_STATUS = "ready_for_final_review"

_FORBIDDEN_TRUE_FIELDS = (
    "production_test_lifecycle_closure",
    "remote_push_performed",
    "pr_created",
    "production_merge_performed",
    "release_performed",
    "production_signoff_performed",
    "global_causal_truth_mutation",
)


_VALID_FINAL_REVIEW_DECISIONS = {
    "accept_for_master",
    "accept_for_master_with_scope_limit",
    "reject_to_execution_via_master",
    "request_test_expansion_via_master",
    "request_more_evidence_via_master",
    "governance_blocker_to_master",
    "blocked_resource_policy",
}


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Phase21AHandoffValidationError("handoff package must be a JSON object")
    return value


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _ensure_false_if_present(handoff: dict[str, Any], field_name: str) -> None:
    if field_name in handoff and handoff[field_name] is not False:
        raise Phase21AHandoffValidationError(f"{field_name} must be false in Phase 21A handoff validation")


def _assert_phase20b_handoff_gate(handoff: dict[str, Any]) -> None:
    if handoff.get("handoff_kind") != HANDOFF_KIND:
        raise Phase21AHandoffValidationError("handoff_kind must be test_real_worker_result")
    if handoff.get("target") != HANDOFF_TARGET:
        raise Phase21AHandoffValidationError("target must be final_review")
    if handoff.get("status") != HANDOFF_READY_STATUS:
        raise Phase21AHandoffValidationError("status must be ready_for_final_review")

    final_test_result = handoff.get("final_test_result")
    if final_test_result == "passed":
        pass
    elif isinstance(final_test_result, dict) and final_test_result.get("result") == "passed":
        pass
    else:
        raise Phase21AHandoffValidationError("final_test_result must be passed")

    for audit_field in ("proof_audit_status", "output_audit_status"):
        if audit_field in handoff and handoff[audit_field] != "passed":
            raise Phase21AHandoffValidationError(f"{audit_field} must be passed")

    route_results = handoff.get("route_results")
    if route_results is not None:
        failed_routes = _failed_route_result_ids(route_results)
        if failed_routes:
            raise Phase21AHandoffValidationError(f"all route_results must be passed: {failed_routes}")

    for field_name in _FORBIDDEN_TRUE_FIELDS:
        _ensure_false_if_present(handoff, field_name)


def _as_string_list(value: Any, *, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise Phase21AHandoffValidationError("expected a list of non-empty strings")
    return list(value)


def _first_non_empty(*values: Any, default: str) -> str:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return default


def _route_result_items(route_results: Any) -> list[tuple[str, Any]]:
    if isinstance(route_results, dict):
        return [(str(route_id), result) for route_id, result in route_results.items()]
    if isinstance(route_results, list):
        items: list[tuple[str, Any]] = []
        for index, item in enumerate(route_results):
            if not isinstance(item, dict):
                raise Phase21AHandoffValidationError("route_results list entries must be objects")
            route_id = item.get("route_id")
            if not isinstance(route_id, str) or not route_id:
                raise Phase21AHandoffValidationError("route_results list entries must include route_id")
            result = item.get("route_result", item.get("result", item.get("status")))
            items.append((route_id, result))
        return items
    raise Phase21AHandoffValidationError("route_results must be an object or list when present")


def _failed_route_result_ids(route_results: Any) -> list[str]:
    return [route_id for route_id, result in _route_result_items(route_results) if result != "passed"]


def _route_result_ids(route_results: Any) -> list[str]:
    return [route_id for route_id, _result in _route_result_items(route_results)]


def _route_report_refs_from_handoff(handoff: dict[str, Any]) -> list[str]:
    explicit = handoff.get("test_route_report_refs") or handoff.get("route_report_refs")
    if explicit is not None:
        return _as_string_list(explicit, default=[])
    route_results = handoff.get("route_results")
    if route_results is not None:
        route_ids = _route_result_ids(route_results)
        if route_ids:
            return [f"phase20b:route_result:{route_id}" for route_id in sorted(route_ids)]
    return ["phase20b:test_worker_route_results"]


def _test_evidence_refs_from_handoff(handoff: dict[str, Any]) -> list[str]:
    explicit = handoff.get("test_evidence_refs") or handoff.get("worker_evidence_refs")
    if explicit is not None:
        return _as_string_list(explicit, default=[])
    refs: list[str] = []
    for key in (
        "test_worker_proof_audit_ref",
        "test_worker_output_audit_ref",
        "worker_outputs_ref",
        "worker_proofs_ref",
        "worker_work_evidence_ref",
    ):
        value = handoff.get(key)
        if isinstance(value, str) and value:
            refs.append(value)
    if refs:
        return refs
    return ["phase20b:test_worker_proofs_outputs_and_private_evidence"]


def _reviewed_refs_from_handoff(handoff: dict[str, Any]) -> dict[str, Any]:
    explicit = handoff.get("reviewed_refs")
    if isinstance(explicit, dict):
        return explicit

    return {
        "execution_final_report_ref": _first_non_empty(
            handoff.get("execution_final_report_ref"),
            handoff.get("execution_report_ref"),
            default="phase19b:execution_final_report",
        ),
        "execution_causal_chain_ref": _first_non_empty(
            handoff.get("execution_causal_chain_ref"),
            handoff.get("execution_causal_candidate_ref"),
            default="phase19b:execution_causal_candidate",
        ),
        "test_final_report_ref": _first_non_empty(
            handoff.get("test_final_report_ref"),
            handoff.get("final_test_result_ref"),
            default="phase20b:final_test_result_phase20b.json",
        ),
        "test_plan_ref": _first_non_empty(
            handoff.get("test_plan_ref"),
            handoff.get("validation_package_ref"),
            default="phase20b:validation_package",
        ),
        "test_route_report_refs": _route_report_refs_from_handoff(handoff),
        "test_evidence_refs": _test_evidence_refs_from_handoff(handoff),
        "reproducibility_set_ref": _first_non_empty(
            handoff.get("reproducibility_set_ref"),
            default="phase20b:reproducibility_set",
        ),
        "artifact_manifest_ref": _first_non_empty(
            handoff.get("artifact_manifest_ref"),
            default="phase20b:artifact_manifest",
        ),
        "debate_refs": _as_string_list(handoff.get("debate_refs"), default=[]),
    }


def _synthesize_final_review_input_package(handoff: dict[str, Any]) -> dict[str, Any]:
    final_code_ref = _first_non_empty(
        handoff.get("final_code_ref"),
        handoff.get("integration_commit"),
        handoff.get("integration_branch"),
        default="phase19b:integration_candidate",
    )
    implementation_candidate_ref = _first_non_empty(
        handoff.get("implementation_candidate_ref"),
        handoff.get("execution_candidate_ref"),
        default=final_code_ref,
    )
    tested_candidate_ref = _first_non_empty(
        handoff.get("tested_candidate_ref"),
        handoff.get("test_candidate_ref"),
        default=final_code_ref,
    )

    return {
        "task_scope": _as_string_list(
            handoff.get("task_scope"),
            default=["Phase 19B/20B sandbox integration candidate scoped to changed files and sandbox pytest"],
        ),
        "final_code_ref": final_code_ref,
        "implementation_candidate_ref": implementation_candidate_ref,
        "tested_candidate_ref": tested_candidate_ref,
        "reviewed_refs": _reviewed_refs_from_handoff(handoff),
        "accepted_scope": _as_string_list(
            handoff.get("accepted_scope"),
            default=["Phase 20B passed routes only"],
        ),
        "blocked_scope": _as_string_list(handoff.get("blocked_scope"), default=[]),
        "known_limits": _as_string_list(handoff.get("known_limits"), default=[]),
        "missing_evidence": _as_string_list(handoff.get("missing_evidence"), default=[]),
        "governance_blockers": _as_string_list(handoff.get("governance_blockers"), default=[]),
        "material_conditions": _as_string_list(
            handoff.get("material_conditions"),
            default=["Phase 21A uses Test Phase 20B scoped evidence and does not claim production lifecycle closure"],
        ),
        "assumptions": _as_string_list(
            handoff.get("assumptions"),
            default=["Phase 20B handoff evidence references are available to Final Review"],
        ),
        "execution_defects": _as_string_list(handoff.get("execution_defects"), default=[]),
        "test_evidence_deficiencies": _as_string_list(handoff.get("test_evidence_deficiencies"), default=[]),
        "evidence_contradictions": _as_string_list(handoff.get("evidence_contradictions"), default=[]),
        "object_mapping_evidence": _as_string_list(handoff.get("object_mapping_evidence"), default=[]),
        "debate_used": bool(handoff.get("debate_used", False)),
    }


def _resource_policy_from_handoff(handoff: dict[str, Any]) -> dict[str, Any]:
    resource_policy = handoff.get("resource_policy")
    if isinstance(resource_policy, dict):
        return resource_policy
    return {
        "policy_ref": handoff.get("policy_ref", "MODEL_REASONING_BUDGET_POLICY.yaml"),
        "required_profile": "final_review_leader",
        "resolved_profile": "final_review_leader",
        "reasoning_budget": "maximum",
        "fallback_used": False,
        "status": "satisfied",
    }


def build_final_review_request_from_phase21a_handoff(handoff: dict[str, Any]) -> dict[str, Any]:
    """Validate a Phase 20B handoff and return a Final Review request payload."""
    _assert_phase20b_handoff_gate(handoff)

    if isinstance(handoff.get("final_review_request"), dict):
        request = dict(handoff["final_review_request"])
    else:
        input_package = handoff.get("final_review_input_package")
        if not isinstance(input_package, dict):
            input_package = _synthesize_final_review_input_package(handoff)
        request = {
            "request_id": _first_non_empty(
                handoff.get("request_id"),
                default=f"phase21a-final-review-{uuid4().hex}",
            ),
            "source": "test",
            "resource_policy": _resource_policy_from_handoff(handoff),
            "final_review_input_package": input_package,
        }

    try:
        parsed = FinalReviewRequest.from_dict(request)
    except FinalReviewContractError as exc:
        raise Phase21AHandoffValidationError(str(exc)) from exc
    return parsed.to_dict()


def _validate_final_review_result(result: dict[str, Any]) -> None:
    if result.get("target") != "master":
        raise Phase21AHandoffValidationError("Final Review result target must be master")
    if result.get("decision") not in _VALID_FINAL_REVIEW_DECISIONS:
        raise Phase21AHandoffValidationError("Final Review result decision is invalid")
    if result.get("status") != "final_review_recommendation":
        raise Phase21AHandoffValidationError("Final Review result status must be final_review_recommendation")
    boundary = result.get("causal_boundary", "")
    if "not global causal truth" not in boundary:
        raise Phase21AHandoffValidationError("Final Review result must preserve causal boundary")


def run_phase21a_handoff_validation(handoff_package_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    """Run Phase 21A handoff validation and write request/result/summary artifacts."""
    output_root = Path(output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    handoff = load_json(handoff_package_path)
    request = build_final_review_request_from_phase21a_handoff(handoff)
    request_path = output_root / "phase21a_final_review_request.json"
    write_json(request_path, request)

    leader = FinalReviewLeader(output_root / "final_review_private")
    result = leader.run(request).to_dict()
    _validate_final_review_result(result)
    result_path = output_root / "phase21a_final_review_result.json"
    write_json(result_path, result)

    accepted = result["target"] == "master" and result["decision"] != "blocked_resource_policy"
    summary = {
        "acceptance_status": ACCEPTANCE_STATUS if accepted else result["decision"],
        "phase_boundary": "final_review_handoff_validation_not_real_final_review_leader",
        "handoff_kind": handoff.get("handoff_kind"),
        "source_status": handoff.get("status"),
        "request_id": result["request_id"],
        "decision": result["decision"],
        "target": result["target"],
        "output_route": "final_review -> master",
        "request_artifact": str(request_path),
        "result_artifact": str(result_path),
        "real_final_review_leader_created": False,
        "final_review_worker_created": False,
        "production_final_review_lifecycle_closure": False,
        "production_release_review_closure": False,
        "global_causal_truth_mutation": False,
    }
    summary_path = output_root / "phase21a_handoff_validation_summary.json"
    write_json(summary_path, summary)
    return summary


__all__ = [
    "ACCEPTANCE_STATUS",
    "Phase21AHandoffValidationError",
    "build_final_review_request_from_phase21a_handoff",
    "run_phase21a_handoff_validation",
]
