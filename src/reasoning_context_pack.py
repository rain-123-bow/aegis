from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from path_security import (
    PathSecurityError,
    is_within,
    lexical_absolute,
    read_regular_file,
    same_path,
)
from reasoning_ledger.models import (
    QUERY_EMBEDDING_SOURCE_KINDS,
    contains_forbidden_authority_key,
)


REASONING_CONTEXT_PACK_SCHEMA = "aegis.reasoning_context_pack.v3"
MAX_CONTEXT_PACK_BYTES = 16 * 1024 * 1024
MAX_EVIDENCE_BYTES = 64 * 1024 * 1024

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
    "candidates",
    "causal_revisions",
    "relations",
    "conflicts",
    "warnings",
    "evidence_descriptors",
    "evidence_index",
    "canonical_payload_sha256",
}
_BINDING_FIELDS = {"project_seal", "engineering_documents_sha256"}
_LEDGER_FIELDS = {"revision", "snapshot_sha256"}
_RETRIEVAL_FIELDS = {
    "mode",
    "embedding_source",
    "scope",
    "limit",
    "include_causes",
    "trace",
}
_TRACE_FIELDS = {
    "hard_filters",
    "lexical_candidates",
    "semantic_candidates",
    "embedding_profile_id",
    "embedding_query_receipt",
    "causal_relations",
    "max_causal_depth",
    "limit",
}
_QUERY_EMBEDDING_RECEIPT_FIELDS = {
    "schema",
    "profile_id",
    "source",
    "embedding_sha256",
    "generator_identity",
}
_HARD_FILTER_FIELDS = {
    "project_id",
    "scope",
    "validities",
    "statement_types",
    "created_after",
    "created_before",
}
_REVISION_FIELDS = {
    "project_id",
    "statement_id",
    "revision",
    "statement_type",
    "content",
    "structured_conditions",
    "validity",
    "current_validity",
    "scope",
    "confidence",
    "content_sha256",
    "created_at",
    "evidence_ids",
}
_RELATION_FIELDS = {
    "project_id",
    "relation_id",
    "from_statement_id",
    "from_revision",
    "to_statement_id",
    "to_revision",
    "relation_type",
    "applicable_conditions",
    "reason",
    "content_sha256",
    "created_at",
    "evidence_ids",
}
_EVIDENCE_FIELDS = {
    "project_id",
    "evidence_id",
    "path",
    "size",
    "sha256",
    "captured_at",
    "scope",
    "content_sha256",
    "created_at",
}
_EVIDENCE_INDEX_FIELDS = {
    "evidence_id",
    "path",
    "size",
    "sha256",
}
_STATEMENT_TYPES = {
    "OBSERVATION",
    "FACT",
    "CONSTRAINT",
    "REQUIREMENT",
    "DECISION",
    "RULE",
    "HYPOTHESIS",
    "CLAIM",
}
_VALIDITIES = {"ACTIVE", "STALE", "INVALID", "SUPERSEDED"}
_RELATION_TYPES = {
    "SUPPORTS",
    "REFUTES",
    "ASSUMES",
    "SUPERSEDES",
    "CAUSES",
    "ENABLES",
    "PREVENTS",
    "REQUIRES",
}


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
        raise ReasoningContextPackError(
            "reasoning context pack path is not the immutable snapshot path"
        )
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
        raise ReasoningContextPackError(
            "reasoning context pack is invalid JSON"
        ) from error
    if not isinstance(payload, dict) or set(payload) != _TOP_LEVEL_FIELDS:
        raise ReasoningContextPackError("reasoning context pack has invalid fields")
    if payload["schema"] != REASONING_CONTEXT_PACK_SCHEMA:
        raise ReasoningContextPackError(
            "reasoning context pack has an unsupported schema"
        )
    declared_canonical_hash = _require_sha256(
        payload["canonical_payload_sha256"], "canonical payload"
    )
    canonical_payload = dict(payload)
    del canonical_payload["canonical_payload_sha256"]
    if hashlib.sha256(_canonical_bytes(canonical_payload)).hexdigest() != declared_canonical_hash:
        raise ReasoningContextPackError(
            "reasoning context pack canonical payload hash does not match"
        )
    if _HEX_16_PATTERN.fullmatch(project_id_hex) is None:
        raise ValueError("project_id_hex must contain 32 lowercase hex digits")
    if payload["project_id_hex"] != project_id_hex:
        raise ReasoningContextPackError(
            "reasoning context pack project identity does not match"
        )
    if _SEAL_PATTERN.fullmatch(project_seal) is None:
        raise ValueError("project_seal is invalid")
    _require_sha256(engineering_documents_sha256, "engineering documents")
    task_id = _nonempty_string(payload["task_id"], "task ID", 256)
    agent_role = _nonempty_string(payload["agent_role"], "agent role", 128)
    _nonempty_string(payload["query"], "query", 64 * 1024)
    _parse_utc(payload["generated_at_utc"], "generation time")
    bindings = payload["bindings"]
    if not isinstance(bindings, dict) or set(bindings) != _BINDING_FIELDS:
        raise ReasoningContextPackError("reasoning context pack has invalid bindings")
    if bindings["project_seal"] != project_seal:
        raise ReasoningContextPackError(
            "reasoning context pack project seal does not match"
        )
    if bindings["engineering_documents_sha256"] != engineering_documents_sha256:
        raise ReasoningContextPackError(
            "reasoning context pack engineering inputs do not match"
        )
    ledger = payload["ledger"]
    if not isinstance(ledger, dict) or set(ledger) != _LEDGER_FIELDS:
        raise ReasoningContextPackError(
            "reasoning context pack has invalid ledger identity"
        )
    revision = ledger["revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ReasoningContextPackError(
            "reasoning context pack has an invalid ledger revision"
        )
    ledger_snapshot_sha256 = _require_sha256(
        ledger["snapshot_sha256"], "ledger snapshot"
    )
    _validate_retrieval(payload["retrieval"])
    retrieval = payload["retrieval"]
    trace = retrieval["trace"]
    if (
        trace["hard_filters"]["project_id"] != project_id_hex
        or trace["hard_filters"]["scope"] != retrieval["scope"]
    ):
        raise ReasoningContextPackError(
            "reasoning retrieval hard filters differ from pack bindings"
        )
    revisions: dict[tuple[str, int], dict[str, Any]] = {}
    candidate_keys: set[tuple[str, int]] = set()
    observed_lexical: set[str] = set()
    observed_semantic: set[str] = set()
    candidates = payload["candidates"]
    if not isinstance(candidates, list) or len(candidates) > 10_000:
        raise ReasoningContextPackError(
            "reasoning context pack candidate revisions are invalid"
        )
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict) or set(candidate) != {
            "revision",
            "sources",
            "lexical_rank",
            "semantic_distance",
        }:
            raise ReasoningContextPackError(
                f"reasoning candidate {index} has invalid fields"
            )
        row = _validate_revision(
            candidate["revision"], project_id_hex, f"candidate {index}"
        )
        key = (row["statement_id"], row["revision"])
        if key in revisions:
            raise ReasoningContextPackError("reasoning candidates are duplicated")
        revisions[key] = row
        candidate_keys.add(key)
        sources = candidate["sources"]
        if (
            not isinstance(sources, list)
            or not sources
            or set(sources) - {"LEXICAL", "SEMANTIC"}
            or len(sources) != len(set(sources))
        ):
            raise ReasoningContextPackError("reasoning candidate sources are invalid")
        _optional_number(candidate["lexical_rank"], "lexical rank")
        _optional_number(candidate["semantic_distance"], "semantic distance")
        if "LEXICAL" in sources and candidate["lexical_rank"] is None:
            raise ReasoningContextPackError("lexical candidate has no lexical rank")
        if "SEMANTIC" in sources and candidate["semantic_distance"] is None:
            raise ReasoningContextPackError(
                "semantic candidate has no semantic distance"
            )
        revision_key = f"{key[0]}@{key[1]}"
        if "LEXICAL" in sources:
            observed_lexical.add(revision_key)
        if "SEMANTIC" in sources:
            observed_semantic.add(revision_key)
    if observed_lexical != set(trace["lexical_candidates"]) or observed_semantic != set(trace["semantic_candidates"]):
        raise ReasoningContextPackError(
            "reasoning candidate sources differ from the retrieval trace"
        )
    if observed_semantic and trace["embedding_profile_id"] is None:
        raise ReasoningContextPackError(
            "semantic candidates have no embedding profile identity"
        )

    causal = payload["causal_revisions"]
    if not isinstance(causal, list):
        raise ReasoningContextPackError("causal revisions are invalid")
    for index, raw_revision in enumerate(causal):
        row = _validate_revision(
            raw_revision, project_id_hex, f"causal revision {index}"
        )
        key = (row["statement_id"], row["revision"])
        if key in revisions:
            raise ReasoningContextPackError("reasoning revisions are duplicated")
        revisions[key] = row

    relation_ids: set[str] = set()
    relations = _validate_relations(
        payload["relations"],
        project_id_hex=project_id_hex,
        revisions=set(revisions),
        relation_ids=relation_ids,
        label="relation",
    )
    conflicts = _validate_relations(
        payload["conflicts"],
        project_id_hex=project_id_hex,
        revisions=set(revisions),
        relation_ids=relation_ids,
        label="conflict",
    )
    if any(row["relation_type"] not in {"REFUTES", "PREVENTS"} for row in conflicts):
        raise ReasoningContextPackError(
            "reasoning conflict has a non-conflict relation type"
        )

    evidence = _validate_evidence_descriptors(
        payload["evidence_descriptors"], project_id_hex
    )
    evidence_ids = set(evidence)
    referenced_evidence = {
        evidence_id
        for row in revisions.values()
        for evidence_id in row["evidence_ids"]
    }
    referenced_evidence.update(
        evidence_id
        for row in (*relations, *conflicts)
        for evidence_id in row["evidence_ids"]
    )
    if referenced_evidence != evidence_ids:
        raise ReasoningContextPackError(
            "reasoning context evidence set differs from referenced authority evidence"
        )
    _validate_evidence_index(
        payload["evidence_index"],
        evidence=evidence,
        project_root=project,
        artifact_root=artifacts,
    )
    warnings = _string_list(payload["warnings"], "warnings", max_items=10_000)
    required_warnings = {
        f"{row['statement_id']}@{row['revision']} validity is {row['current_validity']}"
        for row in revisions.values()
        if row["current_validity"] != "ACTIVE"
    }
    required_warnings.update(
        f"{row['statement_id']}@{row['revision']} is an unverified hypothesis"
        for row in revisions.values()
        if row["statement_type"] == "HYPOTHESIS"
    )
    if conflicts:
        required_warnings.add(
            "retrieved causal closure contains refuting or preventing relations"
        )
    if not required_warnings.issubset(set(warnings)):
        raise ReasoningContextPackError(
            "reasoning context pack omits validity, hypothesis, or conflict warnings"
        )

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
        raise ReasoningContextPackError(
            "reasoning context pack has invalid retrieval metadata"
        )
    mode = _nonempty_string(value["mode"], "retrieval mode", 128)
    if mode not in {"lexical_exact", "hybrid_exact"}:
        raise ReasoningContextPackError("reasoning retrieval mode is invalid")
    _nonempty_string(value["embedding_source"], "embedding source", 256)
    if (
        not isinstance(value["scope"], dict)
        or contains_forbidden_authority_key(value["scope"])
        or not isinstance(value["trace"], dict)
    ):
        raise ReasoningContextPackError("reasoning retrieval scope or trace is invalid")
    limit = value["limit"]
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10_000:
        raise ReasoningContextPackError("reasoning retrieval limit is invalid")
    if not isinstance(value["include_causes"], bool):
        raise ReasoningContextPackError("reasoning cause setting is invalid")
    trace = value["trace"]
    if set(trace) != _TRACE_FIELDS:
        raise ReasoningContextPackError("reasoning retrieval trace fields are invalid")
    hard_filters = trace["hard_filters"]
    if not isinstance(hard_filters, dict) or set(hard_filters) != _HARD_FILTER_FIELDS:
        raise ReasoningContextPackError("reasoning retrieval hard filters are invalid")
    if not isinstance(hard_filters["scope"], dict) or contains_forbidden_authority_key(
        hard_filters["scope"]
    ):
        raise ReasoningContextPackError("reasoning retrieval hard-filter scope is invalid")
    for field in ("validities", "statement_types"):
        rows = _string_list(hard_filters[field], field, max_items=10_000)
        if len(rows) != len(set(rows)):
            raise ReasoningContextPackError(f"reasoning retrieval {field} are duplicated")
    for field in ("created_after", "created_before"):
        if hard_filters[field] is not None:
            _parse_utc(hard_filters[field], field)
    for field in ("lexical_candidates", "semantic_candidates", "causal_relations"):
        rows = _string_list(trace[field], field, max_items=50_000)
        if len(rows) != len(set(rows)):
            raise ReasoningContextPackError(f"reasoning retrieval {field} are duplicated")
    profile_id = trace["embedding_profile_id"]
    if profile_id is not None:
        _nonempty_string(profile_id, "embedding profile ID", 512)
    receipt = trace["embedding_query_receipt"]
    if receipt is None:
        if profile_id is not None or trace["semantic_candidates"]:
            raise ReasoningContextPackError(
                "semantic retrieval has no query embedding receipt"
            )
        if value["embedding_source"] != "none":
            raise ReasoningContextPackError(
                "non-semantic retrieval declares an embedding source"
            )
    elif (
        not isinstance(receipt, dict)
        or set(receipt) != _QUERY_EMBEDDING_RECEIPT_FIELDS
        or receipt.get("schema") != "aegis.query_embedding_receipt.v1"
        or receipt.get("profile_id") != profile_id
        or receipt.get("source") != value["embedding_source"]
        or receipt.get("source") not in QUERY_EMBEDDING_SOURCE_KINDS
        or not isinstance(receipt.get("generator_identity"), dict)
        or not receipt["generator_identity"]
        or receipt["generator_identity"].get("kind")
        != QUERY_EMBEDDING_SOURCE_KINDS.get(receipt.get("source"))
        or contains_forbidden_authority_key(receipt["generator_identity"])
    ):
        raise ReasoningContextPackError(
            "reasoning query embedding receipt is invalid"
        )
    else:
        _require_sha256(receipt["embedding_sha256"], "query embedding")
    expected_mode = "hybrid_exact" if receipt is not None else "lexical_exact"
    if mode != expected_mode:
        raise ReasoningContextPackError(
            "reasoning retrieval mode differs from the query embedding receipt"
        )
    if isinstance(trace["max_causal_depth"], bool) or not isinstance(trace["max_causal_depth"], int) or trace["max_causal_depth"] < 0:
        raise ReasoningContextPackError("reasoning maximum causal depth is invalid")
    if trace["limit"] != limit:
        raise ReasoningContextPackError("reasoning trace limit differs from retrieval limit")


