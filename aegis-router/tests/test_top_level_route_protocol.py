from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime, timezone

import pytest

from aegis_router import Router
from aegis_router.errors import PermissionDeniedError

pytestmark = pytest.mark.contract

VALID_ROUTES = [
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
]

INVALID_ROUTES = [
    ("test", "master"),
    ("master", "test"),
    ("debate", "test"),
    ("final_review", "execution"),
    ("final_review", "debate"),
    ("test", "debate"),
]


def _identity_secret(agent_id: str) -> str:
    return f"{agent_id}-secret"


def _identity_key_id(agent_id: str) -> str:
    return f"{agent_id}-key"


def _sign_route_envelope(sender: str, receiver: str, path: str, nonce: str, timestamp: str) -> str:
    material = "|".join([sender, receiver, path, nonce, timestamp]).encode("utf-8")
    digest = hmac.new(_identity_secret(sender).encode("utf-8"), material, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def _top_level_router(tmp_path) -> Router:
    router = Router(tmp_path / "state.json")
    router.create_domain("top_level_master_domain", owner_agent_id="master")
    for role in ["master", "debate", "execution", "test", "final_review"]:
        router.register_agent(
            role,
            "top_level_master_domain",
            role,
            metadata={"dev_identity_keys": {_identity_key_id(role): _identity_secret(role)}},
        )
    return router


def _route_envelope(sender: str, receiver: str) -> dict:
    path = "opaque-receiver-path"
    nonce = f"{sender}-{receiver}-{datetime.now(timezone.utc).timestamp()}"
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
            "signature": _sign_route_envelope(sender, receiver, path, nonce, timestamp),
        },
    }


@pytest.mark.parametrize(("sender", "receiver"), VALID_ROUTES)
def test_contract_valid_top_level_routes_are_sendable(tmp_path, sender: str, receiver: str):
    router = _top_level_router(tmp_path)

    message = router.send_message(sender, receiver, "route_envelope", _route_envelope(sender, receiver))

    assert message["from_id"] == sender
    assert message["to_id"] == receiver
    assert message["status"] == "pending"


@pytest.mark.parametrize(("sender", "receiver"), INVALID_ROUTES)
def test_contract_invalid_top_level_routes_are_rejected(tmp_path, sender: str, receiver: str):
    router = _top_level_router(tmp_path)

    with pytest.raises(PermissionDeniedError):
        router.send_message(sender, receiver, "route_envelope", _route_envelope(sender, receiver))


def test_contract_same_domain_visibility_does_not_imply_send_permission(tmp_path):
    router = _top_level_router(tmp_path)

    visible_to_master = {agent["agent_id"] for agent in router.list_visible_agents("master")}
    assert "test" in visible_to_master

    with pytest.raises(PermissionDeniedError):
        router.send_message("master", "test", "route_envelope", _route_envelope("master", "test"))


def test_contract_protocol_pairs_do_not_create_unrestricted_chat(tmp_path):
    router = _top_level_router(tmp_path)

    with pytest.raises(PermissionDeniedError):
        router.send_message("debate", "test", "route_envelope", _route_envelope("debate", "test"))


def test_contract_role_local_route_tables_are_derived_from_authoritative_routes(tmp_path):
    router = _top_level_router(tmp_path)
    expected = {
        "master": {
            "outgoing": ["debate", "execution"],
            "incoming": ["debate", "final_review", "execution"],
        },
        "debate": {
            "outgoing": ["master", "execution"],
            "incoming": ["master", "execution"],
        },
        "execution": {
            "outgoing": ["test", "debate", "master"],
            "incoming": ["master", "test", "debate"],
        },
        "test": {
            "outgoing": ["final_review", "execution"],
            "incoming": ["execution"],
        },
        "final_review": {
            "outgoing": ["master"],
            "incoming": ["test"],
        },
    }

    for role, route_table in expected.items():
        actual = router.get_local_route_table(role)
        assert actual["agent_id"] == role
        assert actual["outgoing"] == route_table["outgoing"]
        assert actual["incoming"] == route_table["incoming"]
