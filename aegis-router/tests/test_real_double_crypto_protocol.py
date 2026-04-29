from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

from aegis_router import Router, create_mailbucket_message, make_rsa_oaep_sha256_path_token, resolve_route_envelope_path
from aegis_router.core import REAL_ED25519_AUTH_ALG
from aegis_router.errors import InvalidRequestError, PermissionDeniedError

pytestmark = pytest.mark.contract

ROLES = ["master", "debate", "execution", "test", "final_review"]


def _public_pem(key) -> str:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def _private_pem(key) -> str:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")


def _signature_material(sender: str, receiver: str, path: str, nonce: str, timestamp: str) -> bytes:
    return "|".join([sender, receiver, path, nonce, timestamp]).encode("utf-8")


def _signed_envelope(
    *,
    sender: str,
    receiver: str,
    path: str,
    identity_private_key,
    key_id: str | None = None,
    nonce: str | None = None,
    timestamp: str | None = None,
) -> dict:
    nonce = nonce or f"{sender}-{receiver}-{datetime.now(timezone.utc).timestamp()}"
    timestamp = timestamp or datetime.now(timezone.utc).isoformat()
    signature = identity_private_key.sign(_signature_material(sender, receiver, path, nonce, timestamp))
    return {
        "sender": sender,
        "receiver": receiver,
        "path": path,
        "auth": {
            "alg": REAL_ED25519_AUTH_ALG,
            "key_id": key_id or f"{sender}-identity-ed25519-1",
            "nonce": nonce,
            "timestamp": timestamp,
            "signature": base64.b64encode(signature).decode("ascii"),
        },
    }


def _real_crypto_router(tmp_path):
    router = Router(tmp_path / "state.json")
    router.create_domain("top_level_master_domain", owner_agent_id="master")
    material = {}
    for role in ROLES:
        identity_private = ed25519.Ed25519PrivateKey.generate()
        path_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        identity_key_id = f"{role}-identity-ed25519-1"
        path_key_id = f"{role}-path-rsa-oaep-1"
        material[role] = {
            "identity_private": identity_private,
            "identity_key_id": identity_key_id,
            "path_private_pem": _private_pem(path_private),
            "path_public_pem": _public_pem(path_private),
            "path_key_id": path_key_id,
        }
        router.register_agent(
            role,
            "top_level_master_domain",
            role,
            metadata={
                "identity_public_keys": {
                    identity_key_id: {
                        "alg": "ed25519",
                        "public_key": _public_pem(identity_private),
                    }
                },
                "path_public_keys": {
                    path_key_id: {
                        "alg": "rsa-oaep-sha256",
                        "public_key": _public_pem(path_private),
                    }
                },
            },
        )
    return router, material


def _encrypted_path_for(tmp_path, material, receiver: str = "execution", path: str | Path | None = None) -> str:
    target = path or (tmp_path / "mailbucket" / "master__execution__20260429T000000Z__nonce")
    return make_rsa_oaep_sha256_path_token(
        target,
        receiver_path_key_id=material[receiver]["path_key_id"],
        receiver_public_key=material[receiver]["path_public_pem"],
    )


def test_real_ed25519_signed_route_envelope_is_accepted_on_valid_directed_edge(tmp_path):
    router, material = _real_crypto_router(tmp_path)
    path = _encrypted_path_for(tmp_path, material, "execution")
    envelope = _signed_envelope(
        sender="master",
        receiver="execution",
        path=path,
        identity_private_key=material["master"]["identity_private"],
    )

    message = router.send_message("master", "execution", "route_envelope", envelope)

    assert message["from_id"] == "master"
    assert message["to_id"] == "execution"
    assert message["payload"]["path"] == path


def test_forged_sender_signature_is_rejected(tmp_path):
    router, material = _real_crypto_router(tmp_path)
    path = _encrypted_path_for(tmp_path, material, "execution")
    envelope = _signed_envelope(
        sender="master",
        receiver="execution",
        path=path,
        identity_private_key=material["debate"]["identity_private"],
    )

    with pytest.raises(PermissionDeniedError):
        router.send_message("master", "execution", "route_envelope", envelope)


def test_missing_registered_sender_public_key_is_rejected(tmp_path):
    router, material = _real_crypto_router(tmp_path)
    data = router._load()
    data["agents"]["master"]["metadata"]["identity_public_keys"] = {}
    router._save(data)
    envelope = _signed_envelope(
        sender="master",
        receiver="execution",
        path=_encrypted_path_for(tmp_path, material, "execution"),
        identity_private_key=material["master"]["identity_private"],
    )

    with pytest.raises(PermissionDeniedError):
        router.send_message("master", "execution", "route_envelope", envelope)


