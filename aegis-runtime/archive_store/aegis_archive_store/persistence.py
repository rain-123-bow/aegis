from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

ACCEPTED_CANDIDATE_TYPES = {"archive_event", "archive_event_candidate"}
TRUTH_STATUSES = {"knowledge", "causal", "global_truth", "active_global_truth", "canonical_global_truth"}
DIRECT_WRITE_FIELDS = (
    "production_archive_persistence",
    "production_archive_write",
    "archive_store_write_performed",
    "knowledge_store_write_performed",
    "causal_store_write_performed",
    "causal_truth_mutation",
    "ordinary_agent_direct_write_allowed",
    "direct_archive_write",
)


class ArchivePersistenceError(ValueError):
    """Raised when Phase 23A archive persistence input is malformed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ArchivePersistenceResult:
    archive_persistence_result_id: str
    phase: str
    status: str
    decision: str
    reason: str
    archive_root: str
    event_id: str | None
    segment_id: str | None
    operation: str
    written_files: list[str] = field(default_factory=list)
    sealed_segment_ids: list[str] = field(default_factory=list)
    new_active_segment_id: str | None = None
    rollback_ref: str | None = None
    artifact_manifest_updated: bool = False
    index_updated: bool = False
    changelog_written: bool = False
    segment_sealed: bool = False
    compressed_payload_written: bool = False
    production_archive_persistence: bool = False
    production_encryption: bool = False
    remote_sync_performed: bool = False
    knowledge_store_write_performed: bool = False
    causal_store_write_performed: bool = False
    archive_produces_truth: bool = False
    ordinary_agent_direct_write_allowed: bool = False
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "archive_persistence_result_id": self.archive_persistence_result_id,
            "phase": self.phase,
            "status": self.status,
            "decision": self.decision,
            "reason": self.reason,
            "archive_root": self.archive_root,
            "event_id": self.event_id,
            "segment_id": self.segment_id,
            "operation": self.operation,
            "written_files": list(self.written_files),
            "sealed_segment_ids": list(self.sealed_segment_ids),
            "new_active_segment_id": self.new_active_segment_id,
            "rollback_ref": self.rollback_ref,
            "artifact_manifest_updated": self.artifact_manifest_updated,
            "index_updated": self.index_updated,
            "changelog_written": self.changelog_written,
            "segment_sealed": self.segment_sealed,
            "compressed_payload_written": self.compressed_payload_written,
            "production_archive_persistence": self.production_archive_persistence,
            "production_encryption": self.production_encryption,
            "remote_sync_performed": self.remote_sync_performed,
            "knowledge_store_write_performed": self.knowledge_store_write_performed,
            "causal_store_write_performed": self.causal_store_write_performed,
            "archive_produces_truth": self.archive_produces_truth,
            "ordinary_agent_direct_write_allowed": self.ordinary_agent_direct_write_allowed,
            "created_at": self.created_at,
        }


def load_json_object(path: str | Path) -> dict[str, Any]:
    """Load Phase 23A JSON-formatted, YAML-compatible local demo files."""
    p = Path(path)
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArchivePersistenceError(f"archive event candidate file not found: {p}") from exc
    except json.JSONDecodeError as exc:
        raise ArchivePersistenceError(f"archive event candidate file is not valid JSON: {p}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ArchivePersistenceError("archive event candidate file must contain a JSON object")
    return payload


def write_json_compatible_yaml(path: Path, payload: Any) -> None:
    """Write indented JSON into `.yaml` paths as YAML-compatible demo payload."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def persist_archive_event_file(
    event_candidate_path: str | Path,
    *,
    archive_root: str | Path,
    max_events_per_segment: int = 1000,
    max_segment_size_bytes: int = 5_000_000,
) -> ArchivePersistenceResult:
    return persist_archive_event(
        load_json_object(event_candidate_path),
        archive_root=archive_root,
        source_ref=str(event_candidate_path),
        max_events_per_segment=max_events_per_segment,
        max_segment_size_bytes=max_segment_size_bytes,
    )


