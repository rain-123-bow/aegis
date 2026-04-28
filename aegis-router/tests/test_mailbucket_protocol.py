from __future__ import annotations

import base64
import hashlib
import hmac
import os
import shutil
from datetime import datetime, timedelta, timezone

import pytest

from aegis_router import Router, create_mailbucket_message
from aegis_router.errors import InvalidRequestError, PermissionDeniedError
from aegis_router.path_resolution import make_dev_protected_path_token, resolve_route_envelope_path

pytestmark = pytest.mark.contract


def _identity_secret(agent_id: str) -> str:
    return f"{agent_id}-secret"


def _identity_key_id(agent_id: str) -> str:
    return f"{agent_id}-key"


def _signature(secret: str, sender: str, receiver: str, path: str, nonce: str, timestamp: str) -> str:
    material = "|".join([sender, receiver, path, nonce, timestamp]).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), material, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def _signed_route_envelope(
    sender: str = "master",
    receiver: str = "execution",
    *,
    path: str = "encrypted-path",
    nonce: str | None = None,
    timestamp: str | None = None,
    secret: str | None = None,
    key_id: str | None = None,
) -> dict:
    nonce = nonce or f"{sender}-{receiver}-{datetime.now(timezone.utc).timestamp()}"
    timestamp = timestamp or datetime.now(timezone.utc).isoformat()
    secret = secret or _identity_secret(sender)
    key_id = key_id or _identity_key_id(sender)
    return {
        "sender": sender,
        "receiver": receiver,
        "path": path,
        "auth": {
            "alg": "aegis-dev-hmac-sha256",
            "key_id": key_id,
            "nonce": nonce,
            "timestamp": timestamp,
            "signature": _signature(secret, sender, receiver, path, nonce, timestamp),
        },
    }


def _router_with_agents(tmp_path) -> Router:
    router = Router(tmp_path / "state.json")
    router.create_domain("top_level_master_domain", owner_agent_id="master")
    router.register_agent(
        "master",
        "top_level_master_domain",
        "master",
        metadata={"dev_identity_keys": {_identity_key_id("master"): _identity_secret("master")}},
    )
    router.register_agent(
        "execution",
        "top_level_master_domain",
        "execution",
        metadata={"dev_identity_keys": {_identity_key_id("execution"): _identity_secret("execution")}},
    )
    router.register_agent(
        "debate",
        "top_level_master_domain",
        "debate",
        metadata={"dev_identity_keys": {_identity_key_id("debate"): _identity_secret("debate")}},
    )
    return router


@pytest.mark.parametrize(
    "payload",
    [
        {"receiver": "execution", "path": "encrypted-path", "auth": {"signature": "sig"}},
        {"sender": "master", "path": "encrypted-path", "auth": {"signature": "sig"}},
        {"sender": "master", "receiver": "execution", "auth": {"signature": "sig"}},
        {"sender": "master", "receiver": "execution", "path": "encrypted-path"},
    ],
)
def test_contract_envelope_requires_sender_receiver_path_and_auth(tmp_path, payload: dict):
    router = _router_with_agents(tmp_path)

    with pytest.raises(InvalidRequestError):
        router.send_message("master", "execution", "route_envelope", payload)


def test_contract_forged_sender_identity_is_rejected(tmp_path):
    router = _router_with_agents(tmp_path)
    forged = _signed_route_envelope(secret=_identity_secret("execution"))

    with pytest.raises(PermissionDeniedError):
        router.send_message("master", "execution", "route_envelope", forged)


def test_contract_auth_covers_path_nonce_and_timestamp(tmp_path):
    router = _router_with_agents(tmp_path)
    envelope = _signed_route_envelope(path="original-encrypted-path")
    envelope["path"] = "tampered-encrypted-path"

    with pytest.raises(PermissionDeniedError):
        router.send_message("master", "execution", "route_envelope", envelope)


