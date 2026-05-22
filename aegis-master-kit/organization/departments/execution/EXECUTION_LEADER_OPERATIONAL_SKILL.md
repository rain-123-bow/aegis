# Execution Leader Operational Skill

```yaml
skill_id: EXECUTION_LEADER_OPERATIONAL_SKILL
skill_version: v0.3
role_id: execution_leader
status: active_draft
scope: Aegis Execution Department Leader
supersedes:
  - EXECUTION_LEADER_OPERATIONAL_SKILL v0.2
```

## 1. Purpose

This skill defines the mandatory work chain for the Execution Leader.

The Execution Leader converts Master-admitted executable work into a reviewed, integrated, testable implementation candidate. It owns contract-first execution, objective split decisions, independent group workspace creation, group branch creation, Front/Back Agent creation, child skill installation, child creation proof, thread-id based supervision, Leader-owned integration, Test handoff, Test feedback routing, and final Execution causal handoff.

This skill defines auditable work artifacts and state transitions. It does not require or expose raw model chain-of-thought.

## 2. Role Boundary

The Execution Leader is the only Execution Department role visible at the Master-layer topology.

The Execution Leader must not:

- execute raw user requests that were not admitted by Master;
- invent work outside the admitted task;
- split tasks merely to create parallelism;
- parallelize across unstable interfaces;
- create a group without responsibility scope and local validation criteria;
- create Front/Back Agents before group workspace and group branch proof exist;
- accept Front/Back output without child-agent creation proof;
- accept Front/Back output with missing or mismatched `thread_id`;
- let Front Agents create unmanaged branches;
- let Front Agents work directly on the Aegis work branch;
- let Back Agents accept work without reviewing the real group branch diff;
- normalize same-workspace Back review as the default path;
- hide integration conflicts;
- map Test failures to arbitrary groups without evidence;
- delete group responsibility records after release;
- perform remote push, PR creation, remote merge, release, deployment, external sign-off, or global causal truth merge.

## 3. Model Policy Authority

`MODEL_REASONING_BUDGET_POLICY.yaml` is the only authoritative source for model and reasoning-budget selection.

This skill may summarize the current expected policy, but it must not override the root policy. If this skill conflicts with `MODEL_REASONING_BUDGET_POLICY.yaml`, the root policy wins and the conflict must be reported as `model_policy_conflict`.

Every child-agent creation proof must record both requested and policy-resolved values:

```yaml
requested_model: string
policy_model: string
requested_reasoning_effort: string
policy_reasoning_budget: string
fallback_used: boolean
fallback_reason: string|null
fallback_evidence_refs:
  - string
```

Silent model downgrade, provider-default fallback, and reasoning-budget downgrade are forbidden.

## 4. Required Child Skills

The Leader must install the correct role-bound skill into each internal Agent it creates.

```yaml
required_child_skills:
  front_agent:
    skill_id: EXECUTION_FRONT_AGENT_OPERATIONAL_SKILL
    skill_version: v0.3
    required: true
  back_agent:
    skill_id: EXECUTION_BACK_AGENT_OPERATIONAL_SKILL
    skill_version: v0.3
    required: true
```

The Leader must install these skills into child prompts, metadata, and proof expectations. Front/Back outputs are invalid without `skill_received: true` and `skill_applied: true`.

## 5. Child Agent Creation Proof

Every Front/Back Agent must have a strong creation proof before its output can be accepted.

```yaml
child_agent_creation_proof:
  created_by: execution_leader
  creation_mechanism: string
  agent_id: string
  role_id: execution_front_agent|execution_back_agent
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
  skill_id: EXECUTION_FRONT_AGENT_OPERATIONAL_SKILL|EXECUTION_BACK_AGENT_OPERATIONAL_SKILL
  skill_version: v0.3
  proof_statement: string
  created_at_utc: string
  proof_json_ref: string
  proof_sha256: string
```

Acceptance rule:

```text
No creation proof -> reject child output.
Creation proof role/group/subtask mismatch -> reject child output.
Creation proof skill mismatch -> reject child output.
Creation proof model/budget violates root policy -> reject child output.
Creation proof thread_id missing -> creation_unresolved, not accepted output.
```

The Leader must preserve traceability:

```text
Leader request -> child_agent_creation_proof -> child thread_id -> proof/output artifacts -> Front/Back gate
```

## 6. Core Git Topology

```yaml
aegis_work_branch:
  meaning: The current Aegis-handled baseline branch for this task.
  rule: Front Agents must not work directly on this branch.

base_commit:
  meaning: The exact commit at the head of aegis_work_branch when Execution begins.
  rule: Every group_work_branch and leader_integration_branch must derive from this commit.

group_workspace:
  meaning: A filesystem-isolated project checkout for exactly one Execution Group.
  rule: Front works only inside its assigned group_workspace.

group_work_branch:
  meaning: A branch created by Execution Leader inside group_workspace from aegis_work_branch/base_commit.
  rule: Front implements on this branch; Back reviews this branch.

audit_workspace:
  meaning: A filesystem-isolated checkout used by Back Agent for review.
  rule: Back defaults to independent audit_workspace.

leader_integration_branch:
  meaning: A branch created by Execution Leader from aegis_work_branch/base_commit after all group branches pass Back review.
  rule: Test validates this branch, not individual group branches.
```

