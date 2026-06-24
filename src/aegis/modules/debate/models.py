"""Data contracts for DebateSubgraph v2."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from aegis.models import StrictModel, utc_now


class DebateStatus(str, Enum):
    """Top-level DebateSubgraph completion states."""

    COMPLETED = "completed"
    DEBATE_NOT_REQUIRED = "debate_not_required"
    NEED_MORE_CONTEXT = "need_more_context"
    NEED_MEASUREMENT = "need_measurement"
    NON_CONVERGENT = "non_convergent"
    SCOPE_LIMITED = "scope_limited"
    BLOCKED = "blocked"
    FAILED = "failed"


class ConstraintStatus(str, Enum):
    """Hard-constraint admission status."""

    VERIFIED = "verified"
    UNSUPPORTED = "unsupported"
    DOWNGRADED_TO_PREFERENCE = "downgraded_to_preference"
    REJECTED = "rejected"


class StanceAdmissionStatus(str, Enum):
    """Stance admission state."""

    ADMITTED = "admitted"
    REJECTED = "rejected"


class StanceRelationKind(str, Enum):
    """Semantic relation between two candidate stances."""

    MUTUALLY_EXCLUSIVE = "mutually_exclusive"
    DUPLICATE = "duplicate"
    COMPATIBLE = "compatible"
    SCOPE_SPLIT_CANDIDATE = "scope_split_candidate"
    LEFT_DOMINATES_RIGHT = "left_dominates_right"
    RIGHT_DOMINATES_LEFT = "right_dominates_left"
    MEASUREMENT_NEEDED = "measurement_needed"


class LeaderDecision(str, Enum):
    """Leader round-level decision."""

    CONTINUE_DEBATE = "continue_debate"
    STOP_CONVERGED = "stop_converged"
    STOP_NEED_CONTEXT = "stop_need_context"
    REQUEST_WORKER_REPAIR = "request_worker_repair"
    ABORT_PROTOCOL_VIOLATION = "abort_protocol_violation"


class WorkerViolationSeverity(str, Enum):
    """Worker protocol violation severity."""

    MINOR = "minor"
    MATERIAL = "material"
    FATAL = "fatal"


class CausalCandidateStatus(str, Enum):
    """Causal output status from Debate."""

    CAUSAL_CANDIDATE = "causal_candidate"


class DebateRequiredOutcome(str, Enum):
    """Allowed requested output shapes for DebateSubgraph."""

    CHOOSE_ONE = "choose_one"
    RANK = "rank"
    SCOPE_SPLIT = "scope_split"
    REJECT_ALL = "reject_all"
    NEED_MEASUREMENT = "need_measurement"
    NEED_MASTER = "need_master"


class CandidatePosition(StrictModel):
    """A proposed stance that may enter adversarial debate."""

    stance_id: str
    statement: str
    summary: str
    source_artifact_refs: list[str] = Field(default_factory=list)

    @field_validator("stance_id", "statement", "summary")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class HardConstraint(StrictModel):
    """A claimed hard constraint that requires objective support."""

    constraint_id: str
    statement: str
    source: Literal[
        "user_claim",
        "user",
        "customer_written_evidence",
        "knowledge",
        "causal",
        "law",
        "platform",
        "cost_boundary",
        "first_principles",
    ]
    evidence_ref: str | None = None
    why_hard: str | None = None

    @field_validator("constraint_id", "statement")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class FirstPrinciplesNecessityCheck(StrictModel):
    """First-principles admission check for a stance or constraint."""

    statement: str | None = None
    category: str | None = None
    accepted: bool
    rationale: str
    depends_on_project_fact: bool = False
    required_project_fact_ref: str | None = None

    @model_validator(mode="after")
    def _project_fact_dependency_must_be_explicit(
        self,
    ) -> "FirstPrinciplesNecessityCheck":
        if (
            self.accepted
            and self.depends_on_project_fact
            and not self.required_project_fact_ref
        ):
            raise ValueError(
                "accepted project-fact-dependent checks require "
                "required_project_fact_ref"
            )
        return self


class DebateRuntimeConfig(StrictModel):
    """Deterministic runtime limits for DebateSubgraph."""

    max_rounds: int = 4
    max_workers: int = 5
    max_turns_per_worker: int = 4
    max_artifact_bytes: int = 2_000_000
    max_knowledge_context_refs: int = 50
    max_causal_context_refs: int = 50
    max_context_bundle_bytes: int = 256 * 1024
    require_first_principles_audit: bool = True
    max_worker_repair_attempts: int = 1
    stable_selected_stance_round_threshold: int = 1
    max_protocol_violations_per_worker: int = 1
    allow_scope_limited_verdict_on_max_rounds: bool = False
    allow_real_agent_adapter: bool = False

    @field_validator(
        "max_rounds",
        "max_workers",
        "max_turns_per_worker",
        "max_artifact_bytes",
        "max_knowledge_context_refs",
        "max_causal_context_refs",
        "max_context_bundle_bytes",
    )
    @classmethod
    def _positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("value must be positive")
        return value

    @field_validator(
        "max_worker_repair_attempts",
        "stable_selected_stance_round_threshold",
        "max_protocol_violations_per_worker",
    )
    @classmethod
    def _non_negative_threshold(cls, value: int) -> int:
        if value < 0:
            raise ValueError("value must not be negative")
        return value


class DebateBoundary(StrictModel):
    """Hard boundary proof for DebateSubgraph output."""

    wrote_causal_truth: bool = False
    wrote_knowledge_truth: bool = False
    modified_code: bool = False
    global_causal_truth_written: bool = False
    archive_written: bool = False
    knowledge_written: bool = False
    project_code_modified: bool = False


class DebateInputPackage(StrictModel):
    """Input package accepted by DebateSubgraph."""

    request_id: str
    source_module: Literal["master", "execution", "final_review", "causal_review"] | None = None
    project_root: Path
    decision_problem: str
    decision_scope: str | None = None
    required_outcome: DebateRequiredOutcome | None = None
    requester: Literal["master", "execution", "final_review", "causal_review"] = "master"
    candidate_positions: list[CandidatePosition]
    hard_constraints: list[HardConstraint] = Field(default_factory=list)
    knowledge_query_refs: list[str] = Field(default_factory=list)
    causal_query_refs: list[str] = Field(default_factory=list)
    source_artifact_refs: list[str] = Field(default_factory=list)
    created_at_utc: str = Field(default_factory=utc_now)

    @field_validator("request_id", "decision_problem")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @field_validator("candidate_positions")
    @classmethod
    def _positions_required(
        cls,
        value: list[CandidatePosition],
    ) -> list[CandidatePosition]:
        if not value:
            raise ValueError("candidate_positions must not be empty")
        return value

    @model_validator(mode="before")
    @classmethod
    def _source_module_sets_requester(cls, data: object) -> object:
        if isinstance(data, dict) and data.get("source_module") is not None:
            normalized = dict(data)
            normalized.setdefault("requester", normalized["source_module"])
            return normalized
        return data


class DebateErrorRecord(StrictModel):
    """JSON-safe error record in Debate output."""

    code: str
    message: str
    context: dict[str, object] = Field(default_factory=dict)


class KnowledgeContextRef(StrictModel):
    """A knowledge-store result admitted into Debate context."""

    knowledge_id: int | str | None = None
    statement: str = ""
    subject: str | None = None
    object: str | None = None
    object_ref: str | None = None
    predicate: str | None = None
    scope: str
    evidence_ref: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    applicability_reason: str | None = None
    confidence: Literal["high", "medium", "low"] = "medium"

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_shape(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if not normalized.get("statement"):
            parts = [
                str(normalized.get("subject") or ""),
                str(normalized.get("predicate") or ""),
                str(normalized.get("object") or ""),
            ]
            normalized["statement"] = " ".join(part for part in parts if part)
        if not normalized.get("object_ref") and normalized.get("object"):
            normalized["object_ref"] = normalized["object"]
        refs = normalized.get("evidence_refs") or []
        if not normalized.get("evidence_ref") and refs:
            normalized["evidence_ref"] = refs[0]
        return normalized


class RejectedKnowledgeRef(StrictModel):
    """Knowledge-store result rejected from Debate context."""

    ref: str
    reason: str


class CausalContextRef(StrictModel):
    """A causal-store node admitted into Debate context."""

    node_id: int | None = None
    content: str
    semantic_summary: str
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"


class ArtifactContextRef(StrictModel):
    """A verified non-code project artifact accepted as evidence context."""

    input_ref: str
    resolved_ref: str
    scope: Literal["project_artifact"]
    content_preview: str = ""


class RejectedArtifactRef(StrictModel):
    """Project artifact ref rejected by path or evidence policy."""

    ref: str
    reason: str


class RejectedCausalRef(StrictModel):
    """Causal-store result rejected from Debate context."""

    ref: str
    reason: str


class MeasurementNeed(StrictModel):
    """A missing measurement that blocks reliable debate closure."""

    need_id: str
    question: str
    blocking_level: Literal["blocking", "non_blocking"]
    suggested_owner: Literal["master", "execution", "test"]


class DegradedRecallWarning(StrictModel):
    """Warning that context retrieval may be incomplete."""

    warning_id: str
    message: str


class RetrievalAudit(StrictModel):
    """Audit of knowledge and causal retrieval inputs."""

    knowledge_query_refs: list[str] = Field(default_factory=list)
    causal_query_refs: list[str] = Field(default_factory=list)
    admitted_knowledge_count: int = 0
    admitted_causal_count: int = 0
    degraded_recall: bool = False


class DebateContextBundle(StrictModel):
    """Knowledge and causal context used by Debate."""

    debate_id: str | None = None
    knowledge_refs: list[KnowledgeContextRef] = Field(default_factory=list)
    rejected_knowledge_refs: list[RejectedKnowledgeRef] = Field(default_factory=list)
    causal_refs: list[CausalContextRef] = Field(default_factory=list)
    artifact_refs: list[ArtifactContextRef] = Field(default_factory=list)
    rejected_causal_refs: list[RejectedCausalRef] = Field(default_factory=list)
    rejected_artifact_refs: list[RejectedArtifactRef] = Field(default_factory=list)
    missing_measurements: list[MeasurementNeed] = Field(default_factory=list)
    degraded_recall_warnings: list[DegradedRecallWarning] = Field(default_factory=list)
    retrieval_audit: RetrievalAudit = Field(default_factory=RetrievalAudit)


class HardConstraintValidation(StrictModel):
    """Hard-constraint validation result."""

    constraint_id: str
    status: ConstraintStatus
    reason: str
    evidence_refs: list[str] = Field(default_factory=list)
    matched_knowledge_refs: list[str] = Field(default_factory=list)
    matched_causal_refs: list[int] = Field(default_factory=list)
    matched_artifact_refs: list[str] = Field(default_factory=list)

    @property
    def validation_status(self) -> str:
        return self.status.value

    @property
    def rejection_reason(self) -> str:
        return self.reason


class StanceAdmissionRecord(StrictModel):
    """Admission record for a candidate stance."""

    stance_id: str
    status: StanceAdmissionStatus
    reason: str
    supporting_refs: list[str] = Field(default_factory=list)


class StanceRelationRecord(StrictModel):
    """Relation between two admitted stances."""

    left_stance_id: str
    right_stance_id: str
    relation: StanceRelationKind
    reason: str


class WorkerSelfAudit(StrictModel):
    """Worker self-audit required for each turn."""

    knowledge_constraints_checked: bool = False
    causal_refs_checked: bool = False
    unsupported_claims: list[str] = Field(default_factory=list)
    possible_protocol_violations: list[str] = Field(default_factory=list)
    pressure_to_concede: bool = False
    truth_status_claimed: Literal[
        "local_argument_only",
        "causal_candidate",
        "global_truth",
    ] = "local_argument_only"


class WorkerConcession(StrictModel):
    """A worker concession with causal defeat evidence."""

    target_ref: str
    why_conceded: str
    defeating_ref: str | None = None


class WorkerAttack(StrictModel):
    """A worker attack against another stance or claim."""

    target_ref: str
    claim: str
    why: str
    evidence_refs: list[str] = Field(default_factory=list)


class WorkerCausalChainDelta(StrictModel):
    """A worker's local causal-chain update for one turn."""

    added_local_nodes: list[dict[str, object]] = Field(default_factory=list)
    added_local_edges: list[dict[str, object]] = Field(default_factory=list)
    added_edges: list[dict[str, object]] = Field(default_factory=list)
    superseded_local_nodes: list[str] = Field(default_factory=list)
    invalidated_local_nodes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize_legacy_edge_names(self) -> "WorkerCausalChainDelta":
        if self.added_edges and not self.added_local_edges:
            self.added_local_edges = self.added_edges
        if self.invalidated_local_nodes and not self.superseded_local_nodes:
            self.superseded_local_nodes = self.invalidated_local_nodes
        return self


