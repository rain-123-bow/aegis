from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aegis_execution_runtime import ExecutionLeader, ExecutionRunState, FinalExecutionReport

pytestmark = pytest.mark.router


def _identity_secret(agent_id: str) -> str:
    return f"{agent_id}-secret"


def _identity_key_id(agent_id: str) -> str:
    return f"{agent_id}-key"


def _sign(sender: str, receiver: str, path: str, nonce: str, timestamp: str) -> str:
    material = "|".join([sender, receiver, path, nonce, timestamp]).encode("utf-8")
    digest = hmac.new(_identity_secret(sender).encode("utf-8"), material, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def _route_envelope(sender: str, receiver: str, protected_path: str, label: str) -> dict:
    nonce = f"{sender}-{receiver}-{label}-{datetime.now(timezone.utc).timestamp()}"
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "sender": sender,
        "receiver": receiver,
        "path": protected_path,
        "auth": {
            "alg": "aegis-dev-hmac-sha256",
            "key_id": _identity_key_id(sender),
            "nonce": nonce,
            "timestamp": timestamp,
            "signature": _sign(sender, receiver, protected_path, nonce, timestamp),
        },
    }


def _top_level_router(tmp_path):
    from aegis_router import Router

    router = Router(tmp_path / "router_state.json")
    router.create_domain("top_level_master_domain", owner_agent_id="master")
    for role in ["master", "execution", "test", "debate"]:
        router.register_agent(
            role,
            "top_level_master_domain",
            role,
            metadata={"dev_identity_keys": {_identity_key_id(role): _identity_secret(role)}},
        )
    return router


def _mail(router, tmp_path, *, sender: str, receiver: str, readme: str, filename: str, payload: dict, nonce: str):
    from aegis_router import create_mailbucket_message

    source = tmp_path / f"{nonce}_{filename}"
    source.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return create_mailbucket_message(
        sender=sender,
        receiver=receiver,
        shared_mailbucket_root=router.shared_communication_root,
        readme_text=readme,
        attachments={filename: source},
        nonce=nonce,
    )


def _resolve_payload(router, envelope: dict, mail: dict, filename: str) -> dict:
    from aegis_router import resolve_route_envelope_path

    folder = resolve_route_envelope_path(
        envelope,
        shared_mailbucket_root=router.shared_communication_root,
        resolver_material=mail["resolver_material"],
    )
    return json.loads((folder / filename).read_text(encoding="utf-8"))


def _request() -> dict:
    return {
        "request_id": "router-integrated-execution-001",
        "sender": "master",
        "objective": "Implement a traceable demo candidate with two independent subtasks and Test feedback rework.",
        "scope": "Execution router-integrated demo fixture.",
        "constraints": [
            "contract-first execution",
            "one Execution Group per independent subtask",
            "Back Agent review is mandatory",
            "Test feedback is mandatory whether pass or fail",
            "Execution output remains causal_candidate",
        ],
        "applicable_contracts": [
            "aegis-master-kit/organization/departments/execution/EXECUTION_LEADER_CONTRACT.md",
            "aegis-master-kit/organization/departments/execution/INTEGRATION_AND_TEST_HANDOFF_CONTRACT.md",
            "aegis-master-kit/organization/departments/execution/TEST_FEEDBACK_AND_REWORK_CONTRACT.md",
        ],
        "success_criteria": [
            "group outputs integrated",
            "Test failure maps to original group",
            "Test success releases groups",
            "execution_causal_chain returned to Master",
        ],
        "forbidden_actions": ["remote push", "main merge", "release", "global causal store mutation"],
        "base_branch": "v0.1.0-alpha",
        "evidence": [{"type": "contract", "ref": "router-integrated-execution-demo", "relevance": "closure test"}],
        "candidate_plans": [
            {
                "plan_id": "P1",
                "claim": "Use direct split-integrate-test-feedback execution.",
                "why": "It preserves group responsibility and Test feedback mapping.",
                "valid_under_contracts": True,
                "dominated": False,
                "strengths": ["traceable", "contract-aligned"],
                "weaknesses": ["demo filesystem branch model only"],
                "evidence": ["P1"],
            },
            {
                "plan_id": "P2",
                "claim": "Use one unstructured worker.",
                "why": "Simpler but loses responsibility mapping.",
                "valid_under_contracts": True,
                "dominated": True,
                "strengths": ["simple"],
                "weaknesses": ["no responsibility mapping"],
                "evidence": ["P2"],
            },
        ],
        "subtasks": [
            {
                "subtask_id": "S1",
                "responsibility": "Create execution overview document.",
                "owned_files_or_modules": ["docs/execution_overview.md"],
                "input_contract": "docs overview input fixed by request",
                "output_contract": "overview documents objective",
                "dependencies": [],
                "independence_reason": "Overview document owns its own file.",
                "local_success_criteria": ["overview exists"],
                "expected_branch": "execution/router-demo/G1/overview",
                "merge_risk": "low",
                "feedback_mapping_rule": "docs/execution_overview.md -> G1",
                "file_changes": [
                    {
                        "path": "docs/execution_overview.md",
                        "content": "# Execution overview\n\nExecution demo overview.\n",
                        "change_type": "add",
                        "why_changed": "G1 owns overview."
                    }
                ]
            },
            {
                "subtask_id": "S2",
                "responsibility": "Create execution fixture output.",
                "owned_files_or_modules": ["fixtures/execution_output.txt"],
                "input_contract": "fixture shape follows overview",
                "output_contract": "fixture captures deterministic execution output",
                "dependencies": ["S1"],
                "independence_reason": "Fixture owns a distinct file after S1 output shape is fixed.",
                "local_success_criteria": ["fixture exists"],
                "expected_branch": "execution/router-demo/G2/fixture",
                "merge_risk": "low",
                "feedback_mapping_rule": "fixtures/execution_output.txt and REWORK_NOTES.md -> G2",
                "file_changes": [
                    {
                        "path": "fixtures/execution_output.txt",
                        "content": "status=initial-candidate\n",
                        "change_type": "add",
                        "why_changed": "G2 owns fixture."
                    }
                ]
            }
        ]
    }


