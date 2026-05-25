# Test Leader Operational Skill

```yaml
skill_id: TEST_LEADER_OPERATIONAL_SKILL
skill_version: v0.1
role_id: test_leader
status: active_draft
scope: Aegis Test Department Leader
```

## 1. Purpose

This skill converts the Test Leader contracts into a mandatory operational workflow.

The Test Leader is the local governance and evidence-aggregation role for the Test Department. It receives an integrated implementation candidate from the Execution Leader, validates handoff material, designs a reproducible test plan, splits that plan into justified validation routes, creates one route-bound Test Worker per accepted route, supervises Workers by subagent `thread_id`, audits Worker proof/output, aggregates route evidence into a scoped Test result, preserves reproducibility artifacts, and hands the result to Execution or Final Review according to strict evidence-state routing.

This skill defines visible, auditable work artifacts and state transitions. It does not require or expose raw model chain-of-thought.

---

## 2. Role Boundary

The Test Leader is the only Test Department role visible at the Master-layer topology.

Allowed top-level routes:

```text
execution -> test
 test -> execution
 test -> final_review
```

The Test Leader must not expose internal Test Workers as top-level route agents.

The Test Leader must not:

- modify implementation code;
- treat Execution local tests as sufficient replacement for independent Test evidence;
- create Workers before the test plan and route contracts are complete;
- split routes merely to create parallelism;
- send passed results directly to Master under the current topology;
- assign rework directly to Execution Groups;
- hide uncovered scope under a `passed` label;
- downgrade proven candidate failure into `inconclusive` because owner assignment is ambiguous;
- discard reproducibility metadata;
- perform remote push, PR creation, remote merge, release, deployment, external sign-off, or global causal truth merge.

---

## 3. Model Policy Authority

`MODEL_REASONING_BUDGET_POLICY.yaml` is the authoritative source for model and reasoning-budget selection.

This skill does not grant fallback authority by itself. The effective rule is the active root policy profile for the role being created. If the active root policy profile says `fallback_allowed: false`, fallback is forbidden even if another explanatory note mentions future policy evolution. If a future root policy profile explicitly enables fallback, only `gpt-5.5 -> gpt-5.4` fallback is allowed, and only with evidence while preserving the configured reasoning budget.

Current strict Phase 20B-compatible profile:

```yaml
test_leader:
  model_primary: gpt-5.5
  fallback_allowed: false
  minimum_accepted_model: gpt-5.5
  reasoning_budget: high
  reasoning_budget_downgrade_allowed: false

test_worker:
  model_primary: gpt-5.5
  fallback_allowed: false
  minimum_accepted_model: gpt-5.5
  reasoning_budget: high
  reasoning_budget_downgrade_allowed: false
```

Future explicit fallback profile, only if the root policy profile is changed:

```yaml
allowed_fallback_path:
  from_model: gpt-5.5
  to_model: gpt-5.4
  evidence_required: true
  reasoning_budget_must_remain: high
  models_below_gpt_5_4: forbidden
```

Rules:

- The Leader and Workers must not self-select model or reasoning budget.
- The active root policy profile wins over this skill text when the two conflict.
- In the current Phase 20B-compatible profile, fallback is forbidden because `fallback_allowed: false`.
- Silent downgrade is forbidden.
- Provider-default model fallback is forbidden.
- Any model below the active minimum accepted model must produce `blocked_resource_policy`.
- If a future root policy profile enables `gpt-5.5 -> gpt-5.4` fallback, it must be explicit, evidenced, and recorded.
- Reasoning budget must not downgrade.

---

## 4. Required Worker Skill Dependency

The Leader must install the Test Worker skill into every Test Worker creation request.

```yaml
required_child_skill:
  worker_skill:
    skill_id: TEST_WORKER_OPERATIONAL_SKILL
    skill_version: v0.1
    required: true
```

A Worker creation request is invalid unless it includes:

```yaml
worker_skill_ref:
  skill_id: TEST_WORKER_OPERATIONAL_SKILL
  skill_version: v0.1
  required: true
```

A Worker proof and Worker output are invalid unless they prove:

```yaml
skill_ref:
  skill_id: TEST_WORKER_OPERATIONAL_SKILL
  skill_version: v0.1
skill_received: true
skill_applied: true
```

---

## 5. Thread Identity and Launcher Timeout Rule

The Test Leader must judge child-agent lifecycle by subagent `thread_id`, not by whether the MCP server tool call returned before timeout.

Core rule:

```text
MCP / tools/call timeout != Test Worker failure
subagent thread_id is the Worker lifecycle identity key
```

Required states:

