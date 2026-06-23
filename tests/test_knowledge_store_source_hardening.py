import math
import sqlite3

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
    NeedRule,
    QueueRevalidationRequest,
    ResolveRevalidationRequest,
)


def _store(tmp_path) -> KnowledgeStore:
    return KnowledgeStore(tmp_path / ".aegis" / "stores" / "knowledge" / "knowledge.sqlite3")


def _evidence(ref_id: str) -> EvidenceRef:
    return EvidenceRef(
        ref_type="test",
        ref_id=ref_id,
        verifier="test",
        verification_method="source hardening test evidence",
    )


def _profile(**overrides) -> ApplicabilityProfile:
    data = {
        "applicability_scope": {"project": "demo"},
        "affected_entities": [],
        "affected_operations": [],
        "affected_qualities": [],
        "required_conditions": [],
        "risk_classes": [],
        "task_intents": ["implementation"],
        "lifecycle_phases": [],
        "must_consider_when": [],
        "exclude_when": [],
        "priority": "normal",
    }
    data.update(overrides)
    return ApplicabilityProfile(**data)


def _fact(
    *,
    ref_id: str,
    subject_kind: str = "runtime",
    subject_id: str = "python",
    predicate: str = "version_is",
    object_value=None,
    semantic_summary: str = "Python target runtime version is 3.11",
    semantic_keys: list[str] | None = None,
    validity_scope: dict | None = None,
    profile: ApplicabilityProfile | None = None,
    no_known_invalidation: bool = False,
) -> KnowledgeFactDraft:
    invalidation_rules = [] if no_known_invalidation else [
        InvalidationRule(
            invalidation_condition="runtime version changes",
            affected_scope={"project": "demo"},
            revalidation_required=True,
        )
    ]
    return KnowledgeFactDraft(
        fact_kind="platform",
        subject_kind=subject_kind,
        subject_id=subject_id,
        subject_attributes={"project": "demo"},
        predicate=predicate,
        object_kind="version",
        object=object_value or {"version": "3.11"},
        qualifiers={},
        fact_validity_scope=validity_scope or {"project": "demo", "runtime": subject_id},
        semantic_summary=semantic_summary,
        semantic_keys=semantic_keys or ["target runtime version", "python"],
        source_module="master",
        evidence_refs=[_evidence(ref_id)],
        applicability_profile=profile or _profile(),
        invalidation_rules=invalidation_rules,
        no_known_invalidation=no_known_invalidation,
    )


def _admit(store: KnowledgeStore, knowledge_id: int, ref_id: str) -> None:
    store.admit_fact(
        AdmissionRequest(
            knowledge_id=knowledge_id,
            admitted_by_module="master",
            admission_method="repository_inspected",
            rationale="accepted for source hardening test",
            evidence_refs=[EvidencePointer(ref_type="test", ref_id=ref_id)],
        )
    )


def _returned_fact_ids(result) -> set[int]:
    return {
        fact.knowledge_id
        for fact in [*result.mandatory_facts, *result.supplemental_facts]
    }


def test_task_intent_only_profile_can_be_mandatory_recalled(tmp_path):
    store = _store(tmp_path)
    knowledge_id = store.put_candidate(
        _fact(
            ref_id="test/task-intent-only",
            profile=_profile(task_intents=["deploy"]),
        )
    )
    _admit(store, knowledge_id, "test/task-intent-only")

    result = store.query(
        KnowledgeQueryContext(
            project_id="demo",
            task_intents=["deploy"],
            lifecycle_phase="planning",
            subject_refs=[{"subject_kind": "runtime", "subject_id": "python"}],
        )
    )

    assert [fact.knowledge_id for fact in result.mandatory_facts] == [knowledge_id]


def test_fact_validity_scope_blocks_wrong_host(tmp_path):
    store = _store(tmp_path)
    knowledge_id = store.put_candidate(
        _fact(
            ref_id="test/server-a",
            subject_kind="host",
            subject_id="server-A",
            semantic_summary="Server-A storage controller is unstable under high load",
            semantic_keys=["server-A", "high load storage"],
            validity_scope={"project": "demo", "host": "server-A"},
            profile=_profile(affected_entities=["server-A"], task_intents=["benchmark"]),
        )
    )
    _admit(store, knowledge_id, "test/server-a")

    result = store.query(
        KnowledgeQueryContext(
            project_id="demo",
            task_intents=["benchmark"],
            lifecycle_phase="implementation",
            affected_entities=["server-B"],
            query_terms=["server-B high load storage"],
        )
    )

    assert result.mandatory_facts == []
    assert result.supplemental_facts == []


