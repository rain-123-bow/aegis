# Knowledge Status Contract

## 1. Status values

```text
active       = current accepted fact within declared scope/version/conditions
tentative    = usable only with explicit Master permission and visible uncertainty
deprecated  = obsolete or discouraged for new reasoning, retained for history
invalidated = false or no longer valid, retained with invalidation reason
superseded  = replaced by newer Knowledge entry
conflicted   = conflicts with another entry and awaits Master resolution
```

## 2. No deletion rule

Knowledge entries must not be deleted when obsolete or false.

They must be retained with status transition metadata.

## 3. Required invalidation metadata

When an entry is invalidated, the entry must record:

- invalidated_at
- invalidated_by
- invalidation_reason
- invalidation_evidence
- superseded_by, if applicable

## 4. Required supersession metadata

When an entry is superseded, both sides must record the relationship:

```text
old_entry.superseded_by = new_entry
new_entry.supersedes = old_entry
```

## 5. Terminal non-current statuses

These statuses must not be used as current facts:

- deprecated
- invalidated
- superseded
- conflicted

They remain queryable for audit, traceability, and historical explanation.
