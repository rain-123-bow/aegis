# Knowledge Store Persistence Policy

## 1. Purpose

Phase 23B defines the first Master-owned local Knowledge Store persistence closure.

It answers:

```text
How does a Master-approved knowledge_candidate become a local demo Knowledge entry with index, changelog, and rollback metadata?
```

Phase 23B is not production Knowledge infrastructure.

It does not implement:

- production Knowledge backend
- production encryption
- key lifecycle
- remote sync
- Archive persistence
- Causal persistence
- router/topology changes
- a separate knowledge-store department
- a long-lived knowledge runtime agent profile

## 2. Knowledge boundary

Knowledge records what is known: verified neutral facts, constraints, interfaces, environment facts, policy facts, version facts, and glossary facts.

Knowledge does not record task history.

Knowledge does not produce Causal truth.

Knowledge does not record:

- task history
- responsibility chains
- discussion trajectory
- causal conclusions
- strategic judgments
- implementation opinions
- unreviewed developer claims as active facts

Knowledge may contain objective conditional facts when the condition and result are source-backed.

Knowledge must not contain causal reasoning chains such as:

```text
because X, therefore design Y is correct
```

Causal-shaped proposals must go through Causal admission and review instead.

## 3. Accepted input candidates

Phase 23B may persist only Master-approved Knowledge candidates.

Accepted candidate shape:

```yaml
candidate_type: knowledge|knowledge_candidate
statement: string
scope: string
version_context: string
evidence_refs:
  - string
master_verified: true
category: platform|environment|constraint|interface|dependency|policy|glossary|fact|other
```

Optional operation fields:

```yaml
operation: add|add_entry|update|update_entry|supersede|supersede_entry|deprecate|deprecate_entry
target_entry_id: Kxxxx
supersedes:
  - Kxxxx
deprecates:
  - Kxxxx
```

## 4. Rejection rules

Phase 23B must reject persistence when:

- required Knowledge fields are missing;
- candidate is not Master verified;
- claim status is developer_asserted and not verified;
- candidate contains causal shape: `why`, `depends_on`, `invalidates`, `supersedes` used as causal reasoning without Knowledge operation, `causal_chain`, or causal conclusion markers;
- candidate is archive-event-shaped: `event_type`, `actor`, `occurred_at` as task history;
- candidate attempts Archive or Causal writes;
- candidate attempts production Knowledge persistence;
- candidate claims global truth or causal truth;
- supersession/deprecation references are missing or do not exist;
- target files would be overwritten with non-identical content.

Rejected candidates must not create Knowledge Store layout files.

## 5. Local demo persistence layout

Phase 23B writes a local demo Knowledge Store layout:

```text
knowledge/
  index.yaml
  entries/
    K0001.yaml
  history/
    changelog.md
    changes/
      C0001.yaml
  rollback/
    R0001.yaml
```

The resulting persistence is a local demo/runtime closure.

It must explicitly record:

```yaml
production_knowledge_persistence: false
production_encryption: false
remote_sync_performed: false
archive_store_write_performed: false
causal_store_write_performed: false
knowledge_produces_causal_truth: false
```

## 6. Knowledge changelog

Phase 23B must write a semantic Knowledge changelog for every accepted persistence operation.

This is not redundant with Git.

```text
Git history = file-level diff history.
Knowledge changelog = knowledge-state evolution history.
```

The changelog records:

- which Knowledge entry was added;
- which Knowledge entry was superseded or deprecated;
- why the Knowledge state changed;
- which evidence supported the change;
- affected scopes and version contexts;
- rollback reference.

## 7. Supersession and deprecation

When a candidate stages a Knowledge supersession or deprecation, Phase 23B must update referenced existing Knowledge entries when they exist.

Superseded entries must record:

```yaml
status: superseded
superseded_by: Kxxxx
```

Deprecated entries must record:

```yaml
status: deprecated
deprecated_by: Kxxxx
```

The operation must also be reflected in:

```text
index.yaml
history/changes/Cxxxx.yaml
history/changelog.md
rollback/Rxxxx.yaml
```

## 8. Serialization format

Phase 23B local demo runtime keeps `.yaml` file names for Knowledge Store layout compatibility.

The demo implementation writes JSON-formatted YAML-compatible payloads into those `.yaml` files. JSON is a YAML subset and keeps the demo runtime dependency-free.

This is a demo/runtime serialization choice, not a production Knowledge storage format commitment.

## 9. Summary

```text
Archive records what happened.
Knowledge records what is known.
Causal records why a judgment holds.
Phase 23B persists Knowledge only and does not write Archive or Causal.
```
