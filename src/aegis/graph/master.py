from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from aegis.graph.debate import debate_node
from aegis.graph.execution import execution_dispatch
from aegis.graph.final_review import final_review_node
from aegis.graph.routing import FLOW_ROUTING_POLICY
from aegis.graph.state import AegisState
from aegis.graph.test import run_dynamic_tests, synthesize_test_graph
from aegis.models import (
    AegisGraphState,
    CommitGate,
    DebateRequestState,
    DeveloperInterruptRecord,
    RouteExpandPlan,
    SelectedFact,
    StoreCandidate,
    TaskBoundary,
    new_initial_state,
)
from aegis.modules.master.flow import (
    continuity_preflight,
    execution_handoff,
    pm_intake,
    pm_session_start_or_resume,
    requirement_doc_draft,
    requirement_review,
    requirement_user_approval,
    route_after_pm_intake,
    review_debate_dispatch,
    review_user_approval,
    route_after_continuity_preflight,
    route_after_requirement_approval,
    route_after_review_approval,
)
from aegis.stores import ProjectStores
from aegis.tools import ToolCallRequest, ToolGovernance


def _goal(state: dict[str, Any]) -> str:
    return state["current_query"]["goal"]


def _append_audit(state: dict[str, Any], audit: dict[str, Any]) -> list[dict[str, Any]]:
    return [*(state.get("tool_intent_audits") or []), audit]


def master_intake(state: AegisState) -> dict[str, Any]:
    AegisGraphState.model_validate(state)
    return {}


def task_boundary_decision(state: AegisState) -> dict[str, Any]:
    goal = _goal(state)
    lowered = goal.lower()
    if "planning only" in lowered:
        decision = "planning_only"
    elif "reject" in lowered:
        decision = "reject"
    elif "split" in lowered:
        decision = "split"
    else:
        decision = "create"
    boundary = TaskBoundary(
        decision=decision,
        task_ids=[f"task-{uuid4().hex[:8]}"] if decision in {"create", "split"} else [],
        reason="deterministic task boundary decision for first runnable milestone",
    )
    return {"task_boundary": boundary.model_dump(mode="json")}


def project_state_context_load(state: AegisState) -> dict[str, Any]:
    stores = ProjectStores(state["project_root"])
    layout = stores.ensure_layout()
    return {
        "tool_intent_audits": _append_audit(
            state,
            {
                "tool_name": "stores.ensure_layout",
                "decision": "allow",
                "paths": layout,
            },
        )
    }


def route_expand_planning(state: AegisState) -> dict[str, Any]:
    goal = _goal(state).lower()
    selected_facts = [
        SelectedFact(
            fact_id="single_project_default",
            route_grade="A",
            expand_grade="A",
            reason="Aegis v2 defaults to single-project execution.",
        )
    ]
    plan = RouteExpandPlan(selected_facts=selected_facts)

    updates: dict[str, Any] = {"route_expand_plan": plan.model_dump(mode="json")}
    if any(marker in goal for marker in ["remote push", "create pr", "merge", "release", "deploy"]):
        tool_name = "git.push" if "push" in goal else "release.perform"
        request = ToolCallRequest(
            calling_node="route_expand_planning",
            actor_role="master",
            tool_name=tool_name,
            arguments={"goal": state["current_query"]["goal"]},
            declared_intent="request external responsibility action",
            expected_side_effects=["external", "irreversible", "remote"],
            project_scope=state["project_root"],
        )
        decision = ToolGovernance().assess(request)
        updates["pending_tool_request"] = request.model_dump(mode="json")
        updates["tool_intent_audits"] = _append_audit(
            state,
            {
                "tool_name": request.tool_name,
                "decision": decision.decision,
                "reason": decision.reason,
            },
        )
    elif any(marker in goal for marker in ["debate", "ambiguous", "non-dominated", "causal conflict"]):
        updates["debate_request_state"] = DebateRequestState(
            debate_required=True,
            requested_by="master",
            trigger_kind=["master_condition"],
            candidate_positions=["single_execution_actor", "multi_group_execution"],
            resume_target="master_review",
        ).model_dump(mode="json")
    return updates


def route_after_planning(state: AegisState) -> str:
    if state.get("pending_tool_request"):
        return "developer_authorization_interrupt"
    debate_request = state.get("debate_request_state") or {}
    if debate_request.get("debate_required") and not state.get("debate_result"):
        FLOW_ROUTING_POLICY.require_allowed("master", "debate")
        return "debate_node"
    FLOW_ROUTING_POLICY.require_allowed("master", "execution")
    return "execution_dispatch"


