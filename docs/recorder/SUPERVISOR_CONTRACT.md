# Aegis Recorder supervisor contract

Status: `NORMATIVE_DRAFT_FOR_REREVIEW_8`

## 1. Process roles

The Windows production profile has two Recorder processes:

```text
Desktop/Codex parent pipes
        |
        +-- guard
              |
              +-- outer Job Object
                    |
                    +-- engine
                          |
                          +-- target Job Object
                                |
                                +-- target codex.exe app-server
                                +-- target descendants
```

The guard owns the outer Job Object, engine process handle, and supervision
sidecar. The engine owns the journal, relay threads, target Job Object, target
process handle, and all target-facing pipe endpoints. The guard never parses,
journals, reads, or writes app-server bytes.

The guard remains outside the outer Job Object. It creates the engine suspended,
assigns it to the outer Job Object, and only then resumes it. The outer Job has
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`; breakaway flags are absent.

The engine creates the target suspended, assigns it to the nested target Job,
establishes an independent guard wait handle, durably records containment, and
publishes durable resume intent. Only then may the guard main thread call
`ResumeThread`. The target primary thread cannot execute before these gates
complete.

The POSIX profile uses one Recorder process and a new process group. It does not
claim the Windows guard deadline.

## 2. Trusted Windows bootstrap and exact proxy CLI

The Windows production profile has exactly one public proxy argv grammar:

```text
<ABSOLUTE_TRUSTED_PYTHON_EXE>
-I
-S
-B
-X
utf8
<ABSOLUTE_PROTECTED_RUNTIME_ROOT>\aegis_recorder_bootstrap.py
proxy
--session-dir
<ABSOLUTE_ABSENT_SESSION_DIRECTORY>
--
<ABSOLUTE_REGULAR_TARGET_EXE>
<TARGET_ARG_1> ... <TARGET_ARG_N>
```

The line breaks above separate argv elements; they are not command-shell
syntax. For the intended Codex target, `TARGET_ARG_1` is literal
`app-server`. Test fixtures may use another absolute regular `.exe`. Options
cannot be reordered, repeated, abbreviated, or introduced after `--`.

Production launch is a direct `CreateProcessW` call made by the trusted
operator/Master using the canonical serializer below. PATH lookup, a shell,
an activated virtual environment, a generated console-script launcher,
`py.exe`, bare `python`, and ordinary `python -m aegis_recorder` are
development conveniences only and do not satisfy the production profile.

The packaged console-script and module parsers reject `proxy` on every
platform before importing `guard`, `engine`, or any target-launch module. They
expose only read-only `verify` and `validate-report`. A POSIX validation proxy
enters only through the external `LINUX_PROTECTED_BOOTSTRAP_V1`
`execveat`/fixed-procfd deployment, isolation, argv, output, and import
contract in `POSIX_ADAPTER_CONTRACT.md`. A Linux implementation earns
validation evidence only after that external prerequisite and contract pass.
Neither `python -m aegis_recorder` nor an installed console script is a proxy
path. The Windows trusted bootstrap enters a private guard function directly;
it does not route through the public console/module parser.

The Windows absolute bootstrap script and absolute interpreter are deployment
trust anchors selected outside the candidate repository. Production never creates
the protected runtime with `pip install --target`; the protected-runtime
deployment subsection defines the sole production path. Ordinary wheel
installation with pip remains a development and packaging test only.

### Operator-to-guard production launcher

The first Windows proxy process is created by a distinct operator-controlled
launcher. This is not the protected-runtime deployer launcher and is not the
guard-to-engine launch path. Recorder supplies only a conformance harness; it
does not supply, select, or self-authorize this launcher or its approval slot.

The external approval slot selects the exact absolute interpreter and
bootstrap paths plus their expected SHA-256 values, fixed-drive NTFS volume
identities, and `FILE_ID_INFO` values. Candidate argv, environment, cwd,
configuration, repository files, wheel contents, and Recorder output cannot
select or replace that slot.

Before `CreateProcessW`, the launcher:

1. applies the frozen Windows path grammar below and requires current
   drive/volume `QueryDosDeviceW` equality;
2. opens the native volume roots, every ancestor, the interpreter, and the
   bootstrap by relative `NtCreateFile` with `OBJ_DONT_REPARSE` and
   `FILE_OPEN_REPARSE_POINT`;
3. rejects every reparse tag, volume transition, spelling/identity mismatch,
   non-regular leaf, or non-NTFS volume;
4. opens interpreter/bootstrap leaves without write or delete sharing and
   ancestor directories without delete sharing, hashes the held file objects,
   and compares both complete digests and identities with the external slot;
5. retains all those handles until the guard process has terminated; none is
   inheritable by the child;
6. applies the exact pipe type/mode, pairwise object/name distinction, and
   read-only-stdin/write-only-output access predicates defined below, then
   creates three child-only inheritable duplicates of the approved stdin,
   stdout, and stderr handles. The originals and every ambient handle remain
   non-inheritable;
7. sets `STARTF_USESTDHANDLES`, puts exactly those three duplicates in one
   `PROC_THREAD_ATTRIBUTE_HANDLE_LIST`, sets `bInheritHandles=TRUE`, and calls
   `CreateProcessW` directly with the exact `lpApplicationName`, canonical
   `lpCommandLine`, and absolute requested target cwd;
8. closes the three temporary duplicates immediately after process creation
   while retaining the non-inheritable originals and trust-object handles.

The launcher conformance matrix proves hash/identity mismatch, component
reparse, DOS-device inequality, forbidden share access, missing/aliased/wrong-
direction standard handles, one extra ambient inheritable handle, a changed
bootstrap after validation, and every `UpdateProcThreadAttribute`/
`CreateProcessW` failure. Every case fails before unapproved bootstrap code can
execute. If the external launcher or approval slot is missing or nonconforming,
the Windows production proxy is unavailable; there is no ordinary path launch
fallback. Bootstrap self-checks are defense in depth and cannot replace this
pre-execution authority.

The bootstrap's first executable statement enters a top-level `BaseException`
barrier before any Recorder import. Inside that barrier it first imports only
the already-loaded `sys` builtin, requires `sys.flags.isolated == 1`,
`sys.flags.no_site == 1`, `sys.flags.dont_write_bytecode == 1`, and UTF-8 mode,
sets `sys.dont_write_bytecode = True`, confirms the value, and installs the
frozen import/output guards. It then:

1. calls `GetCommandLineW`, reconstructs the exact expected full argv above,
   and rejects a raw command line that is not its unique canonical
   serialization;
2. rechecks the four interpreter flags, the exact absolute interpreter path,
   and the exact absolute bootstrap path;
3. captures the initial absolute current directory as the target cwd, then
   switches to the protected runtime root before importing Recorder modules;
4. reads the frozen runtime manifest by absolute path, verifies its
   bootstrap-embedded expected digest, hashes every listed package/runtime
   member, and rejects missing, extra, linked/reparse, or mismatched members;
   the bootstrap trust-anchor file itself is intentionally outside that
   non-circular manifest;
5. rejects every `.pyc`, `__pycache__`, case-fold collision, unexpected
   directory, `.dist-info`, `Scripts`, link, or reparse member;
6. freezes the pre-bootstrap `sys.modules` set, permits later imports only when
   the top-level standard-library name is in the bootstrap-embedded stdlib
   allowlist or the relative `aegis_recorder` module is listed in the verified
   runtime manifest, and rejects all other imports before module execution;
7. hashes the interpreter bytes for the journal interpreter identity fields;
8. imports and enters the guard only after all checks pass.

The exact interpreter-flag predicates above are normative. The CPython 3.13
command-line page is informative reviewer provenance only and is not
incorporated by reference:
https://docs.python.org/3.13/using/cmdline.html.

The same recursive root enumeration and import policy runs on every guard and
internal-engine launch. Recorder does not claim that the runtime is immutable.
The acceptance invariant is narrower: two sequential clean launches, with no
external mutation injected between them, must each verify the complete root
before Recorder import and must observe the identical
member-name/type/size/hash set. `-B` plus the explicit
`sys.dont_write_bytecode` assignment prevents Recorder imports from creating
bytecode. Drift observed at either launch rejects that launch; no statement is
made about bytes after verification or about an actor that can replace them.

Allowed package module names are derived only from manifest-listed regular
`.py` paths: `aegis_recorder/__init__.py` maps to `aegis_recorder`, and
`aegis_recorder/x/y.py` maps to `aegis_recorder.x.y`. Namespace packages,
extension modules, zip imports, absolute file loaders, path mutation, and a
module whose normalized path is absent from the manifest are forbidden. The
bootstrap-embedded stdlib top-level allowlist is a literal immutable tuple; a
transitive stdlib import must also appear in it. Interpreter-startup modules
already present in the first captured `sys.modules` snapshot are recorded as
preloaded and are not relabelled as bootstrap imports.

The bootstrap does not claim that Windows ACLs prevent the same user or an
administrator from replacing those trust-anchor bytes. Selecting and
protecting the runtime root is an operator precondition and remains inside the
local-assurance boundary.

The direct launcher's `lpCurrentDirectory` is therefore the requested target
cwd. It must be absolute. It is preserved for target `CreateProcessW` after the
guard and engine switch to the protected runtime root.

The guard starts the engine through the same verified bootstrap, never by an
ordinary module lookup:

```text
ABSOLUTE_TRUSTED_PYTHON_EXE -I -S -B -X utf8
ABSOLUTE_BOOTSTRAP_PY --internal-engine <PRIVATE_FIXED_ARGUMENTS>
```

`<PRIVATE_FIXED_ARGUMENTS>` contains only the exact decimal inherited-handle
values, canonical UUIDs, nonce, session directory, target argv, target cwd, and
expected manifest digest defined by this contract. The public parser rejects
`--internal-engine`; only the bootstrap's manifest-verified internal parser
accepts it.

### Protected runtime deployment

This deployment mechanism is Windows-only. Linux/WSL2 validation uses the
distinct externally approved native launcher/deployment-adapter, fixed-FD
procfs bootstrap, and native-filesystem contract in
`POSIX_ADAPTER_CONTRACT.md`. Unsupported POSIX has no fallback.

`recorder/tools/deploy_protected_runtime.py` is repository source, not its own
production trust anchor. For production, an operator-controlled launcher
places an exact reviewed copy outside the candidate repository, wheel,
protected root, final-root parent, and current directory. The expected
interpreter and deployer SHA-256 values come from an operator-approved record
outside all candidate-controlled inputs. The candidate cannot write, delete,
rename, or replace the selected deployer, trusted interpreter installation,
stdlib/dynamic-load trees, or any of their path ancestors. The launcher opens
the interpreter, deployer, and every path component by native relative handle,
excludes write and delete sharing on the two files and delete sharing on their
ancestors, hashes the held file handles, verifies the operator-protected
interpreter-tree identities and access boundary, compares the external expected
hashes, and keeps those handles open until the deployer process exits. The
external record also binds the trusted interpreter-root identity and the
absence of `<INTERPRETER_ROOT>\python313.zip`. A value supplied by the deployer,
wheel, repository, or final root cannot authorize those comparisons. The
deployer's later self-hash is defence in depth against post-selection drift,
not a self-issued trust claim.

The operator launcher and its external approved-hash record are deployment
prerequisites, not Recorder deliverables. Recorder supplies this normative
launch contract and an independent conformance harness only. If the operator
cannot provide a launcher that passes the contract, protected-runtime
deployment is unavailable; the project does not fall back to a repository
launcher or weaken the trust claim.

The only deployer argv grammar is:

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

The line breaks separate argv elements. Options have the exact order above and
cannot be omitted, repeated, abbreviated, reordered, or followed by another
element. Every path element is an exact Windows UTF-16 code-unit sequence.

The external launcher calls `CreateProcessW` directly. `lpApplicationName` is
the exact interpreter path and `lpCommandLine` is the unique canonical
serialization of the argv above. `lpCurrentDirectory` is the exact
operator-protected control directory named by `--control-dir`; that directory
is outside all candidate paths and is empty when selected. The Unicode child
environment contains exactly, in this order,
`SystemRoot=<trusted-Windows-root>` and
`WINDIR=<same-trusted-Windows-root>`, followed by the terminating empty entry.
There is no `PATH`, `PYTHON*`, user-profile, virtual-environment, or temporary
directory variable. Launch uses
`CREATE_UNICODE_ENVIRONMENT|EXTENDED_STARTUPINFO_PRESENT`, no shell, and
`STARTUPINFOEXW.StartupInfo.dwFlags=STARTF_USESTDHANDLES`.
`hStdInput`, `hStdOutput`, and `hStdError` are respectively a read-only `NUL`
handle, the deploy-report stdout pipe's child write handle, and a distinct
captured-stderr pipe's child write handle. The launcher creates one dedicated
inheritable duplicate for each of those three child handles; the parent-side
handles and all original handles are non-inheritable. The
`PROC_THREAD_ATTRIBUTE_HANDLE_LIST` contains exactly those three inheritable
duplicates, `CreateProcessW.bInheritHandles=TRUE`, and the launcher closes the
three child duplicates after the creation call. Any duplicate failure, alias,
wrong direction/type, fourth list member, inherited ambient handle,
`bInheritHandles=FALSE`, absent `STARTF_USESTDHANDLES`, or standard-handle/list
mismatch fails before the deployer starts.

The deployer's first executable statement installs one top-level
`BaseException` barrier before a non-preloaded import. Inside it, the deployer:

1. requires the frozen 64-bit Windows CPython 3.13.13 profile and exact
   `-I -S -B -X utf8` flag semantics, sets and confirms
   `sys.dont_write_bytecode`, and checks the expected `sys.executable` and
   fixed-order `sys.argv` values available from already-loaded `sys`;
2. before any non-preloaded import, requires the initial `sys.path` to equal
   this exact CPython 3.13.13 vector, using the exact absolute spellings already
   identity-bound and held by the external launcher:

   ```text
   <INTERPRETER_ROOT>\python313.zip
   <ABSOLUTE_TRUSTED_STDLIB_DYNLOAD_ROOT>
   <ABSOLUTE_TRUSTED_STDLIB_ROOT>
   <INTERPRETER_ROOT>
   ```

   The first element must be absent beneath the held interpreter-root handle
   and externally bound as absent; the dynamic-load root must be exact
   `<INTERPRETER_ROOT>\DLLs`, the stdlib root exact
   `<INTERPRETER_ROOT>\Lib`, and the last element the held interpreter root.
   Cwd, deployer-directory, wheel, final-root, site-packages, user-site, and
   any fifth entry are forbidden;
3. validates preloaded import machinery and every preloaded module, including
   the required `encodings` origin under the held `Lib` root. It then performs
   the sole permitted bootstrap path mutation:
   `sys.path[:] = [<held DLLs>, <held Lib>]`, removes importer-cache entries
   outside those two roots, freezes the resulting vector, and installs a
   pre-execution import guard. Any later `sys.path`, path-hook, finder, or
   importer-cache mutation fails;
4. permits only `built-in` and `frozen` origins, regular non-reparse `.py` files
   below the held standard-library root, and regular non-reparse `.pyd` files
   below the held dynamic-load root. Loader, `__spec__.origin`, `__file__`, and
   resolved held-file identity must agree. Zip, namespace, candidate, wheel,
   protected-root, site, and path-mutating imports fail before module
   execution;
5. imports only the frozen standard-library allowlist needed for native path
   access, hashing, restricted JSON, ZIP parsing, and output, then rechecks the
   same provenance after every import;
6. using only those guarded imports, opens the interpreter and its own source
   through retained native component handles, hashes the held files, requires
   the two externally supplied expected hashes, and checks the exact cwd plus
   canonical `GetCommandLineW` value before reading the wheel.

An interpreter/startup loader failure before the first deployer statement
remains an external-launcher failure. The external interpreter installation,
its startup modules, and the operator launcher are outside Recorder's local
code-byte claim.

All deployment paths use one frozen Windows grammar:

```text
[A-Z]:\<COMPONENT>(\<COMPONENT>)*
```

UNC, device, volume-GUID, extended-prefix, rooted-relative, drive-relative,
forward-slash, empty, `.`, and `..` spellings are rejected. A component cannot
contain NUL, control code units, `\ / : * ? " < > |`, an alternate data stream,
or a trailing space or dot; DOS device names are rejected
case-insensitively. Component length cannot exceed the native volume's reported
maximum, and total length cannot exceed 32767 UTF-16 code units. No Unicode or
case normalization changes the input; the exact component spelling is checked
against the opened object.

