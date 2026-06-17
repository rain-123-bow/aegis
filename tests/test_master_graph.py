import ast
import json
import subprocess
from pathlib import Path

from aegis.graph import AegisRuntime


def _run_git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _make_project_with_remote(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    project = tmp_path / "project"
    _run_git(tmp_path, "init", "--bare", str(remote))
    _run_git(tmp_path, "clone", str(remote), str(project))
    _run_git(project, "config", "user.email", "aegis@example.invalid")
    _run_git(project, "config", "user.name", "Aegis Test")
    (project / "README.md").write_text("# Demo\n", encoding="utf-8")
    _run_git(project, "add", "README.md")
    _run_git(project, "commit", "-m", "initial")
    _run_git(project, "push", "origin", "HEAD")
    return project


def _make_project_without_remote(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    _run_git(project, "init")
    _run_git(project, "config", "user.email", "aegis@example.invalid")
    _run_git(project, "config", "user.name", "Aegis Test")
    (project / "README.md").write_text("# Demo\n", encoding="utf-8")
    _run_git(project, "add", "README.md")
    _run_git(project, "commit", "-m", "initial")
    return project


def _read_artifact_json(artifact_ref: dict) -> dict:
    return json.loads(Path(artifact_ref["machine_data_path"]).read_text(encoding="utf-8"))


def _semantic_analysis_for(goal: str) -> dict:
    return {
        "purpose": goal,
        "deliverable_requests": ["project artifact"],
        "status": "ready_for_document",
    }


def _approve_master_documents(runtime: AegisRuntime, thread_id: str, goal: str):
    first = runtime.run(
        goal,
        thread_id=thread_id,
        master_semantic_analysis=_semantic_analysis_for(goal),
    )
    assert first["result"]["__interrupt__"][0].value["approval_type"] == "requirement_document"
    second = runtime.resume(thread_id, {"approved": True, "comments": "approved"})
    assert second["result"]["__interrupt__"][0].value["approval_type"] == "review_document"
    return runtime.resume(thread_id, {"approved": True, "comments": "approved"})


def _approve_master_documents_with_semantics(
    runtime: AegisRuntime,
    thread_id: str,
    goal: str,
    semantic_analysis: dict,
):
    first = runtime.run(goal, thread_id=thread_id, master_semantic_analysis=semantic_analysis)
    assert first["result"]["__interrupt__"][0].value["approval_type"] == "requirement_document"
    second = runtime.resume(thread_id, {"approved": True, "comments": "approved"})
    assert second["result"]["__interrupt__"][0].value["approval_type"] == "review_document"
    return runtime.resume(thread_id, {"approved": True, "comments": "approved"})


def test_normal_task_runs_end_to_end(tmp_path, monkeypatch):
    project = _make_project_with_remote(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    with AegisRuntime(project) as runtime:
        payload = _approve_master_documents(runtime, "normal", "implement a small feature")

    result = payload["result"]
    assert result["thread_id"] == "normal"
    handoff = _read_artifact_json(result["master_module_state"]["execution_handoff_ref"])
    assert handoff["status"] == "ready_for_execution"
    assert result["execution_state"]["status"] == "completed"
    assert result["test_state"]["final_test_result"]["result"] == "passed"
    assert result["final_review_result"]["decision"] == "accept_for_master"
    assert result["closeout"]["langgraph_store_used_for_project_memory"] is False
    assert Path(result["closeout"]["archive_ref"]).exists()
    assert Path(result["closeout"]["knowledge_ref"]).exists()
    assert Path(result["closeout"]["causal_ref"]).exists()


def test_master_conditionally_triggers_debate(tmp_path, monkeypatch):
    project = _make_project_with_remote(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    with AegisRuntime(project) as runtime:
        payload = _approve_master_documents(runtime, "debate", "ambiguous architecture needs debate")

    result = payload["result"]
    assert result["debate_result"]["status"] == "causal_candidate"
    assert result["execution_state"]["status"] == "completed"


def test_execution_can_trigger_debate_and_resume(tmp_path, monkeypatch):
    project = _make_project_with_remote(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    with AegisRuntime(project) as runtime:
        payload = _approve_master_documents(
            runtime,
            "exec-debate",
            "implementation route conflict during execution",
        )

    result = payload["result"]
    assert result["debate_result"]["causal_package"]["requested_by"] == "execution_actor"
    assert result["execution_state"]["adjudication_applied"] is True


def test_cross_project_task_closes_with_governance_blocker(tmp_path, monkeypatch):
    project = _make_project_with_remote(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    with AegisRuntime(project) as runtime:
        payload = _approve_master_documents(
            runtime,
            "blocked",
            "implement feature across multiple repos",
        )

    result = payload["result"]
    assert result["execution_state"]["status"] == "blocked"
    assert result["test_state"]["final_test_result"]["result"] == "inconclusive"
    assert result["final_review_result"]["decision"] == "governance_blocker"
    assert result["closeout"]["status"] == "closed"


def test_test_failure_returns_to_execution_then_passes_after_rework(tmp_path, monkeypatch):
    project = _make_project_with_remote(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    with AegisRuntime(project) as runtime:
        payload = _approve_master_documents(
            runtime,
            "rework",
            "parallel test failure should rework",
        )

    result = payload["result"]
    assert result["execution_state"]["rework_applied"] is True
    assert result["test_state"]["final_test_result"]["result"] == "passed"


def test_external_tool_request_interrupts_and_can_resume(tmp_path, monkeypatch):
    project = _make_project_with_remote(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    goal = "please perform remote push"
    with AegisRuntime(project) as runtime:
        first = runtime.run(
            goal,
            thread_id="interrupt",
            master_semantic_analysis=_semantic_analysis_for(goal),
        )
        assert first["result"]["__interrupt__"][0].value["approval_type"] == "requirement_document"
        second = runtime.resume("interrupt", {"approved": True})
        assert second["result"]["__interrupt__"][0].value["approval_type"] == "review_document"
        third = runtime.resume("interrupt", {"approved": True})
        assert third["result"]["__interrupt__"][0].value["tool_name"] == "git.push"

        resumed = runtime.resume("interrupt", {"approved": False})

    result = resumed["result"]
    assert result["developer_interrupts"][0]["resolved"] is True
    assert result["commit_gate"]["remote_push_performed"] is False
    assert result["closeout"]["status"] == "closed"


def test_checkpoint_can_be_inspected_with_same_thread_id(tmp_path, monkeypatch):
    project = _make_project_with_remote(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    with AegisRuntime(project) as runtime:
        _approve_master_documents(runtime, "checkpoint", "implement checkpointed feature")

    with AegisRuntime(project) as runtime:
        snapshot = runtime.inspect("checkpoint")

    assert snapshot["values"]["run_id"]
    assert snapshot["values"]["closeout"]["status"] == "closed"


def test_requirement_rejection_blocks_review_and_execution(tmp_path, monkeypatch):
    project = _make_project_with_remote(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    goal = "implement a small feature"
    with AegisRuntime(project) as runtime:
        first = runtime.run(
            goal,
            thread_id="requirement-denied",
            master_semantic_analysis=_semantic_analysis_for(goal),
        )
        assert first["result"]["__interrupt__"][0].value["approval_type"] == "requirement_document"
        payload = runtime.resume("requirement-denied", {"approved": False, "comments": "not accepted"})

    result = payload["result"]
    assert result["master_module_state"]["requirement_approval"]["approved"] is False
    assert result["master_module_state"].get("review_document") is None
    assert result["execution_state"]["status"] == "not_started"
    assert "requirement document not approved" in result["blockers"]


def test_requirement_approval_interrupt_uses_file_ref_not_inline_document(
    tmp_path, monkeypatch
):
    project = _make_project_with_remote(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    goal = "一个一次性用到根据数据画表格，我要求用 C++ 实现"

    with AegisRuntime(project) as runtime:
        first = runtime.run(
            goal,
            thread_id="artifact-ref",
            master_semantic_analysis={
                "purpose": "根据用户提供的数据生成一次性表格交付物",
                "technical_path_requests": ["C++"],
                "deliverable_requests": ["table artifact"],
                "status": "ready_for_document",
            },
        )

    interrupt_value = first["result"]["__interrupt__"][0].value
    assert interrupt_value["approval_type"] == "requirement_document"
    assert "document" not in interrupt_value
    artifact_ref = interrupt_value["artifact_ref"]
    assert Path(artifact_ref["readme_path"]).name == "README.md"
    assert Path(artifact_ref["readme_path"]).exists()
    assert Path(artifact_ref["primary_document_path"]).exists()

    machine_payload = json.loads(Path(artifact_ref["machine_data_path"]).read_text(encoding="utf-8"))
    assert "C++" not in machine_payload["objective"]
    assert machine_payload["constraints"][0]["admission"] == "preference"

    module_state = first["result"]["master_module_state"]
    assert "requirement_document" not in module_state
    assert "requirement_document_ref" in module_state


def test_master_module_state_carries_artifact_refs_after_full_run(tmp_path, monkeypatch):
    project = _make_project_with_remote(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    goal = "implement a small feature"

    with AegisRuntime(project) as runtime:
        first = runtime.run(
            goal,
            thread_id="state-refs",
            master_semantic_analysis=_semantic_analysis_for(goal),
        )
        requirement_ref = first["result"]["__interrupt__"][0].value["artifact_ref"]
        second = runtime.resume("state-refs", {"approved": True})
        review_ref = second["result"]["__interrupt__"][0].value["artifact_ref"]
        payload = runtime.resume("state-refs", {"approved": True})

    result = payload["result"]
    module_state = result["master_module_state"]
    assert "requirement_document" not in module_state
    assert "review_document" not in module_state
    assert "execution_handoff" not in module_state
    assert module_state["requirement_approval"]["artifact_sha256"] == requirement_ref["sha256"]
    assert module_state["review_approval"]["artifact_sha256"] == review_ref["sha256"]
    assert Path(module_state["execution_handoff_ref"]["readme_path"]).name == "README.md"


def test_continuity_no_remote_blocks_before_requirement_review(tmp_path, monkeypatch):
    project = _make_project_without_remote(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    goal = "implement a small feature"
    with AegisRuntime(project) as runtime:
        payload = runtime.run(
            goal,
            thread_id="no-remote",
            master_semantic_analysis=_semantic_analysis_for(goal),
        )

    result = payload["result"]
    assert "__interrupt__" not in result
    assert result["master_module_state"]["continuity_check"]["status"] == "unknown_remote"
    assert result["master_module_state"].get("requirement_document") is None
    assert result["execution_state"]["status"] == "not_started"
    assert "git remote origin is required for continuity recovery" in result["blockers"]


def test_master_blocks_when_pm_semantic_analysis_is_missing(tmp_path, monkeypatch):
    project = _make_project_with_remote(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))

    with AegisRuntime(project) as runtime:
        payload = runtime.run("implement a small feature", thread_id="missing-semantic-analysis")

    result = payload["result"]
    module_state = result["master_module_state"]
    assert "__interrupt__" not in result
    assert module_state["phase"] == "pm_semantic_analysis_required"
    assert "pm_session" in module_state
    assert "requirement_document_ref" not in module_state
    assert result["execution_state"]["status"] == "not_started"
    assert "PM semantic analysis is required before requirement drafting" in result["blockers"]


def test_master_blocks_when_pm_semantic_analysis_is_not_closed(tmp_path, monkeypatch):
    project = _make_project_with_remote(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))

    with AegisRuntime(project) as runtime:
        payload = runtime.run(
            "用 C++ 做个东西",
            thread_id="clarifying-semantic-analysis",
            master_semantic_analysis={
                "purpose": "",
                "technical_path_requests": ["C++"],
                "unresolved_questions": ["Need objective and success criteria."],
                "status": "clarifying",
            },
        )

    result = payload["result"]
    module_state = result["master_module_state"]
    assert "__interrupt__" not in result
    assert module_state["phase"] == "requirement_intake_needs_clarification"
    assert "conversation_ref" in module_state
    assert "requirement_document_ref" not in module_state
    assert "requirement intake is not closed" in result["blockers"]


def test_master_pm_session_is_created_once_and_survives_node_flow(tmp_path, monkeypatch):
    project = _make_project_with_remote(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    goal = "implement a small feature"

    with AegisRuntime(project) as runtime:
        first = runtime.run(
            goal,
            thread_id="pm-session-stability",
            master_semantic_analysis=_semantic_analysis_for(goal),
        )
        first_pm = first["result"]["master_module_state"]["pm_session"]
        second = runtime.resume("pm-session-stability", {"approved": True})
        second_pm = second["result"]["master_module_state"]["pm_session"]
        payload = runtime.resume("pm-session-stability", {"approved": True})
        final_pm = payload["result"]["master_module_state"]["pm_session"]

    assert first_pm["pm_session_id"] == second_pm["pm_session_id"] == final_pm["pm_session_id"]
    assert first_pm["pm_agent_id"] == second_pm["pm_agent_id"] == final_pm["pm_agent_id"]
    assert first_pm["pm_thread_id"] == second_pm["pm_thread_id"] == final_pm["pm_thread_id"]
    assert final_pm["status"] == "active"


def test_review_debate_gate_resolves_weak_solution_lock(tmp_path, monkeypatch):
    project = _make_project_with_remote(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    goal = "Implement persistence and must use direct JSON files for all persistence."
    with AegisRuntime(project) as runtime:
        payload = _approve_master_documents_with_semantics(
            runtime,
            "review-debate",
            goal,
            {
                "purpose": "Implement persistence for the local project.",
                "technical_path_requests": ["direct JSON files"],
                "deliverable_requests": ["project artifact"],
                "status": "ready_for_document",
            },
        )

    state = payload["result"]["master_module_state"]
    review = _read_artifact_json(state["review_document_ref"])
    handoff = _read_artifact_json(state["execution_handoff_ref"])
    issues = review["debate_issues"]
    assert issues
    assert issues[0]["status"] == "resolved"
    assert handoff["open_limits"] == []


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
