from aegis.tools import ToolCallRequest, ToolGovernance


def test_safe_tool_call_is_allowed(tmp_path):
    request = ToolCallRequest(
        calling_node="project_closeout",
        actor_role="master",
        tool_name="stores.write_candidate",
        declared_intent="write candidate to local project store",
        expected_side_effects=["local_project_state"],
        project_scope=str(tmp_path),
    )

    decision = ToolGovernance().assess(request)

    assert decision.decision == "allow"


def test_uncertain_intent_interrupts(tmp_path):
    request = ToolCallRequest(
        calling_node="x",
        actor_role="master",
        tool_name="stores.write_candidate",
        declared_intent="unknown",
        project_scope=str(tmp_path),
    )

    decision = ToolGovernance().assess(request)

    assert decision.decision == "interrupt"
    assert decision.assessment.developer_decision_required is True


def test_forbidden_capability_is_denied(tmp_path):
    request = ToolCallRequest(
        calling_node="x",
        actor_role="final_review_leader",
        tool_name="test.run_route",
        declared_intent="run tests",
        project_scope=str(tmp_path),
    )

    decision = ToolGovernance().assess(request)

    assert decision.decision == "deny"


def test_external_responsibility_action_interrupts(tmp_path):
    request = ToolCallRequest(
        calling_node="route_expand_planning",
        actor_role="master",
        tool_name="git.push",
        declared_intent="request external responsibility action",
        expected_side_effects=["remote", "irreversible"],
        project_scope=str(tmp_path),
    )

    decision = ToolGovernance().assess(request)

    assert decision.decision == "interrupt"
