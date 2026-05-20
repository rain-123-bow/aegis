from __future__ import annotations

from pathlib import Path

from aegis_debate_runtime.real_nested_codex import load_debate_worker_policy


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_model_policy_defines_debate_worker_as_gpt_5_5_high():
    policy_path = REPO_ROOT / "MODEL_REASONING_BUDGET_POLICY.yaml"
    profile = load_debate_worker_policy(policy_path)

    assert profile.role_id == "debate_worker"
    assert profile.model == "gpt-5.5"
    assert profile.reasoning_budget == "high"
    assert profile.fallback_allowed is False
    assert profile.dynamic_adjustment_allowed is False

    text = policy_path.read_text(encoding="utf-8")
    assert "  - debate_worker" not in text


def test_debate_contract_preserves_two_layer_shape_and_no_extra_roles():
    contract = (REPO_ROOT / "aegis-master-kit/organization/departments/debate/DEBATE_DEPARTMENT_CONTRACT.md").read_text(
        encoding="utf-8"
    )

    assert "Debate Leader" in contract
    assert "Debate Worker per valid stance" in contract
    assert "independent evidence collector agent" in contract
    assert "Medium Debate Workers" in contract
    assert "real nested-Codex Debate Workers" in contract


def test_debate_worker_skill_requires_local_causal_state_priority():
    contract = (REPO_ROOT / "aegis-master-kit/organization/departments/debate/DEBATE_WORKER_OPERATIONAL_SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "worker_local_causal_state" in contract
    assert "route_priority" in contract
    assert "expand_priority" in contract
    assert "compact authoritative representation of its stance for later turns" in contract
