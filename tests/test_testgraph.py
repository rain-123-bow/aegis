from aegis.graph.test import DynamicTestSubgraph, TestGraphCompiler, synthesize_test_graph
from aegis.models import TestGraphSpec, TestRouteSpec, new_initial_state


def test_compiler_groups_parallel_superstep():
    spec = TestGraphSpec(
        routes=[
            TestRouteSpec(route_id="a", description="A", superstep="s1"),
            TestRouteSpec(route_id="b", description="B", superstep="s1"),
            TestRouteSpec(route_id="c", description="C", superstep="s2"),
        ]
    )

    compiled = TestGraphCompiler().compile(spec)

    assert [route.route_id for route in compiled["s1"]] == ["a", "b"]
    assert [route.route_id for route in compiled["s2"]] == ["c"]


def test_parallel_failure_completes_current_superstep_before_barrier(tmp_path):
    state = new_initial_state(str(tmp_path), "parallel test failure")
    state["execution_state"]["status"] = "completed"
    state = {**state, **synthesize_test_graph(state)}

    result = DynamicTestSubgraph().run(state)
    route_results = result["test_state"]["route_results"]

    assert len(route_results) == 2
    assert result["test_state"]["final_test_result"]["result"] == "failed"
    assert result["test_state"]["final_test_result"]["barrier_summary"]

