from __future__ import annotations

import json
from pathlib import Path

from aegis.modules.debate import (
    CandidatePosition,
    DebateInputPackage,
    DebateRuntime,
    DebateRuntimeConfig,
    run_deterministic_debate,
)


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "code").mkdir(parents=True)
    (root / "artifacts").mkdir()
    (root / "knowledge").mkdir()
    (root / "causal").mkdir()
    return root


def test_deterministic_debate_writes_candidate_package_without_polluting_code(tmp_path: Path) -> None:
    root = _project(tmp_path)
    simple_ref = root / "artifacts" / "simple.md"
    adapter_ref = root / "artifacts" / "adapter.md"
    simple_ref.write_text("simple direct implementation evidence", encoding="utf-8")
    adapter_ref.write_text("structured adapter implementation evidence", encoding="utf-8")
    package = DebateInputPackage(
        request_id="req-1",
        source_module="execution",
        project_root=str(root),
        decision_problem="Choose implementation route",
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

    output = run_deterministic_debate(package, DebateRuntimeConfig(max_rounds=2))

    assert output.status == "completed"
    assert output.decision_type == "choose_one"
    assert output.causal_candidate_ref is not None
    assert output.boundary.modified_code is False
    assert not list((root / "code").glob("**/*"))

    candidate = json.loads(Path(output.causal_candidate_ref).read_text(encoding="utf-8"))
    assert candidate["source_module"] == "debate"
    assert candidate["proposed_nodes"]


def test_deterministic_debate_is_idempotent_for_same_input(tmp_path: Path) -> None:
    root = _project(tmp_path)
    simple_ref = root / "artifacts" / "simple.md"
    adapter_ref = root / "artifacts" / "adapter.md"
    simple_ref.write_text("simple direct implementation evidence", encoding="utf-8")
    adapter_ref.write_text("structured adapter implementation evidence", encoding="utf-8")
    package = DebateInputPackage(
        request_id="req-idempotent",
        source_module="execution",
        project_root=str(root),
        decision_problem="Choose implementation route",
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

    first = run_deterministic_debate(package, DebateRuntimeConfig(max_rounds=2))
    first_write = json.loads(
        (Path(first.artifact_root) / "causal_write_result.json").read_text(
            encoding="utf-8"
        )
    )
    second = run_deterministic_debate(package, DebateRuntimeConfig(max_rounds=2))
    second_write = json.loads(
        (Path(second.artifact_root) / "causal_write_result.json").read_text(
            encoding="utf-8"
        )
    )

    assert first.status == "completed"
    assert second.status == "completed"
    assert first.debate_id == second.debate_id
    assert first.causal_store_candidate_id == second.causal_store_candidate_id
    assert first_write["write_status"] == "written"
    assert second_write["write_status"] == "already_exists"
    assert second_write["existing_node_ids"] == first_write["inserted_node_ids"]


def test_debate_runtime_checkpoints_and_resumes_completed_output(tmp_path: Path) -> None:
    root = _project(tmp_path)
    simple_ref = root / "artifacts" / "simple.md"
    adapter_ref = root / "artifacts" / "adapter.md"
    simple_ref.write_text("simple direct implementation evidence", encoding="utf-8")
    adapter_ref.write_text("structured adapter implementation evidence", encoding="utf-8")
    package = DebateInputPackage(
        request_id="req-checkpoint",
        source_module="execution",
        project_root=str(root),
        decision_problem="Choose implementation route",
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

    with DebateRuntime(root) as runtime:
        first = runtime.run(
            package,
            DebateRuntimeConfig(max_rounds=2),
            thread_id="debate-checkpoint",
        )
        snapshot = runtime.inspect("debate-checkpoint")
        resumed = runtime.resume("debate-checkpoint")

    assert (root / ".aegis" / "runtime" / "debate_checkpoints.sqlite3").exists()
    assert snapshot["thread_id"] == "debate-checkpoint"
    assert snapshot["values"]["output_package"]["status"] == "completed"
    assert first["result"].status == "completed"
    assert resumed["result"].status == "completed"
    assert resumed["result"].debate_id == first["result"].debate_id


def test_deterministic_debate_returns_not_required_for_duplicate_stances(tmp_path: Path) -> None:
    root = _project(tmp_path)
    package = DebateInputPackage(
        request_id="req-duplicate",
        source_module="master",
        project_root=str(root),
        decision_problem="Choose route",
        decision_scope="local project",
        required_outcome="choose_one",
        candidate_positions=[
            CandidatePosition(stance_id="a", statement="Use route A", summary="same"),
            CandidatePosition(stance_id="b", statement="Use route A", summary="same"),
        ],
    )

    output = run_deterministic_debate(package, DebateRuntimeConfig(max_rounds=1))

    assert output.status == "debate_not_required"
    assert output.errors[0].code == "INSUFFICIENT_CONTESTED_STANCES"
