from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime, timezone

import pytest

from aegis_router import Router
from aegis_router.errors import PermissionDeniedError
from aegis_router.server import AegisRouterMcpServer

pytestmark = pytest.mark.contract

ROLES = ["master", "debate", "execution", "test", "final_review"]

VALID_EDGES = {
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
}

GOVERNANCE_TYPES_BY_EDGE = {
    ("master", "debate"): {"debate_request", "status_update"},
    ("master", "execution"): {"execution_request", "status_update"},
    ("debate", "master"): {"debate_result", "escalation", "status_update"},
    ("execution", "test"): {"implementation_candidate", "status_update"},
    ("test", "final_review"): {"test_result", "status_update"},
    ("final_review", "master"): {"final_review_result", "status_update"},
    ("test", "execution"): {"test_feedback", "failure_feedback", "status_update"},
    ("execution", "debate"): {"adjudication_request", "status_update"},
    ("debate", "execution"): {"adjudication_result", "status_update"},
    ("execution", "master"): {"causal_fork_submission", "governance_blocker", "status_update"},
}

ALL_GOVERNANCE_TYPES = set().union(*GOVERNANCE_TYPES_BY_EDGE.values())


def _identity_secret(agent_id: str) -> str:
    return f"{agent_id}-secret"


def _identity_key_id(agent_id: str) -> str:
    return f"{agent_id}-key"


def _sign(sender: str, receiver: str, path: str, nonce: str, timestamp: str) -> str:
    material = "|".join([sender, receiver, path, nonce, timestamp]).encode("utf-8")
    digest = hmac.new(_identity_secret(sender).encode("utf-8"), material, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def _route_envelope(sender: str, receiver: str, label: str = "matrix") -> dict:
    path = f"opaque-{label}-path"
    nonce = f"{sender}-{receiver}-{label}-{datetime.now(timezone.utc).timestamp()}"
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "sender": sender,
        "receiver": receiver,
        "path": path,
        "auth": {
            "alg": "aegis-dev-hmac-sha256",
            "key_id": _identity_key_id(sender),
            "nonce": nonce,
            "timestamp": timestamp,
            "signature": _sign(sender, receiver, path, nonce, timestamp),
        },
    }


def _top_level_router(tmp_path) -> Router:
    router = Router(tmp_path / "state.json")
    router.create_domain("top_level_master_domain", owner_agent_id="master")
    for role in ROLES:
        router.register_agent(
            role,
            "top_level_master_domain",
            role,
            metadata={"dev_identity_keys": {_identity_key_id(role): _identity_secret(role)}},
        )
    return router


def _mcp_call(server: AegisRouterMcpServer, name: str, arguments: dict):
    return server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}})


@pytest.mark.parametrize("sender", ROLES)
@pytest.mark.parametrize("receiver", ROLES)
def test_contract_exhaustive_top_level_role_matrix(tmp_path, sender: str, receiver: str):
    router = _top_level_router(tmp_path)
    payload = _route_envelope(sender, receiver, label=f"{sender}-{receiver}")

    if (sender, receiver) in VALID_EDGES:
        message = router.send_message(sender, receiver, "route_envelope", payload)
        assert message["from_id"] == sender
        assert message["to_id"] == receiver
    else:
        with pytest.raises(PermissionDeniedError):
            router.send_message(sender, receiver, "route_envelope", payload)


@pytest.mark.parametrize(("sender", "receiver"), sorted(VALID_EDGES))
def test_contract_governance_allowed_edge_type_pairs_pass(tmp_path, sender: str, receiver: str):
    router = _top_level_router(tmp_path)

    for message_type in sorted(GOVERNANCE_TYPES_BY_EDGE[(sender, receiver)]):
        message = router.send_message(sender, receiver, message_type, _route_envelope(sender, receiver, label=message_type))
        assert message["message_type"] == message_type


@pytest.mark.parametrize(("sender", "receiver"), sorted(VALID_EDGES))
def test_contract_governance_disallowed_type_on_allowed_edge_fails(tmp_path, sender: str, receiver: str):
    router = _top_level_router(tmp_path)
    disallowed_type = sorted(ALL_GOVERNANCE_TYPES - GOVERNANCE_TYPES_BY_EDGE[(sender, receiver)])[0]

    with pytest.raises(PermissionDeniedError):
        router.send_message(sender, receiver, disallowed_type, _route_envelope(sender, receiver, label=disallowed_type))


def test_contract_route_envelope_cannot_bypass_directed_edge(tmp_path):
    router = _top_level_router(tmp_path)

    with pytest.raises(PermissionDeniedError):
        router.send_message("master", "test", "route_envelope", _route_envelope("master", "test"))


def test_contract_mcp_send_message_matches_core_topology_rejection(tmp_path):
    router = _top_level_router(tmp_path)
    server = AegisRouterMcpServer(router)
    payload = _route_envelope("master", "test", label="mcp-invalid-edge")

    with pytest.raises(PermissionDeniedError):
        router.send_message("master", "test", "route_envelope", payload)

    response = _mcp_call(
        server,
        "send_message",
        {"from_id": "master", "to_id": "test", "message_type": "route_envelope", "payload": payload},
    )

    assert response is not None
    assert response["error"]["data"]["type"] == "PermissionDeniedError"


def test_contract_mcp_governance_type_rejection_matches_core(tmp_path):
    router = _top_level_router(tmp_path)
    server = AegisRouterMcpServer(router)
    payload = _route_envelope("execution", "master", label="mcp-invalid-governance-type")

    with pytest.raises(PermissionDeniedError):
        router.send_message("execution", "master", "test_result", payload)

    response = _mcp_call(
        server,
        "send_message",
        {"from_id": "execution", "to_id": "master", "message_type": "test_result", "payload": payload},
    )

    assert response is not None
    assert response["error"]["data"]["type"] == "PermissionDeniedError"


def test_contract_deactivated_unregistered_and_cross_domain_agents_cannot_bypass_topology(tmp_path):
    router = _top_level_router(tmp_path)
    router.create_domain("other_domain")
    router.register_agent(
        "external",
        "other_domain",
        "external",
        metadata={"dev_identity_keys": {"external-key": "external-secret"}},
    )

    router.deactivate_agent("master")
    with pytest.raises(PermissionDeniedError):
        router.send_message("master", "debate", "route_envelope", _route_envelope("master", "debate"))

    router.unregister_agent("master")
    with pytest.raises(PermissionDeniedError):
        router.send_message("external", "debate", "route_envelope", _route_envelope("external", "debate"))
