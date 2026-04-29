# Task Split Contract

## 1. Purpose

This contract prevents the Execution Leader from splitting tasks arbitrarily.

Splitting is allowed only when it follows objective engineering structure.

## 2. Core rule

```text
No proven independence -> no parallel split.
No frozen interaction contract -> no cross-module parallel split.
No local validation criteria -> no valid subtask.
```

## 3. Valid split criteria

A subtask is valid only if all required criteria hold:

1. It has a clear responsibility boundary.
2. Its input and output contracts can be described.
3. Its owned files/modules or ownership scope can be named.
4. Its dependencies are explicit.
5. Its local success criteria are testable or reviewable.
6. Its merge risk is understood.
7. Its Test feedback can be mapped back to the group.
8. Its work can be performed without hidden dependency on an unfinished sibling subtask, unless the dependency is declared and ordered.

## 4. Invalid split patterns

The Leader must reject splits when:

- two groups would modify the same core logic without ownership resolution;
- interface contracts are not frozen;
- one group cannot know what to implement until another group finishes;
- split is based only on file count or workload balancing;
- subtask cannot be independently reviewed;
- integration risk is higher than parallelism benefit;
- failure cannot be attributed to a group;
- scope boundary is semantic fiction rather than real engineering separation.

## 5. Split justification schema

Every split must include:

```yaml
subtask_split:
  parent_task_id: ...
  split_decision: accepted|rejected|needs_debate|needs_contract
  why_split_is_valid: ...
  common_contracts:
    - ...
  subtasks:
    - subtask_id: ...
      responsibility: ...
      owned_files_or_modules:
        - ...
      input_contract: ...
      output_contract: ...
      dependencies:
        - ...
      independence_reason: ...
      local_success_criteria:
        - ...
      expected_branch: ...
      merge_risk: low|medium|high
      feedback_mapping_rule: ...
  rejected_splits:
    - proposal: ...
      why_rejected: ...
```

## 6. Split changes

If implementation or Test feedback proves that the split was invalid, the Leader must record this as a planning failure, not as ordinary group failure.

The Leader must then:

- re-plan;
- request Debate if multiple viable repair plans exist;
- or report a governance/contract blocker to Master.