Each accepted drive must return `DRIVE_FIXED` from `GetDriveTypeW`. For every
distinct drive used by the interpreter, deployer, standard-library roots,
control directory, wheel, or final root, both the external launcher and
deployer independently require `GetVolumeNameForVolumeMountPointW(<X:\>)` to
return one canonical volume-GUID name. They call `QueryDosDeviceW` for `X:` and
for that volume name stripped of its `\\?\` prefix and trailing slash; the
first current native targets must be byte-for-byte equal. The external launcher
performs this comparison once immediately before `CreateProcessW`, then retains
the opened native volume and ancestor handles until deployer exit. The deployer
performs its own comparison during preflight, retains its first pair, and alone
repeats the comparison immediately before publication; inequality or drift
from its first pair rejects. There is no launcher/deployer ready-ack channel
and no post-launch launcher recheck claim. Failure, malformed or ambiguous
output, or observed inequality/drift rejects SUBST and other directory
DOS-device mappings that are not filesystem reparse points. An unobserved
change-and-restore between the deployer's two snapshots remains outside the
claim; held handles prevent it from retargeting the actual publication object.

The deployer opens the accepted native volume root, requires filesystem name
`NTFS` from `GetVolumeInformationByHandleW`, and then opens and retains every
component relative to the previous handle with `NtCreateFile`,
`RootDirectory`, `OBJ_DONT_REPARSE`, and `FILE_OPEN_REPARSE_POINT`. It queries
attributes, reparse tag, volume identity, `FILE_ID_INFO`, and exact
final-component spelling from each handle. A reparse point, link-like object,
volume transition, case-only alias, incompatible share mode, identity change,
or string-path reopen fails closed. The wheel is read only through its retained
regular-file handle. The final leaf must be absent beneath a retained
final-parent handle.

Before creating staging, the deployer requires 64-bit pointer and two-byte
`WCHAR` layout; native `FileRenameInformation == 10`;
`sizeof(FILE_RENAME_INFORMATION)==24`; `FILE_RENAME_INFORMATION` offsets
`offsetof(ReplaceIfExists)=0`, `offsetof(RootDirectory)=8`,
`offsetof(FileNameLength)=16`, and `offsetof(FileName)=20`; a 16-byte
`IO_STATUS_BLOCK`; the `ntdll!NtSetInformationFile` and
`NtWaitForSingleObject` exports; fixed NTFS
identity; an externally approved Windows build/profile with real-host
retained-parent rename/collision conformance evidence; and every required
access/share predicate. The final-parent handle has
`FILE_TRAVERSE`,
`FILE_LIST_DIRECTORY`, `FILE_ADD_SUBDIRECTORY`, `FILE_READ_ATTRIBUTES`, and
`SYNCHRONIZE`, with no delete sharing. If this static capability and layout
preflight is not established, deployment fails without creating staging. The
eventual rename call may still fail and is handled as a normal no-publication
failure.

The deployer independently validates the expected-hash wheel's filename,
complete ZipInfo/member set, `RECORD`, bootstrap bytes, runtime manifest bytes,
embedded manifest digest, member sizes/hashes/types, normalized relative paths,
case-fold uniqueness, and absence of links/reparse semantics. A caller's prior
validation does not let the deployer skip this independent read. It never
imports the build backend, wheel runtime code, distribution metadata, or
`aegis_recorder`. It enforces the plan's exact 64-MiB physical/uncompressed,
512-member, 16-MiB member, and 512-byte path limits before extraction.

The protected runtime's recursive regular-file set is exactly:

```text
aegis_recorder_bootstrap.py
aegis_recorder/code_manifest.v1.json
<every normalized relative runtime file listed by code_manifest.v1.json>
```

Directories are allowed only as prefixes required by those files. The final
root contains no wheel `.dist-info`, `Scripts`, installer metadata, `.pyc`,
`__pycache__`, directory entry from the archive, unlisted file, alternate-case
alias, link, device, or reparse point.

Deployment is transactional:

1. recheck through the retained final-parent handle that the final component is
   absent;
2. create one cryptographically unpredictable, single-component, create-new
   staging directory relative to that same held parent; refuse a pre-existing
   name; open it with `DELETE|FILE_LIST_DIRECTORY|FILE_READ_ATTRIBUTES` and
   `SYNCHRONIZE`, `FILE_SYNCHRONOUS_IO_NONALERT`, and
   `FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE`; immediately record its
   `FILE_ID_INFO`, and retain that staging handle through publication and
   result emission;
3. derive the frozen extraction allowlist from the already-validated bootstrap,
   manifest, and manifest-listed runtime rows;
4. create each directory and regular file relative to retained directory
   handles with no overwrite, stream the exact wheel bytes, verify the counted
   size/hash, call `FlushFileBuffers`, and close every member-file handle;
5. reopen every staged file without following a link/reparse target, reread all
   bytes, and independently recheck path, type, size, and hash;
6. through the held staging handle, recursively enumerate and require the exact
   file/directory set, including rejection of case collisions, extras, `.pyc`,
   `__pycache__`, and reparse points; require its current
   `VolumeSerialNumber` and 128-bit `FileId` to equal the creation identity;
   close every member handle while retaining only staging and its
   ancestor/final-parent handles;
7. checked-add `max(sizeof(FILE_RENAME_INFORMATION),
   offsetof(FILE_RENAME_INFORMATION,FileName)+FileNameLength)`, allocate and
   zero that exact buffer, and write `ReplaceIfExists=FALSE`,
   `RootDirectory=<held final-parent handle>`,
   `FileNameLength=<exact final-component UTF-16LE byte count>`, and `FileName`
   beginning at offset 20 with that one component and no separator or
   terminating NUL. The zero tail supplies the documented minimum structure
   padding but is not part of `FileNameLength`. Call
   `NtSetInformationFile` on the held `DELETE`-capable staging handle with a
   `IO_STATUS_BLOCK` initialized to `Status=0xffffffff,Information=0`, native
   `FileRenameInformation=10`, and
   `Length=max(24,20+FileNameLength)`. Matching `STATUS_SUCCESS` from the call
   and IOSB commits. `STATUS_PENDING` waits on the held staging handle through
   `NtWaitForSingleObject` and uses the final IOSB only after a successful
   wait. Its timeout is one non-null signed `LARGE_INTEGER` containing the
   ceiling-rounded negative 100-nanosecond remainder; zero budget never waits,
   and null, infinite, nonnegative, or overflowing encodings are forbidden.
   Only exact `STATUS_SUCCESS`, `STATUS_OBJECT_NAME_COLLISION`,
   `STATUS_INVALID_INFO_CLASS`, `STATUS_INVALID_PARAMETER`, and
   `STATUS_NOT_SUPPORTED` have known meanings. Every other 32-bit value,
   including nonzero success, informational, warning, unlisted error,
   sentinel, and still-pending values, is
   `PUBLICATION_OUTCOME_UNKNOWN`; timeout, alert/failure, or call/IOSB
   disagreement is also unknown. Unknown is neither `published` nor
   `not published`. Definite `STATUS_OBJECT_NAME_COLLISION` proves no-replace.
   The complete constants, deadline mapping, and call/wait/IOSB state table are
   frozen in `IMPLEMENTATION_PLAN_FINAL.md`.
   `SetFileInformationByHandle`, a null `RootDirectory`, pathname rename, and
   replace/POSIX/ignore-readonly/storage-reserve semantics are forbidden;
8. after the successful rename, keep the source staging handle open, reopen the
   final component relative to the same held parent with no reparse traversal,
   and query `FILE_ID_INFO` from both handles. Success requires both
   `VolumeSerialNumber` and all 128 `FileId` bits from the pre-rename staging,
   post-rename staging, and reopened final handles to match, followed by one
   final exact-member/hash enumeration through the reopened final handle.

The successful rename is the namespace publication point, but it is not the
terminal success point. Any definite pre-publication failure leaves the final
name absent unless a foreign actor occupied it; such an occupant is never
replaced or deleted. An unresolved pending/mismatch result makes no such
claim. A failure in the post-publication identity/member checks returns
`PUBLISHED_IDENTITY_UNCONFIRMED`, reports
`publication_state="PUBLISHED"`, and never claims a successful deployment. An
unresolved pending or contradictory native result returns
`PUBLICATION_OUTCOME_UNKNOWN` with
`publication_state="PUBLICATION_OUTCOME_UNKNOWN"`. It performs no final-path
lookup to collapse that uncertainty. Neither case attempts rollback, deletion,
repair, replacement, or a second rename.

V1 performs no automatic recursive cleanup after any failed deployment. It
does not recursively delete, rename, merge, quarantine, or reuse the failed
staging namespace. It reports the original staging path and retained file
identity for operator-directed quarantine, then closes handles on exit. A retry
uses a fresh create-new name. This avoids converting a same-user name race into
deletion of a foreign tree. Same-user replacement after publication remains
inside the declared local-assurance boundary.

After its first statement, every controlled deployer outcome attempts exactly
one restricted-canonical-JSON ASCII line on stdout and zero bytes on stderr.
Keys are ASCII-lexicographically ordered, there is no whitespace or BOM, and
one LF terminates the line:

```json
{"exit_code":0,"final_root":{"encoding":"windows-utf16le-hex","value":"<lowercase-hex>"},"post_publish_identity_confirmed":true,"publication_state":"PUBLISHED","published_file_id":{"file_id_hex":"<32-lowercase-hex>","volume_serial_number_hex":"<16-lowercase-hex>"},"reason_id":"DEPLOYED","schema_version":"AegisRecorderProtectedRuntimeDeploymentReport.v1","staging_file_id":{"file_id_hex":"<32-lowercase-hex>","volume_serial_number_hex":"<16-lowercase-hex>"},"staging_path":{"encoding":"windows-utf16le-hex","value":"<lowercase-hex>"},"status":"SUCCEEDED"}
```

Each path value is the exact UTF-16LE code-unit bytes, with no BOM or
terminating NUL, encoded as lowercase hexadecimal; no display-path string is
authoritative. Before argv parsing, `final_root` is `null`. Before staging
creation, both staging fields are `null`. After staging creation, the original
staging path and pre-rename identity remain populated on success and failure,
even though the old name no longer exists after publication. Before final
reopen, `published_file_id` is `null`. All non-success rows use
`status="FAILED"` and `post_publish_identity_confirmed=false`.

Argument parsing is all-or-nothing: every `INVALID_INVOCATION` row has
`final_root=null`, both staging fields null, `published_file_id=null`, and
`publication_state="NOT_PUBLISHED"`, even if a malformed prefix contained
path-like text. After
grammar acceptance, `final_root` is populated before trust/input validation.
If final reopen succeeds but identity comparison fails, its observed
`published_file_id` remains populated as evidence and does not imply
confirmation.

Exit 0 is only `DEPLOYED`. Exit 64 is only `INVALID_INVOCATION`. Exit 1 covers
`TRUST_ANCHOR_REJECTED`, `INPUT_REJECTED`, `DEPLOYMENT_FAILED`, and
`PUBLISHED_IDENTITY_UNCONFIRMED`, and `PUBLICATION_OUTCOME_UNKNOWN`. With a
healthy report channel, exit 70 has one complete canonical
`INTERNAL_DEPLOYER_FAILURE` row. `publication_state` is exactly
`NOT_PUBLISHED`, `PUBLICATION_OUTCOME_UNKNOWN`, or `PUBLISHED`; it is derived
only from the frozen native status machine and is never inferred from a path
lookup. Unknown outcome requires non-null final/staging locators and staging
identity, null `published_file_id`, and
`post_publish_identity_confirmed=false`. A missing/invalid report handle fails before staging, is itself a
report-channel failure, and produces no deployment-report object. The process
exits 74 with empty stderr; the external launcher retains the exact stdout
prefix it captured, normally empty. The same rule applies if the report pipe is
lost while emitting the preselected intended row: no process can fabricate
the missing line. The intended row may be a success or any failure row.

The deployer bypasses Python text streams. It encodes the complete row plus LF
before its first output call and writes those bytes to the validated blocking
binary stdout handle through one unbuffered counted `WriteFile` loop. Each call
must acknowledge `1..remaining` bytes. Positive short progress advances by
exactly the acknowledged count; zero progress, an impossible count, or API
failure terminates the loop. After all bytes are acknowledged, the deployer
performs exactly one terminal `CloseHandle` on its stdout handle. It performs
no retry, fallback write, stderr write, second close, or Python stream flush.

Any counted write or terminal-close failure exits 74 through a non-finalizing
process-exit primitive, preserving the exact acknowledged raw prefix and zero
stderr bytes. Healthy completion also uses the fixed process-exit path after a
successful terminal close, so CPython finalization cannot replace the intended
exit with 120. The external launcher records the exact raw stdout bytes it
captured. Those bytes may be any prefix, including empty or complete, of the
preselected intended row. Exit 74 is reserved exclusively for report-channel
failure and prevents a
complete-looking prefix from being observationally identical to the healthy
exit-70 row. The launcher accepts exit 70 only with one complete, canonical,
semantically valid row whose embedded `exit_code` is 70; it never parses exit
74 bytes as a report.

### Unique `lpCommandLine` serialization

One implementation serializes both guard-to-engine and engine-to-target argv.
Every argv element is a sequence of exact UTF-16 code units with no
`U+0000`. Encoding uses UTF-16LE with surrogate preservation. The complete
mutable buffer, including its one terminating UTF-16 NUL, must contain at most
`32767` code units.

The only algorithm is the code-unit-preserving form of CPython 3.13
`subprocess.list2cmdline`, named `PYTHON_LIST2CMDLINE_UTF16_V1` here. The
journal binds its exact resulting bytes, count, hash, and application name.
Production implements the algorithm directly and does not import `subprocess`.
For each argument:

1. add outer quotes only if it is empty or contains `U+0020` or `U+0009`; a
   literal `U+0022` alone does not trigger outer quotes;
2. if outer quotes are required, emit one opening `U+0022`;
3. buffer each consecutive `U+005C` backslash;
4. before an ordinary code unit, emit all `n` buffered backslashes unchanged,
   then the code unit;
5. before a literal `U+0022`, emit `2*n+1` backslashes for the buffered run of
   `n`, then emit the quote;
6. at argument end, emit `2*n` backslashes and one closing quote when outer
   quotes are active; otherwise emit the `n` backslashes unchanged;
7. join encoded arguments with exactly one `U+0020` and no leading or trailing
   separator.

`lpApplicationName` is the same exact absolute executable as argv element
zero. `lpCommandLine` includes argv element zero and is backed by a mutable
`uint16_t` array constructed from the serialized UTF-16LE code units; a Python
text buffer with implementation-defined surrogate conversion is forbidden.

Canonical examples:

```text
argv:
  C:\Program Files\Codex\codex.exe
  app-server
  --root=C:\work
