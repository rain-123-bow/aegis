# Phase 23B Knowledge Store Persistence Patch Plan

## Scope

Phase 23B adds local demo Knowledge Store persistence after Phase 22A Knowledge candidate admission.

It persists verified neutral facts and constraints into a local demo Knowledge Store:

```text
knowledge_candidate
  -> knowledge/entries/Kxxxx.yaml
  -> knowledge/index.yaml
  -> knowledge/history/changes/Cxxxx.yaml
  -> knowledge/history/changelog.md
  -> knowledge/rollback/Rxxxx.yaml
```

## Boundary

Phase 23B is not:

- production Knowledge backend;
- production encryption / key lifecycle;
- remote sync;
- Archive persistence;
- Causal persistence;
- separate knowledge-store department closure;
- long-lived knowledge runtime agent profile closure;
- router/topology extension;
- causal truth production.

## Key validations

- verified static facts persist;
- versioned platform/toolchain constraints persist;
- unverified developer assertions are rejected;
- causal-shaped inputs are rejected;
- archive-event-shaped inputs are rejected even when they also carry a statement;
- direct Archive/Causal/global truth write attempts are rejected;
- unknown or ambiguous operation values are rejected instead of defaulting to add_entry;
- supersession and deprecation update referenced Knowledge entries;
- missing references are rejected;
- rejected inputs do not create Knowledge layout state;
- JSON-formatted YAML-compatible payload behavior is documented.

Semantic grep note: `causal_store_write_performed.*true` may appear only inside a negative test input that proves causal-store write attempts are rejected. Runtime result output must preserve `causal_store_write_performed: false`.

## Expected local validation

```text
compileall: pass
pytest: 20 passed
```
