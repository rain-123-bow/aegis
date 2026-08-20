# ADR-0003: Deploy an exact Recorder protected runtime

## Status

Proposed. Acceptance requires the independent Recorder plan reviewer to return
zero P0/P1 findings.

## Date

2026-07-28

Amended 2026-07-29 after the Win32 root-relative rename probe failed and the
native `NtSetInformationFile` profile succeeded.

## Context

The Windows production bootstrap verifies its own runtime before importing
Recorder code. That verification needs one finite expected member set and one
deploy path that does not execute candidate code.

`pip install --target` does not provide that contract. Installer metadata,
scripts, bytecode, cache directories, and later import-time bytecode can make
the installed tree differ from the wheel. Ignoring those files would leave an
undefined import and shadowing surface.

A repository-shipped Python deployer cannot establish its own authority by
hashing itself or by accepting a hash supplied by the same repository. A
path-based hash followed by a Python launch also permits replacement between
the hash and the interpreter's script open. Publication by pathname has the
same identity gap.

Ordinary wheel installation remains necessary for package compatibility, but
it is a different goal from constructing the production trust anchor.

## Decision

The Recorder-delivered V1 protected-runtime deployer supports only 64-bit
Windows on a native fixed-drive NTFS volume. Linux/WSL2 validation relies on a
distinct operator-provided native deployment adapter and launcher selected by
an external trust slot and fixed-grammar `AegisRecorderPosixApproval.v1`
record. They require a closed-ABI static `ET_EXEC` approval-bound adapter whose
page-rounded `PT_LOAD` mappings cannot overlap,
  the exact CPython 3.12.3 interpreter digest/build in a direct-`P` layout, one
  externally approved 15-byte `python3.12._pth`, curated stdlib/dynload roots,
  and other root-owned/runtime-nonwritable trust objects, a
  nonzero-UID/nonzero-GID launcher with no supplementary groups, no
capabilities, and `no_new_privs`, bound to approved user/mount namespace
identities, native ext4 proven from the held FD by `statx` mount ID, matching
`/proc/self/mountinfo` type, and `fstatfs` magic, `openat2` no-symlink
resolution, exact adapter/runtime pre/post-exec descriptor tables, normalized
  signal state, pre-exec rejection of every venv/build/competing-`._pth`
  override, `execveat` of held executable objects, a fixed single-root initial
  `sys.path`, fixed procfd bootstrap, retained-FD stdlib/runtime loading after
  one explicitly external hash-seed prerequisite plus complete package-parent, explicit
`PRELOADED`/`SEED`/`LATE`, one-to-one preloaded-`encodings`, and disjoint
remaining finder-name checks,
distinct report-channel exit 74, and
`renameat2(RENAME_NOREPLACE)` publication with post-publication inode/member/
parent-fsync checks. Recorder ships only the conformance harness and cannot
select the slot/record or self-authorize the adapter. `/mnt/c`, 9p/DrvFS,
  unsupported Linux, non-Linux POSIX, any other CPython patch/build, and
  CPython 3.13 have no fallback.

The Linux getpath file is a deliberate pre-bootstrap pathname prerequisite.
The external launcher authenticates it immediately before exec; CPython reads
it by pathname; the bootstrap reopens it no-follow, verifies and retains it
after entry. This detects only drift still present at reopen and cannot turn
the earlier read into a held-object read. Root/operator replacement in that
interval, including change-and-restore ABA before reopen, remains locally
indistinguishable and outside Recorder authority.

Linux `renameat2` still names its source relative to a parent; the retained
staging directory FD detects substitution before a success report but cannot
prevent a same-UID transient source race. Linux remains a validation profile
with that explicit boundary and cannot acquire Windows production or release
authority.

`recorder/tools/deploy_protected_runtime.py` is reviewed source, not a trust
root. An operator-controlled launcher selects a production copy outside the
candidate repository, wheel, protected root, final-root parent, and cwd.
Expected interpreter and deployer hashes come from an approved record outside
candidate-controlled inputs. The launcher opens the interpreter, deployer, and
every ancestor by native relative handle; the two files exclude write/delete
sharing and ancestors exclude delete sharing. It hashes the held file handles
and retains them until child exit. The external record also binds the
interpreter-root identity and absence of `python313.zip`. The candidate cannot
write or replace the deployer, trusted interpreter/stdlib/dynamic-load tree, or
their ancestors.

