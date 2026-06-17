from aegis.graph.final_review import final_review_node
from aegis.models import new_initial_state


def test_final_review_does_not_create_workers_run_tests_or_modify_code(tmp_path):
    state = new_initial_state(str(tmp_path), "implement feature")
    state["execution_state"]["status"] = "completed"
    state["test_state"]["final_test_result"] = {"result": "passed", "route_results": [], "barrier_summary": "ok"}

    result = final_review_node(state)["final_review_result"]

    assert result["decision"] == "accept_for_master"
    assert result["workers_created"] is False
    assert result["tests_run"] is False
    assert result["code_modified"] is False
    assert result["global_causal_truth_merge_performed"] is False