def route_after_execution(state: AegisState) -> str:
    execution_state = state.get("execution_state") or {}
    debate_request = state.get("debate_request_state") or {}
    if debate_request.get("debate_required") and execution_state.get("discovered_debate_need"):
        FLOW_ROUTING_POLICY.require_allowed("execution", "debate")
        return "debate_node"
    FLOW_ROUTING_POLICY.require_allowed("execution", "test")
    return "test_synthesize"


def route_after_test(state: AegisState) -> str:
    final_result = ((state.get("test_state") or {}).get("final_test_result") or {}).get("result")
    execution_state = state.get("execution_state") or {}
    if execution_state.get("status") == "blocked":
        FLOW_ROUTING_POLICY.require_allowed("test", "final_review")
        return "final_review"
    if final_result in {"failed", "blocked", "inconclusive"} and not execution_state.get("rework_applied"):
        FLOW_ROUTING_POLICY.require_allowed("test", "execution")
        return "execution_dispatch"
    FLOW_ROUTING_POLICY.require_allowed("test", "final_review")
    return "final_review"


def developer_authorization_interrupt(state: AegisState) -> dict[str, Any]:
    pending = state.get("pending_tool_request")
    if not pending:
        return {}
    request = ToolCallRequest.model_validate(pending)
    decision = ToolGovernance().assess(request)
    resume_value = interrupt(
        {
            "request_id": request.request_id,
            "tool_name": request.tool_name,
            "reason": decision.reason,
            "recommended_decision": decision.assessment.recommended_decision,
        }
    )
    approved = bool(isinstance(resume_value, dict) and resume_value.get("approved"))
    record = DeveloperInterruptRecord(
        request_id=request.request_id,
        reason=decision.reason,
        decision=resume_value if isinstance(resume_value, dict) else {"value": resume_value},
        resolved=True,
    )
    blockers = list(state.get("blockers") or [])
    blockers.append(
        "developer approved external action; Aegis recorded approval but did not execute it"
        if approved
        else "developer denied or did not approve external action"
    )
    return {
        "developer_interrupts": [
            *(state.get("developer_interrupts") or []),
            record.model_dump(mode="json"),
        ],
        "pending_tool_request": None,
        "blockers": blockers,
    }


def final_commit_gate(state: AegisState) -> dict[str, Any]:
    if state.get("final_review_result"):
        FLOW_ROUTING_POLICY.require_allowed("final_review", "master_closeout")
    goal = _goal(state).lower()
    external_requested = any(
        marker in goal for marker in ["remote push", "create pr", "merge", "release", "deploy"]
    )
    gate = CommitGate(
        commit_candidate_requested=True,
        developer_authorization_required=True,
        remote_push_performed=False,
        pr_created=False,
        remote_merge_performed=False,
        release_performed=False,
    )
    blockers = list(state.get("blockers") or [])
    if external_requested and not blockers:
        blockers.append("external responsibility action requires developer authorization")
    return {"commit_gate": gate.model_dump(mode="json"), "blockers": blockers}


def project_closeout(state: AegisState) -> dict[str, Any]:
    stores = ProjectStores(state["project_root"])
    causal = StoreCandidate(
        store="causal",
        kind="causal_candidate",
        payload={
            "debate_result": state.get("debate_result"),
            "final_review_result": state.get("final_review_result"),
            "scope": "first_milestone_runtime_closeout",
        },
    )
    knowledge = StoreCandidate(
        store="knowledge",
        kind="static_boundary",
        payload={
            "fact": "LangGraph Store is not used for Aegis project memory",
            "scope": "aegis_v0_1_2",
        },
    )
    for candidate in (causal, knowledge):
        candidate.artifact_ref = stores.write_candidate(candidate)

    closeout = {
        "status": "closed",
        "history_source": "git_commit_history",
        "knowledge_ref": knowledge.artifact_ref,
        "causal_ref": causal.artifact_ref,
        "langgraph_store_used_for_project_memory": False,
    }
    return {
        "knowledge_candidates": [
            *(state.get("knowledge_candidates") or []),
            knowledge.model_dump(mode="json"),
        ],
        "causal_candidates": [*(state.get("causal_candidates") or []), causal.model_dump(mode="json")],
        "closeout": closeout,
    }


