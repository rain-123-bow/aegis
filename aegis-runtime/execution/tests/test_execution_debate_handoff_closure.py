from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aegis_execution_runtime import ExecutionLeader, ExecutionRunState, FinalExecutionReport
from aegis_router import Router, create_mailbucket_message, resolve_route_envelope_path
from aegis_router.errors import RouterError

pytestmark = pytest.mark.router


def _secret(agent_id: str) -> str:
    return f"{agent_id}-phase14-secret"


def _key_id(agent_id: str) -> str:
    return f"{agent_id}-phase14-key"


def _sign(sender: str, receiver: str, path: str, nonce: str, timestamp: str) -> str:
    material = "|".join([sender, receiver, path, nonce, timestamp]).encode("utf-8")
    digest = hmac.new(_secret(sender).encode("utf-8"), material, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def _route_envelope(sender: str, receiver: str, protected_path: str, nonce: str) -> dict:
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "sender": sender,
        "receiver": receiver,
        "path": protected_path,
        "auth": {
            "alg": "aegis-dev-hmac-sha256",
            "key_id": _key_id(sender),
            "nonce": nonce,
            "timestamp": timestamp,
            "signature": _sign(sender, receiver, protected_path, nonce, timestamp),
        },
    }


def _register(router: Router, agent_id: str) -> None:
    router.register_agent(
        agent_id,
        "top_level_master_domain",
        agent_id,
        metadata={"dev_identity_keys": {_key_id(agent_id): _secret(agent_id)}},
    )


def _mail(router: Router, tmp_path: Path, *, sender: str, receiver: str, filename: str, payload: dict, nonce: str) -> dict:
    source = tmp_path / f"{nonce}_{filename}"
    source.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return create_mailbucket_message(
        sender=sender,
        receiver=receiver,
        shared_mailbucket_root=router.shared_communication_root,
        readme_text=f"{sender} sends {filename} to {receiver}.",
        attachments={filename: source},
        nonce=nonce,
    )


def _resolve(envelope: dict, mail: dict, filename: str, root: Path) -> dict:
    folder = resolve_route_envelope_path(
        envelope,
        shared_mailbucket_root=root,
        resolver_material=mail["resolver_material"],
    )
    return json.loads((folder / filename).read_text(encoding="utf-8"))


def _request() -> dict:
    return {
        "request_id": "phase14-execution-debate-001",
        "sender": "master",
        "objective": "Implement a small extension point with one selected implementation route.",
        "scope": "Execution demo project with a route selected by Debate.",
        "constraints": [
            "both candidate plans are contract-valid",
            "no candidate has complete engineering dominance",
            "missing evidence is not a direct measurement blocker",
            "Execution must bind Debate result without re-litigating it",
        ],
        "applicable_contracts": [
            "aegis-master-kit/organization/departments/execution/DECISION_TO_DEBATE_RULES.md",
            "aegis-master-kit/organization/departments/execution/EXECUTION_LEADER_CONTRACT.md",
        ],
        "success_criteria": [
            "Debate selects one route",
            "Execution binds Debate result",
            "Execution creates groups after adjudication",
            "Execution returns final causal_candidate to Master",
        ],
        "forbidden_actions": ["remote push", "main merge", "global causal store mutation"],
        "base_branch": "v0.1.0-alpha",
        "candidate_plans": [
            {
                "plan_id": "PLAN_A",
                "claim": "Use simple direct implementation.",
                "why": "The direct route has lower complexity.",
                "valid_under_contracts": True,
                "dominated": False,
                "strengths": ["lower complexity"],
                "weaknesses": ["less extensible"],
                "evidence": ["plan-a:valid-direct-route"],
            },
            {
                "plan_id": "PLAN_B",
                "claim": "Use structured adapter implementation.",
                "why": "The adapter route preserves a better extension boundary.",
                "valid_under_contracts": True,
                "dominated": False,
                "strengths": ["better extension boundary"],
                "weaknesses": ["slightly more code"],
                "evidence": ["plan-b:valid-adapter-route"],
            },
        ],
        "subtasks": [
            {
                "subtask_id": "S1",
                "responsibility": "Create adapter boundary document.",
                "owned_files_or_modules": ["docs/adapter_boundary.md"],
                "input_contract": "selected route defines extension boundary",
                "output_contract": "document explains the selected adapter seam",
                "dependencies": [],
                "independence_reason": "The document owns a distinct path.",
                "local_success_criteria": ["adapter boundary document exists"],
                "expected_branch": "execution/phase14/G1/adapter-boundary",
                "merge_risk": "low",
                "feedback_mapping_rule": "docs/adapter_boundary.md -> G1",
                "file_changes": [
                    {
                        "path": "docs/adapter_boundary.md",
                        "content": "# Adapter boundary\n\nStructured adapter implementation selected by Debate.\n",
                        "change_type": "add",
                        "why_changed": "G1 implements the Debate-selected adapter documentation.",
                    }
                ],
            },
            {
                "subtask_id": "S2",
                "responsibility": "Create adapter fixture.",
                "owned_files_or_modules": ["fixtures/adapter_fixture.txt"],
                "input_contract": "adapter boundary document exists",
                "output_contract": "fixture records selected adapter route",
                "dependencies": ["S1"],
                "independence_reason": "The fixture owns a distinct path after S1 fixes the boundary shape.",
                "local_success_criteria": ["adapter fixture exists"],
                "expected_branch": "execution/phase14/G2/adapter-fixture",
                "merge_risk": "low",
                "feedback_mapping_rule": "fixtures/adapter_fixture.txt -> G2",
                "file_changes": [
                    {
                        "path": "fixtures/adapter_fixture.txt",
                        "content": "selected_plan=PLAN_B\n",
                        "change_type": "add",
                        "why_changed": "G2 records the Debate-selected route.",
                    }
                ],
            },
        ],
    }


