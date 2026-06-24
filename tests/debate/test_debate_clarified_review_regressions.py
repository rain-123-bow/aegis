from __future__ import annotations

import json
from pathlib import Path

from aegis.modules.debate import (
    CandidatePosition,
    DebateContextBundle,
    DebateInputPackage,
    DebateRuntimeConfig,
    HardConstraint,
    KnowledgeContextRef,
    bind_project_stores,
    build_context_bundle,
    run_deterministic_debate,
    validate_hard_constraints,
)
from aegis.modules.debate.admission import admit_stances
from aegis.stores.causal.models import (
    AdmissionTransaction,
    CausalNodeDraft,
)
from aegis.stores.causal.store import CausalStore
from aegis.stores.knowledge.models import NeedRule
from aegis.stores.knowledge.store import KnowledgeStore


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    for name in ("code", "archive", "knowledge", "causal"):
        (root / name).mkdir(parents=True)
    return root


def _evidence_file(root: Path, name: str, text: str = "verified evidence") -> Path:
    path = root / "archive" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _package(root: Path, *, source_refs: bool = True) -> DebateInputPackage:
    simple_ref = _evidence_file(root, "simple-route.md", "simple direct route evidence")
    adapter_ref = _evidence_file(root, "adapter-route.md", "adapter route evidence")
    return DebateInputPackage(
        request_id="req-clarified",
        source_module="execution",
        project_root=root,
        decision_problem="Choose implementation route",
        required_outcome="choose_one",
        candidate_positions=[
            CandidatePosition(
                stance_id="simple",
                statement="Use simple direct implementation",
                summary="Simple direct implementation has lower complexity.",
                source_artifact_refs=[str(simple_ref)] if source_refs else [],
            ),
            CandidatePosition(
                stance_id="adapter",
                statement="Use adapter implementation",
                summary="Adapter implementation improves extension boundary.",
                source_artifact_refs=[str(adapter_ref)] if source_refs else [],
            ),
        ],
    )


def test_unverified_source_artifact_ref_cannot_admit_stance(tmp_path: Path) -> None:
    root = _project(tmp_path)
    package = DebateInputPackage(
        request_id="req-unverified-artifact",
        source_module="master",
        project_root=root,
        decision_problem="Choose route",
        candidate_positions=[
            CandidatePosition(
                stance_id="fake",
                statement="Use fake route",
                summary="fake route",
                source_artifact_refs=["fake/path/or/unverified-ref"],
            )
        ],
    )

    records = admit_stances(package, DebateContextBundle(), [])

    assert records[0].status == "rejected"
    assert records[0].supporting_refs == []


def test_verified_project_artifact_ref_can_admit_stance(tmp_path: Path) -> None:
    root = _project(tmp_path)
    evidence_ref = _evidence_file(root, "verified-route.md")
    package = DebateInputPackage(
        request_id="req-verified-artifact",
        source_module="master",
        project_root=root,
        decision_problem="Choose route",
        candidate_positions=[
            CandidatePosition(
                stance_id="verified",
                statement="Use verified route",
                summary="verified route",
                source_artifact_refs=[str(evidence_ref)],
            )
        ],
    )
    context = build_context_bundle(
        package,
        bind_project_stores(root, debate_id="debate-artifact-validation"),
        DebateRuntimeConfig(),
    )

    records = admit_stances(package, context, [])

    assert records[0].status == "admitted"
    assert str(evidence_ref.resolve()) in records[0].supporting_refs


def test_code_root_artifact_ref_cannot_support_stance(tmp_path: Path) -> None:
    root = _project(tmp_path)
    code_ref = root / "code" / "implementation.py"
    code_ref.write_text("print('not governance evidence')\n", encoding="utf-8")
    package = DebateInputPackage(
        request_id="req-code-ref",
        source_module="master",
        project_root=root,
        decision_problem="Choose route",
        candidate_positions=[
            CandidatePosition(
                stance_id="code",
                statement="Use code route",
                summary="code route",
                source_artifact_refs=[str(code_ref)],
            )
        ],
    )
    context = build_context_bundle(
        package,
        bind_project_stores(root, debate_id="debate-code-ref"),
        DebateRuntimeConfig(),
    )

    records = admit_stances(package, context, [])

    assert records[0].status == "rejected"


