from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    import rfc8785
except ImportError as exc:  # pragma: no cover - exercised by CLI preflight
    raise RuntimeError(
        "The independent reference model requires rfc8785==0.1.4."
    ) from exc


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_non_finite(token: str) -> None:
    raise ValueError(f"non-I-JSON number is forbidden: {token}")


def loads_json(raw: bytes, *, source: str = "<bytes>") -> Any:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"UTF-8 BOM is forbidden: {source}")
    return json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_non_finite,
    )


def load_json(path: str | Path) -> Any:
    return loads_json(Path(path).read_bytes(), source=str(path))


def jcs_bytes(value: Any) -> bytes:
    encoded = rfc8785.dumps(value)
    if not isinstance(encoded, bytes):
        raise TypeError("rfc8785.dumps did not return bytes")
    return encoded


def sha256_hex_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_hex(value: Any) -> str:
    return sha256_hex_bytes(jcs_bytes(value))


def content_id(value: Any) -> str:
    return f"sha256:{sha256_hex(value)}"


def with_self_hash(
    value: dict[str, Any], field: str, *, prefix: bool = False
) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result.pop(field, None)
    digest = sha256_hex(result)
    result[field] = f"sha256:{digest}" if prefix else digest
    return result


def verify_self_hash(
    value: dict[str, Any], field: str, *, prefix: bool = False
) -> bool:
    observed = value.get(field)
    if not isinstance(observed, str):
        return False
    unsigned = dict(value)
    unsigned.pop(field, None)
    digest = sha256_hex(unsigned)
    expected = f"sha256:{digest}" if prefix else digest
    return observed == expected


def jsonl_bytes(value: Any) -> bytes:
    return jcs_bytes(value) + b"\n"
