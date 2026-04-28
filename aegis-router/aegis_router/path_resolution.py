from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .errors import InvalidRequestError, PermissionDeniedError

DEV_PATH_TOKEN_PREFIX = "aegis-dev-path-token:v1:"


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


def resolve_route_envelope_path(
    payload: dict[str, Any],
    *,
    shared_mailbucket_root: str | Path,
    resolver_material: Mapping[str, str | Path],
) -> Path:
    """Resolve an opaque route-envelope path using receiver-local material.

    The resolver validates filesystem safety only. It does not inspect README.md,
    attachments, or business payload content.
    """
    protected_path = payload.get("path")
    if not isinstance(protected_path, str) or not protected_path:
        raise InvalidRequestError("route_envelope path must be a non-empty opaque string")
    if not protected_path.startswith(DEV_PATH_TOKEN_PREFIX):
        raise InvalidRequestError("route_envelope path is not a supported dev protected path token")

    token = protected_path.removeprefix(DEV_PATH_TOKEN_PREFIX)
    if not token or "/" in token or "\\" in token or token in {".", ".."}:
        raise InvalidRequestError("route_envelope path token is malformed")
    if token not in resolver_material:
        raise InvalidRequestError("route_envelope path token cannot be resolved by receiver material")

    candidate_value = resolver_material[token]
    if not isinstance(candidate_value, (str, Path)) or not str(candidate_value):
        raise InvalidRequestError("resolved route_envelope path must be a non-empty filesystem path")

    shared_root = Path(shared_mailbucket_root).resolve()
    candidate_path = Path(candidate_value)
    if ".." in candidate_path.parts:
        raise PermissionDeniedError("resolved route_envelope path must not contain traversal")

    resolved = (candidate_path if candidate_path.is_absolute() else shared_root / candidate_path).resolve()
    if resolved != shared_root and shared_root not in resolved.parents:
        raise PermissionDeniedError("resolved route_envelope path is outside the shared mailbucket root")
    return resolved
