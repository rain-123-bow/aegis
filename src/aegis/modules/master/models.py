from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from aegis.models import StrictModel, utc_now


ConstraintSource = Literal[
    "user",
    "explicit_requirement",
    "project_knowledge",
    "customer_written_evidence",
    "regulatory",
    "platform",
    "hard_cost",
    "first_principle",
]
ConstraintAdmission = Literal["candidate", "hard_constraint", "preference", "rejected"]
ReviewDecision = Literal[
    "accept",
    "reject_as_hard_constraint",
    "request_more_evidence",
    "route_to_debate",
]
ContinuityStatus = Literal["clean", "dirty", "unknown_remote", "baseline_missing"]


class MasterGateError(RuntimeError):
    """Raised when a hard Master governance gate is violated."""


class RequirementConstraint(StrictModel):
    text: str
    source: ConstraintSource = "user"
    evidence_refs: list[str] = Field(default_factory=list)
    admission: ConstraintAdmission = "candidate"
    hard_constraint: bool = False
    reason: str = ""


class MasterArtifactRef(StrictModel):
    artifact_id: str
    kind: Literal[
        "requirement_intake",
        "requirement_document",
        "requirement_review",
        "execution_handoff",
    ]
    package_dir: str
    readme_path: str
    primary_document_path: str
    machine_data_path: str
    sha256: str
    created_at: str = Field(default_factory=utc_now)


class RequirementConversation(StrictModel):
    conversation_id: str = Field(default_factory=lambda: f"conversation-{uuid4().hex[:8]}")
    goal: str
    purpose: str
    technical_path_requests: list[str] = Field(default_factory=list)
    deliverable_requests: list[str] = Field(default_factory=list)
    user_messages: list[str] = Field(default_factory=list)
    raw_constraints: list[RequirementConstraint] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    status: Literal["clarifying", "ready_for_document"] = "ready_for_document"


def _format_semantic_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        primary = value.get("request") or value.get("deliverable") or value.get("artifact")
        details: list[str] = []
        for key, detail in value.items():
            if key in {"request", "deliverable", "artifact", "hard_constraint_admitted", "reason"}:
                continue
            if detail in (None, "", [], {}):
                continue
            if isinstance(detail, list):
                detail_text = ", ".join(str(item) for item in detail)
            else:
                detail_text = str(detail)
            details.append(f"{key}: {detail_text}")
        if primary and details:
            return f"{primary}; {'; '.join(details)}".strip()
        if primary:
            return str(primary).strip()
    return str(value).strip()


def _format_admitted_constraint(value: Any) -> str:
    if isinstance(value, dict):
        if value.get("admitted") is False:
            return ""
        primary = (
            value.get("constraint")
            or value.get("text")
            or value.get("requirement")
            or value.get("request")
        )
        if primary:
            evidence = value.get("evidence_refs") or value.get("evidence_ref")
            if evidence:
                evidence_values = evidence if isinstance(evidence, list) else [evidence]
                evidence_text = ", ".join(str(item) for item in evidence_values)
                return f"{str(primary).strip()}; evidence_ref: {evidence_text}"
            return str(primary).strip()
    return _format_semantic_value(value)


def _coerce_semantic_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = [value]
    normalized = [_format_semantic_value(item) for item in values]
    return [item for item in normalized if item]


def _coerce_admitted_constraint_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = [value]
    normalized = [_format_admitted_constraint(item) for item in values]
    return [item for item in normalized if item]


