from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from aegis.top_level.graph import AegisTopLevelRuntime
from aegis.top_level.manifest import write_package_manifest
from aegis.top_level.models import (
    ModuleRouteDecision,
    RouteStatus,
    TopLevelHandoffEnvelope,
    TopLevelTerminalStatus,
)
from aegis.top_level.registry import ModuleRegistry, ResidentModule
from aegis.top_level.routing import RouteValidationError, default_route_schema_registry
from aegis.top_level.runtime_lock import RuntimeLockError, RuntimeProjectLock, canonical_project_root


class ScriptedResidentModule:
    def __init__(
        self,
        module_type: str,
        responses: list[tuple[str, str, str]],
        *,
        fail_on_call: bool = False,
    ) -> None:
        self.module_type = module_type
        self.module_instance_id = f"{module_type}:default"
        self.resident_agents = (
            ["debate_leader"]
            if module_type == "debate"
            else [f"{module_type}_agent"]
        )
        self.responses = responses
        self.fail_on_call = fail_on_call
        self.calls: list[dict[str, Any]] = []

    def handle(self, state: dict[str, Any]) -> ModuleRouteDecision:
        if self.fail_on_call:
            raise RuntimeError(f"{self.module_type} failed")
        if not self.responses:
            raise RuntimeError(f"{self.module_type} has no scripted response")
        target, handoff_kind, status = self.responses.pop(0)
        self.calls.append(
            {
                "run_id": state["run_id"],
                "active_handoff": state.get("active_handoff_ref"),
            }
        )
        if status == "runtime_terminal":
            return ModuleRouteDecision(
                source_module=self.module_type,
                route_status=RouteStatus.RUNTIME_TERMINAL,
                next_route=target,
                handoff_kind=handoff_kind,
            )
        envelope = make_handoff(
            Path(state["project_root"]),
            run_id=state["run_id"],
            source=self.module_type,
            target=target,
            handoff_kind=handoff_kind,
        )
        return ModuleRouteDecision(
            source_module=self.module_type,
            route_status=RouteStatus.READY,
            next_route=target,
            handoff_kind=handoff_kind,
            output_handoff=envelope,
        )


def make_registry(**modules: ResidentModule) -> ModuleRegistry:
    return ModuleRegistry.from_modules(list(modules.values()))


def make_handoff(
    project_root: Path,
    *,
    run_id: str,
    source: str,
    target: str,
    handoff_kind: str,
    body: str = "handoff body\n",
) -> TopLevelHandoffEnvelope:
    package_root = (
        project_root
        / ".aegis"
        / "artifacts"
        / source
        / run_id
        / f"{source}_to_{target}_{handoff_kind}_{uuid4().hex[:8]}"
    )
    package_root.mkdir(parents=True)
    readme = package_root / "README.md"
    readme.write_text(body, encoding="utf-8", newline="\n")
    payload = package_root / "payload.json"
    payload.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "source": source,
                "target": target,
                "handoff_kind": handoff_kind,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    manifest_path, manifest_sha = write_package_manifest(
        package_root=package_root,
        run_id=run_id,
        producer_module=source,
        producer_module_instance_id=f"{source}:default",
    )
    return TopLevelHandoffEnvelope(
        run_id=run_id,
        source_module=source,
        target_module=target,
        source_module_instance_id=f"{source}:default",
        target_module_instance_id=f"{target}:default" if target != "closeout" else "master:default",
        handoff_kind=handoff_kind,
        package_path=str(readme),
        package_manifest_path=str(manifest_path),
        package_sha256=manifest_sha,
        declared_next_route=target,
    )


def test_project_runtime_lock_rejects_second_runtime_for_same_canonical_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    first = RuntimeProjectLock(project)
    first.acquire()
    try:
        with pytest.raises(RuntimeLockError, match="already locked"):
            RuntimeProjectLock(project / ".").acquire()
    finally:
        first.release()


