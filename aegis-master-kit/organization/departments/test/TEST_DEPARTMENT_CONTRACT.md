# Test Department Contract

## 1. Definition

The Test Department is the evidence-production department for integrated implementation candidates.

It validates a candidate against declared task objectives, success criteria, contracts, changed scope, risks, and expected test focus.

It produces:

- a reproducible test plan;
- per-route worker reports;
- evidence artifacts and data references;
- a scoped test conclusion;
- failure feedback for Execution Leader when the candidate fails;
- final review handoff material when the candidate passes or passes with explicit scope limits.

## 2. Non-definition

The Test Department is not:

- a generic pytest wrapper;
- a code-writing department;
- a rework assignment authority inside Execution;
- a Final Review substitute;
- a Master bypass path;
- a global Causal Store writer.

## 3. External routes

The Test Department must obey the top-level route table.

Accepted top-level route meanings:

```text
execution -> test
  Test receives an implementation candidate from Execution Leader.

 test -> execution
  Test returns failed, inconclusive, blocked, missing-evidence, or evidence-backed feedback to Execution Leader.

 test -> final_review
  Test returns passed, passed_with_scope_limit, or final test result material to Final Review.
```

Under the current topology, Test must not send passed results directly to Master.

## 4. Input authority

The canonical Test input is the Execution implementation candidate.

A valid request must include at least:

```yaml
request_id: ...
source: execution
objective: ...
scope: ...
base_branch: ...
integration_branch: ...
implementation_candidate_ref: ...
final_code_ref: ...
changed_files:
  - ...
ownership_map:
  path_or_module: execution_group_or_integration
local_test_evidence:
  - ...
back_review_summaries:
  - ...
known_risks:
  - ...
expected_test_focus:
  - ...
success_criteria:
  - ...
forbidden_actions:
  - ...
```

If the request does not contain enough information to design reproducible tests, Test Leader must request more context or return an inconclusive result instead of inventing a test plan.

## 5. Output authority

The Test Department owns:

- test route design;
- test execution evidence;
- test data preservation;
- route-level observations;
- scoped test conclusion.

The Test Department does not own:

- source code modification;
- Execution Group rework assignment;
- branch merge authorization;
- global causal truth promotion;
- release or deployment authority.

## 6. Success path

When the candidate passes, Test Leader must send to Final Review:

```yaml
final_code_ref: ...
implementation_candidate_ref: ...
test_plan: ...
test_route_reports:
  - ...
test_data_refs:
  - ...
coverage_summary: ...
uncovered_scope:
  - ...
final_test_result: passed|passed_with_scope_limit
reproducibility_set_ref: ...
```

The handoff must include enough evidence for Final Review to inspect both the final code and the test basis.

## 7. Failure path

When the candidate fails, Test Leader must send evidence and test data to Execution Leader.

Failure feedback may include owner hints, but it must not command a specific Execution Group to rework.

Execution Leader owns rework assignment based on Test evidence, ownership map, group records, integration records, and execution context.

## 8. Test result labels

Allowed result labels:

```text
passed
passed_with_scope_limit
failed
inconclusive
blocked
request_more_context
```

The labels are mutually exclusive and must be selected by evidence state.

### passed

Use only when:

1. all mandatory routes passed;
2. declared validation scope is covered;
3. uncovered scope is empty or immaterial;
4. no unresolved blocker remains;
5. final code ref and implementation candidate ref are included.

### passed_with_scope_limit

Use only when:

1. all mandatory routes passed;
2. remaining uncovered scope is explicit;
3. the uncovered scope is not silently hidden;
4. Final Review receives the scope limit.

This label must not be used when a mandatory route is failed, inconclusive, or blocked.

### failed

Use when the candidate was testable and evidence proves that a mandatory validation expectation was not met.

A failed result does not require Test to know the final rework owner.

If the failure evidence is clear but owner responsibility is unclear, the result remains:

```yaml
result: failed
owner_hint:
  owner_type: ambiguous
```

Ambiguous ownership must not downgrade a proven failure into `inconclusive` or `blocked`.

### inconclusive

Use when testing was attempted but the evidence is insufficient, unstable, contradictory, non-reproducible, or not strong enough to prove either pass or fail.

Examples:

- missing failing command;
- missing log or artifact;
- unstable pass/fail behavior;
- contradictory route reports;
- insufficient reproduction detail.

Inconclusive is not candidate failure.

### blocked

Use when testing cannot proceed because a precondition is missing or invalid.

Examples:

- missing environment;
- missing dependency;
- missing candidate material;
- invalid handoff;
- unavailable mandatory input data;
- governance or policy blocker.

Blocked is not candidate failure unless candidate-specific evidence separately proves failure.

Blocked results must include:

```yaml
blocker_kind: environment|dependency|handoff|candidate_material|governance|policy|unknown
blocker_scope: ...
required_next_action: ...
```

### request_more_context

Use only at admission stage when the request lacks objective, scope, success criteria, candidate reference, ownership map, expected focus, or other minimum handoff context.

Do not use `request_more_context` for executed route failures.

## 9. Owner hint semantics

`owner_hint` is advisory evidence.

Allowed values:

```yaml
owner_hint:
  owner_type: group|integration|ambiguous|none
  owner_id: optional
```

Meaning:

- `group`: evidence points to files/modules owned by one Execution Group.
- `integration`: evidence points to integration logic, merge result, or integration-only behavior.
- `ambiguous`: evidence proves failure, but responsibility cannot be assigned by Test.
- `none`: no candidate failure owner exists, usually for environment or test-side blockers.

The Test Department must not turn `owner_hint` into rework assignment.

Execution Leader owns rework assignment after receiving Test evidence.

## 10. Governance blocker semantics

If Test discovers that a route, validation expectation, candidate behavior, or requested action requires bypassing top-level governance, branch policy, release authority, or responsibility boundaries, the result must be:

```yaml
result: blocked
blocker_kind: governance
requires_governance_review: true
```

Test must not:

- patch around the policy;
- ask Execution to bypass the policy;
- mark the candidate as passed;
- send directly to Master under the current topology.

Routing rule:

- return to Execution Leader when the blocker is caused by invalid Execution handoff or candidate request;
- hand off to Final Review when the blocker requires final acceptance, policy review, or top-level governance decision.

## 11. Causal boundary

Test output is evidence and a scoped test conclusion.

It may support Final Review, Execution rework, or later Master causal merge, but it is not global causal truth by itself.

All Test claims must carry evidence, scope, assumptions, and material conditions.
