from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .errors import InvalidRequestError, PermissionDeniedError

DEV_PATH_TOKEN_PREFIX = "aegis-dev-path-token:v1:"
REAL_RSA_OAEP_PATH_TOKEN_PREFIX = "aegis-rsa-oaep-sha256:v1:"


def make_dev_protected_path_token(token: str) -> str:
    """Create a local development path token.

    This is a receiver-side test abstraction, not production encryption.
    The router must treat the returned string as opaque.
    """
    if not isinstance(token, str) or not token:
        raise InvalidRequestError("path token must be a non-empty string")
    if "/" in token or "\\" in token or token in {".", ".."}:
        raise InvalidRequestError("path token must not contain path separators")
    return f"{DEV_PATH_TOKEN_PREFIX}{token}"


def _load_rsa_public_key(public_key_text: str) -> rsa.RSAPublicKey:
    if not isinstance(public_key_text, str) or not public_key_text:
        raise InvalidRequestError("receiver path public key must be a non-empty string")
    try:
        loaded = serialization.load_pem_public_key(public_key_text.encode("utf-8"))
    except ValueError as exc:
        raise InvalidRequestError("receiver path public key is malformed") from exc
    if not isinstance(loaded, rsa.RSAPublicKey):
        raise InvalidRequestError("receiver path public key must be RSA")
    return loaded


def _load_rsa_private_key(private_key_text: str) -> rsa.RSAPrivateKey:
    if not isinstance(private_key_text, str) or not private_key_text:
        raise InvalidRequestError("receiver path private key must be a non-empty string")
    try:
        loaded = serialization.load_pem_private_key(private_key_text.encode("utf-8"), password=None)
    except ValueError as exc:
        raise InvalidRequestError("receiver path private key is malformed") from exc
    if not isinstance(loaded, rsa.RSAPrivateKey):
        raise InvalidRequestError("receiver path private key must be RSA")
    return loaded


def make_rsa_oaep_sha256_path_token(
    path: str | Path,
    *,
    receiver_path_key_id: str,
    receiver_public_key: str,
) -> str:
    """Encrypt a mailbucket path for receiver-side resolution.

    This helper encrypts only the path reference. It does not encrypt README.md,
    attachments, or business payload content.
    """
    if not isinstance(receiver_path_key_id, str) or not receiver_path_key_id:
        raise InvalidRequestError("receiver_path_key_id must be a non-empty string")
    if ":" in receiver_path_key_id:
        raise InvalidRequestError("receiver_path_key_id must not contain ':'")
    if not isinstance(path, (str, Path)) or not str(path):
        raise InvalidRequestError("path must be a non-empty filesystem path")

    public_key = _load_rsa_public_key(receiver_public_key)
    ciphertext = public_key.encrypt(
        str(path).encode("utf-8"),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    encoded = base64.b64encode(ciphertext).decode("ascii")
    return f"{REAL_RSA_OAEP_PATH_TOKEN_PREFIX}{receiver_path_key_id}:{encoded}"


def _resolve_decrypted_path(shared_mailbucket_root: str | Path, decrypted_path: str) -> Path:
    if not isinstance(decrypted_path, str) or not decrypted_path:
        raise InvalidRequestError("decrypted route_envelope path must be a non-empty filesystem path")

    shared_root = Path(shared_mailbucket_root).resolve()
    candidate_path = Path(decrypted_path)
    if ".." in candidate_path.parts:
        raise PermissionDeniedError("resolved route_envelope path must not contain traversal")

    resolved = (candidate_path if candidate_path.is_absolute() else shared_root / candidate_path).resolve()
    if resolved != shared_root and shared_root not in resolved.parents:
        raise PermissionDeniedError("resolved route_envelope path is outside the shared mailbucket root")
    return resolved


def _resolve_dev_path_token(
    protected_path: str,
    *,
    shared_mailbucket_root: str | Path,
    resolver_material: Mapping[str, str | Path] | None,
) -> Path:
    if resolver_material is None:
        raise InvalidRequestError("dev path token resolver_material is required")

    token = protected_path.removeprefix(DEV_PATH_TOKEN_PREFIX)
    if not token or "/" in token or "\\" in token or token in {".", ".."}:
        raise InvalidRequestError("route_envelope path token is malformed")
    if token not in resolver_material:
        raise InvalidRequestError("route_envelope path token cannot be resolved by receiver material")

    candidate_value = resolver_material[token]
    if not isinstance(candidate_value, (str, Path)) or not str(candidate_value):
        raise InvalidRequestError("resolved route_envelope path must be a non-empty filesystem path")
    return _resolve_decrypted_path(shared_mailbucket_root, str(candidate_value))


def _resolve_real_rsa_oaep_path_token(
    protected_path: str,
    *,
    shared_mailbucket_root: str | Path,
    receiver_private_path_keys: Mapping[str, str] | None,
) -> Path:
    if receiver_private_path_keys is None:
        raise InvalidRequestError("receiver_private_path_keys is required for encrypted path resolution")

    remainder = protected_path.removeprefix(REAL_RSA_OAEP_PATH_TOKEN_PREFIX)
    parts = remainder.split(":", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise InvalidRequestError("route_envelope encrypted path token is malformed")
    key_id, ciphertext_text = parts
    private_key_text = receiver_private_path_keys.get(key_id)
    if not isinstance(private_key_text, str) or not private_key_text:
        raise PermissionDeniedError("receiver private path key is not available")

    try:
        ciphertext = base64.b64decode(ciphertext_text, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise InvalidRequestError("route_envelope encrypted path ciphertext must be base64") from exc

    private_key = _load_rsa_private_key(private_key_text)
    try:
        decrypted = private_key.decrypt(
            ciphertext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
    except ValueError as exc:
        raise PermissionDeniedError("route_envelope encrypted path decryption failed") from exc

    return _resolve_decrypted_path(shared_mailbucket_root, decrypted.decode("utf-8"))


def resolve_route_envelope_path(
    payload: dict[str, Any],
    *,
    shared_mailbucket_root: str | Path,
    resolver_material: Mapping[str, str | Path] | None = None,
    receiver_private_path_keys: Mapping[str, str] | None = None,
) -> Path:
    """Resolve an opaque route-envelope path using receiver-local material.

    The resolver validates filesystem safety only. It does not inspect README.md,
    attachments, or business payload content.
    """
    protected_path = payload.get("path")
    if not isinstance(protected_path, str) or not protected_path:
        raise InvalidRequestError("route_envelope path must be a non-empty opaque string")

    if protected_path.startswith(DEV_PATH_TOKEN_PREFIX):
        return _resolve_dev_path_token(
            protected_path,
            shared_mailbucket_root=shared_mailbucket_root,
            resolver_material=resolver_material,
        )
    if protected_path.startswith(REAL_RSA_OAEP_PATH_TOKEN_PREFIX):
        return _resolve_real_rsa_oaep_path_token(
            protected_path,
            shared_mailbucket_root=shared_mailbucket_root,
            receiver_private_path_keys=receiver_private_path_keys,
        )
    raise InvalidRequestError("route_envelope path is not a supported protected path token")
