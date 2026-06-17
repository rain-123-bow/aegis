from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import Field

from aegis.models import StrictModel
from aegis.tools import ToolCallRequest, ToolGovernance


LlmRole = Literal[
    "master",
    "debate_leader",
    "execution_actor",
    "test_leader",
    "final_review_leader",
]


class LlmNodeRequest(StrictModel):
    role: LlmRole
    task: str
    state_refs: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    evidence_requirements: list[str] = Field(default_factory=list)


class LlmNodeResult(StrictModel):
    decision: str
    state_patch: dict[str, Any] = Field(default_factory=dict)
    tool_requests: list[ToolCallRequest] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    self_audit: dict[str, Any] = Field(default_factory=dict)
    schema_valid: bool
    blocked_reason: str | None = None


class LlmNodeAdapter(Protocol):
    def invoke(self, request: LlmNodeRequest) -> LlmNodeResult:
        ...


class DeterministicLlmNodeAdapter:
    """CI-safe adapter that proves the LLM node contract without real LLM calls."""

    def invoke(self, request: LlmNodeRequest) -> LlmNodeResult:
        return LlmNodeResult(
            decision=f"{request.role}_deterministic_decision",
            state_patch={
                "llm_node": {
                    "role": request.role,
                    "task": request.task,
                    "state_refs": request.state_refs,
                }
            },
            tool_requests=[],
            evidence_refs=list(request.evidence_requirements),
            self_audit={
                "adapter": "deterministic",
                "real_llm_called": False,
                "forbidden_actions_respected": True,
                "allowed_tools": request.allowed_tools,
            },
            schema_valid=True,
        )


class RealLlmNodeAdapter:
    """Placeholder adapter. Real LLM execution must be enabled explicitly later."""

    def invoke(self, request: LlmNodeRequest) -> LlmNodeResult:
        raise NotImplementedError("real LLM node adapter is intentionally not enabled by default")


class LlmNodeRunner:
    def __init__(
        self,
        adapter: LlmNodeAdapter | None = None,
        governance: ToolGovernance | None = None,
    ):
        self.adapter = adapter or DeterministicLlmNodeAdapter()
        self.governance = governance or ToolGovernance()

    def run(self, request: LlmNodeRequest) -> LlmNodeResult:
        result = self.adapter.invoke(request)
        audits: list[dict[str, Any]] = []

        schema_error = self._schema_error(request, result)
        if schema_error:
            return self._blocked(result, schema_error, audits)

        for tool_request in result.tool_requests:
            if tool_request.tool_name not in request.allowed_tools:
                return self._blocked(
                    result,
                    f"{tool_request.tool_name} is not allowed by the LLM node allowed tool list",
                    audits,
                )
            decision = self.governance.assess(tool_request)
            audits.append(
                {
                    "tool_name": tool_request.tool_name,
                    "decision": decision.decision,
                    "reason": decision.reason,
                }
            )
            if decision.decision != "allow":
                return self._blocked(result, decision.reason, audits)

        result.self_audit = {**result.self_audit, "tool_governance_audits": audits}
        return result

    @staticmethod
    def _schema_error(request: LlmNodeRequest, result: LlmNodeResult) -> str | None:
        if not result.schema_valid:
            return result.blocked_reason or "LLM node output marked schema invalid"
        required = request.output_schema.get("required", [])
        if not isinstance(required, list):
            return "LLM node output schema has invalid required field declaration"
        output = result.model_dump(mode="json")
        state_patch = result.state_patch
        for field in required:
            if not isinstance(field, str):
                return "LLM node output schema required field is not a string"
            if field not in output and field not in state_patch:
                return f"LLM node output missing required field: {field}"
        return None

    @staticmethod
    def _blocked(result: LlmNodeResult, reason: str, audits: list[dict[str, Any]]) -> LlmNodeResult:
        return result.model_copy(
            update={
                "schema_valid": False,
                "blocked_reason": reason,
                "self_audit": {**result.self_audit, "tool_governance_audits": audits},
            }
        )
