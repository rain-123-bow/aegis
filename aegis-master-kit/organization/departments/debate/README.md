# Debate Department

## Purpose

The Debate Department is the top-level adversarial reasoning department under the Master-governed organization.

It exists to resolve ambiguous, high-impact, multi-solution, or causally incomplete questions before they affect project direction.

It is not a general chat room, not a brainstorming pool, and not a permanent worker team.

## Department boundary

The Department exposes exactly one top-level identity to the Master-layer topology:

```text
debate
```

The top-level `debate` identity is the Debate Leader. It communicates with Master and Execution through the already-defined top-level route contract.

Internal Debate Workers are department-local, request-scoped, and temporary. They must not be exposed as top-level organization members.

## Internal shape

```text
Debate Department
  Debate Leader         long-lived department leader
    Debate Worker N     request-scoped stance-bound worker
    Debate Worker N+1   request-scoped stance-bound worker
    ...
```

The Leader receives a debate request, splits it into multiple independent defensible stances, creates one temporary worker per stance, runs a leader-mediated adversarial process, adjudicates the result, releases temporary resources, and returns a causally complete result to the request sender.

## Core rule

A Debate Worker is disposable. A Debate Result is not.

```text
worker lifecycle: per request, temporary, releasable
causal result: persistent, reviewable, transferable, merge-candidate
```

## Why causal structure is mandatory

The Debate Department must preserve causal structure, not merely conclusions.

A conclusion without its cause can be mistaken for an unconditional fact. Most engineering conclusions are not unconditional facts. They hold only under concrete material conditions, assumptions, constraints, evidence, and scope.

Example:

```text
Conclusion-only record:
CPU usage must not exceed 60%.
```

This looks like a static rule.

But the real causal structure may be:

```text
Because the current chip is weak and higher CPU usage would reduce scheduling margin for critical tasks, CPU usage must not exceed 60% on this platform.
```

If the chip is later replaced with a stronger chip, the condition that supported the conclusion may disappear. The old conclusion should then be rechecked, narrowed, or invalidated. If only the conclusion was stored, the system would not know what condition changed and would preserve a stale rule as if it were objective reality.

Therefore every Debate Result must preserve:

- why the selected position was selected;
- why alternatives were rejected, scoped, or deferred;
- which assumptions support the result;
- which material conditions sustain the result;
- which condition changes would invalidate or reopen the result;
- what action impact follows from the result.

This is a hard department rule.

## Contract files

- `DEBATE_DEPARTMENT_CONTRACT.md` — department-level contract.
- `DEBATE_LEADER_CONTRACT.md` — leader responsibility and authority.
- `DEBATE_WORKER_CONTRACT.md` — temporary worker behavior contract.
- `DEBATE_RUN_LIFECYCLE.md` — request-scoped lifecycle.
- `INTERNAL_TOPOLOGY_CONTRACT.md` — leader-mediated round-robin broadcast topology.
- `ADJUDICATION_AND_CAUSAL_OUTPUT_RULES.md` — adjudication and final causal output requirements.
- `CAUSAL_STRUCTURE_RATIONALE.md` — first-principles reason for preserving causal structure instead of conclusions.
- `schemas/` — machine-readable contract shapes.
- `templates/` — authoring templates.
- `tests/` — Codex / agent constraint tests.

## Non-goals

This package does not implement runtime code, nested-codex invocation, process management, or production security.

It defines the Debate Department contract that runtime/demo code must obey.
