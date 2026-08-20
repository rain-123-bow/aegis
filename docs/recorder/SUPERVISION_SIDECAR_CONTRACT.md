# Aegis Recorder Windows supervision sidecar contract

Status: `NORMATIVE_DRAFT_FOR_REREVIEW_8`

## 1. Purpose and authority

`supervision.aegissup` is the guard-owned, append-only companion to
`journal.aegisrec`. It preserves the distinction between:

```text
NO_TERMINATION_REQUEST
TERMINATION_REQUESTED_RECLAMATION_CONFIRMED
TERMINATION_REQUESTED_RECLAMATION_UNCONFIRMED
```

The journal remains the transport-evidence authority. The sidecar is only the
Windows guard/supervision authority. Neither file may repair, overwrite, or
infer records in the other.

The sidecar does not claim administrator resistance, same-user immutability,
physical power-loss durability, or process disappearance that the guard did
not observe.

## 2. Creation and ownership

The guard generates canonical UUIDv4 `session_id` and
`recorder_instance_id`, creates the absent absolute session directory, and
then creates `supervision.aegissup` with:

```text
CreateFileW(
  desired_access = GENERIC_READ | GENERIC_WRITE,
  share_mode = 0,
  creation_disposition = CREATE_NEW,
  flags = FILE_ATTRIBUTE_NORMAL | FILE_FLAG_WRITE_THROUGH
)
```

The sidecar handle is non-inheritable. The engine and target never receive it.
Only the guard main thread may append. A handshake worker may publish validated
values in guard memory and terminate, but it never touches the sidecar handle,
sequence, offset, or digest.
The guard passes the two UUID strings to the engine; every journal entry must
use those exact values. The engine creates only `journal.aegisrec` inside the
already-created session directory.

The guard writes one sidecar header, immediately flushes it, then appends and
flushes `GUARD_STARTED` before creating the engine. Every record append is:

```text
verify current file offset
-> counted WriteFile loop for the exact 256-byte record
-> verify resulting file offset
-> FlushFileBuffers
```

A zero-progress write, short-write failure, offset mismatch, write error, or
flush error permanently poisons the sidecar. Before target resume, poison
forbids resume. After target resume, poison triggers emergency outer-Job
containment, proxy class 16, and no supervision-complete claim.

## 3. File header

The header is exactly 128 bytes. Integers are unsigned little-endian.

| Offset | Size | Field |
|---:|---:|---|
| 0 | 8 | ASCII `AEGSUPV1` |
| 8 | 2 | major `1` |
| 10 | 2 | minor `0` |
| 12 | 4 | header size `128` |
| 16 | 16 | RFC 4122 network-order bytes of `session_id` |
| 32 | 16 | RFC 4122 network-order bytes of `recorder_instance_id` |
| 48 | 32 | guard-generated random nonce |
| 80 | 32 | `session_path_sha256`, defined below |
| 112 | 16 | reserved zero |

The UUID bytes must encode lowercase canonical UUID strings when rendered.
`session_path_sha256` binds the original Windows session path recorded at
creation time. It does not bind the later location from which a copied evidence
package is verified.

Constants:

```text
HEADER_DOMAIN = ASCII "AEGIS-SUPERVISION-HEADER-V1" followed by one NUL
SESSION_PATH_DOMAIN = ASCII "AEGIS-RECORDER-SESSION-PATH-V1" followed by one NUL
session_path_canonical_bytes =
  restricted_canonical_json(session_path)
session_path_sha256 =
  SHA256(SESSION_PATH_DOMAIN || session_path_canonical_bytes)
header_digest = SHA256(HEADER_DOMAIN || exact_128_byte_header)
```

The engine receives the same original session path from the guard and commits
both `session_path` and `session_path_sha256` in `SESSION_STARTED`. The journal
protocol defines `session_path` as the current Recorder platform's absolute
session-directory `OsStringIdentity`, without a terminating NUL, and defines
restricted canonical JSON.
The two implementations compute the digest independently from the same domain
and bytes. The digest is an origin-identity binding, not a path-race, ACL, or
current-location claim.

## 4. Fixed record

Each committed record is exactly 256 bytes:

