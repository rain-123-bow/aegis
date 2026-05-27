# Final Review Result Template

This is the normative Final Review result shape. It must be returned only through:

```text
final_review -> master
```

## Required shape

```yaml
final_review_result_id: ...
request_id: ...
status: final_review_recommendation
decision: accept_for_master|accept_for_master_with_scope_limit|reject_to_execution_via_master|request_test_expansion_via_master|request_more_evidence_via_master|governance_blocker_to_master|blocked_resource_policy
target: master
why: ...

final_code_ref: ...
implementation_candidate_ref: ...
tested_candidate_ref: ...

reviewed_refs:
  execution_final_report_ref: ...
  execution_causal_chain_ref: ...
  test_final_report_ref: ...
  test_plan_ref: ...
  test_route_report_refs:
    - ...
  test_evidence_refs:
    - ...
  reproducibility_set_ref: ...
  artifact_manifest_ref: ...
  debate_refs:
    - ...

debate_applicability: used|not_used
no_debate_used_reason: ...|null

whole_chain_review:
  status: completed|not_started
  graph_built: true|false
  not_started_reason: ...|null
  reviewed_edges:
    - from: ...
      to: ...
      relation: ...
      evidence_refs:
        - ...
  consistency_findings:
    - ...

accepted_scope:
  - ...
blocked_scope:
  - ...
known_limits:
  - ...
missing_evidence:
  - ...
governance_blockers:
  - ...
material_conditions:
  - ...
assumptions:
  - ...

resource_policy:
  policy_ref: ...
  required_profile: final_review_leader
  requested_model: ...
  resolved_model: ...
  requested_reasoning_budget: extra_high
  resolved_reasoning_budget: extra_high
  fallback_used: false
  fallback_reason: null
  fallback_evidence_refs: []
  dynamic_adjustment_used: false
  status: satisfied|missing|unavailable|insufficient|fallback_forbidden

causal_boundary: Final Review output is a recommendation to Master; it is not global causal truth.
recommended_master_action: ...

remote_push_performed: false
pull_request_created: false
remote_merge_performed: false
release_performed: false
deployment_performed: false
external_signoff_performed: false
production_store_write_performed: false
global_causal_truth_merge_performed: false
```

## Strict interpretation

- `target` must be `master`.
- `status` must be `final_review_recommendation`.
- Resource policy failure must return `blocked_resource_policy`.
- `blocked_resource_policy` requires `whole_chain_review.status: not_started` and `graph_built: false`.
- Non-resource-blocked decisions require `whole_chain_review.status: completed` and `graph_built: true`.
- `accept_for_master` requires empty `known_limits`, `blocked_scope`, `missing_evidence`, and `governance_blockers`.
- Any limiting known limit requires `accept_for_master_with_scope_limit` or a non-accept decision.
- `material_conditions` may describe context, but must not hide acceptance limits.
- `reject_to_execution_via_master` does not mean Final Review can route directly to Execution.
- `request_test_expansion_via_master` does not mean Final Review can route directly to Test.
- Final Review must not push, merge, release, modify code, run tests, or merge global causal truth.
- Debate non-use must be explicit through `debate_applicability: not_used` and a non-empty `no_debate_used_reason`.

## Complete normative examples

All examples below use the full required result shape. Empty lists or empty strings mean the field is intentionally not applicable for that decision.

### blocked_resource_policy

```yaml
final_review_result_id: FRR-BLOCKED-001
request_id: FR-REQ-001
status: final_review_recommendation
decision: blocked_resource_policy
target: master
why: Required final_review_leader resource policy is missing.

final_code_ref: ""
implementation_candidate_ref: ""
tested_candidate_ref: ""

reviewed_refs:
  execution_final_report_ref: ""
  execution_causal_chain_ref: ""
  test_final_report_ref: ""
  test_plan_ref: ""
  test_route_report_refs: []
  test_evidence_refs: []
  reproducibility_set_ref: ""
  artifact_manifest_ref: ""
  debate_refs: []

debate_applicability: not_used
no_debate_used_reason: Resource policy blocked review before Debate applicability could affect substantive review.

whole_chain_review:
  status: not_started
  graph_built: false
  not_started_reason: blocked_resource_policy
  reviewed_edges: []
  consistency_findings: []

accepted_scope: []
blocked_scope:
  - final_review
known_limits: []
missing_evidence: []
governance_blockers: []
material_conditions: []
assumptions: []

resource_policy:
  policy_ref: ""
  required_profile: final_review_leader
  requested_model: ""
  resolved_model: ""
  requested_reasoning_budget: extra_high
  resolved_reasoning_budget: extra_high
  fallback_used: false
  fallback_reason: null
  fallback_evidence_refs: []
  dynamic_adjustment_used: false
  status: missing

causal_boundary: Final Review stopped before substantive review; no causal merge occurred.
recommended_master_action: Provide or repair root model and reasoning-budget policy.

remote_push_performed: false
pull_request_created: false
remote_merge_performed: false
release_performed: false
deployment_performed: false
external_signoff_performed: false
production_store_write_performed: false
global_causal_truth_merge_performed: false
```

### accept_for_master

