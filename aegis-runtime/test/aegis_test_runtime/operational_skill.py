from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

PHASE = "phase27b_test_role_operational_skill_runtime_validation"
LEADER_SKILL_ID = "TEST_LEADER_OPERATIONAL_SKILL"
WORKER_SKILL_ID = "TEST_WORKER_OPERATIONAL_SKILL"
SKILL_VERSION = "v0.1"

ALLOWED_ROUTE_RESULTS = {"passed", "failed", "inconclusive", "blocked"}
ALLOWED_FINAL_RESULTS = {"passed", "passed_with_scope_limit", "failed", "inconclusive", "blocked", "request_more_context"}
ALLOWED_NEXT_ROUTES = {"execution", "final_review"}
ALLOWED_CREATION_MECHANISMS = {
    "real_nested_codex_mcp",
    "mcp__nested_codex__.codex",
    "codex_cli_verified",
}
FORBIDDEN_TRUE_FIELDS = (
    "remote_push_performed",
    "pull_request_created",
    "remote_merge_performed",
    "release_performed",
    "deployment_performed",
    "external_signoff_performed",
    "production_store_write_performed",
    "global_causal_truth_merge_performed",
    "global_causal_truth_claimed",
)
WORKER_FORBIDDEN_TRUE_FIELDS = FORBIDDEN_TRUE_FIELDS + (
    "implementation_code_modified",
    "whole_candidate_result_decided",
    "direct_execution_feedback_sent",
    "direct_master_route_used",
)


