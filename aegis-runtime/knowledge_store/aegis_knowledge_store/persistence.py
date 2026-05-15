from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

ACCEPTED_CANDIDATE_TYPES = {"knowledge", "knowledge_candidate"}
PERSISTABLE_OPERATIONS = {
    "add": "add_entry",
    "add_entry": "add_entry",
    "update": "update_entry",
    "update_entry": "update_entry",
    "supersede": "supersede_entry",
    "supersede_entry": "supersede_entry",
    "deprecate": "deprecate_entry",
    "deprecate_entry": "deprecate_entry",
}
DIRECT_WRITE_FIELDS = (
    "production_knowledge_persistence",
    "production_store_write_performed",
    "archive_store_write_performed",
    "causal_store_write_performed",
    "knowledge_store_write_performed",
    "global_causal_truth_mutation",
    "causal_truth_mutation",
    "direct_global_write",
    "write_global_truth",
    "ordinary_agent_direct_write_allowed",
)
TRUTH_STATUSES = {"causal", "global_truth", "active_global_truth", "canonical_global_truth"}
CAUSAL_SHAPE_FIELDS = {"why", "depends_on", "invalidates", "causal_chain"}
CAUSAL_TEXT_MARKERS = (
    " because ",
    " therefore ",
    " thus ",
    " hence ",
    "所以",
    "因为",
    "因此",
    "导致",
)


class KnowledgePersistenceError(ValueError):
    """Raised when Phase 23B knowledge persistence input is malformed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class KnowledgePersistenceResult:
    knowledge_persistence_result_id: str
    phase: str
    status: str
    decision: str
    reason: str
    knowledge_root: str
    entry_id: str | None
    operation: str
    written_files: list[str] = field(default_factory=list)
    change_record_id: str | None = None
    rollback_ref: str | None = None
    index_updated: bool = False
    changelog_written: bool = False
    production_knowledge_persistence: bool = False
    production_encryption: bool = False
    remote_sync_performed: bool = False
    archive_store_write_performed: bool = False
    causal_store_write_performed: bool = False
    knowledge_produces_causal_truth: bool = False
    ordinary_agent_direct_write_allowed: bool = False
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge_persistence_result_id": self.knowledge_persistence_result_id,
            "phase": self.phase,
            "status": self.status,
            "decision": self.decision,
            "reason": self.reason,
            "knowledge_root": self.knowledge_root,
            "entry_id": self.entry_id,
            "operation": self.operation,
            "written_files": list(self.written_files),
            "change_record_id": self.change_record_id,
            "rollback_ref": self.rollback_ref,
            "index_updated": self.index_updated,
            "changelog_written": self.changelog_written,
            "production_knowledge_persistence": self.production_knowledge_persistence,
            "production_encryption": self.production_encryption,
            "remote_sync_performed": self.remote_sync_performed,
            "archive_store_write_performed": self.archive_store_write_performed,
            "causal_store_write_performed": self.causal_store_write_performed,
            "knowledge_produces_causal_truth": self.knowledge_produces_causal_truth,
            "ordinary_agent_direct_write_allowed": self.ordinary_agent_direct_write_allowed,
            "created_at": self.created_at,
        }


def load_json_object(path: str | Path) -> dict[str, Any]:
    """Load Phase 23B JSON-formatted, YAML-compatible local demo files."""
    p = Path(path)
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise KnowledgePersistenceError(f"knowledge candidate file not found: {p}") from exc
    except json.JSONDecodeError as exc:
        raise KnowledgePersistenceError(f"knowledge candidate file is not valid JSON: {p}: {exc}") from exc
    if not isinstance(payload, dict):
        raise KnowledgePersistenceError("knowledge candidate file must contain a JSON object")
    return payload


def write_json_compatible_yaml(path: Path, payload: Any) -> None:
    """Write indented JSON into `.yaml` paths as YAML-compatible demo payload."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def persist_knowledge_candidate_file(candidate_path: str | Path, *, knowledge_root: str | Path) -> KnowledgePersistenceResult:
    return persist_knowledge_candidate(load_json_object(candidate_path), knowledge_root=knowledge_root, source_ref=str(candidate_path))


