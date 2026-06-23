import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from aegis.stores.knowledge import (
    AdmissionRequest,
    ApplicabilityProfile,
    EvidencePointer,
    EvidenceRef,
    InvalidationRequest,
    InvalidationRule,
    KnowledgeFactDraft,
    KnowledgeQueryContext,
    KnowledgeStore,
    KnowledgeStoreError,
    SupersessionRequest,
)


def _store(tmp_path) -> KnowledgeStore:
    return KnowledgeStore(tmp_path / ".aegis" / "stores" / "knowledge" / "knowledge.sqlite3")


def _evidence(ref_id: str) -> EvidenceRef:
    return EvidenceRef(
        ref_type="test",
        ref_id=ref_id,
        verifier="test",
        verification_method="hardening test evidence",
    )


def _profile(scope: dict | None = None, *, conditions: list[str] | None = None) -> ApplicabilityProfile:
    return ApplicabilityProfile(
        applicability_scope=scope or {"project": "demo"},
        affected_entities=["project"],
        affected_operations=["runtime_selection"],
        affected_qualities=["compatibility"],
        required_conditions=conditions or [],
        risk_classes=["compatibility"],
        task_intents=["implementation"],
        lifecycle_phases=["implementation"],
        must_consider_when=["runtime_selection"],
        exclude_when=[],
        priority="normal",
    )


def _fact(
    text: str,
    *,
    ref_id: str,
    subject_kind: str = "runtime",
    object_kind: str = "version",
    object_json: dict | None = None,
    scope: dict | None = None,
) -> KnowledgeFactDraft:
    return KnowledgeFactDraft(
        fact_kind="platform",
        subject_kind=subject_kind,
        subject_id="project.python",
        subject_attributes={"project": "demo"},
        predicate="version_is",
        object_kind=object_kind,
        object=object_json or {"version": text},
        unit=None,
        qualifiers={},
        fact_validity_scope=scope or {"project": "demo", "runtime": "python"},
        semantic_summary=f"Python runtime version is {text}",
        semantic_keys=["Python", text, "运行时"],
        source_module="master",
        evidence_refs=[_evidence(ref_id)],
        applicability_profile=_profile(scope),
        invalidation_rules=[
            InvalidationRule(
                invalidation_condition="runtime version changes",
                affected_scope={"project": "demo"},
                revalidation_required=True,
            )
        ],
    )


def _admit(store: KnowledgeStore, knowledge_id: int, ref_id: str) -> None:
    store.admit_fact(
        AdmissionRequest(
            knowledge_id=knowledge_id,
            admitted_by_module="master",
            admission_method="repository_inspected",
            rationale="accepted for hardening test",
            evidence_refs=[EvidencePointer(ref_type="test", ref_id=ref_id)],
        )
    )


def _returned_ids(result) -> list[int]:
    return [
        fact.knowledge_id
        for fact in [*result.mandatory_facts, *result.supplemental_facts]
    ]


