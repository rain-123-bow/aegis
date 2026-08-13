from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence


DECISION_SCHEMA = "aegis.semantic_decoy_decision.v1"
MANIFEST_SCHEMA = "aegis.semantic_decoy_manifest.v1"

_DECISION_FIELDS = {
    "schema",
    "task_id",
    "phase",
    "enabled",
    "decision_source",
    "response_summary",
    "asked_at_utc",
    "answered_at_utc",
}
_MANIFEST_FIELDS = {
    "schema",
    "task_id",
    "decision_sha256",
    "requirement_document_sha256",
    "context_pack_sha256",
    "project_seal",
    "entries",
}
_ENTRY_FIELDS = {
    "decoy_id",
    "classification",
    "code_anchors",
    "predicate",
    "true_semantics",
    "surface_semantics",
    "constraint_item_ids",
    "invalidation_conditions",
}
_HEX_64 = re.compile(r"[0-9a-f]{64}")
_PROJECT_SEAL = re.compile(r"ASC1:[0-9a-f]{64}")


class SemanticDecoyContractError(ValueError):
    pass


class DecoyClassification(str, Enum):
    REAL = "REAL"
    DECOY_UNREACHABLE = "DECOY_UNREACHABLE"
    UNKNOWN_STALE = "UNKNOWN-STALE"


@dataclass(frozen=True, slots=True)
class SemanticDecoyDecision:
    task_id: str
    enabled: bool
    decision_source: str
    response_summary: str
    asked_at_utc: str
    answered_at_utc: str


@dataclass(frozen=True, slots=True)
class SemanticDecoyEntryEvaluation:
    decoy_id: str
    declared_classification: DecoyClassification
    effective_classification: DecoyClassification
    internal_logic_test_required: bool
    perimeter_tests_required: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SemanticDecoyEvaluation:
    policy_enabled: bool
    entries: tuple[SemanticDecoyEntryEvaluation, ...]
    structurally_eligible_decoy_ids: tuple[str, ...]
    all_declared_decoys_structurally_valid: bool
    blocking_reasons: tuple[str, ...]


def parse_semantic_decoy_decision(
    value: Mapping[str, Any],
) -> SemanticDecoyDecision:
    if not isinstance(value, Mapping) or set(value) != _DECISION_FIELDS:
        raise SemanticDecoyContractError(
            "semantic decoy decision has an invalid field set"
        )
    if value["schema"] != DECISION_SCHEMA:
        raise SemanticDecoyContractError(
            "semantic decoy decision has an unsupported schema"
        )
    task_id = _require_text(value["task_id"], "task_id")
    if value["phase"] != "pre_requirement_draft":
        raise SemanticDecoyContractError(
            "semantic decoy decision was not made before requirement drafting"
        )
    enabled = value["enabled"]
    if type(enabled) is not bool:
        raise SemanticDecoyContractError("semantic decoy enabled must be boolean")
    decision_source = _require_text(
        value["decision_source"], "decision_source"
    )
    valid_sources = (
        {"developer_explicit_confirmation"}
        if enabled
        else {"developer_explicit_decline", "default_disabled"}
    )
    if decision_source not in valid_sources:
        raise SemanticDecoyContractError(
            "semantic decoy enablement requires explicit developer confirmation"
        )
    response_summary = _require_text(
        value["response_summary"], "response_summary"
    )
    asked_text, asked = _require_utc(value["asked_at_utc"], "asked_at_utc")
    answered_text, answered = _require_utc(
        value["answered_at_utc"], "answered_at_utc"
    )
    if answered < asked:
        raise SemanticDecoyContractError(
            "semantic decoy answer precedes the question"
        )
    return SemanticDecoyDecision(
        task_id=task_id,
        enabled=enabled,
        decision_source=decision_source,
        response_summary=response_summary,
        asked_at_utc=asked_text,
        answered_at_utc=answered_text,
    )


