# Causal Store Persistence Result Contract

## 1. Purpose

This contract defines the Phase 22C output artifact.

A Phase 22C result is a local demo Causal Store persistence result.

It is not:

- production persistence;
- remote sync;
- encryption;
- canonical production database write;
- Archive or Knowledge persistence.

## 2. Required result fields

```yaml
persistence_result_id: string
phase: phase22c_causal_store_persistence
status: persisted|rejected
decision: string
reason: string
source_review_decision_id: string
source_decision: string
fact_id: string|null
operation: add_fact|scope_limited_add|supersede|invalidate|rejected
added_facts:
  - string
updated_facts:
  - string
written_files:
  - string
change_record_id: string|null
snapshot_id: string|null
rollback_ref: string|null
semantic_changelog_written: bool
index_updated: bool
snapshot_written: bool
rollback_metadata_written: bool
production_persistence: false
global_causal_truth_merge_performed: false
remote_sync_performed: false
encryption_performed: false
production_encryption: false
archive_store_write_performed: false
knowledge_store_write_performed: false
created_at: timestamp
```

## 3. Required local files for successful persistence

A successful persistence result must reference these local files:

```text
facts/Fxxxx.yaml
index.yaml
history/changes/Cxxxx.yaml
history/changelog.md
snapshots/Sxxxx.yaml
rollback/Rxxxx.yaml
```

## 4. Serialization boundary

The required local files use `.yaml` names to match the Causal Store layout.

Phase 22C demo runtime writes JSON-formatted YAML-compatible payloads into those `.yaml` files and reads them with `json.loads`.

This is intentional:

```text
.yaml path names preserve the Aegis Causal Store layout.
JSON payloads keep the demo runtime dependency-free.
JSON is a YAML subset.
```

A later production backend may replace this serialization format. Phase 22C does not claim production storage format closure.

## 5. Required false fields

Every Phase 22C result must preserve:

```yaml
production_persistence: false
global_causal_truth_merge_performed: false
remote_sync_performed: false
encryption_performed: false
production_encryption: false
archive_store_write_performed: false
knowledge_store_write_performed: false
```

## 6. Semantic changelog requirement

A successful result must set:

```yaml
semantic_changelog_written: true
```

The semantic changelog must describe causal-state operations, not Git diffs.

## 7. Rejected result

A rejected result must include:

```yaml
status: rejected
fact_id: null
written_files: []
semantic_changelog_written: false
index_updated: false
snapshot_written: false
rollback_metadata_written: false
```

## 8. Boundary

Phase 22C may persist local demo facts under a provided causal root.

It must not claim production Causal Store closure.
