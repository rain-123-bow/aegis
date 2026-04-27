from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


@dataclass(slots=True)
class DomainRecord:
    domain_id: str
    owner_agent_id: str | None = None
    parent_domain_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain_id": self.domain_id,
            "owner_agent_id": self.owner_agent_id,
            "parent_domain_id": self.parent_domain_id,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DomainRecord":
        return cls(
            domain_id=data["domain_id"],
            owner_agent_id=data.get("owner_agent_id"),
            parent_domain_id=data.get("parent_domain_id"),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", utc_now()),
        )


@dataclass(slots=True)
class AgentRecord:
    agent_id: str
    domain_id: str
    role: str
    parent_id: str | None = None
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "active"
    registered_at: str = field(default_factory=utc_now)
    last_heartbeat_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "domain_id": self.domain_id,
            "role": self.role,
            "parent_id": self.parent_id,
            "capabilities": self.capabilities,
            "metadata": self.metadata,
            "status": self.status,
            "registered_at": self.registered_at,
            "last_heartbeat_at": self.last_heartbeat_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentRecord":
        return cls(
            agent_id=data["agent_id"],
            domain_id=data["domain_id"],
            role=data["role"],
            parent_id=data.get("parent_id"),
            capabilities=list(data.get("capabilities", [])),
            metadata=data.get("metadata", {}),
            status=data.get("status", "active"),
            registered_at=data.get("registered_at", utc_now()),
            last_heartbeat_at=data.get("last_heartbeat_at"),
        )


@dataclass(slots=True)
class MessageRecord:
    message_id: str
    domain_id: str
    from_id: str
    to_id: str
    message_type: str
    payload: dict[str, Any]
    task_id: str | None = None
    priority: str = "normal"
    requires_ack: bool = True
    status: str = "pending"
    created_at: str = field(default_factory=utc_now)
    delivered_at: str | None = None
    acked_at: str | None = None

    @classmethod
    def create(
        cls,
        *,
        domain_id: str,
        from_id: str,
        to_id: str,
        message_type: str,
        payload: dict[str, Any],
        task_id: str | None = None,
        priority: str = "normal",
        requires_ack: bool = True,
    ) -> "MessageRecord":
        return cls(
            message_id=new_id("msg"),
            domain_id=domain_id,
            from_id=from_id,
            to_id=to_id,
            message_type=message_type,
            payload=payload,
            task_id=task_id,
            priority=priority,
            requires_ack=requires_ack,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "domain_id": self.domain_id,
            "from_id": self.from_id,
            "to_id": self.to_id,
            "message_type": self.message_type,
            "payload": self.payload,
            "task_id": self.task_id,
            "priority": self.priority,
            "requires_ack": self.requires_ack,
            "status": self.status,
            "created_at": self.created_at,
            "delivered_at": self.delivered_at,
            "acked_at": self.acked_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MessageRecord":
        return cls(
            message_id=data["message_id"],
            domain_id=data["domain_id"],
            from_id=data["from_id"],
            to_id=data["to_id"],
            message_type=data["message_type"],
            payload=data.get("payload", {}),
            task_id=data.get("task_id"),
            priority=data.get("priority", "normal"),
            requires_ack=bool(data.get("requires_ack", True)),
            status=data.get("status", "pending"),
            created_at=data.get("created_at", utc_now()),
            delivered_at=data.get("delivered_at"),
            acked_at=data.get("acked_at"),
        )