def test_contract_signature_covers_sender_receiver_path_nonce_and_timestamp(tmp_path):
    router = _router_with_agents(tmp_path)
    timestamp = datetime.now(timezone.utc).isoformat()
    mutated_timestamp = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
    cases = [
        ("sender", "debate", "debate", "execution"),
        ("receiver", "debate", "master", "debate"),
        ("path", "tampered-path", "master", "execution"),
        ("nonce", "tampered-nonce", "master", "execution"),
        ("timestamp", mutated_timestamp, "master", "execution"),
    ]

    for field, value, from_id, to_id in cases:
        envelope = _signed_route_envelope(nonce=f"nonce-for-{field}", timestamp=timestamp)
        if field in {"sender", "receiver", "path"}:
            envelope[field] = value
        else:
            envelope["auth"][field] = value

        with pytest.raises(PermissionDeniedError):
            router.send_message(from_id, to_id, "route_envelope", envelope)


def test_contract_missing_auth_fields_are_rejected(tmp_path):
    router = _router_with_agents(tmp_path)

    for field in ["alg", "key_id", "nonce", "timestamp", "signature"]:
        envelope = _signed_route_envelope(nonce=f"missing-{field}")
        envelope["auth"].pop(field)

        with pytest.raises(InvalidRequestError):
            router.send_message("master", "execution", "route_envelope", envelope)


def test_contract_replayed_nonce_is_rejected(tmp_path):
    router = _router_with_agents(tmp_path)
    envelope = _signed_route_envelope(nonce="nonce-for-replay-test")

    router.send_message("master", "execution", "route_envelope", envelope)

    with pytest.raises(PermissionDeniedError):
        router.send_message("master", "execution", "route_envelope", envelope)


def test_contract_sender_without_registered_auth_material_is_rejected(tmp_path):
    router = Router(tmp_path / "state.json")
    router.create_domain("top_level_master_domain", owner_agent_id="master")
    router.register_agent("master", "top_level_master_domain", "master")
    router.register_agent(
        "execution",
        "top_level_master_domain",
        "execution",
        metadata={"dev_identity_keys": {_identity_key_id("execution"): _identity_secret("execution")}},
    )

    with pytest.raises(PermissionDeniedError):
        router.send_message("master", "execution", "route_envelope", _signed_route_envelope())


def test_contract_stale_and_future_timestamps_are_rejected(tmp_path):
    router = _router_with_agents(tmp_path)
    timestamps = [
        datetime.now(timezone.utc) - timedelta(seconds=301),
        datetime.now(timezone.utc) + timedelta(seconds=301),
    ]

    for index, timestamp in enumerate(timestamps):
        envelope = _signed_route_envelope(nonce=f"timestamp-window-{index}", timestamp=timestamp.isoformat())

        with pytest.raises(PermissionDeniedError):
            router.send_message("master", "execution", "route_envelope", envelope)


def test_contract_receiver_resolves_valid_protected_path_without_readme_or_attachment_inspection(tmp_path):
    shared_root = tmp_path / "mailbucket"
    message_folder = shared_root / "master__execution__20260428T000000Z__nonce"
    message_folder.mkdir(parents=True)
    (message_folder / "attachment.txt").write_text("receiver-only material", encoding="utf-8")
    envelope = _signed_route_envelope(path=make_dev_protected_path_token("msg-001"))

    resolved = resolve_route_envelope_path(
        envelope,
        shared_mailbucket_root=shared_root,
        resolver_material={"msg-001": message_folder.name},
    )

    assert resolved == message_folder.resolve()


def test_contract_receiver_rejects_malformed_protected_path(tmp_path):
    envelope = _signed_route_envelope(path="not-a-supported-protected-path")

    with pytest.raises(InvalidRequestError):
        resolve_route_envelope_path(
            envelope,
            shared_mailbucket_root=tmp_path / "mailbucket",
            resolver_material={"msg-001": "folder"},
        )


def test_contract_receiver_rejects_outside_traversal_and_absolute_paths(tmp_path):
    shared_root = tmp_path / "mailbucket"
    outside = tmp_path / "outside"
    cases = [
        {"traversal": "../outside"},
        {"absolute-outside": outside},
    ]

    for resolver_material in cases:
        token = next(iter(resolver_material))
        envelope = _signed_route_envelope(path=make_dev_protected_path_token(token))

        with pytest.raises(PermissionDeniedError):
            resolve_route_envelope_path(
                envelope,
                shared_mailbucket_root=shared_root,
                resolver_material=resolver_material,
            )


