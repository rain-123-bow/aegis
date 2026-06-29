from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from aegis.models import StrictModel, utc_now


KnowledgeStatus = Literal[
    "candidate",
    "admitted",
    "rejected",
    "invalidated",
    "deprecated",
    "superseded",
]
FactKind = Literal[
    "environment",
    "dependency",
    "platform",
    "customer_constraint",
    "repository_source",
    "test_result",
    "policy",
    "interface",
    "configuration",
    "business_rule",
    "other",
]
SubjectKind = Literal[
    "project",
    "module",
    "file",
    "function",
    "class",
    "dependency",
    "runtime",
    "platform",
    "customer",
    "device",
    "host",
    "service",
    "api",
    "schema",
    "other",
]
ObjectKind = Literal[
    "scalar",
    "range",
    "set",
    "object",
    "version",
    "path",
    "url",
    "identifier",
    "boolean",
    "other",
]
SourceModule = Literal[
    "master",
    "debate",
    "execution",
    "test",
    "final_review",
    "knowledge_review",
    "store_import",
]
AdmissionModule = Literal[
    "master",
    "debate",
    "execution",
    "test",
    "final_review",
    "knowledge_review",
    "store_import",
]
AuthorizedAdmissionModule = Literal["master", "knowledge_review", "store_import"]
EvidenceRefType = Literal[
    "test",
    "external",
    "artifact",
    "customer_written",
    "platform_doc",
    "repository_source",
]
VerifierModule = Literal["master", "debate", "execution", "test", "final_review", "knowledge_review"]
AdmissionMethod = Literal[
    "master_manual_review",
    "knowledge_review",
    "test_verified",
    "repository_inspected",
    "external_authority_verified",
]
Priority = Literal["low", "normal", "high", "critical"]
BlockingLevel = Literal[
    "hard_block",
    "needs_user_clarification",
    "request_test_measurement",
    "request_evidence_artifact_lookup",
    "advisory",
]
RevalidationStatus = Literal["pending", "in_progress", "resolved", "cancelled", "failed"]
ConflictStatus = Literal["open", "resolved", "accepted_with_scope_split", "dismissed"]
KnowledgeQueryMode = Literal[
    "active",
    "historical",
    "review",
    "include_rejected",
    "include_invalidated",
    "include_superseded",
]


class KnowledgeStoreError(RuntimeError):
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


class KnowledgeStoreWarning(StrictModel):
    code: str
    message: str


