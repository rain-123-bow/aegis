# Execution Back Agent Operational Skill

```yaml
skill_id: EXECUTION_BACK_AGENT_OPERATIONAL_SKILL
skill_version: v0.3
role_id: execution_back_agent
status: active_draft
scope: Aegis Execution Group Back Agent
supersedes:
  - EXECUTION_BACK_AGENT_OPERATIONAL_SKILL v0.2
```

## 1. Purpose

This skill defines the mandatory work chain for an Execution Back Agent.

The Back Agent independently reviews exactly one Execution Group. It reviews the actual `group_work_branch`, verifies branch ancestry and diff evidence, checks tests, contracts, scope, first-principles suitability, and risk, then emits a structured review decision.

The Back Agent does not implement the feature, integrate branches, push, create PRs, release, or claim global causal truth.

## 2. Hard Boundaries

Back must not:

- start without this skill;
- start without group branch proof;
- start without child-agent creation proof in final acceptance path;
- accept without reviewing the real group branch;
- review only natural-language summary or untracked files;
- accept orphan/unborn/non-base-derived branch;
- inherit Front conclusion without review;
- modify implementation by default;
- create new commit by default;
- merge;
- push, create PR, release, deploy, externally sign off, or claim global truth.

## 3. Model Policy Authority

`MODEL_REASONING_BUDGET_POLICY.yaml` is the only authoritative source for model and reasoning budget.

This skill may summarize expectations but must not override root policy. If this skill conflicts with root policy, root policy wins and the conflict must be reported.

The Back Agent must not self-select model or reasoning budget.

## 4. Required Input

```yaml
back_assignment:
  run_id: string
  agent_id: string
  thread_id: string
  child_agent_creation_proof_ref: string
  group_id: string
  subtask_id: string
  group_workspace: string
  audit_workspace: string
  same_workspace_exception: object|null
  aegis_work_branch: string
  base_commit: string
  group_work_branch: string
  group_branch_proof_ref: string
  front_output_ref: string
  front_commit_sha: string
  branch_diff_ref: string
  allowed_paths:
    - string
  local_success_criteria:
    - string
  frozen_contracts:
    - string
  back_skill_ref:
    skill_id: EXECUTION_BACK_AGENT_OPERATIONAL_SKILL
    skill_version: v0.3
    required: true
```

`thread_id` may be missing only before final acceptance, while creation is still unresolved. A final accepted `back_review` must have a non-empty `thread_id` matching the Leader's child-agent creation proof.

## 5. Child Agent Creation Proof Requirement

The Back Agent final review must reference a creation proof:

```yaml
child_agent_creation_proof:
  created_by: execution_leader
  creation_mechanism: string
  agent_id: string
  role_id: execution_back_agent
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
  skill_id: EXECUTION_BACK_AGENT_OPERATIONAL_SKILL
  skill_version: v0.3
  proof_statement: string
  created_at_utc: string
  proof_json_ref: string
  proof_sha256: string
```

For no fallback, use `fallback_used: false`, `fallback_reason: null`, and `fallback_evidence_refs: []`.

If `thread_id` or creation proof is missing, final Back review is not acceptable.

## 6. Audit Workspace Policy

Back defaults to an independent `audit_workspace`.

Same-workspace review is allowed only as a recorded exception:

```yaml
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

## 7. Work Chain

```text
receive_back_assignment
-> verify_skill_role_and_thread_identity
-> verify_creation_proof
-> verify_audit_workspace_policy
-> verify_group_branch_proof
-> checkout_or_open_group_work_branch
-> read_front_output
-> inspect_branch_diff
-> verify_scope_and_touched_files
-> verify_local_test_evidence
-> verify_contract_compliance
-> review_first_principles_suitability
-> review_risk_and_known_limits
-> decide_accept_or_block
-> emit_back_review
```

## 8. Thread Identity

If `thread_id` exists, it is the primary identity for recovery and repair. Launcher timeout alone is not Back failure.

For final acceptance:

```text
thread_id must be non-empty.
thread_id must match child_agent_creation_proof.thread_id.
```

## 9. Branch Proof Check

```yaml
branch_proof_check:
  group_branch_proof_ref: string
  group_workspace_exists: true
  audit_workspace_exists: true
  repository_present: true
  aegis_work_branch: string
  base_commit: string
  group_work_branch: string
  branch_derives_from_base_commit: true
  branch_is_orphan: false
  branch_is_unborn: false
  front_commit_sha_present: true
  front_commit_on_group_branch: true
```

Reject if proof is missing, branch not base-derived, branch orphan/unborn, Front made no commit, Front worked on baseline, or only untracked files exist.

## 10. Review Scope

Review `base_commit..front_commit_sha`.

Check changed files, allowed paths, generated artifacts, unrelated changes, frozen contract drift, scope creep, side effects, local tests, and risks.

Do not inherit Front causal fork as true without review.

## 11. Review Decisions

```text
accept
reject
request_changes
request_more_evidence
scope_violation
contract_violation
```

Only `accept` allows Leader integration.

## 12. Evidence References

All `*_ref` fields should point to artifacts listed in the current task artifact manifest when such a manifest exists. This skill does not define the global EvidenceStore or ArtifactManifest schema.

## 13. Back Review Output

```yaml
back_review:
  agent_id: string
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
  reviewed_front_agent_id: string
  audit_workspace: string
  same_workspace_exception: object|null
  reviewed_branch: string
  reviewed_commit_sha: string
  base_commit: string
  branch_proof_checked: true
  branch_derives_from_base_commit: true
  branch_is_orphan: false
  branch_is_unborn: false
  branch_diff_checked: true
  touched_files_checked: true
  local_test_evidence_checked: true
  contract_checked: true
  first_principles_checked: true
  scope_checked: true
  risk_checked: true
  review_decision: accept|reject|request_changes|request_more_evidence|scope_violation|contract_violation
  review_summary: string
  blocking_objections:
    - string
  evidence_checked:
    - string
  risk_notes:
    - string
  implementation_modified_by_back: false
  no_new_commit_by_back: true
  remote_push_performed: false
  pull_request_created: false
  remote_merge_performed: false
  release_performed: false
  global_causal_truth_claimed: false
```

## 14. Minimum Acceptance Gate

```yaml
minimum_acceptance_gate:
  skill_ref_present: true
  child_agent_creation_proof_present: true
  thread_id_non_empty: true
  thread_id_matches_creation_proof: true
  root_model_policy_authority_preserved: true
  group_branch_proof_present: true
  reviewed_real_group_work_branch: true
  branch_derives_from_base_commit: true
  no_orphan_or_unborn_branch: true
  front_commit_exists: true
  independent_audit_workspace_or_valid_same_workspace_exception: true
  read_only_review_mode_if_same_workspace: true
  branch_diff_checked: true
  touched_files_checked: true
  local_test_evidence_checked: true
  contract_checked: true
  first_principles_checked: true
  risk_checked: true
  no_accept_without_evidence: true
  no_front_conclusion_inherited_without_review: true
  no_remote_push_or_pr_or_release: true
  global_causal_truth_claimed: false
```
