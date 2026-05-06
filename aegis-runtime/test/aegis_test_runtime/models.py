from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

ResultLabel = Literal["passed", "passed_with_scope_limit", "failed", "inconclusive", "blocked", "request_more_context"]
RouteResultLabel = Literal["passed", "failed", "inconclusive", "blocked"]
FeedbackKind = Literal["success", "failure", "inconclusive", "blocked", "missing_context", "governance_blocker"]
NextRoute = Literal["execution", "final_review"]
OwnerType = Literal["group", "integration", "ambiguous", "none"]
BlockerKind = Literal["environment", "dependency", "handoff", "candidate_material", "governance", "policy", "unknown"]


class TestContractError(ValueError):
    """Raised when the Test runtime violates the department contract."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_string(value: Any, name: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise TestContractError(f"{name} must be a {'possibly empty ' if allow_empty else ''}string")
    return value


def _ensure_string_list(value: Any, name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise TestContractError(f"{name} must be a list of non-empty strings")
    return list(value)


def _ensure_string_dict(value: Any, name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TestContractError(f"{name} must be an object")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise TestContractError(f"{name} keys must be non-empty strings")
        if not isinstance(item, str):
            raise TestContractError(f"{name}.{key} must be a string")
        result[key] = item
    return result


def _safe_rel_path(value: str, name: str) -> str:
    path = _ensure_string(value, name)
    parts = Path(path).parts
    if path.startswith("/") or ".." in parts:
        raise TestContractError(f"{name} must be repository-relative and safe")
    return path


@dataclass(frozen=True)
class OwnerHint:
    owner_type: OwnerType
    owner_id: str = ""

    @classmethod
    def from_dict(cls, value: Any) -> "OwnerHint":
        if value is None:
            return cls(owner_type="none")
        if not isinstance(value, dict):
            raise TestContractError("owner_hint must be an object")
        owner_type = value.get("owner_type", "none")
        if owner_type not in {"group", "integration", "ambiguous", "none"}:
            raise TestContractError("owner_hint.owner_type must be group, integration, ambiguous, or none")
        owner_id = value.get("owner_id", "")
        if not isinstance(owner_id, str):
            raise TestContractError("owner_hint.owner_id must be a string")
        return cls(owner_type=owner_type, owner_id=owner_id)

    def to_dict(self) -> dict[str, str]:
        data = {"owner_type": self.owner_type}
        if self.owner_id:
            data["owner_id"] = self.owner_id
        return data


@dataclass(frozen=True)
class TestRoute:
    route_id: str
    route_type: str
    mandatory: bool
    scope: list[str]
    method: str
    required_files: list[str] = field(default_factory=list)
    expected_patterns: dict[str, str] = field(default_factory=dict)
    commands: list[str] = field(default_factory=list)
    inspection_steps: list[str] = field(default_factory=list)
    evidence_requirements: list[str] = field(default_factory=list)
    failure_owner_files: list[str] = field(default_factory=list)
    simulate_result: RouteResultLabel | None = None
    blocker_kind: BlockerKind | None = None
    blocker_scope: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any], index: int) -> "TestRoute":
        if not isinstance(value, dict):
            raise TestContractError("test route must be an object")
        route_id = _ensure_string(value.get("route_id") or f"route_{index + 1}", "route.route_id")
        route_type = _ensure_string(value.get("route_type", "inspection"), "route.route_type")
        method = _ensure_string(value.get("method", "inspection"), "route.method")
        required_files = [_safe_rel_path(item, "route.required_files[]") for item in value.get("required_files", [])]
        expected_patterns = _ensure_string_dict(value.get("expected_patterns", {}), "route.expected_patterns")
        for path in expected_patterns:
            _safe_rel_path(path, "route.expected_patterns key")
        failure_owner_files = [_safe_rel_path(item, "route.failure_owner_files[]") for item in value.get("failure_owner_files", [])]
        simulate_result = value.get("simulate_result")
        if simulate_result is not None and simulate_result not in {"passed", "failed", "inconclusive", "blocked"}:
            raise TestContractError("route.simulate_result must be passed, failed, inconclusive, or blocked")
        blocker_kind = value.get("blocker_kind")
        if blocker_kind is not None and blocker_kind not in {
            "environment",
            "dependency",
            "handoff",
            "candidate_material",
            "governance",
            "policy",
            "unknown",
        }:
            raise TestContractError("route.blocker_kind is invalid")
        return cls(
            route_id=route_id,
            route_type=route_type,
            mandatory=bool(value.get("mandatory", True)),
            scope=_ensure_string_list(value.get("scope", []), "route.scope"),
            method=method,
            required_files=required_files,
            expected_patterns=expected_patterns,
            commands=_ensure_string_list(value.get("commands", []), "route.commands"),
            inspection_steps=_ensure_string_list(value.get("inspection_steps", []), "route.inspection_steps"),
            evidence_requirements=_ensure_string_list(value.get("evidence_requirements", []), "route.evidence_requirements"),
            failure_owner_files=failure_owner_files,
            simulate_result=simulate_result,
            blocker_kind=blocker_kind,
            blocker_scope=_ensure_string(value.get("blocker_scope", ""), "route.blocker_scope", allow_empty=True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "route_type": self.route_type,
            "mandatory": self.mandatory,
            "scope": list(self.scope),
            "method": self.method,
            "required_files": list(self.required_files),
            "expected_patterns": dict(self.expected_patterns),
            "commands": list(self.commands),
            "inspection_steps": list(self.inspection_steps),
            "evidence_requirements": list(self.evidence_requirements),
            "failure_owner_files": list(self.failure_owner_files),
            "simulate_result": self.simulate_result,
            "blocker_kind": self.blocker_kind,
            "blocker_scope": self.blocker_scope,
        }


@dataclass(frozen=True)
class TestRequest:
    request_id: str
    source: str
    objective: str
    scope: str
    base_branch: str
    integration_branch: str
    implementation_candidate_ref: str
    final_code_ref: str
    changed_files: list[str]
    ownership_map: dict[str, str]
    local_test_evidence: list[str]
    back_review_summaries: list[str]
    known_risks: list[str]
    expected_test_focus: list[str]
    success_criteria: list[str]
    forbidden_actions: list[str]
    evidence_refs: list[str]
    candidate_files: dict[str, str]
    route_specs: list[TestRoute]
    requested_actions: list[str]
    governance_review_required: bool = False
    uncovered_scope_override: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TestRequest":
        if not isinstance(value, dict):
            raise TestContractError("test request must be an object")
        changed_files = [_safe_rel_path(item, "request.changed_files[]") for item in value.get("changed_files", [])]
        candidate_files = _ensure_string_dict(value.get("candidate_files", {}), "request.candidate_files")
        for path in candidate_files:
            _safe_rel_path(path, "request.candidate_files key")
        return cls(
            request_id=_ensure_string(value.get("request_id") or f"test-run-{uuid4().hex}", "request.request_id"),
            source=_ensure_string(value.get("source", "execution"), "request.source"),
            objective=_ensure_string(value.get("objective", ""), "request.objective", allow_empty=True),
            scope=_ensure_string(value.get("scope", ""), "request.scope", allow_empty=True),
            base_branch=_ensure_string(value.get("base_branch", ""), "request.base_branch", allow_empty=True),
            integration_branch=_ensure_string(value.get("integration_branch", ""), "request.integration_branch", allow_empty=True),
            implementation_candidate_ref=_ensure_string(
                value.get("implementation_candidate_ref", ""), "request.implementation_candidate_ref", allow_empty=True
            ),
            final_code_ref=_ensure_string(value.get("final_code_ref", ""), "request.final_code_ref", allow_empty=True),
            changed_files=changed_files,
            ownership_map=_ensure_string_dict(value.get("ownership_map", {}), "request.ownership_map"),
            local_test_evidence=_ensure_string_list(value.get("local_test_evidence", []), "request.local_test_evidence"),
            back_review_summaries=_ensure_string_list(value.get("back_review_summaries", []), "request.back_review_summaries"),
            known_risks=_ensure_string_list(value.get("known_risks", []), "request.known_risks"),
            expected_test_focus=_ensure_string_list(value.get("expected_test_focus", []), "request.expected_test_focus"),
            success_criteria=_ensure_string_list(value.get("success_criteria", []), "request.success_criteria"),
            forbidden_actions=_ensure_string_list(value.get("forbidden_actions", []), "request.forbidden_actions"),
            evidence_refs=_ensure_string_list(value.get("evidence_refs", []), "request.evidence_refs"),
            candidate_files=candidate_files,
            route_specs=[TestRoute.from_dict(item, idx) for idx, item in enumerate(value.get("route_specs", []))],
            requested_actions=_ensure_string_list(value.get("requested_actions", []), "request.requested_actions"),
            governance_review_required=bool(value.get("governance_review_required", False)),
            uncovered_scope_override=_ensure_string_list(value.get("uncovered_scope_override", []), "request.uncovered_scope_override"),
        )

    def missing_context(self) -> list[str]:
        missing: list[str] = []
        for field_name in (
            "objective",
            "scope",
            "base_branch",
            "integration_branch",
            "implementation_candidate_ref",
            "final_code_ref",
        ):
            if not getattr(self, field_name):
                missing.append(field_name)
        if not self.changed_files:
            missing.append("changed_files")
        if not self.ownership_map:
            missing.append("ownership_map")
        if not self.local_test_evidence:
            missing.append("local_test_evidence")
        if not self.back_review_summaries:
            missing.append("back_review_summaries")
        if not self.expected_test_focus:
            missing.append("expected_test_focus")
        if not self.success_criteria:
            missing.append("success_criteria")
        return missing

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "source": self.source,
            "objective": self.objective,
            "scope": self.scope,
            "base_branch": self.base_branch,
            "integration_branch": self.integration_branch,
            "implementation_candidate_ref": self.implementation_candidate_ref,
            "final_code_ref": self.final_code_ref,
            "changed_files": list(self.changed_files),
            "ownership_map": dict(self.ownership_map),
            "local_test_evidence": list(self.local_test_evidence),
            "back_review_summaries": list(self.back_review_summaries),
            "known_risks": list(self.known_risks),
            "expected_test_focus": list(self.expected_test_focus),
            "success_criteria": list(self.success_criteria),
            "forbidden_actions": list(self.forbidden_actions),
            "evidence_refs": list(self.evidence_refs),
            "candidate_files": dict(self.candidate_files),
            "route_specs": [route.to_dict() for route in self.route_specs],
            "requested_actions": list(self.requested_actions),
            "governance_review_required": self.governance_review_required,
            "uncovered_scope_override": list(self.uncovered_scope_override),
        }


@dataclass(frozen=True)
class TestPlan:
    plan_id: str
    request_id: str
    objective: str
    validation_scope: list[str]
    mandatory_routes: list[str]
    optional_routes: list[str]
    routes: list[TestRoute]
    route_independence: list[str]
    artifact_plan: list[str]
    generated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "request_id": self.request_id,
            "objective": self.objective,
            "validation_scope": list(self.validation_scope),
            "mandatory_routes": list(self.mandatory_routes),
            "optional_routes": list(self.optional_routes),
            "routes": [route.to_dict() for route in self.routes],
            "route_independence": list(self.route_independence),
            "artifact_plan": list(self.artifact_plan),
            "generated_at": self.generated_at,
        }


@dataclass(frozen=True)
class TestWorkerReport:
    route_id: str
    worker_id: str
    route_scope: list[str]
    commands_run: list[dict[str, Any]]
    inspection_steps_run: list[str]
    logs: list[str]
    artifacts: list[str]
    environment: dict[str, Any]
    covered_scope: list[str]
    uncovered_scope: list[str]
    observations: list[str]
    route_result: RouteResultLabel
    failure_signatures: list[str]
    evidence_refs: list[str]
    test_data_refs: list[str]
    owner_hint: OwnerHint
    blocker_kind: BlockerKind | None
    blocker_scope: str
    why: str
    assumptions: list[str]
    material_conditions: list[str]
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "worker_id": self.worker_id,
            "route_scope": list(self.route_scope),
            "commands_run": list(self.commands_run),
            "inspection_steps_run": list(self.inspection_steps_run),
            "logs": list(self.logs),
            "artifacts": list(self.artifacts),
            "environment": dict(self.environment),
            "covered_scope": list(self.covered_scope),
            "uncovered_scope": list(self.uncovered_scope),
            "observations": list(self.observations),
            "route_result": self.route_result,
            "failure_signatures": list(self.failure_signatures),
            "evidence_refs": list(self.evidence_refs),
            "test_data_refs": list(self.test_data_refs),
            "owner_hint": self.owner_hint.to_dict(),
            "blocker_kind": self.blocker_kind,
            "blocker_scope": self.blocker_scope,
            "why": self.why,
            "assumptions": list(self.assumptions),
            "material_conditions": list(self.material_conditions),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class FinalTestReport:
    run_id: str
    request_id: str
    result: ResultLabel
    feedback_kind: FeedbackKind
    next_route: NextRoute
    decision: str
    final_code_ref: str
    implementation_candidate_ref: str
    test_plan_ref: str
    route_reports: list[dict[str, Any]]
    test_data_refs: list[str]
    evidence_refs: list[str]
    coverage_summary: dict[str, Any]
    covered_scope: list[str]
    uncovered_scope: list[str]
    failure_signatures: list[str]
    owner_hint: OwnerHint
    blocker_kind: BlockerKind | None
    blocker_scope: str
    requires_governance_review: bool
    required_next_action: str
    known_limits: list[str]
    assumptions: list[str]
    material_conditions: list[str]
    reproducibility_set_ref: str
    artifact_manifest_ref: str
    artifact_paths: dict[str, str]
    status: Literal["test_evidence_candidate"] = "test_evidence_candidate"
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "request_id": self.request_id,
            "result": self.result,
            "feedback_kind": self.feedback_kind,
            "next_route": self.next_route,
            "decision": self.decision,
            "final_code_ref": self.final_code_ref,
            "implementation_candidate_ref": self.implementation_candidate_ref,
            "test_plan_ref": self.test_plan_ref,
            "route_reports": list(self.route_reports),
            "test_data_refs": list(self.test_data_refs),
            "evidence_refs": list(self.evidence_refs),
            "coverage_summary": dict(self.coverage_summary),
            "covered_scope": list(self.covered_scope),
            "uncovered_scope": list(self.uncovered_scope),
            "failure_signatures": list(self.failure_signatures),
            "owner_hint": self.owner_hint.to_dict(),
            "blocker_kind": self.blocker_kind,
            "blocker_scope": self.blocker_scope,
            "requires_governance_review": self.requires_governance_review,
            "required_next_action": self.required_next_action,
            "known_limits": list(self.known_limits),
            "assumptions": list(self.assumptions),
            "material_conditions": list(self.material_conditions),
            "reproducibility_set_ref": self.reproducibility_set_ref,
            "artifact_manifest_ref": self.artifact_manifest_ref,
            "artifact_paths": dict(self.artifact_paths),
            "status": self.status,
            "created_at": self.created_at,
            "causal_boundary": "Test result is evidence and scoped conclusion only; it is not global causal truth.",
        }
