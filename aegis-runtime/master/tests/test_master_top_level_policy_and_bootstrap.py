from __future__ import annotations

from pathlib import Path

import pytest

from aegis_master_runtime import MasterTopLevelRuntime
from aegis_master_runtime.mcp_client import RecordingNestedCodexClient
from aegis_master_runtime.models import MasterRuntimeContractError, NestedCodexCreateResponse
from aegis_master_runtime.policy import load_model_reasoning_policy


def _policy_path() -> Path:
    return Path(__file__).resolve().parents[3] / "MODEL_REASONING_BUDGET_POLICY.yaml"


def test_locked_policy_parses_top_level_profiles():
    policy = load_model_reasoning_policy(_policy_path())

    assert policy.policy_id == "model_reasoning_budget_policy"
    assert policy.version == "v0.2"
    assert policy.status == "locked_static_policy_with_explicit_gpt54_fallback"
    assert policy.default_fallback_allowed is False
    assert policy.silent_downgrade_allowed is False
    assert policy.explicit_gpt55_to_gpt54_fallback_allowed is True
    assert policy.fallback_authority == "root_policy_only"
    assert policy.require_profile("master").model == "gpt-5.5"
    assert policy.require_profile("master").reasoning_budget == "extra_high"
    assert policy.require_profile("master").fallback_allowed is False
    assert policy.require_profile("master").fallback_authority == "root_policy_only"
    assert policy.require_profile("debate_leader").reasoning_budget == "high"
    assert policy.require_profile("execution_leader").reasoning_budget == "high"
    assert policy.require_profile("test_leader").reasoning_budget == "high"
    assert policy.require_profile("final_review_leader").reasoning_budget == "extra_high"
    assert policy.require_profile("final_review_leader").parallel_internal_workers == "forbidden"


def test_master_uses_policy_to_create_all_top_level_leaders_and_register_router(tmp_path):
    pytest.importorskip("aegis_router")

    client = RecordingNestedCodexClient()
    runtime = MasterTopLevelRuntime(
        policy_path=_policy_path(),
        nested_codex_client=client,
        private_root=tmp_path / "private",
        router_state_path=tmp_path / "router_state.json",
    )

    report = runtime.bootstrap().to_dict()

    assert report["status"] == "top_level_nested_codex_creation_verified"
    assert report["master_profile"]["resolved_model"] == "gpt-5.5"
    assert report["master_profile"]["resolved_reasoning_budget"] == "extra_high"
    assert report["audit"]["created_agent_count"] == 4
    assert len(client.requests) == 4

    by_agent = {record["agent_id"]: record for record in report["leader_records"]}
    assert by_agent["debate"]["reasoning_budget"] == "high"
    assert by_agent["execution"]["reasoning_budget"] == "high"
    assert by_agent["test"]["reasoning_budget"] == "high"
    assert by_agent["final_review"]["reasoning_budget"] == "extra_high"
    assert all(record["model"] == "gpt-5.5" for record in by_agent.values())
    assert all(record["thread_id"] for record in by_agent.values())
    assert all(record["model_attestation_status"] == "requested_policy_only" for record in by_agent.values())
    assert all(record["proof_path"].endswith("_leader_proof.json") for record in by_agent.values())
    assert all("leader_outputs" in record["task_output_dir"] for record in by_agent.values())
    assert all(record["router_registered"] for record in by_agent.values())
    assert all(check["verified"] for check in report["route_checks"])
    assert report["audit"]["fallback_used"] is False
    assert report["audit"]["dynamic_adjustment_used"] is False
    assert report["audit"]["proof_output_boundary"]["proof_path_is_not_task_output_dir"] is True
    assert (tmp_path / "private" / "top_level_bootstrap_report.json").is_file()

    for request in client.requests:
        assert request.metadata["fallback_authority"] == "root_policy_only"
        assert request.metadata["proof_path"].endswith("_leader_proof.json")
        assert "leader_outputs" in request.metadata["task_output_dir"]
        assert request.metadata["write_boundary"]["proof_only_is_not_consultation_output"] is True


def test_nested_codex_response_requires_thread_id_and_valid_attestation_status():
    with pytest.raises(MasterRuntimeContractError, match="thread_id"):
        NestedCodexCreateResponse.from_mapping(
            {
                "agent_id": "execution",
                "role_id": "execution_leader",
                "status": "created",
                "resolved_model": "gpt-5.5",
                "resolved_reasoning_budget": "high",
                "model_attestation_status": "tool_attested",
            }
        )

    with pytest.raises(MasterRuntimeContractError, match="model_attestation_status"):
        NestedCodexCreateResponse.from_mapping(
            {
                "agent_id": "execution",
                "role_id": "execution_leader",
                "status": "created",
                "resolved_model": "gpt-5.5",
                "resolved_reasoning_budget": "high",
                "thread_id": "thread-001",
                "model_attestation_status": "claimed_without_tool_support",
            }
        )

    response = NestedCodexCreateResponse.from_mapping(
        {
            "agent_id": "execution",
            "role_id": "execution_leader",
            "status": "created",
            "resolved_model": "gpt-5.5",
            "resolved_reasoning_budget": "high",
            "thread_id": "thread-001",
            "model_attestation_status": "behaviorally_attested",
        }
    )
    assert response.model_attestation_status == "behaviorally_attested"
