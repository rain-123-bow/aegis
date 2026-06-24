from __future__ import annotations

from aegis.modules.debate import (
    ConvergenceSignals,
    WorkerProtocolViolation,
    WorkerTurnPacket,
    detect_worker_protocol_violations,
    assess_leader_round,
    build_causal_candidate_nodes,
)


def test_worker_protocol_violation_turn_unusable_for_unsupported_invention() -> None:
    packet = WorkerTurnPacket(
        turn_id="turn-1",
        debate_id="debate-1",
        worker_id="worker-a",
        stance_id="a",
        round_index=1,
        observed_canonical_transcript_ref="transcript/round-1.md",
        defense={
            "claims": ["A hidden project fact proves this"],
            "supporting_knowledge_refs": [],
            "supporting_causal_refs": [],
            "first_principles_claims": [],
            "local_causal_nodes": [],
        },
        self_audit={
            "knowledge_constraints_checked": True,
            "causal_refs_checked": True,
            "unsupported_claims": ["A hidden project fact proves this"],
            "possible_protocol_violations": [],
        },
    )

    violations = detect_worker_protocol_violations(packet)

    assert violations[0].violation_type == "unsupported_invention"
    assert violations[0].action == "mark_turn_unusable"


def test_leader_structural_stop_when_one_undefeated_stance_remains() -> None:
    assessment = assess_leader_round(
        debate_id="debate-1",
        round_index=2,
        active_stances=["a", "b"],
        dominated_stances=["a"],
        violations=[],
        signals=ConvergenceSignals(
            active_stance_count=2,
            undefeated_stance_count=1,
            unresolved_conflict_count=0,
            new_material_argument_count=0,
            decisive_constraint_count=1,
            stable_selected_stance_rounds=2,
        ),
    )

    assert assessment.next_action == "stop_converged"
    assert assessment.stop_reason


def test_leader_requests_repair_for_material_violation() -> None:
    assessment = assess_leader_round(
        debate_id="debate-1",
        round_index=1,
        active_stances=["a", "b"],
        dominated_stances=[],
        violations=[
            WorkerProtocolViolation(
                worker_id="worker-a",
                turn_id="turn-1",
                violation_type="premature_concession",
                severity="material",
                action="request_worker_repair",
                reason="concession has no defeating ref",
            )
        ],
        signals=ConvergenceSignals(
            active_stance_count=2,
            undefeated_stance_count=2,
            unresolved_conflict_count=1,
            new_material_argument_count=1,
            worker_protocol_violation_count=1,
        ),
    )

    assert assessment.next_action == "request_worker_repair"


def test_causal_candidate_maps_dependency_groups_and_excludes_unusable_turns() -> None:
    usable = WorkerTurnPacket(
        turn_id="turn-good",
        debate_id="debate-1",
        worker_id="worker-b",
        stance_id="b",
        round_index=1,
        observed_canonical_transcript_ref="transcript/round-1.md",
        chain_delta={
            "added_local_nodes": [
                {
                    "local_node_ref": "n-b",
                    "minimal_semantic_content": "Adapter route improves extension boundary",
                    "semantic_summary": "Adapter extension boundary",
                    "semantic_keys": ["adapter", "extension"],
                    "knowledge_refs": ["k-adapter"],
                    "evidence_refs": ["artifact/adapter"],
                    "assumptions": ["single local project"],
                    "scope": "local project",
                    "confidence": "medium",
                    "invalidation_conditions": ["adapter overhead dominates"],
                }
            ],
            "added_edges": [],
            "invalidated_local_nodes": [],
        },
    )
    unusable = WorkerTurnPacket(
        turn_id="turn-bad",
        debate_id="debate-1",
        worker_id="worker-a",
        stance_id="a",
        round_index=1,
        observed_canonical_transcript_ref="transcript/round-1.md",
        self_audit={
            "knowledge_constraints_checked": True,
            "causal_refs_checked": True,
            "unsupported_claims": ["invented"],
            "possible_protocol_violations": [],
        },
    )

    nodes = build_causal_candidate_nodes(
        debate_id="debate-1",
        packets=[usable, unusable],
        violations=detect_worker_protocol_violations(unusable),
    )

    assert [node.local_node_ref for node in nodes] == ["n-b"]
    assert nodes[0].dependency_groups[0].knowledge_refs == ["k-adapter"]
