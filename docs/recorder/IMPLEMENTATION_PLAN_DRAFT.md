# Aegis Recorder implementation plan

Status: `SUPERSEDED_BY_IMPLEMENTATION_PLAN_FINAL`

Historical artifact only. Do not implement from this file. The reconciled plan
is `IMPLEMENTATION_PLAN_FINAL.md`.

Requirement input: `docs/recorder/REQUIREMENT_ADDENDUM.md`

Threat model input: `docs/recorder/THREAT_MODEL.md`

User confirmation: `2026-07-28T07:17:06.3171799Z`

## Decision

Implement a standalone, standard-library Python stdio owner/proxy with a binary
write-ahead journal and a separate read-only verifier.

Do not add a cryptography dependency. Do not implement private-key storage.
Do not connect the public Phase 0A freeze finalizer to local evidence.

## Candidate comparison

| Candidate | Captures exact boundary bytes | Detects transport uncertainty | Independent authority | Decision |
|---|---:|---:|---:|---|
| Codex hooks collector | No; incomplete event coverage | No | No | Reject |
| Rollout/history tailer | Post-hoc mutable projection | No | No | Reject |
| Recorder-owned app-server stdio proxy | Yes | Yes | No without external checkpoint | Select |
| Compliance/provider adapter | Unknown coverage and unavailable contract | Unknown | Potentially | Defer |
| Home-grown/local-key signatures | Adds key compromise and false assurance | No additional transport proof | No against same user | Reject |

## Journal contract

One create-new session directory contains:

- `journal.aegisrec`: binary append-only evidence;
- `session.json`: create-new, immutable session locator and requested command;
- `verification.json`: optional operator-generated verifier output; never part
  of the journal's own authority.

The journal has a fixed magic/version header. Every record is:

1. record magic;
2. canonical metadata length;
3. payload length;
4. canonical integer/string/boolean/null metadata bytes;
5. exact payload bytes;
6. SHA-256 over a domain separator, previous digest, framing, metadata, and
   payload;
7. commit marker.

The first record binds the session ID, Recorder instance ID, format version,
command, interpreter, platform, process ID, and configured frame limit.

All later records bind:

- session and instance identity;
- contiguous sequence;
- entry kind and stream;
- UTC nanoseconds and process-monotonic nanoseconds;
- wall-clock regression flag;
- payload size and SHA-256;
- previous entry SHA-256.

## Relay protocol

Each complete source frame follows:

1. read one delimiter-terminated frame with a bounded reader;
2. append `WIRE_OBSERVED`;
3. flush Python buffers and call `os.fsync`;
4. write all exact bytes to the destination;
5. append and fsync `WIRE_FORWARD_SUCCEEDED`.

If destination writing fails, append `WIRE_FORWARD_FAILED` when possible and
stop. If the success record cannot be durably committed, the observation has no
terminal result and verification returns `SEND_OUTCOME_UNKNOWN`.

EOF with no buffered bytes is recorded. EOF with partial bytes is recorded as
`INCOMPLETE_FRAME` and is not forwarded.

The child stdout, child stderr, and parent stdin are handled concurrently.
Journal append is serialized by one in-process lock. No unbounded event queue
is used.

## Modules

| File | Responsibility |
|---|---|
| `src/aegis_recorder/__init__.py` | Version and public types |
| `src/aegis_recorder/canonical.py` | Restricted canonical metadata encoding |
| `src/aegis_recorder/format.py` | Binary framing, digest, parser |
| `src/aegis_recorder/journal.py` | Create-new session, locking, append, fsync |
| `src/aegis_recorder/verify.py` | Read-only structural and transport verifier |
| `src/aegis_recorder/proxy.py` | Child ownership, concurrent relay, fail-closed shutdown |
| `src/aegis_recorder/cli.py` | `proxy` and `verify` commands |
| `src/aegis_recorder/__main__.py` | Module entry point |
| `test/phase0a/test_recorder_format.py` | Mutation and truncation tests |
| `test/phase0a/test_recorder_journal.py` | durability, locking, clock, path tests |
| `test/phase0a/test_recorder_proxy.py` | exact relay and crash-window tests |
| `test/phase0a/helpers/recorder_child.py` | deterministic subprocess fixture |

`pyproject.toml` gains only the `aegis-recorder` script. Existing dependency
pins remain unchanged.

## TDD order

1. Write verifier mutation tests and confirm they fail because the modules do
   not exist.
2. Implement format/parser until round-trip and corruption tests pass.
3. Write journal durability/path/lock tests and confirm failure.
4. Implement journal and create-new session semantics.
5. Write proxy write-ahead, exact-byte, incomplete-frame, broken-pipe, fsync
   failure, and unresolved-ack tests and confirm failure.
6. Implement proxy and CLI.
7. Run a real subprocess crash test; kill the Recorder after a durable
   observation and verify non-clean, non-replayable evidence.
8. Run the full existing Phase 0A/reference regression suites.

## Fault injection seams

Production defaults use direct `os.write`, `flush`, `os.fsync`, clocks, and
subprocess APIs. Tests inject narrow callables for:

- record write;
- fsync;
- destination write;
- wall and monotonic clocks;
- child termination.

Injection is constructor-only Python API state. It is not exposed through
environment variables or the production CLI.

## Exit contract

`proxy`:

- `0`: child and all streams closed cleanly; every observation has one durable
  terminal forwarding result;
- nonzero: launch, capture, persistence, forwarding, child, or close failure.

`verify`:

- `0`: format and chain valid, clean terminal record, transport complete;
- `1`: chain parseable but incomplete, unclean, or forwarding uncertainty;
- `2`: corrupt or invalid format;
- `64`: command usage error.

Every result includes `authority_verified=false` and
`release_authority_eligible=false`.

## Integration boundary

The supported initial launch form is:

```text
python -m aegis_recorder proxy --session-dir <new-local-path> -- <child argv...>
```

The intended child is `codex app-server`. The implementation must also work
with deterministic fixture children.

Current Codex Desktop cannot be redirected or attached after its stdio
app-server has started. No test or documentation may claim otherwise.

## Requirement trace

| Requirements | Implementation area | Primary tests |
|---|---|---|
| REC-001, REC-002, REC-019 | CLI/proxy | child ownership, existing-process exclusion |
| REC-003, REC-012 | bounded frame reader/format | malformed, opaque, incomplete, oversized |
| REC-004 to REC-006, REC-011, REC-013 | journal/proxy | ordering and injected write/fsync/pipe failures |
| REC-007, REC-008, REC-014, REC-016 | format/verifier | mutation, reorder, duplicate, clock rollback |
| REC-009, REC-010, REC-021 | journal path/lock | existing path, link/reparse, concurrent writer |
| REC-015 | proxy | stderr, EOF, return code, termination |
| REC-017, REC-018, REC-020 | verifier/docs | explicit non-authority outputs |
| REC-022 | docs/session metadata policy | no hidden redaction claim |

## Completion gate

- independent plan reviewer has zero open P0/P1;
- all new tests pass;
- targeted existing tests pass;
- independent code/evidence reviewer has zero open P0/P1;
- no authority PASS is emitted;
- worktree diff and continuation record identify every change and unverified
  boundary.
