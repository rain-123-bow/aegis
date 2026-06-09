from __future__ import annotations

from .models import ArtifactContract, CapabilityRule, SkillDefinition, SkillRegistrySnapshot, StateTransition

PHASE = "phase31a_governance_runtime_kernel"


class SkillRegistry:
    """Machine-readable role-skill registry used by runtime hard gates."""

    def __init__(self, snapshot: SkillRegistrySnapshot):
        self.snapshot = snapshot
        self._by_role = {item.role_id: item for item in snapshot.skills}
        self._by_id = {item.skill_id: item for item in snapshot.skills}

    def require_role(self, role_id: str) -> SkillDefinition:
        try:
            return self._by_role[role_id]
        except KeyError as exc:
            raise KeyError(f"skill definition missing for role: {role_id}") from exc

    def require_skill(self, skill_id: str) -> SkillDefinition:
        try:
            return self._by_id[skill_id]
        except KeyError as exc:
            raise KeyError(f"skill definition missing: {skill_id}") from exc

    def roles(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_role))


def load_default_skill_registry() -> SkillRegistry:
    return SkillRegistry(default_registry_snapshot())


def default_registry_snapshot() -> SkillRegistrySnapshot:
    return SkillRegistrySnapshot(
        registry_id="aegis_governance_runtime_kernel_registry",
        version="v0.1",
        phase=PHASE,
        skills=_skills(),
        capability_rules=_capabilities(),
        state_transitions=_transitions(),
        artifact_contracts=_contracts(),
    )


def _skill(skill_id: str, version: str, role: str, actions: tuple[str, ...], denied: tuple[str, ...], *, parent: str | None = None, children: tuple[str, ...] = (), profile: str | None = None) -> SkillDefinition:
    return SkillDefinition(skill_id, version, role, "runtime_hard_gate", profile or role, parent, children, actions, denied)


def _skills() -> tuple[SkillDefinition, ...]:
    no_release = ("remote_push", "create_pr", "remote_merge", "release", "deployment")
    return (
        _skill("MASTER_OPERATIONAL_WORKFLOW_SKILL", "v0.3", "master", ("classify_input", "create_top_level_leader", "dispatch_to_debate", "dispatch_to_execution", "create_commit_candidate", "write_archive_candidate", "write_knowledge_candidate", "stage_causal_candidate"), ("create_debate_worker", "create_execution_front_agent", "create_execution_back_agent", "create_test_worker", "dispatch_to_test", "dispatch_to_final_review") + no_release, children=("debate_leader", "execution_leader", "test_leader", "final_review_leader")),
        _skill("DEBATE_LEADER_OPERATIONAL_SKILL", "v0.1", "debate_leader", ("admit_debate", "create_debate_worker", "adjudicate_debate", "emit_debate_result"), no_release, parent="master"),
        _skill("DEBATE_WORKER_OPERATIONAL_SKILL", "v0.1", "debate_worker", ("analyze_assigned_stance", "emit_stance_report"), ("adjudicate_debate",) + no_release, parent="debate_leader"),
        _skill("EXECUTION_LEADER_OPERATIONAL_SKILL", "v0.3", "execution_leader", ("validate_execution_request", "create_group_branch", "create_execution_front_agent", "create_execution_back_agent", "integrate_accepted_groups", "emit_test_handoff"), no_release, parent="master"),
        _skill("EXECUTION_FRONT_AGENT_OPERATIONAL_SKILL", "v0.3", "execution_front_agent", ("modify_allowed_files", "run_local_validation", "emit_front_output"), ("self_approve", "review_front_output") + no_release, parent="execution_leader"),
        _skill("EXECUTION_BACK_AGENT_OPERATIONAL_SKILL", "v0.3", "execution_back_agent", ("review_front_output", "emit_back_review"), ("modify_code", "self_approve") + no_release, parent="execution_leader"),
        _skill("TEST_LEADER_OPERATIONAL_SKILL", "v0.1", "test_leader", ("validate_test_request", "create_test_worker", "aggregate_test_evidence", "emit_final_review_handoff"), ("modify_code",) + no_release, parent="master"),
        _skill("TEST_WORKER_OPERATIONAL_SKILL", "v0.1", "test_worker", ("read_candidate", "run_assigned_validation", "write_test_evidence", "emit_test_worker_report"), ("modify_code", "decide_whole_candidate") + no_release, parent="test_leader"),
        _skill("FINAL_REVIEW_LEADER_OPERATIONAL_SKILL", "v0.3", "final_review_leader", ("read_final_review_package", "resolve_resource_policy", "build_whole_chain_review", "emit_final_review_result"), ("create_worker", "run_test", "modify_code", "dispatch_to_execution", "dispatch_to_test") + no_release, parent="master"),
    )


