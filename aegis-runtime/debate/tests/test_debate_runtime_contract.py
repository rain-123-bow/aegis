from __future__ import annotations

import pytest

from aegis_debate_runtime.adapters import InProcessDemoWorker, InProcessDemoWorkerFactory
from aegis_debate_runtime.leader import DebateLeaderRuntime
from aegis_debate_runtime.models import DebateProtocolError, StancePacket, WorkerTurn
from aegis_debate_runtime.topology import LeaderMediatedRoundRobinTopology

pytestmark = pytest.mark.contract


def _stance(stance_id: str, claim: str | None = None) -> dict:
    return {
        "stance_id": stance_id,
        "claim": claim or f"Claim {stance_id}",
        "why": f"Why {stance_id}",
        "scope": "demo scope",
        "assumptions": [f"assumption {stance_id}"],
        "evidence": [{"type": "contract", "ref": f"ref-{stance_id}", "relevance": "demo"}],
        "action_impact": f"action {stance_id}",
        "risk_if_wrong": f"risk {stance_id}",
        "material_conditions": ["local demo"],
        "invalidation_conditions": [f"condition change {stance_id}"],
    }


def _request(**overrides) -> dict:
    data = {
        "request_id": "test-request",
        "sender": "execution",
        "decision_target": "choose demo path",
        "question": "Which implementation path should the demo choose?",
        "scope": "demo scope",
        "constraints": ["contract-first"],
        "evidence": [{"type": "contract", "ref": "debate contract", "relevance": "test"}],
        "candidate_stances": [_stance("S1"), _stance("S2")],
        "max_rounds": 2,
        "no_new_information_round_limit": 1,
    }
    data.update(overrides)
    return data


def test_rejects_single_stance_before_worker_creation():
    result = DebateLeaderRuntime().run(_request(candidate_stances=[_stance("S1")]))

    assert result.admitted is False
    assert result.workers_created == []
    assert result.final_report.decision == "rejected_no_debate_needed"
    assert result.final_report.causal_status == "causal_candidate"


def test_request_more_context_before_worker_creation():
    result = DebateLeaderRuntime().run(_request(decision_target="", scope=""))

    assert result.admitted is False
    assert result.workers_created == []
    assert result.final_report.decision is None
    assert result.final_report.admission_decision == "request_more_context"
    assert result.final_report.next_action["target"] == "execution"


def test_creates_one_worker_per_valid_stance_and_releases_all():
    result = DebateLeaderRuntime().run(_request(candidate_stances=[_stance("S1"), _stance("S2"), _stance("S3")]))

    assert result.admitted is True
    assert len(result.workers_created) == 3
    assert len(result.workers_released) == 3
    assert {record.stance_id for record in result.workers_created} == {"S1", "S2", "S3"}
    assert all(record.status == "released" for record in result.workers_released)
    assert result.final_report.cleanup_result["topology"]["topology_released"] is True


def test_round_robin_broadcast_gives_all_workers_same_transcript_state():
    result = DebateLeaderRuntime().run(_request(candidate_stances=[_stance("S1"), _stance("S2"), _stance("S3")]))

    worker_ids = {record.worker_id for record in result.workers_created}
    # Every turn after the first should have seen some canonical transcript state.
    seen_sets = [set(turn.transcript_seen_turn_ids) for turn in result.transcript[1:]]
    assert seen_sets
    assert all(isinstance(item, set) for item in seen_sets)
    assert worker_ids == {record.worker_id for record in result.workers_released}


def test_worker_direct_peer_message_is_forbidden():
    stance = StancePacket.from_dict(_stance("S1"), 0)
    worker = InProcessDemoWorkerFactory().create_worker(run_id="run", stance=stance)
    topology = LeaderMediatedRoundRobinTopology(run_id="run", workers=[worker])

    with pytest.raises(DebateProtocolError):
        topology.send_peer_message(worker.worker_id, "other-worker", {"message": "bypass"})


def test_malicious_worker_cannot_switch_stance_silently():
    class MaliciousWorker(InProcessDemoWorker):
        def take_turn(self, *, run_id, round_index, turn_index, context):  # type: ignore[override]
            turn = super().take_turn(run_id=run_id, round_index=round_index, turn_index=turn_index, context=context)
            return WorkerTurn(
                run_id=turn.run_id,
                round_index=turn.round_index,
                turn_index=turn.turn_index,
                worker_id=turn.worker_id,
                stance_id="S999",
                turn_type=turn.turn_type,
                claim=turn.claim,
                why=turn.why,
                evidence=turn.evidence,
                assumptions=turn.assumptions,
                targets_attacked=turn.targets_attacked,
                weakness_found=turn.weakness_found,
                confidence=turn.confidence,
                new_information=turn.new_information,
                transcript_seen_turn_ids=turn.transcript_seen_turn_ids,
            )

    class MaliciousFactory:
        def create_worker(self, *, run_id, stance):
            return MaliciousWorker(worker_id=f"bad-{stance.stance_id}", stance=stance)

    with pytest.raises(DebateProtocolError):
        DebateLeaderRuntime(worker_factory=MaliciousFactory()).run(_request())


def test_final_report_contains_causal_structure_and_rejected_alternatives():
    result = DebateLeaderRuntime().run(_request())
    report = result.final_report.to_dict()
    causal = report["causal_result"]

    assert report["decision"] == "accept_one"
    assert causal["statement"]
    assert causal["why"]
    assert causal["scope"]
    assert causal["assumptions"]
    assert causal["invalidation_conditions"]
    assert causal["risk_if_wrong"]
    assert report["rejected_positions"]
    assert report["causal_status"] == "causal_candidate"


def test_stop_and_request_test_label_has_test_target_and_measurements():
    result = DebateLeaderRuntime().run(
        _request(
            requires_measurement=True,
            required_measurements=["benchmark CPU overhead", "capture end-to-end latency"],
        )
    )
    report = result.final_report.to_dict()

    assert report["decision"] == "stop_and_request_test"
    assert report["next_action"]["target"] == "test"
    assert "benchmark CPU overhead" in report["required_measurements"]
    assert report["test_request"]["target"] == "test"
    assert "benchmark CPU overhead" in report["unresolved_questions"]
    assert "benchmark CPU overhead" in report["causal_result"]["invalidation_conditions"]


def test_stop_and_escalate_to_master_label_has_master_target():
    result = DebateLeaderRuntime().run(_request(governance_impact=True))
    report = result.final_report.to_dict()

    assert report["decision"] == "stop_and_escalate_to_master"
    assert report["next_action"]["target"] == "master"
    assert report["escalation"]["target"] == "master"
    assert "governance" in report["causal_result"]["why"].lower()


def test_accept_multiple_by_scope_keeps_scoped_positions():
    result = DebateLeaderRuntime().run(_request(allow_scoped_outcome=True))
    report = result.final_report.to_dict()

    assert report["decision"] == "accept_multiple_by_scope"
    assert len(report["scoped_positions"]) == 2
    assert report["causal_result"]["scoped_alternatives"]


def test_runtime_does_not_claim_global_causal_truth_or_top_level_worker_routes():
    result = DebateLeaderRuntime().run(_request())
    payload = result.to_dict()

    assert payload["final_report"]["causal_status"] == "causal_candidate"
    assert "global_causal_truth" not in str(payload)
    assert "master -> debate_worker" not in str(payload)
