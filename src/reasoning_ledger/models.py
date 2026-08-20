from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence


class ItemType(str, Enum):
    INPUT = "input"
    FACT = "fact"
    RULE = "rule"
    CLAIM = "claim"


class ItemStatus(str, Enum):
    ACTIVE = "active"
    STALE = "stale"
    INVALID = "invalid"
    SUPERSEDED = "superseded"


class EdgeRelation(str, Enum):
    SUPPORTS = "supports"
    REFUTES = "refutes"
    ASSUMES = "assumes"
    SUPERSEDES = "supersedes"


class EdgeStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class EventType(str, Enum):
    CREATED = "created"
    LINKED = "linked"
    INVALIDATED = "invalidated"
    MARKED_STALE = "marked_stale"
    REVALIDATED = "revalidated"
    SUPERSEDED = "superseded"
    INDEX_REBUILT = "index_rebuilt"


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
    return dict(scope)


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
    return values


def json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class CreateItem:
    id: str
    type: ItemType | str
    scope: Mapping[str, Any]
    content: str
    created_by: str
    status: ItemStatus | str = ItemStatus.ACTIVE
    artifact_path: str | None = None
    source: str | None = None
    evidence_path: str | None = None
    confidence: float | None = None
    level: int = 0
    version: int = 1
    embedding: Sequence[float] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("item id must not be empty")
        if not self.content:
            raise ValueError("item content must not be empty")
        if not self.created_by:
            raise ValueError("created_by must not be empty")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if self.level < 0:
            raise ValueError("level must be >= 0")
        if self.version < 1:
            raise ValueError("version must be >= 1")
        enum_value(self.type)
        enum_value(self.status)
        normalize_relative_path(self.artifact_path)
        normalize_relative_path(self.evidence_path)
        validate_scope(self.scope)
        validate_embedding(self.embedding)


@dataclass(frozen=True)
class LinkItems:
    from_id: str
    to_id: str
    relation: EdgeRelation | str
    reason: str
    created_by: str
    confidence: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.from_id or not self.to_id:
            raise ValueError("edge endpoints must not be empty")
        if self.from_id == self.to_id:
            raise ValueError("edge endpoints must be different")
        if not self.reason:
            raise ValueError("edge reason must not be empty")
        if not self.created_by:
            raise ValueError("created_by must not be empty")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        enum_value(self.relation)


@dataclass(frozen=True)
class LedgerItem:
    id: str
    project_id: str
    type: ItemType | str
    status: ItemStatus | str
    scope: Mapping[str, Any]
    content: str
    artifact_path: str | None
    source: str | None
    evidence_path: str | None
    confidence: float | None
    level: int
    version: int
    metadata: Mapping[str, Any]
    created_by: str
    created_at: datetime | str
    updated_at: datetime | str

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "LedgerItem":
        return cls(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            type=str(row["type"]),
            status=str(row["status"]),
            scope=dict(row["scope"] or {}),
            content=str(row["content"]),
            artifact_path=row.get("artifact_path"),
            source=row.get("source"),
            evidence_path=row.get("evidence_path"),
            confidence=row.get("confidence"),
            level=int(row["level"]),
            version=int(row["version"]),
            metadata=dict(row["metadata"] or {}),
            created_by=str(row["created_by"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return json_ready(self.__dict__)


@dataclass(frozen=True)
class LedgerEdge:
    id: int
    project_id: str
    from_id: str
    to_id: str
    relation: EdgeRelation | str
    status: EdgeStatus | str
    reason: str
    confidence: float | None
    metadata: Mapping[str, Any]
    created_by: str
    created_at: datetime | str

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "LedgerEdge":
        return cls(
            id=int(row["id"]),
            project_id=str(row["project_id"]),
            from_id=str(row["from_id"]),
            to_id=str(row["to_id"]),
            relation=str(row["relation"]),
            status=str(row["status"]),
            reason=str(row["reason"]),
            confidence=row.get("confidence"),
            metadata=dict(row["metadata"] or {}),
            created_by=str(row["created_by"]),
            created_at=row["created_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return json_ready(self.__dict__)


@dataclass(frozen=True)
class LedgerEvent:
    id: int
    project_id: str
    target_kind: str
    target_id: str
    event_type: EventType | str
    reason: str
    payload: Mapping[str, Any]
    created_by: str
    created_at: datetime | str

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "LedgerEvent":
        return cls(
            id=int(row["id"]),
            project_id=str(row["project_id"]),
            target_kind=str(row["target_kind"]),
            target_id=str(row["target_id"]),
            event_type=str(row["event_type"]),
            reason=str(row["reason"]),
            payload=dict(row["payload"] or {}),
            created_by=str(row["created_by"]),
            created_at=row["created_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return json_ready(self.__dict__)


@dataclass(frozen=True)
class SearchResult:
    item: LedgerItem
    distance: float

    def to_dict(self) -> dict[str, Any]:
        return {"item": self.item.to_dict(), "distance": self.distance}


@dataclass(frozen=True)
class ContextPack:
    project_id: str
    task_id: str
    agent_role: str
    query: str
    items: Sequence[LedgerItem]
    cause_items: Sequence[LedgerItem]
    edges: Sequence[LedgerEdge]
    warnings: Sequence[str]
    artifact_paths: Sequence[str]

    def to_agent_payload(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "task_id": self.task_id,
            "agent_role": self.agent_role,
            "query": self.query,
            "items": [item.to_dict() for item in self.items],
            "cause_items": [item.to_dict() for item in self.cause_items],
            "edges": [edge.to_dict() for edge in self.edges],
            "warnings": list(self.warnings),
            "required_artifact_paths": list(dict.fromkeys(self.artifact_paths)),
        }
