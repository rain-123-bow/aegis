from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SUPPORTED_EMBEDDING_INPUT_TEMPLATE_VERSION = "statement-v1"


class StatementType(str, Enum):
    OBSERVATION = "OBSERVATION"
    FACT = "FACT"
    CONSTRAINT = "CONSTRAINT"
    REQUIREMENT = "REQUIREMENT"
    DECISION = "DECISION"
    RULE = "RULE"
    HYPOTHESIS = "HYPOTHESIS"
    CLAIM = "CLAIM"


class RevisionValidity(str, Enum):
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    INVALID = "INVALID"
    SUPERSEDED = "SUPERSEDED"


class RelationType(str, Enum):
    SUPPORTS = "SUPPORTS"
    REFUTES = "REFUTES"
    ASSUMES = "ASSUMES"
    SUPERSEDES = "SUPERSEDES"
    CAUSES = "CAUSES"
    ENABLES = "ENABLES"
    PREVENTS = "PREVENTS"
    REQUIRES = "REQUIRES"


def enum_value(value: str | Enum) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def normalize_relative_path(path: str | None) -> str | None:
    if path is None:
        return None
    value = path.replace("\\", "/").strip()
    if not value:
        raise ValueError("artifact/evidence path must not be empty")
    if value.startswith("/") or value.startswith("~") or len(value) >= 2 and value[1] == ":":
        raise ValueError(f"path must be project-relative: {path!r}")
    posix = PurePosixPath(value)
    if any(part in ("", ".", "..") for part in posix.parts):
        raise ValueError(f"path must be normalized and project-relative: {path!r}")
    return str(posix)


