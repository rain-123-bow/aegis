"""Data contracts for Final Review Subgraph v2."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, Literal
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from aegis.models import StrictModel, utc_now


FinalReviewDecision = Literal[
    "accept_for_master_closeout",
    "accept_with_scope_limits",
    "reject_to_execution",
    "request_more_test_evidence",
    "governance_blocker",
    "causal_conflict_detected",
]
FinalReviewStatus = Literal["accepted", "accepted_with_scope_limits", "rejected", "blocked"]
NextStage = Literal["master_closeout", "execution", "test", "master"]
Severity = Literal["critical", "error", "warning", "info"]
ProhibitedActionRiskClass = Literal[
    "test_execution",
    "code_mutation",
    "truth_store_mutation",
    "external_side_effect",
    "governance_bypass",
]
FinalReviewBlocker = Literal[
    "missing_required_artifact",
    "artifact_hash_mismatch",
    "artifact_root_escape",
    "code_root_escape",
    "execution_not_completed",
    "execution_wrong_next_stage",
    "test_not_passed",
    "test_wrong_next_stage",
    "boundary_flag_violation",
    "terminal_consistency_mismatch",
    "context_unavailable",
    "schema_validation_failed",
    "test_artifact_schema_failed",
    "test_state_boundary_failed",
    "code_surface_mismatch",
    "critical_threat",
    "hard_requirement_mismatch",
    "active_causal_conflict",
]

REQUIRED_THREAT_CHECKLIST_IDS: tuple[str, ...] = (
    "THREAT-001-shell-command-execution",
    "THREAT-002-path-input-handling",
    "THREAT-003-file-delete-move-overwrite-recursive-scan",
    "THREAT-004-secret-read-or-logging",
    "THREAT-005-network-or-remote-publication",
    "THREAT-006-truth-store-write",
    "THREAT-007-governance-bypass",
    "THREAT-008-unbounded-resource-or-concurrency",
    "THREAT-009-raw-report-trust",
    "THREAT-010-unadmitted-dependency-or-platform-assumption",
)


class ArtifactRef(StrictModel):
    """Reference to a local artifact file or folder."""

    artifact_id: str
    artifact_type: str
    path: str
    readme_path: str
    sha256: str
    created_by_node: str
    created_at_utc: str = Field(default_factory=utc_now)
    round: int | None = None

    @field_validator("artifact_id", "artifact_type", "path", "readme_path", "sha256", "created_by_node")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class FinalReviewProhibitedActionAttempt(StrictModel):
    """Forbidden action request that Final Review must deny and audit."""

    attempted_action: str
    requested_tool: str
    reason: str
    risk_class: ProhibitedActionRiskClass
    affected_artifact_refs: list[str] = Field(default_factory=list)

    @field_validator("attempted_action", "requested_tool", "reason")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class FinalReviewInputPackage(StrictModel):
    """Input accepted by the standalone Final Review Subgraph."""

    __test__: ClassVar[bool] = False

    run_id: str = Field(default_factory=lambda: f"final-review-run-{uuid4().hex[:12]}")
    parent_thread_id: str | None = None
    project_root: Path
    code_root: Path
    requirement_package_dir: Path
    requirement_review_package_dir: Path
    execution_output_package_path: Path
    test_output_package_path: Path
    knowledge_context_path: Path | None = None
    causal_context_path: Path | None = None
    max_serialized_state_bytes: int = Field(default=65_536, ge=1)
    prohibited_action_attempts: list[FinalReviewProhibitedActionAttempt] = Field(default_factory=list)

    @field_validator("run_id")
    @classmethod
    def _run_id_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("run_id must not be blank")
        return stripped


class FinalReviewProjectBinding(StrictModel):
    """Resolved project roots for a Final Review run."""

    __test__: ClassVar[bool] = False

    project_root: Path
    code_root: Path
    archive_store_root: str
    knowledge_store_root: str
    causal_store_root: str
    final_review_artifact_root: Path


class FinalReviewInputValidation(StrictModel):
    """Machine-readable validation of Final Review handoff inputs."""

    requirement_package_valid: bool
    requirement_review_package_valid: bool
    execution_output_valid: bool
    test_output_valid: bool
    artifact_hashes_valid: bool
    boundary_flags_valid: bool
    code_root_valid: bool
    allowed_artifact_roots_valid: bool
    terminal_consistency_valid: bool
    status: Literal["accepted", "blocked"]
    blocker: FinalReviewBlocker | None = None
    reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _blocked_requires_blocker(self) -> "FinalReviewInputValidation":
        if self.status == "blocked" and self.blocker is None:
            raise ValueError("blocked validation requires blocker")
        return self


class FinalReviewContextPackage(StrictModel):
    """Bounded Knowledge/Causal context resolution result."""

    knowledge_refs: list[str] = Field(default_factory=list)
    causal_active_refs: list[str] = Field(default_factory=list)
    causal_candidate_refs: list[str] = Field(default_factory=list)
    rejected_refs: list[dict[str, Any]] = Field(default_factory=list)
    missing_context_items: list[dict[str, Any]] = Field(default_factory=list)
    degraded_recall: bool = False
    store_availability: dict[str, Literal["available", "missing", "degraded", "not_requested"]]
    requirement_context_sufficient: bool = True
    threat_context_sufficient: bool = True
    causal_context_sufficient: bool = True


class CodeSurfaceConsistency(StrictModel):
    """Consistency of Execution, Test, and current changed-file surfaces."""

    execution_changed_files_ref: ArtifactRef | None = None
    test_code_diff_ref: ArtifactRef | None = None
    final_review_current_manifest_ref: ArtifactRef
    changed_file_hashes_match_execution: bool
    changed_file_hashes_match_test: bool
    unexpected_current_changes: list[str] = Field(default_factory=list)
    missing_expected_changes: list[str] = Field(default_factory=list)
    symlink_or_path_escape_detected: bool = False
    comparison_mode: Literal["full_manifest", "changed_files_only", "not_applicable"] = "not_applicable"
    status: Literal["consistent", "mismatch", "not_applicable"]


class RequirementAlignmentItem(StrictModel):
    requirement_id: str
    status: Literal[
        "satisfied",
        "satisfied_with_scope_limit",
        "not_satisfied",
        "not_testable_from_available_evidence",
        "out_of_scope",
    ]
    evidence_refs: list[str] = Field(default_factory=list)


class ThreatChecklistItem(StrictModel):
    checklist_id: str
    question: str
    status: Literal["yes", "no", "not_applicable", "unknown"]
    evidence_refs: list[ArtifactRef] = Field(default_factory=list)
    reviewed_paths: list[str] = Field(default_factory=list)
    finding_refs: list[str] = Field(default_factory=list)
    blocker: bool = False


class ThreatChecklistMatrix(StrictModel):
    items: list[ThreatChecklistItem]
    all_items_answered: bool
    unknown_security_relevant_items: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _must_answer_all(self) -> "ThreatChecklistMatrix":
        if not self.items:
            raise ValueError("threat checklist requires items")
        ids = [item.checklist_id for item in self.items]
        if set(ids) != set(REQUIRED_THREAT_CHECKLIST_IDS):
            raise ValueError("threat checklist must cover every required threat surface")
        if len(ids) != len(set(ids)):
            raise ValueError("threat checklist ids must be unique")
        unanswered = [item.checklist_id for item in self.items if item.status == "unknown"]
        if unanswered and self.all_items_answered:
            raise ValueError("unknown checklist items cannot be all_items_answered")
        return self


class ReviewFinding(StrictModel):
    finding_id: str
    category: Literal[
        "requirement_alignment",
        "threat",
        "code_quality",
        "evidence",
        "causal_consistency",
        "governance",
    ]
    severity: Severity
    title: str
    description: str
    affected_refs: list[ArtifactRef] = Field(default_factory=list)
    evidence_refs: list[ArtifactRef] = Field(default_factory=list)
    requirement_ids: list[str] = Field(default_factory=list)
    knowledge_refs: list[str] = Field(default_factory=list)
    causal_refs: list[str] = Field(default_factory=list)
    recommendation: str
    recommended_next_owner: Literal["execution", "test", "master", "causal_review", "none"]
    blocks_closeout: bool

    @model_validator(mode="after")
    def _blocking_severity_consistency(self) -> "ReviewFinding":
        if self.blocks_closeout and self.severity not in {"critical", "error"}:
            raise ValueError("blocking findings must be critical or error severity")
        return self


class EvidenceReviewMatrix(StrictModel):
    test_output_status: str
    artifact_schema_status: str
    state_boundary_status: str
    evidence_matrix_status: str
    raw_report_overrode_structured_evidence: bool = False
    status: Literal["accepted", "gap", "blocked"]
    blocker: FinalReviewBlocker | None = None


class CausalRefAssessment(StrictModel):
    causal_ref: str
    status: Literal[
        "candidate",
        "admitted",
        "active",
        "invalidated",
        "superseded",
        "deprecated",
        "rejected",
        "pending_revalidation",
        "unknown",
    ]
    usable_as_hard_constraint: bool
    usable_as_advisory_context: bool
    conflict_materiality: Literal["none", "low", "medium", "high", "blocker"]
    assessment_reason: str


class FinalReviewDecisionTrace(StrictModel):
    matched_rule: str
    considered_rules: list[str]
    decision: FinalReviewDecision
    status: FinalReviewStatus
    next_stage: NextStage
    blocker: FinalReviewBlocker | None = None


class FinalReviewBoundaryFlags(StrictModel):
    code_modified: bool = False
    tests_run: bool = False
    workers_created: bool = False
    archive_truth_written: bool = False
    knowledge_truth_written: bool = False
    causal_truth_written: bool = False
    remote_published: bool = False
    external_side_effect_performed: bool = False
    long_text_in_state_detected: bool = False

    @model_validator(mode="after")
    def _forbidden_flags(self) -> "FinalReviewBoundaryFlags":
        if (
            self.code_modified
            or self.tests_run
            or self.workers_created
            or self.archive_truth_written
            or self.knowledge_truth_written
            or self.causal_truth_written
            or self.remote_published
            or self.external_side_effect_performed
        ):
            raise ValueError("Final Review boundary flags must remain false")
        return self


class FinalReviewStateBoundaryResult(StrictModel):
    serialized_state_size_bytes: int = Field(ge=0)
    max_serialized_state_bytes: int = Field(default=65_536, ge=1)
    long_text_fields_detected: list[str] = Field(default_factory=list)
    artifact_refs_only: bool
    status: Literal["passed", "failed"]


class FinalReviewRunManifest(StrictModel):
    run_id: str
    current_terminal_status: FinalReviewStatus
    decision: FinalReviewDecision
    input_validation_hash: str
    input_fingerprint_sha256: str | None = None
    final_report_hash: str | None = None
    final_review_output_package_hash_path: str | None = None
    final_review_output_package_hash_policy: Literal["detached_after_closeout"] = "detached_after_closeout"


class FinalReviewOutputPackage(StrictModel):
    """Terminal package returned to Parent Graph."""

    __test__: ClassVar[bool] = False

    schema_version: Literal["final_review.output.v2"] = "final_review.output.v2"
    run_id: str
    status: FinalReviewStatus
    decision: FinalReviewDecision
    next_stage: NextStage
    final_review_run_dir: str
    input_validation_ref: ArtifactRef
    context_resolution_ref: ArtifactRef
    code_surface_manifest_ref: ArtifactRef
    requirement_alignment_ref: ArtifactRef
    threat_findings_ref: ArtifactRef
    code_quality_findings_ref: ArtifactRef
    evidence_review_ref: ArtifactRef
    causal_consistency_ref: ArtifactRef
    threat_checklist_matrix_ref: ArtifactRef
    code_surface_consistency_ref: ArtifactRef
    decision_precedence_trace_ref: ArtifactRef
    final_review_report_ref: ArtifactRef
    decision_ref: ArtifactRef
    next_route_ref: ArtifactRef
    run_manifest_ref: ArtifactRef
    evidence_index_ref: ArtifactRef
    artifact_hashes_ref: ArtifactRef
    artifact_schema_validation_ref: ArtifactRef
    state_boundary_results_ref: ArtifactRef
    tool_audit_ref: ArtifactRef
    boundary_flags: FinalReviewBoundaryFlags = Field(default_factory=FinalReviewBoundaryFlags)
    scope_limits: list[str] = Field(default_factory=list)
    blocker: FinalReviewBlocker | None = None

    @model_validator(mode="after")
    def _terminal_consistency(self) -> "FinalReviewOutputPackage":
        if self.decision == "accept_for_master_closeout":
            if self.status != "accepted" or self.next_stage != "master_closeout":
                raise ValueError("accept_for_master_closeout requires accepted/master_closeout")
            if self.blocker is not None or self.scope_limits:
                raise ValueError("accepted closeout must not carry blocker or scope limits")
        elif self.decision == "accept_with_scope_limits":
            if self.status != "accepted_with_scope_limits" or self.next_stage != "master_closeout":
                raise ValueError("accept_with_scope_limits requires accepted_with_scope_limits/master_closeout")
            if self.blocker is not None or not self.scope_limits:
                raise ValueError("accept_with_scope_limits requires scope limits and no blocker")
        elif self.decision == "reject_to_execution":
            if self.status != "rejected" or self.next_stage != "execution" or self.blocker is None:
                raise ValueError("reject_to_execution requires rejected/execution with blocker")
        elif self.decision == "request_more_test_evidence":
            if self.status != "blocked" or self.next_stage != "test" or self.blocker is None:
                raise ValueError("request_more_test_evidence requires blocked/test with blocker")
        elif self.decision == "governance_blocker":
            if self.status != "blocked" or self.next_stage != "master" or self.blocker is None:
                raise ValueError("governance_blocker requires blocked/master with blocker")
        elif self.decision == "causal_conflict_detected":
            if (
                self.status != "blocked"
                or self.next_stage != "master"
                or self.blocker != "active_causal_conflict"
            ):
                raise ValueError("causal_conflict_detected requires active causal conflict blocker")
        return self
