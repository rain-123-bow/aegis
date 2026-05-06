from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegis_master_runtime import MasterTopLevelRuntime
from aegis_master_runtime.mcp_client import RecordingNestedCodexClient

pytestmark = pytest.mark.router

pytest.importorskip("aegis_router")


def _policy_path() -> Path:
    return Path(__file__).resolve().parents[3] / "MODEL_REASONING_BUDGET_POLICY.yaml"


def test_router_state_contains_policy_bound_nested_codex_leaders(tmp_path):
    runtime = MasterTopLevelRuntime(
        policy_path=_policy_path(),
        nested_codex_client=RecordingNestedCodexClient(),
        private_root=tmp_path / "private",
        router_state_path=tmp_path / "router_state.json",
    )

    report = runtime.bootstrap().to_dict()

    router_state = json.loads((tmp_path / "router_state.json").read_text(encoding="utf-8"))
    agents = router_state["agents"]

    assert set(["master", "debate", "execution", "test", "final_review"]) <= set(agents)
    assert agents["master"]["metadata"]["model_policy"]["resolved_reasoning_budget"] == "extra_high"
    assert agents["final_review"]["metadata"]["model_policy"]["resolved_reasoning_budget"] == "extra_high"
    assert agents["execution"]["metadata"]["model_policy"]["resolved_reasoning_budget"] == "high"
    assert agents["debate"]["metadata"]["nested_codex"]["status"] == "created"
    assert "global_causal" not in json.dumps(router_state, sort_keys=True)
    assert "causal_store" not in json.dumps(router_state, sort_keys=True)
    assert len(report["route_checks"]) == 10
    assert any(check["from"] == "debate" and check["to"] == "master" for check in report["route_checks"])