def validate_scope(scope: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(scope, Mapping):
        raise TypeError("scope must be a mapping")
    normalized = dict(scope)
    permissions = normalized.get("required_permissions")
    if permissions is not None and (
        not isinstance(permissions, list)
        or any(not isinstance(value, str) or not value.strip() for value in permissions)
        or len(permissions) != len(set(permissions))
    ):
        raise ValueError("scope required_permissions must be unique non-empty strings")
    return normalized


def validate_embedding(
    embedding: Sequence[float] | None,
    *,
    dimensions: int | None = None,
) -> list[float] | None:
    if embedding is None:
        return None
    values = [float(value) for value in embedding]
    if dimensions is not None and len(values) != dimensions:
        raise ValueError(f"embedding dimension mismatch: expected {dimensions}, got {len(values)}")
    if not values:
        raise ValueError("embedding must not be empty")
    if any(not math.isfinite(value) for value in values):
        raise ValueError("embedding values must be finite")
    return values


def json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        encoded = value.isoformat()
        return encoded[:-6] + "Z" if encoded.endswith("+00:00") else encoded
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    return value


def canonical_content_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        json_ready(dict(value)),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class EvidenceDescriptor:
    evidence_id: str
    path: str
    size: int
    sha256: str
    source_identity: Mapping[str, Any]
    captured_at: datetime | str
    scope: Mapping[str, Any]
    created_by: str
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("evidence_id must not be empty")
        normalized_path = normalize_relative_path(self.path)
        if normalized_path is None:
            raise ValueError("evidence path must not be empty")
        if (
            isinstance(self.size, bool)
            or not isinstance(self.size, int)
            or self.size < 0
        ):
            raise ValueError("evidence size must be >= 0")
        if _SHA256_PATTERN.fullmatch(self.sha256) is None:
            raise ValueError("evidence sha256 must be 64 lowercase hex characters")
        if not isinstance(self.source_identity, Mapping) or not self.source_identity:
            raise ValueError("source_identity must be a non-empty mapping")
        if not str(self.captured_at).strip():
            raise ValueError("captured_at must not be empty")
        if not self.created_by.strip():
            raise ValueError("created_by must not be empty")
        normalized_scope = validate_scope(self.scope)
        object.__setattr__(self, "path", normalized_path)
        object.__setattr__(self, "source_identity", dict(self.source_identity))
        object.__setattr__(self, "scope", normalized_scope)
        object.__setattr__(
            self,
            "content_sha256",
            canonical_content_sha256(
                {
                    "path": normalized_path,
                    "size": self.size,
                    "sha256": self.sha256,
                    "source_identity": dict(self.source_identity),
                    "captured_at": self.captured_at,
                    "scope": normalized_scope,
                    "created_by": self.created_by,
                }
            ),
        )


@dataclass(frozen=True)
class StatementRevision:
    statement_id: str
    revision: int
    statement_type: StatementType | str
    content: str
    structured_conditions: Mapping[str, Any]
    validity: RevisionValidity | str
    scope: Mapping[str, Any]
    confidence: float | None
    created_by: str
    evidence_ids: Sequence[str] = ()
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.statement_id.strip():
            raise ValueError("statement_id must not be empty")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise ValueError("revision must be >= 1")
        if not self.content.strip():
            raise ValueError("statement content must not be empty")
        statement_type = enum_value(self.statement_type).upper()
        validity = enum_value(self.validity).upper()
        if statement_type not in {value.value for value in StatementType}:
            raise ValueError("statement_type is invalid")
        if validity not in {value.value for value in RevisionValidity}:
            raise ValueError("validity is invalid")
        if self.confidence is not None and (
            not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1
        ):
            raise ValueError("confidence must be finite and between 0 and 1")
        if not self.created_by.strip():
            raise ValueError("created_by must not be empty")
        evidence_ids = tuple(str(value) for value in self.evidence_ids)
        if not evidence_ids or any(not value.strip() for value in evidence_ids):
            raise ValueError("evidence_ids must be non-empty")
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence_ids must be unique")
        conditions = validate_scope(self.structured_conditions)
        scope = validate_scope(self.scope)
        object.__setattr__(self, "statement_type", statement_type)
        object.__setattr__(self, "validity", validity)
        object.__setattr__(self, "structured_conditions", conditions)
        object.__setattr__(self, "scope", scope)
        object.__setattr__(self, "evidence_ids", evidence_ids)
        object.__setattr__(
            self,
            "content_sha256",
            canonical_content_sha256(
                {
                    "statement_type": statement_type,
                    "content": self.content,
                    "structured_conditions": conditions,
                    "validity": validity,
                    "scope": scope,
                    "confidence": self.confidence,
                    "evidence_ids": list(evidence_ids),
                }
            ),
        )


@dataclass(frozen=True)
class EmbeddingProfile:
    profile_id: str
    provider: str
    model: str
    model_version: str
    dimensions: int
    normalization: str
    input_template_version: str
    created_by: str
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        identity_values = {
            "provider": self.provider,
            "model": self.model,
            "model_version": self.model_version,
            "normalization": self.normalization,
            "input_template_version": self.input_template_version,
        }
        if any(not value.strip() for value in identity_values.values()) or not self.created_by.strip():
            raise ValueError("embedding profile string fields must not be empty")
        if self.dimensions <= 0:
            raise ValueError("embedding profile dimensions must be > 0")
        object.__setattr__(
            self,
            "content_sha256",
            canonical_content_sha256(
                {**identity_values, "dimensions": self.dimensions}
            ),
        )


@dataclass(frozen=True)
class StatementRelation:
    relation_id: str
    from_statement_id: str
    from_revision: int
    to_statement_id: str
    to_revision: int
    relation_type: RelationType | str
    applicable_conditions: Mapping[str, Any]
    reason: str
    created_by: str
    evidence_ids: Sequence[str]
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        for field_name in (
            "relation_id",
            "from_statement_id",
            "to_statement_id",
            "reason",
            "created_by",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.from_revision < 1 or self.to_revision < 1:
            raise ValueError("relation revisions must be >= 1")
        if (
            self.from_statement_id == self.to_statement_id
            and self.from_revision == self.to_revision
        ):
            raise ValueError("relation endpoints must be different")
        relation_type = enum_value(self.relation_type).upper()
        if relation_type not in {value.value for value in RelationType}:
            raise ValueError("relation_type is invalid")
        evidence_ids = tuple(str(value) for value in self.evidence_ids)
        if not evidence_ids or any(not value.strip() for value in evidence_ids):
            raise ValueError("relation evidence_ids must be non-empty")
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("relation evidence_ids must be unique")
        conditions = validate_scope(self.applicable_conditions)
        object.__setattr__(self, "relation_type", relation_type)
        object.__setattr__(self, "applicable_conditions", conditions)
        object.__setattr__(self, "evidence_ids", evidence_ids)
        object.__setattr__(
            self,
            "content_sha256",
            canonical_content_sha256(
                {
                    "from_statement_id": self.from_statement_id,
                    "from_revision": self.from_revision,
                    "to_statement_id": self.to_statement_id,
                    "to_revision": self.to_revision,
                    "relation_type": relation_type,
                    "applicable_conditions": conditions,
                    "reason": self.reason,
                    "evidence_ids": list(evidence_ids),
                }
            ),
        )


@dataclass(frozen=True)
class LedgerEvidence:
    project_id: str
    evidence_id: str
    path: str
    size: int
    sha256: str
    source_identity: Mapping[str, Any]
    captured_at: datetime | str
    scope: Mapping[str, Any]
    content_sha256: str
    created_by: str
    created_at: datetime | str

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "LedgerEvidence":
        return cls(
            project_id=str(row["project_id"]),
            evidence_id=str(row["evidence_id"]),
            path=str(row["path"]),
            size=int(row["size"]),
            sha256=str(row["sha256"]),
            source_identity=dict(row["source_identity"] or {}),
            captured_at=row["captured_at"],
            scope=dict(row["scope"] or {}),
            content_sha256=str(row["content_sha256"]),
            created_by=str(row["created_by"]),
            created_at=row["created_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return json_ready(self.__dict__)


@dataclass(frozen=True)
class LedgerStatementRevision:
    project_id: str
    statement_id: str
    revision: int
    statement_type: str
    content: str
    structured_conditions: Mapping[str, Any]
    validity: str
    current_validity: str
    scope: Mapping[str, Any]
    confidence: float | None
    content_sha256: str
    created_by: str
    created_at: datetime | str
    evidence_ids: Sequence[str] = ()

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "LedgerStatementRevision":
        raw_evidence = row.get("evidence_ids") or []
        return cls(
            project_id=str(row["project_id"]),
            statement_id=str(row["statement_id"]),
            revision=int(row["revision"]),
            statement_type=str(row["statement_type"]),
            content=str(row["content"]),
            structured_conditions=dict(row["structured_conditions"] or {}),
            validity=str(row["validity"]),
            current_validity=str(row.get("current_validity") or row["validity"]),
            scope=dict(row["scope"] or {}),
            confidence=row.get("confidence"),
            content_sha256=str(row["content_sha256"]),
            created_by=str(row["created_by"]),
            created_at=row["created_at"],
            evidence_ids=tuple(str(value) for value in raw_evidence),
        )

    @property
    def id(self) -> str:
        return self.statement_id

    @property
    def status(self) -> str:
        return self.current_validity

    @property
    def type(self) -> str:
        return self.statement_type

    def to_dict(self) -> dict[str, Any]:
        return json_ready(self.__dict__)


def render_statement_embedding_input(
    revision: LedgerStatementRevision,
    *,
    template_version: str,
) -> str:
    if template_version != SUPPORTED_EMBEDDING_INPUT_TEMPLATE_VERSION:
        raise ValueError(
            f"unsupported statement embedding input template: {template_version}"
        )
    return json.dumps(
        {
            "schema": SUPPORTED_EMBEDDING_INPUT_TEMPLATE_VERSION,
            "statement_type": revision.statement_type,
            "content": revision.content,
            "structured_conditions": json_ready(dict(revision.structured_conditions)),
            "scope": json_ready(dict(revision.scope)),
        },
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True)
class LedgerRelation:
    project_id: str
    relation_id: str
    from_statement_id: str
    from_revision: int
    to_statement_id: str
    to_revision: int
    relation_type: str
    applicable_conditions: Mapping[str, Any]
    reason: str
    content_sha256: str
    created_by: str
    created_at: datetime | str
    evidence_ids: Sequence[str] = ()

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "LedgerRelation":
        return cls(
            project_id=str(row["project_id"]),
            relation_id=str(row["relation_id"]),
            from_statement_id=str(row["from_statement_id"]),
            from_revision=int(row["from_revision"]),
            to_statement_id=str(row["to_statement_id"]),
            to_revision=int(row["to_revision"]),
            relation_type=str(row["relation_type"]),
            applicable_conditions=dict(row["applicable_conditions"] or {}),
            reason=str(row["reason"]),
            content_sha256=str(row["content_sha256"]),
            created_by=str(row["created_by"]),
            created_at=row["created_at"],
            evidence_ids=tuple(str(value) for value in row.get("evidence_ids") or []),
        )

    @property
    def id(self) -> str:
        return self.relation_id

    @property
    def from_id(self) -> str:
        return self.from_statement_id

    @property
    def to_id(self) -> str:
        return self.to_statement_id

    @property
    def relation(self) -> str:
        return self.relation_type

    def to_dict(self) -> dict[str, Any]:
        return json_ready(self.__dict__)


@dataclass(frozen=True)
class LedgerAuthorityEvent:
    project_id: str
    event_id: int
    aggregate_kind: str
    aggregate_id: str
    event_type: str
    reason: str
    payload: Mapping[str, Any]
    created_by: str
    created_at: datetime | str

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "LedgerAuthorityEvent":
        return cls(
            project_id=str(row["project_id"]),
            event_id=int(row["event_id"]),
            aggregate_kind=str(row["aggregate_kind"]),
            aggregate_id=str(row["aggregate_id"]),
            event_type=str(row["event_type"]),
            reason=str(row["reason"]),
            payload=dict(row["payload"] or {}),
            created_by=str(row["created_by"]),
            created_at=row["created_at"],
        )

    @property
    def id(self) -> int:
        return self.event_id

    def to_dict(self) -> dict[str, Any]:
        return json_ready(self.__dict__)


@dataclass(frozen=True)
class CandidateHit:
    revision: LedgerStatementRevision
    sources: Sequence[str]
    lexical_rank: float | None = None
    semantic_distance: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision": self.revision.to_dict(),
            "sources": list(self.sources),
            "lexical_rank": self.lexical_rank,
            "semantic_distance": self.semantic_distance,
        }


@dataclass(frozen=True)
class AuthorityContextPack:
    project_id: str
    task_id: str
    agent_role: str
    query: str
    candidates: Sequence[CandidateHit]
    causal_revisions: Sequence[LedgerStatementRevision]
    relations: Sequence[LedgerRelation]
    conflicts: Sequence[LedgerRelation]
    warnings: Sequence[str]
    evidence_descriptors: Sequence[LedgerEvidence]
    retrieval_trace: Mapping[str, Any]

    def to_agent_payload(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "task_id": self.task_id,
            "agent_role": self.agent_role,
            "query": self.query,
            "candidates": [value.to_dict() for value in self.candidates],
            "causal_revisions": [value.to_dict() for value in self.causal_revisions],
            "relations": [value.to_dict() for value in self.relations],
            "conflicts": [value.to_dict() for value in self.conflicts],
            "warnings": list(self.warnings),
            "evidence_descriptors": [
                value.to_dict() for value in self.evidence_descriptors
            ],
            "retrieval_trace": json_ready(dict(self.retrieval_trace)),
        }
