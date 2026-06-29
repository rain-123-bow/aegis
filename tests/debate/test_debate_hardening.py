from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from aegis.modules.debate import (
    CandidatePosition,
    DebateInputPackage,
    DebateRuntimeConfig,
    HardConstraint,
    KnowledgeContextRef,
    DebateContextBundle,
    admit_stances,
    bind_project_stores,
    run_deterministic_debate,
    validate_hard_constraints,
    write_causal_store_candidate,
    build_update_candidate,
    CausalCandidateNode,
    CausalCandidateDependencyGroup,
)
from aegis.modules.debate.candidate_writer import CausalCandidateWriteError
from aegis.modules.debate.context import build_context_bundle
from aegis.modules.debate.errors import DebateRuntimeError
from aegis.stores.knowledge.models import (
    AdmissionRequest,
    ApplicabilityProfile,
    EvidencePointer,
    EvidenceRef,
    KnowledgeFactDraft,
)
from aegis.stores.knowledge.store import KnowledgeStore


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    for name in ("code", "artifacts", "knowledge", "causal"):
        (root / name).mkdir(parents=True)
    return root


def _package(root: Path) -> DebateInputPackage:
    adapter_ref = root / "artifacts" / "adapter-weak.md"
    simple_ref = root / "artifacts" / "simple-strong.md"
    simple_review_ref = root / "artifacts" / "simple-review.md"
    adapter_ref.write_text("adapter route extension overhead evidence", encoding="utf-8")
    simple_ref.write_text("simple direct implementation evidence", encoding="utf-8")
    simple_review_ref.write_text("simple direct review evidence", encoding="utf-8")
    return DebateInputPackage(
        request_id="req-hardening",
        source_module="execution",
        project_root=root,
        decision_problem="Choose implementation route",
        decision_scope="local project",
        required_outcome="choose_one",
        candidate_positions=[
            CandidatePosition(
                stance_id="adapter",
                statement="Use adapter implementation",
                summary="adapter route has extension overhead",
                source_artifact_refs=[str(adapter_ref)],
            ),
            CandidatePosition(
                stance_id="simple",
                statement="Use simple direct implementation",
                summary="simple route has lower complexity",
                source_artifact_refs=[str(simple_ref), str(simple_review_ref)],
            ),
        ],
    )


def _admit_knowledge_fact(root: Path, evidence_id: str = "platform/real") -> int:
    store = KnowledgeStore(root / "knowledge" / "knowledge.sqlite3")
    fact_id = store.put_candidate(
        KnowledgeFactDraft(
            fact_kind="platform",
            subject_kind="project",
            subject_id=root.name,
            predicate="supports",
            object_kind="scalar",
            object="simple direct implementation",
            fact_validity_scope={"project": root.name},
            semantic_summary="Simple direct implementation is supported by platform evidence.",
            semantic_keys=["simple", "direct", "implementation", "platform"],
            source_module="knowledge_review",
            source_artifact_ref=evidence_id,
            evidence_refs=[
                EvidenceRef(
                    ref_type="platform_doc",
                    ref_id=evidence_id,
                    verifier="knowledge_review",
                    verification_method="repository_inspected",
                )
            ],
            applicability_profile=ApplicabilityProfile(
                applicability_scope={"project": root.name},
                affected_entities=["implementation route"],
                affected_operations=["choose implementation route"],
                task_intents=["implementation"],
                lifecycle_phases=["debate"],
                must_consider_when=["implementation route"],
                priority="high",
            ),
            no_known_invalidation=True,
        )
    )
    store.admit_fact(
        AdmissionRequest(
            knowledge_id=fact_id,
            admitted_by_module="knowledge_review",
            admission_method="knowledge_review",
            rationale="Verified platform evidence.",
            evidence_refs=[EvidencePointer(ref_type="platform_doc", ref_id=evidence_id)],
        )
    )
    return fact_id


def test_fake_evidence_ref_does_not_verify_hard_constraint(tmp_path: Path) -> None:
    root = _project(tmp_path)
    package = DebateInputPackage(
        request_id="req-fake-ref",
        source_module="master",
        project_root=root,
        decision_problem="Choose route",
        candidate_positions=[
            CandidatePosition(stance_id="a", statement="A", summary="A"),
            CandidatePosition(stance_id="b", statement="B", summary="B"),
        ],
        hard_constraints=[
            HardConstraint(
                constraint_id="hc-platform",
                statement="Must use A",
                source="platform",
                evidence_ref="platform/fake",
            )
        ],
    )

    validations = validate_hard_constraints(package, DebateContextBundle())

    assert validations[0].validation_status == "unsupported"