def test_free_text_query_terms_cannot_satisfy_project_validity_scope(tmp_path):
    store = _store(tmp_path)
    knowledge_id = store.put_candidate(
        _fact(
            ref_id="test/project-a-runtime-free-text",
            validity_scope={"project": "project-A", "runtime": "python"},
            profile=_profile(applicability_scope={"project": "project-A"}, task_intents=["deploy"]),
        )
    )
    _admit(store, knowledge_id, "test/project-a-runtime-free-text")

    result = store.query(
        KnowledgeQueryContext(
            project_id="project-B",
            task_intents=["deploy"],
            lifecycle_phase="planning",
            subject_refs=[{"subject_kind": "runtime", "subject_id": "python"}],
            query_terms=["project-A"],
        )
    )

    assert result.mandatory_facts == []
    assert result.supplemental_facts == []
    assert [(fact.knowledge_id, fact.reason) for fact in result.rejected_facts] == [
        (knowledge_id, "fact_validity_scope_mismatch")
    ]


def test_free_text_query_terms_cannot_satisfy_host_validity_scope(tmp_path):
    store = _store(tmp_path)
    knowledge_id = store.put_candidate(
        _fact(
            ref_id="test/server-a-host-free-text",
            subject_kind="host",
            subject_id="server-A",
            semantic_summary="Server-A storage controller is unstable under high load",
            semantic_keys=["server-A", "storage controller"],
            validity_scope={"project": "demo", "host": "server-A"},
            profile=_profile(affected_entities=["server-A"], task_intents=["benchmark"]),
        )
    )
    _admit(store, knowledge_id, "test/server-a-host-free-text")

    result = store.query(
        KnowledgeQueryContext(
            project_id="demo",
            task_intents=["benchmark"],
            lifecycle_phase="implementation",
            subject_refs=[{"subject_kind": "host", "subject_id": "server-B"}],
            affected_entities=["server-B"],
            query_terms=["server-A"],
        )
    )

    assert result.mandatory_facts == []
    assert result.supplemental_facts == []
    assert [(fact.knowledge_id, fact.reason) for fact in result.rejected_facts] == [
        (knowledge_id, "fact_validity_scope_mismatch")
    ]


def test_missing_need_requires_scope_and_dimension_matching_fact(tmp_path):
    store = _store(tmp_path)
    store.register_need_rule(
        NeedRule(
            rule_id="need-target-runtime-version",
            required_dimension="target_runtime_version",
            trigger_task_intents=["deploy"],
            required_subject_kinds=["runtime"],
            acceptable_sources=["repository_source"],
            default_blocking_level="hard_block",
            rationale="deployment requires scoped target runtime version",
        )
    )
    project_a_fact = store.put_candidate(
        _fact(
            ref_id="test/project-a-runtime",
            validity_scope={"project": "project-A", "runtime": "python"},
            profile=_profile(applicability_scope={"project": "project-A"}, task_intents=["deploy"]),
        )
    )
    _admit(store, project_a_fact, "test/project-a-runtime")

    missing = store.query(
        KnowledgeQueryContext(
            project_id="project-B",
            task_intents=["deploy"],
            lifecycle_phase="planning",
            subject_refs=[{"subject_kind": "runtime", "subject_id": "python"}],
        )
    )
    assert [need.rule_id for need in missing.missing_knowledge_needs] == [
        "need-target-runtime-version"
    ]

    project_b_fact = store.put_candidate(
        _fact(
            ref_id="test/project-b-runtime",
            validity_scope={"project": "project-B", "runtime": "python"},
            profile=_profile(applicability_scope={"project": "project-B"}, task_intents=["deploy"]),
        )
    )
    _admit(store, project_b_fact, "test/project-b-runtime")

    satisfied = store.query(
        KnowledgeQueryContext(
            project_id="project-B",
            task_intents=["deploy"],
            lifecycle_phase="planning",
            subject_refs=[{"subject_kind": "runtime", "subject_id": "python"}],
        )
    )
    assert satisfied.missing_knowledge_needs == []


def test_free_text_scope_mention_does_not_clear_missing_need_for_wrong_project(tmp_path):
    store = _store(tmp_path)
    store.register_need_rule(
        NeedRule(
            rule_id="need-target-runtime-version",
            required_dimension="target_runtime_version",
            trigger_task_intents=["deploy"],
            required_subject_kinds=["runtime"],
            acceptable_sources=["repository_source"],
            default_blocking_level="hard_block",
            rationale="deployment requires scoped target runtime version",
        )
    )
    project_a_fact = store.put_candidate(
        _fact(
            ref_id="test/project-a-runtime-free-text-need",
            validity_scope={"project": "project-A", "runtime": "python"},
            profile=_profile(applicability_scope={"project": "project-A"}, task_intents=["deploy"]),
        )
    )
    _admit(store, project_a_fact, "test/project-a-runtime-free-text-need")

    result = store.query(
        KnowledgeQueryContext(
            project_id="project-B",
            task_intents=["deploy"],
            lifecycle_phase="planning",
            subject_refs=[{"subject_kind": "runtime", "subject_id": "python"}],
            query_terms=["project-A"],
        )
    )

    assert result.mandatory_facts == []
    assert result.supplemental_facts == []
    assert [need.rule_id for need in result.missing_knowledge_needs] == [
        "need-target-runtime-version"
    ]


