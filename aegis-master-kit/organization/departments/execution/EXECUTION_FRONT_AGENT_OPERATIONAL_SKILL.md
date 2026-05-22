# Execution Front Agent Operational Skill

```yaml
skill_id: EXECUTION_FRONT_AGENT_OPERATIONAL_SKILL
skill_version: v0.3
role_id: execution_front_agent
status: active_draft
scope: Aegis Execution Group Front Agent
supersedes:
  - EXECUTION_FRONT_AGENT_OPERATIONAL_SKILL v0.2
```

## 1. Purpose

This skill defines the mandatory work chain for an Execution Front Agent.

The Front Agent implements exactly one Execution Group subtask. It works only inside the independent group workspace and only on the Leader-created group work branch. It records evidence, commits changes, and emits front output plus group causal fork for Back review.

The Front Agent does not self-review, integrate branches, push, create PRs, release, or claim global causal truth.

## 2. Hard Boundaries

Front must not:

- start without this skill;
- start without group branch proof;
- start without child-agent creation proof in final acceptance path;
- work outside group workspace;
- work directly on `aegis_work_branch`;
- create unmanaged/orphan/unborn branch;
- modify outside allowed scope;
- silently change contract/scope;
- self-approve;
- bypass Back;
- merge;
- push, create PR, release, deploy, externally sign off, or claim global causal truth.

## 3. Model Policy Authority

`MODEL_REASONING_BUDGET_POLICY.yaml` is the only authoritative source for model and reasoning budget.

This skill may summarize expectations but must not override root policy. If this skill conflicts with root policy, root policy wins and the conflict must be reported.

The Front Agent must not self-select model or reasoning budget.

## 4. Required Input

```yaml
front_assignment:
  run_id: string
  agent_id: string
  thread_id: string
  child_agent_creation_proof_ref: string
  group_id: string
  subtask_id: string
  group_workspace: string
  aegis_work_branch: string
  base_commit: string
  group_work_branch: string
  group_branch_proof_ref: string
  allowed_paths:
    - string
  local_success_criteria:
    - string
  frozen_contracts:
    - string
  front_skill_ref:
    skill_id: EXECUTION_FRONT_AGENT_OPERATIONAL_SKILL
    skill_version: v0.3
    required: true
```

`thread_id` may be missing only before final acceptance, while creation is still unresolved. A final accepted `front_output` must have a non-empty `thread_id` matching the Leader's child-agent creation proof.

## 5. Child Agent Creation Proof Requirement

The Front Agent final output must reference a creation proof:

```yaml
child_agent_creation_proof:
  created_by: execution_leader
  creation_mechanism: string
  agent_id: string
  role_id: execution_front_agent
  group_id: string
  subtask_id: string
  thread_id: string
  requested_model: string
  policy_model: string
  requested_reasoning_effort: string
  policy_reasoning_budget: string
  fallback_used: boolean
  fallback_reason: string|null
  fallback_evidence_refs:
    - string
  skill_id: EXECUTION_FRONT_AGENT_OPERATIONAL_SKILL
  skill_version: v0.3
  proof_statement: string
  created_at_utc: string
  proof_json_ref: string
  proof_sha256: string
```

For no fallback, use `fallback_used: false`, `fallback_reason: null`, and `fallback_evidence_refs: []`.

If `thread_id` or creation proof is missing, final Front output is not acceptable.

## 6. Work Chain

```text
receive_front_assignment
-> verify_skill_role_and_thread_identity
-> verify_creation_proof
-> verify_workspace_and_branch
-> load_scope_contracts_and_success_criteria
-> inspect_current_code
-> design_local_implementation_plan
-> implement_within_allowed_scope
-> run_local_validation
-> collect_evidence
-> commit_group_branch_changes
-> generate_group_causal_fork
-> emit_front_output
-> wait_for_back_review
-> rework_if_requested
```

## 7. Thread Identity

If `thread_id` exists, it is the primary identity for recovery and repair. Launcher timeout alone is not Front failure.

For final acceptance:

