from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone

import pytest

from aegis_test_runtime import TestLeader

pytestmark = pytest.mark.router


aegis_router = pytest.importorskip("aegis_router")


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
    for role in ["execution", "test", "final_review"]:
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


def _request(final_summary: bool) -> dict:
    fixture_content = "status=reworked\nfinal summary: ready\n" if final_summary else "status=initial-candidate\n"
    return {
        "request_id": "router-integrated-test-001",
        "source": "execution",
        "objective": "Validate integrated execution candidate.",
        "scope": "docs and fixture output",
        "base_branch": "v0.1.0-alpha",
        "integration_branch": "execution/router-demo/integration",
        "implementation_candidate_ref": "artifact:implementation_candidate.json",
        "final_code_ref": "branch:execution/router-demo/integration",
        "changed_files": ["docs/execution_overview.md", "fixtures/execution_output.txt"],
        "ownership_map": {
            "docs/execution_overview.md": "G1",
            "fixtures/execution_output.txt": "G2",
        },
        "local_test_evidence": ["G1:local-test", "G2:local-test"],
        "back_review_summaries": ["G1:back-review", "G2:back-review"],
        "known_risks": ["fixture output may miss final summary"],
        "expected_test_focus": ["overview exists", "fixture output includes final summary"],
        "success_criteria": ["overview exists", "fixture output includes final summary"],
        "forbidden_actions": ["remote push", "main merge", "release"],
        "evidence_refs": ["execution-final-candidate"],
        "candidate_files": {
            "docs/execution_overview.md": "# Execution overview\n",
            "fixtures/execution_output.txt": fixture_content,
        },
        "requested_actions": [],
    }


def test_test_runtime_returns_failed_feedback_to_execution_and_passed_result_to_final_review(tmp_path):
    router = _top_level_router(tmp_path)

    failure_mail = _mail(
        router,
        tmp_path,
        sender="execution",
        receiver="test",
        readme="Execution sends implementation candidate to Test.",
        filename="test_request.json",
        payload=_request(final_summary=False),
        nonce="execution-test-failure-candidate",
    )
    failure_envelope = _route_envelope("execution", "test", failure_mail["protected_path"], "failure-candidate")
    router.send_message("execution", "test", "implementation_candidate", failure_envelope)
    received_failure = router.receive_messages("test")[-1]
    failure_payload = _resolve_payload(router, received_failure["payload"], failure_mail, "test_request.json")

    leader = TestLeader(tmp_path / "test_private")
    failure_report = leader.run(failure_payload).to_dict()
    assert failure_report["result"] == "failed"
    assert failure_report["next_route"] == "execution"

    feedback_mail = _mail(
        router,
        tmp_path,
        sender="test",
        receiver="execution",
        readme="Test returns evidence-backed failed feedback to Execution Leader.",
        filename="test_result.json",
        payload=failure_report,
        nonce="test-execution-feedback",
    )
    feedback_envelope = _route_envelope("test", "execution", feedback_mail["protected_path"], "failure-feedback")
    router.send_message("test", "execution", "test_feedback", feedback_envelope)
    execution_received = router.receive_messages("execution")[-1]
    returned_feedback = _resolve_payload(router, execution_received["payload"], feedback_mail, "test_result.json")
    assert returned_feedback["result"] == "failed"
    assert returned_feedback["owner_hint"]["owner_type"] == "group"

    pass_mail = _mail(
        router,
        tmp_path,
        sender="execution",
        receiver="test",
        readme="Execution sends reworked implementation candidate to Test.",
        filename="test_request.json",
        payload=_request(final_summary=True),
        nonce="execution-test-pass-candidate",
    )
    pass_envelope = _route_envelope("execution", "test", pass_mail["protected_path"], "pass-candidate")
    router.send_message("execution", "test", "implementation_candidate", pass_envelope)
    received_pass = router.receive_messages("test")[-1]
    pass_payload = _resolve_payload(router, received_pass["payload"], pass_mail, "test_request.json")

    pass_report = leader.run(pass_payload).to_dict()
    assert pass_report["result"] == "passed"
    assert pass_report["next_route"] == "final_review"

    result_mail = _mail(
        router,
        tmp_path,
        sender="test",
        receiver="final_review",
        readme="Test sends passed result and evidence to Final Review.",
        filename="test_result.json",
        payload=pass_report,
        nonce="test-final-review-result",
    )
    result_envelope = _route_envelope("test", "final_review", result_mail["protected_path"], "pass-result")
    router.send_message("test", "final_review", "test_result", result_envelope)
    final_review_received = router.receive_messages("final_review")[-1]
    returned_result = _resolve_payload(router, final_review_received["payload"], result_mail, "test_result.json")

    assert returned_result["result"] == "passed"
    assert returned_result["status"] == "test_evidence_candidate"
    assert returned_result["causal_boundary"].startswith("Test result is evidence")

    snapshot = router.domain_snapshot("top_level_master_domain")
    serialized = json.dumps(snapshot, sort_keys=True)
    assert "global_causal" not in serialized
    assert "causal_store" not in serialized
