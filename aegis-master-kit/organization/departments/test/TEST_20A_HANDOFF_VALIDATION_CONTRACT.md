# Test Phase 20A Handoff Validation Contract

## 1. Purpose

Phase 20A validates that the Test Department can consume an Execution Phase 19B handoff package and produce reproducible test evidence against the sandbox integration branch.

It is intentionally placed before real Test Worker Codex agent acceptance.

## 2. Accepted chain

```text
Execution Phase 19B handoff package
  -> Test Leader
      -> validate handoff fields
      -> validate sandbox local clone
      -> checkout integration branch
      -> run local test command
      -> preserve reproducibility set
      -> preserve artifact manifest
      -> produce scoped Test result
```

## 3. Required target repository

The intended target repository is:

```text
rain-123-bow/aegis-execution-sandbox
```

The repository is business-code target material, not Aegis control-plane code.

## 4. Required input fields

The handoff package must contain:

```yaml
handoff_kind: execution_real_front_back_candidate
target: test
status: ready_for_test_department
run_id: <string>
target_repo: <local path>
base_branch: main
integration_branch: <local branch>
integration_commit: <sha>
changed_files:
  - <repo-relative path>
group_mapping:
  - group_id: <string>
    branch_name: <string>
    touched_files:
      - <repo-relative path>
```

## 5. Test Leader duties

The Test Leader must:

1. verify that the handoff target is `test`;
2. verify that the handoff status is `ready_for_test_department`;
3. verify that the local target repository exists;
4. verify that the target repo is a git repository;
5. verify that the worktree is clean before checkout;
6. checkout the integration branch locally;
7. verify the checked-out commit matches the expected integration commit when provided;
8. run the declared local test command;
9. save stdout, stderr, exit code, branch, commit, changed files, and environment;
10. produce a reproducibility set;
11. produce an artifact manifest;
12. produce a scoped Test result.

## 6. Result labels

If the command succeeds, the accepted status is:

```text
accepted_test_handoff_validation_closure
```

The Test result is:

```text
passed
```

If the command fails with evidence, result is:

```text
failed
```

If handoff material is invalid or target repo is unavailable, result is:

```text
blocked
```

## 7. Forbidden claims

Phase 20A must not be labeled:

```text
accepted_real_test_worker_closure
production_test_lifecycle_closure
```

## 8. Forbidden actions

Phase 20A must not perform:

- source code modification;
- remote push;
- PR creation;
- remote merge;
- release;
- deployment;
- production sign-off;
- global causal truth merge.

## 9. Boundary to Phase 20B

Phase 20B may later introduce real Test Worker Codex agents.

Phase 20A only proves Test Leader handoff validation and local evidence production against a real sandbox integration branch.
