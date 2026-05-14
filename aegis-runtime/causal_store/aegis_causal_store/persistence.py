from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

PERSISTABLE_DECISIONS = {
    "stage_canonical_merge_candidate": "add_fact",
    "stage_scope_limited_merge_candidate": "scope_limited_add",
    "stage_supersession_candidate": "supersede",
    "stage_invalidation_candidate": "invalidate",
}

REJECTED_DECISIONS = {
    "developer_decision_required",
    "needs_more_evidence",
    "needs_debate",
    "reject_candidate",
    "reject_direct_merge_or_store_write",
}

DIRECT_WRITE_FIELDS = (
    "canonical_global_merge_performed",
    "production_store_write_performed",
    "causal_store_write_performed",
    "production_persistence",
    "global_causal_truth_merge_performed",
    "remote_sync_performed",
)


class CausalStorePersistenceError(ValueError):
    """Raised when Phase 22C persistence input is malformed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CausalStorePersistenceResult:
    persistence_result_id: str
    phase: str
    status: str
    decision: str
    reason: str
    source_review_decision_id: str
    source_decision: str
    fact_id: str | None
    operation: str
    added_facts: list[str] = field(default_factory=list)
    updated_facts: list[str] = field(default_factory=list)
    written_files: list[str] = field(default_factory=list)
    change_record_id: str | None = None
    snapshot_id: str | None = None
    rollback_ref: str | None = None
    semantic_changelog_written: bool = False
    index_updated: bool = False
    snapshot_written: bool = False
    rollback_metadata_written: bool = False
    production_persistence: bool = False
    global_causal_truth_merge_performed: bool = False
    remote_sync_performed: bool = False
    encryption_performed: bool = False
    production_encryption: bool = False
    archive_store_write_performed: bool = False
    knowledge_store_write_performed: bool = False
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "persistence_result_id": self.persistence_result_id,
            "phase": self.phase,
            "status": self.status,
            "decision": self.decision,
            "reason": self.reason,
            "source_review_decision_id": self.source_review_decision_id,
            "source_decision": self.source_decision,
            "fact_id": self.fact_id,
            "operation": self.operation,
            "added_facts": list(self.added_facts),
            "updated_facts": list(self.updated_facts),
            "written_files": list(self.written_files),
            "change_record_id": self.change_record_id,
            "snapshot_id": self.snapshot_id,
            "rollback_ref": self.rollback_ref,
            "semantic_changelog_written": self.semantic_changelog_written,
            "index_updated": self.index_updated,
            "snapshot_written": self.snapshot_written,
            "rollback_metadata_written": self.rollback_metadata_written,
            "production_persistence": self.production_persistence,
            "global_causal_truth_merge_performed": self.global_causal_truth_merge_performed,
            "remote_sync_performed": self.remote_sync_performed,
            "encryption_performed": self.encryption_performed,
            "production_encryption": self.production_encryption,
            "archive_store_write_performed": self.archive_store_write_performed,
            "knowledge_store_write_performed": self.knowledge_store_write_performed,
            "created_at": self.created_at,
        }


def load_json_object(path: str | Path) -> dict[str, Any]:
    """Load Phase 22C JSON-formatted, YAML-compatible local demo files.

    Phase 22C keeps the historical Aegis `.yaml` file names for causal facts,
    index, snapshots, changes, and rollback records. The local demo runtime
    serializes those files as indented JSON because JSON is a YAML subset and
    avoids adding a YAML parser dependency. Consumers of this runtime must parse
    the files with JSON tooling unless a later production backend replaces the
    serialization format.
    """
    p = Path(path)
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CausalStorePersistenceError(f"review decision file not found: {p}") from exc
    except json.JSONDecodeError as exc:
        raise CausalStorePersistenceError(f"review decision file is not valid JSON: {p}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CausalStorePersistenceError("review decision file must contain a JSON object")
    return payload


def write_json_compatible_yaml(path: Path, payload: Any) -> None:
    """Write indented JSON into `.yaml` paths as YAML-compatible demo payload."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def persist_review_decision_file(review_decision_path: str | Path, causal_root: str | Path) -> CausalStorePersistenceResult:
    return persist_review_decision(load_json_object(review_decision_path), causal_root=causal_root, source_ref=str(review_decision_path))


