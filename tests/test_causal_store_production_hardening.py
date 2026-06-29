from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from aegis.stores.causal import (
    AdmissionTransaction,
    CausalDependencyGroup,
    CausalNodeDraft,
    CausalQuery,
    CausalRef,
    CausalStore,
    CausalStoreError,
    InvalidationRequest,
    SupersessionRequest,
)


def _store(tmp_path) -> CausalStore:
    return CausalStore(tmp_path / ".aegis" / "stores" / "causal" / "causal.sqlite3")


def _root_node(content: str, *, evidence_ref: str = "test/root") -> CausalNodeDraft:
    return CausalNodeDraft(
        content=content,
        semantic_summary=content,
        semantic_keys=["causal", "root", *content.lower().split()[:4]],
        source_module="test",
        root_kind="test_result",
        node_refs=[("test", evidence_ref)],
        dependency_groups=[],
    )


def _admit(store: CausalStore, *node_ids: int) -> None:
    store.admit_nodes(
        AdmissionTransaction(
            node_ids=list(node_ids),
            admitted_by_module="master",
            rationale="accepted by production hardening test",
            evidence_ref="review/evidence",
        )
    )


def _candidate_with_group(content: str, predecessor: int) -> CausalNodeDraft:
    return CausalNodeDraft(
        content=content,
        semantic_summary=content,
        semantic_keys=["causal", "group", "typed"],
        source_module="debate",
        dependency_groups=[
            CausalDependencyGroup(
                causal_dependencies=[predecessor],
                validity_refs=[
                    CausalRef(ref_type="artifact", ref_id="artifact/task-1"),
                    CausalRef(ref_type="knowledge", ref_id="knowledge/fact-1"),
                    CausalRef(ref_type="test", ref_id="test/result-1"),
                    CausalRef(ref_type="external", ref_id="external/email-1"),
                    CausalRef(ref_type="artifact", ref_id="artifact/report-1"),
                ],
                scope="production hardening",
                conditions=["same project"],
                assumptions=["local sqlite store"],
                confidence="high",
                invalidation_conditions=["project scope changes"],
            )
        ],
    )


def test_concurrent_same_identity_insert_persists_one_active_node(tmp_path):
    store = _store(tmp_path)
    draft = _root_node("Concurrent duplicate causal identity must be database constrained")

    def insert_once() -> tuple[str, int | str]:
        local_store = CausalStore(store.db_path)
        try:
            return ("ok", local_store.put_candidate(draft))
        except CausalStoreError as exc:
            return ("error", exc.code)

    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(lambda _index: insert_once(), range(24)))

    persisted = [value for status, value in results if status == "ok"]
    errors = [value for status, value in results if status == "error"]
    assert len(persisted) == 1
    assert set(errors) == {"DUPLICATE_NODE"}

    with sqlite3.connect(store.db_path) as conn:
        active_total, distinct_total = conn.execute(
            """
            SELECT COUNT(causal_identity_hash), COUNT(DISTINCT causal_identity_hash)
            FROM causal_nodes
            WHERE status IN ('candidate', 'admitted', 'deprecated', 'superseded')
            """
        ).fetchone()
    assert active_total == distinct_total == 1


def test_supersession_requires_valid_lifecycle_and_preserves_failed_state(tmp_path):
    store = _store(tmp_path)
    old_candidate = store.put_candidate(_root_node("Candidate cannot be superseded"))
    admitted_old = store.put_candidate(_root_node("Admitted old causal node"))
    admitted_new = store.put_candidate(_root_node("Admitted replacement causal node"))
    candidate_new = store.put_candidate(_root_node("Candidate replacement is not accepted truth"))
    _admit(store, admitted_old, admitted_new)

    with pytest.raises(CausalStoreError) as self_failure:
        store.supersede_node(
            SupersessionRequest(
                old_node_id=admitted_old,
                new_node_id=admitted_old,
                reason="self replacement is invalid",
            )
        )
    assert self_failure.value.code == "SELF_SUPERSESSION_FORBIDDEN"

    with pytest.raises(CausalStoreError) as old_failure:
        store.supersede_node(
            SupersessionRequest(
                old_node_id=old_candidate,
                new_node_id=admitted_new,
                reason="candidate old node is not admitted truth",
            )
        )
    assert old_failure.value.code == "INVALID_STATUS_TRANSITION"

    with pytest.raises(CausalStoreError) as new_failure:
        store.supersede_node(
            SupersessionRequest(
                old_node_id=admitted_old,
                new_node_id=candidate_new,
                reason="candidate replacement is not admitted truth",
            )
        )
    assert new_failure.value.code == "SUPERSESSION_REPLACEMENT_NOT_ADMITTED"
    assert store.get_node(admitted_old).status == "admitted"
    assert store.get_node(candidate_new).status == "candidate"

    result = store.supersede_node(
        SupersessionRequest(
            old_node_id=admitted_old,
            new_node_id=admitted_new,
            reason="admitted replacement supersedes old admitted causal node",
        )
    )
    assert result.old_node_id == admitted_old
    assert store.get_node(admitted_old).status == "superseded"