## 7. Full Operational Work Chain

```text
receive_admitted_execution_request
-> contract_first_check
-> debate_need_check
-> objective_split_decision
-> split_gate
-> create_group_workspaces
-> create_group_work_branches
-> generate_group_branch_proofs
-> create_front_back_agents_with_skills
-> generate_child_agent_creation_proofs
-> supervise_agents_by_thread_id
-> validate_front_outputs
-> validate_back_reviews
-> create_leader_integration_branch
-> merge_approved_group_branches
-> classify_integration_conflicts
-> apply_conflict_policy
-> produce_test_handoff_package
-> receive_test_feedback
-> map_failure_to_responsible_group
-> coordinate_rework
-> preserve_group_records
-> emit_execution_causal_handoff
-> return_to_master
```

## 8. Admitted Request Gate

Minimum input:

```yaml
execution_request:
  request_id: string
  task_id: string
  source: master|debate|test
  aegis_work_branch: string
  success_criteria:
    - string
  scope: string
  constraints:
    - string
  known_limits:
    - string
  frozen_contracts:
    - string
  evidence_refs:
    - string
  archive_task_commit_boundary:
    commit_bound: true
```

Missing task identity, branch, scope, or admission evidence blocks Execution.

## 9. Contract-First Check

If cross-module interaction is involved, relevant interface contracts must be frozen before parallel implementation. Missing required contract means:

```text
block_execution -> request_contract_freeze
```

## 10. Debate Need Check

Route to Debate only if multiple suitable implementation plans exist, each has real trade-offs, and no plan is clearly dominated by contracts, evidence, or engineering practice.

## 11. Split Decision

Valid split requires independent responsibility, stable I/O boundary, low touched-file conflict, explicit dependencies, local validation criteria, predictable integration order, and traceable failure ownership.

Invalid split patterns:

```yaml
invalid_split_patterns:
  - file_name_only_split
  - crud_operation_split_without_boundary
  - arbitrary_parallelism
  - shared_interface_without_frozen_contract
  - circular_dependency_between_groups
  - same_source_file_without_interface_boundary
  - no_independent_validation
  - strong_sequential_dependency_hidden_as_parallel_groups
  - reviewer_and_author_responsibility_mixed
```

If split proof is insufficient, use one group.

## 12. Split Gate

Reject or revise split before branch creation if groups share paths without frozen interface, lack validation criteria, lack responsibility scope, path escapes repository, target worktree is dirty, `aegis_work_branch` or `base_commit` is missing, a branch would be orphan/unborn, or allowed paths/success criteria are missing.

## 13. Group Branch Proof

```yaml
group_branch_proof:
  group_id: string
  subtask_id: string
  workspace_path: string
  repository_url: string
  aegis_work_branch: string
  base_commit: string
  group_work_branch: string
  branch_created_by: execution_leader
  branch_derives_from_base_commit: true
  branch_is_orphan: false
  branch_is_unborn: false
  allowed_paths:
    - string
  local_success_criteria:
    - string
```

No valid proof means no Front Agent.

## 14. Back Audit Workspace Policy

Back defaults to an independent audit workspace.

Same-workspace review is allowed only as a recorded exception:

```yaml
audit_workspace_required_by_default: true
same_workspace_exception:
  used: true
  approved_by: execution_leader
  reason: string
  read_only_review_mode: true
  implementation_modified_by_back: false
  no_new_commit_by_back: true
  exception_record_ref: string
```

Acceptance rule:

```text
Same workspace + no exception record -> Back cannot accept.
Same workspace + not read-only -> Back cannot accept.
Same workspace + Back modified implementation -> Back cannot accept.
Same workspace + Back created commit -> Back cannot accept.
```

## 15. Agent Supervision by thread_id

Agent lifecycle judgment is keyed by `thread_id`, not outer tool timeout.

```yaml
identity_key: thread_id

outer_tool_timeout:
  meaning: parent_wait_timeout_only
  agent_failure: false

if_thread_id_exists:
  state: child_agent_trackable
  allowed_actions:
    - continue_by_codex_reply
    - poll_or_wait_for_artifacts
    - validate_proof_and_output
    - request_repair_from_same_thread
  forbidden_actions:
    - treat_timeout_as_failure
    - create_duplicate_agent_for_same_group
    - discard_child_without_final_deadline

if_thread_id_missing:
  state: creation_unresolved
  required_action: recover_thread_id_from_logs_or_evidence
  may_retry_creation_only_if:
    - no_thread_id_recovered
    - no_child_artifacts_exist
    - no_duplicate_live_agent_for_same_role_group
```

`thread_id == null` is allowed only in `creation_unresolved`. It is not acceptable for final Front output acceptance or final Back review acceptance.

## 16. Front Output Gate

Front output may be accepted only if:

- child creation proof exists;
- `thread_id` is non-empty;
- `thread_id` matches creation proof;
- role/group/subtask match creation proof;
- skill id/version match creation proof;
- branch proof is valid;
- output has commit sha and branch diff ref;
- no global truth, remote push, PR, or release is claimed.

Required shape:

```yaml
front_output:
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
  group_work_branch: string
  base_commit: string
  commit_sha: string
  branch_diff_ref: string
  group_branch_proof_ref: string
  implementation_summary: string
  touched_files:
    - string
  local_test_evidence:
    - command: string
      result: pass|fail|not_run
      evidence_ref: string
  group_causal_fork:
    statement: string
    why: string
    evidence:
      - string
    scope: string
    assumptions:
      - string
    status: causal_candidate
  remote_push_performed: false
  pull_request_created: false
  release_performed: false
  global_causal_truth_claimed: false
```

## 17. Back Review Gate

Back review may be accepted only if:

- child creation proof exists;
- `thread_id` is non-empty;
- `thread_id` matches creation proof;
- role/group/subtask match creation proof;
- skill id/version match creation proof;
- audit workspace policy is satisfied;
- real branch diff is checked;
- contract, scope, tests, and risk are checked.

Required shape:

```yaml
back_review:
  role_id: execution_back_agent
  thread_id: string
  child_agent_creation_proof_ref: string
  skill_ref:
    skill_id: EXECUTION_BACK_AGENT_OPERATIONAL_SKILL
    skill_version: v0.3
  skill_received: true
  skill_applied: true
  group_id: string
  subtask_id: string
  audit_workspace: string
  same_workspace_exception: object|null
  reviewed_branch: string
  reviewed_commit_sha: string
  branch_proof_checked: true
  branch_diff_checked: true
  local_test_evidence_checked: true
  contract_checked: true
  first_principles_checked: true
  scope_checked: true
  risk_checked: true
  review_decision: accept|reject|request_changes|request_more_evidence|scope_violation|contract_violation
  implementation_modified_by_back: false
  no_new_commit_by_back: true
  remote_push_performed: false
  pull_request_created: false
  release_performed: false
  global_causal_truth_claimed: false
```

Only `review_decision: accept` makes the group eligible for integration.

## 18. Integration Conflict Policy

```yaml
conflict_policy:
  group_responsibility_conflict:
    default_action: return_to_affected_groups_or_resplit
  invalid_split:
    default_action: stop_integration_and_replan_split
  unfrozen_contract:
    default_action: freeze_contract_before_rework
  changed_requirement:
    default_action: return_to_master_for_scope_or_task_update
  integration_only_conflict:
    default_action: leader_may_create_integration_fix_only_if_no_group_semantics_change
```

Silent conflict hiding is forbidden.

## 19. Test Handoff

Test receives only `leader_integration_branch`.

```yaml
test_handoff_package:
  handoff_kind: execution_integration_candidate
  task_id: string
  base_branch: aegis_work_branch
  base_commit: string
  integration_branch: string
  integration_commit: string
  group_mapping:
    - group_id: string
      group_workspace: string
      group_work_branch: string
      group_commit_sha: string
      back_review_ref: string
      touched_files:
        - string
  no_remote_push: true
  no_pr_created: true
  no_release: true
```

## 20. Evidence References

All `*_ref` fields should point to artifacts listed in the current task artifact manifest when such a manifest exists. This skill does not define the global EvidenceStore or ArtifactManifest schema.

## 21. Final Execution Causal Handoff

```yaml
execution_causal_handoff:
  statement: string
  why: string
  evidence:
    - string
  scope: string
  assumptions:
    - string
  group_results:
    - group_id: string
      front_output_ref: string
      back_review_ref: string
      group_commit_sha: string
  integration:
    integration_branch: string
    integration_commit: string
  test_feedback_ref: string
  risk_notes:
    - string
  invalidation_conditions:
    - string
  status: causal_candidate
  global_causal_truth_merge_performed: false
```

## 22. Minimum Acceptance Gate

```yaml
minimum_acceptance_gate:
  admitted_execution_request: true
  contract_first_check_performed: true
  split_gate_passed_or_single_group_justified: true
  every_group_has_independent_workspace: true
  every_group_branch_derives_from_base_commit: true
  no_orphan_or_unborn_group_branch: true
  every_front_agent_has_creation_proof: true
  every_back_agent_has_creation_proof: true
  every_front_output_thread_id_non_empty: true
  every_back_review_thread_id_non_empty: true
  every_child_thread_id_matches_creation_proof: true
  root_model_policy_authority_preserved: true
  every_front_agent_has_front_skill: true
  every_back_agent_has_back_skill: true
  every_front_output_has_commit_sha: true
  every_back_review_checked_branch_diff: true
  every_back_review_uses_independent_audit_workspace_or_valid_exception: true
  all_required_groups_accepted_before_integration: true
  leader_integration_branch_derives_from_base_commit: true
  test_handoff_targets_integration_branch: true
  no_remote_push_or_pr_or_release: true
  final_execution_causal_handoff_present: true
```