| Offset | Size | Field |
|---:|---:|---|
| 0 | 8 | ASCII `AEGSUPE1` |
| 8 | 2 | record version `1` |
| 10 | 2 | `event_type` |
| 12 | 4 | record size `256` |
| 16 | 8 | zero-based `sequence` |
| 24 | 8 | guard monotonic timestamp in ns |
| 32 | 8 | guard UTC timestamp in ns |
| 40 | 8 | guard PID |
| 48 | 8 | engine PID, zero while unavailable |
| 56 | 8 | target PID, zero while unavailable |
| 64 | 4 | `termination_reason` |
| 68 | 4 | flags |
| 72 | 4 | event-local Win32 error, zero when unavailable or operation succeeded |
| 76 | 4 | trigger value, or `UINT32_MAX` when unavailable |
| 80 | 8 | observed Job active-process count, or `UINT64_MAX` when unavailable |
| 88 | 32 | `journal_genesis_sha256`, all zero before journal binding |
| 120 | 32 | previous record digest, or `header_digest` for sequence zero |
| 152 | 56 | reserved zero |
| 208 | 32 | record digest |
| 240 | 16 | ASCII `AEGSUP-COMMIT-V1` |

The digest is:

```text
RECORD_DOMAIN = ASCII "AEGIS-SUPERVISION-RECORD-V1" followed by one NUL
record_digest = SHA256(RECORD_DOMAIN || bytes[0:208])
```

Sequence starts at zero and increases by exactly one. Timestamps never
decrease. Nonzero PIDs are at most `UINT32_MAX`. An observed active-process
count is at most `UINT32_MAX`; only the unavailable sentinel is `UINT64_MAX`.
PIDs and the journal hash, once nonzero, never change.

Flag bits are exact:

```text
0x00000001  TERMINATION_CALL_RETURNED
0x00000002  TERMINATION_CALL_SUCCEEDED
0x00000004  ENGINE_PROCESS_SIGNALED
0x00000008  TARGET_PROCESS_SIGNALED
0x00000010  JOB_ACTIVE_COUNT_OBSERVED
0x00000020  TERMINAL_RECORD
0xffffffc0  reserved; must be zero
```

## 5. Event and reason enums

Event types are:

```text
1  GUARD_STARTED
2  JOURNAL_BOUND
3  TERMINATION_REQUESTED
4  TERMINATION_CALL_RETURNED
5  RECLAMATION_CONFIRMED
6  RECLAMATION_UNCONFIRMED
7  NORMAL_SUPERVISION_COMPLETED
```

Termination reasons are:

```text
0  NONE
1  STARTUP_DEADLINE
2  RUNTIME_FATAL_DEADLINE
3  OUTPUT_DRAIN_DEADLINE
4  ENGINE_EXITED_FIRST
5  SHUTDOWN_EVENT
6  HANDSHAKE_PROTOCOL_FAILURE
7  SIDECAR_FAILURE
8  GUARD_INTERNAL_FAILURE
9  ENGINE_RESUME_STATE_FAILURE
10 TARGET_RESUME_STATE_FAILURE
```

`GUARD_STARTED`, `JOURNAL_BOUND`, and `NORMAL_SUPERVISION_COMPLETED` require
reason zero. The four termination events require the same nonzero reason first
written by `TERMINATION_REQUESTED` and preserve its trigger value.

Per-event fields are exact:

| Event | Required flags | Error field | Active count |
|---|---|---|---|
| `GUARD_STARTED` | zero | zero | `UINT64_MAX` |
| `JOURNAL_BOUND` | zero | zero | `UINT64_MAX` |
| `TERMINATION_REQUESTED` | zero | trigger error defined below | `UINT64_MAX` |
| `TERMINATION_CALL_RETURNED` | `TERMINATION_CALL_RETURNED`, plus `TERMINATION_CALL_SUCCEEDED` iff true | termination-call error | `UINT64_MAX` |
| `RECLAMATION_CONFIRMED` | copied call flags, engine signaled, target signaled iff target PID exists, Job count observed, terminal | zero | zero |
| `RECLAMATION_UNCONFIRMED` | copied call flags, terminal, and only actually observed process/Job flags | zero | observed count or `UINT64_MAX` |
| `NORMAL_SUPERVISION_COMPLETED` | engine signaled, target signaled iff target PID exists, Job count observed, terminal | zero | zero |

Any additional flag invalidates the record. `JOURNAL_BOUND` requires nonzero
engine PID, target PID, and journal hash. Those values propagate unchanged
through every later record. Before binding, target PID and journal hash are
zero.

## 6. Journal binding

