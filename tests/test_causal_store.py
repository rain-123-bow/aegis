import sqlite3

import pytest

from aegis.stores.causal import (
    AdmissionTransaction,
    CausalDependencyGroup,
    CausalNodeDraft,
    CausalQuery,
    CausalStore,
    CausalStoreError,
    ExpandContextRequest,
    InvalidationRequest,
    RevalidationResolutionRequest,
)


def _store(tmp_path):
    return CausalStore(tmp_path / ".aegis" / "stores" / "causal" / "causal.sqlite3")


def _root_node(content: str, *, evidence_ref: str = "test-report-root"):
    return CausalNodeDraft(
        content=content,
        semantic_summary=content,
        semantic_keys=["sqlite", "causal", "root"],
        source_module="test",
        root_kind="test_result",
        node_refs=[("test", evidence_ref)],
        dependency_groups=[],
    )


def _dependent_node(content: str, predecessor: int, *, scope: str = "local project"):
    return CausalNodeDraft(
        content=content,
        semantic_summary=content,
        semantic_keys=["dependent", "causal", "search"],
        source_module="debate",
        dependency_groups=[
            CausalDependencyGroup(
                causal_dependencies=[predecessor],
                knowledge_refs=["project-fact-1"],
                evidence_refs=["test-report-dependent"],
                scope=scope,
                conditions=["predecessor remains admitted"],
                assumptions=["single local project"],
                confidence="high",
                invalidation_conditions=["predecessor is invalidated"],
            )
        ],
    )


def _admit(store: CausalStore, *node_ids: int):
    return store.admit_nodes(
        AdmissionTransaction(
            node_ids=list(node_ids),
            admitted_by_module="master",
            rationale="reviewed and accepted for causal store test",
            evidence_ref="admission-evidence",
        )
    )


def test_candidate_admission_search_and_projection_round_trip(tmp_path):
    store = _store(tmp_path)
    root_id = store.put_candidate(_root_node("SQLite is the canonical causal store"))
    _admit(store, root_id)

    child_id = store.put_candidate(
        _dependent_node("Causal nodes can be retrieved from SQLite by semantic query", root_id)
    )
    _admit(store, child_id)

    child = store.get_node(child_id)
    assert child.status == "admitted"
    assert child.dependency_groups[0].causal_dependencies == [root_id]
    assert child.dependency_groups[0].knowledge_refs == ["project-fact-1"]
    assert child.dependency_groups[0].evidence_refs == ["test-report-dependent"]

    search = store.search_nodes(CausalQuery(query="semantic causal query sqlite"))
    assert [node.node_id for node in search.nodes] == [child_id, root_id]
    assert search.rejected_nodes == []

    context = store.expand_context(ExpandContextRequest(node_ids=[child_id], depth=2))
    assert child_id in context.selected_nodes
    assert root_id in context.selected_nodes
    assert [child_id, root_id] in context.dependency_paths


def test_admission_rejects_candidate_dependency_unless_atomic(tmp_path):
    store = _store(tmp_path)
    root_id = store.put_candidate(_root_node("Root evidence supports local causal admission"))
    child_id = store.put_candidate(_dependent_node("Child depends on unadmitted root", root_id))

    with pytest.raises(CausalStoreError) as failure:
        _admit(store, child_id)
    assert failure.value.code == "DEPENDENCY_NOT_ADMITTED"

    result = _admit(store, root_id, child_id)
    assert result.admitted_node_ids == [root_id, child_id]
    assert store.get_node(child_id).status == "admitted"


def test_root_admission_requires_trusted_source(tmp_path):
    store = _store(tmp_path)
    node_id = store.put_candidate(
        CausalNodeDraft(
            content="Pure reasoning alone is not admitted root truth",
            semantic_summary="Pure reasoning root candidate",
            semantic_keys=["root", "candidate"],
            source_module="debate",
            root_kind="observation",
            dependency_groups=[],
        )
    )

    with pytest.raises(CausalStoreError) as failure:
        _admit(store, node_id)
    assert failure.value.code == "ROOT_SOURCE_REQUIRED"


def test_duplicate_hashes_block_exact_causal_duplicates(tmp_path):
    store = _store(tmp_path)
    first = _root_node("Duplicate causal identity should be rejected")
    store.put_candidate(first)

    with pytest.raises(CausalStoreError) as failure:
        store.put_candidate(first)
    assert failure.value.code == "DUPLICATE_NODE"


def test_invalidation_preserves_history_and_queues_revalidation(tmp_path):
    store = _store(tmp_path)
    root_id = store.put_candidate(_root_node("Invalidated predecessor should queue dependents"))
    _admit(store, root_id)
    child_id = store.put_candidate(
        _dependent_node("Dependent admitted node requires revalidation after predecessor invalidation", root_id)
    )
    _admit(store, child_id)

    result = store.invalidate_node(
        InvalidationRequest(
            node_id=root_id,
            invalidated_by_module="causal_review",
            reason="predecessor evidence was invalidated",
            invalidation_condition="source test report withdrawn",
        )
    )

    assert result.queued_revalidation_node_ids == [child_id]
    assert store.get_node(root_id).status == "invalidated"
    assert store.get_node(child_id).status == "admitted"

    search = store.search_nodes(CausalQuery(query="revalidation predecessor invalidation"))
    assert child_id not in [node.node_id for node in search.nodes]
    assert any(item.node_id == child_id and item.reason == "pending_revalidation" for item in search.rejected_nodes)


