# Causal Store Persistence Policy

## 1. Purpose

Phase 22C defines the first Master-owned local Causal Store persistence closure after Phase 22B causal review.

It answers:

```text
How does a reviewed causal decision become a local demo Causal Store fact with semantic history, snapshot, and rollback metadata?
```

Phase 22C is not production Causal Store infrastructure.

It does not implement:

- production encryption
- key lifecycle
- remote sync
- database storage
- multi-client locking
- Archive persistence
- Knowledge persistence
- router/topology changes
- a separate causal-store department
- a long-lived Causal Store Agent

## 2. Accepted input decisions

Phase 22C may persist only Phase 22B decision artifacts with one of these decisions:

```text
stage_canonical_merge_candidate
stage_scope_limited_merge_candidate
stage_supersession_candidate
stage_invalidation_candidate
```

All other Phase 22B decisions must be rejected by persistence:

```text
developer_decision_required
needs_more_evidence
needs_debate
reject_candidate
reject_direct_merge_or_store_write
```

## 3. Local demo persistence boundary

Phase 22C writes a local demo Causal Store layout.

It may create or update files under a caller-provided local causal root:

```text
causal/
  index.yaml
  facts/
    F0001.yaml
  history/
    changelog.md
    changes/
      C0001.yaml
  snapshots/
    S0001.yaml
  rollback/
    R0001.yaml
```

The resulting persistence is a local demo/runtime closure.

It must explicitly record:

```yaml
production_persistence: false
global_causal_truth_merge_performed: false
remote_sync_performed: false
encryption_performed: false
production_encryption: false
archive_store_write_performed: false
knowledge_store_write_performed: false
```

## 4. Serialization format

Phase 22C local demo runtime keeps `.yaml` file names for causal store records because the project-level Causal Store contract historically names facts, index, snapshots, change records, and rollback records as YAML files.

The Phase 22C demo implementation writes **JSON-formatted YAML-compatible payloads** into those `.yaml` files. JSON is a YAML subset, and this keeps the demo runtime dependency-free by using Python `json.loads` / `json.dumps`.

Therefore, for Phase 22C:

```text
file extension = .yaml for Aegis causal store layout compatibility
file payload    = indented JSON, YAML-compatible subset
parser          = json.loads in the demo runtime
```

This is a demo/runtime serialization choice, not a production storage format commitment. A later production backend may use encrypted payloads, real YAML, a database, or another sealed storage format.

## 5. Causal semantic changelog

Phase 22C must write a causal semantic changelog for every accepted persistence operation.

This is not redundant with Git.

```text
Git history = file-level diff history.
Causal semantic changelog = causal-state evolution history.
```

Git can show that a file changed. It does not directly answer:

- which causal fact was added;
- which causal fact was superseded;
- which causal fact was invalidated;
- why the causal state changed;
- which review decision caused the change;
- which evidence supported the change;
- which scopes were affected;
- which rollback record can revert the semantic operation.

Phase 22C therefore must create:

```text
history/changes/Cxxxx.yaml
history/changelog.md
```

for each accepted persistence operation.

## 6. Fact record requirements

A persisted causal fact must include:

```yaml
id: Fxxxx
statement: string
why: string
evidence:
  - string
scope: string
assumptions:
  - string
depends_on:
  - string
supersedes:
  - string
invalidates:
  - string
confidence: object
status: active|superseded|invalidated|tentative
source_review_decision_id: string
created_at: timestamp
updated_at: timestamp
```

A persisted fact must not be a bare conclusion.

## 7. Supersession and invalidation

When a decision stages supersession or invalidation, Phase 22C must update the referenced existing fact files when they exist.

Superseded facts must record:

```yaml
status: superseded
superseded_by: Fxxxx
```

Invalidated facts must record:

```yaml
status: invalidated
invalidated_by: Fxxxx
```

The operation must also be reflected in:

```text
index.yaml
history/changes/Cxxxx.yaml
history/changelog.md
rollback/Rxxxx.yaml
```

## 8. Snapshot and rollback

Each accepted persistence operation must create:

```text
snapshots/Sxxxx.yaml
rollback/Rxxxx.yaml
```

Snapshot captures the post-operation causal index and affected facts.

Rollback metadata captures enough information to undo the local demo persistence operation:

- files created by the operation;
- files updated by the operation;
- previous file contents for updated files;
- source review decision;
- affected fact IDs.

Rollback metadata is local demo metadata, not a production transaction system.

## 9. Rejection rules

Phase 22C must reject persistence when:

- the review decision is not persistable;
- required causal fields are missing;
- direct merge/write flags are true;
- the candidate tries to perform production persistence;
- the decision claims global causal truth merge has already occurred;
- supersession or invalidation references are required but missing;
- a referenced superseded or invalidated fact does not exist in the local causal root;
- a new fact target file already exists with non-identical local content;
- target causal root is invalid or not writable.

## 10. Summary

```text
22A stages causal candidates.
22B reviews causal candidates.
22C persists accepted review artifacts into a local demo Causal Store with semantic changelog, snapshot, and rollback metadata.
```
