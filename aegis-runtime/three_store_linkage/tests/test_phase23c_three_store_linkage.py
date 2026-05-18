from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

from aegis_three_store_linkage import validate_three_store_linkage


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _archive_event(**overrides):
    payload = {
        "event_id": "E0001",
        "candidate_id": "AC-001",
        "candidate_type": "archive_event",
        "segment_id": "segment_0001",
        "event_type": "developer_decision",
        "actor": "developer",
        "occurred_at": "2026-05-17T00:00:00Z",
        "recorded_at": "2026-05-17T00:01:00Z",
        "task_id": "T-001",
        "scope": "phase23c-demo",
        "artifact_refs": ["runtime_test_reports/PHASE_23C_THREE_STORE_LINKAGE_PATCH_PLAN.md"],
        "evidence_refs": ["runtime_test_reports/PHASE_23C_THREE_STORE_LINKAGE_PATCH_PLAN.md"],
        "promoted_to_knowledge": ["K0001"],
        "promoted_to_causal": ["F0001"],
        "archive_produces_truth": False,
        "production_archive_persistence": False,
    }
    payload.update(overrides)
    return payload


def _knowledge_entry(**overrides):
    payload = {
        "id": "K0001",
        "statement": "Phase 23C validates local cross-store references only.",
        "category": "policy",
        "scope": "phase23c-demo",
        "version_context": "v0.1.0-alpha",
        "evidence_refs": ["archive:E0001", "runtime_test_reports/PHASE_23C_THREE_STORE_LINKAGE_PATCH_PLAN.md"],
        "master_verified": True,
        "status": "active",
        "production_knowledge_persistence": False,
        "knowledge_produces_causal_truth": False,
    }
    payload.update(overrides)
    return payload


def _causal_fact(**overrides):
    payload = {
        "id": "F0001",
        "statement": "Phase 23C can accept the linkage graph when all typed local references resolve.",
        "why": "The validator resolves Archive, Knowledge, and Causal local references before accepting the graph.",
        "evidence": ["archive:E0001", "knowledge:K0001"],
        "scope": "phase23c-demo",
        "assumptions": ["local demo store roots are complete for this validation run"],
        "depends_on": [],
        "supersedes": [],
        "invalidates": [],
        "source_review_decision_id": "CRD-001",
        "source_decision": "stage_scope_limited_merge_candidate",
        "status": "active",
        "production_persistence": False,
        "global_causal_truth_merge_performed": False,
    }
    payload.update(overrides)
    return payload


def _make_valid_three_store(root: Path) -> tuple[Path, Path, Path]:
    archive_root = root / "archive"
    knowledge_root = root / "knowledge"
    causal_root = root / "causal"
    _write(archive_root / "active" / "segment_0001" / "events" / "E0001.yaml", _archive_event())
    _write(knowledge_root / "entries" / "K0001.yaml", _knowledge_entry())
    _write(causal_root / "facts" / "F0001.yaml", _causal_fact())
    return archive_root, knowledge_root, causal_root


def _validate(root: Path):
    archive_root, knowledge_root, causal_root = _make_valid_three_store(root)
    return validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root)


def test_valid_cross_store_links_pass(tmp_path: Path) -> None:
    result = _validate(tmp_path)
    payload = result.to_dict()
    assert payload["status"] == "validated"
    assert payload["decision"] == "accepted_local_three_store_linkage"
    assert payload["archive_event_count"] == 1
    assert payload["knowledge_entry_count"] == 1
    assert payload["causal_fact_count"] == 1
    assert payload["checked_reference_count"] >= 4
    assert payload["production_linkage_persistence"] is False
    assert payload["global_causal_truth_merge_performed"] is False


def test_archive_missing_promoted_knowledge_ref_rejected(tmp_path: Path) -> None:
    archive_root, knowledge_root, causal_root = _make_valid_three_store(tmp_path)
    _write(archive_root / "active" / "segment_0001" / "events" / "E0001.yaml", _archive_event(promoted_to_knowledge=["K9999"]))
    result = validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root)
    assert result.status == "rejected"
    assert result.missing_refs[0]["target_store"] == "knowledge"
    assert result.missing_refs[0]["target_id"] == "K9999"


def test_archive_missing_promoted_causal_ref_rejected(tmp_path: Path) -> None:
    archive_root, knowledge_root, causal_root = _make_valid_three_store(tmp_path)
    _write(archive_root / "active" / "segment_0001" / "events" / "E0001.yaml", _archive_event(promoted_to_causal=["F9999"]))
    result = validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root)
    assert result.status == "rejected"
    assert result.missing_refs[0]["target_store"] == "causal"


def test_knowledge_missing_typed_archive_evidence_rejected(tmp_path: Path) -> None:
    archive_root, knowledge_root, causal_root = _make_valid_three_store(tmp_path)
    _write(knowledge_root / "entries" / "K0001.yaml", _knowledge_entry(evidence_refs=["archive:E9999"]))
    result = validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root)
    assert result.status == "rejected"
    assert any(item["target_id"] == "E9999" for item in result.missing_refs)


