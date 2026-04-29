# Branch and Workspace Contract

## 1. Purpose

This contract makes Execution Group work traceable, reversible, and attributable.

## 2. Branch model

Each Execution Group owns one group branch/workspace derived from the current project branch.

Recommended naming:

```text
execution/<task_id>/<group_id>/<short_name>
```

The Execution Leader creates a separate integration branch after group outputs are accepted.

Recommended naming:

```text
execution/<task_id>/integration
```

## 3. Ownership mapping

The Leader must maintain:

```yaml
branch_ownership:
  task_id: ...
  base_branch: ...
  integration_branch: ...
  groups:
    - group_id: ...
      subtask_id: ...
      branch_name: ...
      owned_files_or_modules:
        - ...
      responsibility: ...
      status: ...
```

## 4. Group branch rules

A group branch must contain only changes required for that group's subtask.

If the group needs to modify outside its scope, it must request Leader approval before continuing.

## 5. Integration branch rules

Only the Execution Leader integrates accepted group branches.

The integration branch is the candidate sent to Test.

Groups must not directly send their group branch to Test unless explicitly authorized for single-group tasks.

## 6. Conflict handling

When merge conflicts occur, the Leader must record conflict id, files, involved groups, cause, resolution, safety reason, and whether replan is required.

`unknown` cannot be accepted as final if the candidate is sent to Test.

## 7. Forbidden repository operations

Execution runtime may create local branches/workspaces in demo or future implementation, but it must not perform remote push, main branch merge, release, production deployment, or external sign-off.