def persist_review_decision(
    review_decision: dict[str, Any],
    *,
    causal_root: str | Path,
    source_ref: str | None = None,
) -> CausalStorePersistenceResult:
    if not isinstance(review_decision, dict):
        raise CausalStorePersistenceError("review_decision must be a JSON object")

    causal_root_path = Path(causal_root).resolve()
    _ensure_layout(causal_root_path)

    source_decision = str(review_decision.get("decision", ""))
    review_id = str(review_decision.get("review_decision_id") or review_decision.get("id") or "")
    if not review_id:
        return _rejected(review_decision, source_decision, "review_decision_id is required")

    if _has_forbidden_write_flag(review_decision):
        return _rejected(
            review_decision,
            source_decision,
            "Review decision attempts production persistence, direct store write, or global causal merge.",
        )

    if source_decision not in PERSISTABLE_DECISIONS:
        reason = "Review decision is not persistable by Phase 22C."
        if source_decision in REJECTED_DECISIONS:
            reason = f"Review decision {source_decision} must not be persisted."
        return _rejected(review_decision, source_decision, reason)

    missing = _missing_fact_fields(review_decision)
    if missing:
        return _rejected(review_decision, source_decision, f"Review decision missing required causal field(s): {', '.join(missing)}")

    operation = PERSISTABLE_DECISIONS[source_decision]
    refs_to_update = _as_string_list(review_decision.get("supersedes" if operation == "supersede" else "invalidates", []))
    if operation in {"supersede", "invalidate"} and not refs_to_update:
        return _rejected(review_decision, source_decision, f"{operation} operation requires referenced fact IDs")
    if operation in {"supersede", "invalidate"}:
        missing_refs = [ref for ref in refs_to_update if not (causal_root_path / "facts" / f"{ref}.yaml").is_file()]
        if missing_refs:
            return _rejected(
                review_decision,
                source_decision,
                f"{operation} operation references missing fact ID(s): {', '.join(missing_refs)}",
            )

    index_path = causal_root_path / "index.yaml"
    index = _load_index(index_path)
    previous_files: dict[str, str | None] = {}
    created_files: list[str] = []
    updated_files: list[str] = []

    fact_id = _next_id(index, "next_fact_id", "F")
    change_id = _next_id(index, "next_change_id", "C")
    snapshot_id = _next_id(index, "next_snapshot_id", "S")
    rollback_id = _next_id(index, "next_rollback_id", "R")

    now = utc_now()
    fact = _build_fact(fact_id, review_decision, operation=operation, now=now)
    fact_path = causal_root_path / "facts" / f"{fact_id}.yaml"
    if fact_path.exists():
        return _rejected(
            review_decision,
            source_decision,
            f"Target fact file already exists and would be overwritten: {_rel(causal_root_path, fact_path)}",
        )
    _remember_before(fact_path, previous_files)
    write_json_compatible_yaml(fact_path, fact)
    created_files.append(_rel(causal_root_path, fact_path))

    updated_fact_ids: list[str] = []
    if operation in {"supersede", "invalidate"}:
        for ref in refs_to_update:
            ref_path = causal_root_path / "facts" / f"{ref}.yaml"
            if ref_path.is_file():
                _remember_before(ref_path, previous_files)
                existing = load_json_object(ref_path)
                if operation == "supersede":
                    existing["status"] = "superseded"
                    existing["superseded_by"] = fact_id
                else:
                    existing["status"] = "invalidated"
                    existing["invalidated_by"] = fact_id
                existing["updated_at"] = now
                write_json_compatible_yaml(ref_path, existing)
                updated_files.append(_rel(causal_root_path, ref_path))
                updated_fact_ids.append(ref)

    _update_index(index, fact, updated_fact_ids=updated_fact_ids, operation=operation, now=now)
    _remember_before(index_path, previous_files)
    write_json_compatible_yaml(index_path, index)
    updated_files.append(_rel(causal_root_path, index_path))

    rollback_path = causal_root_path / "rollback" / f"{rollback_id}.yaml"
    rollback = {
        "rollback_id": rollback_id,
        "change_id": change_id,
        "created_at": now,
        "source_review_decision_id": review_id,
        "source_review_decision_ref": source_ref,
        "operation": operation,
        "affected_fact_ids": [fact_id] + updated_fact_ids,
        "created_files": list(created_files),
        "updated_files": list(updated_files),
        "previous_file_contents": previous_files,
        "production_transaction": False,
    }
    write_json_compatible_yaml(rollback_path, rollback)
    created_files.append(_rel(causal_root_path, rollback_path))

    change_path = causal_root_path / "history" / "changes" / f"{change_id}.yaml"
    change = {
        "change_id": change_id,
        "created_at": now,
        "source_review_decision_id": review_id,
        "source_review_decision_ref": source_ref,
        "operation": operation,
        "semantic_operations": _semantic_operations(operation, fact_id, review_decision),
        "added_facts": [fact_id],
        "updated_facts": updated_fact_ids,
        "reason": str(review_decision.get("why", "")),
        "evidence_refs": _as_string_list(review_decision.get("evidence_refs", [])),
        "affected_scopes": [str(review_decision.get("scope", ""))],
        "rollback_ref": _rel(causal_root_path, rollback_path),
        "git_commit_ref": review_decision.get("git_commit_ref"),
        "production_persistence": False,
        "global_causal_truth_merge_performed": False,
    }
    write_json_compatible_yaml(change_path, change)
    created_files.append(_rel(causal_root_path, change_path))

    changelog_path = causal_root_path / "history" / "changelog.md"
    _remember_before(changelog_path, previous_files)
    _append_changelog(changelog_path, change)
    updated_files.append(_rel(causal_root_path, changelog_path))

    snapshot_path = causal_root_path / "snapshots" / f"{snapshot_id}.yaml"
    snapshot = {
        "snapshot_id": snapshot_id,
        "created_at": now,
        "source_change_id": change_id,
        "index": index,
        "affected_facts": {fact_id: fact},
        "production_snapshot": False,
    }
    write_json_compatible_yaml(snapshot_path, snapshot)
    created_files.append(_rel(causal_root_path, snapshot_path))

    written_files = sorted(set(created_files + updated_files))
    return CausalStorePersistenceResult(
        persistence_result_id=f"persist-{uuid4().hex}",
        phase="phase22c_causal_store_persistence",
        status="persisted",
        decision="persisted",
        reason=f"Persisted {source_decision} as local demo causal fact {fact_id}.",
        source_review_decision_id=review_id,
        source_decision=source_decision,
        fact_id=fact_id,
        operation=operation,
        added_facts=[fact_id],
        updated_facts=updated_fact_ids,
        written_files=written_files,
        change_record_id=change_id,
        snapshot_id=snapshot_id,
        rollback_ref=_rel(causal_root_path, rollback_path),
        semantic_changelog_written=True,
        index_updated=True,
        snapshot_written=True,
        rollback_metadata_written=True,
    )


