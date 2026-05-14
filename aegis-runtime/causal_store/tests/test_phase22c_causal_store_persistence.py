from __future__ import annotations

import json
from pathlib import Path

from aegis_causal_store import persist_review_decision, persist_review_decision_file


def _decision(**overrides):
    base = {
        "review_decision_id": "R22B-001",
        "decision": "stage_canonical_merge_candidate",
        "candidate_id": "C-001",
        "candidate_statement": "Aegis Phase 22C persists causal review decisions locally.",
        "why": "Phase 22B produced a high-confidence review artifact and Phase 22C owns local persistence.",
        "source_origin": "master_unique_conclusion",
        "accepted_status": "canonical_merge_candidate",
        "required_next_step": "phase22c_causal_store_persistence",
        "scope": "Aegis Phase 22C demo persistence",
        "assumptions": ["Phase 22C is local demo persistence"],
        "evidence_refs": ["runtime_test_reports/PHASE_22B_MASTER_CAUSAL_REVIEW_ACCEPTANCE_REPORT.md"],
        "master_confidence": {"type": "contract_proven", "value": "proven", "evidence_refs": ["policy"]},
        "canonical_global_merge_performed": False,
        "production_store_write_performed": False,
        "causal_store_write_performed": False,
    }
    base.update(overrides)
    return base


def _read_json_compatible_yaml(path: Path):
    # Phase 22C local demo files keep `.yaml` names but contain JSON-formatted
    # YAML-compatible payloads to avoid a YAML parser dependency.
    return json.loads(path.read_text(encoding="utf-8"))


def test_canonical_merge_candidate_persists_fact_index_changelog_snapshot_and_rollback(tmp_path: Path) -> None:
    causal_root = tmp_path / "causal"
    result = persist_review_decision(_decision(), causal_root=causal_root).to_dict()

    assert result["status"] == "persisted"
    assert result["fact_id"] == "F0001"
    assert result["semantic_changelog_written"] is True
    assert result["index_updated"] is True
    assert result["snapshot_written"] is True
    assert result["rollback_metadata_written"] is True
    assert result["production_persistence"] is False
    assert result["global_causal_truth_merge_performed"] is False

    assert (causal_root / "facts" / "F0001.yaml").is_file()
    assert (causal_root / "index.yaml").is_file()
    assert (causal_root / "history" / "changes" / "C0001.yaml").is_file()
    assert (causal_root / "history" / "changelog.md").is_file()
    assert (causal_root / "snapshots" / "S0001.yaml").is_file()
    assert (causal_root / "rollback" / "R0001.yaml").is_file()

    fact = _read_json_compatible_yaml(causal_root / "facts" / "F0001.yaml")
    assert fact["status"] == "active"
    assert fact["statement"] == _decision()["candidate_statement"]

    index = _read_json_compatible_yaml(causal_root / "index.yaml")
    assert index["fact_count"] == 1
    assert index["facts"][0]["id"] == "F0001"


def test_scope_limited_candidate_preserves_narrowed_scope(tmp_path: Path) -> None:
    result = persist_review_decision(
        _decision(
            review_decision_id="R22B-002",
            decision="stage_scope_limited_merge_candidate",
            scope="broad production scope",
            accepted_scope="narrow scope only",
        ),
        causal_root=tmp_path / "causal",
    )
    fact = _read_json_compatible_yaml(tmp_path / "causal" / "facts" / f"{result.fact_id}.yaml")
    assert fact["scope"] == "narrow scope only"
    assert fact["original_scope"] == "broad production scope"
    assert fact["accepted_scope"] == "narrow scope only"
    assert result.operation == "scope_limited_add"


def test_supersession_candidate_updates_existing_fact(tmp_path: Path) -> None:
    causal_root = tmp_path / "causal"
    first = persist_review_decision(_decision(review_decision_id="R22B-003"), causal_root=causal_root)
    assert first.fact_id == "F0001"

    second = persist_review_decision(
        _decision(
            review_decision_id="R22B-004",
            decision="stage_supersession_candidate",
            candidate_statement="New causal fact supersedes old fact.",
            supersedes=["F0001"],
        ),
        causal_root=causal_root,
    ).to_dict()

    old_fact = _read_json_compatible_yaml(causal_root / "facts" / "F0001.yaml")
    assert old_fact["status"] == "superseded"
    assert old_fact["superseded_by"] == "F0002"
    assert second["operation"] == "supersede"
    assert "F0001" in second["updated_facts"]


def test_invalidation_candidate_updates_existing_fact(tmp_path: Path) -> None:
    causal_root = tmp_path / "causal"
    persist_review_decision(_decision(review_decision_id="R22B-005"), causal_root=causal_root)

    result = persist_review_decision(
        _decision(
            review_decision_id="R22B-006",
            decision="stage_invalidation_candidate",
            candidate_statement="New constraints invalidate old causal fact.",
            invalidates=["F0001"],
        ),
        causal_root=causal_root,
    ).to_dict()

    old_fact = _read_json_compatible_yaml(causal_root / "facts" / "F0001.yaml")
    assert old_fact["status"] == "invalidated"
    assert old_fact["invalidated_by"] == "F0002"
    assert result["operation"] == "invalidate"


