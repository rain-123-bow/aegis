from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

LOCAL_STORES = {"archive", "knowledge", "causal"}
PROMOTED_ASSET_TARGET_STORES = {"knowledge", "causal"}
KNOWLEDGE_EVIDENCE_LOCAL_STORES = {"archive"}
STORE_ALIASES = {
    "archive": "archive",
    "archive_event": "archive",
    "archive_events": "archive",
    "archive_store": "archive",
    "knowledge": "knowledge",
    "knowledge_entry": "knowledge",
    "knowledge_entries": "knowledge",
    "knowledge_store": "knowledge",
    "causal": "causal",
    "causal_fact": "causal",
    "causal_facts": "causal",
    "causal_store": "causal",
}
ID_TO_STORE = {"E": "archive", "K": "knowledge", "F": "causal"}
ID_PATTERN = re.compile(r"^[EKF][0-9]{4}$")
ACCEPTED_REQUEST_TYPES = {"three_store_linkage_request", "three_store_linkage_validation_request"}

BOUNDARY_TRUE_FIELDS = {
    "archive": (
        "archive_produces_truth",
        "production_archive_persistence",
        "production_encryption",
        "remote_sync_performed",
        "knowledge_store_write_performed",
        "causal_store_write_performed",
        "ordinary_agent_direct_write_allowed",
    ),
    "knowledge": (
        "knowledge_produces_causal_truth",
        "production_knowledge_persistence",
        "production_encryption",
        "remote_sync_performed",
        "archive_store_write_performed",
        "causal_store_write_performed",
        "ordinary_agent_direct_write_allowed",
    ),
    "causal": (
        "production_persistence",
        "global_causal_truth_merge_performed",
        "canonical_global_merge_performed",
        "remote_sync_performed",
        "encryption_performed",
        "production_encryption",
        "archive_store_write_performed",
        "knowledge_store_write_performed",
    ),
}


