# Knowledge Contract

## 1. Definition

Knowledge is the project-level neutral fact and constraint store.

It records objective facts, external constraints, runtime conditions, environment facts, platform facts, and project rules that may be used by all roles during reasoning and task execution.

Knowledge is not Archive and is not Causal.

```text
Archive   = historical task audit records.
Knowledge = neutral known facts and constraints.
Causal    = reusable reasoning truths with why/evidence/scope/assumptions.
```

## 2. Global validity model

A Knowledge entry is globally valid only inside its declared:

- scope
- version_context
- applicability conditions
- status

Global validity does not mean unconditional validity.

Conditional Knowledge is allowed when it describes an objective condition-triggered fact.

Example:

```text
If chip temperature exceeds 85 C, target device X severely downclocks.
```

This is Knowledge if the condition is observable and source-backed.

## 3. Neutrality rule

Knowledge must be neutral.

Knowledge may say:

```text
Target deployment OS is Ubuntu 22.04.
```

Knowledge must not say:

```text
Therefore solution A is better than solution B.
```

Knowledge must not encode strategy, preferences, causal conclusions, blame, or responsibility.

## 4. Source rule

Every Knowledge entry must have at least one source.

Entries without source are invalid and must not be admitted as active Knowledge.

Allowed source types include:

- developer_input
- agent_observation
- test_result
- runtime_log
- code_inspection
- vendor_doc
- customer_requirement
- external_spec
- project_document

## 5. Master admission rule

Developer and agents may submit Knowledge proposals.

Only Master may approve a proposal into Knowledge.

Developer input is not automatically a fact. It must be admitted with a status and confidence appropriate to its evidence level.

## 6. Preservation rule

Knowledge entries are append-preserved.

Historical entries must not be physically deleted or silently rewritten.

Obsolete or false entries must be retained with status and reason metadata:

- deprecated
- invalidated
- superseded
- conflicted

## 7. Conflict rule

Within the same scope and version_context, two conflicting facts must not both be active.

Conflicts must be marked and escalated to Master for review.

## 8. Security rule

Project Knowledge must be encrypted at rest in the local repository and protected by Master-private integrity mechanisms.

Private security material must never be exposed to developer, ordinary agents, logs, or repository files.
