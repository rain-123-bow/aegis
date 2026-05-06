# Test Result and Handoff Contract

## 1. Purpose

This contract defines how Test results leave the Test Department.

It keeps failure feedback, success handoff, Final Review handoff, and causal boundaries distinct.

## 2. Strict handoff routing

The route depends on result class and required next authority.

### To Execution Leader

Use `test -> execution` when the next action belongs to Execution Leader:

- `failed`;
- `inconclusive`;
- ordinary `blocked`;
- `request_more_context`;
- invalid handoff;
- missing candidate material;
- ambiguous owner requiring Execution triage;
- environment or dependency rerun owned by Execution/test setup.

A proven failure with ambiguous owner still routes to Execution Leader:

```yaml
result: failed
owner_hint:
  owner_type: ambiguous
recommended_execution_action: triage_by_execution_leader
```

### To Final Review

Use `test -> final_review` when the candidate is ready for final review or when final governance review is required:

- `passed`;
- `passed_with_scope_limit`;
- `blocked` with `blocker_kind: governance` when the blocker requires final acceptance, policy review, or top-level governance review.

### Never directly to Master

Under the current topology, Test must not send directly to Master.

## 3. Invalid handoff cases

The following are contract violations:

1. Reporting `inconclusive` only because owner responsibility is ambiguous while failure evidence is clear.
2. Reporting `failed` when no command, log, artifact, reproduction, or inspection evidence exists.
3. Reporting `passed_with_scope_limit` when a mandatory route failed, was blocked, or was inconclusive.
4. Asking Execution to patch around governance policy.
5. Sending passed or governance-blocked results directly to Master.
6. Treating Test result as global causal truth.

## 4. Failure handoff to Execution

When a candidate fails, is blocked, or is inconclusive, Test Leader sends feedback to Execution Leader.

Message route:

```text
test -> execution
```

Preferred message type:

```text
test_feedback
```

Backward-compatible failed-feedback message type:

```text
failure_feedback
```

Payload minimum:

```yaml
feedback_id: ...
request_id: ...
result: failed|inconclusive|blocked
feedback_kind: failure|inconclusive|blocked|missing_context
evidence_refs:
  - ...
test_data_refs:
  - ...
covered_scope:
  - ...
uncovered_scope:
  - ...
failure_signatures:
  - ...
affected_files_or_modules:
  - ...
owner_hint:
  owner_type: group|integration|ambiguous|none
  owner_id: optional
why: ...
reproduction:
  commands:
    - ...
  environment_ref: ...
  artifacts:
    - ...
```

The owner hint is advisory. Execution Leader decides rework assignment.

## 5. Success handoff to Final Review

When a candidate passes or passes with scope limits, Test Leader sends final test material to Final Review.

Message route:

```text
test -> final_review
```

Message type:

```text
test_result
```

Payload minimum:

```yaml
test_result_id: ...
request_id: ...
result: passed|passed_with_scope_limit
final_code_ref: ...
implementation_candidate_ref: ...
test_plan_ref: ...
test_route_reports:
  - ...
test_data_refs:
  - ...
coverage_summary:
  covered_scope:
    - ...
  uncovered_scope:
    - ...
known_limits:
  - ...
reproducibility_set_ref: ...
evidence_refs:
  - ...
why: ...
assumptions:
  - ...
material_conditions:
  - ...
```

## 6. No direct Master handoff under current topology

Under the current top-level topology, Test must not send passed results directly to Master.

Final Review is responsible for reviewing final code plus Test evidence and returning the final review result to Master.

## 7. Final Review material

The Test result sent to Final Review must be sufficient to evaluate:

- final code reference;
- tested candidate reference;
- test plan quality;
- route coverage;
- evidence completeness;
- known limits;
- uncovered scope;
- reproducibility metadata;
- whether Test result supports or limits the candidate.

## 8. Result integrity

A `passed` result must not hide:

- skipped mandatory routes;
- missing artifacts;
- unstable environment;
- unresolved blockers;
- uncovered material scope.

If any of these exists, use `passed_with_scope_limit`, `inconclusive`, or `blocked`.

## 9. Causal boundary

The final Test result is evidence for downstream review and causal construction.

It is not a global causal fact until Master or the authorized causal merge process accepts it.