class WorkerTurnPacket(StrictModel):
    """Machine-readable worker turn packet."""

    turn_id: str
    debate_id: str | None = None
    round_index: int
    worker_id: str
    stance_id: str
    observed_canonical_transcript_ref: str | None = None
    defense: str | dict[str, object] = ""
    attacks: list[WorkerAttack] = Field(default_factory=list)
    concessions: list[WorkerConcession] = Field(default_factory=list)
    chain_delta: WorkerCausalChainDelta = Field(
        default_factory=WorkerCausalChainDelta
    )
    evidence_refs: list[str] = Field(default_factory=list)
    self_audit: WorkerSelfAudit = Field(default_factory=WorkerSelfAudit)


class WorkerProtocolViolation(StrictModel):
    """Detected worker protocol violation."""

    turn_id: str
    worker_id: str
    violation_type: str
    severity: WorkerViolationSeverity
    reason: str
    action: Literal[
        "request_repair",
        "request_worker_repair",
        "mark_turn_unusable",
        "abort_debate",
    ] | None = None
    required_action: Literal[
        "request_repair",
        "mark_turn_unusable",
        "abort_debate",
    ] | None = None

    @model_validator(mode="after")
    def _normalize_action(self) -> "WorkerProtocolViolation":
        if self.required_action is None:
            if self.action == "request_worker_repair":
                self.required_action = "request_repair"
            elif self.action in {"request_repair", "mark_turn_unusable", "abort_debate"}:
                self.required_action = self.action
        if self.action is None and self.required_action is not None:
            self.action = self.required_action
        if self.required_action is None:
            raise ValueError("required_action or action is required")
        return self


