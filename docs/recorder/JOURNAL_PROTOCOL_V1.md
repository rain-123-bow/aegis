# Aegis Recorder Journal Protocol v1

Status: `NORMATIVE_DRAFT_FOR_REREVIEW_8`

All offsets and lengths are byte counts. Fixed-width binary integer fields are
unsigned big-endian; JSON integers follow section 4. A verifier must reject
every reserved value not explicitly allowed.

## 1. File header

The file header is exactly 16 bytes:

| Offset | Size | Value |
|---:|---:|---|
| 0 | 8 | ASCII `AEGISREC` |
| 8 | 2 | major version `0x0001` |
| 10 | 2 | minor version `0x0000` |
| 12 | 4 | header size `0x00000010` |

Any other magic, major, minor, or header size is unsupported and invalid.

Constants:

```text
HEADER_DOMAIN = ASCII "AEGIS-RECORDER-HEADER-V1" followed by one NUL byte
header_digest = SHA256(HEADER_DOMAIN || exact_16_byte_file_header)
```

`header_digest` is not stored in the 16-byte header. It is recomputed by every
implementation and is the hash-chain predecessor for sequence zero.

## 2. Entry layout

Every entry is:

| Part | Size |
|---|---:|
| record magic `AREN` | 4 |
| record version `0x0001` | 2 |
| flags `0x0000` | 2 |
| metadata length | 4 |
| payload length | 8 |
| metadata bytes | declared |
| payload bytes | declared |
| entry SHA-256 | 32 |
| commit marker `CMIT` | 4 |

The fixed entry prefix is 20 bytes. Normative resource limits are:

```text
MAX_JOURNAL_BYTES = 1099511627776
MAX_ENTRY_COUNT = 100000000
MAX_METADATA_BYTES = 65536
MAX_PAYLOAD_BYTES = 10485761
MAX_CONTROL_PAYLOAD_BYTES = 4194304
MAX_ENTRY_BYTES = 10551353
```

Metadata length is `1..MAX_METADATA_BYTES`. Payload length is
`0..MAX_PAYLOAD_BYTES`. A canonical-JSON control payload is additionally
limited to `MAX_CONTROL_PAYLOAD_BYTES`. `MAX_ENTRY_BYTES` includes the prefix,
maximum metadata, maximum payload, digest, and commit marker.

Before allocating or seeking, the Verifier must reject a known file size above
`MAX_JOURNAL_BYTES`, an entry count above `MAX_ENTRY_COUNT`, a declared length
above its limit, or any checked-addition overflow while calculating:

```text
20 + metadata_length + payload_length + 32 + 4
```

The Writer must refuse an append that would make the file exceed
`MAX_JOURNAL_BYTES` or the entry count exceed `MAX_ENTRY_COUNT`. It must not
write a partial prefix as a refusal mechanism.

A complete entry requires every declared byte, the 32-byte digest, and the
four-byte commit marker. EOF anywhere earlier is a partial tail. The verifier
reports the exact number of bytes after the last committed entry and never
truncates or repairs the file.

## 3. Entry digest

Constants:

```text
ENTRY_DOMAIN = ASCII "AEGIS-RECORDER-ENTRY-V1" followed by one NUL byte
```

For entry `n`:

```text
previous_digest =
  header_digest                     when n = 0
  stored digest bytes of entry n-1  when n > 0

entry_digest = SHA256(
  ENTRY_DOMAIN
  || previous_digest
  || fixed_20_byte_entry_prefix
  || metadata_bytes
  || payload_bytes
)
```

The commit marker is not part of the digest. Its only meaning is that record
framing reached its final byte before the subsequent flush attempt.
Only the running Writer knows that `FlushFileBuffers`/`fsync` returned success.
The read-only Verifier therefore also requires a clean final session record;
a parseable last record in an unclean journal is not assumed durable.

The Writer uses write-all semantics for the header and every entry. An append
is successful only after the exact prefix, metadata, payload, digest, and
commit marker have been written and the platform durability call has returned
success. It may begin no state-dependent external side effect and append no
later entry before that success. Thus an observation is durable before its
forward attempt, an attempt is durable before its OS operation, and its
terminal result is durably appended afterward. A short write, zero-progress
write, or durability error is a journal failure; forwarding stops and
`SESSION_ENDED` is forbidden.

After a journal becomes poisoned, emergency containment is an explicit
exception to attempt-before-effect lifecycle recording. The engine may cancel
I/O, close its owned handles, and terminate its owned Job/process group even
though no further attempt record can be persisted. Those effects are not
claimed as proven and `SESSION_ENDED` remains forbidden. A read-only Verifier
reports only observable structure: the last byte-complete valid prefix, any
partial-tail component and byte count, missing terminal entries, and missing
`SESSION_ENDED`. It cannot distinguish a Writer poison event from process
death, power loss, later file truncation, or an incomplete copy merely from an
absent suffix. Journal v1 therefore defines no persistence-cause report reason;
none may be inferred or emitted. This exception exists only to stop a live
process after the Writer has observed an evidence-persistence failure; that
private observation does not become post-hoc Verifier evidence.

## 4. Restricted canonical JSON metadata

Metadata is UTF-8 without BOM and is one JSON object. Every control payload
identified below as JSON uses the same grammar. The following limits apply
independently to each metadata object and each JSON control payload:

```text
MAX_JSON_DEPTH = 16
MAX_JSON_NODES = 4096
MAX_OBJECT_MEMBERS = 256
MAX_ARRAY_ITEMS = 4096
MAX_KEY_UTF8_BYTES = 128
MAX_STRING_UTF8_BYTES = 262144
```

The root has depth one. Each object-member value and each array element is one
level deeper. Every value, including the root, counts as one node; object names
do not count as nodes. Limits are checked during parsing, before constructing
an unbounded container. An object name is `1..MAX_KEY_UTF8_BYTES`; a string
value is `0..MAX_STRING_UTF8_BYTES`, measured after UTF-8 encoding.

Allowed values:

- object;
- array;
- Unicode string without surrogate code points;
- signed integer in `[-9223372036854775808, 9223372036854775807]`;
- `true`, `false`, `null`.

