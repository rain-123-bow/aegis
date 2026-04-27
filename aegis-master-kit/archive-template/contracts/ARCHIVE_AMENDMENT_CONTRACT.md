# Archive Amendment Contract

## 1. Purpose

Archive records must be correctable without destroying history.

Amendment is the only valid method to correct a sealed Archive record.

## 2. No silent overwrite

After a task, decision, timeline event, artifact record, or outcome is sealed, it must not be silently overwritten.

Corrections must be appended as amendment records.

## 3. Amendment triggers

An amendment is required when:

- a sealed field is wrong
- a task title changes after sealing
- a responsibility record is corrected
- a timestamp is corrected
- an artifact reference changes
- a decision is superseded
- an outcome is clarified
- sensitive content must be redacted
- an integrity issue is repaired

## 4. Amendment fields

Each amendment record must include:

```yaml
amendment_id: A001
amended_at: <timestamp>
amended_by: <master id>
requested_by: <actor or null>
reason: <why correction is needed>
target:
  file: <plaintext payload path or logical path>
  field: <field path or section id>
previous_value_ref: <opaque or summarized previous value>
new_value: <new value or summary>
evidence_refs:
  - <reference>
approval:
  required: true|false
  approved_by: <human/master/null>
  approved_at: <timestamp or null>
seal_ref: <seal id>
```

## 5. Amendment visibility

Public metadata may expose that an amendment occurred, but must not expose sensitive details unless explicitly allowed.

## 6. Repair after unauthorized mutation

If direct mutation is detected, Master must not silently normalize the local files.

Master must:

1. mark violation
2. stop trusting the local Archive copy
3. compare against latest trusted seal if available
4. recover from trusted source or request human decision
5. append amendment or incident record if recovery proceeds
6. generate a new seal

## 7. Supersession

A task may supersede another task.

Supersession must be explicit:

```yaml
supersedes:
  - T20260427-001-old-task
superseded_by:
  - T20260427-002-new-task
```

Supersession does not delete the old task.
