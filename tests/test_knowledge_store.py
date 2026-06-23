import sqlite3

import pytest
from pydantic import ValidationError

from aegis.stores.knowledge import (
    AdmissionRequest,
    ApplicabilityProfile,
    EvidencePointer,
    EvidenceRef,
    InvalidationRule,
    KnowledgeFactDraft,
    KnowledgeQueryContext,
    KnowledgeStore,
    KnowledgeStoreError,
    NeedRule,
    RejectionRequest,
)


def _store(tmp_path) -> KnowledgeStore:
    return KnowledgeStore(tmp_path / ".aegis" / "stores" / "knowledge" / "knowledge.sqlite3")


def _evidence(ref_id: str = "test/evidence-1") -> EvidenceRef:
    return EvidenceRef(
        ref_type="test",
        ref_id=ref_id,
        verifier="test",
        verification_method="deterministic test evidence",
    )


def _profile(**overrides) -> ApplicabilityProfile:
    data = {
        "applicability_scope": {"project": "demo"},
        "affected_entities": ["server-A"],
        "affected_operations": ["storage_read"],
        "affected_qualities": ["throughput"],
        "required_conditions": ["high_load", "server-A"],
        "risk_classes": ["performance_regression"],
        "task_intents": ["benchmark"],
        "lifecycle_phases": ["implementation"],
        "must_consider_when": ["high_load_storage_read_performance"],
        "exclude_when": ["host_not_server-A"],
        "priority": "high",
    }
    data.update(overrides)
    return ApplicabilityProfile(**data)


def _fact(
    *,
    subject_id: str = "server-A.storage-controller.X123",
    predicate: str = "degrades",
    object_json: dict | None = None,
    evidence: EvidenceRef | None = None,
    profile: ApplicabilityProfile | None = None,
    source_module: str = "test",
) -> KnowledgeFactDraft:
    return KnowledgeFactDraft(
        fact_kind="environment",
        subject_kind="device",
        subject_id=subject_id,
        subject_attributes={"host": "server-A", "component": "X123"},
        predicate=predicate,
        object_kind="range",
        object=object_json
        or {"metric": "cpu_storage_read_throughput", "lower_percent": 12, "upper_percent": 18},
        unit="percent",
        qualifiers={"condition": "high_load"},
        fact_validity_scope={"host": "server-A", "component": "X123", "condition": "high_load"},
        semantic_summary="Server-A X123 aging reduces storage-read throughput under high load",
        semantic_keys=["server-A", "X123 aging", "storage read throughput", "高负载"],
        source_module=source_module,
        evidence_refs=[evidence or _evidence()],
        applicability_profile=profile or _profile(),
        invalidation_rules=[
            InvalidationRule(
                invalidation_condition="component X123 is replaced",
                affected_scope={"host": "server-A"},
                revalidation_required=True,
            )
        ],
    )


def _admit(store: KnowledgeStore, knowledge_id: int) -> None:
    store.admit_fact(
        AdmissionRequest(
            knowledge_id=knowledge_id,
            admitted_by_module="master",
            admission_method="test_verified",
            rationale="accepted by knowledge store test",
            evidence_refs=[EvidencePointer(ref_type="test", ref_id="test/evidence-1")],
        )
    )


def test_candidate_admission_and_mandatory_applicability_recall(tmp_path):
    store = _store(tmp_path)
    knowledge_id = store.put_candidate(_fact())
    _admit(store, knowledge_id)

    result = store.query(
        KnowledgeQueryContext(
            project_id="demo",
            task_intents=["benchmark"],
            lifecycle_phase="implementation",
            affected_entities=["server-A"],
            operations=["storage_read"],
            qualities=["throughput"],
            conditions=["high_load", "server-A"],
            risk_classes=["performance_regression"],
            subject_refs=[{"subject_kind": "device", "subject_id": "server-A.storage-controller.X123"}],
            query_terms=["ordinary benchmark question without aging keyword"],
            required_dimensions=[],
        )
    )

    assert [fact.knowledge_id for fact in result.mandatory_facts] == [knowledge_id]
    assert result.missing_knowledge_needs == []
    assert result.query_plan["full_scan_used"] is False