The journal genesis is the exact byte range from offset zero through the commit
marker of sequence-zero `SESSION_STARTED`. Its SHA-256 is
`journal_genesis_sha256`.

The engine commits and flushes the journal genesis before target creation. It
publishes its hash in handshake state `TARGET_READY`. The guard handshake
worker validates the fixed handshake and exits. The guard main thread observes
that worker-handle signal in a timer-first wait, durably appends
`JOURNAL_BOUND`, publishes acknowledgement, and only then lets the engine
continue. From that record onward every sidecar record contains the same
nonzero hash.

An independent Verifier must:

1. parse the journal header and first complete entry independently;
2. hash the exact journal-genesis byte range;
3. compare that hash with `JOURNAL_BOUND`;
4. compare both canonical UUIDs in every journal entry with the sidecar header;
5. independently recompute journal `SESSION_STARTED.session_path_sha256` from
   restricted canonical JSON of `SESSION_STARTED.session_path` using
   `SESSION_PATH_DOMAIN`;
6. compare that recomputed digest, the journal-declared digest, and the sidecar
   header `session_path_sha256` for three-way equality.

Any mismatch invalidates the evidence package. A sidecar with no
`JOURNAL_BOUND` can document a pre-journal guard failure. When no journal
exists, the sidecar path digest is retained as a sidecar fact but cannot be
cross-bound. Moving or copying the session directory never creates a mismatch:
the verifier's current absolute session-directory path is excluded from all
origin-binding calculations.

## 7. Legal state traces

The only complete traces are:

```text
GUARD_STARTED
-> JOURNAL_BOUND
-> NORMAL_SUPERVISION_COMPLETED
```

and:

```text
GUARD_STARTED
-> [JOURNAL_BOUND]
-> TERMINATION_REQUESTED
-> TERMINATION_CALL_RETURNED
-> RECLAMATION_CONFIRMED | RECLAMATION_UNCONFIRMED
```

The brackets mean only that a pre-journal failure may omit `JOURNAL_BOUND`.
The two legal incomplete termination prefixes are:

```text
... -> TERMINATION_REQUESTED
... -> TERMINATION_REQUESTED -> TERMINATION_CALL_RETURNED
```

A guard killed or blocked inside the termination call can end at the first
prefix. A guard killed after the call returned but before terminal persistence
can end at the second. Either missing terminal is not a parse error and is
reconstructed as `TERMINATION_REQUESTED_RECLAMATION_UNCONFIRMED`. A committed
`RECLAMATION_CONFIRMED` or `RECLAMATION_UNCONFIRMED` without the immediately
preceding legal `TERMINATION_CALL_RETURNED` is an invalid state transition; it
is never accepted as a terminal shortcut. A partial or invalid record after a
request adds a sidecar-invalid issue but cannot upgrade reclamation.

`TERMINATION_REQUESTED` is flushed before the first terminating Job call or
kill-on-close Job-handle release. It has no call-return flags and uses
`UINT64_MAX` for active count. Reasons `ENGINE_RESUME_STATE_FAILURE` and
`TARGET_RESUME_STATE_FAILURE` store the exact `ResumeThread` return in trigger
value and, only for return `0xffffffff`, its nonzero `GetLastError` in the
event-local error field. Every other reason uses `UINT32_MAX` as trigger value
and zero event-local error.

`TERMINATION_CALL_RETURNED` is legal only after the relevant Windows call
returns. It sets `TERMINATION_CALL_RETURNED`; it additionally sets
`TERMINATION_CALL_SUCCEEDED` exactly when the API returned success. A failed
call stores nonzero `GetLastError`; a successful call stores zero. It preserves
the request trigger value.

`RECLAMATION_CONFIRMED` is legal only when:

- `TERMINATION_CALL_RETURNED` exists;
- the engine process handle is signaled;
- the target process handle is signaled when a target PID exists;
- a successful Job query reported active-process count zero.

It sets the corresponding observed flags, `JOB_ACTIVE_COUNT_OBSERVED`,
`TERMINAL_RECORD`, and stores active count zero.

`RECLAMATION_UNCONFIRMED` is written after a returned termination call when the
two-second confirmation deadline expires or a required process/Job query
fails. It sets `TERMINAL_RECORD`, records only observations actually made, and
never fills an unavailable active count with zero.

