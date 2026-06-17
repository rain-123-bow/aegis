from aegis.models import AegisGraphState, TaskBoundary, new_initial_state


def test_aegis_graph_state_schema_validates(tmp_path):
    state = new_initial_state(str(tmp_path), "implement feature")
    parsed = AegisGraphState.model_validate(state)

    assert parsed.project_root == str(tmp_path)
    assert parsed.current_query.goal == "implement feature"
    assert parsed.execution_state.status == "not_started"


def test_task_boundary_supports_required_decisions():
    for decision in ["create", "bind", "split", "planning_only", "reject"]:
        boundary = TaskBoundary(decision=decision, task_ids=[])
        assert boundary.decision == decision