def _ensure_layout(causal_root: Path) -> None:
    for sub in ("facts", "history/changes", "snapshots", "rollback"):
        (causal_root / sub).mkdir(parents=True, exist_ok=True)
    changelog = causal_root / "history" / "changelog.md"
    if not changelog.exists():
        changelog.write_text("# Causal Semantic Changelog\n\n", encoding="utf-8")


def _load_index(index_path: Path) -> dict[str, Any]:
    if not index_path.exists():
        return {
            "version": "phase22c_demo_v1",
            "fact_count": 0,
            "next_fact_id": 1,
            "next_change_id": 1,
            "next_snapshot_id": 1,
            "next_rollback_id": 1,
            "facts": [],
            "updated_at": utc_now(),
            "production_index": False,
        }
    return load_json_object(index_path)


def _next_id(index: dict[str, Any], key: str, prefix: str) -> str:
    value = int(index.get(key, 1))
    index[key] = value + 1
    return f"{prefix}{value:04d}"


def _missing_fact_fields(review_decision: dict[str, Any]) -> list[str]:
    missing = []
    for field_name in ("candidate_statement", "why", "scope"):
        if not str(review_decision.get(field_name, "")).strip():
            missing.append(field_name)
    if not _as_string_list(review_decision.get("assumptions", [])):
        missing.append("assumptions")
    if not _as_string_list(review_decision.get("evidence_refs", [])):
        missing.append("evidence_refs")
    return missing


