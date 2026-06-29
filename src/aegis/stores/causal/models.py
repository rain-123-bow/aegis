from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import Field, field_validator

from aegis.models import StrictModel, utc_now


NodeStatus = Literal["candidate", "admitted", "invalidated", "deprecated", "superseded"]
SourceModule = Literal["master", "debate", "execution", "test", "final_review", "causal_review"]
AuthorityModule = Literal["master", "causal_review"]
RootKind = Literal["observation", "test_result", "user_constraint", "design_decision", "external_evidence"]
RefType = Literal["knowledge", "test", "external", "artifact", "repository_source"]
Confidence = Literal["high", "medium", "low"]
RetrievalMode = Literal[
    "admitted_only",
    "working_candidates",
    "historical",
    "include_invalidated_as_counterevidence",
    "human_review",
]
TriggerType = Literal[
    "dependency_invalidated",
    "dependency_superseded",
    "dependency_deprecated",
    "scope_rule_changed",
    "knowledge_ref_changed",
    "evidence_ref_changed",
    "manual_review",
]


class CausalStoreError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        context: dict[str, object] | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = context or {}
        self.cause = cause


class CausalStoreWarning(StrictModel):
    code: str
    message: str


class CausalRef(StrictModel):
    ref_type: RefType
    ref_id: str


class CausalDependencyGroup(StrictModel):
    group_id: str = Field(default_factory=lambda: f"group-{uuid4().hex[:12]}")
    causal_dependencies: list[int] = Field(default_factory=list)
    validity_refs: list[CausalRef] = Field(default_factory=list)
    knowledge_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    scope: str = "default"
    conditions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confidence: Confidence = "medium"
    invalidation_conditions: list[str] = Field(default_factory=list)


class CausalNodeDraft(StrictModel):
    content: str
    semantic_summary: str
    semantic_keys: list[str] = Field(default_factory=list)
    source_module: SourceModule
    source_run_id: str | None = None
    source_artifact_ref: str | None = None
    root_kind: RootKind | None = None
    node_refs: list[tuple[RefType, str]] = Field(default_factory=list)
    dependency_groups: list[CausalDependencyGroup] = Field(default_factory=list)

    @field_validator("content", "semantic_summary")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("causal node content and semantic_summary must be non-empty")
        return value


class CausalNode(StrictModel):
    node_id: int
    node_uuid: str
    created_at_utc: str
    updated_at_utc: str
    content: str
    semantic_summary: str
    semantic_keys: list[str]
    status: NodeStatus
    source_module: SourceModule
    source_run_id: str | None = None
    source_artifact_ref: str | None = None
    root_kind: RootKind | None = None
    strict_content_hash: str
    causal_identity_hash: str
    semantic_fingerprint: str | None = None
    duplicate_of_node_id: int | None = None
    node_refs: list[tuple[RefType, str]] = Field(default_factory=list)
    dependency_groups: list[CausalDependencyGroup] = Field(default_factory=list)


class AdmissionTransaction(StrictModel):
    node_ids: list[int]
    admitted_by_module: AuthorityModule
    rationale: str
    admission_run_id: str | None = None
    evidence_ref: str | None = None


class AdmissionResult(StrictModel):
    admitted_node_ids: list[int]
    admitted_at_utc: str


class InvalidationRequest(StrictModel):
    node_id: int
    invalidated_by_module: AuthorityModule
    reason: str
    invalidation_condition: str | None = None
    invalidation_run_id: str | None = None


class InvalidationResult(StrictModel):
    node_id: int
    invalidated_at_utc: str
    queued_revalidation_node_ids: list[int]


class RevalidationQueueItem(StrictModel):
    queue_id: str
    node_id: int
    triggered_by_node_id: int | None = None
    trigger_type: TriggerType
    queued_at_utc: str
    reason: str
    status: Literal["pending", "in_progress", "resolved", "dismissed"]
    resolved_at_utc: str | None = None
    resolution_rationale: str | None = None


class RevalidationResolutionRequest(StrictModel):
    queue_id: str
    status: Literal["resolved", "dismissed"]
    rationale: str


class RevalidationResolutionResult(StrictModel):
    queue_id: str
    status: Literal["resolved", "dismissed"]
    resolved_at_utc: str


class SupersessionRequest(StrictModel):
    old_node_id: int
    new_node_id: int
    reason: str


class SupersessionResult(StrictModel):
    old_node_id: int
    new_node_id: int
    superseded_at_utc: str
    queued_revalidation_node_ids: list[int]


class CausalQuery(StrictModel):
    query: str
    mode: RetrievalMode = "admitted_only"
    limit: int = 10
    include_rejected: bool = True
    required_scope: str | None = None


class RejectedNode(StrictModel):
    node_id: int
    reason: str


class CausalSearchResult(StrictModel):
    query: str
    mode: RetrievalMode
    nodes: list[CausalNode]
    rejected_nodes: list[RejectedNode] = Field(default_factory=list)
    warnings: list[CausalStoreWarning] = Field(default_factory=list)
    degraded_recall: bool = False


class ExpandContextRequest(StrictModel):
    node_ids: list[int]
    depth: int = 2
    mode: RetrievalMode = "admitted_only"


class CausalContextPackage(StrictModel):
    root_node_ids: list[int]
    mode: RetrievalMode
    selected_nodes: list[int]
    dependency_paths: list[list[int]]
    rejected_nodes: list[RejectedNode] = Field(default_factory=list)


class RebuildIndexResult(StrictModel):
    rebuilt_fts_rows: int
    rebuilt_embedding_rows: int
    rebuilt_at_utc: str = Field(default_factory=utc_now)