def persist_archive_event(
    event_candidate: dict[str, Any],
    *,
    archive_root: str | Path,
    source_ref: str | None = None,
    max_events_per_segment: int = 1000,
    max_segment_size_bytes: int = 5_000_000,
) -> ArchivePersistenceResult:
    if not isinstance(event_candidate, dict):
        raise ArchivePersistenceError("event_candidate must be a JSON object")
    archive_root_path = Path(archive_root).resolve()

    if max_events_per_segment < 1:
        raise ArchivePersistenceError("max_events_per_segment must be >= 1")
    if max_segment_size_bytes < 1:
        raise ArchivePersistenceError("max_segment_size_bytes must be >= 1")

    if _has_direct_write_attempt(event_candidate):
        return _rejected(archive_root_path, event_candidate, "Archive event attempts direct production or ordinary-agent write.")
    if str(event_candidate.get("candidate_type", "")) not in ACCEPTED_CANDIDATE_TYPES:
        return _rejected(archive_root_path, event_candidate, "Archive persistence accepts only archive_event_candidate input.")
    if event_candidate.get("truth_status") in TRUTH_STATUSES or event_candidate.get("target_store") in {"knowledge", "causal"}:
        return _rejected(archive_root_path, event_candidate, "Archive records history only and must reject truth/Knowledge/Causal status claims.")

    missing = _missing_event_fields(event_candidate)
    if missing:
        return _rejected(archive_root_path, event_candidate, f"Archive event missing required field(s): {', '.join(missing)}")

    event_payload_for_size = json.dumps(event_candidate, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    if len(event_payload_for_size) > max_segment_size_bytes:
        return _rejected(archive_root_path, event_candidate, "Archive event payload cannot fit into an empty active segment under max_segment_size_bytes.")

    # State cleanliness boundary: rejected candidates above must not create
    # archive layout files. The local demo Archive layout is created only after
    # admission checks pass and the event is known to be persistable.
    _ensure_layout(archive_root_path)

    index_path = archive_root_path / "index.yaml"
    index = _load_index(index_path)
    active_segment_id = _active_segment_id(index)
    sealed_segment_ids: list[str] = []
    written_files: list[str] = []
    previous_files: dict[str, str | None] = {}
    now = utc_now()

    active_segment_path = archive_root_path / "active" / active_segment_id
    _ensure_segment(active_segment_path, active_segment_id, previous_segment_id=index.get("last_sealed_segment_id"))
    segment_state = _load_segment_state(active_segment_path)

    if _segment_should_rollover(active_segment_path, segment_state, len(event_payload_for_size), max_events_per_segment, max_segment_size_bytes):
        sealed_id, sealed_written = _seal_segment(archive_root_path, active_segment_id, index, now=now)
        sealed_segment_ids.append(sealed_id)
        written_files.extend(sealed_written)
        index["last_sealed_segment_id"] = sealed_id
        active_segment_id = _next_segment_id(index)
        index["active_segment_id"] = active_segment_id
        active_segment_path = archive_root_path / "active" / active_segment_id
        _ensure_segment(active_segment_path, active_segment_id, previous_segment_id=sealed_id)
        segment_state = _load_segment_state(active_segment_path)

    event_id = _next_id(index, "next_event_id", "E")
    rollback_id = _next_id(index, "next_rollback_id", "R")
    event = _build_event(event_id, event_candidate, segment_id=active_segment_id, source_ref=source_ref, now=now)
    event_path = active_segment_path / "events" / f"{event_id}.yaml"
    if event_path.exists():
        return _rejected(archive_root_path, event_candidate, f"Target event file already exists: {_rel(archive_root_path, event_path)}")

    _remember_before(event_path, previous_files)
    write_json_compatible_yaml(event_path, event)
    written_files.append(_rel(archive_root_path, event_path))

    _update_segment_index(active_segment_path, event, previous_files, archive_root_path, written_files)
    _update_segment_state(active_segment_path, event, previous_files, archive_root_path, written_files)
    _update_artifact_manifest(archive_root_path, event, previous_files, written_files)
    _append_changelog(archive_root_path, event, previous_files, written_files)
    _update_global_index(index, event, active_segment_id, now=now)
    _remember_before(index_path, previous_files)
    write_json_compatible_yaml(index_path, index)
    written_files.append(_rel(archive_root_path, index_path))

    rollback_path = archive_root_path / "rollback" / f"{rollback_id}.yaml"
    previous_files_for_rollback = {
        _rel(archive_root_path, Path(path)): before for path, before in previous_files.items()
    }
    rollback = {
        "rollback_id": rollback_id,
        "created_at": now,
        "operation": "rollover_and_append" if sealed_segment_ids else "append_event",
        "event_id": event_id,
        "segment_id": active_segment_id,
        "source_ref": source_ref,
        "created_files": [path for path, before in previous_files_for_rollback.items() if before is None],
        "updated_files": [path for path, before in previous_files_for_rollback.items() if before is not None],
        "previous_file_contents": previous_files_for_rollback,
        "rollover_occurred": bool(sealed_segment_ids),
        "sealed_segment_ids": sealed_segment_ids,
        "new_active_segment_id": active_segment_id if sealed_segment_ids else None,
        "production_transaction": False,
    }
    write_json_compatible_yaml(rollback_path, rollback)
    written_files.append(_rel(archive_root_path, rollback_path))

    return ArchivePersistenceResult(
        archive_persistence_result_id=f"archive-persist-{uuid4().hex}",
        phase="phase23a_archive_segmented_persistence",
        status="persisted",
        decision="persisted",
        reason=f"Persisted archive event {event_id} into active segment {active_segment_id}.",
        archive_root=str(archive_root_path),
        event_id=event_id,
        segment_id=active_segment_id,
        operation="rollover_and_append" if sealed_segment_ids else "append_event",
        written_files=sorted(set(written_files)),
        sealed_segment_ids=sealed_segment_ids,
        new_active_segment_id=active_segment_id if sealed_segment_ids else None,
        rollback_ref=_rel(archive_root_path, rollback_path),
        artifact_manifest_updated=True,
        index_updated=True,
        changelog_written=True,
        segment_sealed=bool(sealed_segment_ids),
        compressed_payload_written=bool(sealed_segment_ids),
    )


def _ensure_layout(archive_root: Path) -> None:
    for sub in ("active", "sealed", "artifacts", "history", "rollback"):
        (archive_root / sub).mkdir(parents=True, exist_ok=True)
    changelog = archive_root / "history" / "changelog.md"
    if not changelog.exists():
        changelog.write_text("# Archive Changelog\n\n", encoding="utf-8")


def _load_index(index_path: Path) -> dict[str, Any]:
    if not index_path.exists():
        return {
            "version": "phase23a_demo_v1",
            "active_segment_id": "segment_0001",
            "last_sealed_segment_id": None,
            "next_segment_id": 2,
            "next_event_id": 1,
            "next_rollback_id": 1,
            "event_count": 0,
            "segments": [],
            "events": [],
            "updated_at": utc_now(),
            "production_index": False,
        }
    return load_json_object(index_path)


def _active_segment_id(index: dict[str, Any]) -> str:
    return str(index.get("active_segment_id") or "segment_0001")


def _next_segment_id(index: dict[str, Any]) -> str:
    value = int(index.get("next_segment_id", 1))
    index["next_segment_id"] = value + 1
    return f"segment_{value:04d}"


def _next_id(index: dict[str, Any], key: str, prefix: str) -> str:
    value = int(index.get(key, 1))
    index[key] = value + 1
    return f"{prefix}{value:04d}"


def _ensure_segment(segment_path: Path, segment_id: str, *, previous_segment_id: str | None) -> None:
    (segment_path / "events").mkdir(parents=True, exist_ok=True)
    state_path = segment_path / "segment_state.yaml"
    if not state_path.exists():
        write_json_compatible_yaml(state_path, {
            "segment_id": segment_id,
            "status": "active",
            "previous_segment_id": previous_segment_id,
            "event_count": 0,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "production_segment": False,
        })
    initial_index = {
            "segment_id": segment_id,
            "events": [],
            "task_ids": [],
            "event_types": [],
            "actors": [],
            "artifact_refs": [],
            "production_index": False,
    }
    for index_name in ("segment_index.yaml", "index.yaml"):
        segment_index = segment_path / index_name
        if not segment_index.exists():
            write_json_compatible_yaml(segment_index, initial_index)


def _load_segment_state(segment_path: Path) -> dict[str, Any]:
    return load_json_object(segment_path / "segment_state.yaml")


def _segment_size_bytes(segment_path: Path) -> int:
    if not segment_path.exists():
        return 0
    total = 0
    for path in segment_path.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total


def _segment_should_rollover(segment_path: Path, state: dict[str, Any], event_size: int, max_events: int, max_size: int) -> bool:
    event_count = int(state.get("event_count", 0))
    if event_count >= max_events:
        return True
    if event_count > 0 and _segment_size_bytes(segment_path) + event_size > max_size:
        return True
    return False


def _seal_segment(archive_root: Path, segment_id: str, index: dict[str, Any], *, now: str) -> tuple[str, list[str]]:
    active_path = archive_root / "active" / segment_id
    sealed_path = archive_root / "sealed" / segment_id
    sealed_path.mkdir(parents=True, exist_ok=True)
    events = _segment_events(active_path)
    summary = {
        "segment_id": segment_id,
        "closed_at": now,
        "event_count": len(events),
        "task_ids": sorted({str(event.get("task_id")) for event in events if event.get("task_id")}),
        "event_types": sorted({str(event.get("event_type")) for event in events if event.get("event_type")}),
        "actors": sorted({str(event.get("actor")) for event in events if event.get("actor")}),
        "artifact_refs": sorted({ref for event in events for ref in _as_string_list(event.get("artifact_refs", []))}),
        "developer_decision_events": [event["event_id"] for event in events if event.get("event_type") == "developer_decision"],
        "production_summary": False,
    }
    sealed_index = {
        "segment_id": segment_id,
        "events": [{"event_id": event["event_id"], "event_type": event.get("event_type"), "task_id": event.get("task_id"), "actor": event.get("actor")} for event in events],
        "production_index": False,
    }
    summary_path = sealed_path / "summary.yaml"
    index_path = sealed_path / "index.yaml"
    write_json_compatible_yaml(summary_path, summary)
    write_json_compatible_yaml(index_path, sealed_index)
    zip_path = sealed_path / "compressed_payload.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in active_path.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(active_path))
    payload_hash = _hash_file(zip_path)
    summary_hash = _hash_file(summary_path)
    index_hash = _hash_file(index_path)
    seal = {
        "segment_id": segment_id,
        "previous_segment_id": index.get("last_sealed_segment_id"),
        "closed_at": now,
        "event_count": len(events),
        "payload_hash": payload_hash,
        "summary_hash": summary_hash,
        "index_hash": index_hash,
        "compression_method": "zip",
        "production_seal": False,
    }
    seal_path = sealed_path / "seal.yaml"
    write_json_compatible_yaml(seal_path, seal)
    shutil.rmtree(active_path)
    return segment_id, [_rel(archive_root, summary_path), _rel(archive_root, index_path), _rel(archive_root, zip_path), _rel(archive_root, seal_path)]


def _segment_events(segment_path: Path) -> list[dict[str, Any]]:
    events = []
    for path in sorted((segment_path / "events").glob("E*.yaml")):
        events.append(load_json_object(path))
    return events


def _build_event(event_id: str, candidate: dict[str, Any], *, segment_id: str, source_ref: str | None, now: str) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "candidate_id": candidate.get("candidate_id"),
        "candidate_type": "archive_event",
        "segment_id": segment_id,
        "event_type": candidate.get("event_type"),
        "actor": candidate.get("actor"),
        "occurred_at": candidate.get("occurred_at"),
        "recorded_at": now,
        "task_id": candidate.get("task_id"),
        "scope": candidate.get("scope"),
        "responsibility_boundary": candidate.get("responsibility_boundary"),
        "alternatives": _as_string_list(candidate.get("alternatives", [])),
        "master_recommendation": candidate.get("master_recommendation"),
        "developer_selection": candidate.get("developer_selection"),
        "uncertainty_reason": candidate.get("uncertainty_reason"),
        "decision_refs": _as_string_list(candidate.get("decision_refs", [])),
        "artifact_refs": _as_string_list(candidate.get("artifact_refs", candidate.get("evidence_refs", []))),
        "evidence_refs": _as_string_list(candidate.get("evidence_refs", [])),
        "promoted_to_knowledge": _as_string_list(candidate.get("promoted_to_knowledge", [])),
        "promoted_to_causal": _as_string_list(candidate.get("promoted_to_causal", [])),
        "source_ref": source_ref,
        "archive_produces_truth": False,
        "production_archive_persistence": False,
    }