def test_contract_router_stores_only_opaque_path_not_resolved_path(tmp_path):
    router = _router_with_agents(tmp_path)
    shared_root = tmp_path / "mailbucket"
    resolved_path = shared_root / "master__execution__20260428T000000Z__nonce"
    opaque_path = make_dev_protected_path_token("msg-opaque")
    envelope = _signed_route_envelope(path=opaque_path)

    message = router.send_message("master", "execution", "route_envelope", envelope)
    received = router.receive_messages("execution")

    assert message["payload"]["path"] == opaque_path
    assert received[0]["payload"]["path"] == opaque_path
    assert str(resolved_path) not in str(message)
    assert str(resolved_path) not in str(received)


def test_contract_tampered_opaque_path_still_fails_auth(tmp_path):
    router = _router_with_agents(tmp_path)
    envelope = _signed_route_envelope(path=make_dev_protected_path_token("msg-original"))
    envelope["path"] = make_dev_protected_path_token("msg-tampered")

    with pytest.raises(PermissionDeniedError):
        router.send_message("master", "execution", "route_envelope", envelope)


def test_contract_router_owns_shared_mailbucket_root(tmp_path):
    router = _router_with_agents(tmp_path)

    assert hasattr(router, "shared_communication_root")
    assert router.shared_communication_root == (tmp_path / "mailbucket").resolve()


def test_contract_mailbucket_folder_requires_readme(tmp_path):
    with pytest.raises(InvalidRequestError):
        create_mailbucket_message(
            sender="master",
            receiver="execution",
            shared_mailbucket_root=tmp_path / "mailbucket",
            readme_text="",
            nonce="nonce",
        )


def test_contract_sender_creates_unique_mailbucket_folder_with_readme_and_attachment(tmp_path):
    source_attachment = tmp_path / "evidence.txt"
    source_attachment.write_text("raw evidence bytes", encoding="utf-8")

    message = create_mailbucket_message(
        sender="master",
        receiver="execution",
        shared_mailbucket_root=tmp_path / "mailbucket",
        readme_text="One-time message body.",
        attachments={"evidence/evidence.txt": source_attachment},
        nonce="nonce001",
    )
    folder = tmp_path / "mailbucket" / message["folder_name"]

    assert folder.is_dir()
    assert "master__execution__" in message["folder_name"]
    assert message["folder_name"].endswith("__nonce001")
    assert (folder / "README.md").is_file()
    assert (folder / "evidence" / "evidence.txt").is_file()
    assert message["protected_path"].startswith("aegis-dev-path-token:v1:")
    assert message["protected_path"] != str(folder)


def test_contract_mailbucket_protected_path_resolves_to_created_folder(tmp_path):
    message = create_mailbucket_message(
        sender="master",
        receiver="execution",
        shared_mailbucket_root=tmp_path / "mailbucket",
        readme_text="Receiver can read this directly once.",
        nonce="nonce002",
    )

    resolved = resolve_route_envelope_path(
        {"path": message["protected_path"]},
        shared_mailbucket_root=tmp_path / "mailbucket",
        resolver_material=message["resolver_material"],
    )

    assert resolved == (tmp_path / "mailbucket" / message["folder_name"]).resolve()
    assert (resolved / "README.md").read_text(encoding="utf-8") == "Receiver can read this directly once."


def test_contract_mailbucket_rejects_unsafe_folder_and_attachment_destinations(tmp_path):
    source_attachment = tmp_path / "evidence.txt"
    source_attachment.write_text("raw evidence bytes", encoding="utf-8")

    with pytest.raises(InvalidRequestError):
        create_mailbucket_message(
            sender="../master",
            receiver="execution",
            shared_mailbucket_root=tmp_path / "mailbucket",
            readme_text="body",
        )

    with pytest.raises(PermissionDeniedError):
        create_mailbucket_message(
            sender="master",
            receiver="execution",
            shared_mailbucket_root=tmp_path / "mailbucket",
            readme_text="body",
            attachments={"../escape.txt": source_attachment},
        )