def _evaluate_semantic_decoy_manifest(
    manifest: Mapping[str, Any],
    *,
    decision: SemanticDecoyDecision,
    decision_sha256: str,
    requirement_document_sha256: str,
    context_pack_sha256: str,
    current_project_seal: str,
    context_pack: Mapping[str, Any],
) -> SemanticDecoyEvaluation:
    if not isinstance(manifest, Mapping) or set(manifest) != _MANIFEST_FIELDS:
        raise SemanticDecoyContractError(
            "semantic decoy manifest has an invalid field set"
        )
    if manifest["schema"] != MANIFEST_SCHEMA:
        raise SemanticDecoyContractError(
            "semantic decoy manifest has an unsupported schema"
        )
    task_id = _require_text(manifest["task_id"], "manifest task_id")
    recorded_decision_sha = _require_sha256(
        manifest["decision_sha256"], "decision_sha256"
    )
    recorded_requirement_sha = _require_sha256(
        manifest["requirement_document_sha256"],
        "requirement_document_sha256",
    )
    recorded_context_pack_sha = _require_sha256(
        manifest["context_pack_sha256"],
        "context_pack_sha256",
    )
    recorded_seal = _require_project_seal(manifest["project_seal"])
    actual_decision_sha = _require_sha256(
        decision_sha256, "actual decision_sha256"
    )
    actual_requirement_sha = _require_sha256(
        requirement_document_sha256,
        "actual requirement_document_sha256",
    )
    actual_context_pack_sha = _require_sha256(
        context_pack_sha256,
        "actual context_pack_sha256",
    )
    actual_seal = _require_project_seal(current_project_seal)
    raw_entries = manifest["entries"]
    if not isinstance(raw_entries, list):
        raise SemanticDecoyContractError("semantic decoy entries must be a list")

    global_reasons: list[str] = []
    if task_id != decision.task_id:
        global_reasons.append("manifest task does not match the decision task")
    if recorded_decision_sha != actual_decision_sha:
        global_reasons.append("semantic decoy decision SHA-256 mismatch")
    if recorded_requirement_sha != actual_requirement_sha:
        global_reasons.append("requirement document SHA-256 mismatch")
    if recorded_context_pack_sha != actual_context_pack_sha:
        global_reasons.append("reasoning context pack SHA-256 mismatch")
    if recorded_seal != actual_seal:
        global_reasons.append("project Seal mismatch")
    if context_pack.get("task_id") != task_id:
        global_reasons.append("reasoning context pack task does not match manifest")
    context_metadata = context_pack.get("metadata")
    if (
        not isinstance(context_metadata, Mapping)
        or context_metadata.get("project_seal") != actual_seal
    ):
        global_reasons.append(
            "reasoning context pack is not bound to the current project Seal"
        )

    ledger_items = _index_context_items(context_pack)
    entry_results: list[SemanticDecoyEntryEvaluation] = []
    seen_ids: set[str] = set()
    blocking_reasons = list(global_reasons)
    for raw_entry in raw_entries:
        parsed = _parse_manifest_entry(raw_entry)
        decoy_id = parsed["decoy_id"]
        if decoy_id in seen_ids:
            raise SemanticDecoyContractError(
                f"duplicate semantic decoy id: {decoy_id}"
            )
        seen_ids.add(decoy_id)
        result = _evaluate_entry(
            parsed,
            policy_enabled=decision.enabled,
            global_reasons=global_reasons,
            ledger_items=ledger_items,
        )
        entry_results.append(result)
        blocking_reasons.extend(
            f"{decoy_id}: {reason}" for reason in result.reasons
        )

    unique_blocking = tuple(dict.fromkeys(blocking_reasons))
    structurally_eligible = tuple(
        entry.decoy_id
        for entry in entry_results
        if entry.effective_classification
        is DecoyClassification.DECOY_UNREACHABLE
    )
    return SemanticDecoyEvaluation(
        policy_enabled=decision.enabled,
        entries=tuple(entry_results),
        structurally_eligible_decoy_ids=structurally_eligible,
        all_declared_decoys_structurally_valid=not unique_blocking,
        blocking_reasons=unique_blocking,
    )


