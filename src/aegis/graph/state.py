from __future__ import annotations

from typing import Any, TypedDict


class AegisState(TypedDict, total=False):
    run_id: str
    project_id: str
    project_root: str
    current_query: dict[str, Any]
    task_boundary: dict[str, Any] | None
    route_expand_plan: dict[str, Any]
    debate_request_state: dict[str, Any]
    debate_result: dict[str, Any] | None
    execution_state: dict[str, Any]
    test_state: dict[str, Any]
    final_review_result: dict[str, Any] | None
    tool_intent_audits: list[dict[str, Any]]
    archive_candidates: list[dict[str, Any]]
    knowledge_candidates: list[dict[str, Any]]
    causal_candidates: list[dict[str, Any]]
    blockers: list[str]
    developer_interrupts: list[dict[str, Any]]
    commit_gate: dict[str, Any] | None
    pending_tool_request: dict[str, Any] | None
    closeout: dict[str, Any] | None

