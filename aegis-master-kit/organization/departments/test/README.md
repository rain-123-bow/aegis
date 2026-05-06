# Test Department

## Definition

The Test Department converts an integrated implementation candidate into reproducible evidence and a scoped test conclusion.

It is not an Execution helper, not a code modification agent, not a final review authority, and not a global causal merge authority.

## External boundary

At the Master-layer topology, the whole department appears as the top-level role:

```text
test
```

The Test Leader is the only external department boundary.

Internal Test Workers must not become top-level Master-route agents.

## Internal model

```text
Test Leader
  -> receive implementation candidate from Execution Leader
  -> inspect task objective, plan, changed scope, ownership map, local evidence, risks, and success criteria
  -> design a reproducible test plan
  -> split the plan into independent test routes only when justified
  -> create one Test Worker per accepted route
  -> collect route reports, logs, data, and artifacts
  -> aggregate route reports into a scoped test_result
  -> if failed: send evidence and test data to Execution Leader
  -> if passed or scoped-pass: send result, evidence, test plan, data, and final code reference to Final Review
  -> retain the minimal reproducibility set for later inspection
```

## Top-level route semantics

The current top-level route semantics are:

```text
execution -> test          implementation_candidate

test -> execution          test_feedback / failure_feedback compatibility

test -> final_review       test_result
```

The Test Department must not send passed results directly to Master unless a future topology explicitly adds that route.

## Core invariants

1. Test owns evidence production, not implementation modification.
2. Test Leader owns test planning, route split, worker creation, evidence aggregation, and scoped conclusion generation.
3. Test Worker owns exactly one accepted test route.
4. Test Worker reports route facts and artifacts; it does not decide whole-candidate acceptance.
5. Test failure feedback goes to the Execution Leader, not directly to Execution Groups.
6. Test may provide owner hints, affected scope, and evidence, but Execution Leader owns final rework assignment.
7. Passed results go to Final Review with test results, test data, and final code references.
8. A pass is valid only when mandatory routes pass, declared validation scope is covered, unresolved blockers are absent, and uncovered scope is explicit.
9. Test results are evidence and scoped conclusions, not global causal truth.
10. At minimum, the test plan and reproducibility metadata must be retained after the task.
11. Failed evidence with ambiguous owner remains `failed`, not `inconclusive`.
12. Missing, unstable, contradictory, or insufficient evidence is `inconclusive` or `blocked`, not `failed`.
13. Governance or policy bypass discovered by Test is `blocked` with `blocker_kind: governance`.
14. Test result labels must follow the evidence-state decision tree; they must not be selected for convenience.

## Strict result semantics

Test result labels are not interchangeable.

A route or final result must be classified by evidence state, not by convenience:

- `failed` means the candidate was testable and evidence proves that a mandatory validation expectation was not met.
- `inconclusive` means the test was attempted but evidence is insufficient, unstable, contradictory, or not strong enough to support either pass or fail.
- `blocked` means the route or department cannot proceed because a precondition is missing or invalid, such as missing environment, missing dependency, missing candidate material, invalid handoff, or governance/policy blocker.
- `passed_with_scope_limit` is allowed only when all mandatory routes pass and remaining uncovered scope is explicit and acceptable for Final Review.
- `passed` is allowed only when all mandatory routes pass, declared validation scope is covered, and no unresolved blocker remains.

Ambiguous ownership is not the same thing as inconclusive testing.

If evidence proves candidate failure but Test cannot determine the responsible Execution owner, the result is still:

```yaml
result: failed
owner_hint:
  owner_type: ambiguous
```

Execution Leader owns rework assignment.

Test only provides evidence, affected scope, failure signatures, and advisory owner hints.

## Governance blocker rule

If Test discovers that passing, validating, accepting, or exercising the candidate would require bypassing top-level governance, branch policy, release authority, or responsibility boundaries, Test must return:

```yaml
result: blocked
blocker_kind: governance
requires_governance_review: true
```

Test must not ask Execution to patch around governance policy.

Test must not send directly to Master under the current topology.

Routing rule:

- If the blocker is caused by an invalid Execution handoff or candidate request, return to Execution Leader.
- If the blocker requires final acceptance, policy review, or top-level governance review, hand off to Final Review.

## Key files

```text
TEST_DEPARTMENT_CONTRACT.md
TEST_LEADER_CONTRACT.md
TEST_WORKER_CONTRACT.md
TEST_PLAN_AND_ROUTE_SPLIT_CONTRACT.md
TEST_EVIDENCE_AND_RETENTION_CONTRACT.md
TEST_RESULT_AND_HANDOFF_CONTRACT.md
schemas/
templates/
tests/
```

## Runtime boundary

This package defines department contracts only.

The future runtime implementation belongs under:

```text
aegis-runtime/test/
```
