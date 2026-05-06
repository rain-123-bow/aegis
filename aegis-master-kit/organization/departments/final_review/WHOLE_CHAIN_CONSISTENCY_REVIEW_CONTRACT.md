# Whole-Chain Consistency Review Contract

## 1. Purpose

This contract defines the checks Final Review must perform as a whole-chain review gate.

The review is not a set of independent worker subtasks.

It is a single-Leader review over one connected evidence graph.

## Precondition

Whole-chain consistency review may start only after the required Final Review resource policy is satisfied.

If resource policy is unresolved or insufficient, the whole-chain review must not proceed.

Return `blocked_resource_policy`.

## 2. Whole-chain review graph

Final Review must connect:

```text
task objective
-> Master-admitted scope
-> Debate decision, if used
-> Execution plan and split
-> Execution implementation and review evidence
-> Execution integration candidate
-> Test plan
-> Test route evidence
-> Test final result
-> final code reference
-> final recommendation to Master
```

## 3. Candidate object consistency

The Leader must verify consistency between:

```text
implementation_candidate_ref
tested_candidate_ref
final_code_ref
```

If these refer to different material objects without an explicit mapping, acceptance is forbidden.

## 4. Scope consistency

The Leader must compare task scope, Execution changed scope, Test validation scope, covered scope, uncovered scope, known limits, and material conditions.

Hidden uncovered scope blocks unconditional acceptance.

`known_limits` and `material_conditions` are different.

- `material_conditions` describe the conditions under which evidence was produced or conclusions apply.
- `known_limits` describe restrictions, untested areas, incomplete support, or limits on acceptance.

Unconditional `accept_for_master` may include material conditions, but must not include limiting `known_limits`.

## 5. Evidence consistency

The Leader must detect missing, stale, contradictory, non-reproducible, or wrong-object evidence.

## 6. Debate consistency

If Debate was used, Final Review must verify that Debate selected route is referenced by Execution and remains causal candidate, not global truth.

## 7. Execution consistency

The Leader must verify that Execution output is an implementation candidate, not a production merge; responsibility records and rework history are preserved; and no unreviewed code is hidden.

## 8. Test consistency

The Leader must verify that Test result label follows evidence-state semantics, mandatory routes passed for acceptance, reproducibility set exists, artifact manifest exists, and Test did not modify code, assign rework, or route directly to Master.

## 9. Governance consistency

The Leader must verify that acceptance does not bypass topology, Master, Test, Execution responsibility, branch/release policy, or global causal merge authority.

## 10. Review result

The review result must include decision, why, evidence references, accepted scope, blocked scope, known limits, missing evidence, recommended Master action, resource policy status, and causal boundary statement.
