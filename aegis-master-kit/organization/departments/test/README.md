# Test Department

## Purpose

The Test Department converts an integrated implementation candidate into reproducible evidence and a scoped test conclusion.

It is not an Execution helper, not a code modification agent, not a final review authority, and not a global causal merge authority.

## Department boundary

At the Master-layer topology, the whole department appears as the top-level role:

```text
test
```

The `test` identity is the Test Leader.

Internal Test Workers are department-local, request-scoped, route-bound, and temporary. They must not become top-level Master-route agents.

## Role-bound operational skills

Phase 27A moves Test Leader / Worker role behavior from role contracts into explicit role-bound operational skills:

```text
TEST_LEADER_OPERATIONAL_SKILL.md
TEST_WORKER_OPERATIONAL_SKILL.md
TEST_LEADER_WORKER_SKILL_ENFORCEMENT_CONTRACT.md
```

The Leader skill defines the full Test Leader work chain:

```text
receive Execution handoff
-> intake / admission
-> governance blocker check
-> handoff validation
-> reproducible test plan
-> justified route split
-> Worker skill installation
-> real Worker creation with thread_id tracking
-> proof/output audit
-> evidence aggregation
-> strict result-label decision
-> reproducibility set + artifact manifest
-> feedback to Execution or handoff to Final Review
```

The Worker skill defines the full Test Worker work chain:

```text
receive one route
-> verify skill / role / thread / scope
-> write proof before substantive work
-> execute assigned commands or inspections
-> capture logs / stdout / stderr / artifacts / environment
-> classify route result by evidence state
-> emit structured route evidence
```

## Mandatory Worker skill installation

A Test Leader must not create a Test Worker unless the Worker creation request includes:

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

## Thread identity rule

The Test Leader must supervise Test Workers by subagent `thread_id`, not by whether the outer MCP / `tools/call` launcher returned before timeout.

Core rule:

```text
MCP / tools/call timeout != Test Worker failure
subagent thread_id is the Worker lifecycle identity key
```

Required consequences:

- persist `thread_id` immediately when creation returns or logs it;
- classify outer launcher timeout as `launcher_timeout`, not `worker_failed`;
- do not create a duplicate Worker for the same route solely because the launcher timed out;
- recover, poll, or continue by `thread_id` when possible;
- final Worker proof and output must include the same non-empty `thread_id`;
- missing proof/output becomes failure only after final deadline and recovery attempts fail.

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
2. Test Leader owns test planning, route split, Worker creation, evidence aggregation, and scoped conclusion generation.
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
15. Worker lifecycle status must be keyed by `thread_id`, not parent tool timeout.

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

## Remaining support files

The following files remain as department support material until later phases decide whether they should also become skills:

```text
TEST_DEPARTMENT_CONTRACT.md
TEST_PLAN_AND_ROUTE_SPLIT_CONTRACT.md
TEST_EVIDENCE_AND_RETENTION_CONTRACT.md
TEST_RESULT_AND_HANDOFF_CONTRACT.md
TEST_20A_HANDOFF_VALIDATION_CONTRACT.md
TEST_20B_ACCEPTANCE_CONTRACT.md
TEST_REAL_WORKER_CONTRACT.md
schemas/
templates/
tests/
```

The following old role-contract files are superseded and removed by Phase 27A:

```text
TEST_LEADER_CONTRACT.md
TEST_WORKER_CONTRACT.md
```

## Runtime boundary

This package defines department contracts and role-bound operational skills.

The deterministic and real-worker runtime support currently lives under:

```text
aegis-runtime/test/
```

Phase 27A is a role-skill document replacement patch.

Phase 27B adds a local deterministic role-skill validator under:

```text
aegis-runtime/test/aegis_test_runtime/operational_skill.py
```

The Phase 27B validator checks Test Leader / Worker role-skill artifacts for skill binding, `thread_id`-based Worker lifecycle supervision, proof/output thread identity matching, canonical `requested_reasoning_effort`, canonical `command_evidence`, strict evidence-state aggregation, reproducibility retention, artifact manifest retention, and valid handoff routing. It does not claim production Test lifecycle closure.

## Runtime validator

Phase 27B validator target:

```text
aegis-runtime/test/aegis_test_runtime/operational_skill.py
aegis-runtime/test/tests/test_phase27b_test_role_operational_skills.py
runtime_test_reports/PHASE_27B_TEST_ROLE_OPERATIONAL_SKILLS_PATCH_PLAN.md
```

It validates runtime artifacts only. It does not create real production Test Workers, run production CI, or mutate business code.

## Non-goals

Phase 27A does not implement production Test lifecycle closure, production CI, durable environment provisioning, external artifact backend, remote branch governance, remote push, PR creation, remote merge, release, deployment, external sign-off, production store writes, or global causal truth merge.
