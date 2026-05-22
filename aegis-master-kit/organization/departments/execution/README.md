# Execution Department

## Purpose

The Execution Department converts admitted executable work into reviewable, integrated, testable engineering candidates.

It is not a generic code-writing pool. It is a governed engineering department with explicit contract-first checks, objective task splitting, independent group workspaces, Front/Back implementation-review units, Leader-owned integration, Test feedback handling, and causal handoff.

## Department boundary

At the Master-layer topology, the whole department appears as the top-level role:

```text
execution
```

The Execution Leader is the only external department boundary. Internal Execution Groups, Front Agents, and Back Agents must not become top-level Master-route agents.

## Role-bound operational skills

Phase 26A moves Execution Leader / Front Agent / Back Agent role behavior from role contracts into explicit operational skills:

```text
EXECUTION_LEADER_OPERATIONAL_SKILL.md
EXECUTION_FRONT_AGENT_OPERATIONAL_SKILL.md
EXECUTION_BACK_AGENT_OPERATIONAL_SKILL.md
EXECUTION_LEADER_FRONT_BACK_SKILL_ENFORCEMENT_CONTRACT.md
```

The Leader skill defines the full Execution Leader work chain:

```text
admitted request -> contract-first check -> split gate -> independent group workspaces -> group branches -> Front/Back skill installation -> thread_id-based supervision -> Back-gated group readiness -> Leader-owned integration branch -> Test handoff -> Test feedback routing -> final execution causal handoff
```

The Front skill defines the Front Agent work chain:

```text
one group -> verify skill and branch proof -> work only in group workspace / group work branch -> implement -> local validation -> commit -> front_output + group causal fork
```

The Back skill defines the Back Agent work chain:

```text
one group -> verify skill and branch proof -> use independent audit workspace by default -> review real group branch diff -> check tests/contracts/scope/risk -> emit back_review
```

## Mandatory child skill installation

The Execution Leader must not create a Front or Back Agent unless the creation request includes the required skill reference:

```yaml
front_skill_ref:
  skill_id: EXECUTION_FRONT_AGENT_OPERATIONAL_SKILL
  skill_version: v0.3
  required: true
back_skill_ref:
  skill_id: EXECUTION_BACK_AGENT_OPERATIONAL_SKILL
  skill_version: v0.3
  required: true
```

Front/Back outputs are invalid unless they prove:

```yaml
skill_received: true
skill_applied: true
```

## Core git topology rule

Each Execution Group uses its own independent workspace and group work branch:

```text
aegis_work_branch
  -> group_workspace_N
      -> group_work_branch_N
          -> Front implements
          -> Back reviews same group_work_branch

all accepted group_work_branch_N
  -> Leader-created leader_integration_branch
  -> Test handoff
```

Front must not work directly on `aegis_work_branch`. Back must not accept without reviewing the real group branch diff. Leader must not create the integration branch until required group Back reviews are accepted.

## Remaining support files

The following files remain as department support material until later phases decide whether they should also become skills:

```text
EXECUTION_DEPARTMENT_CONTRACT.md
TASK_SPLIT_CONTRACT.md
DECISION_TO_DEBATE_RULES.md
EXECUTION_GROUP_CONTRACT.md
BRANCH_AND_WORKSPACE_CONTRACT.md
INTEGRATION_AND_TEST_HANDOFF_CONTRACT.md
TEST_FEEDBACK_AND_REWORK_CONTRACT.md
EXECUTION_CAUSAL_CHAIN_RULES.md
EXECUTION_GIT_TOPOLOGY_CLOSURE_CONTRACT.md
EXECUTION_19A_ACCEPTANCE_CONTRACT.md
EXECUTION_19B_ACCEPTANCE_CONTRACT.md
schemas/
templates/
tests/
```

The following old role-contract files are superseded and removed by Phase 26A:

```text
EXECUTION_LEADER_CONTRACT.md
FRONT_AGENT_CONTRACT.md
BACK_AGENT_CONTRACT.md
EXECUTION_REAL_FRONT_BACK_AGENT_CONTRACT.md
```

## Non-goals

Phase 26A does not implement production branch governance, production worker supervision, remote push, PR creation, remote merge, release, deployment, external sign-off, production store writes, or global causal truth merge.
