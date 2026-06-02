from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read(rel: str) -> str:
    return (_repo_root() / rel).read_text(encoding="utf-8")


def test_model_policy_defines_root_only_fallback_authority() -> None:
    policy = _read("MODEL_REASONING_BUDGET_POLICY.yaml")

    assert "authority: root_policy_only" in policy
    assert "role_profile_fallback_allowed_false_means" in policy
    assert "The role may not self-authorize fallback" in policy
    assert "unresolved_tool_attestation_behavior" in policy
    assert "requested_policy_only or" in policy


def test_topology_patch_admission_contract_blocks_missing_edge_runtime_use() -> None:
    contract = _read("aegis-master-kit/organization/contracts/TOPOLOGY_PATCH_ADMISSION_CONTRACT.md")

    assert "reject_runtime_route_request" in contract
    assert "admit_topology_patch_investigation" in contract
    assert "admit_topology_patch_task" in contract
    assert "test -> master" in contract
    assert "It does not add any new route by itself." in contract
    assert "An investigation must not activate the requested route." in contract


def test_topology_contract_separates_bootstrap_from_runtime_route_authority() -> None:
    topology = _read("aegis-master-kit/organization/contracts/TOP_LEVEL_ROUTE_TOPOLOGY_CONTRACT.md")
    organization = _read("aegis-master-kit/organization/ORGANIZATION_MODEL.md")
    master_skill = _read("aegis-master-kit/master/MASTER_OPERATIONAL_WORKFLOW_SKILL.md")

    assert "Bootstrap authority is not runtime route authority" in topology
    assert "Master has runtime outgoing edges only to `debate` and `execution`" in topology
    assert "Creating or auditing a Test Leader or Final Review Leader" in master_skill
    assert "bootstrap authority is separate from runtime route authority" in organization
    assert "TOPOLOGY_PATCH_ADMISSION_CONTRACT.md" in master_skill


def test_nested_codex_contract_requires_thread_id_and_separate_output_paths() -> None:
    contract = _read("aegis-runtime/master/NESTED_CODEX_MCP_CREATE_AGENT_CONTRACT.md")

    assert '"thread_id": "019e..."' in contract
    assert "model_attestation_status" in contract
    assert "behaviorally_attested" in contract
    assert "requested_policy_only" in contract
    assert "task_output_dir" in contract
    assert "proof_only_is_not_consultation_output" in contract
    assert "`proof_path` and `task_output_dir` are separate" in contract


def test_behavioral_attestation_challenge_is_fixed_and_inferential() -> None:
    challenge = _read("aegis-runtime/master/NESTED_CODEX_BEHAVIORAL_ATTESTATION_CHALLENGE.md")

    assert "aegis-model-behavioral-attestation-v1" in challenge
    assert "Behavioral attestation is not tool-level attestation." in challenge
    assert "rejects immediate `test -> master` runtime use" in challenge
    assert "role-local fallback versus root-policy-only fallback" in challenge
    assert "does not claim private backend model knowledge" in challenge
    assert "Minimum accepted score" in challenge