class RequirementSemanticAnalysis(StrictModel):
    """Semantic interpretation supplied by PM LLM/agent, not by keyword parsing."""

    purpose: str
    technical_path_requests: list[str] = Field(default_factory=list)
    deliverable_requests: list[str] = Field(default_factory=list)
    hard_constraints: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    status: Literal["clarifying", "ready_for_document"] = "ready_for_document"

    @model_validator(mode="before")
    @classmethod
    def split_admitted_technical_paths(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        raw_paths = normalized.get("technical_path_requests") or []
        path_items = raw_paths if isinstance(raw_paths, list) else [raw_paths]
        hard_items = normalized.get("hard_constraints") or []
        hard_items = hard_items if isinstance(hard_items, list) else [hard_items]
        remaining_paths: list[Any] = []
        for item in path_items:
            if isinstance(item, dict) and item.get("hard_constraint_admitted") is True:
                hard_items.append(item)
            else:
                remaining_paths.append(item)
        normalized["technical_path_requests"] = remaining_paths
        normalized["hard_constraints"] = hard_items

        status = normalized.get("status")
        if status not in {"clarifying", "ready_for_document"}:
            unresolved = _coerce_semantic_text_list(normalized.get("unresolved_questions"))
            normalized["status"] = "clarifying" if unresolved else "ready_for_document"
        return normalized

    @field_validator(
        "technical_path_requests",
        "deliverable_requests",
        "preferences",
        "unresolved_questions",
        mode="before",
    )
    @classmethod
    def semantic_text_lists_accept_structured_agent_items(cls, value: Any) -> list[str]:
        return _coerce_semantic_text_list(value)

    @field_validator("hard_constraints", mode="before")
    @classmethod
    def hard_constraints_accept_structured_agent_items(cls, value: Any) -> list[str]:
        return _coerce_admitted_constraint_list(value)


class PmActorSession(StrictModel):
    """Stable resident Project Manager identity for one Master thread."""

    pm_session_id: str
    pm_agent_id: str
    pm_thread_id: str
    created_at: str = Field(default_factory=utc_now)
    status: Literal["active", "blocked", "closed"] = "active"
    creation_mechanism: Literal["runtime_resident_pm_session"] = "runtime_resident_pm_session"
    context_refs: list[MasterArtifactRef] = Field(default_factory=list)


class RequirementDocument(StrictModel):
    document_id: str = Field(default_factory=lambda: f"requirement-{uuid4().hex[:8]}")
    goal: str
    objective: str
    constraints: list[RequirementConstraint] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    excluded_subjective_preferences: list[str] = Field(default_factory=list)
    status: Literal["draft", "approved"] = "draft"
    created_at: str = Field(default_factory=utc_now)


class RequirementApprovalDecision(StrictModel):
    approved: bool
    approved_by: Literal["user"] = "user"
    artifact_id: str | None = None
    artifact_readme_path: str | None = None
    artifact_sha256: str | None = None
    comments: str = ""
    requested_changes: list[str] = Field(default_factory=list)
    decided_at: str = Field(default_factory=utc_now)


class DebateIssue(StrictModel):
    issue_id: str = Field(default_factory=lambda: f"debate-issue-{uuid4().hex[:8]}")
    question: str
    why: str
    candidate_positions: list[str] = Field(default_factory=list)
    status: Literal["pending", "resolved"] = "pending"
    result: dict[str, Any] | None = None


class RequirementReviewFinding(StrictModel):
    requirement_item: str
    decision: ReviewDecision
    why: str
    evidence_refs: list[str] = Field(default_factory=list)
    first_principles: list[str] = Field(default_factory=list)
    debate_issue_id: str | None = None


class RequirementReviewDocument(StrictModel):
    document_id: str = Field(default_factory=lambda: f"review-{uuid4().hex[:8]}")
    requirement_document_id: str
    findings: list[RequirementReviewFinding] = Field(default_factory=list)
    debate_issues: list[DebateIssue] = Field(default_factory=list)
    conclusion: str
    status: Literal["reviewed", "approved"] = "reviewed"
    created_at: str = Field(default_factory=utc_now)


class ExecutionHandoffPackage(StrictModel):
    handoff_id: str = Field(default_factory=lambda: f"execution-handoff-{uuid4().hex[:8]}")
    requirement_document_id: str
    review_document_id: str
    status: Literal["ready_for_execution"] = "ready_for_execution"
    accepted_constraints: list[str] = Field(default_factory=list)
    rejected_constraints: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    open_limits: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(
        default_factory=lambda: [
            "master_executes_code",
            "master_runs_tests",
            "master_merges_global_causal_truth",
        ]
    )


class ContinuityBaseline(StrictModel):
    project_key: str
    project_root: str
    remote_url: str
    baseline_commit: str
    tracked_fingerprint: str
    updated_at: str = Field(default_factory=utc_now)
    last_closeout_ref: str | None = None


class ContinuityCheckResult(StrictModel):
    status: ContinuityStatus
    can_proceed: bool
    project_root: str
    remote_url: str | None = None
    baseline_commit: str | None = None
    current_commit: str | None = None
    tracked_fingerprint: str | None = None
    action_taken: str | None = None
    quarantine_path: str | None = None
    blocked_reason: str | None = None
    message_to_user: str = ""


class MasterModuleState(StrictModel):
    phase: str = "not_started"
    continuity_check: ContinuityCheckResult | None = None
    pm_session: PmActorSession | None = None
    conversation_ref: MasterArtifactRef | None = None
    requirement_document_ref: MasterArtifactRef | None = None
    requirement_approval: RequirementApprovalDecision | None = None
    review_document_ref: MasterArtifactRef | None = None
    review_approval: RequirementApprovalDecision | None = None
    execution_handoff_ref: MasterArtifactRef | None = None
