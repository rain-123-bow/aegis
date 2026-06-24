"""Merge worker causal-chain deltas into causal candidate nodes."""

from __future__ import annotations

from aegis.modules.debate.models import (
    CausalCandidateDependencyGroup,
    CausalCandidateNode,
    WorkerProtocolViolation,
    WorkerTurnPacket,
)


def build_causal_candidate_nodes(
    *,
    debate_id: str,
    packets: list[WorkerTurnPacket],
    violations: list[WorkerProtocolViolation],
) -> list[CausalCandidateNode]:
    """Build causal candidate nodes from usable worker chain deltas."""

    _ = debate_id
    unusable_turn_ids = {
        violation.turn_id
        for violation in violations
        if violation.required_action in {"mark_turn_unusable", "abort_debate"}
    }
    nodes_by_ref: dict[str, CausalCandidateNode] = {}
    for packet in packets:
        if packet.turn_id in unusable_turn_ids:
            continue
        for index, raw_node in enumerate(packet.chain_delta.added_local_nodes):
            statement = str(
                raw_node.get("statement")
                or raw_node.get("minimal_semantic_content")
                or packet.defense
            )
            semantic_summary = str(raw_node.get("semantic_summary") or statement)
            scope = str(raw_node.get("scope") or "current debate decision")
            confidence = raw_node.get("confidence") or "medium"
            if confidence not in {"high", "medium", "low"}:
                confidence = "medium"
            group = CausalCandidateDependencyGroup(
                group_id=f"{packet.turn_id}-dep-{index}",
                causal_dependencies=[
                    str(value)
                    for value in raw_node.get("causal_dependencies", [])
                ],
                knowledge_refs=[
                    str(value) for value in raw_node.get("knowledge_refs", [])
                ],
                evidence_refs=[
                    str(value)
                    for value in raw_node.get("evidence_refs", packet.evidence_refs)
                ],
                conditions=[
                    str(value) for value in raw_node.get("conditions", [])
                ],
                assumptions=[
                    str(value) for value in raw_node.get("assumptions", [])
                ],
                scope=scope,
                confidence=confidence,  # type: ignore[arg-type]
                invalidation_conditions=[
                    str(value)
                    for value in raw_node.get("invalidation_conditions", [])
                ],
            )
            local_ref = str(
                raw_node.get("local_node_ref")
                or f"{packet.turn_id}-node-{index}"
            )
            nodes_by_ref[local_ref] = CausalCandidateNode(
                local_node_ref=local_ref,
                statement=statement,
                semantic_summary=semantic_summary,
                semantic_keys=[
                    str(value) for value in raw_node.get("semantic_keys", [])
                ],
                source_worker_id=packet.worker_id,
                source_stance_id=packet.stance_id,
                dependency_groups=[group],
            )
    return list(nodes_by_ref.values())
