# Execution Phase 19A Acceptance Contract

## 1. Phase definition

Phase 19A is the Execution Department git topology acceptance phase.

It is intentionally placed before real Front/Back Codex CLI agent acceptance.

## 2. Accepted chain

```text
Master
  -> Execution Leader
      -> target sandbox local clone
      -> split validation
      -> Execution Groups
      -> group branches
      -> Leader integration branch
      -> Test handoff package
```

## 3. Required target repository

The intended target repository is:

```text
rain-123-bow/aegis-execution-sandbox
```

The repository must be used as a business-code sandbox, not as Aegis control-plane code.

## 4. Master boundary

Master may create or call the Execution Leader.

Master must not directly create Execution Groups, Front Agents, Back Agents, or group branches.

## 5. Execution Leader duties

The Execution Leader must:

1. verify the request has objective, scope, constraints, and success criteria;
2. verify the target repo exists locally and is clean;
3. validate the split;
4. create one group branch per accepted independent subtask;
5. preserve group responsibility records;
6. create the Leader-owned integration branch;
7. merge accepted group branches;
8. produce the Test handoff package;
9. preserve the execution causal candidate.

## 6. Group boundary

An Execution Group is an internal responsibility unit.

In Phase 19A the group branch proves topology and responsibility mapping. It does not yet prove real Front/Back agent execution.

## 7. Test handoff package

The package must contain:

```text
README.md
execution_git_topology_report.json
test_handoff_package.json
group_records/<group_id>.json
```

## 8. Strict boundaries

Phase 19A must preserve these boundaries:

- deterministic group changes are allowed only for topology validation;
- in-process or deterministic changes must not be mislabeled as real Codex agent work;
- no remote push / PR / merge / release;
- no production lifecycle claim;
- no global causal truth claim.

## 9. Completion status

If the local git topology and handoff package are complete, the accepted status is:

```text
accepted_execution_git_topology_closure
```