def test_group_validity_refs_round_trip_preserves_ref_types(tmp_path):
    store = _store(tmp_path)
    root_id = store.put_candidate(_root_node("Typed group refs root"))
    _admit(store, root_id)
    node_id = store.put_candidate(_candidate_with_group("Typed group refs survive round trip", root_id))

    group = store.get_node(node_id).dependency_groups[0]
    assert [(ref.ref_type, ref.ref_id) for ref in group.validity_refs] == [
        ("artifact", "artifact/report-1"),
        ("artifact", "artifact/task-1"),
        ("external", "external/email-1"),
        ("knowledge", "knowledge/fact-1"),
        ("test", "test/result-1"),
    ]
    assert group.knowledge_refs == ["knowledge/fact-1"]
    assert group.evidence_refs == ["test/result-1"]


def test_chinese_and_mixed_language_retrieval_survives_rebuild(tmp_path):
    store = _store(tmp_path)
    node_id = store.put_candidate(
        CausalNodeDraft(
            content="领导者中介拓扑优于全网格通信，因为它保留裁决控制并减少隐藏通道",
            semantic_summary="领导者中介拓扑支持 Debate closure",
            semantic_keys=["领导者拓扑", "Debate closure", "hidden side channel"],
            source_module="test",
            root_kind="test_result",
            node_refs=[("test", "test/cjk")],
        )
    )
    _admit(store, node_id)

    assert store.search_nodes(CausalQuery(query="领导者拓扑")).nodes[0].node_id == node_id
    assert store.search_nodes(CausalQuery(query="Debate hidden channel")).nodes[0].node_id == node_id

    store.rebuild_indexes()
    assert store.search_nodes(CausalQuery(query="领导者拓扑")).nodes[0].node_id == node_id


def test_search_marks_degraded_recall_when_fts_is_unavailable(tmp_path):
    store = _store(tmp_path)
    node_id = store.put_candidate(_root_node("Fallback term recall survives FTS outage"))
    _admit(store, node_id)

    with sqlite3.connect(store.db_path) as conn:
        conn.execute("DROP TABLE causal_nodes_fts")
        conn.commit()

    result = store.search_nodes(CausalQuery(query="fallback recall outage"))
    assert result.degraded_recall is True
    assert any(warning.code == "FTS_INDEX_UNAVAILABLE" for warning in result.warnings)
    assert result.nodes[0].node_id == node_id


def test_repeated_admission_is_controlled_and_does_not_duplicate_audit(tmp_path):
    store = _store(tmp_path)
    node_id = store.put_candidate(_root_node("Repeated admission must not pollute audit"))
    _admit(store, node_id)

    with pytest.raises(CausalStoreError) as failure:
        _admit(store, node_id)
    assert failure.value.code == "ALREADY_ADMITTED"

    with sqlite3.connect(store.db_path) as conn:
        audit_count = conn.execute(
            "SELECT COUNT(*) FROM causal_admission_records WHERE node_id = ?",
            (node_id,),
        ).fetchone()[0]
    assert audit_count == 1


def test_revalidation_queue_reports_only_newly_queued_nodes(tmp_path):
    store = _store(tmp_path)
    root_id = store.put_candidate(_root_node("Revalidation queue predecessor"))
    _admit(store, root_id)
    child_id = store.put_candidate(
        CausalNodeDraft(
            content="Repeated invalidation should not overreport new queue entries",
            semantic_summary="Repeated invalidation should not overreport",
            semantic_keys=["revalidation", "queue"],
            source_module="debate",
            dependency_groups=[
                CausalDependencyGroup(
                    causal_dependencies=[root_id],
                    evidence_refs=["test/revalidation"],
                    scope="queue hardening",
                )
            ],
        )
    )
    _admit(store, child_id)

    first = store.invalidate_node(
        InvalidationRequest(
            node_id=root_id,
            invalidated_by_module="causal_review",
            reason="first invalidation",
        )
    )
    second = store.invalidate_node(
        InvalidationRequest(
            node_id=root_id,
            invalidated_by_module="causal_review",
            reason="second invalidation",
        )
    )
    assert first.queued_revalidation_node_ids == [child_id]
    assert second.queued_revalidation_node_ids == []
