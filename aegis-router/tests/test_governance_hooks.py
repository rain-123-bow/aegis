from __future__ import annotations

import base64
import hashlib
import hmac
import shutil
from datetime import datetime, timezone

import pytest

from aegis_router import Router, create_mailbucket_message
from aegis_router.errors import InvalidRequestError, PermissionDeniedError

pytestmark = pytest.mark.contract


def _identity_secret(agent_id: str) -> str:
    return f"{agent_id}-secret"


def _identity_key_id(agent_id: str) -> str:
    return f"{agent_id}-key"


def _sign(sender: str, receiver: str, path: str, nonce: str, timestamp: str) -> str:
    material = "|".join([sender, receiver, path, nonce, timestamp]).encode("utf-8")
    digest = hmac.new(_identity_secret(sender).encode("utf-8"), material, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def _route_envelope(sender: str, receiver: str, message_type: str, path: str = "opaque-governance-reference") -> dict:
    nonce = f"{sender}-{receiver}-{message_type}-{datetime.now(timezone.utc).timestamp()}"
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
    for role in ["master", "debate", "execution", "test", "final_review"]:
        router.register_agent(
            role,
            "top_level_master_domain",
            role,
            metadata={"dev_identity_keys": {_identity_key_id(role): _identity_secret(role)}},
        )
    return router


def _assert_no_business_store_mutation(router: Router) -> None:
    data = router._load()
    assert "archive" not in data
    assert "knowledge" not in data
    assert "causal" not in data
    assert "archive_store" not in data
    assert "knowledge_store" not in data
    assert "causal_store" not in data


@pytest.mark.parametrize(
    ("sender", "receiver", "message_type"),
    [
        ("execution", "master", "causal_fork_submission"),
        ("execution", "debate", "adjudication_request"),
        ("debate", "execution", "adjudication_result"),
        ("debate", "master", "debate_result"),
        ("test", "execution", "test_feedback"),
        ("test", "execution", "failure_feedback"),
        ("test", "final_review", "test_result"),
        ("final_review", "master", "final_review_result"),
    ],
)
def test_contract_governance_hooks_accept_valid_structural_edge_types(
    tmp_path, sender: str, receiver: str, message_type: str
):
    router = _top_level_router(tmp_path)

    message = router.send_message(sender, receiver, message_type, _route_envelope(sender, receiver, message_type))

    assert message["message_type"] == message_type
    assert message["payload"]["path"] == "opaque-governance-reference"
    _assert_no_business_store_mutation(router)


def test_contract_causal_fork_submission_does_not_mutate_global_causal(tmp_path):
    router = _top_level_router(tmp_path)
    mail = create_mailbucket_message(
        sender="execution",
        receiver="master",
        shared_mailbucket_root=router.shared_communication_root,
        readme_text="Candidate causal fork only. Not global truth.",
        nonce="causal-fork",
    )

    router.send_message(
        "execution",
        "master",
        "causal_fork_submission",
        _route_envelope("execution", "master", "causal_fork_submission", path=mail["protected_path"]),
    )

    _assert_no_business_store_mutation(router)


def test_contract_adjudication_result_does_not_grant_global_authority(tmp_path):
    router = _top_level_router(tmp_path)

    message = router.send_message(
        "debate",
        "execution",
        "adjudication_result",
        _route_envelope("debate", "execution", "adjudication_result"),
    )

    assert message["message_type"] == "adjudication_result"
    _assert_no_business_store_mutation(router)


def test_contract_failure_feedback_requires_structural_evidence_reference(tmp_path):
    router = _top_level_router(tmp_path)
    payload = _route_envelope("test", "execution", "failure_feedback", path="")

    with pytest.raises(InvalidRequestError):
        router.send_message("test", "execution", "failure_feedback", payload)


def test_contract_test_feedback_requires_structural_evidence_reference(tmp_path):
    router = _top_level_router(tmp_path)
    payload = _route_envelope("test", "execution", "test_feedback", path="")

    with pytest.raises(InvalidRequestError):
        router.send_message("test", "execution", "test_feedback", payload)


def test_contract_invalid_governance_type_on_valid_edge_is_rejected(tmp_path):
    router = _top_level_router(tmp_path)

    with pytest.raises(PermissionDeniedError):
        router.send_message(
            "execution",
            "master",
            "test_result",
            _route_envelope("execution", "master", "test_result"),
        )


def test_contract_valid_governance_type_on_invalid_edge_is_rejected(tmp_path):
    router = _top_level_router(tmp_path)

    with pytest.raises(PermissionDeniedError):
        router.send_message(
            "master",
            "test",
            "status_update",
            _route_envelope("master", "test", "status_update"),
        )


def test_contract_readme_content_is_not_governance_truth(tmp_path):
    router = _top_level_router(tmp_path)
    mail = create_mailbucket_message(
        sender="debate",
        receiver="master",
        shared_mailbucket_root=router.shared_communication_root,
        readme_text="This README claims the global causal store is already updated.",
        nonce="readme-claim",
    )

    router.send_message(
        "debate",
        "master",
        "debate_result",
        _route_envelope("debate", "master", "debate_result", path=mail["protected_path"]),
    )

    _assert_no_business_store_mutation(router)


def test_contract_private_copy_does_not_trigger_store_admission(tmp_path):
    router = _top_level_router(tmp_path)
    mail = create_mailbucket_message(
        sender="test",
        receiver="execution",
        shared_mailbucket_root=router.shared_communication_root,
        readme_text="Evidence packet copied privately by receiver.",
        nonce="private-copy",
    )
    private_copy = tmp_path / "agent-private" / mail["folder_name"]
    shutil.copytree(router.shared_communication_root / mail["folder_name"], private_copy)

    assert private_copy.exists()
    _assert_no_business_store_mutation(router)