Floating-point numbers are forbidden. Duplicate object names are forbidden.
Object names are sorted by Unicode code-point order.

String encoding uses:

- `\"` for quote;
- `\\` for backslash;
- `\b`, `\t`, `\n`, `\f`, `\r` for those five control characters;
- lowercase `\u00xx` for every other U+0000 through U+001F;
- direct UTF-8 for all other allowed code points.

There is no insignificant whitespace. Integers use the shortest decimal form;
zero is `0`; a negative integer has one leading `-`; leading zeroes are
forbidden.

The Verifier parses with duplicate-name rejection, validates the restricted
type grammar and resource limits, re-encodes with its own canonical encoder,
and requires byte equality.

Restricted canonical JSON is retained instead of adding a binary TLV grammar.
The grammar above already has one byte representation for each allowed value.
Using the same small semantic model in the Writer, independent Verifier, and
independent test oracle creates fewer encoder/parser branches than maintaining
both TLV and JSON. This reduces the three-implementation defect surface without
weakening byte-level identity.

## 5. Operating-system string identity

An operating-system string is never identified by a presentation string.
`OsStringIdentity` is an object with exactly `encoding` and `data`.

On Windows:

```json
{"data":"63003a005c00","encoding":"windows-utf16le-hex"}
```

- `data` is lowercase hexadecimal for the exact UTF-16LE code units passed to
  a wide-character Windows API;
- no BOM and no trailing NUL code unit is included;
- its hexadecimal length is divisible by four;
- an embedded `0x0000` code unit is invalid;
- encoding and decoding use surrogate preservation, so even unpaired UTF-16
  code units remain reversible.

On POSIX:

```json
{"data":"L3RtcC94","encoding":"posix-bytes-base64url"}
```

- `data` is unpadded RFC 4648 base64url over the exact bytes passed to the OS;
- only `A-Z`, `a-z`, `0-9`, `-`, and `_` are allowed; `=` is forbidden;
- decoding followed by unpadded base64url re-encoding must reproduce the same
  bytes;
- an embedded NUL byte is invalid.

For Python `str` input on POSIX, the exact bytes are obtained with the active
filesystem encoding and `surrogateescape`. A Python `bytes` input is retained
unchanged. Empty data is legal only where the operating-system API permits an
empty value; cwd and executable identities are never empty.

Identity hashes are:

```text
OS_IDENTITY_DOMAIN = ASCII "AEGIS-RECORDER-OS-IDENTITY-V1" followed by NUL
identity_sha256 = SHA256(
  OS_IDENTITY_DOMAIN || restricted_canonical_json(identity_value)
)
```

`identity_value` may be one `OsStringIdentity`, an ordered argv array, or an
explicitly ordered environment representation. A presentation/decoded string,
if emitted outside the normative identity object, is advisory and is excluded
from resolution, equality, and identity-hash decisions.

Exact inherited-environment hashes use a separate domain:

```text
OS_ENVIRONMENT_DOMAIN =
  ASCII "AEGIS-RECORDER-OS-ENVIRONMENT-V1" followed by NUL
```

The session-directory identity uses a third domain:

```text
SESSION_PATH_DOMAIN =
  ASCII "AEGIS-RECORDER-SESSION-PATH-V1" followed by NUL
session_path_sha256 = SHA256(
  SESSION_PATH_DOMAIN || restricted_canonical_json(session_path)
)
```

`session_path` is one `OsStringIdentity` for the absolute session directory
used by the Writer on the recording host. The Writer computes the digest from
that exact identity before it emits `SESSION_STARTED`. A supervision sidecar
binds to the journal by comparing its persisted session-path digest with the
persisted `session_path_sha256` value. A Verifier running after the artifacts
were copied or moved must not derive this comparison from its current input
path, current working directory, host platform, or presentation spelling.

The Windows target command line uses a fourth domain:

```text
WINDOWS_COMMAND_LINE_DOMAIN =
  ASCII "AEGIS-RECORDER-WINDOWS-COMMAND-LINE-V1" followed by NUL
target_lp_command_line_sha256 = SHA256(
  WINDOWS_COMMAND_LINE_DOMAIN || target_lp_command_line_utf16le_bytes
)
```

## 6. Common metadata object

Every entry has exactly these keys:

```text
accepted_byte_count
accepted_byte_lower_bound
append_monotonic_ns
append_utc_ns
attempt_entry_sha256
attempt_sequence
entry_kind
error_code
payload_sha256
payload_size
previous_entry_sha256
recorder_instance_id
schema_version
sequence
session_id
source_observed_monotonic_ns
source_byte_offset
source_terminal_cause
stream
subject_entry_sha256
subject_sequence
unit_index
wall_clock_regression
```

Rules:

- `schema_version = "AegisRecorderJournalEntry.v1"`.
- `session_id` and `recorder_instance_id` are lowercase canonical UUID strings.
- `sequence` starts at zero and increases by exactly one.
- `previous_entry_sha256` is 64 lowercase hex characters and equals the
  previous stored digest, or `header_digest` for sequence zero.
- `append_monotonic_ns` and `append_utc_ns` are nonnegative integers sampled
  inside the journal lock after sequence allocation.
- `append_monotonic_ns` never decreases.
- `wall_clock_regression` is true exactly when `append_utc_ns` is lower than the
  preceding entry's value.
- sequence zero has `wall_clock_regression = false`.
- `source_observed_monotonic_ns` is non-null only for source events defined in
  section 8. It is sampled immediately after the source read, EOF, read
  failure, or cancellation becomes observable and is no later than
  `append_monotonic_ns`.
- `unit_index` and `source_byte_offset` are non-null only for source-data
  events defined in section 8. Otherwise they are null.
- `source_terminal_cause` is null except on source terminal events. It is
  exactly `EOF`, `READ_FAILED`, `CANCELLED`, or `LIMIT_EXCEEDED` according to
  section 8.
