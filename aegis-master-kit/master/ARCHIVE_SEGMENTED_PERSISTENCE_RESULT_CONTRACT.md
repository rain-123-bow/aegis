# Archive Segmented Persistence Result Contract

## 1. Purpose

This contract defines the Phase 23A output artifact.

A Phase 23A result is a local demo Archive persistence result.

It is not:

- production Archive persistence;
- production encryption;
- remote sync;
- Knowledge persistence;
- Causal persistence;
- truth production.

## 2. Required result fields

```yaml
archive_persistence_result_id: string
phase: phase23a_archive_segmented_persistence
status: persisted|rejected
decision: persisted|rejected
reason: string
archive_root: string
event_id: string|null
segment_id: string|null
operation: append_event|rollover_and_append|rejected
written_files:
  - string
sealed_segment_ids:
  - string
new_active_segment_id: string|null
rollback_ref: string|null
artifact_manifest_updated: bool
index_updated: bool
changelog_written: bool
segment_sealed: bool
compressed_payload_written: bool
production_archive_persistence: false
production_encryption: false
remote_sync_performed: false
knowledge_store_write_performed: false
causal_store_write_performed: false
archive_produces_truth: false
ordinary_agent_direct_write_allowed: false
created_at: timestamp
```

## 3. Accepted event candidate fields

An accepted `archive_event_candidate` must include at least:

```yaml
candidate_type: archive_event|archive_event_candidate
event_type: string
actor: string
occurred_at: timestamp
evidence_refs:
  - string
scope: string
```

It should include when applicable:

```yaml
task_id: string
responsibility_boundary: string
decision_refs:
  - string
artifact_refs:
  - string
promoted_to_knowledge:
  - string
promoted_to_causal:
  - string
```

## 4. Required local files for successful persistence

Successful persistence must update or create local demo Archive files, for example:

```text
index.yaml
active/segment_xxxx/segment_state.yaml
active/segment_xxxx/events/Exxxx.yaml
active/segment_xxxx/index.yaml
active/segment_xxxx/segment_index.yaml
artifacts/manifest.yaml
history/changelog.md
rollback/Rxxxx.yaml
```

When rollover occurs, it must additionally create:

```text
sealed/segment_xxxx/summary.yaml
sealed/segment_xxxx/index.yaml
sealed/segment_xxxx/seal.yaml
sealed/segment_xxxx/compressed_payload.zip
```

## 5. Required false fields

Every Phase 23A result must preserve:

```yaml
production_archive_persistence: false
production_encryption: false
remote_sync_performed: false
knowledge_store_write_performed: false
causal_store_write_performed: false
archive_produces_truth: false
ordinary_agent_direct_write_allowed: false
```

## 6. Sealed segment rule

A sealed segment is read-only history in Phase 23A.

The runtime must not append new events to a sealed segment.

New writes must use the current active segment.

## 7. Boundary

Phase 23A may persist local demo Archive events under a caller-provided archive root.

It must not claim production Archive closure.


## Rejected result boundary

A rejected Phase 23A result must not create Archive layout files, active segment files, changelog files, or rollback files. Rejection is a pure decision artifact.

## Sealed segment boundary

Successful rollover may create a sealed segment. After sealing, the segment is immutable local history. Later persistence operations must not mutate sealed segment files.