The launcher and approved-hash root are operator-provided external
prerequisites, not Recorder deliverables. Recorder provides the contract and an
independent conformance harness that tests observable launch behavior but
cannot create the authority it tests. If no conforming external launcher is
provisioned, deployment is unavailable. There is no repository-owned fallback.

The initial Windows proxy uses a second, distinct operator-controlled launcher.
Its external slot binds the approved interpreter and bootstrap hashes and
identities. The launcher opens every native component no-reparse, excludes
write/delete replacement, retains file and ancestor handles through guard
exit, and starts the guard with exactly three dedicated inheritable
standard-handle duplicates in its handle list. Recorder provides only the
observable conformance harness. Without this launcher, proxy execution is
unavailable; bootstrap self-checks cannot retroactively authorize bytes that
already executed.

The sole launch argv is:

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

Options are fixed-order and nonrepeatable. A direct `CreateProcessW` call uses
the exact interpreter as `lpApplicationName`, the canonical full command line,
the named operator-protected control directory as cwd, and a Unicode
environment containing only exact `SystemRoot` and `WINDIR` entries for the
trusted Windows root. `STARTF_USESTDHANDLES` binds a read-only `NUL`,
deploy-report child pipe, and distinct stderr child pipe to the three standard
handle fields. Exactly three dedicated inheritable duplicates appear in
`PROC_THREAD_ATTRIBUTE_HANDLE_LIST`, `bInheritHandles=TRUE`, and every original,
parent-side, and ambient handle remains non-inheritable. No PATH lookup, shell,
site, user profile, virtual environment, or `PYTHON*` state participates.

The deployer's first statement enters a `BaseException` barrier. Before any
non-preloaded import, the frozen Windows CPython 3.13.13 profile must expose
exactly `[interpreter_root\python313.zip, DLLs, Lib, interpreter_root]` in
`sys.path`; the externally bound ZIP candidate must be absent. The deployer
validates the preloaded import machinery and `encodings` origin, performs the
sole permitted in-place narrowing to held `[DLLs, Lib]`, and installs its
pre-execution provenance guard. It then uses guarded imports to validate exact
cwd/raw argv, reopen and hash its source and interpreter through retained
native component handles, and compare the externally supplied expected values.
The self-hash detects drift; it does not self-authorize.

The guarded path permits only built-in/frozen origins, regular non-reparse
`.py` files under the held trusted stdlib root, and regular non-reparse `.pyd`
files under the held trusted dynamic-load root. Preloaded and later modules
must satisfy the same provenance rules; zip, namespace, site, cwd, candidate,
wheel, protected-root, and every later path/finder/cache mutation are rejected.

Every deployment path uses the exact uppercase-drive grammar in
`SUPERVISOR_CONTRACT.md`. `GetDriveTypeW` must report `DRIVE_FIXED` and
`GetVolumeInformationByHandleW` must report NTFS. For every used drive, both the
external launcher and deployer require the canonical volume-GUID name and exact
equality between the first current `QueryDosDeviceW` mappings for `X:` and the
stripped volume-GUID name. The launcher checks once before process creation and
retains its handles. The deployer checks during preflight and alone repeats its
own comparison immediately before publication. No ready-ack channel or
post-launch launcher recheck exists. Failure, ambiguity, inequality, or
deployer-observed drift rejects SUBST and other DOS-device directory mappings;
an unobserved change-and-restore remains outside the claim and cannot retarget
the retained publication handles. Each component is opened relative to a
retained native volume/parent handle with `NtCreateFile`,
`OBJ_DONT_REPARSE`, and `FILE_OPEN_REPARSE_POINT`. Attribute, tag, spelling,
volume, and `FILE_ID_INFO` checks use those handles. UNC, device, extended,
relative, reparse, link,
mounted-volume-transition, case-alias, and alternate-data-stream paths fail
closed.

Before staging exists, the deployer preflights 64-bit
`sizeof(FILE_RENAME_INFORMATION)==24`,
`FILE_RENAME_INFORMATION`
`offsetof(ReplaceIfExists/RootDirectory/FileNameLength/FileName)=0/8/16/20`,
two-byte `WCHAR`, 16-byte `IO_STATUS_BLOCK`,
`FileRenameInformation == 10`, the `ntdll!NtSetInformationFile` and
`NtWaitForSingleObject` exports, a
reviewed Windows build/profile with real-host retained-parent
rename/collision conformance evidence, fixed NTFS, and required access/share
predicates. It then independently verifies the complete
expected-hash wheel and extracts only:

