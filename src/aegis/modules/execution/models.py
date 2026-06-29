"""Data contracts for Execution Subgraph v2."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from aegis.models import StrictModel, utc_now


ExecutionPhase = Literal["planning", "reviewing", "implementing", "testing", "completed", "blocked"]
OutputStatus = Literal[
    "completed",
    "blocked",
    "failed",
    "request_debate",
    "request_test",
    "request_developer_input",
    "accepted_with_scope_limits",
]
NextStage = Literal["test_subgraph", "master", "debate", "developer_input", "blocked_closeout"]
ReviewDecision = Literal["approved", "changes_required", "blocked", "request_debate"]
IssueSeverity = Literal["error", "warning", "suggestion"]
ChangeType = Literal["added", "modified", "deleted"]
CommandRisk = Literal[
    "read_only",
    "local_write",
    "destructive",
    "external_write",
    "remote_publish",
    "unknown",
]


class ArtifactRef(StrictModel):
    """Reference to a local artifact folder or file."""

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


class ProjectStoreRefs(StrictModel):
    """Project-local store roots available to ExecutionSubgraph."""

    knowledge_store_root: str
    causal_store_root: str
    knowledge_read_mode: Literal["readonly"] = "readonly"
    causal_read_mode: Literal["readonly_or_candidate_write"] = "readonly_or_candidate_write"
    candidate_write_root: str


class ProjectStoreBinding(ProjectStoreRefs):
    """Resolved project roots for ExecutionSubgraph runtime."""

    project_root: Path
    code_root: Path
    execution_artifact_root: Path


class ExecutionInputPackage(StrictModel):
    """Input accepted by the standalone ExecutionSubgraph."""

    run_id: str = Field(default_factory=lambda: f"execution-run-{uuid4().hex[:12]}")
    thread_id: str | None = None
    subgraph_thread_id: str | None = None
    project_root: Path
    code_root: Path | None = None
    master_handoff_path: Path
    max_review_rounds: int = Field(default=3, ge=1, le=10)
    deterministic_review_sequence: list["DeterministicReviewOutcome"] = Field(default_factory=list)
    planned_shell_commands: list[str] = Field(default_factory=list)
    simple_test_plan: list["SimpleTestCommandSpec"] = Field(default_factory=list)

    @field_validator("run_id")
    @classmethod
    def _run_id_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("run_id must not be blank")
        return stripped


class DeterministicReviewOutcome(StrictModel):
    """Deterministic review adapter output used to test graph routing."""

    decision: ReviewDecision
    score: int = Field(ge=0, le=100)
    error_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    suggestion_count: int = Field(default=0, ge=0)
    blocking_error: bool = False
    explanation: str = "Deterministic review outcome."
    required_change: str | None = None


class SimpleTestCommandSpec(StrictModel):
    """Approved simple-test command spec for Execution-owned sanity checks."""

    command_id: str
    command: str
    timeout_seconds: int = Field(default=10, gt=0, le=300)
    allowed_by_approved_plan: bool = True

    @field_validator("command_id", "command")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class ExecutionBlocker(StrictModel):
    """Terminal or routing blocker."""

    label: Literal[
        "plan_not_approved",
        "max_review_rounds_exceeded",
        "cross_project_scope",
        "missing_required_evidence",
        "unsafe_tool_request",
        "requires_debate",
        "unsupported_runtime_environment",
        "artifact_integrity_error",
        "implementation_boundary_violation",
    ]
    reason: str
    evidence_refs: list[str] = Field(default_factory=list)
    next_action: Literal["master", "debate", "developer_input", "test", "blocked_closeout"]
    parent_route_label: str = "master"
    required_payload_ref: ArtifactRef | None = None
    retry_allowed: bool = False


class ExecutionInputValidation(StrictModel):
    """Machine-readable validation result for Master handoff artifacts."""

    master_handoff_ref: ArtifactRef
    required_files_present: bool
    readme_valid: bool
    hashes_valid: bool
    accepted_constraints_valid: bool
    rejected_constraints_valid: bool
    evidence_refs_valid: bool
    requirement_review_valid: bool
    status: Literal["accepted", "blocked"]
    blocker: ExecutionBlocker | None = None

    @model_validator(mode="after")
    def _blocked_requires_blocker(self) -> "ExecutionInputValidation":
        if self.status == "blocked" and self.blocker is None:
            raise ValueError("blocked input validation requires blocker")
        return self


class ReviewBaseline(StrictModel):
    """Review Node independent understanding before plan review."""

    baseline_id: str
    requirement_understanding_ref: ArtifactRef
    review_criteria_ref: ArtifactRef
    hard_constraints_summary_ref: ArtifactRef
    non_goals_summary_ref: ArtifactRef
    created_before_plan_review: bool = True

    @model_validator(mode="after")
    def _must_be_before_review(self) -> "ReviewBaseline":
        if not self.created_before_plan_review:
            raise ValueError("review baseline must be created before plan review")
        return self


class ReviewIssue(StrictModel):
    """Structured review issue."""

    issue_id: str
    severity: IssueSeverity
    requirement_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    explanation: str
    required_change: str | None = None
    blocking: bool = False

    @field_validator("issue_id", "explanation")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class ReviewScorecard(StrictModel):
    """Review Node scorecard with consistency checks."""

    decision: ReviewDecision
    score: int = Field(ge=0, le=100)
    dimensions: dict[str, int]
    error_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    suggestion_count: int = Field(ge=0)
    blocking_issues: list[ReviewIssue] = Field(default_factory=list)
    non_blocking_issues: list[ReviewIssue] = Field(default_factory=list)
    policy_violations: list[str] = Field(default_factory=list)
    baseline_ref: ArtifactRef
    review_artifact_ref: ArtifactRef

    @model_validator(mode="after")
    def _consistent(self) -> "ReviewScorecard":
        if self.decision == "approved" and self.score < 95:
            raise ValueError("approved scorecards require score >= 95")
        if self.decision == "approved" and self.error_count != 0:
            raise ValueError("approved scorecards require error_count == 0")
        if self.error_count > 0 and self.decision == "approved":
            raise ValueError("error_count > 0 cannot approve")
        for issue in self.blocking_issues:
            if issue.severity != "error":
                raise ValueError("blocking issues must have severity=error")
            if not issue.blocking:
                raise ValueError("blocking issues must set blocking=True")
        if (
            self.decision != "approved"
            and self.score >= 95
            and self.error_count == 0
            and not self.blocking_issues
        ):
            raise ValueError("warning-only reviews with score >= 95 must approve")
        actual_errors = sum(
            1
            for issue in [*self.blocking_issues, *self.non_blocking_issues]
            if issue.severity == "error"
        )
        if actual_errors != self.error_count:
            raise ValueError("error_count must match issue severities")
        return self


class ReviewPolicyViolation(StrictModel):
    """Review policy violation with mandatory handling action."""

    violation_type: Literal[
        "warning_only_blocked",
        "suggestion_blocked",
        "out_of_scope_requirement",
        "preference_as_error",
        "scorecard_inconsistent",
    ]
    severity: Literal["warning", "material", "fatal"]
    action: Literal[
        "auto_override_to_approved",
        "request_review_repair",
        "escalate_master",
        "request_debate",
        "block",
    ]
    rationale: str
    source_review_ref: ArtifactRef
    repair_attempted: bool = False


class ExpectedFileChange(StrictModel):
    """Machine-readable expected file change from an approved plan."""

    change_id: str
    path: str
    allowed_change_types: list[ChangeType]
    requirement_refs: list[str]
    rationale: str


class ChangedFile(StrictModel):
    """Actual file change detected after implementation."""

    path: str
    change_type: ChangeType
    within_code_root: bool
    expected_by_plan: bool = False
    expected_change_id: str | None = None
    sha256_before: str | None = None
    sha256_after: str | None = None


class FileTreeEntry(StrictModel):
    """File entry captured by the implementation diff scanner."""

    path: str
    sha256: str
    size_bytes: int


class FileTreeSnapshot(StrictModel):
    """Snapshot of files under a code root."""

    root: str
    entries: list[FileTreeEntry] = Field(default_factory=list)


class ImplementationChangeSet(StrictModel):
    """Before/after proof of implementation file changes."""

    run_id: str
    approved_plan_ref: ArtifactRef
    expected_file_changes_ref: ArtifactRef
    before_tree_hash: str
    after_tree_hash: str
    changed_files: list[ChangedFile] = Field(default_factory=list)
    unexpected_changes: list[str] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    status: Literal["accepted", "blocked"] = "accepted"


class ImplementationFailurePolicy(StrictModel):
    """Policy for failed implementation writes."""

    on_failure: Literal[
        "preserve_dirty_tree_for_debug",
        "rollback_to_before_tree",
        "block_and_request_developer_input",
    ] = "preserve_dirty_tree_for_debug"
    retry_allowed: bool = True
    max_in_plan_repair_attempts: int = 1
    dirty_tree_snapshot_ref: ArtifactRef | None = None
    rollback_evidence_ref: ArtifactRef | None = None
    dirty_tree_status: Literal["clean", "dirty_preserved", "rolled_back", "unknown"] = "unknown"


class ToolActionPlan(StrictModel):
    """Planned tool action before execution."""

    action_id: str
    tool_name: str
    intent: str
    target_paths: list[str] = Field(default_factory=list)
    side_effect_level: Literal[
        "none",
        "read_only",
        "local_write",
        "destructive",
        "external_write",
        "remote_publish",
    ]
    requires_interrupt: bool
    approved_by: str | None = None
    expected_outputs: list[str] = Field(default_factory=list)


class CommandSafetyAnalysis(StrictModel):
    """Risk classification for shell commands."""

    command_id: str
    command: str
    cwd: str
    parsed_risk: CommandRisk
    touches_paths: list[str] = Field(default_factory=list)
    network_access_expected: bool = False
    requires_interrupt: bool
    allowed_by_approved_plan: bool = False


class ToolExecutionRecord(StrictModel):
    """Audit record for tool execution."""

    action_id: str
    status: Literal["skipped", "executed", "blocked", "failed"]
    command_or_tool_ref: str
    started_at_utc: str = Field(default_factory=utc_now)
    ended_at_utc: str = Field(default_factory=utc_now)
    exit_code: int | None = None
    stdout_ref: ArtifactRef | None = None
    stderr_ref: ArtifactRef | None = None
    changed_files: list[str] = Field(default_factory=list)
    error: str | None = None


class SimpleTestCommandEvidence(StrictModel):
    """Single simple test command evidence."""

    command_id: str
    command: str
    cwd: str
    timeout_seconds: int = Field(gt=0)
    exit_code: int
    stdout_ref: ArtifactRef
    stderr_ref: ArtifactRef
    duration_ms: int = Field(ge=0)
    status: Literal["passed", "failed", "skipped", "timeout"]


class SimpleTestEvidence(StrictModel):
    """Structured evidence for Execution-owned sanity checks."""

    run_id: str
    test_plan_ref: ArtifactRef
    commands: list[SimpleTestCommandEvidence]
    summary_status: Literal["passed", "failed", "partial", "not_run"]
    failure_reason: str | None = None

    @model_validator(mode="after")
    def _passed_requires_no_failed_commands(self) -> "SimpleTestEvidence":
        if self.summary_status == "passed":
            for command in self.commands:
                if command.status != "passed" or command.exit_code != 0:
                    raise ValueError("passed simple test evidence requires all commands to pass")
        return self


class ExecutionCausalDependencyGroup(StrictModel):
    """Dependency group in an execution causal candidate."""

    group_id: str
    causal_dependencies: dict[str, list[Any]] = Field(
        default_factory=lambda: {"existing_node_ids": [], "local_node_refs": []}
    )
    knowledge_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    scope: str
    confidence: Literal["high", "medium", "low"] = "medium"
    invalidation_conditions: list[str] = Field(default_factory=list)


class ExecutionCausalCandidateNode(StrictModel):
    """Causal candidate node proposed by Execution."""

    local_node_ref: str
    minimal_semantic_content: str
    semantic_summary: str
    semantic_keys: list[str]
    dependency_groups: list[ExecutionCausalDependencyGroup]


class ExecutionCausalCandidate(StrictModel):
    """Execution causal candidate package."""

    candidate_id: str
    source_module: Literal["execution"] = "execution"
    source_run_id: str
    source_artifact_ref: ArtifactRef
    proposed_nodes: list[ExecutionCausalCandidateNode]
    admission_requirements: dict[str, bool] = Field(
        default_factory=lambda: {
            "requires_master_review": True,
            "requires_causal_review": True,
        }
    )


class ExecutionCausalCandidateWriteResult(StrictModel):
    """Persistence result for execution causal candidate."""

    package_candidate_id: str
    artifact_ref: ArtifactRef
    db_candidate_node_ids: list[int] = Field(default_factory=list)
    reused_node_ids: list[int] = Field(default_factory=list)
    skipped_duplicate_refs: list[dict[str, Any]] = Field(default_factory=list)
    write_status: Literal["written", "artifact_only", "already_exists", "failed"]
    error: str | None = None


class ExecutionBoundaryFlags(StrictModel):
    """Truth and external publication boundary proof."""

    wrote_knowledge_truth: bool = False
    wrote_causal_truth: bool = False
    remote_published: bool = False

    @model_validator(mode="after")
    def _all_false(self) -> "ExecutionBoundaryFlags":
        if (
            self.wrote_knowledge_truth
            or self.wrote_causal_truth
            or self.remote_published
        ):
            raise ValueError("ExecutionOutputPackage boundary flags must remain false")
        return self


class ExecutionToTestHandoff(StrictModel):
    """Payload passed from Execution to Test Subgraph."""

    run_id: str
    implementation_artifact_ref: ArtifactRef
    implementation_changeset_ref: ArtifactRef
    changed_files_ref: ArtifactRef
    simple_test_evidence_ref: ArtifactRef
    known_limits_ref: ArtifactRef
    execution_causal_candidate_ref: ArtifactRef
    approved_review_ref: ArtifactRef
    requirement_mapping_ref: ArtifactRef


class ExecutionOutputPackage(StrictModel):
    """Terminal package returned to Parent Graph."""

    schema_version: Literal["execution.output.v2"] = "execution.output.v2"
    run_id: str
    status: OutputStatus
    phase: ExecutionPhase
    master_handoff_ref: ArtifactRef
    input_validation_ref: ArtifactRef
    review_baseline_ref: ArtifactRef | None = None
    approved_review_ref: ArtifactRef | None = None
    implementation_artifact_ref: ArtifactRef | None = None
    implementation_changeset_ref: ArtifactRef | None = None
    simple_test_evidence_ref: ArtifactRef | None = None
    execution_causal_candidate_ref: ArtifactRef | None = None
    execution_causal_candidate_write_result_ref: ArtifactRef | None = None
    blocker: ExecutionBlocker | None = None
    known_limits_ref: ArtifactRef | None = None
    boundary: ExecutionBoundaryFlags
    next_stage: NextStage
    execution_to_test_handoff_ref: ArtifactRef | None = None
    evidence_index_ref: ArtifactRef

    @model_validator(mode="after")
    def _terminal_consistency(self) -> "ExecutionOutputPackage":
        if self.status == "completed":
            if self.implementation_artifact_ref is None:
                raise ValueError("completed output requires implementation_artifact_ref")
            if self.implementation_changeset_ref is None:
                raise ValueError("completed output requires implementation_changeset_ref")
            if self.simple_test_evidence_ref is None:
                raise ValueError("completed output requires simple_test_evidence_ref")
            if self.next_stage != "test_subgraph":
                raise ValueError("completed output must route to test_subgraph")
        if self.status in {"blocked", "failed", "request_developer_input"} and self.blocker is None:
            raise ValueError("blocked/failed/developer-input output requires blocker")
        return self


class ExecutionNodeResult(StrictModel):
    """Machine-readable result from each graph node."""

    node_name: str
    status: Literal["ok", "terminal", "failed"]
    updated_state_fields: dict[str, Any] = Field(default_factory=dict)
    artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    error: dict[str, Any] | None = None
    idempotency_key: str | None = None
    safe_to_retry: bool = True


class RealAgentValidationResult(StrictModel):
    """Independent validator output for real-agent behavior evidence."""

    validator_name: Literal["RealAgentExecutionValidator", "RealAgentReviewValidator"]
    thread_id: str
    status: Literal["passed", "failed", "accepted_with_scope_limits"]
    checked_artifacts: list[ArtifactRef] = Field(default_factory=list)
    policy_violations: list[ReviewPolicyViolation] = Field(default_factory=list)
    behavior_findings_ref: ArtifactRef | None = None


class StateSizePolicy(StrictModel):
    """Maximum serialized state policy."""

    max_serialized_state_bytes: int = 65_536
    on_exceed: Literal["block", "write_artifact_and_replace_with_ref"] = (
        "write_artifact_and_replace_with_ref"
    )