def _update_segment_index(segment_path: Path, event: dict[str, Any], previous_files: dict[str, str | None], archive_root: Path, written_files: list[str]) -> None:
    path = segment_path / "segment_index.yaml"
    _remember_before(path, previous_files)
    segment_index = load_json_object(path)
    segment_index["events"] = list(segment_index.get("events", [])) + [{
        "event_id": event["event_id"],
        "event_type": event.get("event_type"),
        "task_id": event.get("task_id"),
        "actor": event.get("actor"),
    }]
    for key, value in {
        "task_ids": event.get("task_id"),
        "event_types": event.get("event_type"),
        "actors": event.get("actor"),
    }.items():
        items = set(segment_index.get(key, []))
        if value:
            items.add(str(value))
        segment_index[key] = sorted(items)
    artifacts = set(segment_index.get("artifact_refs", []))
    artifacts.update(_as_string_list(event.get("artifact_refs", [])))
    segment_index["artifact_refs"] = sorted(artifacts)
    write_json_compatible_yaml(path, segment_index)
    written_files.append(_rel(archive_root, path))
    alias_path = segment_path / "index.yaml"
    _remember_before(alias_path, previous_files)
    write_json_compatible_yaml(alias_path, segment_index)
    written_files.append(_rel(archive_root, alias_path))