def test_matched_knowledge_evidence_ref_verifies_hard_constraint(tmp_path: Path) -> None:
    root = _project(tmp_path)
    context = DebateContextBundle(
        knowledge_refs=[
            KnowledgeContextRef(
                knowledge_id="k1",
                statement="Platform rule requires adapter architecture.",
                scope="local project",
                evidence_ref="platform/real",
            )
        ]
    )
    package = DebateInputPackage(
        request_id="req-real-ref",
        source_module="master",
        project_root=root,
        decision_problem="Choose route",
        candidate_positions=[
            CandidatePosition(stance_id="a", statement="A", summary="A"),
            CandidatePosition(stance_id="b", statement="B", summary="B"),
        ],
        hard_constraints=[
            HardConstraint(
                constraint_id="hc-platform",
                statement="Adapter architecture is mandatory.",
                source="platform",
                evidence_ref="platform/real",
            )
        ],
    )

    validations = validate_hard_constraints(package, context)

    assert validations[0].validation_status == "verified"


def test_opposing_evidence_does_not_verify_hard_constraint(tmp_path: Path) -> None:
    root = _project(tmp_path)
    context = DebateContextBundle(
        knowledge_refs=[
            KnowledgeContextRef(
                knowledge_id="k1",
                statement=(
                    "Platform review forbids adapter architecture because the "
                    "current extension boundary must stay direct."
                ),
                scope="local project",
                evidence_ref="platform/adapter-forbidden",
            )
        ]
    )
    package = DebateInputPackage(
        request_id="req-opposing-ref",
        source_module="master",
        project_root=root,
        decision_problem="Choose route",
        candidate_positions=[
            CandidatePosition(stance_id="simple", statement="Simple", summary="Simple"),
            CandidatePosition(stance_id="adapter", statement="Adapter", summary="Adapter"),
        ],
        hard_constraints=[
            HardConstraint(
                constraint_id="hc-adapter",
                statement="Adapter architecture is mandatory.",
                source="platform",
                evidence_ref="platform/adapter-forbidden",
            )
        ],
    )

    validations = validate_hard_constraints(package, context)

    assert validations[0].validation_status == "unsupported"


def test_unrelated_project_artifact_does_not_admit_stance(tmp_path: Path) -> None:
    root = _project(tmp_path)
    unrelated_ref = root / "artifacts" / "unrelated.md"
    unrelated_ref.write_text(
        "Meeting note about release timing and owner availability.",
        encoding="utf-8",
    )
    package = DebateInputPackage(
        request_id="req-unrelated-artifact",
        source_module="master",
        project_root=root,
        decision_problem="Choose route",
        candidate_positions=[
            CandidatePosition(
                stance_id="adapter",
                statement="Use adapter architecture",
                summary="Adapter boundary",
                source_artifact_refs=[str(unrelated_ref)],
            )
        ],
    )
    context = build_context_bundle(
        package,
        bind_project_stores(root, debate_id="debate-unrelated-artifact"),
        DebateRuntimeConfig(),
    )

    records = admit_stances(package, context, [])

    assert records[0].status == "rejected"
    assert records[0].supporting_refs == []


def test_context_builder_reads_project_knowledge_store(tmp_path: Path) -> None:
    root = _project(tmp_path)
    fact_id = _admit_knowledge_fact(root)
    package = _package(root)
    binding = bind_project_stores(root, debate_id="debate-context")

    context = build_context_bundle(package, binding, DebateRuntimeConfig())

    assert any(ref.knowledge_id == fact_id for ref in context.knowledge_refs)
    assert context.retrieval_audit.admitted_knowledge_count >= 1


def test_custom_store_root_outside_project_is_rejected(tmp_path: Path) -> None:
    root = _project(tmp_path)
    outside = tmp_path / "outside-causal"
    outside.mkdir()

    with pytest.raises(DebateRuntimeError):
        bind_project_stores(root, debate_id="debate-outside", causal_store_root=outside)


def test_leader_selection_not_based_on_adapter_keyword(tmp_path: Path) -> None:
    root = _project(tmp_path)
    output = run_deterministic_debate(_package(root), DebateRuntimeConfig(max_rounds=3))

    assert output.status == "completed"
    assert output.selected_stance_id == "simple"


def test_leader_selection_is_not_input_order_when_later_stance_has_stronger_evidence(tmp_path: Path) -> None:
    root = _project(tmp_path)
    weak_ref = root / "artifacts" / "weak.md"
    strong_ref_1 = root / "artifacts" / "strong-1.md"
    strong_ref_2 = root / "artifacts" / "strong-2.md"
    weak_ref.write_text("simple direct implementation evidence", encoding="utf-8")
    strong_ref_1.write_text("adapter architecture platform evidence", encoding="utf-8")
    strong_ref_2.write_text("adapter architecture review evidence", encoding="utf-8")
    package = DebateInputPackage(
        request_id="req-order-independent",
        source_module="execution",
        project_root=root,
        decision_problem="Choose implementation route",
        required_outcome="choose_one",
        candidate_positions=[
            CandidatePosition(
                stance_id="simple",
                statement="Use simple direct implementation",
                summary="simple direct implementation",
                source_artifact_refs=[str(weak_ref)],
            ),
            CandidatePosition(
                stance_id="adapter",
                statement="Use adapter architecture",
                summary="adapter architecture",
                source_artifact_refs=[str(strong_ref_1), str(strong_ref_2)],
            ),
        ],
    )

    output = run_deterministic_debate(package, DebateRuntimeConfig(max_rounds=3))

    assert output.status == "completed"
    assert output.selected_stance_id == "adapter"


