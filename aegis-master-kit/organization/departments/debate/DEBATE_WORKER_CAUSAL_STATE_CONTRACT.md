# Debate Worker Causal State Contract

## 1. Purpose

This contract defines the local causal state that every request-scoped Debate Worker must maintain while defending one stance.

The goal is to prevent long debate compression from erasing the causal structure behind a worker's position.

A Debate Worker must not rely only on transcript context. Its own local causal state is the authoritative compact representation of its stance.

---

## 2. Scope

This contract applies to Debate Department internal workers only.

It does not create new top-level roles.

It does not allow persistent expert agents, independent evidence collectors, independent scope checkers, or free-form research agents.

```text
Debate Leader
  -> Debate Worker per valid stance
```

Each Debate Worker owns the full personal work for its stance:

- collect information inside allowed evidence boundaries;
- defend its own stance;
- attack competing stances;
- answer attacks;
- narrow scope when required;
- concede when defeated;
- maintain causal state and route/expand priority.

---

## 3. Worker model policy

In the current phase:

```text
Debate Worker -> gpt-5.5 / high
```

Forbidden:

- `medium` Debate Worker;
- fallback;
- silent downgrade;
- worker self-selection of model or budget.

---

## 4. Required local causal state

Every Debate Worker must maintain:

```yaml
worker_local_causal_state:
  run_id: <string>
  worker_id: <string>
  stance_id: <string>
  claim: <string>
  why: <string>
  evidence:
    - type: <string>
      ref: <string>
      relevance: <string>
  scope: <string>
  assumptions:
    - <string>
  depends_on:
    - <fact_or_condition_id>
  rejected_attacks:
    - attack_ref: <string>
      why_rejected: <string>
  accepted_weaknesses:
    - weakness_ref: <string>
      impact: <string>
  scope_narrowing_history:
    - previous_scope: <string>
      new_scope: <string>
      reason: <string>
  invalidation_conditions:
    - <string>
  risk_if_wrong: <string>
  route_priority:
    - id: <string>
      route_grade: A|B|C|D|E|F
      reason: <string>
  expand_priority:
    - id: <string>
      expand_grade: A|B|C|D
      reason: <string>
  status: active|scoped|conceded|needs_evidence
```

---

## 5. Priority meaning

Route priority answers whether a causal item must enter the worker's current reasoning.

```text
A = current stance core; omission changes the argument
B = high relevance; should enter the main defense/attack
C = relevant but deferrable
D = background only
E = indexed but not currently relevant
F = explicitly excluded from current turn
```

Expand priority answers how deeply the worker should unfold that item.

```text
A = statement + why + evidence + scope + assumptions
B = statement + why + scope
C = statement only
D = index only
```

---

## 6. Update triggers

A worker must update local causal state when:

1. it receives a new attack;
2. it finds a weakness in another stance;
3. it accepts a weakness in its own stance;
4. it narrows scope;
5. it requests evidence;
6. it concedes;
7. it detects a failed assumption;
8. it finds an invalidation condition.

---

## 7. First-principles discipline

A Debate Worker must argue from:

- first principles;
- real material conditions;
- evidence;
- explicit assumptions;
- system contracts;
- scope boundaries;
- risk if wrong.

It must not:

- invent evidence;
- add hidden assumptions;
- expand scope silently;
- attack rhetorically;
- concede because of pressure rather than causal defeat;
- keep defending after its core causal support has failed;
- turn debate into endless obstruction.

---

## 8. Output relationship

The worker's local causal state is not global causal truth.

It is evidence for the Debate Leader's adjudication and must be included in the final Debate causal package.