lpCommandLine:
  "C:\Program Files\Codex\codex.exe" app-server --root=C:\work

argument: <empty>
serialized: ""

argument: C:\dir with space\
serialized: "C:\dir with space\\"

argument: a"b
serialized: a\"b

argument code units: 0061 005c 005c 0022 0062
serialized code units: 0061 005c 005c 005c 005c 005c 0022 0062

argument: a b
serialized: "a b"

argument code units: 0061 d800 0062
serialized code units: 0061 d800 0062
```

Rejected non-equivalent or noncanonical forms include:

```text
'C:\Program Files\Codex\codex.exe' app-server
C:\Program Files\Codex\codex.exe app-server
"C:\dir with space\"                 # trailing slash escapes the closing quote
"a\"b"                               # unnecessary outer quotes; canonical is a\"b
<argv elements joined with spaces>   # loses empty and embedded-space elements
cmd.exe /c ...
powershell.exe -Command ...
```

Tests compare the exact UTF-16LE buffer, round-trip adversarial argv through an
independent Windows fixture, and reject alternate spellings that parse to the
same argv. Mandatory vectors include `a"b`, consecutive backslashes before a
quote, an empty argument, space, tab, trailing backslashes in a quoted
argument, non-BMP pairs, and unpaired surrogates. The contract binds bytes
passed to `CreateProcessW`; a target that implements a nonstandard command-line
parser remains outside Recorder's guarantee.