def test_developer_decision_required_is_rejected(tmp_path: Path) -> None:
    result = persist_review_decision(
        _decision(decision="developer_decision_required", accepted_status="pending_developer_decision"),
        causal_root=tmp_path / "causal",
    ).to_dict()
    assert result["status"] == "rejected"
    assert result["fact_id"] is None
    assert result["semantic_changelog_written"] is False


def test_needs_more_evidence_is_rejected(tmp_path: Path) -> None:
    result = persist_review_decision(_decision(decision="needs_more_evidence"), causal_root=tmp_path / "causal").to_dict()
    assert result["status"] == "rejected"
    assert "must not be persisted" in result["reason"]


def test_direct_write_flag_is_rejected(tmp_path: Path) -> None:
    result = persist_review_decision(
        _decision(canonical_global_merge_performed=True),
        causal_root=tmp_path / "causal",
    ).to_dict()
    assert result["status"] == "rejected"
    assert result["production_persistence"] is False
    assert result["global_causal_truth_merge_performed"] is False


def test_missing_required_causal_fields_are_rejected(tmp_path: Path) -> None:
    bad = _decision()
    bad.pop("why")
    result = persist_review_decision(bad, causal_root=tmp_path / "causal").to_dict()
    assert result["status"] == "rejected"
    assert "why" in result["reason"]


def test_missing_supersession_reference_is_rejected_without_new_fact(tmp_path: Path) -> None:
    causal_root = tmp_path / "causal"
    result = persist_review_decision(
        _decision(
            review_decision_id="R22B-010",
            decision="stage_supersession_candidate",
            supersedes=["F9999"],
        ),
        causal_root=causal_root,
    ).to_dict()
    assert result["status"] == "rejected"
    assert "missing fact ID" in result["reason"]
    assert not (causal_root / "facts" / "F0001.yaml").exists()


def test_existing_non_identical_fact_target_is_not_overwritten(tmp_path: Path) -> None:
    causal_root = tmp_path / "causal"
    fact_path = causal_root / "facts" / "F0001.yaml"
    fact_path.parent.mkdir(parents=True)
    fact_path.write_text("conflicting-content", encoding="utf-8")

    result = persist_review_decision(_decision(review_decision_id="R22B-011"), causal_root=causal_root).to_dict()

    assert result["status"] == "rejected"
    assert "would be overwritten" in result["reason"]
    assert fact_path.read_text(encoding="utf-8") == "conflicting-content"


def test_index_fact_count_increments(tmp_path: Path) -> None:
    causal_root = tmp_path / "causal"
    persist_review_decision(_decision(review_decision_id="R22B-007"), causal_root=causal_root)
    persist_review_decision(_decision(review_decision_id="R22B-008", candidate_statement="Second fact."), causal_root=causal_root)
    index = _read_json_compatible_yaml(causal_root / "index.yaml")
    assert index["fact_count"] == 2
    assert [fact["id"] for fact in index["facts"]] == ["F0001", "F0002"]


def test_rollback_metadata_contains_created_and_previous_files(tmp_path: Path) -> None:
    causal_root = tmp_path / "causal"
    result = persist_review_decision(_decision(), causal_root=causal_root).to_dict()
    rollback = _read_json_compatible_yaml(causal_root / result["rollback_ref"])
    assert "facts/F0001.yaml" in rollback["created_files"]
    assert any(path.endswith("index.yaml") for path in rollback["updated_files"])
    assert rollback["change_id"] == result["change_record_id"]
    assert rollback["affected_fact_ids"] == ["F0001"]
    assert rollback["production_transaction"] is False


def test_change_record_contains_semantic_operations_not_git_diff(tmp_path: Path) -> None:
    causal_root = tmp_path / "causal"
    result = persist_review_decision(_decision(), causal_root=causal_root).to_dict()
    change = _read_json_compatible_yaml(causal_root / "history" / "changes" / f"{result['change_record_id']}.yaml")
    assert change["semantic_operations"][0]["op"] == "add_fact"
    assert "git_diff" not in change
    assert change["production_persistence"] is False


def test_cli_file_persistence(tmp_path: Path) -> None:
    causal_root = tmp_path / "causal"
    decision_path = tmp_path / "decision.json"
    decision_path.write_text(json.dumps(_decision(review_decision_id="R22B-009")), encoding="utf-8")
    result = persist_review_decision_file(decision_path, causal_root)
    assert result.status == "persisted"
    assert (causal_root / "facts" / "F0001.yaml").is_file()