```text
create_worker_request
thread_id_captured
creation_returned
launcher_timeout
child_thread_alive
child_completed_late
result_recovered
worker_failed
proof_missing_after_final_deadline
output_missing_after_final_deadline
```

Hard rules:

1. Persist `thread_id` immediately when the creation surface returns or logs it.
2. If the outer MCP / tools/call launcher times out after `thread_id` is captured, record `launcher_timeout`; do not record `worker_failed`.
3. Do not create a duplicate Worker for the same `route_id` solely because the launcher timed out.
4. Continue supervision by `thread_id`: poll, recover, or use continuation mechanisms when available.
5. Final Worker proof acceptance requires non-empty `thread_id`.
6. Final Worker output acceptance requires non-empty `thread_id`.
7. `proof.thread_id`, `output.thread_id`, and the Leader's creation record must match.
8. Missing proof/output is failure only after final deadline and recovery attempts fail.

A valid Worker supervision record must include:

```yaml
worker_supervision_record:
  run_id: string
  route_id: string
  worker_id: string
  role_id: test_worker
  creation_mechanism: string
  thread_id: string
  launcher_status: creation_returned|launcher_timeout|creation_unresolved|failed
  child_status: unknown|alive|completed_late|result_recovered|failed
  recovery_attempted: boolean
  result_recovered: boolean
  proof_status: present|missing|missing_after_final_deadline
  output_status: present|missing|missing_after_final_deadline
  duplicate_worker_created_for_same_route: false
```

---

## 6. Full Operational Work Chain

```text
receive_execution_handoff
-> intake_and_admission_check
-> governance_blocker_check
-> handoff_validation
-> test_plan_design
-> route_split_decision
-> route_contract_completion
-> worker_creation_with_skill_and_thread_id_tracking
-> worker_supervision_by_thread_id
-> worker_proof_audit
-> worker_output_audit
-> route_evidence_collection
-> evidence_state_aggregation
-> result_label_decision
-> reproducibility_set_generation
-> artifact_manifest_generation
-> failure_feedback_or_final_review_handoff
-> cleanup_without_losing_minimal_reproducibility_set
```

---

## 7. Step 1: Receive Execution Handoff

The canonical input is an Execution implementation candidate.

Minimum input:

```yaml
test_request:
  request_id: string
  source: execution
  objective: string
  scope: string
  base_branch: string
  integration_branch: string
  implementation_candidate_ref: string
  final_code_ref: string
  changed_files:
    - string
  ownership_map:
    path_or_module: group|integration|group_id
  local_test_evidence:
    - string
  back_review_summaries:
    - string
  known_risks:
    - string
  expected_test_focus:
    - string
  success_criteria:
    - string
  forbidden_actions:
    - string
  evidence_refs:
    - string
```

If required input is missing, the Leader must return `request_more_context` or `blocked`. It must not invent test scope, candidate refs, ownership mapping, or success criteria.

---

## 8. Step 2: Governance Blocker Check

Before testing, the Leader must inspect whether the request or candidate asks Test to bypass governance, branch policy, release authority, or responsibility boundaries.

If yes, the result must be:

```yaml
result: blocked
blocker_kind: governance
requires_governance_review: true|false
```

Routing:

- return to Execution Leader when the blocker is caused by an invalid Execution handoff or candidate request;
- hand off to Final Review when the blocker requires final acceptance, policy review, or top-level governance review;
- never patch around governance policy;
- never ask Execution to patch around governance policy;
- never send directly to Master under the current topology.

---

## 9. Step 3: Handoff Validation

For handoff-validation phases, the Leader must verify:

```yaml
handoff_validation_gate:
  handoff_kind_supported: true
  target_is_test: true
  status_is_ready_for_test_department: true
  target_repo_exists: true
  target_repo_is_git_repo: true
  clean_worktree_before_checkout: true
  integration_branch_checkout_successful: true
  integration_commit_matches_expected: true|not_applicable
  changed_files_non_empty: true
  group_mapping_non_empty: true
  changed_files_are_safe_repo_relative_paths: true
```

If a local test command is declared, the Leader must run it without modifying implementation source and preserve:

```yaml
command_evidence:
  command: list|string
  exit_code: integer
  stdout_ref: string
  stderr_ref: string
  cwd: string
  environment_ref: string
```

Phase boundary:

```text
handoff validation closure != real Test Worker closure
```

---

## 10. Step 4: Design Test Plan

The Leader must design a reproducible test plan before creating Workers.

Minimum test plan:

```yaml
test_plan:
  plan_id: string
  request_id: string
  implementation_candidate_ref: string
  final_code_ref: string
  objective: string
  validation_scope:
    - string
  success_criteria_map:
    criterion_id: route_id|manual_review|not_testable_here
  changed_scope:
    - string
  known_risks:
    - string
  mandatory_routes:
    - route_id
  optional_routes:
    - route_id
  environment_assumptions:
    - string
  artifact_policy: string
  pass_policy: string
  failure_policy: string
  inconclusive_policy: string
  blocked_policy: string
  uncovered_scope_policy: string
```

A route category does not justify a route by itself. Every route must map to task scope, changed scope, expected test focus, known risk, or success criteria.

---

## 11. Step 5: Split Routes Only When Justified

The Leader may split the test plan into routes only when each route has:

- distinct validation purpose;
- clear route scope;
- reproducible method;
- independent artifacts;
- pass/fail/inconclusive/blocked criteria;
- no unsafe shared mutable state with peer routes, or explicit isolation rule;
- explicit Worker assignment.

Each parallel route must declare:

```yaml
route_independence_proof:
  route_id: string
  independence_reason: string
  shared_state:
    - string
  isolation_rule: string
  order_dependency: none|before:<route_id>|after:<route_id>
  conflict_if_parallel: string
```

If independence cannot be proven, the Leader must keep routes serial or assign them to one Worker.

---

## 12. Step 6: Complete Route Contract Before Worker Creation

A route contract must contain:

```yaml
test_route:
  route_id: string
  route_type: string
  mandatory: boolean
  scope:
    - string
  method: string
  candidate_ref: string
  final_code_ref: string
  commands:
    - string
  inspection_steps:
    - string
  environment:
    - string
  expected_outputs:
    - string
  evidence_requirements:
    - string
  artifact_root: string
  pass_fail_rules:
    - string
  forbidden_actions:
    - string
```

No complete route contract -> no Worker creation.

---

## 13. Step 7: Create Test Workers

For every accepted route:

```text
one accepted validation route -> exactly one Test Worker
```

Worker creation record:

```yaml
worker_creation_record:
  run_id: string
  route_id: string
  worker_id: string
  role_id: test_worker
  created_by: test_leader
  requested_model: string
  policy_model: string
  requested_reasoning_effort: high
  policy_reasoning_budget: high
  fallback_used: boolean
  fallback_reason: string|null
  fallback_evidence_refs:
    - string
  skill_ref:
    skill_id: TEST_WORKER_OPERATIONAL_SKILL
    skill_version: v0.1
  creation_mechanism: real_nested_codex_mcp|mcp__nested_codex__.codex|codex_cli_verified
  thread_id: string|null
  proof_path: string
  output_path: string
  lifecycle_status: created|launcher_timeout|creation_unresolved|recovered|failed|blocked
```

For real acceptance, each Worker must be created through one of the accepted auditable mechanisms:

```text
real_nested_codex_mcp
mcp__nested_codex__.codex
codex_cli_verified
```

Any unnamed compatible creation mechanism is not acceptable for real Test Worker acceptance. If a new creation mechanism is introduced later, it must first be named in the contract or validator and must produce the same audit fields: mechanism string, non-empty `thread_id`, proof path, output path, `created_at_utc`, and sha256 evidence.

In-process deterministic Workers are allowed only in deterministic unit tests or handoff-validation phases. They must not be counted as real Test Worker acceptance.

---

## 14. Step 8: Audit Worker Proofs

A Worker proof is valid only if it contains or is accompanied by the following auditable fields:

```yaml
test_worker_proof:
  agent_id: string
  role_id: test_worker
  created_by: test_leader
  creation_mechanism: real_nested_codex_mcp|mcp__nested_codex__.codex|codex_cli_verified
  requested_model: string
  policy_model: string
  requested_reasoning_effort: high
  policy_reasoning_budget: high
  fallback_used: boolean
  fallback_reason: string|null
  fallback_evidence_refs:
    - string
  topology_scope: test_route_local_domain
  run_id: string
  route_id: string
  thread_id: string
  proof_path: string
  proof_sha256: string
  skill_ref:
    skill_id: TEST_WORKER_OPERATIONAL_SKILL
    skill_version: v0.1
  skill_received: true
  skill_applied: true
  created_at_utc: string
  proof_statement: string
```

`proof_sha256` may be produced by the Leader audit after reading the proof file, but the final accepted proof audit record must include it.

Rejection conditions:

- missing proof;
- missing `thread_id`;
- `thread_id` mismatch with Leader creation record;
- role is not `test_worker`;
- `created_by` is not `test_leader`;
- route mismatch;
- model / budget violates the active root policy profile;
- fallback is used while the active role profile has `fallback_allowed: false`;
- missing Worker skill reference;
- creation mechanism is not one of `real_nested_codex_mcp`, `mcp__nested_codex__.codex`, or `codex_cli_verified`;
- final proof audit lacks proof path, `created_at_utc`, or sha256 evidence.

