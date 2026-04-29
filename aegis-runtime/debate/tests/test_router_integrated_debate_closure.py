from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aegis_debate_runtime.leader import DebateLeaderRuntime
from aegis_router import Router, create_mailbucket_message
from aegis_router.errors import PermissionDeniedError

pytestmark = pytest.mark.contract


def _secret(agent_id: str) -> str:
    return f"{agent_id}-dev-secret"


def _key_id(agent_id: str) -> str:
    return f"{agent_id}-dev-key"


def _sign(sender: str, receiver: str, path: str, nonce: str, timestamp: str) -> str:
    material = "|".join([sender, receiver, path, nonce, timestamp]).encode("utf-8")
    digest = hmac.new(_secret(sender).encode("utf-8"), material, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def _route_envelope(sender: str, receiver: str, path: str, nonce: str) -> dict:
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "sender": sender,
        "receiver": receiver,
        "path": path,
        "auth": {
            "alg": "aegis-dev-hmac-sha256",
            "key_id": _key_id(sender),
            "nonce": nonce,
            "timestamp": timestamp,
            "signature": _sign(sender, receiver, path, nonce, timestamp),
        },
    }


def _register_top_level_agent(router: Router, agent_id: str) -> None:
    router.register_agent(
        agent_id,
        "top_level_master_domain",
        agent_id,
        metadata={"dev_identity_keys": {_key_id(agent_id): _secret(agent_id)}},
    )


def _debate_request() -> dict:
    return {
        "request_id": "router-integrated-debate-001",
        "sender": "master",
        "decision_target": "Choose the internal Debate Worker communication model for demo runtime.",
        "question": (
            "Choose the internal Debate Worker communication model for demo runtime: "
            "S1 = full-mesh asynchronous worker chat; "
            "S2 = leader-mediated round-robin broadcast; "
            "S3 = independent workers with final synthesis only."
        ),
        "scope": "Aegis Debate Department demo runtime on one local machine.",
        "constraints": [
            "Debate Workers are request-scoped temporary agents.",
            "The Leader owns the canonical transcript.",
            "Workers must be able to attack alternatives.",
            "Internal Debate Workers must not become top-level Master-route agents.",
        ],
        "evidence": [
            {
                "type": "contract",
                "ref": "aegis-master-kit/organization/departments/debate/INTERNAL_TOPOLOGY_CONTRACT.md",
                "relevance": "Defines leader-mediated round-robin broadcast and forbids default full-mesh worker chat.",
            }
        ],
        "material_conditions": ["local deterministic demo runtime", "no production distributed worker requirement"],
        "max_rounds": 2,
        "no_new_information_round_limit": 1,
        "candidate_stances": [
            {
                "stance_id": "S1",
                "claim": "Use full-mesh asynchronous worker chat.",
                "why": "Every worker could challenge every other worker directly without waiting for the Leader.",
                "scope": "Uncontrolled internal worker chat.",
                "assumptions": ["message ordering and side-channel risks are acceptable"],
                "evidence": [{"type": "proposal", "ref": "S1", "relevance": "candidate rejected by topology contract"}],
                "action_impact": "Create direct worker-to-worker routes.",
                "risk_if_wrong": "Message explosion, hidden side channels, ordering ambiguity, and weak Leader control.",
                "material_conditions": ["many asynchronous worker messages"],
                "invalidation_conditions": ["a future contract explicitly permits constrained peer-to-peer worker routes"],
            },
            {
                "stance_id": "S2",
                "claim": "Use leader-mediated round-robin broadcast.",
                "why": (
                    "The Leader controls speaking order, maintains the canonical transcript, broadcasts shared state, "
                    "and prevents uncontrolled worker-to-worker messaging."
                ),
                "scope": "Current Debate Department demo runtime.",
                "assumptions": ["one Leader controls each request-scoped run"],
                "evidence": [
                    {
                        "type": "contract",
                        "ref": "INTERNAL_TOPOLOGY_CONTRACT.md",
                        "relevance": "This is the required default Debate Department internal topology.",
                    }
                ],
                "action_impact": "Use worker -> Leader turns and Leader -> all transcript broadcasts.",
                "risk_if_wrong": "Debate may lose controlled ordering or become free-form group chat.",
                "material_conditions": ["request-scoped debate run", "Leader owns transcript and turn order"],
                "invalidation_conditions": ["a future contract changes the default internal topology"],
            },
            {
                "stance_id": "S3",
                "claim": "Use independent workers with final synthesis only.",
                "why": "Workers could independently analyze the topic and the Leader could synthesize outputs at the end.",
                "scope": "Parallel isolated analysis without shared transcript.",
                "assumptions": ["adversarial pressure is not required during the run"],
                "evidence": [{"type": "proposal", "ref": "S3", "relevance": "candidate weaker than shared transcript debate"}],
                "action_impact": "Run workers independently and skip transcript broadcasts until final synthesis.",
                "risk_if_wrong": "Workers cannot see each other's arguments, so adversarial pressure is lost.",
                "material_conditions": ["isolated worker analysis"],
                "invalidation_conditions": ["the request is analysis-only and no adversarial pressure is required"],
            },
        ],
    }


