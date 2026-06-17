import ast
from pathlib import Path

from aegis.graph import AegisRuntime


def test_normal_task_runs_end_to_end(tmp_path):
    with AegisRuntime(tmp_path) as runtime:
        payload = runtime.run("implement a small feature", thread_id="normal")

    result = payload["result"]
    assert result["thread_id"] == "normal"
    assert result["execution_state"]["status"] == "completed"
    assert result["test_state"]["final_test_result"]["result"] == "passed"
    assert result["final_review_result"]["decision"] == "accept_for_master"
    assert result["closeout"]["langgraph_store_used_for_project_memory"] is False
    assert Path(result["closeout"]["archive_ref"]).exists()
    assert Path(result["closeout"]["knowledge_ref"]).exists()
    assert Path(result["closeout"]["causal_ref"]).exists()


def test_master_conditionally_triggers_debate(tmp_path):
    with AegisRuntime(tmp_path) as runtime:
        payload = runtime.run("ambiguous architecture needs debate", thread_id="debate")

    result = payload["result"]
    assert result["debate_result"]["status"] == "causal_candidate"
    assert result["execution_state"]["status"] == "completed"


def test_execution_can_trigger_debate_and_resume(tmp_path):
    with AegisRuntime(tmp_path) as runtime:
        payload = runtime.run("implementation route conflict during execution", thread_id="exec-debate")

    result = payload["result"]
    assert result["debate_result"]["causal_package"]["requested_by"] == "execution_actor"
    assert result["execution_state"]["adjudication_applied"] is True


def test_cross_project_task_closes_with_governance_blocker(tmp_path):
    with AegisRuntime(tmp_path) as runtime:
        payload = runtime.run("implement feature across multiple repos", thread_id="blocked")

    result = payload["result"]
    assert result["execution_state"]["status"] == "blocked"
    assert result["test_state"]["final_test_result"]["result"] == "inconclusive"
    assert result["final_review_result"]["decision"] == "governance_blocker"
    assert result["closeout"]["status"] == "closed"


def test_test_failure_returns_to_execution_then_passes_after_rework(tmp_path):
    with AegisRuntime(tmp_path) as runtime:
        payload = runtime.run("parallel test failure should rework", thread_id="rework")

    result = payload["result"]
    assert result["execution_state"]["rework_applied"] is True
    assert result["test_state"]["final_test_result"]["result"] == "passed"


def test_external_tool_request_interrupts_and_can_resume(tmp_path):
    with AegisRuntime(tmp_path) as runtime:
        first = runtime.run("please perform remote push", thread_id="interrupt")
        assert "__interrupt__" in first["result"]

        resumed = runtime.resume("interrupt", {"approved": False})

    result = resumed["result"]
    assert result["developer_interrupts"][0]["resolved"] is True
    assert result["commit_gate"]["remote_push_performed"] is False
    assert result["closeout"]["status"] == "closed"


def test_checkpoint_can_be_inspected_with_same_thread_id(tmp_path):
    with AegisRuntime(tmp_path) as runtime:
        runtime.run("implement checkpointed feature", thread_id="checkpoint")

    with AegisRuntime(tmp_path) as runtime:
        snapshot = runtime.inspect("checkpoint")

    assert snapshot["values"]["run_id"]
    assert snapshot["values"]["closeout"]["status"] == "closed"


def test_langgraph_store_is_not_used_for_project_memory():
    root = Path(__file__).resolve().parents[1]
    source = "\n".join(path.read_text(encoding="utf-8") for path in (root / "src").rglob("*.py"))
    master_source = (root / "src" / "aegis" / "graph" / "master.py").read_text(encoding="utf-8")
    tree = ast.parse(master_source)

    assert ".compile(checkpointer=checkpointer)" in source
    assert "BaseStore" not in source
    assert "InMemoryStore" not in source
    compile_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "compile"
    ]
    assert compile_calls
    assert all(keyword.arg != "store" for call in compile_calls for keyword in call.keywords)
    assert "ExecutionGroup" not in source
    assert "FrontAgent" not in source
    assert "BackAgent" not in source