def test_wrong_auth_key_id_is_rejected(tmp_path):
    router, material = _real_crypto_router(tmp_path)
    envelope = _signed_envelope(
        sender="master",
        receiver="execution",
        path=_encrypted_path_for(tmp_path, material, "execution"),
        identity_private_key=material["master"]["identity_private"],
        key_id="missing-key",
    )

    with pytest.raises(PermissionDeniedError):
        router.send_message("master", "execution", "route_envelope", envelope)


@pytest.mark.parametrize(
    ("field", "value", "from_id", "to_id"),
    [
        ("sender", "debate", "debate", "execution"),
        ("receiver", "debate", "master", "debate"),
        ("path", "aegis-rsa-oaep-sha256:v1:execution-path-rsa-oaep-1:tampered", "master", "execution"),
        ("nonce", "tampered-nonce", "master", "execution"),
        ("timestamp", (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(), "master", "execution"),
    ],
)
def test_modifying_signed_envelope_fields_invalidates_signature(tmp_path, field, value, from_id, to_id):
    router, material = _real_crypto_router(tmp_path)
    envelope = _signed_envelope(
        sender="master",
        receiver="execution",
        path=_encrypted_path_for(tmp_path, material, "execution"),
        identity_private_key=material["master"]["identity_private"],
        nonce=f"mutation-{field}",
    )
    if field in {"sender", "receiver", "path"}:
        envelope[field] = value
    else:
        envelope["auth"][field] = value

    with pytest.raises(PermissionDeniedError):
        router.send_message(from_id, to_id, "route_envelope", envelope)


def test_replayed_nonce_is_rejected_for_real_ed25519_auth(tmp_path):
    router, material = _real_crypto_router(tmp_path)
    envelope = _signed_envelope(
        sender="master",
        receiver="execution",
        path=_encrypted_path_for(tmp_path, material, "execution"),
        identity_private_key=material["master"]["identity_private"],
        nonce="real-replay-nonce",
    )

    router.send_message("master", "execution", "route_envelope", envelope)

    with pytest.raises(PermissionDeniedError):
        router.send_message("master", "execution", "route_envelope", envelope)


def test_stale_timestamp_is_rejected_for_real_ed25519_auth(tmp_path):
    router, material = _real_crypto_router(tmp_path)
    envelope = _signed_envelope(
        sender="master",
        receiver="execution",
        path=_encrypted_path_for(tmp_path, material, "execution"),
        identity_private_key=material["master"]["identity_private"],
        timestamp=(datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat(),
    )

    with pytest.raises(PermissionDeniedError):
        router.send_message("master", "execution", "route_envelope", envelope)


def test_receiver_can_decrypt_real_encrypted_path_with_correct_private_key(tmp_path):
    router, material = _real_crypto_router(tmp_path)
    mail = create_mailbucket_message(
        sender="master",
        receiver="execution",
        shared_mailbucket_root=router.shared_communication_root,
        readme_text="receiver body",
        nonce="realcrypto001",
    )
    encrypted_path = _encrypted_path_for(tmp_path, material, "execution", mail["folder_path"])

    resolved = resolve_route_envelope_path(
        {"path": encrypted_path},
        shared_mailbucket_root=router.shared_communication_root,
        receiver_private_path_keys={material["execution"]["path_key_id"]: material["execution"]["path_private_pem"]},
    )

    assert resolved == Path(mail["folder_path"]).resolve()


def test_wrong_receiver_private_key_cannot_decrypt_path(tmp_path):
    router, material = _real_crypto_router(tmp_path)
    encrypted_path = _encrypted_path_for(tmp_path, material, "execution")

    with pytest.raises(PermissionDeniedError):
        resolve_route_envelope_path(
            {"path": encrypted_path},
            shared_mailbucket_root=router.shared_communication_root,
            receiver_private_path_keys={material["execution"]["path_key_id"]: material["debate"]["path_private_pem"]},
        )


def test_tampered_path_ciphertext_cannot_decrypt(tmp_path):
    router, material = _real_crypto_router(tmp_path)
    encrypted_path = _encrypted_path_for(tmp_path, material, "execution")
    prefix, ciphertext = encrypted_path.rsplit(":", 1)
    tampered = f"{prefix}:{'A' if ciphertext[0] != 'A' else 'B'}{ciphertext[1:]}"

    with pytest.raises(PermissionDeniedError):
        resolve_route_envelope_path(
            {"path": tampered},
            shared_mailbucket_root=router.shared_communication_root,
            receiver_private_path_keys={material["execution"]["path_key_id"]: material["execution"]["path_private_pem"]},
        )


def test_decrypted_outside_root_path_is_rejected(tmp_path):
    router, material = _real_crypto_router(tmp_path)
    encrypted_path = _encrypted_path_for(tmp_path, material, "execution", tmp_path / "outside")

    with pytest.raises(PermissionDeniedError):
        resolve_route_envelope_path(
            {"path": encrypted_path},
            shared_mailbucket_root=router.shared_communication_root,
            receiver_private_path_keys={material["execution"]["path_key_id"]: material["execution"]["path_private_pem"]},
        )


def test_decrypted_traversal_path_is_rejected(tmp_path):
    router, material = _real_crypto_router(tmp_path)
    encrypted_path = _encrypted_path_for(tmp_path, material, "execution", "../outside")

    with pytest.raises(PermissionDeniedError):
        resolve_route_envelope_path(
            {"path": encrypted_path},
            shared_mailbucket_root=router.shared_communication_root,
            receiver_private_path_keys={material["execution"]["path_key_id"]: material["execution"]["path_private_pem"]},
        )


def test_router_stored_and_forwarded_envelope_does_not_contain_decrypted_path(tmp_path):
    router, material = _real_crypto_router(tmp_path)
    decrypted_path = router.shared_communication_root / "master__execution__20260429T000000Z__nonce"
    encrypted_path = _encrypted_path_for(tmp_path, material, "execution", decrypted_path)
    envelope = _signed_envelope(
        sender="master",
        receiver="execution",
        path=encrypted_path,
        identity_private_key=material["master"]["identity_private"],
    )

    message = router.send_message("master", "execution", "route_envelope", envelope)
    received = router.receive_messages("execution")

    assert message["payload"]["path"] == encrypted_path
    assert received[0]["payload"]["path"] == encrypted_path
    assert str(decrypted_path) not in str(message)
    assert str(decrypted_path) not in str(received)


def test_router_state_has_no_receiver_private_path_key(tmp_path):
    router, material = _real_crypto_router(tmp_path)

    state_text = str(router._load())

    assert material["execution"]["path_private_pem"] not in state_text
    assert "PRIVATE KEY" not in state_text


def test_router_does_not_read_readme_or_attachments_for_crypto_success(tmp_path):
    router, material = _real_crypto_router(tmp_path)
    attachment = tmp_path / "evidence.txt"
    attachment.write_text("evidence bytes", encoding="utf-8")
    mail = create_mailbucket_message(
        sender="master",
        receiver="execution",
        shared_mailbucket_root=router.shared_communication_root,
        readme_text="This content is not router truth.",
        attachments={"evidence.txt": attachment},
        nonce="realcrypto002",
    )
    encrypted_path = _encrypted_path_for(tmp_path, material, "execution", mail["folder_path"])
    envelope = _signed_envelope(
        sender="master",
        receiver="execution",
        path=encrypted_path,
        identity_private_key=material["master"]["identity_private"],
    )

    message = router.send_message("master", "execution", "route_envelope", envelope)

    assert "This content is not router truth" not in str(message)
    assert "evidence bytes" not in str(message)


def test_strict_topology_rejects_invalid_edge_even_with_valid_crypto(tmp_path):
    router, material = _real_crypto_router(tmp_path)
    envelope = _signed_envelope(
        sender="master",
        receiver="test",
        path=_encrypted_path_for(tmp_path, material, "test"),
        identity_private_key=material["master"]["identity_private"],
    )

    with pytest.raises(PermissionDeniedError):
        router.send_message("master", "test", "route_envelope", envelope)


def test_valid_crypto_does_not_imply_payload_truth_or_causal_admission(tmp_path):
    router, material = _real_crypto_router(tmp_path)
    envelope = _signed_envelope(
        sender="master",
        receiver="execution",
        path=_encrypted_path_for(tmp_path, material, "execution"),
        identity_private_key=material["master"]["identity_private"],
    )

    message = router.send_message("master", "execution", "route_envelope", envelope)
    state = router._load()

    assert message["status"] == "pending"
    assert "archive" not in state
    assert "knowledge" not in state
    assert "causal" not in state
