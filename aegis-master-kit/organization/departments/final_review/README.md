# Final Review Department

## Definition

The Final Review Department is the single-Leader final review gate before results return to Master.

It performs whole-chain consistency review over the final candidate, Execution outputs, Test evidence, Debate references when present, known limits, uncovered scope, governance blockers, and causal boundaries.

It is not a parallel reviewer pool, not a testing department, not an implementation department, and not the global Causal Store merge authority.

## External boundary

The external department boundary is:

```text
Final Review Leader
```

At the Master-layer topology, the Leader is represented by the top-level role:

```text
final_review
```

The valid route edges are:

```text
test -> final_review
final_review -> master
```

The boundary identity and route edges are not the same thing.

There are no internal Final Review Workers in v0.1.

## Top-level route semantics

The current top-level route semantics are:

```text
test -> final_review      test_result
final_review -> master    final_review_result
```

Final Review must not invent routes to Execution or Test.

If Final Review recommends rework, test expansion, or more evidence, it must return that recommendation to Master through `final_review -> master`.

Master decides the next top-level route.

## Internal model

```text
Final Review Leader
  -> receive final review package from Test
  -> verify input completeness
  -> resolve model/resource policy reference when available
  -> perform single-subject whole-chain review
  -> verify candidate/test object consistency
  -> verify Execution/Test/Debate consistency
  -> verify evidence sufficiency and scope coverage
  -> verify known limits and uncovered scope
  -> verify responsibility and governance boundaries
  -> produce final_review_result
  -> send final_review_result to Master
```

## Core invariants

1. Final Review has exactly one Leader and no internal worker fanout.
2. Final Review must preserve uninterrupted whole-chain semantic integration.
3. Checklists are allowed; parallel reviewer agents are forbidden.
4. Final Review reviews evidence; it does not produce new Test evidence.
5. Final Review reviews implementation references; it does not modify code.
6. Final Review may recommend Execution rework, but it must not assign rework to Execution Groups.
7. Final Review may request test expansion, but it must not run tests itself.
8. Final Review returns only to Master under the current topology.
9. Final Review does not merge global causal truth.
10. Final Review must detect object mismatch between final code, implementation candidate, and tested candidate.
11. Final Review must surface scope limits instead of hiding them behind acceptance.
12. Final Review must block or reject when required evidence is missing, contradictory, stale, or not reproducible.
13. Final Review must fail fast with `blocked_resource_policy` when the required review resource policy cannot be satisfied.
14. Final Review output is a recommendation to Master, not a push, merge, release, or global-causal action.
15. `accept_for_master` is forbidden when `known_limits`, `blocked_scope`, or `missing_evidence` are non-empty.
16. Limiting known limits require `accept_for_master_with_scope_limit` or a non-accept decision.
17. Material conditions may be present in an acceptance result, but they are not the same as limiting `known_limits`.
18. Resource policy failure has highest precedence and must return `blocked_resource_policy` before review continues.
19. Final Review result examples must include the full required result shape, not partial fragments that omit required fields.

## Strict acceptance semantics

`accept_for_master` is an unconditional recommendation that the package is ready for Master review under the declared scope.

It is valid only when:

- `known_limits` is empty;
- `blocked_scope` is empty;
- `missing_evidence` is empty;
- no unresolved governance blocker exists;
- the resource policy is satisfied;
- final code, implementation candidate, and tested candidate are consistent;
- required Test and Execution evidence is present and reproducible.

If any material known limit constrains the accepted scope, Final Review must not use `accept_for_master`.

Use one of:

```text
accept_for_master_with_scope_limit
request_test_expansion_via_master
request_more_evidence_via_master
reject_to_execution_via_master
governance_blocker_to_master
blocked_resource_policy
```

Material conditions are allowed in acceptance results as context, but they must not be used to hide limiting `known_limits`.

## Resource policy precedence

Resource policy is a pre-review gate.

If the required `final_review_leader` resource policy is missing, unavailable, insufficient, or forbidden fallback would be used, Final Review must return:

```yaml
decision: blocked_resource_policy
target: master
```

It must not continue into object review, Test evidence review, or causal review.

Resource policy failure is not ordinary missing evidence.

## Key files

```text
FINAL_REVIEW_DEPARTMENT_CONTRACT.md
FINAL_REVIEW_LEADER_CONTRACT.md
FINAL_REVIEW_INPUT_PACKAGE_CONTRACT.md
WHOLE_CHAIN_CONSISTENCY_REVIEW_CONTRACT.md
FINAL_REVIEW_RESULT_AND_HANDOFF_CONTRACT.md
RESOURCE_POLICY_REFERENCE_CONTRACT.md
schemas/
templates/
tests/
```

## Runtime boundary

This package defines department contracts only.

The future runtime implementation belongs under:

```text
aegis-runtime/final_review/
```