```text
aegis_recorder_bootstrap.py
aegis_recorder/code_manifest.v1.json
every regular runtime file listed by code_manifest.v1.json
```

It creates a cryptographically unpredictable single-component staging
directory relative to the held final-parent handle, immediately records its
`FILE_ID_INFO`, and retains a `DELETE|SYNCHRONIZE`-capable synchronous staging
handle. Every member is
create-new, size/hash checked while writing, `FlushFileBuffers`ed, closed,
reopened through held directories, reread, and included in an exact recursive
enumeration. The creation identity is rechecked before publication. Links,
reparse points, devices, case collisions, extras, `.dist-info`, `Scripts`,
`.pyc`, and `__pycache__` fail.

After all member-file handles close, publication is exactly:

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

The checked allocation is zero-filled and has exactly that
`max(24,20+FileNameLength)` size. The non-NUL filename starts at offset 20;
zero tail bytes satisfy the minimum native structure size and are excluded
from `FileNameLength`. The final name is one component.
`ReplaceIfExists=FALSE` forbids replacement. Matching `STATUS_SUCCESS` from
the call and `IO_STATUS_BLOCK` is the namespace publication point, not terminal
deployment success. `STATUS_PENDING` waits on the held staging handle and uses
only the final IOSB after a successful wait. The wait uses a non-null,
ceiling-rounded negative relative 100-nanosecond `LARGE_INTEGER`; zero budget
does not wait. Only exact success, collision, and the three frozen unsupported
statuses have known meanings. Every other 32-bit value, timeout, wait failure,
still-pending IOSB, or call/IOSB mismatch returns
`PUBLICATION_OUTCOME_UNKNOWN`; it makes neither a published nor an unpublished
claim and performs no path-based inference, retry, cleanup, or rollback. The
full exhaustive NTSTATUS/deadline matrix is frozen in
`IMPLEMENTATION_PLAN_FINAL.md`. On definite success, the deployer keeps the
staging handle open,
reopens the final component relative to the held parent, and compares the
pre-rename staging, post-rename staging, and final-handle `FILE_ID_INFO` volume
serial plus all 128 FileId bits. It then revalidates exact final membership.
Only a complete match returns success. A post-publication mismatch returns
`PUBLISHED_IDENTITY_UNCONFIRMED` with
`publication_state=PUBLISHED`; it does not roll back or claim success. Reports
use the tri-state `NOT_PUBLISHED`, `PUBLICATION_OUTCOME_UNKNOWN`, or
`PUBLISHED` value in `publication_state`; a boolean cannot represent this
boundary.
`SetFileInformationByHandle`, a null `RootDirectory`, and pathname rename are
forbidden.

After staging creation, every controlled healthy-channel terminal report
includes the original staging path as exact UTF-16LE lowercase hex and its
volume/FileId. Stdout is one LF-terminated restricted-canonical-JSON ASCII
object under `AegisRecorderProtectedRuntimeDeploymentReport.v1`; stderr is
empty. Exit 0 is only `DEPLOYED`, 64 is only invalid invocation, 1 covers
controlled rejection, definite deployment/identity failure, and unknown
publication outcome; an internal failure with a healthy channel emits its
canonical row at exit 70. Report-channel loss
instead has no report object: exit is 74, stderr is empty, and the external
launcher preserves the exact observed stdout prefix, including an empty or
complete prefix, without interpreting it as a deployment result. Exit 74 is
reserved for this state; exit 70 is accepted only with one complete canonical
row whose embedded exit code is 70.

Each branch preselects its intended success or failure row before output.
One blocking binary unbuffered counted writer emits its precomputed ASCII-plus-
LF bytes, advances only by acknowledged positive progress, and performs one
terminal close. Zero/invalid progress, write error, or terminal-close failure
preserves the exact acknowledged prefix and uses a non-finalizing exit 74.
Healthy close uses the fixed intended exit path. Python text translation,
stream finalization, retry, stderr fallback, and exit-code rewrite to 120 are
outside the mechanism.

