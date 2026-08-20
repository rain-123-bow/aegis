# Aegis Recorder verifier contract

Status: `NORMATIVE_DRAFT_FOR_REREVIEW_8`

The Verifier is a separate, read-only implementation. It does not import
Writer canonicalization, digest, record construction, journal append,
forwarding state, or recovery code. It never repairs or truncates evidence.

## 1. CLI behavior

```text
aegis-recorder verify ABSOLUTE_SESSION_DIRECTORY
python -m aegis_recorder verify ABSOLUTE_SESSION_DIRECTORY
```

For a syntactically valid invocation, stdout contains exactly one canonical
UTF-8 JSON report followed by one LF. Human diagnostics may appear on stderr
but must not contain journal payload excerpts.

A usage error before a session-directory argument is accepted returns 64 and
emits no report: stdout is empty and stderr is exactly
`usage: aegis-recorder verify ABSOLUTE_SESSION_DIRECTORY` plus one LF. Both
entrypoints use that canonical diagnostic. The command accepts exactly one
positional absolute path and no options. After that path is accepted, every
normal result, input error, or contained internal error emits the report
schema.

The positional path must name an existing directory. The Verifier derives only
these literal children:

```text
ABSOLUTE_SESSION_DIRECTORY/journal.aegisrec
ABSOLUTE_SESSION_DIRECTORY/supervision.aegissup
```

There is no journal or sidecar override. Each consumed child is opened
read-only, with no write sharing where the platform can enforce it, and must be
a regular file. The report `journal_path` is the derived absolute journal path
even when that child is missing. The Verifier does not resolve, open, import,
execute, or fetch any path, URL, module, or command found inside evidence
metadata or payloads.

Path safety is fail-closed before evidence parsing:

- POSIX opens the session directory with
  `O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC`, retains that `dirfd`, opens each
  fixed child with `openat(dirfd, literal_name,
  O_RDONLY|O_NOFOLLOW|O_CLOEXEC)`, and accepts only `fstat` regular files;
- Windows v1 accepts only a drive-absolute DOS path with grammar
  `[A-Za-z]:\component(\component)*`. It rejects UNC, extended/device/NT
  namespaces, volume-GUID input, drive-relative/root-only/relative paths,
  forward slashes, empty components, `.` or `..`, alternate-stream colons,
  U+0000..U+001F, `<`, `>`, `"`, `|`, `?`, `*`, unpaired UTF-16 surrogates,
  and trailing dot/space. It also rejects a component whose case-insensitive
  stem before the first dot is `CON`, `PRN`, `AUX`, `NUL`, `CLOCK$`,
  `COM1`..`COM9`, `LPT1`..`LPT9`, `COM¹`..`COM³`, or `LPT¹`..`LPT³`. Each
  component is `1..255` UTF-16 code units; the input and both displayed derived
  paths are at most `32767` UTF-16 code units. No case or Unicode normalization
  changes the accepted display spelling; report child paths append their
  literal names to that spelling;
