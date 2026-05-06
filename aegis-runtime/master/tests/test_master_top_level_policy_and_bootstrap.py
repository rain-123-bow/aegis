from __future__ import annotations

from pathlib import Path

import pytest

from aegis_master_runtime import MasterTopLevelRuntime
from aegis_master_runtime.mcp_client import RecordingNestedCodexClient
from aegis_master_runtime.policy import load_model_reasoning_policy


def _policy_path() -> Path:
    return Path(__file__).resolve().parents[3] / "MODEL_REASONING_BUDGET_POLICY.yaml"


def test_locked_policy_parses_top_level_profiles():
    policy = load_model_reasoning_policy(_policy_path())

    assert policy.policy_id == "model_reasoning_budget_policy"
    assert policy.version == "v0.1"
    assert policy.require_profile("master").model == "gpt-5.5"
    assert policy.require_profile("master").reasoning_budget == "extra_high"
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
    assert all(record["router_registered"] for record in by_agent.values())
    assert all(check["verified"] for check in report["route_checks"])
    assert report["audit"]["fallback_used"] is False
    assert report["audit"]["dynamic_adjustment_used"] is False
    assert (tmp_path / "private" / "top_level_bootstrap_report.json").is_file()
