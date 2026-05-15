from __future__ import annotations

import json
from pathlib import Path

from aegis_knowledge_store import persist_knowledge_candidate, persist_knowledge_candidate_file


def _candidate(**overrides):
    base = {
        "candidate_type": "knowledge_candidate",
        "candidate_id": "KC-001",
        "statement": "The target sandbox repository is rain-123-bow/aegis-execution-sandbox.",
        "scope": "Aegis Execution sandbox",
        "version_context": "v0.1.0-alpha",
        "evidence_refs": ["runtime_test_reports/PHASE_19B_EXECUTION_REAL_FRONT_BACK_AGENT_FULL_ACCEPTANCE_REPORT.md"],
        "master_verified": True,
        "category": "environment",
    }
    base.update(overrides)
    return base


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_verified_static_fact_persists(tmp_path: Path) -> None:
    result = persist_knowledge_candidate(_candidate(), knowledge_root=tmp_path / "knowledge")
    payload = result.to_dict()
    assert payload["status"] == "persisted"
    assert payload["operation"] == "add_entry"
    assert payload["entry_id"] == "K0001"
    assert payload["production_knowledge_persistence"] is False
    assert payload["knowledge_produces_causal_truth"] is False
    assert (tmp_path / "knowledge" / "entries" / "K0001.yaml").is_file()


def test_versioned_platform_constraint_persists(tmp_path: Path) -> None:
    result = persist_knowledge_candidate(
        _candidate(
            statement="The target runtime baseline is Python >=3.11.",
            category="toolchain",
            scope="Aegis Python runtime modules",
            version_context="phase23b-demo",
            evidence_refs=["pyproject.toml"],
        ),
        knowledge_root=tmp_path / "knowledge",
    )
    entry = _load(tmp_path / "knowledge" / "entries" / "K0001.yaml")
    assert entry["statement"] == "The target runtime baseline is Python >=3.11."
    assert entry["category"] == "toolchain"


