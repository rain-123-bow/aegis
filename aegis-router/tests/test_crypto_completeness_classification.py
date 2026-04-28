from __future__ import annotations

import inspect
import re

from aegis_router.core import DEV_HMAC_AUTH_ALG, ROUTE_ENVELOPE_REPLAY_WINDOW_SECONDS, Router
from aegis_router.mailbucket import create_mailbucket_message
from aegis_router.path_resolution import DEV_PATH_TOKEN_PREFIX, make_dev_protected_path_token


def test_contract_sender_auth_is_dev_hmac_not_public_key_signature():
    assert DEV_HMAC_AUTH_ALG == "aegis-dev-hmac-sha256"
    assert "ed25519" not in DEV_HMAC_AUTH_ALG.lower()
    assert "rsa" not in DEV_HMAC_AUTH_ALG.lower()


def test_contract_runtime_does_not_expose_production_public_key_crypto():
    import aegis_router.core as core
    import aegis_router.path_resolution as path_resolution

    source = inspect.getsource(core) + inspect.getsource(path_resolution)
    lowered = source.lower()

    assert re.search(r"\bed25519\b", lowered) is None
    assert re.search(r"\bx25519\b", lowered) is None
    assert re.search(r"\brsa\b", lowered) is None
    assert re.search(r"\bprivate_key\b", lowered) is None
    assert re.search(r"\bpublic_key\b", lowered) is None


def test_contract_path_protection_is_dev_token_not_encryption():
    token = make_dev_protected_path_token("message-folder")

    assert token == f"{DEV_PATH_TOKEN_PREFIX}message-folder"
    assert "encrypt" not in DEV_PATH_TOKEN_PREFIX
    assert "cipher" not in DEV_PATH_TOKEN_PREFIX


def test_contract_payload_content_is_plain_mailbucket_files(tmp_path):
    message = create_mailbucket_message(
        sender="master",
        receiver="execution",
        shared_mailbucket_root=tmp_path / "mailbucket",
        readme_text="Plain README content.",
        nonce="plain-content",
    )

    folder = tmp_path / "mailbucket" / message["folder_name"]

    assert (folder / "README.md").read_text(encoding="utf-8") == "Plain README content."


def test_contract_replay_nonce_exists_but_has_no_ttl_cleanup_api(tmp_path):
    router = Router(tmp_path / "state.json")

    assert ROUTE_ENVELOPE_REPLAY_WINDOW_SECONDS == 300
    assert not hasattr(router, "cleanup_replay_nonces")
