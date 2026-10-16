"""Resolve a sealed witness identity without storing a machine-local path."""
from __future__ import annotations

import os
import re
from pathlib import Path


LEGACY_WITNESS_CONFIG_SCHEMA = "aegis.remote_seal_witness_config.v3"
WITNESS_CONFIG_SCHEMA = "aegis.remote_seal_witness_config.v4"


def resolve_witness_identity(config: dict[str, object]) -> tuple[Path, str]:
    schema = config.get("schema")
    if schema not in (LEGACY_WITNESS_CONFIG_SCHEMA, WITNESS_CONFIG_SCHEMA):
        raise ValueError("remote seal witness config has an unsupported schema")
    location_field = "path" if schema == LEGACY_WITNESS_CONFIG_SCHEMA else "path_env"
    identity = config.get("ssh_identity")
    if not isinstance(identity, dict) or set(identity) != {location_field, "sha256"}:
        raise ValueError("remote seal witness SSH identity descriptor is invalid")
    digest = identity["sha256"]
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("remote seal witness SSH identity digest is invalid")
    value = identity[location_field]
    if location_field == "path_env":
        if not isinstance(value, str) or re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", value) is None:
            raise ValueError("remote seal witness identity environment name is invalid")
        variable = value
        value = os.environ.get(variable)
        if not value:
            raise ValueError(f"set {variable} to the approved SSH identity's absolute path")
    if (
        not isinstance(value, str)
        or any(character in value for character in ("\x00", "\r", "\n"))
        or not Path(value).is_absolute()
    ):
        raise ValueError("remote seal witness SSH identity path must be absolute")
    # Do not resolve links here: the caller's stable-file lock rejects redirection.
    return Path(value), digest
