# Phase 23A Archive Segmented Persistence Patch Plan

## Scope

Phase 23A adds Master-owned local demo Archive segmented persistence.

It persists `archive_event_candidate` inputs into a bounded active Archive segment and rolls over into sealed read-only history when thresholds are reached.

## Included

- `ARCHIVE_SEGMENTED_PERSISTENCE_POLICY.md`
- `ARCHIVE_SEGMENTED_PERSISTENCE_RESULT_CONTRACT.md`
- deterministic `aegis-runtime/archive_store` runtime and CLI
- tests for event persistence, rollover, sealing, artifact manifest, rollback, rejection, and JSON-formatted YAML-compatible payloads

## Boundary

Phase 23A does not implement production Archive backend, production encryption, key lifecycle, remote sync, Knowledge persistence, Causal persistence, router/topology changes, a separate archive-store department, or a long-lived archive runtime agent profile.

Archive records what happened. It does not produce truth.

## Expected local validation

```text
compileall: pass
pytest: 16 passed
```


Additional v0.2 hardening:

- Rejected archive candidates must not create local archive directories or changelog placeholders.
- Sealed segments are immutable local history; later writes must not mutate sealed segment files.
