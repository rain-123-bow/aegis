# Knowledge Conflict Contract

## 1. Conflict definition

A Knowledge conflict exists when two or more entries cannot all be true under the same scope and version_context.

Example:

```text
K001: Target OS is Ubuntu 20.04.
K002: Target OS is Ubuntu 22.04.
```

If both entries have the same target environment scope and version_context, they conflict.

## 2. No dual-active rule

Conflicting entries must not both remain active in the same scope/version_context.

## 3. Master action

Master must either:

- bind entries to different scopes
- bind entries to different version_contexts
- mark one invalidated or superseded
- mark entries conflicted and require more evidence

## 4. Conflict record

Every conflict must be recorded with:

- conflict_id
- involved_entry_ids
- detected_at
- detected_by
- conflict_summary
- required_resolution
- status
- resolution

## 5. Reasoning access rule

Agents must not treat conflicted entries as current facts unless Master explicitly authorizes a constrained investigation mode.
