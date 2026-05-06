from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone

import pytest

from aegis_final_review_runtime import FinalReviewLeader

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
    for role in ["test", "final_review", "master"]:
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
        "request_id": "router-integrated-final-review-001",
        "source": "test",
        "resource_policy": {
            "policy_ref": "policy:root-model-budget",
            "required_profile": "final_review_leader",
            "resolved_profile": "final_review_leader",
            "reasoning_budget": "maximum",
            "fallback_used": False,
            "status": "satisfied",
        },
        "final_review_input_package": {
            "task_scope": ["declared_scope"],
            "final_code_ref": "candidate:final",
            "implementation_candidate_ref": "candidate:final",
            "tested_candidate_ref": "candidate:final",
            "reviewed_refs": {
                "execution_final_report_ref": "exec:final-report",
                "execution_causal_chain_ref": "exec:causal-candidate",
                "test_final_report_ref": "test:final-report",
                "test_plan_ref": "test:plan",
                "test_route_report_refs": ["test:route-report"],
                "test_evidence_refs": ["test:evidence"],
                "reproducibility_set_ref": "test:reproducibility",
                "artifact_manifest_ref": "test:artifact-manifest",
                "debate_refs": [],
            },
            "accepted_scope": ["declared_scope"],
            "blocked_scope": [],
            "known_limits": [],
            "missing_evidence": [],
            "governance_blockers": [],
            "material_conditions": ["deterministic demo candidate snapshot"],
            "assumptions": ["demo input refs are durable"],
            "execution_defects": [],
            "test_evidence_deficiencies": [],
            "evidence_contradictions": [],
            "object_mapping_evidence": [],
            "debate_used": False,
        },
    }


def test_final_review_receives_test_result_and_returns_master_recommendation(tmp_path):
    router = _top_level_router(tmp_path)

    request_mail = _mail(
        router,
        tmp_path,
        sender="test",
        receiver="final_review",
        readme="Test sends final review package to Final Review.",
        filename="final_review_request.json",
        payload=_request(),
        nonce="test-final-review-request",
    )
    request_envelope = _route_envelope("test", "final_review", request_mail["protected_path"], "request")
    router.send_message("test", "final_review", "test_result", request_envelope)
    received = router.receive_messages("final_review")[-1]
    request_payload = _resolve_payload(router, received["payload"], request_mail, "final_review_request.json")

    leader = FinalReviewLeader(tmp_path / "final_review_private")
    result = leader.run(request_payload).to_dict()

    assert result["decision"] == "accept_for_master"
    assert result["target"] == "master"
    assert result["known_limits"] == []
    assert result["resource_policy"]["status"] == "satisfied"

    result_mail = _mail(
        router,
        tmp_path,
        sender="final_review",
        receiver="master",
        readme="Final Review returns final_review_result to Master.",
        filename="final_review_result.json",
        payload=result,
        nonce="final-review-master-result",
    )
    result_envelope = _route_envelope("final_review", "master", result_mail["protected_path"], "result")
    router.send_message("final_review", "master", "final_review_result", result_envelope)
    master_received = router.receive_messages("master")[-1]
    returned_result = _resolve_payload(router, master_received["payload"], result_mail, "final_review_result.json")

    assert returned_result["decision"] == "accept_for_master"
    assert returned_result["target"] == "master"
    assert returned_result["causal_boundary"].startswith("Final Review output is a recommendation")

    snapshot = router.domain_snapshot("top_level_master_domain")
    serialized = json.dumps(snapshot, sort_keys=True)
    assert "global_causal" not in serialized
    assert "causal_store" not in serialized