def _capabilities() -> tuple[CapabilityRule, ...]:
    return tuple(
        CapabilityRule(item.role_id, item.allowed_actions, item.denied_actions)
        for item in _skills()
    ) + (
        CapabilityRule("execution_front_agent", ("modify_allowed_files", "run_local_validation", "emit_front_output"), ("self_approve",), ("workspaces/execution/front",), {"modify_allowed_files": ("group_branch_proof",)}),
        CapabilityRule("execution_back_agent", ("review_front_output", "emit_back_review"), ("modify_code",), ("artifacts/execution/back",), {"review_front_output": ("front_output_candidate",)}),
        CapabilityRule("test_worker", ("read_candidate", "run_assigned_validation", "write_test_evidence", "emit_test_worker_report"), ("modify_code",), ("artifacts/test/worker",), {"emit_test_worker_report": ("test_worker_report_candidate",)}),
        CapabilityRule("final_review_leader", ("read_final_review_package", "resolve_resource_policy", "build_whole_chain_review", "emit_final_review_result"), ("create_worker", "run_test", "modify_code"), ("artifacts/final_review",), {"build_whole_chain_review": ("final_review_input_package",), "emit_final_review_result": ("final_review_result_candidate",)}),
    )


def _transitions() -> tuple[StateTransition, ...]:
    return (
        StateTransition("execution_leader", "execution_request_received", "create_group_branch", "group_branch_created"),
        StateTransition("execution_leader", "group_branch_created", "create_execution_front_agent", "front_agent_created", ("group_branch_proof",)),
        StateTransition("execution_leader", "back_review_accepted", "integrate_accepted_groups", "leader_integration_created", ("back_review_candidate",)),
        StateTransition("test_leader", "test_request_received", "create_test_worker", "test_worker_created", ("test_route_plan",)),
        StateTransition("test_leader", "test_evidence_aggregated", "emit_final_review_handoff", "final_review_handoff_emitted", ("final_test_result_candidate", "artifact_manifest")),
        StateTransition("final_review_leader", "final_review_package_received", "resolve_resource_policy", "resource_policy_resolved", ("final_review_input_package",)),
        StateTransition("final_review_leader", "resource_policy_resolved", "build_whole_chain_review", "whole_chain_review_built", ("final_review_input_package",)),
        StateTransition("final_review_leader", "whole_chain_review_built", "emit_final_review_result", "final_review_result_emitted", ("final_review_result_candidate",)),
    )


def _contracts() -> tuple[ArtifactContract, ...]:
    return (
        ArtifactContract("group_branch_proof", ("group_id", "base_commit", "group_work_branch", "allowed_paths"), ("branch_derives_from_base_commit",), ("branch_is_orphan", "branch_is_unborn")),
        ArtifactContract("front_output_candidate", ("role_id", "group_id", "thread_id", "commit_sha", "branch_diff_ref"), allowed_values={"role_id": ("execution_front_agent",), "status": ("front_output_candidate",)}),
        ArtifactContract("back_review_candidate", ("role_id", "group_id", "reviewed_commit_sha", "review_decision"), allowed_values={"role_id": ("execution_back_agent",)}),
        ArtifactContract("test_worker_report_candidate", ("role_id", "route_id", "thread_id", "route_result", "command_evidence", "evidence_refs"), allowed_values={"role_id": ("test_worker",), "status": ("test_worker_report_candidate",)}),
        ArtifactContract("final_review_result_candidate", ("final_review_result_id", "request_id", "status", "decision", "target", "resource_policy", "causal_boundary"), allowed_values={"status": ("final_review_recommendation",), "target": ("master",)}),
        ArtifactContract("commit_gate_candidate", ("task_id", "decision"), ("exactly_one_task_bound",), ("remote_push_performed", "pr_created", "remote_merge_performed", "release_performed")),
    )
