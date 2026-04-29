from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .errors import ConflictError, InvalidRequestError, NotFoundError, PermissionDeniedError
from .mailbucket import cleanup_expired_mailbucket_messages
from .models import AgentRecord, DomainRecord, MessageRecord, utc_now
from .storage import JsonStore

TOP_LEVEL_DOMAIN_ID = "top_level_master_domain"
TOP_LEVEL_TOPOLOGY_ID = "master_top_level_v1"
TOP_LEVEL_ROUTE_EDGES: tuple[tuple[str, str], ...] = (
    ("master", "debate"),
    ("master", "execution"),
    ("debate", "master"),
    ("execution", "test"),
    ("test", "final_review"),
    ("final_review", "master"),
    ("test", "execution"),
    ("execution", "debate"),
    ("debate", "execution"),
    ("execution", "master"),
)
ROUTE_ENVELOPE_FIELDS = frozenset({"sender", "receiver", "path", "auth"})
ROUTE_ENVELOPE_AUTH_FIELDS = frozenset({"alg", "key_id", "nonce", "timestamp", "signature"})
DEV_HMAC_AUTH_ALG = "aegis-dev-hmac-sha256"
REAL_ED25519_AUTH_ALG = "aegis-ed25519-v1"
ROUTE_ENVELOPE_REPLAY_WINDOW_SECONDS = 300
GOVERNANCE_MESSAGE_TYPES_BY_EDGE: dict[tuple[str, str], frozenset[str]] = {
    ("master", "debate"): frozenset({"debate_request", "status_update"}),
    ("master", "execution"): frozenset({"execution_request", "status_update"}),
    ("debate", "master"): frozenset({"debate_result", "escalation", "status_update"}),
    ("execution", "test"): frozenset({"implementation_candidate", "status_update"}),
    ("test", "final_review"): frozenset({"test_result", "status_update"}),
    ("final_review", "master"): frozenset({"final_review_result", "status_update"}),
    ("test", "execution"): frozenset({"failure_feedback", "status_update"}),
    ("execution", "debate"): frozenset({"adjudication_request", "status_update"}),
    ("debate", "execution"): frozenset({"adjudication_result", "status_update"}),
    ("execution", "master"): frozenset({"causal_fork_submission", "governance_blocker", "status_update"}),
}
GOVERNANCE_MESSAGE_TYPES = frozenset(
    message_type
    for allowed_types in GOVERNANCE_MESSAGE_TYPES_BY_EDGE.values()
    for message_type in allowed_types
)