def test_contract_router_envelope_carries_only_mailbucket_reference(tmp_path):
    router = _router_with_agents(tmp_path)
    mail = create_mailbucket_message(
        sender="master",
        receiver="execution",
        shared_mailbucket_root=router.shared_communication_root,
        readme_text="Large body lives in README.md, not router payload.",
        nonce="nonce003",
    )
    envelope = _signed_route_envelope(path=mail["protected_path"])

    message = router.send_message("master", "execution", "route_envelope", envelope)

    assert set(message["payload"]) == {"sender", "receiver", "path", "auth"}
    assert message["payload"]["path"] == mail["protected_path"]
    assert "Large body lives in README.md" not in str(message["payload"])


def test_contract_mailbucket_cleanup_exists_and_preserves_private_copies(tmp_path):
    router = _router_with_agents(tmp_path)
    old_timestamp = datetime.now(timezone.utc) - timedelta(minutes=30)
    fresh_timestamp = datetime.now(timezone.utc)
    valuable_source = tmp_path / "valuable-source.txt"
    valuable_source.write_text("valuable attachment", encoding="utf-8")
    old_mail = create_mailbucket_message(
        sender="master",
        receiver="execution",
        shared_mailbucket_root=router.shared_communication_root,
        readme_text="KEEP FOREVER because this is valuable.",
        attachments={"valuable.txt": valuable_source},
        nonce="oldnonce",
        timestamp=old_timestamp,
    )
    fresh_mail = create_mailbucket_message(
        sender="master",
        receiver="execution",
        shared_mailbucket_root=router.shared_communication_root,
        readme_text="Fresh one-time message.",
        nonce="freshnonce",
        timestamp=fresh_timestamp,
    )
    old_folder = router.shared_communication_root / old_mail["folder_name"]
    fresh_folder = router.shared_communication_root / fresh_mail["folder_name"]
    private_copy = tmp_path / "agent-private" / old_mail["folder_name"]
    shutil.copytree(old_folder, private_copy)
    old_mtime = datetime.now(timezone.utc).timestamp() - 3600
    fresh_mtime = datetime.now(timezone.utc).timestamp()
    os.utime(old_folder, (old_mtime, old_mtime))
    os.utime(fresh_folder, (fresh_mtime, fresh_mtime))

    result = router.cleanup_mailbucket(grace_period_seconds=300)

    assert str(old_folder.resolve()) in result["deleted"]
    assert any(item["path"] == str(fresh_folder.resolve()) for item in result["skipped"])
    assert not old_folder.exists()
    assert fresh_folder.exists()
    assert private_copy.exists()
    assert (private_copy / "README.md").read_text(encoding="utf-8") == "KEEP FOREVER because this is valuable."


def test_contract_mailbucket_cleanup_skips_files_and_is_deterministic(tmp_path):
    shared_root = tmp_path / "mailbucket"
    shared_root.mkdir()
    (shared_root / "not-a-message-folder.txt").write_text("not a folder", encoding="utf-8")
    old_mail_a = create_mailbucket_message(
        sender="master",
        receiver="execution",
        shared_mailbucket_root=shared_root,
        readme_text="old a",
        nonce="a",
    )
    old_mail_b = create_mailbucket_message(
        sender="master",
        receiver="execution",
        shared_mailbucket_root=shared_root,
        readme_text="old b",
        nonce="b",
    )
    old_mtime = datetime.now(timezone.utc).timestamp() - 3600
    for mail in [old_mail_b, old_mail_a]:
        folder = shared_root / mail["folder_name"]
        os.utime(folder, (old_mtime, old_mtime))

    result = Router(tmp_path / "state.json", shared_communication_root=shared_root).cleanup_mailbucket(
        grace_period_seconds=300
    )

    assert result["deleted"] == sorted(result["deleted"])
    assert len(result["deleted"]) == 2
    assert any(item["reason"] == "not_directory" for item in result["skipped"])