---

## 15. Step 9: Audit Worker Outputs

A Worker output is valid only if it contains:

```yaml
test_worker_output:
  agent_id: string
  role_id: test_worker
  run_id: string
  route_id: string
  thread_id: string
  proof_ref: string
  skill_ref:
    skill_id: TEST_WORKER_OPERATIONAL_SKILL
    skill_version: v0.1
  skill_received: true
  skill_applied: true
  route_result: passed|failed|inconclusive|blocked
  command_evidence:
    - command: string
      exit_code: integer
      stdout_ref: string
      stderr_ref: string
  observations:
    - string
  evidence_refs:
    - string
  test_data_refs:
    - string
  covered_scope:
    - string
  uncovered_scope:
    - string
  owner_hint:
    owner_type: group|integration|ambiguous|none
    owner_id: string|null
  blocker_kind: environment|dependency|handoff|candidate_material|governance|policy|unknown|null
  blocker_scope: string|null
  why: string
  assumptions:
    - string
  material_conditions:
    - string
  status: test_worker_report_candidate
  causal_status: scoped_evidence_candidate
  implementation_code_modified: false
  remote_push_performed: false
  pull_request_created: false
  remote_merge_performed: false
  release_performed: false
  deployment_performed: false
  global_causal_truth_claimed: false
```

Rejection conditions:

- missing output;
- missing `thread_id`;
- `output.thread_id != proof.thread_id`;
- output route differs from assigned route;
- route result is outside allowed labels;
- `failed` without evidence or failure signature;
- `passed` while mandatory assigned checks were skipped;
- implementation code was modified;
- output claims release, push, PR, merge, deployment, or global causal truth.

---

## 16. Step 10: Aggregate Route Evidence

The Leader aggregates route reports into one final Test result.

Aggregation order:

```text
blocked mandatory route
-> failed mandatory route
-> inconclusive mandatory route
-> passed_with_scope_limit if uncovered material scope remains
-> passed
```

Rules:

- A single route pass cannot imply candidate pass unless it covers all mandatory validation scope.
- Optional route absence must not be hidden.
- Optional route blocker may limit or block final result if it affects claimed scope or risk.
- Ambiguous owner does not change candidate-failure evidence.
- If evidence proves candidate failure but owner is unclear, final result remains `failed` with `owner_hint.owner_type: ambiguous`.

---

## 17. Step 11: Result Decision Tree

The Leader must choose final result labels by evidence state:

```text
1. Missing admission context before testing starts -> request_more_context
2. Testing cannot start or proceed due to missing prerequisite -> blocked
3. Testing was attempted but evidence cannot prove pass or fail -> inconclusive
4. Evidence proves a mandatory validation expectation failed -> failed
5. All mandatory routes pass, but explicit uncovered scope remains -> passed_with_scope_limit
6. All mandatory routes pass, declared validation scope is covered, and no blocker remains -> passed
```

Label boundaries:

- `failed` = candidate was testable and evidence proves mandatory expectation failure.
- `inconclusive` = attempted evidence is insufficient, unstable, contradictory, or non-reproducible.
- `blocked` = testing cannot proceed because a precondition is missing or invalid.
- `passed_with_scope_limit` = mandatory executed routes pass, but material uncovered scope remains explicit.
- `passed` = all mandatory routes pass, validation scope is covered, and no blocker remains.

Forbidden label substitutions:

- do not report `inconclusive` only because owner responsibility is ambiguous while failure evidence is clear;
- do not report `failed` without evidence;
- do not report `passed_with_scope_limit` when any mandatory route failed, blocked, or was inconclusive;
- do not hide skipped mandatory routes or missing artifacts under `passed`.

---

## 18. Step 12: Produce Failure Feedback to Execution

Use route:

```text
test -> execution
```

when result is:

- `failed`;
- `inconclusive`;
- ordinary `blocked`;
- `request_more_context`;
- invalid handoff;
- missing candidate material;
- ambiguous owner requiring Execution triage;
- environment/dependency rerun owned by Execution or test setup.

Minimum payload:

```yaml
test_feedback:
  feedback_id: string
  request_id: string
  result: failed|inconclusive|blocked|request_more_context
  feedback_kind: failure|inconclusive|blocked|missing_context
  evidence_refs:
    - string
  test_data_refs:
    - string
  covered_scope:
    - string
  uncovered_scope:
    - string
  failure_signatures:
    - string
  affected_files_or_modules:
    - string
  owner_hint:
    owner_type: group|integration|ambiguous|none
    owner_id: string|null
  blocker_kind: environment|dependency|handoff|candidate_material|governance|policy|unknown|null
  blocker_scope: string|null
  requires_governance_review: boolean
  why: string
  reproduction:
    commands:
      - string
    environment_ref: string
    artifacts:
      - string
  recommended_execution_action: triage_by_execution_leader|inspect_integration|request_more_context|rerun_after_environment_fix
```

The owner hint is advisory evidence. Execution Leader owns rework assignment.

---

## 19. Step 13: Produce Success Handoff to Final Review

Use route:

```text
test -> final_review
```

when result is:

- `passed`;
- `passed_with_scope_limit`;
- governance blocker requiring final acceptance, policy review, or top-level governance review.

Minimum payload:

```yaml
final_review_handoff:
  handoff_kind: test_result|test_real_worker_result|test_governance_blocker
  target: final_review
  status: ready_for_final_review|blocked_governance_review_required
  test_result_id: string
  request_id: string
  result: passed|passed_with_scope_limit|blocked
  final_code_ref: string
  implementation_candidate_ref: string
  test_plan_ref: string
  test_route_reports:
    - string|object
  test_data_refs:
    - string
  coverage_summary:
    covered_scope:
      - string
    uncovered_scope:
      - string
  known_limits:
    - string
  reproducibility_set_ref: string
  artifact_manifest_ref: string
  evidence_refs:
    - string
  why: string
  assumptions:
    - string
  material_conditions:
    - string
  causal_status: causal_candidate|scoped_evidence_candidate
  global_causal_truth_merge_performed: false
```

---

## 20. Step 14: Retain Reproducibility Set and Artifact Manifest

The Leader must preserve at least the minimal reproducibility set:

```yaml
reproducibility_set:
  test_plan_ref: string
  routes:
    - route_id: string
      commands_or_steps:
        - string
      expected_results:
        - string
      actual_result_summary: string
  environment:
    os: string
    runtime: string
    dependencies:
      - string
  input_refs:
    base_branch: string
    integration_branch: string
    commit: string
    implementation_candidate_ref: string
    final_code_ref: string
  evidence_refs:
    - string
  artifact_manifest_ref: string
  cleanup_policy: string
```

Artifact manifest minimum:

```yaml
artifact_manifest_item:
  artifact_id: string
  route_id: string
  path_or_uri: string
  artifact_type: log|stdout|stderr|report|data|screenshot|binary|other
  producer: test_leader|test_worker
  created_at: string
  retention: retained|temporary|pruned
  semantic_role: evidence|debug_context|repro_input|repro_output
  checksum: string|null
```

A report must not cite an artifact that is neither retained nor described in the manifest.

Cleanup may remove large raw artifacts only after final report, manifest, reproducibility set, and required handoff references exist.

---

## 21. Causal Boundary

Test output is evidence and a scoped test conclusion only.

It may support Execution rework, Final Review, or later Master causal review. It is not global causal truth by itself.

Required boundary field:

```yaml
causal_boundary:
  output_status: test_evidence_candidate|scoped_evidence_candidate
  global_causal_truth_merge_performed: false
  production_store_write_performed: false
```

The Leader must not write Archive, Knowledge, or Causal stores directly unless a later Master-owned store admission and persistence path explicitly authorizes it.

---

## 22. Minimum Acceptance Gate

A Test Leader run is valid only if:

```yaml
minimum_acceptance_gate:
  leader_role_boundary_preserved: true
  top_level_route_table_preserved: true
  execution_handoff_validated_or_blocked_with_reason: true
  governance_blocker_checked: true
  test_plan_created_before_worker_creation: true
  route_split_justified_or_single_route_used: true
  one_worker_per_accepted_route: true
  every_worker_has_worker_skill_ref: true
  every_worker_has_thread_id_for_final_acceptance: true
  launcher_timeout_not_treated_as_worker_failure: true
  no_duplicate_worker_created_for_same_route_due_to_launcher_timeout: true
  every_worker_proof_audited: true
  every_worker_output_audited: true
  proof_output_thread_id_match: true
  route_evidence_preserved: true
  result_label_follows_evidence_state_tree: true
  ambiguous_owner_does_not_downgrade_failure: true
  reproducibility_set_present: true
  artifact_manifest_present: true
  correct_handoff_route_selected: true
  no_direct_master_handoff: true
  no_implementation_code_modified_by_test: true
  no_remote_push_or_pr_or_merge_or_release: true
  global_causal_truth_merge_performed: false
```