def test_developer_asserted_unverified_rejected_without_layout(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    result = persist_knowledge_candidate(
        _candidate(claim_status="developer_asserted", master_verified=False),
        knowledge_root=root,
    )
    assert result.status == "rejected"
    assert not root.exists()


def test_unverified_claim_rejected_without_layout(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    candidate = _candidate()
    candidate.pop("master_verified")
    result = persist_knowledge_candidate(candidate, knowledge_root=root)
    assert result.status == "rejected"
    assert not root.exists()


def test_causal_shape_with_why_rejected(tmp_path: Path) -> None:
    result = persist_knowledge_candidate(_candidate(why="Because X, therefore design Y holds."), knowledge_root=tmp_path / "knowledge")
    assert result.status == "rejected"
    assert "Causal-shaped" in result.reason


def test_causal_marker_statement_rejected(tmp_path: Path) -> None:
    result = persist_knowledge_candidate(
        _candidate(statement="Because the runtime is Python, this design is globally correct."),
        knowledge_root=tmp_path / "knowledge",
    )
    assert result.status == "rejected"


def test_objective_conditional_fact_is_allowed(tmp_path: Path) -> None:
    result = persist_knowledge_candidate(
        _candidate(statement="When chip temperature exceeds 85 C, target device X downclocks.", category="platform"),
        knowledge_root=tmp_path / "knowledge",
    )
    assert result.status == "persisted"


def test_archive_event_shape_rejected(tmp_path: Path) -> None:
    result = persist_knowledge_candidate(
        {
            "candidate_type": "knowledge_candidate",
            "event_type": "task_requested",
            "actor": "developer",
            "occurred_at": "2026-05-15T00:00:00Z",
            "scope": "bad",
            "version_context": "bad",
            "evidence_refs": ["chat:bad"],
            "master_verified": True,
        },
        knowledge_root=tmp_path / "knowledge",
    )
    assert result.status == "rejected"
    assert "Archive-shaped" in result.reason




def test_archive_event_shape_with_statement_is_rejected(tmp_path: Path) -> None:
    result = persist_knowledge_candidate(
        {
            "candidate_type": "knowledge_candidate",
            "statement": "A developer requested a task, therefore it should be stored as Knowledge.",
            "event_type": "task_requested",
            "actor": "developer",
            "occurred_at": "2026-05-15T00:00:00Z",
            "task_id": "T-BAD",
            "scope": "bad",
            "version_context": "bad",
            "evidence_refs": ["chat:bad"],
            "master_verified": True,
        },
        knowledge_root=tmp_path / "knowledge",
    )
    assert result.status == "rejected"
    assert "Archive-shaped" in result.reason


def test_unknown_operation_rejected_without_layout(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    result = persist_knowledge_candidate(_candidate(operation="merge_global_truth"), knowledge_root=root)
    assert result.status == "rejected"
    assert "Unknown Knowledge persistence operation" in result.reason
    assert not root.exists()


def test_direct_causal_write_rejected(tmp_path: Path) -> None:
    result = persist_knowledge_candidate(_candidate(causal_store_write_performed=True), knowledge_root=tmp_path / "knowledge")
    assert result.status == "rejected"
    assert result.causal_store_write_performed is False


def test_global_truth_claim_rejected(tmp_path: Path) -> None:
    result = persist_knowledge_candidate(_candidate(truth_status="global_truth"), knowledge_root=tmp_path / "knowledge")
    assert result.status == "rejected"


def test_missing_evidence_rejected(tmp_path: Path) -> None:
    result = persist_knowledge_candidate(_candidate(evidence_refs=[]), knowledge_root=tmp_path / "knowledge")
    assert result.status == "rejected"
    assert "evidence_refs" in result.reason


def test_supersession_updates_existing_entry(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    first = persist_knowledge_candidate(_candidate(), knowledge_root=root)
    second = persist_knowledge_candidate(
        _candidate(
            statement="The target sandbox repository remains rain-123-bow/aegis-execution-sandbox for Phase 19B.",
            operation="supersede",
            supersedes=[first.entry_id],
            candidate_id="KC-002",
        ),
        knowledge_root=root,
    )
    assert second.status == "persisted"
    old = _load(root / "entries" / f"{first.entry_id}.yaml")
    assert old["status"] == "superseded"
    assert old["superseded_by"] == second.entry_id
    change_files = list((root / "history" / "changes").glob("*.yaml"))
    assert len(change_files) == 2


def test_deprecation_updates_existing_entry(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    first = persist_knowledge_candidate(_candidate(), knowledge_root=root)
    second = persist_knowledge_candidate(
        _candidate(
            statement="The earlier sandbox repository statement is deprecated for this scope.",
            operation="deprecate",
            deprecates=[first.entry_id],
            candidate_id="KC-003",
        ),
        knowledge_root=root,
    )
    old = _load(root / "entries" / f"{first.entry_id}.yaml")
    assert second.status == "persisted"
    assert old["status"] == "deprecated"
    assert old["deprecated_by"] == second.entry_id


def test_update_entry_updates_existing_entry_without_new_id(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    first = persist_knowledge_candidate(_candidate(), knowledge_root=root)
    result = persist_knowledge_candidate(
        _candidate(
            statement="The target sandbox repository is rain-123-bow/aegis-execution-sandbox for Phase 23B.",
            operation="update_entry",
            target_entry_id=first.entry_id,
            candidate_id="KC-004",
        ),
        knowledge_root=root,
    )
    entry = _load(root / "entries" / f"{first.entry_id}.yaml")
    index = _load(root / "index.yaml")
    change = _load(root / "history" / "changes" / "C0002.yaml")
    rollback = _load(root / "rollback" / "R0002.yaml")

    assert result.status == "persisted"
    assert result.operation == "update_entry"
    assert result.entry_id == first.entry_id
    assert entry["statement"].endswith("for Phase 23B.")
    assert index["entry_count"] == 1
    assert change["candidate_id"] == "KC-004"
    assert rollback["candidate_id"] == "KC-004"


def test_missing_supersession_reference_rejected(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    persist_knowledge_candidate(_candidate(), knowledge_root=root)
    result = persist_knowledge_candidate(_candidate(operation="supersede", supersedes=["K9999"]), knowledge_root=root)
    assert result.status == "rejected"
    assert "missing" in result.reason



def test_missing_supersession_reference_rejected_without_layout(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    result = persist_knowledge_candidate(_candidate(operation="supersede", supersedes=["K9999"]), knowledge_root=root)
    assert result.status == "rejected"
    assert "missing" in result.reason
    assert not root.exists()

def test_index_changelog_and_rollback_written(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    result = persist_knowledge_candidate(_candidate(), knowledge_root=root)
    assert (root / "index.yaml").is_file()
    assert (root / "history" / "changelog.md").is_file()
    assert (root / "history" / "changes" / "C0001.yaml").is_file()
    assert (root / "rollback" / "R0001.yaml").is_file()
    payload = result.to_dict()
    assert payload["index_updated"] is True
    assert payload["changelog_written"] is True


def test_conflicting_target_file_rejected(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    (root / "entries").mkdir(parents=True)
    (root / "entries" / "K0001.yaml").write_text("conflict", encoding="utf-8")
    result = persist_knowledge_candidate(_candidate(), knowledge_root=root)
    assert result.status == "rejected"
    assert "Target Knowledge entry file already exists" in result.reason
    assert (root / "entries" / "K0001.yaml").read_text(encoding="utf-8") == "conflict"


def test_cli_persists_candidate_file(tmp_path: Path) -> None:
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(json.dumps(_candidate()), encoding="utf-8")
    result = persist_knowledge_candidate_file(candidate_path, knowledge_root=tmp_path / "knowledge")
    assert result.status == "persisted"