- `payload_size` equals the declared payload length.
- `payload_sha256` equals SHA-256 of exact payload bytes.
- `stream` is one of `CONTROL`, `CLIENT_TO_SERVER`, `SERVER_TO_CLIENT`,
  `CHILD_STDERR`.
- digest fields use 64 lowercase hex characters; unavailable references are
  null.
- `accepted_byte_count` is non-null only on `FORWARD_SUCCEEDED` and
  `FORWARD_FAILED`; it is an exact count.
- `accepted_byte_lower_bound` is non-null only on
  `FORWARD_OUTCOME_UNKNOWN`. It is the sum of byte counts returned by earlier
  successful write calls in that attempt and does not claim what an ambiguous
  final call accepted.
- `error_code` is non-null on `CHILD_SPAWN_FAILED`, `SOURCE_READ_FAILED`,
  `SOURCE_CANCELLED`, `FORWARD_FAILED`, `FORWARD_OUTCOME_UNKNOWN`,
  `STREAM_CLOSE_FAILED`,
  `CHILD_RESUME_FAILED`, `CHILD_SIGNAL_FAILED`, and `INTERNAL_FAILURE`; it is
  also non-null on `INCOMPLETE_FRAME` whose terminal cause is `READ_FAILED` or
  `CANCELLED`; it is null on an EOF-caused incomplete frame and every other
  kind. A cancellation uses a stable policy code such as
  `POLICY:CHILD_EXITED` rather than pretending an OS error occurred. A
  non-null value is an ASCII string of at most 128 bytes, such as
  `WIN32:109`, `POSIX:32`, or `PYTHON:BrokenPipeError`.

Sequence zero is `SESSION_STARTED`, uses `CONTROL`, all reference/count/error,
source-position, and source-terminal fields are null, and uses `header_digest`
as its previous digest. It is not exempt from any common rule.

## 7. Entry kinds

Allowed kinds:

```text
SESSION_STARTED
CHILD_SPAWN_REQUESTED
CHILD_SPAWNED
CHILD_SPAWN_FAILED
WIRE_FRAME_OBSERVED
STDERR_CHUNK_OBSERVED
FORWARD_ATTEMPT_STARTED
FORWARD_SUCCEEDED
FORWARD_FAILED
FORWARD_OUTCOME_UNKNOWN
STREAM_EOF
SOURCE_READ_FAILED
SOURCE_CANCELLED
INCOMPLETE_FRAME
FRAME_LIMIT_EXCEEDED
STREAM_CLOSE_ATTEMPT_STARTED
STREAM_CLOSE_SUCCEEDED
STREAM_CLOSE_FAILED
CHILD_RESUME_ATTEMPT_STARTED
CHILD_RESUMED
CHILD_RESUME_FAILED
CHILD_EXITED
TERMINATION_REQUESTED
KILL_REQUESTED
CHILD_SIGNAL_ATTEMPT_STARTED
CHILD_SIGNAL_SUCCEEDED
CHILD_SIGNAL_FAILED
INTERNAL_FAILURE
SESSION_ENDED
```

Any `entry_kind` not in this list is invalid. A Verifier must fail closed; it
must not skip, reinterpret, or downgrade an unknown kind.

Payload classes are exact:

- `WIRE_FRAME_OBSERVED`, `STDERR_CHUNK_OBSERVED`, `INCOMPLETE_FRAME`, and
  `FRAME_LIMIT_EXCEEDED` contain opaque source bytes.
- `FORWARD_ATTEMPT_STARTED`, `FORWARD_SUCCEEDED`, `FORWARD_FAILED`,
  `FORWARD_OUTCOME_UNKNOWN`, `STREAM_EOF`, `SOURCE_READ_FAILED`,
  `SOURCE_CANCELLED`,
  `STREAM_CLOSE_ATTEMPT_STARTED`, `STREAM_CLOSE_SUCCEEDED`,
  `STREAM_CLOSE_FAILED`, `CHILD_SPAWN_FAILED`,
  `CHILD_RESUME_ATTEMPT_STARTED`, `CHILD_RESUMED`,
  `CHILD_RESUME_FAILED`, `CHILD_SIGNAL_ATTEMPT_STARTED`,
  `CHILD_SIGNAL_SUCCEEDED`, and `CHILD_SIGNAL_FAILED` have zero payload bytes.
- all remaining kinds contain one restricted canonical JSON object. It has a
  `schema_version` equal to
  `AegisRecorderPayload.<ENTRY_KIND>.v1`. Unknown schema versions and unknown
  object members are invalid.

The exact non-envelope members of the JSON payloads are:

| Kind | Required members besides `schema_version` |
|---|---|
| `SESSION_STARTED` | `protocol_version`, `recorder_version`, `recorder_code_manifest_sha256`, `requested_argv`, `requested_argv_sha256`, `requested_cwd`, `session_path`, `session_path_sha256`, `platform_profile`, `interpreter_path`, `interpreter_version`, `interpreter_sha256`, `frame_limit_bytes`, `stderr_chunk_limit_bytes`, `max_journal_bytes`, `assurance_level`, `evidence_scope`, `authority_verified`, `release_authority_eligible`, `header_digest_sha256` |
| `CHILD_SPAWN_REQUESTED` | `requested_argv`, `requested_argv_sha256`, `requested_cwd`, `resolved_executable`, `resolved_executable_size`, `resolved_executable_sha256`, `resolved_file_identity`, `resolution_environment_value_sha256`, `inherited_environment_sha256`, `resolution_execution_race_acknowledged`, `target_lp_application_name`, `target_lp_command_line_utf16le_hex`, `target_lp_command_line_code_unit_count`, `target_lp_command_line_sha256` |
| `CHILD_SPAWNED` | `guard_pid`, `engine_pid`, `target_pid`, `actual_executable`, `containment_type`, `containment_identity`, `guard_wait_handle_acknowledged` |
| `CHILD_EXITED` | `return_code` |
| `TERMINATION_REQUESTED`, `KILL_REQUESTED` | `reason_code` |
| `INTERNAL_FAILURE` | `failure_class` |
| `SESSION_ENDED` | `clean_shutdown`, `transport_complete`, `child_return_code`, `committed_entry_count`, `final_source_byte_count`, `forwarded_byte_count` |

