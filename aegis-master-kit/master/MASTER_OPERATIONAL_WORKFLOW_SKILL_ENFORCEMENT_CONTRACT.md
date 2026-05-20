# Master Operational Workflow Skill Enforcement Contract

## 1. Purpose

Phase 24A upgrades the Master operational workflow from a passive contract set into a role-bound, always-on skill boundary.

This contract defines the minimum validation artifact Master must produce or pass before a substantive project-facing response, department dispatch, state-store update, or commit candidate is treated as governed by Aegis.

The contract enforces the visible operational work chain. It does **not** store raw model chain-of-thought.

## 2. Authority

The authoritative skill file is:

```text
aegis-master-kit/master/MASTER_OPERATIONAL_WORKFLOW_SKILL.md
```

Master must treat this skill as mandatory for every substantive user/project interaction.

This skill supersedes duplicated prose in older Master-facing documents when the older prose is less strict. Older contracts remain valid as source contracts unless explicitly removed in a later cleanup phase.

## 3. Required Master cycle artifact

A Master operational cycle artifact is a JSON object with at least:

```yaml
skill_ref:
  skill_id: MASTER_OPERATIONAL_WORKFLOW_SKILL
  skill_version: v0.3
cycle_id: string
master_role_id: master
user_input_classification: string
requires_task: bool
requires_archive_event: bool
requires_knowledge_candidate: bool
requires_causal_candidate: bool
requires_department_dispatch: bool
requires_commit_gate: bool
task_boundary:
  decision: create|bind|aggregate|split|planning_only|reject|defer|question_only
  reasoning_summary: string
  final_archive_task_ids:
    - TASK-...
  existing_archived_tasks_merged: false
  aggregation_after_archive: false
  commit_candidate_task_id: string|null
  commit_candidate_count: integer
  split_commit_count: integer
model_policy_resolution:
  - role_id: string
    requested_model: gpt-5.5|gpt-5.4
    resolved_model: gpt-5.5|gpt-5.4
    requested_reasoning_budget: high|extra_high
    resolved_reasoning_budget: high|extra_high
    policy_reasoning_budget: high|extra_high
    fallback_used: bool
    fallback_reason: string|null
    fallback_evidence_refs:
      - string
archive_event_candidates:
  - object
knowledge_candidates:
  - object
causal_candidates:
  - object
department_dispatch:
  target_department: debate|execution|test|final_review|null
  master_created_top_level_leader_only: bool
  master_created_internal_worker: false
  model_policy_checked: bool
supervision:
  nested_codex_timeout_state: none|launcher_timeout|child_thread_alive|child_completed_late|result_recovered|child_failed|proof_missing_after_final_deadline
  thread_id_recorded: bool
  recovery_attempted: bool
commit_gate:
  commit_candidate_requested: bool
  exactly_one_archive_task_per_commit: bool
  developer_authorization_required: bool
  remote_push_performed: false
  pr_created: false
  remote_merge_performed: false
  release_performed: false
responsibility_boundary:
  developer_retains_remote_push: true
  developer_retains_main_merge: true
  developer_retains_release: true
  developer_retains_external_signoff: true
```

## 4. Required rejection / blocked states

The Master cycle must be rejected or blocked when:

- `skill_ref` is missing or does not name this skill;
- `master_role_id` is not `master`;
- a task-like input has no task boundary decision;
- an executable task lacks an Archive event candidate;
- an already archived task is merged into another task;
- aggregation occurs after archival task creation;
- a commit candidate is not bound to exactly one final Archive task;
- a model below `gpt-5.4` is requested or resolved;
- fallback from `gpt-5.5` to `gpt-5.4` lacks evidence;
- reasoning budget is downgraded;
- provider-default model fallback is used without explicit model resolution;
- Master directly creates internal workers instead of only top-level Leaders;
- a `launcher_timeout` is treated as final child-agent failure without recovery/final deadline;
- a remote push, PR, remote merge, release, or external sign-off is performed by Master.

## 5. Task identity rules

Archive tasks are commit-bound.

```text
one final Archive task <-> one final git commit candidate
```

Master may aggregate multiple not-yet-archived user inputs into one final Archive task only before formal Archive task creation.

Master may split one user request into multiple final Archive tasks when correct engineering output requires multiple commits.

Existing archived tasks must not be merged.

Planning hierarchy may be arbitrary-depth, but final Archive task identities must remain commit-bound.

## 6. Model fallback rules

Primary model is `gpt-5.5`.

If `gpt-5.5` is objectively unavailable, `gpt-5.4` is allowed only when:

- the fallback is explicit;
- the fallback is recorded;
- evidence is provided;
- the reasoning budget is unchanged;
- the resolved model is not below `gpt-5.4`.

Reasoning budget downgrade is always forbidden.

## 7. Runtime boundary

Phase 24A validates Master operational skill usage only.

It does not create a production scheduler, production persistent workflow engine, production global causal merge, remote push, PR, release, or external sign-off authority.

## 8. Acceptance label

A successful Phase 24A validation may be labeled:

```text
accepted_master_operational_workflow_skill_enforcement
```

It must not be labeled:

```text
production_master_autonomy_closure
production_release_authority_closure
global_causal_truth_merge_closure
```