The normative Windows argument-conversion reference is:
https://docs.python.org/3.13/library/subprocess.html#converting-an-argument-sequence-to-a-string-on-windows.

The engine journals the four command-line identity fields fixed by
`JOURNAL_PROTOCOL_V1.md`. The independent Verifier reserializes
`requested_argv`, checks the full hex buffer, code-unit count, domain-separated
hash, and `lpApplicationName`, and rejects any mismatch.

## 3. Output channels

During an active proxy:

- stdout contains only exact target stdout bytes;
- stderr contains only exact target stderr bytes;
- the guard never writes either stream;
- engine diagnostics are journal control entries;
- after the trusted bootstrap executes its first statement, bootstrap, guard,
  and engine diagnostic contribution to stdout and stderr is exactly zero
  bytes on every controlled success and failure, including before engine
  launch and after target stream closure;
- a controlled failure before target creation therefore leaves both streams
  exactly empty; after target creation, any bytes are target bytes only;
- no status JSON is written to proxy stdout.

The public Windows console-script/module `proxy` rejection remains a usage
path, not the trusted bootstrap path: it exits 64 before importing guard or
engine, writes zero stdout bytes, and writes exactly these ASCII stderr bytes:

```text
aegis-recorder: Windows proxy requires the protected bootstrap
```

The code block contains exactly one final LF and no other trailing byte.
Read-only public commands retain their own output contracts.

The bootstrap installs the top-level exception barrier before its first
explicit non-`sys` import. It converts every caught bootstrap/guard exception
to the stable class below without a traceback, warning, logging fallback,
`unraisablehook`, or interpreter-shutdown diagnostic. The engine installs the
same zero-diagnostic barriers before Recorder imports and communicates only
through the journal, sidecar, private handshake, and process exit class.

The output guard replaces Python-level `sys.stdout`, `sys.stderr`,
`sys.__stdout__`, and `sys.__stderr__` with sealed non-forwarding objects
without closing or changing the three underlying parent pipe handles. It
installs non-writing `sys.excepthook` and `sys.unraisablehook`; after the
allowlisted `threading` import it also installs a non-writing
`threading.excepthook`. Production bootstrap/guard/engine code is forbidden
from `print`, logging stream handlers, warnings-to-stream, `os.write(1|2,...)`,
or native console/file writes. Target pipes are transferred and relayed only
through the explicit Win32 handle path, so Python stream suppression cannot
discard target bytes.

Controlled failure mapping is exhaustive and first-failure-wins:

| Failure category | Stable class |
|---|---:|
| trusted-bootstrap argv grammar/canonical raw-command mismatch | 64 |
| missing `-I -S -B -X utf8`, wrong interpreter, or bytecode-disable failure | 10 |
| bootstrap/runtime manifest, import allowlist, root membership, hash, type, case-collision, pyc, or reparse failure | 10 |
| bootstrap/interpreter/cwd/session-parent absolute-path preflight failure | 10 |
| standard-pipe type, direction, alias, mode, or identity failure | 10 |
| guard already inside a host Job | 10 |
| absent-session create-new failure before sidecar creation | 10 |
| sidecar create/write/flush/state failure | 16 |
| outer-Job create/configuration failure | 16 |
| engine `CreateProcessW` failure | 12 |
| engine outer-Job assignment failure | 16 |
| engine `ResumeThread` non-one result or missing resume terminal | 16 |
| startup handshake/timer/ack/state failure | 16 |
| unexpected bootstrap, guard, or engine internal exception not already classified | 16 |
| journal create/write/flush/offset failure after engine start | 11 |
| target create/target-Job assignment/target resume failure or unknown | 12 |

