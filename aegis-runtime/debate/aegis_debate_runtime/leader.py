from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from .adapters import DebateWorkerFactory, InProcessDemoWorkerFactory
from .models import (
    DebateContractError,
    DebateProtocolError,
    DebateRequest,
    DebateRunResult,
    FinalReport,
    StancePacket,
    WorkerRecord,
    WorkerTurn,
)
from .topology import LeaderMediatedRoundRobinTopology


@dataclass
class DebateLeaderRuntime:
    """Demo Debate Leader runtime.

    This class owns request admission, stance-worker binding, leader-mediated
    round-robin broadcast, adjudication, cleanup, and causal final report creation.
    It does not mutate a global Causal Store. Its output is a causal candidate.
    """

    worker_factory: DebateWorkerFactory = field(default_factory=InProcessDemoWorkerFactory)

    def run(self, request_data: DebateRequest | dict[str, Any]) -> DebateRunResult:
        request = request_data if isinstance(request_data, DebateRequest) else DebateRequest.from_dict(request_data)
        run_id = f"debate-run-{uuid4().hex}"

        if not request.has_admission_context():
            return self._early_result(
                run_id=run_id,
                request=request,
                admission_decision="request_more_context",
                reason=(
                    "Admission-stage context is incomplete. Debate Leader cannot derive defensible stances "
                    "without a decision target and scope."
                ),
                next_action={"target": request.sender, "recommendation": "provide decision_target, scope, constraints, and evidence references"},
            )

        valid_stances = request.valid_stances()
        if len(valid_stances) < 2:
            return self._early_result(
                run_id=run_id,
                request=request,
                admission_decision="rejected_no_debate_needed",
                reason=(
                    "Debate requires at least two materially distinct defensible stances. "
                    "The request is deterministic, under-specified, or has only one valid path."
                ),
                next_action={"target": request.sender, "recommendation": "route to direct execution, contract lookup, or provide more stances"},
            )

        workers = [self.worker_factory.create_worker(run_id=run_id, stance=stance) for stance in valid_stances]
        workers_created = [WorkerRecord(worker_id=worker.worker_id, stance_id=worker.stance.stance_id, status="active") for worker in workers]
        topology = LeaderMediatedRoundRobinTopology(run_id=run_id, workers=workers)
        transcript: list[WorkerTurn] = []
        no_new_information_rounds = 0
        turn_index = 0

        try:
            for round_index in range(request.max_rounds):
                round_had_new_information = False
                for worker in topology.ordered_workers():
                    broadcast_event = topology.broadcast_transcript(transcript)
                    context = {
                        "request": request.to_dict(),
                        "stances": [stance.to_dict() for stance in valid_stances],
                        "transcript_digest": broadcast_event["digest"],
                        "broadcast_recipients": broadcast_event["recipients"],
                    }
                    turn = worker.take_turn(
                        run_id=run_id,
                        round_index=round_index,
                        turn_index=turn_index,
                        context=context,
                    )
                    self._validate_worker_turn(worker_stance_id=worker.stance.stance_id, turn=turn)
                    transcript.append(turn)
                    round_had_new_information = round_had_new_information or turn.new_information
                    turn_index += 1
                if round_had_new_information:
                    no_new_information_rounds = 0
                else:
                    no_new_information_rounds += 1
                    if no_new_information_rounds >= request.no_new_information_round_limit:
                        break
        finally:
            released_records = [worker.release() for worker in workers]
            topology_release = topology.release()

        final_report = self._make_final_report(
            run_id=run_id,
            request=request,
            stances=valid_stances,
            transcript=transcript,
            cleanup_result={
                "workers_released": [record.to_dict() for record in released_records],
                "topology": topology_release,
                "persistent_artifacts": ["final_report", "transcript_digest", "stance_packets", "evidence_references"],
            },
        )

        return DebateRunResult(
            run_id=run_id,
            request_id=request.request_id,
            admitted=True,
            workers_created=workers_created,
            workers_released=released_records,
            transcript=transcript,
            final_report=final_report,
            protocol_violations=[],
        )

    def _validate_worker_turn(self, *, worker_stance_id: str, turn: WorkerTurn) -> None:
        if turn.stance_id != worker_stance_id:
            raise DebateProtocolError(
                f"worker attempted to switch stance: expected {worker_stance_id}, got {turn.stance_id}"
            )
        if not turn.claim or not turn.why:
            raise DebateProtocolError("worker turn must contain claim and why")
        if not turn.targets_attacked and turn.turn_type in {"defend", "attack"}:
            raise DebateProtocolError("worker must attack or pressure competing stances during debate turns")

    def _early_result(
        self,
        *,
        run_id: str,
        request: DebateRequest,
        admission_decision: str,
        reason: str,
        next_action: dict[str, str],
    ) -> DebateRunResult:
        cleanup_result = {
            "workers_released": [],
            "topology": {"topology_released": True, "reason": "no topology created before admission"},
            "persistent_artifacts": ["final_report"],
        }
        final_report = FinalReport(
            run_id=run_id,
            request_id=request.request_id,
            decision="rejected_no_debate_needed" if admission_decision == "rejected_no_debate_needed" else None,
            admission_decision=admission_decision,  # type: ignore[arg-type]
            selected_position=None,
            selected_reason=None,
            rejected_positions=[],
            scoped_positions=[],
            unresolved_questions=[reason],
            causal_result={
                "statement": admission_decision,
                "why": reason,
                "evidence": [item.to_dict() for item in request.evidence]
                or [{"type": "request", "ref": request.request_id, "relevance": "admission result"}],
                "scope": request.scope or "admission stage before debate run",
                "assumptions": request.constraints or ["The Debate Department must not create workers without valid stance split."],
                "depends_on": [],
                "invalidates": [],
                "supersedes": [],
                "rejected_alternatives": [],
                "scoped_alternatives": [],
                "material_conditions": request.material_conditions or ["current request lacks debate admission conditions"],
                "invalidation_conditions": ["new context provides at least two defensible independent stances"],
                "risk_if_wrong": "Workers may be created for a non-debate request or a vague request.",
                "confidence": "high",
                "status": "causal_candidate",
            },
            next_action=next_action,
            transcript_digest=[],
            cleanup_result=cleanup_result,
        )
        return DebateRunResult(
            run_id=run_id,
            request_id=request.request_id,
            admitted=False,
            workers_created=[],
            workers_released=[],
            transcript=[],
            final_report=final_report,
            protocol_violations=[],
        )

    def _make_final_report(
        self,
        *,
        run_id: str,
        request: DebateRequest,
        stances: list[StancePacket],
        transcript: list[WorkerTurn],
        cleanup_result: dict[str, Any],
    ) -> FinalReport:
        selected = self._select_stance(stances)
        transcript_digest = [
            {
                "turn_id": turn.turn_id,
                "worker_id": turn.worker_id,
                "stance_id": turn.stance_id,
                "turn_type": turn.turn_type,
                "claim": turn.claim,
                "new_information": turn.new_information,
            }
            for turn in transcript
        ]

        if request.governance_impact:
            decision = "stop_and_escalate_to_master"
            selected_position = None
            selected_reason = None
            rejected_positions = []
            scoped_positions = []
            unresolved = [
                "The remaining issue affects top-level governance, authority, topology, or global causal merge policy."
            ]
            next_action = {"target": "master", "recommendation": "review governance-impacting conflict and decide authority/scope"}
            statement = "Debate stopped and escalated to Master because the conflict exceeds department-local authority."
            required_measurements: list[str] = []
            test_request = None
            escalation = {
                "target": "master",
                "issue": "The remaining issue affects top-level governance, authority, topology, or global causal merge policy.",
                "competing_positions": [stance.to_dict() for stance in stances],
                "why_debate_cannot_decide": "The Debate Department cannot decide Master-owned governance boundaries.",
                "master_decision_needed": "Decide authority, scope, or policy before implementation continues.",
            }
        elif request.requires_measurement:
            decision = "stop_and_request_test"
            selected_position = None
            selected_reason = None
            rejected_positions = []
            scoped_positions = []
            unresolved = request.required_measurements or [
                "The decisive missing evidence is measurable and must be produced by Test Department."
            ]
            next_action = {"target": "test", "recommendation": "run required measurements before final adjudication"}
            statement = "Debate stopped because the remaining conflict requires concrete measurement evidence."
            required_measurements = list(request.required_measurements)
            test_request = {
                "target": "test",
                "plan_ref": "debate-runtime-demo-required-measurements",
                "why_needed": "Continued debate cannot resolve the conflict without concrete measurement evidence.",
            }
            escalation = None
        elif request.allow_scoped_outcome:
            decision = "accept_multiple_by_scope"
            selected_position = None
            selected_reason = None
            rejected_positions = []
            scoped_positions = [
                {
                    "stance_id": stance.stance_id,
                    "claim": stance.claim,
                    "valid_scope": stance.scope,
                    "invalid_scope": "outside the stated scope or when listed invalidation conditions hold",
                    "transition_condition": stance.invalidation_conditions or request.material_conditions,
                    "action_when_condition_holds": stance.action_impact,
                }
                for stance in stances
            ]
            unresolved = []
            next_action = {"target": request.sender, "recommendation": "apply each stance only inside its valid scope"}
            statement = "Multiple stances are accepted under distinct scopes; no universal winner is forced."
            required_measurements = []
            test_request = None
            escalation = None
        else:
            decision = "accept_one"
            selected_position = selected.to_dict()
            selected_reason = {
                "claim": selected.claim,
                "why": selected.why,
                "evidence": [item.to_dict() for item in selected.evidence],
                "scope": selected.scope,
                "assumptions": selected.assumptions,
                "risk_if_wrong": selected.risk_if_wrong,
                "action_impact": selected.action_impact,
            }
            rejected_positions = [
                self._rejected_position(stance) for stance in stances if stance.stance_id != selected.stance_id
            ]
            scoped_positions = []
            unresolved = []
            next_action = {"target": request.sender, "recommendation": selected.action_impact}
            statement = selected.claim
            required_measurements = []
            test_request = None
            escalation = None

        causal_result = {
            "statement": statement,
            "why": self._causal_why(decision=decision, selected=selected, request=request),
            "evidence": [item.to_dict() for item in (selected.evidence or request.evidence)]
            or [{"type": "transcript", "ref": run_id, "relevance": "demo debate transcript"}],
            "scope": selected.scope if decision == "accept_one" else request.scope,
            "assumptions": selected.assumptions or request.constraints or ["demo runtime operates under Debate Department contract"],
            "depends_on": [],
            "invalidates": [],
            "supersedes": [],
            "rejected_alternatives": rejected_positions,
            "scoped_alternatives": scoped_positions,
            "material_conditions": selected.material_conditions or request.material_conditions or request.constraints,
            "invalidation_conditions": self._invalidation_conditions(selected=selected, request=request, decision=decision),
            "risk_if_wrong": selected.risk_if_wrong or "Incorrect adjudication may route later work under a stale or unsupported condition.",
            "confidence": "medium",
            "status": "causal_candidate",
        }
        if required_measurements:
            causal_result["required_measurements"] = list(required_measurements)
        if test_request:
            causal_result["test_request"] = dict(test_request)
        if escalation:
            causal_result["escalation"] = dict(escalation)

        report = FinalReport(
            run_id=run_id,
            request_id=request.request_id,
            decision=decision,  # type: ignore[arg-type]
            selected_position=selected_position,
            selected_reason=selected_reason,
            rejected_positions=rejected_positions,
            scoped_positions=scoped_positions,
            unresolved_questions=unresolved,
            causal_result=causal_result,
            next_action=next_action,
            transcript_digest=transcript_digest,
            cleanup_result=cleanup_result,
            required_measurements=required_measurements,
            test_request=test_request,
            escalation=escalation,
        )
        report.validate_no_bare_conclusion()
        return report

    def _select_stance(self, stances: list[StancePacket]) -> StancePacket:
        for stance in stances:
            text = " ".join([stance.stance_id, stance.claim, stance.why, stance.scope, stance.action_impact]).lower()
            if "leader-mediated" in text or "round-robin" in text:
                return stance
        return stances[0]

    def _causal_why(self, *, decision: str, selected: StancePacket, request: DebateRequest) -> str:
        if decision == "stop_and_request_test":
            return "Continued argument cannot resolve the conflict because the decisive evidence is measurable and missing."
        if decision == "stop_and_escalate_to_master":
            return "The conflict affects governance authority or top-level policy and exceeds Debate Department authority."
        if decision == "accept_multiple_by_scope":
            return "Workers exposed distinct valid scopes, so forcing one universal winner would erase conditional validity."
        return (
            f"Selected stance {selected.stance_id} because its claim is defensible under the current request scope, "
            "its assumptions are explicit, and alternatives are recorded for rejection or future reopening."
        )

    def _rejected_position(self, stance: StancePacket) -> dict[str, Any]:
        text = " ".join([stance.stance_id, stance.claim, stance.why]).lower()
        if "full-mesh" in text or "full mesh" in text:
            why_rejected = (
                "Full-mesh worker chat is rejected because it causes message explosion, hidden side channels, "
                "ordering ambiguity, and weak Leader control."
            )
            decisive_failure = "Violates the leader-mediated topology boundary required by the Debate Department contract."
        elif "independent" in text and "synthesis" in text:
            why_rejected = (
                "Independent workers with final synthesis only are rejected because workers cannot see each other's "
                "arguments, so adversarial pressure is lost."
            )
            decisive_failure = "Does not provide the shared transcript needed for attacks, answers, concessions, and scope refinement."
        else:
            why_rejected = "Not selected in this demo adjudication; retained as an explicit rejected/reopenable alternative."
            decisive_failure = (
                "Lower current causal priority than the selected stance under request scope, or requires changed material conditions."
            )
        return {
            "stance_id": stance.stance_id,
            "claim": stance.claim,
            "best_argument": stance.why,
            "why_rejected": why_rejected,
            "decisive_failure": decisive_failure,
            "reopen_if": stance.invalidation_conditions
            or stance.material_conditions
            or ["new evidence or material condition makes this stance stronger than the selected stance"],
        }

    def _invalidation_conditions(self, *, selected: StancePacket, request: DebateRequest, decision: str) -> list[str]:
        conditions = list(selected.invalidation_conditions)
        conditions.extend(request.material_conditions)
        if decision == "stop_and_request_test":
            conditions.extend(request.required_measurements or ["required measurement evidence is produced"])
        if decision == "stop_and_escalate_to_master":
            conditions.append("Master resolves governance boundary or changes authority policy")
        if not conditions:
            conditions = [
                "request scope changes",
                "new evidence contradicts the selected assumptions",
                "material hardware, contract, budget, or deployment conditions change",
            ]
        return conditions