def _validate_revision(value: Any, project_id: str, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _REVISION_FIELDS:
        raise ReasoningContextPackError(f"{label} has invalid fields")
    if value["project_id"] != project_id:
        raise ReasoningContextPackError(f"{label} project identity differs")
    _nonempty_string(value["statement_id"], f"{label} statement ID", 512)
    if isinstance(value["revision"], bool) or not isinstance(value["revision"], int) or value["revision"] < 1:
        raise ReasoningContextPackError(f"{label} revision is invalid")
    if value["statement_type"] not in _STATEMENT_TYPES:
        raise ReasoningContextPackError(f"{label} statement type is invalid")
    if value["validity"] not in _VALIDITIES or value["current_validity"] not in _VALIDITIES:
        raise ReasoningContextPackError(f"{label} validity is invalid")
    _nonempty_string(value["content"], f"{label} content", 2 * 1024 * 1024)
    if (
        not isinstance(value["structured_conditions"], dict)
        or not isinstance(value["scope"], dict)
        or contains_forbidden_authority_key(value["structured_conditions"])
        or contains_forbidden_authority_key(value["scope"])
    ):
        raise ReasoningContextPackError(f"{label} conditions or scope is invalid")
    _optional_number(value["confidence"], f"{label} confidence", bounded=True)
    _require_sha256(value["content_sha256"], f"{label} content")
    _parse_utc(value["created_at"], f"{label} creation time")
    evidence_ids = _string_list(value["evidence_ids"], f"{label} evidence IDs", max_items=10_000)
    if not evidence_ids or len(evidence_ids) != len(set(evidence_ids)):
        raise ReasoningContextPackError(f"{label} evidence IDs are invalid")
    return value


def _validate_relations(
    value: Any,
    *,
    project_id_hex: str,
    revisions: set[tuple[str, int]],
    relation_ids: set[str],
    label: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 50_000:
        raise ReasoningContextPackError(f"reasoning {label} list is invalid")
    result: list[dict[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, dict) or set(row) != _RELATION_FIELDS:
            raise ReasoningContextPackError(f"reasoning {label} {index} has invalid fields")
        relation_id = _nonempty_string(row["relation_id"], f"{label} ID", 512)
        if relation_id in relation_ids:
            raise ReasoningContextPackError("reasoning relation IDs are duplicated")
        relation_ids.add(relation_id)
        if row["project_id"] != project_id_hex or row["relation_type"] not in _RELATION_TYPES:
            raise ReasoningContextPackError(f"reasoning {label} identity or type is invalid")
        from_key = (row["from_statement_id"], row["from_revision"])
        to_key = (row["to_statement_id"], row["to_revision"])
        if from_key not in revisions or to_key not in revisions:
            raise ReasoningContextPackError(f"reasoning {label} endpoint is absent")
        if not isinstance(row["applicable_conditions"], dict) or contains_forbidden_authority_key(
            row["applicable_conditions"]
        ):
            raise ReasoningContextPackError(f"reasoning {label} conditions are invalid")
        _nonempty_string(row["reason"], f"{label} reason", 64 * 1024)
        _require_sha256(row["content_sha256"], f"{label} content")
        _parse_utc(row["created_at"], f"{label} creation time")
        ids = _string_list(row["evidence_ids"], f"{label} evidence IDs", max_items=10_000)
        if not ids or len(ids) != len(set(ids)):
            raise ReasoningContextPackError(f"reasoning {label} evidence IDs are invalid")
        result.append(row)
    return result


def _validate_evidence_descriptors(value: Any, project_id: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 10_000:
        raise ReasoningContextPackError("reasoning evidence descriptors are invalid")
    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(value):
        if not isinstance(row, dict) or set(row) != _EVIDENCE_FIELDS:
            raise ReasoningContextPackError(f"reasoning evidence {index} has invalid fields")
        evidence_id = _nonempty_string(row["evidence_id"], "evidence ID", 512)
        if evidence_id in result or row["project_id"] != project_id:
            raise ReasoningContextPackError("reasoning evidence identity is invalid")
        _nonempty_string(row["path"], "evidence path", 4096)
        if isinstance(row["size"], bool) or not isinstance(row["size"], int) or row["size"] < 0:
            raise ReasoningContextPackError("reasoning evidence size is invalid")
        _require_sha256(row["sha256"], "evidence bytes")
        _require_sha256(row["content_sha256"], "evidence descriptor")
        if not isinstance(row["scope"], dict) or contains_forbidden_authority_key(
            row["scope"]
        ):
            raise ReasoningContextPackError("reasoning evidence scope is invalid")
        _parse_utc(row["captured_at"], "evidence capture time")
        _parse_utc(row["created_at"], "evidence creation time")
        result[evidence_id] = row
    return result


def _validate_evidence_index(
    value: Any,
    *,
    evidence: Mapping[str, Mapping[str, Any]],
    project_root: Path,
    artifact_root: Path,
) -> None:
    if not isinstance(value, list) or len(value) != len(evidence):
        raise ReasoningContextPackError("reasoning evidence index is incomplete")
    seen: set[str] = set()
    for index, descriptor in enumerate(value):
        if not isinstance(descriptor, dict) or set(descriptor) != _EVIDENCE_INDEX_FIELDS:
            raise ReasoningContextPackError(f"context evidence {index} has invalid fields")
        evidence_id = descriptor["evidence_id"]
        authority = evidence.get(evidence_id)
        if authority is None or evidence_id in seen:
            raise ReasoningContextPackError("context evidence identity is invalid")
        seen.add(evidence_id)
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
        digest = hashlib.sha256(content).hexdigest()
        if (
            descriptor["size"] != len(content)
            or descriptor["sha256"] != digest
            or descriptor["size"] != authority["size"]
            or descriptor["sha256"] != authority["sha256"]
            or not same_path(path, project_root / str(authority["path"]))
        ):
            raise ReasoningContextPackError(
                f"context evidence {index} differs from authority descriptor"
            )


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _string_list(value: Any, label: str, *, max_items: int) -> list[str]:
    if not isinstance(value, list) or len(value) > max_items:
        raise ReasoningContextPackError(f"reasoning context pack {label} is invalid")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ReasoningContextPackError(
                f"reasoning context pack {label} contains an invalid string"
            )
        result.append(item)
    return result


def _nonempty_string(value: Any, label: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ReasoningContextPackError(f"reasoning context pack {label} is invalid")
    return value


def _optional_number(value: Any, label: str, *, bounded: bool = False) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReasoningContextPackError(f"reasoning context pack {label} is invalid")
    if bounded and not 0 <= value <= 1:
        raise ReasoningContextPackError(f"reasoning context pack {label} is invalid")


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or _HEX_32_PATTERN.fullmatch(value) is None:
        raise ReasoningContextPackError(
            f"reasoning context pack {label} SHA-256 is invalid"
        )
    return value


def _parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ReasoningContextPackError(
            f"reasoning context pack {label} is not UTC"
        )
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ReasoningContextPackError(
            f"reasoning context pack {label} is invalid"
        ) from error
