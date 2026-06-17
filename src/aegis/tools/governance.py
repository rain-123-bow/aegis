from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field

from aegis.models import StrictModel


RiskLevel = Literal["none", "low", "medium", "high", "critical"]
ToolDecisionValue = Literal["allow", "deny", "interrupt"]


class ToolCallRequest(StrictModel):
    request_id: str = Field(default_factory=lambda: f"tool-{uuid4().hex[:10]}")
    calling_node: str
    actor_role: Literal[
        "master",
        "execution_actor",
        "test_leader",
        "test_worker",
        "final_review_leader",
        "debate_leader",
        "debate_worker",
    ]
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    declared_intent: str
    expected_side_effects: list[str] = Field(default_factory=list)
    project_scope: str
    artifact_refs: list[str] = Field(default_factory=list)


class ToolIntentAssessment(StrictModel):
    inferred_intent: str
    intent_match: bool | Literal["uncertain"]
    risk_level: RiskLevel
    risk_kinds: list[str] = Field(default_factory=list)
    developer_decision_required: bool = False
    recommended_decision: Literal["allow", "deny", "modify_scope", "request_more_context"]


class ToolDecision(StrictModel):
    decision: ToolDecisionValue
    reason: str
    assessment: ToolIntentAssessment


class ToolExecutionResult(StrictModel):
    request: ToolCallRequest
    decision: ToolDecision
    executed: bool = False
    result: Any = None
    audit: dict[str, Any] = Field(default_factory=dict)


class ToolGovernance:
    """Conservative pre-action gate for runtime tool calls."""

    forbidden_external_tools = {
        "git.push",
        "git.merge",
        "github.create_pr",
        "release.perform",
        "deploy.perform",
    }
    side_effect_interrupt_markers = {
        "irreversible",
        "external",
        "remote",
        "release",
        "deployment",
        "hidden_project_state_mutation",
        "responsibility_transfer",
    }

    role_tool_allowlist = {
        "master": {
            "stores.ensure_layout",
            "stores.write_candidate",
            "checkpoint.inspect",
            "git.push",
            "github.create_pr",
            "release.perform",
            "deploy.perform",
        },
        "execution_actor": {
            "execution.write_artifact",
            "debate.request",
            "stores.write_candidate",
        },
        "test_leader": {
            "test.run_route",
            "test.write_evidence",
            "stores.write_candidate",
        },
        "final_review_leader": {
            "final_review.emit_recommendation",
        },
        "debate_leader": {
            "debate.emit_causal_package",
        },
        "debate_worker": set(),
        "test_worker": {
            "test.run_route",
            "test.write_evidence",
        },
    }

    def assess(self, request: ToolCallRequest) -> ToolDecision:
        if request.tool_name not in self.role_tool_allowlist.get(request.actor_role, set()):
            assessment = ToolIntentAssessment(
                inferred_intent=request.declared_intent or "unknown",
                intent_match=False,
                risk_level="high",
                risk_kinds=["capability_violation"],
                developer_decision_required=False,
                recommended_decision="deny",
            )
            return ToolDecision(
                decision="deny",
                reason=f"{request.actor_role} is not allowed to call {request.tool_name}",
                assessment=assessment,
            )

        intent_text = request.declared_intent.strip().lower()
        if not intent_text or "unknown" in intent_text or "uncertain" in intent_text:
            assessment = ToolIntentAssessment(
                inferred_intent=intent_text or "unknown",
                intent_match="uncertain",
                risk_level="medium",
                risk_kinds=["uncertain_intent"],
                developer_decision_required=True,
                recommended_decision="request_more_context",
            )
            return ToolDecision(
                decision="interrupt",
                reason="tool intent is uncertain",
                assessment=assessment,
            )

        side_effects = {item.lower() for item in request.expected_side_effects}
        if request.tool_name in self.forbidden_external_tools:
            assessment = ToolIntentAssessment(
                inferred_intent=intent_text,
                intent_match=True,
                risk_level="critical",
                risk_kinds=["unauthorized_external_side_effect"],
                developer_decision_required=True,
                recommended_decision="deny",
            )
            return ToolDecision(
                decision="interrupt",
                reason="external responsibility action requires developer authorization",
                assessment=assessment,
            )

        if side_effects & self.side_effect_interrupt_markers:
            assessment = ToolIntentAssessment(
                inferred_intent=intent_text,
                intent_match=True,
                risk_level="high",
                risk_kinds=sorted(side_effects & self.side_effect_interrupt_markers),
                developer_decision_required=True,
                recommended_decision="request_more_context",
            )
            return ToolDecision(
                decision="interrupt",
                reason="side effect requires developer review",
                assessment=assessment,
            )

        assessment = ToolIntentAssessment(
            inferred_intent=intent_text,
            intent_match=True,
            risk_level="low" if request.expected_side_effects else "none",
            risk_kinds=[],
            developer_decision_required=False,
            recommended_decision="allow",
        )
        return ToolDecision(decision="allow", reason="allowed by tool governance", assessment=assessment)

    def execute(self, request: ToolCallRequest, action: Callable[[], Any]) -> ToolExecutionResult:
        decision = self.assess(request)
        if decision.decision != "allow":
            return ToolExecutionResult(request=request, decision=decision, executed=False)
        result = action()
        return ToolExecutionResult(
            request=request,
            decision=decision,
            executed=True,
            result=result,
            audit={
                "tool_name": request.tool_name,
                "calling_node": request.calling_node,
                "actor_role": request.actor_role,
                "decision": decision.decision,
            },
        )

