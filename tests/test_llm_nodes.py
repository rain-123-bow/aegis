from aegis.llm import (
    DeterministicLlmNodeAdapter,
    LlmNodeRequest,
    LlmNodeResult,
    LlmNodeRunner,
)
from aegis.tools import ToolCallRequest


def test_deterministic_llm_adapter_returns_schema_valid_self_audited_result():
    request = LlmNodeRequest(
        role="debate_leader",
        task="select a causal candidate",
        state_refs=["debate_request_state"],
        allowed_tools=["debate.emit_causal_package"],
        forbidden_actions=["global_causal_truth_merge"],
        output_schema={"type": "object", "required": ["decision"]},
        evidence_requirements=["why", "scope"],
    )

    result = LlmNodeRunner(DeterministicLlmNodeAdapter()).run(request)

    assert result.schema_valid is True
    assert result.self_audit["adapter"] == "deterministic"
    assert result.self_audit["real_llm_called"] is False
    assert result.self_audit["forbidden_actions_respected"] is True
    assert result.evidence_refs == ["why", "scope"]


def test_llm_node_runner_blocks_tool_requests_that_bypass_governance():
    class UnsafeAdapter:
        def invoke(self, request: LlmNodeRequest) -> LlmNodeResult:
            return LlmNodeResult(
                decision="try_forbidden_tool",
                state_patch={},
                tool_requests=[
                    ToolCallRequest(
                        calling_node="final_review",
                        actor_role="final_review_leader",
                        tool_name="test.run_route",
                        declared_intent="run tests from final review",
                        project_scope="demo",
                    )
                ],
                evidence_refs=[],
                self_audit={"adapter": "unsafe"},
                schema_valid=True,
            )

    request = LlmNodeRequest(
        role="final_review_leader",
        task="review final evidence",
        state_refs=["final_review_result"],
        allowed_tools=["final_review.emit_recommendation"],
        forbidden_actions=["run_tests", "modify_code"],
        output_schema={"type": "object"},
        evidence_requirements=[],
    )

    result = LlmNodeRunner(UnsafeAdapter()).run(request)

    assert result.schema_valid is False
    assert result.blocked_reason
    assert "not allowed" in result.blocked_reason


def test_llm_node_runner_blocks_schema_invalid_output():
    class MissingRequiredFieldAdapter:
        def invoke(self, request: LlmNodeRequest) -> LlmNodeResult:
            return LlmNodeResult(
                decision="incomplete",
                state_patch={},
                evidence_refs=[],
                self_audit={"adapter": "missing_required"},
                schema_valid=True,
            )

    request = LlmNodeRequest(
        role="execution_actor",
        task="produce implementation route",
        output_schema={"type": "object", "required": ["implementation_plan"]},
    )

    result = LlmNodeRunner(MissingRequiredFieldAdapter()).run(request)

    assert result.schema_valid is False
    assert result.blocked_reason == "LLM node output missing required field: implementation_plan"