class TestOperationalSkillError(ValueError):
    """Raised when Phase 27B Test role-skill validation input is malformed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TestSkillValidationResult:
    test_skill_validation_result_id: str
    phase: str
    status: str
    decision: str
    reason: str
    leader_skill_ref: dict[str, str]
    worker_skill_ref: dict[str, str]
    route_count: int = 0
    worker_creation_count: int = 0
    worker_proof_count: int = 0
    worker_output_count: int = 0
    violations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    leader_skill_installed: bool = False
    worker_skill_installation_verified: bool = False
    thread_id_supervision_verified: bool = False
    worker_proofs_verified: bool = False
    worker_outputs_verified: bool = False
    evidence_state_aggregation_verified: bool = False
    reproducibility_set_verified: bool = False
    artifact_manifest_verified: bool = False
    global_causal_truth_merge_performed: bool = False
    production_store_write_performed: bool = False
    remote_push_performed: bool = False
    pull_request_created: bool = False
    remote_merge_performed: bool = False
    release_performed: bool = False
    deployment_performed: bool = False
    external_signoff_performed: bool = False
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_skill_validation_result_id": self.test_skill_validation_result_id,
            "phase": self.phase,
            "status": self.status,
            "decision": self.decision,
            "reason": self.reason,
            "leader_skill_ref": dict(self.leader_skill_ref),
            "worker_skill_ref": dict(self.worker_skill_ref),
            "route_count": self.route_count,
            "worker_creation_count": self.worker_creation_count,
            "worker_proof_count": self.worker_proof_count,
            "worker_output_count": self.worker_output_count,
            "violations": list(self.violations),
            "warnings": list(self.warnings),
            "leader_skill_installed": self.leader_skill_installed,
            "worker_skill_installation_verified": self.worker_skill_installation_verified,
            "thread_id_supervision_verified": self.thread_id_supervision_verified,
            "worker_proofs_verified": self.worker_proofs_verified,
            "worker_outputs_verified": self.worker_outputs_verified,
            "evidence_state_aggregation_verified": self.evidence_state_aggregation_verified,
            "reproducibility_set_verified": self.reproducibility_set_verified,
            "artifact_manifest_verified": self.artifact_manifest_verified,
            "global_causal_truth_merge_performed": self.global_causal_truth_merge_performed,
            "production_store_write_performed": self.production_store_write_performed,
            "remote_push_performed": self.remote_push_performed,
            "pull_request_created": self.pull_request_created,
            "remote_merge_performed": self.remote_merge_performed,
            "release_performed": self.release_performed,
            "deployment_performed": self.deployment_performed,
            "external_signoff_performed": self.external_signoff_performed,
            "created_at": self.created_at,
        }


def load_json_object(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TestOperationalSkillError(f"file not found: {p}") from exc
    except json.JSONDecodeError as exc:
        raise TestOperationalSkillError(f"file is not valid JSON: {p}: {exc}") from exc
    if not isinstance(payload, dict):
        raise TestOperationalSkillError(f"file must contain a JSON object: {p}")
    return payload


def validate_test_skill_run_file(
    run_path: str | Path,
    *,
    leader_skill_path: str | Path | None = None,
    worker_skill_path: str | Path | None = None,
    enforcement_contract_path: str | Path | None = None,
) -> TestSkillValidationResult:
    return validate_test_skill_run(
        load_json_object(run_path),
        leader_skill_path=leader_skill_path,
        worker_skill_path=worker_skill_path,
        enforcement_contract_path=enforcement_contract_path,
    )


def validate_test_skill_run(
    run: dict[str, Any],
    *,
    leader_skill_path: str | Path | None = None,
    worker_skill_path: str | Path | None = None,
    enforcement_contract_path: str | Path | None = None,
) -> TestSkillValidationResult:
    if not isinstance(run, dict):
        raise TestOperationalSkillError("run must be a JSON object")

    violations: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if leader_skill_path is not None:
        _check_skill_file(
            leader_skill_path,
            field="leader_skill_file",
            required_markers=[
                "skill_id: TEST_LEADER_OPERATIONAL_SKILL",
                "skill_version: v0.1",
                "thread_id is the Worker lifecycle identity key",
                "launcher_timeout",
                "requested_reasoning_effort",
                "command_evidence",
            ],
            violations=violations,
        )
    if worker_skill_path is not None:
        _check_skill_file(
            worker_skill_path,
            field="worker_skill_file",
            required_markers=[
                "skill_id: TEST_WORKER_OPERATIONAL_SKILL",
                "skill_version: v0.1",
                "thread_id is the lifecycle identity key",
                "requested_reasoning_effort",
                "command_evidence",
                "test_worker_report_candidate",
            ],
            violations=violations,
        )
    if enforcement_contract_path is not None:
        _check_skill_file(
            enforcement_contract_path,
            field="enforcement_contract_file",
            required_markers=[
                "TEST_LEADER_WORKER_SKILL_ENFORCEMENT_CONTRACT",
                "launcher_timeout != worker_failed",
                "thread_id is the Worker lifecycle identity key",
                "requested_reasoning_effort",
                "command_evidence",
            ],
            violations=violations,
        )

    adapters = _adapter_pairs(run.get("compatibility_adapters", []))

    leader_ref = _ref(run.get("skill_ref"))
    leader_skill_installed = _is_skill_ref(leader_ref, LEADER_SKILL_ID)
    if not leader_skill_installed:
        violations.append(_violation("skill_ref", "Test Leader run must reference TEST_LEADER_OPERATIONAL_SKILL v0.1."))

    request = _ref(run.get("test_request"))
    _check_request(request, violations)

    governance_check = _ref(run.get("governance_check"))
    if governance_check.get("performed") is not True:
        violations.append(_violation("governance_check.performed", "Test Leader must perform governance blocker check."))

    routes = _extract_routes(run, violations)
    route_ids = [str(route.get("route_id", "")) for route in routes if route.get("route_id")]
    if not routes and not _is_pre_route_terminal(run):
        violations.append(_violation("test_plan.routes", "Skill-enforced Test run requires at least one route unless it ended before route execution."))

    worker_creations = _as_dict_list(run.get("worker_creation_requests", []), "worker_creation_requests", violations)
    worker_proofs = _as_dict_list(run.get("worker_proofs", []), "worker_proofs", violations)
    worker_outputs = _as_dict_list(run.get("worker_outputs", []), "worker_outputs", violations)
    supervision_records = _as_dict_list(run.get("worker_supervision_records", []), "worker_supervision_records", violations)

    creation_by_route: dict[str, dict[str, Any]] = {}
    for creation in worker_creations:
        _check_worker_creation(creation, route_ids=route_ids, adapters=adapters, violations=violations)
        route_id = str(creation.get("route_id", ""))
        if route_id:
            if route_id in creation_by_route:
                violations.append(_violation("worker_creation_requests.route_id", f"duplicate Worker creation for route {route_id}"))
            creation_by_route[route_id] = creation

    if routes:
        for route_id in route_ids:
            if route_id not in creation_by_route:
                violations.append(_violation("worker_creation_requests", f"missing Worker creation for route {route_id}"))

    supervision_by_route: dict[str, dict[str, Any]] = {}
    for record in supervision_records:
        _check_supervision_record(record, creation_by_route=creation_by_route, violations=violations)
        route_id = str(record.get("route_id", ""))
        if route_id:
            supervision_by_route[route_id] = record

    if worker_creations and not supervision_records:
        violations.append(_violation("worker_supervision_records", "Worker supervision records are required for created Workers."))

    proof_by_route: dict[str, dict[str, Any]] = {}
    for proof in worker_proofs:
        _check_worker_proof(proof, creation_by_route=creation_by_route, adapters=adapters, violations=violations)
        route_id = str(proof.get("route_id", ""))
        if route_id:
            proof_by_route[route_id] = proof

    output_by_route: dict[str, dict[str, Any]] = {}
    for output in worker_outputs:
        _check_worker_output(output, creation_by_route=creation_by_route, proof_by_route=proof_by_route, adapters=adapters, violations=violations)
        route_id = str(output.get("route_id", ""))
        if route_id:
            output_by_route[route_id] = output

    if routes:
        for route_id in route_ids:
            if route_id not in proof_by_route:
                violations.append(_violation("worker_proofs", f"missing Worker proof for route {route_id}"))
            if route_id not in output_by_route:
                violations.append(_violation("worker_outputs", f"missing Worker output for route {route_id}"))

    final_result = _ref(run.get("final_test_result") or run.get("final_report"))
    _check_final_result(final_result, routes=routes, outputs=worker_outputs, governance_check=governance_check, violations=violations)

    _check_reproducibility(run, final_result, violations)
    _check_forbidden_flags(run, final_result, violations)

    status = "validated" if not violations else "rejected"
    boundaries = _ref(run.get("boundaries"))
    return TestSkillValidationResult(
        test_skill_validation_result_id=f"test-skill-validation-{uuid4().hex}",
        phase=PHASE,
        status=status,
        decision="accepted_test_role_skill_runtime_validation" if status == "validated" else "rejected",
        reason="Validated Test Leader/Worker role-bound operational skill runtime artifact." if status == "validated" else "Test role-bound skill runtime validation failed.",
        leader_skill_ref={"skill_id": LEADER_SKILL_ID, "skill_version": SKILL_VERSION},
        worker_skill_ref={"skill_id": WORKER_SKILL_ID, "skill_version": SKILL_VERSION},
        route_count=len(routes),
        worker_creation_count=len(worker_creations),
        worker_proof_count=len(worker_proofs),
        worker_output_count=len(worker_outputs),
        violations=violations,
        warnings=warnings,
        leader_skill_installed=leader_skill_installed,
        worker_skill_installation_verified=not any(v["field"].startswith("worker_creation_requests") for v in violations),
        thread_id_supervision_verified=not any(v["field"].startswith("worker_supervision_records") or "thread_id" in v["field"] for v in violations),
        worker_proofs_verified=not any(v["field"].startswith("worker_proofs") for v in violations),
        worker_outputs_verified=not any(v["field"].startswith("worker_outputs") for v in violations),
        evidence_state_aggregation_verified=not any(v["field"].startswith("final_test_result") for v in violations),
        reproducibility_set_verified=not any(v["field"].startswith("reproducibility_set") for v in violations),
        artifact_manifest_verified=not any(v["field"].startswith("artifact_manifest") for v in violations),
        global_causal_truth_merge_performed=bool(run.get("global_causal_truth_merge_performed") or final_result.get("global_causal_truth_merge_performed") or boundaries.get("global_causal_truth_merge_performed")),
        production_store_write_performed=bool(run.get("production_store_write_performed") or final_result.get("production_store_write_performed") or boundaries.get("production_store_write_performed")),
        remote_push_performed=bool(run.get("remote_push_performed") or final_result.get("remote_push_performed") or boundaries.get("remote_push_performed")),
        pull_request_created=bool(run.get("pull_request_created") or final_result.get("pull_request_created") or boundaries.get("pull_request_created")),
        remote_merge_performed=bool(run.get("remote_merge_performed") or final_result.get("remote_merge_performed") or boundaries.get("remote_merge_performed")),
        release_performed=bool(run.get("release_performed") or final_result.get("release_performed") or boundaries.get("release_performed")),
        deployment_performed=bool(run.get("deployment_performed") or final_result.get("deployment_performed") or boundaries.get("deployment_performed")),
        external_signoff_performed=bool(run.get("external_signoff_performed") or final_result.get("external_signoff_performed") or boundaries.get("external_signoff_performed")),
    )


def _check_request(request: dict[str, Any], violations: list[dict[str, Any]]) -> None:
    if not request:
        violations.append(_violation("test_request", "test_request is required."))
        return
    if request.get("source") != "execution":
        violations.append(_violation("test_request.source", "Test Department must accept implementation candidates from Execution."))
    for key in (
        "request_id",
        "objective",
        "scope",
        "implementation_candidate_ref",
        "final_code_ref",
        "changed_files",
        "ownership_map",
        "success_criteria",
    ):
        if _missing(request.get(key)):
            violations.append(_violation(f"test_request.{key}", "test_request missing required handoff field."))


def _extract_routes(run: dict[str, Any], violations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan = _ref(run.get("test_plan"))
    routes = _as_dict_list(plan.get("routes", run.get("routes", [])), "test_plan.routes", violations)
    seen: set[str] = set()
    for index, route in enumerate(routes):
        route_id = str(route.get("route_id", ""))
        if not route_id:
            violations.append(_violation(f"test_plan.routes[{index}].route_id", "route_id is required."))
            continue
        if route_id in seen:
            violations.append(_violation("test_plan.routes", f"duplicate route_id: {route_id}"))
        seen.add(route_id)
        if "mandatory" not in route:
            violations.append(_violation(f"test_plan.routes[{index}].mandatory", "route mandatory flag is required."))
    return routes


def _check_worker_creation(
    creation: dict[str, Any],
    *,
    route_ids: list[str],
    adapters: set[tuple[str, str]],
    violations: list[dict[str, Any]],
) -> None:
    route_id = str(creation.get("route_id", ""))
    if not route_id:
        violations.append(_violation("worker_creation_requests.route_id", "Worker creation requires route_id."))
    elif route_ids and route_id not in route_ids:
        violations.append(_violation("worker_creation_requests.route_id", f"Worker creation references unknown route {route_id}."))

    if creation.get("role_id") != "test_worker":
        violations.append(_violation("worker_creation_requests.role_id", "Worker creation role_id must be test_worker."))
    if not _is_skill_ref(_ref(creation.get("worker_skill_ref")), WORKER_SKILL_ID):
        violations.append(_violation("worker_creation_requests.worker_skill_ref", "Worker creation must include TEST_WORKER_OPERATIONAL_SKILL v0.1."))
    if creation.get("creation_mechanism") not in ALLOWED_CREATION_MECHANISMS:
        violations.append(_violation("worker_creation_requests.creation_mechanism", "Worker creation mechanism is not an accepted auditable mechanism."))
    if _missing(creation.get("thread_id")):
        violations.append(_violation("worker_creation_requests.thread_id", "Final Worker creation acceptance requires non-empty thread_id."))
    _check_model_fields(creation, "worker_creation_requests", adapters, violations)


def _check_supervision_record(
    record: dict[str, Any],
    *,
    creation_by_route: dict[str, dict[str, Any]],
    violations: list[dict[str, Any]],
) -> None:
    route_id = str(record.get("route_id", ""))
    creation = creation_by_route.get(route_id, {})
    if not route_id:
        violations.append(_violation("worker_supervision_records.route_id", "Supervision record requires route_id."))
    if _missing(record.get("thread_id")):
        violations.append(_violation("worker_supervision_records.thread_id", "Supervision record requires thread_id."))
    elif creation and record.get("thread_id") != creation.get("thread_id"):
        violations.append(_violation("worker_supervision_records.thread_id", "Supervision thread_id must match Worker creation record."))
    if record.get("launcher_status") == "launcher_timeout":
        if record.get("worker_failed") is True or record.get("child_status") in {"failed", "worker_failed"}:
            violations.append(_violation("worker_supervision_records.launcher_status", "launcher_timeout with captured thread_id must not be treated as worker_failed."))
        if record.get("recovery_attempted") is not True:
            violations.append(_violation("worker_supervision_records.recovery_attempted", "launcher_timeout must trigger recovery/polling before final failure."))
    if record.get("duplicate_worker_created_for_same_route") is True:
        violations.append(_violation("worker_supervision_records.duplicate_worker_created_for_same_route", "Leader must not create duplicate Worker solely due to launcher timeout."))


def _check_worker_proof(
    proof: dict[str, Any],
    *,
    creation_by_route: dict[str, dict[str, Any]],
    adapters: set[tuple[str, str]],
    violations: list[dict[str, Any]],
) -> None:
    route_id = str(proof.get("route_id", ""))
    creation = creation_by_route.get(route_id, {})
    if proof.get("role_id") != "test_worker":
        violations.append(_violation("worker_proofs.role_id", "Worker proof role_id must be test_worker."))
    if proof.get("created_by") != "test_leader":
        violations.append(_violation("worker_proofs.created_by", "Worker proof must record created_by=test_leader."))
    if proof.get("creation_mechanism") not in ALLOWED_CREATION_MECHANISMS:
        violations.append(_violation("worker_proofs.creation_mechanism", "Worker proof creation mechanism is not accepted."))
    if _missing(proof.get("thread_id")):
        violations.append(_violation("worker_proofs.thread_id", "Worker proof requires non-empty thread_id."))
    elif creation and proof.get("thread_id") != creation.get("thread_id"):
        violations.append(_violation("worker_proofs.thread_id", "Worker proof thread_id must match creation record."))
    if not _is_skill_ref(_ref(proof.get("skill_ref")), WORKER_SKILL_ID):
        violations.append(_violation("worker_proofs.skill_ref", "Worker proof must reference TEST_WORKER_OPERATIONAL_SKILL v0.1."))
    if proof.get("skill_received") is not True or proof.get("skill_applied") is not True:
        violations.append(_violation("worker_proofs.skill_received", "Worker proof must prove skill receipt/application."))
    if proof.get("topology_scope") != "test_route_local_domain":
        violations.append(_violation("worker_proofs.topology_scope", "Worker proof topology_scope must be test_route_local_domain."))
    for key in ("created_at_utc", "proof_statement"):
        if _missing(proof.get(key)):
            violations.append(_violation(f"worker_proofs.{key}", "Worker proof missing required field."))
    if _missing(proof.get("proof_path")) and _missing(proof.get("proof_ref")):
        violations.append(_violation("worker_proofs.proof_path", "Worker proof requires proof_path or proof_ref."))
    if _missing(proof.get("proof_sha256")):
        violations.append(_violation("worker_proofs.proof_sha256", "Final proof audit record requires proof_sha256."))
    _check_model_fields(proof, "worker_proofs", adapters, violations)


def _check_worker_output(
    output: dict[str, Any],
    *,
    creation_by_route: dict[str, dict[str, Any]],
    proof_by_route: dict[str, dict[str, Any]],
    adapters: set[tuple[str, str]],
    violations: list[dict[str, Any]],
) -> None:
    route_id = str(output.get("route_id", ""))
    creation = creation_by_route.get(route_id, {})
    proof = proof_by_route.get(route_id, {})

    if output.get("role_id") != "test_worker":
        violations.append(_violation("worker_outputs.role_id", "Worker output role_id must be test_worker."))
    if _as_list(output.get("route_ids", [])) and len(_as_list(output.get("route_ids", []))) > 1:
        violations.append(_violation("worker_outputs.route_ids", "Worker output must not handle more than one route."))
    if _missing(output.get("thread_id")):
        violations.append(_violation("worker_outputs.thread_id", "Worker output requires non-empty thread_id."))
    else:
        if creation and output.get("thread_id") != creation.get("thread_id"):
            violations.append(_violation("worker_outputs.thread_id", "Worker output thread_id must match creation record."))
        if proof and output.get("thread_id") != proof.get("thread_id"):
            violations.append(_violation("worker_outputs.thread_id", "Worker output thread_id must match proof."))
    if not _is_skill_ref(_ref(output.get("skill_ref")), WORKER_SKILL_ID):
        violations.append(_violation("worker_outputs.skill_ref", "Worker output must reference TEST_WORKER_OPERATIONAL_SKILL v0.1."))
    if output.get("skill_received") is not True or output.get("skill_applied") is not True:
        violations.append(_violation("worker_outputs.skill_received", "Worker output must prove skill receipt/application."))
    if output.get("route_result") not in ALLOWED_ROUTE_RESULTS:
        violations.append(_violation("worker_outputs.route_result", "Worker output route_result is invalid."))

    command_evidence = _canonical_value(
        output,
        canonical="command_evidence",
        legacy="commands_run",
        adapters=adapters,
        field_prefix="worker_outputs",
        violations=violations,
        required=True,
    )
    if command_evidence is not None and not isinstance(command_evidence, list):
        violations.append(_violation("worker_outputs.command_evidence", "command_evidence must be a list."))

    for key in ("observations", "evidence_refs", "test_data_refs", "covered_scope", "uncovered_scope"):
        if key not in output or not isinstance(output.get(key), list):
            violations.append(_violation(f"worker_outputs.{key}", f"{key} must be present as a list."))

    if output.get("route_result") == "failed":
        if not _as_list(output.get("evidence_refs", [])) or not _as_list(output.get("failure_signatures", [])):
            violations.append(_violation("worker_outputs.failure_signatures", "failed route output requires evidence_refs and failure_signatures."))
    if output.get("route_result") == "passed" and output.get("mandatory_checks_skipped") is True:
        violations.append(_violation("worker_outputs.mandatory_checks_skipped", "passed route must not skip mandatory assigned checks."))
    if output.get("status") != "test_worker_report_candidate":
        violations.append(_violation("worker_outputs.status", "Worker output status must be test_worker_report_candidate."))
    if output.get("causal_status") != "scoped_evidence_candidate":
        violations.append(_violation("worker_outputs.causal_status", "Worker output causal_status must be scoped_evidence_candidate."))
    if output.get("whole_candidate_result_decided") is True or "whole_candidate_result" in output:
        violations.append(_violation("worker_outputs.whole_candidate_result", "Worker must not decide whole-candidate acceptance."))
    _check_true_fields(output, "worker_outputs", WORKER_FORBIDDEN_TRUE_FIELDS, violations)


def _check_model_fields(
    payload: dict[str, Any],
    prefix: str,
    adapters: set[tuple[str, str]],
    violations: list[dict[str, Any]],
) -> None:
    requested_effort = _canonical_value(
        payload,
        canonical="requested_reasoning_effort",
        legacy="requested_reasoning_budget",
        adapters=adapters,
        field_prefix=prefix,
        violations=violations,
        required=True,
    )
    policy_budget = payload.get("policy_reasoning_budget")
    if _missing(policy_budget):
        violations.append(_violation(f"{prefix}.policy_reasoning_budget", "policy_reasoning_budget is required."))
    elif requested_effort and requested_effort != policy_budget:
        violations.append(_violation(f"{prefix}.requested_reasoning_effort", "requested_reasoning_effort must match policy_reasoning_budget."))
    if _missing(payload.get("requested_model")):
        violations.append(_violation(f"{prefix}.requested_model", "requested_model is required."))
    if _missing(payload.get("policy_model")):
        violations.append(_violation(f"{prefix}.policy_model", "policy_model is required."))
    elif payload.get("requested_model") and payload.get("requested_model") != payload.get("policy_model") and payload.get("fallback_used") is not True:
        violations.append(_violation(f"{prefix}.policy_model", "model mismatch without explicit fallback is forbidden."))
    if "fallback_used" not in payload:
        violations.append(_violation(f"{prefix}.fallback_used", "fallback_used audit field is required."))
    if payload.get("fallback_used") is True:
        fallback_allowed = payload.get("active_profile_fallback_allowed") is True or payload.get("fallback_allowed") is True
        if not fallback_allowed:
            violations.append(_violation(f"{prefix}.fallback_used", "fallback is forbidden while active role profile has fallback_allowed:false."))
        if _missing(payload.get("fallback_reason")) or not _as_list(payload.get("fallback_evidence_refs", [])):
            violations.append(_violation(f"{prefix}.fallback_evidence_refs", "fallback requires reason and evidence refs."))


def _check_final_result(
    final_result: dict[str, Any],
    *,
    routes: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    governance_check: dict[str, Any],
    violations: list[dict[str, Any]],
) -> None:
    if not final_result:
        violations.append(_violation("final_test_result", "final_test_result is required."))
        return
    result = final_result.get("result")
    if result not in ALLOWED_FINAL_RESULTS:
        violations.append(_violation("final_test_result.result", "final Test result label is invalid."))
        return
    next_route = final_result.get("next_route")
    if next_route not in ALLOWED_NEXT_ROUTES:
        violations.append(_violation("final_test_result.next_route", "next_route must be execution or final_review."))
    if next_route == "master":
        violations.append(_violation("final_test_result.next_route", "Test must not route directly to Master."))

    mandatory_ids = {str(route.get("route_id")) for route in routes if route.get("mandatory", True)}
    output_by_route = {str(output.get("route_id")): output for output in outputs}
    mandatory_outputs = [output_by_route[route_id] for route_id in mandatory_ids if route_id in output_by_route]

    expected: str | None = None
    if result == "request_more_context":
        expected = "request_more_context"
    elif final_result.get("blocker_kind") == "governance" and result == "blocked":
        expected = "blocked"
    elif mandatory_outputs:
        route_results = [str(output.get("route_result")) for output in mandatory_outputs]
        if "blocked" in route_results:
            expected = "blocked"
        elif "failed" in route_results:
            expected = "failed"
        elif "inconclusive" in route_results:
            expected = "inconclusive"
        elif _as_list(final_result.get("uncovered_scope", [])):
            expected = "passed_with_scope_limit"
        else:
            expected = "passed"

    if expected is not None and result != expected:
        violations.append(_violation("final_test_result.result", f"final result must follow evidence-state aggregation; expected {expected}, got {result}."))

    if result in {"failed", "inconclusive", "request_more_context"}:
        if next_route != "execution":
            violations.append(_violation("final_test_result.next_route", f"{result} must route to Execution Leader."))
    if result == "blocked":
        governance = final_result.get("blocker_kind") == "governance"
        if governance and final_result.get("requires_governance_review") is True:
            if next_route != "final_review":
                violations.append(_violation("final_test_result.next_route", "governance blocker requiring review must route to Final Review."))
        elif next_route != "execution":
            violations.append(_violation("final_test_result.next_route", "ordinary blocked result must route to Execution Leader."))
    if result in {"passed", "passed_with_scope_limit"} and next_route != "final_review":
        violations.append(_violation("final_test_result.next_route", "passed results must route to Final Review."))
    if result == "passed" and _as_list(final_result.get("uncovered_scope", [])):
        violations.append(_violation("final_test_result.uncovered_scope", "passed result must not hide uncovered scope."))
    if result == "passed_with_scope_limit":
        route_results = [str(output.get("route_result")) for output in mandatory_outputs]
        if any(item in {"failed", "blocked", "inconclusive"} for item in route_results):
            violations.append(_violation("final_test_result.result", "passed_with_scope_limit is forbidden when a mandatory route failed, blocked, or was inconclusive."))
    if result == "inconclusive":
        if any(str(output.get("route_result")) == "failed" for output in mandatory_outputs):
            violations.append(_violation("final_test_result.result", "proven candidate failure must not be downgraded to inconclusive because owner is ambiguous."))


def _check_reproducibility(run: dict[str, Any], final_result: dict[str, Any], violations: list[dict[str, Any]]) -> None:
    if not _ref(run.get("reproducibility_set")) and _missing(final_result.get("reproducibility_set_ref")):
        violations.append(_violation("reproducibility_set", "reproducibility_set or reproducibility_set_ref is required."))
    if not _ref(run.get("artifact_manifest")) and _missing(final_result.get("artifact_manifest_ref")):
        violations.append(_violation("artifact_manifest", "artifact_manifest or artifact_manifest_ref is required."))


def _check_forbidden_flags(run: dict[str, Any], final_result: dict[str, Any], violations: list[dict[str, Any]]) -> None:
    boundaries = _ref(run.get("boundaries"))
    for payload, prefix in ((run, "run"), (final_result, "final_test_result"), (boundaries, "boundaries")):
        _check_true_fields(payload, prefix, FORBIDDEN_TRUE_FIELDS, violations)


def _check_true_fields(payload: dict[str, Any], prefix: str, fields: tuple[str, ...], violations: list[dict[str, Any]]) -> None:
    for field_name in fields:
        if payload.get(field_name) is True:
            violations.append(_violation(f"{prefix}.{field_name}", f"{field_name} must remain false."))


def _check_skill_file(path: str | Path, *, field: str, required_markers: list[str], violations: list[dict[str, Any]]) -> None:
    p = Path(path)
    if not p.is_file():
        violations.append(_violation(field, f"skill/contract file not found: {p}"))
        return
    text = p.read_text(encoding="utf-8")
    missing = [marker for marker in required_markers if marker not in text]
    if missing:
        violations.append(_violation(field, "file missing marker(s): " + ", ".join(missing)))


def _canonical_value(
    payload: dict[str, Any],
    *,
    canonical: str,
    legacy: str,
    adapters: set[tuple[str, str]],
    field_prefix: str,
    violations: list[dict[str, Any]],
    required: bool,
) -> Any:
    if canonical in payload and not _missing(payload.get(canonical)):
        return payload.get(canonical)
    if legacy in payload and not _missing(payload.get(legacy)):
        if (legacy, canonical) in adapters:
            return payload.get(legacy)
        violations.append(_violation(f"{field_prefix}.{canonical}", f"{canonical} is required; legacy {legacy} needs explicit compatibility adapter."))
        return None
    if required:
        violations.append(_violation(f"{field_prefix}.{canonical}", f"{canonical} is required."))
    return None


def _adapter_pairs(value: Any) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return pairs
    for item in value:
        if not isinstance(item, dict):
            continue
        if item.get("enabled", True) is False:
            continue
        source = item.get("from") or item.get("from_field") or item.get("legacy_field")
        target = item.get("to") or item.get("to_field") or item.get("canonical_field")
        if isinstance(source, str) and isinstance(target, str):
            pairs.add((source, target))
    return pairs


def _is_pre_route_terminal(run: dict[str, Any]) -> bool:
    final_result = _ref(run.get("final_test_result") or run.get("final_report"))
    return final_result.get("result") in {"request_more_context", "blocked"} and not run.get("worker_creation_requests")


def _is_skill_ref(value: dict[str, Any], skill_id: str) -> bool:
    return value.get("skill_id") == skill_id and value.get("skill_version") == SKILL_VERSION


def _ref(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_dict_list(value: Any, field: str, violations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        violations.append(_violation(field, f"{field} must be a list."))
        return []
    output: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if isinstance(item, dict):
            output.append(dict(item))
        else:
            violations.append(_violation(f"{field}[{index}]", f"{field} item must be an object."))
    return output


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _missing(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _violation(field: str, reason: str) -> dict[str, Any]:
    return {"field": field, "reason": reason}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Aegis Test Leader/Worker role operational skill enforcement.")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="Validate one Test role-skill run JSON artifact.")
    validate.add_argument("--run", required=True, help="Path to Test skill run JSON.")
    validate.add_argument("--leader-skill", help="Optional path to TEST_LEADER_OPERATIONAL_SKILL.md.")
    validate.add_argument("--worker-skill", help="Optional path to TEST_WORKER_OPERATIONAL_SKILL.md.")
    validate.add_argument("--enforcement-contract", help="Optional path to TEST_LEADER_WORKER_SKILL_ENFORCEMENT_CONTRACT.md.")
    validate.add_argument("--output", help="Optional output path for validation result JSON.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    if args.command == "validate":
        result = validate_test_skill_run_file(
            args.run,
            leader_skill_path=args.leader_skill,
            worker_skill_path=args.worker_skill,
            enforcement_contract_path=args.enforcement_contract,
        ).to_dict()
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