def _debate_result() -> dict:
    return {
        "selected_plan_id": "PLAN_B",
        "decision": "accept_one",
        "why_selected": (
            "Plan B is selected because the structured adapter boundary is more extensible while remaining "
            "contract-valid; Plan A remains valid but is weaker for future extension."
        ),
        "rejected_or_scoped_plans": [
            {
                "plan_id": "PLAN_A",
                "classification": "scoped",
                "why": "Simple direct implementation remains acceptable only when extension is not a material concern.",
            }
        ],
        "causal_chain": {
            "chain_id": "debate-chain-phase14-plan-b",
            "source_request_id": "phase14-execution-debate-001",
            "decision_problem": "Choose between direct and structured adapter implementation routes.",
            "selected_plan_id": "PLAN_B",
            "nodes": [
                {
                    "id": "debate.selection.PLAN_B",
                    "type": "conclusion",
                    "statement": "Debate adjudicated Plan B as the selected route.",
                    "why": "Structured adapter implementation preserves the extension boundary.",
                    "evidence_refs": ["plan-b:valid-adapter-route"],
                    "assumptions": ["extension boundary matters in this scope"],
                    "scope": "Execution demo project with a route selected by Debate.",
                    "confidence": "high",
                }
            ],
            "edges": [],
            "selected_path": ["debate.selection.PLAN_B"],
            "status": "causal_candidate",
        },
        "status": "causal_candidate",
    }