def _has_forbidden_write_flag(payload: dict[str, Any]) -> bool:
    return any(payload.get(field) is True for field in DIRECT_WRITE_FIELDS)


def _build_fact(fact_id: str, review_decision: dict[str, Any], *, operation: str, now: str) -> dict[str, Any]:
    accepted_scope = review_decision.get("accepted_scope") if operation == "scope_limited_add" else None
    scope = str(accepted_scope or review_decision["scope"])
    return {
        "id": fact_id,
        "statement": str(review_decision["candidate_statement"]),
        "why": str(review_decision["why"]),
        "evidence": _as_string_list(review_decision.get("evidence_refs", [])),
        "scope": scope,
        "original_scope": review_decision.get("scope") if accepted_scope else None,
        "accepted_scope": accepted_scope,
        "assumptions": _as_string_list(review_decision.get("assumptions", [])),
        "depends_on": _as_string_list(review_decision.get("depends_on", [])),
        "supersedes": _as_string_list(review_decision.get("supersedes", [])),
        "invalidates": _as_string_list(review_decision.get("invalidates", [])),
        "confidence": review_decision.get("master_confidence", {}),
        "source_origin": review_decision.get("source_origin"),
        "source_review_decision_id": review_decision.get("review_decision_id"),
        "source_decision": review_decision.get("decision"),
        "operation": operation,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "production_persistence": False,
        "global_causal_truth_merge_performed": False,
    }


def _update_index(index: dict[str, Any], fact: dict[str, Any], *, updated_fact_ids: list[str], operation: str, now: str) -> None:
    facts = list(index.get("facts", []))
    facts = [entry for entry in facts if entry.get("id") != fact["id"]]
    for entry in facts:
        if entry.get("id") in updated_fact_ids:
            if operation == "supersede":
                entry["status"] = "superseded"
            elif operation == "invalidate":
                entry["status"] = "invalidated"
            entry["updated_at"] = now
    facts.append({
        "id": fact["id"],
        "statement": fact["statement"],
        "scope": fact["scope"],
        "status": fact["status"],
        "source_review_decision_id": fact["source_review_decision_id"],
        "updated_at": now,
    })
    index["facts"] = sorted(facts, key=lambda item: item["id"])
    index["fact_count"] = len(index["facts"])
    index["updated_at"] = now
    index["production_index"] = False


def _semantic_operations(operation: str, fact_id: str, review_decision: dict[str, Any]) -> list[dict[str, Any]]:
    ops = [{"op": "add_fact", "fact_id": fact_id, "statement": review_decision.get("candidate_statement")}]
    if operation == "supersede":
        for ref in _as_string_list(review_decision.get("supersedes", [])):
            ops.append({"op": "supersede_fact", "fact_id": ref, "by": fact_id})
    if operation == "invalidate":
        for ref in _as_string_list(review_decision.get("invalidates", [])):
            ops.append({"op": "invalidate_fact", "fact_id": ref, "by": fact_id})
    return ops


def _append_changelog(path: Path, change: dict[str, Any]) -> None:
    lines = [
        f"## {change['change_id']} — {change['operation']}",
        "",
        f"- created_at: {change['created_at']}",
        f"- source_review_decision_id: {change['source_review_decision_id']}",
        f"- added_facts: {', '.join(change['added_facts']) if change['added_facts'] else 'none'}",
        f"- updated_facts: {', '.join(change['updated_facts']) if change['updated_facts'] else 'none'}",
        f"- affected_scopes: {', '.join(change['affected_scopes'])}",
        f"- rollback_ref: {change['rollback_ref']}",
        f"- reason: {change['reason']}",
        "",
    ]
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


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
                raise CausalStorePersistenceError("expected list entries to be strings or objects with id/ref/path")
        return output
    raise CausalStorePersistenceError("expected string list")


def _rel(root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def _rejected(review_decision: dict[str, Any], source_decision: str, reason: str) -> CausalStorePersistenceResult:
    return CausalStorePersistenceResult(
        persistence_result_id=f"persist-{uuid4().hex}",
        phase="phase22c_causal_store_persistence",
        status="rejected",
        decision="rejected",
        reason=reason,
        source_review_decision_id=str(review_decision.get("review_decision_id", "")),
        source_decision=source_decision,
        fact_id=None,
        operation="rejected",
    )
