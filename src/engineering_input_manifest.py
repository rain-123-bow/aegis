from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from path_security import PathSecurityError, lexical_absolute, read_regular_file, same_path


ENGINEERING_INPUT_MANIFEST_SCHEMA = "aegis.engineering_input_manifest.v1"
ENGINEERING_INPUT_KINDS = frozenset({"REQUIREMENTS", "IMPLEMENTATION_PLAN"})

_HEX_16_PATTERN = re.compile(r"[0-9a-f]{32}")
_HEX_32_PATTERN = re.compile(r"[0-9a-f]{64}")
_TOP_LEVEL_FIELDS = {
    "schema",
    "project_id_hex",
    "created_at_utc",
    "documents",
}
_DOCUMENT_FIELDS = {"kind", "path", "size", "sha256"}


class EngineeringInputManifestError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ValidatedEngineeringInputManifest:
    path: Path
    sha256: str
    documents_sha256: str
    payload: dict[str, Any]


def validate_engineering_input_manifest(
    manifest_path: str | Path,
    *,
    project_root: str | Path,
    project_id_hex: str,
    expected_manifest_path: str | Path | None = None,
) -> ValidatedEngineeringInputManifest:
    project = lexical_absolute(project_root)
    path = lexical_absolute(manifest_path)
    if expected_manifest_path is not None and not same_path(
        path, expected_manifest_path
    ):
        raise EngineeringInputManifestError(
            "engineering input manifest does not use its immutable snapshot path"
        )
    if _HEX_16_PATTERN.fullmatch(project_id_hex) is None:
        raise ValueError("project_id_hex must contain 32 lowercase hex digits")
    raw_bytes, payload = _read_json(path)
    if not isinstance(payload, dict) or set(payload) != _TOP_LEVEL_FIELDS:
        raise EngineeringInputManifestError(
            "engineering input manifest has invalid top-level fields"
        )
    if payload["schema"] != ENGINEERING_INPUT_MANIFEST_SCHEMA:
        raise EngineeringInputManifestError(
            "engineering input manifest has an unsupported schema"
        )
    if payload["project_id_hex"] != project_id_hex:
        raise EngineeringInputManifestError(
            "engineering input manifest project identity does not match the run"
        )
    _parse_utc(payload["created_at_utc"])
    documents = payload["documents"]
    if not isinstance(documents, list) or not documents:
        raise EngineeringInputManifestError(
            "engineering input manifest has no documents"
        )

    seen_paths: set[Path] = set()
    seen_kinds: set[str] = set()
    for index, document in enumerate(documents):
        if not isinstance(document, dict) or set(document) != _DOCUMENT_FIELDS:
            raise EngineeringInputManifestError(
                f"engineering input document {index} has invalid fields"
            )
        kind = document["kind"]
        if kind not in ENGINEERING_INPUT_KINDS:
            raise EngineeringInputManifestError(
                f"engineering input document {index} has an invalid kind"
            )
        seen_kinds.add(str(kind))
        document_path = _validate_document(
            document,
            index=index,
            project_root=project,
        )
        if document_path in seen_paths:
            raise EngineeringInputManifestError(
                "engineering input manifest contains a duplicate document path"
            )
        seen_paths.add(document_path)
    missing = ENGINEERING_INPUT_KINDS - seen_kinds
    if missing:
        raise EngineeringInputManifestError(
            "engineering input manifest is missing required kinds: "
            + ", ".join(sorted(missing))
        )

    documents_bytes = json.dumps(
        documents,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return ValidatedEngineeringInputManifest(
        path=path,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        documents_sha256=hashlib.sha256(documents_bytes).hexdigest(),
        payload=payload,
    )


def _validate_document(
    document: dict[str, Any],
    *,
    index: int,
    project_root: Path,
) -> Path:
    raw_path = document["path"]
    if not isinstance(raw_path, str) or not raw_path:
        raise EngineeringInputManifestError(
            f"engineering input document {index} has an invalid path"
        )
    raw_document_path = Path(raw_path)
    if not raw_document_path.is_absolute():
        raise EngineeringInputManifestError(
            f"engineering input document {index} path is not absolute"
        )
    path = lexical_absolute(raw_document_path)
    try:
        path.relative_to(project_root)
    except ValueError as error:
        raise EngineeringInputManifestError(
            f"engineering input document {index} is outside the project root"
        ) from error
    try:
        content, _identity = read_regular_file(
            path,
            allowed_root=project_root,
            label=f"engineering input document {index}",
            max_bytes=256 * 1024 * 1024,
        )
    except PathSecurityError as error:
        raise EngineeringInputManifestError(
            f"cannot read engineering input document {index}: {error}"
        ) from error
    size = document["size"]
    sha256 = document["sha256"]
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise EngineeringInputManifestError(
            f"engineering input document {index} has an invalid size"
        )
    if _HEX_32_PATTERN.fullmatch(sha256) is None:
        raise EngineeringInputManifestError(
            f"engineering input document {index} has an invalid SHA-256"
        )
    if len(content) != size or hashlib.sha256(content).hexdigest() != sha256:
        raise EngineeringInputManifestError(
            f"engineering input document {index} content does not match its descriptor"
        )
    return path


def _read_json(path: Path) -> tuple[bytes, Any]:
    try:
        raw_bytes, _identity = read_regular_file(
            path,
            allowed_root=path.parent,
            label="engineering input manifest",
            max_bytes=16 * 1024 * 1024,
        )
        payload = json.loads(raw_bytes.decode("utf-8", errors="strict"))
    except (PathSecurityError, UnicodeError, json.JSONDecodeError) as error:
        raise EngineeringInputManifestError(
            f"cannot read engineering input manifest: {path}: {error}"
        ) from error
    return raw_bytes, payload


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise EngineeringInputManifestError(
            "engineering input manifest creation time is not UTC"
        )
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise EngineeringInputManifestError(
            "engineering input manifest creation time is invalid"
        ) from error