def test_execution_requests_debate_binds_adjudication_and_returns_master_candidate(tmp_path):
    router = Router(tmp_path / "router_state.json", shared_communication_root=tmp_path / "mailbucket")
    router.create_domain("top_level_master_domain", owner_agent_id="master")
    for agent_id in ["master", "execution", "debate"]:
        _register(router, agent_id)

    request_payload = _request()
    request_mail = _mail(
        router,
        tmp_path,
        sender="master",
        receiver="execution",
        filename="execution_request.json",
        payload=request_payload,
        nonce="phase14-master-execution-request",
    )
    request_envelope = _route_envelope(
        "master",
        "execution",
        request_mail["protected_path"],
        "phase14-master-execution-request",
    )
    router.send_message("master", "execution", "execution_request", request_envelope)
    execution_request_message = router.receive_messages("execution")[-1]
    received_request = _resolve(
        execution_request_message["payload"],
        request_mail,
        "execution_request.json",
        router.shared_communication_root,
    )

    leader = ExecutionLeader(tmp_path / "execution_private")
    admission_report = leader.start_run(received_request)
    assert isinstance(admission_report, FinalExecutionReport)
    assert admission_report.decision == "request_debate"
    assert admission_report.next_action["target"] == "debate"

    adjudication_request_payload = {
        "request_id": received_request["request_id"],
        "decision": "request_debate",
        "candidate_plans": received_request["candidate_plans"],
        "why": "Execution found multiple contract-valid non-dominated implementation plans.",
    }
    adjudication_request_mail = _mail(
        router,
        tmp_path,
        sender="execution",
        receiver="debate",
        filename="adjudication_request.json",
        payload=adjudication_request_payload,
        nonce="phase14-execution-debate-request",
    )
    adjudication_request_envelope = _route_envelope(
        "execution",
        "debate",
        adjudication_request_mail["protected_path"],
        "phase14-execution-debate-request",
    )
    execution_to_debate = router.send_message(
        "execution",
        "debate",
        "adjudication_request",
        adjudication_request_envelope,
    )
    assert execution_to_debate["from_id"] == "execution"
    assert execution_to_debate["to_id"] == "debate"
    assert execution_to_debate["message_type"] == "adjudication_request"
    assert router.receive_messages("debate")[-1]["message_id"] == execution_to_debate["message_id"]

    with pytest.raises(RouterError):
        router.send_message("master", "execution_group_G1", "direct_group_message", {"forbidden": True})

    debate_result_payload = _debate_result()
    debate_result_mail = _mail(
        router,
        tmp_path,
        sender="debate",
        receiver="execution",
        filename="adjudication_result.json",
        payload=debate_result_payload,
        nonce="phase14-debate-execution-result",
    )
    debate_result_envelope = _route_envelope(
        "debate",
        "execution",
        debate_result_mail["protected_path"],
        "phase14-debate-execution-result",
    )
    debate_to_execution = router.send_message(
        "debate",
        "execution",
        "adjudication_result",
        debate_result_envelope,
    )
    assert debate_to_execution["from_id"] == "debate"
    assert debate_to_execution["to_id"] == "execution"
    assert debate_to_execution["message_type"] == "adjudication_result"
    debate_result_message = router.receive_messages("execution")[-1]
    received_debate_result = _resolve(
        debate_result_message["payload"],
        debate_result_mail,
        "adjudication_result.json",
        router.shared_communication_root,
    )

    state = leader.continue_after_debate(received_request, received_debate_result)
    assert isinstance(state, ExecutionRunState)
    assert state.selected_plan and state.selected_plan.plan_id == "PLAN_B"
    assert state.debate_reference["used"] is True
    assert state.debate_reference["selected_plan_id"] == "PLAN_B"
    assert state.debate_reference["causal_chain_ref"] == "debate-chain-phase14-plan-b"
    assert len(state.groups) == 2
    assert all(group.status == "UNDER_TEST" for group in state.groups)
    assert state.integration_candidate["debate_reference"]["used"] is True
    assert state.integration_candidate["debate_reference"]["selected_plan_id"] == "PLAN_B"

    final_report = leader.handle_test_feedback(
        state,
        {
            "feedback_id": "phase14-success",
            "result": "passed",
            "feedback_kind": "success",
            "evidence_refs": ["phase14:test:passed"],
            "covered_scope": ["docs/adapter_boundary.md", "fixtures/adapter_fixture.txt"],
            "uncovered_scope": [],
            "owner_type": "none",
            "why": "The Debate-selected adapter route passed the demo validation scope.",
        },
    )
    assert isinstance(final_report, FinalExecutionReport)
    final_payload = final_report.to_dict()
    chain = final_payload["execution_causal_chain"]
    debate_nodes = [node for node in chain["nodes"] if node["type"] == "debate_adjudication"]
    assert debate_nodes
    assert "Debate adjudicated PLAN_B" in debate_nodes[0]["statement"]
    assert "debate-chain-phase14-plan-b" in debate_nodes[0]["evidence_refs"]
    assert any(
        edge["from"] == "debate_adjudication.PLAN_B"
        and edge["to"] == "plan.PLAN_B"
        and edge["relation"] == "supports"
        for edge in chain["edges"]
    )
    assert chain["debate_reference"]["used"] is True
    assert chain["debate_reference"]["selected_plan_id"] == "PLAN_B"

    final_mail = _mail(
        router,
        tmp_path,
        sender="execution",
        receiver="master",
        filename="final_execution_report.json",
        payload=final_payload,
        nonce="phase14-execution-master-final",
    )
    final_envelope = _route_envelope(
        "execution",
        "master",
        final_mail["protected_path"],
        "phase14-execution-master-final",
    )
    result_message = router.send_message("execution", "master", "status_update", final_envelope)
    master_received = router.receive_messages("master")[-1]
    assert master_received["message_id"] == result_message["message_id"]
    returned_final = _resolve(
        master_received["payload"],
        final_mail,
        "final_execution_report.json",
        router.shared_communication_root,
    )
    assert returned_final["decision"] == "submit_causal_fork_to_master"
    assert returned_final["execution_causal_chain"]["status"] == "causal_candidate"
    assert returned_final["execution_causal_chain"]["debate_reference"]["used"] is True

    router_state_text = json.dumps(router._load(), sort_keys=True).lower()
    for forbidden in ["archive", "knowledge", "causal", "global_causal", "causal_store"]:
        assert forbidden not in router_state_text