class Router:
    """Local Aegis message router.

    Phase-1 policy: communication is only allowed inside the same domain.
    Cross-domain communication must be mediated by a higher-level hub in a future version.
    """

    def __init__(self, store_path: str | Path, shared_communication_root: str | Path | None = None):
        self.store = JsonStore(store_path)
        root = shared_communication_root or (self.store.path.parent / "mailbucket")
        self.shared_communication_root = Path(root).resolve()

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

    def _configured_route_edges(self, data: dict[str, Any], domain_id: str) -> tuple[tuple[str, str], ...] | None:
        domain = data["domains"].get(domain_id, {})
        metadata = domain.get("metadata", {})
        configured = metadata.get("router_route_table")
        if configured is not None:
            edges: list[tuple[str, str]] = []
            for item in configured:
                if isinstance(item, dict):
                    edge_from = item.get("from")
                    edge_to = item.get("to")
                elif isinstance(item, (list, tuple)) and len(item) == 2:
                    edge_from, edge_to = item
                else:
                    raise InvalidRequestError("router_route_table entries must define from/to")
                if not edge_from or not edge_to:
                    raise InvalidRequestError("router_route_table entries must define from/to")
                edges.append((str(edge_from), str(edge_to)))
            return tuple(edges)
        if domain_id == TOP_LEVEL_DOMAIN_ID or metadata.get("topology_id") == TOP_LEVEL_TOPOLOGY_ID:
            return TOP_LEVEL_ROUTE_EDGES
        return None

    def _assert_route_allowed(self, data: dict[str, Any], domain_id: str, from_id: str, to_id: str) -> None:
        route_edges = self._configured_route_edges(data, domain_id)
        if route_edges is None:
            return
        if (from_id, to_id) not in route_edges:
            raise PermissionDeniedError(f"directed route is not allowed: {from_id} -> {to_id}")

    def _validate_top_level_message_type(self, domain_id: str, from_id: str, to_id: str, message_type: str) -> None:
        if domain_id != TOP_LEVEL_DOMAIN_ID or message_type == "route_envelope":
            return
        allowed = GOVERNANCE_MESSAGE_TYPES_BY_EDGE.get((from_id, to_id))
        if allowed is None:
            return
        if message_type not in allowed:
            raise PermissionDeniedError(f"governance message type is not allowed on edge: {message_type} {from_id} -> {to_id}")

    def _validate_route_envelope_shape(self, from_id: str, to_id: str, payload: dict[str, Any]) -> None:
        missing = [field for field in ("sender", "receiver", "path", "auth") if field not in payload]
        if missing:
            raise InvalidRequestError(f"route_envelope missing required field(s): {', '.join(missing)}")
        unknown = sorted(set(payload) - ROUTE_ENVELOPE_FIELDS)
        if unknown:
            raise InvalidRequestError(f"route_envelope has unknown field(s): {', '.join(unknown)}")
        if payload["sender"] != from_id:
            raise InvalidRequestError("route_envelope sender must match from_id")
        if payload["receiver"] != to_id:
            raise InvalidRequestError("route_envelope receiver must match to_id")
        if not isinstance(payload["sender"], str) or not payload["sender"]:
            raise InvalidRequestError("route_envelope sender must be a non-empty string")
        if not isinstance(payload["receiver"], str) or not payload["receiver"]:
            raise InvalidRequestError("route_envelope receiver must be a non-empty string")
        if not isinstance(payload["path"], str) or not payload["path"]:
            raise InvalidRequestError("route_envelope path must be a non-empty opaque string")
        if not isinstance(payload["auth"], dict):
            raise InvalidRequestError("route_envelope auth must be an object")

    def _parse_route_envelope_timestamp(self, value: Any) -> datetime:
        if isinstance(value, (int, float)):
            # Numeric timestamps are milliseconds since epoch.
            return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
        if isinstance(value, str) and value:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                raise InvalidRequestError("route_envelope auth timestamp must include timezone")
            return parsed.astimezone(timezone.utc)
        raise InvalidRequestError("route_envelope auth timestamp must be an ISO UTC string or unix milliseconds")

    def _route_envelope_signature_material(self, payload: dict[str, Any]) -> bytes:
        auth = payload["auth"]
        # Canonical auth material follows the documented Envelope v1 order.
        parts = [
            payload["sender"],
            payload["receiver"],
            payload["path"],
            auth["nonce"],
            str(auth["timestamp"]),
        ]
        return "|".join(parts).encode("utf-8")

    def _load_ed25519_public_key(self, public_key_text: str) -> Ed25519PublicKey:
        if not isinstance(public_key_text, str) or not public_key_text:
            raise InvalidRequestError("sender identity public key must be a non-empty string")
        key_bytes = public_key_text.encode("utf-8")
        try:
            if "BEGIN PUBLIC KEY" in public_key_text:
                loaded = serialization.load_pem_public_key(key_bytes)
                if not isinstance(loaded, Ed25519PublicKey):
                    raise InvalidRequestError("sender identity public key must be Ed25519")
                return loaded
            return Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_text, validate=True))
        except ValueError as exc:
            raise InvalidRequestError("sender identity public key is malformed") from exc

    def _validate_dev_hmac_route_envelope_auth(
        self, data: dict[str, Any], payload: dict[str, Any], material: bytes
    ) -> None:
        auth = payload["auth"]
        sender = self._agent(data, payload["sender"])
        metadata = sender.get("metadata", {})
        identity_keys = metadata.get("dev_identity_keys") or metadata.get("identity_keys") or {}
        if not isinstance(identity_keys, dict):
            raise InvalidRequestError("agent identity key registry must be an object")
        key = identity_keys.get(auth["key_id"])
        if not isinstance(key, str) or not key:
            raise PermissionDeniedError("sender identity key is not registered")

        expected = base64.b64encode(hmac.new(key.encode("utf-8"), material, hashlib.sha256).digest()).decode("ascii")
        if not hmac.compare_digest(expected, auth["signature"]):
            raise PermissionDeniedError("route_envelope signature verification failed")

    def _validate_ed25519_route_envelope_auth(
        self, data: dict[str, Any], payload: dict[str, Any], material: bytes
    ) -> None:
        auth = payload["auth"]
        sender = self._agent(data, payload["sender"])
        metadata = sender.get("metadata", {})
        identity_public_keys = metadata.get("identity_public_keys") or {}
        if not isinstance(identity_public_keys, dict):
            raise InvalidRequestError("agent identity public key registry must be an object")
        key_entry = identity_public_keys.get(auth["key_id"])
        if not isinstance(key_entry, dict):
            raise PermissionDeniedError("sender identity public key is not registered")
        if key_entry.get("alg") != "ed25519":
            raise PermissionDeniedError("sender identity public key algorithm is not supported")

        public_key = self._load_ed25519_public_key(key_entry.get("public_key", ""))
        try:
            signature = base64.b64decode(auth["signature"], validate=True)
        except ValueError as exc:
            raise InvalidRequestError("route_envelope signature must be base64") from exc
        try:
            public_key.verify(signature, material)
        except InvalidSignature as exc:
            raise PermissionDeniedError("route_envelope signature verification failed") from exc

    def _validate_route_envelope_auth(self, data: dict[str, Any], payload: dict[str, Any]) -> None:
        auth = payload["auth"]
        missing = [field for field in ("alg", "key_id", "nonce", "timestamp", "signature") if field not in auth]
        if missing:
            raise InvalidRequestError(f"route_envelope auth missing required field(s): {', '.join(missing)}")
        unknown = sorted(set(auth) - ROUTE_ENVELOPE_AUTH_FIELDS)
        if unknown:
            raise InvalidRequestError(f"route_envelope auth has unknown field(s): {', '.join(unknown)}")
        if auth["alg"] not in {DEV_HMAC_AUTH_ALG, REAL_ED25519_AUTH_ALG}:
            raise PermissionDeniedError(f"unsupported route_envelope auth algorithm: {auth['alg']}")
        for field in ("key_id", "nonce", "signature"):
            if not isinstance(auth[field], str) or not auth[field]:
                raise InvalidRequestError(f"route_envelope auth {field} must be a non-empty string")

        timestamp = self._parse_route_envelope_timestamp(auth["timestamp"])
        now = datetime.now(timezone.utc)
        age_seconds = abs((now - timestamp).total_seconds())
        if age_seconds > ROUTE_ENVELOPE_REPLAY_WINDOW_SECONDS:
            raise PermissionDeniedError("route_envelope auth timestamp is outside replay window")

        material = self._route_envelope_signature_material(payload)
        if auth["alg"] == DEV_HMAC_AUTH_ALG:
            self._validate_dev_hmac_route_envelope_auth(data, payload, material)
        else:
            self._validate_ed25519_route_envelope_auth(data, payload, material)

        replay_nonces = data.setdefault("route_envelope_replay_nonces", {})
        replay_key = f"{payload['sender']}:{auth['key_id']}:{auth['nonce']}"
        if replay_key in replay_nonces:
            raise PermissionDeniedError("route_envelope nonce has already been used")
        replay_nonces[replay_key] = timestamp.isoformat()

    def get_local_route_table(self, agent_id: str) -> dict[str, Any]:
        data = self._load()
        agent = self._agent(data, agent_id)
        domain_id = agent["domain_id"]
        route_edges = self._configured_route_edges(data, domain_id) or ()
        outgoing = [to_id for from_id, to_id in route_edges if from_id == agent_id]
        incoming = [from_id for from_id, to_id in route_edges if to_id == agent_id]
        return {
            "agent_id": agent_id,
            "domain_id": domain_id,
            "topology_id": data["domains"].get(domain_id, {}).get("metadata", {}).get("topology_id"),
            "outgoing": outgoing,
            "incoming": incoming,
        }

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
        if message_type == "route_envelope" or message_type in GOVERNANCE_MESSAGE_TYPES:
            self._validate_route_envelope_shape(from_id, to_id, payload)
        data = self._load()
        domain_id = self._assert_same_domain(data, from_id, to_id)
        self._assert_route_allowed(data, domain_id, from_id, to_id)
        self._validate_top_level_message_type(domain_id, from_id, to_id, message_type)
        if message_type == "route_envelope" or message_type in GOVERNANCE_MESSAGE_TYPES:
            self._validate_route_envelope_auth(data, payload)
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

    def cleanup_mailbucket(self, grace_period_seconds: int | float, now: datetime | None = None) -> dict[str, Any]:
        return cleanup_expired_mailbucket_messages(
            shared_mailbucket_root=self.shared_communication_root,
            grace_period_seconds=grace_period_seconds,
            now=now,
        )

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