`NORMAL_SUPERVISION_COMPLETED` is legal only without
`TERMINATION_REQUESTED`, after engine exit, all known process handles are
signaled, and a Job query reports zero active processes. It sets
`TERMINAL_RECORD`, the applicable signaled flags,
`JOB_ACTIVE_COUNT_OBSERVED`, and active count zero.

No record may follow a terminal record.

A crash after the flushed header but before committed `GUARD_STARTED` leaves a
128-byte header-only file. It is a valid incomplete prefix, not malformed
evidence: last committed sequence is null, `supervision_journal_bound=false`,
and `guard_terminal_state=MISSING`; no terminal event is inferred.

## 8. Verifier integration contract

The exact verification invocation is:

```text
aegis-recorder verify ABSOLUTE_SESSION_DIRECTORY
python -m aegis_recorder verify ABSOLUTE_SESSION_DIRECTORY
```

The positional input is one existing absolute directory. The verifier derives
exactly two children and accepts no file override:

```text
ABSOLUTE_SESSION_DIRECTORY/journal.aegisrec
ABSOLUTE_SESSION_DIRECTORY/supervision.aegissup
```

The Verifier contract's retained-volume-root/ancestor/session/child handle
chain and no-follow rules apply before this sidecar parser runs. A symlink,
junction, mount point, or any observed nonzero reparse tag at any Windows path
component is INPUT_ERROR/66; it is never interpreted as a missing or alternate
sidecar.

A Windows production `PASS` requires both derived children to be regular
read-only inputs. A missing sidecar after a readable Windows journal yields an
explicit incomplete report. A valid readable sidecar with no journal yields a
machine-verifiable supervision-only row instead of being discarded. An invalid
readable sidecar with no journal yields an undetermined invalid row with no
supervision assurance. Both derived files absent is an input error.
Non-Windows and undetermined-profile report sentinels are defined by the
Verifier contract.

The read-only sidecar parser contains literal v1 constants and its own hash,
framing, flag, and transition checks. It must not import guard-side record
construction, append, or recovery code.

The verification report must add these required fields:

```text
supervision_sidecar_path
supervision_sidecar_file_size
supervision_sidecar_sha256
supervision_sidecar_valid
supervision_journal_bound
supervision_journal_binding_valid
supervision_last_committed_sequence
supervision_partial_tail_byte_count
guard_terminal_state
guard_termination_requested
guard_termination_reason
guard_trigger_value
guard_trigger_win32_error
guard_termination_call_returned
guard_termination_call_succeeded
guard_termination_win32_error
guard_reclamation_state
guard_reclamation_active_process_count
```

Windows-observed value domains are:

```text
guard_terminal_state =
  null |
  NORMAL_SUPERVISION_COMPLETED |
  RECLAMATION_CONFIRMED |
  RECLAMATION_UNCONFIRMED |
  MISSING

guard_reclamation_state =
  null |
  NOT_REQUESTED |
  CONFIRMED |
  UNCONFIRMED

guard_termination_reason =
  null |
  STARTUP_DEADLINE |
  RUNTIME_FATAL_DEADLINE |
  OUTPUT_DRAIN_DEADLINE |
  ENGINE_EXITED_FIRST |
  SHUTDOWN_EVENT |
  HANDSHAKE_PROTOCOL_FAILURE |
  SIDECAR_FAILURE |
  GUARD_INTERNAL_FAILURE |
  ENGINE_RESUME_STATE_FAILURE |
  TARGET_RESUME_STATE_FAILURE
```

For Windows:

- a readable sidecar path/size/SHA are the exact opened file values;
- `supervision_journal_bound` is true/false when the longest legal prefix
  establishes presence/absence of `JOURNAL_BOUND`, and null when parsing cannot
  establish that fact;
- `supervision_sidecar_path` is the exact derived absolute child path; an
  absent or inaccessible required sidecar uses
  null size/SHA/sequence/guard-observation values, tail count zero,
  `supervision_sidecar_valid=null`,
  `supervision_journal_binding_valid=false`,
  `guard_terminal_state=MISSING`,
  `guard_termination_requested=null`, and null reclamation state;
- an invalid sidecar uses `supervision_sidecar_valid=false`; committed
  longest-legal-prefix facts may still establish a request and unconfirmed
  reclamation;
- a legal structural/hash/state prefix, including one missing only a terminal,
  uses `supervision_sidecar_valid=true`;
