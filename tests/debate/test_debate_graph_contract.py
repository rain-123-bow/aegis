from __future__ import annotations

from pathlib import Path

from aegis.modules.debate import CandidatePosition, DebateInputPackage, build_debate_subgraph


def test_langgraph_builder_returns_output_package(tmp_path: Path) -> None:
    root = tmp_path / "project"
    (root / "code").mkdir(parents=True)
    (root / "artifacts").mkdir()
    (root / "knowledge").mkdir()
    (root / "causal").mkdir()
    simple_ref = root / "artifacts" / "simple.md"
    adapter_ref = root / "artifacts" / "adapter.md"
    simple_ref.write_text("simple direct implementation evidence", encoding="utf-8")
    adapter_ref.write_text("structured adapter implementation evidence", encoding="utf-8")
    graph = build_debate_subgraph()
    package = DebateInputPackage(
        request_id="req-graph",
        source_module="master",
        project_root=str(root),
        decision_problem="Choose route",
        decision_scope="local project",
        required_outcome="choose_one",
        candidate_positions=[
            CandidatePosition(
                stance_id="simple",
                statement="Use simple direct implementation",
                summary="lower complexity",
                source_artifact_refs=[str(simple_ref)],
            ),
            CandidatePosition(
                stance_id="adapter",
                statement="Use structured adapter implementation",
                summary="better extension boundary",
                source_artifact_refs=[str(adapter_ref)],
            ),
        ],
    )

    result = graph.invoke({"input_package": package.model_dump(mode="json")})

    assert result["output_package"]["status"] == "completed"
    assert result["output_package"]["boundary"]["wrote_causal_truth"] is False


def test_langgraph_builder_exposes_debate_workflow_stages() -> None:
    graph = build_debate_subgraph().get_graph()

    assert {
        "initialize_run",
        "build_context",
        "admit_stances",
        "run_worker_rounds",
        "write_candidate",
    }.issubset(graph.nodes.keys())