The category is selected at the failing operation; later cleanup failure cannot
rewrite it except the already-specified guard deadline rule for an absent or
nonterminal engine result. Tests inject one failure at every row and require the
listed exit, zero Recorder stdout bytes, zero Recorder stderr bytes, target
nonexecution where applicable, and only the evidence permitted before that
failure point.

This zero-output guarantee begins only after the bootstrap's first statement
executes. Interpreter image loading, script opening/decoding, syntax failure,
or replacement of a trust-anchor byte that prevents execution of that first
statement is a launcher precondition outside Recorder control. Python or the OS
may emit bytes in that boundary case; Recorder records no fabricated class or
evidence and does not claim the controlled-output guarantee.

The `verify` command writes one UTF-8 JSON object followed by one LF to stdout.
It may write human diagnostics to stderr. It opens the fixed evidence members
of one absolute session directory read-only.

## 4. Windows byte and pipe preflight

The production Windows profile requires native 64-bit CPython 3.13 and checks:

```text
ctypes.sizeof(ctypes.c_void_p) == 8
ctypes.sizeof(ctypes.c_wchar) == 2
sys.maxsize == 0x7fffffffffffffff
IsWow64Process2(GetCurrentProcess()) succeeds
process_machine == IMAGE_FILE_MACHINE_UNKNOWN == 0x0000
native_machine in {IMAGE_FILE_MACHINE_AMD64=0x8664,
                   IMAGE_FILE_MACHINE_ARM64=0xaa64}
```

Any 32-bit/WOW64 process is unsupported and rejected. v1 never interprets an
x86 native structure layout. A missing `IsWow64Process2` entry point is also
rejected. Windows may report an x64 process on ARM64 with
`process_machine=IMAGE_FILE_MACHINE_UNKNOWN`; v1 does not use this call to
distinguish that case because the enforced 64-bit layouts below are identical.

The first Recorder application actions in both guard and engine, before any
Recorder read, write, or diagnostic, are:

```python
msvcrt.setmode(0, os.O_BINARY)
msvcrt.setmode(1, os.O_BINARY)
msvcrt.setmode(2, os.O_BINARY)
```

Preflight then:

1. obtains the three standard OS handles;
2. requires `GetFileType(handle) == FILE_TYPE_PIPE` for each;
3. uses documented `CompareObjectHandles` on all three pairs and rejects any
   pair that names the same underlying kernel object; absence/failure of any
   comparison is fail-closed;
4. calls `GetNamedPipeInfo` and requires byte-stream type, then calls
   `GetNamedPipeHandleStateW` and requires blocking byte-read mode; message-mode
   or nonblocking pipes are rejected;
5. uses `NtQueryObject(ObjectBasicInformation)` with the exact structure and
   access-mask predicates below to require read-only data access on stdin and
   write-only data access on stdout/stderr;
6. obtains `ObjectNameInformation` with the exact 64-bit `UNICODE_STRING`
   layout below and requires all three nonempty pipe-name byte strings to
   differ, which rejects opposite endpoints or separate handles of one named
   pipe. Returned names are never decoded for identity and never logged;
7. clears `HANDLE_FLAG_INHERIT` on all parent-owned handles;
8. creates dedicated inheritable duplicates only when constructing one child
   handle list; originals remain non-inheritable and each temporary duplicate
   is closed immediately after `CreateProcessW`;
9. rejects a console, disk file, character device, invalid handle, any
   standard-handle alias, bidirectional handle, shared pipe name, unsupported
   pipe mode, or failed identity/access check.

`ObjectBasicInformation` is numeric information class `0`.
`PUBLIC_OBJECT_BASIC_INFORMATION` is exactly 56 bytes on the supported ABI:

| Offset | Size | Field |
|---:|---:|---|
| 0 | 4 | `ULONG Attributes` |
| 4 | 4 | `ACCESS_MASK GrantedAccess` |
| 8 | 4 | `ULONG HandleCount` |
| 12 | 4 | `ULONG PointerCount` |
| 16 | 40 | `ULONG Reserved[10]` |

`ACCESS_MASK` is read as an unsigned 32-bit value. Direction constants and
predicates are exact:

```text
FILE_READ_DATA       = 0x00000001
FILE_WRITE_DATA      = 0x00000002
FILE_APPEND_DATA     = 0x00000004
READ_WRITE_DATA_MASK = 0x00000003
GENERIC_RIGHTS_MASK  = 0xf0000000
MAXIMUM_ALLOWED      = 0x02000000

stdin:
  (GrantedAccess & READ_WRITE_DATA_MASK) == FILE_READ_DATA
  (GrantedAccess & FILE_APPEND_DATA) == 0

stdout:
  (GrantedAccess & READ_WRITE_DATA_MASK) == FILE_WRITE_DATA

stderr:
  (GrantedAccess & READ_WRITE_DATA_MASK) == FILE_WRITE_DATA

all: (GrantedAccess & (GENERIC_RIGHTS_MASK | MAXIMUM_ALLOWED)) == 0
```

Metadata rights such as `SYNCHRONIZE`, `READ_CONTROL`, and attribute access do
not establish data direction and are permitted. Generic or maximum-allowed
bits, append-only data access without `FILE_WRITE_DATA`, missing required data
access, or both read/write data bits are ambiguous and rejected.
`FILE_APPEND_DATA` may accompany `FILE_WRITE_DATA` on a mapped generic-write
pipe handle and does not make that handle readable.

`ObjectNameInformation` is numeric information class `1`. On the only
supported 64-bit ABI its leading `UNICODE_STRING` is exactly:

| Offset | Size | Field |
|---:|---:|---|
| 0 | 2 | `USHORT Length` |
| 2 | 2 | `USHORT MaximumLength` |
| 4 | 4 | alignment padding, zeroed by the caller |
| 8 | 8 | `PWSTR Buffer` |

The header size is 16 bytes. The two lengths must be even,
`0 < Length <= MaximumLength`, and the `[Buffer, Buffer + Length)` range must
lie wholly inside the returned allocation without pointer overflow. Identity
comparison uses those exact `Length` bytes. The allocation is capped at
`65536` bytes; a larger required return length is rejected.

`NtQueryObject` is the sole native query in this preflight. `NTSTATUS` is
interpreted as signed 32-bit; only `STATUS_SUCCESS` accepts a populated result.
The size-discovery call may return
`STATUS_INFO_LENGTH_MISMATCH (0xc0000004)` and nothing else. Windows reserves
the right to remove this API, so a missing entry point, unsupported pointer
size, unexpected return size, invalid in-buffer pointer, unexpected access
mask, empty name, or query failure rejects before engine creation.

The engine relay path calls Win32 `ReadFile` and `WriteFile` directly. It does
not use `sys.stdin`, `sys.stdout`, `sys.stderr`, buffered Python file objects,
universal-newline translation, or text codecs. CR, LF, NUL, `0x1A`, and invalid
UTF-8 remain exact bytes.

## 5. Journal and supervision-sidecar creation

The requested session path must be absolute and absent. Every observed ancestor
must be a directory without a reparse-point attribute. These checks reduce
accidental escape but do not eliminate a same-user path race.

The guard generates `session_id` and `recorder_instance_id`, creates the
session directory once, creates and flushes `supervision.aegissup`, then
appends and flushes its `GUARD_STARTED` record before engine creation. The
sidecar follows
`SUPERVISION_SIDECAR_CONTRACT.md`. Failure to persist either item prevents
engine launch.

The guard and engine independently compute the protocol
`session_path_sha256` from the same exact Windows `session_path` identity.
The sidecar header and journal `SESSION_STARTED` retain that origin digest.
Later verification compares those evidence-carried values; it never hashes the
verifier host's current copied-directory path as origin identity.

The engine receives the two canonical UUIDs through its private canonical
command line. It creates `journal.aegisrec` inside that already-created
directory through the single production path:

```text
CreateFileW(
  desired_access = GENERIC_READ | GENERIC_WRITE,
  share_mode = 0,
  creation_disposition = CREATE_NEW,
  flags = FILE_ATTRIBUTE_NORMAL | FILE_FLAG_WRITE_THROUGH
)
```

The journal handle is non-inheritable and is never wrapped in a Python buffered
file object. Every committed record uses:

```text
verify current file offset
→ counted WriteFile loop for prefix + metadata + payload + digest + marker
→ verify resulting file offset
→ FlushFileBuffers
```

Any zero-byte write, short-write loop failure, offset mismatch, write error, or
flush error permanently poisons the journal. A successful `FlushFileBuffers`
only means the Windows API reported success. It is not a claim of hardware
power-loss durability.

