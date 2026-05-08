# Execution Git Topology Closure Contract

## 1. Purpose

This contract defines Phase 19A for the Execution Department.

Phase 19A validates real local git topology and Leader-owned integration before real Codex CLI Front/Back agent execution is introduced.

It proves that the Execution Department can:

- operate on a real target repository clone;
- validate task split boundaries;
- create one group branch per accepted subtask;
- keep group responsibility records;
- integrate accepted group branches into a Leader-owned integration branch;
- produce a Test handoff package.

## 2. Non-goal

Phase 19A does not prove real Front Agent or Back Agent reasoning.

Front/Back behavior may be deterministic in Phase 19A, provided the result is explicitly labeled as topology closure only.

## 3. Topology

```text
Execution Leader
  -> Execution Group 1
       -> group branch/workspace
  -> Execution Group 2
       -> group branch/workspace
  -> Leader-owned integration branch
  -> Test handoff package
```

## 4. Required git objects

A valid Phase 19A run must produce:

```yaml
base_branch: <string>
base_commit: <sha>
group_branches:
  - group_id: <string>
    subtask_id: <string>
    branch_name: <string>
    commit_sha: <sha>
    touched_files:
      - <repo-relative-path>
integration_branch: <string>
integration_commit: <sha>
changed_files:
  - <repo-relative-path>
```

## 5. Split gate

The Leader must reject the run before creating group branches if:

- two groups claim the same file path without a frozen interface;
- a subtask lacks local validation criteria;
- a subtask lacks responsibility scope;
- a path escapes the target repository;
- the target repository has a dirty worktree;
- the base branch is missing.

## 6. Integration rule

The Leader owns the integration branch.

Groups must not merge themselves into the integration branch.

If integration conflicts occur, the Leader must report them as:

- group responsibility conflict;
- invalid split;
- unfrozen contract;
- changed requirement;
- integration-only conflict.

Manual silent conflict hiding is forbidden.

## 7. Test handoff

The handoff to Test must include:

```yaml
handoff_kind: execution_git_topology_candidate
integration_branch: <string>
integration_commit: <sha>
base_commit: <sha>
changed_files:
  - <path>
group_mapping:
  - group_id: <string>
    branch_name: <string>
    touched_files:
      - <path>
known_limits:
  - Phase 19A uses deterministic local file changes, not real Codex Front/Back execution.
```

## 8. Forbidden actions

Phase 19A must not perform:

- remote push;
- PR creation;
- branch merge on remote;
- release;
- deployment;
- production sign-off;
- global causal merge.

## 9. Acceptance label

A successful Phase 19A run may be labeled:

```text
accepted_execution_git_topology_closure
```

It must not be labeled:

```text
accepted_real_execution_agent_closure
```
