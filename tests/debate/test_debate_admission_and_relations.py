from __future__ import annotations

from pathlib import Path

from aegis.modules.debate import (
    ArtifactContextRef,
    CandidatePosition,
    DebateContextBundle,
    DebateInputPackage,
    HardConstraint,
    KnowledgeContextRef,
    validate_hard_constraints,
    admit_stances,
    analyze_stance_relations,
)


def _input(tmp_path: Path, positions: list[CandidatePosition]) -> DebateInputPackage:
    return DebateInputPackage(
        request_id="req-1",
        source_module="master",
        project_root=str(tmp_path),
        decision_problem="Choose route",
        decision_scope="local project",
        required_outcome="choose_one",
        candidate_positions=positions,
        hard_constraints=[
            HardConstraint(
                constraint_id="hc-user-pref",
                statement="User prefers route A",
                source="user",
            )
        ],
    )


def test_unsupported_hard_constraint_is_not_effective(tmp_path: Path) -> None:
    package = _input(
        tmp_path,
        [
            CandidatePosition(stance_id="a", statement="Route A", summary="A"),
            CandidatePosition(stance_id="b", statement="Route B", summary="B"),
        ],
    )

    validations = validate_hard_constraints(package, DebateContextBundle(debate_id="debate-1"))

    assert validations[0].validation_status == "unsupported"
    assert validations[0].rejection_reason


def test_stance_admission_requires_defensible_basis(tmp_path: Path) -> None:
    package = _input(
        tmp_path,
        [
            CandidatePosition(stance_id="supported", statement="Use indexed lookup", summary="indexed lookup"),
            CandidatePosition(stance_id="unsupported", statement="Use magic", summary="magic"),
        ],
    )
    context = DebateContextBundle(
        debate_id="debate-1",
        knowledge_refs=[
            KnowledgeContextRef(
                knowledge_id="k-index",
                subject="lookup",
                predicate="supports",
                object="indexed lookup",
                scope="local project",
                evidence_refs=["test/index"],
                applicability_reason="route support",
            )
        ],
    )

    records = admit_stances(package, context, [])

    by_id = {record.stance_id: record for record in records}
    assert by_id["supported"].status == "admitted"
    assert by_id["unsupported"].status == "rejected"


def test_duplicate_or_compatible_relations_prevent_contested_debate(tmp_path: Path) -> None:
    a_ref = tmp_path / "a.md"
    b_ref = tmp_path / "b.md"
    a_ref.write_text("route A evidence", encoding="utf-8")
    b_ref.write_text("route A evidence", encoding="utf-8")
    package = _input(
        tmp_path,
        [
            CandidatePosition(
                stance_id="a",
                statement="Use route A",
                summary="same route",
                source_artifact_refs=[str(a_ref)],
            ),
            CandidatePosition(
                stance_id="b",
                statement="Use route A",
                summary="same route",
                source_artifact_refs=[str(b_ref)],
            ),
        ],
    )
    context = DebateContextBundle(
        debate_id="debate-1",
        artifact_refs=[
            ArtifactContextRef(
                input_ref=str(a_ref),
                resolved_ref=str(a_ref.resolve()),
                scope="project_artifact",
                content_preview="route A evidence",
            ),
            ArtifactContextRef(
                input_ref=str(b_ref),
                resolved_ref=str(b_ref.resolve()),
                scope="project_artifact",
                content_preview="route A evidence",
            ),
        ],
    )
    records = admit_stances(package, context, [])
    relations = analyze_stance_relations(package, records, context)

    assert relations[0].relation == "duplicate"


def test_mutually_exclusive_supported_stances_are_contested(tmp_path: Path) -> None:
    simple_ref = tmp_path / "simple.md"
    adapter_ref = tmp_path / "adapter.md"
    simple_ref.write_text("direct implementation evidence", encoding="utf-8")
    adapter_ref.write_text("adapter implementation evidence", encoding="utf-8")
    package = _input(
        tmp_path,
        [
            CandidatePosition(
                stance_id="simple",
                statement="Use direct implementation",
                summary="lower complexity",
                source_artifact_refs=[str(simple_ref)],
            ),
            CandidatePosition(
                stance_id="adapter",
                statement="Use adapter implementation",
                summary="better extension boundary",
                source_artifact_refs=[str(adapter_ref)],
            ),
        ],
    )
    context = DebateContextBundle(
        debate_id="debate-1",
        artifact_refs=[
            ArtifactContextRef(
                input_ref=str(simple_ref),
                resolved_ref=str(simple_ref.resolve()),
                scope="project_artifact",
                content_preview="direct implementation evidence",
            ),
            ArtifactContextRef(
                input_ref=str(adapter_ref),
                resolved_ref=str(adapter_ref.resolve()),
                scope="project_artifact",
                content_preview="adapter implementation evidence",
            ),
        ],
    )
    records = admit_stances(package, context, [])
    relations = analyze_stance_relations(package, records, context)

    assert records[0].status == "admitted"
    assert records[1].status == "admitted"
    assert relations[0].relation == "mutually_exclusive"