def _update_segment_state(segment_path: Path, event: dict[str, Any], previous_files: dict[str, str | None], archive_root: Path, written_files: list[str]) -> None:
    path = segment_path / "segment_state.yaml"
    _remember_before(path, previous_files)
    state = load_json_object(path)
    state["event_count"] = int(state.get("event_count", 0)) + 1
    state["updated_at"] = utc_now()
    state["size_bytes"] = _segment_size_bytes(segment_path)
    write_json_compatible_yaml(path, state)
    written_files.append(_rel(archive_root, path))


def _update_artifact_manifest(archive_root: Path, event: dict[str, Any], previous_files: dict[str, str | None], written_files: list[str]) -> None:
    path = archive_root / "artifacts" / "manifest.yaml"
    _remember_before(path, previous_files)
    if path.exists():
        manifest = load_json_object(path)
    else:
        manifest = {"version": "phase23a_demo_v1", "artifacts": [], "production_manifest": False}
    artifacts = list(manifest.get("artifacts", []))
    for ref in _as_string_list(event.get("artifact_refs", [])):
        artifacts.append({"ref": ref, "event_id": event["event_id"], "segment_id": event["segment_id"]})
    manifest["artifacts"] = artifacts
    manifest["updated_at"] = utc_now()
    write_json_compatible_yaml(path, manifest)
    written_files.append(_rel(archive_root, path))


