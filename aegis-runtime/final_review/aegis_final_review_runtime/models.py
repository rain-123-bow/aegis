from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

DecisionLabel = Literal[
    "accept_for_master",
    "accept_for_master_with_scope_limit",
    "reject_to_execution_via_master",
    "request_test_expansion_via_master",
    "request_more_evidence_via_master",
    "governance_blocker_to_master",
    "blocked_resource_policy",
]
ResourceStatus = Literal["satisfied", "missing", "unavailable", "insufficient", "fallback_forbidden"]


class FinalReviewContractError(ValueError):
    """Raised when Final Review runtime input violates the demo contract."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_string(value: Any, name: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise FinalReviewContractError(f"{name} must be a {'possibly empty ' if allow_empty else ''}string")
    return value


def _ensure_string_list(value: Any, name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise FinalReviewContractError(f"{name} must be a list of strings")
    return list(value)


@dataclass(frozen=True)
class ResourcePolicy:
    policy_ref: str
    required_profile: str
    resolved_profile: str
    reasoning_budget: str
    fallback_used: bool
    status: ResourceStatus

    @classmethod
    def from_dict(cls, value: Any) -> "ResourcePolicy":
        if value is None:
            return cls(
                policy_ref="",
                required_profile="final_review_leader",
                resolved_profile="",
                reasoning_budget="unknown",
                fallback_used=False,
                status="missing",
            )
        if not isinstance(value, dict):
            raise FinalReviewContractError("resource_policy must be an object")
        status = value.get("status", "missing")
        if status not in {"satisfied", "missing", "unavailable", "insufficient", "fallback_forbidden"}:
            raise FinalReviewContractError("resource_policy.status is invalid")
        return cls(
            policy_ref=_ensure_string(value.get("policy_ref", ""), "resource_policy.policy_ref", allow_empty=True),
            required_profile=_ensure_string(
                value.get("required_profile", "final_review_leader"), "resource_policy.required_profile"
            ),
            resolved_profile=_ensure_string(
                value.get("resolved_profile", ""), "resource_policy.resolved_profile", allow_empty=True
            ),
            reasoning_budget=_ensure_string(
                value.get("reasoning_budget", "unknown"), "resource_policy.reasoning_budget"
            ),
            fallback_used=bool(value.get("fallback_used", False)),
            status=status,  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_ref": self.policy_ref,
            "required_profile": self.required_profile,
            "resolved_profile": self.resolved_profile,
            "reasoning_budget": self.reasoning_budget,
            "fallback_used": self.fallback_used,
            "status": self.status,
        }


@dataclass(frozen=True)
class ReviewedRefs:
    execution_final_report_ref: str
    execution_causal_chain_ref: str
    test_final_report_ref: str
    test_plan_ref: str
    test_route_report_refs: list[str]
    test_evidence_refs: list[str]
    reproducibility_set_ref: str
    artifact_manifest_ref: str
    debate_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: Any) -> "ReviewedRefs":
        if not isinstance(value, dict):
            raise FinalReviewContractError("reviewed_refs must be an object")
        return cls(
            execution_final_report_ref=_ensure_string(
                value.get("execution_final_report_ref", ""), "reviewed_refs.execution_final_report_ref", allow_empty=True
            ),
            execution_causal_chain_ref=_ensure_string(
                value.get("execution_causal_chain_ref", ""), "reviewed_refs.execution_causal_chain_ref", allow_empty=True
            ),
            test_final_report_ref=_ensure_string(
                value.get("test_final_report_ref", ""), "reviewed_refs.test_final_report_ref", allow_empty=True
            ),
            test_plan_ref=_ensure_string(value.get("test_plan_ref", ""), "reviewed_refs.test_plan_ref", allow_empty=True),
            test_route_report_refs=_ensure_string_list(
                value.get("test_route_report_refs", []), "reviewed_refs.test_route_report_refs"
            ),
            test_evidence_refs=_ensure_string_list(value.get("test_evidence_refs", []), "reviewed_refs.test_evidence_refs"),
            reproducibility_set_ref=_ensure_string(
                value.get("reproducibility_set_ref", ""), "reviewed_refs.reproducibility_set_ref", allow_empty=True
            ),
            artifact_manifest_ref=_ensure_string(
                value.get("artifact_manifest_ref", ""), "reviewed_refs.artifact_manifest_ref", allow_empty=True
            ),
            debate_refs=_ensure_string_list(value.get("debate_refs", []), "reviewed_refs.debate_refs"),
        )

    def missing_required(self) -> list[str]:
        missing: list[str] = []
        for field_name in (
            "execution_final_report_ref",
            "execution_causal_chain_ref",
            "test_final_report_ref",
            "test_plan_ref",
            "reproducibility_set_ref",
            "artifact_manifest_ref",
        ):
            if not getattr(self, field_name):
                missing.append(f"reviewed_refs.{field_name}")
        if not self.test_route_report_refs:
            missing.append("reviewed_refs.test_route_report_refs")
        if not self.test_evidence_refs:
            missing.append("reviewed_refs.test_evidence_refs")
        return missing

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_final_report_ref": self.execution_final_report_ref,
            "execution_causal_chain_ref": self.execution_causal_chain_ref,
            "test_final_report_ref": self.test_final_report_ref,
            "test_plan_ref": self.test_plan_ref,
            "test_route_report_refs": list(self.test_route_report_refs),
            "test_evidence_refs": list(self.test_evidence_refs),
            "reproducibility_set_ref": self.reproducibility_set_ref,
            "artifact_manifest_ref": self.artifact_manifest_ref,
            "debate_refs": list(self.debate_refs),
        }


@dataclass(frozen=True)
class FinalReviewInputPackage:
    task_scope: list[str]
    final_code_ref: str
    implementation_candidate_ref: str
    tested_candidate_ref: str
    reviewed_refs: ReviewedRefs
    accepted_scope: list[str]
    blocked_scope: list[str]
    known_limits: list[str]
    missing_evidence: list[str]
    governance_blockers: list[str]
    material_conditions: list[str]
    assumptions: list[str]
    execution_defects: list[str]
    test_evidence_deficiencies: list[str]
    evidence_contradictions: list[str]
    object_mapping_evidence: list[str]
    debate_used: bool

    @classmethod
    def from_dict(cls, value: Any) -> "FinalReviewInputPackage":
        if not isinstance(value, dict):
            raise FinalReviewContractError("final_review_input_package must be an object")
        reviewed_refs = ReviewedRefs.from_dict(value.get("reviewed_refs", {}))
        return cls(
            task_scope=_ensure_string_list(value.get("task_scope", []), "input.task_scope"),
            final_code_ref=_ensure_string(value.get("final_code_ref", ""), "input.final_code_ref", allow_empty=True),
            implementation_candidate_ref=_ensure_string(
                value.get("implementation_candidate_ref", ""), "input.implementation_candidate_ref", allow_empty=True
            ),
            tested_candidate_ref=_ensure_string(
                value.get("tested_candidate_ref", ""), "input.tested_candidate_ref", allow_empty=True
            ),
            reviewed_refs=reviewed_refs,
            accepted_scope=_ensure_string_list(value.get("accepted_scope", []), "input.accepted_scope"),
            blocked_scope=_ensure_string_list(value.get("blocked_scope", []), "input.blocked_scope"),
            known_limits=_ensure_string_list(value.get("known_limits", []), "input.known_limits"),
            missing_evidence=_ensure_string_list(value.get("missing_evidence", []), "input.missing_evidence"),
            governance_blockers=_ensure_string_list(value.get("governance_blockers", []), "input.governance_blockers"),
            material_conditions=_ensure_string_list(value.get("material_conditions", []), "input.material_conditions"),
            assumptions=_ensure_string_list(value.get("assumptions", []), "input.assumptions"),
            execution_defects=_ensure_string_list(value.get("execution_defects", []), "input.execution_defects"),
            test_evidence_deficiencies=_ensure_string_list(
                value.get("test_evidence_deficiencies", []), "input.test_evidence_deficiencies"
            ),
            evidence_contradictions=_ensure_string_list(
                value.get("evidence_contradictions", []), "input.evidence_contradictions"
            ),
            object_mapping_evidence=_ensure_string_list(
                value.get("object_mapping_evidence", []), "input.object_mapping_evidence"
            ),
            debate_used=bool(value.get("debate_used", False)),
        )

    def refs_consistent(self) -> bool:
        if self.final_code_ref == self.implementation_candidate_ref == self.tested_candidate_ref:
            return True
        return bool(self.object_mapping_evidence)

    def missing_required(self) -> list[str]:
        missing: list[str] = []
        for field_name in ("final_code_ref", "implementation_candidate_ref", "tested_candidate_ref"):
            if not getattr(self, field_name):
                missing.append(field_name)
        missing.extend(self.reviewed_refs.missing_required())
        if self.debate_used and not self.reviewed_refs.debate_refs:
            missing.append("reviewed_refs.debate_refs")
        return missing

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_scope": list(self.task_scope),
            "final_code_ref": self.final_code_ref,
            "implementation_candidate_ref": self.implementation_candidate_ref,
            "tested_candidate_ref": self.tested_candidate_ref,
            "reviewed_refs": self.reviewed_refs.to_dict(),
            "accepted_scope": list(self.accepted_scope),
            "blocked_scope": list(self.blocked_scope),
            "known_limits": list(self.known_limits),
            "missing_evidence": list(self.missing_evidence),
            "governance_blockers": list(self.governance_blockers),
            "material_conditions": list(self.material_conditions),
            "assumptions": list(self.assumptions),
            "execution_defects": list(self.execution_defects),
            "test_evidence_deficiencies": list(self.test_evidence_deficiencies),
            "evidence_contradictions": list(self.evidence_contradictions),
            "object_mapping_evidence": list(self.object_mapping_evidence),
            "debate_used": self.debate_used,
        }


@dataclass(frozen=True)
class FinalReviewRequest:
    request_id: str
    source: str
    resource_policy: ResourcePolicy
    final_review_input_package: FinalReviewInputPackage

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "FinalReviewRequest":
        if not isinstance(value, dict):
            raise FinalReviewContractError("final review request must be an object")
        return cls(
            request_id=_ensure_string(value.get("request_id") or f"final-review-{uuid4().hex}", "request.request_id"),
            source=_ensure_string(value.get("source", "test"), "request.source"),
            resource_policy=ResourcePolicy.from_dict(value.get("resource_policy")),
            final_review_input_package=FinalReviewInputPackage.from_dict(value.get("final_review_input_package", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "source": self.source,
            "resource_policy": self.resource_policy.to_dict(),
            "final_review_input_package": self.final_review_input_package.to_dict(),
        }


@dataclass(frozen=True)
class FinalReviewResult:
    final_review_result_id: str
    request_id: str
    decision: DecisionLabel
    target: Literal["master"]
    why: str
    final_code_ref: str
    implementation_candidate_ref: str
    tested_candidate_ref: str
    reviewed_refs: ReviewedRefs
    accepted_scope: list[str]
    blocked_scope: list[str]
    known_limits: list[str]
    missing_evidence: list[str]
    governance_blockers: list[str]
    resource_policy: ResourcePolicy
    causal_boundary: str
    recommended_master_action: str
    status: Literal["final_review_recommendation"] = "final_review_recommendation"
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_review_result_id": self.final_review_result_id,
            "request_id": self.request_id,
            "decision": self.decision,
            "target": self.target,
            "why": self.why,
            "final_code_ref": self.final_code_ref,
            "implementation_candidate_ref": self.implementation_candidate_ref,
            "tested_candidate_ref": self.tested_candidate_ref,
            "reviewed_refs": self.reviewed_refs.to_dict(),
            "accepted_scope": list(self.accepted_scope),
            "blocked_scope": list(self.blocked_scope),
            "known_limits": list(self.known_limits),
            "missing_evidence": list(self.missing_evidence),
            "governance_blockers": list(self.governance_blockers),
            "resource_policy": self.resource_policy.to_dict(),
            "causal_boundary": self.causal_boundary,
            "recommended_master_action": self.recommended_master_action,
            "status": self.status,
            "created_at": self.created_at,
        }