No failure recursively deletes, renames, repairs, quarantines, or reuses a
staging tree. A foreign final-name occupant is neither replaced nor deleted.
Operator policy owns quarantine from the reported path and identity.

Production launches CPython with:

```text
-I -S -B -X utf8
```

The bootstrap also sets and confirms `sys.dont_write_bytecode` before Recorder
imports. Every guard and engine launch rechecks exact recursive membership.
Recorder does not claim filesystem immutability. Two sequential clean launches,
with no external mutation between them, must independently observe identical
name/type/size/hash snapshots before import. No claim covers bytes after that
check or an actor able to replace them.

Normal pip installation and console/module checks remain release tests. Their
site-packages, dist-info, and generated launchers never become the Windows
production protected root.

## Alternatives considered

### Use `pip install --target` and scan the entire target

Rejected. The resulting member set contains installer-derived state and may
gain import-derived bytecode after a successful first launch.

### Use `pip install --target --no-compile`

Rejected as the production mechanism. It suppresses initial bytecode but does
not define all installer metadata, scripts, later runtime writes, or behavior
across pip versions.

### Ignore dist-info, scripts, and cache paths during bootstrap verification

Rejected. An ignored subtree is an unreviewed mutation and import-shadowing
surface. Exact absence is simpler to test and stronger.

### Import directly from the wheel

Rejected. It introduces zip-import behavior into the production loader,
conflicts with the regular-file/reparse contract, and expands the bootstrap
verification surface.

### Let the deployer verify a hash supplied by itself or the repository

Rejected. Matching candidate-controlled bytes to a candidate-controlled value
proves consistency, not authority. The expected value and held-file comparison
must come from the external operator launcher.

### Hash a path, close it, then launch or rename by path

Rejected. Closing the handle restores a replacement window. Trust selection and
publication retain component/file handles through process exit or final
identity confirmation.

### Let CPython discover its prefix from ZIP, `os.py`, or ambient landmarks

Rejected for Linux validation. CPython searches venv, `._pth`, build, ancestor
ZIP, stdlib, and dynload landmarks before the bootstrap can reject an
unexpected source. The exact one-line approved `._pth` fixes the initial path
to one stdlib root and removes dynload/ZIP from the pre-entry import surface.

### Publish with `MoveFileExW`

Rejected. The pathname API does not bind the source and parent objects already
validated. Native `NtSetInformationFile(FileRenameInformation=10)` binds the
held source handle, held parent handle, single final component, and explicit
no-replace value.

## Consequences

- The repository gains a separately tested production deployer.
- Production also needs an independently controlled launcher and expected-hash
  record; the repository cannot manufacture this authority. Recorder ships a
  conformance harness, not the launcher.
- The protected runtime is not a conventional Python installation and has no
  generated console script; the operator launches the absolute bootstrap.
- Linux validation is pinned to the reviewed CPython 3.12.3 interpreter hash,
  build constants, direct-`P` layout, and exact getpath bytes. A patch/build
  change requires a new profile review.
- Wheel/pip installability remains independently tested.
- Deployment is limited to 64-bit Windows fixed-drive NTFS and fails before
  staging when the native handle/layout profile is unavailable.
- A post-publication identity failure can leave a final namespace object while
  correctly returning failure; operators must use the reported FileId before
  quarantine.
- Failed staging trees may remain for explicit operator quarantine; the
  deployer never trades cleanup convenience for a path-race deletion risk.
- `-B` is required because CPython documents that it prevents import-time
  `.pyc` writes; `-I` isolates environment/user paths and `-S` disables
  `site` path mutation:
  https://docs.python.org/3.13/using/cmdline.html.
- The deployer and manifest establish local code-byte identity only. Same-user
  replacement after publication remains outside external-authority claims.
- Native `FILE_RENAME_INFORMATION`, `RootDirectory`, and no-replace semantics:
  https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/ns-ntifs-_file_rename_information
- `FILE_ID_INFO`:
  https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info
- Fixed-drive and filesystem preflight:
  https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getdrivetypew
  and
  https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getvolumeinformationbyhandlew.

These URLs are informative provenance, not incorporated normative content.
The exact accepted behavior is the decision text above plus frozen tests;
changes at a live URL cannot modify this ADR.