class ConvergenceSignals(StrictModel):
    """Leader-visible debate convergence signals."""

    active_stance_count: int | None = None
    undefeated_stance_count: int
    unresolved_conflict_count: int
    new_material_argument_count: int
    unresolved_blocking_missing_need_count: int = 0
    decisive_constraint_count: int = 0
    stable_selected_stance_rounds: int = 0
    worker_protocol_violation_count: int = 0


class LeaderRoundAssessment(StrictModel):
    """Leader decision after a debate round."""

    round_index: int
    decision: LeaderDecision
    reason: str
    selected_stance_id: str | None = None
    rejected_stance_ids: list[str] = Field(default_factory=list)
    required_repairs: list[str] = Field(default_factory=list)

    @property
    def next_action(self) -> str:
        if self.decision == LeaderDecision.REQUEST_WORKER_REPAIR:
            return "request_worker_repair"
        return self.decision.value

    @property
    def stop_reason(self) -> str:
        return self.reason


class CausalCandidateDependencyGroup(StrictModel):
    """Dependency group for one causal candidate node."""

    group_id: str
    causal_dependencies: list[str] = Field(default_factory=list)
    knowledge_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    scope: str
    confidence: Literal["high", "medium", "low"] = "medium"
    invalidation_conditions: list[str] = Field(default_factory=list)


