---
name: aegis-master-subagent-provisioner
version: 2
description: Provision or replace the single independent Master reviewer; A-F roles are created dynamically by the runtime.
---

# Master Reviewer Provisioner

## Scope

This skill provisions only `MASTER_REVIEWER`.

Master directly authors requirements, implementation plans, code, and causal facts. These responsibilities must never be delegated.

A-F roles are not provisioned here. RuntimeCoordinator creates or resumes their persistent Codex App Server threads from dynamic role templates.

## Reviewer contract

- One independent reviewer may review both requirements and implementation plans.
- The reviewer uses a thread distinct from Master.
- Requirement review reads the complete requirement artifact.
- Implementation-plan review reads both the frozen requirement and the complete plan.
- The reviewer returns findings and evidence; Master reads the original review artifact.
- The reviewer never edits Master artifacts.
- Missing reviewer blocks approval.

## Persistence

Reviewer identity belongs under the project runtime root, never under `.aegis/` and never in `config/agent_registry.json`.

Persist project ID, role, thread ID, lifecycle, model, effort, instruction/skill hashes, timestamps, replacement relationship, and retirement reason. Static repository config contains templates only.

## Lifecycle

1. Resolve project ID and runtime root.
2. Resume a matching active reviewer.
3. Retire a faulty or contract-mismatched reviewer with evidence.
4. Create a replacement linked to the retired thread.
5. Never reuse a reviewer across projects or as an A-F role.
6. Never close a healthy reviewer because one workflow ended.

If the agent creation interface is unavailable, stop. Do not fabricate identity or registry state.

## Forbidden

- Delegating Master authorship.
- Precreating A-F threads.
- Writing runtime state under `.aegis/`.
- Writing real thread IDs to static config.
- Reusing Master as its own reviewer.

## Completion

Completion requires a real resumable reviewer thread and durable project-scoped runtime record. Otherwise report a blocker.