```yaml
final_review_result_id: FRR-ACCEPT-001
request_id: FR-REQ-002
status: final_review_recommendation
decision: accept_for_master
target: master
why: Final code, implementation candidate, tested candidate, Execution evidence, and Test evidence are consistent for the declared scope.

final_code_ref: code:final
implementation_candidate_ref: code:final
tested_candidate_ref: code:final

reviewed_refs:
  execution_final_report_ref: exec:final-report
  execution_causal_chain_ref: exec:causal-candidate
  test_final_report_ref: test:final-report
  test_plan_ref: test:plan
  test_route_report_refs:
    - test:route-report
  test_evidence_refs:
    - test:evidence
  reproducibility_set_ref: test:reproducibility
  artifact_manifest_ref: test:artifact-manifest
  debate_refs: []

debate_applicability: not_used
no_debate_used_reason: Execution did not use Debate for this task.

whole_chain_review:
  status: completed
  graph_built: true
  not_started_reason: null
  reviewed_edges:
    - from: task_objective
      to: implementation_candidate_ref
      relation: scope_defines_candidate
      evidence_refs:
        - exec:final-report
    - from: implementation_candidate_ref
      to: tested_candidate_ref
      relation: object_consistency_checked
      evidence_refs:
        - test:final-report
    - from: test_final_result
      to: final_recommendation
      relation: supports_acceptance
      evidence_refs:
        - test:evidence
  consistency_findings:
    - final code, implementation candidate, and tested candidate are consistent
    - Test evidence covers the declared scope

accepted_scope:
  - declared_scope
blocked_scope: []
known_limits: []
missing_evidence: []
governance_blockers: []
material_conditions:
  - evidence applies to declared_scope
assumptions:
  - referenced artifacts are retained and inspectable

resource_policy:
  policy_ref: policy:root-model-budget
  required_profile: final_review_leader
  requested_model: gpt-5.5
  resolved_model: gpt-5.5
  requested_reasoning_budget: extra_high
  resolved_reasoning_budget: extra_high
  fallback_used: false
  fallback_reason: null
  fallback_evidence_refs: []
  dynamic_adjustment_used: false
  status: satisfied

causal_boundary: Final Review output is a recommendation to Master; it is not global causal truth.
recommended_master_action: Review the recommendation and decide the next Master governance action.

remote_push_performed: false
pull_request_created: false
remote_merge_performed: false
release_performed: false
deployment_performed: false
external_signoff_performed: false
production_store_write_performed: false
global_causal_truth_merge_performed: false
```

### accept_for_master_with_scope_limit

```yaml
final_review_result_id: FRR-SCOPED-001
request_id: FR-REQ-003
status: final_review_recommendation
decision: accept_for_master_with_scope_limit
target: master
why: Evidence supports the accepted scope, but business write/notify validation remains outside the accepted scope.

final_code_ref: code:final
implementation_candidate_ref: code:final
tested_candidate_ref: code:final

reviewed_refs:
  execution_final_report_ref: exec:final-report
  execution_causal_chain_ref: exec:causal-candidate
  test_final_report_ref: test:final-report
  test_plan_ref: test:plan
  test_route_report_refs:
    - test:route-report
  test_evidence_refs:
    - test:evidence
  reproducibility_set_ref: test:reproducibility
  artifact_manifest_ref: test:artifact-manifest
  debate_refs: []

debate_applicability: not_used
no_debate_used_reason: Execution did not use Debate for this task.

whole_chain_review:
  status: completed
  graph_built: true
  not_started_reason: null
  reviewed_edges:
    - from: implementation_candidate_ref
      to: tested_candidate_ref
      relation: object_consistency_checked
      evidence_refs:
        - test:final-report
    - from: test_final_result
      to: known_limits
      relation: limits_acceptance_scope
      evidence_refs:
        - test:evidence
    - from: known_limits
      to: final_recommendation
      relation: requires_scoped_acceptance
      evidence_refs:
        - test:final-report
  consistency_findings:
    - candidate object references are consistent
    - known limits require scoped acceptance

accepted_scope:
  - BLE advertising and discovery reachability
blocked_scope:
  - deterministic business write/notify transaction
known_limits:
  - business write/notify transaction not proven
missing_evidence: []
governance_blockers: []
material_conditions:
  - evidence produced on declared BLE test hosts
assumptions:
  - referenced BLE artifacts are retained

resource_policy:
  policy_ref: policy:root-model-budget
  required_profile: final_review_leader
  requested_model: gpt-5.5
  resolved_model: gpt-5.5
  requested_reasoning_budget: extra_high
  resolved_reasoning_budget: extra_high
  fallback_used: false
  fallback_reason: null
  fallback_evidence_refs: []
  dynamic_adjustment_used: false
  status: satisfied

causal_boundary: Causal support is limited to accepted_scope and remains a recommendation to Master.
recommended_master_action: Decide whether scoped acceptance is acceptable.

remote_push_performed: false
pull_request_created: false
remote_merge_performed: false
release_performed: false
deployment_performed: false
external_signoff_performed: false
production_store_write_performed: false
global_causal_truth_merge_performed: false
```