def persist_knowledge_candidate(
    candidate: dict[str, Any],
    *,
    knowledge_root: str | Path,
    source_ref: str | None = None,
) -> KnowledgePersistenceResult:
    if not isinstance(candidate, dict):
        raise KnowledgePersistenceError("candidate must be a JSON object")

    root = Path(knowledge_root).resolve()

    rejection_reason = _rejection_reason(candidate)
    if rejection_reason:
        return _rejected(root, candidate, rejection_reason)

    operation = _operation(candidate)
    refs_to_update = _refs_for_operation(candidate, operation)
    missing_refs = [ref for ref in refs_to_update if not (root / "entries" / f"{ref}.yaml").is_file()]
    if missing_refs:
        return _rejected(root, candidate, f"{operation} operation references missing Knowledge entry ID(s): {', '.join(missing_refs)}")

    # State cleanliness boundary: rejected candidates above must not create
    # knowledge layout files. The local demo Knowledge layout is created only
    # after the candidate passes admission checks and is persistable.
    _ensure_layout(root)

    index_path = root / "index.yaml"
    index = _load_index(index_path)
    previous_files: dict[str, str | None] = {}
    created_files: list[str] = []
    updated_files: list[str] = []

    change_id = _next_id(index, "next_change_id", "C")
    rollback_id = _next_id(index, "next_rollback_id", "R")
    now = utc_now()
    candidate_id = candidate.get("candidate_id") or candidate.get("id")

    updated_entry_ids: list[str] = []
    if operation == "update_entry":
        entry_id = refs_to_update[0]
        entry_path = root / "entries" / f"{entry_id}.yaml"
        _remember_before(entry_path, previous_files)
        existing_entry = load_json_object(entry_path)
        entry = _build_entry(entry_id, candidate, operation=operation, now=now)
        entry["created_at"] = existing_entry.get("created_at", now)
        entry["updated_from"] = existing_entry.get("id", entry_id)
        write_json_compatible_yaml(entry_path, entry)
        updated_files.append(_rel(root, entry_path))
        updated_entry_ids.append(entry_id)
    else:
        entry_id = _next_id(index, "next_entry_id", "K")
        entry = _build_entry(entry_id, candidate, operation=operation, now=now)
        entry_path = root / "entries" / f"{entry_id}.yaml"
        if entry_path.exists():
            return _rejected(root, candidate, f"Target Knowledge entry file already exists: {_rel(root, entry_path)}")
        _remember_before(entry_path, previous_files)
        write_json_compatible_yaml(entry_path, entry)
        created_files.append(_rel(root, entry_path))

    if operation in {"supersede_entry", "deprecate_entry"}:
        for ref in refs_to_update:
            ref_path = root / "entries" / f"{ref}.yaml"
            _remember_before(ref_path, previous_files)
            existing = load_json_object(ref_path)
            if operation == "supersede_entry":
                existing["status"] = "superseded"
                existing["superseded_by"] = entry_id
            else:
                existing["status"] = "deprecated"
                existing["deprecated_by"] = entry_id
            existing["updated_at"] = now
            write_json_compatible_yaml(ref_path, existing)
            updated_files.append(_rel(root, ref_path))
            updated_entry_ids.append(ref)

    _update_index(index, entry, updated_entry_ids=updated_entry_ids, operation=operation, now=now)
    _remember_before(index_path, previous_files)
    write_json_compatible_yaml(index_path, index)
    updated_files.append(_rel(root, index_path))

    rollback_path = root / "rollback" / f"{rollback_id}.yaml"
    previous_files_for_rollback = {_rel(root, Path(path)): before for path, before in previous_files.items()}
    rollback = {
        "rollback_id": rollback_id,
        "created_at": now,
        "operation": operation,
        "entry_id": entry_id,
        "candidate_id": candidate_id,
        "source_ref": source_ref,
        "created_files": [path for path, before in previous_files_for_rollback.items() if before is None],
        "updated_files": [path for path, before in previous_files_for_rollback.items() if before is not None],
        "previous_file_contents": previous_files_for_rollback,
        "production_transaction": False,
    }
    write_json_compatible_yaml(rollback_path, rollback)
    created_files.append(_rel(root, rollback_path))

    change_path = root / "history" / "changes" / f"{change_id}.yaml"
    change = {
        "change_id": change_id,
        "created_at": now,
        "operation": operation,
        "entry_id": entry_id,
        "candidate_id": candidate_id,
        "updated_entries": updated_entry_ids,
        "statement": entry["statement"],
        "reason": candidate.get("persistence_reason") or "Master-approved Knowledge candidate persisted.",
        "evidence_refs": _as_string_list(candidate.get("evidence_refs") or candidate.get("evidence") or []),
        "affected_scopes": [entry["scope"]],
        "version_context": entry["version_context"],
        "rollback_ref": _rel(root, rollback_path),
        "production_knowledge_persistence": False,
    }
    write_json_compatible_yaml(change_path, change)
    created_files.append(_rel(root, change_path))

    changelog_path = root / "history" / "changelog.md"
    _remember_before(changelog_path, previous_files)
    _append_changelog(changelog_path, change)
    updated_files.append(_rel(root, changelog_path))

    written_files = sorted(set(created_files + updated_files))
    return KnowledgePersistenceResult(
        knowledge_persistence_result_id=f"knowledge-persist-{uuid4().hex}",
        phase="phase23b_knowledge_store_persistence",
        status="persisted",
        decision="persisted",
        reason=f"Persisted Knowledge candidate as local demo Knowledge entry {entry_id}.",
        knowledge_root=str(root),
        entry_id=entry_id,
        operation=operation,
        written_files=written_files,
        change_record_id=change_id,
        rollback_ref=_rel(root, rollback_path),
        index_updated=True,
        changelog_written=True,
    )


