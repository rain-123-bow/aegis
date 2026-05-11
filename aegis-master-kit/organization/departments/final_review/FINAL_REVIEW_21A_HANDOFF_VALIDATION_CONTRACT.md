# Final Review Phase 21A Handoff Validation Contract

## 1. Purpose

Phase 21A validates that the Final Review Department can consume the real Test Phase 20B handoff material and return a valid `final_review_result` to Master.

This phase is a handoff-validation closure only.

It does not create a real nested-Codex Final Review Leader, does not create Final Review Workers, does not perform production release review, and does not merge global causal truth.

## 2. Accepted input

The accepted input is a Test Department handoff package with the following minimum semantic fields:

```yaml
handoff_kind: test_real_worker_result
target: final_review
status: ready_for_final_review
final_test_result: passed | { result: passed, ... }
```

If present, the following evidence fields must not contradict acceptance:

```yaml
proof_audit_status: passed
output_audit_status: passed
route_results:
  <route_id>: passed
production_test_lifecycle_closure: false
remote_push_performed: false
pr_created: false
production_merge_performed: false
release_performed: false
production_signoff_performed: false
global_causal_truth_mutation: false
```

## 3. Final Review request construction

The Phase 21A validator must build or validate a Final Review request with:

```yaml
source: test
resource_policy:
  required_profile: final_review_leader
final_review_input_package:
  final_code_ref: string
  implementation_candidate_ref: string
  tested_candidate_ref: string
  reviewed_refs: object
```

If the handoff package already contains a complete `final_review_request`, the validator may use it after enforcing the Phase 21A handoff gates.

If the handoff package contains `final_review_input_package` and `resource_policy`, the validator must wrap them into a Final Review request.

If the handoff package contains only the Phase 20B evidence summary fields, the validator may synthesize a deterministic demo request from those evidence references. Synthesized references are still scoped evidence references, not production artifact references.

## 4. Output route

The only valid output route remains:

```text
final_review -> master
```

The output message type remains:

```text
final_review_result
```

## 5. Acceptance label

A successful Phase 21A run must use:

```text
accepted_final_review_handoff_validation_closure
```

## 6. Forbidden labels

Phase 21A must not claim:

```text
accepted_real_final_review_leader_closure
production_final_review_lifecycle_closure
production_release_review_closure
global_causal_truth_closure
```

## 7. Hard rules

- Master does not create a real Final Review Leader in Phase 21A.
- Final Review does not create internal workers.
- Final Review does not parallelize review.
- Final Review does not run or replace Test routes.
- Final Review does not modify implementation code.
- Final Review does not push, create PRs, merge, release, deploy, sign off production, or mutate global causal truth.
- Test Phase 20B output remains scoped evidence / causal candidate material.
- Final Review output remains a recommendation to Master.
- Resource policy precedence from `FINAL_REVIEW_RESULT_AND_HANDOFF_CONTRACT.md` still applies.
