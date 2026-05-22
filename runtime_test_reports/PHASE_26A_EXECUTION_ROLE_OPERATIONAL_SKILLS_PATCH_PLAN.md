# Phase 26A Execution Role Operational Skills Patch Plan

## Purpose

Convert Execution Leader, Execution Front Agent, and Execution Back Agent behavior into explicit role-bound operational skills.

## Scope

This patch installs:

```text
EXECUTION_LEADER_OPERATIONAL_SKILL.md
EXECUTION_FRONT_AGENT_OPERATIONAL_SKILL.md
EXECUTION_BACK_AGENT_OPERATIONAL_SKILL.md
EXECUTION_LEADER_FRONT_BACK_SKILL_ENFORCEMENT_CONTRACT.md
```

It removes superseded role-contract files:

```text
EXECUTION_LEADER_CONTRACT.md
FRONT_AGENT_CONTRACT.md
BACK_AGENT_CONTRACT.md
EXECUTION_REAL_FRONT_BACK_AGENT_CONTRACT.md
```

It preserves support contracts such as task split, group, branch/workspace, integration/test handoff, test feedback/rework, and execution causal chain rules.

## Target-Branch Validation Expansion

The patch package expected:

```text
18 passed
```

Target-branch acceptance added stricter tests after live Leader review exposed additional enforcement gaps. The current target-branch expected result is:

```text
26 passed
```

Additional target-branch coverage:

- Front output requires `child_agent_creation_proof_ref`.
- Back review requires `child_agent_creation_proof_ref`.
- Back same-workspace review requires a recorded exception.
- Back reviewed commit must match Front commit.
- Back evidence must include Front branch diff reference.
- Front forbidden true fields are rejected.
- Back forbidden true fields are rejected.

## Validation Target

```powershell
python -m compileall .\aegis-runtime\execution\aegis_execution_runtime
python -m pytest .\aegis-runtime\execution\tests\test_phase26a_execution_role_operational_skills.py -vv
python -m pytest .\aegis-runtime\execution -vv
```

Expected target-branch result:

```text
compileall: passed
targeted Phase 26A tests: 26 passed
full Execution runtime suite: 42 passed
```

## Non-Goals

No router/topology mutation, production branch governance, remote push, PR creation, remote merge, release, deployment, external sign-off, production store write, or global causal truth merge is claimed.
