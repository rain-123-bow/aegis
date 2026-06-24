"""Debate leader adjudication."""

from __future__ import annotations

from aegis.modules.debate.models import (
    ConvergenceSignals,
    HardConstraintValidation,
    LeaderDecision,
    LeaderRoundAssessment,
    StanceAdmissionRecord,
    WorkerProtocolViolation,
    WorkerTurnPacket,
)


def assess_leader_round(
    *,
    round_index: int,
    active_stance_ids: list[str] | None = None,
    active_stances: list[str] | None = None,
    dominated_stances: list[str] | None = None,
    violations: list[WorkerProtocolViolation],
    signals: ConvergenceSignals,
    debate_id: str | None = None,
) -> LeaderRoundAssessment:
    """Assess whether the debate should continue, repair, or close."""

    _ = debate_id
    active_stance_ids = active_stance_ids or active_stances or []
    dominated_stances = dominated_stances or []
    fatal_turns = [
        violation.turn_id
        for violation in violations
        if violation.required_action in {"mark_turn_unusable", "abort_debate"}
    ]
    repair_turns = [
        violation.turn_id
        for violation in violations
        if violation.required_action == "request_repair"
    ]
    if fatal_turns:
        return LeaderRoundAssessment(
            round_index=round_index,
            decision=LeaderDecision.ABORT_PROTOCOL_VIOLATION,
            reason="Fatal worker protocol violations make the round unusable.",
            required_repairs=fatal_turns,
        )
    if repair_turns:
        return LeaderRoundAssessment(
            round_index=round_index,
            decision=LeaderDecision.REQUEST_WORKER_REPAIR,
            reason="Material worker protocol violations require repair.",
            required_repairs=repair_turns,
        )
    if signals.unresolved_blocking_missing_need_count > 0:
        return LeaderRoundAssessment(
            round_index=round_index,
            decision=LeaderDecision.STOP_NEED_CONTEXT,
            reason="Debate cannot close because blocking evidence is missing.",
        )
    if signals.undefeated_stance_count <= 1 and active_stance_ids:
        selected_candidates = [
            stance_id
            for stance_id in active_stance_ids
            if stance_id not in dominated_stances
        ]
        selected = selected_candidates[0] if selected_candidates else active_stance_ids[0]
        return LeaderRoundAssessment(
            round_index=round_index,
            decision=LeaderDecision.STOP_CONVERGED,
            reason="Only one stance remains undefeated.",
            selected_stance_id=selected,
            rejected_stance_ids=[
                stance_id for stance_id in active_stance_ids if stance_id != selected
            ],
        )
    if (
        signals.unresolved_conflict_count == 0
        and signals.new_material_argument_count == 0
        and active_stance_ids
    ):
        selected = active_stance_ids[0]
        return LeaderRoundAssessment(
            round_index=round_index,
            decision=LeaderDecision.STOP_CONVERGED,
            reason="No unresolved conflict or new material argument remains.",
            selected_stance_id=selected,
            rejected_stance_ids=[
                stance_id for stance_id in active_stance_ids if stance_id != selected
            ],
        )
    return LeaderRoundAssessment(
        round_index=round_index,
        decision=LeaderDecision.CONTINUE_DEBATE,
        reason="More adversarial pressure is required before adjudication.",
    )


def select_leader_candidate_stance(
    *,
    active_stance_ids: list[str],
    packets: list[WorkerTurnPacket],
    admission_records: list[StanceAdmissionRecord],
    hard_constraint_validations: list[HardConstraintValidation],
) -> str | None:
    """Rank stances from the actual round packets and admitted evidence.

    This function is deliberately part of the Leader module: graph orchestration
    may ask the Leader for an adjudication candidate, but it must not choose the
    winner itself.
    """

    if not active_stance_ids:
        return None
    score = {stance_id: 0 for stance_id in active_stance_ids}
    admission_refs = {
        record.stance_id: set(record.supporting_refs)
        for record in admission_records
    }
    verified_refs = {
        ref
        for validation in hard_constraint_validations
        if validation.status.value == "verified"
        for ref in validation.evidence_refs
    }
    for stance_id in active_stance_ids:
        score[stance_id] += len(admission_refs.get(stance_id, set())) * 5
    for packet in packets:
        if packet.stance_id not in score:
            continue
        evidence_refs = set(packet.evidence_refs)
        score[packet.stance_id] += len(evidence_refs) * 10
        score[packet.stance_id] += len(packet.chain_delta.added_local_nodes) * 4
        score[packet.stance_id] += sum(
            3 for attack in packet.attacks if attack.evidence_refs
        )
        score[packet.stance_id] -= len(packet.concessions) * 8
        if evidence_refs & verified_refs:
            score[packet.stance_id] += 20
        for attack in packet.attacks:
            target = attack.target_ref
            if target in score and attack.evidence_refs:
                score[target] -= 3

    ordered = sorted(
        active_stance_ids,
        key=lambda stance_id: (
            score[stance_id],
            len(admission_refs.get(stance_id, set())),
            stance_id,
        ),
        reverse=True,
    )
    if not ordered:
        return None
    return ordered[0]
