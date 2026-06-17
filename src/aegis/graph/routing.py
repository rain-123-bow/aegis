from __future__ import annotations

from typing import Literal

from pydantic import Field

from aegis.models import StrictModel


FlowNode = Literal["master", "debate", "execution", "test", "final_review", "master_closeout"]


class FlowEdgeContract(StrictModel):
    source: FlowNode
    target: FlowNode
    condition: str
    required_state_fields: list[str] = Field(default_factory=list)
    forbidden_side_effects: list[str] = Field(
        default_factory=lambda: [
            "archive_truth_mutation",
            "knowledge_truth_mutation",
            "global_causal_truth_merge",
            "remote_push",
            "pr_create",
            "release",
        ]
    )


class FlowRoutingPolicy:
    def __init__(self, contracts: list[FlowEdgeContract]):
        self.contracts = tuple(contracts)
        self._edges = {(contract.source, contract.target): contract for contract in self.contracts}

    def is_allowed(self, source: FlowNode, target: FlowNode) -> bool:
        return (source, target) in self._edges

    def require_allowed(self, source: FlowNode, target: FlowNode) -> FlowEdgeContract:
        contract = self._edges.get((source, target))
        if contract is None:
            raise ValueError(f"flow edge {source} -> {target} is not declared")
        return contract


FLOW_ROUTING_POLICY = FlowRoutingPolicy(
    [
        FlowEdgeContract(
            source="master",
            target="debate",
            condition="Master identifies multiple defensible stances before execution.",
            required_state_fields=["debate_request_state"],
        ),
        FlowEdgeContract(
            source="master",
            target="execution",
            condition="Master admits a single-project executable task without required Debate.",
            required_state_fields=["task_boundary", "route_expand_plan"],
        ),
        FlowEdgeContract(
            source="debate",
            target="execution",
            condition="Debate returns a causal_candidate adjudication package to the requester.",
            required_state_fields=["debate_result"],
        ),
        FlowEdgeContract(
            source="execution",
            target="debate",
            condition="Execution discovers multiple non-dominated valid implementation routes.",
            required_state_fields=["execution_state", "debate_request_state"],
        ),
        FlowEdgeContract(
            source="execution",
            target="test",
            condition="Execution produces an implementation artifact or rework artifact.",
            required_state_fields=["execution_state"],
        ),
        FlowEdgeContract(
            source="test",
            target="execution",
            condition="Test result fails or is inconclusive and rework has not yet been applied.",
            required_state_fields=["test_state", "execution_state"],
        ),
        FlowEdgeContract(
            source="test",
            target="final_review",
            condition="Test reaches a terminal route result for final evidence review.",
            required_state_fields=["test_state"],
        ),
        FlowEdgeContract(
            source="final_review",
            target="master_closeout",
            condition="Final Review emits a recommendation for Master closeout.",
            required_state_fields=["final_review_result"],
        ),
    ]
)
