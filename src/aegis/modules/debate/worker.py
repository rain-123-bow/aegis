"""Debate worker protocol validation."""

from __future__ import annotations

from aegis.modules.debate.models import (
    WorkerProtocolViolation,
    WorkerTurnPacket,
    WorkerViolationSeverity,
)


def detect_worker_protocol_violations(
    packet: WorkerTurnPacket,
) -> list[WorkerProtocolViolation]:
    """Detect worker behavior that cannot enter causal-chain merge."""

    violations: list[WorkerProtocolViolation] = []
    if packet.self_audit.unsupported_claims:
        violations.append(
            WorkerProtocolViolation(
                turn_id=packet.turn_id,
                worker_id=packet.worker_id,
                violation_type="unsupported_invention",
                severity=WorkerViolationSeverity.FATAL,
                reason=(
                    "Worker reported unsupported claims; the turn cannot be "
                    "used as causal evidence."
                ),
                required_action="mark_turn_unusable",
            )
        )
    if packet.self_audit.truth_status_claimed == "global_truth":
        violations.append(
            WorkerProtocolViolation(
                turn_id=packet.turn_id,
                worker_id=packet.worker_id,
                violation_type="global_truth_confusion",
                severity=WorkerViolationSeverity.FATAL,
                reason="Debate workers cannot claim global causal truth.",
                required_action="mark_turn_unusable",
            )
        )
    for concession in packet.concessions:
        if not concession.defeating_ref or not concession.why_conceded.strip():
            violations.append(
                WorkerProtocolViolation(
                    turn_id=packet.turn_id,
                    worker_id=packet.worker_id,
                    violation_type="premature_concession",
                    severity=WorkerViolationSeverity.MATERIAL,
                    reason=(
                        "A concession must cite the defeating argument or "
                        "evidence that genuinely changed the worker position."
                    ),
                    required_action="request_repair",
                )
            )
    return violations
