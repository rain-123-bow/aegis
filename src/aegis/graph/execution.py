from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from aegis.models import ExecutionState
from aegis.tools import ToolCallRequest, ToolGovernance


def is_cross_project_goal(goal: str) -> bool:
    lowered = goal.lower()
    markers = ["multi-repo", "multiple repos", "cross project", "cross-project", "two repositories"]
    return any(marker in lowered for marker in markers)


def needs_execution_debate(goal: str) -> bool:
    lowered = goal.lower()
    markers = ["execution conflict", "route conflict", "non-dominated implementation"]
    return any(marker in lowered for marker in markers)


class ExecutionActor:
    def __init__(self, governance: ToolGovernance | None = None):
        self.governance = governance or ToolGovernance()

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        goal = state["current_query"]["goal"]
        project_root = Path(state["project_root"])
        execution_state = dict(state.get("execution_state") or {})

        if is_cross_project_goal(goal):
            blocked = ExecutionState(
                status="blocked",
                blocked_reason="task_requires_cross_project_coordination",
            )
            return {"execution_state": blocked.model_dump(mode="json")}

        if needs_execution_debate(goal) and not state.get("debate_result"):
            request = {
                "debate_required": True,
                "requested_by": "execution_actor",
                "trigger_kind": ["implementation_route_non_unique"],
                "candidate_positions": ["structured_adapter", "direct_implementation"],
                "resume_target": "execution_resume",
            }
            execution_state.update({"status": "running", "discovered_debate_need": True})
            return {"execution_state": execution_state, "debate_request_state": request}

        test_result = (state.get("test_state") or {}).get("final_test_result") or {}
        rework_applied = bool(execution_state.get("rework_applied"))
        if test_result.get("result") == "failed" and not rework_applied:
            rework_applied = True

        artifact_ref = self._write_artifact(project_root, goal, state, rework_applied)
        completed = ExecutionState(
            status="completed",
            implementation_artifact_ref=artifact_ref,
            discovered_debate_need=False,
            rework_applied=rework_applied,
            adjudication_applied=bool(state.get("debate_result")),
        )
        return {"execution_state": completed.model_dump(mode="json")}

    def _write_artifact(
        self,
        project_root: Path,
        goal: str,
        state: dict[str, Any],
        rework_applied: bool,
    ) -> str:
        request = ToolCallRequest(
            calling_node="execution_dispatch",
            actor_role="execution_actor",
            tool_name="execution.write_artifact",
            declared_intent="write local implementation artifact",
            expected_side_effects=["local_project_state"],
            project_scope=str(project_root),
        )

        def action() -> str:
            artifact_dir = project_root / ".aegis" / "artifacts"
            artifact_dir.mkdir(parents=True, exist_ok=True)
            path = artifact_dir / f"implementation-{uuid4().hex[:8]}.json"
            payload = {
                "goal": goal,
                "execution_model": "single_execution_actor",
                "execution_groups_created": 0,
                "front_back_agents_created": False,
                "debate_result_ref": state.get("debate_result"),
                "rework_applied": rework_applied,
            }
            path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return str(path)

        result = self.governance.execute(request, action)
        if not result.executed:
            raise RuntimeError(result.decision.reason)
        audits = state.setdefault("tool_intent_audits", [])
        audits.append(result.audit)
        return result.result


def execution_dispatch(state: dict[str, Any]) -> dict[str, Any]:
    actor = ExecutionActor()
    return actor.run(state)

