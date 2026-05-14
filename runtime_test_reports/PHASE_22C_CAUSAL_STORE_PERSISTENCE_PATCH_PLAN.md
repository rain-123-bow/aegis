# Phase 22C Causal Store Persistence Patch Plan

## Scope

Add local demo/runtime Causal Store persistence after Phase 22B causal review.

Input:

```text
causal_review_decision
```

Persistable decisions:

```text
stage_canonical_merge_candidate
stage_scope_limited_merge_candidate
stage_supersession_candidate
stage_invalidation_candidate
```

Output:

```text
causal_persistence_result
```

## Boundary

Phase 22C writes local demo causal files under a caller-provided causal root.

It does not claim:

- production Causal Store backend closure
- production encryption / key lifecycle
- remote sync
- database persistence
- Archive persistence
- Knowledge persistence
- router/topology changes
- new department
- long-lived Causal Store Agent

## Files added

```text
aegis-master-kit/master/CAUSAL_STORE_PERSISTENCE_POLICY.md
aegis-master-kit/master/CAUSAL_STORE_PERSISTENCE_RESULT_CONTRACT.md
aegis-runtime/causal_store/
```

## Semantic changelog

Phase 22C intentionally includes a semantic causal changelog.

This is not redundant with Git.

```text
Git history = file-level diff history.
Causal semantic changelog = causal-state evolution history.
```

## Validation

Expected:

```text
compileall: pass
pytest: 12 passed
```


## Apply safety

The apply script performs preflight checks before copying files.

It refuses to overwrite existing non-identical target files and reports conflicts instead of silently replacing them. Identical existing files are skipped. Operators should run `--dry-run` before formal apply.

## Serialization note

Phase 22C uses `.yaml` path names for Causal Store layout compatibility, but the local demo runtime writes JSON-formatted YAML-compatible payloads and reads them with `json.loads`.

This avoids a YAML dependency and does not claim production storage format closure.
