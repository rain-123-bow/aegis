from __future__ import annotations

import inspect

from aegis_router.core import DEV_HMAC_AUTH_ALG, REAL_ED25519_AUTH_ALG, ROUTE_ENVELOPE_REPLAY_WINDOW_SECONDS, Router
from aegis_router.mailbucket import create_mailbucket_message
from aegis_router.path_resolution import (
    DEV_PATH_TOKEN_PREFIX,
    REAL_RSA_OAEP_PATH_TOKEN_PREFIX,
    make_dev_protected_path_token,
    make_rsa_oaep_sha256_path_token,
)


def test_contract_dev_hmac_mode_remains_explicitly_development_scoped():
    assert DEV_HMAC_AUTH_ALG == "aegis-dev-hmac-sha256"
    assert "dev" in DEV_HMAC_AUTH_ALG


def test_contract_real_double_crypto_runtime_path_is_present():
    import aegis_router.core as core
    import aegis_router.path_resolution as path_resolution

    source = inspect.getsource(core) + inspect.getsource(path_resolution)
    lowered = source.lower()

    assert REAL_ED25519_AUTH_ALG == "aegis-ed25519-v1"
    assert REAL_RSA_OAEP_PATH_TOKEN_PREFIX == "aegis-rsa-oaep-sha256:v1:"
    assert "ed25519" in lowered
    assert "rsa" in lowered
    assert "oaep" in lowered


def test_contract_dev_path_token_mode_remains_available_for_local_tests():
    token = make_dev_protected_path_token("message-folder")

    assert token == f"{DEV_PATH_TOKEN_PREFIX}message-folder"
    assert callable(make_rsa_oaep_sha256_path_token)


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


def test_contract_full_key_lifecycle_remains_future_work(tmp_path):
    router = Router(tmp_path / "state.json")

    assert ROUTE_ENVELOPE_REPLAY_WINDOW_SECONDS == 300
    assert not hasattr(router, "cleanup_replay_nonces")
    assert not hasattr(router, "rotate_identity_keys")
    assert not hasattr(router, "rotate_path_keys")