`FILE_FLAG_NO_BUFFERING` is forbidden in v1 because its sector-alignment
requirements are not part of the journal format.

The guard never writes `journal.aegisrec`. The engine never writes
`supervision.aegissup`. A clean Windows verification requires both files and
their independently verified genesis/UUID binding.

## 6. Guard and engine launch

The trusted bootstrap enters the guard. The guard:

1. completes byte/pipe preflight;
2. calls `IsProcessInJob` for itself and fails preflight if it already belongs
   to any host Job Object; v1 has no breakaway or third-party Job profile;
3. creates an outer Job Object and sets kill-on-close without breakaway;
4. creates a shutdown event, target-ready event, target-ack event,
   resume-intent-ready event, resume-result event, manual-reset startup
   waitable timer, and a page-file-backed fixed-size handshake mapping; their
   guard-side handles are non-inheritable;
5. reuses the exact absolute trusted CPython `python.exe` identity validated by
   the bootstrap;
6. launches the engine with `CreateProcessW`, `CREATE_SUSPENDED`, and
   `EXTENDED_STARTUPINFO_PRESENT`;
7. assigns the suspended engine to the outer Job;
8. terminates the still-suspended engine on assignment failure;
9. resumes the engine only after assignment succeeds.

The guard also accepts only `ResumeThread(engine_primary_thread) == 1`. It
never drains an unexpected suspend count. `0xffffffff` is API failure; zero
means engine execution may already have occurred; a value greater than one
means the engine remains suspended after one decrement. Every non-one value
uses sidecar reason `ENGINE_RESUME_STATE_FAILURE`, requests outer-Job
containment, stores the exact return and applicable `GetLastError` in the
request record, and returns proxy class 16.

For both engine and target resume calls, `GetLastError` is captured immediately
after a `0xffffffff` return and before any other Win32 call. It is ignored for
every successful return.

The guard uses documented Win32 APIs through `ctypes`, plus only the explicitly
fail-closed `NtQueryObject` preflight above. Production code must not depend on
`_winapi`, `subprocess.Popen._handle`, or another private CPython API.

The guard creates temporary inheritable duplicates of the three parent
standard handles and the seven private objects. The engine handle list contains
only those ten duplicates. They are enumerated in one
`PROC_THREAD_ATTRIBUTE_HANDLE_LIST`; that attribute, rather than global process
handle enumeration, defines the child inheritance boundary. Guard originals
stay non-inheritable; the ten temporary duplicates are closed in the guard
immediately after process creation.

The exact engine command is:

```text
ABSOLUTE_TRUSTED_PYTHON_EXE -I -S -B -X utf8 ABSOLUTE_BOOTSTRAP_PY
--internal-engine <PRIVATE_FIXED_ARGUMENTS>
```

The engine current directory is the protected runtime root, never the candidate
repository or target cwd. `PYTHONPATH`, `PYTHONHOME`, `PYTHONUSERBASE`,
`PYTHONSTARTUP`, `PYTHONINSPECT`, and `PYTHONDONTWRITEBYTECODE` are removed from
the engine environment because command-line flags and bootstrap state, not
ambient variables, enforce isolation. Before journal creation, the engine
repeats exact protected-root enumeration, import-allowlist enforcement, and
manifest validation, and requires the guard-supplied expected manifest digest.
A candidate-local `aegis_recorder` package cannot affect module resolution.

After engine resume, the guard main thread remains the startup supervisor. A
separate daemon handshake worker waits for target-ready, validates mapping and
target handles, publishes immutable results in guard memory, and exits. It
never writes the sidecar or acknowledges the engine.

The main thread first waits failure-first on the shared timer, shutdown,
engine, and handshake-worker thread handle. A worker-handle win lets the main
thread persist `JOURNAL_BOUND`, publish state 3, and signal target-ack. The
main thread then waits failure-first on the same timer, shutdown, engine, and
resume-intent-ready. Worker completion/ack lets the engine persist resume
intent but never authorizes target execution. Only the guard main thread may
call `ResumeThread` on the duplicated target primary-thread handle. After that
call returns and its result is published, the main thread switches to the
runtime wait set, which replaces startup objects with the engine-to-guard
duplicate of the target process handle.

### Handshake wire contract

The page-file mapping is exactly 128 bytes. Every integer is unsigned
little-endian. Reserved bytes must remain zero.

| Offset | Size | Field |
|---:|---:|---|
| 0 | 8 | ASCII `AEGRDHS1` |
| 8 | 2 | major `1` |
| 10 | 2 | minor `0` |
| 12 | 4 | mapping size `128` |
| 16 | 32 | guard-generated random nonce |
| 48 | 4 | state |
| 52 | 4 | flags, v1 zero |
| 56 | 8 | engine PID |
| 64 | 8 | target PID |
| 72 | 8 | engine-local target process handle value |
| 80 | 32 | SHA-256 of exact journal-genesis bytes |
| 112 | 8 | engine-local target primary-thread handle value |
| 120 | 4 | `ResumeThread` return, initialized `0xffffffff` |
| 124 | 4 | `GetLastError`, initialized zero |

State values and transitions are:

```text
0 ZEROED          -> 1 GUARD_INITIALIZED
1 GUARD_INITIALIZED -> 2 TARGET_READY
2 TARGET_READY    -> 3 TARGET_ACKNOWLEDGED
3 TARGET_ACKNOWLEDGED -> 4 RESUME_INTENT_DURABLE
4 RESUME_INTENT_DURABLE -> 5 RESUME_CALL_RETURNED
```

No other transition is legal. In state 1, target PID and target handle are
and thread handles and journal-genesis hash are all zero; resume return is
`0xffffffff` and error is zero. In states 2 through 4, target PID, both handles,
and journal-genesis hash are nonzero while the initialized resume fields remain
unchanged. State 5 contains the exact call result; error is nonzero if and only
if return is `0xffffffff`. A handle value is the zero-extended Windows
`ULONG_PTR` represented in the 64-bit field.

The shutdown, target-ready, target-ack, resume-intent-ready, and resume-result
objects are manual-reset events, initially nonsignaled, and are never reset.
The startup timer is one manual-reset waitable-timer kernel object. The guard
and engine receive handles to that same object; neither process creates or
restarts a relative replacement timer. The guard initializes the fixed header,
nonce, engine PID, zero target/hash/handle fields, initialized resume fields,
and state 1 before resuming the engine. The nonce is also passed as 64 lowercase
hex command-line characters. All private child handle values are passed as
unsigned decimal without leading zeroes.

The engine verifies size, header, nonce, state, reserved bytes, and its own PID.
After committing and flushing journal sequence zero, the engine writes target
PID, process/thread handles, and journal-genesis hash, writes state 2 last,
then calls `SetEvent` on target-ready. The handshake worker waits for that
event before reading state 2. It duplicates both handles from the engine
process with non-inheritable requested access:

```text
target process: SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION
primary thread: SYNCHRONIZE | THREAD_QUERY_LIMITED_INFORMATION |
                THREAD_SUSPEND_RESUME
```

It requires `GetProcessId(process_handle)` and
`GetProcessIdOfThread(thread_handle)` to equal the declared target PID,
publishes the immutable validated handles/hash/PID result in guard memory, and
exits. `DUPLICATE_SAME_ACCESS` is not used. The worker never writes the
sidecar/mapping, cancels/re-arms the startup timer, signals an engine event, or
calls `ResumeThread`.

After a failure-first worker-handle win, the guard main thread revalidates state
2 against the immutable worker result, durably appends sidecar
`JOURNAL_BOUND`, writes state 3 last, and calls `SetEvent(target_ack)`. From
that call onward the completed worker has no live access to shared launch
objects.

The engine accepts target-ack only from its failure-first wait and state 3. It
starts all relay owners, appends/flushes `CHILD_SPAWNED`, appends/flushes
`CHILD_RESUME_ATTEMPT_STARTED`, writes state 4 last, and signals
resume-intent-ready. The guard main thread alone calls `ResumeThread` on its
validated duplicate. After the call returns, it writes the exact return/error,
writes state 5 last, and signals resume-result. The engine accepts that result
only from its failure-first wait and state 5, then appends the required journal
resume terminal. Event signal/wait boundaries are the publication boundaries
for the mapping.

The guard owns the mapping view, original events, original startup timer,
sidecar handle, outer Job, engine process handle, and duplicated target process
and primary-thread handles.
The engine owns only inherited private duplicates. It closes handshake-only
duplicates after a state-5 result or failure and retains the shutdown event only
for the runtime protocol. The target inherits none of them. On every exit, the
guard closes its objects only after recording the applicable sidecar terminal
state.

The mapping is not a journal or evidence authority. It is only a bounded launch
handshake. The durable resume attempt precedes the guard-main call; the durable
resume terminal independently binds the returned state-5 result.

### Startup deadline