class ThreeStoreLinkageError(ValueError):
    """Raised when Phase 23C linkage validation input is malformed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ThreeStoreLinkageResult:
    three_store_linkage_result_id: str
    phase: str
    status: str
    decision: str
    reason: str
    archive_root: str
    knowledge_root: str
    causal_root: str
    archive_event_count: int = 0
    knowledge_entry_count: int = 0
    causal_fact_count: int = 0
    checked_reference_count: int = 0
    validated_links: list[dict[str, Any]] = field(default_factory=list)
    external_refs: list[dict[str, Any]] = field(default_factory=list)
    missing_refs: list[dict[str, Any]] = field(default_factory=list)
    type_mismatches: list[dict[str, Any]] = field(default_factory=list)
    store_boundary_violations: list[dict[str, Any]] = field(default_factory=list)
    duplicate_ids: list[dict[str, Any]] = field(default_factory=list)
    request_checked: bool = False
    production_linkage_persistence: bool = False
    production_encryption: bool = False
    remote_sync_performed: bool = False
    archive_store_write_performed: bool = False
    knowledge_store_write_performed: bool = False
    causal_store_write_performed: bool = False
    global_causal_truth_merge_performed: bool = False
    ordinary_agent_direct_write_allowed: bool = False
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "three_store_linkage_result_id": self.three_store_linkage_result_id,
            "phase": self.phase,
            "status": self.status,
            "decision": self.decision,
            "reason": self.reason,
            "archive_root": self.archive_root,
            "knowledge_root": self.knowledge_root,
            "causal_root": self.causal_root,
            "archive_event_count": self.archive_event_count,
            "knowledge_entry_count": self.knowledge_entry_count,
            "causal_fact_count": self.causal_fact_count,
            "checked_reference_count": self.checked_reference_count,
            "validated_links": list(self.validated_links),
            "external_refs": list(self.external_refs),
            "missing_refs": list(self.missing_refs),
            "type_mismatches": list(self.type_mismatches),
            "store_boundary_violations": list(self.store_boundary_violations),
            "duplicate_ids": list(self.duplicate_ids),
            "request_checked": self.request_checked,
            "production_linkage_persistence": self.production_linkage_persistence,
            "production_encryption": self.production_encryption,
            "remote_sync_performed": self.remote_sync_performed,
            "archive_store_write_performed": self.archive_store_write_performed,
            "knowledge_store_write_performed": self.knowledge_store_write_performed,
            "causal_store_write_performed": self.causal_store_write_performed,
            "global_causal_truth_merge_performed": self.global_causal_truth_merge_performed,
            "ordinary_agent_direct_write_allowed": self.ordinary_agent_direct_write_allowed,
            "created_at": self.created_at,
        }


def load_json_object(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ThreeStoreLinkageError(f"file not found: {p}") from exc
    except json.JSONDecodeError as exc:
        raise ThreeStoreLinkageError(f"file is not valid JSON/YAML-compatible payload: {p}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ThreeStoreLinkageError(f"file must contain a JSON object: {p}")
    return payload


def write_json_compatible_yaml(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_three_store_linkage_request_file(
    linkage_request_path: str | Path,
    *,
    archive_root: str | Path,
    knowledge_root: str | Path,
    causal_root: str | Path,
) -> ThreeStoreLinkageResult:
    return validate_three_store_linkage(
        archive_root=archive_root,
        knowledge_root=knowledge_root,
        causal_root=causal_root,
        linkage_request=load_json_object(linkage_request_path),
    )


def validate_three_store_linkage(
    *,
    archive_root: str | Path,
    knowledge_root: str | Path,
    causal_root: str | Path,
    linkage_request: dict[str, Any] | None = None,
) -> ThreeStoreLinkageResult:
    archive_root_path = Path(archive_root).resolve()
    knowledge_root_path = Path(knowledge_root).resolve()
    causal_root_path = Path(causal_root).resolve()

    missing_roots = [
        str(path)
        for path in (archive_root_path, knowledge_root_path, causal_root_path)
        if not path.exists()
    ]
    if missing_roots:
        return _result(
            archive_root_path,
            knowledge_root_path,
            causal_root_path,
            status="rejected",
            decision="rejected",
            reason="Three-store linkage validation requires existing local Archive, Knowledge, and Causal roots: "
            + ", ".join(missing_roots),
        )

    request_error = _request_error(linkage_request)
    if request_error:
        return _result(
            archive_root_path,
            knowledge_root_path,
            causal_root_path,
            status="rejected",
            decision="rejected",
            reason=request_error,
            request_checked=linkage_request is not None,
        )

    archive_records, archive_duplicates = _load_archive_records(archive_root_path)
    knowledge_records, knowledge_duplicates = _load_simple_records(knowledge_root_path / "entries", "K", "id")
    causal_records, causal_duplicates = _load_simple_records(causal_root_path / "facts", "F", "id")
    registry = {
        "archive": archive_records,
        "knowledge": knowledge_records,
        "causal": causal_records,
    }

    duplicate_ids = archive_duplicates + knowledge_duplicates + causal_duplicates
    store_boundary_violations = _collect_boundary_violations(registry)
    checked_refs: list[dict[str, Any]] = []
    validated_links: list[dict[str, Any]] = []
    external_refs: list[dict[str, Any]] = []
    missing_refs: list[dict[str, Any]] = []
    type_mismatches: list[dict[str, Any]] = []

    for record in archive_records.values():
        payload = record["payload"]
        _check_refs(
            registry,
            checked_refs,
            validated_links,
            external_refs,
            missing_refs,
            type_mismatches,
            source_store="archive",
            source_id=record["id"],
            field_name="promoted_to_knowledge",
            value=payload.get("promoted_to_knowledge", []),
            expected_store="knowledge",
        )
        _check_refs(
            registry,
            checked_refs,
            validated_links,
            external_refs,
            missing_refs,
            type_mismatches,
            source_store="archive",
            source_id=record["id"],
            field_name="promoted_to_causal",
            value=payload.get("promoted_to_causal", []),
            expected_store="causal",
        )
        _check_promoted_assets(
            registry,
            checked_refs,
            validated_links,
            external_refs,
            missing_refs,
            type_mismatches,
            source_store="archive",
            source_id=record["id"],
            value=payload.get("promoted_assets", []),
        )
        _check_refs(
            registry,
            checked_refs,
            validated_links,
            external_refs,
            missing_refs,
            type_mismatches,
            source_store="archive",
            source_id=record["id"],
            field_name="decision_refs",
            value=payload.get("decision_refs", []),
            expected_store=None,
        )

    for record in knowledge_records.values():
        payload = record["payload"]
        _check_allowed_store_refs(
            registry,
            checked_refs,
            validated_links,
            external_refs,
            missing_refs,
            type_mismatches,
            source_store="knowledge",
            source_id=record["id"],
            field_name="evidence_refs",
            value=payload.get("evidence_refs", []),
            allowed_stores=KNOWLEDGE_EVIDENCE_LOCAL_STORES,
            boundary_reason="Knowledge evidence_refs may cite Archive events or external source material, not Knowledge or Causal local records.",
        )

    for record in causal_records.values():
        payload = record["payload"]
        _check_refs(
            registry,
            checked_refs,
            validated_links,
            external_refs,
            missing_refs,
            type_mismatches,
            source_store="causal",
            source_id=record["id"],
            field_name="evidence",
            value=payload.get("evidence", payload.get("evidence_refs", [])),
            expected_store=None,
        )
        for field_name in ("depends_on", "supersedes", "invalidates"):
            _check_refs(
                registry,
                checked_refs,
                validated_links,
                external_refs,
                missing_refs,
                type_mismatches,
                source_store="causal",
                source_id=record["id"],
                field_name=field_name,
                value=payload.get(field_name, []),
                expected_store="causal",
            )

    if linkage_request is not None:
        _check_request_expected_links(
            registry,
            checked_refs,
            validated_links,
            external_refs,
            missing_refs,
            type_mismatches,
            linkage_request,
        )

    if duplicate_ids or store_boundary_violations or missing_refs or type_mismatches:
        reason_parts = []
        if duplicate_ids:
            reason_parts.append("duplicate local store IDs detected")
        if store_boundary_violations:
            reason_parts.append("store boundary violation detected")
        if missing_refs:
            reason_parts.append("missing typed local references detected")
        if type_mismatches:
            reason_parts.append("cross-store reference type mismatch detected")
        return _result(
            archive_root_path,
            knowledge_root_path,
            causal_root_path,
            status="rejected",
            decision="rejected",
            reason="; ".join(reason_parts),
            archive_event_count=len(archive_records),
            knowledge_entry_count=len(knowledge_records),
            causal_fact_count=len(causal_records),
            checked_reference_count=len(checked_refs),
            validated_links=validated_links,
            external_refs=external_refs,
            missing_refs=missing_refs,
            type_mismatches=type_mismatches,
            store_boundary_violations=store_boundary_violations,
            duplicate_ids=duplicate_ids,
            request_checked=linkage_request is not None,
        )

    return _result(
        archive_root_path,
        knowledge_root_path,
        causal_root_path,
        status="validated",
        decision="accepted_local_three_store_linkage",
        reason="Validated local demo Archive/Knowledge/Causal cross-store reference integrity.",
        archive_event_count=len(archive_records),
        knowledge_entry_count=len(knowledge_records),
        causal_fact_count=len(causal_records),
        checked_reference_count=len(checked_refs),
        validated_links=validated_links,
        external_refs=external_refs,
        request_checked=linkage_request is not None,
    )


def _request_error(linkage_request: dict[str, Any] | None) -> str | None:
    if linkage_request is None:
        return None
    if not isinstance(linkage_request, dict):
        return "linkage_request must be a JSON object"
    if str(linkage_request.get("request_type", "")) not in ACCEPTED_REQUEST_TYPES:
        allowed = ", ".join(sorted(ACCEPTED_REQUEST_TYPES))
        return f"linkage_request has invalid request_type. Allowed: {allowed}."
    if linkage_request.get("master_verified") is not True:
        return "linkage_request must be Master verified before Phase 23C validation."
    forbidden_flags = (
        "production_linkage_persistence",
        "production_store_write_performed",
        "global_causal_truth_merge_performed",
        "archive_store_write_performed",
        "knowledge_store_write_performed",
        "causal_store_write_performed",
        "ordinary_agent_direct_write_allowed",
    )
    if any(linkage_request.get(flag) is True for flag in forbidden_flags):
        return "linkage_request attempts production store write, global truth merge, or ordinary-agent direct write."
    return None


def _load_archive_records(archive_root: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    records: dict[str, dict[str, Any]] = {}
    duplicates: list[dict[str, Any]] = []

    for path in sorted((archive_root / "active").glob("*/events/E*.yaml")):
        _add_record(records, duplicates, store="archive", path=path, payload=load_json_object(path), id_field="event_id")

    for path in sorted((archive_root / "sealed").glob("*/events/E*.yaml")):
        _add_record(records, duplicates, store="archive", path=path, payload=load_json_object(path), id_field="event_id")

    for zip_path in sorted((archive_root / "sealed").glob("*/compressed_payload.zip")):
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in sorted(zf.namelist()):
                normalized = name.replace("\\", "/")
                if not normalized.startswith("events/") or not normalized.endswith(".yaml"):
                    continue
                payload = json.loads(zf.read(name).decode("utf-8"))
                pseudo_path = Path(f"{zip_path}!{normalized}")
                _add_record(records, duplicates, store="archive", path=pseudo_path, payload=payload, id_field="event_id")

    for index_path in sorted((archive_root / "sealed").glob("*/index.yaml")):
        try:
            index = load_json_object(index_path)
        except ThreeStoreLinkageError:
            continue
        for event in index.get("events", []):
            if not isinstance(event, dict):
                continue
            event_id = str(event.get("event_id", ""))
            if event_id and event_id not in records:
                records[event_id] = {"store": "archive", "id": event_id, "path": _display_path(index_path), "payload": {"event_id": event_id}}
    return records, duplicates


def _load_simple_records(root: Path, id_prefix: str, id_field: str) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    records: dict[str, dict[str, Any]] = {}
    duplicates: list[dict[str, Any]] = []
    if not root.exists():
        return records, duplicates
    for path in sorted(root.glob(f"{id_prefix}*.yaml")):
        payload = load_json_object(path)
        store = ID_TO_STORE[id_prefix]
        _add_record(records, duplicates, store=store, path=path, payload=payload, id_field=id_field)
    return records, duplicates


def _add_record(
    records: dict[str, dict[str, Any]],
    duplicates: list[dict[str, Any]],
    *,
    store: str,
    path: Path,
    payload: dict[str, Any],
    id_field: str,
) -> None:
    record_id = str(payload.get(id_field, ""))
    if not record_id:
        record_id = _id_from_text(path.name) or ""
    if not record_id:
        duplicates.append({"store": store, "path": _display_path(path), "reason": f"missing {id_field}"})
        return
    if record_id in records:
        duplicates.append({"store": store, "id": record_id, "path": _display_path(path), "existing_path": records[record_id]["path"]})
        return
    records[record_id] = {"store": store, "id": record_id, "path": _display_path(path), "payload": payload}


def _collect_boundary_violations(registry: dict[str, dict[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for store, records in registry.items():
        for record in records.values():
            payload = record["payload"]
            for field_name in BOUNDARY_TRUE_FIELDS[store]:
                if payload.get(field_name) is True:
                    violations.append({
                        "store": store,
                        "id": record["id"],
                        "field": field_name,
                        "path": record["path"],
                        "reason": f"{store} local demo payload cannot set {field_name}=true in Phase 23C.",
                    })
    return violations


def _check_promoted_assets(
    registry: dict[str, dict[str, dict[str, Any]]],
    checked_refs: list[dict[str, Any]],
    validated_links: list[dict[str, Any]],
    external_refs: list[dict[str, Any]],
    missing_refs: list[dict[str, Any]],
    type_mismatches: list[dict[str, Any]],
    *,
    source_store: str,
    source_id: str,
    value: Any,
) -> None:
    _check_allowed_store_refs(
        registry,
        checked_refs,
        validated_links,
        external_refs,
        missing_refs,
        type_mismatches,
        source_store=source_store,
        source_id=source_id,
        field_name="promoted_assets",
        value=value,
        allowed_stores=PROMOTED_ASSET_TARGET_STORES,
        boundary_reason="Archive promoted_assets may target only Knowledge or Causal local records, never Archive.",
    )


def _check_allowed_store_refs(
    registry: dict[str, dict[str, dict[str, Any]]],
    checked_refs: list[dict[str, Any]],
    validated_links: list[dict[str, Any]],
    external_refs: list[dict[str, Any]],
    missing_refs: list[dict[str, Any]],
    type_mismatches: list[dict[str, Any]],
    *,
    source_store: str,
    source_id: str,
    field_name: str,
    value: Any,
    allowed_stores: set[str],
    boundary_reason: str,
) -> None:
    for raw in _as_list(value):
        ref = _parse_ref(raw, expected_store=None)
        base = {
            "source_store": source_store,
            "source_id": source_id,
            "field": field_name,
            "raw": ref["raw"],
        }
        if ref["external"]:
            external_refs.append({**base, "reason": "external or non-local source reference; not a Phase 23C local typed reference"})
            continue
        checked = {**base, "target_store": ref["store"], "target_id": ref["id"]}
        checked_refs.append(checked)
        if ref["type_mismatch"]:
            type_mismatches.append({**checked, "reason": ref["type_mismatch"]})
            continue
        if ref["store"] not in allowed_stores:
            allowed = ", ".join(sorted(allowed_stores))
            type_mismatches.append({
                **checked,
                "reason": f"{boundary_reason} Allowed local target store(s): {allowed}; got {ref['store']}:{ref['id']}.",
            })
            continue
        if ref["store"] not in registry or ref["id"] not in registry[ref["store"]]:
            missing_refs.append({**checked, "reason": "typed local reference target does not exist"})
            continue
        validated_links.append({**checked, "target_path": registry[ref["store"]][ref["id"]]["path"]})


def _check_refs(
    registry: dict[str, dict[str, dict[str, Any]]],
    checked_refs: list[dict[str, Any]],
    validated_links: list[dict[str, Any]],
    external_refs: list[dict[str, Any]],
    missing_refs: list[dict[str, Any]],
    type_mismatches: list[dict[str, Any]],
    *,
    source_store: str,
    source_id: str,
    field_name: str,
    value: Any,
    expected_store: str | None,
) -> None:
    for raw in _as_list(value):
        _check_one_ref(
            registry,
            checked_refs,
            validated_links,
            external_refs,
            missing_refs,
            type_mismatches,
            source_store=source_store,
            source_id=source_id,
            field_name=field_name,
            raw=raw,
            expected_store=expected_store,
        )


def _check_one_ref(
    registry: dict[str, dict[str, dict[str, Any]]],
    checked_refs: list[dict[str, Any]],
    validated_links: list[dict[str, Any]],
    external_refs: list[dict[str, Any]],
    missing_refs: list[dict[str, Any]],
    type_mismatches: list[dict[str, Any]],
    *,
    source_store: str,
    source_id: str,
    field_name: str,
    raw: Any,
    expected_store: str | None,
) -> None:
    ref = _parse_ref(raw, expected_store=expected_store)
    base = {
        "source_store": source_store,
        "source_id": source_id,
        "field": field_name,
        "raw": ref["raw"],
    }
    if ref["external"]:
        external_refs.append({**base, "reason": "external or non-local source reference; not a Phase 23C local typed reference"})
        return
    checked = {**base, "target_store": ref["store"], "target_id": ref["id"]}
    checked_refs.append(checked)
    if ref["type_mismatch"]:
        type_mismatches.append({**checked, "reason": ref["type_mismatch"]})
        return
    if ref["store"] not in registry or ref["id"] not in registry[ref["store"]]:
        missing_refs.append({**checked, "reason": "typed local reference target does not exist"})
        return
    validated_links.append({**checked, "target_path": registry[ref["store"]][ref["id"]]["path"]})


def _check_request_expected_links(
    registry: dict[str, dict[str, dict[str, Any]]],
    checked_refs: list[dict[str, Any]],
    validated_links: list[dict[str, Any]],
    external_refs: list[dict[str, Any]],
    missing_refs: list[dict[str, Any]],
    type_mismatches: list[dict[str, Any]],
    request: dict[str, Any],
) -> None:
    for item in _as_list(request.get("expected_links", [])):
        if not isinstance(item, dict):
            external_refs.append({"source_store": "request", "source_id": request.get("request_id"), "field": "expected_links", "raw": item, "reason": "malformed expected link item"})
            continue
        from_store = _normalize_store(item.get("from_store"))
        from_id = str(item.get("from_id", ""))
        to_store = _normalize_store(item.get("to_store"))
        to_id = str(item.get("to_id", ""))
        link_type = str(item.get("link_type", "expected_link"))
        if from_store not in LOCAL_STORES or to_store not in LOCAL_STORES:
            type_mismatches.append({"source_store": "request", "source_id": request.get("request_id"), "field": "expected_links", "raw": item, "reason": "expected_links must use archive, knowledge, or causal stores"})
            continue
        if from_id not in registry[from_store]:
            missing_refs.append({"source_store": "request", "source_id": request.get("request_id"), "field": "expected_links", "raw": item, "target_store": from_store, "target_id": from_id, "reason": "expected link source does not exist"})
        _check_one_ref(
            registry,
            checked_refs,
            validated_links,
            external_refs,
            missing_refs,
            type_mismatches,
            source_store=from_store,
            source_id=from_id,
            field_name=f"expected_links:{link_type}",
            raw={"target_store": to_store, "target_id": to_id},
            expected_store=to_store,
        )


def _parse_ref(raw: Any, *, expected_store: str | None) -> dict[str, Any]:
    provided_store: str | None = None
    target_id: str | None = None
    raw_display = raw

    if isinstance(raw, dict):
        provided_store = _normalize_store(raw.get("target_store") or raw.get("store") or raw.get("target_type"))
        raw_value = raw.get("target_id") or raw.get("id") or raw.get("ref") or raw.get("path")
        raw_display = raw
    else:
        raw_value = raw

    if raw_value is None:
        return {"raw": raw_display, "external": True, "store": None, "id": None, "type_mismatch": None}

    text = str(raw_value).strip()
    typed_store, typed_body = _split_typed_ref(text)
    if typed_store:
        provided_store = typed_store
        text = typed_body

    target_id = _id_from_text(text)
    if target_id is None:
        return {"raw": raw_display, "external": True, "store": None, "id": None, "type_mismatch": None}

    inferred_store = ID_TO_STORE[target_id[0]]
    effective_store = provided_store or inferred_store
    mismatch: str | None = None
    if provided_store in LOCAL_STORES and provided_store != inferred_store:
        mismatch = f"reference ID {target_id} belongs to {inferred_store}, not declared store {provided_store}"
    if expected_store and effective_store != expected_store:
        mismatch = f"field expects {expected_store} reference, got {effective_store}:{target_id}"
    return {"raw": raw_display, "external": False, "store": effective_store, "id": target_id, "type_mismatch": mismatch}


def _split_typed_ref(text: str) -> tuple[str | None, str]:
    if ":" not in text:
        return None, text
    prefix, body = text.split(":", 1)
    store = _normalize_store(prefix.strip())
    if store in LOCAL_STORES:
        return store, body.strip()
    return None, text


def _id_from_text(text: str) -> str | None:
    clean = str(text).strip().replace("\\", "/")
    if ID_PATTERN.fullmatch(clean):
        return clean
    basename = clean.rsplit("/", 1)[-1]
    if basename.endswith(".yaml"):
        basename = basename[:-5]
    if ID_PATTERN.fullmatch(basename):
        return basename
    return None


def _normalize_store(value: Any) -> str | None:
    if value is None:
        return None
    return STORE_ALIASES.get(str(value).strip().lower())


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _display_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def _result(
    archive_root: Path,
    knowledge_root: Path,
    causal_root: Path,
    *,
    status: str,
    decision: str,
    reason: str,
    archive_event_count: int = 0,
    knowledge_entry_count: int = 0,
    causal_fact_count: int = 0,
    checked_reference_count: int = 0,
    validated_links: list[dict[str, Any]] | None = None,
    external_refs: list[dict[str, Any]] | None = None,
    missing_refs: list[dict[str, Any]] | None = None,
    type_mismatches: list[dict[str, Any]] | None = None,
    store_boundary_violations: list[dict[str, Any]] | None = None,
    duplicate_ids: list[dict[str, Any]] | None = None,
    request_checked: bool = False,
) -> ThreeStoreLinkageResult:
    return ThreeStoreLinkageResult(
        three_store_linkage_result_id=f"three-store-linkage-{uuid4().hex}",
        phase="phase23c_three_store_linkage_integrity",
        status=status,
        decision=decision,
        reason=reason,
        archive_root=str(archive_root),
        knowledge_root=str(knowledge_root),
        causal_root=str(causal_root),
        archive_event_count=archive_event_count,
        knowledge_entry_count=knowledge_entry_count,
        causal_fact_count=causal_fact_count,
        checked_reference_count=checked_reference_count,
        validated_links=validated_links or [],
        external_refs=external_refs or [],
        missing_refs=missing_refs or [],
        type_mismatches=type_mismatches or [],
        store_boundary_violations=store_boundary_violations or [],
        duplicate_ids=duplicate_ids or [],
        request_checked=request_checked,
    )
