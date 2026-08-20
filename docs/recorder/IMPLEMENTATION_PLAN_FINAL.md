# Aegis Recorder implementation plan

Status: `ROUND_11_CONTRACT_AND_SNAPSHOT_RECONCILIATION_IN_PROGRESS`

## Normative inputs

- `REQUIREMENT_ADDENDUM.md`
- `THREAT_MODEL.md`
- `JOURNAL_PROTOCOL_V1.md`
- `SUPERVISOR_CONTRACT.md`
- `SUPERVISION_SIDECAR_CONTRACT.md`
- `POSIX_ADAPTER_CONTRACT.md`
- `VERIFIER_CONTRACT.md`
- `REVIEW_BATCH_PROTOCOL.md`
- `REASONING_LEDGER_STATUS.md`
- `CODEBASE_FACTS.md`
- `USER_CONFIRMATION.md`
- `docs/decisions/0002-recorder-session-directory-evidence.md`
- `docs/decisions/0003-recorder-protected-runtime-deployment.md`
- `schemas/aegis/v2/recorder_verification_report.v1.schema.json`

## Non-normative authoring provenance

`PLAN_REVIEW_REPORT.md`, `IMPLEMENTATION_PLAN_DRAFT.md`, `README.md`, and
`CONTINUATION.md` preserve navigation, rejected drafts, review history, and
handoff state. No requirement, mechanism, test, or completion condition may
depend only on those files. A fresh final reviewer is default-denied from them
and reads only the current validated review-snapshot allowlist.

## Authoring and review control

Every plan-review round follows `REVIEW_BATCH_PROTOCOL.md`. Review input is one
immutable external snapshot identified by its manifest hash. All reviewers in
one batch read that same snapshot, complete their assigned full scan, and write
one independent Markdown result. The author does not modify source while that
batch is open. Only after every expected result is present and the complete
batch is aggregated may the author apply one unified remediation. A later
source change requires a new snapshot and a new review batch; a result from an
older snapshot remains retained and is never silently discarded.

## Claim under review

The planned implementation can preserve and verify exact app-server stdio
bytes across ordinary execution, partial writes, crashes, persistence errors,
backpressure, and process termination without converting local evidence into an
external-authority claim.

## Rereview round 6 closure trace

| Finding | Exact closure |
|---|---|
| `R-001` | `JOURNAL_PROTOCOL_V1.md` fixes the only three-channel topology; one legal `CHILD_SPAWNED` atomically activates all three logical source/destination pairs and its absence activates none. |
| `R-002` | `VERIFIER_CONTRACT.md` gives each legal close, resume, signal, termination, and kill failure state bidirectional stable reason/count predicates. |
| `R-003` | `SUPERVISION_SIDECAR_CONTRACT.md` defines a create-new, guard-only, journal-bound durable record chain for termination request/call/reclamation truth. |
| `A-001` | `SUPERVISOR_CONTRACT.md` fixes the only Windows production proxy argv grammar, trust anchors, cwd/environment behavior, exclusions, and output rules. |
| `A-002` | The supervisor/protocol contracts fix one UTF-16 code-unit serializer; `CHILD_SPAWN_REQUESTED` binds the exact mutable buffer, code-unit count, domain hash, and `lpApplicationName`, which the Verifier independently recomputes. |
| `L-001` | `REASONING_LEDGER_STATUS.md` records the attempted command, exit code, pre-connection failure, and `UNKNOWN_NOT_RETRIEVED` result for active/stale/invalid/superseded; no unavailable category is treated as empty. |
| `C-001` | `POSIX_ADAPTER_CONTRACT.md` fixes retained-dirfd no-follow path traversal, create-new flags, link/owner/mode checks, file/directory fsync order, write/fsync failures, `start_new_session`, and SIGTERM/SIGKILL/reap states. |
| `C-002` | `CODEBASE_FACTS.md` binds branch/HEAD, root pyproject hash and incomplete entry point, current source/test tree, schema hash/reference state, versions, and reproduction commands. |
| `G-001` | The handshake now gives target-resume authority only to guard main after one failure-first timer arbitration; the worker validates and exits, while engine only persists intent/results. |
| `G-002` | Engine and target resume accept only prior suspend count one; API failure, zero, and values greater than one have exact fail-closed sidecar/journal behavior. |
| `G-003` | The report schema and verifier contract define non-null evidence sizes plus finite file/hash/tail/platform/sidecar truth tables for every exit row. |
| `C-003` | Packaging below fixes distribution/version/tags, exact metadata and ZipInfo, `RECORD`, no-overwrite publication, direct/prepared/sdist build equality, and implements mandatory PEP 517 `build_sdist`. |
| `U-001` | The finite mutation ledger below pairs every invariant-breaking mutation with a relationship-preserving control and forbids unreviewed generated mutations. |
| `K-001` | The sole Windows production entry is an absolute package-independent bootstrap which validates isolation, raw command line, runtime-root manifest, interpreter, and cwd before importing Recorder. |
| `G-004` | The supervisor contract fixes the 64-bit `NtQueryObject` layouts and exact access-mask predicates/mutations for all three standard handles. |
| `G-005` | `VERIFIER_CONTRACT.md` maps a Windows child return from the observed unsigned `DWORD` by zero-extension into signed-64 report range. |
| `G-006` | `validate-report` has a fixed one-path grammar, bounded bytes, exact stdout/stderr bytes, and exit 0/2/64/66/70 rows. |
| `K-002` | Framed v1 source reads request exactly one byte and commit a delimiter/limit terminal before another read; read-ahead and multi-byte returns fail closed. |

## Rereview round 8 reconciliation

| Finding | Exact closure |
|---|---|
| `R7-R-001` | Windows verification accepts only the frozen fixed-NTFS drive grammar, anchors the native volume root, then opens and retains every component with `NtCreateFile`, `RootDirectory`, `OBJ_DONT_REPARSE`, and `FILE_OPEN_REPARSE_POINT`. Replacement or identity drift after a component's first open fails against its retained handle. A child observed only before its first open proves current state at that observation, not historical absence or identity. |
| `R7-C-001` | Production `pip --target` is removed. A separate standard-library deployer independently validates an expected-hash wheel, extracts only the frozen protected-runtime allowlist into a same-parent create-new staging root, flushes and rereads every file, verifies exact recursive membership, and atomically renames without replacement. |
| `R7-G-001` | The sole production argv is `-I -S -B -X utf8`; bootstrap validates flags and disables bytecode before Recorder import, enforces frozen runtime/stdlib import allowlists, contributes zero diagnostic bytes, and maps every controlled bootstrap/guard/engine failure to one stable existing exit class. Loader/syntax/trust-anchor failure before the first bootstrap statement is explicitly outside Recorder control. |
| `R7-U-001` | `INTERNAL_FAILURE.failure_class` is the closed singleton `SUPERVISION`; each legal entry contributes exactly once to `SUPERVISION_FAILED`. The unobservable `JOURNAL_PERSISTENCE_UNCONFIRMED` reason is removed, and poison aftermath is reported only through durable prefix/tail/lifecycle facts. |
| `R7-P2-001` | Superseded by `R8-P-001`. The earlier POSIX console/module proxy grammar is withdrawn because it bypasses the protected-bootstrap trust boundary. |
| `R7-P2-002` | The active/stale/invalid/superseded ledger query was repeated for Round 8 and again failed before DSN resolution because `.aegis/project.json` is absent; every category remains `UNKNOWN_NOT_RETRIEVED`, and no missing result is treated as empty. |
| `R8-X-001` | Guard-to-engine and engine-to-target command lines use only `PYTHON_LIST2CMDLINE_UTF16_V1`, matching CPython 3.13 `subprocess.list2cmdline`: a quote alone does not trigger outer quotes. Exact vectors cover `a"b`, consecutive backslashes plus quote, whitespace, empty arguments, non-BMP pairs, and unpaired surrogates. |
| `R8-V-001` | Journal absent plus invalid sidecar stays `UNDETERMINED` with `NONE/NONE/NONE`, INVALID/exit 2, and retains only physical-byte and longest-valid-prefix diagnostics. `WINDOWS_SUPERVISION_ONLY` is legal only for a valid sidecar and exit 1. |
| `R8-D-001` | The repository deployer cannot authorize itself. An operator-controlled external launcher holds the interpreter/deployer and ancestor handles without write/delete replacement, compares hashes supplied by an external approved record, starts one exact `-I -S -B -X utf8` argv with a two-variable clean environment and protected cwd, and keeps the handles until exit. The launcher/hash root are external prerequisites, not Recorder deliverables; Recorder supplies only a conformance harness and disables deployment when they are absent. The deployer validates the real CPython 3.13.13 four-entry startup path, requires the `python313.zip` candidate absent, performs the sole permitted narrowing to held `DLLs`/`Lib`, then enforces import origin before execution and independently rechecks its own expected hash. |
| `R8-D-002` | `REOPENED_BY_R11-WIN-PUBLISH-ABI-001`. The retained-handle and NTFS boundary remains required, but the former `SetFileInformationByHandle(FileRenameInfoEx, RootDirectory!=NULL)` mechanism failed with `ERROR_INVALID_PARAMETER` on the supported probe host. The corrected native `NtSetInformationFile(FileRenameInformation=10)` contract below must pass independent review and real NTFS RED/GREEN before this row closes again. |
| `R8-D-003` | The exact deploy argv, inherited-standard-handle profile, exit classes, healthy-channel canonical stdout, distinct exit 74 for report-channel raw-prefix failure, empty stderr, UTF-16LE-lowercase-hex path representation, staging path/FileId reporting, published-but-unconfirmed failure, and zero automatic recursive cleanup are frozen below and in ADR-0003. |
| `R8-P-001` | No public console/module proxy exists on POSIX. Linux/WSL2 proxy execution uses only `LINUX_PROTECTED_BOOTSTRAP_V1`: an external operator trust slot selects approved user/mount namespace identities, root-owned runtime-nonwritable fixed ASCII approval/stdlib/ELF-closure manifests, and the held launcher, static deployment adapter, interpreter, wheel, curated roots, and final name. The launcher is unprivileged, capability-empty, and `no_new_privs`; it normalizes signals and enters CPython by `execveat` with FDs `0..12`. The bootstrap first sees exactly `0..11`, parses FD 10/11 without a filesystem import, loads the externally approved hash seed and all later modules from retained FDs, and independently rejects inherited wait/signal defects. The static adapter has one argv/FD/env/cwd/report ABI and a distinct report-channel exit 74. Recorder supplies only a conformance harness with `authority_verified=false`; missing prerequisites disable the validation profile. |
| `R8-I-001` | “Runtime immutable” is not claimed. The testable invariant is only that two sequential clean launches, without an injected external mutation, independently verify and observe the same name/type/size/hash membership before Recorder import. |
| `R8-S-001` | Five signed-64 boundary literals in the Recorder schema exceeded the Phase0 RFC 8785/JCS safe-integer domain and made a 53-schema freeze impossible. The schema keeps JSON `integer` shape without unsafe min/max literals; the independent fixed `validate-report` implementation owns signed-64 and nonnegative-signed-64 semantics. Boundary tests cover `-2^63`, `-2^63-1`, `2^63-1`, and `2^63`. `schema_bundle.v1.json`, `reference/source_manifest.v1.json`, and `evaluation_manifest.v1.json` are rebuilt only after an independent reviewer accepts the schema/validator split. Current evidence remains failed: the 88-case primary suite returned 46 failures and 6 errors because the directory requires 53 schemas while the frozen bundle still has 52; the independent reference suite passes 35/35. |

## Rereview round 9 targeted closure

| Finding | Exact closure |
|---|---|
| `R9-W-001` | The Windows RED matrix separates initial DOS-device inequality from a deterministic prepublication drift. The latter changes only the deployer's second snapshot after staging verification and proves no rename call, `publication_state=NOT_PUBLISHED`, canonical exit-1 `DEPLOYMENT_FAILED`, retained staging path/FileId, and zero automatic cleanup. |
| `R9-P-001` | Linux runtime UID and GID are both nonzero; all real/effective/saved/filesystem slots match; the supplementary-group set is exactly empty in native `getgroups`, builtin `posix.getgroups()`, and the Linux 6.6 exact `/proc/self/status` row `Groups:\t \n`. Capabilities remain empty and `no_new_privs=1`. |
| `R9-P-002` | Every stdlib dotted-name prefix is an explicit package row. Manifest rows have closed `PRELOADED`, `SEED`, or `LATE` stages. The three fixed preloaded `encodings` filesystem objects map one-to-one to their `PRELOADED` rows and are never finder-served; every other early/builtin/frozen/manifest/protected name set is disjoint, and wrapped builtin/frozen finders reject names outside their exact tables. |
| `R9-P-003` | The static adapter is a closed `ET_EXEC` x86-64 ELF ABI: exact header fields, checked table arithmetic, an explicit program-header allowlist and counts, page-aligned loads with pairwise-disjoint page-rounded kernel mapping intervals, a file-backed executable entry, absent dynamic/interpreter state, and exactly one non-executable stack header. |
| `R9-P2-001` | After the first bootstrap statement, new filesystem imports are forbidden before the seed step. Until the manifest finder is installed, the one externally approved retained-procfd `_hashlib` seed is the sole permitted new filesystem-backed import. |

## Rereview round 10 getpath closure

| Finding | Exact closure |
|---|---|
| `R10-P1-GETPATH-001` | The Linux profile is frozen to the exact approved CPython 3.12.3 interpreter digest/build and direct-`P` layout. A root-owned/runtime-nonwritable `python3.12._pth` has exactly `lib/python3.12\n`; the launcher authenticates it and rejects venv/build/competing-`._pth` overrides before `execveat`. Initial `sys.path` is only `[stdlib_root]`; prefix, executable, stdlib, and preloaded-module observations are exact. The bootstrap reopens and retains the getpath file after entry without claiming that this changes CPython's earlier pathname read into held-FD execution. |
| `R10-P1-GETPATH-002` | RED covers exact positive held-FD launch, pre-first-statement stderr observation, every getpath-file byte/identity/permission mutation, both venv locations, both build markers, competing `._pth`, patch/build/layout drift, drift still present at bootstrap reopen, the locally indistinguishable change-and-restore ABA boundary, and forbidden stdlib `os.py`. |

## Round 11 contract and snapshot reconciliation

| Finding | State and required closure |
|---|---|
| `R10-P-ABA-001` | The post-entry getpath check is limited to drift still observable at bootstrap reopen. A change-and-restore ABA fixture proves that stock CPython pathname startup cannot establish continuity; the result remains an external-boundary demonstration and cannot be called a security PASS. |
| `R10-W-ENTRY-001` | A distinct operator-to-guard launcher now binds and retains the externally approved interpreter and bootstrap, traverses native handles without reparses, fixes volume/DOS-device identity, and inherits exactly three dedicated standard-handle duplicates. Absence makes the proxy unavailable. |
| `R10-W-REPORT-001` | Every deployer branch preselects its intended row. One binary counted writer preserves its exact acknowledged prefix; write or terminal-close failure exits 74 through a non-finalizing primitive, and the launcher never parses those bytes. |
| `R10-META-001..007` | `PENDING_R11_REPLACEMENT_GATE`. Review history is non-normative and the reviewer-readable domain is allowlist-only. The exact replacement transport, scope, authority boundary, migration, RED/GREEN matrix, and failure semantics below must pass an independent review with `P0=0` and `P1=0` before this row can become closed. No current snapshot result is final-review evidence. |
| `R11-WIN-PUBLISH-ABI-001` | `PENDING`. On Windows 11 build 26200, the documented Win32 wrapper rejected `FileRenameInfoEx=22`, `Flags=0`, and a non-null retained `RootDirectory` with error 87. Setting `RootDirectory=NULL` is forbidden because the same probe resolved the simple name through process cwd. Native `NtSetInformationFile(FileRenameInformation=10)` with `ReplaceIfExists=FALSE`, the retained parent handle, and the same retained source handle succeeded and returned `STATUS_OBJECT_NAME_COLLISION` without mutation for a competitor. Every affected plan/contract/ADR/test must use and verify only that native ABI; no Win32/pathname fallback is legal. |

## Round 11 bootstrap review transport

This section is normative. It replaces the unsafe directory snapshot design and
all Git-derived worktree evidence. The transport has only three purposes:

1. carry the exact bytes selected for one review;
2. let an independent parser bind those bytes to an externally supplied
   expected content ID and required-domain declaration;
3. persist bounded point-in-time observations for Master handoff.

It cannot authenticate Codex, a reviewer, Master, or the user. It cannot emit
`AUTHORIZED`, `QUALITY_PASS`, or an equivalent claim. A transport failure makes
the review invalid; transport success cannot make a review pass.

### Authority and decision boundary

The Codex task message is an observed external input, not a cryptographic
authority channel. Before dispatch, Master supplies one
`ReviewDispatchObservation.v1` value containing:

- `review_run_id`: the observed Codex subagent/task ID;
- `expected_content_id` and `expected_review_domain_id`;
- `expected_instance_id` and `expected_source_root_identity`;
- the exact sorted `required_files` and `required_absences`;
- one `subject_path`;
- the exact sorted `focus_areas`;
- `reviewer_role=FIRST_PRINCIPLES_IMPLEMENTATION_PLAN_REVIEWER`;
- `authority_verified=false`.

The reviewer independently requires exact equality between that declaration
and the bundle manifest. It also evaluates whether the declared domain is
complete for the requested review. Matching a generator-authored manifest is
insufficient. The reviewer receives the declaration and expected IDs through
the review-dispatch message, not by asking the generator to rediscover them.

The bootstrap state transitions are exact:

| Current state | Required next record | Next state |
|---|---|---|
| `CANDIDATE_PUBLISHED` | create-new valid dispatch observation | `DISPATCH_RECORDED` |
| `DISPATCH_RECORDED` | create-new bundle-verification plus fresh live-domain START observation | `START_PERSISTED` on `MATCH`; `START_REJECTED` otherwise |
| `START_REJECTED` | create-new failure whose predecessor is the rejected START observation | `INVALID_REVIEW` |
| `START_PERSISTED` | create-new `ReviewerInvocationAttempt.v1` send reservation | `REVIEW_INVOCATION_RESERVED` |
| `REVIEW_INVOCATION_RESERVED` | the fresh confirmed reservation creator sends once; an authoritatively associated final event is parsed and create-new persisted as `ReviewerInvocationOutcome.v1` | `REVIEW_INVOCATION_OUTCOME_OBSERVED` |
| `REVIEW_INVOCATION_OUTCOME_OBSERVED` | create-new bundle-verification plus fresh live-domain END observation bound to the invocation outcome | `END_PERSISTED` on `MATCH`; `END_REJECTED` otherwise |
| `END_REJECTED` | create-new failure whose predecessor is the rejected END observation | `INVALID_REVIEW` |
| `END_PERSISTED` | create-new `BootstrapPlanReviewHandoff.v1` | `USER_DECISION_PENDING` |
| `USER_DECISION_PENDING` | recovered-chain validation plus create-new `UserDecisionAttempt.v1` reservation | `USER_DECISION_ATTEMPT_RESERVED` |
| `USER_DECISION_ATTEMPT_RESERVED` | the fresh confirmed reservation creator makes at most one create-new `UserDecisionObservation.v1` call; a definite decision-publication failure may instead create one bound `BootstrapReviewFailure.v1` | `USER_ACCEPTED`, `USER_ACCEPTED_WITH_FINDINGS`, `REVISE_REQUESTED`, `USER_REJECTED`, or `INVALID_REVIEW` |
| any pre-handoff nonterminal state through `END_PERSISTED` | create-new `BootstrapReviewFailure.v1` in the current head's deterministic transition slot only after validation or a definitely-not-published persistence failure | `INVALID_REVIEW` |

`CANDIDATE_PUBLISHED` exists only for an `OK/PUBLISHED_CONFIRMED` publication
result with both writer and independent-inspector IDs equal and a validated
nested artifact-directory binding/ID.

The invocation attempt is the only send authorization. Master destroys its
single-use capability immediately when the host send call is issued. A crash
before the outcome record can leave the send result unknown. Recovery may only
query or reattach to the exact `review_run_id`; it never sends again. If the
host cannot produce an authoritative terminal association, Master returns the
terminal status `REVIEW_INVOCATION_OUTCOME_UNKNOWN`, retains the attempt, and
starts a new review from a new candidate transition chain. It cannot publish a
failure into the attempt successor because a late valid outcome could occupy
that same slot.

Cross-process user-decision recovery is fail-before-write until it has proven
the exact artifact directory and current handoff chain head. A failure before
that proof returns typed `INVALID_CHAIN`; it cannot safely publish a
`BootstrapReviewFailure` into an untrusted or unknown namespace. After proof,
the first write is a deterministic `UserDecisionAttempt.v1` reservation in the
handoff's successor slot. Only the invocation that receives
`OK/PUBLISHED_CONFIRMED` for newly creating that reservation may make one
decision-publication call. An invocation that observes an already-existing
reservation never publishes a decision or failure, even when the reservation
has no successor. This deliberately sacrifices liveness after a crash between
reservation commit and successor commit so that a user-decision publication
call cannot be reissued across processes.

The handoff always contains `state=USER_DECISION_PENDING`; it never predicts
the later user response. The reservation binds the intent and handoff. The user
response is a separate create-new successor of that reservation, bound to the
reservation and handoff content IDs, review run, bundle
content/domain/instance IDs, artifact-directory identity, and request hash;
the handoff content ID indirectly binds the advisory counts.
`USER_ACCEPTED` is legal only when the advisory
counts are `P0=0/P1=0`. Accepting any nonzero count becomes
`USER_ACCEPTED_WITH_FINDINGS`. No user decision rewrites a reviewer FAIL into
`QUALITY_PASS`.

Production Recorder may later retain a bootstrap handoff only as
`BOOTSTRAP_UNAUTHENTICATED_PROVENANCE`. It must not ingest a bootstrap
observation, handoff, or user-decision observation as a dispatch receipt,
reviewer-final event, user-authentication event, or authorization state
transition.

### Exact authoritative domain

The authoritative review domain is the externally declared allowlist, not the
repository or worktree. The transport executes no Git command, parses no Git
administrative file, loads no Git configuration, and computes no tracked,
staged, ignored, diff, branch, HEAD, index, submodule, or sparse-checkout
claim. `subprocess.Popen`, `subprocess.run`, shell execution, hooks, filters,
textconv, fsmonitor, credential helpers, and external diff helpers are absent
from every capture and verification path.

| Source category | Rule |
|---|---|
| tracked, staged, modified, or untracked file | Included only when its exact repository-relative path is in `required_files`; Git disposition is irrelevant. |
| ignored file | Same rule as every other regular file. Ignore files and global/system excludes have no effect. |
| file outside the allowlist | Excluded and cannot affect the review-domain ID. A change outside the allowlist does not invalidate this review. |
| `.git` administrative path | Always rejected, including worktree indirection, object stores, refs, index, replace refs, and nested `.git`. |
| `.gitignore`, `.gitattributes`, `.gitmodules` | Ordinary bytes only when explicitly allowlisted; they never alter capture semantics. |
| nested repository, submodule, or sparse checkout | No special meaning. Only explicitly allowlisted regular files are read. A gitlink or missing worktree file fails the required-file check. |
| local frozen external source | Copied into a declared ordinary local path first, then captured as a required file. URLs and network retrieval are forbidden during capture. |
| symlink, junction, reparse point, mount crossing, directory, FIFO, socket, device, or hard-linked file | Rejected. Every required file must be one local regular file with link count one. A metadata-only no-follow probe classifies any present non-regular object before body open. |
| required absence | A point-in-time metadata-only no-follow probe must return `ABSENT`; every present object type returns `REQUIRED_ABSENCE_PRESENT`. The result remains an `ABSENT_OBSERVATION`, not a continuous or transferable absence proof. |
| artifact directory | A user-selected, existing local directory outside the source root on the same supported storage anchor. It cannot be a source ancestor, source descendant, link, reparse point, mount alias, network filesystem, or current-source repository path. It must already satisfy the exact permission profile below and is validated but never chmodded, chowned, re-ACL'd, renamed, deleted, or reused after a validation failure. |

Repository paths are ASCII bytes, use `/`, are 1..240 bytes, and match
`[A-Za-z0-9][A-Za-z0-9._/-]*`. Empty components, `.`, `..`, leading/trailing
`/`, `//`, `\`, control bytes, drive prefixes, device prefixes, and
case-fold-equivalent duplicates are rejected. Required files and absences are
strictly sorted by path. Before namespace I/O, the union of required files and
absences is checked with one component-boundary ancestor predicate: for any two
distinct rows, neither path may equal, contain, or be contained by the other.
Thus both `required_file="a"` plus `required_absence="a/b"` and the inverse
are `INVALID_DOMAIN_REQUEST`; byte prefixes such as `a` and `ab/c` remain
legal. The predicate is repeated after ASCII case folding, so a cross-list
case variant cannot bypass it. The subject path must occur exactly once in
`required_files`.

For the final Recorder-plan review, the dispatch minimum is:

- every path under `Normative inputs`;
- `docs/recorder/IMPLEMENTATION_PLAN_FINAL.md`;
- all new review-transport implementation modules;
- the independent verifier;
- every review-transport test and golden vector;
- the applicable root `pyproject.toml`;
- any local frozen source whose claim is used by the plan.

The reviewer may reject this minimum as incomplete. The generator may not
silently reduce it.

### Machine readiness control

Final-review readiness is not inferred from arbitrary Markdown. The fixed path
`evaluation/aegis_v2/review_control.v1.json` must be a required allowlisted
file with exact restricted-canonical-JSON bytes:

```text
{
  "implementation_or_test_execution_claims_allowed": false,
  "pass_condition": {"P0": 0, "P1": 0},
  "required_status": "READY_FOR_FINAL_REVIEW",
  "review_type": "FIRST_PRINCIPLES_IMPLEMENTATION_PLAN_REVIEW",
  "schema": "AegisReviewControl.v1",
  "subject_path": "docs/recorder/IMPLEMENTATION_PLAN_FINAL.md",
  "subject_sha256": "sha256:<64-lowercase-hex>"
}
```

The displayed whitespace above is explanatory; the file itself is one
canonical JSON value with no trailing byte. `subject_sha256` must equal the
raw subject bytes. The third physical line, including its LF terminator, must
equal the byte string
`5374617475733a206052454144595f464f525f46494e414c5f524556494557600a`
decoded from
lowercase hexadecimal. No other physical line may equal that complete decoded
content. Substring occurrences and explanatory mentions do not participate in
this equality check.

Manifest and dispatch both carry the fixed control path, status, review type,
and pass condition. Candidate inspection, dispatched verification, START, and
END reject an absent, noncanonical, non-allowlisted, hash-mismatched,
non-READY, wrong-review-type, or wrong-threshold control.

Until R11A..R11E pass, this control file is absent and the subject status stays
`ROUND_11_CONTRACT_AND_SNAPSHOT_RECONCILIATION_IN_PROGRESS`. R11F creates the
control and changes line 3 in the same reviewed change.

### Root and file observations

The caller supplies only a path used to open the source root. The implementation
derives root identity from the retained object:

- Linux: `{"platform":"linux","st_dev":"<decimal-u64>",
  "st_ino":"<decimal-u64>","statx_mnt_id":"<decimal-u64>"}`;
- Windows: `{"platform":"windows","volume_serial_number":
  "<decimal-u64>","file_id_128":"<32-lowercase-hex>"}`.

Every file record contains the same platform-specific object identity, link
count one, byte size, and SHA-256. Integer-valued OS identities are encoded as
decimal strings so JCS safe-integer limits cannot truncate them. The expected
root identity in the dispatch must equal the manifest identity. This catches
an accidental wrong-root handoff but does not authenticate who supplied the
expected identity.

The implementation internally creates a UUIDv4 instance ID and UTC capture
start/end values. The public builder accepts none of those values. Times use
exact `YYYY-MM-DDTHH:MM:SS.ffffffZ`, start is not after end, elapsed capture
time is at most 120 seconds, and end cannot exceed the verifier's local clock
by more than 300 seconds. UUID provides instance uniqueness; wall time provides
ordering evidence only inside this one bounded capture and is not a
cross-process ordering oracle.

Builder order is fixed: validate the caller's required-domain declaration;
select and preflight one platform profile; generate the UUID; open and validate
the artifact directory; open and identify the source root; prove their
handle-bound non-alias/non-ancestry relation; bind the artifact directory;
acquire one UTC value and use it as both `binding_observed_at_utc` and
`capture_started_at_utc`; capture the domain through the retained source
handle; record capture-completion time; write and inspect the candidate;
publish. Thus the binding observation occurs on the already-open validated
directory after the source/artifact relationship proof and
`binding_observed_at_utc=capture_started_at_utc<=capture_completed_at_utc`.
The nested binding is exposed only on final confirmed success. This order is
the nullability basis for the result table below.

The stable `review_domain_id` is SHA-256 over:

```text
"AEGIS_REVIEW_DOMAIN_V1\0"
+ restricted-canonical-JSON({
    schema="AegisReviewDomain.v1",
    source_root_identity,
    subject_path,
    review_control_path,
    required_status,
    review_type,
    pass_condition,
    focus_areas,
    records
  })
```

It excludes UUID and capture times, so START and END can compare current
allowlisted bytes with the reviewed domain. It includes exact file paths,
sizes, hashes, object observations, and absence observations. No point-in-time
comparison claims continuous monitoring.

The domain preimage object has exactly the nine keys shown in the pseudocode:
`focus_areas,pass_condition,records,required_status,review_control_path,
review_type,schema,source_root_identity,subject_path`.

### `AegisReviewBundle.v1` byte protocol

All integers are unsigned big-endian. The parser checks every length before
allocation or addition.

| Field | Exact bytes |
|---|---|
| magic | 16 bytes: `41 65 67 69 73 52 65 76 69 65 77 56 31 00 00 00` (`AegisReviewV1` plus three NUL bytes) |
| record count | `u32`, 1..512 |
| record | one tag, one path, then tag-specific payload |
| file tag | `0x01` |
| absence tag | `0x02` |
| path | `u16` byte length followed by canonical ASCII path bytes |
| file payload | `u64` content length, exact content bytes, then raw 32-byte SHA-256 |
| absence payload | zero additional bytes |
| manifest tag | `0x7f` |
| manifest | `u32` byte length followed by exact restricted-canonical-JSON bytes |
| trailer tag | `0xff` |
| trailer | raw 32-byte bundle content digest, immediately followed by EOF |

Records are strictly increasing by raw path bytes. The manifest has exact keys:

```text
authority_verified=false
capture_completed_at_utc
capture_started_at_utc
focus_areas
instance_id
pass_condition
records
required_status
review_control_path
review_domain_id
review_type
schema="AegisReviewBundle.v1"
source_root_identity
subject_path
```

Each manifest record exactly matches one binary record. A file row adds
`kind=FILE`, `size`, `sha256`, `object_identity`, and `link_count=1`; an absence
row contains only `kind=ABSENT_OBSERVATION` and `path`. Strings are restricted
to the ASCII grammars in this section; JSON floats, negative integers, unsafe
integers, duplicate keys, escapes, unknown keys, and Unicode are rejected.
Canonical JSON has UTF-8 encoding, lexicographically sorted ASCII keys, no
insignificant whitespace, and no trailing LF.

### Canonical schema grammars

Every JSON object has the exact key set declared below. Unknown, missing, or
duplicate keys fail. No stored string permits `"` or `\`, so JSON escapes are
never legal.

| Name | Exact grammar and semantic bound |
|---|---|
| `PATH` | `[A-Za-z0-9][A-Za-z0-9._/-]{0,239}` plus the component, slash, `.git`, and case-fold rules above |
| `TOKEN` | `[A-Z][A-Z0-9_:-]{0,127}` |
| `RUN_ID` | `[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}` |
| `UUID4` | lowercase `[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}` |
| `SHA256_ID` | `sha256:[0-9a-f]{64}` |
| `UTC` | `[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\\.[0-9]{6}Z`, also a valid UTC date/time |
| `U64_DECIMAL` | `0|[1-9][0-9]{0,19}`, parsed value at most `18446744073709551615` |
| `I64_DECIMAL` | `0|-?[1-9][0-9]{0,18}`, parsed value from `-9223372036854775808` through `9223372036854775807`; negative zero and leading zero are forbidden |
| `FILE_ID_128` | `[0-9a-f]{32}` |
| `COUNT` | JSON integer `0..9999` |
| `WINDOWS_SID` | canonical uppercase `S-1-<identifier-authority>-<subauthority>...`; authority is canonical decimal `0..281474976710655`, there are 1..15 canonical decimal subauthorities each `0..4294967295`, and no leading zero except the value zero |

Arrays have fixed rules:

- `required_files`: 1..256 `PATH` values, strictly increasing by raw ASCII and
  unique under case fold;
- `required_absences`: 0..256 `PATH` values with the same ordering, uniqueness,
  and ancestry exclusions;
- `focus_areas`: 1..32 `TOKEN` values, strictly increasing and unique;
- `records`: exactly the sorted union of both required-path arrays, 1..512,
  strictly increasing by `path`;
- no other array occurs in the bootstrap schemas.

Identity objects are platform-discriminated and have no alternative keys:

```text
LinuxRootOrFileIdentity = {
  "platform": "linux",
  "st_dev": U64_DECIMAL,
  "st_ino": U64_DECIMAL,
  "statx_mnt_id": U64_DECIMAL
}

WindowsRootOrFileIdentity = {
  "file_id_128": FILE_ID_128,
  "platform": "windows",
  "volume_serial_number": U64_DECIMAL
}
```

`RootIdentity` and `RootOrFileIdentity` below are shorthand for exactly
`LinuxRootOrFileIdentity | WindowsRootOrFileIdentity`; they introduce no
additional shape. `NativeLocator` is the closed platform-discriminated grammar
defined under `Publication and error state`; forward references to it admit no
path-like or string alternative.

Artifact-directory protection is also a closed platform-discriminated value:

```text
LinuxArtifactDirectoryProtection = {
  "access_acl_present": false,
  "default_acl_present": false,
  "mode_octal": "0700",
  "owner_uid": U64_DECIMAL,
  "platform": "linux"
}

WindowsArtifactDirectoryProtection = {
  "canonical_sddl":
    "O:<owner_sid>D:P(A;;FA;;;SY)(A;;FA;;;<owner_sid>)",
  "owner_sid": WINDOWS_SID,
  "platform": "windows"
}
```

The two `<owner_sid>` substitutions are byte-identical to `owner_sid`; no
equivalent ACE ordering, inherited ACE, group field, alias expansion, or
alternate SDDL spelling is accepted. `ArtifactDirectoryProtection` below is
exactly the union of these two values.

Directory storage anchoring is another closed union:

```text
LinuxDirectoryStorageAnchor = {
  "platform": "linux",
  "statx_mnt_id": U64_DECIMAL
}

WindowsDirectoryStorageAnchor = {
  "drive_letter": "[A-Z]",
  "native_device_target_utf16le_hex": "<4..2048 lowercase hex chars,
                                        length divisible by four>",
  "platform": "windows",
  "volume_guid_utf16le_hex": "<exact canonical volume-GUID path>",
  "volume_serial_number": U64_DECIMAL
}
```

The Windows GUID field decodes as strict UTF-16LE to exactly
`\\?\Volume{xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx}\` with lowercase hex in the
`8-4-4-4-12` groups and no NUL. The native-target field decodes
as strict UTF-16LE to the first current `QueryDosDeviceW` target, begins
`\Device\`, and has no NUL. The drive letter equals the canonical locator.
The volume serial equals every bound Windows directory identity. Linux
`statx_mnt_id` equals every bound Linux directory identity. No alternate
mapping spelling or later target is accepted.
`DirectoryStorageAnchor` is exactly this union.

Each manifest file record has exact keys
`kind,link_count,object_identity,path,sha256,size`, where `kind="FILE"`,
`link_count=1`, `path=PATH`, `sha256=SHA256_ID`, and `size` is a JSON integer
`0..16777216`. Each absence record has only
`kind="ABSENT_OBSERVATION",path=PATH`.

`AegisReviewBundle.v1` has exactly the manifest keys listed above with:

- `authority_verified=false`;
- `instance_id=UUID4`;
- both capture fields `UTC`;
- `schema="AegisReviewBundle.v1"`;
- `review_control_path=
  "evaluation/aegis_v2/review_control.v1.json"`;
- `required_status="READY_FOR_FINAL_REVIEW"`;
- `review_type="FIRST_PRINCIPLES_IMPLEMENTATION_PLAN_REVIEW"`;
- `pass_condition={"P0":0,"P1":0}`;
- `subject_path=PATH`, `review_domain_id=SHA256_ID`;
- the exact root identity, focus array, and record array defined above.

`CapturedReviewDomainFacts.v1` is an immutable, non-authorizing boundary
between real platform capture and pure domain assembly. It has exactly:

```text
authority_verified=false
capture_completed_at_utc=UTC
capture_started_at_utc=UTC
instance_id=UUID4
records=<the exact manifest record array>
schema="CapturedReviewDomainFacts.v1"
source_root_identity=LinuxRootOrFileIdentity
                           | WindowsRootOrFileIdentity
```

It contains observations and hashes, not file bodies or open handles.
`capture_started_at_utc <= capture_completed_at_utc`; all record, identity,
size, ordering, count, and capture-window rules in this section apply. It is
not persisted as review evidence. Production creates it only from retained
platform handles; the pure assembler accepts exact canonical bytes so R11B can
be tested without pretending that test-supplied facts came from a filesystem.

`ParsedReviewerAdvisory.v1` is also ephemeral and non-authorizing. It has
exactly:

```text
advisory_p0=COUNT
advisory_p1=COUNT
advisory_verdict="PASS" | "FAIL"
authority_verified=false
master_observed_reviewer_final_text_sha256=SHA256_ID
normalized_utf8_size=<JSON integer 1..1048576>
schema="ParsedReviewerAdvisory.v1"
```

Its verdict/count equivalence and text normalization are exactly those in
`Bootstrap observations and handoff`. The parser returns this canonical value;
it does not retain, rewrite, or authenticate the normalized text.

`ArtifactDirectoryBinding.v1` is the content-addressed, non-authorizing
cross-call binding for the local artifact mailbox. It has exactly:

```text
artifact_directory_identity=LinuxRootOrFileIdentity
                            | WindowsRootOrFileIdentity
artifact_directory_locator=NativeLocator
artifact_directory_protection=ArtifactDirectoryProtection
artifact_directory_storage_anchor=DirectoryStorageAnchor
authority_verified=false
binding_observed_at_utc=UTC
continuous_identity_verified=false
evidence_origin="NATIVE_RUNTIME" | "SYNTHETIC_CONFORMANCE"
instance_id=UUID4
profile="WINDOWS_NTFS_V1" | "LINUX_LOCAL_V1"
schema="ArtifactDirectoryBinding.v1"
```

Its platform relation is iff and independently validated:
`LINUX_LOCAL_V1` requires a `POSIX_BYTES_HEX` locator plus Linux identity and
Linux protection/anchor; `WINDOWS_NTFS_V1` requires a `UTF16LE_HEX` locator
plus Windows identity and Windows protection/anchor. The anchor fields must
equal the identity and locator relations above. No mixed tuple is structurally
legal. Its locator also obeys the non-root artifact-directory grammar and
105-unit child headroom below. When the runtime creates or reopens a binding,
the observed effective UID/SID must equal the protection owner; this principal
equality is runtime evidence, not derivable from detached binding bytes. A
successful bundle result's profile equals its nested binding profile.

Its content ID is `sha256:` plus lowercase SHA-256 over
`"AEGIS_ARTIFACT_DIRECTORY_BINDING_V1\0"` and its exact canonical bytes.
The builder creates it after generating the candidate instance ID and
successfully opening, identifying, and validating the existing artifact
directory, but before candidate-file creation. Its `instance_id` equals the
candidate instance and `binding_observed_at_utc` equals the bundle's
`capture_started_at_utc`. A successful builder result carries the exact nested
binding and content ID.

Every later pre-decision facade call receives the exact binding bytes instead
of a bare artifact-directory locator. It reopens the locator, requires the
current profile, identity, owner, mode/DACL/ACL, filesystem, and binding ID to
match the exact binding identity, protection, and storage-anchor objects; the
current effective UID/SID must also equal the bound owner. It then retains that
handle for every read and write in that call.
User-decision recovery performs the same proof from a fresh process. A valid
binding is point evidence only: replacement and restoration between calls is
not observed, identity reuse is outside this local claim, and
`continuous_identity_verified` is permanently false. Within one call, all
namespace operations remain relative to its retained handle. A publishing call
also performs the separate precommit and postcommit locator reopens defined
below; those point checks do not replace the retained-handle rule.

The candidate builder accepts exactly three caller inputs: one native absolute
source-root locator, one native absolute existing `artifact_path` directory
locator, and the raw bytes of `CandidateDomainRequest.v1`. It accepts no
caller UUID, wall time, expected content/domain ID, root identity, output file
name, environment-derived path, or open file object. The two locators are used
only to acquire retained root/directory handles and are then identity-checked;
all later traversal and publication is relative to those handles. The artifact
directory is never created or permission-modified by this entry point.

`CandidateDomainRequest.v1` is the only semantic request value and has exact
keys:

```text
authority_verified=false
focus_areas=<focus array>
pass_condition={"P0":0,"P1":0}
required_absences=<absence path array>
required_files=<file path array>
required_status="READY_FOR_FINAL_REVIEW"
review_control_path="evaluation/aegis_v2/review_control.v1.json"
review_type="FIRST_PRINCIPLES_IMPLEMENTATION_PLAN_REVIEW"
schema="CandidateDomainRequest.v1"
subject_path=PATH
```

It is an unauthenticated selection request, not a completeness proof. Its
shared fields must equal the resulting manifest. The final reviewer still
judges whether the selection omitted relevant inputs.

`ReviewDispatchObservation.v1` has exactly:

```text
artifact_directory_binding_id=SHA256_ID
authority_verified=false
dispatch_observation_id=UUID4
dispatch_observed_at_utc=UTC
expected_content_id=SHA256_ID
expected_instance_id=UUID4
expected_review_domain_id=SHA256_ID
expected_source_root_identity=LinuxRootOrFileIdentity
                              | WindowsRootOrFileIdentity
focus_areas=<focus array>
pass_condition={"P0":0,"P1":0}
predecessor_content_id=SHA256_ID
required_absences=<absence path array>
required_files=<file path array>
required_status="READY_FOR_FINAL_REVIEW"
review_control_path="evaluation/aegis_v2/review_control.v1.json"
review_run_id=RUN_ID
review_type="FIRST_PRINCIPLES_IMPLEMENTATION_PLAN_REVIEW"
reviewer_role="FIRST_PRINCIPLES_IMPLEMENTATION_PLAN_REVIEWER"
schema="ReviewDispatchObservation.v1"
subject_path=PATH
```

Every dispatch field shared with the manifest must be exactly equal. The file
and absence arrays must equal the corresponding manifest-record paths, not a
subset. `predecessor_content_id` must equal `expected_content_id`; this binds
the first transition slot to the published bundle. Its artifact-directory
binding ID must equal the successful candidate result.

`ReviewerInvocationAttempt.v1` is the durable send reservation and has exactly:

```text
artifact_directory_binding_id=SHA256_ID
authority_verified=false
dispatch_content_id=SHA256_ID
instance_id=UUID4
predecessor_content_id=SHA256_ID
review_payload_sha256=SHA256_ID
review_request_sha256=SHA256_ID
review_run_id=RUN_ID
schema="ReviewerInvocationAttempt.v1"
snapshot_content_id=SHA256_ID
start_observation_content_id=SHA256_ID
state="REVIEW_INVOCATION_RESERVED"
```

The predecessor and START IDs both equal the matched START observation content
ID. The payload is 1..1,048,576 strict UTF-8 bytes containing only Unicode
scalars and no NUL. `review_payload_sha256` is its raw SHA-256. The stable
`review_request_sha256` is SHA-256 over
`"AEGIS_REVIEW_INVOCATION_REQUEST_V1\0"`, the exact dispatch bytes, the exact
START bytes, and the exact payload bytes in that order. A successful
create-new publication of this record returns one process-local, single-use
send capability. Reading an existing matching record never recreates that
capability.

`ReviewerInvocationOutcome.v1` is the durable observation needed to reconstruct
END and has exactly:

```text
advisory_p0=COUNT
advisory_p1=COUNT
advisory_verdict="PASS" | "FAIL"
artifact_directory_binding_id=SHA256_ID
attempt_content_id=SHA256_ID
authority_verified=false
instance_id=UUID4
master_observed_final_event_at_utc=UTC
master_observed_reviewer_final_text_sha256=SHA256_ID
normalized_utf8_size=<JSON integer 1..1048576>
predecessor_content_id=SHA256_ID
review_request_sha256=SHA256_ID
review_run_id=RUN_ID
schema="ReviewerInvocationOutcome.v1"
snapshot_content_id=SHA256_ID
state="REVIEW_INVOCATION_OUTCOME_OBSERVED"
```

Its predecessor and attempt IDs equal the invocation-attempt content ID. Its
advisory fields and normalized text facts equal one successful
`ParsedReviewerAdvisory.v1`. An outcome is published only after the host has
authoritatively associated the observed final event with the exact
`review_run_id` and request. A later process may query or reattach only through
that stable host ID. If the host cannot distinguish “not sent,” “running,”
“completed,” and “lost result,” the attempt is terminal
`REVIEW_INVOCATION_OUTCOME_UNKNOWN`: it is never resent, guessed, or converted
into an END, and a new review run is required.

`BootstrapReviewObservation.v1` has the exact key set listed in the observation
section. Its artifact-directory binding ID, all expected IDs, and expected
root are non-null and follow the grammars above. The binding ID equals the
dispatch and supplied binding. Observed IDs and observed root are either the
corresponding valid value or JSON `null`. `MATCH` requires every observed value
non-null and equal to its expected value, with `observation_reason_code=OK`.
`MISMATCH` requires every observed value non-null, at least one inequality,
and `OBSERVED_VALUE_MISMATCH`. `UNSUPPORTED` requires
`UNSUPPORTED_PLATFORM` and at least one unavailable observed value.
`INVALID` never authorizes continuation; it requires at least one unavailable
observed value except that `OBSERVATION_LIMIT_EXCEEDED` may retain all four
values when the deadline or monotonic-source failure is first observed after
the final live-domain calculation. No other all-non-null `INVALID` row is
legal.
`predecessor_content_id` is always `SHA256_ID`. START requires every advisory
field null. END requires advisory verdict/counts/text hash/final-event time
non-null and internally consistent.

`BootstrapPlanReviewHandoff.v1` has exactly:

```text
advisory_p0=COUNT
advisory_p1=COUNT
advisory_verdict="PASS" | "FAIL"
artifact_directory_binding_id=SHA256_ID
artifact_directory_identity=LinuxRootOrFileIdentity
                            | WindowsRootOrFileIdentity
authority_verified=false
dispatch_content_id=SHA256_ID
dispatch_observation_id=UUID4
end_observation_content_id=SHA256_ID
end_observation_id=UUID4
handoff_record_id=UUID4
instance_id=UUID4
invocation_attempt_content_id=SHA256_ID
invocation_outcome_content_id=SHA256_ID
master_observed_final_event_at_utc=UTC
master_observed_reviewer_final_text_sha256=SHA256_ID
predecessor_content_id=SHA256_ID
review_request_sha256=SHA256_ID
review_domain_id=SHA256_ID
review_run_id=RUN_ID
schema="BootstrapPlanReviewHandoff.v1"
snapshot_content_id=SHA256_ID
start_observation_content_id=SHA256_ID
start_observation_id=UUID4
state="USER_DECISION_PENDING"
```

`advisory_verdict="PASS"` is equivalent to `advisory_p0=0` and
`advisory_p1=0`; `FAIL` is equivalent to at least one nonzero count.
`predecessor_content_id` must equal `end_observation_content_id`. Invocation
IDs and request hash must equal the validated START -> invocation-attempt ->
invocation-outcome -> END chain. The binding ID equals dispatch, START,
invocation records, END, and the supplied binding; the full identity equals
the identity inside that binding.

`UserDecisionAttempt.v1` is the process-persistent pre-publication reservation
and has exactly:

```text
artifact_directory_binding_id=SHA256_ID
artifact_directory_identity=LinuxRootOrFileIdentity
                            | WindowsRootOrFileIdentity
attempt_ordinal=0
authority_verified=false
decision_observation_id=UUID4
handoff_content_id=SHA256_ID
handoff_record_id=UUID4
instance_id=UUID4
intended_decision="USER_ACCEPTED" | "USER_ACCEPTED_WITH_FINDINGS"
                  | "REVISE_REQUESTED" | "USER_REJECTED"
master_observed_user_decision_at_utc=UTC
predecessor_content_id=SHA256_ID
request_sha256=SHA256_ID
review_domain_id=SHA256_ID
review_run_id=RUN_ID
schema="UserDecisionAttempt.v1"
snapshot_content_id=SHA256_ID
state="DECISION_PUBLICATION_RESERVED"
```

Every field is derived from the validated handoff and stable intent.
`predecessor_content_id` must equal `handoff_content_id`. The reservation
contains no attempted decision content ID because the decision's predecessor
is the reservation content ID; storing the decision ID in the reservation
would create a content-hash cycle. Its binding ID and full artifact-directory
identity equal the handoff, intent, and current reopened binding.

`UserDecisionObservation.v1` has exactly:

```text
artifact_directory_binding_id=SHA256_ID
artifact_directory_identity=LinuxRootOrFileIdentity
                            | WindowsRootOrFileIdentity
attempt_content_id=SHA256_ID
attempt_ordinal=0
authority_verified=false
decision="USER_ACCEPTED" | "USER_ACCEPTED_WITH_FINDINGS"
       | "REVISE_REQUESTED" | "USER_REJECTED"
decision_observation_id=UUID4
handoff_content_id=SHA256_ID
handoff_record_id=UUID4
instance_id=UUID4
master_observed_user_decision_at_utc=UTC
predecessor_content_id=SHA256_ID
request_sha256=SHA256_ID
review_domain_id=SHA256_ID
review_run_id=RUN_ID
schema="UserDecisionObservation.v1"
snapshot_content_id=SHA256_ID
```

The validator loads the exact handoff selected by `handoff_content_id` and
the exact reservation selected by `attempt_content_id`, then requires the
current retained artifact-directory binding ID/identity and all repeated IDs
equal.
`USER_ACCEPTED` requires a PASS handoff;
`USER_ACCEPTED_WITH_FINDINGS` requires a FAIL handoff.
`predecessor_content_id` must equal `attempt_content_id`; the attempt must have
`predecessor_content_id=handoff_content_id` and `attempt_ordinal=0`.
Intent `ACCEPT` derives `USER_ACCEPTED` for PASS and
`USER_ACCEPTED_WITH_FINDINGS` for FAIL; `REVISE` derives
`REVISE_REQUESTED`; `REJECT` derives `USER_REJECTED`. The caller cannot select
the stored internal decision token directly. The observation ID and
Master-observed time equal the stable intent fields below. They are
traceability fields under `authority_verified=false`, not authenticated user
identity, uniqueness, or wall-clock-order proofs.

`UserDecisionIntent.v1` is the stable unauthenticated user-decision input with
exactly:

```text
authority_verified=false
decision_observation_id=UUID4
expected_artifact_directory_binding_id=SHA256_ID
expected_artifact_directory_identity=LinuxRootOrFileIdentity
                                     | WindowsRootOrFileIdentity
expected_end_observation_content_id=SHA256_ID
expected_handoff_content_id=SHA256_ID
expected_instance_id=UUID4
expected_review_domain_id=SHA256_ID
expected_review_run_id=RUN_ID
expected_snapshot_content_id=SHA256_ID
master_observed_user_decision_at_utc=UTC
requested_decision="ACCEPT" | "REVISE" | "REJECT"
schema="UserDecisionIntent.v1"
```

After the user decides, Master generates the UUID/time exactly once, writes
the exact intent bytes to its continuation state outside the artifact
directory, and reuses those bytes unchanged for every recovery call. Python
does not regenerate either field. If those exact bytes are lost, a new review
is required. `request_sha256` is `sha256:` plus lowercase SHA-256 over
`"AEGIS_USER_DECISION_INTENT_V1\0"` and the exact
restricted-canonical-JSON intent bytes. Because every other observation field
is derived from the validated handoff and reservation, the same intent and
handoff construct the same `UserDecisionAttempt.v1`; its content ID then
constructs the same `UserDecisionObservation.v1` bytes and content ID.

`UserDecisionPriorOutcome.v1` has exactly:

```text
attempt_content_id=SHA256_ID
attempt_transition_result=TransitionPublicationResult.v1 | null
attempted_decision_content_id=SHA256_ID | null
authority_verified=false
decision_transition_result=TransitionPublicationResult.v1 | null
failure_content_id=SHA256_ID | null
failure_transition_result=TransitionPublicationResult.v1 | null
request_sha256=SHA256_ID
resume_state = ATTEMPT_PERSISTENCE_UNCONFIRMED
             | ATTEMPT_PUBLICATION_OUTCOME_UNKNOWN
             | DECISION_ATTEMPT_OUTCOME_UNKNOWN
             | DECISION_FAILURE_RECORDED
             | FAILURE_PERSISTENCE_UNRECORDED
             | FAILURE_PERSISTENCE_UNCONFIRMED
             | FAILURE_PUBLICATION_OUTCOME_UNKNOWN
             | DECISION_PERSISTENCE_UNCONFIRMED
             | DECISION_PUBLICATION_OUTCOME_UNKNOWN
schema="UserDecisionPriorOutcome.v1"
```

Its state and nested-result fields must match the
`UserDecisionResumeResult.v1` table exactly. It is external recovery evidence,
not authority. Every nested transition result's binding ID must equal the
intent's expected binding ID through `request_sha256`; a prior outcome cannot
be replayed into another binding or review instance.

The second argument to the recovery entry is exact canonical
`UserDecisionResumeEnvelope.v1` bytes:

```text
intent=UserDecisionIntent.v1
prior_outcome=UserDecisionPriorOutcome.v1 | null
schema="UserDecisionResumeEnvelope.v1"
```

The first call uses null. After a result in one of the nine
`UserDecisionPriorOutcome.v1` states returns, Master must persist and supply
its exact validated prior outcome on every later call. Omitting such a returned
outcome violates the Master contract. Write-free
`RECOVERY_LIMIT_EXCEEDED` may retry only with the same envelope, including the
same null or non-null prior outcome; invalid-chain/conflict states are terminal
for that run. A process crash before return has no prior outcome;
the persisted reservation, not an externally remembered counter, prevents a
second decision-publication call.

`BootstrapReviewFailure.v1` has exactly
`artifact_directory_binding_id=SHA256_ID`,
`attempt_content_id=SHA256_ID|null`, `attempt_ordinal=0|null`,
`attempted_user_decision_content_id=SHA256_ID|null`,
`authority_verified=false`, `failure_record_id=UUID4`,
`failed_state=CANDIDATE_PUBLISHED|DISPATCH_RECORDED|START_PERSISTED|
START_REJECTED|REVIEW_INVOCATION_RESERVED|
REVIEW_INVOCATION_OUTCOME_OBSERVED|END_PERSISTED|END_REJECTED|
USER_DECISION_ATTEMPT_RESERVED`,
`intended_user_decision=USER_ACCEPTED|USER_ACCEPTED_WITH_FINDINGS|
REVISE_REQUESTED|USER_REJECTED|null`,
`instance_id=UUID4`, `observed_at_utc=UTC`,
`persistence_reason_code=TransitionPublicationReason|null`,
`predecessor_content_id=SHA256_ID`,
`reason_code=<closed reason below>`, `review_domain_id=SHA256_ID`,
`review_run_id=RUN_ID|null`, `schema="BootstrapReviewFailure.v1"`, and
`snapshot_content_id=SHA256_ID`,
`user_decision_request_sha256=SHA256_ID|null`,
`user_decision_transition_result=TransitionPublicationResult.v1|null`.
Bootstrap processing starts
only after a confirmed candidate exists, so the instance, domain, snapshot,
and predecessor fields are never null. The exact
state/reason/nullability/user-decision-binding matrix appears under
`BootstrapFailureReason`.

Bootstrap JSON records contain no self-ID. Their externally referenced content
ID is `sha256:` plus lowercase SHA-256 over the named domain, one NUL byte, and
the exact restricted-canonical-JSON bytes:

| Schema | Domain ASCII |
|---|---|
| `ReviewDispatchObservation.v1` | `AEGIS_REVIEW_DISPATCH_OBSERVATION_V1` |
| `BootstrapReviewObservation.v1` | `AEGIS_BOOTSTRAP_REVIEW_OBSERVATION_V1` |
| `ReviewerInvocationAttempt.v1` | `AEGIS_REVIEWER_INVOCATION_ATTEMPT_V1` |
| `ReviewerInvocationOutcome.v1` | `AEGIS_REVIEWER_INVOCATION_OUTCOME_V1` |
| `BootstrapPlanReviewHandoff.v1` | `AEGIS_BOOTSTRAP_PLAN_REVIEW_HANDOFF_V1` |
| `UserDecisionAttempt.v1` | `AEGIS_USER_DECISION_ATTEMPT_V1` |
| `UserDecisionObservation.v1` | `AEGIS_USER_DECISION_OBSERVATION_V1` |
| `BootstrapReviewFailure.v1` | `AEGIS_BOOTSTRAP_REVIEW_FAILURE_V1` |

Each record is persisted create-new with no trailing byte and the platform
permission profile. Every successor occupies the one deterministic component
`transition-<64 lowercase hex digits from predecessor_content_id>.json`
inside the retained artifact directory. Dispatch, handoff, attempt, and
decision records, reviewer invocation records, observations, and failures all
carry an explicit predecessor field. Every record carries the same
artifact-directory
binding ID, and the publisher rejects a mismatch before opening the directory.
The component and predecessor field must agree. A predecessor
therefore has at most one namespace successor: success, rejected observation,
reservation, or failure all compete for the same create-new slot. The handoff
slot can contain only its one user-decision attempt reservation. The START
slot can contain only its reviewer invocation attempt or a bound failure; that
invocation-attempt slot can contain only its outcome or a bound failure; the
invocation-outcome slot can contain only END or a bound failure. The
user-decision attempt slot can contain only its decision or its request-bound
persistence failure. A pre-existing
slot is never overwritten, deleted, or treated as a successful publication by
the current invocation.

After complete chain proof, `resume_user_decision` may return read-only
`ALREADY_RECORDED` or `ALREADY_DECISION_FAILURE_RECORDED` for an exact existing
successor. It never reissues decision bytes. Only the in-memory invocation that
has just received `OK/PUBLISHED_CONFIRMED` for creating the attempt may call the
decision publisher, once. A later process cannot reconstruct that permission
from the attempt bytes, a prior outcome, or a matching intent. This rule bounds
the decision-publication syscall count for one intent to at most one under the
supported stable protected-namespace assumption.

START and END always attempt to persist their observation first, including
`MISMATCH`, `INVALID`, and `UNSUPPORTED`. Only
`OK/PUBLISHED_CONFIRMED` makes a rejected observation the chain head; the
immediately following failure must then name that observation's independently
recomputed content ID as its predecessor. A directory-binding or other
nonconfirmed persistence result terminates with that result and creates no
failure record in an unproved namespace. Except for
`UserDecisionAttempt.v1`, a definitely-not-published transition-persistence
failure may instead publish a failure into the still-empty slot of the prior
head. Attempt-reservation nonpublication returns its typed attempt state and
never spends the handoff slot on a failure. If the attempted transition is
`PUBLISHED_UNCONFIRMED` or `PUBLICATION_OUTCOME_UNKNOWN`, no competing failure
is attempted: Master terminates with the original result and an explicitly
unrecorded terminal error. If failure persistence itself fails or is
unconfirmed, Master terminates without claiming a persisted failure. These are
the only no-persist terminal boundaries.

A successor references the independently recomputed predecessor content ID.
Re-signing a changed predecessor therefore requires changing every successor,
and the one-slot rule prevents two create-new successors from forming a valid
fork. None of these mechanics can produce authority.

Record persistence reuses the same held regular-file write, flush, rewind,
independent reparse, create-new publication, postcommit identity, no-rollback,
fixed-false authority, and power-loss-boundary rules as the bundle. It does
not use `Path.write_text`, a pathname temporary, or overwrite an existing
record.

On Windows, a non-attempt transition staging component is exactly
`.aegis-transition-staging-<independent-lowercase-UUID4>.tmp`; the attempt
exception remains the deterministic component defined below. Once create-new
returns a retained staging handle, a subsequent identity/protection query
failure, wrong type/identity/protection observation, or deadline never deletes
the named file. Query failure or observed inequality returns
`TRANSITION_CREATED_OBJECT_QUERY_FAILED`; deadline or monotonic-source failure
returns
`TRANSITION_CREATED_LIMIT_EXCEEDED` with the staging locator and null object
identity. Bundle creation uses the analogous
`CANDIDATE_CREATED_OBJECT_QUERY_FAILED` or
`CANDIDATE_CREATED_LIMIT_EXCEEDED`. Linux closes the corresponding unlinked
inode and has no staging locator. The phase moves to WRITE only after identity
and protection are fully observed and the following deadline check passes, so
these CREATE rows are exhaustive and do not expose a partially trusted
identity.

The bundle content digest is:

```text
SHA-256("AEGIS_REVIEW_BUNDLE_CONTENT_V1\0"
       + every byte from magic through the final manifest byte)
```

The externally visible ID is `sha256:` plus its lowercase hexadecimal form.
The trailer stores the raw digest. The manifest deliberately contains no
self-ID. Unknown tags, duplicate or out-of-order records, unreferenced data,
hash mismatch, manifest/frame mismatch, truncation, trailing bytes, short
read/write, arithmetic overflow, or noncanonical JSON fail closed.

Bounds are exact:

| Resource | Bound |
|---|---|
| required files | 1..256 |
| required absences | 0..256 |
| total records | 1..512 |
| focus areas | 1..32; each one `TOKEN` |
| one file | 0..16,777,216 bytes |
| manifest | 1..2,097,152 bytes |
| complete container | 1..67,108,864 bytes |
| one artifact-directory binding | 1..65,536 bytes |
| one canonical transition JSON record | 1..2,097,152 bytes |
| one user-decision resume envelope | 1..2,097,152 bytes |
| normalized reviewer final text | 1..1,048,576 bytes |
| stream chunk | at most 65,536 bytes |
| build or verify controlled elapsed time | 120 seconds |
| one file controlled elapsed time | 30 seconds |
| subprocess count | exactly zero |

The monotonic timer starts before input validation. It is checked before and
after every platform probe, UUID/UTC acquisition, open, read, write, flush,
link/rename, reopen, and parse step. A missing, invalid, or failed monotonic
sample is fail-closed and maps exactly as an exceeded deadline in the current
phase. A bound exceeded during input, platform selection, instance generation,
source/artifact-directory setup (including the binding/capture-start UTC
sample), capture, candidate
creation, candidate write, candidate verification, pre-publication work, or
postcommit confirmation maps respectively to `INPUT_LIMIT_EXCEEDED`,
`PLATFORM_LIMIT_EXCEEDED`, `INSTANCE_LIMIT_EXCEEDED`,
`ROOT_LIMIT_EXCEEDED`, `CAPTURE_LIMIT_EXCEEDED`,
`CANDIDATE_CREATE_LIMIT_EXCEEDED`, `CANDIDATE_WRITE_LIMIT_EXCEEDED`,
`CANDIDATE_VERIFY_LIMIT_EXCEEDED`, `PUBLISH_LIMIT_EXCEEDED`, or
`POSTCOMMIT_LIMIT_EXCEEDED`. The phase,
commit-state, and nullability table below is authoritative. A successful
publication syscall observed after its deadline has already committed and
therefore maps to `POSTCOMMIT_LIMIT_EXCEEDED/PUBLISHED_UNCONFIRMED`; it can
never be reported as a precommit timeout. An issued Windows rename with no
definite final status follows the separate unknown-outcome rule below. A
kernel call that never returns is an external OS liveness boundary; the
implementation must not claim a hard deadline across that boundary.

### Supported platform and publication profiles

No generic POSIX or pathname-rename fallback exists.

| Profile | Required capabilities | Publication |
|---|---|---|
| `WINDOWS_NTFS_V1` | initial approved tuple: x64 Windows 11 build 26200, local fixed NTFS, CPython 3.13.13; `GetDriveTypeW`, `GetVolumeNameForVolumeMountPointW`, `QueryDosDeviceW`, `NtCreateFile`, `NtSetInformationFile`, `NtWaitForSingleObject`, `FILE_ID_INFO`, and `FlushFileBuffers` | Retain a no-delete-share destination-directory handle. Require source and artifact locators to share the same fixed drive letter and volume-GUID/native-device mapping. Create a random staging regular file relative to that handle with `NtCreateFile`, `CreateDisposition=FILE_CREATE`, and `CreateOptions` including `FILE_SYNCHRONOUS_IO_NONALERT`; reject reparse traversal and require link count one plus a retained read/write/delete/synchronize handle. Write, flush, rewind, independently verify, and record its `FILE_ID_INFO`. Rename that held file only with `NtSetInformationFile(FileRenameInformation=10)`, `ReplaceIfExists=FALSE`, `RootDirectory=held parent`, and one UTF-16 component. Resolve call status and `IO_STATUS_BLOCK.Status` through the frozen table below; only a definite final `STATUS_SUCCESS` is the commit point. Reopen relative to the held parent and require the final FileId to equal the retained source FileId. |
| `LINUX_LOCAL_V1` | initial approved tuple: x86-64 WSL2 Linux `6.6.87.2-microsoft-standard-WSL2`, native ext4, CPython 3.12.3; `statx(STATX_MNT_ID)`, `openat2`, `O_TMPFILE`, `fsync`, procfs mounted at `/proc`, and `linkat` | Retain the destination dirfd. Create an unnamed inode with `openat(O_TMPFILE|O_RDWR|O_CLOEXEC`) without `O_EXCL`. Write, fsync, rewind, independently verify, and record `(statx_mnt_id,st_dev,st_ino)`. Publish create-new with `linkat` from the held inode: `AT_EMPTY_PATH` when authorized, otherwise the documented `/proc/self/fd/<fd>` plus `AT_SYMLINK_FOLLOW` form. The destination is one component relative to the retained dirfd. Success is the commit point. Reopen relative to that dirfd, compare the full identity, then fsync the directory. |

The final component is exactly
`aegis-review-<lowercase-instance-UUID4>.arb1`. Windows staging is exactly
`.aegis-review-staging-<independent-lowercase-UUID4>.tmp`; Linux has no staging
name.

Windows `UserDecisionAttempt.v1` reservation publication is the sole staging
exception. Its staging component is deterministic:
`.aegis-user-decision-attempt-staging-<64 lowercase hex digits from the
attempt content ID>.tmp`. No alternate component is permitted. Recovery probes
the final transition component and this staging component relative to the held
artifact-directory handle before creating either. A pre-existing staging
component must be a protected single-link regular file whose complete
canonical bytes hash to the expected attempt content ID. A matching component,
or a create-new collision followed by that same verification, returns
`ATTEMPT_PUBLICATION_OUTCOME_UNKNOWN/ATTEMPT_STAGING_PRESENT`; it does not
replace, delete, reuse, or republish the staging file and it never calls the
decision publisher. Any other occupant is `ATTEMPT_SLOT_OCCUPIED`. Thus
repeated crash recovery can leave at most one
reservation staging component and, because the decision publisher is called at
most once, at most one decision staging component per intent. Linux uses one
unnamed inode per live call; an unlinked inode does not accumulate after
process exit.

The Windows preflight requires the `ntdll!NtSetInformationFile` export,
`FileRenameInformation==10`, 64-bit
`FILE_RENAME_INFORMATION` size/offsets `24` and `0/8/16/20`, a 16-byte
`IO_STATUS_BLOCK`, and prior R11C real-NTFS conformance evidence that a
retained parent publishes the retained source while a pre-existing target
yields `STATUS_OBJECT_NAME_COLLISION` and remains byte-identical. The
zero-filled
rename buffer size is
`max(sizeof(FILE_RENAME_INFORMATION),
offsetof(FILE_RENAME_INFORMATION,FileName)+FileNameLength)`. This is 24 bytes
for a one- or two-WCHAR name and `20+FileNameLength` thereafter. Byte zero is
`ReplaceIfExists=FALSE`, bytes 1..7 remain zero, `RootDirectory` is the held
parent, and the non-NUL UTF-16LE component begins at offset 20. Neither
`SetFileInformationByHandle`, a null `RootDirectory`, nor a pathname move is a
fallback.

The Windows rename status machine is exact. Before the call,
`IO_STATUS_BLOCK.Status` is the sentinel `0xffffffff` and `Information=0`.
All call, wait, and IOSB values are interpreted as unsigned 32-bit NTSTATUS.
Only the following five exact final values have a non-unknown meaning:

| Final value | Meaning when the publication deadline has not expired |
|---|---|
| `STATUS_SUCCESS (0x00000000)` | commit occurred; continue at `POSTCOMMIT` |
| `STATUS_OBJECT_NAME_COLLISION (0xc0000035)` | `FINAL_NAME_EXISTS/NOT_PUBLISHED` |
| `STATUS_INVALID_INFO_CLASS (0xc0000003)`, `STATUS_INVALID_PARAMETER (0xc000000d)`, `STATUS_NOT_SUPPORTED (0xc00000bb)` | `PUBLICATION_PRIMITIVE_UNSUPPORTED/NOT_PUBLISHED` |

Every other one of the remaining 32-bit values maps to
`WINDOWS_RENAME_OUTCOME_UNKNOWN/PUBLISH/PUBLICATION_OUTCOME_UNKNOWN`,
including nonzero success-severity, informational, warning, unlisted error,
sentinel, and still-pending values. `PUBLICATION_FAILED/NOT_PUBLISHED` is
therefore a Linux definite-error mapping; Windows never infers nonpublication
from an unlisted NTSTATUS.

The call/IOSB resolver is mutually exclusive and exhaustive:

In a consistent observation, `wait_status_u32_or_none` is `None` exactly when the call return is not
`STATUS_PENDING`. A non-pending call paired with any wait value is an
inconsistent observation and returns `PUBLICATION_OUTCOME_UNKNOWN`. A pending
call paired with `None` means no bounded wait result was observed and also
returns `PUBLICATION_OUTCOME_UNKNOWN`, regardless of IOSB or deadline. Only a
pending call paired with one unsigned-32-bit wait value enters the two pending
rows below. These are semantic outcomes, not type-validation errors.

| `NtSetInformationFile` return | `IO_STATUS_BLOCK.Status` / wait | Final classification |
|---|---|---|
| `STATUS_SUCCESS (0x00000000)` | exactly `STATUS_SUCCESS` | commit occurred; continue at `POSTCOMMIT` |
| `STATUS_SUCCESS` | any other value | `WINDOWS_RENAME_OUTCOME_UNKNOWN / PUBLISH / PUBLICATION_OUTCOME_UNKNOWN` |
| `STATUS_PENDING (0x00000103)` | bounded wait returns `STATUS_SUCCESS`; classify every final IOSB, including sentinel/pending, only by the five-value/catch-all table above | final table result |
| `STATUS_PENDING` | wait returns any other 32-bit value; final IOSB is not separately classified | `WINDOWS_RENAME_OUTCOME_UNKNOWN / PUBLISH / PUBLICATION_OUTCOME_UNKNOWN` |
| one of the four listed non-success definite values | IOSB remains sentinel or equals the call return | classify the call return by the table above |
| one of the four listed non-success definite values | IOSB contains any different value | `WINDOWS_RENAME_OUTCOME_UNKNOWN / PUBLISH / PUBLICATION_OUTCOME_UNKNOWN` |
| every other 32-bit call return | IOSB has any value | `WINDOWS_RENAME_OUTCOME_UNKNOWN / PUBLISH / PUBLICATION_OUTCOME_UNKNOWN` |

The pending wait ABI is frozen. Immediately before waiting, compute
`remaining_ns=deadline_monotonic_ns-monotonic_ns()` with Python integers. If it
is zero or negative, do not call wait and return unknown outcome. Otherwise
compute `ticks_100ns=(remaining_ns+99)//100`; require
`1 <= ticks_100ns <= 0x7fffffffffffffff`; encode the signed 64-bit
`LARGE_INTEGER.QuadPart=-ticks_100ns` in native little-endian form; and pass
its non-null pointer to
`NtWaitForSingleObject(held_source,FALSE,&relative_timeout)`. A conversion
bound failure is unknown outcome. A null/infinite or nonnegative timeout is
forbidden. The imported ABI is exactly
`NTSTATUS NTAPI NtWaitForSingleObject(HANDLE,BOOLEAN,PLARGE_INTEGER)`:
pointer-sized `HANDLE`, one-byte unsigned `BOOLEAN` equal to zero, and a
non-null pointer to one native eight-byte signed `LARGE_INTEGER`; no Win32 wait
wrapper or millisecond conversion is permitted.

The resolver samples the monotonic clock immediately after classifying an
immediate call and immediately after a successful wait. A definite success
observed after the deadline is
`POSTCOMMIT_LIMIT_EXCEEDED/PUBLISHED_UNCONFIRMED`; a listed definite
nonpublication status observed after the deadline is
`PUBLISH_LIMIT_EXCEEDED/NOT_PUBLISHED`; an unknown status remains unknown.

Unknown outcome is not a not-published result and is distinct from a known
published object whose postcommit checks failed. The runtime performs no
cleanup, retry, second rename, rollback, or competing failure-record publish;
it retains the source and parent handles until the exact result bytes are
complete, returns both final and staging locators plus the held object
identity, and tells Master to terminate the automated review for operator
inspection. Here `run` is one public facade invocation. Its native adapter
closes all invocation-scope handles exactly once at the facade boundary after
the result is fixed; no handle lease crosses the byte-return API. A named
Windows stage remains in the namespace. Boundary closure does not
retroactively narrow the reported uncertainty or authorize lookup-based
inference.

The staging desired-access set is exactly `FILE_READ_DATA`, `FILE_WRITE_DATA`,
`FILE_READ_ATTRIBUTES`, `FILE_WRITE_ATTRIBUTES`, `DELETE`, and `SYNCHRONIZE`;
share access is exactly `FILE_SHARE_READ`. The parent handle denies delete
sharing. A pre-existing incompatible writer/deleter or later replacement
attempt therefore fails before commit.

`/mnt/c`, DrvFs, network filesystems, FUSE, overlayfs, FAT/exFAT, macOS, other
POSIX systems, unapproved OS/interpreter build tuples, and capability/ABI
mismatches fail closed. An unapproved tuple is `UNRECOGNIZED_PLATFORM`; a
recognized tuple missing a required capability is `UNSUPPORTED_PLATFORM`.
They never fall back to a named source plus
`rename`, `shutil`, recursive copy, or recursive cleanup.

Linux publication uses an exact branch selected before creating the unnamed
inode:

| Condition before publication | Only permitted call | Error mapping |
|---|---|---|
| effective `CAP_DAC_READ_SEARCH` is present | `linkat(held_fd,"",held_dirfd,final_component,AT_EMPTY_PATH)` | `EEXIST -> FINAL_NAME_EXISTS`; `ENOENT`, `EPERM`, `EINVAL`, `EOPNOTSUPP`, or `EXDEV -> PUBLICATION_PRIMITIVE_UNSUPPORTED`; all other errors -> `PUBLICATION_FAILED`; no fallback |
| capability is absent and verified procfs is available | `linkat(AT_FDCWD,"/proc/self/fd/<held_fd>",held_dirfd,final_component,AT_SYMLINK_FOLLOW)` | `EEXIST -> FINAL_NAME_EXISTS`; `ENOENT`, `EPERM`, `EINVAL`, `EOPNOTSUPP`, or `EXDEV -> PUBLICATION_PRIMITIVE_UNSUPPORTED`; all other errors -> `PUBLICATION_FAILED`; no retry through the other branch |
| neither condition holds | no publication syscall | `UNSUPPORTED_PLATFORM` |

The procfs branch requires `/proc` `fstatfs` type `PROC_SUPER_MAGIC`, a
single-threaded descriptor owner, no signal handler that closes descriptors,
and an immediate `fstat` identity match between the held fd and an
`O_PATH|O_CLOEXEC` open that follows only the verified procfs
`/proc/self/fd/<fd>` magic link. `O_TMPFILE` is opened as
`O_TMPFILE|O_RDWR|O_CLOEXEC` without `O_EXCL`, with requested mode `0600`.
Capability selection uses Linux capability ABI v3 and only effective
`CAP_DAC_READ_SEARCH` bit 2. Constants are
`AT_FDCWD=-100`, `AT_SYMLINK_FOLLOW=0x400`, and
`AT_EMPTY_PATH=0x1000`.
Before instance generation, an unnamed-only `O_TMPFILE` probe verifies
creation, mode, identity, and close without creating a namespace entry. A
capability, procfs, unnamed-inode, identity, or mode failure is
`UNSUPPORTED_PLATFORM`. The authoritative creation remains a separate call;
its failure is `CANDIDATE_CREATE_FAILED`. The link call itself is tested only
by the authoritative no-replace publication; an unsupported result is typed
without deleting or replacing any path.

Local confidentiality and mutation resistance are explicit but do not protect
against another process running as the same user. The user-selected artifact
directory is input only. The runtime never changes that existing directory's
owner, mode, ACL, DACL, or name. It creates only the bundle and deterministic
transition components defined by this protocol. It accepts the directory only
if it already satisfies the applicable profile:

- Linux: retained local-ext4 directory handle, owner effective UID, exact mode
  `0700`, and no access/default POSIX ACL xattr;
- Windows: retained local-NTFS non-reparse directory handle, current-user
  owner, DACL protection set, and the exact canonical full-control ACE set for
  only current user and `LOCAL_SYSTEM`.

The Windows directory's exact SDDL is
`O:<current-user-sid>D:P(A;;FA;;;SY)(A;;FA;;;<current-user-sid>)`.
Directory mismatch is `ARTIFACT_DIRECTORY_INVALID/ROOT/NOT_PUBLISHED`;
permission mutation or a fallback directory is forbidden. Linux candidates
are `fchmod(0600)` before publication and verified as owner UID, mode `0600`,
link count zero before publish and one after publish. Windows files receive
the same protected non-inherited descriptor at create-new creation. Every
published file is reopened and rechecked through the retained artifact-
directory handle. Ambient umask, inherited ACLs, default DACLs, or
post-publication permission repair are never accepted as proof.

“Outside the source root” is a handle-bound relation, not a string-prefix
claim. The canonical locators are first rejected when either is the lexical
ancestor of the other. The runtime then requires one conservative shared
storage anchor: on Windows both locators must resolve through the same
fixed drive letter, volume-GUID/native-device mapping, and volume serial; on Linux both
final handles must have the same native-ext4 `statx_mnt_id`. A different
anchor is rejected rather than assumed independent. This deliberately rejects
cross-volume mailboxes and same-filesystem multiple/bind mounts; it closes the
mount-alias ambiguity without trusting mount-table text.

Windows opens and retains the native volume root and every source/artifact
directory component with no reparse traversal and no delete sharing. Linux
retains both final dirfds, then walks each parent chain with bounded
handle-relative `openat2("..", O_PATH|O_DIRECTORY|O_CLOEXEC)` plus
`RESOLVE_NO_MAGICLINKS|RESOLVE_NO_SYMLINKS`, querying full identity at each
step. A same-identity parent is the namespace-root terminator. A parent with a
different `statx_mnt_id` proves that the current object is the selected mount
root and is not added to the in-anchor chain. Any other parent is appended and
the walk continues. Every opened object remains held until the relationship
decision. Each in-anchor chain, including its final directory and mount root,
is limited to 256 directories. The source final identity must not occur in the
artifact ancestor chain and the artifact final identity must not occur in the
source ancestor chain. Windows applies the same comparison to the retained
volume-root traversal chains. Equal final identities, an ancestor hit,
reparse/link observation, storage-anchor mismatch, incomplete walk, or
component-limit overflow is
`ARTIFACT_DIRECTORY_INVALID/ROOT/NOT_PUBLISHED`; deadline or monotonic failure
is `ROOT_LIMIT_EXCEEDED`.

Here “repository path” means the current source-root object and its namespace
descendants; Recorder does not inspect Git metadata or claim to identify every
unrelated repository on the machine. The relationship proof is a bounded
point observation. Linux same-user namespace mutation after the held walk is
outside the continuous-identity claim; every later artifact operation still
uses/rechecks its binding as specified.

Linux source reads use `openat2` relative to the retained source-root dirfd with
`RESOLVE_BENEATH|RESOLVE_NO_MAGICLINKS|RESOLVE_NO_SYMLINKS|RESOLVE_NO_XDEV`.
After the parent chain is retained, Linux classifies each leaf with
`statx(parent_fd,component,AT_SYMLINK_NOFOLLOW|AT_NO_AUTOMOUNT,
STATX_TYPE|STATX_MODE|STATX_INO|STATX_NLINK|STATX_SIZE|STATX_MNT_ID|
STATX_CTIME)`. This
probe opens no body stream and cannot block on a FIFO. A required-file leaf
classified as a regular file is then opened with
`O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK`; the retained handle must reproduce
the probed identity and supported kind or the source is changed. Windows
classifies each leaf relative to the retained parent with a probe-local
metadata handle opened by `NtCreateFile` using `OBJ_DONT_REPARSE`,
`FILE_OPEN_REPARSE_POINT`, `FILE_READ_ATTRIBUTES|SYNCHRONIZE`, and no data
access. It queries identity, directory/regular type, reparse state,
`EndOfFile`, and `ChangeTime`, then closes only that probe-local handle. A
regular required file is reopened with
the fixed-volume, read, and share modes that deny write/delete replacement
while captured; the retained handle must reproduce the probe identity and
supported kind. For either profile, a declared absence accepts only `ABSENT`;
every `PRESENT` kind maps to `REQUIRED_ABSENCE_PRESENT`. A required file maps
initial `ABSENT` to `REQUIRED_FILE_MISSING`, initial `DIRECTORY` or
`UNSUPPORTED_OBJECT` to `UNSUPPORTED_FILE_TYPE`, and only initial
`REGULAR_FILE` proceeds to retained open. After that regular probe, a missing
open, different identity, or different supported/unsupported kind maps to
`SOURCE_CHANGED`. A retained regular file whose link count is not one maps to
`UNSUPPORTED_FILE_TYPE`. A pure probe/open/query I/O failure maps to
`SOURCE_IO_FAILED`. Both profiles compare pre/post identity, type, link count,
size, and change token. Captured bytes are authoritative;
this is not a claim that multiple source files existed simultaneously as one
filesystem snapshot.

The platform adapters convert change observations to one opaque
`SHA256_ID`. Exact `NativeChangeObservation.v1` is either
`{ctime_nanoseconds=<JSON integer 0..999999999>,
ctime_seconds=I64_DECIMAL,identity=LinuxRootOrFileIdentity,
platform="linux",schema="NativeChangeObservation.v1"}` or
`{change_time_100ns=I64_DECIMAL,identity=WindowsRootOrFileIdentity,
platform="windows",schema="NativeChangeObservation.v1"}`. The token is
SHA-256 over `"AEGIS_NATIVE_CHANGE_TOKEN_V1\0"` plus its exact canonical
bytes. The initial no-follow probe,
retained-handle pre-read query, and retained-handle post-read query must all
produce the same token. A regular file's observed size must also equal the
captured byte count. Unsupported objects still carry a probe change token but
no size; absent leaves carry neither. An unavailable size/change query is
`SOURCE_IO_FAILED`, never a silently omitted comparison.

### Writer, verifier, and dependency direction

The writer streams file bodies and never keeps one complete body in memory.
After sealing the manifest and trailer, it rewinds a duplicated handle and
invokes the independent verifier on the same file object. The writer compares
its incremental IDs with the independent parser's observed IDs. Publication is
allowed only after those two calculations agree. This produces a
non-authoritative candidate; an externally expected ID cannot exist before a
new UUID/time-bearing candidate is built.

The independent verifier:

- does not import writer, model, capture, platform, or observation modules;
- implements its own byte parser and restricted canonical serializer;
- exposes `inspect_candidate_handle`, which returns observed IDs without an
  integrity or authorization claim, and `verify_dispatched_handle`, which
  additionally requires every external dispatch expectation;
- streams file bodies and retains at most the manifest, record metadata, and
  one 65,536-byte chunk;
- supplies separate golden vectors, mutation vectors, and content-ID
  calculations;
- is not the final reviewer. The final reviewer also recomputes the bundle ID
  through a fresh script or equivalent independent path and checks the
  dispatch allowlist for completeness.

The reviewer reads normative bytes only from its independently parsed
container stream or from create-new extracted copies whose hashes it recomputes
against the frames. Repository pathnames and a convenience unpack directory
are non-authoritative navigation. START/END live capture detects source-domain
drift; it does not change which bytes the reviewer reviewed.
Neither the transport nor the final reviewer imports or executes Python,
hooks, tests, binaries, or commands supplied inside the bundle during plan
review.

After candidate publication, Master receives the observed IDs and exact
manifest values plus the validated artifact-directory binding/ID, constructs
the dispatch observation, and delivers those values to the reviewer. This
handoff cannot authenticate Master or prove that
the generator chose a complete domain. Its value is narrower: the reviewer
cannot be silently moved to different bytes after dispatch, and must
independently judge domain completeness before issuing advice.

Allowed dependency direction is:

```text
platform I/O -> no model/parser dependency
domain capture -> platform I/O + immutable value records
bundle writer -> captured value records
independent verifier -> stdlib only
bootstrap observation -> independent verifier + fresh domain capture
production api -> native ports + shared orchestration core
conformance worker -> model ports + the same shared orchestration core
shared orchestration core -> immutable port contracts; no api/conformance import
```

The container never calls Git. Inventory never publishes. Platform I/O never
parses a manifest. Observation code never constructs a verifier success.
At both START and END it first verifies the published bundle against every
dispatch expectation, then opens the source root anew, derives its root
identity, recaptures the exact dispatch file/absence set, revalidates the READY
control, and recomputes the live `review_domain_id`. A bundle-only recheck is
insufficient. Any root, file, identity, absence, control, or domain mismatch
constructs a rejected observation. Master must persist it before constructing
`INVALID_REVIEW`; if the bound artifact directory cannot accept that
create-new transition, the typed persistence result is the terminal evidence
and no persisted-failure claim is made. These remain two point observations,
not continuous monitoring.

### Frozen production facade

Production-behavior R11A tests bind only
`evaluation.aegis_v2.review_transport.api_v1`. They do not import an
implementation module, private class, dataclass, enum, canonicalizer, or
platform wrapper. The facade exports exactly the following exception classes:

```python
class ReviewTransportError(Exception): ...
class ReviewTransportValidationError(ReviewTransportError): ...
class ReviewTransportOperationError(ReviewTransportError): ...
```

Exception text and attributes are not contract. A direct pure/parser boundary
rejects malformed, noncanonical, inconsistent, out-of-bound, or wrong-type
caller input only with `ReviewTransportValidationError`. A direct handle
boundary reports an expected read/seek fault only with
`ReviewTransportOperationError`. Leaking a raw `OSError`, `KeyError`,
`UnicodeError`, decoder exception, or private exception for a controlled case
is a conformance failure. Each stateful facade below has its own closed
pre-write/result mapping; no general exception fallback exists.

Facade signatures are keyword-only and frozen:

```python
def validate_record_bytes(
    *,
    expected_schema: str,
    record_bytes: bytes,
) -> bytes: ...

def assemble_review_domain(
    *,
    capture_facts_bytes: bytes,
    request_bytes: bytes,
) -> tuple[str, bytes]: ...

def build_and_publish_candidate(
    *,
    source_root_locator: bytes,
    artifact_directory_locator: bytes,
    request_bytes: bytes,
) -> bytes: ...

def extract_artifact_directory_binding(
    *,
    bundle_publication_result_bytes: bytes,
) -> tuple[str, bytes]: ...

def inspect_candidate_handle(
    *,
    candidate_handle: BinaryIO,
) -> tuple[str, str, bytes]: ...

def verify_dispatched_handle(
    *,
    candidate_handle: BinaryIO,
    dispatch_bytes: bytes,
) -> tuple[str, str, bytes]: ...

def publish_transition_record(
    *,
    artifact_directory_binding_bytes: bytes,
    canonical_record_bytes: bytes,
) -> bytes: ...

def parse_reviewer_advisory(
    *,
    master_observed_text: str,
) -> bytes: ...

def capture_review_observation(
    *,
    source_root_locator: bytes,
    artifact_directory_binding_bytes: bytes,
    dispatch_bytes: bytes,
    phase: Literal["START", "END"],
    prior_observation_bytes: bytes | None,
    invocation_outcome_bytes: bytes | None,
) -> bytes: ...

def construct_review_handoff(
    *,
    artifact_directory_binding_bytes: bytes,
    dispatch_bytes: bytes,
    start_observation_bytes: bytes,
    invocation_attempt_bytes: bytes,
    invocation_outcome_bytes: bytes,
    end_observation_bytes: bytes,
) -> bytes: ...

def resume_user_decision(
    *,
    artifact_directory_binding_bytes: bytes,
    envelope_bytes: bytes,
) -> bytes: ...

def resolve_windows_rename_outcome(
    *,
    call_status_u32: int,
    iosb_status_u32: int,
    wait_status_u32_or_none: int | None,
    deadline_expired: bool,
) -> str: ...

def encode_windows_relative_timeout(
    *,
    remaining_ns: int,
) -> bytes | None: ...

def classify_linux_linkat_result(
    *,
    errno_or_zero: int,
    selected_branch: Literal[
        "AT_EMPTY_PATH",
        "PROC_SELF_FD",
        "NO_SUPPORTED_BRANCH",
    ],
    deadline_expired: bool,
) -> str: ...
```

`validate_record_bytes` accepts only this closed schema-name set:

```text
AegisReviewControl.v1
CandidateDomainRequest.v1
CapturedReviewDomainFacts.v1
ArtifactDirectoryBinding.v1
AegisReviewDomain.v1
AegisReviewBundle.v1
ReviewDispatchObservation.v1
BootstrapReviewObservation.v1
ParsedReviewerAdvisory.v1
ReviewerInvocationAttempt.v1
ReviewerInvocationOutcome.v1
BootstrapPlanReviewHandoff.v1
UserDecisionIntent.v1
UserDecisionAttempt.v1
UserDecisionObservation.v1
BootstrapReviewFailure.v1
UserDecisionPriorOutcome.v1
UserDecisionResumeEnvelope.v1
BundlePublicationResult.v1
TransitionPublicationResult.v1
UserDecisionResumeResult.v1
```

It returns the exact input bytes on success; it never recanonicalizes accepted
bytes. `assemble_review_domain` accepts exact
`CapturedReviewDomainFacts.v1` and `CandidateDomainRequest.v1` bytes, checks
their complete relationship, and returns
`(review_domain_id, canonical_AegisReviewDomain_v1_bytes)`. Neither call makes
an I/O or authority claim.

`extract_artifact_directory_binding` accepts only an exact validated
`OK/PUBLISHED_CONFIRMED` builder result whose nested binding bytes and binding
content ID agree. It returns `(binding_id, canonical_binding_bytes)`.
Every other result row or mutation raises
`ReviewTransportValidationError`; it performs no I/O.

The two candidate-handle calls accept only an already-open, seekable binary
object that provides `tell()`, `seek()`, and `readinto()` with ordinary Python
binary-I/O semantics. Their tuple is
`(content_id, review_domain_id, canonical_manifest_bytes)`. Their position
state machine is exact:

1. call `tell()` once before any other handle operation. Its return must have
   exact Python type `int`, not `bool`, and be in `0..9223372036854775807`.
   Failure or any other return raises `ReviewTransportOperationError`; the
   original position is unknown and no restore is attempted;
2. call `seek(0, SEEK_SET)`. Success requires exact Python type `int`, not
   `bool`, and value zero. If it raises or returns any other value, attempt exactly one
   `seek(original_position, SEEK_SET)` because a failing seek may have changed
   state. Then raise `ReviewTransportOperationError`;
3. retain the primary parse outcome: success tuple,
   `ReviewTransportValidationError`, or
   `ReviewTransportOperationError`;
4. every `readinto(buffer)` return must have exact type `int`, not `bool`, and
   be in `0..len(buffer)`. Zero is EOF; positive progress contributes exactly
   the first returned-count bytes and the next call receives a fresh
   65,536-byte buffer. A negative, over-buffer, non-int, or mutation outside
   the returned prefix is `ReviewTransportOperationError`;
5. after every attempted read/parse path, attempt exactly one
   `seek(original_position, SEEK_SET)`. Restore success requires exact type
   `int`, not `bool`, and exact value `original_position`;
6. if that restore succeeds, deliver the retained primary outcome. If it
   fails, `ReviewTransportOperationError` dominates every primary outcome, the
   final position is explicitly unknown, and no success or validation result
   is delivered.

The object is never closed. A wrong `readinto` return, short-progress loop,
read exception, or invalid seek/tell behavior is an operation error. Tests
cover initial tell failure, initial seek failure with successful and failed
restore, read failure with successful restore, parse failure with successful
restore, successful parse with failed restore, and primary-plus-restore
failure.
`inspect_candidate_handle` claims only what it parsed.
`verify_dispatched_handle` additionally checks every dispatch expectation.
Neither returns a success boolean or authority field.

The builder's two native locator arguments are not path-like objects or JSON.
On Windows they are the exact absolute UTF-16LE pathname bytes without a
trailing NUL; on Linux they are the exact absolute POSIX pathname bytes. NUL,
relative, over-bound, wrong-platform, `str`, `Path`, and implicit cwd inputs
are rejected. The lexical grammar is closed:

- POSIX is 1..4,095 bytes, begins with `/`, has no empty interior, `.` or `..`
  component, and has no trailing `/` except the one-byte root;
- Windows is 3..4,096 well-formed UTF-16 code units, begins with one uppercase
  ASCII drive and `:\`, uses only `\` separators, has no empty interior, `.`
  or `..` component, and has no trailing separator except the three-unit drive
  root. UNC, device, extended, drive-relative, slash-separated, and
  normalization-dependent spellings are invalid. Every component also obeys
  the frozen Windows component grammar.

Neither source root nor artifact directory may be a filesystem/drive root.
Artifact-directory input additionally leaves room for one separator plus the
longest frozen child component (105 ASCII units): at most 3,989 POSIX bytes or
3,990 Windows UTF-16 code units. Joining is byte/code-unit concatenation of the
exact bound locator, one native separator, and one validated component. No
normalization, case conversion, ambient cwd, or alternate spelling occurs.
These rules make every final/staging locator fit the `NativeLocator` bound; a
violation is `INVALID_PATH` before platform I/O.
The locators are used only for the initial retained-handle acquisition
described above. Later calls accept the exact binding bytes, obtain their
locator from that canonical value, and reject a current identity/profile/
permission mismatch before mutation. Returned locators remain canonical
`NativeLocator` JSON objects inside result records.
Immediately before the commit primitive, the runtime both rechecks the
retained directory handle and independently reopens the binding locator. Both
objects must match the binding's profile, identity, protection, and
storage-anchor snapshot.
A mismatch issues no link/rename. It is definite `NOT_PUBLISHED`; an already
created Windows staging file remains quarantined in the originally retained
directory, while a Linux unnamed inode is closed without a link. The newly
resolved replacement directory is never mutated. After a commit and
object-relative reopen, the runtime independently reopens the binding locator
again and compares the same facts. A postcommit mismatch is
`PUBLISHED_UNCONFIRMED`, preserves the published object, and performs no
rollback.

The immediate precommit check maps open, identity, storage-anchor, protection,
and profile failure respectively to
`ARTIFACT_DIRECTORY_PREPUBLISH_OPEN_FAILED`,
`ARTIFACT_DIRECTORY_PREPUBLISH_IDENTITY_MISMATCH`,
`ARTIFACT_DIRECTORY_PREPUBLISH_STORAGE_ANCHOR_MISMATCH`,
`ARTIFACT_DIRECTORY_PREPUBLISH_PROTECTION_MISMATCH`, or
`ARTIFACT_DIRECTORY_PREPUBLISH_PROFILE_UNSUPPORTED` in the PUBLISH row.
Postcommit open or any equality failure maps
`ARTIFACT_DIRECTORY_POSTCOMMIT_UNCONFIRMED`. The same reason tokens are legal
in bundle and transition result schemas. Entry-time failures alone use the
ROOT/DIRECTORY reasons. Builder artifact-directory open, wrong type,
filesystem, owner, protection, link/reparse, or identity mismatch maps to
`ARTIFACT_DIRECTORY_INVALID/ROOT`; `ROOT_OPEN_FAILED` is reserved for the
source-root open. For transition publication, entry open failure maps
`ARTIFACT_DIRECTORY_OPEN_FAILED`; object-identity inequality maps
`ARTIFACT_DIRECTORY_IDENTITY_MISMATCH`; wrong type/filesystem/owner/protection
or storage-anchor/link/reparse state maps `ARTIFACT_DIRECTORY_INVALID`; a recognized profile
unavailable on this host maps `ARTIFACT_DIRECTORY_PROFILE_UNSUPPORTED`; and a
deadline or monotonic-source failure maps
`ARTIFACT_DIRECTORY_LIMIT_EXCEEDED`. The categories are disjoint and the first
check reached wins.

`build_and_publish_candidate` represents every controlled caller-input and
runtime outcome in exact canonical `BundlePublicationResult.v1` bytes.
`publish_transition_record` first requires canonical binding and record bytes
whose binding IDs agree and whose binding has
`evidence_origin=NATIVE_RUNTIME`. It recursively validates every nested
`TransitionPublicationResult.v1` in the record and requires its binding ID and
`evidence_origin` to equal that same input binding. A mixed-origin
`BootstrapReviewFailure.v1` is invalid even when all hashes and reason/state
fields are otherwise well formed. A violation raises
`ReviewTransportValidationError` before namespace access; after that proof,
every directory, I/O, timing, collision, unsupported-platform, and
commit-uncertainty outcome is exact
`TransitionPublicationResult.v1` bytes. `NONCANONICAL_RECORD` is therefore a
post-write independent-reparse mismatch, not malformed caller input.
`resume_user_decision` similarly raises
`ReviewTransportValidationError` only for malformed/noncanonical binding bytes
or a binding whose evidence origin is not `NATIVE_RUNTIME`; that bounded
65,536-byte precondition is checked before the recovery timer.
With a valid binding, even an invalid envelope returns exact
`UserDecisionResumeResult.v1` bytes. Every nested transition result in an
envelope, prior outcome, or recovered failure must match the binding ID and
origin before the first write; a mismatch is
`INVALID_CHAIN/REQUEST_INVALID` with all six content/result fields null. No
mutable Python result object is public.
Every stateful production result schema that contains `evidence_origin` emits
only `NATIVE_RUNTIME`; observation/handoff records instead bind an exact
native-origin artifact-directory binding ID. Every stateful production facade
rejects a `SYNTHETIC_CONFORMANCE` binding before namespace I/O. The
conformance facade emits only synthetic-origin result schemas, requires every
stateful input binding/result to carry that same origin, and cannot mint a
native-origin value. Pure parsing/validation may inspect either origin but
never upgrades or rewrites it.

`parse_reviewer_advisory` returns exact
`ParsedReviewerAdvisory.v1` bytes. `capture_review_observation` returns exact
`BootstrapReviewObservation.v1` bytes. START requires
`prior_observation_bytes=null` and `invocation_outcome_bytes=null`. END
requires the exact canonical START bytes and exact canonical
`ReviewerInvocationOutcome.v1` bytes. Both phases receive the exact dispatch
bytes; no call rediscovers a
dispatch or predecessor by scanning the artifact directory.
`construct_review_handoff` receives and independently revalidates the exact
dispatch, START, invocation-attempt, invocation-outcome, and END bytes, then
returns exact
`BootstrapPlanReviewHandoff.v1` bytes. Passing predecessor content IDs alone
is deliberately insufficient because deterministic successor names do not
provide a reverse lookup from a record's own content ID.

Observation construction has one closed priority table:

| First observed condition | Public outcome | Master mapping |
|---|---|---|
| Wrong Python type, malformed/noncanonical/over-bound source-root locator, non-native-origin binding, malformed binding/dispatch/prior observation/phase/invocation outcome, or invalid relationship | `ReviewTransportValidationError`; zero namespace I/O | `START_OBSERVATION_CONSTRUCTION_FAILED` or `END_OBSERVATION_CONSTRUCTION_FAILED` |
| Deadline observed before the construction basis is complete; UUID/UTC generation failure; output canonicalization failure | `ReviewTransportOperationError`; zero later namespace I/O | same construction-failed reason |
| Valid construction basis, then recognized binding profile is unavailable on this host | canonical observation with `result=UNSUPPORTED`, `observation_reason_code=UNSUPPORTED_PLATFORM`; unavailable observed fields null | persist the observation, then `START_OBSERVATION_REJECTED` or `END_OBSERVATION_REJECTED` |
| Valid construction basis, then current artifact binding/open/identity/protection/storage-anchor or source/artifact-relation failure, bundle/source missing or invalid, read/query failure, capture limit, or deadline | canonical observation with `result=INVALID` and the unique closed reason below; every unavailable observed field null and already completed observations retained | persist the observation, then the matching rejected reason |
| Bundle, root, and live domain are all fully observed before the deadline, but at least one expected value differs | canonical observation with `result=MISMATCH`, `observation_reason_code=OBSERVED_VALUE_MISMATCH`; every observed field non-null | persist the observation, then the matching rejected reason |
| Every observation is fully available and equal before the deadline | canonical observation with `result=MATCH`, `observation_reason_code=OK` | continuation permitted only after confirmed persistence |

The construction basis is complete only after the facade, in this fixed order,
has validated the binding/content ID and required `NATIVE_RUNTIME` origin;
dispatch; source-root locator syntax,
bound, platform encoding, and relationship to the binding profile; phase and
exact START predecessor rule; and the phase-specific reviewer fields, then
generated the observation UUID and UTC. A syntactically valid locator whose
real object cannot be opened or satisfy the required root/profile constraints
is the later canonical `SOURCE_ROOT_MISSING_OR_INVALID` observation; malformed
caller bytes are the pre-I/O validation error. The monotonic deadline is
checked before the first validation and after each listed step. Therefore the
first check or validation actually reached wins: an already-observed timeout
is not overwritten by a later malformed field, and an already-observed
malformed field is not relabelled by a later clock advance. After the basis
exists, environment work is ordered artifact-directory reopen/binding proof,
bundle reopen/dispatch verification, source-root reopen, repeated
source/artifact relation proof, required-file capture, required-absence
capture, READY validation, and live-domain calculation. The first failed step
stops later I/O and fixes the row above. A failure while serializing that
negative observation is an operation error and produces no partial record.
Immediately after source-root reopen and before any required-file read, the
facade repeats the same shared-anchor and retained-ancestor proof against the
current bound artifact handle. Relation/anchor failure uses
`ARTIFACT_DIRECTORY_INVALID`; deadline or monotonic failure uses
`OBSERVATION_LIMIT_EXCEEDED`.

`ObservationReasonCode` is closed:

```text
OK
OBSERVED_VALUE_MISMATCH
UNSUPPORTED_PLATFORM
ARTIFACT_DIRECTORY_INVALID
ARTIFACT_DIRECTORY_IDENTITY_MISMATCH
ARTIFACT_DIRECTORY_PROTECTION_MISMATCH
BUNDLE_MISSING_OR_INVALID
SOURCE_ROOT_MISSING_OR_INVALID
LIVE_DOMAIN_INVALID
OBSERVATION_IO_FAILED
OBSERVATION_LIMIT_EXCEEDED
```

The first failing environmental operation selects the corresponding reason.
A missing/wrong-type artifact directory uses `ARTIFACT_DIRECTORY_INVALID`;
identity inequality uses `ARTIFACT_DIRECTORY_IDENTITY_MISMATCH`; owner,
mode/DACL/ACL inequality uses `ARTIFACT_DIRECTORY_PROTECTION_MISMATCH`. A
storage-anchor or source/artifact relation inequality uses
`ARTIFACT_DIRECTORY_INVALID`. A missing/invalid bundle uses
`BUNDLE_MISSING_OR_INVALID`; source-root
open/type/profile failure uses `SOURCE_ROOT_MISSING_OR_INVALID`; required-file,
required-absence, READY, or captured-domain invalidity uses
`LIVE_DOMAIN_INVALID`; an expected read/query failure uses
`OBSERVATION_IO_FAILED`; a deadline or monotonic-source failure uses
`OBSERVATION_LIMIT_EXCEEDED`. These reasons are observations, not authority.

Handoff construction has no negative handoff record:

| First observed condition | Public outcome | Master mapping |
|---|---|---|
| Malformed/noncanonical/over-bound or non-native-origin binding, dispatch, START, invocation attempt/outcome, or END; binding-ID/request mismatch; non-MATCH observation; pair/replay/order/advisory inconsistency | `ReviewTransportValidationError`; zero namespace write | `HANDOFF_INVALID` |
| Deadline, current directory open/profile/identity/permission/storage-anchor failure, query failure, UUID generation failure, or output canonicalization failure after valid inputs | `ReviewTransportOperationError`; zero namespace write | `HANDOFF_INVALID` |
| Exact chain, advisory, binding, and current directory proof | canonical `BootstrapPlanReviewHandoff.v1` bytes | publish separately; a later nonconfirmed result maps to `HANDOFF_PERSISTENCE_FAILED` |

Its fixed order is deadline check, binding parse, dispatch parse, START parse,
invocation-attempt parse, invocation-outcome parse, END parse,
pair/request/advisory/binding relationships, current directory reopen and
profile/identity/permission/storage-anchor proof, handoff UUID generation, and canonical
serialization, with deadline checks before and after each operation. The first
observed failure wins and later operations are not attempted. Neither
construction function publishes, deletes, repairs, or scans a directory.

The two publication classifiers return one exact token:

```text
COMMITTED
COMMITTED_AFTER_DEADLINE
FINAL_NAME_EXISTS
PUBLICATION_PRIMITIVE_UNSUPPORTED
DEFINITE_PUBLICATION_FAILURE
PRECOMMIT_LIMIT_EXCEEDED
PUBLICATION_OUTCOME_UNKNOWN
UNSUPPORTED_PLATFORM
```

Only tokens reachable under the applicable platform table are legal.
`NO_SUPPORTED_BRANCH` returns `UNSUPPORTED_PLATFORM` without a syscall.
A zero `errno_or_zero` means Linux link success. A definite Linux
nonpublication observed after expiry returns
`PRECOMMIT_LIMIT_EXCEEDED`; success observed after expiry returns
`COMMITTED_AFTER_DEADLINE`. Windows returns
`PUBLICATION_OUTCOME_UNKNOWN` for every unresolved combination, including an
expired pending wait that was not issued. Status inputs require
`type(value) is int` and `0 <= value <= 0xffffffff`; Linux errno requires
`type(value) is int` and `0 <= value <= 0x7fffffff`;
`NO_SUPPORTED_BRANCH` additionally requires errno zero. Deadline inputs
require `type(value) is bool`. Any violation raises
`ReviewTransportValidationError`.

`encode_windows_relative_timeout` returns the exact native little-endian
eight-byte signed `LARGE_INTEGER`. `type(remaining_ns) is int` is mandatory;
bool or any other type raises `ReviewTransportValidationError`. It returns
`None` when `remaining_ns <= 0` or
`remaining_ns > 922337203685477580700`, before addition or multiplication.
Otherwise it applies the ceiling conversion, whose tick count is then exactly
1..`0x7fffffffffffffff`. It never returns a zero,
positive, null-pointer, or millisecond timeout.

This facade is a compatibility boundary, not an authorization API. Adding a
public function, changing one signature/return shape, or making tests depend
on a private symbol requires a plan revision and independent rereview.

### Frozen synthetic conformance facade

Unreachable native statuses, short I/O, post-effect crashes, and concurrency
cannot be tested deterministically through real black-box OS calls. Production
`api_v1` therefore receives no fault, clock, backend, hook, scheduler, or port
parameter. A separate, data-only facade is frozen at
`evaluation.aegis_v2.review_transport_conformance.api_v1`:

```python
class ReviewTransportConformanceError(Exception): ...
class ReviewTransportConformanceValidationError(
    ReviewTransportConformanceError
): ...

def run_conformance_script(
    *,
    script_bytes: bytes,
) -> bytes: ...
```

Tests import no other conformance module. Script validation failure raises only
`ReviewTransportConformanceValidationError`; exception text is not contract.
A valid script returns exact canonical
`ReviewTransportConformanceEventLog.v1` bytes. Neither conformance schema is a
production record, is accepted by production `validate_record_bytes`, or may
occupy an artifact transition slot.

`ReviewTransportConformanceScript.v1` has exactly:

```text
actors=<actor array>
blobs=<blob array>
case_id=TOKEN
controls=<control array>
create_objects=<create-object array>
initial_namespace=ConformanceNamespaceSnapshot.v1
namespace_mutations=<namespace-mutation array>
profile="WINDOWS_NTFS_V1" | "LINUX_LOCAL_V1"
publication_branch="WINDOWS_NT_RENAME" | "AT_EMPTY_PATH"
                   | "PROC_SELF_FD" | "NO_SUPPORTED_BRANCH"
request_declarations=<request-declaration array>
schedule=<schedule array>
schema="ReviewTransportConformanceScript.v1"
sources=<deterministic-source array>
```

The branch relation is iff: Windows requires `WINDOWS_NT_RENAME`; Linux
requires one of the other three. It is a synthetic, hashed preflight fact, not
a host capability probe. `NO_SUPPORTED_BRANCH` makes the shared core return
the closed unsupported-platform result without issuing a publication atom.

The script is 1..8,388,608 canonical ASCII JSON bytes. Its conformance-only
`PY_KWARG` grammar is `[a-z][a-z0-9_]{0,63}`. All byte/text values are
lowercase even-length hex; decoded text must be strict UTF-8 Unicode scalar
text. No callable, import/module/class name, pickle, environment/argv
reference, real path lookup, loop, condition, wildcard selector, or executable
expression is legal.
`script_content_id` is `sha256:` plus lowercase SHA-256 over
`"AEGIS_REVIEW_TRANSPORT_CONFORMANCE_SCRIPT_V1\0"` followed by the exact
script bytes. Blob content IDs are raw SHA-256 over decoded blob bytes; the two
domains are never interchangeable.

Each `sources` item has exact keys `selector,value_kind,value`. The selector is
the exact `ConformanceSelector.v1` defined below and its operation is
`MONOTONIC_READ`, `UTC_READ`, or `UUID4_READ`; `value_kind` and `value` are
respectively `U64_DECIMAL`, `UTC`, or `UUID4` and must match that operation.
There are 0..12,288 items, strictly ordered by the canonical selector bytes,
with unique `(actor_id,operation,purpose,ordinal)`. A source call consumes only
its keyed item, never a global FIFO. Missing, duplicate-hit, or leftover source
items produce `TRACE_MISMATCH`. A non-`DEFAULT` control for a source operation
forbids a source item at the same selector, so an injected failure cannot leave
an ambiguous unused value.

Each `blobs` item has exact keys `bytes_hex,content_id`; there are 0..256
items, decoded bytes per item are 0..2,097,152, total decoded bytes are at most
4,194,304, IDs are unique, every ID is independently recomputed, and the array
is strictly content-ID ordered.

`ConformanceRequestDeclaration.v1` has exactly
`actor_id,arguments,operation,ordinal,purpose,schema`, with
`schema="ConformanceRequestDeclaration.v1"`. The other fields have the exact
grammar and per-operation argument shape of the port table below. Its content
ID is SHA-256 over
`"AEGIS_CONFORMANCE_REQUEST_DECLARATION_V1\0"` plus its canonical bytes.
The script has 0..12,288 declarations, strictly ordered by
`(actor_id,operation,purpose,numeric ordinal)`, with no duplicate tuple or
content ID.

Every worker-originated port request, lifecycle request, and recovery-result
echo that can be reached under the script has exactly one declaration. Values
derived from declared sources, blobs, templates, prior requests, or facade
arguments must already be resolved in that declaration. This includes handle
IDs, byte counts, components, dispositions, record IDs, and slot locators.
Declarations are validated with the complete script before an actor starts.
At runtime the worker sends the computed declaration content ID with the
request; the coordinator requires every field and framed byte to match the
declared value before logging or effect. Missing, extra, duplicate-hit,
unreachable, or leftover declarations produce `TRACE_MISMATCH`. Thus a
control cannot become legal only after observing an argument-dependent
request.

`ConformanceNamespaceSnapshot.v1` has exactly
`names,objects,schema="ConformanceNamespaceSnapshot.v1"`. Each object has exact
keys:

```text
blob_content_id=SHA256_ID | null
change_token=SHA256_ID
flush_state="FLUSHED" | "DIRTY"
identity=RootOrFileIdentity
kind="DIRECTORY" | "REGULAR_FILE" | "UNSUPPORTED_OBJECT"
link_count=U64_DECIMAL | null
object_key=TOKEN
protection=ArtifactDirectoryProtection | PublishedFileProtection | null
size_bytes=U64_DECIMAL | null
storage_anchor=DirectoryStorageAnchor | null
unsupported_kind=null | "SYMLINK" | "REPARSE_POINT" | "FIFO" | "SOCKET"
                 | "BLOCK_DEVICE" | "CHARACTER_DEVICE" | "OTHER"
```

Objects are strictly ordered by `object_key`, which is unique. Full
`RootOrFileIdentity` values are also unique across distinct objects; multiple
hard-link names select one object instead of duplicating its identity.
Directories require null blob/link count/size, an
`ArtifactDirectoryProtection`, a non-null storage anchor matching their
identity/profile, and null `unsupported_kind`. Regular files require a blob, a
link count, null storage anchor, `PublishedFileProtection`, a size equal to the
decoded blob byte length, and null `unsupported_kind`: the Linux shape is exactly
`{access_acl_present=false,mode_octal="0600",owner_uid=U64_DECIMAL,
platform="linux"}`; the Windows shape is the exact protected owner/SYSTEM SDDL
shape already defined for the artifact directory, with
`platform="windows"`. An unsupported object requires null blob/size, null
protection, null storage anchor, non-null link count,
`flush_state="FLUSHED"`, and one non-null `unsupported_kind`. `SYMLINK`,
`FIFO`, `SOCKET`, `BLOCK_DEVICE`, and `CHARACTER_DEVICE` are Linux-only;
`REPARSE_POINT` is Windows-only; `OTHER` is legal on either profile. Each name
has exact keys
`component,kind,locator,object_key,parent_object_key`. For `kind="ROOT"`,
`locator=NativeLocator`, component/parent are null, and the object is a
directory. For `kind="CHILD"`, locator is null,
`component=NativeComponent`, parent selects a declared directory, and the
selected child may be a directory, regular file, or unsupported object. A
directory may have both an addressable ROOT locator and one CHILD relation;
ROOT means “openable by this absolute model locator,” not “has no namespace
parent.” Root locators and
`(parent_object_key,canonical component)` pairs are independently unique.
Names are strictly ordered by their complete canonical bytes and every key
selects one declared object. Directory-child relations are acyclic and every
directory has at most one CHILD parent. A directory with no CHILD parent is a
model namespace root; parent-open on it returns the same object. Every
non-directory object's link count equals its CHILD-name count. The snapshot
has 0..2048 objects and 0..2048 names.
Every CHILD relation is storage-bound to its parent. A directory child has
exactly the same `DirectoryStorageAnchor` as its parent. Every non-directory
child has the same platform and its Linux `statx_mnt_id` or Windows
`volume_serial_number` equals the parent anchor. If one non-directory object
has multiple CHILD names, every parent has the same exact anchor. Every Windows
ROOT locator's drive letter equals the selected directory anchor's
`drive_letter`. These are bidirectional snapshot-validity rules, not facts
inferred by a host path library.
Every initial object is reachable from a ROOT locator. A runtime-created
unlinked live Linux inode is one object with no name and link count zero.
An empty snapshot has no names or objects. Every nonempty snapshot has exactly
one filesystem-root ROOT name: POSIX `/` or one canonical Windows `[A-Z]:\`,
selecting the sole directory with no CHILD parent. Every
other ROOT locator selects a directory with exactly one CHILD-ancestor chain
to that namespace root, and its decoded locator must equal the root locator
plus that exact component sequence under the frozen join grammar. Each object
has at most one ROOT locator. Thus an absolute locator is an index over the
same hierarchy used by `PARENT_OPEN`, not an unrelated flat alias.
Every identity, protection value, storage anchor, locator encoding, create
disposition, and publication primitive in one script must match
`script.profile`; model profile is independent of the host running the
coordinator.

Every live object has one current `change_token`. A body-byte, size,
link-count, or name-binding mutation replaces it with SHA-256 over
`"AEGIS_MODEL_CHANGE_TOKEN_V1\0"`, the prior token, the exact canonical
request or coordinator-mutation bytes that caused the effect, and the exact
canonical `ConformanceObjectChangeProjection.v1`. That projection contains
every post-effect object field except `change_token`, plus
`schema="ConformanceObjectChangeProjection.v1"`; it therefore has no hash
cycle. A positive write updates `blob_content_id`,
`size_bytes`, and the token atomically; a zero-progress write changes none.
A rename/link/removal/replacement updates every affected object's link count
and token. Flush-state-only changes do not change the token. A create template
supplies the new object's initial token and size. These rules make metadata
drift visible without accepting an arbitrary replacement
`BoundObjectFacts.v1`.

The worker-facing observable projection is exact `BoundObjectFacts.v1`:

```text
change_token=SHA256_ID
identity=RootOrFileIdentity
kind="DIRECTORY" | "REGULAR_FILE"
link_count=U64_DECIMAL | null
protection=ArtifactDirectoryProtection | PublishedFileProtection | null
size_bytes=U64_DECIMAL | null
storage_anchor=DirectoryStorageAnchor | null
```

A directory has null link count/size and any non-null protection is
`ArtifactDirectoryProtection`; a regular file has non-null link count and
size, null storage anchor, and any non-null protection is
`PublishedFileProtection`. A
non-null protection or anchor obeys the same profile/identity relations as the
snapshot. Null protection or directory anchor means that the native query
completed but the observed value is outside the approved closed shape; an
unavailable query is the typed `IO_ERROR` instead. The conformance default
projection drops `blob_content_id`, `flush_state`, and `object_key` from the
selected snapshot object while retaining its size and change token. Production
native ports construct the same facts from a retained handle. No model object
key or flush state crosses the worker RPC boundary, and no snapshot
`blob_content_id` appears in an object-facts response. Transport blob IDs occur
only in the separately framed byte operations below and stop at the adapter.

The metadata-only leaf result is exact `ObjectProbeResult.v1`:

```text
change_token=SHA256_ID | null
identity=RootOrFileIdentity | null
kind=null | "DIRECTORY" | "REGULAR_FILE" | "UNSUPPORTED_OBJECT"
schema="ObjectProbeResult.v1"
size_bytes=U64_DECIMAL | null
state="ABSENT" | "PRESENT"
unsupported_kind=null | "SYMLINK" | "REPARSE_POINT" | "FIFO" | "SOCKET"
                 | "BLOCK_DEVICE" | "CHARACTER_DEVICE" | "OTHER"
```

`ABSENT` requires every nullable fact field to be null. `PRESENT`
requires non-null identity, kind, and change token. `unsupported_kind` is
non-null iff kind is `UNSUPPORTED_OBJECT` and obeys the same platform
partition as the namespace snapshot. Size is non-null exactly for a regular
file and equals its current byte length. Directory and regular-file results
always have null `unsupported_kind`. This value reports only one
retained-parent-relative,
no-follow point observation; it is neither a body handle nor a continuous
existence claim. `BoundObjectFacts.v1` remains deliberately limited to
retained supported directory and regular-file handles. An unsupported object
never produces `BoundObjectFacts.v1`.

Each `create_objects` item has exact keys `object,selector`.
`selector` must select `OBJECT_OPEN` with a create disposition. `object` is one
regular-file object whose key and identity are absent from the initial
snapshot and every other template;
its blob is the empty-blob content ID, size is `"0"`, link count is `"0"`,
change token is unique across the script, and flush state is `DIRTY`. A
matching create call atomically moves this template
into the live snapshot, returns its predeclared identity/object key, and on
Windows installs exactly the request's `(retained parent object,component)`
CHILD name with link count one; Linux installs no name and keeps link count
zero. Before that effect, the template identity's Linux `statx_mnt_id` or
Windows `volume_serial_number` must equal the retained parent anchor;
inequality is a dynamic `TRACE_MISMATCH`. Missing, duplicate-hit,
contradictory, or leftover
templates are `TRACE_MISMATCH`. Actor termination closes its handles and
removes its still-unlinked Linux objects; named objects remain. The model
contains only this catalog and these name/object effects; it is not a general
virtual filesystem.
The create-object array is strictly ordered by canonical selector bytes.
A create selector requires exactly one template only under `DEFAULT`; any
nondefault control at that selector forbids a template and applies before a
create effect.

`namespace_mutations` models an external namespace actor without granting a
worker a mutation hook. Each exact `ConformanceNamespaceMutation.v1` has
`action,component,mutation_id,parent_object_key,replacement_object_key,schema,
step`. `schema="ConformanceNamespaceMutation.v1"`;
`action="REMOVE"|"REPLACE"`; `mutation_id=TOKEN`; `step=U64_DECIMAL`.
`REMOVE` requires a null replacement; `REPLACE` requires one live declared
replacement object. The named CHILD must exist at the start of the mutation.
The parent and replacement must have the same profile/storage anchor, and a
replacement must satisfy the name's object-kind requirement. Applying the
mutation removes the current binding, decrements its object's link count,
installs/increments the replacement when present, updates all affected change
tokens, and removes any zero-link object with no live handle. It never mutates
body bytes.

There are 0..4096 mutations, strictly ordered by
`(numeric step,raw-ASCII mutation_id)`, with unique IDs. A mutation step has no
schedule item at that same step. Combined distinct values across schedule and
mutation steps are contiguous from one. At a mutation-only step the
coordinator applies every mutation in raw-ASCII ID order and emits exact
`COORDINATOR_NAMESPACE_MUTATION` REQUESTED/EFFECT_APPLIED/RETURNED events with
reserved `actor_id="HARNESS"`. `canonical_request` is the exact mutation
object; the derived effect/return outcome is
`{kind="DEFAULT",namespace_effect="MODEL_MUTATION",response=null,
schema="ReviewTransportPortOutcome.v1"}`. A dynamic precondition mismatch
stops with `TRACE_MISMATCH` before effect. Script actor IDs cannot equal
`HARNESS`. This
allows a committed name to be removed or replaced before a declared
`FINAL_REOPEN` at the next step, while preserving a visible causal event.

The actor array has 0..32 items and is strictly raw-ASCII actor-ID ordered.
Each actor has exact keys
`actor_id,entrypoint,kwargs`. Actor IDs are unique
`[A-Z][A-Z0-9_:-]{0,95}` values, a bounded subset of `TOKEN` that leaves room
for every deterministic handle ID; `HARNESS` is reserved and forbidden;
`entrypoint` is one of:

```text
BUILD_CANDIDATE
PUBLISH_TRANSITION
CAPTURE_OBSERVATION
CONSTRUCT_HANDOFF
RESUME_USER_DECISION
```

The mapping is exact:

| Actor entrypoint | Shared-core facade behavior |
|---|---|
| `BUILD_CANDIDATE` | `build_and_publish_candidate` |
| `PUBLISH_TRANSITION` | `publish_transition_record` |
| `CAPTURE_OBSERVATION` | `capture_review_observation` |
| `CONSTRUCT_HANDOFF` | `construct_review_handoff` |
| `RESUME_USER_DECISION` | `resume_user_decision` |

`kwargs` is a strictly increasing array by `name` of exact
`{name=PY_KWARG,value_kind="BYTES_HEX"|"UTF8_HEX"|"NULL",value}` objects that
must equal the selected production facade's complete keyword set. Values are
hex or null according to kind. A script cannot pass a port or control object
as a facade argument.

Zero actors is the codec/empty-model case. One actor may use any entrypoint.
Two through 32 actors must all use `RESUME_USER_DECISION`; deterministic
synthetic multi-actor scheduling exists only for the reservation/decision/
failure race that production recovery must arbitrate. Direct bundle or
transition publisher competition remains a real native no-replace test, not a
host-scheduler-dependent model claim.

The coordinator owns one model namespace and event log. Every actor runs in a
new Python `spawn` process and invokes the same production orchestration core
used by `review_transport.api_v1`, with only its native platform port replaced
by coordinator RPC. A crashed actor's heap, module globals, local handles, and
in-memory decision capability disappear. Namespace effects already applied by
the coordinator remain. A later actor always uses a fresh interpreter.
These harness actors are outside the production transport's exact-zero
subprocess contract; production never enters this coordinator.

The only synthetic atomic operation/event names are; the first eighteen are
model-port calls and the final five are coordinator orchestration
boundaries/markers:

```text
MONOTONIC_READ
UTC_READ
UUID4_READ
PLATFORM_PREFLIGHT
DIRECTORY_OPEN
PARENT_OPEN
OBJECT_PROBE
OBJECT_OPEN
OBJECT_QUERY
STREAM_READ
STREAM_WRITE
FILE_FLUSH
WINDOWS_RENAME_CALL
WINDOWS_RENAME_WAIT
LINUX_LINKAT_CALL
FINAL_REOPEN
DIRECTORY_FLUSH
TRANSITION_READ
RECOVERY_PUBLISH_CALL
RECOVERY_PUBLISH_RESULT
INVOCATION_LIFECYCLE
ACTOR_EXIT
COORDINATOR_NAMESPACE_MUTATION
```

Every accepted worker-originated or recovery-echo request is exact
`ReviewTransportPortRequest.v1={actor_id,arguments,operation,ordinal,purpose,
request_declaration_id,schema}`.
`schema="ReviewTransportPortRequest.v1"`; `request_declaration_id` is the
matched declaration content ID; the other common fields equal its
`ConformanceSelector.v1`. `arguments` has the following exact keys; an
unlisted key or value is invalid:

Every `*_blob_content_id` in a request or response binds one exact raw-byte
RPC data frame in the same direction. The sender transmits the frame
out-of-band from the canonical request/outcome object; the receiver
independently hashes it before use. A request frame from a worker is added to
`produced_blobs` unless already declared in `script.blobs`; a coordinator
response frame must already exist in the current script/produced blob catalog.
When one object contains multiple such fields, frames are ordered by raw-ASCII
field name. Missing, extra, reordered, hash-mismatched, or over-bound frames are
`TRACE_MISMATCH`. The frame mechanism carries bytes only and exposes no
callable, object, path, or control channel.
These IDs are wire framing, not shared-core port values. Before returning a
response to the shared core, the worker adapter verifies the frame and replaces
each content-ID/frame pair with the exact immutable raw bytes. For an outbound
port call it accepts raw bytes from the core, hashes them, and creates the wire
field/frame pair. The native adapter gives the core raw bytes directly. The
shared core cannot branch on a model blob ID or access a frame catalog.

| Operation | Exact `arguments` keys | Exact normal returned `values` |
|---|---|---|
| `MONOTONIC_READ` | none | `value=U64_DECIMAL` |
| `UTC_READ` | none | `value=UTC` |
| `UUID4_READ` | none | `value=UUID4` |
| `PLATFORM_PREFLIGHT` | `profile` | `profile,publication_branch,supported=true` |
| `DIRECTORY_OPEN` | `locator,profile` | `handle_id` |
| `PARENT_OPEN` | `child_directory_handle_id,no_follow` | `handle_id` |
| `OBJECT_PROBE` | `component,no_follow,parent_handle_id` | `result=ObjectProbeResult.v1` |
| `OBJECT_OPEN` | `access,component,disposition,expected_kind,no_follow,parent_handle_id` | `created,handle_id` |
| `OBJECT_QUERY` | `handle_id,query="BOUND_OBJECT_FACTS"` | `facts=BoundObjectFacts.v1` |
| `STREAM_READ` | `byte_count,handle_id,offset` | `blob_content_id,byte_count,eof` |
| `STREAM_WRITE` | `blob_content_id,byte_count,handle_id,offset` | `accepted_count` |
| `FILE_FLUSH` | `handle_id` | none |
| `WINDOWS_RENAME_CALL` | `component,parent_handle_id,replace_if_exists=false,source_handle_id` | `call_status_u32,iosb_status_u32` |
| `WINDOWS_RENAME_WAIT` | `source_handle_id,timeout_le_i64_hex` | `iosb_status_u32,wait_status_u32` |
| `LINUX_LINKAT_CALL` | `branch,component,parent_handle_id,source_handle_id` | `errno` |
| `FINAL_REOPEN` | `component,parent_handle_id` | `handle_id` |
| `DIRECTORY_FLUSH` | `handle_id` | none |
| `TRANSITION_READ` | `directory_handle_id,max_byte_count,predecessor_content_id` | `blob_content_id,object_facts=BoundObjectFacts.v1` |
| `RECOVERY_PUBLISH_CALL` | `artifact_directory_binding_blob_content_id,directory_handle_id,record_blob_content_id,record_content_id,record_schema,slot_locator` | `mode="EXECUTE"|"INJECT",result_blob_content_id` |
| `RECOVERY_PUBLISH_RESULT` | `recovery_publish_call_ordinal,result_blob_content_id` | `status="ACCEPTED"` |
| `INVOCATION_LIFECYCLE` | `entrypoint,result_blob_content_id` | `status="STARTED"|"RETURNED"` |
| `ACTOR_EXIT` | `actor_status` | `closed_handle_count,reclaimed_object_keys,status="CLOSED"` |

`handle_id` is the deterministic `TOKEN`
`HANDLE:<actor_id>:<that actor's 1-based successful-open ordinal>`, scoped to
one actor and invalid after that actor exits; it never contains a PID, native
handle value, or arrival-order counter. It is also wire-only. The conformance
adapter wraps it in an opaque handle capability before the shared core sees
it; the core may retain that capability and pass it back to port calls but may
not stringify, parse, compare, order, hash, serialize, or inspect it. The
native adapter supplies the same abstract capability backed by a retained
native handle. AST/import tests enforce that the shared core never branches on
the wrapper implementation or a conformance token. A successful
`DIRECTORY_OPEN` resolves
one exact ROOT name and retains the tuple `(directory object key, exact opened
ROOT locator, filesystem-root ROOT locator, exact root-to-object component
sequence, profile)`. The two locator constructions are byte-identical under
the namespace invariant. `PARENT_OPEN` resolves the directory's unique CHILD
parent, or the same object at a model namespace root, and returns another
retained directory handle with the root-to-object sequence shortened by one
component when a parent exists and unchanged when already at the namespace
root; it performs no ROOT-locator lookup. `OBJECT_PROBE` resolves only the
CHILD pair `(retained parent object key,component)` without issuing a retained
body handle. A missing pair returns `ABSENT`; a present pair returns the exact
identity and supported or unsupported kind projection. A successful
`OBJECT_OPEN` resolves only that same CHILD pair `(retained parent object key,
component)`; its handle retains the selected object key, the filesystem-root
locator, and the parent sequence plus that component. Thus later replacement
of a ROOT name cannot retarget an already-issued handle, while a locator
reported from a handle is still the unique frozen root-plus-sequence
composition. Handle IDs cannot cross actors, and a non-directory handle
cannot be supplied where a parent or directory handle is required. `access` is
`READ|READ_WRITE|DIRECTORY_TRAVERSE`; `expected_kind` is
`DIRECTORY|REGULAR_FILE`; `disposition` is
`OPEN_EXISTING|WINDOWS_CREATE_NEW|LINUX_CREATE_UNNAMED`. `component` is null
only for `LINUX_CREATE_UNNAMED`; otherwise it is `NativeComponent`, an exact
`{encoding,value}` object. POSIX encoding is `POSIX_BYTES_HEX` with 2..510
lowercase even-length hex characters. Windows encoding is `UTF16LE_HEX` with
4..1020 lowercase hex characters, length divisible by four, and strict
well-formed UTF-16. The decoded value is one nonempty component, not dot or
dot-dot, with no NUL or slash/backslash. The Windows profile is deliberately
ASCII-only: every decoded code unit is one ASCII letter, digit, space, `.`,
`_`, or `-`; leading/trailing space and trailing dot are forbidden. It also
rejects an ASCII-case-insensitive basename
`CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]` before any first dot. Windows CHILD
uniqueness uses lowercase-ASCII component bytes, while the locator/CHILD
spelling relation remains byte-exact. No Unicode normalization, host upcase
table, or locale fold occurs. These are the complete model component rules;
host path libraries do not add rules. Its encoding must match the script
profile.
`byte_count` is `U64_DECIMAL` with parsed value 1..65,536; offset is
`U64_DECIMAL`. A read response's blob decodes to exactly its count;
`eof=true` means the returned range reaches the then-current blob end. A write
request's blob and count agree exactly.

Request relations are closed. `profile` equals `script.profile`, and a normal
preflight response returns the script's exact `publication_branch`;
`no_follow=true`. `PARENT_OPEN` accepts only a live directory handle and may
return that same object only when it has no CHILD parent. `OBJECT_PROBE`
accepts one live parent-directory handle and a non-null component.
`OPEN_EXISTING` uses a non-null component and exactly
`READ` for a regular file or `DIRECTORY_TRAVERSE` for a directory and returns
`created=false`. If the selected existing object has a different supported
kind or is an unsupported object, no handle is returned; the port returns
typed `UNSUPPORTED_OBJECT_TYPE` with its exact present
`ObjectProbeResult.v1`. A create always expects a regular file, uses `READ_WRITE`, and
returns `created=true`; `WINDOWS_CREATE_NEW` plus a component is Windows-only,
while `LINUX_CREATE_UNNAMED` plus null component is Linux-only. `WRITE` is not
an emitted access token. File and directory flushes accept only the matching
handle kind. A Windows wait timeout is exactly 16 lowercase hex characters
decoding to one negative little-endian signed-64 relative timeout produced by
the frozen encoder. Linux `branch` is exactly
`AT_EMPTY_PATH|PROC_SELF_FD` and matches `script.publication_branch`;
`NO_SUPPORTED_BRANCH` forbids a `LINUX_LINKAT_CALL`.
`max_byte_count` is `U64_DECIMAL` in 1..2,097,152. Lifecycle `entrypoint`
equals the owning actor entrypoint. Its START request has null
`result_blob_content_id` and returns `STARTED`; its after-result request has
the independently hashed non-null content ID of the exact facade return bytes
and returns `RETURNED`. A public exception or unexpected exception has no
after-result gate because it produced no return bytes. Any wrong handle owner/kind/access,
profile, disposition, component relation, or response `created` flag is
`TRACE_MISMATCH`.

The coordinator, not the worker, assigns `purpose`. `BUILD_CANDIDATE` is
`BUNDLE`; direct transition publication parses the canonical record and
derives `ATTEMPT`, `DECISION`, `FAILURE`, or `TRANSITION`; capture/handoff
reads, both `INVOCATION_LIFECYCLE` markers, and `ACTOR_EXIT` are `NONE`.
Reviewer invocation attempt/outcome records use `TRANSITION`; their semantic
send reservation is not the user-decision `ATTEMPT` purpose. For recovery, the
coordinator validates the complete
`RECOVERY_PUBLISH_CALL` request and record, derives purpose from
`record_schema`, and only then records `REQUESTED`. Its
`directory_handle_id` must be that actor's live handle for the exact directory
profile/identity/protection/storage anchor in the supplied binding. Its
`slot_locator` must equal the
canonical locator formed from that handle's retained ROOT locator plus the
single deterministic transition component derived from the record's
`predecessor_content_id`; it cannot select a different root, parent, or
component. A malformed request is `TRACE_MISMATCH`, does not increment a
publisher count, and cannot be relabelled by a worker-supplied tag.

One actor has at most one active recovery-publisher call. Its active slot has
this closed state set; `NONE` means no active call, while every other state
carries one immutable call key:

```text
NONE
CALL_REQUESTED_AT_BEFORE_GATE
CALL_RELEASED_AWAITING_RESULT
RESULT_ACCEPTED_PENDING_ACK
CLOSED
TERMINAL_BEFORE_RESULT
TERMINAL_POSTEFFECT_CRASH
```

The call key is `(actor_id,purpose,ordinal)`. It cannot occur in the actor's
closed-call ledger, and its ordinal must be the next value for that
actor/operation/purpose. The validated call request installs that sole active
call and enters `CALL_REQUESTED_AT_BEFORE_GATE`. A
before-gate CRASH or controlled call/nested-atom NONRETURN enters
`TERMINAL_BEFORE_RESULT` and legally produces no result request. A RELEASE
that begins DEFAULT or INJECT execution enters
`CALL_RELEASED_AWAITING_RESULT`.

Under
`DEFAULT`, a released `RECOVERY_PUBLISH_CALL` returns
`{mode="EXECUTE",result_blob_content_id=null}`. The worker adapter invokes the
same transition publisher used by production recovery through the model port
and intercepts its exact returned bytes before giving them to the outer shared
core. Under a `PUBLISH_RESULT` control, the call returns
`{mode="INJECT",result_blob_content_id=<controlled ID>}` plus that exact
coordinator-to-worker frame; no low-level publisher atom runs and the declared
namespace effect is still deferred.

In both modes the adapter must next send one
`RECOVERY_PUBLISH_RESULT` request with the exact raw result frame. Its purpose
equals the outstanding call, its selector ordinal and
`recovery_publish_call_ordinal` both equal that call's ordinal, and no second
or out-of-order result is legal. The coordinator independently parses the
result and validates its binding, slot, schema, record, content IDs, origin,
truth-table row, and relationship to the complete stored call. For `DEFAULT`
it additionally validates the result against the already logged low-level
events and current namespace. For injection it requires byte equality with the
controlled frame, then and only then applies the deferred namespace effect.
After validation/effect the call enters `RESULT_ACCEPTED_PENDING_ACK`; the
outstanding-result obligation is consumed, although the request remains at
the after-effect gate. RELEASE logs `RETURNED`, returns
`status="ACCEPTED"`, enters `CLOSED`, and only then lets the adapter return the
held raw bytes to the outer shared core. A scheduled CRASH at that exact gate
logs `CRASHED`, enters `TERMINAL_POSTEFFECT_CRASH`, retains any applied effect,
and legally delivers no nested result.

A malformed/missing/extra result frame, result outside
`CALL_RELEASED_AWAITING_RESULT`, relation mismatch, or actor exit while still
in `CALL_RELEASED_AWAITING_RESULT` is `TRACE_MISMATCH`. Exit from
`RESULT_ACCEPTED_PENDING_ACK` is legal only after the matching scheduled
CRASH action has first selected `TERMINAL_POSTEFFECT_CRASH`; an ambient or
unscheduled exit there is `TRACE_MISMATCH`. An injected effect not yet reached
is not applied. `CLOSED` appends the call key to the immutable closed-call
ledger and clears the active slot; a still-live actor may then issue its next
strictly ordered attempt, decision, or failure call. Both `TERMINAL_*` states
terminate the actor and forbid another call. A replayed closed key, two active
calls, or a gap/regression in the per-purpose ordinal is `TRACE_MISMATCH`.

`DEFAULT` behavior is closed. Source atoms return their keyed value.
Preflight returns the script profile and publication branch as supported;
`NO_SUPPORTED_BRANCH` is then classified without a publication call.
`DIRECTORY_OPEN` resolves only an exact ROOT locator. `PARENT_OPEN` resolves
the unique declared directory parent or the namespace-root self relation.
`OBJECT_PROBE` resolves a CHILD to exact `ABSENT` or present metadata without
creating a handle. Every other open/read/publish atom resolves CHILD
names through the retained directory-object key, never by resolving that ROOT
locator again; outside `OBJECT_PROBE`, a missing ROOT or CHILD name is the
typed missing outcome.
An `OBJECT_OPEN(OPEN_EXISTING)` kind mismatch returns
`UNSUPPORTED_OBJECT_TYPE` and the present probe result without a handle.
Query returns only the current `BoundObjectFacts.v1` projection. Read returns the requested range
and exact EOF fact. Write replaces that exact range, materializes the resulting
blob, and marks the object dirty; a gap or out-of-range offset is an I/O error.
File/directory flush marks the selected object flushed. Windows create-new
consumes its exact template and installs one CHILD under the retained parent;
Linux create-unnamed consumes its template without a name. A default Windows
rename returns collision without effect when the destination CHILD exists,
otherwise moves the held source CHILD under the retained parent to the final
component and returns matching immediate success statuses. A default Linux
link returns `EEXIST` without effect when that CHILD exists, otherwise adds the
CHILD, increments link count, and returns zero. Final reopen resolves
`(retained parent object,component)`; transition read derives its deterministic
component from the predecessor and resolves it under the retained directory
object, returning its exact bounded bytes and facts projection. No default
operation manufactures an undeclared identity, locator, object, component, or
byte sequence.

`RECOVERY_PUBLISH_CALL` is a conformance-only orchestration boundary around
the same transition publisher called internally by production recovery; it is
not a native-port method or public production hook. `DEFAULT` authorizes the
worker adapter to execute that publisher through low-level model atoms;
`PUBLISH_RESULT` supplies one independently validated result with an effect
deferred to `RECOVERY_PUBLISH_RESULT`. `INVOCATION_LIFECYCLE` and `ACTOR_EXIT`
are generated only by the worker/coordinator envelope outside the shared core.
Production wiring contains none of these four boundaries/markers.

Every coordinator-log outcome is exact
`ReviewTransportPortOutcome.v1={kind,namespace_effect,operation,response,
schema}`. `schema="ReviewTransportPortOutcome.v1"`; `operation` equals the
request. `kind` is exactly
`OK|IO_ERROR|NONRETURN|SHORT_IO|WINDOWS_CALL_STATUS|WINDOWS_WAIT_STATUS|
LINUX_ERRNO|MISSING|SUBSTITUTE|UNSUPPORTED_OBJECT_TYPE|UNSUPPORTED|
PUBLISH_RESULT`.
`DEFAULT` produces the exact state-derived `OK`, `MISSING`,
`UNSUPPORTED_OBJECT_TYPE`, or platform `UNSUPPORTED` kind; it is a script
directive, not a returned kind.
`namespace_effect` is
`NONE|MODEL_MUTATION|INSTALL_REQUEST|HIDDEN_INSTALL_REQUEST`.
`response` is the exact normal values object in the operation table, the exact
status/result fields required by the selected control, or null for
`IO_ERROR|NONRETURN|MISSING|UNSUPPORTED`. For `SHORT_IO`, a read response is
`{blob_content_id,byte_count,eof=false}` for the exact selected prefix, while a
write response is `{accepted_count}`. For `SUBSTITUTE`, response has the named
operation's normal shape populated from the replacement object, or the exact
injected `facts` for `OBJECT_QUERY`. Model keys remain only in the script
control and coordinator state; they never appear in the worker response.
For `UNSUPPORTED_OBJECT_TYPE`, response is exactly
`{result=ObjectProbeResult.v1}` with `state="PRESENT"` and a kind different
from the open request's `expected_kind`.
The worker RPC receives only the response or typed failure signal; it never
receives `namespace_effect`. `NONRETURN` is recorded by the coordinator but no
RPC response is delivered.
The shared core maps these typed outcomes through the same
public result/exception tables as native ports. Raw model outcomes never become
actor facade results. Tests assert request/outcome bytes in the log. Adding an
atom, key, enum, or mapping is a plan/API revision; private Python names are
never logged or selectable.

The control and schedule arrays each have 0..4096 items. Each control has exact
keys `control_id,outcome,selector`. IDs are unique `TOKEN` and controls are
strictly raw-ASCII control-ID ordered; selectors are also unique, so one atom
can never match two controls.
One declared controllable request with no matching control uses `DEFAULT`; an
explicit `DEFAULT` control is equivalent but must be consumed exactly once.
`ConformanceSelector.v1` has
exact keys
`actor_id,operation,ordinal,purpose,request_declaration_id`;
`request_declaration_id` is the exact matching
`ConformanceRequestDeclaration.v1` content ID;
`ordinal` is `U64_DECIMAL` starting at one independently for
`(actor_id,operation,purpose)`, and purpose is
`BUNDLE|TRANSITION|ATTEMPT|DECISION|FAILURE|NONE`.
`outcome` is one closed tagged union:

| `kind` | Additional exact fields | Meaning |
|---|---|---|
| `DEFAULT` | none | use the model's normal operation |
| `IO_ERROR` | none | return the operation's controlled I/O failure |
| `NONRETURN` | none | actor blocks until the coordinator records and kills it |
| `SHORT_IO` | `accepted_count=U64_DECIMAL` | read/write exactly that bounded prefix |
| `WINDOWS_CALL_STATUS` | `call_status_u32`, `iosb_status_u32`, `namespace_effect` | inject exact unsigned-32-bit rename-call/initial-IOSB pair |
| `WINDOWS_WAIT_STATUS` | `wait_status_u32`, `iosb_status_u32`, `namespace_effect` | inject exact unsigned-32-bit wait/final-IOSB pair |
| `LINUX_ERRNO` | `errno`, `namespace_effect` | inject exact nonnegative errno |
| `MISSING` | none | the selected reopen/read observes no object |
| `SUBSTITUTE` | `replacement_facts=BoundObjectFacts.v1` for `OBJECT_QUERY`; otherwise `replacement_object_key=TOKEN` | return injected observable facts or a different already-live declared object without changing any name |
| `UNSUPPORTED_OBJECT_TYPE` | `result=ObjectProbeResult.v1` | an existing-open observes a present object whose kind differs from `expected_kind` |
| `UNSUPPORTED` | none | return an unavailable platform profile |
| `PUBLISH_RESULT` | `deferred_namespace_effect,installed_flush_state,residual_staging_object,result_blob_content_id` | inject one predeclared synthetic transition result and defer its exact atomic namespace effect until the echoed result request |

Allowed combinations are the following exhaustive matrix. A missing cell is
illegal; there is no default-by-analogy rule.

| Operation | Complete allowed control outcomes |
|---|---|
| `MONOTONIC_READ` | `DEFAULT`, `IO_ERROR`, `NONRETURN` |
| `UTC_READ` | `DEFAULT`, `IO_ERROR`, `NONRETURN` |
| `UUID4_READ` | `DEFAULT`, `IO_ERROR`, `NONRETURN` |
| `PLATFORM_PREFLIGHT` | `DEFAULT`, `IO_ERROR`, `NONRETURN`, `UNSUPPORTED` |
| `DIRECTORY_OPEN` | `DEFAULT`, `IO_ERROR`, `NONRETURN`, `MISSING`, `SUBSTITUTE` |
| `PARENT_OPEN` | `DEFAULT`, `IO_ERROR`, `NONRETURN`, `MISSING`, `SUBSTITUTE` |
| `OBJECT_PROBE` | `DEFAULT`, `IO_ERROR`, `NONRETURN` |
| `OBJECT_OPEN` | `DEFAULT`, `IO_ERROR`, `NONRETURN`, `MISSING`, `SUBSTITUTE`, `UNSUPPORTED_OBJECT_TYPE` |
| `OBJECT_QUERY` | `DEFAULT`, `IO_ERROR`, `NONRETURN`, `SUBSTITUTE` |
| `STREAM_READ` | `DEFAULT`, `IO_ERROR`, `NONRETURN`, `SHORT_IO` |
| `STREAM_WRITE` | `DEFAULT`, `IO_ERROR`, `NONRETURN`, `SHORT_IO` |
| `FILE_FLUSH` | `DEFAULT`, `IO_ERROR`, `NONRETURN` |
| `WINDOWS_RENAME_CALL` | `DEFAULT`, `IO_ERROR`, `NONRETURN`, `WINDOWS_CALL_STATUS` |
| `WINDOWS_RENAME_WAIT` | `DEFAULT`, `IO_ERROR`, `NONRETURN`, `WINDOWS_WAIT_STATUS` |
| `LINUX_LINKAT_CALL` | `DEFAULT`, `IO_ERROR`, `NONRETURN`, `LINUX_ERRNO` |
| `FINAL_REOPEN` | `DEFAULT`, `IO_ERROR`, `NONRETURN`, `MISSING`, `SUBSTITUTE` |
| `DIRECTORY_FLUSH` | `DEFAULT`, `IO_ERROR`, `NONRETURN` |
| `TRANSITION_READ` | `DEFAULT`, `IO_ERROR`, `NONRETURN`, `MISSING`, `SUBSTITUTE` |
| `RECOVERY_PUBLISH_CALL` | `DEFAULT`, `NONRETURN`, `PUBLISH_RESULT` |

No control selects `RECOVERY_PUBLISH_RESULT`, `INVOCATION_LIFECYCLE`, or
`ACTOR_EXIT`; their behavior is derived from the validated call, schedule,
and observed process exit. `SHORT_IO` requires `STREAM_READ` or
`STREAM_WRITE`; the accepted count is smaller than the declared request count,
and zero means zero-progress failure, never EOF or success. `MISSING` and
`UNSUPPORTED_OBJECT_TYPE` on `OBJECT_OPEN` additionally require
`disposition=OPEN_EXISTING`; a create request cannot select either.
For an object-selecting `SUBSTITUTE`, the replacement object is live,
profile-compatible, kind-compatible, and different from the declared default
object. For `OBJECT_QUERY`, `replacement_facts` is present instead of an
object key, is profile-compatible, and differs from the default projection.
All argument-dependent restrictions are checked against the frozen request
declaration before actors start.

`IO_ERROR`, `NONRETURN`, `MISSING`, `SUBSTITUTE`,
`UNSUPPORTED_OBJECT_TYPE`, and `UNSUPPORTED` apply before any namespace
effect; `SUBSTITUTE` changes only the returned object.
`SHORT_IO` applies exactly its accepted prefix before returning, so a positive
short write may dirty/change the object while zero progress changes nothing.

For ordinary default operations, `MODEL_MUTATION` is used exactly when a
staging/unnamed create, write, flush-state transition, or actor-exit
reclamation actually changes the snapshot;
read/query/open-existing/source/preflight operations use `NONE`. A successful
final rename/link uses `INSTALL_REQUEST`. Low-level publication controls use
only `NONE|INSTALL_REQUEST|HIDDEN_INSTALL_REQUEST`. Windows definite success
requires `INSTALL_REQUEST`; collision/unsupported requires `NONE`; an unknown
outcome may use `NONE` or `HIDDEN_INSTALL_REQUEST`. A pending call plus wait
script requires `NONE` on the call and applies at most one install effect at
the wait; its combined statuses/effect
must obey the frozen resolver. Linux errno zero requires `INSTALL_REQUEST`,
and a definite failure requires `NONE`. At `RECOVERY_PUBLISH_CALL`,
`PUBLISH_RESULT` independently parses the exact `SYNTHETIC_CONFORMANCE`
`TransitionPublicationResult.v1`, requires its
binding/slot/schema/record/content IDs to match the request, stores the
deferred effect, and returns an `INJECT` response with outcome
`namespace_effect=NONE`. The echoed `RECOVERY_PUBLISH_RESULT` revalidates the
same bytes and emits the derived `PUBLISH_RESULT` outcome with
`namespace_effect=deferred_namespace_effect`. Confirmed or unconfirmed
publication requires `INSTALL_REQUEST`; unknown publication uses
`MODEL_MUTATION` when the rename did not install and
`HIDDEN_INSTALL_REQUEST` when it did; definite `NOT_PUBLISHED` uses
`MODEL_MUTATION` exactly when its Windows result has a non-null staging
locator, otherwise `NONE`. Thus a named Windows stage is never silently erased
from the model.

`installed_flush_state` is exactly `FLUSHED` for
deferred `INSTALL_REQUEST|HIDDEN_INSTALL_REQUEST` and null for
`NONE|MODEL_MUTATION`: transition publication cannot reach its commit primitive
until the held record file has completed its precommit file flush and
independent verification. A dirty final install is a static contradiction.
`residual_staging_object` is non-null exactly for `MODEL_MUTATION`, null
otherwise, and has the exact snapshot-object shape for one regular file with
link count one. Its object key is
`STAGING:<uppercase 64-hex digest from result_blob_content_id>`, its protection
is derived from the validated binding as published-file protection, and its
blob must be declared in `script.blobs`. Its identity equals the result object
identity when that field is non-null; when the CREATE result deliberately has
null identity, the predeclared model identity is not exposed to the actor.
CREATE-query/limit rows require empty bytes and `DIRTY`; WRITE-failed/limit rows
require a possibly empty exact record prefix and `DIRTY`; SEAL-failed requires
the complete record and `DIRTY`; VERIFY/PUBLISH/unknown rows require the
complete record and `FLUSHED`.

Applying `MODEL_MUTATION` adds that object and the single CHILD component
obtained by removing the retained binding-root prefix and separator from the
validated `staging_origin_locator`; its object key, identity, and CHILD pair
must all be absent before effect. Applying an install requires the final target
CHILD under the retained `directory_handle_id`, the derived published object
key, and the result identity all to be absent. Any dynamic contradiction is
`TRACE_MISMATCH` before effect. A final install creates object key
`PUBLISHED:<uppercase 64-hex record digest>`, places the exact requested record
bytes in that object, and adds exactly one CHILD using the deterministic
component encoded by `slot_locator`. Identity comes from the validated result.
Its identity's mount ID or volume serial must match the retained directory
anchor or the request is `TRACE_MISMATCH` before effect.
Published-file protection is derived from the validated binding owner and
profile, never copied as directory protection: Linux fixes mode `0600`, owner
UID, and no access ACL; Windows fixes the protected owner/SYSTEM file SDDL.
The new file has size equal to the requested record bytes, link count one,
flush state `FLUSHED`, and the deterministic post-effect change token. Hidden install
means only that the actor's result does not prove the effect, not that the
final model omits it.
At the low-level Windows atom an install moves the held staging name to the
final component and keeps the same object/link count; at Linux linkat it adds
the final name to the held unnamed object and increments link count from zero
to one. A hidden install applies those same namespace facts.

Static contradictions are rejected before actor start. A contradiction
depending on a dynamic request is detected after the complete request is
validated and logged but before any effect, sets `TRACE_MISMATCH`, and stops
all actors. Every control is one-shot; an unmatched, duplicate-hit, or leftover
control also produces `TRACE_MISMATCH`.

Each schedule item has exact keys `action,phase,selector,step`.
`step` is canonical decimal. The array is ordered by `(numeric step,
canonical selector bytes, raw-ASCII phase)`. Each `(selector,phase)` pair is
unique. Multiple items may share a step and form a barrier group. `action` is
`RELEASE|CRASH`; `selector` is exact `ConformanceSelector.v1`. Only this matrix
is legal:

| Operation / phase | Legal action |
|---|---|
| `INVOCATION_LIFECYCLE / START` | `RELEASE` |
| `INVOCATION_LIFECYCLE / AFTER_RESULT_BEFORE_EXTERNAL_PERSIST` | `RELEASE` or `CRASH` |
| `RECOVERY_PUBLISH_CALL / BEFORE_EFFECT` | `RELEASE` or `CRASH` |
| `RECOVERY_PUBLISH_RESULT / AFTER_EFFECT_BEFORE_RETURN` | `RELEASE` or `CRASH` |
| `OBJECT_OPEN / AFTER_EFFECT_BEFORE_RETURN` | `RELEASE` or `CRASH`; successful create only |
| `STREAM_WRITE / AFTER_EFFECT_BEFORE_RETURN` | `RELEASE` or `CRASH`; positive accepted count only |
| `FILE_FLUSH / AFTER_EFFECT_BEFORE_RETURN` | `RELEASE` or `CRASH`; dirty-to-flushed transition only |
| `WINDOWS_RENAME_CALL / AFTER_EFFECT_BEFORE_RETURN` | `RELEASE` or `CRASH`; immediate install only |
| `WINDOWS_RENAME_WAIT / AFTER_EFFECT_BEFORE_RETURN` | `RELEASE` or `CRASH`; waited install only |
| `LINUX_LINKAT_CALL / AFTER_EFFECT_BEFORE_RETURN` | `RELEASE` or `CRASH`; successful link only |
| `FINAL_REOPEN / AFTER_EFFECT_BEFORE_RETURN` | `RELEASE` or `CRASH`; successful handle acquisition only |
| `DIRECTORY_FLUSH / AFTER_EFFECT_BEFORE_RETURN` | `RELEASE` or `CRASH`; successful flush only |

Lifecycle START and AFTER_RESULT use `purpose=NONE` and respectively that
actor's first and second lifecycle ordinal. A recovery pair uses one
`RECOVERY_PUBLISH_CALL` BEFORE selector and the corresponding
`RECOVERY_PUBLISH_RESULT` AFTER selector with the same actor, purpose, and
numeric ordinal. Its BEFORE step is strictly lower than its AFTER step. One
actor occurs at most once in a barrier step, and each actor's schedule entries
follow its program-order gates. Violations are statically invalid rather than
scheduler-dependent deadlocks.

The schedule's distinct steps need not be contiguous by themselves; the union
of schedule steps and mutation-only steps is contiguous from one. A
low-level after-effect gate is reached only for the exact effect/acquisition
row named above. Its selector binds the frozen request declaration, so the
coordinator knows before actor start whether the gate is argument-compatible.
Dynamic status still decides reachability; an impossible or missing reached
gate is `TRACE_MISMATCH`.

The coordinator waits until every selector in one barrier group has arrived,
then applies actions in raw-ASCII actor-ID order. A released
`RECOVERY_PUBLISH_CALL` runs its `DEFAULT` nested publication, or completes its
INJECT echo, atomically until it has arrived and blocked at the corresponding
`RECOVERY_PUBLISH_RESULT` gate before the next actor in that group; a
controlled nested nonreturn terminates instead. The coordinator does not
release the result gate ahead of its own schedule step. No low-level or
deferred effect from two actors interleaves. This permits both actors to
construct requests from the same pre-effect namespace while making commit
arbitration reproducible.

Every actor has one lifecycle START gate. Every facade result that reaches the
coordinator as exact return bytes has one after-result gate that binds their
content ID. Public or unexpected exceptions terminate without that gate. Every recovery publisher call first
hits a before-effect gate. A CRASH there forbids nested execution and an
after-effect gate. A RELEASE begins the nested call; if that call reaches its
after-effect boundary it requires exactly one after-effect gate. A controlled
`NONRETURN` on the outer call or any issued nested atom prevents that boundary
and forbids an after-effect entry; the coordinator records the nonreturn and
terminates the actor as specified below. Multi-actor scripts schedule every
gate reachable under their selected controls and source values.
For a zero-actor script the schedule is empty. A single-actor script may use
an entirely empty schedule only when it contains no crash or interleaving
assertion; all reached gates then auto-release in program order and every
event has `schedule_step=0`. If any schedule entry exists, every dynamically
reached gate must have exactly one entry. A worker blocks until its exact
barrier `step`; the
coordinator never resolves ordering by sleep, arrival order, random retry, or
ambient process scheduling. Missing, duplicate, impossible, leftover, or
deadlocked entries produce `TRACE_MISMATCH`.

Crash semantics are exact:

- `BEFORE_EFFECT`: the call's REQUESTED event and count exist; namespace is
  unchanged; no nested publisher atom, result request, or facade result
  exists;
- `AFTER_EFFECT_BEFORE_RETURN`: the exact
  request and worker-to-coordinator result frame exist. For
  `RECOVERY_PUBLISH_RESULT`, every applicable nested/deferred effect remains
  but the outer core receives no nested result. For a low-level gate, its
  create/write/flush/install/handle-acquisition effect and
  `EFFECT_APPLIED` event remain but no RPC response reaches the shared core.
  In both cases there is no gate `RETURNED`/ACK and the actor leaves no reusable
  in-memory capability;
- `AFTER_RESULT_BEFORE_EXTERNAL_PERSIST`: the result is recorded only in the
  synthetic blob set and the lifecycle request binds its content ID; no
  `UserDecisionPriorOutcome.v1` is supplied to the next actor unless the script
  explicitly does so;
- `NONRETURN`: the coordinator records `NONRETURN`, kills that worker, and
  never fabricates a product timeout result.

For every scheduled CRASH or controlled `NONRETURN`, the coordinator closes
that actor's RPC channel, hard-kills the process, and waits/joins until
OS-observed exit before releasing another actor. Confirmed normal and abnormal
exit then run the explicit `ACTOR_EXIT` marker below; handle closure or Linux
unlinked-object reclamation is never a silent final-namespace edit. If exit
cannot be confirmed within the harness watchdog, the run is
`HARNESS_LIVENESS_FAILURE`, all other workers are killed, no `ACTOR_EXIT`
marker or modeled reclamation is emitted for that actor, and no later
non-teardown effect from that actor is allowed. Other workers are joined when
possible and receive only their confirmed `ACTOR_EXIT` cleanup markers; an
unconfirmed actor's still-live zero-link object remains in `final_namespace`.

`ACTOR_EXIT` is a coordinator-generated terminal request, not worker RPC,
script control, or schedule gate. It is emitted exactly once after the
coordinator has observed and joined that actor's OS process. Its derived request has
`purpose=NONE`, ordinal one, and no request declaration. Its `schedule_step`
equals the actor's most recently released step for an independent normal/
scheduled termination, or zero for an unscheduled single actor. When a global
stop causes collateral termination, every affected exit instead uses the
synthetic terminal cleanup step `run_stop_step + 1`; that step contains only
exit markers and need not occur in the script. `run_stop_step` is
the exact barrier step whose crash, nonreturn, mismatch, resource limit, or
liveness failure first forced collateral termination; it is zero when no
global stop occurred. Therefore no raw-ASCII actor ordering can serialize a
collateral exit before the event that caused its kill. Its
`actor_status` is exactly the terminal status later stored in that actor's
result:

Its event `canonical_request` is exact
`CoordinatorDerivedRequest.v1={actor_id,arguments={actor_status},
operation="ACTOR_EXIT",ordinal="1",purpose="NONE",
schema="CoordinatorDerivedRequest.v1"}`. It has no
`request_declaration_id` and can never match a script selector.

```text
RETURNED
CRASHED
NONRETURN
PUBLIC_VALIDATION_ERROR
PUBLIC_OPERATION_ERROR
UNEXPECTED_EXCEPTION
```

The mapping is closed. `RETURNED` requires the external facade-return gate to
have ACKed. A scheduled crash, or a coordinator kill caused by another
actor's terminal run failure before this actor produced a public result, is
`CRASHED`. A selected controlled nonreturn is `NONRETURN`. The two public
error statuses require their exact frozen exception classes.
`UNEXPECTED_EXCEPTION` covers every other worker exception, protocol breach,
or impossible exit. A result that reached the after-result crash gate but was
not ACKed is `CRASHED`, not `RETURNED`. No exit code, signal, or coordinator
preference can relabel these rows.

The response is exact
`{closed_handle_count=U64_DECIMAL,reclaimed_object_keys=<array>,
status="CLOSED"}`. The array has 0..2048 unique `TOKEN` values in raw-ASCII
order. `closed_handle_count` counts every still-live model handle owned by the
actor, including directory and regular-file handles; the coordinator
invalidates each exactly once. It then removes exactly those live Linux
regular-file objects whose link count is zero and whose last live handles
were among the just-closed set. It never removes a named object, a directory,
a Windows staging object, or a Linux object with a positive link count.
`reclaimed_object_keys` is exactly the removed set.

The marker logs `REQUESTED`, then one derived `kind=OK` outcome. If removal
changes the namespace it logs one `EFFECT_APPLIED` with
`namespace_effect=MODEL_MUTATION`; otherwise it logs no effect event and the
outcome has `namespace_effect=NONE`. It finally logs `RETURNED` with the same
outcome. Handle invalidation alone is not a namespace mutation. No
`DEFAULT`, fault control, source item, template, or schedule item selects this
outcome.

The coordinator does not release a later schedule step while an actor has
terminally completed at the current step but has not been joined and processed
through `ACTOR_EXIT`. When multiple actors terminally complete at one barrier,
their exit markers are processed in raw-ASCII actor-ID order. This preserves
the same effect order later used for event serialization. A protocol failure
such as an ambient exit in `CALL_REQUESTED_AT_BEFORE_GATE` or
`CALL_RELEASED_AWAITING_RESULT`, or an ambient exit in
`RESULT_ACCEPTED_PENDING_ACK` before a scheduled CRASH action, first fixes the
actor status to `UNEXPECTED_EXCEPTION`, sets `TRACE_MISMATCH`, then still emits
the marker if OS exit is confirmed. The legal
`TERMINAL_POSTEFFECT_CRASH` state remains `CRASHED`. Without confirmed OS exit there is no marker,
no modeled close, no modeled reclamation, and no actor-result finalization.
Production native adapters instead own all invocation-scope handles and close
them at their public-facade boundary; the conformance marker is evidence of
equivalent lifecycle cleanup, not a production hook.

`RECOVERY_PUBLISH_CALL/REQUESTED` is logged before effect. Attempt, decision,
and failure call counts are computed from those events, never from a SUT
counter. The coordinator has a 120-second total and 30-second per-actor
watchdog only for harness liveness; expiry is
`HARNESS_LIVENESS_FAILURE`, not a product timeout.

`ReviewTransportConformanceEventLog.v1` has exact keys:

```text
actor_results
authority_verified=false
case_id=TOKEN
evidence_kind="SYNTHETIC_CONFORMANCE"
events
final_namespace
native_status_observed=false
produced_blobs
run_state="COMPLETED" | "COMPLETED_WITH_CRASHES"
        | "EXTERNAL_NONRETURN" | "TRACE_MISMATCH"
        | "HARNESS_RESOURCE_LIMIT_EXCEEDED"
        | "HARNESS_LIVENESS_FAILURE"
schema="ReviewTransportConformanceEventLog.v1"
script_content_id=SHA256_ID
unused_create_object_selectors
unused_control_ids
unused_namespace_mutation_ids
unused_request_declaration_ids
unused_schedule_entries
unused_source_selectors
```

`final_namespace` is exact `ConformanceNamespaceSnapshot.v1`.
`produced_blobs` is a strictly content-ID-ordered array of the same exact blob
shape as script blobs; it contains newly materialized request/read/result
bytes not already present in script blobs. It has at most 65,536 items, each
at most 2,097,152 decoded bytes, and at most 67,108,864 decoded bytes total.
Actor results have at most 32 items; unused arrays have at most their
corresponding script bounds. Actor results are strictly raw-ASCII actor-ID
ordered; unused control, mutation, and request-declaration IDs are raw-ASCII
ordered and unused source/template/schedule selectors are ordered by their
canonical selector keys and
`(numeric step,canonical selector bytes,raw-ASCII phase)` keys respectively.
Events
have at most 131,072 items and the complete
canonical event-log result is at most 134,217,728 bytes.

Every event has exact keys
`actor_id,actor_sequence,canonical_outcome,canonical_request,effect_sequence,
namespace_after_sha256,namespace_before_sha256,operation,ordinal,phase,purpose,
schedule_step,sequence`.
Phase is `REQUESTED|EFFECT_APPLIED|RETURNED|CRASHED|NONRETURN`;
`actor_sequence` is contiguous from one per actor. `schedule_step` is zero for
an unscheduled single-actor run. A scheduled gate-arrival event uses that
gate's step; work after a release and before the next gate uses the most
recently released step. No event uses a future step merely because the actor
is advancing toward it. Events are serialized only after the run, strictly by
`(numeric schedule_step, raw-ASCII actor_id,
numeric actor_sequence)`; `sequence` is the resulting contiguous 1-based
position, never RPC arrival order. All snapshot-changing actions at one step
were already applied in the same actor-ID order, so hashes and serialization
are reproducible across hosts. `sequence` is storage order, not a claim that
one actor's non-effect reads temporally preceded another's; causal assertions
use the barrier step, per-actor sequence, and before/after hashes together.
`effect_sequence` is null except on `EFFECT_APPLIED`; effect events receive the
globally contiguous `U64_DECIMAL` sequence from one in the exact order the
coordinator mutated the namespace. Replay reproduces both every before/after
hash and this sequence. At a mutation-only step, reserved `HARNESS` events are
the only events; `HARNESS` has its own contiguous `actor_sequence` and no
actor-result row.
The namespace hashes are SHA-256 IDs over
the exact restricted-canonical-JSON `ConformanceNamespaceSnapshot.v1` bytes.
`REQUESTED` always has the complete validated request, null outcome, and equal
namespace hashes. `EFFECT_APPLIED` occurs exactly once when an atom changes the
snapshot and carries the selected outcome and before/after hashes. `RETURNED`
carries request/outcome and equal current hashes. A pre-effect crash has null
outcome; a post-effect crash retains it. `NONRETURN` carries the coordinator's
typed `NONRETURN` outcome. `ACTOR_EXIT` follows its three-event rule above,
continues that actor's `actor_sequence`, and is the only terminal cleanup
event. No event field is supplied by a SUT counter.
Each actor result is exactly
`{actor_id,result_blob_content_id,status}`, where status is
`RETURNED|CRASHED|NONRETURN|PUBLIC_VALIDATION_ERROR|
PUBLIC_OPERATION_ERROR|UNEXPECTED_EXCEPTION`; only `RETURNED` has a result
blob. The coordinator appends an actor result only after the actor's
`ACTOR_EXIT/RETURNED` event, and every such event has exactly one row; an
unconfirmed live actor has none. Therefore `final_namespace` is byte-for-byte the
snapshot after the last serialized exit marker and is never recomputed by
silent teardown. Any `UNEXPECTED_EXCEPTION` forces `TRACE_MISMATCH`. Logs contain no
exception text, private name, stack, direct contact/payment data, or
SUT-supplied counter.

Before accepting an event, blob, object, or result that would exceed a count or
byte bound, the coordinator stops all workers and emits a complete
`HARNESS_RESOURCE_LIMIT_EXCEEDED` log; it reserves terminal-log space from the
start for every actor's REQUESTED/optional EFFECT_APPLIED/RETURNED exit
sequence, its response, and its actor-result row, and never truncates an
accepted event or blob. Run-state precedence is
exact:

```text
HARNESS_LIVENESS_FAILURE
> HARNESS_RESOURCE_LIMIT_EXCEEDED
> TRACE_MISMATCH
> EXTERNAL_NONRETURN
> COMPLETED_WITH_CRASHES
> COMPLETED
```

Every terminal state retains all already accepted events and exact unused
selector IDs. A watchdog expiry is liveness failure, never a product timeout.

Real native gates use six canonical preimages and one derived, test-owned
receipt. Hash agreement alone is never a native gate.

`NativeHostFacts.v1` has exact keys:

```text
artifact_directory_identity=RootOrFileIdentity
artifact_directory_protection=ArtifactDirectoryProtection
artifact_directory_storage_anchor=DirectoryStorageAnchor
platform_facts=WindowsNativeHostFacts.v1 | LinuxNativeHostFacts.v1
profile="WINDOWS_NTFS_V1" | "LINUX_LOCAL_V1"
publication_branch="WINDOWS_NT_RENAME" | "AT_EMPTY_PATH" | "PROC_SELF_FD"
schema="NativeHostFacts.v1"
```

`WindowsNativeHostFacts.v1` is exact:

```text
architecture="AMD64"
cpython_version="3.13.13"
drive_type="DRIVE_FIXED"
file_id_info=true
filesystem="NTFS"
flush_file_buffers=true
io_status_block_size="16"
nt_create_file=true
nt_set_information_file=true
nt_wait_for_single_object=true
os_build="26200"
rename_information_class="10"
rename_layout="SIZE24_OFFSETS_0_8_16_20"
schema="WindowsNativeHostFacts.v1"
```

`LinuxNativeHostFacts.v1` is exact:

```text
architecture="X86_64"
cpython_version="3.12.3"
effective_cap_dac_read_search=true | false
filesystem="EXT4"
fstatfs_magic="0xef53"
fsync=true
kernel_release="6.6.87.2-microsoft-standard-WSL2"
linkat=true
openat2=true
o_tmpfile=true
procfs_magic="0x9fa0"
statx_mnt_id=true
schema="LinuxNativeHostFacts.v1"
```

The Windows shape requires the Windows profile/branch and a Windows identity,
protection, and storage anchor. The Linux shape requires the Linux profile and
Linux values. Its effective capability is true iff the branch is
`AT_EMPTY_PATH`; false requires `PROC_SELF_FD` and the procfs fact. Every
artifact-directory identity, protection owner, and storage-anchor relation is
revalidated by the same closed rules as `ArtifactDirectoryBinding.v1`.
Unapproved versions, `/mnt/c`, non-ext4 magic, non-fixed/non-NTFS storage,
ambiguous DOS-device mapping, or a missing capability rejects the preimage
before a facade call.

`NativeNamespaceObservation.v1` has exact keys
`artifact_directory_binding_id,complete,phase,schema,slots`, where
`complete=true`, `phase="BEFORE"|"AFTER"`,
`schema="NativeNamespaceObservation.v1"`, and `slots` has 0..64 items in
strict canonical `NativeComponent` order. Each exact slot is:

```text
blob_content_id=SHA256_ID | null
component=NativeComponent
facts=BoundObjectFacts.v1 | null
state="ABSENT" | "PRESENT"
```

`ABSENT` requires both nullable fields null. `PRESENT` requires a regular-file
fact with link count one, non-null approved published-file protection, null
storage anchor, and the content ID of bytes independently read to EOF through the held
artifact-directory handle. The runner uses a dedicated native test directory,
rejects unsupported children, and records every requested target/staging
component plus every directory child; therefore `complete=true` is a
completeness claim over that held directory, not a sampled path listing.
Components are unique. The BEFORE enumeration bytes/facts are frozen before
the facade call; after runtime-generated target/stage components become known,
the runner may add only corresponding `ABSENT` rows proved by that frozen
complete enumeration. It cannot perform a later query and label it BEFORE.

`NativeInvocationDeclaration.v1` is constructed by the test case before the
native runner calls the shared core. It has exactly:

```text
arguments=<native invocation argument array>
entrypoint="BUILD_CANDIDATE" | "PUBLISH_TRANSITION"
         | "CAPTURE_OBSERVATION" | "CONSTRUCT_HANDOFF"
         | "RESUME_USER_DECISION"
schema="NativeInvocationDeclaration.v1"
```

Each argument has exact keys `name,value,value_kind`;
`value_kind="BYTES_FRAME"|"UTF8"|"NULL"`. `BYTES_FRAME` requires
`value=SHA256_ID` selecting one trace frame; `UTF8` requires a Unicode scalar
string with no NUL and at most 256 UTF-8 bytes; `NULL` requires JSON null.
Arguments are strictly raw-ASCII `name` ordered and equal the selected frozen
facade's complete keyword set:

| Entrypoint | Exact argument names and kinds |
|---|---|
| `BUILD_CANDIDATE` | `artifact_directory_locator:BYTES_FRAME`, `request_bytes:BYTES_FRAME`, `source_root_locator:BYTES_FRAME` |
| `PUBLISH_TRANSITION` | `artifact_directory_binding_bytes:BYTES_FRAME`, `canonical_record_bytes:BYTES_FRAME` |
| `CAPTURE_OBSERVATION` | `artifact_directory_binding_bytes:BYTES_FRAME`, `dispatch_bytes:BYTES_FRAME`, `invocation_outcome_bytes:BYTES_FRAME|NULL`, `phase:UTF8`, `prior_observation_bytes:BYTES_FRAME|NULL`, `source_root_locator:BYTES_FRAME` |
| `CONSTRUCT_HANDOFF` | `artifact_directory_binding_bytes:BYTES_FRAME`, `dispatch_bytes:BYTES_FRAME`, `end_observation_bytes:BYTES_FRAME`, `invocation_attempt_bytes:BYTES_FRAME`, `invocation_outcome_bytes:BYTES_FRAME`, `start_observation_bytes:BYTES_FRAME` |
| `RESUME_USER_DECISION` | `artifact_directory_binding_bytes:BYTES_FRAME`, `envelope_bytes:BYTES_FRAME` |

`CAPTURE_OBSERVATION` permits only the START/END nullability relation frozen
by the facade and `phase` is exactly `START` or `END`. Each frame ID binds the
exact raw caller argument bytes in trace `frames`. Locator frames are the
exact Python `bytes` arguments; the aggregator
independently validates their native absolute grammar, converts them to the
closed `NativeLocator` value, and requires byte equality with every
corresponding directory-open request. Every typed frame is independently
parsed under the selected entrypoint's schema and cross-record relations.
The declaration bytes are a separate aggregator preimage and its hash is
carried by the trace; a trace-embedded replacement cannot redefine the caller
input.

`NativePortTrace.v1` has exact keys:

```text
artifact_directory_binding_id=SHA256_ID
case_id=TOKEN
entrypoint="BUILD_CANDIDATE" | "PUBLISH_TRANSITION"
         | "CAPTURE_OBSERVATION" | "CONSTRUCT_HANDOFF"
         | "RESUME_USER_DECISION"
events=<NativePortTraceEvent.v1 array>
final_observation=NativeNamespaceObservation.v1
frames=<raw-byte frame array>
initial_observation=NativeNamespaceObservation.v1
invocation_declaration_sha256=SHA256_ID
profile="WINDOWS_NTFS_V1" | "LINUX_LOCAL_V1"
publication_branch="WINDOWS_NT_RENAME" | "AT_EMPTY_PATH" | "PROC_SELF_FD"
result_blob_content_id=SHA256_ID
schema="NativePortTrace.v1"
```

The frame shape, hash rule, ordering, per-frame limit, and total-byte limit are
the same as conformance `blobs`. The complete canonical trace is
1..16,777,216 bytes; the runner rejects the next frame/event before accepting
it when that ceiling could be exceeded. There are 1..4096 events in exact
execution order. Each event has exact keys
`arguments,operation,ordinal,outcome,response,schema`;
`schema="NativePortTraceEvent.v1"`, ordinal is the contiguous global
`U64_DECIMAL` sequence from one, and operation is one of the first eighteen
native-port operations above. Arguments and normal responses use those exact
rows, except native trace handles are deterministic opaque
`NATIVE_HANDLE:<open ordinal>` tokens and never contain an OS handle, PID, or
address.

The exact native event outcome is
`{kind,raw_status,schema="NativePortTraceOutcome.v1"}`. Kind is
`OK|IO_ERROR|SHORT_IO|WINDOWS_CALL_STATUS|WINDOWS_WAIT_STATUS|LINUX_ERRNO|
MISSING|UNSUPPORTED_OBJECT_TYPE|UNSUPPORTED`. `raw_status` is null except for
these closed values:

```text
WindowsNativeCallStatus = {
  iosb_status_u32: <JSON integer 0..4294967295>,
  platform: "windows",
  return_status_u32: <JSON integer 0..4294967295>,
  syscall: "NtSetInformationFile"
}
WindowsNativeWaitStatus = {
  iosb_status_u32: <JSON integer 0..4294967295>,
  platform: "windows",
  return_status_u32: <JSON integer 0..4294967295>,
  syscall: "NtWaitForSingleObject"
}
LinuxNativeLinkStatus = {
  errno: <JSON integer 0..4095>,
  platform: "linux",
  syscall: "linkat"
}
```

The operation, outcome kind, raw-status variant, and response status fields
must agree: Windows rename call/wait and Linux link use their named kind and
raw value; every other operation has null raw status. `OK` and the three
native-status kinds carry the named operation's exact normal response;
`IO_ERROR|MISSING|UNSUPPORTED` carry null; `SHORT_IO` carries only the exact
bounded prefix/count response already defined for the synthetic contract.
`UNSUPPORTED_OBJECT_TYPE` carries only
`{result=ObjectProbeResult.v1}` under the same existing-open mismatch rule as
the synthetic contract.
For the three status operations, every status repeated in `response` is
integer-equal to `raw_status`; no normalized reason may replace the raw value.
The aggregator replays
the ordered trace through an independent typed handle/byte state machine:
open ownership and kind, frame hashes/counts, read/write offsets, complete
writes, source/artifact retained-parent walks and common storage anchor,
manifest file/absence observations, flush-before-publication, branch,
no-replace flag, call/wait/IOSB resolution, final reopen, and result/record/
binding identity relations are all checked. Missing,
extra, reordered, duplicated, or semantically impossible events/frames reject
the trace.

The trace is not obtained through a production hook. A test-owned
`TransparentNativeTracePort` wraps the real production native port outside
`review_transport`, invokes each underlying method exactly once with the same
opaque capabilities/raw bytes/typed arguments, records only the exact typed
request/outcome already crossing that boundary, and returns the same
capability objects and value bytes without normalization or substitution. It
has no clock, fault, source, scheduler, retry, or namespace control. Raw
NTSTATUS/errno values come from the production native port outcome; the
observer cannot supply them.

The native runner calls the same frozen shared-core entry with that wrapped
real port. Before that call it hashes the exact immutable caller arguments,
emits `NativeInvocationDeclaration.v1`, freezes their frames, and passes those
same Python byte objects to the core; no reassignment, parse-and-reencode,
fallback input, or fixture lookup occurs between declaration and call.
Production `api_v1` calls the same entry with the same port factory
unwrapped. Import/call-graph and AST tests reject any facade branch, alternate
core, alternate native factory, trace-aware production conditional, or reverse
test import. They also reject declaration/call argument-object divergence.
Independent public-facade black-box cases run on separate
isomorphic native directories and must satisfy the same result row and
namespace relations; the event sequence applies to the observed-port run.
The receipt proves the observed native-port/shared-core
execution; the call-graph audit and black-box pair cover the thin production
wrapper. It does not falsely claim that an internal trace was extracted from
an uninstrumented public call.

Each native case has one repository-frozen
`NativeCaseExpectation.v1` preimage with exact keys:

```text
case_id=TOKEN
entrypoint="BUILD_CANDIDATE" | "PUBLISH_TRANSITION"
         | "CAPTURE_OBSERVATION" | "CONSTRUCT_HANDOFF"
         | "RESUME_USER_DECISION"
expected_events=<NativeExpectedEvent.v1 array>
expected_facade_outcome=NativeExpectedFacadeOutcome.v1
expected_relations=<strictly raw-ASCII ordered relation-token array>
expected_result_schema="BundlePublicationResult.v1"
                     | "TransitionPublicationResult.v1"
                     | "BootstrapReviewObservation.v1"
                     | "BootstrapPlanReviewHandoff.v1"
                     | "UserDecisionResumeResult.v1"
expected_staging_blob_content_id=SHA256_ID | null
invocation_rule="DECLARED_BUILD_INPUTS" | "DECLARED_TRANSITION_INPUTS"
              | "DECLARED_OBSERVATION_INPUTS" | "DECLARED_HANDOFF_INPUTS"
              | "DECLARED_RESUME_INPUTS"
profile="WINDOWS_NTFS_V1" | "LINUX_LOCAL_V1"
publication_branch="WINDOWS_NT_RENAME" | "AT_EMPTY_PATH" | "PROC_SELF_FD"
schema="NativeCaseExpectation.v1"
staging_component_rule=null | "NONE" | "BUNDLE_UUID4" | "TRANSITION_UUID4"
                       | "ATTEMPT_CONTENT_ID"
target_component_rule=null | "BUNDLE_INSTANCE_UUID"
                      | "TRANSITION_PREDECESSOR_ID"
```

`NativeExpectedFacadeOutcome.v1` is one closed tagged union:

| `kind` | Additional exact fields |
|---|---|
| `BUNDLE_PUBLICATION` | `commit_state,phase,reason_code` from one legal `BundlePublicationResult.v1` row |
| `TRANSITION_PUBLICATION` | `commit_state,phase,reason_code` from one legal `TransitionPublicationResult.v1` row |
| `OBSERVATION` | `observation_phase="START"|"END",observation_reason_code,result` from one legal `BootstrapReviewObservation.v1` row |
| `HANDOFF` | `advisory_p0,advisory_p1,advisory_verdict,state="USER_DECISION_PENDING"` |
| `USER_DECISION_RESUME` | `reason_code,state` from one legal `UserDecisionResumeResult.v1` row |

Every variant also has
`schema="NativeExpectedFacadeOutcome.v1"` and no fields from another variant.
The variant, result schema, entrypoint, and invocation rule have a bijective
five-row mapping.

Each expected event is exact
`{operation,ordinal,outcome_kind,raw_status,
schema="NativeExpectedEvent.v1"}` and the complete array must match trace
length, order, operations, outcome kinds, and raw statuses. It has 1..4096
items. `expected_relations` has 1..16 unique tokens. A BUILD, transition, or
resume case that reaches a native publication atom contains at least one
non-null raw status. Observation and handoff cases, and resume paths that stop
before publication, require every raw status null. The expected facade outcome
must be one legal row of the selected frozen result/record truth table.
`DECLARED_BUILD_INPUTS` is legal exactly for `BUILD_CANDIDATE`;
`DECLARED_TRANSITION_INPUTS` is legal exactly for `PUBLISH_TRANSITION`;
the other three rules are legal exactly for their same-named entrypoints. The
closed relation tokens and
their exact assertions are:

| Token | Required relation |
|---|---|
| `INITIAL_TARGET_ABSENT` | The initial target slot is absent. |
| `FINAL_TARGET_ABSENT` | The final target slot is absent. |
| `FINAL_TARGET_IS_RESULT_OBJECT` | The final target is present; its independently read content ID equals the result's bundle content ID or transition record content ID, and its identity equals the result object identity. |
| `FINAL_TARGET_ABSENT_AFTER_COMMIT` | A definite native commit event exists, but the complete final observation has no target. This is legal only for `PUBLISHED_UNCONFIRMED`. |
| `FINAL_TARGET_NOT_RESULT_OBJECT_AFTER_COMMIT` | A definite native commit event exists and the final target is present, but its content ID or identity differs from the result object. This is legal only for `PUBLISHED_UNCONFIRMED`. |
| `INITIAL_COMPETITOR_UNCHANGED` | The target is present initially and its complete slot is byte-identical after the call; the result bytes/identity were not installed there. |
| `UNKNOWN_TARGET_MATCHES_OBSERVATION` | The target and stage were absent initially; afterward exactly one is present with the expected complete bytes/result identity and the other is absent, while the public result remains `PUBLICATION_OUTCOME_UNKNOWN`. |
| `WINDOWS_STAGE_RETAINED` | The final staging slot is present with `expected_staging_blob_content_id`; if the result object identity is non-null, the slot identity equals it. This token makes no target claim. |
| `WINDOWS_STAGE_ABSENT` | The final staging slot is absent. |
| `LINUX_NO_NAMED_STAGE` | Staging component is null and neither observation contains a synthetic staging name. |
| `NO_UNDECLARED_DIRECTORY_CHANGE` | Every complete slot not selected as target/staging is byte-identical before and after. |
| `OBSERVATION_READ_ONLY` | The complete BEFORE and AFTER artifact-directory observations are byte-identical; the trace contains the exact source and transition reads implied by the declared START/END inputs. |
| `HANDOFF_READ_ONLY` | The complete BEFORE and AFTER observations are byte-identical; all handoff output fields derive from the six declared input frames. |
| `RESUME_RESULT_MATCHES_NAMESPACE` | The aggregator derives every attempt/decision/failure slot from the declared envelope and chain, then requires the returned resume row, all native publication statuses, and complete AFTER occupants to agree. |

The target rule is `BUNDLE_INSTANCE_UUID` iff the entrypoint is
`BUILD_CANDIDATE`; it is `TRANSITION_PREDECESSOR_ID` for
`PUBLISH_TRANSITION`; both target and staging rules are null for the other
three entrypoints. The aggregator
derives the exact component from the validated result and requires equality
with its locator basename, every trace publication argument, and the
observation slot. For BUILD/PUBLISH, a Linux case uses
`staging_component_rule=NONE`; Windows uses the bundle UUID or transition UUID
rule exactly as selected by entrypoint and record schema. Resume attempt-stage
relations are instead derived by `RESUME_RESULT_MATCHES_NAMESPACE`, so they
cannot be replaced by a caller-selected staging rule.
The UUID rules bind the exact `UUID4_READ` trace value; no repository-frozen
fixture pretends to know a runtime UUID. The derived stage component must
equal the result's non-null staging-locator basename whenever that field is
present.

`expected_staging_blob_content_id` is non-null exactly when
`WINDOWS_STAGE_RETAINED` is selected and is null for the three non-publication
target-rule entrypoints. `CAPTURE_OBSERVATION` requires
`OBSERVATION_READ_ONLY`; `CONSTRUCT_HANDOFF` requires
`HANDOFF_READ_ONLY`; `RESUME_USER_DECISION` requires
`RESUME_RESULT_MATCHES_NAMESPACE`. Relation combinations for BUILD/PUBLISH are
closed by result truth: confirmed publication requires
`INITIAL_TARGET_ABSENT`, `FINAL_TARGET_IS_RESULT_OBJECT`, and
`WINDOWS_STAGE_ABSENT` or `LINUX_NO_NAMED_STAGE`. Unconfirmed publication
requires `INITIAL_TARGET_ABSENT`, a definite-success native commit status, and
exactly one of `FINAL_TARGET_IS_RESULT_OBJECT`,
`FINAL_TARGET_ABSENT_AFTER_COMMIT`, or
`FINAL_TARGET_NOT_RESULT_OBJECT_AFTER_COMMIT`; Windows also requires
`WINDOWS_STAGE_ABSENT`, while Linux requires `LINUX_NO_NAMED_STAGE`. The later
observation does not change the already recorded commit fact into a confirmed
identity claim. Collision requires
`INITIAL_COMPETITOR_UNCHANGED` plus `WINDOWS_STAGE_RETAINED` on Windows or
`LINUX_NO_NAMED_STAGE` on Linux. Other definite Windows precommit
nonpublication requires `INITIAL_TARGET_ABSENT` and `FINAL_TARGET_ABSENT`,
plus `WINDOWS_STAGE_RETAINED` exactly when the result exposes a staging
locator and `WINDOWS_STAGE_ABSENT` otherwise. Other definite Linux
nonpublication requires `INITIAL_TARGET_ABSENT`, `FINAL_TARGET_ABSENT`, and
`LINUX_NO_NAMED_STAGE`. Unknown Windows publication requires only its unknown
relation for target/stage occupancy. No case may claim both a retained stage
and installed target. Every combination includes
`NO_UNDECLARED_DIRECTORY_CHANGE`. These assertions prove observation truth
without converting a later observation into authority or durability.

R11A also freezes canonical `NativeCaseCatalog.v1` bytes with exact keys
`cases,schema="NativeCaseCatalog.v1"`. It has 1..4096 cases in strictly
raw-ASCII `case_id` order and is 1..2,097,152 bytes. Each exact case is:

```text
case_expectation_sha256=SHA256_ID
case_id=TOKEN
entrypoint="BUILD_CANDIDATE" | "PUBLISH_TRANSITION"
         | "CAPTURE_OBSERVATION" | "CONSTRUCT_HANDOFF"
         | "RESUME_USER_DECISION"
profile="WINDOWS_NTFS_V1" | "LINUX_LOCAL_V1"
required_host="WINDOWS_NTFS_V1" | "LINUX_LOCAL_V1"
schema="NativeCaseCatalogEntry.v1"
```

Each ID and expectation hash is unique; the catalog entry must equal its
expectation's case/profile/entrypoint fields. The test-owned aggregator freezes
the reviewed catalog SHA-256 as a code constant and accepts an expectation
only when its hash is the one registered for that case. The caller cannot
supply or replace the catalog. A changed catalog is an R11A fixture/code
change requiring the same independent test-quality review; an arbitrary
self-serving expectation cannot mint a receipt.

The test-only endpoint is frozen at
`evaluation.aegis_v2.tests.native_conformance_evidence.aggregate_native_conformance_evidence`:

```python
def aggregate_native_conformance_evidence(
    *,
    artifact_directory_binding_bytes: bytes,
    case_expectation_bytes: bytes,
    host_facts_bytes: bytes,
    invocation_declaration_bytes: bytes,
    native_trace_bytes: bytes,
    result_bytes: bytes,
) -> bytes: ...
```

It accepts the six raw preimages, never caller-supplied hashes or a
`native_status_observed` flag. It independently parses each canonical schema,
with byte ceilings 65,536 for binding, 2,097,152 for expectation, 65,536 for
host facts, 65,536 for invocation declaration, 16,777,216 for trace, and
2,097,152 for result. A ceiling is checked before decode/tree allocation or
canonical parse; oversize, truncated, or trailing bytes reject without a
partial receipt.

The aggregator recomputes the invocation-declaration hash and requires exact
equality with `NativePortTrace.v1.invocation_declaration_sha256`. It requires
the declaration entrypoint to equal the trace, registered expectation,
result-schema-derived entrypoint, and shared-core lifecycle entrypoint. Every
`BYTES_FRAME` argument must select one byte-identical trace frame whose
independently recomputed ID matches; `UTF8` and `NULL` values must match their
facade call objects exactly. It then independently replays the declared caller
input:

- `BUILD_CANDIDATE`: validate the exact source-root and artifact-directory
  locator frames under the selected native pathname grammar, convert each to
  its exact `NativeLocator`, and require them at the state-machine-designated
  source/artifact `DIRECTORY_OPEN` requests. Independently parse the exact
  request frame as canonical `CandidateDomainRequest.v1`; every request-derived
  manifest field, capture selection, result relation, and port argument that
  exists on the reached result path must equal that request. The resulting
  binding locator must equal the declared artifact-directory locator.
- `PUBLISH_TRANSITION`: require the declared binding frame byte-identical to
  the separate `artifact_directory_binding_bytes` preimage, independently
  parse the declared record frame as the exact canonical transition schema,
  validate their binding/content/predecessor relations, derive the binding
  locator used by every artifact-directory `DIRECTORY_OPEN`, and require the
  exact record bytes/content ID at every write, verification, publication-slot,
  and public-result relation reached by the frozen transition state machine.
- `CAPTURE_OBSERVATION`: validate binding, dispatch, source locator, phase,
  START/null prior relation, and invocation-outcome/null relation; require
  every bundle/source read, live-domain fact, predecessor, advisory field, and
  returned observation byte to derive from those declared values.
- `CONSTRUCT_HANDOFF`: independently parse the binding, dispatch, START,
  invocation attempt, invocation outcome, and END frames; verify the complete
  predecessor/request/advisory relation and require every returned handoff
  field to derive from them with zero namespace mutation.
- `RESUME_USER_DECISION`: independently parse the binding/envelope and every
  deterministically reached chain record; derive attempt/decision/failure
  bytes and slots, replay every publication status and namespace effect, and
  require exact equality with the returned resume truth-table row.

Thus replacing caller input A with a self-consistent trace/result for B cannot
mint a receipt. The aggregator also validates the exact native-origin
`ArtifactDirectoryBinding.v1`, and requires its identity/protection/anchor to
equal host facts and its ID to equal trace/observation/result fields wherever
the result carries that operand. For `BUILD_CANDIDATE`, its locator,
instance, and observation UTC must also equal the exact directory-open,
`UUID4_READ`, and `UTC_READ` values selected by the frozen builder state
machine; for every other entrypoint it must be byte-identical to the declared
facade input. Case/profile/entrypoint/branch and
result-content relations must also agree. It validates the public result with its
frozen validator. Publication/resume results must carry
`evidence_origin=NATIVE_RUNTIME`; observation/handoff records have no origin
field and instead must bind the separately supplied exact native-origin
artifact-directory binding without adding one. It checks the exact
expectation row, replays the native trace, checks every namespace relation,
and derives `native_status_observed=true` only when at least one expected
non-null raw status exists and all such statuses match. It derives false only
when the expectation permits no raw status and the trace contains none. It
then returns exact
`NativeConformanceEvidence.v1`:

```text
artifact_directory_binding_id=SHA256_ID
authority_verified=false
case_catalog_sha256=SHA256_ID
case_expectation_sha256=SHA256_ID
case_id=TOKEN
evidence_origin="NATIVE_RUNTIME"
host_facts_sha256=SHA256_ID
invocation_declaration_sha256=SHA256_ID
native_status_observed=true | false
native_trace_complete=true
native_trace_sha256=SHA256_ID
profile="WINDOWS_NTFS_V1" | "LINUX_LOCAL_V1"
result_bytes_sha256=SHA256_ID
schema="NativeConformanceEvidence.v1"
```

This receipt is issued only after a valid artifact-directory binding exists;
tests that deliberately reject a host before binding prove that result
directly and cannot manufacture native evidence. R11A freezes every
expectation byte string/hash, the catalog bytes/hash, and supplies independent
one-field, one-status, event-order, frame, identity, target, stage, and
competitor mutation witnesses. R11C stores all six preimages beside the
receipt so any gate can rerun aggregation; a detached receipt, detached
result, hash-only tuple, producer-set status flag, or missing preimage fails.
The native runner and its trace collector remain within the explicitly
reviewed test-runner integrity boundary; this evidence is not authentication,
authority, or power-loss proof. It is never accepted by production
`validate_record_bytes`. The synthetic facade cannot emit it, and no
synthetic event log/result can satisfy its native-origin, approved-host,
raw-status, or namespace-observation relations.

Production isolation is mandatory:

```text
review_transport_conformance -> shared orchestration core
tests/native_trace_port       -> production native port + shared core
review_transport.api_v1       -> shared orchestration core
review_transport              -X-> review_transport_conformance
review_transport              -X-> evaluation.aegis_v2.tests
```

Production facade signatures contain no injection parameter and construct only
native ports. Production code reads no conformance environment variable,
configuration, argv, registry value, or module global. The conformance package
is not re-exported by production, cannot resolve a model locator to a real
path, and is excluded from every production wheel/sdist/source manifest.
Import-graph, AST-signature, environment-pollution, and archive-membership
tests enforce this direction. Conformance workers can construct only
`SYNTHETIC_CONFORMANCE` bindings/results; stateful production entries reject
that taint before namespace I/O. Synthetic logs can never satisfy the required
real NTFS/native-ext4 positive, collision, buffer, identity, or no-replace
evidence. `evidence_origin` is an enforced information-flow taint, not user,
host, or reviewer authentication.
`orchestration_core.py` imports only platform-neutral value/port contracts and
never imports `windows_bound_io.py` or `posix_bound_io.py`; production
`api_v1.py` performs the host selection, while conformance workers import
neither native module. This import rule is what makes both model profiles
portable on both hosts.
The shared port contract contains opaque handle capabilities, raw immutable
bytes, `ObjectProbeResult.v1`, `BoundObjectFacts.v1`, typed source values, and
typed operation outcomes. Conformance content IDs, frames, object keys,
selectors, controls, and schedule steps exist only outside that contract in
the RPC adapter and coordinator.

### Publication and error state

The builder/publisher returns only `BundlePublicationResult.v1` with exact
keys:

```text
schema="BundlePublicationResult.v1"
evidence_origin = NATIVE_RUNTIME | SYNTHETIC_CONFORMANCE
profile = WINDOWS_NTFS_V1 | LINUX_LOCAL_V1 | null
phase = INPUT | PLATFORM | INSTANCE | ROOT | CAPTURE | CANDIDATE_CREATE
      | CANDIDATE_WRITE | CANDIDATE_VERIFY | PUBLISH | POSTCOMMIT
reason_code
commit_state = NOT_PUBLISHED
             | PUBLICATION_OUTCOME_UNKNOWN
             | PUBLISHED_UNCONFIRMED
             | PUBLISHED_CONFIRMED
content_id = SHA256_ID | null
review_domain_id = SHA256_ID | null
instance_id = UUID4 | null
source_root_identity = RootIdentity | null
artifact_directory_binding = ArtifactDirectoryBinding.v1 | null
artifact_directory_binding_id = SHA256_ID | null
artifact_locator = NativeLocator | null
staging_origin_locator = NativeLocator | null
object_identity = RootOrFileIdentity | null
confirmation_scope = CURRENT_RUNTIME_ONLY
power_loss_durable = false
authority_verified = false
```

`NativeLocator` is either
`{"encoding":"POSIX_BYTES_HEX","value":"<2..8190 lowercase hex chars with even
length>"}` or
`{"encoding":"UTF16LE_HEX","value":"<12..16384 lowercase hex chars whose length
is divisible by four>"}`. It obeys the same lexical grammar above. A result
locator's decoded form is the exact bound parent locator plus one separator and
the validated final/staging component. This composition is structural; a
confirmed publication additionally verifies the named object through the
retained parent, while an unknown Windows rename outcome deliberately cannot
make that claim. A locator is navigation evidence, not object identity.

Across both publication-result schemas, every non-null
`source_root_identity`/`object_identity` platform and every non-null locator
encoding must match `profile`: Linux permits only Linux identities and
`POSIX_BYTES_HEX`; Windows permits only Windows identities and
`UTF16LE_HEX`. This relation is fully present in the result and the standalone
validator rejects every mixed tuple.

Controlled pre-commit failure is `NOT_PUBLISHED`. Linux closes the unnamed
inode; Windows retains the exact staging path/FileId for operator action and
performs no pathname cleanup. A final-name competitor is never replaced,
renamed, truncated, or deleted. Successful
`linkat`/`NtSetInformationFile(FileRenameInformation)` is the commit point.
Any later reopen, identity, flush, or directory-fsync failure is
`PUBLISHED_UNCONFIRMED`; the published file remains untouched. Only a
same-object reopen plus required final flushes yields `PUBLISHED_CONFIRMED`.
No post-commit result attempts rollback. `PUBLISHED_CONFIRMED` means only that
the current process observed the same named object and completed the specified
flush calls. Windows has no directory-durability proof; Linux filesystem
behavior is not a power-loss test. Every row therefore carries
`confirmation_scope=CURRENT_RUNTIME_ONLY` and
`power_loss_durable=false`.

`BundlePublicationReason` is closed:

```text
OK
INVALID_DOMAIN_REQUEST
INVALID_PATH
INPUT_LIMIT_EXCEEDED
UNRECOGNIZED_PLATFORM
UNSUPPORTED_PLATFORM
PLATFORM_LIMIT_EXCEEDED
INSTANCE_ID_SOURCE_FAILED
CAPTURE_START_TIME_SOURCE_FAILED
INSTANCE_LIMIT_EXCEEDED
ARTIFACT_DIRECTORY_INVALID
ROOT_OPEN_FAILED
ROOT_LIMIT_EXCEEDED
SOURCE_ROOT_MISMATCH
SOURCE_CHANGED
INVALID_DOMAIN
REQUIRED_FILE_MISSING
REQUIRED_ABSENCE_PRESENT
UNSUPPORTED_FILE_TYPE
CAPTURE_LIMIT_EXCEEDED
SOURCE_IO_FAILED
CAPTURE_END_TIME_SOURCE_FAILED
CANDIDATE_CREATE_FAILED
CANDIDATE_CREATE_LIMIT_EXCEEDED
CANDIDATE_CREATED_OBJECT_QUERY_FAILED
CANDIDATE_CREATED_LIMIT_EXCEEDED
CANDIDATE_WRITE_FAILED
CANDIDATE_SEAL_FAILED
CANDIDATE_WRITE_LIMIT_EXCEEDED
CANDIDATE_VERIFY_FAILED
NONCANONICAL_CONTAINER
CANDIDATE_VERIFY_LIMIT_EXCEEDED
FINAL_NAME_EXISTS
PUBLICATION_PRIMITIVE_UNSUPPORTED
PUBLICATION_FAILED
PUBLISH_LIMIT_EXCEEDED
ARTIFACT_DIRECTORY_PREPUBLISH_OPEN_FAILED
ARTIFACT_DIRECTORY_PREPUBLISH_IDENTITY_MISMATCH
ARTIFACT_DIRECTORY_PREPUBLISH_STORAGE_ANCHOR_MISMATCH
ARTIFACT_DIRECTORY_PREPUBLISH_PROTECTION_MISMATCH
ARTIFACT_DIRECTORY_PREPUBLISH_PROFILE_UNSUPPORTED
WINDOWS_RENAME_OUTCOME_UNKNOWN
ARTIFACT_DIRECTORY_POSTCOMMIT_UNCONFIRMED
PUBLISHED_IDENTITY_UNCONFIRMED
PUBLISHED_FLUSH_UNCONFIRMED
POSTCOMMIT_LIMIT_EXCEEDED
```

The publication-result truth table is bidirectional:

| Reason codes | Phase / commit state | Required non-null | Required null |
|---|---|---|---|
| `INVALID_DOMAIN_REQUEST`, `INVALID_PATH`, `INPUT_LIMIT_EXCEEDED` | `INPUT / NOT_PUBLISHED` | none of the conditional fields | profile, all IDs/identities/locators |
| `UNRECOGNIZED_PLATFORM` | `PLATFORM / NOT_PUBLISHED` | none of the conditional fields | profile, all IDs/identities/locators |
| `UNSUPPORTED_PLATFORM`, `PLATFORM_LIMIT_EXCEEDED` | `PLATFORM / NOT_PUBLISHED` | profile | all IDs/identities/locators |
| `INSTANCE_ID_SOURCE_FAILED`, `INSTANCE_LIMIT_EXCEEDED` | `INSTANCE / NOT_PUBLISHED` | profile | all IDs/identities/locators |
| `CAPTURE_START_TIME_SOURCE_FAILED`, `ARTIFACT_DIRECTORY_INVALID`, `ROOT_OPEN_FAILED`, `ROOT_LIMIT_EXCEEDED` | `ROOT / NOT_PUBLISHED` | profile, instance ID | root/domain/content/object/locators |
| `SOURCE_ROOT_MISMATCH`, `SOURCE_CHANGED`, `INVALID_DOMAIN`, `REQUIRED_FILE_MISSING`, `REQUIRED_ABSENCE_PRESENT`, `UNSUPPORTED_FILE_TYPE`, `CAPTURE_LIMIT_EXCEEDED`, `SOURCE_IO_FAILED`, `CAPTURE_END_TIME_SOURCE_FAILED` | `CAPTURE / NOT_PUBLISHED` | profile, instance ID, source-root identity | domain/content/object/locators |
| `CANDIDATE_CREATE_FAILED`, `CANDIDATE_CREATE_LIMIT_EXCEEDED` | `CANDIDATE_CREATE / NOT_PUBLISHED` | profile, instance ID, source-root identity, review-domain ID | content/object/locators |
| `CANDIDATE_CREATED_OBJECT_QUERY_FAILED`, `CANDIDATE_CREATED_LIMIT_EXCEEDED` | `CANDIDATE_CREATE / NOT_PUBLISHED` | profile, instance ID, source-root identity, review-domain ID; Windows staging-origin locator only | content ID, object identity, artifact locator; Linux staging-origin locator |
| `CANDIDATE_WRITE_FAILED`, `CANDIDATE_SEAL_FAILED`, `CANDIDATE_WRITE_LIMIT_EXCEEDED` | `CANDIDATE_WRITE / NOT_PUBLISHED` | profile, instance ID, source-root identity, review-domain ID, object identity; Windows staging-origin locator only | content ID, artifact locator; Linux staging-origin locator |
| `CANDIDATE_VERIFY_FAILED`, `NONCANONICAL_CONTAINER`, `CANDIDATE_VERIFY_LIMIT_EXCEEDED` | `CANDIDATE_VERIFY / NOT_PUBLISHED` | profile, all IDs/identities; Windows staging-origin locator only | artifact locator; Linux staging-origin locator |
| `FINAL_NAME_EXISTS`, `PUBLICATION_PRIMITIVE_UNSUPPORTED`, `PUBLICATION_FAILED`, `PUBLISH_LIMIT_EXCEEDED`, `ARTIFACT_DIRECTORY_PREPUBLISH_OPEN_FAILED`, `ARTIFACT_DIRECTORY_PREPUBLISH_IDENTITY_MISMATCH`, `ARTIFACT_DIRECTORY_PREPUBLISH_STORAGE_ANCHOR_MISMATCH`, `ARTIFACT_DIRECTORY_PREPUBLISH_PROTECTION_MISMATCH`, `ARTIFACT_DIRECTORY_PREPUBLISH_PROFILE_UNSUPPORTED` | `PUBLISH / NOT_PUBLISHED` | profile, all IDs/identities; Windows staging-origin locator only | artifact locator; Linux staging-origin locator |
| `WINDOWS_RENAME_OUTCOME_UNKNOWN` | `PUBLISH / PUBLICATION_OUTCOME_UNKNOWN` | Windows profile, all IDs/identities, artifact locator, staging-origin locator | none of the conditional fields |
| `ARTIFACT_DIRECTORY_POSTCOMMIT_UNCONFIRMED`, `PUBLISHED_IDENTITY_UNCONFIRMED`, `PUBLISHED_FLUSH_UNCONFIRMED`, `POSTCOMMIT_LIMIT_EXCEEDED` | `POSTCOMMIT / PUBLISHED_UNCONFIRMED` | profile, all IDs/identities, artifact locator; Windows staging-origin locator only | Linux staging-origin locator |
| `OK` | `POSTCOMMIT / PUBLISHED_CONFIRMED` | profile, all IDs/identities, artifact locator; Windows staging-origin locator only | Linux staging-origin locator |

No other reason/state/phase combination is legal. `OK` is equivalent to
`PUBLISHED_CONFIRMED`; every non-OK row has `authority_verified=false`,
`power_loss_durable=false`, and never exposes a success boolean. The standalone
result validator rejects every mutation that violates canonical bytes, a
grammar/bound, a platform-tagged union, a fixed value, this truth table, or a
cross-field relation whose complete operands are present in the result. It
cannot prove that a different but well-formed observed identity is true, nor
can it infer the parent of a well-formed locator when the result contains no
binding preimage. Those substitutions may remain structurally valid and must
instead be rejected by the producing runtime trace/reopen oracle or by a bound
consumer that also receives the exact binding bytes. R11A pairs each such
substitution with both controls: standalone structural acceptance and bound
semantic rejection. Claiming standalone rejection would invent information
absent from the value. The table's “all IDs/identities” shorthand states
presence, platform grammar, and nullability only and excludes the two binding
fields:
`artifact_directory_binding` and `artifact_directory_binding_id` are both
non-null only for `OK/PUBLISHED_CONFIRMED`, must hash/match each other and the
instance/profile/artifact-locator parent, must share the result's
`evidence_origin`, and are both null for every other row. Production builder
rows always use `NATIVE_RUNTIME`; conformance builder rows always use
`SYNTHETIC_CONFORMANCE`.

Transition records do not pretend to be bundles. Their publisher returns the
separate exact `TransitionPublicationResult.v1`:

```text
schema="TransitionPublicationResult.v1"
evidence_origin = NATIVE_RUNTIME | SYNTHETIC_CONFORMANCE
profile = WINDOWS_NTFS_V1 | LINUX_LOCAL_V1
phase = DIRECTORY | CREATE | WRITE | VERIFY | PUBLISH | POSTCOMMIT
reason_code = TransitionPublicationReason
commit_state = NOT_PUBLISHED
             | PUBLICATION_OUTCOME_UNKNOWN
             | PUBLISHED_UNCONFIRMED
             | PUBLISHED_CONFIRMED
predecessor_content_id = SHA256_ID
artifact_directory_binding_id = SHA256_ID
record_content_id = SHA256_ID
record_schema = ReviewDispatchObservation.v1
              | BootstrapReviewObservation.v1
              | ReviewerInvocationAttempt.v1
              | ReviewerInvocationOutcome.v1
              | BootstrapPlanReviewHandoff.v1
              | UserDecisionAttempt.v1
              | UserDecisionObservation.v1
              | BootstrapReviewFailure.v1
transition_locator = NativeLocator
staging_origin_locator = NativeLocator | null
object_identity = RootOrFileIdentity | null
confirmation_scope = CURRENT_RUNTIME_ONLY
power_loss_durable = false
authority_verified = false
```

`record_content_id` is independently recomputed before write and after
reopen. `transition_locator` is derived from the retained artifact-directory
handle plus the deterministic component; it is always non-null and is not an
identity claim. `TransitionPublicationReason` is closed:

```text
OK
ARTIFACT_DIRECTORY_OPEN_FAILED
ARTIFACT_DIRECTORY_INVALID
ARTIFACT_DIRECTORY_IDENTITY_MISMATCH
ARTIFACT_DIRECTORY_PROFILE_UNSUPPORTED
ARTIFACT_DIRECTORY_LIMIT_EXCEEDED
TRANSITION_CREATE_FAILED
TRANSITION_CREATE_LIMIT_EXCEEDED
TRANSITION_CREATED_OBJECT_QUERY_FAILED
TRANSITION_CREATED_LIMIT_EXCEEDED
TRANSITION_WRITE_FAILED
TRANSITION_SEAL_FAILED
TRANSITION_WRITE_LIMIT_EXCEEDED
TRANSITION_VERIFY_FAILED
NONCANONICAL_RECORD
TRANSITION_VERIFY_LIMIT_EXCEEDED
TRANSITION_SLOT_OCCUPIED
PUBLICATION_PRIMITIVE_UNSUPPORTED
TRANSITION_PUBLICATION_FAILED
TRANSITION_PUBLISH_LIMIT_EXCEEDED
ARTIFACT_DIRECTORY_PREPUBLISH_OPEN_FAILED
ARTIFACT_DIRECTORY_PREPUBLISH_IDENTITY_MISMATCH
ARTIFACT_DIRECTORY_PREPUBLISH_STORAGE_ANCHOR_MISMATCH
ARTIFACT_DIRECTORY_PREPUBLISH_PROTECTION_MISMATCH
ARTIFACT_DIRECTORY_PREPUBLISH_PROFILE_UNSUPPORTED
WINDOWS_RENAME_OUTCOME_UNKNOWN
ARTIFACT_DIRECTORY_POSTCOMMIT_UNCONFIRMED
TRANSITION_IDENTITY_UNCONFIRMED
TRANSITION_FLUSH_UNCONFIRMED
TRANSITION_POSTCOMMIT_LIMIT_EXCEEDED
```

Its phase/state/nullability table is also bidirectional:

| Reason codes | Phase / commit state | `object_identity` | `staging_origin_locator` |
|---|---|---|---|
| `ARTIFACT_DIRECTORY_OPEN_FAILED`, `ARTIFACT_DIRECTORY_INVALID`, `ARTIFACT_DIRECTORY_IDENTITY_MISMATCH`, `ARTIFACT_DIRECTORY_PROFILE_UNSUPPORTED`, `ARTIFACT_DIRECTORY_LIMIT_EXCEEDED` | `DIRECTORY / NOT_PUBLISHED` | null | null |
| `TRANSITION_CREATE_FAILED`, `TRANSITION_CREATE_LIMIT_EXCEEDED` | `CREATE / NOT_PUBLISHED` | null | null |
| `TRANSITION_CREATED_OBJECT_QUERY_FAILED`, `TRANSITION_CREATED_LIMIT_EXCEEDED` | `CREATE / NOT_PUBLISHED` | null | Windows non-null; Linux null |
| `TRANSITION_WRITE_FAILED`, `TRANSITION_SEAL_FAILED`, `TRANSITION_WRITE_LIMIT_EXCEEDED` | `WRITE / NOT_PUBLISHED` | non-null | Windows non-null; Linux null |
| `TRANSITION_VERIFY_FAILED`, `NONCANONICAL_RECORD`, `TRANSITION_VERIFY_LIMIT_EXCEEDED` | `VERIFY / NOT_PUBLISHED` | non-null | Windows non-null; Linux null |
| `TRANSITION_SLOT_OCCUPIED`, `PUBLICATION_PRIMITIVE_UNSUPPORTED`, `TRANSITION_PUBLICATION_FAILED`, `TRANSITION_PUBLISH_LIMIT_EXCEEDED`, `ARTIFACT_DIRECTORY_PREPUBLISH_OPEN_FAILED`, `ARTIFACT_DIRECTORY_PREPUBLISH_IDENTITY_MISMATCH`, `ARTIFACT_DIRECTORY_PREPUBLISH_STORAGE_ANCHOR_MISMATCH`, `ARTIFACT_DIRECTORY_PREPUBLISH_PROTECTION_MISMATCH`, `ARTIFACT_DIRECTORY_PREPUBLISH_PROFILE_UNSUPPORTED` | `PUBLISH / NOT_PUBLISHED` | non-null | Windows non-null; Linux null |
| `WINDOWS_RENAME_OUTCOME_UNKNOWN` | `PUBLISH / PUBLICATION_OUTCOME_UNKNOWN` | non-null Windows identity | non-null Windows locator |
| `ARTIFACT_DIRECTORY_POSTCOMMIT_UNCONFIRMED`, `TRANSITION_IDENTITY_UNCONFIRMED`, `TRANSITION_FLUSH_UNCONFIRMED`, `TRANSITION_POSTCOMMIT_LIMIT_EXCEEDED` | `POSTCOMMIT / PUBLISHED_UNCONFIRMED` | non-null | Windows non-null; Linux null |
| `OK` | `POSTCOMMIT / PUBLISHED_CONFIRMED` | non-null | Windows non-null; Linux null |

Every row requires non-null profile, artifact-directory binding ID,
predecessor ID, record ID, record schema, and transition locator plus the three
fixed non-authority/durability fields and `evidence_origin`. The DIRECTORY row derives its
non-authoritative transition locator from the validated binding and canonical
record before attempting the open; it performs zero namespace mutation.
Malformed binding/record input or a record binding-ID mismatch raises
`ReviewTransportValidationError` before this table. No other combination is
legal. Its standalone validator has the same information boundary as the
bundle result: it validates locator/identity grammar, platform, nullability,
and internal relations, but only a caller holding the binding preimage and
runtime evidence can validate locator parentage or observational truth.
Transition publication uses the same frozen
native Windows status machine and Linux branch as bundle publication but the
transition component grammar, result schema, and record parser above. In that
context a definite collision/EEXIST maps to `TRANSITION_SLOT_OCCUPIED`, a
definite unsupported primitive maps to
`PUBLICATION_PRIMITIVE_UNSUPPORTED`, any other definite publication failure
maps to `TRANSITION_PUBLICATION_FAILED`, and unresolved Windows status maps to
`WINDOWS_RENAME_OUTCOME_UNKNOWN`.

`BootstrapFailureReason` is closed and occurs only in
`BootstrapReviewFailure.v1`:

```text
REVIEWER_PROVISION_FAILED
INVALID_DISPATCH
DISPATCH_PERSISTENCE_FAILED
START_OBSERVATION_CONSTRUCTION_FAILED
START_PERSISTENCE_FAILED
START_OBSERVATION_REJECTED
REVIEW_INVOCATION_ATTEMPT_CONSTRUCTION_FAILED
REVIEW_INVOCATION_RESERVATION_FAILED
ADVISORY_RESULT_MISSING
ADVISORY_RESULT_INVALID
REVIEW_INVOCATION_OUTCOME_PERSISTENCE_FAILED
END_OBSERVATION_CONSTRUCTION_FAILED
END_PERSISTENCE_FAILED
END_OBSERVATION_REJECTED
HANDOFF_INVALID
HANDOFF_PERSISTENCE_FAILED
USER_DECISION_PERSISTENCE_FAILED
```

The failure state/reason/predecessor/nullability matrix is bidirectional:

| `failed_state` | Permitted `reason_code` | Required predecessor | `review_run_id` | `persistence_reason_code` | User-decision binding |
|---|---|---|---|---|---|
| `CANDIDATE_PUBLISHED` | `REVIEWER_PROVISION_FAILED` | snapshot content ID | null | null | all six null |
| `CANDIDATE_PUBLISHED` | `INVALID_DISPATCH` | snapshot content ID | non-null | null | all six null |
| `CANDIDATE_PUBLISHED` | `DISPATCH_PERSISTENCE_FAILED` | snapshot content ID | non-null | non-null | all six null |
| `DISPATCH_RECORDED` | `START_OBSERVATION_CONSTRUCTION_FAILED` | dispatch content ID | non-null | null | all six null |
| `DISPATCH_RECORDED` | `START_PERSISTENCE_FAILED` | dispatch content ID | non-null | non-null | all six null |
| `START_REJECTED` | `START_OBSERVATION_REJECTED` | rejected START observation content ID | non-null | null | all six null |
| `START_PERSISTED` | `REVIEW_INVOCATION_ATTEMPT_CONSTRUCTION_FAILED`, `REVIEW_INVOCATION_RESERVATION_FAILED` | matched START observation content ID | non-null | non-null only for `REVIEW_INVOCATION_RESERVATION_FAILED` | all six null |
| `REVIEW_INVOCATION_RESERVED` | `ADVISORY_RESULT_MISSING`, `ADVISORY_RESULT_INVALID`, `REVIEW_INVOCATION_OUTCOME_PERSISTENCE_FAILED` | invocation-attempt content ID | non-null | non-null only for `REVIEW_INVOCATION_OUTCOME_PERSISTENCE_FAILED` | all six null |
| `REVIEW_INVOCATION_OUTCOME_OBSERVED` | `END_OBSERVATION_CONSTRUCTION_FAILED`, `END_PERSISTENCE_FAILED` | invocation-outcome content ID | non-null | non-null only for `END_PERSISTENCE_FAILED` | all six null |
| `END_REJECTED` | `END_OBSERVATION_REJECTED` | rejected END observation content ID | non-null | null | all six null |
| `END_PERSISTED` | `HANDOFF_INVALID`, `HANDOFF_PERSISTENCE_FAILED` | matched END observation content ID | non-null | non-null only for `HANDOFF_PERSISTENCE_FAILED` | all six null |
| `USER_DECISION_ATTEMPT_RESERVED` | `USER_DECISION_PERSISTENCE_FAILED` | attempt content ID | non-null | non-null | attempt ID/ordinal, attempted decision ID, intended decision, request hash, and complete decision transition result all non-null and exactly match the deterministic attempted observation |

Every row also requires non-null `artifact_directory_binding_id`,
`failure_record_id`, `instance_id`, `observed_at_utc`,
`predecessor_content_id`, `review_domain_id`, and `snapshot_content_id`. The
binding ID equals the successful candidate result and every available chain
record. No other state/reason/predecessor combination is legal.
A “user-decision binding” consists, in table order, of `attempt_content_id`,
`attempt_ordinal`, `attempted_user_decision_content_id`,
`intended_user_decision`, and `user_decision_request_sha256`, plus
`user_decision_transition_result`. The user-decision row requires all six;
every other row requires all six JSON null. The attempt must be the valid
current chain head. The nested result must be a valid `NOT_PUBLISHED`
`UserDecisionObservation.v1` result with matching predecessor, record ID,
reason, `persistence_reason_code`, artifact-directory binding ID, and
`evidence_origin`; production chains require `NATIVE_RUNTIME`, while synthetic
conformance chains require `SYNTHETIC_CONFORMANCE`.
A non-null `persistence_reason_code` must be the actual underlying
`TransitionPublicationReason` from a `NOT_PUBLISHED` result, may be embedded
in a new failure record only after the publisher has proved the current
artifact-directory binding usable, and is limited to:

```text
TRANSITION_CREATE_FAILED
TRANSITION_CREATE_LIMIT_EXCEEDED
TRANSITION_CREATED_OBJECT_QUERY_FAILED
TRANSITION_CREATED_LIMIT_EXCEEDED
TRANSITION_WRITE_FAILED
TRANSITION_SEAL_FAILED
TRANSITION_WRITE_LIMIT_EXCEEDED
TRANSITION_VERIFY_FAILED
NONCANONICAL_RECORD
TRANSITION_VERIFY_LIMIT_EXCEEDED
PUBLICATION_PRIMITIVE_UNSUPPORTED
TRANSITION_PUBLICATION_FAILED
TRANSITION_PUBLISH_LIMIT_EXCEEDED
```

An artifact-directory `DIRECTORY/NOT_PUBLISHED` result or any of the five
listed prepublish artifact-directory `PUBLISH/NOT_PUBLISHED` results means no safe
current namespace for the compensating failure has been established, so no
failure publication is attempted. `TRANSITION_SLOT_OCCUPIED` means the deterministic successor
slot is already occupied; `PUBLISHED_UNCONFIRMED` and
`PUBLICATION_OUTCOME_UNKNOWN` mean it may be occupied. In all four cases no
competing failure is written. Master terminates with
`TRANSITION_DIRECTORY_UNAVAILABLE_UNRECORDED`,
`TRANSITION_SLOT_OCCUPIED_UNRECORDED`,
`TRANSITION_PUBLISHED_UNCONFIRMED`, or
`TRANSITION_PUBLICATION_OUTCOME_UNKNOWN` respectively and preserves the
publication result as the only local evidence.

For bootstrap stages before `UserDecisionAttempt.v1`, a compensating failure
publisher's definite `NOT_PUBLISHED` result other than slot collision maps
`FAILURE_PERSISTENCE_UNRECORDED`; slot collision maps
`TRANSITION_SLOT_OCCUPIED_UNRECORDED`; `PUBLISHED_UNCONFIRMED` maps
`TRANSITION_PUBLISHED_UNCONFIRMED`; and unknown maps
`TRANSITION_PUBLICATION_OUTCOME_UNKNOWN`. Master preserves both the original
and failure publication results and makes no persisted-failure claim. These
five terminal labels are Master status values, not constructible JSON
`reason_code` values. The user-decision row does not use these coarse Master
labels; steps 12–13 and the `UserDecisionResumeResult.v1` table below map its
failure publisher into the three distinct recovery states and collision
reread.

### Bootstrap observations and handoff

`BootstrapReviewObservation.v1` has exact keys:

```text
schema
observation_id
review_run_id
phase = START | END
predecessor_content_id
artifact_directory_binding_id=SHA256_ID
expected_content_id
observed_content_id
expected_review_domain_id
observed_review_domain_id
expected_instance_id
observed_instance_id
expected_source_root_identity
observed_source_root_identity
observed_at_utc
advisory_verdict = null | PASS | FAIL
advisory_p0 = null | COUNT
advisory_p1 = null | COUNT
master_observed_reviewer_final_text_sha256 = null | SHA256_ID
master_observed_final_event_at_utc = null | UTC
result = MATCH | MISMATCH | INVALID | UNSUPPORTED
observation_reason_code = ObservationReasonCode
continuous_observation = false
authority_verified = false
```

IDs and time are generated internally. Pairing requires exact equality of
`review_run_id`, artifact-directory binding ID, expected IDs, expected
instance, and expected root across START and END. At each phase,
`observed_content_id` comes from
`verify_dispatched_handle` over the published bundle, while
`observed_review_domain_id` and root identity come from a new handle-bound
capture of the current source root using the dispatch file/absence set. The
READY control is revalidated in both captures.

START `predecessor_content_id` is the dispatch-observation content ID and all
five advisory fields are null. END `predecessor_content_id` is the
`ReviewerInvocationOutcome.v1` content ID. Its five advisory fields are
non-null and byte-for-byte equal the parsed facts carried by that outcome.
The outcome's predecessor is the invocation attempt, and that attempt's
predecessor is START; this closed chain establishes the START/END pairing.

No validator imposes an inequality across dispatch, START, reviewer-final,
END, user-decision, or failure UTC fields. These observations may come from
different processes/clocks, and a wall-clock regression is structurally
legal. Validators check UTC grammar, exact repeated-field equality, and the
single-capture start/completion rule only. Cross-record order is proved by the
content-ID predecessor chain and the persist-before-send/call state machine;
timestamps remain non-authorizing trace fields.

Master first provisions a new `implementation_plan_reviewer` with
`fork_turns=none`, only the global quality law and first-principles role, and
no authoring/review history or review content. It obtains the observed
`review_run_id`. START and then `ReviewerInvocationAttempt.v1` must be
persisted before Master sends the review payload. Only the invocation that
freshly created that attempt may send, and it sends at most once. After the
host associates final text with that run, Master parses it and persists
`ReviewerInvocationOutcome.v1`; only then may END be constructed and
persisted. Unknown fields, reordered state, duplicate phase, END without the
complete invocation chain, cross-run replay, or changed expectations fail END
construction with `END_OBSERVATION_CONSTRUCTION_FAILED`. A fresh live-domain
mismatch produces and first persists a rejected END, then
`END_OBSERVATION_REJECTED`. A relationship defect discovered only while
constructing the post-END handoff is `HANDOFF_INVALID`.

The host does not expose authenticated original message bytes. The only local
input is `master_observed_reviewer_final_text`:

1. accept the Unicode scalar string visible to Master; reject NUL and unpaired
   surrogates;
2. replace CRLF with LF, then remaining CR with LF; perform no Unicode
   normalization;
3. encode strict UTF-8 and reject a result over 1,048,576 bytes;
4. parse only the fixed restricted YAML subset below; do not invoke a general
   YAML loader;
5. require the role verdict and derived blocker counts to agree;
6. hash
   `"AEGIS_MASTER_OBSERVED_REVIEWER_TEXT_V1\0"+normalized_utf8` as the stored
   `master_observed_reviewer_final_text_sha256`.

The reviewer remains governed by two active contracts: the local
`aegis-master-implementation-plan-designer` output shape, and the provisioned
`implementation_plan_reviewer` developer contract requiring every nonempty
diagnostic item to carry `id`, `issue`, and `required_fix`. The task prompt
does not replace either contract with a custom first line. The accepted wire
format is their strict intersection: it retains the local
`assumption`/`location` fields and also retains the developer contract's common
`issue` field. This plan independently freezes that complete subset and does
not trust or reread mutable skill bytes at runtime. Later host/skill drift can
only make parsing fail closed. The exact top-level key order is:

```text
verdict
requirement_alignment_issues
unconfirmed_assumptions
ledger_issues
codebase_fit_issues
ambiguities
unverifiable_items
risk_gaps
required_fixes
optional_suggestions
```

The accepted wire subset is deliberately smaller than YAML:

- no document marker, directive, tag, anchor, alias, merge key, comment,
  tab, blank line, block scalar, flow map, or flow sequence except the literal
  empty list `[]`;
- `verdict: PASS` or `verdict: FAIL` is the first physical line;
- each remaining top-level key occurs once in the fixed order, begins at
  column zero, and is either `<key>: []` or `<key>:` followed immediately by
  its indented items;
- diagnostic items begin `  - id: <ISSUE_ID>`. Their following fields are
  indented four spaces and occur in the frozen order. Every diagnostic item
  has mandatory `issue,required_fix` fields. An
  `unconfirmed_assumptions` item has mandatory
  `assumption,issue,required_fix`; an `ambiguities` item has mandatory
  `location,issue,required_fix`; every other diagnostic array has exactly
  `issue,required_fix`. Thus the common high-priority reviewer contract is
  satisfied without dropping the more specific assumption/location text;
- every free-text value and every item of `required_fixes` or
  `optional_suggestions` is one JSON double-quoted string on one physical
  line. The parser accepts only JSON string escapes, decodes to Unicode scalar
  values, and rejects NUL, unpaired surrogates, and decoded strings over
  16,384 UTF-8 bytes;
- `ISSUE_ID` is unquoted ASCII
  `[A-Z][A-Z0-9_-]{0,95}-P[012]-[0-9]{3}`. IDs are unique across all seven
  diagnostic arrays. The review payload asks the reviewer to encode severity
  this way; this constrains the role's existing `id` field and does not alter
  its output shape;
- each P0/P1 ID has exactly one `required_fixes` string beginning
  `<ISSUE_ID>:`; P2 IDs have none. Other `required_fixes` strings are
  forbidden. `optional_suggestions` is nonblocking;
- no more than 256 diagnostic items, 256 required fixes, or 256 optional
  suggestions are accepted. The normalized document has no leading/trailing
  blank line and may have either zero or one final LF.

`advisory_p0` and `advisory_p1` are the counts of unique P0 and P1 issue IDs
across the seven diagnostic arrays. `verdict=PASS` is legal exactly when both
counts are zero; `verdict=FAIL` is legal exactly when either count is nonzero.
A malformed response, inconsistent verdict, missing required-fix mapping,
duplicate ID, or out-of-contract YAML is `ADVISORY_RESULT_INVALID`; it never
reaches END or handoff. Parsed values remain Master-observed,
host-unauthenticated advisory facts.

R11A must capture two real, fresh `implementation_plan_reviewer` outputs with
`fork_turns=none`: one PASS fixture and one deliberately defective fixture
whose result contains at least one nonempty `unconfirmed_assumptions` item and
one nonempty `ambiguities` item. The exact normalized outputs become positive
goldens. Mutations that remove mandatory `issue`, `assumption`, `location`, or
`required_fix`, add an unknown field, reorder fields, duplicate an ID, or
break severity/fix arithmetic are negative goldens. If the provisioned
reviewer cannot emit this frozen intersection, the protocol returns to plan
review; production code may not silently normalize the host output.

`BootstrapPlanReviewHandoff.v1` contains the dispatch, START,
invocation-attempt, invocation-outcome, and END content IDs plus the
observation record UUIDs, stable request hash, exact dispatch identity fields,
parsed advisory values, normalized-text hash, and Master-observed final-event
time. Every advisory field must equal the invocation outcome and END. Its
`artifact_directory_identity` is queried
from the handle newly reopened and retained for the complete handoff call; it
must equal the identity in the candidate-created binding, and the handoff
stores that binding ID. This is equality of two point observations, not proof
that the handle remained open between facade calls. It is create-new, has only
`state=USER_DECISION_PENDING`, and is stored outside the repository at the
prevalidated local `artifact_path` directory.

After the advisory is shown to the user, Master may call the independent,
cross-process entry point
`resume_user_decision(artifact_directory_binding_bytes,envelope_bytes)`. These
are its only two inputs. It does not accept a retained handle, Python object,
conversation state, source-root path, bare locator, or unbound decision
record. The only UUID/time it accepts are inside the exact stable
`UserDecisionIntent.v1` created once by Master; both remain explicitly
unauthenticated. This entry point is valid after the original Python process,
Codex turn, or Codex host process has ended.

Before yielding for user input, Master must display and retain outside the
artifact directory the exact binding bytes/ID, artifact locator,
artifact-directory identity, snapshot/domain/instance/run IDs, END content ID,
and handoff content ID needed to construct the later intent. After the user
decides, Master must generate and
persist the exact intent bytes before the first call. After every return whose
state is representable by `UserDecisionPriorOutcome.v1`, it must also persist
the exact validated prior outcome before another call. A Codex continuation
file or host task state may carry these
unauthenticated navigation copies. The recovery entry never rediscovers
expected IDs by scanning the artifact directory. If the navigation or stable
intent copy is lost, the run remains inspectable but cannot accept a new
decision; starting a new review is the fail-closed recovery.

Recovery has an independent bounded execution contract. After the bounded
binding precondition succeeds, the monotonic timer starts before the envelope
length check. The total deadline is exactly 120 seconds. Every individual
envelope, transition, handoff, manifest, and bundle read has a subdeadline
equal to the lesser of the remaining total
deadline and 30 seconds from immediately before its open. The implementation
checks the applicable deadline before and after every platform probe, open,
64-KiB read chunk, parse, hash, verify, publication call, reopen, and result
construction. Before the attempt-reservation publication call, expiry maps by
current phase to exactly one of:

```text
RESUME_INPUT_LIMIT_EXCEEDED
RESUME_DIRECTORY_LIMIT_EXCEEDED
RESUME_CHAIN_LIMIT_EXCEEDED
RESUME_BUNDLE_LIMIT_EXCEEDED
RESUME_PREPUBLISH_LIMIT_EXCEEDED
```

It returns `RECOVERY_LIMIT_EXCEEDED` with all six content/result fields null
and performs no attempt, decision, or failure write. Once any transition
publication call starts, its own phase/reason/commit-state/deadline table is
authoritative; a late commit is never relabeled as a precommit recovery
timeout. Expiry after the reservation is confirmed but before the decision
publisher is called returns
`DECISION_ATTEMPT_OUTCOME_UNKNOWN/DECISION_PREPUBLISH_LIMIT_EXCEEDED` with the
confirmed attempt result and no decision/failure result. No later invocation
may take over that reservation. A kernel call that never returns remains the
explicit external OS liveness boundary and cannot be claimed as a
Python-enforced hard deadline.

The recovery algorithm is exact:

1. use the already validated exact `ArtifactDirectoryBinding.v1` and content
   ID; enforce the envelope bound; parse canonical
   `UserDecisionResumeEnvelope.v1`, its intent, and optional prior outcome;
   require every expected binding ID and identity to match; then reopen the
   binding's absolute artifact directory under its selected platform profile,
   revalidate its
   local-filesystem/type/owner/mode-or-DACL/no-link contract, and require its
   newly observed identity to equal the intent's
   `expected_artifact_directory_identity`;
2. retain that directory handle for every later operation. A pathname
   replacement after open cannot redirect any read, absence check, or publish;
3. derive the handoff transition component from
   the intent's `expected_end_observation_content_id`, open it
   handle-relative/no-follow,
   require a single-link protected regular file, parse it independently, and
   require its content ID to equal `expected_handoff_content_id` and every
   intent expectation to equal the handoff;
4. derive and independently parse exactly one dispatch slot from the snapshot
   ID, one START slot from the dispatch content ID, one invocation-attempt slot
   from START, one invocation-outcome slot from that attempt, and one END slot
   from that outcome. Require the handoff's complete chain IDs, request hash,
   observation record UUIDs, repeated fields including copied UTC values,
   observation results, advisory values, and predecessor links to match. Apply
   no cross-record UTC inequality. No directory scan or filename guess can
   substitute for these deterministic lookups;
5. derive the bundle component from the handoff instance ID; independently
   verify the complete bundle against the now-validated dispatch and handoff
   snapshot, domain, instance, source-root, required-file, required-absence,
   control, focus, and pass-condition values;
6. derive the stored decision token from the intent and PASS/FAIL handoff; copy
   the intent's fixed observation UUID/time; bind `request_sha256`; construct,
   independently validate, and hash the deterministic
   `UserDecisionAttempt.v1`. Validate any prior outcome against that request
   hash, attempt content ID, and the nested-result truth table. The decision
   bytes and content ID are constructed only after the attempt ID exists;
7. handle-relative/no-follow probe the handoff successor slot. A canonical
   matching `UserDecisionAttempt.v1` is a pre-existing reservation for this
   invocation. Set `fresh_reservation_owner=false`, construct the deterministic
   decision with that attempt as predecessor, and inspect the attempt successor
   under the tables below. Never publish a decision or failure from this path.
   A malformed, foreign-intent, or non-attempt occupant returns
   `DECISION_CONFLICT/ATTEMPT_SLOT_OCCUPIED`;
8. if the attempt slot is absent, apply the reservation/prior table below. A
   null prior outcome may make one attempt-publication call. A supplied
   `ATTEMPT_PUBLICATION_OUTCOME_UNKNOWN` returns unchanged without another
   attempt. A supplied unconfirmed or any post-attempt state with a missing
   reservation is a prior-outcome conflict. A definite-no-effect attempt
   result is terminal and is never accepted as a later prior outcome. On
   Windows, the deterministic
   attempt-staging component is also probed; a matching canonical occupant or
   create-new collision followed by matching verification returns
   `ATTEMPT_PUBLICATION_OUTCOME_UNKNOWN/ATTEMPT_STAGING_PRESENT` with no
   decision/failure call and no staging mutation;
9. after the last write-free deadline check, publish the attempt once. Only an
   `OK/PUBLISHED_CONFIRMED` result, followed by exact handle-relative reopen
   and identity/content verification, sets the invocation-local flag
   `fresh_reservation_owner=true`. A definite final-slot collision is reopened
   and handled by step 7 with the flag false. Definite other nonpublication,
   published-unconfirmed, and unknown results map to the exact attempt states
   below and return without constructing a writable decision path;
10. only while `fresh_reservation_owner=true`, construct and independently
    validate the exact deterministic `UserDecisionObservation.v1`. Perform the
    final deadline check. Expiry abandons the reservation with
    `DECISION_ATTEMPT_OUTCOME_UNKNOWN/DECISION_PREPUBLISH_LIMIT_EXCEEDED`.
    Otherwise consume the one-shot capability by permanently clearing the
    invocation-local owner flag immediately before entering the decision
    publisher, then invoke that boundary exactly once. An unexpected exception
    yields no typed completion claim and ends the invocation; it cannot restore
    the flag. A later entry observes the persisted reservation and remains
    read-only. No loop, exception handler, caller retry, prior outcome, or later
    process can set the flag again;
11. if that one decision call returns definite `TRANSITION_SLOT_OCCUPIED`,
    reopen the attempt successor once through the retained directory handle
    and apply the successor/prior table. Missing-after-collision or an
    unprovable occupant is `DECISION_CONFLICT/DECISION_SLOT_OCCUPIED`;
12. if decision publication is `DIRECTORY/NOT_PUBLISHED` or one of the five
    prepublish artifact-directory `PUBLISH/NOT_PUBLISHED` rows, return terminal
    `DECISION_PERSISTENCE_UNRECORDED/
    DECISION_TRANSITION_NOT_PUBLISHED_WITHOUT_FAILURE` with the exact decision
    result and no failure fields or failure call. The consumed owner capability
    is not restored. For every other definite `NOT_PUBLISHED` reason,
    construct and independently validate exactly one
    `BootstrapReviewFailure.v1(reason_code=
    USER_DECISION_PERSISTENCE_FAILED)` in the still-empty attempt successor
    slot. It binds the attempt ID/ordinal, request hash, intended decision,
    attempted decision content ID, and complete independently validated
    decision transition result. A deadline check precedes its publication;
    expiry returns
    `FAILURE_PERSISTENCE_UNRECORDED/FAILURE_PREPUBLISH_LIMIT_EXCEEDED` with the
    constructed failure content ID, null failure transition result, and zero
    failure syscall. Otherwise it is published once. A collision is reread
    through the successor/prior table;
13. if decision publication is unconfirmed/unknown, no failure is attempted.
    If failure publication is not confirmed, no decision or failure is retried
    in that invocation. Return the exact result-table state and require Master
    to retain it as the next envelope's prior outcome.

After complete chain verification, reservation arbitration is bidirectional:

| Prior outcome | Matching valid attempt | Attempt absent; no Windows stage | Attempt absent; matching deterministic Windows stage exists |
|---|---|---|---|
| null | inspect successor read-only | make one reservation-publication call | `ATTEMPT_STAGING_PRESENT`; no write |
| `ATTEMPT_PUBLICATION_OUTCOME_UNKNOWN` | inspect successor read-only | return unchanged; no write | return unchanged; no write |
| `ATTEMPT_PERSISTENCE_UNCONFIRMED` | inspect successor read-only | `PREVIOUS_ATTEMPT_RECORD_MISSING` | `PREVIOUS_ATTEMPT_RECORD_MISSING` |
| `DECISION_ATTEMPT_OUTCOME_UNKNOWN` or any decision/failure state | inspect successor read-only | `PREVIOUS_ATTEMPT_RECORD_MISSING` | `PREVIOUS_ATTEMPT_RECORD_MISSING` |

Any invalid attempt or staging occupant is
`DECISION_CONFLICT/ATTEMPT_SLOT_OCCUPIED`; it is never repaired or replaced.
The matching-attempt column never grants the fresh-owner flag.

After an exact attempt is established, successor/prior arbitration is also
bidirectional:

| Prior outcome | Matching decision occupant | Matching bound failure occupant | Absent successor |
|---|---|---|---|
| null or any attempt-publication state | `ALREADY_RECORDED` | `ALREADY_DECISION_FAILURE_RECORDED` | `DECISION_ATTEMPT_OUTCOME_UNKNOWN`; no write |
| `DECISION_ATTEMPT_OUTCOME_UNKNOWN` | `ALREADY_RECORDED` | `ALREADY_DECISION_FAILURE_RECORDED` | return unchanged; no write |
| `DECISION_PUBLICATION_OUTCOME_UNKNOWN` | `ALREADY_RECORDED` | `ALREADY_DECISION_FAILURE_RECORDED` | return unchanged; no write |
| `DECISION_PERSISTENCE_UNCONFIRMED` | `ALREADY_RECORDED` | `PRIOR_OUTCOME_MISMATCH` | `PREVIOUS_PUBLISHED_RECORD_MISSING` |
| `DECISION_FAILURE_RECORDED` | `PRIOR_OUTCOME_MISMATCH` | `ALREADY_DECISION_FAILURE_RECORDED` | `CONFIRMED_FAILURE_RECORD_MISSING` |
| `FAILURE_PERSISTENCE_UNRECORDED` | `ALREADY_RECORDED` | `ALREADY_DECISION_FAILURE_RECORDED` | return unchanged; no write |
| `FAILURE_PERSISTENCE_UNCONFIRMED` | `PRIOR_OUTCOME_MISMATCH` | `ALREADY_DECISION_FAILURE_RECORDED` | `PREVIOUS_FAILURE_RECORD_MISSING` |
| `FAILURE_PUBLICATION_OUTCOME_UNKNOWN` | `ALREADY_RECORDED` | `ALREADY_DECISION_FAILURE_RECORDED` | return unchanged; no write |

`FAILURE_PERSISTENCE_UNRECORDED` and
`FAILURE_PUBLICATION_OUTCOME_UNKNOWN` do not prove that a failure committed;
therefore a fully verified matching same-intent decision winner is accepted
read-only. `DECISION_FAILURE_RECORDED` and
`FAILURE_PERSISTENCE_UNCONFIRMED` claim a committed failure strongly enough
that a decision occupant contradicts the prior outcome. A matching failure
under either strong state additionally requires its recomputed content ID to
equal the prior `failure_content_id`. Other rows require the complete
attempt/request/decision/transition binding and may recover a semantically
matching winner without granting publication authority.

The R11D truth-table suite takes the Cartesian product of every prior row and
the three final-occupant columns. Its syscall-order fixtures include: decision
committed before a failure call; decision definitely not published then
failure committed; failure definite nonpublication then an independently
installed matching decision winner; failure unknown then a matching decision
winner; decision/failure collision in both observation orders; unknown or
unconfirmed decision with failure-call count zero; and absent final slot after
each weak and strong prior. Each fixture asserts the final occupant bytes, both
publisher call counts, returned state/reason, and every nullable result field.
These injected schedules validate recovery arbitration; they do not authorize
a second conforming process to publish through an existing attempt.

A malformed, foreign-request, wrong-decision, wrong-predecessor, or otherwise
unprovable occupant is always `DECISION_SLOT_OCCUPIED`, never a matching row.

Missing/truncated records, wrong permissions/type/identity, directory
replacement, bundle drift, predecessor mismatch, END-before-START, rejected
observation, wrong advisory arithmetic, duplicate transition, or request
mismatch stops before a new write. Reopening only the handoff is insufficient.
No recovery path infers publication from mere path existence: every existing
record is opened relative to the retained directory, parsed independently,
hashed, permission/identity checked, and matched to the complete chain.
This recovery validates persisted state; it does not claim the current source
tree still equals the reviewed snapshot. Any later authorization gate must
perform its own fresh-source check against the bound snapshot/domain ID.

The non-persisted return value is exact:

```text
schema="UserDecisionResumeResult.v1"
artifact_directory_binding_id=SHA256_ID
evidence_origin = NATIVE_RUNTIME | SYNTHETIC_CONFORMANCE
state = RECORDED | ALREADY_RECORDED
      | ALREADY_DECISION_FAILURE_RECORDED
      | INVALID_CHAIN | DECISION_CONFLICT
      | PRIOR_OUTCOME_CONFLICT | RECOVERY_LIMIT_EXCEEDED
      | ATTEMPT_PERSISTENCE_UNRECORDED
      | ATTEMPT_PERSISTENCE_UNCONFIRMED
      | ATTEMPT_PUBLICATION_OUTCOME_UNKNOWN
      | DECISION_ATTEMPT_OUTCOME_UNKNOWN
      | DECISION_PERSISTENCE_UNRECORDED
      | DECISION_FAILURE_RECORDED
      | FAILURE_PERSISTENCE_UNRECORDED
      | FAILURE_PERSISTENCE_UNCONFIRMED
      | FAILURE_PUBLICATION_OUTCOME_UNKNOWN
      | DECISION_PERSISTENCE_UNCONFIRMED
      | DECISION_PUBLICATION_OUTCOME_UNKNOWN
reason_code
attempt_content_id = SHA256_ID | null
attempt_transition_result = TransitionPublicationResult.v1 | null
decision_content_id = SHA256_ID | null
decision_transition_result = TransitionPublicationResult.v1 | null
failure_content_id = SHA256_ID | null
failure_transition_result = TransitionPublicationResult.v1 | null
authority_verified=false
```

The result table is bidirectional:

| State | Only reason | Attempt fields | Decision fields | Failure fields |
|---|---|---|---|---|
| `RECORDED` | `OK` | ID; `OK/PUBLISHED_CONFIRMED` result created by this invocation | ID; `OK/PUBLISHED_CONFIRMED` result | both null |
| `ALREADY_RECORDED` | `DECISION_ALREADY_RECORDED` | independently recomputed existing ID; null result | independently recomputed existing ID; null result | both null |
| `ALREADY_DECISION_FAILURE_RECORDED` | `DECISION_FAILURE_ALREADY_RECORDED` | independently recomputed existing ID; null result | attempted ID and exact `NOT_PUBLISHED` result recovered from the failure | independently recomputed existing failure ID; null result |
| `ATTEMPT_PERSISTENCE_UNRECORDED` | `ATTEMPT_TRANSITION_NOT_PUBLISHED` | constructed ID; definite `NOT_PUBLISHED` result other than final-slot or deterministic-stage occupation | both null | both null |
| `ATTEMPT_PERSISTENCE_UNCONFIRMED` | `ATTEMPT_TRANSITION_PUBLISHED_UNCONFIRMED` | constructed ID; `PUBLISHED_UNCONFIRMED` result | both null | both null |
| `ATTEMPT_PUBLICATION_OUTCOME_UNKNOWN` | `ATTEMPT_TRANSITION_PUBLICATION_OUTCOME_UNKNOWN` or `ATTEMPT_STAGING_PRESENT` | constructed ID; respectively `PUBLICATION_OUTCOME_UNKNOWN` result or null result | both null | both null |
| `DECISION_ATTEMPT_OUTCOME_UNKNOWN` | `EXISTING_ATTEMPT_WITHOUT_SUCCESSOR` or `DECISION_PREPUBLISH_LIMIT_EXCEEDED` | existing ID; respectively null result or this invocation's `OK/PUBLISHED_CONFIRMED` result | constructed ID; null result | both null |
| `DECISION_PERSISTENCE_UNRECORDED` | `DECISION_TRANSITION_NOT_PUBLISHED_WITHOUT_FAILURE` | ID; this invocation's `OK/PUBLISHED_CONFIRMED` result | constructed ID; definite `DIRECTORY/NOT_PUBLISHED` or prepublish artifact-directory `PUBLISH/NOT_PUBLISHED` result | both null |
| `INVALID_CHAIN` | `REQUEST_INVALID`, `UNSUPPORTED_PLATFORM`, `ARTIFACT_DIRECTORY_INVALID`, `ARTIFACT_DIRECTORY_IDENTITY_MISMATCH`, `HANDOFF_MISSING_OR_INVALID`, `BUNDLE_MISSING_OR_INVALID`, `DISPATCH_MISSING_OR_INVALID`, `START_MISSING_OR_INVALID`, `END_MISSING_OR_INVALID`, or `CHAIN_MISMATCH` | both null | both null | both null |
| `DECISION_CONFLICT` | `ATTEMPT_SLOT_OCCUPIED` or `DECISION_SLOT_OCCUPIED` | both null | both null | both null |
| `PRIOR_OUTCOME_CONFLICT` | `PRIOR_OUTCOME_MISMATCH`, `PREVIOUS_ATTEMPT_RECORD_MISSING`, `PREVIOUS_PUBLISHED_RECORD_MISSING`, `PREVIOUS_FAILURE_RECORD_MISSING`, or `CONFIRMED_FAILURE_RECORD_MISSING` | both null | both null | both null |
| `RECOVERY_LIMIT_EXCEEDED` | `RESUME_INPUT_LIMIT_EXCEEDED`, `RESUME_DIRECTORY_LIMIT_EXCEEDED`, `RESUME_CHAIN_LIMIT_EXCEEDED`, `RESUME_BUNDLE_LIMIT_EXCEEDED`, or `RESUME_PREPUBLISH_LIMIT_EXCEEDED` | both null | both null | both null |
| `DECISION_FAILURE_RECORDED` | `USER_DECISION_PERSISTENCE_FAILED_RECORDED` | ID; this invocation's `OK/PUBLISHED_CONFIRMED` result | constructed ID; a definite `NOT_PUBLISHED` result other than slot occupation | non-null failure ID; `OK/PUBLISHED_CONFIRMED` result |
| `FAILURE_PERSISTENCE_UNRECORDED` | `FAILURE_PERSISTENCE_UNRECORDED` or `FAILURE_PREPUBLISH_LIMIT_EXCEEDED` | ID; this invocation's `OK/PUBLISHED_CONFIRMED` result | constructed ID; a definite `NOT_PUBLISHED` result | non-null failure ID; respectively definite `NOT_PUBLISHED` result except slot occupation, or null result with zero failure syscall |
| `FAILURE_PERSISTENCE_UNCONFIRMED` | `FAILURE_TRANSITION_PUBLISHED_UNCONFIRMED` | ID; this invocation's `OK/PUBLISHED_CONFIRMED` result | constructed ID; a definite `NOT_PUBLISHED` result | non-null failure ID; `PUBLISHED_UNCONFIRMED` result |
| `FAILURE_PUBLICATION_OUTCOME_UNKNOWN` | `FAILURE_TRANSITION_PUBLICATION_OUTCOME_UNKNOWN` | ID; this invocation's `OK/PUBLISHED_CONFIRMED` result | constructed ID; a definite `NOT_PUBLISHED` result | non-null failure ID; `PUBLICATION_OUTCOME_UNKNOWN` result |
| `DECISION_PERSISTENCE_UNCONFIRMED` | `TRANSITION_PUBLISHED_UNCONFIRMED` | ID; this invocation's `OK/PUBLISHED_CONFIRMED` result | constructed ID; `PUBLISHED_UNCONFIRMED` result | both null |
| `DECISION_PUBLICATION_OUTCOME_UNKNOWN` | `TRANSITION_PUBLICATION_OUTCOME_UNKNOWN` | ID; this invocation's `OK/PUBLISHED_CONFIRMED` result | constructed ID; `PUBLICATION_OUTCOME_UNKNOWN` result | both null |

For the resume DIRECTORY phase, a recognized binding profile unavailable on
the host maps `INVALID_CHAIN/UNSUPPORTED_PLATFORM`; an opened directory whose
object identity differs maps
`INVALID_CHAIN/ARTIFACT_DIRECTORY_IDENTITY_MISMATCH`; missing/open failure,
wrong type/filesystem/owner/protection/storage-anchor, or link/reparse state maps
`INVALID_CHAIN/ARTIFACT_DIRECTORY_INVALID`. A deadline or monotonic-source
failure maps `RECOVERY_LIMIT_EXCEEDED/RESUME_DIRECTORY_LIMIT_EXCEEDED`.
Protection drift never maps to identity mismatch.

No other state/reason/nullability combination is legal. Every row's
artifact-directory binding ID is non-null, equals the validated facade input,
intent, handoff, complete chain, and every nested transition result. Malformed
binding bytes raise `ReviewTransportValidationError` before a resume result;
therefore a null or mismatched binding ID is never legal. Nested transition
results must independently validate before the resume result is consumed and
must have the same `evidence_origin` as the resume result and binding.
Within `FAILURE_PERSISTENCE_UNRECORDED`, a null
`failure_transition_result` is legal only for
`FAILURE_PREPUBLISH_LIMIT_EXCEEDED`; the non-null failure content ID binds the
already constructed bytes, and no file identity or staging locator is
fabricated. A later absent-successor read returns that same reason from this
unique prior shape without invoking a publisher.
Only the nine attempt/decision/failure persistence states listed by
`UserDecisionPriorOutcome.v1` may be copied into a later envelope; every copied
field must equal this table. `RECORDED`, read-only, invalid, conflict, and
pre-attempt timeout states are terminal for this run.
`ATTEMPT_PERSISTENCE_UNRECORDED` is also terminal: the caller retains its exact
result as evidence and must start a new reviewed user-decision run. It cannot
submit that result as `UserDecisionPriorOutcome.v1`, recreate an owner, or
retry the reservation.
`DECISION_PERSISTENCE_UNRECORDED` is also terminal and is deliberately absent
from `UserDecisionPriorOutcome.v1`; a later process can only observe the
existing attempt read-only and can never regain decision-publication
capability.
No return state authorizes work. Local Python checks shape, persistence,
pairing, recovery, and PASS/FAIL-to-decision arithmetic only. It cannot
authenticate the reviewer final event, Master, or the user.

### Source touchpoints and migration

```text
evaluation/aegis_v2/review_transport/
  __init__.py
  api_v1.py
  port_contracts.py
  orchestration_core.py
  value_records.py
  publication_result.py
  domain_capture.py
  posix_bound_io.py
  windows_bound_io.py
  bundle_writer.py
  independent_bundle_verifier.py
  restricted_reviewer_yaml.py
  transition_store.py
  bootstrap_observation.py
  decision_recovery.py
evaluation/aegis_v2/review_transport_conformance/
  __init__.py
  api_v1.py
  canonical_records.py
  coordinator.py
  model_ports.py
  worker.py
evaluation/aegis_v2/review_control.v1.json
evaluation/aegis_v2/tests/
  review_transport_test_support.py
  native_conformance_evidence.py
  native_trace_port.py
  test_review_transport_contract_red.py
  test_review_transport_object_probe_red.py
  test_review_transport_conformance_red.py
  test_review_transport_evidence_origin_red.py
  test_review_transport_readiness_red.py
  test_review_transport_posix_red.py
  test_review_transport_windows_red.py
  test_review_transport_publication_red.py
  test_review_transport_observation_red.py
  test_review_transport_reviewer_yaml_red.py
  test_review_transport_transition_chain_red.py
  test_review_transport_decision_recovery_red.py
  test_review_transport_permissions_red.py
  test_review_transport_independent_verifier_red.py
  fixtures/native_cases/
    native_case_catalog.v1.json
  fixtures/review_bundle_v1/
    fixture_manifest.v1.json
pyproject.toml
.gitattributes
```

`evaluation/aegis_v2/review_snapshot.py` is frozen unsafe code. No new module
may import it. After every old invariant has a witnessed replacement RED test,
it becomes a fail-closed compatibility shim whose public entry points return
`LEGACY_SNAPSHOT_UNSUPPORTED`; it is then deleted only after repository-wide
import search proves zero consumers. Its directory-bundle output is never
accepted by the new verifier.

Old-test migration is complete only when every group below has named RED
coverage:

| Old invariant group | Required replacement coverage |
|---|---|
| subject/readiness/protocol: `test_manifest_binds_fixed_final_review_protocol_and_rejects_drift`, `test_ready_review_subject_is_allowlisted_and_self_hashed`, `test_review_subject_parameter_is_mandatory`, `test_review_subject_must_be_ready_and_have_one_canonical_status`, `test_review_subject_must_be_inside_the_allowlist`, `test_ready_status_in_non_machine_markdown_context_is_rejected` | Dispatch equality, exact subject membership, exact machine status, unknown-field rejection. |
| instance/time/root: `test_instance_and_capture_times_are_inside_the_self_hash`, `test_build_rejects_invalid_instance_or_capture_window`, `test_live_verification_returns_explicit_start_and_end_receipts`, `test_live_verification_rejects_unknown_boundary`, `test_offline_integrity_result_cannot_be_a_live_receipt` | Internal UUID/time only, root derived from handle, full content binding, typed non-authoritative START/END observations, no receipt type. |
| old Git state/provenance: `test_build_captures_allowlist_files_git_context_and_full_self_hash`, `test_repository_evidence_binds_exact_allowlist_git_preimages`, `test_repository_evidence_and_gate_aggregate_reject_forgery`, `test_file_records_bind_git_objects_modes_and_regular_file_kind`, `test_verify_rejects_resigned_git_and_file_identity_forgery`, `test_build_rejects_unmerged_index_conflict`, `test_verify_rejects_git_state_change_outside_the_allowlist`, `test_bundle_contains_exact_allowlist_git_evidence_and_verifies_offline`, `test_bundle_rejects_missing_git_evidence_object`, `test_git_index_environment_is_rejected_or_ignored`, `test_git_dir_and_work_tree_environment_is_rejected_or_ignored`, `test_git_object_directory_environment_is_rejected_or_ignored`, `test_git_config_environment_is_rejected_or_ignored` | Replace with raw allowlist byte capture, outside-domain irrelevance, exact object observations, zero subprocess/Git calls, hostile filter/process/fsmonitor/hook/config sentinels, replace-ref/nested-repo/submodule/sparse/ignore irrelevance. |
| path/type/absence: `test_build_rejects_directory_and_link_inputs`, `test_build_rejects_non_ascii_or_non_canonical_paths`, `test_build_rejects_unsorted_duplicate_and_casefold_paths`, `test_required_absent_paths_use_strict_path_contract`, `test_build_rejects_required_absent_file_or_directory_present`, `test_live_verify_rejects_required_absent_path_appearing`, `test_verify_rejects_resigned_absence_reordering_and_duplicate`, `test_build_rejects_absence_descendant_conflicts`, `test_build_rejects_missing_or_deleted_allowlisted_file`, `test_bundle_rejects_resigned_absence_ancestry_conflicts`, `test_ancestor_link_exchange_fails_closed` | Canonical paths, strict order/case fold, regular/link-count-one files, metadata-only nonblocking probes for every declared special-object kind, required-absence rejection for every present kind, initial missing/directory/unsupported mapping, regular-probe-to-missing/different-identity/different-kind races, exact absence observations, and ancestor/reparse/mount exchange fixtures. |
| external source/domain mutation: `test_external_sources_require_exact_local_frozen_bytes`, `test_external_sources_reject_reordering_duplicates_and_bad_paths`, `test_verify_rejects_resigned_external_source_metadata_forgery`, `test_verify_rejects_resigned_external_reordering_and_duplicate`, `test_verify_rejects_every_unsigned_control_field_tamper`, `test_verify_rejects_unknown_manifest_control_even_when_resigned`, `test_verify_rejects_resigned_path_reordering_and_duplicates`, `test_verify_rejects_resigned_file_and_aggregate_forgery`, `test_verify_rejects_selected_file_byte_tamper` | External sources are ordinary frozen required files; every manifest/frame/control mutation changes domain/content IDs or is rejected structurally. |
| old directory bundle: `test_write_bundle_is_create_new_canonical_and_deduplicated`, `test_bundle_publication_never_exposes_a_partial_target`, `test_posix_publish_race_preserves_competitor_empty_target`, `test_target_cleanup_aba_preserves_competitor_directory`, `test_staging_bundle_aba_preserves_competitor_directory`, `test_post_publication_failure_never_leaves_final_name_partial`, `test_write_bundle_rejects_stale_snapshot_without_partial_output`, `test_bundle_directory_name_must_equal_snapshot_instance_id`, `test_bundle_rejects_tampered_missing_and_extra_objects`, `test_bundle_rejects_noncanonical_or_tampered_manifest`, `test_bundle_rejects_unexpected_files_outside_object_store` | Exact single-file grammar, held-object write/verify/publish, destination-root/source/final-name races, typed commit state, no rollback, competitor preservation, truncation/extra/unknown/duplicate/overflow bounds. |
| offline portability/privacy: `test_bundle_verification_does_not_depend_on_original_worktree`, `test_offline_bundle_does_not_claim_current_worktree_absence`, `test_copied_bundle_remains_self_contained`, `test_reviewer_readable_bundle_excludes_non_allowlisted_git_bytes` | Offline stream verification needs no source tree, absence remains observational, copied bytes retain ID, only allowlisted file bodies occur in the container. |
| out-of-band identity/result types: `test_offline_api_requires_expected_snapshot_content_id`, `test_offline_result_is_typed_and_explicitly_non_authorizing`, `test_resigned_bundle_is_rejected_by_out_of_band_expected_id` | Expected content/domain/instance/root/required-set values are mandatory; results are frozen, typed, and permanently non-authorizing. |

### R11A independently distinguishable RED evidence

R11A creates no file under
`evaluation/aegis_v2/review_transport/` or
`evaluation/aegis_v2/review_transport_conformance/` and does not create
`evaluation/aegis_v2/review_control.v1.json`. It may add only the approved
tests, test-owned fixtures/support, `pyproject.toml` collection correction, and
the fixture binary rule in `.gitattributes`. A production package, empty
`__init__.py`, facade stub, fake result, or import shim is forbidden.

The test-owned support module defines structural `ReviewTransportAdapter` and
`ReviewTransportConformanceAdapter` `Protocol` values containing the two
frozen facade signatures. They are oracle-side type descriptions only and
never supply behavior. Each case resolves exactly one endpoint inside the test
body from either
`evaluation.aegis_v2.review_transport.api_v1` or
`evaluation.aegis_v2.review_transport_conformance.api_v1`. Module-level SUT
import,
`pytest.importorskip`, `xfail`, `expectedFailure`, and catching a missing
endpoint as success are forbidden.

Each conformance case has a globally unique stable `case_id`, one facade
operation, exact fixture or generated input, expected public result or
exception class, expected namespace state, one static
`required_hosts=PORTABLE|WINDOWS_NTFS_V1|LINUX_LOCAL_V1`, and an oracle
assertion. A missing required-host module or endpoint produces an assertion
failure with exactly:

```text
R11A_RED::<case_id>::ENDPOINT_ABSENT::<endpoint_name>
```

It is never a collection error. After endpoint resolution, the same test body
must continue with a scenario-specific facade call and contract assertion;
an unconditional `fail()` or an endpoint-presence-only test is forbidden.

Every reusable semantic oracle assertion for a result, record, event trace, or
namespace has a mutation witness owned by the tests:

1. an independently constructed valid expected value passes;
2. one relevant field, byte, call-order entry, or namespace fact is changed;
3. that single mutation is rejected by the same assertion.

Primitive framework assertions used to prove that the semantic oracle accepts
its control and rejects its mutation do not recursively require another
witness. The witness cannot call a production/conformance canonicalizer,
validator, hash helper, or fixture builder. Case-catalog integrity, fixture
hashes, independent oracle checks, and mutation-witness meta-tests may pass
during R11A. Each applicable facade case must be RED on every required host.
An oracle may assert only relations for which its fixture supplies every
operand. A standalone-result oracle tests structural relations only; identity
truth and locator parentage belong to the bound-runtime or conformance-trace
oracle defined above.
This separates “the implementation endpoint does not yet exist” from “the
oracle cannot detect the defect” and does not pretend that an absent
implementation exercised domain behavior.

Every case targeting
`evaluation.aegis_v2.review_transport_conformance.api_v1` has
`required_hosts=PORTABLE`, regardless of the script's Windows or Linux model
profile. `script.profile` selects model semantics only; it never probes or
depends on the host OS/filesystem. Pure production validators/classifiers are
also portable. Only a case that invokes a real native port through production
`api_v1` may use `WINDOWS_NTFS_V1` or `LINUX_LOCAL_V1`.

The Windows/WSL outcome matrix is exact:

| Case scope | Windows host | WSL native host |
|---|---|---|
| `PORTABLE` | own `ENDPOINT_ABSENT` RED | own `ENDPOINT_ABSENT` RED |
| `WINDOWS_NTFS_V1` | own `ENDPOINT_ABSENT` RED | exact permitted skip |
| `LINUX_LOCAL_V1` | exact permitted skip | own `ENDPOINT_ABSENT` RED |
| fixture/oracle/mutation meta-test | PASS | PASS |

The only permitted skip text is
`R11A_SKIP::<case_id>::HOST_NOT_APPLICABLE::<profile>`. A required host that
lacks its approved OS/filesystem/interpreter/profile emits
`R11A_BLOCKED::<case_id>::REQUIRED_HOST_UNAVAILABLE::<profile>` and blocks the
gate; it is neither a skip nor RED evidence. Both hosts collect the same case
IDs. Portable cases must be RED twice; platform cases must be RED on their
required host and exact-skip only on the other. Every platform test file
contains at least one portable pure case, so no file is all-skip.
Consequently every synthetic Windows-status and Linux-link case is independently
RED on both hosts during R11A and GREEN on both hosts at its R11C/R11D stage;
host-dependent behavior is a conformance defect, not a permitted skip.

The synthetic facade RED catalog includes at minimum: metadata-only
`OBJECT_PROBE` for `ABSENT`, directory, regular file, and every platform-legal
unsupported subtype; every present kind against a required absence; initial
missing/directory/unsupported required files; regular-probe followed by
missing, different-identity regular, directory, or unsupported open;
nonstandard NTSTATUS;
pending/wait/IOSB disagreement, non-pending-plus-wait, and pending-plus-null;
partial write; flush failure; final reopen
identity drift; create effect followed by identity/protection-query failure or
deadline; clock values on both sides of each deadline; attempt commit
before decision call crash; decision and failure effect after commit but
before return; result before external prior persistence; two actors released
against one empty attempt slot; attempt/decision/failure REQUESTED call counts;
hidden-install unknown outcome; actor-keyed source ordering; create-template
consumption, unnamed-object reclamation, and exact Windows residual-stage
retention for injected nonpublication/unknown results; zero-progress versus EOF; invalid
operation/outcome pairs; malformed publish request not counted; unused and
duplicate controls/sources/templates; missing/extra/reordered or hash-mismatched
RPC blob frames; DEFAULT and injected recovery CALL/RESULT round trips;
missing/extra/reordered/mismatched recovery-result frames; crash after effect
and result request but before result ACK; one actor's
attempt-to-decision and attempt-to-decision-to-failure sequences with each
closed call ACKed before the next, plus replayed/gapped/overlapping call
rejection and crash/nonreturn at every call; missing schedule release; confirmed
hard-kill before next release; coordinator nonreturn; explicit `ACTOR_EXIT`
handle counts, zero-link Linux reclamation, named-object retention, no
unconfirmed-exit reclamation, and final-namespace equality after the last exit
event; event/resource bounds
and run-state precedence; synthetic origin rejection by production;
Windows-model and Linux-model scripts on both hosts; and event-log
field/order/namespace mutation witnesses. It also rejects distinct model
objects or materializations with one identity, proves same-identity
permission/anchor drift through `replacement_facts`, and proves that
`object_key`, model `flush_state`, and snapshot `blob_content_id` never enter
an object-facts response; transport blob IDs stop at the adapter. Every body
continues past
`run_conformance_script`
resolution to assert public result bytes, event order, namespace hashes/final
occupant, actor lifecycle, and call counts.

The native-evidence catalog independently mutates every one of the six raw
preimages and rejects: detached binding/result bytes; unapproved host tuple or
anchor; producer-set status claims; declaration/trace hash or entrypoint
mismatch; a declared caller-input frame replaced A-to-B together with an
otherwise self-consistent trace/result; source/artifact locator swap; declared
binding or record bytes detached from the actual transition input; one raw
NTSTATUS/errno change; missing, extra, or reordered port events/frames; illegal
handle reuse; an absent probe carrying facts; a present probe with null
identity, inconsistent kind/subtype, or wrong platform subtype; an
unsupported-open result carrying a handle or a kind equal to the request;
write/flush/publish/reopen order drift; target/stage identity or
byte drift; competitor replacement; incomplete directory observations;
undeclared slot changes; and a receipt whose hashes are internally consistent
but whose trace violates the frozen case expectation. It also rejects an
unregistered expectation, case-ID swap, duplicate catalog ID/hash,
catalog/order mutation, or aggregator constant that differs from the reviewed
catalog hash. AST/call-graph cases also reject an observer that alters
arguments/returns, calls an underlying method more than once, selects another
native factory/core, passes a different byte object after declaration, or
becomes importable from production. The valid control for each mutation must
aggregate from raw preimages; copying a previously emitted receipt is not an
oracle.

The binding catalog independently covers: successful builder result versus
nested binding/hash mismatch; binding locator/profile/identity/protection/
storage-anchor/instance/origin and fixed-false mutations; same locator reopened as a different directory; same
identity with permission/mode/DACL/ACL drift; missing/wrong binding ID in every
transition record; a synthetic-origin nested result inside an otherwise valid
native failure record or resume prior, rejected before namespace I/O;
dispatch/START/END pair disagreement; failure and handoff
binding mismatch; intent versus handoff mismatch before reservation; a
complete chain copied into another valid directory; same directory with
another review instance; replacement before publication; replacement observed
only after commit; lexical and handle-observed source/artifact ancestry in both
directions; Windows volume-GUID/native-target/FileId mutation; Linux
`statx_mnt_id`/dev/inode mutation, bind/multiple-mount alias rejection, and
retained `..` walk bounds; and `/mnt/c` rejected as native-ext4 evidence. An entry-time or
pre-write mismatch asserts zero namespace mutation. A mismatch first observed
by the immediate precommit reopen asserts zero publication syscalls, zero
mutation through the replacement handle, retained Windows staging or unlinked
Linux-inode behavior exactly as specified, and `NOT_PUBLISHED`. A postcommit
mismatch is `PUBLISHED_UNCONFIRMED` with no rollback.

Evidence is complete only when all conditions hold:

- Windows and WSL `pytest --collect-only` both exit zero, collect the identical
  catalogued case-ID set, and have zero collection errors or fallback-path
  warnings;
- Windows and WSL `pytest --maxfail=0` both run every R11A file; every file has
  at least one independent RED, zero errors, zero xfail/XPASS, zero
  expected-failure outcomes, and only matrix-permitted skips;
- every case selected alone has its own required-host `ENDPOINT_ABSENT` RED and
  its non-required-host exact skip, not a fixture/setup/import failure from
  another case;
- a case-ID aggregator merges both complete outputs and rejects conformance
  PASS, ERROR, missing case, nonpermitted skip, or blocked required host; the
  first import failure or pytest exit code alone is not evidence;
- an independent test-quality reviewer reads test bodies, fixtures, case
  catalog, witnesses, and RED output and returns `P0=0/P1=0`.

The R11A gate emits canonical `R11ATestBaseline.v2` outside the candidate
repository. It has exact keys
`collection_roots,entries,required_absences,schema`, with
`schema="R11ATestBaseline.v2"`. `collection_roots` is exactly:

```text
evaluation/aegis_v2
schemas/aegis/v2
test
```

`entries` has 1..4096 strictly raw-ASCII path-ordered exact
`{mode="100644"|"100755",path=R11A_BASELINE_PATH,sha256=SHA256_ID,
size=<JSON integer 0..134217728>}` rows. It contains every ordinary file
recursively reachable beneath those three roots plus root `pyproject.toml` and
`.gitattributes`; there is no suffix filter or unrecorded helper, fixture,
catalog, schema, conftest, plugin, or collection input. Directories, links,
reparse points, devices, case-fold collisions, unlisted descendants, and a
summed size over 536,870,912 bytes invalidate the baseline.
`R11A_BASELINE_PATH` is exactly
`PATH | ".gitattributes" | ".pytest.ini"`.

`required_absences` is a strictly raw-ASCII ordered 1..256
`R11A_BASELINE_PATH` array. It
contains every production module/package/directory that R11A promises absent,
every root or ancestor `conftest.py`/pytest plugin/config candidate outside the
recorded entries that could affect collection, and every generated bytecode or
cache directory under the collection roots. R11A executes with
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, a fixed empty explicit third-party plugin
list, and no inherited `PYTHONPATH`; the exact interpreter/stdlib/pytest
identity and environment keys are recorded separately in each host receipt.
Any required absence appearing is drift, not a new baseline member.

The baseline content ID is SHA-256 over
`"AEGIS_R11A_TEST_BASELINE_V2\0"` plus exact canonical bytes. Master publishes
those bytes create-new into a repository-external retained directory, flushes
the file and directory, reopens by retained parent, verifies identity,
protection, size, bytes, and hash, and then emits exact
`R11ABaselineCustody.v1`:

```text
baseline_content_id=SHA256_ID
baseline_identity=RootOrFileIdentity
baseline_locator=NativeLocator
baseline_size=<JSON integer 1..536870912>
custody_created_at_utc=UTC
power_loss_durable=true | false
protection=PublishedFileProtection
schema="R11ABaselineCustody.v1"
```

`power_loss_durable` equals the actual platform confirmation. Its content ID
is SHA-256 over `"AEGIS_R11A_BASELINE_CUSTODY_V1\0"` plus exact canonical
bytes. The custody record is itself create-new, flushed, reopened, and
content-addressed. The R11A gate advances only when both baseline and custody
publications confirm `power_loss_durable=true`; otherwise it remains blocked.
Master stores its expected content ID both in
host continuation state and one second create-new navigation record outside
the checkout; neither copy grants authority.

Every R11B..E gate reopens the custody object, verifies the expected ID, and
recomputes the complete recursive membership, required absences, bytes,
collection command, and host receipt before running tests. Missing or
unverifiable custody, navigation loss, any test/oracle/fixture/catalog/schema/
collection drift, or any new executable input returns explicitly to R11A and
requires a new independent test-quality review. Only that review gate may
create a replacement baseline/custody pair; an implementation agent cannot
weaken tests or refresh its own baseline.

The root pytest collection list becomes exactly:

```toml
testpaths = [
  "evaluation/aegis_v2/reference/tests",
  "evaluation/aegis_v2/tests",
  "test",
]
```

Exact-byte fixtures are indexed by
`fixtures/review_bundle_v1/fixture_manifest.v1.json`, which records relative
path, byte count, SHA-256, purpose, and provenance. Their repository rule is:

```gitattributes
evaluation/aegis_v2/tests/fixtures/review_bundle_v1/** -text -eol
```

Every R11B..E two-host gate runs one immutable
`Round11StageCandidate.v1`, never two independently selected worktrees. It has
exact keys:

```text
entries=<stage entry array>
membership_sha256=SHA256_ID
package_source_manifest_ids=<three exact name/content-ID rows>
required_absences=<R11A_BASELINE_PATH array>
r11a_baseline_content_id=SHA256_ID
r11a_custody_content_id=SHA256_ID
schema="Round11StageCandidate.v1"
stage="R11B" | "R11C" | "R11D" | "R11E"
```

Entries are the complete recursive union of production source, conformance
source, tests, support code, fixtures, schemas, catalogs, root build/test
configuration, and package/deploy build inputs for that stage. Each exact row
is `{mode,path,sha256,size}` with the same ordering/type/bounds as the R11A
baseline. Required absences close all generated caches, unlisted collection
plugins, build outputs, alternate production modules, and stage-forbidden
future modules. The three source-manifest IDs bind the exact deploy, wheel, and
sdist source manifests defined below. Each row is exact
`{artifact_kind,content_id=SHA256_ID,name}`; names are
`deploy_source_manifest.v1.json`, `sdist_source_manifest.v1.json`, and
`wheel_source_manifest.v1.json`, strictly raw-ASCII name ordered, and
`artifact_kind` must match the manifest. The candidate ID is SHA-256 over
`"AEGIS_ROUND11_STAGE_CANDIDATE_V1\0"` plus canonical bytes.
`membership_sha256` is SHA-256 over
`"AEGIS_ROUND11_STAGE_MEMBERSHIP_V1\0"` plus exact canonical
`Round11StageMembership.v1={entries,required_absences,
schema="Round11StageMembership.v1"}` bytes.

Master materializes the exact candidate twice: one repository-external Windows
local-filesystem tree and one WSL native-ext4 tree. WSL input reaches ext4 by
copying verified bytes from `/mnt/<drive>/...`; tests never execute from
DrvFS. Each materializer create-new writes files, applies the declared mode,
rejects extra/link/special/case-colliding members, flushes, and then performs a
fresh complete membership/byte hash. It emits
`StageMaterializationReceipt.v1={candidate_content_id,host_facts_sha256,
materialized_root_identity,membership_before_sha256,profile,schema}`.
`schema="StageMaterializationReceipt.v1"` and
`membership_before_sha256` must equal the candidate membership hash. Windows
and WSL receipts must carry the same candidate ID; host facts remain separate.

Each test command then emits `StageHostTestReceipt.v1` containing the same
candidate ID, materialization receipt ID, exact argv/environment,
collection-case-set hash, result summary/hash, start/completion UTC, and a
post-run complete membership hash. The before/after membership hashes must
equal the candidate's `membership_sha256`. A host-specific source edit,
unrecorded generated file,
different case set, or mismatched candidate blocks the gate instead of being
described as a portable pass.

### Atomic Round 11 replacement stages

1. `R11A RED`: independent test authors with disjoint file ownership add the
   complete migration, hostile Git/filter, READY-control, complete-schema
   mutation, result truth-table, bounds, platform-race, immutable
   artifact-directory permission, native-status, live-domain,
   restricted-role-YAML, single-successor chain, failure matrix, handoff,
   cross-process recovery, and user-decision tests. Production modules remain
   absent. Gate: the two-host matrix covers every catalogued case at its named
   production or synthetic-conformance endpoint; every reusable semantic
   oracle has its mutation witness; an independent test-quality reviewer
   returns `P0=0/P1=0`.
2. `R11B FORMAT GREEN`: a separate implementation agent adds `api_v1.py`,
   immutable value/result validation, pure
   `CapturedReviewDomainFacts.v1`-to-domain assembly, and the independent
   bundle verifier. It also adds the synthetic conformance script/log codecs,
   validation, zero-actor/empty-model execution, and production-import/archive
   isolation, but no platform or recovery atom. It does not read a source
   pathname, claim platform capture, publish a file, or implement
   observation/recovery behavior. Gate: hand-built golden vectors, every
   schema and canonical mutation, endpoint-plus-one bounds, verifier import
   isolation, conformance input contradiction and unused
   declaration/control/source/template/mutation/schedule rejection,
   operation/outcome matrix closure, resource-limit/run-state
   precedence, and
   all applicable pure R11B facade cases pass on Windows and WSL.
3. `R11C PLATFORM GREEN`: add Windows and Linux held-object capture, streaming
   bundle writer, candidate builder, and create-new bundle/transition
   publication. Only real retained-handle capture may create
   `CapturedReviewDomainFacts.v1`; the R11B pure assembler remains unaware of
   pathnames and handles. Add one-worker conformance coordination, deterministic
   sources, model namespace, and platform preflight/open/probe/query/read/write/
   flush/rename/wait/linkat/reopen/directory-flush atoms. Gate: zero
   subprocess/Git calls in production, real NTFS and
   WSL-native-ext4 positive tests;
   native Windows one-/two-WCHAR length, non-null root, null-root/cwd rejection,
   immediate/pending/mismatched-IOSB/timeout/unknown NTSTATUS, every severity
   class, nonzero success/informational/warning catch-all, a non-pending call
   plus wait, pending plus null, timeout bool rejection, zero/one/maximum/
   maximum-plus-one nanoseconds and ceiling timeout ticks, collision,
   root/staging/source/final-name exchange, no-follow required-absence
   observation for every host-creatable object kind, FIFO nonblocking,
   symlink/reparse/directory/device rejection, probe-to-open deletion,
   identity/type/size/change-token substitution, body-preserving metadata
   change, short write, flush failure, explicit postcommit remove/replace,
   every low-level after-effect crash gate, reopen drift, immutable
   artifact-directory DACL/mode/ACL, and
   unsupported-filesystem tests pass.
   A pure resolver/property matrix covers the complete unsigned-32-bit
   partition and timeout arithmetic; synthetic-conformance scripts cover
   otherwise unreachable statuses, short I/O, flush/reopen failures, and exact
   actor-keyed before/after-deadline clocks on both Windows and WSL hosts; real
   NTFS conformance independently covers
   actual success, collision, buffer layout, handle identity, and no-replace.
   Synthetic status injection is never mislabeled as an observed NTFS return.
4. `R11D HANDOFF GREEN`: add fresh-source START/END pairing from exact dispatch
   and predecessor bytes, normalized advisory parsing through the restricted
   role-YAML grammar, deterministic
   one-successor transition slots, rejected-observation/failure chaining,
   pending-only handoff, process-persistent pre-decision attempt reservation,
   separate
   user-decision/failure persistence, exact failed-state matrix, and
   fixed-false authority/durability fields. Add transition-read,
   recovery-publish, invocation-lifecycle, multi-worker schedule, hard-kill,
   and persistent model-namespace conformance atoms. Gate:
   every synthetic schedule passes with identical canonical bytes on both
   hosts; every crash/nonreturn proves worker exit before the next release;
   reviewer-invocation reservation-before-send, reservation-commit crash,
   send-before-outcome crash with authoritative reattach, unsupported reattach
   terminal-without-resend, outcome-commit-before-END recovery,
   fork/race/replay/reorder/cross-run/unknown-field/advisory-missing/
   live-domain-drift/decision-before-handoff/original-process-exit/
   fresh-Python-resume/Codex-restart/concurrent-reservation-single-owner/
   attempt-commit-before-decision-call-crash/
   decision-call-before-result-crash/return-before-prior-persist-crash/
   two-consecutive-recovery-crashes/global-decision-call-count-one/
   failure-commit-before-result-crash/read-only-already-recorded/
   already-failure-recorded/post-collision-reread/
   attempt-not-published-empty-slot/attempt-unknown-empty-slot/
   attempt-unconfirmed-empty-slot/partial-or-conflicting-attempt/
   Windows-deterministic-attempt-staging-no-accumulation/
   decision-unknown-empty-slot/decision-unconfirmed-empty-slot/
   failure-unknown-empty-slot/failure-unconfirmed-empty-slot/
   every-decision-failure-syscall-order-and-final-occupant/
   prior-outcome-mismatch/artifact-directory-replacement/
   missing-or-truncated-chain/duplicate-or-conflicting-decision/
   recovery-total-timeout/recovery-per-file-timeout/
   recovery-kernel-no-return-boundary/failure-persistence-failure tests pass
   and no `authorized=true` or equivalent path exists.
5. `R11E MIGRATION`: make the legacy module fail closed, run the complete old
   invariant mapping, repository-wide import search, Windows suite, WSL suite,
   security-contract suite, production/conformance reverse-import and
   AST-signature audit, environment-pollution and archive-membership audit,
   synthetic/native-evidence origin and stateful-input rejection audit,
   `NativeConformanceEvidence.v1` six-preimage semantic reaggregation,
   raw-status/namespace mutation audit, detached-result confusion audit,
   independent code audit,
   namespace audit, and receipt/claim audit. Gate: all tests pass and every
   audit returns `P0=0/P1=0`.
6. `R11F FINAL PLAN REVIEW`: set the plan to `READY_FOR_FINAL_REVIEW`, build one
   bundle, dispatch a fresh first-principles reviewer with the external
   declaration, obtain START/advisory-result/END/handoff evidence, and present
   the result to the user. Only the user chooses accept/revise/reject.

Round 11 does not enter Recorder production implementation. A failed stage
returns to its corresponding RED or GREEN owner; a Master/dispatch defect ends
the automated review and is recorded in the handoff.

## Architecture candidate comparison

Selection is based on the required evidence claim, not implementation
familiarity:

| Candidate | Assumptions/dependencies | Strengths | Failure modes and evidence limit | Testability/maintenance |
|---|---|---|---|---|
| In-process monkeypatch/test double | Private symbols stay stable; a process crash can be simulated without losing the test process. | Lowest implementation cost; fast unit feedback. | Cannot prove heap/capability loss, process death, handle cleanup, or post-effect crash recovery; implementation and oracle can share the same defect. | Easy initially; brittle under refactor; rejected as primary evidence. |
| Spawned actor + typed RPC coordinator | Python `spawn`, bounded framed IPC, and OS kill/join are available. | Real process isolation; deterministic schedule/effect ordering; one shared orchestration core; exact crash and cleanup evidence. | Coordinator/model may drift from native semantics; protocol and state-space complexity are high. | Closed schemas, replay, mutation witnesses, and native paired tests make drift observable. Selected. |
| Declarative trace-only replay/model checker | All relevant behavior can be represented without executing the shared core. | Small trusted runtime; exhaustive state exploration is possible. | Proves the model/trace, not that production shared-core control flow issued those operations; easy self-consistency. | Valuable independent oracle; retained only as verifier/replay, not execution evidence. |
| Real-kernel-only fault/concurrency suite | Target statuses/crash windows can be reproduced reliably on approved NTFS/ext4 hosts. | Highest fidelity for observed syscalls and namespace effects. | Rare statuses, precise crash windows, and races are nondeterministic or unreachable; slow and host-specific. | Mandatory positive/collision/ABI evidence; supplemental rather than complete. |

The selected combination is spawned actors for adversarial state-machine
execution, an independent declarative replay verifier, and real-kernel paired
cases for native truth. Re-selection is required if spawn cannot guarantee
process isolation/kill observation, typed RPC cannot remain bounded and
data-only, the shared core gains host-specific branches, or native paired
tests show a model/adapter semantic mismatch.

## Selected architecture

Create `recorder/` as an independent Python distribution.

Reasons:

- the root package currently declares `aegis.cli:main`, but `src/aegis/cli.py`
  does not exist;
- attaching Recorder packaging to that incomplete root entry would make a
  clean-wheel result ambiguous;
- a separate distribution gives Recorder an isolated dependency, test, wheel,
  and CLI contract;
- no runtime IDs, local session paths, keys, or agent registry state enter the
  repository.

`CODEBASE_FACTS.md` binds the read-only branch, HEAD, root pyproject hash,
source/test tree, absent `aegis`/`aegis_recorder` imports, current schema hash,
and current Python/tool versions. Implementation repeats those commands before
editing; drift is reconciled instead of silently inheriting this snapshot.

## Source touchpoints

```text
recorder/
  build_backend/
    aegis_recorder_build.py
  pyproject.toml
  wheel_source_manifest.v1.json
  sdist_source_manifest.v1.json
  deploy_source_manifest.v1.json
  README.md
  tools/
    deploy_protected_runtime.py
  src/aegis_recorder_bootstrap.py
  src/aegis_recorder/
    __init__.py
    __main__.py
    code_manifest.v1.json
    recorder_verification_report.v1.schema.json
    cli.py
    writer_canonical.py
    writer_format.py
    journal.py
    framing.py
    proxy.py
    engine.py
    guard.py
    supervision_sidecar_writer.py
    supervision_sidecar_verifier.py
    platform_base.py
    platform_posix.py
    platform_windows.py
    win32_types.py
    verifier_canonical.py
    verifier_input_posix.py
    verifier_input_windows.py
    verifier_parser.py
    verifier_state.py
    verifier_report.py
    report_semantic_validator.py
  tests/
    independent_oracle.py
    fixtures/
      mutation_ledger.v1.json
      golden/
        journal_clean.v1.aegisrec
        supervision_clean.v1.aegissup
        annotated_offsets.v1.json
        posix_approval_record.conformance.v1.txt
        posix_stdlib_manifest.conformance.v1.txt
        posix_elf_closure_manifest.conformance.v1.txt
        posix_deployment_report.conformance.v1.json
      traces/
        lifecycle_valid.v1.json
        lifecycle_invalid.v1.json
    helpers/
      echo_app_server.py
      blocking_child.py
      inherited_handle_probe.py
      external_launcher_conformance_harness.py
      posix_external_prerequisite_conformance.py
    test_writer_format_red.py
    test_verifier_mutations_red.py
    test_report_semantics_red.py
    test_journal_faults_red.py
    test_proxy_state_machine_red.py
    test_process_containment_red.py
    test_guard_deadline_red.py
    test_supervision_sidecar_red.py
    test_session_directory_verification_red.py
    test_production_bootstrap_red.py
    test_contract_consistency.py
    test_windows_handle_inheritance_red.py
    test_windows_host_job_red.py
    test_engine_isolation_red.py
    test_protected_runtime_deploy_red.py
    test_protected_runtime_deployer_launch_red.py
    test_external_launcher_conformance_red.py
    test_protected_runtime_publish_identity_red.py
    test_bootstrap_import_policy_red.py
    test_bootstrap_failure_contract_red.py
    test_windows_argv_serializer_red.py
    test_packaging_red.py
    test_offline_wheel_red.py
```

Repository integration touchpoints:

```text
.gitattributes
.gitignore
schemas/aegis/v2/recorder_verification_report.v1.schema.json
docs/recorder/*
CONTINUATION.md
```

Review-gated Phase0 derived artifacts are:

```text
schemas/aegis/v2/schema_bundle.v1.json
evaluation/aegis_v2/reference/source_manifest.v1.json
evaluation/aegis_v2/evaluation_manifest.v1.json
```

They are not regenerated from an unreviewed Recorder schema. First the
independent schema reviewer must accept removal of the five non-JCS-safe
boundary literals and the fixed-validator boundary matrix; only then are all
three derived artifacts rebuilt together and their closure/hash tests rerun.

Root `pyproject.toml`, `config/`, agent registry, and Master subagent manifest
are outside Recorder implementation scope.

The production operator launcher and its approved-hash root are also outside
Recorder delivery. Recorder delivers only the executable deployer, the
normative launcher contract, and an independent launcher-conformance harness.
No conforming external launcher means deployment is unavailable; no project
binary may self-promote into that authority role.

## Packaging

The three repository source manifests use exact
`RecorderSourceManifest.v1`:

```text
artifact_kind="DEPLOY_SOURCE" | "WHEEL_SOURCE" | "SDIST_SOURCE"
entries=<source entry array>
schema="RecorderSourceManifest.v1"
self_policy="EXCLUDED"
```

Each entry is exactly
`{mode="100644"|"100755",path=PATH,sha256=SHA256_ID,
size=<JSON integer 0..16777216>,type="REGULAR_FILE"}`. Entries are 1..512,
strictly ordered by raw UTF-8 path bytes, case-fold unique, and total at most
67,108,864 bytes. No directory, link, reparse point, device, missing member,
unlisted member, alternate mode, or path outside the manifest's fixed source
root is legal. A manifest content ID is SHA-256 over
`"AEGIS_RECORDER_SOURCE_MANIFEST_V1\0"` plus its exact canonical bytes.

`self_policy="EXCLUDED"` means the manifest file never lists or authorizes
itself; its expected content ID comes from the external
`Round11StageCandidate.v1`. The dependency graph is acyclic:

- `deploy_source_manifest.v1.json` lists only the standalone deployer and its
  repository-owned static data;
- `wheel_source_manifest.v1.json` lists the build backend and exact runtime
  wheel inputs, excluding all three source manifests from the wheel;
- `sdist_source_manifest.v1.json` lists the exact sdist members, including the
  deploy and wheel manifests but excluding itself.

An unpacked sdist can therefore build the wheel from its included wheel
manifest, but v1 does not claim that an sdist can rebuild an identical sdist
without the externally bound sdist manifest. Before any build/deploy test,
the stage gate verifies all three manifest IDs, their exact entry bytes, the
acyclic inclusion rules, and complete source-root membership. The manifests
are deterministic selection inputs, not self-authenticating authority.

Recorder packaging is frozen as:

```text
distribution name = aegis-recorder
normalized name = aegis_recorder
version = 0.1.0a1
Requires-Python = >=3.12,<3.14
wheel tag set = py312-none-any, py313-none-any
wheel filename =
  aegis_recorder-0.1.0a1-py312.py313-none-any.whl
dist-info directory = aegis_recorder-0.1.0a1.dist-info
sdist filename = aegis_recorder-0.1.0a1.tar.gz
runtime dependencies = none
build dependencies = none
```

Recorder `pyproject.toml` contains:

```toml
[build-system]
requires = []
build-backend = "aegis_recorder_build"
backend-path = ["build_backend"]

[project]
name = "aegis-recorder"
version = "0.1.0a1"
requires-python = ">=3.12,<3.14"
dependencies = []

[project.scripts]
aegis-recorder = "aegis_recorder.cli:main"
```

The repository-local backend uses only the standard library. PEP 517 requires
`build_wheel` and `build_sdist`; v1 implements both. It also implements
`get_requires_for_build_wheel`, `get_requires_for_build_sdist`, and
`prepare_metadata_for_build_wheel`. Both requirement hooks return `[]`.
Editable-build hooks are absent. Unknown nonempty `config_settings` are
rejected.

`build_wheel` returns only the wheel basename and places one wheel in the
supplied directory. If `metadata_directory` is supplied, the backend verifies
the complete prepared dist-info member set and exact bytes, including
unrecognized members, and emits byte-identical metadata as required by PEP
517. It never ignores or rewrites caller-supplied prepared metadata.

`build_sdist` emits a deterministic POSIX pax-format `.tar.gz` with one
top-level `aegis_recorder-0.1.0a1/` directory, the exact source allowlist,
`pyproject.toml`, build backend, manifests, and `PKG-INFO`. Tar members use
lexical UTF-8 path order, uid/gid zero, empty owner/group names, mtime zero,
fixed regular-file modes, and no links. The gzip header uses mtime zero and no
source filename. Building a wheel from the unpacked sdist must produce the
same wheel bytes as a direct build in the same interpreter/platform profile.

Wheel metadata bytes are fixed:

```text
METADATA:
  Metadata-Version: 2.3
  Name: aegis-recorder
  Version: 0.1.0a1
  Summary: Deterministic local transport evidence recorder for Aegis.
  Requires-Python: >=3.12,<3.14
  no Requires-Dist

WHEEL:
  Wheel-Version: 1.0
  Generator: aegis-recorder-build 0.1
  Root-Is-Purelib: true
  Tag: py312-none-any
  Tag: py313-none-any

entry_points.txt:
  [console_scripts]
  aegis-recorder = aegis_recorder.cli:main
```

Each file uses UTF-8, LF, and one final LF. The wheel is `ZIP_STORED` to remove
zlib-version variability. Every `ZipInfo` has a normalized relative `/` path,
no directory entry, no link, no extra field, no archive comment,
`date_time=(1980,1,1,0,0,0)`, `create_system=3`, UTF-8 flag, and regular-file
mode `0100644`. Non-`RECORD` members are ordered by raw UTF-8 path bytes;
`RECORD` is last. Duplicate, absolute, backslash, empty-component, `.`, `..`,
non-NFC, unlisted, link, reparse, device, or case-colliding names fail.
The complete wheel is `1..67108864` bytes with `1..512` members. Each UTF-8
member path is `1..512` bytes, each stored member is at most `16777216` bytes,
and the sum of uncompressed member sizes is at most `67108864`. Builder,
independent verifier, and both protected-runtime deployers enforce the same
limits before allocation or extraction.

`RECORD` is UTF-8 CSV with LF and minimal quoting. Every member except itself
has:

```text
normalized/path,sha256=<urlsafe-base64-without-padding>,<decimal-size>
```

Its own row is:

```text
aegis_recorder-0.1.0a1.dist-info/RECORD,,
```

The backend reads only `wheel_source_manifest.v1.json` or
`sdist_source_manifest.v1.json`. Missing, extra, changed-size, changed-hash,
absolute, parent-traversal, link, and observed reparse members fail before
publication. It never imports runtime code, mutates source, invokes another
build tool, reads a package index, or accesses the network.

Publication uses a same-directory create-new temporary file. The backend
writes, flushes, `fsync`s, closes, reopens, and independently validates the
complete archive before one atomic no-overwrite `os.link(temp, final)`
publication. An existing final name fails. Failure before the link leaves no
final artifact. After a successful link, the final artifact is already
complete; temporary-file cleanup cannot invalidate it. A filesystem without
same-directory hard-link support is unsupported rather than falling back to a
partial visible copy.

The wheel contains top-level `aegis_recorder_bootstrap.py` plus
`aegis_recorder/code_manifest.v1.json`. The manifest lists every production
package/runtime member except itself and the non-circular bootstrap trust
anchor by normalized wheel path, byte size, and SHA-256. Its own
restricted-canonical-JSON SHA-256 is embedded both in the bootstrap and
`SESSION_STARTED`. Packaging tests recompute every member and reject any
bootstrap whose embedded digest differs.

`recorder/tools/deploy_protected_runtime.py` is the only Windows production
deployer source. It uses only a provenance-guarded standard-library allowlist
and never imports the backend, Recorder runtime, candidate site packages, or
wheel code. `deploy_source_manifest.v1.json` freezes its reviewed source bytes;
both are repository/sdist operational sources and are excluded from the runtime
wheel and protected root. A production copy is selected outside all
candidate-controlled paths. It becomes executable only after an external
operator launcher, using an expected hash from outside the repository/wheel,
holds and hashes that deployer plus the selected interpreter without
write/delete replacement. The in-process self-hash detects drift but cannot
self-authorize.

Windows production uses the exact deploy argv, direct `CreateProcessW` launch,
operator-protected cwd, exact two-variable environment, interpreter flags,
import-provenance rules, fixed-drive path grammar, and terminal report contract
in `SUPERVISOR_CONTRACT.md`. Linux/WSL2 validation instead requires the
external native provisioning/launch contract in
`POSIX_ADAPTER_CONTRACT.md`; Recorder implements only its conformance harness
and has no self-authorizing fallback.

Given the held expected-hash wheel, the deployer independently revalidates the
complete wheel/`RECORD`/ZipInfo set, bootstrap, embedded manifest digest, and
runtime allowlist. It accepts only native fixed-drive NTFS objects, resolves
every path component through retained no-reparse handles, and creates one
cryptographically unpredictable create-new staging root relative to the held
parent of the absent final root. It extracts only:

```text
aegis_recorder_bootstrap.py
aegis_recorder/code_manifest.v1.json
<manifest-listed runtime files>
```

Each file is created without overwrite, size/hash checked while writing,
`FlushFileBuffers`ed, closed, reopened relative to retained directories without
reparse traversal, reread, and checked again. Exact enumeration rejects every
extra, missing, wrong-type, alternate-case, reparse, `.pyc`, `__pycache__`,
`.dist-info`, `Scripts`, and installer-metadata member. The deployer records
staging `FILE_ID_INFO` immediately after create-new and rechecks it after every
member file handle is closed. It then calls
`NtSetInformationFile(FileRenameInformation=10)` on its held
`DELETE`-capable staging handle with `ReplaceIfExists=FALSE`, the held
final-parent handle as `RootDirectory`, and the exact single final component.
No Win32 wrapper, null-root, replace, or path-based rename is permitted.

Rename success publishes the namespace but does not yet prove deployment
success. The deployer reopens the final component relative to the same held
parent and requires the pre-rename staging, post-rename staging, and final
handle volume serial/FileId values to match, then re-enumerates exact
membership. A post-publication mismatch reports a failed published-but-
unconfirmed result and performs no rollback. Every pre-publication failure
leaves the final name absent unless a foreign actor occupied it; that occupant
is untouched.

No failed staging tree is recursively deleted, renamed, repaired, quarantined,
or reused automatically. The one-line deployment report preserves the original
staging path as exact UTF-16LE lowercase hex plus its `FILE_ID_INFO`. Operator
policy owns later quarantine.

Ordinary `pip install` into a fresh virtual environment remains mandatory wheel
compatibility testing. `pip install --target` is never production deployment
evidence and never creates a protected runtime. The protected root identifies
local code bytes but does not create external authority.

The packaged report schema must be byte-identical to the repository schema.
The production validator does not interpret arbitrary JSON Schema and does not
depend on a third-party schema engine. It implements the fixed v1 structural
field/type/bound contract with standard-library code, then applies the separate
semantic relations. Clean-wheel tests compare schema SHA-256 values and run
both the fixed structural validator and semantic validator against exhaustive
positive and single-field mutation corpora.

Clean packaging validation:

1. create a repository-external virtual environment with no index access;
2. call the PEP 517 hooks directly through a standard-library harness, then
   build twice through
   `pip wheel --no-index --no-deps --no-build-isolation` and require identical
   wheel SHA-256 values;
3. build the sdist twice, require identical SHA-256 values, unpack it in a
   repository-external directory, build its wheel, and compare that wheel
   byte-for-byte with the direct wheel;
4. independently inspect every filename, member, metadata field, WHEEL tag,
   entry point, ZipInfo flag, permission, timestamp, `RECORD` hash, and
   `RECORD` size;
5. require no `Requires-Dist` metadata and prove build/import/verification with
   the package index and network unavailable;
6. install with `pip install --no-index --no-deps` into a second environment;
7. run console-script help and module help;
8. run the standard-library `unittest` portable suite;
9. run verifier against a golden journal;
10. prove Windows protected-bootstrap proxy stdout/stderr isolation with real
    pipes;
11. inject every pre-publication backend failure and prove no final wheel or
    sdist exists; pre-create the final name and prove it is never overwritten;
12. run the externally anchored independent deployer against the verified wheel
    and every frozen launch/path/write/publish/report fault; require exact
    protected-root membership only after post-publication FileId confirmation,
    distinguish pre-publication from published-but-unconfirmed failures,
    preserve every failed staging namespace, then compare two sequential clean
    launch snapshots with no external mutation between them.

Windows production validation uses CPython 3.13. WSL validation uses the
externally approved `LINUX_PROTECTED_BOOTSTRAP_V1` exact CPython 3.12.3
interpreter digest/build, direct-`P` layout, and one-line approved
`python3.12._pth`; it is explicitly non-release.

Informative packaging-source provenance:

The plan fully states the accepted packaging byte contract. The following URLs
are navigation for independent fact checking, not incorporated normative
content. A live-site change cannot change an accepted plan byte.

- PEP 517 backend hooks: https://peps.python.org/pep-0517/
- wheel binary format:
  https://packaging.python.org/en/latest/specifications/binary-distribution-format/
- core metadata:
  https://packaging.python.org/en/latest/specifications/core-metadata/
- entry points:
  https://packaging.python.org/en/latest/specifications/entry-points/
- CPython 3.13 `-B`, `-I`, `-S`, and `-X utf8` semantics:
  https://docs.python.org/3.13/using/cmdline.html
- CPython 3.13 Windows argument-sequence conversion:
  https://docs.python.org/3.13/library/subprocess.html#converting-an-argument-sequence-to-a-string-on-windows

## Protocol representation choice

v1 retains restricted canonical JSON metadata instead of adding a binary TLV
codec. Both can be unambiguous. Restricted JSON has the smaller defect surface
because Writer, Verifier, and the test oracle can independently implement and
inspect the same bounded grammar with standard parsing primitives. Float,
duplicate key, surrogate, whitespace, alternate escape, depth, node, and size
behavior is normative and mutation-tested.

OS identity does not rely on JSON text. Windows values are encoded from exact
UTF-16LE code-unit bytes; POSIX values are encoded from exact OS bytes. The
canonical JSON stores their normative byte representation and hash. Display
strings are advisory.

## Implementation boundaries

### Writer

Writer canonicalization and digest code implement only the normative protocol.
The journal owns one native file handle and one lock. It performs one counted
write path followed by the platform flush. Any partial write or flush error
poisons the journal permanently and prevents later forwarding.

### Verifier

Verifier has separate canonicalization, digest, parser, and state modules. It
opens the journal read-only, streams it, never imports Writer helpers, never
repairs bytes, and always reports local assurance plus
`authority_verified=false`.

The report validator does not import the report builder. Its fixed v1
structural implementation and semantic implementation are separate modules.
It checks field/type/bound rules plus arithmetic/count/list/hash relationships.
Its input is only a report, so it claims report-internal consistency, not
factual membership in a session state. `verify ABSOLUTE_SESSION_DIRECTORY`
remains the evidence operation. It reads only the fixed journal and supervision
sidecar member names; valid Windows supervision remains reportable when the
journal was never created or is missing from the supplied copy. The published
JSON Schema is a reader contract, not executable runtime authority and not a
completion gate by itself.

When the journal is absent, `WINDOWS_SUPERVISION_ONLY` is permitted only if the
sidecar is structurally, cryptographically, and semantically valid; that row is
INCOMPLETE/exit 1. An invalid sidecar with no journal remains
`evidence_platform_profile=UNDETERMINED`,
`assurance_level/evidence_scope/ordering_scope=NONE/NONE/NONE`,
INVALID/exit 2. Its report retains only physical file bytes and the longest
valid sidecar prefix diagnostics; it cannot claim supervision integrity.

### Protected runtime deploy and bootstrap

Production never uses pip to materialize the protected root. The deployer is
Windows-only. An external operator launcher must hold and independently hash
the interpreter and operator-protected deployer from an approval record outside
the candidate before starting this exact argv:

```text
<ABSOLUTE_TRUSTED_PYTHON_EXE>
-I
-S
-B
-X
utf8
<ABSOLUTE_OPERATOR_PROTECTED_DEPLOYER_PY>
deploy
--python-sha256
<64_LOWERCASE_HEX>
--deployer-sha256
<64_LOWERCASE_HEX>
--stdlib-root
<ABSOLUTE_TRUSTED_STDLIB_ROOT>
--stdlib-dynload-root
<ABSOLUTE_TRUSTED_STDLIB_DYNLOAD_ROOT>
--control-dir
<ABSOLUTE_OPERATOR_PROTECTED_CONTROL_DIRECTORY>
--wheel
<ABSOLUTE_VERIFIED_WHEEL>
--wheel-sha256
<64_LOWERCASE_HEX>
--final-root
<ABSOLUTE_ABSENT_PROTECTED_RUNTIME_ROOT>
```

The direct `CreateProcessW` call binds exact `lpApplicationName`, canonical
`lpCommandLine`, protected control-directory cwd, the exact
`SystemRoot`/`WINDIR` Unicode environment and no other variable. It sets
`STARTF_USESTDHANDLES`; assigns a read-only `NUL`, deploy-report child pipe, and
distinct stderr child pipe to `hStdInput/hStdOutput/hStdError`; places exactly
those three dedicated inheritable duplicates in
`PROC_THREAD_ATTRIBUTE_HANDLE_LIST`; and calls with `bInheritHandles=TRUE`.
Parent-side and original handles are non-inheritable, and no ambient handle is
inherited. The launcher retains non-replaceable interpreter, deployer, and
ancestor handles until exit. The deployer checks the external expected
self/interpreter hashes again. Before any non-preloaded import it requires the
observed CPython 3.13.13 `sys.path` vector, in order, to be
`python313.zip`, `DLLs`, `Lib`, interpreter root; the externally bound ZIP
candidate must be absent. It validates preloaded `encodings` and import
machinery, then performs the only permitted path mutation by narrowing in place
to held `DLLs` and `Lib`. The pre-execution guard permits only built-in/frozen
modules or regular non-reparse standard-library `.py`/`.pyd` origins under
those two trusted roots. Later path/finder/cache mutation fails.

The external launcher is an operator-provided prerequisite, not an
implementation touchpoint. `external_launcher_conformance_harness.py` exercises
its observable handle/hash/argv/environment/cwd/output obligations with
adversarial fixtures but cannot confer production authority on itself or on the
test launcher. A missing or nonconforming operator launcher blocks deployment,
not compilation or portable Recorder tests.

A separate external launcher owns the initial Windows operator-to-guard proxy
entry. Its external slot selects expected interpreter/bootstrap hashes and
identities. It applies the same fixed-drive NTFS, DOS-device equality, native
no-reparse component traversal, held-file hashing, and no-write/no-delete-
replacement rules, then retains interpreter/bootstrap/ancestor handles until
guard exit. Its `STARTUPINFOEXW` contains exactly three dedicated inheritable
standard-handle duplicates and no trust or ambient handle. Missing or
nonconforming operator-to-guard launch authority makes proxy unavailable; the
bootstrap's later path/self checks cannot authorize bytes that already ran.

All path arguments match the frozen uppercase-drive grammar and resolve only on
`DRIVE_FIXED` NTFS volumes. For every used drive, the launcher and deployer
independently require the canonical volume-GUID name and exact equality between
the first current `QueryDosDeviceW` native targets for `X:` and the stripped
volume-GUID name. The launcher checks once immediately before process creation
and retains its native handles. The deployer checks during preflight, retains
that pair, and alone rechecks it immediately before publication. No
launcher/deployer synchronization channel or post-launch launcher recheck is
claimed. Failure, ambiguity, inequality, or deployer-observed drift rejects
SUBST/DOS-device directory redirection. An unobserved change-and-restore is
outside the claim and cannot retarget the retained publication handles. Native
volume roots and every component are opened and retained with relative
`NtCreateFile`, `OBJ_DONT_REPARSE`, and `FILE_OPEN_REPARSE_POINT`; all
attribute/tag/volume/FileId/spelling checks use handles. No string-path
authorization decision is reopened.

The independent deployer validates the expected-hash wheel again, extracts only
bootstrap, manifest, and manifest-listed runtime files into a create-new
same-parent staging root, flushes and rereads every file, and rejects all
membership/type/path/hash/case/reparse/bytecode drift. Before staging creation
it preflights `FileRenameInformation == 10`,
`sizeof(FILE_RENAME_INFORMATION)==24`, the 64-bit
`FILE_RENAME_INFORMATION`
`offsetof(ReplaceIfExists/RootDirectory/FileNameLength/FileName)=0/8/16/20`,
two-byte `WCHAR`, 16-byte `IO_STATUS_BLOCK`, the
`ntdll!NtSetInformationFile` export, fixed NTFS, an externally approved
Windows build/profile with real-host rename/collision conformance evidence,
and required access/share capabilities. It
closes all member-file handles but retains the final parent and
`DELETE`-capable staging handles. Publication uses only:

```text
NtSetInformationFile(
  held_staging,
  io_status_block,
  FILE_RENAME_INFORMATION(
    ReplaceIfExists=FALSE,
    RootDirectory=held_final_parent,
    FileNameLength=len(final_component_utf16le),
    FileName=final_component_without_NUL),
  Length=max(sizeof(FILE_RENAME_INFORMATION),
             offsetof(FILE_RENAME_INFORMATION,FileName)+FileNameLength),
  FileInformationClass=FileRenameInformation)
```

The checked allocation is zero-filled and has exactly
`max(24,20+FileNameLength)` bytes; byte zero remains `FALSE`, bytes 1..7
remain zero, the non-NUL filename starts at offset 20, and `FileNameLength`
excludes the zero tail. Only matching `STATUS_SUCCESS` from the call and the
`IO_STATUS_BLOCK` commits. Pending, wait, mismatch, and unknown-outcome
handling uses the exact Windows state table in Round 11 above. The
final name is one component. A foreign occupant must return
`STATUS_OBJECT_NAME_COLLISION` and is not replaced. After rename, the deployer
retains the staging handle, reopens the final component relative to the held
parent, and accepts success only when pre/post staging and final
`FILE_ID_INFO` values plus exact recursive membership agree. A failed
post-publication check reports `publication_state=PUBLISHED` and
`PUBLISHED_IDENTITY_UNCONFIRMED`; it never claims success or rolls back.
`SetFileInformationByHandle`, `RootDirectory=NULL`, and pathname rename are
explicitly forbidden.

After any controlled first-statement outcome, stderr is exactly empty. While
the report channel is healthy, stdout is exactly one LF-terminated
restricted-canonical-JSON ASCII object with schema
`AegisRecorderProtectedRuntimeDeploymentReport.v1`. Paths are exact UTF-16LE
code units encoded as lowercase hex, never display strings. The original
staging path and its volume-serial/FileId are populated after create-new
staging on every success or failure. `publication_state` is exactly
`NOT_PUBLISHED`, `PUBLICATION_OUTCOME_UNKNOWN`, or `PUBLISHED`; the unknown row
keeps both locators and staging identity and makes no path-inferred claim.
Exit 0 is only `DEPLOYED`; exit 64 is only
`INVALID_INVOCATION`; exit 1 covers controlled rejection, pre-publication
deployment failure, unknown publication outcome, and
published-but-unconfirmed failure. An internal failure
with a healthy report channel has one canonical row and exit 70. A report-
channel failure has no report object: it exits 74 with empty stderr, and the
external launcher retains the exact observed stdout byte string, which may be
any prefix, including empty or complete, of the preselected intended row,
whether that row is success or failure. The deployer emits the precomputed
ASCII-plus-LF bytes only through one blocking binary unbuffered counted
`WriteFile` loop. Positive short progress advances by the acknowledged count;
zero progress, invalid count, write error, or the one terminal `CloseHandle`
failure preserves the acknowledged prefix and invokes a non-finalizing exit
74. No Python text stream, flush/finalizer, retry, stderr fallback, or second
close participates. Healthy terminal close uses the same fixed process-exit
path with the intended result code, so CPython cannot rewrite it to 120. Exit
74 is reserved for that state; the launcher never parses its bytes as a report.
Exit 70 is accepted only with one complete canonical row whose embedded
`exit_code` is 70. No failure path recursively deletes, renames, quarantines,
repairs, or reuses staging. Ordinary wheel/pip installation remains a
compatibility test.

The production guard and internal engine argv both begin:

```text
ABSOLUTE_TRUSTED_PYTHON_EXE -I -S -B -X utf8 ABSOLUTE_BOOTSTRAP_PY
```

Before Recorder import, the top-level bootstrap barrier verifies isolated,
no-site, no-bytecode, and UTF-8 flags, sets and confirms
`sys.dont_write_bytecode`, validates exact root membership, installs the frozen
stdlib/runtime import allowlists, and suppresses every Recorder diagnostic
write. Recorder does not call the protected root immutable. Two sequential
clean launches with no injected external mutation must independently verify and
observe identical protected-root name/type/size/hash members before import.
Public console/module `proxy` remains an exit-64 usage rejection on every
platform and cannot enter guard/engine.

Runtime module names are derived only from manifest-listed
`aegis_recorder/**/*.py` regular files. The finder rejects namespace packages,
extension/zip/absolute-file loaders, path mutation, unlisted transitive package
modules, and every non-preloaded stdlib top-level module outside the immutable
bootstrap allowlist.

Controlled failures map exactly as follows:

| Category | Exit |
|---|---:|
| bootstrap argv | 64 |
| isolation, manifest, protected path, pipe, host-Job, or session-path preflight | 10 |
| sidecar or outer-Job supervision setup | 16 |
| engine creation | 12 |
| engine outer-Job assignment, engine resume, or startup handshake | 16 |
| journal create/write/flush after engine start | 11 |
| target create/assignment/resume | 12 |
| otherwise unclassified bootstrap/guard/engine exception | 16 |

After the bootstrap's first statement, controlled pre-target failures produce
exactly zero stdout and stderr bytes; after target creation, Recorder still
contributes zero bytes. Loader, syntax, or trust-anchor failure before that
first statement is an external launcher precondition and receives no fabricated
output or evidence guarantee.

### Proxy

Proxy validates byte handles before child launch. Relay threads never hold the
journal lock during source or destination I/O. Every destination write is
preceded by two durable entries: observation and attempt-start.

Guard-to-engine and engine-to-target argv use the same independently
implemented `PYTHON_LIST2CMDLINE_UTF16_V1` algorithm. Outer quotes are added
only for empty/space/tab arguments; a quote alone is escaped but does not add
outer quotes. Journal fields bind the exact UTF-16LE buffer, count, hash, and
`lpApplicationName`.

### Process containment

The Windows entry process is an independent guard outside an outer
kill-on-close Job. It creates the engine suspended, assigns it to that Job, and
then resumes it. The engine creates the target with documented Win32 APIs and
`CREATE_SUSPENDED`, assigns it to a nested target Job, and publishes target
process/thread handles as handshake state 2. A daemon worker only validates
those handles and exits. The guard main thread persists `JOURNAL_BOUND`,
publishes state 3, and acknowledges the engine. The engine then starts relays,
durably records `CHILD_SPAWNED` and `CHILD_RESUME_ATTEMPT_STARTED`, publishes
state 4, and signals resume intent.

Before engine resume, the guard arms one shared 120-second startup waitable
timer; the engine inherits a duplicate of that same kernel object. Guard and
engine use failure-first waits throughout. Only the guard main thread may
cancel/check the timer and call target `ResumeThread`, exactly once, after
state 4. It publishes the exact return/error as state 5; the engine only
persists the matching resume terminal. Neither worker nor engine has resume
authority. The guard separately writes `supervision.aegissup`; the engine
separately writes `journal.aegisrec`. A separate ten-second runtime
shutdown/drain deadline starts after fatal shutdown or target exit. After a
Windows termination call returns, reclamation polling has a final two-second
bound; missing confirmation produces a nonzero guard exit, not a false
reclamation claim. No duration is claimed for a nonreturning Windows kernel
call or an undetected post-handshake engine defect that neither signals
shutdown nor lets the target exit.

The strict Windows v1 profile rejects a guard already associated with any host
Job Object. Target exit enters output draining, not fatal cancellation:
stdout/stderr continue to EOF while only client stdin is stopped.

Linux/WSL2 follows `POSIX_ADAPTER_CONTRACT.md` and can reach these mechanics
only through an external operator trust slot. Its root-owned,
runtime-nonwritable fixed ASCII approval, stdlib, and ELF-closure manifests
bind the held launcher, static deployment adapter, interpreter closure, wheel,
bootstrap, exact getpath file, curated roots, and final name. The exact
CPython 3.12.3 interpreter lives at `P/python3.12`; the one-line
`P/python3.12._pth` exposes only `P/lib/python3.12` during startup. Before exec,
the launcher validates that file, the direct layout and build, and absence of
all venv/build/competing-`._pth` overrides. The nonzero-UID/nonzero-GID launcher
has an empty supplementary-group set, empty capabilities, and
`no_new_privs`. The closed-ABI static `ET_EXEC` adapter alone provisions and
publishes the protected root through its
frozen argv/FD/env/cwd/report ABI; report-channel failure is exit 74 and never
an accepted report. The runtime launcher normalizes inherited signal state,
uses pre-exec FDs `0..12`, and executes held CPython through FD 12 with
`execveat(AT_EMPTY_PATH)`. CPython's first bootstrap statement sees exactly
FDs `0..11`.

After the three externally approved startup `encodings` imports and before any
new filesystem import, the bootstrap cursor-parses the approval record
on FD 10 and stdlib manifest on FD 11, validates the initial FD/environment/
argv/signal/getpath profile, reopens and retains the exact getpath file, and
reaps an exact preflight child. It then loads the
externally approved `_hashlib` seed through a retained procfd, verifies all
bound bytes, verifies complete package-parent relations, the exact one-to-one
preloaded-`encodings`/`PRELOADED` relation, and disjoint remaining early/
stdlib/protected module-name sets, removes path finders, and permits `LATE`
stdlib plus protected-runtime execution only from hash-verified retained FDs.
The seed is the
only filesystem-backed import before that finder transition. The interpreter
ELF loader, its dynamic
closure, getpath pathname read, hash seed, and preloaded encodings remain externally approved
prerequisites; post-start checks do not claim pre-loader protection. This plan
does not infer any of those properties from the Windows mechanism. A Linux
proxy run becomes validation evidence only after both the external prerequisite
and Recorder conformance suites pass.

After protected entry, the private Python adapter retains directory
descriptors, uses `O_EXCL|O_NOFOLLOW|O_CLOEXEC|O_APPEND`, persists the
parent-directory, journal, and session-directory entries in the declared
order, and launches the held native ELF target/cwd through fixed procfd
descriptors with `start_new_session=True`, `shell=False`, `close_fds=True`,
`pass_fds=(5,6)`, and exactly `LC_ALL=C`. The target observes an empty signal
mask and default `SIGCHLD`/`SIGTERM`/`SIGPIPE`; an actual exit 7 must remain 7.
Fatal shutdown
escalates one recorded process group from `SIGTERM` to `SIGKILL`, then requires
bounded direct-child reaping and group-absence confirmation. POSIX has no
independent guard; Recorder death and descendant `setsid()` escape remain
explicit non-production boundaries.

## TDD sequence

### Atomic stage 1: format and independent verifier

RED:

- hand-built golden vector is rejected because implementation is absent;
- every truncation, bit flip, length bomb, noncanonical metadata, sequence
  mutation, and state mutation fails against the absent verifier;
- a schema-valid report with contradictory observation/forward counts fails
  against the absent semantic report validator;
- hand-built traces covering success, zero-byte failure, positive-prefix
  failure, explicit unknown outcome with a proven lower bound, no attempt, and
  attempt without outcome fail against the absent mutually exclusive
  forwarding-accounting implementation;
- a report-only boundary case with an internally valid substituted in-range
  sequence documents that only `verify ABSOLUTE_SESSION_DIRECTORY` proves
  factual membership;
- worst-case issue counts above the entry-count limit fail against the absent
  signed-64 issue-count contract;
- the publication schema asserts JSON `integer` shape but contains no
  `minimum`/`maximum` literal outside the RFC 8785/JCS safe-integer domain; an
  independent fixed validator accepts `child_return_code=-2^63` and `2^63-1`,
  rejects `-2^63-1` and `2^63`, accepts nonnegative counters from `0` through
  `2^63-1`, and rejects `-1` and `2^63`; parsing never round-trips these values
  through binary floating point;
- every legal PASS, INCOMPLETE, INVALID, INPUT_ERROR, and INTERNAL_ERROR row is
  accepted while every single-field exit/verdict/clean/reason/issue/flag flip is
  rejected;
- every result contains an exact signed-64 `child_return_code` or null and all
  57 non-OK `reason_counts`; count sums, ordered positive reason IDs, issue
  multiplicity, forwarding counters, partial-forward bounds, and child-nonzero
  equivalence are mutation-tested in both directions;
- `journal_present=false`,
  `evidence_platform_profile=WINDOWS_SUPERVISION_ONLY`,
  `JOURNAL_MISSING`, and `supervision_journal_bound` preserve whether a valid
  guard sidecar predates journal binding or proves a now-missing journal;
  no-journal/no-sidecar remains an input error;
- journal absent plus invalid sidecar requires
  `evidence_platform_profile=UNDETERMINED`, exact
  `NONE/NONE/NONE` assurance/scope/ordering, INVALID/exit 2, and only physical
  bytes plus longest-valid-prefix diagnostics; mutations that promote it to
  supervision integrity are rejected;
- `WINDOWS_SUPERVISION_ONLY` is accepted only for `sidecar_valid=true` with
  INCOMPLETE/exit 1;
- mutations across the exact journal, supervision-only, and no-evidence
  assurance/scope/ordering triples are rejected in both directions;
- a session directory, journal member, or sidecar member containing an observed
  symlink/junction/reparse component is rejected without reading its target;
- every result contains exactly the three ordered boundary IDs, including
  `OS_FLUSH_RETURN_ONLY`;
- declarative valid/invalid state traces fail against the absent verifier.

GREEN:

- implement Writer format;
- implement independent Verifier;
- implement the separately imported report semantic validator;
- produce the exact golden vector and annotated offsets.

Gate:

- all format and semantic mutations detected;
- schema-valid arithmetic contradictions are rejected;
- the Verifier assigns every observation to one forwarding bucket; the
  independent oracle proves failed/unresolved list membership, including
  positive-prefix failure and explicit unknown outcome;
- the report-only validator rejects internal list length/order/range
  contradictions without claiming journal membership;
- a checked-in declarative trace corpus, not generated by Writer or Verifier,
  covers every lifecycle transition and illegal ordering;
- Writer/Verifier import graph proves no critical helper sharing;
- Windows and WSL verifying the same copied session directory return
  identical canonical report fields except the two advisory absolute evidence
  paths; profile and supervision facts come from evidence, not verifier host.

#### Finite mutation ledger

`recorder/tests/fixtures/mutation_ledger.v1.json` is a reviewed finite input,
not a mutation generator. Every row binds the base fixture SHA-256, exact
field/path transformation, whether hashes are recomputed, affected invariant,
expected exit/verdict/reasons, and paired control ID. Tests fail if an
implementation executes an unlisted transform, omits a listed row, or changes
an expected result without updating the reviewed ledger.

Each relationship has both a violating mutation and a relationship-preserving
control. This prevents a Verifier that rejects every changed artifact from
passing the mutation suite.

| ID | Domain | Transformation | Relation | Expected |
|---|---|---|---|---|
| `M01` | journal | increment one sequence; recompute entry/suffix hashes but not logical continuity | breaks | exit 2; `SEQUENCE_GAP_OR_DUPLICATE` |
| `C01` | journal | renumber the same suffix contiguously; update references, counters, and all hashes | preserves | the trace's prior valid verdict |
| `M02` | journal | change one previous digest and recompute only that entry hash | breaks | exit 2; `PREVIOUS_DIGEST_MISMATCH` |
| `C02` | journal | change one payload, then update payload digest, entry digest, every later previous digest, and semantic references | preserves | valid alternate trace |
| `M03` | journal | move one observation from success to no-attempt while retaining success counters | breaks | exit 2; `SESSION_COUNTER_MISMATCH` |
| `C03` | journal | remove the attempt/outcome and consistently update session state | preserves | exit 1; `OBSERVATION_NOT_FORWARDED` |
| `M04` | journal | leave an attempt without outcome but retain a clean session end | breaks | exit 2; `INVALID_ENTRY_STATE` or `SESSION_COUNTER_MISMATCH` |
| `C04` | journal | leave the attempt unresolved, remove the clean claim, and update all counters | preserves | exit 1; `SEND_OUTCOME_UNKNOWN` |
| `M05` | journal | set wall time below the predecessor without the regression flag | breaks | exit 2; `WALL_CLOCK_FLAG_MISMATCH` |
| `C05` | journal | apply the same rollback and set the exact regression flag before rehashing | preserves | prior operational verdict |
| `M06` | report | change child return 0 to 5 only | breaks | validate-report rejects |
| `C06` | report | set return 5, clean false, exit/verdict incomplete, one `CHILD_NONZERO` count/reason/issue | preserves | validate-report accepts |
| `M07` | report | increment one forwarding count without changing lists/reasons/issues | breaks | validate-report rejects |
| `C07` | report | move one sequence between disjoint forwarding buckets and update every count/list/reason/issue relation | preserves | validate-report accepts |
| `M08` | report | set a partial-tail count without tail fields or `PARTIAL_TAIL` | breaks | validate-report rejects |
| `C08` | report | use the report emitted by a real truncated golden journal and retain its fully consistent tail fields/reason | preserves | evidence verify exits 1; `validate-report` accepts and exits 0 |
| `M09` | report | add one issue without changing `issue_count` or `reason_counts` | breaks | validate-report rejects |
| `C09` | report | add an allowed repeated issue and update exact multiplicity while retaining reason order | preserves | validate-report accepts |
| `M10` | report | reorder or omit one mandatory boundary ID | breaks | validate-report rejects |
| `C10` | report | change only advisory absolute journal path within its bounds | preserves | validate-report accepts |

Controls that preserve report-internal relationships do not prove journal
membership. Their purpose is solely to prove that the report validator accepts
different valid points in its declared relation space. Journal controls are
accepted only when the independent oracle reconstructs the changed trace.

### Atomic stage 2: durable journal

RED:

- injected short write, disk full, flush failure, clock rollback, existing
  session, link/reparse, and second writer tests fail;
- on POSIX, ancestor symlink, root/session identity swap, wrong owner/mode,
  hard-link count, missing `O_NOFOLLOW`, file/parent-directory fsync order, and
  lock contention tests fail.

GREEN:

- implement platform journal handles, create-new path, poison state, sequence,
  timestamps, write-all, flush, and close;
- implement the retained-dirfd POSIX creation and persistence sequence from
  `POSIX_ADAPTER_CONTRACT.md`.

Gate:

- no frame-forward method is called after a journal failure;
- partial tails remain untouched and are reported exactly.

### Atomic stage 3: relay state machine

RED:

- exact binary bytes, CRLF, Ctrl-Z, malformed JSON, empty line, incomplete
  frame, oversized frame, stderr chunks, partial destination write, blocked
  destination, and every crash window fail;
- every framed-stream OS read requests exactly one byte; an injected API that
  returns two bytes is rejected before classification, and a delimiter or
  limit-trigger byte is durably classified before the next read;
- Windows `TRUE/1`, `TRUE/0`, `FALSE/109`, cancellation-qualified
  `FALSE/995`, unqualified `FALSE/995`, and other errors, plus POSIX
  byte/empty/EINTR/error outcomes, follow the exact DATA/EOF/cancel/failure
  mapping;
- framed read failure and cancellation with an empty buffer require their source
  terminal, while the same failures with a nonempty buffer require an
  `INCOMPLETE_FRAME` retaining every buffered byte and the exact terminal cause;
- Windows `WriteFile(FALSE)` after zero or positive proven progress produces
  `FORWARD_OUTCOME_UNKNOWN`, never `FORWARD_FAILED`; a failed persistence of
  that outcome leaves only the durable attempt.

GREEN:

- implement bounded framing and relay logic;
- add deterministic external synchronization gates around the four crash
  windows.

Gate:

- in clean sessions, reconstructed succeeded payloads equal target-stdin bytes,
  parent-stdout bytes equal target-stdout observations, and parent-stderr bytes
  equal target-stderr observations with no Recorder diagnostic suffix;
- no unresolved attempt is replayed.

### Atomic stage 4: supervision and containment

RED:

- stdin blocked while child exits;
- stdout blocked while journal fails;
- stderr floods without newline;
- target writes a final stdout/stderr unit and exits immediately under repeated
  forced scheduling;
- child ignores terminate;
- child creates descendant holding a pipe;
- engine outer-Job assignment fails before engine execution;
- engine `ResumeThread` return values `1`, `0xffffffff`, `0`, and `>1` follow
  exact sidecar reasons; only `1` permits engine execution, and a marker proves
  every other value executed no engine instruction;
- target Job assignment or guard-handle acknowledgement fails before target
  execution;
- target resume succeeds but its terminal journal record is lost;
- an engine that blocks before publishing target-ready exceeds the startup
  deadline and is reclaimed with the outer Job;
- an engine that publishes target-ready but blocks before observing target-ack
  exceeds the same absolute deadline, never resumes the target, and causes an
  outer-Job termination request;
- a hand-built 128-byte handshake golden vector is accepted; every mutation of
  magic, version, size, nonce, flags, PID, handle, reserved bytes, state,
  event order, and illegal state transition is rejected;
- exact `PYTHON_LIST2CMDLINE_UTF16_V1` vectors cover empty, space, tab,
  `a"b` without outer quotes, consecutive backslashes immediately before a
  quote, trailing backslashes in a quoted argument, non-BMP pairs, and unpaired
  surrogates; an independent CPython 3.13 oracle agrees on all representable
  vectors, while the old unnecessary-outer-quote spelling for `a"b` fails;
  mutations of buffer hex, count, hash, or `lpApplicationName` are rejected;
- every missing, reordered, duplicated, or ambiently substituted production
  flag fails; only exact `-I -S -B -X utf8` reaches bootstrap imports;
- injected extra member, `.pyc`, `__pycache__`, case collision, reparse point,
  wrong hash/size/type, forbidden stdlib import, unlisted relative package
  import, and candidate-cwd shadow package all fail before Recorder import;
- two sequential clean bootstrap/engine launches, with no injected external
  mutation between them, independently produce identical recursive
  protected-root member snapshots and create no bytecode; the test makes no
  post-verification immutability claim;
- one injected failure for every frozen argv/isolation/manifest/path/pipe/
  host-Job/session/sidecar/outer-Job/engine-create/assignment/resume/handshake/
  internal-exception category proves its exact exit class and exactly zero
  Recorder stdout/stderr bytes; target markers remain absent before target
  creation;
- installed console and module `proxy` both exit 64 before guard/engine import,
  with empty stdout and the exact frozen stderr line; read-only commands remain
  available;
- a corrupt script, syntax error, or loader failure before the first bootstrap
  statement is recorded only as a launcher-precondition test and is never
  asserted to satisfy Recorder's zero-output/class guarantee;
- pre-ready delay consumes the same shared kernel-timer budget as pre-ack delay;
  no phase receives a new relative duration;
- Job active-process count that never reaches zero and repeated query failure
  both force bounded post-call class-16 exit with reclamation unconfirmed;
- a completed handshake worker followed by a guard-main stall before durable
  binding/state 3 leaves the shared timer armed; timer wins and target never
  resumes;
- a guard-main stall after state 3 but before state-4 resume intent, and an
  engine stall after durable intent but before its signal, consume the same
  timer and never grant engine/worker resume authority;
- target `ResumeThread` return values `1`, `0xffffffff`, `0`, and `>1` follow
  the exact state-5 and failure predicates; a call counter proves guard main is
  the sole caller and invokes it at most once;
- missing, truncated, hash-invalid, journal-unbound, contradictory, requested,
  confirmed, and unconfirmed guard sidecars exercise every combined-verifier
  truth-table row;
- a flushed 128-byte sidecar header with no committed `GUARD_STARTED` record is
  a valid incomplete prefix, while a partial header or partial record reports
  its exact tail rather than becoming a fabricated terminal;
- moving/copying a complete session directory changes only advisory report
  paths; mutating either persisted origin-path digest breaks journal/sidecar
  binding;
- a valid sidecar-only engine-resume failure or incomplete evidence copy
  verifies as `WINDOWS_SUPERVISION_ONLY` plus `JOURNAL_MISSING`, while an
  absent journal and absent sidecar is not promoted to evidence; paired
  fixtures cover `supervision_journal_bound=false` and `true`;
- journal absent plus invalid sidecar fixtures retain physical bytes and
  longest-valid-prefix diagnostics but require `UNDETERMINED`,
  `NONE/NONE/NONE`, INVALID/exit 2; only a valid sidecar-only fixture may claim
  `WINDOWS_SUPERVISION_ONLY`, INCOMPLETE/exit 1;
- an externally isolated guard with an injected nonreturning
  `TerminateJobObject` is killed by the harness and leaves no clean claim,
  documenting rather than concealing the kernel-call liveness boundary;
- stdin/stdout/stderr object aliases, shared pipe object names, bidirectional
  access, message mode, and nonblocking mode all fail before target creation;
- relay blocks in `WriteFile` while fatal shutdown starts, proving the
  supervisor never closes its live handle;
- journal poison occurs while target remains live, proving emergency
  containment does not require a new journal attempt;
- guard launched inside a host Job fails before engine execution;
- candidate cwd contains a shadow `aegis_recorder` package;
- engine/target handle-list members are dedicated inheritable duplicates and
  no unlisted handle is usable;
- Linux prerequisite tests reject missing/caller-selected trust slots or
  approval records; malformed/noncanonical approval, stdlib, and ELF-closure
  manifests; non-root-owned/runtime-writable trust objects; zero/mismatched UID
  or GID slots, nonempty supplementary groups, capabilities, or absent
  `no_new_privs`; malformed `PRELOADED`/`SEED`/`LATE` stages,
  missing/non-package dotted parents, invalid preloaded-filesystem mappings,
  early-finder/runtime-name collisions; raw or page-rounded ELF load overlap
  and any other nonconforming closed-ABI static adapter ELF,
  project-authored/ambient native hashing, or argv/FD/env/cwd/report ABI;
  unsupported kernels/filesystems; `/mnt/c`; wrong `openat2` resolution;
  nonconforming runtime FDs `0..12` before and `0..11` after exec; path-based
  interpreter/bootstrap execution; inherited signal/mask/wait defects;
  new filesystem imports after the first statement and before the seed, any
  non-seed filesystem import before
  the manifest finder, pathname-based stdlib/runtime loaders;
  `renameat2` replacement/fallback; report-channel ambiguity; and
  post-publication inode/member/fsync uncertainty;
- the positive Linux getpath fixture launches the exact CPython 3.12.3 object
  through its held FD from `P/python3.12`, authenticates exact 15-byte
  `P/python3.12._pth`, observes only `[P/lib/python3.12]` in initial
  `sys.path`, exact prefix/executable/stdlib fields, and exactly three
  filesystem-backed `encodings` modules. An out-of-band syscall trace adds no
  child FD and proves no `write(2)` before the first fixed bootstrap probe;
- Linux getpath faults independently cover missing/extra/reordered/comment/
  `import site`/blank/whitespace `._pth` lines, CRLF, BOM, NUL, missing LF,
  wrong dev/ino/size/hash/owner/mode/link count, both `pyvenv.cfg` locations,
  `pybuilddir.txt`, `Modules/Setup.local`, competing ELF-closure `._pth`
  candidates, patch/interpreter-digest/PLATLIBDIR/VPATH/layout drift, and drift
  still present when bootstrap reopens the getpath file. Pre-exec mismatches
  prove zero `execveat` calls; observable reopen-time drift cannot produce
  PASS. A separate comment-prefixed, getpath-equivalent ABA fixture restores
  the approved inode/bytes before bootstrap reopen, may satisfy every local
  observation, and must remain an external-boundary demonstration rather than
  a pathname-continuity or security PASS. An extra stdlib `os.py` fails exact
  membership and `os` is accepted only from the frozen wrapper;
- POSIX adapter-level tests prove `getsid(0) == getpid()`,
  `getpgrp() == getpid()`, normal fast-exit draining, exact
  TERM/grace/KILL/reap behavior, same-group descendant reclamation,
  deliberate-`setsid()` escape, and hard-kill evidence boundaries; every
  end-to-end POSIX proxy case must use the external
  `LINUX_PROTECTED_BOOTSTRAP_V1` contract;

GREEN:

- implement real relay thread handles, cancellation attempts, the shared
  startup timer, dedicated handshake worker, timer-before-ack arbitration,
  separate runtime deadline, post-call bounded reclamation confirmation, exact
  fixed handshake, guard-owned sidecar, guard-main target resume, strict pipe
  topology preflight, direct suspended target launch, nested Job Objects, exact
  duplicate-handle lists, package-independent bootstrap, frozen import/output
  guards, exact failure dispatcher, and engine `-I -S -B -X utf8` launch,
  normal-exit output draining, journal-poison emergency
  containment, the retained-dirfd POSIX adapter, Linux external-prerequisite
  conformance harness, fixed approval/stdlib/ELF manifest cursor parsers,
  exact CPython/getpath-layout pre-exec checks and post-entry recheck,
  static-adapter ABI checks, normalized signal and preflight-reap checks,
  retained-FD stdlib/runtime loaders, exact fixed-FD/procfd `Popen`,
  `start_new_session=True` process group, and recorded SIGTERM/SIGKILL
  escalation.

Gate:

- ordinary and fault-injected Windows cases prove no live target/descendant
  after confirmed reclamation;
- startup, runtime, and confirmation bounds are distinct and never restart;
- after Windows calls return, unavailable reclamation proof causes bounded
  class-16 exit, supervision failure, and no clean end;
- kernel-call duration remains an explicit external liveness boundary and is
  never described as a Recorder-controlled deadline;
- injected assignment failure leaves the target marker file absent;
- every controlled bootstrap/guard/engine failure matches one table row, one
  exit class, zero Recorder diagnostic bytes, and the exact maximum evidence
  available at that point;
- two sequential clean-launch root snapshots match without an external mutation
  between them, no bytecode appears, forbidden imports execute no module code,
  and the serializer matches all frozen adversarial UTF-16 vectors; this gate
  does not assert runtime immutability;
- injected pre-ready and pre-ack stalls are terminated by the guard using a
  test-injected shorter timer while preserving the production
  `120000`-millisecond contract;
- a fast-exit target's final bytes are always observed or the session is
  explicitly incomplete, never silently clean;
- real Windows CPython 3.13 covers no-host-Job and host-Job-rejection profiles;
- WSL adapter tests prove direct-child reaping and group-absence confirmation
  within the POSIX bounds; a WSL proxy launch is evidence only through the
  implemented protected-bootstrap contract, and an escaped session cannot
  satisfy the Windows production gate.

### Atomic stage 5: packaging and integration

RED:

- the absent in-tree backend cannot build a wheel or mandatory PEP 517 sdist
  offline;
- direct-wheel, prepared-metadata-wheel, and sdist-derived-wheel equality,
  repeated wheel/sdist determinism, exact tags, independent `RECORD`
  verification, ZipInfo invariants, zero `Requires-Dist`, console script,
  module entry, exact top-level bootstrap, protected-root deployment, installed
  golden verification, and no-overwrite publication initially fail;
- physical wheel, member-count, member-size, total-uncompressed-size, and
  UTF-8-path bounds test exact accepted endpoints plus one-byte/count excess;
  builder, independent verifier, Windows deployer, and POSIX adapter must agree;
- candidate-supplied/self-issued deployer hash, replaceable deployer/ancestor,
  wrong interpreter/deployer hash, missing/reordered flag or option,
  noncanonical raw command, extra environment entry, wrong cwd,
  `bInheritHandles=FALSE`, missing `STARTF_USESTDHANDLES`, non-inheritable or
  aliased standard handle, handle-list/standard-handle mismatch, ambient
  inherited handle, candidate/zip/site/namespace import, or wrong import origin
  fails before wheel processing;
- CPython 3.13.13 tests require the exact startup vector
  `[python313.zip, DLLs, Lib, interpreter_root]`, a held/external absence
  binding for `python313.zip`, preloaded `encodings` under held `Lib`, the sole
  in-place narrowing to `[DLLs, Lib]`, and rejection of every extra, reordered,
  existing-ZIP, later-path, finder, hook, or importer-cache mutation;
- non-Windows, non-64-bit, UNC/device/extended/relative/noncanonical path,
  removable/network/non-NTFS volume, SUBST or initially mismatched/ambiguous
  DOS-device-to-volume mapping, mounted-volume transition, component
  replacement, reparse, case alias, wrong `FILE_RENAME_INFORMATION` or
  `IO_STATUS_BLOCK` size/layout, absent `NtSetInformationFile` or
  `NtWaitForSingleObject`, failed approved-build/conformance-profile match, or
  insufficient handle access/share fails before staging;
- a deterministic publication-gate test records deployer mapping snapshot A,
  completes staging/member verification, then injects a different second
  `QueryDosDeviceW` snapshot B immediately before publication. It proves
  `NtSetInformationFile` is never called, `publication_state=NOT_PUBLISHED`,
  exit 1 with
  canonical `DEPLOYMENT_FAILED`, the original staging UTF-16LE path and FileId
  remain reported, and no automatic cleanup occurs;
- absent/wrong wheel hash, invalid `RECORD`, missing/extra manifest row,
  traversal, alternate-case collision, link/reparse, wrong type/hash/size,
  staged short write, flush failure, reread mismatch, injected extra/pyc/cache/
  dist-info/Scripts member, pre-existing final root, rename race, and rename
  failure fail against the independent deployer;
- API-spy tests require the rename source to be the retained
  `DELETE`-capable staging handle, native information class
  `FileRenameInformation=10`, `ReplaceIfExists=FALSE`, `RootDirectory` equal
  to the retained parent handle, and `FileName` equal to the exact single
  final component without NUL, with a zero-filled
  `max(24,20+FileNameLength)` allocation and the same exact `Length`; one- and
  two-WCHAR names exercise the 24-byte structure
  floor. They reject Win32-wrapper, null-root, and pathname fallbacks. All
  member file handles are closed first;
- native-status tests cover immediate success, immediate collision, immediate
  capability failure, every nonzero success/informational/warning/unlisted-
  error class, pending-then-success, pending-then-failure, zero-budget/no-wait,
  one-tick and rounded timeout encoding, wait timeout, still-pending IOSB, and
  call/IOSB disagreement. Every unresolved case emits
  `PUBLICATION_OUTCOME_UNKNOWN`,
  `publication_state=PUBLICATION_OUTCOME_UNKNOWN`, null
  `published_file_id`, both locators plus staging identity, exit 1, no retry,
  no lookup inference, and no cleanup;
- post-rename final-name substitution, volume/FileId mismatch, final reparse,
  and final membership drift produce
  `PUBLISHED_IDENTITY_UNCONFIRMED`, `publication_state=PUBLISHED`, exit 1, and
  no success claim;
- every pre-publication deploy failure proves no deployer publication; every
  failure after staging creation proves no recursive delete, rename,
  quarantine, repair, or reuse of the staging namespace. A foreign final
  occupant remains byte-for-byte untouched. The canonical report carries the
  original staging UTF-16LE hex and FileId for operator quarantine;
- every healthy-channel exit row proves one LF-terminated canonical ASCII
  stdout object, zero stderr bytes, exact reason/exit/publication-state fields,
  nullable path/identity transitions, and reversible UTF-16LE path hex; broken report-
  channel tests inject loss before byte 0, at interior offsets, and after all
  bytes, plus terminal-close failure for every intended success/failure row;
  they require exit 74, zero stderr, no exit 120, and compare the launcher's
  exact raw capture without treating even a complete-looking prefix as a
  report;
- the initial Windows operator-to-guard conformance matrix mutates the external
  interpreter/bootstrap digest and FileId, every path component/reparse/share/
  DOS-device predicate, each standard-handle role/alias/inheritability, and one
  extra ambient handle. It proves zero unapproved bootstrap execution and no
  ordinary-launch fallback;
- on Windows, installed console/module `proxy` invocations fail before
  guard/engine imports; read-only commands remain available, while the
  production bootstrap reaches the private guard entry.

GREEN:

- add the standard-library PEP 517 wheel/sdist backend, independent protected
  runtime deployer, and CLI;
- run the fixture app-server proxy end-to-end through the Windows protected
  bootstrap only.

Gate:

- two clean Windows wheel builds have identical SHA-256 values and install
  without network, index access, build isolation, or dependency resolution;
- two clean sdists have identical SHA-256 values; a wheel built from the
  unpacked sdist is byte-identical to a direct wheel in the same profile;
- filename, distribution/version, `py312.py313-none-any` tag set, METADATA,
  WHEEL, entry point, member order, ZipInfo, and `RECORD` exactly match the
  frozen packaging contract;
- every wheel member and `RECORD` row is independently verified;
- an ordinary pip install in a fresh virtual environment passes compatibility
  tests but is never accepted as protected-runtime deployment evidence;
- an external operator-launch harness retains non-replaceable interpreter,
  deployer, and ancestor handles, validates out-of-candidate expected hashes,
  launches the exact clean process profile, and proves a candidate cannot
  self-authorize or inject cwd/environment/import state;
- the deployer independently rechecks its own/interpreter hashes and an
  expected-hash wheel without importing build or runtime code, produces an
  absent-root publication whose recursive files are exactly bootstrap,
  manifest, and manifest allowlist, and includes no `.dist-info`, `Scripts`,
  `.pyc`, `__pycache__`, or extra member;
- every staged file has write-time and reopen/reread size/hash evidence before
  `NtSetInformationFile(FileRenameInformation)` publication; pre/post staging
  and relative-final
  `FILE_ID_INFO` match before success, a name-race occupant is never replaced
  or deleted, and post-publication uncertainty is reported as failure;
- every staging-creating result preserves the original staging path/FileId in
  exact canonical output, and no failure performs automatic recursive cleanup;
- two sequential clean production bootstrap/engine launches, with no external
  mutation between them, preserve the exact root member snapshot and embedded
  manifest digest without making a runtime-immutability claim;
- tests contain no production `pip install --target` path;
- every injected failure before `os.link` leaves no final archive; an existing
  final name is never replaced;
- clean Windows install passes the standard-library suite;
- clean Windows console/module entry tests prove `proxy` cannot become an
  alternate pre-isolation launch path;
- the wheel is copied from WSL to the Windows workspace with `cp` through
  `/mnt/c/...`; the copied SHA-256 must equal the WSL source hash;
- WSL clean install passes the portable standard-library and adapter-level
  suite; any proxy run uses the externally approved
  `LINUX_PROTECTED_BOOTSTRAP_V1` contract on the native filesystem rather than
  a console/module path. Missing native launcher/deployment-adapter authority
  blocks that E2E gate without blocking portable unit tests;
- current Desktop attachment remains explicitly unsupported.

## Deterministic crash synchronization

Test-only constructor dependencies expose one-way gates after:

1. source read, before observation flush;
2. observation flush, before attempt append;
3. attempt flush, before/during destination write;
4. destination accepted all bytes, before success flush.

The production CLI cannot enable these gates through environment variables,
config files, or arguments. Tests hard-kill the process only after a separate
controller observes the selected gate.

## WSL role

WSL is reached only through:

```text
ssh nomo@172.21.45.37
```

It validates:

- independent parser and golden vectors;
- exact byte relay;
- POSIX adapter-level process-group termination;
- external Linux launcher/deployment-adapter syscall, trust-slot selection,
  fixed approval/stdlib/ELF manifest, static-adapter ABI, pre/post-exec FD,
  exact CPython 3.12.3/getpath layout, signal, retained-procfd loader,
  report-channel, environment,
  native-filesystem, and fail-closed conformance;
- backpressure and hard-kill windows;
- corrupted/truncated journal behavior;
- clean wheel installation on Python 3.12.3.

It does not validate:

- `msvcrt.setmode`;
- Windows pipe types;
- `CreateFileW`, `FlushFileBuffers`, share modes, or NTFS behavior;
- junction/reparse behavior;
- `CancelSynchronousIo`;
- Job Objects or Windows handle inheritance;
- Windows CPython 3.13 packaging.
- any POSIX proxy launch that does not use the externally approved
  `LINUX_PROTECTED_BOOTSTRAP_V1`
  deployment/isolation/argv/environment/FD/output/import contract.

## Candidate re-selection triggers

Reconsider the stdio-owner proxy only if:

- Codex exposes a supported signed event stream with completeness/replay
  guarantees;
- Desktop exposes a supported external attach/control socket on Windows;
- an independently operated authority provider proves subagent spawn, final
  message, and turn completion coverage.

No local hook/history tailer becomes a fallback.

## Exact user implementation confirmation

General authorization to design or implement Recorder does not accept a later
revised plan. After the final frozen plan-review batch has complete results,
zero aggregate P0/P1, and no source modification, Master presents the user
with the exact plan SHA-256, review snapshot ID, aggregate SHA-256, unresolved
P2 list, and proposed scope `ENTER_R11A_IMPLEMENTATION`. Only a user response
observed after that presentation can select the next stage.

Master records exact repository-external
`UserImplementationConfirmation.v1`:

```text
authority_verified=false
decision="ACCEPT" | "REVISE" | "REJECT"
master_observed_at_utc=UTC
master_observed_text_sha256=SHA256_ID
normalized_utf8_size=<JSON integer 1..1048576>
plan_sha256=SHA256_ID
review_aggregate_sha256=SHA256_ID
review_snapshot_id=SHA256_ID
schema="UserImplementationConfirmation.v1"
scope="ENTER_R11A_IMPLEMENTATION"
```

Text normalization and hash use the reviewer-text CR/LF, Unicode-scalar, NUL,
size, and strict UTF-8 rules with domain
`"AEGIS_MASTER_OBSERVED_USER_IMPLEMENTATION_CONFIRMATION_V1\0"`. The record
does not authenticate user identity or transfer legal responsibility. An
`ACCEPT` decision is effective only for the exact plan/snapshot/aggregate
tuple shown immediately before the response. Any later reviewed-source,
required-input, aggregate, or scope change invalidates it and requires a new
review plus new user decision. Earlier conversational approval cannot be
retrofitted to this record.

## Completion gate

- revised plan reviewer returns zero P0/P1;
- one exact `UserImplementationConfirmation.v1` binds `ACCEPT` to that same
  reviewed snapshot and authorizes only entry into R11A;
- the external-launcher conformance harness passes, while project packaging
  contains no launcher that claims to self-provide the operator trust root; an
  absent operator launcher leaves deployment explicitly unavailable;
- independent schema reviewer accepts the JCS-safe schema/fixed-validator
  signed-64 split before `schema_bundle.v1.json`,
  `reference/source_manifest.v1.json`, or `evaluation_manifest.v1.json` is
  regenerated; the rebuilt 53-schema closure and all manifest hashes then pass;
- reasoning-ledger status remains explicitly unavailable, or a newly available
  active/stale/invalid/superseded query is reconciled before coding;
- codebase-fact commands are rerun and any drift is reconciled;
- every behavior begins with a witnessed RED test;
- new tests pass on Windows;
- portable subset passes in WSL;
- clean-wheel tests pass in fresh environments;
- existing relevant Aegis tests pass;
- independent code/evidence reviewer returns zero P0/P1;
- no `authority_verified=true` path exists;
- branch, status, diff, commands, hashes, known limits, and next actions are
  written to `CONTINUATION.md`;
- no commit or push occurs.
