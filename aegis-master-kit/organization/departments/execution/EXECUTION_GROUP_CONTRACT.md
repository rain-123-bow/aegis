# Execution Group Contract

## 1. Definition

An Execution Group is a project-phase responsibility unit created by the Execution Leader for one independent subtask.

Unlike a Debate Worker, an Execution Group is not released immediately after first output.

It remains responsible through implementation, local review, integration, Test feedback, rework if needed, and final release.

## 2. Composition

Each Execution Group contains exactly:

```text
Front Agent -> implementation and local/module tests
Back Agent  -> independent review and first-principles challenge
```

## 3. Binding

A group is bound to group id, parent task id, subtask id, responsibility scope, group branch/workspace, expected files/modules, local success criteria, Front Agent, Back Agent, and lifecycle record.

The group must not silently expand its scope.

## 4. Lifecycle states

```text
CREATED
PLANNING
IMPLEMENTING
MODULE_TESTING
INTERNAL_REVIEW
CHANGES_REQUESTED
READY_FOR_LEADER
INTEGRATED
UNDER_TEST
TEST_FAILED
REWORK_REQUIRED
REWORKING
REINTEGRATED
TEST_PASSED
ACCEPTED
RELEASED
```

## 5. Persistence rule

The group remains active until Test passes and the Leader releases the group after final causal handoff, the project phase is closed, Master cancels the task, or responsibility is explicitly reassigned with cause.

## 6. Test feedback responsibility

When Test reports a failure, the Leader maps the failure to group(s). The original responsible group must handle the fix unless the Leader proves that reassigning is necessary.

The group must preserve failure feedback id, evidence refs, root cause analysis, fix branch or fix commit ref, Back Agent review of fix, and resubmission result.

## 7. Group output

A group output must include:

```yaml
group_result:
  group_id: ...
  subtask_id: ...
  branch_name: ...
  changed_files:
    - path: ...
      change_type: add|modify|delete
      why_changed: ...
  local_tests:
    - command: ...
      result: pass|fail|not_run
      evidence_ref: ...
  front_report_ref: ...
  back_review_ref: ...
  unresolved_objections:
    - ...
  causal_fork:
    statement: ...
    why: ...
    evidence:
      - ...
    scope: ...
    assumptions:
      - ...
    invalidation_conditions:
      - ...
    status: causal_candidate
```

## 8. Release rule

Releasing a group deactivates active agent/workspace resources.

It must not delete responsibility records, branch records, review records, Test feedback, causal forks, or final causal output.
