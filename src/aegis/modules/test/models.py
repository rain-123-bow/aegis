"""Data contracts for Test Subgraph v2."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, Literal
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from aegis.models import StrictModel, utc_now


TestStatus = Literal["passed", "failed", "blocked"]
NextStage = Literal["final_review", "execution", "master", "developer_input", "blocked_closeout"]
PlanReviewDecision = Literal["approved", "changes_required", "blocked"]
IssueSeverity = Literal["error", "warning", "suggestion"]
CommandRisk = Literal["read_only", "test_write", "destructive", "external_write", "remote_publish", "unknown"]
TestNodeStatus = Literal["passed", "failed", "blocked", "skipped", "timeout"]
TestFailureClassification = Literal[
    "input_invalid",
    "test_plan_not_approvable",
    "command_safety_block",
    "environment_unavailable",
    "process_incomplete",
    "evidence_gap",
    "code_mutation_detected",
    "artifact_schema_invalid",
    "round_limit_exceeded",
    "test_failure",
    "test_timeout",
]


class ArtifactRef(StrictModel):
    """Reference to an artifact file or folder. Long content is never carried inline."""

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


class TestInputPackage(StrictModel):
    """Input accepted by the standalone Test Subgraph."""

    __test__: ClassVar[bool] = False

    run_id: str = Field(default_factory=lambda: f"test-run-{uuid4().hex[:12]}")
    thread_id: str | None = None
    subgraph_thread_id: str | None = None
    project_root: Path
    code_root: Path | None = None
    execution_handoff_dir: Path
    execution_output_package_path: Path
    max_plan_review_rounds: int = Field(default=3, ge=1, le=10)
    max_completeness_rework_rounds: int = Field(default=2, ge=0, le=10)
    max_evidence_retest_rounds: int = Field(default=2, ge=0, le=10)
    deterministic_test_commands: list[str] = Field(default_factory=lambda: ["aegis:pass"])

    @field_validator("run_id")
    @classmethod
    def _run_id_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("run_id must not be blank")
        return stripped


class TestProjectBinding(StrictModel):
    """Resolved project roots for Test Subgraph runtime."""

    __test__: ClassVar[bool] = False

    project_root: Path
    code_root: Path
    archive_store_root: str
    knowledge_store_root: str
    causal_store_root: str
    test_artifact_root: Path


class TestBlocker(StrictModel):
    """Terminal or routing blocker."""

    __test__: ClassVar[bool] = False

    label: Literal[
        "input_invalid",
        "test_plan_not_approvable",
        "unsafe_test_command",
        "test_environment_unavailable",
        "test_execution_incomplete",
        "evidence_not_closable",
        "code_mutation_detected",
        "artifact_schema_invalid",
        "round_limit_exceeded",
    ]
    reason: str
    evidence_refs: list[str] = Field(default_factory=list)
    next_action: Literal["execution", "master", "developer_input", "blocked_closeout"]
    retry_allowed: bool = False


class TestInputValidation(StrictModel):
    """Machine-readable validation of Execution to Test handoff."""

    __test__: ClassVar[bool] = False

    execution_handoff_ref: ArtifactRef
    execution_output_package_ref: ArtifactRef
    readme_valid: bool
    handoff_json_valid: bool
    output_status_valid: bool
    output_next_stage_valid: bool
    boundary_flags_valid: bool
    required_refs_valid: bool
    hash_verified: bool
    status: Literal["accepted", "blocked"]
    blocker: TestBlocker | None = None

    @model_validator(mode="after")
    def _blocked_requires_blocker(self) -> "TestInputValidation":
        if self.status == "blocked" and self.blocker is None:
            raise ValueError("blocked validation requires blocker")
        return self


class TestWritePolicy(StrictModel):
    """Write policy for test commands."""

    __test__: ClassVar[bool] = False

    policy_id: str
    test_run_dir: str
    allowed_temp_roots: list[str]
    forbidden_roots: list[str]

    @model_validator(mode="after")
    def _must_have_forbidden_roots(self) -> "TestWritePolicy":
        if not self.forbidden_roots:
            raise ValueError("TestWritePolicy requires forbidden_roots")
        return self


class TestNode(StrictModel):
    """Approved executable test node."""

    __test__: ClassVar[bool] = False

    test_id: str
    purpose: str
    preconditions: list[str] = Field(default_factory=list)
    command_or_operation: str
    expected_result: str
    evidence_required: list[str]
    depends_on: list[str] = Field(default_factory=list)
    consumes_outputs_from: list[str] = Field(default_factory=list)
    can_rerun_independently: bool = True
    write_policy_ref: ArtifactRef

    @field_validator("test_id", "purpose", "command_or_operation", "expected_result")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class TestPlan(StrictModel):
    """Approved or draft test plan."""

    __test__: ClassVar[bool] = False

    plan_id: str
    source_handoff_dir: str
    test_nodes: list[TestNode]
    dependency_graph_ref: ArtifactRef
    coverage_matrix_ref: ArtifactRef
    evidence_requirements_ref: ArtifactRef
    known_limits_ref: ArtifactRef | None = None

    @model_validator(mode="after")
    def _must_have_nodes(self) -> "TestPlan":
        if not self.test_nodes:
            raise ValueError("TestPlan requires at least one test node")
        ids = [node.test_id for node in self.test_nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("TestPlan test_id values must be unique")
        return self


class TestPlanReviewIssue(StrictModel):
    """Structured issue from the plan reviewer."""

    __test__: ClassVar[bool] = False

    issue_id: str
    severity: IssueSeverity
    test_plan_refs: list[str] = Field(default_factory=list)
    handoff_refs: list[str] = Field(default_factory=list)
    explanation: str
    required_change: str | None = None
    blocking: bool = False


class PlanReviewScorecard(StrictModel):
    """Plan review scorecard with anti-infinite-review consistency rules."""

    decision: PlanReviewDecision
    score: int = Field(ge=0, le=100)
    dimensions: dict[str, int]
    error_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    suggestion_count: int = Field(ge=0)
    issues: list[TestPlanReviewIssue] = Field(default_factory=list)
    baseline_criteria_ref: ArtifactRef
    review_report_ref: ArtifactRef

    @model_validator(mode="after")
    def _consistent(self) -> "PlanReviewScorecard":
        if self.decision == "approved" and self.score < 95:
            raise ValueError("approved scorecards require score >= 95")
        if self.decision == "approved" and self.error_count != 0:
            raise ValueError("approved scorecards require error_count == 0")
        for issue in self.issues:
            if issue.blocking and issue.severity != "error":
                raise ValueError("blocking issues must be error severity")
        if self.score >= 95 and self.error_count == 0 and self.decision != "approved":
            raise ValueError("warning-only scorecards with score >= 95 must approve")
        actual_errors = sum(1 for issue in self.issues if issue.severity == "error")
        if actual_errors != self.error_count:
            raise ValueError("error_count must match error issues")
        return self


class TestCommandSafetyAnalysis(StrictModel):
    """Risk classification for one test command."""

    __test__: ClassVar[bool] = False

    test_id: str
    command: str
    cwd: str
    write_policy_ref: ArtifactRef
    parsed_risk: CommandRisk
    touches_paths: list[str] = Field(default_factory=list)
    allowed_write_roots: list[str] = Field(default_factory=list)
    forbidden_roots_touched: list[str] = Field(default_factory=list)
    requires_interrupt: bool = False
    blocked: bool = False
    reason: str | None = None

    @model_validator(mode="after")
    def _blocked_reason(self) -> "TestCommandSafetyAnalysis":
        if self.blocked and not self.reason:
            raise ValueError("blocked command safety analysis requires reason")
        return self


class TestRunChangedFile(StrictModel):
    """Detected file change after test execution."""

    __test__: ClassVar[bool] = False

    path: str
    change_type: Literal["added", "modified", "deleted"]
    within_code_root: bool
    allowed_runtime_change: bool = False
    sha256_before: str | None = None
    sha256_after: str | None = None


class TestRunChangeSet(StrictModel):
    """Before/after proof that Test did not mutate business code."""

    __test__: ClassVar[bool] = False

    before_code_tree_hash: str
    after_code_tree_hash: str
    changed_files: list[TestRunChangedFile] = Field(default_factory=list)
    forbidden_code_changes: list[str] = Field(default_factory=list)
    allowed_runtime_changes: list[str] = Field(default_factory=list)
    status: Literal["clean", "allowed_runtime_changes", "blocked"]


class TestDependencyEdge(StrictModel):
    """Dependency relation between test nodes."""

    __test__: ClassVar[bool] = False

    from_test_id: str
    to_test_id: str
    dependency_type: Literal["precondition", "artifact_consumer", "environment_setup"]


class TestDependencyGraph(StrictModel):
    """Dependency graph used for minimal retest selection."""

    __test__: ClassVar[bool] = False

    nodes: list[str]
    edges: list[TestDependencyEdge] = Field(default_factory=list)
    cycles_detected: list[list[str]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _cycles_require_handling_elsewhere(self) -> "TestDependencyGraph":
        if len(self.nodes) != len(set(self.nodes)):
            raise ValueError("dependency graph nodes must be unique")
        return self


class MinimalRetestRequest(StrictModel):
    """Evidence-gap minimal retest request."""

    request_id: str
    target_gap_ids: list[str]
    dependency_graph_ref: ArtifactRef
    selected_nodes: list[str]
    excluded_nodes: list[str] = Field(default_factory=list)
    selection_reasoning: str
    cycle_handling: str | None = None
    expected_new_evidence: list[str]


class SkipReason(StrictModel):
    """Explicit skipped verdict reason."""

    skip_type: Literal["approved_conditional_skip", "environment_skip", "executor_omission"]
    reason: str
    approved_by_plan: bool
    evidence_refs: list[ArtifactRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _approval_consistency(self) -> "SkipReason":
        if self.skip_type == "approved_conditional_skip" and not self.approved_by_plan:
            raise ValueError("approved_conditional_skip requires approved_by_plan=True")
        if self.skip_type == "executor_omission" and self.approved_by_plan:
            raise ValueError("executor_omission cannot be approved_by_plan")
        return self


class TestNodeExecutionRecord(StrictModel):
    """Actual execution record for one approved test node."""

    __test__: ClassVar[bool] = False

    test_id: str
    execution_attempt: int
    command_safety_ref: ArtifactRef
    command_ref: ArtifactRef
    stdout_ref: ArtifactRef | None = None
    stderr_ref: ArtifactRef | None = None
    exit_code_ref: ArtifactRef | None = None
    duration_ms_ref: ArtifactRef | None = None
    started_at_utc: str
    ended_at_utc: str
    status: TestNodeStatus
    skip_reason: SkipReason | None = None
    evidence_ref: ArtifactRef
    produced_artifact_refs: list[ArtifactRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _skip_consistency(self) -> "TestNodeExecutionRecord":
        if self.status == "skipped" and self.skip_reason is None:
            raise ValueError("skipped execution record requires skip_reason")
        if self.status != "skipped" and self.skip_reason is not None:
            raise ValueError("non-skipped execution record must not include skip_reason")
        return self

    @classmethod
    def validate_manifest_records(
        cls,
        plan: TestPlan,
        records: list["TestNodeExecutionRecord"],
    ) -> None:
        plan_ids = {node.test_id for node in plan.test_nodes}
        record_ids = {record.test_id for record in records}
        if plan_ids != record_ids:
            raise ValueError("every test node requires execution record")


class EvidenceMatrixItem(StrictModel):
    """Evidence closure state for one test node."""

    test_id: str
    plan_ref: str
    command_or_operation_ref: ArtifactRef | None = None
    stdout_ref: ArtifactRef | None = None
    stderr_ref: ArtifactRef | None = None
    artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    expected_result: str
    actual_result: str
    verdict: TestNodeStatus
    verdict_reason: str
    skip_reason: SkipReason | None = None
    evidence_complete: bool

    @model_validator(mode="after")
    def _skip_and_evidence_consistency(self) -> "EvidenceMatrixItem":
        if self.verdict == "skipped" and self.skip_reason is None:
            raise ValueError("skipped verdict requires skip_reason")
        if self.verdict != "skipped" and self.skip_reason is not None:
            raise ValueError("non-skipped verdict must not include skip_reason")
        if self.skip_reason and self.skip_reason.skip_type == "executor_omission" and self.evidence_complete:
            raise ValueError("executor_omission cannot be evidence_complete")
        return self


class EvidenceMatrix(StrictModel):
    """Evidence matrix consumed by the report processor."""

    test_ids: list[str]
    items: list[EvidenceMatrixItem]
    status: Literal["complete", "gap"]

    @model_validator(mode="after")
    def _status_consistency(self) -> "EvidenceMatrix":
        complete = all(item.evidence_complete for item in self.items)
        if self.status == "complete" and not complete:
            raise ValueError("complete evidence matrix requires all items evidence_complete")
        return self


class TestRunManifest(StrictModel):
    """Run-level index."""

    __test__: ClassVar[bool] = False

    run_id: str
    source_execution_run_id: str
    input_handoff_hash: str
    source_provenance_hash: str
    fixture_provenance_hash: str
    environment_provenance_hash: str
    approved_plan_hash: str | None = None
    execution_manifest_hash: str | None = None
    completeness_report_hash: str | None = None
    evidence_report_hash: str | None = None
    final_report_hash: str | None = None
    current_terminal_status: str


class SourceProvenance(StrictModel):
    """Source snapshot provenance for a test run."""

    source_commit: str | None = None
    source_snapshot_hash: str
    source_manifest_ref: ArtifactRef
    source_file_count: int = Field(ge=0)
    execution_handoff_hash: str
    code_root: str
    collected_at_utc: str = Field(default_factory=utc_now)


class FixtureProvenance(StrictModel):
    """Fixture provenance for a test run."""

    fixture_manifest_hash: str
    fixture_roots: list[str] = Field(default_factory=list)
    fixture_artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    collected_at_utc: str = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _must_have_real_manifest(self) -> "FixtureProvenance":
        if self.fixture_manifest_hash == "0" * 64:
            raise ValueError("FixtureProvenance requires a real fixture manifest hash")
        if not self.fixture_roots:
            raise ValueError("FixtureProvenance requires fixture_roots")
        if not self.fixture_artifact_refs:
            raise ValueError("FixtureProvenance requires fixture_artifact_refs")
        return self


class StateBoundaryResult(StrictModel):
    """Machine-readable proof that graph state carries refs, not long artifacts."""

    serialized_state_size_bytes: int = Field(ge=0)
    max_serialized_state_bytes: int = Field(default=65_536, ge=1)
    long_text_fields_detected: list[str] = Field(default_factory=list)
    stdout_in_state: bool = False
    stderr_in_state: bool = False
    large_json_in_state: bool = False
    artifact_refs_only: bool
    status: Literal["passed", "failed"]

    @model_validator(mode="after")
    def _status_consistency(self) -> "StateBoundaryResult":
        failed = (
            self.serialized_state_size_bytes > self.max_serialized_state_bytes
            or bool(self.long_text_fields_detected)
            or self.stdout_in_state
            or self.stderr_in_state
            or self.large_json_in_state
            or not self.artifact_refs_only
        )
        if failed and self.status != "failed":
            raise ValueError("failed state boundary conditions require status=failed")
        if not failed and self.status != "passed":
            raise ValueError("clean state boundary conditions require status=passed")
        return self


class EnvironmentProvenance(StrictModel):
    """Runtime environment provenance for a test run."""

    os_name: str
    os_version: str
    python_version: str
    command_root: str
    environment_hash: str
    collected_at_utc: str = Field(default_factory=utc_now)


class ArtifactSchemaCheckItem(StrictModel):
    """Schema validation result for one artifact."""

    artifact_ref: ArtifactRef
    schema_name: str
    required: bool
    status: Literal["passed", "failed", "skipped"]
    failure_reason: str | None = None

    @model_validator(mode="after")
    def _failure_reason_consistency(self) -> "ArtifactSchemaCheckItem":
        if self.status == "failed" and not self.failure_reason:
            raise ValueError("failed artifact schema check requires failure_reason")
        return self


class ArtifactSchemaValidationResult(StrictModel):
    """Aggregate artifact schema validation."""

    status: Literal["passed", "failed"]
    checked_artifacts: list[ArtifactSchemaCheckItem]
    failures: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _required_failures_block(self) -> "ArtifactSchemaValidationResult":
        required_failures = [
            item
            for item in self.checked_artifacts
            if item.required and item.status in {"failed", "skipped"}
        ]
        if required_failures and self.status != "failed":
            raise ValueError("required artifact schema failures require status=failed")
        if self.status == "passed" and self.failures:
            raise ValueError("passed artifact schema validation cannot include failures")
        return self


class TestBoundaryFlags(StrictModel):
    """Truth and external publication boundary proof."""

    __test__: ClassVar[bool] = False

    wrote_archive_truth: bool = False
    wrote_knowledge_truth: bool = False
    wrote_causal_truth: bool = False
    remote_published: bool = False
    code_modified: bool = False

    @model_validator(mode="after")
    def _forbidden_flags(self) -> "TestBoundaryFlags":
        if (
            self.wrote_archive_truth
            or self.wrote_knowledge_truth
            or self.wrote_causal_truth
            or self.remote_published
            or self.code_modified
        ):
            raise ValueError("TestOutputPackage boundary flags must remain false")
        return self


class TestOutputPackage(StrictModel):
    """Terminal package returned to Parent Graph."""

    __test__: ClassVar[bool] = False

    schema_version: Literal["test.output.v2"] = "test.output.v2"
    run_id: str
    status: TestStatus
    input_validation_ref: ArtifactRef
    approved_test_plan_ref: ArtifactRef | None = None
    test_execution_manifest_ref: ArtifactRef | None = None
    completeness_check_ref: ArtifactRef | None = None
    evidence_check_ref: ArtifactRef | None = None
    artifact_schema_check_ref: ArtifactRef | None = None
    final_test_report_ref: ArtifactRef | None = None
    state_boundary_results_ref: ArtifactRef
    blocker: TestBlocker | None = None
    failure_classification: TestFailureClassification | None = None
    boundary: TestBoundaryFlags = Field(default_factory=TestBoundaryFlags)
    next_stage: NextStage
    evidence_index_ref: ArtifactRef

    @model_validator(mode="after")
    def _terminal_consistency(self) -> "TestOutputPackage":
        if self.status == "passed":
            missing = [
                self.approved_test_plan_ref,
                self.test_execution_manifest_ref,
                self.completeness_check_ref,
                self.evidence_check_ref,
                self.artifact_schema_check_ref,
                self.final_test_report_ref,
            ]
            if any(item is None for item in missing):
                raise ValueError("passed output requires all terminal artifact refs")
            if self.next_stage != "final_review":
                raise ValueError("passed output must route to final_review")
        if self.status == "failed" and self.next_stage != "execution":
            raise ValueError("failed output must route to execution")
        if self.status == "blocked" and self.blocker is None:
            raise ValueError("blocked output requires blocker")
        return self


class TestNodeResult(StrictModel):
    """Machine-readable graph node result."""

    __test__: ClassVar[bool] = False

    node_name: str
    status: Literal["ok", "terminal", "failed"]
    updated_state_fields: dict[str, Any] = Field(default_factory=dict)
    artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    error: dict[str, Any] | None = None
    idempotency_key: str | None = None
    safe_to_retry: bool = True


class StateSizePolicy(StrictModel):
    """Maximum serialized state policy."""

    max_serialized_state_bytes: int = 65_536
    on_exceed: Literal["block", "write_artifact_and_replace_with_ref"] = "write_artifact_and_replace_with_ref"


class RealAgentTestValidationResult(StrictModel):
    """Independent validator output for real-agent behavior evidence."""

    validator_name: Literal["RealAgentTestValidator"] = "RealAgentTestValidator"
    status: Literal["passed", "failed", "accepted_with_scope_limits"]
    checked_artifacts: list[ArtifactRef] = Field(default_factory=list)
    policy_violations: list[str] = Field(default_factory=list)
    behavior_findings_ref: ArtifactRef

    __test__: ClassVar[bool] = False
