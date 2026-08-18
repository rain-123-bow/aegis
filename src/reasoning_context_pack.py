from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from path_security import PathSecurityError, is_within, lexical_absolute, read_regular_file, same_path


REASONING_CONTEXT_PACK_SCHEMA = "aegis.reasoning_context_pack.v1"
MAX_CONTEXT_PACK_BYTES = 16 * 1024 * 1024
MAX_EVIDENCE_BYTES = 256 * 1024 * 1024

_HEX_16_PATTERN = re.compile(r"[0-9a-f]{32}")
_HEX_32_PATTERN = re.compile(r"[0-9a-f]{64}")
_SEAL_PATTERN = re.compile(r"ASC1:[0-9A-Fa-f]{64}")
_TOP_LEVEL_FIELDS = {
    "schema",
    "project_id_hex",
    "task_id",
    "agent_role",
    "query",
    "generated_at_utc",
    "bindings",
    "ledger",
    "retrieval",
    "coverage",
    "items",
    "cause_items",
    "edges",
    "warnings",
    "required_artifact_paths",
    "evidence_index",
}
_BINDING_FIELDS = {"project_seal", "engineering_documents_sha256"}
_LEDGER_FIELDS = {"revision", "snapshot_sha256"}
_RETRIEVAL_FIELDS = {"mode", "embedding_source", "scope", "limit", "include_causes"}
_COVERAGE_FIELDS = {
    "requirements",
    "implementation_plan",
    "runtime_scope",
    "code_causality",
    "known_refutations",
    "environment_facts",
    "pending_warnings",
}
_ITEM_FIELDS = {
    "id",
    "project_id",
    "type",
    "status",
    "scope",
    "content",
    "artifact_path",
    "source",
    "evidence_path",
    "confidence",
    "level",
    "version",
    "metadata",
    "created_by",
    "created_at",
    "updated_at",
}
_EDGE_FIELDS = {
    "id",
    "project_id",
    "from_id",
    "to_id",
    "relation",
    "status",
    "reason",
    "confidence",
    "metadata",
    "created_by",
    "created_at",
}
_DESCRIPTOR_FIELDS = {"path", "size", "sha256"}
_ITEM_STATUSES = {"active", "stale", "invalid", "superseded"}


class ReasoningContextPackError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ValidatedReasoningContextPack:
    path: Path
    sha256: str
    task_id: str
    agent_role: str
    ledger_revision: int
    ledger_snapshot_sha256: str
    payload: dict[str, Any]


