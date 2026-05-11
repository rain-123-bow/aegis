# Final Review Phase 21B Real Leader Acceptance Contract

## 1. Purpose

Phase 21B validates real nested-Codex / Codex Final Review Leader acceptance after Phase 21A handoff validation.

Phase 21B proves that Master can create exactly one real Final Review Leader, that the Leader can consume Phase 21A Final Review handoff-validation material, and that the Leader can produce an auditable `final_review_result` recommendation back to Master.

This phase is real Final Review Leader acceptance only.

It is not production Final Review lifecycle closure, not production release review, not production sign-off, and not global causal truth merge.

## 2. Required upstream material

The accepted upstream material is Phase 21A output:

```text
.aegis-phase21a-final-review-handoff-validation/outputs/phase21a_handoff_validation_summary.json
.aegis-phase21a-final-review-handoff-validation/outputs/phase21a_final_review_result.json
```

The Phase 21A summary must state:

```yaml
acceptance_status: accepted_final_review_handoff_validation_closure
phase_boundary: final_review_handoff_validation_not_real_final_review_leader
target: master
output_route: final_review -> master
real_final_review_leader_created: false
final_review_worker_created: false
production_final_review_lifecycle_closure: false
production_release_review_closure: false
global_causal_truth_mutation: false
```

The Phase 21A result must remain a Final Review recommendation to Master and must not be global causal truth.

## 3. Real Leader creation shape

The only valid creation shape is:

```text
Master
  -> real nested-Codex / Codex Final Review Leader
      -> consume Phase 21A summary and result
      -> perform single-subject whole-chain review
      -> write proof file
      -> write output file
      -> preserve final_review_result recommendation boundary
  -> Master receives final_review_result material
```

Allowed created agent count:

```yaml
final_review_leader_count: 1
final_review_worker_count: 0
```

Master creates the Final Review Leader directly. The Final Review Leader must not create internal workers.

## 4. Model and reasoning-budget policy

The Final Review Leader profile is resolved only from `MODEL_REASONING_BUDGET_POLICY.yaml`.

Required profile:

```yaml
role_id: final_review_leader
model: gpt-5.5
reasoning_budget: extra_high
fallback_allowed: false
dynamic_adjustment_allowed: false
```

Silent downgrade is forbidden. Fallback is forbidden. Missing or unsatisfied policy must fail fast.

## 5. Proof requirements

The real Final Review Leader must write a proof JSON file before substantive review work.

Minimum proof fields:

```yaml
agent_id: string
role_id: final_review_leader
created_by: master
creation_mechanism: string
requested_model: gpt-5.5
policy_model: gpt-5.5
requested_reasoning_effort: extra_high
policy_reasoning_budget: extra_high
topology_scope: top_level_master_domain
run_id: string
proof_statement: string
created_at_utc: string
```

Missing proof is failure, not skip.

## 6. Output requirements

The real Final Review Leader must write an output JSON file.

Minimum output fields:

```yaml
agent_id: string
role_id: final_review_leader
run_id: string
source_phase: phase21a_final_review_handoff_validation
phase21a_summary_ref: string
phase21a_result_ref: string
final_review_result: object
final_decision: string
output_route: final_review -> master
reviewed_refs: object
evidence_refs:
  - string
recommendation_scope:
  - string
known_limits:
  - string
blocked_scope:
  - string
status: final_review_leader_report_candidate
causal_status: final_review_recommendation_candidate
real_final_review_leader_created: true
final_review_worker_created: false
production_final_review_lifecycle_closure: false
production_release_review_closure: false
global_causal_truth_mutation: false
```

The nested `final_review_result` must satisfy the existing Final Review result contract:

```yaml
target: master
status: final_review_recommendation
causal_boundary: contains "not global causal truth"
resource_policy:
  required_profile: final_review_leader
  status: satisfied
```

## 7. Acceptance label

A successful Phase 21B run must use:

```text
accepted_real_final_review_leader_closure
```

## 8. Forbidden labels

Phase 21B must not claim:

```text
accepted_final_review_worker_closure
production_final_review_lifecycle_closure
production_release_review_closure
global_causal_truth_closure
```

## 9. Hard rules

- Master creates exactly one real Final Review Leader.
- Final Review creates zero workers.
- Final Review remains single-Leader, whole-chain review.
- Final Review does not parallelize review.
- Final Review does not modify implementation code.
- Final Review does not run or replace Test routes.
- Final Review does not push, create PRs, merge, release, deploy, or sign off production.
- Final Review does not mutate global causal truth.
- Final Review output remains a recommendation to Master.
- Phase 21A scope limits must not be erased unless the real Leader has explicit evidence to narrow or supersede them.
- Real Leader proof and output audits are mandatory.