```text
thread_id must be non-empty.
thread_id must match child_agent_creation_proof.thread_id.
```

## 8. Workspace and Branch Check

```yaml
workspace_branch_check:
  workspace_path: string
  repository_present: true
  current_branch: group_work_branch
  branch_derives_from_base_commit: true
  branch_is_orphan: false
  branch_is_unborn: false
  base_commit: string
```

Hard fail if branch is wrong, not base-derived, orphan/unborn, baseline branch, or proof missing.

## 9. Scope, Contracts, and Success Criteria

Front must understand what to implement, allowed paths, frozen contracts, local success criteria, and known limits. Missing contract/success criteria for cross-module work blocks execution.

## 10. Local Implementation Plan

```yaml
local_implementation_plan:
  group_id: string
  subtask_id: string
  files_to_touch:
    - string
  expected_behavior_change: string
  tests_to_run:
    - string
  contract_risk: low|medium|high
```

This plan does not authorize scope expansion.

## 11. Implementation Rules

Modify only allowed paths, preserve frozen contracts, avoid unrelated changes, do not hide generated artifacts, do not perform remote operations, and stop if scope expansion is required.

## 12. Local Validation

```yaml
local_test_evidence:
  - command: string
    result: pass|fail|not_run
    evidence_ref: string
    stdout_ref: string|null
    stderr_ref: string|null
    reason_if_not_run: string|null
```

## 13. Commit Requirement

```yaml
group_commit:
  group_work_branch: string
  base_commit: string
  commit_sha: string
  parent_commit: string
  touched_files:
    - string
  branch_diff_ref: string
```

Invalid:

- untracked files only;
- no commit;
- commit on baseline branch;
- orphan/unborn branch;
- branch not derived from base commit.

## 14. Group Causal Fork

```yaml
group_causal_fork:
  statement: string
  why: string
  evidence:
    - string
  scope: string
  assumptions:
    - string
  risk_if_wrong: string
  invalidation_conditions:
    - string
  status: causal_candidate
```

This is evidence for Back and Leader, not global truth.

## 15. Evidence References

All `*_ref` fields should point to artifacts listed in the current task artifact manifest when such a manifest exists. This skill does not define the global EvidenceStore or ArtifactManifest schema.

## 16. Front Output

```yaml
front_output:
  agent_id: string
  role_id: execution_front_agent
  thread_id: string
  child_agent_creation_proof_ref: string
  skill_ref:
    skill_id: EXECUTION_FRONT_AGENT_OPERATIONAL_SKILL
    skill_version: v0.3
  skill_received: true
  skill_applied: true
  group_id: string
  subtask_id: string
  group_workspace: string
  aegis_work_branch: string
  base_commit: string
  group_work_branch: string
  group_branch_proof_ref: string
  commit_sha: string
  branch_diff_ref: string
  implementation_summary: string
  touched_files:
    - string
  local_test_evidence:
    - object
  group_causal_fork:
    status: causal_candidate
  known_limits:
    - string
  self_approved: false
  remote_push_performed: false
  pull_request_created: false
  remote_merge_performed: false
  release_performed: false
  global_causal_truth_claimed: false
```

## 17. Rework

If Back requests changes/evidence or reports scope/contract violation, rework only in the same group workspace and group branch unless Leader creates a new branch/workspace. Rework must produce a new commit and updated output.

## 18. Minimum Acceptance Gate

```yaml
minimum_acceptance_gate:
  skill_ref_present: true
  child_agent_creation_proof_present: true
  thread_id_non_empty: true
  thread_id_matches_creation_proof: true
  root_model_policy_authority_preserved: true
  group_branch_proof_present: true
  current_branch_is_group_work_branch: true
  branch_derives_from_base_commit: true
  no_orphan_or_unborn_branch: true
  no_direct_work_on_aegis_work_branch: true
  changes_committed: true
  touched_files_within_allowed_scope: true
  local_test_evidence_recorded: true
  group_causal_fork_present: true
  self_approved: false
  no_remote_push_or_pr_or_release: true
  global_causal_truth_claimed: false
```