class CausalCandidateNode(StrictModel):
    """Causal candidate node produced by Debate."""

    local_node_ref: str
    statement: str
    semantic_summary: str
    semantic_keys: list[str] = Field(default_factory=list)
    source_worker_id: str
    source_stance_id: str
    dependency_groups: list[CausalCandidateDependencyGroup]
    status: CausalCandidateStatus = CausalCandidateStatus.CAUSAL_CANDIDATE


class CausalStoreUpdateCandidate(StrictModel):
    """Full causal-store update candidate produced by Debate."""

    candidate_id: str
    request_id: str
    debate_id: str
    selected_stance_id: str
    nodes: list[CausalCandidateNode]
    reused_node_ids: list[int] = Field(default_factory=list)
    rejected_alternatives: list[str] = Field(default_factory=list)
    status: CausalCandidateStatus = CausalCandidateStatus.CAUSAL_CANDIDATE


class CausalCandidateWriteResult(StrictModel):
    """Result of writing causal candidates into local project Causal Store."""

    candidate_id: str
    artifact_ref: str
    write_status: Literal["written", "already_exists", "partial_failed", "failed"] = "written"
    inserted_node_ids: list[int] = Field(default_factory=list)
    existing_node_ids: list[int] = Field(default_factory=list)
    skipped_node_refs: list[str] = Field(default_factory=list)
    errors: list[dict[str, object]] = Field(default_factory=list)


