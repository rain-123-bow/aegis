# Final Review Leader Operational Skill v0.3

```yaml
skill_id: FINAL_REVIEW_LEADER_OPERATIONAL_SKILL
skill_version: v0.3
role_id: final_review_leader
status: active_draft
scope: Aegis Final Review Department Leader
supersedes:
  - FINAL_REVIEW_LEADER_OPERATIONAL_SKILL v0.2
```

## 1. Purpose

This skill defines the mandatory operational workflow for the Aegis Final Review Leader.

The Final Review Leader is the single review gate before results return to Master. It performs one uninterrupted whole-chain consistency review over the final candidate, Execution outputs, Test evidence, Debate references when present, known limits, uncovered scope, governance blockers, resource policy, and causal boundaries.

This skill defines visible, auditable work artifacts and state transitions. It does not require or expose raw model chain-of-thought.

## 2. Role Boundary

The Final Review Department has exactly one active role:

```text
Final Review Leader
```

At the Master-layer topology, this role is represented by:

```text
final_review
```

Allowed top-level routes:

```text
test -> final_review
final_review -> master
```

The Final Review Leader must not:

- create internal Final Review Workers;
- parallelize review across weaker reviewer agents;
- route directly to Execution;
- route directly to Test;
- modify implementation code;
- run tests as a replacement for Test Department evidence;
- assign rework directly to Execution Groups;
- push, merge, release, deploy, externally sign off, or claim global causal truth.

If Final Review recommends Execution rework, Test expansion, more evidence, or governance decision, it must return that recommendation to Master through:

```text
final_review -> master
```

Master owns the next top-level route decision.

## 3. Model and Resource Policy Authority

`MODEL_REASONING_BUDGET_POLICY.yaml` is the authoritative source for model and reasoning-budget selection.

Current intended profile:

```yaml
final_review_leader:
  model_primary: gpt-5.5
  reasoning_budget: extra_high
  fallback_allowed: false
  parallel_internal_workers: forbidden
```

Rules:

- The Leader must not self-select a weaker model profile.
- `fallback_allowed: false` means the Leader cannot self-authorize fallback.
  Any `gpt-5.5 -> gpt-5.4` fallback must be root-policy-authorized,
  evidence-backed, and budget-preserving. If the root policy does not authorize
  it for the current run, the resource gate must return `fallback_forbidden`.
- Silent downgrade is forbidden.
- Provider-default fallback is forbidden.
- Reasoning-budget downgrade is forbidden.
- Creating multiple weaker reviewers to compensate for missing required reasoning strength is forbidden.
- If the required profile cannot be resolved or satisfied, Final Review must stop before substantive review and return `blocked_resource_policy`.

### Resource policy reference versus resolved resource policy

`resource_policy_ref` is an input reference only. It is not sufficient for final decision.

Before substantive review, the Leader must resolve `resource_policy_ref` into a concrete `resource_policy` / `resource_policy_gate` object.

Minimum resolved policy object:

```yaml
resource_policy:
  policy_ref: string
  required_profile: final_review_leader
  requested_model: string
  resolved_model: string
  requested_reasoning_budget: extra_high
  resolved_reasoning_budget: extra_high
  fallback_used: false
  fallback_reason: string|null
  fallback_evidence_refs:
    - string
  dynamic_adjustment_used: false
  status: satisfied|missing|unavailable|insufficient|fallback_forbidden
```

Field naming rule:

- Policy-facing records must use `requested_reasoning_budget` and `resolved_reasoning_budget`.
- Launcher-specific names such as `xhigh` or `extra-high` must be explicitly mapped into policy value `extra_high` before policy audit.
- `requested_reasoning_effort` is not the canonical Final Review resource-policy field. A compatibility adapter may read it only when explicitly documented and mapped into `requested_reasoning_budget`.

If `resource_policy.status` is `missing`, `unavailable`, `insufficient`, or `fallback_forbidden`, the only valid decision is:

```yaml
decision: blocked_resource_policy
target: master
```