def validate_reasoning_context_pack(
    context_pack_path: str | Path,
    *,
    project_root: str | Path,
    artifact_root: str | Path,
    project_id_hex: str,
    project_seal: str,
    engineering_documents_sha256: str,
    expected_path: str | Path | None = None,
) -> ValidatedReasoningContextPack:
    project = lexical_absolute(project_root)
    artifacts = lexical_absolute(artifact_root)
    path = lexical_absolute(context_pack_path)
    if expected_path is not None and not same_path(path, expected_path):
        raise ReasoningContextPackError("reasoning context pack path is not the immutable snapshot path")
    try:
        raw, _identity = read_regular_file(
            path,
            allowed_root=Path(path.anchor),
            label="reasoning context pack",
            max_bytes=MAX_CONTEXT_PACK_BYTES,
        )
    except PathSecurityError as error:
        raise ReasoningContextPackError(str(error)) from error
    try:
        payload = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ReasoningContextPackError("reasoning context pack is invalid JSON") from error
    if not isinstance(payload, dict) or set(payload) != _TOP_LEVEL_FIELDS:
        raise ReasoningContextPackError("reasoning context pack has invalid fields")
    if payload["schema"] != REASONING_CONTEXT_PACK_SCHEMA:
        raise ReasoningContextPackError("reasoning context pack has an unsupported schema")
    if _HEX_16_PATTERN.fullmatch(project_id_hex) is None:
        raise ValueError("project_id_hex must contain 32 lowercase hex digits")
    if payload["project_id_hex"] != project_id_hex:
        raise ReasoningContextPackError("reasoning context pack project identity does not match")
    if _SEAL_PATTERN.fullmatch(project_seal) is None:
        raise ValueError("project_seal is invalid")
    _require_sha256(engineering_documents_sha256, "engineering documents")

    task_id = _nonempty_string(payload["task_id"], "task ID", max_length=256)
    agent_role = _nonempty_string(payload["agent_role"], "agent role", max_length=128)
    _nonempty_string(payload["query"], "query", max_length=64 * 1024)
    _parse_utc(payload["generated_at_utc"], "generation time")

    bindings = payload["bindings"]
    if not isinstance(bindings, dict) or set(bindings) != _BINDING_FIELDS:
        raise ReasoningContextPackError("reasoning context pack has invalid bindings")
    if bindings["project_seal"] != project_seal:
        raise ReasoningContextPackError("reasoning context pack project seal does not match")
    if bindings["engineering_documents_sha256"] != engineering_documents_sha256:
        raise ReasoningContextPackError("reasoning context pack engineering inputs do not match")

    ledger = payload["ledger"]
    if not isinstance(ledger, dict) or set(ledger) != _LEDGER_FIELDS:
        raise ReasoningContextPackError("reasoning context pack has invalid ledger identity")
    revision = ledger["revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ReasoningContextPackError("reasoning context pack has an invalid ledger revision")
    ledger_snapshot_sha256 = _require_sha256(ledger["snapshot_sha256"], "ledger snapshot")
    _validate_retrieval(payload["retrieval"])
    _validate_coverage(payload["coverage"])

    required_paths = _validate_required_paths(payload["required_artifact_paths"])
    evidence_paths = _validate_evidence_index(
        payload["evidence_index"],
        project_root=project,
        artifact_root=artifacts,
    )
    for required_path in required_paths:
        expected_artifact = lexical_absolute(project / Path(required_path))
        if not any(same_path(expected_artifact, evidence_path) for evidence_path in evidence_paths):
            raise ReasoningContextPackError(
                f"reasoning context pack required artifact has no evidence descriptor: {required_path}"
            )

    item_ids: set[str] = set()
    non_active_warnings: list[str] = []
    _validate_items(
        payload["items"],
        label="item",
        project_id_hex=project_id_hex,
        required_paths=required_paths,
        item_ids=item_ids,
        non_active_warnings=non_active_warnings,
    )
    _validate_items(
        payload["cause_items"],
        label="cause item",
        project_id_hex=project_id_hex,
        required_paths=required_paths,
        item_ids=item_ids,
        non_active_warnings=non_active_warnings,
    )
    if not item_ids:
        raise ReasoningContextPackError("reasoning context pack contains no ledger items")
    _validate_edges(payload["edges"], project_id_hex=project_id_hex, item_ids=item_ids)
    warnings = _string_list(payload["warnings"], "warnings", max_items=10_000)
    missing_warnings = [warning for warning in non_active_warnings if warning not in warnings]
    if missing_warnings:
        raise ReasoningContextPackError("reasoning context pack omits stale or invalid warnings")

    return ValidatedReasoningContextPack(
        path=path,
        sha256=hashlib.sha256(raw).hexdigest(),
        task_id=task_id,
        agent_role=agent_role,
        ledger_revision=revision,
        ledger_snapshot_sha256=ledger_snapshot_sha256,
        payload=payload,
    )


def _validate_retrieval(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != _RETRIEVAL_FIELDS:
        raise ReasoningContextPackError("reasoning context pack has invalid retrieval metadata")
    _nonempty_string(value["mode"], "retrieval mode", max_length=128)
    _nonempty_string(value["embedding_source"], "embedding source", max_length=256)
    if not isinstance(value["scope"], dict):
        raise ReasoningContextPackError("reasoning context pack retrieval scope must be an object")
    limit = value["limit"]
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10_000:
        raise ReasoningContextPackError("reasoning context pack retrieval limit is invalid")
    if not isinstance(value["include_causes"], bool):
        raise ReasoningContextPackError("reasoning context pack cause setting is invalid")


def _validate_coverage(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != _COVERAGE_FIELDS:
        raise ReasoningContextPackError("reasoning context pack has invalid coverage declaration")
    missing = sorted(field for field in _COVERAGE_FIELDS if value[field] is not True)
    if missing:
        raise ReasoningContextPackError(
            "reasoning context pack coverage is incomplete: " + ", ".join(missing)
        )


def _validate_required_paths(value: Any) -> set[str]:
    paths = _string_list(value, "required artifact paths", max_items=10_000)
    if not paths:
        raise ReasoningContextPackError("reasoning context pack has no required artifacts")
    normalized: set[str] = set()
    for raw_path in paths:
        path = PurePosixPath(raw_path)
        if (
            raw_path.startswith("/")
            or "\\" in raw_path
            or ":" in raw_path
            or any(part in {"", ".", ".."} for part in path.parts)
            or path.as_posix() != raw_path
        ):
            raise ReasoningContextPackError("reasoning context pack has a non-normalized artifact path")
        if raw_path in normalized:
            raise ReasoningContextPackError("reasoning context pack has duplicate artifact paths")
        normalized.add(raw_path)
    return normalized


def _validate_evidence_index(
    value: Any,
    *,
    project_root: Path,
    artifact_root: Path,
) -> list[Path]:
    if not isinstance(value, list) or not value or len(value) > 10_000:
        raise ReasoningContextPackError("reasoning context pack has an invalid evidence index")
    paths: list[Path] = []
    for index, descriptor in enumerate(value):
        if not isinstance(descriptor, dict) or set(descriptor) != _DESCRIPTOR_FIELDS:
            raise ReasoningContextPackError(f"context evidence {index} has invalid fields")
        raw_path = descriptor["path"]
        if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
            raise ReasoningContextPackError(f"context evidence {index} path is not absolute")
        path = lexical_absolute(raw_path)
        containing_root = next(
            (root for root in (project_root, artifact_root) if is_within(path, root)),
            None,
        )
        if containing_root is None:
            raise ReasoningContextPackError(f"context evidence {index} is outside allowed roots")
        try:
            content, _identity = read_regular_file(
                path,
                allowed_root=containing_root,
                label=f"context evidence {index}",
                max_bytes=MAX_EVIDENCE_BYTES,
            )
        except PathSecurityError as error:
            raise ReasoningContextPackError(str(error)) from error
        size = descriptor["size"]
        digest = descriptor["sha256"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ReasoningContextPackError(f"context evidence {index} has an invalid size")
        _require_sha256(digest, f"context evidence {index}")
        if len(content) != size or hashlib.sha256(content).hexdigest() != digest:
            raise ReasoningContextPackError(f"context evidence {index} does not match its descriptor")
        if any(same_path(path, existing) for existing in paths):
            raise ReasoningContextPackError("reasoning context pack has duplicate evidence paths")
        paths.append(path)
    return paths


def _validate_items(
    value: Any,
    *,
    label: str,
    project_id_hex: str,
    required_paths: set[str],
    item_ids: set[str],
    non_active_warnings: list[str],
) -> None:
    if not isinstance(value, list) or len(value) > 10_000:
        raise ReasoningContextPackError(f"reasoning context pack {label} list is invalid")
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != _ITEM_FIELDS:
            raise ReasoningContextPackError(f"reasoning context pack {label} {index} has invalid fields")
        item_id = _nonempty_string(item["id"], f"{label} ID", max_length=512)
        if item_id in item_ids:
            raise ReasoningContextPackError("reasoning context pack has duplicate item IDs")
        item_ids.add(item_id)
        if item["project_id"] != project_id_hex:
            raise ReasoningContextPackError(f"reasoning context pack {label} project identity differs")
        _nonempty_string(item["type"], f"{label} type", max_length=128)
        status = item["status"]
        if status not in _ITEM_STATUSES:
            raise ReasoningContextPackError(f"reasoning context pack {label} status is invalid")
        if not isinstance(item["scope"], dict) or not isinstance(item["metadata"], dict):
            raise ReasoningContextPackError(f"reasoning context pack {label} metadata is invalid")
        _nonempty_string(item["content"], f"{label} content", max_length=2 * 1024 * 1024)
        for field in ("artifact_path", "evidence_path"):
            path = item[field]
            if path is not None and path not in required_paths:
                raise ReasoningContextPackError(
                    f"reasoning context pack {label} {field} is not in required artifacts"
                )
        if item["source"] is not None and not isinstance(item["source"], str):
            raise ReasoningContextPackError(f"reasoning context pack {label} source is invalid")
        confidence = item["confidence"]
        if confidence is not None and (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 1
        ):
            raise ReasoningContextPackError(f"reasoning context pack {label} confidence is invalid")
        for field in ("level", "version"):
            number = item[field]
            minimum = 0 if field == "level" else 1
            if isinstance(number, bool) or not isinstance(number, int) or number < minimum:
                raise ReasoningContextPackError(f"reasoning context pack {label} {field} is invalid")
        _nonempty_string(item["created_by"], f"{label} creator", max_length=256)
        _parse_utc(item["created_at"], f"{label} creation time")
        _parse_utc(item["updated_at"], f"{label} update time")
        if status != "active":
            non_active_warnings.append(f"{label} {item_id} status is {status}")


def _validate_edges(value: Any, *, project_id_hex: str, item_ids: set[str]) -> None:
    if not isinstance(value, list) or len(value) > 50_000:
        raise ReasoningContextPackError("reasoning context pack edge list is invalid")
    edge_ids: set[int] = set()
    for index, edge in enumerate(value):
        if not isinstance(edge, dict) or set(edge) != _EDGE_FIELDS:
            raise ReasoningContextPackError(f"reasoning context pack edge {index} has invalid fields")
        edge_id = edge["id"]
        if isinstance(edge_id, bool) or not isinstance(edge_id, int) or edge_id < 0 or edge_id in edge_ids:
            raise ReasoningContextPackError("reasoning context pack edge ID is invalid or duplicate")
        edge_ids.add(edge_id)
        if edge["project_id"] != project_id_hex:
            raise ReasoningContextPackError("reasoning context pack edge project identity differs")
        if edge["from_id"] not in item_ids or edge["to_id"] not in item_ids:
            raise ReasoningContextPackError("reasoning context pack edge endpoint is missing")
        _nonempty_string(edge["relation"], "edge relation", max_length=128)
        _nonempty_string(edge["status"], "edge status", max_length=128)
        _nonempty_string(edge["reason"], "edge reason", max_length=64 * 1024)
        if not isinstance(edge["metadata"], dict):
            raise ReasoningContextPackError("reasoning context pack edge metadata is invalid")
        confidence = edge["confidence"]
        if confidence is not None and (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 1
        ):
            raise ReasoningContextPackError("reasoning context pack edge confidence is invalid")
        _nonempty_string(edge["created_by"], "edge creator", max_length=256)
        _parse_utc(edge["created_at"], "edge creation time")


def _string_list(value: Any, label: str, *, max_items: int) -> list[str]:
    if not isinstance(value, list) or len(value) > max_items:
        raise ReasoningContextPackError(f"reasoning context pack {label} is invalid")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ReasoningContextPackError(f"reasoning context pack {label} contains an invalid string")
        result.append(item)
    return result


def _nonempty_string(value: Any, label: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ReasoningContextPackError(f"reasoning context pack {label} is invalid")
    return value


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or _HEX_32_PATTERN.fullmatch(value) is None:
        raise ReasoningContextPackError(f"reasoning context pack {label} SHA-256 is invalid")
    return value


def _parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ReasoningContextPackError(f"reasoning context pack {label} is not UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ReasoningContextPackError(f"reasoning context pack {label} is invalid") from error
    return parsed
