# Archive Segmented Persistence Policy

## 1. Purpose

Phase 23A defines the first Master-owned local Archive persistence closure.

It answers:

```text
How does an archive_event_candidate become a local demo Archive record while keeping Archive growth bounded by segment rollover and sealing?
```

Phase 23A is not production Archive infrastructure.

It does not implement:

- production Archive backend
- production encryption
- key lifecycle
- remote sync
- Knowledge persistence
- Causal persistence
- router/topology changes
- a separate archive-store department
- a long-lived archive runtime agent profile

## 2. Archive boundary

Archive records what happened.

It may record:

- task request events
- task lifecycle events
- developer decision events
- test/review/persistence events
- responsibility boundary events
- artifact references
- amendments and corrections

Archive does not produce truth.

An archived event may prove that a statement was made, a decision interaction occurred, or an artifact was produced. It does not prove that the archived statement is technically correct.

Archive is Master-maintained. Ordinary agents may emit candidate material, but must not directly write Archive.

## 3. Segmented Archive model

Phase 23A uses a segmented local demo Archive layout:

```text
archive/
  index.yaml
  active/
    segment_0001/
      segment_state.yaml
      events/
        E0001.yaml
      index.yaml
      segment_index.yaml
  sealed/
    segment_0000/
      summary.yaml
      index.yaml
      seal.yaml
      compressed_payload.zip
  artifacts/
    manifest.yaml
  history/
    changelog.md
  rollback/
    R0001.yaml
```

The active segment is writable.

A sealed segment is historical and read-only in Phase 23A.

When the active segment reaches configured thresholds, Master seals it and opens a new active segment.

## 4. Rollover thresholds

Phase 23A local demo persistence supports bounded active segments.

A segment may roll over when any threshold is reached:

```text
max_events_per_segment
max_segment_size_bytes
```

The runtime must not keep appending to an active segment after it has reached the configured event limit.

If an event is too large for an empty segment, persistence must reject the event instead of creating an over-limit segment.

Default test thresholds may be intentionally small to prove rollover behavior.

## 5. Sealing rules

Sealing an active segment must create a sealed segment directory containing:

```text
summary.yaml
index.yaml
seal.yaml
compressed_payload.zip
```

The seal record must contain at least:

```yaml
segment_id: string
previous_segment_id: string|null
closed_at: timestamp
event_count: int
payload_hash: string
summary_hash: string
index_hash: string
compression_method: zip
production_seal: false
```

Sealing is local demo sealing only. It is not production cryptographic sealing and not production encryption.

## 6. Summary and index rule

A sealed segment must preserve a compact searchable summary and index.

The summary/index must allow Master to locate:

- task IDs
- event IDs
- event types
- actors
- responsibility-boundary events
- developer decision events
- artifact references
- promoted asset references

without loading the compressed payload.

Hot-path Archive access should prefer active segment plus sealed segment summaries/indexes.

## 7. Artifact manifest

Archive records artifact references, not necessarily artifact payloads.

Phase 23A must maintain a local demo artifact manifest:

```text
archive/artifacts/manifest.yaml
```

The manifest may contain references such as report paths, evidence bundle paths, proof paths, or external IDs.

Artifact references do not become Knowledge or Causal truth.

## 8. Rollback metadata

Every accepted Archive event persistence operation must create rollback metadata:

```text
archive/rollback/Rxxxx.yaml
```

Rollback metadata must record:

- event ID
- segment ID
- files created
- files updated
- previous file contents for updated files
- whether rollover/seal occurred
- sealed segment IDs created
- new active segment ID if rollover occurred

Rollback metadata is local demo metadata, not a production transaction system.

## 9. Rejection rules

Phase 23A must reject archive persistence when:

- required event fields are missing;
- event attempts to claim Knowledge, Causal, or global truth status;
- ordinary agent direct-write flag is present;
- production Archive write is requested;
- event payload cannot fit into an empty active segment;
- target files would be overwritten with non-identical content;
- event targets a sealed segment for mutation.

## 10. Serialization format

Phase 23A local demo runtime keeps `.yaml` file names for Archive layout compatibility.

The demo implementation writes JSON-formatted YAML-compatible payloads into those `.yaml` files. JSON is a YAML subset and keeps the demo runtime dependency-free.

This is a demo/runtime serialization choice, not a production Archive storage format commitment.

## 11. Summary

```text
Archive grows linearly with work.
Phase 23A keeps the hot Archive bounded through active segments.
Sealed segments become read-only history with summary, index, seal, compressed payload, and rollback metadata.
Archive records what happened; it does not produce truth.
```


## Rejected candidate state cleanliness

Rejected event candidates must not create Archive layout files, active segments, or changelog placeholders. Phase 23A local archive state may be created only after the event candidate passes admission checks.

## Sealed segment immutability

A sealed segment is read-only history. Later archive writes must create or use a newer active segment and must not mutate `sealed/segment_xxxx/summary.yaml`, `index.yaml`, `seal.yaml`, or `compressed_payload.zip`. Corrections must be represented as later archive events, not direct edits to sealed payloads.