def _create_internal_debate_domain(router: Router, run_id: str) -> str:
    domain_id = f"debate_run_{run_id.replace('-', '_')}"
    edges = [
        {"from": "debate_worker_S1", "to": "debate_leader"},
        {"from": "debate_worker_S2", "to": "debate_leader"},
        {"from": "debate_worker_S3", "to": "debate_leader"},
        {"from": "debate_leader", "to": "debate_worker_S1"},
        {"from": "debate_leader", "to": "debate_worker_S2"},
        {"from": "debate_leader", "to": "debate_worker_S3"},
    ]
    router.create_domain(
        domain_id,
        owner_agent_id="debate_leader",
        metadata={"router_route_table": edges, "topology": "leader_mediated_round_robin_broadcast"},
    )
    router.register_agent("debate_leader", domain_id, "debate_leader")
    for stance_id in ["S1", "S2", "S3"]:
        router.register_agent(f"debate_worker_{stance_id}", domain_id, "debate_worker")
    return domain_id


def test_master_debate_request_closes_through_router_and_persists_causal_candidate(tmp_path):
    router = Router(tmp_path / "state.json", shared_communication_root=tmp_path / "mailbucket")
    router.create_domain("top_level_master_domain", owner_agent_id="master")
    for agent_id in ["master", "debate", "execution"]:
        _register_top_level_agent(router, agent_id)

    request = _debate_request()
    request_mail = create_mailbucket_message(
        sender="master",
        receiver="debate",
        shared_mailbucket_root=router.shared_communication_root,
        readme_text=json.dumps(request, indent=2, sort_keys=True),
        nonce="router-integrated-request",
    )
    request_envelope = _route_envelope(
        "master",
        "debate",
        request_mail["protected_path"],
        "master-debate-request-nonce",
    )

    request_message = router.send_message("master", "debate", "debate_request", request_envelope)

    assert set(request_message["payload"]) == {"sender", "receiver", "path", "auth"}
    assert "Choose the internal Debate Worker communication model" not in str(request_message["payload"])

    debate_inbox = router.receive_messages("debate")
    assert len(debate_inbox) == 1
    assert debate_inbox[0]["from_id"] == "master"
    assert debate_inbox[0]["message_type"] == "debate_request"

    run_result = DebateLeaderRuntime().run(request)
    run_payload = run_result.to_dict()
    final_report = run_payload["final_report"]
    causal_result = final_report["causal_result"]

    assert run_result.admitted is True
    assert len(run_result.workers_created) == 3
    assert {worker.stance_id for worker in run_result.workers_created} == {"S1", "S2", "S3"}

    internal_domain_id = _create_internal_debate_domain(router, run_result.run_id)

    for from_id, to_id in [
        ("debate_worker_S1", "debate_worker_S2"),
        ("debate_worker_S2", "debate_worker_S3"),
        ("debate_worker_S3", "debate_worker_S1"),
    ]:
        with pytest.raises(PermissionDeniedError):
            router.send_message(from_id, to_id, "worker_peer_message", {"forbidden": True})

    for worker_id in ["debate_worker_S1", "debate_worker_S2", "debate_worker_S3"]:
        with pytest.raises(PermissionDeniedError):
            router.send_message(worker_id, "master", "worker_direct_master", {"forbidden": True})
        with pytest.raises(PermissionDeniedError):
            router.send_message(worker_id, "execution", "worker_direct_execution", {"forbidden": True})

    prior_turn_ids: list[str] = []
    for expected_turn_index, turn in enumerate(run_result.transcript):
        worker_id = f"debate_worker_{turn.stance_id}"
        router.send_message(
            "debate_leader",
            worker_id,
            "transcript_update",
            {"transcript_turn_ids": list(prior_turn_ids)},
            requires_ack=False,
        )
        router.send_message(worker_id, "debate_leader", "worker_turn", turn.to_dict(), requires_ack=False)

        assert turn.turn_index == expected_turn_index
        assert turn.worker_id.endswith(f"__worker__{turn.stance_id}__{turn.worker_id.rsplit('__', 1)[-1]}")
        assert turn.transcript_seen_turn_ids == prior_turn_ids
        assert turn.claim
        assert turn.why
        assert turn.targets_attacked
        prior_turn_ids.append(turn.turn_id)

    assert final_report["decision"] == "accept_one"
    assert final_report["selected_position"]["stance_id"] == "S2"
    assert "leader-mediated round-robin broadcast" in final_report["selected_position"]["claim"].lower()
    rejected_by_id = {item["stance_id"]: item for item in final_report["rejected_positions"]}
    assert "message explosion" in rejected_by_id["S1"]["why_rejected"]
    assert "hidden side channels" in rejected_by_id["S1"]["why_rejected"]
    assert "ordering ambiguity" in rejected_by_id["S1"]["why_rejected"]
    assert "weak Leader control" in rejected_by_id["S1"]["why_rejected"]
    assert "cannot see each other's arguments" in rejected_by_id["S3"]["why_rejected"]
    assert "adversarial pressure is lost" in rejected_by_id["S3"]["why_rejected"]

    for required_key in [
        "why",
        "evidence",
        "assumptions",
        "material_conditions",
        "scope",
        "risk_if_wrong",
        "invalidation_conditions",
        "rejected_alternatives",
    ]:
        assert causal_result[required_key]
    assert final_report["causal_status"] == "causal_candidate"
    assert causal_result["status"] == "causal_candidate"

    report_path = tmp_path / "final_report.json"
    report_path.write_text(json.dumps(final_report, indent=2, sort_keys=True), encoding="utf-8")
    master_private = tmp_path / "master_private" / "final_report.json"
    master_private.parent.mkdir()
    master_private.write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")
    report_mail = create_mailbucket_message(
        sender="debate",
        receiver="master",
        shared_mailbucket_root=router.shared_communication_root,
        readme_text="Debate Leader final causal candidate. See final_report.json attachment.",
        attachments={"final_report.json": report_path},
        nonce="router-integrated-result",
    )
    result_envelope = _route_envelope(
        "debate",
        "master",
        report_mail["protected_path"],
        "debate-master-result-nonce",
    )
    result_message = router.send_message("debate", "master", "debate_result", result_envelope)

    assert "leader-mediated round-robin broadcast" not in str(result_message["payload"])
    master_inbox = router.receive_messages("master")
    delivered = [message for message in master_inbox if message["message_id"] == result_message["message_id"]]
    assert len(delivered) == 1
    acked = router.ack_message("master", result_message["message_id"])
    assert acked["status"] == "acked"

    for agent_id in ["debate_worker_S1", "debate_worker_S2", "debate_worker_S3", "debate_leader"]:
        router.unregister_agent(agent_id)

    internal_snapshot = router.domain_snapshot(internal_domain_id)
    assert internal_snapshot["agents"] == []
    assert master_private.is_file()
    assert (Path(report_mail["folder_path"]) / "final_report.json").is_file()
    persisted = json.loads(master_private.read_text(encoding="utf-8"))
    assert persisted["selected_position"]["stance_id"] == "S2"

    router_state_text = json.dumps(router._load(), sort_keys=True).lower()
    for forbidden in ["archive", "knowledge", "causal", "global_causal", "causal_store"]:
        assert forbidden not in router_state_text