def test_canonical_project_root_normalizes_equivalent_paths(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    assert canonical_project_root(project) == canonical_project_root(project / ".")


def test_handoff_manifest_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    envelope = make_handoff(
        project,
        run_id="run-hash",
        source="execution",
        target="test",
        handoff_kind="execution_to_test",
    )
    payload = json.loads(envelope.model_dump_json())
    payload["package_sha256"] = "0" * 64

    with pytest.raises(RouteValidationError, match="package_sha256"):
        default_route_schema_registry().validate_envelope(
            TopLevelHandoffEnvelope.model_validate(payload),
            project_root=project,
        )


def test_route_schema_registry_distinguishes_debate_return_targets(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    registry = default_route_schema_registry()

    requirement = make_handoff(
        project,
        run_id="run-req",
        source="debate",
        target="master",
        handoff_kind="debate_requirement_to_master",
    )
    registry.validate_envelope(requirement, project_root=project)

    wrong = make_handoff(
        project,
        run_id="run-wrong",
        source="debate",
        target="execution",
        handoff_kind="debate_requirement_to_master",
    )
    with pytest.raises(RouteValidationError, match="handoff_kind"):
        registry.validate_envelope(wrong, project_root=project)


def test_module_registry_requires_exactly_one_core_module_and_no_debate_workers() -> None:
    registry = make_registry(
        master=ScriptedResidentModule("master", []),
        debate=ScriptedResidentModule("debate", []),
        execution=ScriptedResidentModule("execution", []),
        test=ScriptedResidentModule("test", []),
        final_review=ScriptedResidentModule("final_review", []),
    )

    assert set(registry.records) == {"master", "debate", "execution", "test", "final_review"}
    assert registry.records["debate"].resident_agents == ["debate_leader"]
    assert "debate_worker" not in json.dumps(
        {key: record.model_dump(mode="json") for key, record in registry.records.items()}
    )


def test_top_level_normal_flow_routes_resident_subgraphs_to_master_closeout(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    registry = make_registry(
        master=ScriptedResidentModule(
            "master",
            [
                ("execution", "master_to_execution", "ready"),
                ("closeout", "master_closeout", "runtime_terminal"),
            ],
        ),
        debate=ScriptedResidentModule("debate", []),
        execution=ScriptedResidentModule("execution", [("test", "execution_to_test", "ready")]),
        test=ScriptedResidentModule("test", [("final_review", "test_to_final_review", "ready")]),
        final_review=ScriptedResidentModule(
            "final_review",
            [("master", "final_review_to_master", "ready")],
        ),
    )

    with AegisTopLevelRuntime(project, registry=registry, acquire_lock=True) as runtime:
        result = runtime.run(run_id="run-normal")

    assert result.terminal_status == TopLevelTerminalStatus.CLOSED
    assert [event.source_module for event in result.route_history_tail] == [
        "master",
        "execution",
        "test",
        "final_review",
        "master",
    ]
    assert result.route_count == 5
    assert result.route_history_log_ref is not None
    assert Path(result.route_history_log_ref).exists()


def test_master_triggered_debate_returns_to_master_not_execution(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    registry = make_registry(
        master=ScriptedResidentModule(
            "master",
            [
                ("debate", "master_requirement_to_debate", "ready"),
                ("execution", "master_to_execution", "ready"),
                ("closeout", "master_closeout", "runtime_terminal"),
            ],
        ),
        debate=ScriptedResidentModule(
            "debate",
            [("master", "debate_requirement_to_master", "ready")],
        ),
        execution=ScriptedResidentModule("execution", [("test", "execution_to_test", "ready")]),
        test=ScriptedResidentModule("test", [("final_review", "test_to_final_review", "ready")]),
        final_review=ScriptedResidentModule(
            "final_review",
            [("master", "final_review_to_master", "ready")],
        ),
    )

    with AegisTopLevelRuntime(project, registry=registry) as runtime:
        result = runtime.run(run_id="run-master-debate")

    assert [(event.source_module, event.target_module) for event in result.route_history_tail][:3] == [
        ("master", "debate"),
        ("debate", "master"),
        ("master", "execution"),
    ]


def test_execution_triggered_debate_returns_to_execution(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    registry = make_registry(
        master=ScriptedResidentModule(
            "master",
            [
                ("execution", "master_to_execution", "ready"),
                ("closeout", "master_closeout", "runtime_terminal"),
            ],
        ),
        debate=ScriptedResidentModule(
            "debate",
            [("execution", "debate_route_to_execution", "ready")],
        ),
        execution=ScriptedResidentModule(
            "execution",
            [
                ("debate", "execution_route_to_debate", "ready"),
                ("test", "execution_to_test", "ready"),
            ],
        ),
        test=ScriptedResidentModule("test", [("final_review", "test_to_final_review", "ready")]),
        final_review=ScriptedResidentModule(
            "final_review",
            [("master", "final_review_to_master", "ready")],
        ),
    )

    with AegisTopLevelRuntime(project, registry=registry) as runtime:
        result = runtime.run(run_id="run-execution-debate")

    assert ("debate", "execution") in [
        (event.source_module, event.target_module) for event in result.route_history_tail
    ]


def test_test_failure_loops_to_execution_before_final_review(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    registry = make_registry(
        master=ScriptedResidentModule(
            "master",
            [
                ("execution", "master_to_execution", "ready"),
                ("closeout", "master_closeout", "runtime_terminal"),
            ],
        ),
        debate=ScriptedResidentModule("debate", []),
        execution=ScriptedResidentModule(
            "execution",
            [
                ("test", "execution_to_test", "ready"),
                ("test", "execution_to_test", "ready"),
            ],
        ),
        test=ScriptedResidentModule(
            "test",
            [
                ("execution", "test_to_execution_rework", "ready"),
                ("final_review", "test_to_final_review", "ready"),
            ],
        ),
        final_review=ScriptedResidentModule(
            "final_review",
            [("master", "final_review_to_master", "ready")],
        ),
    )

    with AegisTopLevelRuntime(project, registry=registry) as runtime:
        result = runtime.run(run_id="run-test-loop")

    assert [(event.source_module, event.target_module) for event in result.route_history_tail] == [
        ("master", "execution"),
        ("execution", "test"),
        ("test", "execution"),
        ("execution", "test"),
        ("test", "final_review"),
        ("final_review", "master"),
        ("master", "closeout"),
    ]


def test_resident_failure_stops_runtime_and_writes_evidence(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    registry = make_registry(
        master=ScriptedResidentModule("master", [("execution", "master_to_execution", "ready")]),
        debate=ScriptedResidentModule("debate", []),
        execution=ScriptedResidentModule("execution", [], fail_on_call=True),
        test=ScriptedResidentModule("test", []),
        final_review=ScriptedResidentModule("final_review", []),
    )

    with AegisTopLevelRuntime(project, registry=registry) as runtime:
        result = runtime.run(run_id="run-failure")

    assert result.terminal_status == TopLevelTerminalStatus.STOPPED_DUE_TO_MODULE_FAILURE
    assert result.failure_evidence_ref is not None
    assert Path(result.failure_evidence_ref).exists()


def test_route_history_state_is_bounded_but_full_log_is_preserved(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    registry = make_registry(
        master=ScriptedResidentModule(
            "master",
            [
                ("execution", "master_to_execution", "ready"),
                ("closeout", "master_closeout", "runtime_terminal"),
            ],
        ),
        debate=ScriptedResidentModule("debate", []),
        execution=ScriptedResidentModule(
            "execution",
            [
                ("test", "execution_to_test", "ready"),
                ("test", "execution_to_test", "ready"),
            ],
        ),
        test=ScriptedResidentModule(
            "test",
            [
                ("execution", "test_to_execution_rework", "ready"),
                ("final_review", "test_to_final_review", "ready"),
            ],
        ),
        final_review=ScriptedResidentModule(
            "final_review",
            [("master", "final_review_to_master", "ready")],
        ),
    )

    with AegisTopLevelRuntime(
        project,
        registry=registry,
        route_history_tail_limit=3,
    ) as runtime:
        result = runtime.run(run_id="run-history")

    assert result.route_count == 7
    assert len(result.route_history_tail) == 3
    assert result.route_history_log_ref is not None
    assert len(Path(result.route_history_log_ref).read_text(encoding="utf-8").splitlines()) == 7


def test_parent_source_does_not_import_module_business_logic() -> None:
    top_level_dir = Path(__file__).parents[1] / "src" / "aegis" / "top_level"
    forbidden_import_prefixes = {
        "aegis.modules.master.flow",
        "aegis.modules.debate.leader",
        "aegis.modules.execution.graph",
        "aegis.modules.test.graph",
        "aegis.modules.final_review.graph",
    }

    for source_path in top_level_dir.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in forbidden_import_prefixes:
                pytest.fail(f"{source_path.name} imports business module {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden_import_prefixes:
                        pytest.fail(f"{source_path.name} imports business module {alias.name}")