def test_schema_rejects_invalid_subject_and_object_kind(tmp_path):
    store = _store(tmp_path)

    with pytest.raises(ValueError):
        _fact("3.11", ref_id="test/invalid-subject", subject_kind="nonsense")

    with pytest.raises(ValueError):
        _fact("3.11", ref_id="test/invalid-object", object_kind="nonsense")

    with sqlite3.connect(store.db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO knowledge_facts (
                  knowledge_uuid, created_at_utc, updated_at_utc, status, fact_kind,
                  subject_kind, subject_id, subject_attributes_json, predicate,
                  object_kind, object_json, qualifiers_json, fact_validity_scope_json,
                  semantic_summary, source_module, fact_identity_hash, strict_content_hash
                )
                VALUES (
                  'bad-subject', 'now', 'now', 'candidate', 'platform',
                  'nonsense', 'x', '{}', 'version_is',
                  'version', '{}', '{}', '{}',
                  'bad', 'master', 'hash-a', 'hash-b'
                )
                """
            )


def test_duplicate_fact_identity_is_blocked_under_concurrency(tmp_path):
    store = _store(tmp_path)
    draft = _fact("3.11", ref_id="test/concurrent-identity")

    def insert_once() -> tuple[str, int | str]:
        local_store = KnowledgeStore(store.db_path)
        try:
            return ("ok", local_store.put_candidate(draft))
        except KnowledgeStoreError as exc:
            return ("error", exc.code)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _index: insert_once(), range(16)))

    persisted = [value for status, value in results if status == "ok"]
    errors = [value for status, value in results if status == "error"]

    assert len(persisted) == 1
    assert set(errors) == {"DUPLICATE_FACT"}


def test_supersession_enforces_statuses_and_preserves_failed_state(tmp_path):
    store = _store(tmp_path)
    old_candidate = store.put_candidate(_fact("3.10", ref_id="test/old-candidate"))
    admitted_old = store.put_candidate(_fact("3.11", ref_id="test/admitted-old"))
    admitted_new = store.put_candidate(_fact("3.12", ref_id="test/admitted-new"))
    candidate_new = store.put_candidate(_fact("3.13", ref_id="test/candidate-new"))
    _admit(store, admitted_old, "test/admitted-old")
    _admit(store, admitted_new, "test/admitted-new")

    with pytest.raises(KnowledgeStoreError) as self_error:
        store.supersede_fact(
            SupersessionRequest(
                old_knowledge_id=admitted_old,
                new_knowledge_id=admitted_old,
                reason="self replacement is invalid",
            )
        )
    assert self_error.value.code == "SELF_SUPERSESSION_FORBIDDEN"

    with pytest.raises(KnowledgeStoreError) as old_status_error:
        store.supersede_fact(
            SupersessionRequest(
                old_knowledge_id=old_candidate,
                new_knowledge_id=admitted_new,
                reason="candidate old fact cannot be superseded",
            )
        )
    assert old_status_error.value.code == "INVALID_SUPERSEDED_STATUS"

    with pytest.raises(KnowledgeStoreError) as new_status_error:
        store.supersede_fact(
            SupersessionRequest(
                old_knowledge_id=admitted_old,
                new_knowledge_id=candidate_new,
                reason="candidate replacement cannot supersede admitted fact",
            )
        )
    assert new_status_error.value.code == "SUPERSESSION_REPLACEMENT_NOT_ADMITTED"
    assert store.get_fact(admitted_old).status == "admitted"
    assert store.get_fact(candidate_new).status == "candidate"

    store.supersede_fact(
        SupersessionRequest(
            old_knowledge_id=admitted_old,
            new_knowledge_id=admitted_new,
            reason="new admitted fact supersedes old admitted fact",
        )
    )
    assert store.get_fact(admitted_old).status == "superseded"


def test_invalidation_evidence_ref_pair_and_type_are_checked(tmp_path):
    store = _store(tmp_path)
    knowledge_id = store.put_candidate(_fact("3.11", ref_id="test/invalidate"))
    _admit(store, knowledge_id, "test/invalidate")

    with pytest.raises(ValueError):
        InvalidationRequest(
            knowledge_id=knowledge_id,
            invalidated_by_module="knowledge_review",
            reason="invalid evidence type",
            evidence_ref=EvidencePointer(ref_type="manual_admission", ref_id="bad"),
        )

    with sqlite3.connect(store.db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO knowledge_invalidation_records (
                  knowledge_id, invalidated_at_utc, invalidated_by_module,
                  reason, evidence_ref_type, evidence_ref_id
                )
                VALUES (?, 'now', 'knowledge_review', 'bad pair', 'test', NULL)
                """,
                (knowledge_id,),
            )

    store.invalidate_fact(
        InvalidationRequest(
            knowledge_id=knowledge_id,
            invalidated_by_module="knowledge_review",
            reason="runtime version changed",
            evidence_ref=EvidencePointer(ref_type="test", ref_id="test/invalidate"),
        )
    )
    assert store.get_fact(knowledge_id).status == "invalidated"


