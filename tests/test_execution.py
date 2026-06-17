from aegis.graph.execution import ExecutionActor
from aegis.models import new_initial_state


def test_execution_actor_completes_single_project_task(tmp_path):
    state = new_initial_state(str(tmp_path), "implement a small feature")
    result = ExecutionActor().run(state)

    assert result["execution_state"]["status"] == "completed"
    assert result["execution_state"]["implementation_artifact_ref"]
    assert result["execution_state"]["discovered_debate_need"] is False


def test_execution_actor_blocks_multi_repo_task(tmp_path):
    state = new_initial_state(str(tmp_path), "implement feature across multiple repos")
    result = ExecutionActor().run(state)

    assert result["execution_state"]["status"] == "blocked"
    assert result["execution_state"]["blocked_reason"] == "task_requires_cross_project_coordination"


def test_execution_actor_requests_debate_for_non_dominated_route(tmp_path):
    state = new_initial_state(str(tmp_path), "non-dominated implementation route conflict")
    result = ExecutionActor().run(state)

    assert result["execution_state"]["discovered_debate_need"] is True
    assert result["debate_request_state"]["requested_by"] == "execution_actor"

