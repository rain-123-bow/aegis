# Causal Routing and Expansion Contract

## Purpose

Causal Store exists partly to fight context compression and context overload.

If every high-value causal structure is injected into every reasoning turn, the system does not reduce reasoning burden. Route and expansion state determine what enters the current reasoning and how deep it expands.

## Current query

Every route plan is generated for a specific `current_query`.

A current query includes:

- query id
- natural-language query
- task type
- goal
- constraints
- policy profile

## Route grade

```text
A = current conclusion directly depends on it; must enter
B = high relevance; should enter
C = relevant but can be delayed
D = background; index only unless needed
E = weakly relevant
F = excluded this round
```

## Expand grade

```text
A = claim + why + evidence + assumptions + relations
B = claim + why + assumptions
C = claim only
D = index only
```

## Dynamic view rule

Route and expand grades are not permanent claim attributes.

They are dynamic route snapshots under a given query, task phase, policy profile, and causal version.

## Seal rule

Route plans and expansion plans must be sealed. Tampering with route priority or expansion depth can change downstream reasoning.

## Model-readable causal view

Master must generate the agent-facing causal view from a verified route plan and expansion plan. The view must include only selected fields according to expansion grade.