Before resuming the engine, the guard arms the shared waitable timer once for
`120000` milliseconds. The main guard thread first calls
`WaitForMultipleObjects(
[startup_timer, shutdown, engine, handshake_worker_thread], ...)`. After a
successful worker result and main-thread binding/ack publication, it calls
`WaitForMultipleObjects(
[startup_timer, shutdown, engine, resume_intent_ready], ...)`. Every failure
object precedes the success object in both waits, so simultaneous observability
fails closed.

The engine first waits on `[startup_timer, shutdown, target_ack]`. After
publishing state 4 it waits on
`[startup_timer, shutdown, resume_result]`. Both are exact failure-first orders.
No phase restarts a 120-second relative duration.

The timer remains armed across worker validation, main-thread sidecar binding,
main-thread acknowledgement, and the engine's durable
`CHILD_RESUME_ATTEMPT_STARTED`. If an actor or its Windows persistence call
does not return, no later success is inferred; ordinary scheduling delay
remains covered by the same timer. Main-thread ack permits only durable
preparation. It never permits `ResumeThread`.

After a resume-intent-ready result, the main thread performs this exclusive
authorization protocol:

1. require mapping state 4, unchanged resume-result fields, and a validated
   target primary-thread handle; the worker thread is already signaled and has
   no remaining mapping, timer, sidecar, or target-handle access;
2. call `CancelWaitableTimer` and require success;
3. call `WaitForSingleObject(startup_timer, 0)` and require `WAIT_TIMEOUT`;
   `WAIT_OBJECT_0` proves the deadline had already won;
4. recheck mapping state 4 and call
   `ResumeThread(duplicated_target_primary_thread_handle)` exactly once;
5. capture `GetLastError` immediately when the return is `0xffffffff`;
6. if the return is not one, append/flush sidecar `TERMINATION_REQUESTED` with
   reason `TARGET_RESUME_STATE_FAILURE` and the exact return/error before any
   terminating Job call;
7. write the exact `DWORD` return and applicable `GetLastError`, write state 5
   last, and require `SetEvent(resume_result)` success.

Once cancellation returned and the zero-time check observed an unsignaled
timer, that timer cannot become signaled without a forbidden re-arm. If expiry
won the cancellation race, the manual-reset timer remains signaled and step 3
fails closed. The guard-main `ResumeThread` call itself is the authorization;
no worker or engine code can substitute for it. A nonreturning call is an
explicit kernel-call liveness boundary, not permission to infer a result.

A timer win, ready/ack protocol violation, engine exit, shutdown signal,
mapping failure, sidecar binding failure, cancel/check failure, or event failure
causes a durably sidecar-recorded outer-Job termination request, proxy class
16, and no target resume claim. On timer, shutdown, premature resume-result, or
invalid state, the engine requests containment and exits nonzero. Only a
state-5 return of one becomes `CHILD_RESUMED`; every other return follows the
failure rules below. Thus pre-ready, ready-to-ack, ack-to-durable-intent, and
intent-to-main-call delays consume the same budget. Late scheduling can create
only a conservative failure before the guard-main call.

On a startup failure the main guard never closes mapping/event handles while
the daemon handshake worker may still use them. After outer-Job termination
handling and the applicable sidecar terminal append, it calls
`TerminateProcess(GetCurrentProcess(), 16)`; self-termination does not run DLL
detach code that could deadlock on a worker-held lock, and process teardown
closes guard handles and threads together. If the sidecar was already poisoned,
there is no invented terminal evidence. Normal successful startup joins the
worker before ordinary handle cleanup.

If the target exits first, the guard starts an output-drain deadline but does
not set the fatal shutdown event. If the engine exits first, the guard
terminates the outer Job before returning.

Before `TerminateJobObject` or a termination-intended release of the
kill-on-close Job handle, the guard appends and flushes sidecar
`TERMINATION_REQUESTED`. A process death or kernel stall after that append
therefore remains persistently distinguishable from `NO_TERMINATION_REQUEST`.
If the API returns, the guard appends `TERMINATION_CALL_RETURNED` with its
actual Boolean result and `GetLastError` when false.

After the call returns, the guard starts
`RECLAMATION_CONFIRMATION_MS = 2000`. Within that controlled-wait bound it
requires the engine process handle to be signaled, the target process handle
to be signaled when one exists, and a successful Job query to report active
process count zero. Only then does it append and flush
`RECLAMATION_CONFIRMED`.

A required query error or expiry appends and flushes
`RECLAMATION_UNCONFIRMED` before the guard releases the kill-on-close Job
handle. A guard death, sidecar partial tail, or nonreturning call after a valid
termination-request record leaves no legal confirmed terminal; independent
verification also classifies that state as reclamation unconfirmed. The guard
returns proxy class 16, never polls indefinitely, and never equates a
successful termination call with proven process disappearance.

On a path with no termination request, normal guard exit requires signaled
known process handles and a successful Job query with active count zero, then
appends and flushes `NORMAL_SUPERVISION_COMPLETED` before closing the Job
handle. Missing that terminal prevents a Windows `PASS`.

v1 does not claim an upper bound for the duration of `TerminateJobObject`,
`CloseHandle`, or another Windows kernel call itself. A nonreturning kernel API
is outside the Recorder-controlled liveness boundary. The bounded claim begins
only after the call returns. An external black-box test may kill a deliberately
blocked guard and must find a durable request without a confirmed reclamation
record and no clean combined verification claim.

The runtime shutdown/drain deadline starts after either a fatal shutdown event
or target-process termination. It is distinct from the startup deadline. v1
makes no claim that an arbitrary engine defect which occurs after a successful
handshake, never signals, and leaves a live target can be detected within a
fixed time.

## 7. Target launch and handle inheritance

The target command must contain an absolute regular `.exe` path. `.cmd`, `.bat`,
`.ps1`, implicit PATH execution, shell invocation, and npm shims are rejected.
`lpApplicationName` is the resolved absolute executable. `shell=False` is a
semantic requirement even though production uses `CreateProcessW` directly.
`lpCommandLine` is the unique mutable UTF-16LE serialization from section 2;
joining argv, shell quoting, calling `subprocess.list2cmdline` and passing its
Python string result, or any immutable Python string buffer is forbidden. The
direct code-unit implementation must nevertheless match that function's
frozen algorithm and vectors exactly.

The engine creates three anonymous pipe pairs. It keeps every engine endpoint
non-inheritable and creates one temporary inheritable duplicate for each target
endpoint. The one target creation call uses:

```text
CreateProcessW
  CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT
  bInheritHandles = TRUE
  STARTUPINFOEXW / PROC_THREAD_ATTRIBUTE_HANDLE_LIST
```

The handle list contains exactly the three target-side duplicates:

- target stdin read;
- target stdout write;
- target stderr write.

Journal, Job, process, thread, guard-control, event, and engine pipe endpoints
must not appear in the list. All three target-side duplicates are closed in the
engine immediately after `CreateProcessW`; the relay-owned engine endpoints
remain non-inheritable.

Target launch order:

1. independently serialize the requested target argv and append/flush
   `CHILD_SPAWN_REQUESTED` with exact `target_lp_application_name`,
   `target_lp_command_line_utf16le_hex` including the sole final NUL,
   `target_lp_command_line_code_unit_count`, and the domain-separated
   `target_lp_command_line_sha256`;
2. create the target suspended with the exact handle list;
3. assign it to the target Job Object;
4. publish target process/thread handles and receive guard-main handshake
   acknowledgement after worker validation;
5. start relay owners while the target remains suspended;
6. append and flush `CHILD_SPAWNED`;
7. append and flush `CHILD_RESUME_ATTEMPT_STARTED`;
8. publish durable resume intent to the guard main thread;
9. let the guard main thread call `ResumeThread` exactly once;
10. consume the exact state-5 return/error;
11. append and flush `CHILD_RESUMED` or `CHILD_RESUME_FAILED`.

Any failure before step 9 terminates the suspended target; its primary thread
has never executed. A guard crash or journal failure after the resume-attempt
record but before its terminal record produces an unknown start outcome and
cannot be reported as a clean session.

The `CREATE_SUSPENDED` result is the only code path that may increment the
target primary thread's suspend count. Recorder never calls `SuspendThread`,
and no debugger-attachment profile is supported. The guard-main
`ResumeThread` returns the previous `DWORD` suspend count:

```text
return == 1:
  the one Recorder-owned suspension changed from 1 to 0;
  append CHILD_RESUMED.

return == 0xffffffff:
  API failure; capture GetLastError as WIN32:<decimal>;
  append CHILD_RESUME_FAILED and terminate containment.

return == 0:
  the thread was already runnable; execution may already have occurred;
  append CHILD_RESUME_FAILED with
  POLICY:RESUME_PREVIOUS_COUNT_0, classify start outcome unsafe, and
  terminate containment.

return > 1:
  the call removed one suspension but at least one remains;
  append CHILD_RESUME_FAILED with
  POLICY:RESUME_PREVIOUS_COUNT_<unsigned-decimal>, and terminate containment.
```

Only return value `1` is success. Recorder never calls `ResumeThread` again to
"drain" an unexpected count because that could remove a debugger/external
suspension and execute code under an unproved state. Return zero cannot support
the statement that target code never executed. Return greater than one proves
the primary thread remained suspended immediately after this call, but
Recorder still makes no clean resume claim. An uncommitted terminal after any
return remains `RESUME_OUTCOME_UNKNOWN` under the journal protocol.

Because the engine is already in the outer Job, the target first inherits the
outer Job association. Assigning the suspended target to the target Job creates
the nested containment relation. Unsupported nested-job or assignment behavior
fails before resume.

## 8. Threads, handles, and locks

Long-lived engine threads are:

- supervisor/main;
- client-to-server relay;
- server-to-client relay;
- target-stderr relay.

Each relay owns one source role and one destination role. Thread pools are
forbidden. At thread start, the relay calls `DuplicateHandle` on the
`GetCurrentThread()` pseudo-handle and publishes the resulting real,
non-inheritable thread handle to the supervisor. A numeric native thread ID is
never reopened later because IDs can be reused.

Each source/destination OS handle used by relay I/O has one relay owner. The
supervisor may cancel I/O through the real thread handle but must not close or
reuse a relay-owned I/O handle. The relay closes its own handles in its final
path after `ReadFile`/`WriteFile` has returned. Peer-end closure or Job
termination is used to help unblock I/O; the outer guard remains the fallback
when cancellation cannot complete.

There is no lock order because the two locks may never be nested:

- `journal_lock` protects sequence, previous digest, append timestamps,
  current expected offset, `WriteFile`, and `FlushFileBuffers`;
- `fatal_lock` protects only the immutable first-fatal cause and stop-event
  transition.

No lock is held while reading or writing a pipe, waiting for a process, waiting
for a guard acknowledgement, joining a thread, cancelling I/O, signalling a
Job, or terminating a process.

On journal failure, code marks the journal poisoned while holding
`journal_lock`, releases that lock, then acquires `fatal_lock` to publish the
fatal condition. Fatal publication never tries to append another journal
record. This eliminates the journal-to-fatal reverse edge.

Concurrent destination writes already begun when the journal becomes poisoned
cannot be withdrawn. Their outcomes are unknown unless a durable terminal
record already exists.

## 9. Relay operation

For each observed unit, one relay performs:

1. source read;
2. capture source timestamp and stream offset;
3. append and flush the observation;
4. append and flush `FORWARD_ATTEMPT_STARTED`;
5. write exact bytes using a counted `WriteFile` loop;
6. append and flush success or failure.

The write loop retries only documented interruption states. It counts every
accepted byte returned by a successful call and never restarts the observation.
A `FORWARD_FAILED` terminal is legal only when the platform contract proves the
exact total accepted across every call. A successful call with zero progress
for a nonempty remainder is a known failure. POSIX errors use only explicitly
documented zero-transfer cases.

Windows `WriteFile(FALSE)` does not establish how many bytes crossed the pipe
boundary during an interrupted or cancelled call. The engine therefore never
turns that result into `FORWARD_FAILED`. If the journal remains healthy it
appends `FORWARD_OUTCOME_UNKNOWN` with the sum of earlier successful-call counts
as `accepted_byte_lower_bound`, then enters fatal shutdown. If that append also
fails, the durable attempt remains without an outcome record. Both forms are
`SEND_OUTCOME_UNKNOWN`, are never replayed, and forbid `SESSION_ENDED`.

One stream never starts observation `n+1` until observation `n` has a durable
terminal result or the session enters fatal shutdown.

## 10. Target exit, fatal shutdown, cancellation, and deadline

The first fatal condition atomically fixes one fatal cause. Later failures may
be retained as in-memory diagnostics but cannot replace the cause or determine
a different exit class.

### Normal target exit

Target-process exit is not fatal shutdown. The engine records `CHILD_EXITED`
when the journal remains usable and enters `DRAINING_OUTPUT`:

1. stop and cancel only the client-to-server relay;
2. let that relay retain any buffered partial frame and record its non-clean
   source terminal;
3. do not cancel server-to-client or stderr reads;
4. continue both output relays until their target pipe peers close and
   `STREAM_EOF` is durable;
5. close destinations through their normal close attempt/terminal lifecycle;
6. finish the session only after output EOF, relay exit, and recomputed state.

Parent stdin that remains open at target exit produces `SOURCE_CANCELLED` or an
incomplete-frame cancellation. It always makes `transport_complete=false` and
cannot be relabelled as clean merely because its current buffer is empty.

The guard independently starts a ten-second drain deadline when it observes
target exit. If output EOF and engine shutdown do not complete by that
deadline, the guard terminates the outer Job. The journal has no synthesized
clean end. A repeated fast-exit target which writes its final frame immediately
before exit is a mandatory scheduling-stress test.

### Fatal shutdown

For a fatal condition while the journal remains usable, the engine:

1. durably records any protocol-required close/signal attempts that can still
   be recorded;
2. sets the guard-owned shutdown event before waiting on any relay;
3. stops scheduling all new observations;
4. calls `CancelSynchronousIo` with each relay's real thread handle;
5. requests or forces target Job termination;
6. waits up to five seconds for target and relays;
7. calls `TerminateJobObject` if the target Job remains active;
8. lets each relay close its own I/O handles after its pending call returns.

The supervisor never closes a handle while a relay may be executing
`ReadFile`/`WriteFile` on it.

If the journal is poisoned, step 1 is impossible. The engine uses the protocol's
emergency-containment exception: signal the guard, cancel relays, terminate the
target Job, emit no further evidence, and forbid `SESSION_ENDED`.

`CancelSynchronousIo` is an attempt, not proof that cancellation completed.
`ERROR_NOT_FOUND` means no cancellable operation was found. Other errors are
retained when the journal is still usable. The engine does not wait forever on
a relay that ignores or cannot complete cancellation.

At ten seconds after either guard-observed runtime trigger, a still-running
engine causes the guard to flush sidecar `TERMINATION_REQUESTED` and call
`TerminateJobObject` on the outer Job. The guard then applies the two-second
bounded reclamation confirmation and sidecar terminal protocol above. No
`SESSION_ENDED` is synthesized. The Verifier reports supervision failure or
incomplete evidence; disappearance is claimed only when the sidecar records all
required independent observations.

POSIX keeps target exit and fatal shutdown distinct, drains output to EOF on
normal exit, and uses process-group `SIGTERM`/`SIGKILL` only on fatal shutdown
or drain timeout. POSIX has no independent guard and therefore no equivalent
engine hard deadline.

## 11. Shutdown outcomes

| Condition | Required durable state | Clean | Transport complete | Proxy class |
|---|---|---:|---:|---:|
| target rc 0; all sources EOF; all observations succeeded | `SESSION_ENDED.clean_shutdown=true`, `transport_complete=true`, `child_return_code=0` | yes | yes | 0 |
| target nonzero; all sources EOF; all observations terminal | `SESSION_ENDED.clean_shutdown=false`; recomputed transport field | no | yes if no partial/unknown | 15 |
| observation without attempt | no successful session end | no | no | 14 |
| attempt without outcome or `FORWARD_OUTCOME_UNKNOWN` | unresolved outcome | no | no | 14 |
| failed or partial forward | failed terminal | no | no | 14 |
| incomplete/oversized frame | source terminal | no | no | 13 |
| journal write/flush failure | journal poisoned; clean end absent | no | unknown | 11 |
| target containment failure before resume | spawn/resume failure when durable | no | no target transport | 12 |
| resume attempt without terminal | start outcome unknown | no | no | 12 |
| relay survives engine grace period | guard trigger; clean end absent | no | no | 16 |
| guard kills outer Job; reclamation confirmed | sidecar request + confirmed terminal; clean journal end absent | no | no | 16 |
| guard requests termination; reclamation unconfirmed | sidecar request without confirmed terminal; clean journal end absent | no | no | 16 |

Parent stdin still open after target exit is cancelled by the engine. It is not
a client EOF and always makes transport incomplete, including when its current
frame buffer is empty.

## 12. Stable proxy exit classes

```text
0   CLEAN
10  PREFLIGHT_FAILED
11  JOURNAL_FAILED
12  SPAWN_OR_CONTAINMENT_FAILED
13  FRAMING_FAILED
14  TRANSPORT_FAILED_OR_UNKNOWN
15  CHILD_NONZERO
16  SUPERVISION_FAILED
64  USAGE_ERROR
```

The first fatal cause determines the engine result. A guard deadline overrides
an absent or nonterminal engine result with class 16. No exit class asserts
external authority.

## 13. Assurance boundary

The Windows mechanisms cannot prove:

- that the same user did not replace the session parent path;
- that an administrator did not alter process or storage state;
- that the storage controller physically persisted bytes;
- that a complete journal/sidecar pair was not replaced and rehashed later;
- that a process created by an external service belongs to these Job Objects.

Every result therefore retains:

```text
assurance_level = LOCAL_TRANSPORT_INTEGRITY
authority_verified = false
release_authority_eligible = false
```