def test_revalidation_resolution_restores_node_when_alternate_group_remains_valid(tmp_path):
    store = _store(tmp_path)
    first_root = store.put_candidate(_root_node("First dependency can be invalidated"))
    second_root = store.put_candidate(_root_node("Second dependency remains admitted", evidence_ref="test-report-alt"))
    _admit(store, first_root, second_root)

    node_id = store.put_candidate(
        CausalNodeDraft(
            content="A node can remain valid through an alternate dependency group",
            semantic_summary="Alternate dependency group preserves causal usability",
            semantic_keys=["alternate", "dependency", "usable"],
            source_module="debate",
            dependency_groups=[
                CausalDependencyGroup(
                    causal_dependencies=[first_root],
                    evidence_refs=["test-report-first"],
                    scope="path one",
                    conditions=["first path applies"],
                    assumptions=["local project"],
                    confidence="medium",
                ),
                CausalDependencyGroup(
                    causal_dependencies=[second_root],
                    evidence_refs=["test-report-second"],
                    scope="path two",
                    conditions=["second path applies"],
                    assumptions=["local project"],
                    confidence="high",
                ),
            ],
        )
    )
    _admit(store, node_id)

    store.invalidate_node(
        InvalidationRequest(
            node_id=first_root,
            invalidated_by_module="master",
            reason="first path no longer applies",
        )
    )
    queue = store.list_revalidation_queue(status="pending", node_id=node_id)
    assert len(queue) == 1
    assert node_id not in [
        node.node_id
        for node in store.search_nodes(CausalQuery(query="alternate dependency usable")).nodes
    ]

    store.resolve_revalidation(
        RevalidationResolutionRequest(
            queue_id=queue[0].queue_id,
            status="resolved",
            rationale="second dependency group remains admitted and valid",
        )
    )

    search = store.search_nodes(CausalQuery(query="alternate dependency usable"))
    assert search.nodes[0].node_id == node_id


def test_rebuild_indexes_restores_recall_after_index_deletion(tmp_path):
    store = _store(tmp_path)
    node_id = store.put_candidate(_root_node("FTS rebuild restores causal recall"))
    _admit(store, node_id)

    with sqlite3.connect(store.db_path) as conn:
        conn.execute("DELETE FROM causal_nodes_fts")
        conn.execute("DELETE FROM causal_embeddings")
        conn.commit()

    assert store.search_nodes(CausalQuery(query="rebuild recall")).nodes == []

    result = store.rebuild_indexes()
    assert result.rebuilt_fts_rows == 1
    assert result.rebuilt_embedding_rows == 1
    assert [node.node_id for node in store.search_nodes(CausalQuery(query="rebuild recall")).nodes] == [node_id]


def test_schema_constraints_reject_invalid_ref_type_and_module(tmp_path):
    store = _store(tmp_path)
    with sqlite3.connect(store.db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO causal_nodes "
                "(node_id, node_uuid, created_at_utc, updated_at_utc, content, semantic_summary, "
                "status, source_module, root_kind, strict_content_hash, causal_identity_hash) "
                "VALUES (100, 'bad', 'now', 'now', 'bad', 'bad', 'candidate', 'unknown', NULL, 'a', 'b')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO causal_node_refs (node_id, ref_type, ref_id) VALUES (1, 'bad_ref', 'x')"
            )


def test_node_draft_rejects_empty_content_and_summary():
    with pytest.raises(ValueError):
        CausalNodeDraft(
            content="",
            semantic_summary="non-empty",
            source_module="test",
            root_kind="test_result",
        )

    with pytest.raises(ValueError):
        CausalNodeDraft(
            content="non-empty",
            semantic_summary="   ",
            source_module="test",
            root_kind="test_result",
        )


def test_store_rejects_unsupported_future_schema_version(tmp_path):
    store = _store(tmp_path)
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at_utc) VALUES (999, 'future', 'now')"
        )
        conn.commit()

    with pytest.raises(CausalStoreError) as failure:
        CausalStore(store.db_path)
    assert failure.value.code == "UNSUPPORTED_SCHEMA_VERSION"


def test_duplicate_dependency_group_id_returns_controlled_error(tmp_path):
    store = _store(tmp_path)
    parent_id = store.put_candidate(_root_node("Duplicate group parent is admitted"))
    _admit(store, parent_id)

    with pytest.raises(CausalStoreError) as failure:
        store.put_candidate(
            CausalNodeDraft(
                content="Duplicate dependency group ids must be rejected before sqlite writes",
                semantic_summary="Duplicate dependency group ids rejected",
                semantic_keys=["duplicate", "group"],
                source_module="debate",
                dependency_groups=[
                    CausalDependencyGroup(
                        group_id="duplicate-group",
                        causal_dependencies=[parent_id],
                        evidence_refs=["evidence/a"],
                    ),
                    CausalDependencyGroup(
                        group_id="duplicate-group",
                        causal_dependencies=[parent_id],
                        evidence_refs=["evidence/b"],
                    ),
                ],
            )
        )
    assert failure.value.code == "DUPLICATE_DEPENDENCY_GROUP"


