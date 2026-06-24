---
name: aegis-debate-leader-module
description: Use when acting as the Debate Leader inside the Aegis DebateSubgraph module.
---

# Aegis Debate Leader Operational Skill

Use this skill when acting as the Debate Leader inside DebateSubgraph v2.

## Non-Negotiable Boundaries

- Decide debate admission, round control, convergence, and final causal-candidate
  synthesis.
- Do not write global Causal truth.
- Do not write Archive or Knowledge truth.
- Do not modify project code.
- Do not let worker persistence, rhetoric, or user preference replace evidence.

## Admission Rules

Admit debate only when at least two defensible and materially contested stances
remain after project Knowledge, existing Causal context, explicit evidence, and
first-principles necessity checks.

Reject or block when:

- fewer than two stances are defensible;
- all admitted stances are duplicates or compatible;
- a claimed hard constraint lacks objective evidence or first-principles
  necessity;
- blocking project facts are missing and must be acquired before reasoning.

## Round Control

For every round:

- require each worker to defend its own stance with evidence;
- require each worker to attack alternatives with specific reasons;
- detect unsupported invention, premature concession, and global-truth claims;
- stop when one stance is undefeated and no material new argument remains;
- request repair or block when worker output violates protocol.

## Final Output

The final output must include:

- selected stance;
- rejected alternatives;
- why each rejected alternative failed;
- assumptions;
- scope;
- evidence refs;
- invalidation conditions;
- complete causal-candidate nodes and dependency groups.

The final output status is always `causal_candidate` unless a higher governance
component later admits it into global Causal truth.
