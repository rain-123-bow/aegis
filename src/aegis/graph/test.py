from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from aegis.models import TestFinalResult, TestGraphSpec, TestRouteResult, TestRouteSpec
from aegis.tools import ToolCallRequest, ToolGovernance


class TestGraphCompiler:
    def compile(self, spec: TestGraphSpec) -> dict[str, list[TestRouteSpec]]:
        grouped: dict[str, list[TestRouteSpec]] = defaultdict(list)
        for route in spec.routes:
            grouped[route.superstep].append(route)
        return dict(grouped)


def synthesize_test_graph(state: dict[str, Any]) -> dict[str, Any]:
    goal = state["current_query"]["goal"].lower()
    execution_state = state.get("execution_state") or {}
    rework_applied = bool(execution_state.get("rework_applied"))

    if execution_state.get("status") == "blocked":
        routes = [
            TestRouteSpec(
                route_id="execution_blocker_review",
                description="execution blocker evidence route",
                expected_result="blocked",
            )
        ]
        integration_required = False
    elif "parallel" in goal or "super-step" in goal or "superstep" in goal:
        routes = [
            TestRouteSpec(route_id="route_a", description="parallel route A", superstep="parallel"),
            TestRouteSpec(
                route_id="route_b",
                description="parallel route B",
                superstep="parallel",
                expected_result="failed" if "test failure" in goal and not rework_applied else "passed",
            ),
        ]
        integration_required = True
    else:
        routes = [
            TestRouteSpec(
                route_id="atomic",
                description="atomic validation route",
                expected_result="failed" if "test failure" in goal and not rework_applied else "passed",
            )
        ]
        integration_required = False

    spec = TestGraphSpec(routes=routes, integration_required=integration_required)
    test_state = dict(state.get("test_state") or {})
    test_state.update(
        {
            "test_graph_spec_ref": spec.spec_id,
            "test_graph_spec": spec.model_dump(mode="json"),
            "route_results": [],
            "final_test_result": None,
        }
    )
    return {"test_state": test_state}


class DynamicTestSubgraph:
    def __init__(self, governance: ToolGovernance | None = None):
        self.governance = governance or ToolGovernance()
        self.compiler = TestGraphCompiler()

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        project_root = Path(state["project_root"])
        test_state = dict(state.get("test_state") or {})
        spec = TestGraphSpec.model_validate(test_state["test_graph_spec"])
        grouped = self.compiler.compile(spec)
        route_results: list[TestRouteResult] = []
        stop_after_superstep = False

        for superstep, routes in grouped.items():
            test_state["current_superstep"] = superstep
            current_results = [self._run_route(project_root, route) for route in routes]
            route_results.extend(current_results)
            if any(item.result in {"failed", "blocked", "inconclusive"} for item in current_results):
                stop_after_superstep = True
            if stop_after_superstep:
                break

        final_status = "passed"
        if any(item.result == "failed" for item in route_results):
            final_status = "failed"
        elif any(item.result in {"blocked", "inconclusive"} for item in route_results):
            final_status = "inconclusive"

        final = TestFinalResult(
            result=final_status,
            route_results=route_results,
            barrier_summary="completed current superstep before barrier decision",
        )
        test_state.update(
            {
                "route_results": [item.model_dump(mode="json") for item in route_results],
                "final_test_result": final.model_dump(mode="json"),
                "run_count": int(test_state.get("run_count") or 0) + 1,
            }
        )
        return {"test_state": test_state}

    def _run_route(self, project_root: Path, route: TestRouteSpec) -> TestRouteResult:
        request = ToolCallRequest(
            calling_node="dynamic_test_subgraph",
            actor_role="test_leader",
            tool_name="test.run_route",
            arguments={"route_id": route.route_id},
            declared_intent="run deterministic local test route",
            expected_side_effects=["local_project_state"],
            project_scope=str(project_root),
        )

        def action() -> str:
            evidence_dir = project_root / ".aegis" / "test-evidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            path = evidence_dir / f"{route.route_id}-{uuid4().hex[:8]}.json"
            payload = {
                "route_id": route.route_id,
                "description": route.description,
                "result": route.expected_result,
            }
            path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return str(path)

        result = self.governance.execute(request, action)
        if not result.executed:
            return TestRouteResult(
                route_id=route.route_id,
                superstep=route.superstep,
                result="blocked",
                evidence_ref=result.decision.reason,
            )
        return TestRouteResult(
            route_id=route.route_id,
            superstep=route.superstep,
            result=route.expected_result,
            evidence_ref=result.result,
        )


def run_dynamic_tests(state: dict[str, Any]) -> dict[str, Any]:
    return DynamicTestSubgraph().run(state)