def _not_blank(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    return value


class EvidencePointer(StrictModel):
    ref_type: EvidenceRefType
    ref_id: str

    @field_validator("ref_id")
    @classmethod
    def ref_id_must_not_be_blank(cls, value: str) -> str:
        return _not_blank(value, "evidence ref_id")


class EvidenceRef(EvidencePointer):
    verifier: VerifierModule
    verification_method: str
    verified_at_utc: str = Field(default_factory=utc_now)

    @field_validator("verification_method")
    @classmethod
    def verification_method_must_not_be_blank(cls, value: str) -> str:
        return _not_blank(value, "verification_method")


class ApplicabilityProfile(StrictModel):
    profile_id: str = Field(default_factory=lambda: f"profile-{uuid4().hex[:12]}")
    applicability_scope: dict[str, Any] = Field(default_factory=dict)
    affected_entities: list[str] = Field(default_factory=list)
    affected_operations: list[str] = Field(default_factory=list)
    affected_qualities: list[str] = Field(default_factory=list)
    required_conditions: list[str] = Field(default_factory=list)
    risk_classes: list[str] = Field(default_factory=list)
    task_intents: list[str] = Field(default_factory=list)
    lifecycle_phases: list[str] = Field(default_factory=list)
    must_consider_when: list[str] = Field(default_factory=list)
    exclude_when: list[str] = Field(default_factory=list)
    priority: Priority = "normal"

    @model_validator(mode="after")
    def require_at_least_one_recall_trigger(self) -> "ApplicabilityProfile":
        trigger_fields = (
            self.affected_entities,
            self.affected_operations,
            self.affected_qualities,
            self.risk_classes,
            self.task_intents,
            self.lifecycle_phases,
            self.must_consider_when,
        )
        if not any(trigger_fields):
            raise ValueError("applicability profile requires at least one recall trigger")
        return self


class InvalidationRule(StrictModel):
    rule_id: str = Field(default_factory=lambda: f"rule-{uuid4().hex[:12]}")
    invalidation_condition: str
    affected_scope: dict[str, Any] = Field(default_factory=dict)
    revalidation_required: bool = True

    @field_validator("invalidation_condition")
    @classmethod
    def condition_must_not_be_blank(cls, value: str) -> str:
        return _not_blank(value, "invalidation_condition")


class KnowledgeFactDraft(StrictModel):
    fact_kind: FactKind
    subject_kind: SubjectKind
    subject_id: str
    subject_attributes: dict[str, Any] = Field(default_factory=dict)
    predicate: str
    object_kind: ObjectKind
    object: Any
    unit: str | None = None
    qualifiers: dict[str, Any] = Field(default_factory=dict)
    fact_validity_scope: dict[str, Any]
    validity_window: dict[str, Any] | None = None
    semantic_summary: str
    semantic_keys: list[str] = Field(default_factory=list)
    source_module: SourceModule
    source_run_id: str | None = None
    source_artifact_ref: str | None = None
    evidence_refs: list[EvidenceRef]
    applicability_profile: ApplicabilityProfile
    invalidation_rules: list[InvalidationRule] = Field(default_factory=list)
    no_known_invalidation: bool = False

    @field_validator("subject_id", "predicate", "semantic_summary")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        return _not_blank(value, "required knowledge fact text fields")

    @model_validator(mode="after")
    def completeness_gate(self) -> "KnowledgeFactDraft":
        if not self.fact_validity_scope:
            raise ValueError("fact_validity_scope is required")
        if not self.evidence_refs:
            raise ValueError("at least one typed evidence ref is required")
        if not self.invalidation_rules and not self.no_known_invalidation:
            raise ValueError(
                "invalidation rules or explicit no_known_invalidation must be present"
            )
        return self


class KnowledgeFact(StrictModel):
    knowledge_id: int
    knowledge_uuid: str
    created_at_utc: str
    updated_at_utc: str
    status: KnowledgeStatus
    fact_kind: FactKind
    subject_kind: SubjectKind
    subject_id: str
    subject_attributes: dict[str, Any]
    predicate: str
    object_kind: ObjectKind
    object: Any
    unit: str | None = None
    qualifiers: dict[str, Any]
    fact_validity_scope: dict[str, Any]
    validity_window: dict[str, Any] | None = None
    semantic_summary: str
    semantic_keys: list[str]
    source_module: SourceModule
    source_run_id: str | None = None
    source_artifact_ref: str | None = None
    fact_identity_hash: str
    strict_content_hash: str
    semantic_fingerprint: str | None = None
    no_known_invalidation: bool = False
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    applicability_profile: ApplicabilityProfile
    invalidation_rules: list[InvalidationRule] = Field(default_factory=list)


class AdmissionRequest(StrictModel):
    knowledge_id: int
    admitted_by_module: AuthorizedAdmissionModule
    admission_method: AdmissionMethod
    rationale: str
    evidence_refs: list[EvidencePointer]
    admission_run_id: str | None = None

    @field_validator("rationale")
    @classmethod
    def rationale_must_not_be_blank(cls, value: str) -> str:
        return _not_blank(value, "admission rationale")

    @model_validator(mode="after")
    def evidence_required(self) -> "AdmissionRequest":
        if not self.evidence_refs:
            raise ValueError("admission requires at least one evidence ref")
        return self


class AdmissionResult(StrictModel):
    knowledge_id: int
    admitted_at_utc: str


class RejectionRequest(StrictModel):
    knowledge_id: int
    rejected_by_module: VerifierModule
    reason: str
    missing_fields: list[str] = Field(default_factory=list)
    evidence_review: dict[str, Any] = Field(default_factory=dict)
    rejection_run_id: str | None = None

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        return _not_blank(value, "rejection reason")


class RejectionResult(StrictModel):
    knowledge_id: int
    rejected_at_utc: str


class InvalidationRequest(StrictModel):
    knowledge_id: int
    invalidated_by_module: VerifierModule
    reason: str
    triggered_rule_id: str | None = None
    evidence_ref: EvidencePointer | None = None
    invalidation_run_id: str | None = None

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        return _not_blank(value, "invalidation reason")


class InvalidationResult(StrictModel):
    knowledge_id: int
    invalidated_at_utc: str


class SupersessionRequest(StrictModel):
    old_knowledge_id: int
    new_knowledge_id: int
    reason: str
    superseded_by_module: AuthorizedAdmissionModule = "master"
    supersession_run_id: str | None = None

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        return _not_blank(value, "supersession reason")


class SupersessionResult(StrictModel):
    old_knowledge_id: int
    new_knowledge_id: int
    superseded_at_utc: str


class NeedRule(StrictModel):
    rule_id: str
    required_dimension: str
    trigger_terms: list[str] = Field(default_factory=list)
    trigger_task_intents: list[str] = Field(default_factory=list)
    trigger_operations: list[str] = Field(default_factory=list)
    trigger_qualities: list[str] = Field(default_factory=list)
    required_subject_kinds: list[SubjectKind] = Field(default_factory=list)
    acceptable_sources: list[EvidenceRefType] = Field(default_factory=list)
    default_blocking_level: Literal[
        "hard_block",
        "needs_user_clarification",
        "request_test_measurement",
        "request_evidence_artifact_lookup",
    ]
    rationale: str

    @field_validator("rule_id", "required_dimension", "rationale")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        return _not_blank(value, "need rule text field")


class QueueRevalidationRequest(StrictModel):
    knowledge_id: int
    trigger_type: str
    reason: str
    triggered_by_ref: str | None = None

    @field_validator("trigger_type", "reason")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        return _not_blank(value, "revalidation queue field")


class ResolveRevalidationRequest(StrictModel):
    queue_id: str
    resolution_rationale: str

    @field_validator("queue_id", "resolution_rationale")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        return _not_blank(value, "revalidation resolution field")


class RevalidationQueueResult(StrictModel):
    queue_id: str
    knowledge_id: int
    status: RevalidationStatus
    created: bool = False


class MissingKnowledgeNeed(StrictModel):
    need_id: str
    rule_id: str
    required_dimension: str
    subject_kind: str
    subject_id: str | None = None
    why_needed: str
    blocking_level: BlockingLevel
    acceptable_sources: list[str]


class KnowledgeQueryContext(StrictModel):
    project_id: str
    task_intents: list[str] = Field(default_factory=list)
    lifecycle_phase: str
    affected_entities: list[str] = Field(default_factory=list)
    operations: list[str] = Field(default_factory=list)
    qualities: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    risk_classes: list[str] = Field(default_factory=list)
    subject_refs: list[dict[str, Any]] = Field(default_factory=list)
    query_terms: list[str] = Field(default_factory=list)
    required_dimensions: list[str] = Field(default_factory=list)
    mode: KnowledgeQueryMode = "active"


class RejectedFact(StrictModel):
    knowledge_id: int
    reason: str


class KnowledgeQueryResult(StrictModel):
    mandatory_facts: list[KnowledgeFact] = Field(default_factory=list)
    supplemental_facts: list[KnowledgeFact] = Field(default_factory=list)
    rejected_facts: list[RejectedFact] = Field(default_factory=list)
    missing_knowledge_needs: list[MissingKnowledgeNeed] = Field(default_factory=list)
    degraded_recall_warnings: list[KnowledgeStoreWarning] = Field(default_factory=list)
    query_plan: dict[str, Any] = Field(default_factory=dict)


class ConflictRecord(StrictModel):
    conflict_id: str
    left_knowledge_id: int
    right_knowledge_id: int
    detected_at_utc: str
    conflict_reason: str
    status: ConflictStatus
