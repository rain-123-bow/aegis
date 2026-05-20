# Debate Department

## Purpose

The Debate Department is the top-level adversarial reasoning department under the Master-governed organization.

It exists to resolve ambiguous, high-impact, multi-solution, causally incomplete, or project-directional questions before they affect implementation or long-term causal state.

It is not a general chat room, not a brainstorming pool, and not a permanent worker team.

## Department boundary

The Department exposes exactly one top-level identity to the Master-layer topology:

```text
debate
```

The top-level `debate` identity is the Debate Leader. It communicates with Master and Execution through the already-defined top-level route contract.

Internal Debate Workers are department-local, request-scoped, stance-bound, and temporary. They must not be exposed as top-level organization members.

## Role-bound operational skills

Phase 25A moves Debate Leader / Worker behavior from role contracts into explicit operational skills:

```text
DEBATE_LEADER_OPERATIONAL_SKILL.md
DEBATE_WORKER_OPERATIONAL_SKILL.md
DEBATE_LEADER_WORKER_SKILL_ENFORCEMENT_CONTRACT.md
```

The Leader skill defines the full Debate Leader work chain:

```text
receive request -> admission -> stance split -> Worker creation -> Worker skill installation -> topology -> turn control -> adjudicator causal state -> causal adjudication -> complete causal package -> cleanup -> Master handoff
```

The Worker skill defines the full Debate Worker work chain:

```text
receive one stance -> verify skill and boundary -> initialize local causal state -> defend -> attack -> answer -> update state -> narrow scope / request evidence / concede -> emit structured Worker evidence
```

## Mandatory Worker skill installation

A Debate Leader must not create a Debate Worker unless the Worker creation request includes:

```yaml
worker_skill_ref:
  skill_id: DEBATE_WORKER_OPERATIONAL_SKILL
  skill_version: v0.1
  required: true
```

A Worker output is invalid unless it proves:

```yaml
skill_ref:
  skill_id: DEBATE_WORKER_OPERATIONAL_SKILL
  skill_version: v0.1
skill_received: true
skill_applied: true
```

## Core rule

A Debate Worker is disposable. A Debate result is not.

```text
worker lifecycle: per request, temporary, releasable
causal result: persistent, reviewable, transferable, merge-candidate
```

## Why causal structure is mandatory

The Debate Department must preserve causal structure, not merely conclusions.

A conclusion without its cause can be mistaken for an unconditional fact. Most engineering conclusions are not unconditional facts. They hold only under concrete material conditions, assumptions, constraints, evidence, and scope.

Therefore every Debate result must preserve:

- why the selected position was selected;
- why alternatives were rejected, scoped, or deferred;
- which assumptions support the result;
- which material conditions sustain the result;
- which condition changes would invalidate or reopen the result;
- what action impact follows from the result.

This is a hard department rule.

## Remaining support files

The following files remain as department support material until later phases decide whether they also become skills:

```text
DEBATE_DEPARTMENT_CONTRACT.md
DEBATE_RUN_LIFECYCLE.md
INTERNAL_TOPOLOGY_CONTRACT.md
DEBATE_RESULT_MAILBUCKET_PACKAGE_CONTRACT.md
CAUSAL_STRUCTURE_RATIONALE.md
schemas/
templates/
tests/
```

The following old role-contract files are superseded and removed by Phase 25A:

```text
DEBATE_LEADER_CONTRACT.md
DEBATE_WORKER_CONTRACT.md
DEBATE_WORKER_CAUSAL_STATE_CONTRACT.md
DEBATE_ADJUDICATOR_CAUSAL_STATE_CONTRACT.md
ADJUDICATION_AND_CAUSAL_OUTPUT_RULES.md
```

## Non-goals

This package does not implement production process management, production security, remote push, PR creation, remote merge, release, external sign-off, or global causal truth merge.

It defines the Debate Department role-bound operational skills that runtime/demo code must obey.