Types and fixed values:

- argv is a nonempty ordered array of `OsStringIdentity`; cwd, session path,
  interpreter path, resolved executable, actual executable, and every non-null
  `target_lp_application_name` are one `OsStringIdentity`;
- `requested_argv_sha256` equals `identity_sha256` of the ordered argv array;
  `session_path_sha256` equals the domain-separated digest in section 5;
  `header_digest_sha256` equals the computed `header_digest`;
- `protocol_version` equals `AEGISREC-1.0`; `recorder_version` is the installed
  distribution version; `recorder_code_manifest_sha256` binds the packaged
  source-member manifest described by the implementation plan;
- resolved executable, actual executable, cwd, session path, interpreter path,
  and every non-null `target_lp_application_name` identity denote absolute
  paths;
- every non-null scalar field whose name ends in `sha256` is 64 lowercase
  hexadecimal characters;
- `interpreter_sha256` and `resolved_executable_sha256` hash the exact regular
  file bytes observed before launch;
- byte counts and PIDs are nonnegative integers; `return_code` and
  `child_return_code` are signed 64-bit integers, with
  `child_return_code = null` only after spawn failure;
- for `WINDOWS_CPTHON_3_13`, the value copied from `GetExitCodeProcess` is the
  returned `DWORD` interpreted as an unsigned integer in
  `0..4294967295`; it is never sign-extended through a 32-bit signed type.
  The engine waits until the process handle is signalled before calling
  `GetExitCodeProcess`, so `259` is then retained as a possible real target
  exit code rather than treated as `STILL_ACTIVE`;
- `platform_profile` is `WINDOWS_CPTHON_3_13` or
  `POSIX_CPTHON_3_12_VALIDATION`;
- frame, stderr, and journal limits equal the fixed v1 limits in this document;
- assurance fields equal the fixed values in section 13;
- `guard_pid` is a nonnegative integer on Windows and null on POSIX;
- `engine_pid` and `target_pid` are nonnegative integers;
- `guard_wait_handle_acknowledged` is true on Windows and false on POSIX;
- `resolved_file_identity` is exactly
  `{"file_id":"<32 lowercase hex>","volume_serial_number":<integer>}` on
  Windows, or exactly `{"device":<integer>,"inode":<integer>}` on POSIX;
- `resolution_environment_value_sha256` has exactly `PATH`, `PATHEXT`,
  `SystemRoot`, and `ComSpec`; each value is a lowercase SHA-256 or null when
  the platform does not use that variable;
- `resolution_execution_race_acknowledged` is true;
- `containment_type` is `WINDOWS_JOB_OBJECT` or `POSIX_PROCESS_GROUP`;
  `containment_identity` is a canonical UUID for a Job Object or a
  nonnegative process-group ID for POSIX;
- `reason_code` is a nonempty ASCII string of at most 128 bytes;
- `failure_class` has the closed v1 enum whose sole value is `SUPERVISION`;
- `final_source_byte_count` and `forwarded_byte_count` are objects with exactly
  `CLIENT_TO_SERVER`, `SERVER_TO_CLIENT`, and `CHILD_STDERR`, each mapped to a
  recomputable nonnegative integer;
- `committed_entry_count` equals the `SESSION_ENDED` sequence plus one;
  `final_source_byte_count` sums source-data payload sizes by stream;
  `forwarded_byte_count` sums every exact forwarding outcome's
  `accepted_byte_count` by its subject stream, including accepted prefixes on
  failed writes. `SESSION_ENDED` is forbidden after
  `FORWARD_OUTCOME_UNKNOWN`, because no exact accepted-byte total exists.

`INTERNAL_FAILURE` is legal only while the journal is healthy and only when
the Writer directly observes failure of a Recorder-owned supervision or
coordination operation, including an impossible adapter result that prevents
formation of a legal dedicated terminal. Its payload has
`failure_class = SUPERVISION`; its common `error_code` records the observed OS,
runtime, or fixed policy code. When a legal spawn, read, forwarding, close,
resume, signal, framing-limit, child-exit, or sidecar evidence terminal can be
formed, that dedicated representation is mandatory and must not be duplicated
as `INTERNAL_FAILURE`. Journal append or durability failure poisons the Writer
and cannot generate this entry after the fact.

The verification-report reason `SUPERVISION_FAILED` has one and only one
positive Journal predicate:

```text
reason_counts.SUPERVISION_FAILED =
  count(legal INTERNAL_FAILURE entries
        whose failure_class is exactly SUPERVISION)
```

It is positive if and only if that count is positive. No missing suffix,
partial tail, missing `SESSION_ENDED`, journal poison inference, sidecar state,
or other journal entry contributes to this count. An unknown
`failure_class` makes the entry schema-invalid; it cannot create a new reason
or fall back to `SUPERVISION_FAILED`.

For `WINDOWS_CPTHON_3_13`, all four `target_lp_*` members are non-null:

- `target_lp_application_name` is Windows `OsStringIdentity`, equals
  `resolved_executable` byte-for-byte as restricted canonical JSON, and is the
  exact non-NUL UTF-16 value supplied as `lpApplicationName`;
- `target_lp_command_line_utf16le_hex` is lowercase hexadecimal for the exact
  mutable UTF-16LE buffer supplied as `lpCommandLine`, including exactly one
  final `0x0000` code unit and no earlier `0x0000`;
- `target_lp_command_line_code_unit_count` is an integer in `1..32767`, counts
  that final NUL, and multiplied by four equals the hexadecimal string length;
- `target_lp_command_line_sha256` equals the domain-separated hash from
  section 5 over the decoded hex bytes, including the final NUL.

The Verifier independently reconstructs the Windows command line from
`requested_argv`; equality with the stored hex is mandatory. It treats each
argument's `data` as a sequence of 16-bit little-endian code units and applies
this exact algorithm:

1. before every argument except the first, append one `0x0020`;
2. quote an argument exactly when it is empty or contains `0x0020` or
   `0x0009`; if quoted, append opening `0x0022`;