class DebateRunManifest(StrictModel):
    """Artifact manifest for a DebateSubgraph run."""

    debate_id: str
    request_id: str
    artifact_root: Path
    input_hash: str
    input_package_ref: str
    run_status: str = "started"
    updated_at_utc: str = Field(default_factory=utc_now)
    context_bundle_ref: str | None = None
    context_bundle_hash: str | None = None
    transcript_ref: str | None = None
    stance_admissions_ref: str | None = None
    stance_admissions_hash: str | None = None
    stance_relations_ref: str | None = None
    worker_turns_ref: str | None = None
    leader_assessment_ref: str | None = None
    causal_candidate_hash: str | None = None
    causal_candidate_ref: str | None = None
    causal_write_result_ref: str | None = None
    final_report_ref: str | None = None
    output_package_ref: str | None = None


class ProjectStoreBinding(StrictModel):
    """Bound project-local stores and Debate artifact root."""

    project_root: Path
    code_root: Path
    archive_store_root: Path
    knowledge_store_root: Path
    causal_store_root: Path
    debate_candidate_root: Path


class DebateOutputPackage(StrictModel):
    """DebateSubgraph output package."""

    debate_id: str
    request_id: str
    status: DebateStatus
    decision_type: str | None = None
    selected_stance_ids: list[str] = Field(default_factory=list)
    selected_stance_id: str | None = None
    rejected_stance_ids: list[str] = Field(default_factory=list)
    review_summary: str = ""
    causal_candidate_ref: str | None = None
    causal_store_candidate_id: str | None = None
    final_report_ref: str | None = None
    manifest_ref: str | None = None
    artifact_root: str = ""
    errors: list[DebateErrorRecord] = Field(default_factory=list)
    boundary: DebateBoundary = Field(default_factory=DebateBoundary)

    @model_validator(mode="after")
    def _normalize_selected_stance_fields(self) -> "DebateOutputPackage":
        if self.selected_stance_ids and self.selected_stance_id is None:
            self.selected_stance_id = self.selected_stance_ids[0]
        if self.selected_stance_id and not self.selected_stance_ids:
            self.selected_stance_ids = [self.selected_stance_id]
        return self
