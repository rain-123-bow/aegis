# Execution Department

## Definition

The Execution Department converts admitted work into reviewable engineering candidates.

It is not a generic code-writing agent. It is a governed engineering department with explicit task splitting, branch ownership, internal implementation/review units, integration responsibility, test feedback handling, and causal handoff.

## External boundary

At the Master-layer topology, the whole department appears as the top-level role:

```text
execution
```

The Execution Leader is the only external department boundary.

Internal Execution Groups must not become top-level Master-route agents.

## Internal model

```text
Execution Leader
  -> plan and admissibility check
  -> optional execution -> debate route when multiple suitable non-dominated plans exist
  -> objectively justified subtask split
  -> one Execution Group per independent subtask
  -> each group has:
       - Front Agent: implementation and module/local tests
       - Back Agent: independent review and first-principles challenge
  -> group-owned branch/workspace
  -> Leader review
  -> integration branch
  -> execution -> test handoff
  -> test feedback handling
  -> final execution causal_chain
  -> execution -> master causal candidate handoff
```

## Core invariants

1. The Leader must not split tasks merely to create parallelism.
2. A subtask split is valid only when independence, contract boundary, ownership, and validation criteria can be proven.
3. Multiple solution plans trigger Debate only when several plans are suitable, each has meaningful trade-offs, and no plan has a complete/dominant advantage by engineering practice.
4. Every Execution Group owns exactly one independent subtask and one group branch.
5. Each Execution Group contains a Front Agent and a Back Agent.
6. The Back Agent has real rejection and evidence-request authority.
7. The group persists until the project phase is closed or the Leader explicitly releases it after successful test feedback and causal handoff.
8. Test must provide feedback whether the candidate passes or fails.
9. Failed test feedback must be mapped back to responsible Execution Groups before rework.
10. Passed test feedback allows the Leader to release groups but not delete responsibility records.
11. Execution outputs causal candidates and branch-local causal forks. It does not merge global causal truth.

## Key files

```text
EXECUTION_DEPARTMENT_CONTRACT.md
EXECUTION_LEADER_CONTRACT.md
TASK_SPLIT_CONTRACT.md
DECISION_TO_DEBATE_RULES.md
EXECUTION_GROUP_CONTRACT.md
FRONT_AGENT_CONTRACT.md
BACK_AGENT_CONTRACT.md
BRANCH_AND_WORKSPACE_CONTRACT.md
INTEGRATION_AND_TEST_HANDOFF_CONTRACT.md
TEST_FEEDBACK_AND_REWORK_CONTRACT.md
EXECUTION_CAUSAL_CHAIN_RULES.md
schemas/
templates/
tests/
```

## Runtime boundary

This package defines department contracts only.

The future runtime implementation belongs under:

```text
aegis-runtime/execution/
```