def test_applicability_term_lookup_uses_term_leading_index(tmp_path):
    store = _store(tmp_path)
    with sqlite3.connect(store.db_path) as conn:
        plan = [
            row[3]
            for row in conn.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT knowledge_id
                FROM knowledge_applicability_terms
                WHERE term IN (?)
                ORDER BY knowledge_id
                """,
                ("deploy",),
            )
        ]

    assert any(
        "SEARCH knowledge_applicability_terms" in step
        and "idx_knowledge_applicability_term_value" in step
        for step in plan
    ), plan


def test_cjk_partial_phrase_recall_uses_ngram_tokens_when_fts_is_unavailable(tmp_path):
    store = _store(tmp_path)
    knowledge_id = store.put_candidate(
        _fact(
            ref_id="test/cjk-ngram",
            semantic_summary="高负载存储读取性能会下降",
            semantic_keys=["高负载存储读取性能", "吞吐下降"],
            profile=_profile(must_consider_when=["高负载存储读取性能"]),
        )
    )
    _admit(store, knowledge_id, "test/cjk-ngram")

    with sqlite3.connect(store.db_path) as conn:
        conn.execute("DROP TABLE knowledge_facts_fts")
        conn.commit()

    result = store.query(
        KnowledgeQueryContext(
            project_id="demo",
            task_intents=["implementation"],
            lifecycle_phase="implementation",
            subject_refs=[{"subject_kind": "runtime", "subject_id": "python"}],
            query_terms=["存储读取"],
        )
    )

    assert knowledge_id in _returned_fact_ids(result)
    assert result.degraded_recall_warnings
    assert result.query_plan["fallback_token_lookup_used"] is True


def test_invalidation_rule_must_belong_to_invalidated_fact(tmp_path):
    store = _store(tmp_path)
    first = store.put_candidate(_fact(ref_id="test/first"))
    second = store.put_candidate(_fact(ref_id="test/second", subject_id="python-alt"))
    _admit(store, first, "test/first")
    _admit(store, second, "test/second")
    other_rule_id = store.get_fact(second).invalidation_rules[0].rule_id

    with pytest.raises(KnowledgeStoreError) as error:
        store.invalidate_fact(
            InvalidationRequest(
                knowledge_id=first,
                invalidated_by_module="knowledge_review",
                reason="wrong rule ownership must fail",
                triggered_rule_id=other_rule_id,
            )
        )

    assert error.value.code == "INVALIDATION_RULE_NOT_OWNED_BY_FACT"
    assert store.get_fact(first).status == "admitted"


def test_no_known_invalidation_and_revalidation_queue_are_auditable(tmp_path):
    store = _store(tmp_path)
    knowledge_id = store.put_candidate(
        _fact(
            ref_id="test/no-known-invalidation",
            no_known_invalidation=True,
        )
    )
    _admit(store, knowledge_id, "test/no-known-invalidation")

    assert store.get_fact(knowledge_id).no_known_invalidation is True

    queued = store.queue_revalidation(
        QueueRevalidationRequest(
            knowledge_id=knowledge_id,
            trigger_type="dependency_changed",
            reason="dependency lockfile changed",
        )
    )
    hidden = store.query(
        KnowledgeQueryContext(
            project_id="demo",
            task_intents=["implementation"],
            lifecycle_phase="implementation",
            subject_refs=[{"subject_kind": "runtime", "subject_id": "python"}],
            query_terms=["python runtime"],
        )
    )
    assert knowledge_id not in [fact.knowledge_id for fact in hidden.supplemental_facts]

    store.resolve_revalidation(
        ResolveRevalidationRequest(
            queue_id=queued.queue_id,
            resolution_rationale="fact remains valid",
        )
    )
    visible = store.query(
        KnowledgeQueryContext(
            project_id="demo",
            task_intents=["implementation"],
            lifecycle_phase="implementation",
            subject_refs=[{"subject_kind": "runtime", "subject_id": "python"}],
            query_terms=["python runtime"],
        )
    )
    assert knowledge_id in _returned_fact_ids(visible)


def test_canonical_json_normalizes_unicode_and_rejects_non_finite_numbers(tmp_path):
    store = _store(tmp_path)
    nfc = store.put_candidate(
        _fact(
            ref_id="test/nfc",
            subject_id="café",
            validity_scope={"project": "demo", "runtime": "café"},
            profile=_profile(task_intents=["unicode"]),
        )
    )
    with pytest.raises(KnowledgeStoreError) as duplicate:
        store.put_candidate(
            _fact(
                ref_id="test/nfd",
                subject_id="cafe\u0301",
                validity_scope={"runtime": "cafe\u0301", "project": "demo"},
                profile=_profile(task_intents=["unicode"]),
            )
        )
    assert duplicate.value.code == "DUPLICATE_FACT"
    assert store.get_fact(nfc).subject_id == "café"

    with pytest.raises(ValueError):
        store.put_candidate(
            _fact(
                ref_id="test/nan",
                subject_id="nan-runtime",
                object_value={"version": math.nan},
                validity_scope={"project": "demo", "runtime": "nan-runtime"},
            )
        )