- binding is true or false after both valid genesis identities are available;
  comparison success gives true and mismatch gives false. It is also the
  explicit false sentinel for a required missing Windows sidecar and for
  supervision-only evidence where no journal comparison is possible.

When the journal is unavailable and the readable sidecar is valid, the report
uses `evidence_platform_profile=WINDOWS_SUPERVISION_ONLY`,
`journal_present=false`, `supervision_journal_binding_valid=false`, and
`JOURNAL_MISSING`. The name does not imply that `JOURNAL_BOUND` is absent:
`supervision_journal_bound` preserves that distinction. This row is
INCOMPLETE. A malformed sidecar-only row is INVALID with
`evidence_platform_profile=UNDETERMINED` and the `NONE` scope triple. It may
retain physical and longest-legal-prefix diagnostics, but those facts confer no
supervision-integrity assurance. If both fixed files are unavailable, the
result is INPUT_ERROR rather than a supervision row.

`guard_termination_call_returned=false` requires
`guard_termination_call_succeeded=null` and
`guard_termination_win32_error=null`. When it is true, success is Boolean;
success requires error zero and failure requires a nonzero unsigned 32-bit
error. `guard_reclamation_active_process_count` is the observed unsigned
32-bit count in `0..4294967295`, or null when the sidecar stores `UINT64_MAX`;
confirmed and normal terminal records require zero. Unconfirmed reclamation
permits zero, any other observed value in that range, or null.

`guard_trigger_value` and `guard_trigger_win32_error` are non-null only for an
engine/target resume-state reason. They equal the exact request-record fields.
Trigger value `0xffffffff` requires a nonzero error; every other trigger value
requires error zero.

Disk reason `NONE=0` maps to report
`guard_termination_reason=null`; `NONE` is not a report enum value. Normal
supervision has `guard_termination_requested=false`, null termination reason
and trigger fields,
`guard_termination_call_returned=false`, null call success/error,
`guard_reclamation_state=NOT_REQUESTED`, and active-process count zero.

The report reason vocabulary must add:

```text
SUPERVISION_SIDECAR_MISSING
SUPERVISION_SIDECAR_INVALID
SUPERVISION_JOURNAL_BINDING_MISMATCH
GUARD_TERMINAL_STATE_MISSING
GUARD_TERMINATION_REQUESTED
RECLAMATION_UNCONFIRMED
SUPERVISION_STATE_CONTRADICTION
```

Truth predicates are bidirectional:

- Windows `PASS` requires a valid sidecar, a valid journal binding,
  `guard_terminal_state=NORMAL_SUPERVISION_COMPLETED`,
  `guard_termination_requested=false`, and
  `guard_reclamation_state=NOT_REQUESTED`.
- A missing required sidecar yields `INCOMPLETE` with exactly the applicable
  missing-sidecar/supervision-terminal reasons; it can never yield `PASS`.
- Invalid framing, hash chain, enum, flags, state transition, or trailing data
  yields `INVALID` with `SUPERVISION_SIDECAR_INVALID`.
- A journal UUID, genesis hash, or origin-path-digest mismatch yields `INVALID` with
  `SUPERVISION_JOURNAL_BINDING_MISMATCH`.
- A complete legal trace with no terminal yields `INCOMPLETE` with
  `GUARD_TERMINAL_STATE_MISSING`.
- `guard_termination_requested=true` if and only if one valid
  `TERMINATION_REQUESTED` exists. It requires
  `GUARD_TERMINATION_REQUESTED` and prevents `PASS`, including after confirmed
  reclamation.
- `guard_reclamation_state=CONFIRMED` if and only if the legal final event is
  `RECLAMATION_CONFIRMED`; it excludes `RECLAMATION_UNCONFIRMED`.
- `guard_reclamation_state=UNCONFIRMED` if and only if a termination request
  lacks a legal confirmed terminal or ends in `RECLAMATION_UNCONFIRMED`; it
  requires `RECLAMATION_UNCONFIRMED`.
- Any represented booleans/error/counts that disagree with the exact record
  flags and fields yield `INVALID` with `SUPERVISION_STATE_CONTRADICTION`.
- The report `issue_count`, ordered `reason_ids`, and per-reason counts include
  these issues under the same exact-sum and positive-key rules as journal
  reasons.

Input-error, internal-error, POSIX, and undetermined-profile sentinels remain
the exclusive responsibility of the Verifier report contract. They cannot be
used to manufacture Windows supervision-integrity assurance.