def evaluate_semantic_decoy_artifacts(
    manifest_bytes: bytes,
    *,
    decision_bytes: bytes,
    requirement_document_bytes: bytes,
    context_pack_bytes: bytes,
    current_project_seal: str,
) -> SemanticDecoyEvaluation:
    """Evaluate exact artifact bytes and derive every content digest locally."""

    for value, label in (
        (manifest_bytes, "semantic decoy manifest"),
        (decision_bytes, "semantic decoy decision"),
        (requirement_document_bytes, "requirement document"),
        (context_pack_bytes, "reasoning context pack"),
    ):
        if not isinstance(value, bytes):
            raise SemanticDecoyContractError(f"{label} must be bytes")
    manifest = _parse_json_object(manifest_bytes, "semantic decoy manifest")
    decision_data = _parse_json_object(decision_bytes, "semantic decoy decision")
    context_pack = _parse_json_object(context_pack_bytes, "reasoning context pack")
    return _evaluate_semantic_decoy_manifest(
        manifest,
        decision=parse_semantic_decoy_decision(decision_data),
        decision_sha256=hashlib.sha256(decision_bytes).hexdigest(),
        requirement_document_sha256=hashlib.sha256(
            requirement_document_bytes
        ).hexdigest(),
        context_pack_sha256=hashlib.sha256(context_pack_bytes).hexdigest(),
        current_project_seal=current_project_seal,
        context_pack=context_pack,
    )


def evaluate_semantic_decoy_files(
    manifest_path: str | Path,
    *,
    decision_path: str | Path,
    requirement_document_path: str | Path,
    context_pack_path: str | Path,
    current_project_seal: str,
) -> SemanticDecoyEvaluation:
    """Evaluate a policy from exact artifact bytes instead of caller digests."""

    manifest_bytes = _read_required_bytes(manifest_path, "semantic decoy manifest")
    decision_bytes = _read_required_bytes(decision_path, "semantic decoy decision")
    requirement_bytes = _read_required_bytes(
        requirement_document_path,
        "requirement document",
    )
    context_pack_bytes = _read_required_bytes(
        context_pack_path,
        "reasoning context pack",
    )
    return evaluate_semantic_decoy_artifacts(
        manifest_bytes,
        decision_bytes=decision_bytes,
        requirement_document_bytes=requirement_bytes,
        context_pack_bytes=context_pack_bytes,
        current_project_seal=current_project_seal,
    )


