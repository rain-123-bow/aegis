# Execution Final Causal Chain

## Selected Plan

- plan:
- why_this_plan:
- debate_reference:

## Subtask Split

| subtask_id | group_id | independence_reason | branch |
| --- | --- | --- | --- |

## Group Results

| group_id | implementation | review | tests | causal fork |
| --- | --- | --- | --- | --- |

## Integration

- integration_branch:
- merge_result:
- conflicts:
- why_safe:

## Test Feedback

- result: passed|failed
- feedback_decision: test_passed|test_failed_mapped|test_failed_missing_evidence|test_failed_ambiguous_owner
- leader_decision: request_failure_evidence|triage_required|map_to_group|map_to_integration_owner|rework_required|release_groups
- evidence_refs:
- mapped_groups:

## Causal Chain

```yaml
nodes:
  - id: request
    type: request
    statement: ...
    why: ...
edges:
  - from: request
    to: selected_plan
    relation: supports
    why: ...
```

## Invalidation Conditions

- ...

## Status

- status: causal_candidate
- final_decision: submit_causal_fork_to_master|governance_blocker_to_master|rework_required|release_groups
- next_action:
