# Aegis Recorder requirement addendum

Status: `CONFIRMED_FOR_IMPLEMENTATION`

User confirmation recorded at: `2026-07-28T07:17:06.3171799Z`

Confirmation:

> 那就用python单独实现一个。但是这个实现必须可靠。

This addendum authorizes a standalone Python Recorder. It supersedes the
earlier Phase 0A code-absence restriction only for this component. It does not
authorize a live Codex capability probe, formal A-F agents, a product test, or
a Phase 0A PASS claim.

## Purpose

The Recorder is deterministic infrastructure. It has no model, prompt,
judgment, test verdict, relevance filter, or authority to reinterpret events.

It owns a Codex app-server subprocess from process start, relays its framed
stdio byte streams, and produces durable evidence of exactly what crossed that
boundary.

## Requirements

| ID | Requirement | Acceptance condition |
|---|---|---|
| REC-001 | Separate process | The Recorder is an installable Python command and does not run as an agent or LangGraph node. |
| REC-002 | Own the observed boundary | The Recorder starts the child process itself. It refuses claims about a pre-existing Desktop/app-server stream. |
| REC-003 | Exact bytes | Every complete input frame is retained byte-for-byte, including its delimiter. Unknown or malformed JSON is neither normalized nor discarded. |
| REC-004 | Write ahead | A wire frame is appended and durably flushed before any byte is forwarded. |
| REC-005 | Forward acknowledgement | Successful forwarding is followed by a separate durable acknowledgement bound to the exact observation sequence and digest. |
| REC-006 | Uncertain windows fail closed | A crash, persistence failure, or OS write result that cannot prove an exact accepted-byte total yields `SEND_OUTCOME_UNKNOWN`; the Recorder never automatically replays it. |
| REC-007 | Ordered append-only journal | Each entry has one monotonic sequence, exact previous-entry digest, payload size/hash, process-monotonic time, UTC wall time, and a committed trailer. |
| REC-008 | Corruption detection | An independent verifier detects malformed framing, changed bytes, broken hashes, duplicate or skipped sequence, record reorder, partial tail, missing terminal state, and unmatched observations. |
| REC-009 | New evidence namespace | A session directory is create-new. Existing directories, journal files, symlinks, junctions, and observed reparse paths are rejected before capture. |
| REC-010 | Single writer | One process holds an exclusive session lock; concurrent writers fail before child launch. |
| REC-011 | Persistence failure stops transport | Open, append, flush, fsync, or verification failure stops forwarding, terminates the child, records a failure when still possible, and exits nonzero. |
| REC-012 | Bounded resources | Frame size is bounded. An oversized or unterminated frame is retained up to the proven read boundary, marked incomplete, not forwarded, and terminates the session. |
| REC-013 | Backpressure | The Recorder does not acknowledge a forward until the destination accepted all bytes. It does not use an unbounded in-memory event queue. |
| REC-014 | Clock behavior | Ordering uses sequence and process-monotonic time. Wall-clock rollback is recorded and never used to reorder entries. |
| REC-015 | Child lifecycle | Spawn metadata, executable identity, stderr, EOF, return code, termination cause, and clean/unclean close are journaled. |
| REC-016 | Verifier separation | Verification is a separate read-only command. It never repairs or truncates evidence. |
| REC-017 | Assurance is explicit | Output distinguishes `LOCAL_TRANSPORT_INTEGRITY` from external authority. Local hashes, HMAC, files, or process separation never set `authority_verified=true`. |
| REC-018 | No invented upstream claim | Evidence scope is exactly `RECORDER_OWNED_APP_SERVER_STDIO`. It is not OpenAI HTTP raw bytes, a provider signature, or proof of events outside that process boundary. |
| REC-019 | Current Desktop limitation | The Recorder reports that it cannot attach after the current Codex Desktop app-server has started. Production use requires a supported launch/integration path that routes the audited work through this Recorder. |
| REC-020 | Key isolation boundary | The first implementation contains no home-grown cryptography and no private signing key. A future authority adapter must use a candidate-external, preauthorized signer/log and a second-consumer-verifiable proof. |
| REC-021 | Windows truth boundary | Native held-handle traversal rejects observed reparse components and stabilizes objects after their first open. It does not prove pre-open path history, prevent same-user byte mutation through another writable handle, or create external authority. |
| REC-022 | Sensitive payload handling | Documentation states that raw prompts, results, and tool data can contain secrets. The operator selects a protected runtime root and retention policy. |
| REC-023 | Windows byte preflight | On Windows, parent stdin/stdout/stderr must be pipe handles. The Recorder switches all three CRT descriptors to `O_BINARY` before the first read or write and rejects console/file handles in strict proxy mode. |
| REC-024 | Literal framing | Client-to-server and server-to-client frames are delimited only by byte `0x0A`; the delimiter is retained and forwarded. Byte `0x0D` is ordinary payload. JSON parsing and universal-newline handling are forbidden. |
| REC-025 | Durable send intent | `FORWARD_ATTEMPT_STARTED` is durably committed before the first destination write. An attempt with no outcome record or an explicit unknown-outcome record is always `SEND_OUTCOME_UNKNOWN`. |
| REC-026 | Partial-write truth | A decisive forwarding result binds the observation and attempt and records an exact accepted-byte count. An explicit unknown outcome records only a proven lower bound. Any known or possible partial write makes transport incomplete and is never replayed. |
| REC-027 | Process-tree containment | Windows creates the target primary thread suspended, assigns the process to nested kill-on-close Job containment, establishes an independent guard wait handle, and only then resumes it. Assignment failure means target code never executed. POSIX uses a new process group. |
| REC-028 | Independent implementations | Production Writer and Verifier do not share canonical serialization, entry digest, state-machine, or recovery functions. Golden vectors and mutation builders use a third test-only implementation. |
| REC-029 | Packaging isolation | Recorder is a standalone subproject with its own `pyproject.toml`, wheel, console script, module entry point, and clean-environment installation tests. |
| REC-030 | Durable target start intent | The target resume attempt is durably recorded before `ResumeThread`. A missing resume terminal is an unknown start outcome and cannot produce a clean session. |
| REC-031 | Independent shutdown guard | Windows uses an outer guard process and Job Object. After a detected trigger it issues termination within the declared deadline, bounds reclamation confirmation, and distinguishes requested termination from proven disappearance. No bound is claimed for an undetected post-handshake defect that never triggers the guard while the target remains live. |
| REC-032 | Exact OS identity bytes | Windows paths, argv, and environment identity are bound as exact UTF-16LE code-unit bytes; POSIX identity is bound as exact OS bytes. Display strings never establish executable identity. |
| REC-033 | Bounded verification output | Journal size, entry count, metadata structure, issue details, and sequence lists have hard limits. Truncated diagnostic lists retain exact aggregate counts. |
| REC-034 | Normal-exit output drain | Target exit does not cancel stdout/stderr relays. They drain to EOF or the session ends explicitly incomplete at the guard deadline. |
| REC-035 | Relay handle ownership | A relay exclusively owns each handle used by its active synchronous I/O. The supervisor cancels by real thread handle and never closes a handle still used by that relay. |
| REC-036 | Poisoned-journal containment | Journal poison forbids later evidence but does not block emergency process-tree termination. Unrecorded emergency effects are never claimed as proven and no clean session end is emitted. |
| REC-037 | Structural plus semantic report validation | JSON Schema acceptance alone is insufficient. A versioned independent report-only validator rejects internal count, list, hash, partial-tail, reason, verdict, and signed-64 range contradictions. Signed-64 limits that cannot be represented as RFC 8785 safe-integer schema literals remain exact fixed-validator predicates; the external fields remain JSON integers. Report-only validation does not claim session facts; those require `verify ABSOLUTE_SESSION_DIRECTORY`. |
| REC-038 | Strict Windows host boundary | Windows v1 rejects launch when the guard already belongs to a host Job Object. Engine import uses absolute Python isolated mode, protected cwd, sanitized import environment, and verified installed code manifest. |
| REC-039 | Bounded Windows startup handshake | Guard and engine wait timer-before-ack on handles to one guard-armed 120-second kernel timer. A separate handshake worker never cancels it; only the supervising guard thread cancels after observing ack win. Timeout or protocol violation requests outer-Job termination before target resume. |
| REC-040 | Mutually exclusive forwarding accounting | Every observation belongs to exactly one of succeeded, failed, not-attempted, or unresolved. A durably recorded positive-prefix failure is failed, not unresolved. |
| REC-041 | Buffered abnormal-read preservation | Framed read failure or cancellation with buffered bytes emits one incomplete-frame terminal retaining the exact bytes, cause, and error/policy code. |
| REC-042 | Strict Windows pipe topology | All standard-handle pairs are distinct objects and distinct pipe names; each handle has one-way access and blocking byte-stream mode. Any unproved property fails before target creation. |
| REC-043 | Ambiguous write evidence | Windows `WriteFile(FALSE)` never becomes a known failure result. A healthy journal records an explicit unknown outcome and only the lower bound proven by earlier successful calls. |
| REC-044 | Bounded controlled guard waits | After a Windows termination API returns, Recorder-controlled reclamation polling lasts at most two seconds before Job close and nonzero return. No duration is claimed for a nonreturning kernel API; no unobserved disappearance is claimed. |
| REC-045 | Exact report result rows | PASS, INCOMPLETE, INVALID, INPUT_ERROR, and INTERNAL_ERROR have bidirectional predicates for every represented field. Semantic validation rejects every mutation that violates those relations; evidence causes remain `verify ABSOLUTE_SESSION_DIRECTORY` facts. |
| REC-046 | Offline zero-dependency distribution | Recorder build and runtime use only the supported Python standard library. Its in-tree PEP 517 backend builds a deterministic wheel without network access, dependency resolution, build isolation, source mutation, or importing runtime code. Independent tests verify every wheel member and `RECORD` row. |
| REC-047 | Reconstructible stream topology | The protocol fixes client-to-target stdin, target-to-client stdout, and target-to-client stderr as the only topology. A legal `CHILD_SPAWNED` activates all three logical source/destination pairs atomically; its absence activates none. Every activated endpoint has one terminal lifecycle result, including zero-byte sessions. |
| REC-048 | Complete reason mapping | Every legal non-PASS protocol, supervision, evidence, input, and internal terminal state maps bidirectionally to stable reason IDs and exact counts. No legal failure may rely only on prose, a nullable field, or an exit class. |
| REC-049 | Guard-owned supervision evidence | Windows guard facts are written to a separate create-new sidecar owned only by the guard, bound to the journal identity, and independently verified. It distinguishes termination not requested, requested, API success/failure, reclamation confirmed, and reclamation unconfirmed. |
| REC-050 | Exact protected entry | Every Windows production or Linux validation proxy launch uses a held trusted interpreter object with `-I -S -B -X utf8` and an operator-approved bootstrap whose expected digest is selected outside the candidate. Windows uses a distinct operator-to-guard launcher: it validates externally selected interpreter/bootstrap hashes and identities through retained native no-reparse handles, excludes write/delete replacement through guard exit, and gives the guard exactly three dedicated inheritable standard-handle duplicates in one handle list. Missing or nonconforming launch authority makes proxy unavailable. Linux/WSL2 uses fixed `/proc/self/fd/3` backed by the launcher's held approved file and `execveat` interpreter. The bootstrap owns one normative argument grammar, exit/stdout/stderr behavior, descriptor table, and import-root closure. Configuration files, environment aliases, public `python -m`, ordinary console-script import, and candidate-controlled paths cannot become an alternate pre-isolation proxy entry. |
| REC-051 | Exact Windows command line | The journal binds both the exact target argv code units and the exact UTF-16LE `lpCommandLine` passed to `CreateProcessW`. One normative serialization algorithm is used; lossy display strings and alternative quoting algorithms are rejected. |
| REC-052 | Evidence-origin platform profile | The report platform profile comes from a legal journal session-start entry or an explicit valid Windows supervision-only row, never from the verifier host. Windows journal evidence requires a valid bound supervision sidecar; POSIX evidence does not use that sidecar as supervision proof; undetermined evidence cannot PASS. |
| REC-053 | No framed-stream read ahead | v1 requests exactly one byte per direct OS read on framed streams and forbids buffered/read-ahead APIs. A delimiter or limit trigger is durably classified before the next read, so one call cannot consume bytes from a later frame; any future chunked reader requires a separate durable raw-read mapping protocol. |
| REC-054 | Single resume authority | Only the Windows guard main thread may call target `ResumeThread`, exactly once, after failure-first shared-timer arbitration and durable state-4 resume intent. Engine and handshake worker may publish intent and readiness but have no target-resume authority; timeout or invalid prior suspend count fails closed. |
| REC-055 | Session-directory evidence input | Verification accepts one absolute session directory and opens only fixed sibling evidence names without following an observed link/reparse component. A valid guard sidecar remains machine-verifiable when engine execution failed before journal creation; the report marks the journal absent and never fabricates journal facts. Copying the directory changes advisory current paths, not origin identity or journal/sidecar binding. |
| REC-056 | Evidence-class truth | Journal, supervision-only, and no-evidence rows use distinct assurance, scope, and ordering triples. A sidecar-only row cannot claim app-server transport coverage; an input/internal error cannot claim either evidence class. |
| REC-057 | Component-safe Windows evidence open | The Windows Verifier accepts only its frozen local-volume path grammar, anchors a handle at the volume root, and opens every ancestor, the session directory, and each fixed evidence child relative to the preceding held handle with open-reparse-point semantics. Every opened component is independently queried; an observed reparse attribute, nonzero reparse tag, or identity change after that component's first open fails before its evidence bytes are consumed. The contract prevents reparse escape and stabilizes already-open objects; it does not claim the historical identity of an ordinary child before its first open. |
| REC-058 | Exact protected-runtime deployment | Production does not use a mutable `pip --target` tree. An externally digest-bound, isolated standard-library deployment tool extracts only the reviewed runtime allowlist from an independently verified wheel into a create-new, handle-bound staging root on a fixed NTFS volume, validates exact bytes and member types, and publishes that held object by a no-replace handle-relative rename. Launcher and deployer independently reject unequal DOS-device drive/volume mappings; the launcher checks before launch, while the deployer compares its initial mapping snapshot with its own immediate pre-publication snapshot. No post-launch launcher recheck is claimed. The variable rename buffer satisfies the frozen public ABI size and layout. The operator-controlled launcher and approved-hash root are external prerequisites; Recorder supplies no self-authorizing launcher or fallback, and deployment is unavailable when they are absent. Dist-info, scripts, bytecode, cache directories, and installer-derived files are absent. Clean first and second launches must leave the exact member set unchanged; this is an acceptance invariant, not a general write-protection claim. |
| REC-059 | Total production-entry failure relation | After the trusted interpreter transfers control to the bootstrap, every controlled argv, isolation, manifest, path, handle, Job, creation, handshake, and internal-exception result maps to one stable proxy exit class and exact observable stdout/stderr bytes. A healthy result channel carries one complete canonical object. A failed result channel uses dedicated exit 74, carries no report claim, and preserves the exact raw prefix without fabricating missing bytes; even a complete-looking prefix is rejected. Healthy internal failure remains exit 70 and is accepted only with a complete canonical row whose embedded exit code is 70. The exception boundary is installed before Recorder imports. Interpreter/OS-loader failure before the first bootstrap statement is an explicit launcher precondition, not a fabricated Recorder guarantee. |
| REC-060 | Evidence-derived reasons only | Every non-OK reason has a unique positive predicate over durable input bytes. A failure cause that cannot survive its own persistence failure is not inferred. `INTERNAL_FAILURE.failure_class` is a closed enum, and every legal `INTERNAL_FAILURE` contributes exactly once to `SUPERVISION_FAILED` and no other reason. |
| REC-061 | Exact Linux validation entry | `LINUX_PROTECTED_BOOTSTRAP_V1` is reachable only through an externally approved x86-64 Linux/WSL2 trust slot and a nonzero-UID/nonzero-GID launcher with no supplementary groups, no capabilities, and `no_new_privs`, using approved user/mount namespace identities, `openat2`, root-owned/runtime-nonwritable fixed canonical approval/ELF/stdlib manifests and trust objects, fixed pre/post-exec FD tables, normalized signal state, `execveat`, procfs FD paths, one `LC_ALL=C` runtime environment entry, and native ext4 protected/evidence roots proven by held-FD `statx` mount ID, matching `/proc/self/mountinfo` `ext4` type, and `fstatfs` magic. Its launcher, closed-ABI static `ET_EXEC` deployment adapter with nonoverlapping page-rounded load mappings, exact CPython 3.12.3 interpreter closure, wheel, bootstrap, manifests, direct-`P` interpreter layout, one-line externally approved `python3.12._pth`, curated stdlib/dynload roots, other roots, and final name are selected outside candidate-facing argv/env/stdin/cwd/config; Recorder supplies no self-authorizing fallback. Before `execveat`, the launcher authenticates the getpath file, exact layout/build, and absence of venv/build/competing-`._pth` overrides. Initial `sys.path` is exactly the single approved stdlib root; prefix, executable, and stdlib fields are exact. The adapter has one argv/FD/env/cwd/report protocol and distinct exit 74 for report-channel failure. After the three externally approved preloaded `encodings` objects and before its unique externally approved retained-procfd hash-seed load, the Python bootstrap performs no new filesystem import. Stdlib rows use closed `PRELOADED`/`SEED`/`LATE` stages: the three fixed preloaded `encodings` filesystem objects map one-to-one to `PRELOADED`; `os` is approval-bound frozen and absent from the manifest; all other early/builtin/frozen/stdlib/protected-runtime name sets are disjoint. The bootstrap reopens and retains the approved getpath object and rejects identity/byte drift still observable at that reopen. Root/operator change-and-restore ABA before reopen is locally indistinguishable, remains an external prerequisite, and cannot establish pathname continuity or a security PASS. The bootstrap then hashes and executes every `LATE` stdlib module and every protected-runtime module only from retained FDs. It independently rejects inherited `SIGCHLD`/mask defects before `Popen`. One frozen argv grammar, exact OS-byte preservation, target `Popen` call, usage result, pre-launch failure mapping, and post-launch stdout/stderr isolation rule apply. Public console/module proxy requests fail before Recorder proxy imports. Unsupported Linux, `/mnt/c`, non-Linux POSIX, any other CPython patch/build, and CPython 3.13 fail closed. The adapter remains `POSIX_CPTHON_3_12_VALIDATION` and cannot acquire Windows production or release-authority status. |
| REC-062 | Exact deployment-report terminal writer | Every Windows deployer branch preselects one canonical intended success or failure row. One blocking binary unbuffered counted writer emits only its precomputed ASCII-plus-LF bytes, advances only by acknowledged positive progress, and performs exactly one terminal close. Zero or invalid progress, write error, or terminal-close failure preserves the exact acknowledged prefix, writes no stderr, and uses non-finalizing exit 74. The launcher never parses exit-74 bytes, including a complete-looking row; healthy completion cannot be rewritten to CPython exit 120. |

## Required verifier result

The verifier returns a machine-readable result with at least:

- format validity;
- journal presence and evidence-origin platform profile;
- hash-chain validity;
- committed-entry count and final digest;
- clean shutdown status;
- transport completeness;
- unresolved forward outcomes;
- partial-tail byte count;
- assurance level;
- `authority_verified=false`;
- stable reason IDs;
- guard-sidecar validity, journal binding, termination request, and reclamation
  state when applicable, including whether the sidecar ever bound a journal;
- a nonzero process exit for corrupt, incomplete, or uncertain evidence.

An integrity-clean local journal may return zero only for the local transport
contract. It remains ineligible to clear `AUTHORITY_UNVERIFIED`.

## Platform validation profiles

- runner `windows-cpython313` produces evidence profile
  `WINDOWS_CPTHON_3_13`: production transport profile. Requires Windows pipe
  preflight, binary CRT mode, native exclusive/write-through journal handle,
  cancellable synchronous I/O, and Job Object containment.
- runner `linux-cpython312` produces evidence profile
  `POSIX_CPTHON_3_12_VALIDATION`: independent validation profile. It verifies the portable
  journal, verifier, exact byte relay, process-group termination, backpressure,
  and crash semantics. It does not prove Windows behavior or authorize Aegis
  release on Linux.
- `WINDOWS_SUPERVISION_ONLY` is an evidence-only profile for a valid guard
  sidecar when the journal is absent, whether no journal was created or the
  supplied copy is incomplete. It is not a transport profile and can never
  PASS.

## Excluded claims

- completeness of Codex events that never crossed the owned stdio boundary;
- post-hoc capture of the current Desktop process;
- resistance to an administrator or the same OS user rewriting local storage;
- proof that an ordinary path component had the same identity before its first
  handle-relative open;
- general write protection for the protected runtime after deployment;
- trusted wall-clock time;
- independent provider commit position;
- Phase 0A freeze authority;
- product quality or test verdict.