def _parse_manifest_entry(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _ENTRY_FIELDS:
        raise SemanticDecoyContractError(
            "semantic decoy entry has an invalid field set"
        )
    try:
        classification = DecoyClassification(value["classification"])
    except (TypeError, ValueError) as error:
        raise SemanticDecoyContractError(
            "semantic decoy entry has an invalid classification"
        ) from error
    parsed = {
        "decoy_id": _require_text(value["decoy_id"], "decoy_id"),
        "classification": classification,
        "code_anchors": _require_text_list(value["code_anchors"], "code_anchors"),
        "predicate": _require_text(value["predicate"], "predicate"),
        "true_semantics": _require_text(
            value["true_semantics"], "true_semantics"
        ),
        "surface_semantics": _require_text_list(
            value["surface_semantics"],
            "surface_semantics",
            allow_empty=True,
        ),
        "constraint_item_ids": _require_text_list(
            value["constraint_item_ids"],
            "constraint_item_ids",
            allow_empty=True,
        ),
        "invalidation_conditions": _require_text_list(
            value["invalidation_conditions"],
            "invalidation_conditions",
            allow_empty=True,
        ),
    }
    if classification is DecoyClassification.DECOY_UNREACHABLE:
        for field in (
            "surface_semantics",
            "constraint_item_ids",
            "invalidation_conditions",
        ):
            if not parsed[field]:
                raise SemanticDecoyContractError(
                    f"DECOY_UNREACHABLE requires {field}"
                )
    return parsed


def _evaluate_entry(
    entry: Mapping[str, Any],
    *,
    policy_enabled: bool,
    global_reasons: Sequence[str],
    ledger_items: Mapping[str, Sequence[Mapping[str, Any]]],
) -> SemanticDecoyEntryEvaluation:
    declared = entry["classification"]
    assert isinstance(declared, DecoyClassification)
    if declared is DecoyClassification.REAL:
        return SemanticDecoyEntryEvaluation(
            decoy_id=entry["decoy_id"],
            declared_classification=declared,
            effective_classification=DecoyClassification.REAL,
            internal_logic_test_required=True,
            perimeter_tests_required=False,
            reasons=(),
        )

    reasons = list(global_reasons)
    if declared is DecoyClassification.UNKNOWN_STALE:
        reasons.append("entry is explicitly UNKNOWN-STALE")
    if not policy_enabled:
        reasons.append("semantic decoy policy is disabled")

    if declared is DecoyClassification.DECOY_UNREACHABLE:
        for item_id in entry["constraint_item_ids"]:
            candidates = ledger_items.get(item_id, ())
            if len(candidates) != 1:
                reasons.append(
                    f"constraint item {item_id} is missing or ambiguous"
                )
                continue
            item = candidates[0]
            if item.get("status") != "active":
                reasons.append(f"constraint item {item_id} is not active")
            if item.get("type") not in {"fact", "rule"}:
                reasons.append(f"constraint item {item_id} is not a fact or rule")
            evidence_path = item.get("evidence_path")
            if not isinstance(evidence_path, str) or not evidence_path.strip():
                reasons.append(f"constraint item {item_id} has no evidence path")

    effective = (
        DecoyClassification.DECOY_UNREACHABLE
        if declared is DecoyClassification.DECOY_UNREACHABLE and not reasons
        else DecoyClassification.UNKNOWN_STALE
    )
    return SemanticDecoyEntryEvaluation(
        decoy_id=entry["decoy_id"],
        declared_classification=declared,
        effective_classification=effective,
        internal_logic_test_required=effective
        is not DecoyClassification.DECOY_UNREACHABLE,
        perimeter_tests_required=True,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def _index_context_items(
    context_pack: Mapping[str, Any],
) -> dict[str, list[Mapping[str, Any]]]:
    if not isinstance(context_pack, Mapping):
        raise SemanticDecoyContractError("reasoning context pack must be an object")
    result: dict[str, list[Mapping[str, Any]]] = {}
    for section in ("items", "cause_items"):
        rows = context_pack.get(section, [])
        if not isinstance(rows, list):
            raise SemanticDecoyContractError(
                f"reasoning context pack {section} must be a list"
            )
        for row in rows:
            if not isinstance(row, Mapping):
                raise SemanticDecoyContractError(
                    f"reasoning context pack {section} contains a non-object"
                )
            item_id = row.get("id")
            if isinstance(item_id, str) and item_id:
                candidates = result.setdefault(item_id, [])
                if not any(dict(candidate) == dict(row) for candidate in candidates):
                    candidates.append(row)
    return result


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SemanticDecoyContractError(f"{field} must be non-empty text")
    return value


def _require_text_list(
    value: Any,
    field: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list) or (
        not allow_empty and not value
    ) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise SemanticDecoyContractError(
            f"{field} must be a list of non-empty strings"
        )
    if len(set(value)) != len(value):
        raise SemanticDecoyContractError(f"{field} must not contain duplicates")
    return tuple(value)


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise SemanticDecoyContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return value


def _require_project_seal(value: Any) -> str:
    if not isinstance(value, str) or _PROJECT_SEAL.fullmatch(value) is None:
        raise SemanticDecoyContractError(
            "project_seal must use canonical ASC1 form"
        )
    return value


def _require_utc(value: Any, field: str) -> tuple[str, datetime]:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise SemanticDecoyContractError(f"{field} must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise SemanticDecoyContractError(
            f"{field} must be a valid UTC timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise SemanticDecoyContractError(f"{field} must be a UTC timestamp")
    return value, parsed


def _read_required_bytes(path: str | Path, label: str) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError as error:
        raise SemanticDecoyContractError(f"cannot read {label}: {error}") from error


def _parse_json_object(data: bytes, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SemanticDecoyContractError(f"{label} is not valid UTF-8 JSON") from error
    if not isinstance(value, Mapping):
        raise SemanticDecoyContractError(f"{label} must contain a JSON object")
    return value


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SemanticDecoyContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result