def test_knowledge_evidence_causal_ref_rejected(tmp_path: Path) -> None:
    archive_root, knowledge_root, causal_root = _make_valid_three_store(tmp_path)
    _write(knowledge_root / "entries" / "K0001.yaml", _knowledge_entry(evidence_refs=["causal:F0001"]))
    result = validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root)
    assert result.status == "rejected"
    assert any(
        item["field"] == "evidence_refs"
        and item["target_store"] == "causal"
        and "Knowledge evidence_refs may cite Archive events" in item["reason"]
        for item in result.type_mismatches
    )


def test_knowledge_evidence_knowledge_ref_rejected(tmp_path: Path) -> None:
    archive_root, knowledge_root, causal_root = _make_valid_three_store(tmp_path)
    _write(knowledge_root / "entries" / "K0001.yaml", _knowledge_entry(evidence_refs=["knowledge:K0001"]))
    result = validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root)
    assert result.status == "rejected"
    assert any(item["field"] == "evidence_refs" and item["target_store"] == "knowledge" for item in result.type_mismatches)


def test_causal_missing_typed_knowledge_evidence_rejected(tmp_path: Path) -> None:
    archive_root, knowledge_root, causal_root = _make_valid_three_store(tmp_path)
    _write(causal_root / "facts" / "F0001.yaml", _causal_fact(evidence=["knowledge:K9999"]))
    result = validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root)
    assert result.status == "rejected"
    assert any(item["target_store"] == "knowledge" and item["target_id"] == "K9999" for item in result.missing_refs)


def test_causal_missing_dependency_rejected(tmp_path: Path) -> None:
    archive_root, knowledge_root, causal_root = _make_valid_three_store(tmp_path)
    _write(causal_root / "facts" / "F0001.yaml", _causal_fact(depends_on=["F9999"]))
    result = validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root)
    assert result.status == "rejected"
    assert any(item["field"] == "depends_on" and item["target_id"] == "F9999" for item in result.missing_refs)


def test_cross_store_type_mismatch_rejected(tmp_path: Path) -> None:
    archive_root, knowledge_root, causal_root = _make_valid_three_store(tmp_path)
    _write(archive_root / "active" / "segment_0001" / "events" / "E0001.yaml", _archive_event(promoted_to_knowledge=["F0001"]))
    result = validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root)
    assert result.status == "rejected"
    assert result.type_mismatches
    assert "expects knowledge" in result.type_mismatches[0]["reason"]


def test_promoted_assets_dict_links_supported(tmp_path: Path) -> None:
    archive_root, knowledge_root, causal_root = _make_valid_three_store(tmp_path)
    _write(
        archive_root / "active" / "segment_0001" / "events" / "E0001.yaml",
        _archive_event(
            promoted_to_knowledge=[],
            promoted_to_causal=[],
            promoted_assets=[
                {"target_store": "knowledge", "target_id": "K0001", "promotion_reason": "source-backed static fact"},
                {"target_store": "causal", "target_id": "F0001", "promotion_reason": "accepted causal review decision"},
            ],
        ),
    )
    result = validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root)
    assert result.status == "validated"
    assert len([link for link in result.validated_links if link["field"] == "promoted_assets"]) == 2


def test_promoted_assets_archive_target_store_rejected(tmp_path: Path) -> None:
    archive_root, knowledge_root, causal_root = _make_valid_three_store(tmp_path)
    _write(
        archive_root / "active" / "segment_0001" / "events" / "E0001.yaml",
        _archive_event(
            promoted_to_knowledge=[],
            promoted_to_causal=[],
            promoted_assets=[
                {"target_store": "archive", "target_id": "E0001", "promotion_reason": "invalid archive self-promotion"},
            ],
        ),
    )
    result = validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root)
    assert result.status == "rejected"
    assert any(
        item["field"] == "promoted_assets"
        and item["target_store"] == "archive"
        and "target only Knowledge or Causal" in item["reason"]
        for item in result.type_mismatches
    )


def test_promoted_assets_archive_typed_string_rejected(tmp_path: Path) -> None:
    archive_root, knowledge_root, causal_root = _make_valid_three_store(tmp_path)
    _write(
        archive_root / "active" / "segment_0001" / "events" / "E0001.yaml",
        _archive_event(
            promoted_to_knowledge=[],
            promoted_to_causal=[],
            promoted_assets=["archive:E0001"],
        ),
    )
    result = validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root)
    assert result.status == "rejected"
    assert any(item["field"] == "promoted_assets" and item["target_store"] == "archive" for item in result.type_mismatches)


def test_archive_boundary_violation_rejected(tmp_path: Path) -> None:
    archive_root, knowledge_root, causal_root = _make_valid_three_store(tmp_path)
    _write(archive_root / "active" / "segment_0001" / "events" / "E0001.yaml", _archive_event(archive_produces_truth=True))
    result = validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root)
    assert result.status == "rejected"
    assert result.store_boundary_violations[0]["field"] == "archive_produces_truth"


