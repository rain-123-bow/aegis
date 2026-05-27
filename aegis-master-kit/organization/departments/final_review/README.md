# Final Review Department

## Purpose

The Final Review Department is the single-Leader final review gate before results return to Master.

It performs whole-chain consistency review over the final candidate, Execution outputs, Test evidence, Debate references when present, known limits, uncovered scope, governance blockers, resource policy, and causal boundaries.

It is not a parallel reviewer pool, not a testing department, not an implementation department, and not the global Causal Store merge authority.

## Department boundary

At the Master-layer topology, the whole department appears as the top-level role:

```text
final_review
```

The `final_review` identity is the Final Review Leader.

There are no internal Final Review Workers in the current architecture.

Allowed top-level routes:

```text
test -> final_review
final_review -> master
```

Final Review must not invent routes to Execution or Test. If Final Review recommends rework, test expansion, more evidence, or a governance decision, it returns that recommendation to Master through `final_review -> master`. Master decides the next top-level route.

## Role-bound operational skill

Phase 29A moves Final Review Leader role behavior from a role contract into an explicit role-bound operational skill:

```text
FINAL_REVIEW_LEADER_OPERATIONAL_SKILL.md
```

The Leader skill defines the full Final Review work chain:

```text
receive final review package
-> verify route and input shape
-> resolve resource policy
-> block before review if resource policy is unsatisfied
-> build whole-chain review graph
-> verify candidate object consistency
-> verify Execution / Test / Debate consistency
-> verify scope limits and material conditions
-> verify evidence sufficiency and reproducibility
-> verify governance and responsibility boundaries
-> select decision by precedence
-> produce full final_review_result
-> return final_review_result to Master
```

## Resource-policy precedence

Resource policy is a pre-review gate.

`resource_policy_ref` is an input reference only. Before substantive review, the Leader must resolve it into a concrete `resource_policy` / `resource_policy_gate` object.

If the required `final_review_leader` policy is missing, unavailable, insufficient, or fallback-forbidden, the only valid decision is:

```yaml
decision: blocked_resource_policy
target: master
```

In that case, whole-chain review must not start. The result must expose:

```yaml
whole_chain_review:
  status: not_started
  graph_built: false
  not_started_reason: blocked_resource_policy
```

For all non-resource-blocked decisions, `whole_chain_review.graph_built` must be `true`.

## Whole-chain review output

Final Review must preserve uninterrupted whole-chain semantic integration.

The result must expose an auditable `whole_chain_review` object, not only a final conclusion. This object is not raw chain-of-thought. It records visible review structure and evidence references.

Minimum shape:

```yaml
whole_chain_review:
  status: completed|not_started
  graph_built: true|false
  not_started_reason: string|null
  reviewed_edges:
    - from: string
      to: string
      relation: string
      evidence_refs:
        - string
  consistency_findings:
    - string
```

## Debate applicability

The package must explicitly state whether Debate was used.

```yaml
debate_applicability: used|not_used
debate_refs:
  - string
no_debate_used_reason: string|null
```

Rules:

- If `debate_applicability == used`, `debate_refs` must be non-empty.
- If `debate_applicability == not_used`, `no_debate_used_reason` must be non-empty.
- `debate_refs: []` alone is not sufficient evidence that Debate was not used.

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
15. `accept_for_master` is forbidden when `known_limits`, `blocked_scope`, `missing_evidence`, or `governance_blockers` are non-empty.
16. Limiting known limits require `accept_for_master_with_scope_limit` or a non-accept decision.
17. Material conditions may be present in an acceptance result, but they are not the same as limiting `known_limits`.
18. Resource policy failure has highest precedence and must return `blocked_resource_policy`.
19. Final Review result examples must include the full required result shape, not partial fragments that omit required fields.
20. Final Review result must include `status: final_review_recommendation`.

## Strict acceptance semantics

`accept_for_master` is an unconditional recommendation that the package is ready for Master review under the declared scope.

It is valid only when:

- `known_limits` is empty;
- `blocked_scope` is empty;
- `missing_evidence` is empty;
- `governance_blockers` is empty;
- resource policy is satisfied;
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

Material conditions are allowed in acceptance results as context. They must not be used to hide limiting `known_limits`.

## Decision labels

Allowed decisions:

```text
accept_for_master
accept_for_master_with_scope_limit
reject_to_execution_via_master
request_test_expansion_via_master
request_more_evidence_via_master
governance_blocker_to_master
blocked_resource_policy
```

No other Final Review decision label is valid in the current phase.

## Remaining support files

The following files remain as department support material until later phases decide whether they should also become skills:

```text
FINAL_REVIEW_DEPARTMENT_CONTRACT.md
FINAL_REVIEW_INPUT_PACKAGE_CONTRACT.md
WHOLE_CHAIN_CONSISTENCY_REVIEW_CONTRACT.md
FINAL_REVIEW_RESULT_AND_HANDOFF_CONTRACT.md
RESOURCE_POLICY_REFERENCE_CONTRACT.md
FINAL_REVIEW_21A_HANDOFF_VALIDATION_CONTRACT.md
FINAL_REVIEW_21B_REAL_LEADER_ACCEPTANCE_CONTRACT.md
schemas/
templates/
tests/
```

The following old role-contract file is superseded and removed by Phase 29A:

```text
FINAL_REVIEW_LEADER_CONTRACT.md
```

## Runtime boundary

This package defines department contracts and the role-bound Final Review Leader operational skill.

The deterministic and real-Leader runtime support currently lives under:

```text
aegis-runtime/final_review/
```

Phase 29A is a role-skill document replacement patch. A later runtime enforcement phase should add a validator similar to Debate, Execution, and Test role-skill validators.

## Non-goals

Phase 29A does not implement production Final Review lifecycle closure, production release review, durable artifact backend, remote branch governance, remote push, PR creation, remote merge, release, deployment, external sign-off, production store writes, or global causal truth merge.