def test_exclude_when_overrides_must_consider_when(tmp_path):
    store = _store(tmp_path)
    knowledge_id = store.put_candidate(_fact())
    _admit(store, knowledge_id)

    result = store.query(
        KnowledgeQueryContext(
            project_id="demo",
            task_intents=["benchmark"],
            lifecycle_phase="implementation",
            affected_entities=["server-B"],
            operations=["storage_read"],
            qualities=["throughput"],
            conditions=["high_load", "host_not_server-A"],
            risk_classes=["performance_regression"],
            query_terms=["high load storage read"],
            required_dimensions=[],
        )
    )

    assert result.mandatory_facts == []
    assert result.rejected_facts[0].knowledge_id == knowledge_id
    assert result.rejected_facts[0].reason == "excluded_by_applicability_profile"


def test_missing_knowledge_need_requires_deterministic_rule_id(tmp_path):
    store = _store(tmp_path)
    store.register_need_rule(
        NeedRule(
            rule_id="need-target-runtime-version",
            required_dimension="target_runtime_version",
            trigger_terms=["deploy"],
            trigger_task_intents=["deploy"],
            trigger_operations=[],
            trigger_qualities=[],
            required_subject_kinds=["runtime"],
            acceptable_sources=["repository_source", "platform_doc"],
            default_blocking_level="hard_block",
            rationale="deployment requires a known target runtime version",
        )
    )

    result = store.query(
        KnowledgeQueryContext(
            project_id="demo",
            task_intents=["deploy"],
            lifecycle_phase="planning",
            affected_entities=[],
            operations=[],
            qualities=[],
            conditions=[],
            risk_classes=[],
            query_terms=["deploy service"],
            required_dimensions=[],
        )
    )

    assert len(result.missing_knowledge_needs) == 1
    need = result.missing_knowledge_needs[0]
    assert need.rule_id == "need-target-runtime-version"
    assert need.blocking_level == "hard_block"


def test_rejection_is_audited_and_hidden_from_default_retrieval(tmp_path):
    store = _store(tmp_path)
    knowledge_id = store.put_candidate(_fact())

    store.reject_candidate(
        RejectionRequest(
            knowledge_id=knowledge_id,
            rejected_by_module="knowledge_review",
            reason="developer claim alone is insufficient",
            missing_fields=["verified evidence"],
            evidence_review={"developer_claim_only": True},
        )
    )

    assert store.get_fact(knowledge_id).status == "rejected"
    result = store.query(
        KnowledgeQueryContext(
            project_id="demo",
            task_intents=["benchmark"],
            lifecycle_phase="implementation",
            affected_entities=["server-A"],
            operations=["storage_read"],
            qualities=["throughput"],
            conditions=["high_load", "server-A"],
            risk_classes=["performance_regression"],
            query_terms=["storage read"],
            required_dimensions=[],
        )
    )
    assert result.mandatory_facts == []

    with sqlite3.connect(store.db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM knowledge_rejection_records WHERE knowledge_id = ?",
            (knowledge_id,),
        ).fetchone()[0]
    assert count == 1


def test_admission_requires_authorized_module_and_registered_evidence(tmp_path):
    store = _store(tmp_path)
    knowledge_id = store.put_candidate(_fact())

    with pytest.raises(ValidationError):
        AdmissionRequest(
            knowledge_id=knowledge_id,
            admitted_by_module="test",
            admission_method="test_verified",
            rationale="test verifies but cannot admit",
            evidence_refs=[EvidencePointer(ref_type="test", ref_id="test/evidence-1")],
        )

    with pytest.raises(KnowledgeStoreError) as missing_evidence:
        store.admit_fact(
            AdmissionRequest(
                knowledge_id=knowledge_id,
                admitted_by_module="master",
                admission_method="test_verified",
                rationale="missing evidence must fail",
                evidence_refs=[EvidencePointer(ref_type="test", ref_id="missing")],
            )
        )
    assert missing_evidence.value.code == "ADMISSION_EVIDENCE_NOT_REGISTERED"
