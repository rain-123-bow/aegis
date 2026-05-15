# Knowledge Store Persistence Result Contract

## 1. Purpose

This contract defines the Phase 23B output artifact.

A Phase 23B result is a local demo Knowledge Store persistence result.

It is not:

- production Knowledge persistence;
- production encryption;
- remote sync;
- Archive persistence;
- Causal persistence;
- causal truth production.

## 2. Required result fields

```yaml
knowledge_persistence_result_id: string
phase: phase23b_knowledge_store_persistence
status: persisted|rejected
decision: persisted|rejected
reason: string
knowledge_root: string
entry_id: string|null
operation: add_entry|update_entry|supersede_entry|deprecate_entry|rejected
written_files:
  - string
change_record_id: string|null
rollback_ref: string|null
index_updated: bool
changelog_written: bool
production_knowledge_persistence: false
production_encryption: false
remote_sync_performed: false
archive_store_write_performed: false
causal_store_write_performed: false
knowledge_produces_causal_truth: false
ordinary_agent_direct_write_allowed: false
created_at: timestamp
```

## 3. Accepted candidate fields

An accepted `knowledge_candidate` must include at least:

```yaml
candidate_type: knowledge|knowledge_candidate
statement: string
scope: string
version_context: string
evidence_refs:
  - string
master_verified: true
```

## 4. Required local files for successful persistence

Successful persistence must update or create local demo Knowledge files:

```text
index.yaml
entries/Kxxxx.yaml
history/changes/Cxxxx.yaml
history/changelog.md
rollback/Rxxxx.yaml
```

## 5. Required false fields

Every Phase 23B result must preserve:

```yaml
production_knowledge_persistence: false
production_encryption: false
remote_sync_performed: false
archive_store_write_performed: false
causal_store_write_performed: false
knowledge_produces_causal_truth: false
ordinary_agent_direct_write_allowed: false
```

## 6. Rejected result boundary

A rejected Phase 23B result must not create Knowledge layout files, entry files, changelog files, or rollback files. Rejection is a pure decision artifact.

## 7. Boundary

Phase 23B may persist local demo Knowledge entries under a caller-provided Knowledge root.

It must not claim production Knowledge closure.
