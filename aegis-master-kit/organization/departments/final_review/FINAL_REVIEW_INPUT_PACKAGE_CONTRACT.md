# Final Review Input Package Contract

## 1. Purpose

This contract defines the minimum package that Test must provide to Final Review.

Final Review must not operate on a bare pass/fail result.

## 2. Required fields

```yaml
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
material_conditions:
  - string
assumptions:
  - string
debate_refs:
  - string
governance_blockers:
  - string
resource_policy_ref: optional string until root model policy exists
```

## 3. Object references

The package must provide enough references to prove which object was:

1. implemented by Execution;
2. tested by Test;
3. sent to Final Review;
4. proposed for Master review.

Final Review must not assume these are identical without evidence.

## 4. Evidence references

Evidence references must be inspectable enough for Final Review to understand:

- what was tested;
- what passed;
- what failed;
- what was not covered;
- what artifacts remain;
- what cleanup policy was applied.

## 5. Debate references

If Execution used Debate, the package must include Debate reference material or a Debate causal-chain reference.

If Debate was not used, the package must explicitly state that no Debate reference applies.

## 6. Missing package data

If required input is missing, Final Review must return:

```yaml
decision: request_more_evidence_via_master
```

Final Review must not invent missing context.

## 7. Invalid package data

If package data is contradictory, stale, or points to different candidate objects, Final Review must not accept.