def test_hard_constraint_requires_statement_evidence_correspondence(tmp_path: Path) -> None:
    root = _project(tmp_path)
    context = DebateContextBundle(
        knowledge_refs=[
            KnowledgeContextRef(
                knowledge_id="k1",
                statement="Latency benchmark supports the simple direct route.",
                scope="local project",
                evidence_ref="test/latency",
            )
        ]
    )
    package = DebateInputPackage(
        request_id="req-unrelated-evidence",
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
                evidence_ref="test/latency",
            )
        ],
    )

    validations = validate_hard_constraints(package, context)

    assert validations[0].validation_status == "unsupported"


def test_matching_hard_constraint_evidence_is_verified(tmp_path: Path) -> None:
    root = _project(tmp_path)
    context = DebateContextBundle(
        knowledge_refs=[
            KnowledgeContextRef(
                knowledge_id="k1",
                statement="Platform rule requires adapter architecture.",
                scope="local project",
                evidence_ref="platform/adapter-rule",
            )
        ]
    )
    package = DebateInputPackage(
        request_id="req-related-evidence",
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
                evidence_ref="platform/adapter-rule",
            )
        ],
    )

    validations = validate_hard_constraints(package, context)

    assert validations[0].validation_status == "verified"


def test_hard_block_missing_knowledge_stops_debate(tmp_path: Path) -> None:
    root = _project(tmp_path)
    store = KnowledgeStore(root / "knowledge" / "knowledge.sqlite3")
    store.register_need_rule(
        NeedRule(
            rule_id="need-platform-rule",
            required_dimension="platform_rule",
            trigger_operations=["choose implementation route"],
            required_subject_kinds=["project"],
            acceptable_sources=["platform_doc"],
            default_blocking_level="hard_block",
            rationale="A platform rule is required before this route can be debated.",
        )
    )

    output = run_deterministic_debate(_package(root), DebateRuntimeConfig())

    assert output.status == "need_more_context"
    assert output.errors[0].code == "MISSING_REQUIRED_CONTEXT"


def test_request_test_measurement_missing_need_routes_to_measurement(tmp_path: Path) -> None:
    root = _project(tmp_path)
    store = KnowledgeStore(root / "knowledge" / "knowledge.sqlite3")
    store.register_need_rule(
        NeedRule(
            rule_id="need-benchmark",
            required_dimension="benchmark_result",
            trigger_operations=["choose implementation route"],
            required_subject_kinds=["project"],
            acceptable_sources=["test"],
            default_blocking_level="request_test_measurement",
            rationale="Benchmark evidence is required before route adjudication.",
        )
    )

    output = run_deterministic_debate(_package(root), DebateRuntimeConfig())

    assert output.status == "need_measurement"
    assert output.errors[0].code == "MISSING_TEST_MEASUREMENT"


def test_explicit_causal_node_expansion_enters_context_refs(tmp_path: Path) -> None:
    root = _project(tmp_path)
    store = CausalStore(root / "causal" / "causal.sqlite3")
    node_id = store.put_candidate(
        CausalNodeDraft(
            content="Adapter route improves extension boundary.",
            semantic_summary="Adapter extension boundary",
            semantic_keys=["adapter", "extension"],
            source_module="causal_review",
            source_artifact_ref="artifact/causal-review",
            root_kind="design_decision",
            node_refs=[("artifact", "artifact/causal-review")],
        )
    )
    store.admit_nodes(
        AdmissionTransaction(
            node_ids=[node_id],
            admitted_by_module="causal_review",
            rationale="Accepted causal review node.",
            evidence_ref="artifact/causal-review",
        )
    )
    package = _package(root).model_copy(update={"causal_query_refs": [str(node_id)]})

    context = build_context_bundle(
        package,
        bind_project_stores(root, debate_id="debate-causal-expand"),
        DebateRuntimeConfig(),
    )

    assert any(ref.node_id == node_id for ref in context.causal_refs)


def test_max_rounds_without_stable_convergence_returns_non_convergent(tmp_path: Path) -> None:
    root = _project(tmp_path)
    output = run_deterministic_debate(
        _package(root),
        DebateRuntimeConfig(
            max_rounds=1,
            stable_selected_stance_round_threshold=3,
        ),
    )

    assert output.status == "non_convergent"
    assert output.selected_stance_id is None


def test_manifest_records_terminal_status_and_hashes(tmp_path: Path) -> None:
    root = _project(tmp_path)
    output = run_deterministic_debate(_package(root), DebateRuntimeConfig(max_rounds=2))

    manifest = json.loads(Path(output.manifest_ref).read_text(encoding="utf-8"))

    assert manifest["run_status"] == "completed"
    assert manifest["updated_at_utc"]
    assert manifest["context_bundle_hash"]
    assert manifest["causal_candidate_hash"]
