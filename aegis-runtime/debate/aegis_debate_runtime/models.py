from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

DecisionLabel = Literal[
    "accept_one",
    "accept_multiple_by_scope",
    "need_more_evidence",
    "reject_debate_no_valid_position",
    "stop_and_escalate_to_master",
    "stop_and_request_test",
    "rejected_no_debate_needed",
]

AdmissionDecisionLabel = Literal[
    "request_more_context",
    "rejected_no_debate_needed",
]

TurnType = Literal[
    "defend",
    "attack",
    "answer",
    "scope_narrowing",
    "concession",
    "evidence_request",
]


class DebateContractError(ValueError):
    """Base error for Debate Department runtime contract violations."""


class DebateProtocolError(DebateContractError):
    """Raised when a worker or topology violates the Debate Department protocol."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise DebateContractError(f"{field_name} must be a list of non-empty strings")
    return list(value)


@dataclass(frozen=True)
class EvidenceRef:
    type: str
    ref: str
    relevance: str = ""

    @classmethod
    def from_any(cls, value: Any) -> "EvidenceRef":
        if isinstance(value, str):
            return cls(type="reference", ref=value, relevance="provided by request")
        if isinstance(value, dict):
            evidence_type = value.get("type", "reference")
            ref = value.get("ref")
            relevance = value.get("relevance", "")
            if not isinstance(evidence_type, str) or not evidence_type:
                raise DebateContractError("evidence.type must be a non-empty string")
            if not isinstance(ref, str) or not ref:
                raise DebateContractError("evidence.ref must be a non-empty string")
            if not isinstance(relevance, str):
                raise DebateContractError("evidence.relevance must be a string")
            return cls(type=evidence_type, ref=ref, relevance=relevance)
        raise DebateContractError("evidence entries must be strings or objects")

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "ref": self.ref, "relevance": self.relevance}


@dataclass(frozen=True)
class StancePacket:
    stance_id: str
    claim: str
    why: str
    scope: str
    assumptions: list[str]
    evidence: list[EvidenceRef]
    action_impact: str
    risk_if_wrong: str = ""
    material_conditions: list[str] = field(default_factory=list)
    invalidation_conditions: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any], index: int) -> "StancePacket":
        if not isinstance(value, dict):
            raise DebateContractError("stance must be an object")
        stance_id = value.get("stance_id") or f"S{index + 1}"
        claim = value.get("claim")
        why = value.get("why")
        scope = value.get("scope")
        action_impact = value.get("action_impact")
        risk_if_wrong = value.get("risk_if_wrong", "")
        for field_name, field_value in {
            "stance_id": stance_id,
            "claim": claim,
            "why": why,
            "scope": scope,
            "action_impact": action_impact,
        }.items():
            if not isinstance(field_value, str) or not field_value:
                raise DebateContractError(f"stance.{field_name} must be a non-empty string")
        if not isinstance(risk_if_wrong, str):
            raise DebateContractError("stance.risk_if_wrong must be a string")
        evidence = [EvidenceRef.from_any(item) for item in value.get("evidence", [])]
        assumptions = _ensure_string_list(value.get("assumptions", []), "stance.assumptions")
        material_conditions = _ensure_string_list(value.get("material_conditions", []), "stance.material_conditions")
        invalidation_conditions = _ensure_string_list(
            value.get("invalidation_conditions", []), "stance.invalidation_conditions"
        )
        return cls(
            stance_id=stance_id,
            claim=claim,
            why=why,
            scope=scope,
            assumptions=assumptions,
            evidence=evidence,
            action_impact=action_impact,
            risk_if_wrong=risk_if_wrong,
            material_conditions=material_conditions,
            invalidation_conditions=invalidation_conditions,
        )

    def is_defensible(self) -> bool:
        return bool(
            self.claim
            and self.why
            and self.scope
            and self.action_impact
            and (self.assumptions or self.evidence or self.material_conditions)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "stance_id": self.stance_id,
            "claim": self.claim,
            "why": self.why,
            "scope": self.scope,
            "assumptions": list(self.assumptions),
            "evidence": [item.to_dict() for item in self.evidence],
            "action_impact": self.action_impact,
            "risk_if_wrong": self.risk_if_wrong,
            "material_conditions": list(self.material_conditions),
            "invalidation_conditions": list(self.invalidation_conditions),
        }


@dataclass(frozen=True)
class DebateRequest:
    request_id: str
    sender: str
    decision_target: str
    question: str
    scope: str
    constraints: list[str]
    evidence: list[EvidenceRef]
    candidate_stances: list[StancePacket]
    max_rounds: int = 2
    no_new_information_round_limit: int = 1
    requires_measurement: bool = False
    required_measurements: list[str] = field(default_factory=list)
    governance_impact: bool = False
    allow_scoped_outcome: bool = False
    material_conditions: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DebateRequest":
        if not isinstance(value, dict):
            raise DebateContractError("debate request must be an object")
        request_id = value.get("request_id") or f"debate-run-{uuid4().hex}"
        sender = value.get("sender", "unknown")
        decision_target = value.get("decision_target", "")
        question = value.get("question", "")
        scope = value.get("scope", "")
        for field_name, field_value in {
            "request_id": request_id,
            "sender": sender,
            "question": question,
        }.items():
            if not isinstance(field_value, str) or not field_value:
                raise DebateContractError(f"request.{field_name} must be a non-empty string")
        if not isinstance(decision_target, str):
            raise DebateContractError("request.decision_target must be a string")
        if not isinstance(scope, str):
            raise DebateContractError("request.scope must be a string")
        max_rounds = int(value.get("max_rounds", 2))
        no_new_limit = int(value.get("no_new_information_round_limit", 1))
        if max_rounds < 1:
            raise DebateContractError("request.max_rounds must be >= 1")
        if no_new_limit < 1:
            raise DebateContractError("request.no_new_information_round_limit must be >= 1")
        candidate_stances = [
            StancePacket.from_dict(item, idx) for idx, item in enumerate(value.get("candidate_stances", []))
        ]
        return cls(
            request_id=request_id,
            sender=sender,
            decision_target=decision_target,
            question=question,
            scope=scope,
            constraints=_ensure_string_list(value.get("constraints", []), "request.constraints"),
            evidence=[EvidenceRef.from_any(item) for item in value.get("evidence", [])],
            candidate_stances=candidate_stances,
            max_rounds=max_rounds,
            no_new_information_round_limit=no_new_limit,
            requires_measurement=bool(value.get("requires_measurement", False)),
            required_measurements=_ensure_string_list(
                value.get("required_measurements", []), "request.required_measurements"
            ),
            governance_impact=bool(value.get("governance_impact", False)),
            allow_scoped_outcome=bool(value.get("allow_scoped_outcome", False)),
            material_conditions=_ensure_string_list(
                value.get("material_conditions", []), "request.material_conditions"
            ),
        )

    def has_admission_context(self) -> bool:
        return bool(self.decision_target and self.scope)

    def valid_stances(self) -> list[StancePacket]:
        seen: set[str] = set()
        result: list[StancePacket] = []
        for stance in self.candidate_stances:
            if stance.stance_id in seen:
                raise DebateContractError(f"duplicate stance_id: {stance.stance_id}")
            seen.add(stance.stance_id)
            if stance.is_defensible():
                result.append(stance)
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "sender": self.sender,
            "decision_target": self.decision_target,
            "question": self.question,
            "scope": self.scope,
            "constraints": list(self.constraints),
            "evidence": [item.to_dict() for item in self.evidence],
            "candidate_stances": [stance.to_dict() for stance in self.candidate_stances],
            "max_rounds": self.max_rounds,
            "no_new_information_round_limit": self.no_new_information_round_limit,
            "requires_measurement": self.requires_measurement,
            "required_measurements": list(self.required_measurements),
            "governance_impact": self.governance_impact,
            "allow_scoped_outcome": self.allow_scoped_outcome,
            "material_conditions": list(self.material_conditions),
        }


@dataclass(frozen=True)
class WorkerRecord:
    worker_id: str
    stance_id: str
    status: Literal["active", "released"]

    def to_dict(self) -> dict[str, Any]:
        return {"worker_id": self.worker_id, "stance_id": self.stance_id, "status": self.status}


@dataclass(frozen=True)
class WorkerTurn:
    run_id: str
    round_index: int
    turn_index: int
    worker_id: str
    stance_id: str
    turn_type: TurnType
    claim: str
    why: str
    evidence: list[EvidenceRef]
    assumptions: list[str]
    targets_attacked: list[dict[str, str]]
    weakness_found: str
    confidence: Literal["high", "medium", "low"]
    new_information: bool
    transcript_seen_turn_ids: list[str]
    created_at: str = field(default_factory=utc_now)

    @property
    def turn_id(self) -> str:
        return f"{self.run_id}:r{self.round_index}:t{self.turn_index}:{self.worker_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "run_id": self.run_id,
            "round_index": self.round_index,
            "turn_index": self.turn_index,
            "worker_id": self.worker_id,
            "stance_id": self.stance_id,
            "turn_type": self.turn_type,
            "claim": self.claim,
            "why": self.why,
            "evidence": [item.to_dict() for item in self.evidence],
            "assumptions": list(self.assumptions),
            "targets_attacked": list(self.targets_attacked),
            "weakness_found": self.weakness_found,
            "confidence": self.confidence,
            "new_information": self.new_information,
            "transcript_seen_turn_ids": list(self.transcript_seen_turn_ids),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class FinalReport:
    run_id: str
    request_id: str
    decision: DecisionLabel | None
    selected_position: dict[str, Any] | None
    selected_reason: dict[str, Any] | None
    rejected_positions: list[dict[str, Any]]
    scoped_positions: list[dict[str, Any]]
    unresolved_questions: list[str]
    causal_result: dict[str, Any]
    next_action: dict[str, str]
    transcript_digest: list[dict[str, Any]]
    cleanup_result: dict[str, Any]
    admission_decision: AdmissionDecisionLabel | None = None
    required_measurements: list[str] = field(default_factory=list)
    test_request: dict[str, str] | None = None
    escalation: dict[str, Any] | None = None
    causal_status: Literal["causal_candidate"] = "causal_candidate"
    created_at: str = field(default_factory=utc_now)

    def validate_no_bare_conclusion(self) -> None:
        if self.decision is None and self.admission_decision is None:
            raise DebateContractError("final report requires either decision or admission_decision")
        if self.decision == "request_more_context":
            raise DebateContractError("request_more_context is admission-stage only")
        if self.decision == "stop_and_request_test" and not (self.required_measurements or self.test_request):
            raise DebateContractError("stop_and_request_test requires required_measurements or test_request")
        if self.decision == "stop_and_escalate_to_master" and not self.escalation:
            raise DebateContractError("stop_and_escalate_to_master requires escalation details")
        required = ["statement", "why", "evidence", "scope", "assumptions", "invalidation_conditions", "risk_if_wrong"]
        missing = [key for key in required if key not in self.causal_result or self.causal_result[key] in (None, "", [])]
        if missing:
            raise DebateContractError(f"final report causal_result is missing required field(s): {', '.join(missing)}")
        if self.decision in {"accept_one", "accept_multiple_by_scope"} and not (
            self.rejected_positions or self.scoped_positions
        ):
            raise DebateContractError("final report must explain rejected or scoped alternatives")
        if self.decision == "stop_and_request_test" and self.next_action.get("target") != "test":
            raise DebateContractError("stop_and_request_test requires next_action.target == test")
        if self.decision == "stop_and_escalate_to_master" and self.next_action.get("target") != "master":
            raise DebateContractError("stop_and_escalate_to_master requires next_action.target == master")

    def to_dict(self) -> dict[str, Any]:
        self.validate_no_bare_conclusion()
        return {
            "run_id": self.run_id,
            "request_id": self.request_id,
            "decision": self.decision,
            "admission_decision": self.admission_decision,
            "selected_position": self.selected_position,
            "selected_reason": self.selected_reason,
            "rejected_positions": self.rejected_positions,
            "scoped_positions": self.scoped_positions,
            "unresolved_questions": list(self.unresolved_questions),
            "causal_result": self.causal_result,
            "next_action": self.next_action,
            "transcript_digest": list(self.transcript_digest),
            "cleanup_result": self.cleanup_result,
            "required_measurements": list(self.required_measurements),
            "test_request": self.test_request,
            "escalation": self.escalation,
            "causal_status": self.causal_status,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class DebateRunResult:
    run_id: str
    request_id: str
    admitted: bool
    workers_created: list[WorkerRecord]
    workers_released: list[WorkerRecord]
    transcript: list[WorkerTurn]
    final_report: FinalReport
    protocol_violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "request_id": self.request_id,
            "admitted": self.admitted,
            "workers_created": [item.to_dict() for item in self.workers_created],
            "workers_released": [item.to_dict() for item in self.workers_released],
            "transcript": [turn.to_dict() for turn in self.transcript],
            "final_report": self.final_report.to_dict(),
            "protocol_violations": list(self.protocol_violations),
        }
