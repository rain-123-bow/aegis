# Final Review Result

```yaml
final_review_result_id: ...
request_id: ...
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

resource_policy:
  policy_ref: ...
  required_profile: final_review_leader
  resolved_profile: ...
  reasoning_budget: maximum|unknown
  fallback_used: false
  status: satisfied|missing|unavailable|insufficient|fallback_forbidden

causal_boundary: Final Review output is a recommendation to Master; it is not global causal truth.
recommended_master_action: ...
status: final_review_recommendation
```

## Strict interpretation

- `target` must be `master`.
- Resource policy failure must return `blocked_resource_policy`.
- `accept_for_master` requires empty `known_limits`, `blocked_scope`, `missing_evidence`, and `governance_blockers`.
- Any limiting known limit requires `accept_for_master_with_scope_limit` or a non-accept decision.
- `material_conditions` may describe context, but must not hide acceptance limits.
- `reject_to_execution_via_master` does not mean Final Review can route directly to Execution.
- `request_test_expansion_via_master` does not mean Final Review can route directly to Test.
- Final Review must not push, merge, release, modify code, run tests, or merge global causal truth.

## Complete normative examples

All examples below use the full required result shape. Empty lists or empty strings mean the field is intentionally not applicable for that decision.

### blocked_resource_policy

```yaml
final_review_result_id: FRR-BLOCKED-001
request_id: FR-REQ-001
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

accepted_scope: []
blocked_scope:
  - final_review
known_limits: []
missing_evidence: []
governance_blockers: []

resource_policy:
  policy_ref: ""
  required_profile: final_review_leader
  resolved_profile: ""
  reasoning_budget: unknown
  fallback_used: false
  status: missing

causal_boundary: Final Review stopped before substantive review; no causal merge occurred.
recommended_master_action: Provide or repair root model and reasoning-budget policy.
status: final_review_recommendation
```

### accept_for_master

```yaml
final_review_result_id: FRR-ACCEPT-001
request_id: FR-REQ-002
decision: accept_for_master
target: master
why: Final code, implementation candidate, tested candidate, Execution evidence, and Test evidence are consistent for the declared scope.

final_code_ref: code:final
implementation_candidate_ref: exec:candidate
tested_candidate_ref: test:candidate

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

accepted_scope:
  - declared_scope
blocked_scope: []
known_limits: []
missing_evidence: []
governance_blockers: []

resource_policy:
  policy_ref: policy:root-model-budget
  required_profile: final_review_leader
  resolved_profile: final_review_leader
  reasoning_budget: maximum
  fallback_used: false
  status: satisfied

causal_boundary: Final Review output is a recommendation to Master; it is not global causal truth.
recommended_master_action: Review the recommendation and decide the next Master governance action.
status: final_review_recommendation
```

### accept_for_master_with_scope_limit

```yaml
final_review_result_id: FRR-SCOPED-001
request_id: FR-REQ-003
decision: accept_for_master_with_scope_limit
target: master
why: Evidence supports the accepted scope, but compatibility validation remains outside the accepted scope.

final_code_ref: code:final
implementation_candidate_ref: exec:candidate
tested_candidate_ref: test:candidate

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

accepted_scope:
  - core_validated_scope
blocked_scope:
  - compatibility_scope
known_limits:
  - compatibility scope not tested
missing_evidence: []
governance_blockers: []

resource_policy:
  policy_ref: policy:root-model-budget
  required_profile: final_review_leader
  resolved_profile: final_review_leader
  reasoning_budget: maximum
  fallback_used: false
  status: satisfied

causal_boundary: Causal support is limited to accepted_scope and remains a recommendation to Master.
recommended_master_action: Decide whether scoped acceptance is acceptable.
status: final_review_recommendation
```

### request_test_expansion_via_master

```yaml
final_review_result_id: FRR-TEST-001
request_id: FR-REQ-004
decision: request_test_expansion_via_master
target: master
why: Test coverage and reproducibility evidence do not cover the declared validation scope.

final_code_ref: code:final
implementation_candidate_ref: exec:candidate
tested_candidate_ref: test:candidate

reviewed_refs:
  execution_final_report_ref: exec:final-report
  execution_causal_chain_ref: exec:causal-candidate
  test_final_report_ref: test:final-report
  test_plan_ref: test:plan
  test_route_report_refs: []
  test_evidence_refs: []
  reproducibility_set_ref: ""
  artifact_manifest_ref: ""
  debate_refs: []

accepted_scope: []
blocked_scope:
  - declared_validation_scope
known_limits: []
missing_evidence:
  - missing Test route report
  - missing reproducibility set
  - missing artifact manifest
governance_blockers: []

resource_policy:
  policy_ref: policy:root-model-budget
  required_profile: final_review_leader
  resolved_profile: final_review_leader
  reasoning_budget: maximum
  fallback_used: false
  status: satisfied

causal_boundary: No causal merge occurred; Test evidence is insufficient for acceptance.
recommended_master_action: Route to Test for expanded validation.
status: final_review_recommendation
```

### reject_to_execution_via_master

```yaml
final_review_result_id: FRR-EXEC-001
request_id: FR-REQ-005
decision: reject_to_execution_via_master
target: master
why: Final code reference materially differs from the implementation candidate without an evidence-backed mapping.

final_code_ref: code:final-b
implementation_candidate_ref: exec:candidate-a
tested_candidate_ref: test:candidate-a

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

accepted_scope: []
blocked_scope:
  - object_consistency
known_limits: []
missing_evidence:
  - final-to-tested object mapping
governance_blockers: []

resource_policy:
  policy_ref: policy:root-model-budget
  required_profile: final_review_leader
  resolved_profile: final_review_leader
  reasoning_budget: maximum
  fallback_used: false
  status: satisfied

causal_boundary: No causal merge occurred; Execution must repair object consistency or provide mapping evidence.
recommended_master_action: Route to Execution for correction or mapping evidence.
status: final_review_recommendation
```

### governance_blocker_to_master

```yaml
final_review_result_id: FRR-GOV-001
request_id: FR-REQ-006
decision: governance_blocker_to_master
target: master
why: Acceptance would require a release authority decision outside Final Review authority.

final_code_ref: code:final
implementation_candidate_ref: exec:candidate
tested_candidate_ref: test:candidate

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

accepted_scope: []
blocked_scope:
  - release_authority
known_limits: []
missing_evidence: []
governance_blockers:
  - release authority boundary unresolved

resource_policy:
  policy_ref: policy:root-model-budget
  required_profile: final_review_leader
  resolved_profile: final_review_leader
  reasoning_budget: maximum
  fallback_used: false
  status: satisfied

causal_boundary: Final Review does not authorize release or merge global causal truth.
recommended_master_action: Decide the release authority boundary before final acceptance.
status: final_review_recommendation
```