- the Windows drive root is supported only when `GetDriveTypeW` returns
  `DRIVE_FIXED`, `GetVolumeNameForVolumeMountPointW` returns one volume GUID,
  and the first current mappings returned by `QueryDosDeviceW` for the drive
  name (`X:`) and stripped volume name (`Volume{GUID}`: no `\\?\` prefix or
  trailing slash) are the same native `\Device\...` target. This equality
  rejects SUBST and directory redirection. The native target plus one trailing
  backslash is opened as a directory by absolute `NtCreateFile` with
  `OBJ_CASE_INSENSITIVE|OBJ_DONT_REPARSE`, desired access
  `FILE_READ_ATTRIBUTES|FILE_TRAVERSE|SYNCHRONIZE`, share mode exactly
  `FILE_SHARE_READ|FILE_SHARE_WRITE`, disposition `FILE_OPEN`, and create
  options
  `FILE_DIRECTORY_FILE|FILE_OPEN_REPARSE_POINT|FILE_SYNCHRONOUS_IO_NONALERT`;
  `GetVolumeInformationByHandleW` must report `NTFS`. The drive/GUID mapping is
  resolved again immediately before report emission and must be unchanged.
  Failure, ambiguity, mapping change, or identity mismatch is INPUT_ERROR/66;
- from that retained canonical volume-root handle, Windows opens every input
  component in order with `NtCreateFile`, a one-component counted
  `UNICODE_STRING`, and `OBJECT_ATTRIBUTES.RootDirectory` equal to the
  immediately preceding retained directory handle. Attributes are
  `OBJ_CASE_INSENSITIVE|OBJ_DONT_REPARSE`; create options are
  `FILE_DIRECTORY_FILE|FILE_OPEN_REPARSE_POINT|FILE_SYNCHRONOUS_IO_NONALERT`.
  Desired access is
  `FILE_READ_ATTRIBUTES|FILE_TRAVERSE|SYNCHRONIZE`; share mode is exactly
  `FILE_SHARE_READ|FILE_SHARE_WRITE`, omitting `FILE_SHARE_DELETE`;
- Windows opens each literal child relative to the retained session handle with
  the same one-component rule, desired access
  `FILE_READ_DATA|FILE_READ_ATTRIBUTES|SYNCHRONIZE`, share mode exactly
  `FILE_SHARE_READ`, disposition `FILE_OPEN`, and create options
  `FILE_NON_DIRECTORY_FILE|FILE_OPEN_REPARSE_POINT|FILE_SYNCHRONOUS_IO_NONALERT`.
  Thus a consumed child permits neither write nor delete sharing;
- immediately after every Windows root, ancestor, session-directory, and
  present-child open, the Verifier queries `FileAttributeTagInformation` and
  rejects either `FILE_ATTRIBUTE_REPARSE_POINT` or a nonzero reparse tag. It
  also records `FileIdInfo`, verifies the expected directory/non-directory
  type and unchanged volume identity, and never obtains the next handle from a
  reconstructed absolute path;
- root, every ancestor, the session directory, and every present fixed-child
  handle remain open through all reads, hashing, and report construction.
  Before emission the Verifier re-queries type, reparse attribute/tag,
  `FileIdInfo`, and file size. Any mismatch or sharing/identity failure becomes
  INPUT_ERROR/66; partial evidence from that attempt is discarded;
- only `STATUS_OBJECT_NAME_NOT_FOUND` or `STATUS_OBJECT_PATH_NOT_FOUND` for a
  fixed child under the retained safe session handle is absence for the
  evidence truth table. The Verifier repeats that relative absence check before
  emission. Every other open failure is INPUT_ERROR/66;
- a symlink, junction, mount point, or any other nonzero reparse tag encountered
  at a Windows root, ancestor, session, or fixed-child component is
  INPUT_ERROR/66. No reparse target bytes are opened or read;
- a component's first successful handle-relative open defines the object used
  for this verification attempt. From that open through report construction,
  the retained handle and final identity/type/tag/size re-query protect that
  opened object; an observed post-open replacement or identity change is
  INPUT_ERROR/66;
- an ordinary same-volume, non-reparse child substituted before that child's
  first successful open is indistinguishable from the namespace state at first
  open. It is evaluated as that attempt's current object, not reported as a
  detected historical replacement. The Verifier makes no claim that it detects
  replacement history for an object it has not yet opened.

The retained handle chain and omitted delete sharing prevent namespace
replacement of each object after its first successful open. Fixed-child
no-write sharing rejects ordinary concurrent writer handles; the reported
digest still names exactly the bytes read from the retained handle. These
controls do not establish authority, atomic-snapshot semantics, pre-open
ordinary-child replacement detection, or same-user historical immutability:
pre-existing writable mappings, privileged/kernel writers, pre-verification
rewriting, or a different self-consistent directory remain outside the claim.
`authority_verified` and `release_authority_eligible` therefore remain false.

For a journal whose legal `SESSION_STARTED` declares
`WINDOWS_CPTHON_3_13`, sidecar evidence is semantically required. A missing or
unreadable derived sidecar is INCOMPLETE, not a usage error and not a
supervision-success claim. For `POSIX_CPTHON_3_12_VALIDATION`, the derived
sidecar is not consumed. When a present journal has profile `UNDETERMINED`, a
present derived sidecar contributes only path, whole-file size, and SHA-256;
it is not parsed into supervision semantics and cannot change any validity
flag, verdict, issue, or reason count.

When the journal is unavailable and a readable sidecar is valid, the Verifier
emits `evidence_platform_profile=WINDOWS_SUPERVISION_ONLY`. This name means
only that current valid evidence consists solely of Windows supervision bytes;
it does not claim the engine never ran. A legal sidecar may already contain
`JOURNAL_BOUND`. The row is INCOMPLETE with `JOURNAL_MISSING`. A malformed
sidecar-only row is INVALID with profile `UNDETERMINED`, the `NONE` scope
triple, and retained physical/longest-legal-prefix diagnostics; those
diagnostics confer no supervision-integrity assurance. If neither fixed child
supplies readable regular evidence, the result is INPUT_ERROR.

### `validate-report` CLI

```text
aegis-recorder validate-report ABSOLUTE_REPORT_PATH
python -m aegis_recorder validate-report ABSOLUTE_REPORT_PATH
```

The command accepts exactly one positional absolute path and no options. Its
input limit is `8388608` bytes. It opens that exact path read-only, rejects a
non-regular file, reads no journal, and performs no path lookup from report
content. Input must be UTF-8 without BOM and exactly one JSON object serialized
by the rule in section 2, including its single final LF. Duplicate names,
trailing bytes, alternate whitespace, NaN/infinity, floating-point values, and
integers outside their contract field range are invalid. All integer fields are
signed-64-bounded. `guard_reclamation_active_process_count` has the narrower
sidecar-derived range `0..4294967295`; sidecar `UINT64_MAX` maps to null.
Section 4 identifies the signed-64 endpoints that the fixed validator enforces
outside JSON Schema.

Its result contract is complete:

| Exit | Meaning | stdout | exact stderr |
|---:|---|---|---|
| 0 | structural and semantic report validation passed | the unchanged canonical input bytes | empty |
| 2 | report bytes, schema, or represented relation invalid | empty | `INVALID_REPORT` plus LF |
| 64 | invocation/usage error | empty | `usage: aegis-recorder validate-report ABSOLUTE_REPORT_PATH` plus LF |
| 66 | path absent, inaccessible, oversized, or not regular | empty | `REPORT_INPUT_ERROR` plus LF |
| 70 | contained validator implementation/runtime error | empty | `INTERNAL_VERIFIER_ERROR` plus LF |

No failure output contains a supplied path, report value, payload excerpt,
traceback, exception message, or environment value. The production command
has no flag or environment variable that enables diagnostic expansion.

## 2. Result object

Required fields:

```text
schema_version
journal_format
journal_path
journal_present
evidence_platform_profile
file_size
local_verdict
format_valid
canonical_metadata_valid
hash_chain_valid
semantic_valid
file_complete
clean_shutdown
transport_complete
child_return_code
committed_entry_count
last_committed_sequence
header_digest_sha256
final_entry_sha256
partial_tail_byte_count
partial_tail_start_offset
partial_tail_component
partial_tail_expected_total_bytes
partial_tail_missing_byte_count
observation_count
forward_succeeded_count
forward_failed_count
forward_not_attempted_count
unresolved_forward_outcome_count
unresolved_observation_sequences
failed_observation_sequences
sequence_lists_truncated
issue_count
issues_truncated
issues
assurance_level
evidence_scope
ordering_scope
authority_verified
release_authority_eligible
boundary_ids
reason_ids
reason_counts
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
exit_code
```

Fixed values:

```text
schema_version = AegisRecorderVerificationReport.v1
journal_format = AEGISREC-1.0
authority_verified = false
release_authority_eligible = false
boundary_ids equals this ordered array:
  AUTHORITY_UNVERIFIED
  LOCAL_STORAGE_REWRITABLE_BY_SAME_USER
  OS_FLUSH_RETURN_ONLY
```

Scope values form one finite mapping:

| Evidence mode | `assurance_level` | `evidence_scope` | `ordering_scope` |
|---|---|---|---|
| `journal_present=true` | `LOCAL_TRANSPORT_INTEGRITY` | `RECORDER_OWNED_APP_SERVER_STDIO` | `RECORDER_JOURNAL_APPEND_ORDER_ACROSS_PIPES` |
| valid `WINDOWS_SUPERVISION_ONLY` | `LOCAL_SUPERVISION_INTEGRITY` | `WINDOWS_GUARD_SUPERVISION_ONLY` | `SUPERVISION_SIDECAR_APPEND_ORDER` |
| invalid sidecar-only `UNDETERMINED` | `NONE` | `NONE` | `NONE` |
| INPUT_ERROR / INTERNAL_ERROR with no retained evidence | `NONE` | `NONE` | `NONE` |

No sidecar-only row claims app-server transport or journal ordering.

`reason_ids` describe the local parse or transport verdict. Authority limits
belong only in `boundary_ids`; they do not turn a locally complete transport
result into exit 1.

`journal_present` is true exactly when the derived `journal.aegisrec` was opened
as a readable regular file. `evidence_platform_profile` is copied from a legal
`SESSION_STARTED` as `WINDOWS_CPTHON_3_13` or
`POSIX_CPTHON_3_12_VALIDATION`. `WINDOWS_SUPERVISION_ONLY` is required exactly
when `journal_present=false` and a readable derived sidecar is valid.
`UNDETERMINED` is required for a readable but invalid sidecar-only row, when a
present journal has no legal `SESSION_STARTED`, and on INPUT_ERROR or contained
INTERNAL_ERROR rows where no profile was established. Only the two
journal-declared profiles can PASS. The verifier host does not supply this
value; copied evidence can be checked on another operating system without
changing its evidence profile.

Boolean meanings are exact:

- `format_valid`: every consumed structure obeys its binary grammar and
  declared bounds; a valid sidecar-only row can therefore be true, while an
  unparsed UNDETERMINED-profile sidecar cannot change this journal-derived
  value;
- `canonical_metadata_valid`: every complete metadata/control object is valid
  restricted canonical JSON and matches its exact entry schema;
- `hash_chain_valid`: the complete journal header exists and every committed
  journal digest, payload digest, predecessor, and sequence is valid; consumed
  Windows sidecar evidence additionally requires its header/record digests and
  sequence chain to be valid; it is false when `journal_present=false`;
- `semantic_valid`: committed journal entries form a legal protocol trace with
  valid references and recomputed counters, and every semantically consumed
  sidecar trace and available binding comparison is legal. A valid
  sidecar-only trace may be true; a missing required Windows sidecar is
  incomplete evidence, not by itself a false semantic claim;
- `file_complete`: `journal_present=true`, the journal header is complete, and
  no physical journal partial tail exists;
  a byte-complete but malformed file can therefore be complete and invalid;
- `transport_complete`: the independently recomputed journal
  `SESSION_ENDED.transport_complete`, or false when no legal session end
  exists;
- `clean_shutdown`: the independently recomputed journal clean predicate and,
  for a Windows-profile journal, valid/bound normal supervision with no guard
  termination request; it is false for `UNDETERMINED` and for missing,
  invalid, unbound, non-normal, or termination-bearing Windows sidecar
  evidence. The original `SESSION_ENDED.clean_shutdown` must still match the
  journal-local recomputation even when the report-level value is suppressed
  by supervision evidence.
- `child_return_code`: the independently reconstructed signed-64 target return
  code, or null when no legal `CHILD_EXITED` exists.

For a `WINDOWS_CPTHON_3_13` journal, `child_return_code` is the exact
`GetExitCodeProcess` `DWORD` widened without sign extension, so its factual
range is `0..4294967295`. The Verifier rejects a Windows `CHILD_EXITED` or
`SESSION_ENDED` value outside that range and requires both values to match.
The process handle must already have been observed signalled; therefore value
`259` is a retained real exit code at that point, not interpreted as
`STILL_ACTIVE`. The wider signed-64 report type exists for the POSIX profile
and does not authorize a wider Windows value.

These flags are derived independently; absence of complete entries does not
turn an incomplete header into a valid hash chain.

`issues` contains at most 256 objects. Each object has a stable `reason_id`,
optional committed `sequence`, optional absolute `byte_offset`, and a bounded
detail string that contains no payload excerpt. `issue_count` counts all
detected issues, including omitted ones. `issues_truncated` is true exactly
when `issue_count > len(issues)`. `issue_count` has its own signed-64 report
range and is not capped by the maximum journal entry count.

Each sequence list contains at most 256 values while its corresponding count
remains exact. `sequence_lists_truncated` is true exactly when at least one
sequence list was capped.

Serialization is:

```python
json.dumps(
    report,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
).encode("utf-8") + b"\n"
```

### File, hash, committed-count, and tail truth tables

The following table is exhaustive for field presence. “Evidence row” means
exit `0`, `1`, or `2`.

| Row | `journal_present` | `file_size` | `header_digest_sha256` | `committed_entry_count` | `last_committed_sequence` | `final_entry_sha256` |
|---|---:|---|---|---:|---|---|
| INPUT_ERROR | false | null | null | 0 | null | null |
| INTERNAL_ERROR | last established fact | null or observed signed-64 size | null | 0 | null | null |
| supervision-only evidence | false | null | null | 0 | null | null |
| journal, size `0..15` | true | non-null exact size | null | 0 | null | null |
| journal, size `>=16`, no committed entry | true | non-null exact size | SHA-256 of the exact first 16 bytes | 0 | null | null |
| journal, size `>=16`, one or more committed entries | true | non-null exact size | SHA-256 of the exact first 16 bytes | `n` | `n-1` | digest of committed entry `n-1` |

The first-16-byte digest is reported even when those bytes are an invalid
header. It is byte identity, not a validity claim; validity remains in
`format_valid` and `hash_chain_valid`. A positive committed count additionally
requires a legal header and a valid chain through the reported final entry.

Tail fields have exactly one of these states:

| Tail state | component | count | start | expected | missing |
|---|---|---:|---:|---:|---:|
| NONE | null | 0 | null | null | null |
| HEADER | `HEADER` | exact `file_size` in `0..15` | 0 | 16 | `16-file_size` |
| PREFIX | `PREFIX` | `1..19` | non-null | null | null |
| DECLARED_ENTRY | `METADATA`, `PAYLOAD`, `DIGEST`, or `COMMIT_MARKER` | nonzero exact tail bytes | non-null | non-null and greater than count | `expected-count`, at least 1 |

For every non-NONE tail,
`partial_tail_start_offset + partial_tail_byte_count = file_size`.
An empty file is HEADER with count zero; the non-null component distinguishes
it from NONE. A short header fragment that already contradicts the fixed
header is INVALID with tail state NONE. `file_complete=true` if and only if
`journal_present=true`, an evidence row has `file_size>=16`, and tail state
NONE. These rules are
report-internal and do not turn a complete malformed record into a valid one.

### Windows supervision-sidecar fields

The sidecar fields follow
`docs/recorder/SUPERVISION_SIDECAR_CONTRACT.md`. Nullable fields distinguish
“not observed/not applicable” from a negative observation:

- `supervision_sidecar_path` is the exact derived absolute child path whenever
  that path is inspected or a known Windows journal requires the missing child;
  it is null only where the profile/error mode makes no sidecar path claim;
- sidecar file size and SHA-256 are both non-null exactly when the complete
  physical file was read;
- `supervision_sidecar_valid` is true/false only after independent sidecar
  parsing completed, and null when no sidecar bytes were available;
- `supervision_journal_bound` is true/false when a semantically parsed longest
  legal prefix establishes presence/absence of `JOURNAL_BOUND`, and null when
  that fact was not established;
- `supervision_journal_binding_valid` is true only after every required UUID,
  genesis, and origin-path-digest comparison succeeds; it is false for
  supervision-only evidence because no journal is available to compare;
- last sequence is null exactly when no complete sidecar record exists;
- sidecar partial-tail count is `0..255`;
- `guard_termination_reason` is null without a legal termination request;
  otherwise it is exactly one of `STARTUP_DEADLINE`,
  `RUNTIME_FATAL_DEADLINE`, `OUTPUT_DRAIN_DEADLINE`,
  `ENGINE_EXITED_FIRST`, `SHUTDOWN_EVENT`,
  `HANDSHAKE_PROTOCOL_FAILURE`, `SIDECAR_FAILURE`,
  `GUARD_INTERNAL_FAILURE`, `ENGINE_RESUME_STATE_FAILURE`, or
  `TARGET_RESUME_STATE_FAILURE`;
- unavailable guard booleans, trigger values, reason, Win32 errors, terminal,
  reclamation, and active-process observations are null, never guessed.

For a readable sidecar, independent validation enforces:

```text
file_size < 128
  -> last_committed_sequence = null
     and partial_tail_byte_count = file_size

file_size >= 128
  -> partial_tail_byte_count = (file_size - 128) mod 256

supervision_sidecar_valid = true
  -> partial_tail_byte_count = 0
     and (
       file_size = 128 and last_committed_sequence = null
       or
       file_size = 128 + 256 * (last_committed_sequence + 1)
     )
```

Checked arithmetic is mandatory. A complete malformed 256-byte record is not a
partial tail and makes sidecar validity false. A valid header-only sidecar is a
valid incomplete prefix: the guard can stop after flushing the header and
before committing `GUARD_STARTED`.

Profile rules are bidirectional:

| Evidence profile | Sidecar mode |
|---|---|
| `WINDOWS_CPTHON_3_13` | derived sidecar required; PASS requires readable, valid, journal-bound, cross-bound evidence and normal supervision |
| `WINDOWS_SUPERVISION_ONLY` | derived sidecar is readable, parsed, and valid; binding is false; `supervision_journal_bound` preserves whether the legal prefix contains `JOURNAL_BOUND`; guard facts are retained |
| `POSIX_CPTHON_3_12_VALIDATION` | sidecar path/size/hash/validity/journal-bound/binding/sequence and every guard field except terminal state are null; terminal state is `NOT_APPLICABLE`; tail count is zero; no sidecar-derived reason is legal |
| `UNDETERMINED` journal evidence row | a present derived sidecar may report only path, whole-file size, and SHA-256; validity/journal-bound/sequence are null, binding is false, tail count is zero, terminal state is `UNDETERMINED`, other guard fields are null, all sidecar reason counts are zero, and no sidecar fact changes verdict or any validity flag |
| `UNDETERMINED` invalid sidecar-only row | derived sidecar path/size/SHA are non-null, validity is false, binding is false, physical/longest-legal-prefix fields are retained, scope triple is `NONE`, and no supervision assurance is asserted |
| INPUT_ERROR / INTERNAL_ERROR | every nullable sidecar/guard field, including terminal state, is null; tail count is zero |

For Windows, a missing/unreadable required sidecar retains the exact expected
sibling path, uses null file/hash/validity/journal-bound/sequence/guard
observations, tail count zero, `supervision_journal_binding_valid=false`, and
`guard_terminal_state=MISSING`. A present readable sidecar always has non-null
file size and whole-file SHA-256 even when its structure is invalid.
`MISSING` is legal only for a Windows journal, a valid supervision-only row, or
an invalid sidecar-only row whose longest legal prefix lacks a terminal;
`NOT_APPLICABLE` is legal only for known POSIX; and the
`guard_terminal_state=UNDETERMINED` sentinel is legal only for a present
journal evidence row without legal `SESSION_STARTED`.

Sidecar/journal origin binding compares UUIDs, journal genesis, and
`session_path_sha256`. The Verifier independently recomputes the journal digest
as SHA-256 of ASCII `AEGIS-RECORDER-SESSION-PATH-V1`, one NUL, and restricted
canonical JSON of `SESSION_STARTED.session_path`, then compares it with both
the journal-declared digest and the sidecar header digest. The current absolute
session-directory path is never an origin-binding input, so copying a complete
session directory to Windows, WSL, or another location does not invalidate it.

Guard-state predicates are exact:

```text
guard_termination_requested = true
  <-> one legal sidecar TERMINATION_REQUESTED exists

guard_reclamation_state = CONFIRMED
  <-> legal final event is RECLAMATION_CONFIRMED

guard_reclamation_state = UNCONFIRMED
  <-> a legal termination request lacks RECLAMATION_CONFIRMED

guard_reclamation_state = NOT_REQUESTED
  <-> valid parsed trace contains no termination request

guard_terminal_state = NORMAL_SUPERVISION_COMPLETED
  <-> legal final event is NORMAL_SUPERVISION_COMPLETED

guard_terminal_state = RECLAMATION_CONFIRMED
  <-> legal final event is RECLAMATION_CONFIRMED

guard_terminal_state = RECLAMATION_UNCONFIRMED
  <-> legal final event is RECLAMATION_UNCONFIRMED
```

A legal reclamation terminal is accepted only in
`TERMINATION_REQUESTED -> TERMINATION_CALL_RETURNED -> RECLAMATION_*` order.
A trace may end after the request or after the call-returned record; either
missing terminal reconstructs `UNCONFIRMED`. A reclamation terminal that skips
`TERMINATION_CALL_RETURNED` is `SUPERVISION_STATE_CONTRADICTION`, never a legal
shortcut.

Normal supervision has termination-requested false, null reason/trigger
fields, call-returned false, call-succeeded/error null, reclamation
`NOT_REQUESTED`, and active-process count zero. Before a termination call
returns, call-returned is false and call-succeeded/error are null. After it
returns, call-succeeded is boolean; success requires error zero and failure
requires a nonzero DWORD.

`guard_trigger_value` and `guard_trigger_win32_error` are non-null exactly for
`ENGINE_RESUME_STATE_FAILURE` or `TARGET_RESUME_STATE_FAILURE`. Both are
unsigned DWORDs copied from the request record. Trigger `4294967295` requires a
nonzero trigger error; every other trigger value requires trigger error zero.
Confirmed reclamation requires active-process count zero. Unconfirmed
reclamation permits zero, any other observed value in `0..4294967295`, or
null; sidecar `UINT64_MAX` maps only to null.

Guard state fields are reconstructed from the longest semantically legal
record prefix. A later digest-valid record with contradictory flags or fields
is counted by `SUPERVISION_STATE_CONTRADICTION` but is not allowed to inject a
contradictory top-level guard state. `supervision_last_committed_sequence`
still identifies the last framing/hash-committed record, so the report retains
both physical commitment and semantic rejection without becoming
self-contradictory.

## 3. Verdict and exit precedence

```text
0   PASS
    complete valid chain, clean session end, target rc 0, and complete local
    transport

1   INCOMPLETE
    committed prefix is valid, but the file/session/transport is incomplete,
    failed, non-clean, or contains an unresolved external action

2   INVALID
    invalid header, framing, length, canonical metadata, digest, sequence,
    reference, state transition, or resource declaration

64  usage error before journal inspection; stdout is empty and no report exists
66  input path absent, inaccessible, or not a regular file
70  contained Verifier implementation/runtime error
```

Precedence among reportable evidence verdicts is `INVALID > INCOMPLETE > PASS`.
Input and internal errors do not assert that journal bytes are invalid.

The file-availability decision is finite:

| Readable regular journal | Readable regular sidecar | Decision |
|---:|---:|---|
| false | false | INPUT_ERROR/66; `journal_present=false`, profile `UNDETERMINED`, scope triple `NONE` |
| false | true and valid | INCOMPLETE/1; profile `WINDOWS_SUPERVISION_ONLY`, `JOURNAL_MISSING=1`, supervision facts retained |
| false | true and invalid | INVALID/2; profile `UNDETERMINED`, scope triple `NONE`, `JOURNAL_MISSING=1`, physical/valid-prefix facts retained without supervision assurance |
| true | any | journal decides profile and base verdict; known Windows consumes sidecar semantics, known POSIX ignores it, UNDETERMINED consumes only sidecar physical identity |

`WINDOWS_SUPERVISION_ONLY` does not imply absence of `JOURNAL_BOUND`: the
journal may have been deleted or omitted while copying. That fact is preserved
in `supervision_journal_bound`. The sidecar header path digest is retained but
`supervision_journal_binding_valid=false` because no journal exists.

Exit 0 requires all of:

- `local_verdict=PASS`;
- all five validity/completeness booleans true;
- no partial tail;
- no failed, unattempted, or unresolved forwarding;
- legal `SESSION_ENDED` with `clean_shutdown=true`,
  `transport_complete=true`, and `child_return_code=0`;
- target return code zero;
- issue count zero, empty issue/sequence lists, and no truncation flag;
- reason IDs contain only `OK_LOCAL_TRANSPORT_INTEGRITY`.

Exit 0 never changes either authority boolean.

### Allowed result rows

`exit_code` and `local_verdict` are bijective:

| Row | Exit | Verdict | Clean | Required reason class |
|---|---:|---|---:|---|
| PASS | 0 | `PASS` | true | exactly `OK_LOCAL_TRANSPORT_INTEGRITY` |
| INCOMPLETE | 1 | `INCOMPLETE` | false | one or more incomplete reason IDs |
| INVALID | 2 | `INVALID` | false | one or more invalid reason IDs |
| INPUT_ERROR | 66 | `ERROR` | false | exactly `INPUT_ERROR` |
| INTERNAL_ERROR | 70 | `ERROR` | false | exactly `INTERNAL_VERIFIER_ERROR` |

The implications are bidirectional for every fact represented in the report.
In particular,
`clean_shutdown=true` if and only if the row is PASS. Every non-PASS row has
`issue_count >= 1`, nonempty `issues`, no
`OK_LOCAL_TRANSPORT_INTEGRITY`, and `issues_truncated=false` exactly when the
reported issue array is complete. Distinct issue reason IDs equal top-level
`reason_ids`; issue ordering places the first issue for every reason before any
repeated reason, so truncation cannot hide the existence of a top-level reason.

`reason_counts` contains exactly one nonnegative signed-64 count for every
stable reason ID except `OK_LOCAL_TRANSPORT_INTEGRITY`. It closes the
report-internal reason relation:

```text
issue_count = sum(reason_counts.values())
reason_ids = ["OK_LOCAL_TRANSPORT_INTEGRITY"]
  iff exit_code = 0 and every reason count = 0
otherwise:
reason_ids = positive-count IDs in the stable reason order below
```

For non-truncated `issues`, the number of issues with each reason equals its
reason count. For truncated issues it is at most that count. Deterministic issue
ordering retains the first issue for every positive reason before any repeated
reason. Reason presence/count/list arithmetic is therefore independently
checkable without pretending that report-only validation proves the underlying
journal event.

Incomplete reason IDs are exactly:

```text
PARTIAL_TAIL
OBSERVATION_NOT_FORWARDED
SEND_OUTCOME_UNKNOWN
FORWARD_FAILED
PARTIAL_FORWARD
CLOSE_NOT_ATTEMPTED
CLOSE_OUTCOME_UNKNOWN
CLOSE_FAILED
SIGNAL_NOT_ATTEMPTED
SIGNAL_OUTCOME_UNKNOWN
SIGNAL_FAILED
RESUME_NOT_ATTEMPTED
RESUME_OUTCOME_UNKNOWN
RESUME_FAILED
TERMINATION_REQUESTED
KILL_REQUESTED
SOURCE_READ_FAILED
SOURCE_CANCELLED
INCOMPLETE_FRAME
FRAME_LIMIT_EXCEEDED
CHILD_SPAWN_FAILED
CHILD_NONZERO
STREAM_TERMINAL_MISSING
SESSION_END_MISSING
SUPERVISION_FAILED
JOURNAL_MISSING
SUPERVISION_SIDECAR_MISSING
GUARD_TERMINAL_STATE_MISSING
GUARD_TERMINATION_REQUESTED
RECLAMATION_UNCONFIRMED
```

Invalid reason IDs are exactly:

```text
INVALID_FILE_HEADER
UNSUPPORTED_FORMAT_VERSION
INVALID_RECORD_PREFIX
INVALID_RECORD_LENGTH
RESOURCE_LIMIT_EXCEEDED
INVALID_METADATA_UTF8
DUPLICATE_METADATA_KEY
NONCANONICAL_METADATA
ENTRY_SCHEMA_INVALID
PAYLOAD_SIZE_MISMATCH
PAYLOAD_HASH_MISMATCH
ENTRY_HASH_MISMATCH
COMMIT_MARKER_INVALID
SEQUENCE_GAP_OR_DUPLICATE
PREVIOUS_DIGEST_MISMATCH
MONOTONIC_TIME_REGRESSION
WALL_CLOCK_FLAG_MISMATCH
INVALID_ENTRY_STATE
INVALID_REFERENCE
UNSUPPORTED_ENTRY_KIND
SESSION_END_NOT_LAST
SESSION_COUNTER_MISMATCH
SUPERVISION_SIDECAR_INVALID
SUPERVISION_JOURNAL_BINDING_MISMATCH
SUPERVISION_STATE_CONTRADICTION
```

An INVALID row may also retain incomplete reasons found before or after the
first invalidity, but it contains at least one invalid reason. It has
`transport_complete=false` and at least one of `format_valid`,
`canonical_metadata_valid`, `hash_chain_valid`, or `semantic_valid` false.

An INCOMPLETE row contains no invalid or error reason. Its four validity flags
retain their exact independent meanings: for example, a valid truncated header
has `format_valid=true` but `hash_chain_valid=false` because no complete header
exists. `transport_complete` may be true only when a legal `SESSION_ENDED`
proves complete transport but another clean condition, such as child return
code zero, fails.

Representable reason relations are bidirectional:

```text
reason_counts.OBSERVATION_NOT_FORWARDED = forward_not_attempted_count
reason_counts.FORWARD_FAILED = forward_failed_count
reason_counts.SEND_OUTCOME_UNKNOWN = unresolved_forward_outcome_count
reason_counts.PARTIAL_FORWARD
  <= forward_failed_count + unresolved_forward_outcome_count
reason_counts.CHILD_NONZERO = 1
  iff child_return_code is non-null and nonzero
transport_complete = true -> child_return_code is non-null
clean_shutdown = true -> child_return_code = 0
```

Every incomplete lifecycle reason has one count unit and a bidirectional
journal predicate:

| Reason | Exact count |
|---|---|
| `PARTIAL_TAIL` | 1 iff tail state is not NONE; otherwise 0 |
| `PARTIAL_FORWARD` | observations whose known accepted prefix or accepted lower bound is positive and smaller than payload size |
| `CLOSE_NOT_ATTEMPTED` | opened destinations whose legal source terminal exists but which have no close attempt |
| `CLOSE_OUTCOME_UNKNOWN` | close attempts with no terminal close outcome |
| `CLOSE_FAILED` | legal `STREAM_CLOSE_FAILED` terminals |
| `RESUME_NOT_ATTEMPTED` | Windows spawned targets with no resume attempt |
| `RESUME_OUTCOME_UNKNOWN` | resume attempts with no resume terminal |
| `RESUME_FAILED` | legal `CHILD_RESUME_FAILED` terminals |
| `TERMINATION_REQUESTED` | legal `TERMINATION_REQUESTED` entries |
| `KILL_REQUESTED` | legal `KILL_REQUESTED` entries |
| `SIGNAL_NOT_ATTEMPTED` | termination/kill requests with no signal attempt |
| `SIGNAL_OUTCOME_UNKNOWN` | signal attempts with no signal terminal |
| `SIGNAL_FAILED` | legal `CHILD_SIGNAL_FAILED` terminals |
| `SOURCE_READ_FAILED` | legal `SOURCE_READ_FAILED` terminals plus `INCOMPLETE_FRAME` terminals whose cause is `READ_FAILED` |
| `SOURCE_CANCELLED` | legal `SOURCE_CANCELLED` terminals plus `INCOMPLETE_FRAME` terminals whose cause is `CANCELLED` |
| `INCOMPLETE_FRAME` | legal `INCOMPLETE_FRAME` terminals |
| `FRAME_LIMIT_EXCEEDED` | legal `FRAME_LIMIT_EXCEEDED` terminals |
| `CHILD_SPAWN_FAILED` | legal `CHILD_SPAWN_FAILED` terminals |
| `CHILD_NONZERO` | 1 iff the reconstructed child return code is non-null and nonzero; otherwise 0 |
| `STREAM_TERMINAL_MISSING` | streams in the fixed opened source set with no source terminal |
| `SESSION_END_MISSING` | 1 iff no legal `SESSION_ENDED` exists; otherwise 0 |
| `JOURNAL_MISSING` | 1 iff `journal_present=false` and a readable regular sidecar supplies the valid or invalid evidence row (exit 1 or 2); otherwise 0 |
| `SUPERVISION_SIDECAR_MISSING` | 1 iff a Windows-profile journal lacks a readable required sidecar; otherwise 0 |
| `SUPERVISION_SIDECAR_INVALID` | independently detected sidecar framing, digest, enum, flag, transition, or trailing-data violations |
| `SUPERVISION_JOURNAL_BINDING_MISMATCH` | failed UUID, genesis, or origin-path-digest comparisons; zero when a comparison is unavailable |
| `GUARD_TERMINAL_STATE_MISSING` | 1 iff Windows sidecar evidence has `guard_terminal_state=MISSING`; otherwise 0 |
| `GUARD_TERMINATION_REQUESTED` | 1 iff `guard_termination_requested=true`; otherwise 0 |
| `RECLAMATION_UNCONFIRMED` | 1 iff `guard_reclamation_state=UNCONFIRMED`; otherwise 0 |
| `SUPERVISION_STATE_CONTRADICTION` | independently detected contradictions among sidecar event fields, flags, and legal trace state |

The close, resume, and signal rows are disjoint by operation instance:
no-attempted operation, attempted-without-outcome, and explicit failure cannot
be substituted for one another. A termination/kill request is an independent
policy fact, so a successful signal still retains exactly one corresponding
request reason. One request without an attempt therefore contributes both its
policy-request reason and `SIGNAL_NOT_ATTEMPTED`; these are two distinct facts,
not duplicate labels for one fact.

`SUPERVISION_FAILED` equals the count of all legal journal `INTERNAL_FAILURE`
entries whose closed-enum `failure_class` is `SUPERVISION`; it is positive if
and only if that count is positive. Each such entry contributes to no other
reason. Sidecar state, a partial tail, a missing `SESSION_ENDED`, or any poison
inference cannot contribute to this count. A missing journal suffix generates
only reasons for directly observed structure or lifecycle facts; persistence
failure is not inferable from absence.
Invalid reasons count independently detected violating locations or state
instances according to deterministic issue generation.
Their positivity, issue multiplicity, row class, and ordering are
report-internally validated. Their factual cause is established only by
`verify ABSOLUTE_SESSION_DIRECTORY` and the
independent oracle.

INPUT_ERROR uses one sentinel representation:

```text
evidence_platform_profile = UNDETERMINED
journal_present = false
file_size = null
all five validity/completeness flags = false
clean_shutdown = false
transport_complete = false
child_return_code = null
all entry/observation/forward counts = 0
last_committed_sequence = null
all digest and partial-tail nullable fields = null
partial_tail_byte_count = 0
all sequence arrays = []
sequence_lists_truncated = false
issue_count = 1
issues = [one INPUT_ERROR issue with null sequence and byte_offset]
issues_truncated = false
reason_ids = ["INPUT_ERROR"]
reason_counts.INPUT_ERROR = 1 and every other reason count = 0
assurance_level = evidence_scope = ordering_scope = NONE
all sidecar path/size/hash/validity/journal-bound/binding/sequence fields = null
supervision_partial_tail_byte_count = 0
all guard fields = null
```

INTERNAL_ERROR uses the same sentinel except `journal_present` is the last
established Boolean, `file_size` is the already observed signed-64 journal size
or null, and the single issue/reason is `INTERNAL_VERIFIER_ERROR`. It discards
partial parse state rather than emitting unvalidated facts. Its scope triple is
also `NONE/NONE/NONE`. Error-row `journal_format` names the expected input
format; it does not claim that the input was parsed as that format.

## 4. Structural schema and semantic report validator

JSON Schema validates report shape, local constants, enums, bounds, and
single-field implications. Draft 2020-12 cannot express all cross-property
arithmetic. Schema validation alone is therefore never a complete report
contract check.

The schema bundle freezes every schema as RFC 8785 JCS. RFC 8785 cannot
represent the signed-64 endpoint literals exactly. The checked-in structural
schema therefore deliberately omits only these five numeric keywords:

```text
properties.file_size.anyOf[integer].maximum
properties.child_return_code.anyOf[integer].minimum
properties.child_return_code.anyOf[integer].maximum
$defs.issueCount.maximum
$defs.nullableSignedSize.anyOf[integer].maximum
```

This omission does not change any report field type or external range. It
affects these fields and definitions:

```text
file_size
child_return_code
issue_count                         through $defs.issueCount
reason_counts.<every stable reason> through $defs.issueCount
supervision_last_committed_sequence through $defs.nullableIssueCount
supervision_sidecar_file_size       through $defs.nullableSignedSize
```

The fixed-v1 report validator freezes these exact predicates:

```text
SIGNED64_MIN = -9223372036854775808
SIGNED64_MAX =  9223372036854775807

file_size is null or 0 <= file_size <= SIGNED64_MAX
SIGNED64_MIN <= child_return_code <= SIGNED64_MAX, or child_return_code is null
0 <= issue_count <= SIGNED64_MAX
for every key k: 0 <= reason_counts[k] <= SIGNED64_MAX
supervision_last_committed_sequence is null
  or 0 <= supervision_last_committed_sequence <= SIGNED64_MAX
supervision_sidecar_file_size is null
  or 0 <= supervision_sidecar_file_size <= SIGNED64_MAX
```

The Windows-profile `child_return_code` predicate remains the narrower
`0..4294967295` rule already encoded by schema `allOf`. Other protocol,
file-size, sequence, sidecar-size, count-sum, and row predicates can narrow
these generic signed-64 domains further.

A report can therefore satisfy JSON Schema while containing an integer outside
one of these fixed ranges. That structural acceptance has no semantic meaning.
Both `validate-report` and the shared validation library invoked by `verify`
must reject the report. `verify` must convert such an internally constructed
out-of-range report to exit 70 and emit no report bytes.

The distribution provides a separately testable, versioned
`validate-report` command which does not import the Verifier report builder. Its
input is only report JSON. It validates report-internal consistency; it does
not read a journal and cannot prove that a listed sequence actually belongs to
a journal state. Journal truth is established only by
`verify ABSOLUTE_SESSION_DIRECTORY`.

The `verify` command applies the same independent structural/semantic
validation library to its completed in-memory report before serialization. A
validation failure becomes exit 70 and no unvalidated report is emitted. The
library is a fixed v1 standard-library implementation of the checked-in schema
and the relations below; it does not dynamically execute or interpret an
arbitrary schema supplied by a report. The standalone CLI additionally
enforces the canonical input-byte contract in section 1.

Validation enforces:

```text
observation_count =
  forward_succeeded_count
  + forward_failed_count
  + forward_not_attempted_count
  + unresolved_forward_outcome_count

last_committed_sequence =
  null                              when committed_entry_count = 0
  committed_entry_count - 1         otherwise

issue_count = sum(reason_counts.values())
boundary_ids = [
  "AUTHORITY_UNVERIFIED",
  "LOCAL_STORAGE_REWRITABLE_BY_SAME_USER",
  "OS_FLUSH_RETURN_ONLY"
]
```

It also enforces the complete file/hash/count and tail truth tables in section
2, including:

```text
journal_present = false -> file_size is null and journal counts/hashes/tail are empty
journal_present = true and evidence row
  -> file_size is a non-null signed-64 integer
file_size < 16 -> header_digest_sha256 is null
file_size >= 16 -> header_digest_sha256 is non-null
committed_entry_count = 0
  <-> last_committed_sequence is null and final_entry_sha256 is null
committed_entry_count > 0
  <-> last_committed_sequence = committed_entry_count - 1
      and final_entry_sha256 is non-null
tail state != NONE
  -> partial_tail_start_offset + partial_tail_byte_count = file_size
file_complete
  <-> journal_present and evidence row and file_size >= 16 and tail state = NONE
```

`verify ABSOLUTE_SESSION_DIRECTORY` factually derives file availability and
evidence profile. The report-only validator cannot discover an evidence file,
but it enforces every represented row/profile/sidecar implication that follows:

```text
journal_present = true
  -> evidence_platform_profile in {
       WINDOWS_CPTHON_3_13,
       POSIX_CPTHON_3_12_VALIDATION,
       UNDETERMINED
     }
     and scope triple = transport triple

evidence_platform_profile = WINDOWS_SUPERVISION_ONLY
  <-> journal_present = false and readable sidecar evidence is valid
     and exit_code = 1
     and scope triple = supervision triple
     and reason_counts.JOURNAL_MISSING = 1

journal_present = false and readable sidecar evidence is invalid
  <-> evidence_platform_profile = UNDETERMINED
     and exit_code = 2
     and scope triple = NONE/NONE/NONE
     and supervision_sidecar_valid = false
     and reason_counts.JOURNAL_MISSING = 1

exit_code in {66, 70}
  -> scope triple = NONE/NONE/NONE

local_verdict = PASS
  -> evidence_platform_profile in {
       WINDOWS_CPTHON_3_13,
       POSIX_CPTHON_3_12_VALIDATION
     }

evidence_platform_profile in {UNDETERMINED, WINDOWS_SUPERVISION_ONLY}
  -> child_return_code = null

evidence_platform_profile = WINDOWS_CPTHON_3_13 and PASS
  <-> all ordinary PASS predicates
      and supervision_sidecar_valid = true
      and supervision_journal_bound = true
      and supervision_journal_binding_valid = true
      and guard_terminal_state = NORMAL_SUPERVISION_COMPLETED
      and guard_termination_requested = false
      and guard_reclamation_state = NOT_REQUESTED

evidence_platform_profile = POSIX_CPTHON_3_12_VALIDATION
  -> every sidecar-derived nullable field except guard_terminal_state is null,
     guard_terminal_state = NOT_APPLICABLE,
     supervision_partial_tail_byte_count = 0,
     and every sidecar reason count = 0

evidence_platform_profile = UNDETERMINED and journal_present = true
  -> supervision_sidecar_valid = null
     and supervision_journal_bound = null
     and supervision_last_committed_sequence = null
     and supervision_journal_binding_valid = false
     and guard_terminal_state = UNDETERMINED
     and every other guard field is null
     and every sidecar reason count = 0
     and sidecar fields cannot change any verdict or validity flag

evidence_platform_profile = WINDOWS_SUPERVISION_ONLY
  -> supervision_sidecar_path/size/sha256 are non-null
     and supervision_sidecar_valid = true
     and supervision_journal_binding_valid = false
     and journal fields select the absent-journal row
```

The Verifier's factual bucket definitions are:

- PASS has `forward_succeeded_count == observation_count`;
- the four forwarding buckets are mutually exclusive:
  - `forward_succeeded_count` contains observations with one valid
    `FORWARD_SUCCEEDED`;
  - `forward_failed_count` contains every observation with one valid
    `FORWARD_FAILED`, including a positive accepted prefix;
  - `forward_not_attempted_count` contains observations with no
    `FORWARD_ATTEMPT_STARTED`;
  - `unresolved_forward_outcome_count` contains observations with a valid
    `FORWARD_ATTEMPT_STARTED` followed by no outcome record or by
    `FORWARD_OUTCOME_UNKNOWN`;
- `failed_observation_sequences` contains exactly the observation sequences in
  the failed bucket, ordered numerically;
- `unresolved_observation_sequences` contains exactly the observation sequences
  in the unresolved bucket, ordered numerically;
- a positive accepted prefix adds `PARTIAL_FORWARD`, remains only in the failed
  bucket, and does not add `SEND_OUTCOME_UNKNOWN`;
- a positive accepted lower bound on `FORWARD_OUTCOME_UNKNOWN` adds both
  `PARTIAL_FORWARD` and `SEND_OUTCOME_UNKNOWN` and remains only in the unresolved
  bucket;
- `SEND_OUTCOME_UNKNOWN` exists exactly when the unresolved bucket is nonempty;

The report-only validator can enforce the bucket-count sum and the following
internal list properties:

- non-truncated issue/list counts equal their array lengths;
- when `sequence_lists_truncated=false`, both sequence arrays are complete;
- when `sequence_lists_truncated=true`, at least one corresponding aggregate
  count exceeds 256, each sequence array is the first
  `min(aggregate_count, 256)` strictly increasing, duplicate-free sequence
  values claimed for that bucket, and an array whose aggregate count is at most
  256 remains complete;
- every listed sequence is within
  `0..last_committed_sequence`; report-only validation does not claim factual
  bucket membership;
- a truncated issues array has exactly 256 items and a strictly larger
  aggregate issue count;
- issue reason IDs occur in top-level reason IDs;
- reason IDs, `reason_counts`, issue multiplicity, forwarding counts, and
  `child_return_code` obey the bidirectional relations above;
- journal profile, sidecar field mode, guard-state predicates, sidecar reasons,
  and Windows unsigned-DWORD return code obey their bidirectional relations;
- sidecar size/hash/validity/sequence/tail fields obey the checked arithmetic
  in section 2, including DWORD active-count bounds and `UINT64_MAX`-to-null
  handling;
- partial-tail component/offset/expected/missing fields select exactly one
  finite tail row and agree arithmetically with file size;
- hash fields and committed sequence/count fields select exactly one finite
  presence row;
- exit code, local verdict, validity flags, reason IDs, and clean/transport
  fields form exactly one allowed row above;
- every single-field mutation that violates a represented relation is rejected;
  a mutation that still satisfies one complete allowed-row predicate remains
  valid and is not mislabeled contradictory.

Tests must prove a structurally schema-valid but arithmetically contradictory
PASS, overlapping bucket counts, wrong list length/order/range, and contradictory
reason/count relationships are rejected by `validate-report`. A separate
boundary test substitutes one in-range sequence while preserving all internal
relationships and proves that report-only validation cannot detect it.
Consumers that need evidence truth run `verify ABSOLUTE_SESSION_DIRECTORY`;
neither the schema nor
`validate-report REPORT.json` is an evidence verifier.

Signed-64 range tests are exact and may not be replaced by nearby
floating-point-safe values:

```text
child_return_code, POSIX profile:
  -9223372036854775808  accepted by the generic signed-64 range
  -9223372036854775809  rejected by validate-report and verify
   9223372036854775807  accepted by the generic signed-64 range
   9223372036854775808  rejected by validate-report and verify

each nonnegative signed-64 field/definition:
  fields = {
    file_size,
    issue_count,
    every reason_counts value,
    supervision_last_committed_sequence,
    supervision_sidecar_file_size
  }
  -1                   rejected by validate-report and verify
   0                   accepted by the generic range
   9223372036854775807 accepted by the generic range
   9223372036854775808 rejected by validate-report and verify
```

Full-report vectors that use an accepted endpoint must also satisfy every
narrower row and arithmetic predicate. Dedicated range-unit vectors exercise
an endpoint that cannot occur in a semantically valid full row. For every
endpoint whose rejection depends on one of the five intentionally omitted
signed-64 bounds, a companion assertion first proves that the structural
schema alone accepts the integer. An endpoint rejected by a retained structural
predicate, including `-1` for a nonnegative field, instead proves that both the
schema and fixed-v1 validator reject it. These paired assertions prevent either
an accidental non-JCS-safe schema literal or a missing fixed-v1 bound from
masquerading as range coverage.

## 5. Partial-tail classification

Only a record with complete declared bytes, valid digest, and exact commit
marker is committed.

The report independently provides:

```text
partial_tail_byte_count
partial_tail_start_offset
partial_tail_component
partial_tail_expected_total_bytes
partial_tail_missing_byte_count
```

Rules:

- no tail: count `0`; component and all three nullable numeric fields are null;
- a header ending after `0..15` valid prefix bytes: start `0`, component
  `HEADER`, expected total `16`, and missing count `16 - file_size`;
- valid incomplete prefix: start is the first byte after the last committed
  record, count is the exact remaining file bytes, component identifies
  `PREFIX`, `METADATA`, `PAYLOAD`, `DIGEST`, or `COMMIT_MARKER`, expected total
  is the full candidate record size once knowable, and missing count is
  expected minus count;
- a prefix that already contradicts magic, version, reserved fields, declared
  limits, digest prefix, or commit-marker prefix is `INVALID`, not a partial
  tail;
- valid commit-marker prefix ending at EOF is incomplete;
- a complete wrong marker, arbitrary trailing garbage, or any byte after a
  committed `SESSION_ENDED` is invalid.

The Verifier reports the physical tail and never deletes it.

## 6. Stable local reason IDs

```text
OK_LOCAL_TRANSPORT_INTEGRITY
INVALID_FILE_HEADER
UNSUPPORTED_FORMAT_VERSION
INVALID_RECORD_PREFIX
INVALID_RECORD_LENGTH
RESOURCE_LIMIT_EXCEEDED
PARTIAL_TAIL
INVALID_METADATA_UTF8
DUPLICATE_METADATA_KEY
NONCANONICAL_METADATA
ENTRY_SCHEMA_INVALID
PAYLOAD_SIZE_MISMATCH
PAYLOAD_HASH_MISMATCH
ENTRY_HASH_MISMATCH
COMMIT_MARKER_INVALID
SEQUENCE_GAP_OR_DUPLICATE
PREVIOUS_DIGEST_MISMATCH
MONOTONIC_TIME_REGRESSION
WALL_CLOCK_FLAG_MISMATCH
INVALID_ENTRY_STATE
INVALID_REFERENCE
UNSUPPORTED_ENTRY_KIND
OBSERVATION_NOT_FORWARDED
SEND_OUTCOME_UNKNOWN
FORWARD_FAILED
PARTIAL_FORWARD
CLOSE_NOT_ATTEMPTED
CLOSE_OUTCOME_UNKNOWN
CLOSE_FAILED
SIGNAL_NOT_ATTEMPTED
SIGNAL_OUTCOME_UNKNOWN
SIGNAL_FAILED
RESUME_NOT_ATTEMPTED
RESUME_OUTCOME_UNKNOWN
RESUME_FAILED
TERMINATION_REQUESTED
KILL_REQUESTED
SOURCE_READ_FAILED
SOURCE_CANCELLED
INCOMPLETE_FRAME
FRAME_LIMIT_EXCEEDED
CHILD_SPAWN_FAILED
CHILD_NONZERO
STREAM_TERMINAL_MISSING
SESSION_END_MISSING
SESSION_END_NOT_LAST
SESSION_COUNTER_MISMATCH
SUPERVISION_FAILED
JOURNAL_MISSING
SUPERVISION_SIDECAR_MISSING
SUPERVISION_SIDECAR_INVALID
SUPERVISION_JOURNAL_BINDING_MISMATCH
GUARD_TERMINAL_STATE_MISSING
GUARD_TERMINATION_REQUESTED
RECLAMATION_UNCONFIRMED
SUPERVISION_STATE_CONTRADICTION
INPUT_ERROR
INTERNAL_VERIFIER_ERROR
```

The literal order above is the normative stable reason order. `reason_ids`
contains exactly the positive-count IDs in that order.
`OK_LOCAL_TRANSPORT_INTEGRITY` cannot coexist with another local reason ID.

For report-only validation, each positive reason must occur in `issues`.
`reason_ids` must equal the distinct issue reasons in their first-occurrence
order. The first-occurrence prefix contains one issue for every positive reason
in normative reason order before any reason repeats, including when
`issues_truncated=true`. Repeated issues follow in normative reason order,
then by non-null sequence, non-null byte offset, and bounded detail.

Boundary IDs are separate:

```text
AUTHORITY_UNVERIFIED
LOCAL_STORAGE_REWRITABLE_BY_SAME_USER
OS_FLUSH_RETURN_ONLY
```

## 7. Resource behavior

- perform the retained-directory-handle/no-follow preflight from section 1
  before reading evidence bytes;
- reject any observed symlink, junction, mount-point, or other reparse as
  INPUT_ERROR without following it;
- read the fixed header before trusting any declared length;
- reject a physical file larger than the protocol hard maximum before parsing;
- still report that exact oversized physical `file_size` up to signed 64-bit;
- stream payload bytes through the two independent SHA-256 computations;
- never allocate a buffer from unvalidated payload length;
- metadata maximum: protocol header/session limit, at most 65536 bytes;
- frame payload maximum: configured limit plus one trigger byte;
- stderr payload maximum: 65536 bytes;
- entry count maximum: protocol hard maximum;
- journal maximum: session-declared value bounded by the protocol hard maximum;
- canonical JSON nesting depth maximum: 16;
- canonical JSON total node count maximum: 4096;
- object member maximum: 256;
- array item maximum: 4096;
- encoded key maximum: 128 bytes;
- encoded string maximum: 262144 bytes;
- issue and sequence-list caps do not stop validation or exact aggregate
  counting.

Invalid UTF-8, surrogate code points, floats, duplicate keys, excessive depth,
excessive nodes, and integers outside the protocol range are rejected.

An internal exception is converted to exit 70 only at the CLI boundary. The
report includes the exception class but never a payload, environment value,
credential, or traceback. Tests may request a traceback through a test-only
injected sink that production CLI cannot enable.

## 8. Semantic reconstruction

The Verifier independently reconstructs:

- exact sequence continuity and previous-digest chain;
- the empty-or-fixed-three opened source and destination sets from the legal
  spawn terminal, without inferring endpoint absence from missing events;
- per-stream observation unit index and byte offset;
- one-at-a-time observation/attempt/terminal state;
- exact `accepted_byte_count` totals,
  `accepted_byte_lower_bound` values, partial writes, and unknown write
  outcomes;
- source, close, signal, spawn, platform-required resume, child-exit, and
  session terminals;
- target return code, including unsigned-DWORD widening for the Windows
  profile;
- stream byte and unit counts;
- all `SESSION_ENDED` counters.

It does not trust summary counters. Every reference must match both sequence
and entry digest and must point to the correct kind in the same session and
Recorder instance.

## 9. Three-way implementation independence

Production Verifier:

- uses literal protocol constants local to verifier modules;
- implements its own JSON decoder/canonical re-encoder;
- implements its own digest and state machine;
- does not import `writer_*`, `journal`, `proxy`, or platform write modules.

Production Writer does not import verifier modules.

Tests contain a third reference oracle that imports neither production side.
It hand-encodes fixed bytes, recomputes entire chains for semantic mutations,
and is executed in an isolated interpreter. Static AST tests enforce all three
import boundaries.

Golden updates are explicit maintenance operations. Normal tests compare the
checked-in golden SHA-256 and never regenerate or overwrite it.

Required mutations include:

- every byte truncation boundary;
- header, prefix, metadata, payload, digest, and marker bit flips;
- length bombs and arbitrary trailing bytes;
- noncanonical but parseable metadata;
- sequence reorder, duplicate, gap, and deletion;
- correct rehash after illegal state order, bad reference, accepted-byte
  mismatch, counter mismatch, source-terminal violation, and entry after
  session end;
- unresolved write, explicit unknown-write outcome, close, signal, and resume
  attempts;
- source cancellation/read failure, partial frame, oversized frame, nonzero
  target, guard termination, and missing clean end.

Path tests independently cover:

- POSIX symlink at the session directory, journal child, and sidecar child;
- every accepted and rejected Windows v1 path-grammar class, supported-root
  predicate, lowercase/uppercase drive spelling, SUBST/directory-root
  redirection, and volume/file-identity mismatch;
- Windows symlink, junction, mount point, and another nonzero reparse tag at
  every ancestor position, the session directory, and each fixed child;
- a concurrent replacement attempt after every root, ancestor,
  session-directory, and fixed-child handle has been retained; a pre-existing
  incompatible writer/delete handle; and final type/tag/identity/size re-query
  mismatch;
- ordinary same-volume, non-reparse substitution before a child's first open
  is evaluated as the first-open current object and is never reported as
  detected replacement history;
- proof that a reparse target is never opened or read;
- exact INPUT_ERROR/66 report sentinels for every rejected indirection;
- ordinary missing-member rows remain distinct from unsafe-path rows, including
  the repeated relative absence check immediately before report emission.

Passing only Writer-produced fixtures is insufficient evidence.
