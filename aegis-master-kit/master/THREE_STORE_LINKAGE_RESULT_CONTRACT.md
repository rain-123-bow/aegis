# Three-Store Linkage Result Contract

## 1. Purpose

This contract defines the Phase 23C local demo result shape emitted by `aegis-runtime/three_store_linkage`.

The result is a validation artifact. It is not Archive persistence, Knowledge persistence, Causal persistence, production store mutation, or global causal truth merge.

## 2. CLI contract

```powershell
python -m aegis_three_store_linkage.cli validate `
  --archive-root <archive-root> `
  --knowledge-root <knowledge-root> `
  --causal-root <causal-root> `
  [--linkage-request <request-json>] `
  [--output <result-json>]
```

## 3. Result shape

```yaml
three_store_linkage_result_id: string
phase: phase23c_three_store_linkage_integrity
status: validated|rejected
decision: accepted_local_three_store_linkage|rejected
reason: string
archive_root: string
knowledge_root: string
causal_root: string
archive_event_count: integer
knowledge_entry_count: integer
causal_fact_count: integer
checked_reference_count: integer
validated_links:
  - source_store: archive|knowledge|causal
    source_id: E0001|K0001|F0001
    field: string
    raw: string|object
    target_store: archive|knowledge|causal
    target_id: E0001|K0001|F0001
    target_path: string
external_refs:
  - source_store: archive|knowledge|causal|request
    source_id: string
    field: string
    raw: string|object
    reason: string
missing_refs:
  - source_store: archive|knowledge|causal|request
    source_id: string
    field: string
    raw: string|object
    target_store: archive|knowledge|causal
    target_id: E0001|K0001|F0001
    reason: string
type_mismatches:
  - source_store: archive|knowledge|causal|request
    source_id: string
    field: string
    raw: string|object
    target_store: archive|knowledge|causal
    target_id: E0001|K0001|F0001
    reason: string
store_boundary_violations:
  - store: archive|knowledge|causal
    id: string
    field: string
    path: string
    reason: string
duplicate_ids:
  - store: archive|knowledge|causal
    id: string
    path: string
    existing_path: string
request_checked: boolean
production_linkage_persistence: false
production_encryption: false
remote_sync_performed: false
archive_store_write_performed: false
knowledge_store_write_performed: false
causal_store_write_performed: false
global_causal_truth_merge_performed: false
ordinary_agent_direct_write_allowed: false
created_at: string
```

## 4. Accepted result

`status: validated` means:

- all detected typed local references resolve;
- all explicit expected links resolve;
- no local store ID duplicates were found;
- no store-boundary truth leakage flags were found;
- no type mismatch was found.

It does not mean:

- production store write succeeded;
- global causal truth was merged;
- all external file paths were verified;
- Archive, Knowledge, or Causal semantics were changed.

## 5. Rejected result

`status: rejected` must be emitted when any of the following is true:

- root store directory is missing;
- optional linkage request is malformed or not Master verified;
- local typed reference is broken;
- local typed reference has the wrong store type;
- Archive `promoted_assets` targets Archive instead of Knowledge or Causal;
- Knowledge `evidence_refs` uses local Knowledge or Causal references instead of Archive or external source material;
- duplicate IDs are found;
- Archive claims truth production;
- Knowledge claims Causal truth production;
- Causal claims production persistence or global causal truth merge.

Rejected results must not mutate Archive, Knowledge, or Causal roots.

## 6. Non-production flags

The following fields must remain false in Phase 23C:

```yaml
production_linkage_persistence: false
production_encryption: false
remote_sync_performed: false
archive_store_write_performed: false
knowledge_store_write_performed: false
causal_store_write_performed: false
global_causal_truth_merge_performed: false
ordinary_agent_direct_write_allowed: false
```
