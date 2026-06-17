from __future__ import annotations

from typing import Any

from aegis.models import FinalReviewResult


def final_review_node(state: dict[str, Any]) -> dict[str, Any]:
    execution_state = state.get("execution_state") or {}
    test_result = ((state.get("test_state") or {}).get("final_test_result") or {}).get("result")
    blockers = list(state.get("blockers") or [])
    known_limits: list[str] = []
    missing_evidence: list[str] = []

    if execution_state.get("status") == "blocked":
        decision = "governance_blocker"
        known_limits.append(execution_state.get("blocked_reason") or "execution blocked")
    elif test_result in {"passed", "passed_with_scope_limit"}:
        decision = "accept_for_master"
    elif test_result in {"failed", "blocked", "inconclusive"}:
        decision = "reject_to_execution"
        missing_evidence.append("test did not produce passing result")
    else:
        decision = "request_more_evidence"
        missing_evidence.append("missing final test result")

    if blockers:
        decision = "governance_blocker"
        known_limits.extend(blockers)

    result = FinalReviewResult(
        decision=decision,
        why="single Final Review node reviewed execution artifact, test result, and governance blockers",
        whole_chain_review={
            "execution_status": execution_state.get("status"),
            "test_result": test_result,
            "debate_used": bool(state.get("debate_result")),
        },
        known_limits=known_limits,
        missing_evidence=missing_evidence,
    )
    return {"final_review_result": result.model_dump(mode="json")}