3. retain each run of `0x005c`; before an ordinary code unit, append the run
   unchanged and then that code unit;
4. before an input `0x0022`, append twice the retained backslash run plus one
   additional `0x005c`, then append `0x0022`;
5. at argument end, append the retained run unchanged when unquoted; when
   quoted, append it twice and then append closing `0x0022`;
6. after the final argument, append exactly one `0x0000`.

The algorithm operates on code units, not Unicode scalar values, so surrogate
code units remain unchanged. A reconstructed count above 32767, mismatched
hex/count/hash, wrong encoding, missing final NUL, interior NUL, or
`target_lp_application_name != resolved_executable` makes the entry invalid
before any executable-identity conclusion. For
`POSIX_CPTHON_3_12_VALIDATION`, all four `target_lp_*` members are exactly null;
a partially null tuple is invalid on either profile.

The Windows inherited-environment hash is
`SHA256(OS_ENVIRONMENT_DOMAIN || exact_utf16le_environment_block)`, including
all separators and the final double-NUL. The POSIX hash is
`SHA256(OS_ENVIRONMENT_DOMAIN || restricted_canonical_json(ordered_pairs))`,
where `ordered_pairs` is the ordered array of exact key/value byte identities
passed to `execve`. The four resolution-environment value hashes use
`identity_sha256` over their exact `OsStringIdentity`; a missing value is
represented by null, not by the hash of an empty value.

## 8. Source events and per-stream continuity

### Fixed logical relay-pair set

Protocol v1 has exactly these three logical source/destination pairs and no
extension point for a fourth pair or a subset:

| Stream | Logical source | Logical destination |
|---|---|---|
| `CLIENT_TO_SERVER` | Recorder parent stdin | target stdin |
| `SERVER_TO_CLIENT` | target stdout | Recorder parent stdout |
| `CHILD_STDERR` | target stderr | Recorder parent stderr |

Before a legal `CHILD_SPAWNED`, the active logical pair set is empty. The
single durable `CHILD_SPAWNED` is the atomic activation result for all three
pairs at once. There is no independent open request, open result, per-pair
activation, or later open event. A purported source, destination, or pair
outside this exact topology is invalid.

A physical pipe handle may be allocated while satisfying
`CHILD_SPAWN_REQUESTED`, but allocation is not protocol activation. No source
read, destination write, or relay-owned close operation is legal before the
atomic `CHILD_SPAWNED`. A spawn failure leaves the active pair set empty;
cleanup of never-activated physical handles does not claim a logical close
lifecycle.

After activation, the pair set cannot grow or shrink. Every one of the three
logical sources requires exactly one source terminal. Every one of the three
logical destinations requires exactly one close attempt and one terminal close
outcome as specified in section 10. The Verifier derives missing-source,
missing-close-attempt, and missing-close-outcome counts from the fixed
three-pair topology; event absence never proves that an activated endpoint was
not open.

Source-data events are:

```text
WIRE_FRAME_OBSERVED
STDERR_CHUNK_OBSERVED
INCOMPLETE_FRAME
FRAME_LIMIT_EXCEEDED
```

`WIRE_FRAME_OBSERVED`, `INCOMPLETE_FRAME`, and `FRAME_LIMIT_EXCEEDED` are legal
only on `CLIENT_TO_SERVER` and `SERVER_TO_CLIENT`.
`STDERR_CHUNK_OBSERVED` is legal only on `CHILD_STDERR`. Source terminal entries
use the stream whose read ended, failed, or was cancelled.

For each non-`CONTROL` stream independently:

1. the first source-data event has `unit_index = 0` and
   `source_byte_offset = 0`;
2. each later source-data event has the previous source-data event's
   `unit_index + 1`;
3. each later source-data event has the previous `source_byte_offset +
   payload_size`;
4. interleaving entries from other streams does not alter this state;
5. integer overflow or a gap, duplicate, or regression is invalid.

`source_observed_monotonic_ns`, `unit_index`, and `source_byte_offset` are
non-null on source-data events. Source terminal events are `STREAM_EOF`,
`SOURCE_READ_FAILED`, `SOURCE_CANCELLED`, `INCOMPLETE_FRAME`, and
`FRAME_LIMIT_EXCEEDED`. Exactly one source terminal is allowed for each opened
source. No later source event is allowed for that stream.

`STREAM_EOF`, `SOURCE_READ_FAILED`, and `SOURCE_CANCELLED` have non-null
`source_observed_monotonic_ns`, null position fields, and zero payload.
`INCOMPLETE_FRAME` and `FRAME_LIMIT_EXCEEDED` are both source-data and source
terminal events. The final source-byte count is the next expected
`source_byte_offset`: zero when no source-data event exists, otherwise the last
event's offset plus payload size.

Terminal causes are exact:

- `STREAM_EOF` uses `EOF`;
- `SOURCE_READ_FAILED` uses `READ_FAILED`;
- `SOURCE_CANCELLED` uses `CANCELLED`;
- `FRAME_LIMIT_EXCEEDED` uses `LIMIT_EXCEEDED`;
- `INCOMPLETE_FRAME` uses `EOF`, `READ_FAILED`, or `CANCELLED`.

For framed streams, `SOURCE_READ_FAILED` and `SOURCE_CANCELLED` are legal only
when the frame buffer is empty. If a read failure or cancellation occurs with
buffered bytes, `INCOMPLETE_FRAME` retains those exact bytes and records the
corresponding cause and error/policy code. No buffered source byte may disappear
merely because the read terminated abnormally.

`WIRE_FRAME_OBSERVED` and `STDERR_CHUNK_OBSERVED` are forwardable observations.
`INCOMPLETE_FRAME` and `FRAME_LIMIT_EXCEEDED` are terminal evidence and must
never have a forwarding attempt.

### Observation and forwarding references

`WIRE_FRAME_OBSERVED` and `STDERR_CHUNK_OBSERVED`:

- have no subject or attempt reference;
- retain exact source bytes.

`FORWARD_ATTEMPT_STARTED`:

- references one earlier observation through `subject_sequence` and
  `subject_entry_sha256`;
