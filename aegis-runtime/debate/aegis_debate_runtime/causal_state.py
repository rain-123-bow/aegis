from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

RouteGrade = Literal["A", "B", "C", "D", "E", "F"]
ExpandGrade = Literal["A", "B", "C", "D"]
WorkerCausalStatus = Literal["active", "scoped", "conceded", "needs_evidence"]
CandidateStatus = Literal["active", "selected_candidate", "rejected", "scoped", "balanced", "needs_evidence"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PriorityEntry:
    id: str
    reason: str
    route_grade: RouteGrade | None = None
    expand_grade: ExpandGrade | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"id": self.id, "reason": self.reason}
        if self.route_grade is not None:
            data["route_grade"] = self.route_grade
        if self.expand_grade is not None:
            data["expand_grade"] = self.expand_grade
        return data


@dataclass(frozen=True)
class CausalEvidenceRef:
    type: str
    ref: str
    relevance: str = ""

    @classmethod
    def from_any(cls, value: Any) -> "CausalEvidenceRef":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(type="reference", ref=value, relevance="provided string reference")
        if isinstance(value, dict):
            evidence_type = value.get("type", "reference")
            ref = value.get("ref")
            relevance = value.get("relevance", "")
            if not isinstance(evidence_type, str) or not evidence_type:
                raise ValueError("evidence.type must be a non-empty string")
            if not isinstance(ref, str) or not ref:
                raise ValueError("evidence.ref must be a non-empty string")
            if not isinstance(relevance, str):
                raise ValueError("evidence.relevance must be a string")
            return cls(type=evidence_type, ref=ref, relevance=relevance)
        raise ValueError("evidence entries must be strings or objects")

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "ref": self.ref, "relevance": self.relevance}


