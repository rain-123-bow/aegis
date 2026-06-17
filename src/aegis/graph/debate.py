from __future__ import annotations

from typing import Any

from aegis.models import DebateResult


def debate_node(state: dict[str, Any]) -> dict[str, Any]:
    request = state.get("debate_request_state") or {}
    positions = request.get("candidate_positions") or ["single_project_depth", "split_groups"]
    selected = positions[0]
    result = DebateResult(
        selected_position=selected,
        why="selected by deterministic black-box Debate node for the first runnable milestone",
        causal_package={
            "source": "debate_node",
            "requested_by": request.get("requested_by"),
            "trigger_kind": request.get("trigger_kind", []),
            "selected_position": selected,
            "rejected_positions": positions[1:],
            "scope": "first_milestone_black_box_debate",
        },
    )
    execution_state = dict(state.get("execution_state") or {})
    if request.get("requested_by") == "execution_actor":
        execution_state["adjudication_applied"] = True
        execution_state["discovered_debate_need"] = False
    return {
        "debate_result": result.model_dump(mode="json"),
        "execution_state": execution_state,
        "debate_request_state": {
            **request,
            "debate_required": False,
        },
    }

