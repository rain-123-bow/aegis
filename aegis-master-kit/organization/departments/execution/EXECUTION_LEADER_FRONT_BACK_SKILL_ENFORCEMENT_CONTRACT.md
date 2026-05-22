# Execution Leader / Front / Back Skill Enforcement Contract

```yaml
contract_id: EXECUTION_LEADER_FRONT_BACK_SKILL_ENFORCEMENT_CONTRACT
version: v0.1
phase: phase26a_execution_role_operational_skills
```

## Purpose

This contract defines the local validation boundary for Phase 26A Execution role-bound operational skills.

Phase 26A converts Execution Leader, Execution Front Agent, and Execution Back Agent role behavior into explicit operational skills.

It validates skill usage and work-chain evidence only. It does not perform production execution, remote push, PR creation, remote merge, release, deployment, external sign-off, production store writes, or global causal truth merge.

## Required skills

```yaml
leader_skill:
  skill_id: EXECUTION_LEADER_OPERATIONAL_SKILL
  skill_version: v0.3
front_skill:
  skill_id: EXECUTION_FRONT_AGENT_OPERATIONAL_SKILL
  skill_version: v0.3
back_skill:
  skill_id: EXECUTION_BACK_AGENT_OPERATIONAL_SKILL
  skill_version: v0.3
```

## Enforcement requirements

A validated Execution run must prove:

- the Leader references `EXECUTION_LEADER_OPERATIONAL_SKILL v0.3`;
- every Front creation request references `EXECUTION_FRONT_AGENT_OPERATIONAL_SKILL v0.3`;
- every Back creation request references `EXECUTION_BACK_AGENT_OPERATIONAL_SKILL v0.3`;
- every child Front/Back Agent has a `child_agent_creation_proof`;
- final Front/Back acceptance requires non-empty `thread_id`;
- every `thread_id` matches the corresponding creation proof;
- root `MODEL_REASONING_BUDGET_POLICY.yaml` is the model-policy authority;
- every group has an independent group workspace and base-derived group branch;
- no group branch is orphan or unborn;
- Front works only on its group work branch;
- Back reviews the real group branch diff;
- Back uses an independent audit workspace unless a structured same-workspace exception is recorded;
- all groups have accepted Back reviews before Leader integration;
- Leader integration branch derives from the Aegis work branch/base commit;
- Test handoff targets the Leader integration branch;
- Execution output remains a causal candidate, not global causal truth.

## Required false fields

```yaml
remote_push_performed: false
pull_request_created: false
remote_merge_performed: false
release_performed: false
deployment_performed: false
external_signoff_performed: false
global_causal_truth_merge_performed: false
production_store_write_performed: false
```