- has no attempt reference;
- uses the observation's stream;
- is committed and flushed before the first destination write.

`FORWARD_SUCCEEDED`, `FORWARD_FAILED`, and `FORWARD_OUTCOME_UNKNOWN`:

- reference the same observation as the attempt;
- reference the attempt through `attempt_sequence` and
  `attempt_entry_sha256`;
- use the observation's stream;
- contain exactly one acceptance field: the exact `accepted_byte_count` on
  success/failure, or `accepted_byte_lower_bound` on unknown outcome.

Success requires `accepted_byte_count == observed payload_size`.
Failure requires `0 <= accepted_byte_count < observed payload_size`. A terminal
claiming failure after accepting the complete payload is semantically invalid.
`FORWARD_FAILED` is legal only when the platform adapter proves an exact total
for every issued write call. `FORWARD_OUTCOME_UNKNOWN` requires
`0 <= accepted_byte_lower_bound < observed payload_size`.

One observation has at most one attempt and at most one following outcome
record. References must point backward. Cross-session and cross-instance
references are invalid.

Interpretation:

- observation without attempt: definitely not forwarded;
- attempt without an outcome record: `SEND_OUTCOME_UNKNOWN`;
- `FORWARD_OUTCOME_UNKNOWN`: detected uncertainty,
  `SEND_OUTCOME_UNKNOWN`, and never auto-replayed;
- failed attempt with zero accepted bytes: known failure, never auto-replayed;
- failed attempt with a positive prefix: known partial failure, never
  auto-replayed, and `PARTIAL_FORWARD`; it is not
  `SEND_OUTCOME_UNKNOWN` because the durable terminal fixes the accepted prefix;
- success: all bytes accepted by the destination pipe.

Every observation belongs to exactly one reporting bucket:

```text
forward_succeeded
forward_failed
forward_not_attempted
unresolved_forward_outcome
```

The four bucket counts sum to the observation count. `FORWARD_FAILED`, including
a positive accepted prefix, belongs only to `forward_failed`. A durable attempt
with no outcome record or with `FORWARD_OUTCOME_UNKNOWN` belongs only to
`unresolved_forward_outcome`. An unknown outcome with a positive lower bound
adds both `PARTIAL_FORWARD` and `SEND_OUTCOME_UNKNOWN`.

## 9. App-server framing

For `CLIENT_TO_SERVER` and `SERVER_TO_CLIENT`:

- every direct OS source-read request is for exactly one byte;
- buffered wrappers, runtime read-ahead, and any API that may return more than
  the requested byte count are forbidden on this path;
- a successful read returning more than one byte is an invalid platform
  result and triggers fatal shutdown before any byte is classified;
- the only delimiter is byte `0x0A`;
- the delimiter is part of the recorded and forwarded frame;
- byte `0x0D` has no delimiter meaning;
- `0x0A` alone is a valid opaque frame;
- JSON is never parsed;
- a complete frame length, including delimiter, is at most `10485760`;
- the reader consumes at most `10485761` bytes for one candidate frame.

The one-byte read contract is the v1 proof that no raw OS read consumes a byte
belonging to the next frame or a byte beyond the `10485761`-byte candidate
limit. Each returned byte is appended only to the current candidate. Bytes in
an incomplete current candidate remain explicitly non-durable until a frame or
source terminal record commits them. When the returned byte is a delimiter or
the limit trigger, the complete candidate is durably recorded before another
source read begins. An
implementation may introduce chunked reads only in a later protocol version
that first durably records each exact raw read chunk and specifies a
verifiable, lossless mapping from chunk offsets to emitted frames.

Each framed-stream read has exactly one of `DATA`, `EOF`, `READ_FAILED`, or
`CANCELLED` as its local outcome. The outcome-to-entry mapping uses the
empty/nonempty candidate split below; it never treats zero progress as data and
never retries an outcome already classified as terminal.

On Windows, the adapter calls synchronous
`ReadFile(source_handle, buffer, 1, &bytes_read, NULL)` on the preflight-proven
blocking byte-mode pipe:

- `TRUE` with `bytes_read == 1` is `DATA`;
- `TRUE` with `bytes_read == 0` is `READ_FAILED` with
  `POLICY:ZERO_PROGRESS_READ`;
- `TRUE` with any other count is `READ_FAILED` with
  `POLICY:READ_COUNT_OUT_OF_RANGE`;
- `FALSE` with the immediately captured `GetLastError() == 109`
  (`ERROR_BROKEN_PIPE`) is `EOF`;
- `FALSE` with error 995 (`ERROR_OPERATION_ABORTED`) is `CANCELLED` with
  `WIN32:995` only when the Recorder had already requested cancellation for
  that exact stream; without that predicate it is `READ_FAILED` with
  `WIN32:995`;
- every other `FALSE` result is `READ_FAILED` with `WIN32:<unsigned-decimal>`.

`bytes_read` is initialized to zero but ignored after `FALSE`; no unspecified
failure-path value influences classification. A different EOF code, including
`ERROR_HANDLE_EOF`, is not accepted for the preflight-proven pipe profile and
is therefore a read failure rather than inferred EOF.

On POSIX, the adapter calls `os.read(source_fd, 1)` on the preflight-proven
blocking FIFO/socket:

- one returned byte is `DATA`;
- `b""` is `EOF`;
- a returned object of any other length is `READ_FAILED` with
  `POLICY:READ_COUNT_OUT_OF_RANGE`;
- `OSError` with `errno == EINTR` is retried without emitting a source event,
  unless the exact stream's cancellation latch was already set, in which case
  it is `CANCELLED` with the latch's fixed `POLICY:<reason>` code;
- every other `OSError` is `READ_FAILED` with
  `POSIX:<unsigned-decimal-errno>`.

An adapter-requested cancellation observed before issuing the next OS read is
`CANCELLED` and uses its fixed `POLICY:<reason>` code; it does not issue a
zero-length read to manufacture EOF. The complete v1 cancellation policy-code
set is `POLICY:CHILD_EXITED`, `POLICY:FATAL_SHUTDOWN`, and
`POLICY:DRAIN_TIMEOUT`. Missing/negative errno, a non-integer Windows error, or
any other cancellation policy code is an internal protocol failure and cannot
be reported as EOF.

