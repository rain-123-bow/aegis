from __future__ import annotations

import hashlib
import json
from pathlib import Path

from aegis_archive_store import persist_archive_event, persist_archive_event_file


def _event(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "candidate_type": "archive_event_candidate",
        "event_type": "task_requested",
        "actor": "developer",
        "occurred_at": "2026-05-14T00:00:00Z",
        "scope": "Aegis Phase 23A",
        "task_id": "T-23A-001",
        "evidence_refs": ["chat:request"],
        "artifact_refs": ["artifact:demo"],
    }
    base.update(overrides)
    return base


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix().encode("utf-8")
            digest.update(rel)
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def test_archive_event_persists_to_active_segment(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    result = persist_archive_event(_event(), archive_root=root)
    payload = result.to_dict()

    assert payload["status"] == "persisted"
    assert payload["operation"] == "append_event"
    assert payload["production_archive_persistence"] is False
    assert payload["archive_produces_truth"] is False
    assert (root / "active" / "segment_0001" / "events" / "E0001.yaml").is_file()
    assert (root / "active" / "segment_0001" / "index.yaml").is_file()
    assert (root / "index.yaml").is_file()
    assert (root / "artifacts" / "manifest.yaml").is_file()
    assert (root / "history" / "changelog.md").is_file()
    assert (root / "rollback" / "R0001.yaml").is_file()


def test_developer_decision_event_persists_with_responsibility_boundary(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    event = _event(
        event_type="developer_decision",
        actor="developer",
        responsibility_boundary="Developer selected option B under unresolved uncertainty.",
        decision_refs=["decision:phase22b-dev-choice"],
        alternatives=["A", "B", "C"],
        master_recommendation="A",
        developer_selection="B",
        uncertainty_reason="No high-confidence support for a decisive causal conclusion.",
        task_id="T-DECISION",
    )
    result = persist_archive_event(event, archive_root=root)
    stored = _load(root / "active" / "segment_0001" / "events" / "E0001.yaml")

    assert result.status == "persisted"
    assert stored["event_type"] == "developer_decision"
    assert stored["responsibility_boundary"] == "Developer selected option B under unresolved uncertainty."
    assert stored["alternatives"] == ["A", "B", "C"]
    assert stored["master_recommendation"] == "A"
    assert stored["developer_selection"] == "B"
    assert stored["uncertainty_reason"] == "No high-confidence support for a decisive causal conclusion."
    assert stored["archive_produces_truth"] is False


def test_archive_rejects_truth_status_claim(tmp_path: Path) -> None:
    result = persist_archive_event(_event(truth_status="global_truth"), archive_root=tmp_path / "archive")

    assert result.status == "rejected"
    assert "truth" in result.reason.lower()


def test_archive_rejects_knowledge_or_causal_target_store(tmp_path: Path) -> None:
    result = persist_archive_event(_event(target_store="causal"), archive_root=tmp_path / "archive")

    assert result.status == "rejected"
    assert "knowledge" in result.reason.lower() or "causal" in result.reason.lower()


def test_archive_rejects_causal_truth_mutation_attempt(tmp_path: Path) -> None:
    result = persist_archive_event(_event(causal_truth_mutation=True), archive_root=tmp_path / "archive")

    assert result.status == "rejected"
    assert result.causal_store_write_performed is False


def test_missing_required_fields_are_rejected(tmp_path: Path) -> None:
    event = _event()
    event.pop("actor")
    result = persist_archive_event(event, archive_root=tmp_path / "archive")

    assert result.status == "rejected"
    assert "actor" in result.reason


def test_ordinary_agent_direct_write_is_rejected(tmp_path: Path) -> None:
    result = persist_archive_event(_event(ordinary_agent_direct_write_allowed=True), archive_root=tmp_path / "archive")

    assert result.status == "rejected"
    assert "ordinary-agent" in result.reason.lower() or "direct" in result.reason.lower()


def test_rollover_seals_full_active_segment_and_opens_new_one(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    first = persist_archive_event(_event(task_id="T1"), archive_root=root, max_events_per_segment=1)
    second = persist_archive_event(_event(task_id="T2"), archive_root=root, max_events_per_segment=1)

    assert first.status == "persisted"
    assert second.status == "persisted"
    assert second.segment_sealed is True
    assert second.sealed_segment_ids == ["segment_0001"]
    assert second.segment_id == "segment_0002"
    assert not (root / "active" / "segment_0001").exists()
    assert (root / "sealed" / "segment_0001" / "summary.yaml").is_file()
    assert (root / "sealed" / "segment_0001" / "index.yaml").is_file()
    assert (root / "sealed" / "segment_0001" / "seal.yaml").is_file()
    assert (root / "sealed" / "segment_0001" / "compressed_payload.zip").is_file()
    assert (root / "active" / "segment_0002" / "events" / "E0002.yaml").is_file()


def test_sealed_segment_summary_and_seal_are_written(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    persist_archive_event(_event(task_id="T1", event_type="developer_decision"), archive_root=root, max_events_per_segment=1)
    persist_archive_event(_event(task_id="T2"), archive_root=root, max_events_per_segment=1)
    summary = _load(root / "sealed" / "segment_0001" / "summary.yaml")
    seal = _load(root / "sealed" / "segment_0001" / "seal.yaml")

    assert summary["event_count"] == 1
    assert summary["developer_decision_events"] == ["E0001"]
    assert seal["compression_method"] == "zip"
    assert seal["production_seal"] is False
    assert seal["payload_hash"]


def test_artifact_manifest_records_event_artifact_refs(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    persist_archive_event(_event(artifact_refs=["report:a.md", "evidence:b.zip"]), archive_root=root)
    manifest = _load(root / "artifacts" / "manifest.yaml")
    refs = [entry["ref"] for entry in manifest["artifacts"]]

    assert refs == ["report:a.md", "evidence:b.zip"]
    assert manifest["production_manifest"] is False


def test_rollback_metadata_records_created_and_updated_files(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    persist_archive_event(_event(), archive_root=root)
    rollback = _load(root / "rollback" / "R0001.yaml")

    assert rollback["event_id"] == "E0001"
    assert rollback["segment_id"] == "segment_0001"
    assert rollback["operation"] == "append_event"
    assert any(path.endswith("events/E0001.yaml") for path in rollback["created_files"])
    assert rollback["previous_file_contents"]
    assert rollback["production_transaction"] is False


def test_event_too_large_for_empty_segment_is_rejected(tmp_path: Path) -> None:
    result = persist_archive_event(_event(evidence_refs=["x" * 512]), archive_root=tmp_path / "archive", max_segment_size_bytes=10)

    assert result.status == "rejected"
    assert "fit" in result.reason.lower()


def test_cli_persists_event_file(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps(_event(), indent=2), encoding="utf-8")
    result = persist_archive_event_file(candidate, archive_root=root)

    assert result.status == "persisted"
    assert (root / "active" / "segment_0001" / "events" / "E0001.yaml").is_file()


def test_json_formatted_yaml_payloads_are_json_loadable(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    persist_archive_event(_event(), archive_root=root)
    event_file = root / "active" / "segment_0001" / "events" / "E0001.yaml"

    assert json.loads(event_file.read_text(encoding="utf-8"))["event_id"] == "E0001"


def test_index_tracks_segments_and_events(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    persist_archive_event(_event(task_id="T1"), archive_root=root, max_events_per_segment=1)
    persist_archive_event(_event(task_id="T2"), archive_root=root, max_events_per_segment=1)
    index = _load(root / "index.yaml")

    assert index["event_count"] == 2
    assert {segment["segment_id"] for segment in index["segments"]} == {"segment_0001", "segment_0002"}
    assert any(segment["status"] == "sealed" for segment in index["segments"])
    assert index["active_segment_id"] == "segment_0002"


def test_rejected_event_does_not_create_archive_layout(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    result = persist_archive_event(_event(truth_status="global_truth"), archive_root=root)

    assert result.status == "rejected"
    assert not root.exists()


def test_later_writes_do_not_mutate_sealed_segment(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    persist_archive_event(_event(task_id="T1"), archive_root=root, max_events_per_segment=1)
    persist_archive_event(_event(task_id="T2"), archive_root=root, max_events_per_segment=1)

    sealed_segment = root / "sealed" / "segment_0001"
    assert sealed_segment.is_dir()
    before_hash = _hash_tree(sealed_segment)

    persist_archive_event(_event(task_id="T3"), archive_root=root, max_events_per_segment=10)

    after_hash = _hash_tree(sealed_segment)
    assert before_hash == after_hash
    assert (root / "active" / "segment_0002" / "events" / "E0003.yaml").is_file()