def test_second_worker_round_contains_response_concession_instead_of_repeating_first_round(tmp_path: Path) -> None:
    root = _project(tmp_path)
    output = run_deterministic_debate(
        _package(root),
        DebateRuntimeConfig(
            max_rounds=3,
            stable_selected_stance_round_threshold=2,
        ),
    )

    assert output.status == "completed"
    manifest = json.loads(Path(output.manifest_ref).read_text(encoding="utf-8"))
    worker_turns = json.loads(Path(manifest["worker_turns_ref"]).read_text(encoding="utf-8"))
    round_two_turns = [turn for turn in worker_turns if turn["round_index"] == 2]

    assert round_two_turns
    assert any(turn["concessions"] for turn in round_two_turns)
    assert any("responds to round 1" in str(turn["defense"]) for turn in round_two_turns)


def test_candidate_writer_all_failures_are_not_silent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _project(tmp_path)
    binding = bind_project_stores(root, debate_id="debate-write-fail")
    package = _package(root)
    candidate = build_update_candidate(
        package=package,
        debate_id="debate-write-fail",
        selected_stance_id="simple",
        rejected_stance_ids=["adapter"],
        nodes=[
            CausalCandidateNode(
                local_node_ref="n1",
                statement="Simple route selected.",
                semantic_summary="Simple selection",
                source_worker_id="worker-simple",
                source_stance_id="simple",
                dependency_groups=[
                    CausalCandidateDependencyGroup(
                        group_id="g1",
                        evidence_refs=["artifact/simple"],
                        scope="local project",
                    )
                ],
            )
        ],
    )

    def fail_put_candidates(self, drafts):  # noqa: ANN001
        raise RuntimeError("store unavailable")

    monkeypatch.setattr("aegis.modules.debate.candidate_writer.CausalStore.put_candidates", fail_put_candidates)

    with pytest.raises(CausalCandidateWriteError):
        write_causal_store_candidate(
            binding=binding,
            artifact_ref=str(binding.debate_candidate_root / "candidate.json"),
            candidate=candidate,
        )


def test_candidate_writer_partial_failure_rolls_back_candidates(tmp_path: Path) -> None:
    root = _project(tmp_path)
    binding = bind_project_stores(root, debate_id="debate-partial-rollback")
    package = _package(root)
    candidate = build_update_candidate(
        package=package,
        debate_id="debate-partial-rollback",
        selected_stance_id="simple",
        rejected_stance_ids=["adapter"],
        nodes=[
            CausalCandidateNode(
                local_node_ref="n1",
                statement="Simple route selected.",
                semantic_summary="Simple selection",
                source_worker_id="worker-simple",
                source_stance_id="simple",
                dependency_groups=[
                    CausalCandidateDependencyGroup(
                        group_id="duplicate-group",
                        evidence_refs=["artifact/simple"],
                        scope="local project",
                    )
                ],
            ),
            CausalCandidateNode(
                local_node_ref="n2",
                statement="Adapter route rejected.",
                semantic_summary="Adapter rejection",
                source_worker_id="worker-adapter",
                source_stance_id="adapter",
                dependency_groups=[
                    CausalCandidateDependencyGroup(
                        group_id="duplicate-group",
                        evidence_refs=["artifact/adapter"],
                        scope="local project",
                    )
                ],
            ),
        ],
    )

    with pytest.raises(CausalCandidateWriteError) as raised:
        write_causal_store_candidate(
            binding=binding,
            artifact_ref=str(binding.debate_candidate_root / "candidate.json"),
            candidate=candidate,
        )

    assert raised.value.result.write_status == "failed"
    assert raised.value.result.inserted_node_ids == []
    with sqlite3.connect(root / "causal" / "causal.sqlite3") as conn:
        count = conn.execute("SELECT COUNT(*) FROM causal_nodes").fetchone()[0]
    assert count == 0


def test_manifest_written_and_same_request_different_input_does_not_overwrite(tmp_path: Path) -> None:
    root = _project(tmp_path)
    first = _package(root)
    second = first.model_copy(
        update={
            "candidate_positions": [
                CandidatePosition(
                    stance_id="route-x",
                    statement="Use route X",
                    summary="route X",
                    source_artifact_refs=["artifact/x"],
                ),
                CandidatePosition(
                    stance_id="route-y",
                    statement="Use route Y",
                    summary="route Y",
                    source_artifact_refs=["artifact/y", "artifact/y-review"],
                ),
            ]
        }
    )

    first_output = run_deterministic_debate(first, DebateRuntimeConfig())
    second_output = run_deterministic_debate(second, DebateRuntimeConfig())

    assert first_output.manifest_ref is not None
    assert second_output.manifest_ref is not None
    assert first_output.artifact_root != second_output.artifact_root
    first_manifest = json.loads(Path(first_output.manifest_ref).read_text(encoding="utf-8"))
    second_manifest = json.loads(Path(second_output.manifest_ref).read_text(encoding="utf-8"))
    assert first_manifest["input_hash"] != second_manifest["input_hash"]