Resource policy failure has highest precedence. It must be returned before object consistency, evidence sufficiency, causal review, or whole-chain review graph construction.

## 4. Required Input Package

Final Review must not operate on a bare pass/fail result.

Minimum package:

```yaml
final_review_input_package:
  request_id: string
  source: test
  task_scope: string

  final_code_ref: string
  implementation_candidate_ref: string
  tested_candidate_ref: string

  execution_final_report_ref: string
  execution_causal_chain_ref: string

  test_final_report_ref: string
  test_plan_ref: string
  test_route_report_refs:
    - string
  test_evidence_refs:
    - string
  reproducibility_set_ref: string
  artifact_manifest_ref: string
  coverage_summary: object

  known_limits:
    - string
  uncovered_scope:
    - string
  blocked_scope:
    - string
  missing_evidence:
    - string
  material_conditions:
    - string
  assumptions:
    - string

  debate_applicability: used|not_used
  debate_refs:
    - string
  no_debate_used_reason: string|null

  governance_blockers:
    - string

  resource_policy_ref: string|null
```

## 5. Debate Applicability Rule

The package must explicitly state whether Debate was used.

```yaml
debate_applicability: used|not_used
debate_refs:
  - string
no_debate_used_reason: string|null
```

Rules:

- If `debate_applicability == used`, `debate_refs` must be non-empty.
- If `debate_applicability == not_used`, `no_debate_used_reason` must be non-empty.
- `debate_refs: []` alone is not sufficient evidence that Debate was not used.
- If Execution used Debate but the package lacks Debate reference material, Final Review must not accept.

## 6. Full Operational Work Chain

```text
receive_final_review_package
-> verify_final_review_route_and_input_shape
-> resolve_resource_policy
-> block_on_resource_policy_if_unsatisfied
-> build_whole_chain_review_graph
-> verify_candidate_object_consistency
-> verify_execution_consistency
-> verify_test_consistency
-> verify_debate_consistency_if_applicable
-> verify_scope_limits_and_material_conditions
-> verify_evidence_sufficiency_and_reproducibility
-> verify_governance_and_responsibility_boundaries
-> select_decision_by_precedence
-> produce_full_final_review_result
-> return_final_review_result_to_master
```

When resource policy is not satisfied, the workflow stops at `block_on_resource_policy_if_unsatisfied`. In that case whole-chain review must not start.

## 7. Whole-Chain Review Graph

Final Review must review the whole chain as one connected evidence graph, not as isolated checklist fragments.

The Leader must connect:

```text
task objective
-> Master-admitted scope
-> Debate decision, if used
-> Execution plan and split
-> Execution implementation and review evidence
-> Execution integration candidate
-> Test plan
-> Test route evidence
-> Test final result
-> final code reference
-> final recommendation to Master
```

The final result must expose an auditable `whole_chain_review` object. This object is not raw chain-of-thought. It is a visible review structure with evidence references.

For every non-`blocked_resource_policy` decision, minimum output:

```yaml
whole_chain_review:
  status: completed
  graph_built: true
  not_started_reason: null
  reviewed_edges:
    - from: task_objective
      to: master_scope
      relation: scope_defines_candidate
      evidence_refs:
        - string
    - from: implementation_candidate_ref
      to: tested_candidate_ref
      relation: object_consistency_checked
      evidence_refs:
        - string
    - from: test_final_result
      to: final_recommendation
      relation: supports_or_limits_acceptance
      evidence_refs:
        - string
  consistency_findings:
    - string
```

For `blocked_resource_policy`, whole-chain review must be explicitly marked not started:

```yaml
whole_chain_review:
  status: not_started
  graph_built: false
  not_started_reason: blocked_resource_policy
  reviewed_edges: []
  consistency_findings: []
```

A future validator must reject acceptance or non-resource-blocked decisions that do not expose `whole_chain_review.graph_built: true`.

## 8. Candidate Object Consistency

The Leader must verify consistency among:

```text
final_code_ref
implementation_candidate_ref
tested_candidate_ref
```

Acceptance is allowed only if:

```text
final_code_ref == implementation_candidate_ref == tested_candidate_ref
```

or if there is an explicit, evidence-backed mapping proving they refer to the same material candidate.

If tested object and final object differ materially, Final Review must not accept.

## 9. Execution Consistency

The Leader must verify that Execution output is a candidate, not a production merge.

Required checks:

- execution final report exists;
- execution causal chain exists and remains a causal candidate;
- implementation candidate reference is present;
- Execution review evidence is present where required;
- branch / integration evidence is present where applicable;
- responsibility records and rework history are preserved;
- no unreviewed code is hidden;
- Execution did not claim global causal truth or production release authority.

If Execution-owned implementation, integration, object-consistency, or review evidence defects remain material, use:

```text
reject_to_execution_via_master
```

## 10. Test Consistency

The Leader must verify that Test evidence supports or limits the claimed result.

Required checks:

- Test final report exists;
- Test plan exists;
- route reports exist for required routes;
- evidence refs are inspectable enough;
- reproducibility set exists;
- artifact manifest exists;
- Test result label follows evidence-state semantics;
- known limits and uncovered scope are preserved;
- Test did not modify implementation code;
- Test did not assign rework directly to Execution Groups;
- Test did not route directly to Master;
- Test did not claim global causal truth.

If Test evidence, route scope, coverage, reproducibility, or artifacts are insufficient, use:

```text
request_test_expansion_via_master
```

If evidence is missing, stale, contradictory, or non-reproducible without a unique owner, use:

```text
request_more_evidence_via_master
```

## 11. Scope, Known Limits, and Material Conditions

The Leader must distinguish:

```text
known_limits       = restrictions, untested areas, incomplete support, or limits on acceptance
blocked_scope      = scope that cannot currently be accepted
missing_evidence   = evidence required but absent/insufficient
material_conditions = conditions under which evidence was produced or conclusions apply
```

`material_conditions` may appear in an acceptance result as context.

`known_limits`, `blocked_scope`, and `missing_evidence` limit acceptance.

`accept_for_master` is forbidden when any of these are non-empty:

```yaml
known_limits:
  - ...
blocked_scope:
  - ...
missing_evidence:
  - ...
governance_blockers:
  - ...
```

If explicit limits remain acceptable for Master judgment, use:

```text
accept_for_master_with_scope_limit
```

Do not use material conditions to hide limiting known limits.

## 12. Governance and Responsibility Boundary

The Leader must detect whether acceptance would require:

- bypassing branch policy;
- bypassing release authority;
- bypassing Test or Execution;
- hiding responsibility boundaries;
- allowing unreviewed code;
- treating local candidates as production release;
- merging global causal truth without Master authority.

If yes, use:

```text
governance_blocker_to_master
```

Final Review does not authorize push, merge, release, deployment, external sign-off, Archive write, Knowledge write, or Causal merge.

## 13. Decision Precedence

The Leader must select decisions in this order:

```text
1. Resource policy unresolved or insufficient -> blocked_resource_policy
2. Governance / policy / authority blocker -> governance_blocker_to_master
3. Candidate object mismatch or Execution-owned defect -> reject_to_execution_via_master
4. Test coverage / evidence / route deficiency -> request_test_expansion_via_master
5. Missing, stale, contradictory, or non-reproducible evidence without unique owner -> request_more_evidence_via_master
6. All acceptance conditions hold with explicit limits -> accept_for_master_with_scope_limit
7. All acceptance conditions hold with no limits -> accept_for_master
```

Resource policy failure always stops the review before substantive review continues.

## 14. Allowed Decision Labels

```text
accept_for_master
accept_for_master_with_scope_limit
reject_to_execution_via_master
request_test_expansion_via_master
request_more_evidence_via_master
governance_blocker_to_master
blocked_resource_policy
```

No other decision label is valid for this skill.

## 15. Required Final Review Result

The final result must be a recommendation to Master.

Minimum shape:

```yaml
final_review_result:
  final_review_result_id: string
  request_id: string
  status: final_review_recommendation
  decision: accept_for_master|accept_for_master_with_scope_limit|reject_to_execution_via_master|request_test_expansion_via_master|request_more_evidence_via_master|governance_blocker_to_master|blocked_resource_policy
  target: master
  why: string

  final_code_ref: string
  implementation_candidate_ref: string
  tested_candidate_ref: string

  reviewed_refs:
    execution_final_report_ref: string
    execution_causal_chain_ref: string
    test_final_report_ref: string
    test_plan_ref: string
    test_route_report_refs:
      - string
    test_evidence_refs:
      - string
    reproducibility_set_ref: string
    artifact_manifest_ref: string
    debate_refs:
      - string

  debate_applicability: used|not_used
  no_debate_used_reason: string|null

  whole_chain_review:
    status: completed|not_started
    graph_built: true|false
    not_started_reason: string|null
    reviewed_edges:
      - from: string
        to: string
        relation: string
        evidence_refs:
          - string
    consistency_findings:
      - string

  accepted_scope:
    - string
  blocked_scope:
    - string
  known_limits:
    - string
  missing_evidence:
    - string
  governance_blockers:
    - string
  material_conditions:
    - string
  assumptions:
    - string

  resource_policy:
    policy_ref: string
    required_profile: final_review_leader
    requested_model: string
    resolved_model: string
    requested_reasoning_budget: extra_high
    resolved_reasoning_budget: extra_high
    fallback_used: false
    fallback_reason: string|null
    fallback_evidence_refs:
      - string
    dynamic_adjustment_used: false
    status: satisfied|missing|unavailable|insufficient|fallback_forbidden

  causal_boundary: string
  recommended_master_action: string

  remote_push_performed: false
  pull_request_created: false
  remote_merge_performed: false
  release_performed: false
  deployment_performed: false
  external_signoff_performed: false
  production_store_write_performed: false
  global_causal_truth_merge_performed: false
```

Normative examples must include all required fields or explicitly state that they are non-normative fragments.

## 16. Minimum Acceptance Gate

A Final Review Leader run is valid only if:

```yaml
minimum_acceptance_gate:
  leader_role_boundary_preserved: true
  no_internal_workers_created: true
  top_level_route_table_preserved: true
  input_package_present: true
  resource_policy_resolved_before_substantive_review: true
  blocked_resource_policy_precedence_preserved: true
  whole_chain_review_graph_state_valid: true
  non_resource_blocked_result_has_whole_chain_review_graph_built: true
  resource_blocked_result_has_whole_chain_review_not_started: true
  final_code_implementation_tested_object_consistency_checked_when_review_started: true
  execution_consistency_checked_when_review_started: true
  test_consistency_checked_when_review_started: true
  debate_applicability_resolved: true
  scope_limits_preserved: true
  known_limits_not_hidden_as_material_conditions: true
  evidence_sufficiency_checked_when_review_started: true
  governance_boundary_checked_when_review_started: true
  decision_precedence_followed: true
  status_is_final_review_recommendation: true
  output_route_is_final_review_to_master: true
  no_direct_execution_or_test_route: true
  no_code_modification: true
  no_tests_run_as_substitute_for_test: true
  no_remote_push_or_pr_or_merge_or_release: true
  global_causal_truth_merge_performed: false
```

Resource-blocked result rule:

```text
If decision == blocked_resource_policy:
  resource_policy.status must be missing|unavailable|insufficient|fallback_forbidden
  whole_chain_review.status must be not_started
  whole_chain_review.graph_built must be false
  not_started_reason must be blocked_resource_policy
```

Non-resource-blocked result rule:

```text
If decision != blocked_resource_policy:
  resource_policy.status must be satisfied
  whole_chain_review.status must be completed
  whole_chain_review.graph_built must be true
```

If any required item fails, Final Review must return the appropriate non-accept decision to Master rather than silently accepting.

## 17. One-Line Definition

```text
Final Review Leader performs one high-budget, single-subject, whole-chain consistency review over Execution/Test/Debate evidence, preserves scope limits and resource-policy precedence, and returns exactly one structured recommendation to Master.
```
