"""Minimal retest selection for Test Subgraph v2."""

from __future__ import annotations

from aegis.modules.test.models import MinimalRetestRequest, TestDependencyGraph


def select_minimal_retest_nodes(
    *,
    request_id: str,
    target_gap_ids: list[str],
    dependency_graph: TestDependencyGraph,
    dependency_graph_ref,
    still_valid_evidence_nodes: set[str] | None = None,
    break_cycles: bool = False,
) -> MinimalRetestRequest:
    """Select the smallest dependency-closed retest node set.

    The selector starts from evidence-gap test ids, adds required preconditions
    and environment setup ancestors, then adds artifact consumers that must be
    refreshed when their producer is rerun.
    """

    still_valid = still_valid_evidence_nodes or set()
    if dependency_graph.cycles_detected and not break_cycles:
        raise ValueError("cycle without break rule blocks minimal retest selection")

    nodes = set(dependency_graph.nodes)
    targets = set(target_gap_ids)
    unknown = sorted(targets - nodes)
    if unknown:
        raise ValueError(f"target gap ids are not in dependency graph: {', '.join(unknown)}")

    reverse_required: dict[str, set[str]] = {node: set() for node in nodes}
    forward_consumers: dict[str, set[str]] = {node: set() for node in nodes}
    for edge in dependency_graph.edges:
        if edge.dependency_type in {"precondition", "environment_setup"}:
            reverse_required.setdefault(edge.to_test_id, set()).add(edge.from_test_id)
        if edge.dependency_type == "artifact_consumer":
            forward_consumers.setdefault(edge.from_test_id, set()).add(edge.to_test_id)

    selected = set(targets)
    stack = list(targets)
    while stack:
        current = stack.pop()
        for parent in reverse_required.get(current, set()):
            if parent in still_valid:
                continue
            if parent not in selected:
                selected.add(parent)
                stack.append(parent)

    stack = list(selected)
    while stack:
        current = stack.pop()
        for consumer in forward_consumers.get(current, set()):
            if consumer not in selected:
                selected.add(consumer)
                stack.append(consumer)

    excluded = sorted(nodes - selected)
    return MinimalRetestRequest(
        request_id=request_id,
        target_gap_ids=target_gap_ids,
        dependency_graph_ref=dependency_graph_ref,
        selected_nodes=sorted(selected),
        excluded_nodes=excluded,
        selection_reasoning=(
            "Selected gap nodes plus required precondition/environment ancestors "
            "and artifact consumers; reused still-valid evidence where provided."
        ),
        cycle_handling="break rule applied" if dependency_graph.cycles_detected else None,
        expected_new_evidence=sorted(selected),
    )