def test_conflict_detection_is_conservative_and_does_not_auto_resolve(tmp_path):
    store = _store(tmp_path)
    first = store.put_candidate(_fact("3.11", ref_id="test/python-311"))
    _admit(store, first, "test/python-311")
    second = store.put_candidate(_fact("3.12", ref_id="test/python-312"))
    _admit(store, second, "test/python-312")

    conflicts = store.list_conflicts()
    assert len(conflicts) == 1
    assert {conflicts[0].left_knowledge_id, conflicts[0].right_knowledge_id} == {first, second}
    assert conflicts[0].status == "open"

    same_object = store.put_candidate(
        _fact("3.12", ref_id="test/python-312-alt", scope={"project": "demo", "runtime": "python-alt"})
    )
    _admit(store, same_object, "test/python-312-alt")
    assert len(store.list_conflicts()) == 1


def test_cjk_mixed_language_recall_and_fts_degradation_warning(tmp_path):
    store = _store(tmp_path)
    knowledge_id = store.put_candidate(_fact("3.11", ref_id="test/cjk"))
    _admit(store, knowledge_id, "test/cjk")

    result = store.query(
        KnowledgeQueryContext(
            project_id="demo",
            task_intents=["implementation"],
            lifecycle_phase="implementation",
            affected_entities=["project"],
            operations=["runtime_selection"],
            qualities=["compatibility"],
            conditions=[],
            risk_classes=["compatibility"],
            subject_refs=[{"subject_kind": "runtime", "subject_id": "python"}],
            query_terms=["Python 运行时"],
            required_dimensions=[],
        )
    )
    assert knowledge_id in _returned_ids(result)

    with sqlite3.connect(store.db_path) as conn:
        conn.execute("DROP TABLE knowledge_facts_fts")
        indexed_tokens = {
            row[0]
            for row in conn.execute(
                """
                SELECT token
                FROM knowledge_semantic_tokens
                WHERE knowledge_id = ?
                """,
                (knowledge_id,),
            )
        }
        conn.commit()
    assert {"python", "运行时"}.issubset(indexed_tokens)

    degraded = store.query(
        KnowledgeQueryContext(
            project_id="demo",
            task_intents=["implementation"],
            lifecycle_phase="implementation",
            affected_entities=["project"],
            operations=["runtime_selection"],
            qualities=["compatibility"],
            conditions=[],
            risk_classes=["compatibility"],
            subject_refs=[{"subject_kind": "runtime", "subject_id": "python"}],
            query_terms=["Python 运行时"],
            required_dimensions=[],
        )
    )
    assert degraded.degraded_recall_warnings
    assert knowledge_id in _returned_ids(degraded)


def test_backup_restore_snapshot_preserves_query_behavior(tmp_path):
    store = _store(tmp_path)
    knowledge_id = store.put_candidate(_fact("3.11", ref_id="test/backup"))
    _admit(store, knowledge_id, "test/backup")
    backup_path = tmp_path / "backup.sqlite3"

    store.backup_to(backup_path)
    restored = KnowledgeStore(backup_path)
    result = restored.query(
        KnowledgeQueryContext(
            project_id="demo",
            task_intents=["implementation"],
            lifecycle_phase="implementation",
            affected_entities=["project"],
            operations=["runtime_selection"],
            qualities=["compatibility"],
            conditions=[],
            risk_classes=["compatibility"],
            subject_refs=[{"subject_kind": "runtime", "subject_id": "python"}],
            query_terms=["Python 3.11"],
            required_dimensions=[],
        )
    )

    assert knowledge_id in _returned_ids(result)
    assert restored.integrity_check() == {"integrity_check": "ok", "foreign_key_violations": []}
