# Phase 19A Execution Git Topology Patch Plan

## Summary

This patch introduces Phase 19A for the Execution Department.

Phase 19A validates the git/workspace/topology portion of execution before real Codex CLI Front/Back agents are introduced.

## Accepted status

```text
accepted_execution_git_topology_closure
```

## Explicit non-goal

This patch must not claim:

```text
accepted_real_execution_agent_closure
```

## What this patch adds

- Execution git topology closure contract.
- Phase 19A acceptance contract.
- Runtime utility for local git branch creation and Leader-owned integration.
- CLI entry point for running Phase 19A against a local sandbox clone.
- Targeted tests for:
  - group branch creation;
  - integration branch creation;
  - Test handoff package;
  - invalid split rejection;
  - dirty worktree rejection.

## Intended target project

```text
rain-123-bow/aegis-execution-sandbox
```

Use a local clone for testing.

## Boundary

Phase 19A may use deterministic file changes to validate topology.

Real Front Agent and Back Agent Codex CLI execution is deferred to Phase 19B.

## Expected validation commands

```powershell
.\.venv-execution-phase19a\Scripts\python.exe -m pytest .\aegis-runtime\execution\tests\test_execution_git_topology_closure.py -vv
.\.venv-execution-phase19a\Scripts\python.exe -m pytest .\aegis-runtime\execution -vv
```
