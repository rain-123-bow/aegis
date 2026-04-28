# Knowledge Entry Contract

## 1. Entry definition

A Knowledge entry is a single neutral fact, constraint, interface rule, environment fact, runtime fact, or objective conditional fact.

Each entry must have:

- immutable id
- neutral statement
- category
- fact_type
- source list
- scope
- version_context
- applicability
- status
- confidence
- lifecycle metadata
- Master approval metadata

## 2. ID rule

Recommended ID format:

```text
KYYYYMMDD-NNN-short-slug
```

Example:

```text
K20260427-001-target-os
K20260427-002-high-temp-downclock
```

Knowledge IDs are immutable and must not be reused.

## 3. Statement rule

Statements must be descriptive and neutral.

Allowed:

```text
Target deployment OS is Ubuntu 22.04.
```

Allowed conditional fact:

```text
When chip temperature exceeds 85 C, target device X severely downclocks.
```

Forbidden:

```text
Therefore the current buffering design is invalid.
```

## 4. Source rule

At least one source is required.

Each source must identify:

- type
- ref
- provided_by or collected_by
- collected_at
- evidence_level

## 5. Applicability rule

Every entry must state where it applies:

- scope
- version_context
- conditions

Empty conditions are allowed only for unconditional facts.

## 6. Status rule

Allowed statuses:

- active
- tentative
- deprecated
- invalidated
- superseded
- conflicted

`active` entries may be used by all roles within declared scope.

`tentative` entries may be used only when explicitly allowed by Master and must be shown as tentative.

`deprecated`, `invalidated`, `superseded`, and `conflicted` entries must not be used as current facts.

## 7. Preservation rule

Entries must not be physically deleted.

Corrections must be represented by status transition, supersession, or amendment history.