@dataclass(frozen=True)
class WorkerLocalCausalState:
    run_id: str
    worker_id: str
    stance_id: str
    claim: str
    why: str
    evidence: list[CausalEvidenceRef]
    scope: str
    assumptions: list[str]
    depends_on: list[str] = field(default_factory=list)
    rejected_attacks: list[dict[str, str]] = field(default_factory=list)
    accepted_weaknesses: list[dict[str, str]] = field(default_factory=list)
    scope_narrowing_history: list[dict[str, str]] = field(default_factory=list)
    invalidation_conditions: list[str] = field(default_factory=list)
    risk_if_wrong: str = ""
    route_priority: list[PriorityEntry] = field(default_factory=list)
    expand_priority: list[PriorityEntry] = field(default_factory=list)
    status: WorkerCausalStatus = "active"
    updated_at: str = field(default_factory=utc_now)

    @classmethod
    def from_stance(cls, *, run_id: str, worker_id: str, stance: dict[str, Any]) -> "WorkerLocalCausalState":
        stance_id = str(stance.get("stance_id") or worker_id)
        claim = str(stance.get("claim") or "")
        why = str(stance.get("why") or "")
        scope = str(stance.get("scope") or "")
        if not claim or not why or not scope:
            raise ValueError("stance must include claim, why, and scope for worker local causal state")
        evidence = [CausalEvidenceRef.from_any(item) for item in stance.get("evidence", [])]
        assumptions = [str(item) for item in stance.get("assumptions", [])]
        invalidation_conditions = [str(item) for item in stance.get("invalidation_conditions", [])]
        route_priority = [
            PriorityEntry(id=f"stance:{stance_id}", route_grade="A", reason="assigned stance core claim"),
            PriorityEntry(id=f"scope:{stance_id}", route_grade="A", reason="scope bounds whether the stance can remain valid"),
            PriorityEntry(id=f"evidence:{stance_id}", route_grade="B", reason="evidence supports or weakens the stance"),
        ]
        expand_priority = [
            PriorityEntry(id=f"stance:{stance_id}", expand_grade="A", reason="full causal expansion is required for the assigned stance"),
            PriorityEntry(id=f"competitors:{stance_id}", expand_grade="B", reason="competing stances must be attacked by why and scope"),
        ]
        return cls(
            run_id=run_id,
            worker_id=worker_id,
            stance_id=stance_id,
            claim=claim,
            why=why,
            evidence=evidence,
            scope=scope,
            assumptions=assumptions,
            invalidation_conditions=invalidation_conditions,
            risk_if_wrong=str(stance.get("risk_if_wrong", "")),
            route_priority=route_priority,
            expand_priority=expand_priority,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "worker_id": self.worker_id,
            "stance_id": self.stance_id,
            "claim": self.claim,
            "why": self.why,
            "evidence": [item.to_dict() for item in self.evidence],
            "scope": self.scope,
            "assumptions": list(self.assumptions),
            "depends_on": list(self.depends_on),
            "rejected_attacks": list(self.rejected_attacks),
            "accepted_weaknesses": list(self.accepted_weaknesses),
            "scope_narrowing_history": list(self.scope_narrowing_history),
            "invalidation_conditions": list(self.invalidation_conditions),
            "risk_if_wrong": self.risk_if_wrong,
            "route_priority": [item.to_dict() for item in self.route_priority],
            "expand_priority": [item.to_dict() for item in self.expand_priority],
            "status": self.status,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class CandidatePositionState:
    stance_id: str
    claim: str
    current_status: CandidateStatus
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "stance_id": self.stance_id,
            "claim": self.claim,
            "current_status": self.current_status,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AdjudicatorCausalState:
    run_id: str
    decision_target: str
    current_question: str
    candidate_positions: list[CandidatePositionState]
    selected_candidate: dict[str, Any] | None = None
    rejected_candidates: list[dict[str, Any]] = field(default_factory=list)
    scoped_candidates: list[dict[str, Any]] = field(default_factory=list)
    unresolved_conflicts: list[str] = field(default_factory=list)
    decisive_evidence: list[CausalEvidenceRef] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    risk_ranking: list[dict[str, str]] = field(default_factory=list)
    route_priority: list[PriorityEntry] = field(default_factory=list)
    expand_priority: list[PriorityEntry] = field(default_factory=list)
    stop_reason: str = ""
    developer_decision_required: bool = False
    developer_decision_reason: str | None = None
    updated_at: str = field(default_factory=utc_now)

    @classmethod
    def initial(
        cls,
        *,
        run_id: str,
        decision_target: str,
        current_question: str,
        stances: list[dict[str, Any]],
    ) -> "AdjudicatorCausalState":
        positions = [
            CandidatePositionState(
                stance_id=str(stance.get("stance_id") or f"S{index + 1}"),
                claim=str(stance.get("claim") or ""),
                current_status="active",
                reason="initial defensible stance candidate",
            )
            for index, stance in enumerate(stances)
        ]
        route_priority = [
            PriorityEntry(id="decision_target", route_grade="A", reason="adjudication cannot proceed without the target"),
            PriorityEntry(id="stance_set", route_grade="A", reason="the debate is defined by competing stances"),
            PriorityEntry(id="evidence", route_grade="B", reason="evidence strength controls causal selection"),
            PriorityEntry(id="risk", route_grade="B", reason="risk if wrong affects action impact"),
        ]
        expand_priority = [
            PriorityEntry(id="selected_or_balanced_positions", expand_grade="A", reason="final decision requires full causal explanation"),
            PriorityEntry(id="rejected_positions", expand_grade="A", reason="serious alternatives must not disappear silently"),
            PriorityEntry(id="background_context", expand_grade="C", reason="background is only expanded when it changes scope or evidence"),
        ]
        return cls(
            run_id=run_id,
            decision_target=decision_target,
            current_question=current_question,
            candidate_positions=positions,
            route_priority=route_priority,
            expand_priority=expand_priority,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "decision_target": self.decision_target,
            "current_question": self.current_question,
            "candidate_positions": [item.to_dict() for item in self.candidate_positions],
            "selected_candidate": self.selected_candidate,
            "rejected_candidates": list(self.rejected_candidates),
            "scoped_candidates": list(self.scoped_candidates),
            "unresolved_conflicts": list(self.unresolved_conflicts),
            "decisive_evidence": [item.to_dict() for item in self.decisive_evidence],
            "missing_evidence": list(self.missing_evidence),
            "risk_ranking": list(self.risk_ranking),
            "route_priority": [item.to_dict() for item in self.route_priority],
            "expand_priority": [item.to_dict() for item in self.expand_priority],
            "stop_reason": self.stop_reason,
            "developer_decision_required": self.developer_decision_required,
            "developer_decision_reason": self.developer_decision_reason,
            "updated_at": self.updated_at,
        }


def developer_decision_required_from_report(final_report: dict[str, Any]) -> tuple[bool, str | None]:
    if final_report.get("developer_decision_required") is True:
        return True, str(final_report.get("developer_decision_reason") or "causal_equipoise")
    causal_result = final_report.get("causal_result") if isinstance(final_report.get("causal_result"), dict) else {}
    if causal_result.get("developer_decision_required") is True:
        return True, str(causal_result.get("developer_decision_reason") or "causal_equipoise")
    decision = final_report.get("decision")
    balanced = causal_result.get("balanced_positions") or final_report.get("balanced_positions")
    if decision in {"accept_multiple_by_scope", "stop_and_escalate_to_master"} and balanced:
        return True, "causal_equipoise"
    return False, None