def build_master_graph(checkpointer: SqliteSaver | None = None):
    builder = StateGraph(AegisState)
    builder.add_node("continuity_preflight", continuity_preflight)
    builder.add_node("master_intake", master_intake)
    builder.add_node("pm_session_start_or_resume", pm_session_start_or_resume)
    builder.add_node("pm_intake", pm_intake)
    builder.add_node("requirement_doc_draft", requirement_doc_draft)
    builder.add_node("requirement_user_approval", requirement_user_approval)
    builder.add_node("requirement_review", requirement_review)
    builder.add_node("review_debate_dispatch", review_debate_dispatch)
    builder.add_node("review_user_approval", review_user_approval)
    builder.add_node("execution_handoff", execution_handoff)
    builder.add_node("task_boundary_decision", task_boundary_decision)
    builder.add_node("project_state_context_load", project_state_context_load)
    builder.add_node("route_expand_planning", route_expand_planning)
    builder.add_node("developer_authorization_interrupt", developer_authorization_interrupt)
    builder.add_node("debate_node", debate_node)
    builder.add_node("execution_dispatch", execution_dispatch)
    builder.add_node("test_synthesize", synthesize_test_graph)
    builder.add_node("run_dynamic_tests", run_dynamic_tests)
    builder.add_node("final_review", final_review_node)
    builder.add_node("final_commit_gate", final_commit_gate)
    builder.add_node("project_closeout", project_closeout)

    builder.add_edge(START, "continuity_preflight")
    builder.add_conditional_edges(
        "continuity_preflight",
        route_after_continuity_preflight,
        {
            "master_intake": "master_intake",
            "final_commit_gate": "final_commit_gate",
        },
    )
    builder.add_edge("master_intake", "pm_session_start_or_resume")
    builder.add_edge("pm_session_start_or_resume", "pm_intake")
    builder.add_conditional_edges(
        "pm_intake",
        route_after_pm_intake,
        {
            "requirement_doc_draft": "requirement_doc_draft",
            "final_commit_gate": "final_commit_gate",
        },
    )
    builder.add_edge("requirement_doc_draft", "requirement_user_approval")
    builder.add_conditional_edges(
        "requirement_user_approval",
        route_after_requirement_approval,
        {
            "requirement_review": "requirement_review",
            "final_commit_gate": "final_commit_gate",
        },
    )
    builder.add_edge("requirement_review", "review_debate_dispatch")
    builder.add_edge("review_debate_dispatch", "review_user_approval")
    builder.add_conditional_edges(
        "review_user_approval",
        route_after_review_approval,
        {
            "execution_handoff": "execution_handoff",
            "final_commit_gate": "final_commit_gate",
        },
    )
    builder.add_edge("execution_handoff", "task_boundary_decision")
    builder.add_edge("task_boundary_decision", "project_state_context_load")
    builder.add_edge("project_state_context_load", "route_expand_planning")
    builder.add_conditional_edges(
        "route_expand_planning",
        route_after_planning,
        {
            "developer_authorization_interrupt": "developer_authorization_interrupt",
            "debate_node": "debate_node",
            "execution_dispatch": "execution_dispatch",
        },
    )
    builder.add_edge("developer_authorization_interrupt", "final_commit_gate")
    builder.add_edge("debate_node", "execution_dispatch")
    builder.add_conditional_edges(
        "execution_dispatch",
        route_after_execution,
        {
            "debate_node": "debate_node",
            "test_synthesize": "test_synthesize",
            "final_review": "final_review",
        },
    )
    builder.add_edge("test_synthesize", "run_dynamic_tests")
    builder.add_conditional_edges(
        "run_dynamic_tests",
        route_after_test,
        {
            "execution_dispatch": "execution_dispatch",
            "final_review": "final_review",
        },
    )
    builder.add_edge("final_review", "final_commit_gate")
    builder.add_edge("final_commit_gate", "project_closeout")
    builder.add_edge("project_closeout", END)
    return builder.compile(checkpointer=checkpointer)


class AegisRuntime:
    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root)
        stores = ProjectStores(self.project_root)
        stores.runtime_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(stores.checkpoint_path, check_same_thread=False)
        self.checkpointer = SqliteSaver(self._conn)
        if hasattr(self.checkpointer, "setup"):
            self.checkpointer.setup()
        self.graph = build_master_graph(checkpointer=self.checkpointer)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "AegisRuntime":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def run(
        self,
        goal: str,
        thread_id: str | None = None,
        master_semantic_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        actual_thread_id = thread_id or f"thread-{uuid4().hex[:12]}"
        config = {"configurable": {"thread_id": actual_thread_id}}
        state = new_initial_state(str(self.project_root), goal, thread_id=actual_thread_id)
        if master_semantic_analysis is not None:
            state["master_semantic_analysis"] = master_semantic_analysis
        result = self.graph.invoke(state, config=config)
        return {"thread_id": actual_thread_id, "result": result}

    def resume(self, thread_id: str, decision: dict[str, Any]) -> dict[str, Any]:
        config = {"configurable": {"thread_id": thread_id}}
        result = self.graph.invoke(Command(resume=decision), config=config)
        return {"thread_id": thread_id, "result": result}

    def inspect(self, thread_id: str) -> dict[str, Any]:
        config = {"configurable": {"thread_id": thread_id}}
        snapshot = self.graph.get_state(config)
        return {
            "thread_id": thread_id,
            "values": snapshot.values,
            "next": snapshot.next,
            "metadata": snapshot.metadata,
        }