Every `WIRE_FRAME_OBSERVED` payload is `1..10485760` bytes, ends in `0x0A`,
and has no earlier `0x0A`.

EOF with no buffered byte produces `STREAM_EOF`.
EOF with buffered bytes produces `INCOMPLETE_FRAME`; those exact bytes are
recorded and never forwarded. Its payload is `1..10485760` bytes and contains
no `0x0A`.

A read failure or cancellation follows the same empty/nonempty split, using
`SOURCE_READ_FAILED` or `SOURCE_CANCELLED` only for an empty buffer and
`INCOMPLETE_FRAME` for a nonempty buffer.

Reading `10485761` bytes before accepting a frame produces
`FRAME_LIMIT_EXCEEDED`. All `10485761` proven bytes, including the trigger
byte, are retained. The first `10485760` bytes contain no `0x0A`; the trigger
byte may be any byte, including `0x0A`. The remaining source stream is not
consumed. No prefix is forwarded.

`CHILD_STDERR` is not JSONL. It is read in chunks of `1..65536` bytes. Chunk
boundaries have no semantic meaning; concatenated payloads are the exact
observed stream. Each chunk uses the same observation, attempt, and terminal
forwarding state machine. Every `STDERR_CHUNK_OBSERVED` payload is within that
range. Empty EOF produces `STREAM_EOF`.

## 10. Process, resume, close, and signal lifecycles

All reference pairs are atomic: both sequence and digest are null, or both are
non-null and identify the stated earlier entry. Every referenced entry must
share the current `session_id` and `recorder_instance_id`. Entries not assigned
a reference by sections 8 or 10 have null subject and attempt pairs.

### Spawn

`CHILD_SPAWN_REQUESTED` has no references and is committed and flushed before
the first process-creation call. Exactly one `CHILD_SPAWNED` or
`CHILD_SPAWN_FAILED` references it through the subject pair. A spawned child
is still suspended on Windows. `CHILD_SPAWNED` is also the sole, atomic
activation result for all three logical relay pairs from section 8; no separate
open result exists. It has exactly one later `CHILD_EXITED`, which references
`CHILD_SPAWNED` through the subject pair. Spawn and exit entries use `CONTROL`;
their attempt reference and accepted-byte fields are null.

### Target resume

Every Windows `CHILD_SPAWNED` has exactly one
`CHILD_RESUME_ATTEMPT_STARTED`. It references `CHILD_SPAWNED` through the
subject pair, is committed and flushed before `ResumeThread`, and has no
attempt reference.

Exactly one `CHILD_RESUMED` or `CHILD_RESUME_FAILED` references:

- the same `CHILD_SPAWNED` through the subject pair; and
- the resume attempt through the attempt pair.

These entries use `CONTROL`; accepted-byte fields are null. A resume failure
has non-null `error_code`. An attempt without a terminal is
`RESUME_OUTCOME_UNKNOWN`: target code may have executed, automatic relaunch is
forbidden, and no `SESSION_ENDED` is legal.

Absence of `CHILD_RESUME_ATTEMPT_STARTED` after a Windows `CHILD_SPAWNED` is a
distinct not-attempted-resume state: no target instruction is claimed to have
run, but the session is incomplete and cannot end cleanly. It is not merged
with `RESUME_OUTCOME_UNKNOWN`, where the durable attempt proves that
`ResumeThread` was called but its result is unavailable.

The POSIX validation profile forbids resume entries. Its `CHILD_SPAWNED`
means the process-creation API returned a live, already-running child. It cannot
guarantee that no target instruction ran before that terminal was durable.
That narrower guarantee is explicit and cannot satisfy the Windows production
profile.

### Destination close

For every logical destination in the atomically activated three-pair topology
from section 8, exactly one
`STREAM_CLOSE_ATTEMPT_STARTED` references that stream's source terminal through
the subject pair. It is committed and flushed before the close operation. No
later forwarding attempt is legal on that stream.

Exactly one `STREAM_CLOSE_SUCCEEDED` or `STREAM_CLOSE_FAILED` references:

- the same source terminal through the subject pair; and
- the close attempt through the attempt pair.

All three entries use the affected non-`CONTROL` stream. Accepted-byte fields
are null. A close failure has a non-null `error_code`. An attempt without a
terminal result is an unresolved shutdown operation. Once the source terminal
exists, absence of `STREAM_CLOSE_ATTEMPT_STARTED` is a distinct
not-attempted-close state; it is not merged with an attempted operation whose
outcome is unknown.

### Child signal

`TERMINATION_REQUESTED` and `KILL_REQUESTED` express a policy decision and have
no references. Each `CHILD_SIGNAL_ATTEMPT_STARTED` references exactly one such
request through the subject pair, is committed and flushed before the
operating-system signal/termination call, and has no attempt reference.

Exactly one `CHILD_SIGNAL_SUCCEEDED` or `CHILD_SIGNAL_FAILED` references:

- the same request through the subject pair; and
- the signal attempt through the attempt pair.

These entries use `CONTROL`. Accepted-byte fields are null. A signal failure
has a non-null `error_code`. A request may have at most one signal attempt; a
second policy escalation requires a new `KILL_REQUESTED` entry.

A request without `CHILD_SIGNAL_ATTEMPT_STARTED` is a distinct
not-attempted-signal state. An attempt without a terminal is an
unknown-signal-outcome state. A `CHILD_SIGNAL_FAILED` terminal is a known
signal failure. The policy request remains independently observable:
`TERMINATION_REQUESTED` and `KILL_REQUESTED` are counted separately even when
their signal attempts succeed.

An attempt of any class is never inferred from a later success, process exit,
or close. Missing durable `*_ATTEMPT_STARTED` evidence means the operation is
not proven to have begun.

## 11. Partial-tail classification

A partial tail exists only when EOF interrupts a syntactically possible next
entry. It is not a repairable record and never contributes to entry count,
hash-chain state, semantic state, or a clean session.