def test_knowledge_boundary_violation_rejected(tmp_path: Path) -> None:
    archive_root, knowledge_root, causal_root = _make_valid_three_store(tmp_path)
    _write(knowledge_root / "entries" / "K0001.yaml", _knowledge_entry(knowledge_produces_causal_truth=True))
    result = validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root)
    assert result.status == "rejected"
    assert result.store_boundary_violations[0]["field"] == "knowledge_produces_causal_truth"


def test_causal_boundary_violation_rejected(tmp_path: Path) -> None:
    archive_root, knowledge_root, causal_root = _make_valid_three_store(tmp_path)
    _write(causal_root / "facts" / "F0001.yaml", _causal_fact(global_causal_truth_merge_performed=True))
    result = validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root)
    assert result.status == "rejected"
    assert result.store_boundary_violations[0]["field"] == "global_causal_truth_merge_performed"


def test_external_source_refs_are_allowed_but_recorded(tmp_path: Path) -> None:
    archive_root, knowledge_root, causal_root = _make_valid_three_store(tmp_path)
    _write(knowledge_root / "entries" / "K0001.yaml", _knowledge_entry(evidence_refs=["runtime_test_reports/SOURCE.md"]))
    _write(causal_root / "facts" / "F0001.yaml", _causal_fact(evidence=["knowledge:K0001"]))
    result = validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root)
    assert result.status == "validated"
    assert any(item["raw"] == "runtime_test_reports/SOURCE.md" for item in result.external_refs)


def test_missing_store_root_rejected(tmp_path: Path) -> None:
    archive_root = tmp_path / "archive"
    knowledge_root = tmp_path / "knowledge"
    causal_root = tmp_path / "causal"
    archive_root.mkdir()
    knowledge_root.mkdir()
    result = validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root)
    assert result.status == "rejected"
    assert "requires existing local Archive" in result.reason


def test_duplicate_ids_rejected(tmp_path: Path) -> None:
    archive_root, knowledge_root, causal_root = _make_valid_three_store(tmp_path)
    _write(knowledge_root / "entries" / "K0002.yaml", _knowledge_entry(id="K0001", statement="Duplicate ID."))
    result = validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root)
    assert result.status == "rejected"
    assert result.duplicate_ids


def test_master_verified_linkage_request_expected_links_pass(tmp_path: Path) -> None:
    archive_root, knowledge_root, causal_root = _make_valid_three_store(tmp_path)
    request = {
        "request_type": "three_store_linkage_request",
        "request_id": "TSL-001",
        "master_verified": True,
        "expected_links": [
            {"from_store": "archive", "from_id": "E0001", "to_store": "knowledge", "to_id": "K0001", "link_type": "promoted_asset"},
            {"from_store": "causal", "from_id": "F0001", "to_store": "knowledge", "to_id": "K0001", "link_type": "evidence_ref"},
        ],
    }
    result = validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root, linkage_request=request)
    assert result.status == "validated"
    assert result.request_checked is True
    assert any(link["field"] == "expected_links:promoted_asset" for link in result.validated_links)


def test_unverified_linkage_request_rejected(tmp_path: Path) -> None:
    archive_root, knowledge_root, causal_root = _make_valid_three_store(tmp_path)
    request = {"request_type": "three_store_linkage_request", "master_verified": False}
    result = validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root, linkage_request=request)
    assert result.status == "rejected"
    assert "Master verified" in result.reason


def test_sealed_archive_zip_event_is_indexed(tmp_path: Path) -> None:
    archive_root = tmp_path / "archive"
    knowledge_root = tmp_path / "knowledge"
    causal_root = tmp_path / "causal"
    sealed = archive_root / "sealed" / "segment_0001"
    sealed.mkdir(parents=True)
    event_payload = _archive_event()
    with zipfile.ZipFile(sealed / "compressed_payload.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("events/E0001.yaml", json.dumps(event_payload, ensure_ascii=False, indent=2, sort_keys=True))
    _write(knowledge_root / "entries" / "K0001.yaml", _knowledge_entry())
    _write(causal_root / "facts" / "F0001.yaml", _causal_fact())
    result = validate_three_store_linkage(archive_root=archive_root, knowledge_root=knowledge_root, causal_root=causal_root)
    assert result.status == "validated"
    assert result.archive_event_count == 1


def test_cli_writes_validation_result(tmp_path: Path) -> None:
    archive_root, knowledge_root, causal_root = _make_valid_three_store(tmp_path)
    output = tmp_path / "out" / "result.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "aegis_three_store_linkage.cli",
            "validate",
            "--archive-root",
            str(archive_root),
            "--knowledge-root",
            str(knowledge_root),
            "--causal-root",
            str(causal_root),
            "--output",
            str(output),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "accepted_local_three_store_linkage" in completed.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "validated"
