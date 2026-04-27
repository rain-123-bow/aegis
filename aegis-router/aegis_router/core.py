from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import ConflictError, InvalidRequestError, NotFoundError, PermissionDeniedError
from .models import AgentRecord, DomainRecord, MessageRecord, utc_now
from .storage import JsonStore


class Router:
    """Local Aegis message router.

    Phase-1 policy: communication is only allowed inside the same domain.
    Cross-domain communication must be mediated by a higher-level hub in a future version.
    """

    def __init__(self, store_path: str | Path):
        self.store = JsonStore(store_path)

    def _load(self) -> dict[str, Any]:
        return self.store.load()

    def _save(self, data: dict[str, Any]) -> None:
        self.store.save(data)

    def create_domain(
        self,
        domain_id: str,
        owner_agent_id: str | None = None,
        parent_domain_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not domain_id:
            raise InvalidRequestError("domain_id is required")
        data = self._load()
        if domain_id in data["domains"]:
            raise ConflictError(f"domain already exists: {domain_id}")
        if parent_domain_id and parent_domain_id not in data["domains"]:
            raise NotFoundError(f"parent domain not found: {parent_domain_id}")
        record = DomainRecord(
            domain_id=domain_id,
            owner_agent_id=owner_agent_id,
            parent_domain_id=parent_domain_id,
            metadata=metadata or {},
        )
        data["domains"][domain_id] = record.to_dict()
        self._save(data)
        return record.to_dict()

    def register_agent(
        self,
        agent_id: str,
        domain_id: str,
        role: str,
        parent_id: str | None = None,
        capabilities: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not agent_id:
            raise InvalidRequestError("agent_id is required")
        if not role:
            raise InvalidRequestError("role is required")
        data = self._load()
        if domain_id not in data["domains"]:
            raise NotFoundError(f"domain not found: {domain_id}")
        if agent_id in data["agents"]:
            raise ConflictError(f"agent already exists: {agent_id}")
        if parent_id and parent_id not in data["agents"]:
            raise NotFoundError(f"parent agent not found: {parent_id}")
        if parent_id and data["agents"][parent_id].get("domain_id") != domain_id:
            raise PermissionDeniedError(
                f"parent agent must be in the same domain: {data['agents'][parent_id].get('domain_id')} -> {domain_id}"
            )
        record = AgentRecord(
            agent_id=agent_id,
            domain_id=domain_id,
            role=role,
            parent_id=parent_id,
            capabilities=capabilities or [],
            metadata=metadata or {},
        )
        data["agents"][agent_id] = record.to_dict()
        self._save(data)
        return record.to_dict()

    def deactivate_agent(self, agent_id: str) -> dict[str, Any]:
        data = self._load()
        if agent_id not in data["agents"]:
            raise NotFoundError(f"agent not found: {agent_id}")
        data["agents"][agent_id]["status"] = "inactive"
        self._save(data)
        return data["agents"][agent_id]

    def unregister_agent(self, agent_id: str) -> dict[str, Any]:
        data = self._load()
        if agent_id not in data["agents"]:
            raise NotFoundError(f"agent not found: {agent_id}")
        record = data["agents"].pop(agent_id)
        record["status"] = "unregistered"
        self._save(data)
        return record

    def heartbeat(self, agent_id: str) -> dict[str, Any]:
        data = self._load()
        if agent_id not in data["agents"]:
            raise NotFoundError(f"agent not found: {agent_id}")
        if data["agents"][agent_id].get("status") != "active":
            raise PermissionDeniedError(f"agent is not active: {agent_id}")
        data["agents"][agent_id]["last_heartbeat_at"] = utc_now()
        self._save(data)
        return data["agents"][agent_id]

    def _agent(self, data: dict[str, Any], agent_id: str) -> dict[str, Any]:
        try:
            agent = data["agents"][agent_id]
        except KeyError as exc:
            raise NotFoundError(f"agent not found: {agent_id}") from exc
        if agent.get("status") != "active":
            raise PermissionDeniedError(f"agent is not active: {agent_id}")
        return agent

    def _assert_same_domain(self, data: dict[str, Any], from_id: str, to_id: str) -> str:
        src = self._agent(data, from_id)
        dst = self._agent(data, to_id)
        if src["domain_id"] != dst["domain_id"]:
            raise PermissionDeniedError(
                f"cross-domain message is not allowed in phase 1: {src['domain_id']} -> {dst['domain_id']}"
            )
        return src["domain_id"]

    def list_visible_agents(self, agent_id: str) -> list[dict[str, Any]]:
        data = self._load()
        agent = self._agent(data, agent_id)
        domain_id = agent["domain_id"]
        return [
            record
            for record in data["agents"].values()
            if record.get("domain_id") == domain_id and record.get("status") == "active"
        ]

    def send_message(
        self,
        from_id: str,
        to_id: str,
        message_type: str,
        payload: dict[str, Any],
        task_id: str | None = None,
        priority: str = "normal",
        requires_ack: bool = True,
    ) -> dict[str, Any]:
        if not message_type:
            raise InvalidRequestError("message_type is required")
        if not isinstance(payload, dict):
            raise InvalidRequestError("payload must be an object")
        data = self._load()
        domain_id = self._assert_same_domain(data, from_id, to_id)
        msg = MessageRecord.create(
            domain_id=domain_id,
            from_id=from_id,
            to_id=to_id,
            message_type=message_type,
            payload=payload,
            task_id=task_id,
            priority=priority,
            requires_ack=requires_ack,
        )
        data["messages"][msg.message_id] = msg.to_dict()
        self._save(data)
        return msg.to_dict()

    def receive_messages(self, agent_id: str, include_delivered: bool = False) -> list[dict[str, Any]]:
        data = self._load()
        self._agent(data, agent_id)
        result: list[dict[str, Any]] = []
        for message in data["messages"].values():
            if message.get("to_id") != agent_id:
                continue
            if message.get("status") in {"acked", "completed"}:
                continue
            if not include_delivered and message.get("status") == "delivered":
                continue
            if message.get("status") == "pending":
                message["delivered_at"] = utc_now()
                if message.get("requires_ack", True):
                    message["status"] = "delivered"
                else:
                    message["status"] = "completed"
            result.append(dict(message))
        self._save(data)
        return result

    def ack_message(self, agent_id: str, message_id: str) -> dict[str, Any]:
        data = self._load()
        self._agent(data, agent_id)
        if message_id not in data["messages"]:
            raise NotFoundError(f"message not found: {message_id}")
        message = data["messages"][message_id]
        if message.get("to_id") != agent_id:
            raise PermissionDeniedError("only the target agent may ack a message")
        if message.get("status") == "completed":
            raise InvalidRequestError("message does not require ack")
        message["status"] = "acked"
        message["acked_at"] = utc_now()
        self._save(data)
        return dict(message)

    def domain_snapshot(self, domain_id: str) -> dict[str, Any]:
        data = self._load()
        if domain_id not in data["domains"]:
            raise NotFoundError(f"domain not found: {domain_id}")
        agents = [a for a in data["agents"].values() if a.get("domain_id") == domain_id]
        messages = [m for m in data["messages"].values() if m.get("domain_id") == domain_id]
        return {
            "domain": data["domains"][domain_id],
            "agents": agents,
            "messages": messages,
        }