def _append_changelog(archive_root: Path, event: dict[str, Any], previous_files: dict[str, str | None], written_files: list[str]) -> None:
    path = archive_root / "history" / "changelog.md"
    _remember_before(path, previous_files)
    lines = [
        f"## {event['event_id']} — {event.get('event_type')}",
        "",
        f"- segment_id: {event['segment_id']}",
        f"- actor: {event.get('actor')}",
        f"- occurred_at: {event.get('occurred_at')}",
        f"- task_id: {event.get('task_id')}",
        f"- scope: {event.get('scope')}",
        f"- archive_produces_truth: {event.get('archive_produces_truth')}",
        "",
    ]
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    written_files.append(_rel(archive_root, path))


def _update_global_index(index: dict[str, Any], event: dict[str, Any], segment_id: str, *, now: str) -> None:
    events = list(index.get("events", []))
    events.append({"event_id": event["event_id"], "segment_id": segment_id, "event_type": event.get("event_type"), "task_id": event.get("task_id"), "actor": event.get("actor")})
    index["events"] = events
    segments = {seg.get("segment_id"): seg for seg in index.get("segments", [])}
    segments[segment_id] = {"segment_id": segment_id, "status": "active", "event_count": len([evt for evt in events if evt["segment_id"] == segment_id])}
    for seg_id in list(segments):
        if seg_id == index.get("last_sealed_segment_id"):
            segments[seg_id]["status"] = "sealed"
    index["segments"] = [segments[key] for key in sorted(segments)]
    index["event_count"] = len(events)
    index["updated_at"] = now
    index["production_index"] = False


def _missing_event_fields(candidate: dict[str, Any]) -> list[str]:
    missing = []
    for field_name in ("event_type", "actor", "occurred_at", "scope"):
        if not str(candidate.get(field_name, "")).strip():
            missing.append(field_name)
    if not _as_string_list(candidate.get("evidence_refs", candidate.get("artifact_refs", []))):
        missing.append("evidence_refs")
    return missing


def _has_direct_write_attempt(candidate: dict[str, Any]) -> bool:
    return any(candidate.get(field) is True for field in DIRECT_WRITE_FIELDS)


def _remember_before(path: Path, previous_files: dict[str, str | None]) -> None:
    key = str(path)
    if key in previous_files:
        return
    previous_files[key] = path.read_text(encoding="utf-8") if path.exists() else None


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, str) and item:
                out.append(item)
            elif isinstance(item, dict):
                ref = item.get("ref") or item.get("path") or item.get("id")
                if isinstance(ref, str) and ref:
                    out.append(ref)
            else:
                raise ArchivePersistenceError("expected list entries to be strings or objects with ref/path/id")
        return out
    raise ArchivePersistenceError("expected string list")


def _rel(root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def _rejected(archive_root: Path, event_candidate: dict[str, Any], reason: str) -> ArchivePersistenceResult:
    return ArchivePersistenceResult(
        archive_persistence_result_id=f"archive-persist-{uuid4().hex}",
        phase="phase23a_archive_segmented_persistence",
        status="rejected",
        decision="rejected",
        reason=reason,
        archive_root=str(archive_root.resolve()),
        event_id=None,
        segment_id=None,
        operation="rejected",
    )
