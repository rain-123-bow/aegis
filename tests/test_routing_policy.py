import pytest

from aegis.graph.routing import FLOW_ROUTING_POLICY, FlowNode


def test_declared_flow_edges_are_allowed():
    allowed_edges: list[tuple[FlowNode, FlowNode]] = [
        ("master", "debate"),
        ("master", "execution"),
        ("debate", "execution"),
        ("execution", "debate"),
        ("execution", "test"),
        ("test", "execution"),
        ("test", "final_review"),
        ("final_review", "master_closeout"),
    ]

    for source, target in allowed_edges:
        assert FLOW_ROUTING_POLICY.is_allowed(source, target)


def test_undeclared_flow_edges_are_rejected():
    invalid_edges: list[tuple[FlowNode, FlowNode]] = [
        ("master", "test"),
        ("debate", "test"),
        ("test", "master"),
        ("final_review", "execution"),
    ]

    for source, target in invalid_edges:
        with pytest.raises(ValueError):
            FLOW_ROUTING_POLICY.require_allowed(source, target)


def test_each_flow_edge_has_runtime_contract_fields():
    for contract in FLOW_ROUTING_POLICY.contracts:
        assert contract.condition
        assert contract.required_state_fields
        assert "global_causal_truth_merge" in contract.forbidden_side_effects