def test_master_execution_test_feedback_and_causal_chain_close_through_router(tmp_path):
    router = _top_level_router(tmp_path)

    request_mail = _mail(
        router,
        tmp_path,
        sender="master",
        receiver="execution",
        readme="Master sends executable work to Execution.",
        filename="execution_request.json",
        payload=_request(),
        nonce="master-execution-request",
    )
    request_envelope = _route_envelope("master", "execution", request_mail["protected_path"], "request")
    router.send_message("master", "execution", "execution_request", request_envelope)
    received = router.receive_messages("execution")
    assert received and received[0]["from_id"] == "master"
    request_payload = _resolve_payload(router, received[0]["payload"], request_mail, "execution_request.json")

    leader = ExecutionLeader(tmp_path / "execution_private")
    state = leader.start_run(request_payload)
    assert isinstance(state, ExecutionRunState)
    assert state.decision == "send_implementation_candidate_to_test"
    assert len(state.groups) == 2
    assert all(group.status == "UNDER_TEST" for group in state.groups)

    candidate_mail = _mail(
        router,
        tmp_path,
        sender="execution",
        receiver="test",
        readme="Execution sends implementation candidate to Test.",
        filename="implementation_candidate.json",
        payload=state.integration_candidate,
        nonce="execution-test-candidate-1",
    )
    candidate_envelope = _route_envelope("execution", "test", candidate_mail["protected_path"], "candidate-1")
    router.send_message("execution", "test", "implementation_candidate", candidate_envelope)
    assert router.receive_messages("test")

    failure_feedback = {
        "feedback_id": "router-test-failure-001",
        "result": "failed",
        "feedback_kind": "failure",
        "evidence_refs": ["router-test-log:fixture-output-missing-summary"],
        "covered_scope": ["fixtures/execution_output.txt"],
        "uncovered_scope": [],
        "owner_type": "group",
        "owner_id": "G2",
        "required_fix": "Add rework note proving G2 received evidence-backed Test feedback.",
        "why": "The fixture output is missing the extra summary required by this router-integrated demo.",
    }
    failure_mail = _mail(
        router,
        tmp_path,
        sender="test",
        receiver="execution",
        readme="Test returns evidence-backed failure feedback to Execution.",
        filename="test_feedback.json",
        payload=failure_feedback,
        nonce="test-execution-failure",
    )
    failure_envelope = _route_envelope("test", "execution", failure_mail["protected_path"], "failure")
    failure_message = router.send_message("test", "execution", "test_feedback", failure_envelope)
    assert failure_message["message_type"] == "test_feedback"
    failure_received = router.receive_messages("execution")[-1]
    assert failure_received["message_type"] == "test_feedback"
    feedback_payload = _resolve_payload(router, failure_received["payload"], failure_mail, "test_feedback.json")
    assert feedback_payload["result"] == "failed"
    assert feedback_payload["feedback_kind"] == "failure"
    state = leader.handle_test_feedback(state, feedback_payload)
    assert isinstance(state, ExecutionRunState)
    assert state.group_by_id("G2").rework_history

    candidate_mail_2 = _mail(
        router,
        tmp_path,
        sender="execution",
        receiver="test",
        readme="Execution resubmits reworked implementation candidate to Test.",
        filename="implementation_candidate.json",
        payload=state.integration_candidate,
        nonce="execution-test-candidate-2",
    )
    candidate_envelope_2 = _route_envelope("execution", "test", candidate_mail_2["protected_path"], "candidate-2")
    router.send_message("execution", "test", "implementation_candidate", candidate_envelope_2)
    assert router.receive_messages("test")

    success_feedback = {
        "feedback_id": "router-test-success-001",
        "result": "passed",
        "feedback_kind": "success",
        "evidence_refs": ["router-test-log:all-checks-passed"],
        "covered_scope": ["docs/execution_overview.md", "fixtures/execution_output.txt", "REWORK_NOTES.md"],
        "uncovered_scope": [],
        "owner_type": "none",
        "why": "The reworked candidate passed the declared validation scope.",
    }
    success_mail = _mail(
        router,
        tmp_path,
        sender="test",
        receiver="execution",
        readme="Test returns success feedback to Execution.",
        filename="test_feedback.json",
        payload=success_feedback,
        nonce="test-execution-success",
    )
    success_envelope = _route_envelope("test", "execution", success_mail["protected_path"], "success")
    success_message = router.send_message("test", "execution", "test_feedback", success_envelope)
    assert success_message["message_type"] == "test_feedback"
    assert success_message["message_type"] != "failure_feedback"
    success_received = router.receive_messages("execution")[-1]
    assert success_received["message_type"] == "test_feedback"
    success_payload = _resolve_payload(router, success_received["payload"], success_mail, "test_feedback.json")
    assert success_payload["result"] == "passed"
    assert success_payload["feedback_kind"] == "success"
    final_report = leader.handle_test_feedback(state, success_payload)
    assert isinstance(final_report, FinalExecutionReport)
    final_payload = final_report.to_dict()

    assert final_payload["decision"] == "submit_causal_fork_to_master"
    assert final_payload["final_status"] == "test_passed"
    assert all(group["status"] == "RELEASED" for group in final_payload["group_records"])
    assert final_payload["execution_causal_chain"]["status"] == "causal_candidate"
    assert final_payload["execution_causal_chain"]["nodes"]
    assert final_payload["execution_causal_chain"]["edges"]
    assert any(node["type"] == "test_feedback" for node in final_payload["execution_causal_chain"]["nodes"])
    assert any(node["type"] == "rework" for node in final_payload["execution_causal_chain"]["nodes"])

    final_mail = _mail(
        router,
        tmp_path,
        sender="execution",
        receiver="master",
        readme="Execution returns final causal candidate to Master.",
        filename="final_execution_report.json",
        payload=final_payload,
        nonce="execution-master-final",
    )
    final_envelope = _route_envelope("execution", "master", final_mail["protected_path"], "final")
    router.send_message("execution", "master", "causal_fork_submission", final_envelope)
    master_received = router.receive_messages("master")[-1]
    returned_final = _resolve_payload(router, master_received["payload"], final_mail, "final_execution_report.json")
    assert returned_final["execution_causal_chain"]["chain_id"] == final_payload["execution_causal_chain"]["chain_id"]
    router.ack_message("master", master_received["message_id"])

    persisted_path = Path(final_payload["artifact_paths"]["final_report"])
    assert persisted_path.is_file()
    persisted = json.loads(persisted_path.read_text(encoding="utf-8"))
    assert persisted["execution_causal_chain"]["chain_id"] == final_payload["execution_causal_chain"]["chain_id"]

    state_text = json.dumps(router._load(), sort_keys=True).lower()
    for forbidden in ["archive", "knowledge", "global_causal", "causal_store"]:
        assert forbidden not in state_text
    # The word "causal" may appear in message_type causal_fork_submission, but router state must not become a store.
    assert "causal_store" not in state_text