def _ensure_layout(root: Path) -> None:
    for sub in ("entries", "history/changes", "rollback"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    changelog = root / "history" / "changelog.md"
    if not changelog.exists():
        changelog.write_text("# Knowledge Store Changelog\n\n", encoding="utf-8")


def _load_index(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "version": "phase23b_demo_v1",
            "entry_count": 0,
            "next_entry_id": 1,
            "next_change_id": 1,
            "next_rollback_id": 1,
            "entries": [],
            "updated_at": utc_now(),
            "production_index": False,
        }
    return load_json_object(path)


def _rejection_reason(candidate: dict[str, Any]) -> str | None:
    if _has_direct_write_attempt(candidate):
        return "Knowledge candidate attempts direct production, Archive, Causal, ordinary-agent, or global truth write."
    if str(candidate.get("candidate_type", "")) not in ACCEPTED_CANDIDATE_TYPES:
        return "Knowledge persistence accepts only knowledge_candidate input."
    if candidate.get("truth_status") in TRUTH_STATUSES or candidate.get("target_store") in {"archive", "causal"}:
        return "Knowledge Store must reject Archive/Causal/global truth status claims."
    if _archive_event_shape(candidate):
        return "Archive-shaped event input must go to Archive persistence, not Knowledge."
    operation_error = _operation_error(candidate)
    if operation_error:
        return operation_error
    if _causal_shape(candidate):
        return "Causal-shaped input must go to Causal admission/review, not Knowledge."
    if candidate.get("claim_status") == "developer_asserted" and candidate.get("master_verified") is not True:
        return "Developer-asserted claims require Master verification before Knowledge persistence."
    if candidate.get("master_verified") is not True:
        return "Knowledge candidate must be Master verified before persistence."
    missing = _missing_required_fields(candidate)
    if missing:
        return f"Knowledge candidate missing required field(s): {', '.join(missing)}"
    operation = _operation(candidate)
    if operation in {"update_entry", "supersede_entry", "deprecate_entry"} and not _refs_for_operation(candidate, operation):
        return f"{operation} operation requires referenced Knowledge entry IDs."
    return None


def _has_direct_write_attempt(candidate: dict[str, Any]) -> bool:
    return any(candidate.get(field) is True for field in DIRECT_WRITE_FIELDS)


def _archive_event_shape(candidate: dict[str, Any]) -> bool:
    if str(candidate.get("candidate_type", "")) in {"archive_event", "archive_event_candidate"}:
        return True
    # Archive-shaped input must route to Archive even if it also carries a
    # statement field. Otherwise mixed event+statement payloads can slip into
    # Knowledge as if they were neutral facts.
    return any(
        field in candidate
        for field in (
            "event_type",
            "occurred_at",
            "actor",
            "task_id",
            "lifecycle",
            "responsibility",
            "responsibility_boundary",
            "decision_refs",
        )
    )


def _causal_shape(candidate: dict[str, Any]) -> bool:
    if any(field in candidate for field in CAUSAL_SHAPE_FIELDS):
        return True
    # `supersedes` is allowed only when explicitly used as a Knowledge persistence operation.
    if "supersedes" in candidate and _operation(candidate) != "supersede_entry":
        return True
    statement = f" {candidate.get('statement', '')} ".lower()
    return any(marker in statement for marker in CAUSAL_TEXT_MARKERS)


def _missing_required_fields(candidate: dict[str, Any]) -> list[str]:
    missing = []
    for field_name in ("statement", "scope", "version_context"):
        if not str(candidate.get(field_name, "")).strip():
            missing.append(field_name)
    if not _as_string_list(candidate.get("evidence_refs") or candidate.get("evidence") or []):
        missing.append("evidence_refs")
    return missing


def _operation_error(candidate: dict[str, Any]) -> str | None:
    raw = str(candidate.get("operation") or "add")
    if raw not in PERSISTABLE_OPERATIONS:
        allowed = ", ".join(sorted(PERSISTABLE_OPERATIONS))
        return f"Unknown Knowledge persistence operation: {raw}. Allowed operations: {allowed}."
    return None


def _operation(candidate: dict[str, Any]) -> str:
    raw = str(candidate.get("operation") or "add")
    return PERSISTABLE_OPERATIONS[raw]


def _refs_for_operation(candidate: dict[str, Any], operation: str) -> list[str]:
    target_refs = _as_string_list(candidate.get("target_entry_id", []))
    if operation == "update_entry":
        return target_refs
    if operation == "supersede_entry":
        return _as_string_list(candidate.get("supersedes", [])) + target_refs
    if operation == "deprecate_entry":
        return _as_string_list(candidate.get("deprecates", [])) + target_refs
    return []


def _build_entry(entry_id: str, candidate: dict[str, Any], *, operation: str, now: str) -> dict[str, Any]:
    return {
        "id": entry_id,
        "statement": str(candidate["statement"]),
        "category": str(candidate.get("category", "fact")),
        "scope": str(candidate["scope"]),
        "version_context": str(candidate["version_context"]),
        "applicability": candidate.get("applicability"),
        "source": candidate.get("source"),
        "evidence_refs": _as_string_list(candidate.get("evidence_refs") or candidate.get("evidence") or []),
        "master_verified": True,
        "status": "active",
        "operation": operation,
        "supersedes": _as_string_list(candidate.get("supersedes", [])) + _as_string_list(candidate.get("target_entry_id", [])) if operation == "supersede_entry" else _as_string_list(candidate.get("supersedes", [])),
        "deprecates": _as_string_list(candidate.get("deprecates", [])) + _as_string_list(candidate.get("target_entry_id", [])) if operation == "deprecate_entry" else _as_string_list(candidate.get("deprecates", [])),
        "source_candidate_id": candidate.get("candidate_id") or candidate.get("id"),
        "created_at": now,
        "updated_at": now,
        "production_knowledge_persistence": False,
        "knowledge_produces_causal_truth": False,
    }


def _update_index(index: dict[str, Any], entry: dict[str, Any], *, updated_entry_ids: list[str], operation: str, now: str) -> None:
    entries = list(index.get("entries", []))
    replaced = False
    for existing in entries:
        if existing.get("id") in updated_entry_ids:
            if operation == "supersede_entry":
                existing["status"] = "superseded"
            elif operation == "deprecate_entry":
                existing["status"] = "deprecated"
            elif operation == "update_entry":
                existing.update({
                    "statement": entry["statement"],
                    "category": entry["category"],
                    "scope": entry["scope"],
                    "version_context": entry["version_context"],
                    "status": entry["status"],
                })
                replaced = True
            existing["updated_at"] = now
    if not replaced:
        entries.append({
            "id": entry["id"],
            "statement": entry["statement"],
            "category": entry["category"],
            "scope": entry["scope"],
            "version_context": entry["version_context"],
            "status": entry["status"],
            "updated_at": now,
        })
    index["entries"] = sorted(entries, key=lambda item: item["id"])
    index["entry_count"] = len(index["entries"])
    index["updated_at"] = now
    index["production_index"] = False


def _append_changelog(path: Path, change: dict[str, Any]) -> None:
    lines = [
        f"## {change['change_id']} — {change['operation']}",
        "",
        f"- created_at: {change['created_at']}",
        f"- entry_id: {change['entry_id']}",
        f"- updated_entries: {', '.join(change['updated_entries']) if change['updated_entries'] else 'none'}",
        f"- affected_scopes: {', '.join(change['affected_scopes'])}",
        f"- version_context: {change['version_context']}",
        f"- rollback_ref: {change['rollback_ref']}",
        f"- reason: {change['reason']}",
        "",
    ]
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def _next_id(index: dict[str, Any], key: str, prefix: str) -> str:
    value = int(index.get(key, 1))
    index[key] = value + 1
    return f"{prefix}{value:04d}"


def _remember_before(path: Path, previous_files: dict[str, str | None]) -> None:
    key = str(path)
    if key in previous_files:
        return
    if path.exists():
        previous_files[key] = path.read_text(encoding="utf-8")
    else:
        previous_files[key] = None


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        output = []
        for item in value:
            if isinstance(item, str) and item:
                output.append(item)
            elif isinstance(item, dict):
                ref = item.get("id") or item.get("ref") or item.get("path")
                if isinstance(ref, str) and ref:
                    output.append(ref)
            else:
                raise KnowledgePersistenceError("expected list entries to be strings or objects with id/ref/path")
        return output
    raise KnowledgePersistenceError("expected string list")


def _rel(root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def _rejected(root: Path, candidate: dict[str, Any], reason: str) -> KnowledgePersistenceResult:
    return KnowledgePersistenceResult(
        knowledge_persistence_result_id=f"knowledge-persist-{uuid4().hex}",
        phase="phase23b_knowledge_store_persistence",
        status="rejected",
        decision="rejected",
        reason=reason,
        knowledge_root=str(root),
        entry_id=None,
        operation="rejected",
    )