The verification report uses:

```text
partial_tail_start_offset
partial_tail_byte_count
partial_tail_component
partial_tail_expected_total_bytes
partial_tail_missing_byte_count
```

When no partial tail exists:

```text
partial_tail_start_offset = null
partial_tail_byte_count = 0
partial_tail_component = null
partial_tail_expected_total_bytes = null
partial_tail_missing_byte_count = null
```

When the file ends after `0..15` header bytes:

```text
partial_tail_start_offset = 0
partial_tail_byte_count = physical file size
partial_tail_component = "HEADER"
partial_tail_expected_total_bytes = 16
partial_tail_missing_byte_count = 16 - physical file size
```

Every existing byte must equal the corresponding byte of the fixed header.
Otherwise the header is invalid rather than partial.
For the empty file, `partial_tail_byte_count` is zero but
`partial_tail_component = "HEADER"`; the non-null component distinguishes this
state from the no-tail row.

When EOF occurs after `1..19` bytes of a possible fixed prefix:

```text
partial_tail_start_offset = absolute offset of that prefix
partial_tail_byte_count = bytes from that offset through EOF
partial_tail_component = "PREFIX"
partial_tail_expected_total_bytes = null
partial_tail_missing_byte_count = null
```

The available prefix bytes must equal the corresponding prefix of a legal
`AREN`/version/flags prefix. Otherwise this is an invalid record prefix, not a
partial tail.

Once all 20 prefix bytes are available, magic, version, flags, lengths,
checked-addition, per-entry limits, and file limits are validated first. An
invalid value is a format/resource failure, not a partial tail. For a valid
prefix:

```text
expected = 20 + metadata_length + payload_length + 32 + 4
partial_tail_start_offset = absolute offset of the prefix
partial_tail_byte_count = bytes from that offset through EOF
partial_tail_expected_total_bytes = expected
partial_tail_missing_byte_count = expected - partial_tail_byte_count
```

`partial_tail_component` is the component containing EOF:

```text
METADATA
PAYLOAD
DIGEST
COMMIT_MARKER
```

If one to three commit-marker bytes exist, they must equal the corresponding
prefix of `CMIT`; otherwise the record has an invalid commit marker rather than
a partial tail. If one to 31 digest bytes exist, they must equal the same-length
prefix of the independently computed entry digest; otherwise the record is
invalid rather than partial. A record with all declared bytes but a wrong
digest, wrong canonical metadata, or wrong four-byte marker is a complete
malformed record, not a partial tail.

## 12. Session semantics

`SESSION_STARTED` payload binds:

- requested argv and its OS-identity hash;
- requested cwd;
- the recording host's absolute session-path identity and its domain-separated
  digest;
- platform profile;
- interpreter path/version/hash;
- frame, stderr, and journal limits;
- evidence scope;
- assurance level;
- `header_digest`.

`CHILD_SPAWN_REQUESTED` is flushed before process creation and binds:

- requested argv/cwd;
- resolved executable absolute path;
- on Windows, the exact `lpApplicationName` and canonical `lpCommandLine`
  buffer, including its final NUL, code-unit count, and domain-separated hash;
- executable byte size/SHA-256/file identity;
- PATH/PATHEXT/SystemRoot/ComSpec value hashes;
- complete inherited environment-block hash;
- the known same-user resolution-to-execution race.

`CHILD_SPAWNED` binds guard, engine, and target PIDs, actual executable path,
process-containment identity, and guard wait-handle acknowledgement. On
Windows, the resume lifecycle binds whether target execution was attempted and
known to have started. `CHILD_EXITED` binds the target return code.

`SESSION_ENDED` must be the last entry. Its summary is advisory; the Verifier
recomputes all counts and states. Exactly one is allowed. It is legal only
after all of these conditions hold:

1. spawn has one terminal result;
2. a spawned child has `CHILD_EXITED`;
3. every opened source has one source terminal;
4. every forwarding attempt has exactly one decisive `FORWARD_SUCCEEDED` or
   `FORWARD_FAILED`; `FORWARD_OUTCOME_UNKNOWN` and a missing outcome are
   non-decisive and forbid session end; every platform-required resume attempt,
   close attempt, and signal attempt has one terminal result;
5. every forwardable observation either has no attempt or has exactly one
   attempt with a decisive result;
6. all relay and process-observer threads have stopped, so no later entry can
   be produced;
7. no journal write/flush failure has occurred.

An observation with no attempt is a known transport omission, not an unresolved
OS write. It permits a final failure record but forces
`transport_complete=false`.

`transport_complete=true` if and only if:

- a child was spawned;
- on Windows, target resume succeeded;
- every opened source terminates with `STREAM_EOF`;
- every forwardable observation terminates with `FORWARD_SUCCEEDED` and a full
  accepted-byte count;
- every destination terminates with `STREAM_CLOSE_SUCCEEDED`;
- no incomplete/oversized frame, source read failure, source cancellation,
  legal `INTERNAL_FAILURE`, unresolved operation, or nonzero sidecar-derived
  supervision reason exists.

The child return code does not alter transport completeness.

`clean_shutdown=true` if and only if `transport_complete=true`, the child
return code is zero, no termination/kill request exists, no spawn, resume, or
signal failure exists, all advisory counts match recomputation, and
`SESSION_ENDED` is the final byte-complete entry with no tail. A nonzero child
return code may therefore have complete transport but never clean shutdown.
Both booleans must equal the independently recomputed values; either a false
positive or a false negative is an invalid session state.

Missing `SESSION_ENDED` is an incomplete session, not by itself a malformed
hash chain. An entry after `SESSION_ENDED`, a duplicate `SESSION_ENDED`, or
success fields inconsistent with recomputation is invalid.

## 13. Assurance boundary

Every local journal has:

```text
assurance_level = LOCAL_TRANSPORT_INTEGRITY
evidence_scope = RECORDER_OWNED_APP_SERVER_STDIO
authority_verified = false
release_authority_eligible = false
```

No local exit code, hash chain, clean session, or future local signature may
clear `AUTHORITY_UNVERIFIED`.