def test_sqlite_write_failure_is_wrapped_and_rolled_back(tmp_path):
    store = _store(tmp_path)
    node_id = store.put_candidate(_root_node("Forced sqlite failure keeps status admitted"))
    _admit(store, node_id)

    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            """
            CREATE TRIGGER force_invalidation_failure
            BEFORE INSERT ON causal_invalidation_records
            BEGIN
              SELECT RAISE(ABORT, 'forced invalidation audit failure');
            END;
            """
        )
        conn.commit()

    try:
        with pytest.raises(CausalStoreError) as failure:
            store.invalidate_node(
                InvalidationRequest(
                    node_id=node_id,
                    invalidated_by_module="causal_review",
                    reason="forced rollback test",
                )
            )
        assert failure.value.code == "SQLITE_WRITE_FAILED"
        assert store.get_node(node_id).status == "admitted"
    finally:
        with sqlite3.connect(store.db_path) as conn:
            conn.execute("DROP TRIGGER IF EXISTS force_invalidation_failure")
            conn.commit()


def test_scope_filter_excludes_mismatched_dependency_group_scope(tmp_path):
    store = _store(tmp_path)
    parent_id = store.put_candidate(_root_node("Scope parent is admitted"))
    _admit(store, parent_id)
    debate_node = store.put_candidate(
        CausalNodeDraft(
            content="Scope filtered debate topology",
            semantic_summary="Scope filtered debate topology",
            semantic_keys=["scope", "filtered", "topology"],
            source_module="debate",
            dependency_groups=[
                CausalDependencyGroup(
                    causal_dependencies=[parent_id],
                    evidence_refs=["test/scope-debate"],
                    scope="debate runtime",
                )
            ],
        )
    )
    execution_node = store.put_candidate(
        CausalNodeDraft(
            content="Scope filtered execution topology",
            semantic_summary="Scope filtered execution topology",
            semantic_keys=["scope", "filtered", "topology"],
            source_module="execution",
            dependency_groups=[
                CausalDependencyGroup(
                    causal_dependencies=[parent_id],
                    evidence_refs=["test/scope-execution"],
                    scope="execution runtime",
                )
            ],
        )
    )
    _admit(store, debate_node, execution_node)

    result = store.search_nodes(
        CausalQuery(query="scope filtered topology", required_scope="debate runtime")
    )

    assert debate_node in [node.node_id for node in result.nodes]
    assert execution_node not in [node.node_id for node in result.nodes]
    assert any(item.node_id == execution_node and item.reason == "scope_mismatch" for item in result.rejected_nodes)


def test_near_duplicate_requires_review_for_same_content_different_identity(tmp_path):
    store = _store(tmp_path)
    parent_id = store.put_candidate(_root_node("Near duplicate parent"))
    _admit(store, parent_id)
    store.put_candidate(_root_node("Same causal wording with different basis"))

    with pytest.raises(CausalStoreError) as failure:
        store.put_candidate(
            CausalNodeDraft(
                content="Same causal wording with different basis",
                semantic_summary="Same causal wording with different basis",
                semantic_keys=["near", "duplicate"],
                source_module="debate",
                dependency_groups=[
                    CausalDependencyGroup(
                        causal_dependencies=[parent_id],
                        evidence_refs=["test/near-duplicate"],
                    )
                ],
            )
        )
    assert failure.value.code == "NEAR_DUPLICATE_REVIEW_REQUIRED"


def test_core_lookup_query_plans_use_indexes(tmp_path):
    store = _store(tmp_path)
    parent_id = store.put_candidate(_root_node("Query plan parent"))
    _admit(store, parent_id)
    child_id = store.put_candidate(_dependent_node("Query plan child", parent_id))
    _admit(store, child_id)
    store.invalidate_node(
        InvalidationRequest(
            node_id=parent_id,
            invalidated_by_module="causal_review",
            reason="query plan revalidation seed",
        )
    )

    with sqlite3.connect(store.db_path) as conn:
        node_term_plan = " ".join(
            str(item)
            for row in conn.execute(
                "EXPLAIN QUERY PLAN SELECT * FROM causal_node_terms WHERE term IN ('query')"
            )
            for item in row
        )
        revalidation_plan = " ".join(
            str(item)
            for row in conn.execute(
                "EXPLAIN QUERY PLAN SELECT * FROM causal_revalidation_queue WHERE node_id = ? AND status = 'pending'",
                (child_id,),
            )
            for item in row
        )

    assert "idx_causal_node_terms_term_node" in node_term_plan
    assert "idx_revalidation_node_status" in revalidation_plan or "idx_revalidation_status_node" in revalidation_plan
