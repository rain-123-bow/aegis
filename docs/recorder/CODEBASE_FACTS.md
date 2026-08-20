# Recorder codebase facts

Status: `READ_ONLY_SNAPSHOT_FOR_PLAN_REREVIEW_11`

Observed at: `2026-07-28T12:56:30.6439236Z`

Repository: `C:\code\aegis-20260727`

These are current checkout facts, not implementation claims. The checkout is
dirty and concurrent agents are editing other files, so implementation must
repeat this inventory before writing code.

## 1. Git identity

Commands:

```text
git branch --show-current
git rev-parse HEAD
git describe --tags --always --dirty
```

Observed:

```text
branch = v0.1.2-alpha-langgraph-reset
HEAD = 1933fab4fd042f9bb884274c87443d1cb618a859
describe = 1933fab-dirty
```

`pyproject.toml`, `docs/recorder/`, and
`schemas/aegis/v2/recorder_verification_report.v1.schema.json` are currently
untracked. Existing source and test files also contain unrelated modifications.
No Recorder implementation file exists.

## 2. Root package declaration

File:

```text
C:\code\aegis-20260727\pyproject.toml
SHA-256 = 57f50782f883b13da2a0bad6ea60af06f4bbed05b08bb2d367af2d287be79fe3
```

Declared root distribution:

```text
name = aegis-quality-kernel
version = 0.2.0a0
requires-python = >=3.11,<3.14
build-backend = setuptools.build_meta
build requirement = setuptools==83.0.0
console script = aegis-v2 -> aegis.cli:main
```

Declared runtime requirements:

```text
jsonschema[format-nongpl]==4.26.0
langgraph==1.2.9
langgraph-checkpoint-sqlite==3.1.0
rfc8785==0.1.4
```

Declared package discovery includes only `src/aegis*`. Current filesystem
checks:

```text
src/aegis/ = absent
src/aegis/cli.py = absent
recorder/ = absent
```

Isolated interpreter check:

```text
python -I -c "import importlib.util; ..."
{"aegis": false, "aegis_recorder": false}
exit = 0
```

Therefore the root `aegis-v2` entry is declared but has no matching source
module in this checkout. Recorder packaging must not reuse or claim validation
of that root entry.

## 3. Current source tree

Production-like Python files under `src/`:

```text
src/langgraph_contract.py
src/main.py
src/xxhash.py
src/reasoning_ledger/__init__.py
src/reasoning_ledger/__main__.py
src/reasoning_ledger/cli.py
src/reasoning_ledger/context_pack.py
src/reasoning_ledger/embedding.py
src/reasoning_ledger/models.py
src/reasoning_ledger/project.py
src/reasoning_ledger/schema.py
src/reasoning_ledger/store.py
```

`src/aegis_quality_kernel.egg-info/` exists but is ignored by `.gitignore`.
It is generated local state and is not a source or version authority.

No file currently provides:

```text
aegis_recorder
aegis-recorder
Recorder journal Writer
Recorder Verifier
Recorder proxy
Recorder PEP 517 backend
```

## 4. Current tests

Top-level test files:

```text
test/test.py
test/test_langgraph_contract.py
test/test_reasoning_ledger.py
```

The root `pyproject.toml` declares:

```text
testpaths = ["test/phase0a", "test/phase0b"]
```

Neither declared directory currently exists. Command:

```text
python -m pytest --collect-only -q
```

Observed:

```text
exit = 0
collected = 136
warning = No files were found in testpaths; pytest searched recursively
```

The 136 cases include `evaluation/aegis_v2/**` plus current top-level tests.
This fallback collection is not a Recorder test gate. The standalone Recorder
must have an explicit standard-library `unittest` discovery command rooted at
`recorder/tests`, and the root regression command must name its intended
paths rather than rely on fallback discovery.

## 5. Current Recorder schema

File:

```text
schemas/aegis/v2/recorder_verification_report.v1.schema.json
SHA-256 = a3594f09042e5304fd3b37d3f7476f3e9e3a7e127b675d716f7f2bc16cb38b91
```

Observed contract:

```text
title = AegisRecorderVerificationReport.v1
$schema = JSON Schema draft 2020-12
additionalProperties = false
required property count = 62
property count = 62
reason ID count = 58
non-OK reason-count key count = 57
allOf branch count = 59
```

No current Recorder-specific checked-in Python test imports this schema. The
Phase 0A schema builder independently enumerates it because it is under the
normative `schemas/aegis/v2` directory. The planned package copy must be
byte-identical to this repository file at build time.

The frozen bundle still contains 52 schemas while the directory contains 53.
After removing only the five non-JCS-safe signed-64 boundary literals and
assigning those exact range checks to fixed `validate-report`,

```text
python -m evaluation.aegis_v2.build_schema_bundle --check
```

now returns a computable, expected stale result:

```text
exit = 1
state = STALE
schema_count = 53
candidate bundle SHA-256 =
c9357671354214a3513cfd00195ff81990d268ccd94a20e55d08650734641061
```

An independent audit then proved that the original builder copied static
envelope/policy fields from the observed bundle. A re-signed corrupted
`schema_version` or network policy could therefore become its own expected
candidate. The builder now constructs from a frozen complete static contract
and rejects missing, extra, wrong-value, and wrong-JSON-type policy fields.

```text
build_schema_bundle.py SHA-256 =
7acdade5ce28245be45f7cfec6384cf2f4f9e0543d3d1138acad9f6b91080b82
test_build_schema_bundle.py SHA-256 =
09a5fb9314eeb306098de7e0a5ef1520564045198462574d6abc03b274e04084
focused unittest = 7/7 PASS
current --check = STALE, 53 schemas
candidate bundle SHA-256 unchanged =
c9357671354214a3513cfd00195ff81990d268ccd94a20e55d08650734641061
```

No derived bundle or manifest was rebuilt.

Before that responsibility split, the builder rejected the schema because a
signed-64 endpoint exceeded its RFC 8785 safe-integer input domain. The revised
schema has no numeric literal with absolute value above `2^53-1`; it keeps
external report values as JSON integers and does not treat structural schema
acceptance as semantic acceptance.

The independent reference regression remains `35/35 PASS`. The 88-case
Phase 0A suite currently returns 46 failures and 6 errors because schema
closure validation observes 53 directory members against the unregenerated
52-schema bundle. Those derived bundle/source/evaluation manifest identities
must be rebuilt together only after independent review accepts the
schema/fixed-validator split.

## 6. Current Python/build tools

Observed Windows shell:

```text
Python = 3.13.13
pip = 26.0.1
```

These versions establish only the current inspection environment. Release
validation remains the exact clean-environment matrix in the implementation
plan.

### Isolated CPython startup-path probe

The following profile was also run through `System.Diagnostics.Process` with
`UseShellExecute=false`, a direct absolute Python executable, and a child
environment containing only `SystemRoot` and `WINDIR`:

```text
python -I -S -B -X utf8 -c <PROBE>
```

Observed:

```text
exit = 0
stderr bytes = 0
environment entries = 2
sys.flags = isolated=1, no_site=1, dont_write_bytecode=1, utf8_mode=1
sys.path[0] = <INTERPRETER_ROOT>\python313.zip
sys.path[1] = <INTERPRETER_ROOT>\DLLs
sys.path[2] = <INTERPRETER_ROOT>\Lib
sys.path[3] = <INTERPRETER_ROOT>
python313.zip exists = false
```

Therefore `-I -S` does not itself produce a two-root import path. The deployer
contract must validate this exact supported-startup vector and externally bind
the absent ZIP candidate before it performs its single allowed narrowing to
the held `DLLs` and `Lib` roots. Assuming the narrowed path already exists
would make the contract reject the supported interpreter before useful work.

### Windows native rename and drive-mapping probe

A native-layout probe using the active 64-bit Windows CPython and `ctypes`
observed:

```text
Windows version/build = 10.0.26200
pointer size = 8
WCHAR size = 2
sizeof(FILE_RENAME_INFORMATION) = 24
sizeof(IO_STATUS_BLOCK) = 16
ReplaceIfExists/RootDirectory/FileNameLength/FileName offsets = 0/8/16/20
SetFileInformationByHandle(FileRenameInfoEx=22, non-null RootDirectory)
  = ERROR_INVALID_PARAMETER (87)
SetFileInformationByHandle(FileRenameInfoEx=22, null RootDirectory)
  = success, but simple final name resolved through process cwd
NtSetInformationFile(FileRenameInformation=10, non-null RootDirectory)
  = STATUS_SUCCESS for a regular file and a directory; retained source moved
    into retained destination; IO_STATUS_BLOCK.Status = STATUS_SUCCESS
NtSetInformationFile with pre-existing destination
  = STATUS_OBJECT_NAME_COLLISION; source and competitor bytes unchanged
one-WCHAR native buffer Length=22
  = STATUS_INFO_LENGTH_MISMATCH
one-WCHAR native buffer Length=24
  = STATUS_SUCCESS
two-WCHAR native buffer Length=24
  = STATUS_SUCCESS
C: volume GUID = \\?\Volume{39c51ff1-5334-46fe-85a1-df31b8b202cf}\
QueryDosDeviceW(C:) = \Device\HarddiskVolume3
QueryDosDeviceW(Volume{...}) = \Device\HarddiskVolume3
current mapping equality = true
```

Therefore the frozen user-mode publication path is native
`NtSetInformationFile(FileRenameInformation=10)` with
`ReplaceIfExists=FALSE`, retained non-null `RootDirectory`, and exact buffer
length `max(24,20+FileNameLength)`. The Win32 wrapper, null-root, cwd-relative,
and pathname fallbacks are rejected. A fixed-drive/NTFS check alone also
cannot reject SUBST, because DOS-device mappings live in the object namespace
rather than as filesystem reparse points.

The probe observed only immediate success/collision; it did not establish that
`STATUS_PENDING` or a call/IOSB disagreement is impossible. The normative
contract therefore gives known meaning only to exact success, collision,
`STATUS_INVALID_INFO_CLASS`, `STATUS_INVALID_PARAMETER`, and
`STATUS_NOT_SUPPORTED`. Every other 32-bit status is unknown, including
nonzero success, informational, warning, unlisted error, sentinel, and
still-pending values. Pending uses a non-null negative relative
`LARGE_INTEGER`, ceiling-rounded from remaining nanoseconds to 100-nanosecond
ticks; zero budget does not wait. Timeout, wait failure, or disagreement is
`PUBLICATION_OUTCOME_UNKNOWN`. These are fail-closed design rules, not claimed
probe observations.

### WSL protected-entry capability probe

The current WSL host is reached as `nomo@172.21.45.37`. Read-only/native-temp
probes observed:

```text
kernel = 6.6.87.2-microsoft-standard-WSL2
architecture = x86_64
CPython = 3.12.3
regular interpreter = /usr/bin/python3.12
interpreter SHA-256 =
1643dacd9feaedc58f3cc581e4d22577dfe25c09b10282936186ccf0f2e61118
CPython extension suffix = .cpython-312-x86_64-linux-gnu.so
python312.zip exists = false
initial isolated sys.path =
  /usr/lib/python312.zip
  /usr/lib/python3.12
  /usr/lib/python3.12/lib-dynload
LC_ALL=C environment entries = 1
filesystem encoding/errors = utf-8/surrogateescape
flags isolated/ignore_environment/no_site/no_user_site/safe_path/
  dont_write_bytecode/utf8_mode = 1/1/1/1/1/1/1
/tmp fstatfs label/magic = ext2/ext3 / 0xef53
/ mountinfo filesystem type = ext4
/mnt/c fstatfs/mountinfo type = v9fs / 9p
openat2 no-symlink probe = PASS
execveat held-ELF probe = PASS
/proc/self/fd/3 Python-script probe = PASS
getrandom(GRND_NONBLOCK, 16 bytes) = 16
PR_SET_NO_NEW_PRIVS = PASS (0 -> 1)
/tmp statx mount ID / fstatfs = 80 / 0xef53
/mnt/c statx mount ID / fstatfs = 129 / 0x1021997
/usr/bin/python3.12 runtime W_OK = EACCES
user namespace dev/ino = 0000000000000004 / 00000000effffffd
mount namespace dev/ino = 0000000000000004 / 00000000f0000179
```

The same exact interpreter reports these getpath build constants:

```text
PREFIX = /usr
EXEC_PREFIX = /usr
PLATLIBDIR = lib
VPATH = ..
compiled PYTHONPATH = empty
```

A local WSL ext4 temporary probe copied that exact interpreter into a synthetic
root `P` and used `LC_ALL=C`, `-I -S -B -X utf8`. With
`P/bin/python3.12`, three copied `encodings` files, `P/lib/python3.12/os.py`,
and the dynload directory, CPython selected the three expected `P` paths.
Deleting only `os.py` made `sys.prefix` and stdlib fall back to `/usr` while
`sys.exec_prefix` and dynload remained under `P`. Thus the prior three-path
contract was not a pre-bootstrap source guarantee.

A second probe used the direct layout:

```text
P/python3.12
P/python3.12._pth       exact bytes: lib/python3.12\n
P/lib/python3.12/encodings/{__init__.py,aliases.py,utf_8.py}
P/lib/python3.12/lib-dynload/
```

The getpath file is 15 bytes with SHA-256
`489d6a4a7ff6f07d321bda6f61470f964de6fa753ee3e86078ea1b56ded7647a`.
Both pathname execution and held-FD `os.execve(fd, ...)` observed:

```text
sys.executable = P/python3.12
sys.prefix = P
sys.exec_prefix = P
sys.base_prefix = P
sys.base_exec_prefix = P
sys.path = [P/lib/python3.12]
sys._stdlib_dir = P/lib/python3.12
isolated/no_site = 1/1
```

At that direct-layout entry, `sys.meta_path` was exactly
`BuiltinImporter`, `FrozenImporter`, `PathFinder`; the path hooks were
`zipimporter` and `FileFinder`; and the importer cache contained only the
stdlib root and its `encodings` directory. `__spec__.origin` classified exactly
the three `encodings` modules as filesystem-backed. `os` was not loaded and
`_imp.is_frozen("os")` was true.

A Round 10 rereview repeated the exact direct-layout probe with two getpath
files:

```text
A bytes = lib/python3.12\n
A SHA-256 = 489d6a4a7ff6f07d321bda6f61470f964de6fa753ee3e86078ea1b56ded7647a
B bytes = # ignored by getpath\nlib/python3.12\n
B SHA-256 = b7924476c257c28d11e2f226616a45001cf9234201d7913278f5974b194274a2
```

CPython 3.12.3 ignored B's comment and produced the same `sys.path`, prefix,
exec-prefix, base-prefix, base-exec-prefix, `_stdlib_dir`, `isolated`,
`no_site`, and `safe_path` observations as A. Therefore a root/operator can
replace A with B after launcher validation and restore A before bootstrap
reopen without leaving a locally distinguishable observation. The probe proves
the ABA boundary; it is not a protected-entry PASS. Its WSL temporary root was
removed.

The temporary roots were removed after the capability probes. They
are not retained authority or deployment evidence.

The exact held-interpreter capability probe used transient executable FD 11
with `FD_CLOEXEC`; the first bootstrap statement observed only FDs `0..10`,
exactly `LC_ALL=C`, the three paths above, and flags `1/1/1/1`. This proves the
exec-descriptor closure mechanism. It is not the normative Recorder FD table:
the closed contract adds the approval record and stdlib manifest on FDs 10/11,
uses transient interpreter FD 12, and requires the first bootstrap statement
to see exactly `0..11`.

On the same frozen CPython, `posix.listdir("/proc/self/fd")` with persistent
FDs `0..2` returned exactly `["0","1","2","3"]`; 3 was the transient
enumeration FD and was closed on return. The normative bootstrap uses the same
self-accounting shape with persistent `0..11` plus transient 12.

The initial import shape is builtin/frozen finders plus `PathFinder`; path hooks
are `zipimporter` and `FileFinder`. The importer cache initially covers the
absent ZIP candidate, stdlib root, `encodings`, and dynload root. Filesystem
code already executed before the bootstrap is exactly:

```text
encodings          /usr/lib/python3.12/encodings/__init__.py
encodings.aliases  /usr/lib/python3.12/encodings/aliases.py
encodings.utf_8    /usr/lib/python3.12/encodings/utf_8.py
```

The remaining entry modules have `__main__`, builtin, or frozen origins. The
three filesystem modules belong to the externally approved CPython/ELF/stdlib
prerequisite; they cannot be reclassified as locally protected after startup.

Under the clean flags, the observed signal profile is default
`SIGCHLD`/`SIGTERM`/`SIGHUP`/`SIGQUIT`, Python's default-int handler for
`SIGINT`, ignored `SIGPIPE`/`SIGXFSZ`, and an empty mask. Builtin `_signal`
exposes the required mask/pending/disposition operations. A held `_hashlib`
extension can be created and executed through builtin `_imp` from its exact
`/proc/self/fd/N` object and exposes `openssl_sha256`; its ELF/libcrypto
closure remains an external pre-execution prerequisite.

The ordinary WSL shell/Python baseline has four UID/GID slots equal to 1000,
supplementary groups `4 24 27 30 46 100 1000`, zero
`CapInh`/`CapPrm`/`CapEff`/`CapAmb`, and `NoNewPrivs: 0`. The external launcher
must clear all supplementary groups and set and verify `no_new_privs=1`; an
unprivileged `setpriv --no-new-privs` probe observed `NoNewPrivs: 1`. The
ambient shell is capability evidence, not a conforming protected entry.

On Linux `6.6.87.2`, `/proc/1/status` with an empty supplementary-group set
encoded its complete group row as bytes
`47 72 6f 75 70 73 3a 09 20 0a`, namely `Groups:\t \n`. The contract must not
normalize away the kernel's one space before LF.

A compiled native `/tmp` probe independently observed `STATX_MNT_ID` in the
returned mask, mount IDs 80/129 matching the ext4-root and `/mnt/c` mountinfo
rows, `fstatfs` magic `0xef53`/`0x1021997`, runtime-credential `W_OK` rejection
for root-owned `/usr/bin/python3.12`, a full nonblocking 16-byte `getrandom`,
and an unprivileged `PR_SET_NO_NEW_PRIVS` transition from 0 to 1. The temporary
binary is not retained evidence; these facts define capability only and do not
prove the external trust slot.

Python 3.12 exposes no `os.openat2` or `os.renameat2` wrapper. The external
Linux launcher/deployment adapter is therefore a native prerequisite and not a
Recorder self-authorizing Python path. WSL protected deployment and evidence
must use the distribution-native filesystem. `/mnt/c` remains permitted only
for the user's explicit `cp` transfer, followed by a source/destination hash
comparison. The observed distribution `/usr/lib/python3.12` tree is capability
evidence only; conformance requires operator-provisioned curated stdlib and
dynload roots with exact manifest membership.

## 7. Implementation consequences

- Create `recorder/` as a separate distribution.
- Do not modify or depend on the incomplete root package entry.
- Fix the Recorder distribution version in its own `pyproject.toml`.
- Use no root runtime or build dependency.
- Add explicit Recorder tests; do not depend on current pytest fallback.
- Treat the checked-in report schema as input bytes, not as an installed
  `jsonschema` runtime dependency.
- Repeat branch, HEAD, tree, schema hash, Python version, and test inventory
  immediately before implementation and before final evidence review.

## 8. Reproduction commands

```powershell
git branch --show-current
git rev-parse HEAD
git describe --tags --always --dirty
Get-FileHash -Algorithm SHA256 -LiteralPath .\pyproject.toml
Test-Path -LiteralPath .\src\aegis\cli.py
Test-Path -LiteralPath .\recorder
Get-ChildItem -LiteralPath .\src -Recurse -File
Get-ChildItem -LiteralPath .\test -Recurse -File
python -I -c "import importlib.util,json; print(json.dumps({'aegis': importlib.util.find_spec('aegis') is not None, 'aegis_recorder': importlib.util.find_spec('aegis_recorder') is not None}))"
python -m pytest --collect-only -q
Get-FileHash -Algorithm SHA256 -LiteralPath .\schemas\aegis\v2\recorder_verification_report.v1.schema.json
```

```powershell
$pythonExe = (Get-Command python).Source
$psi = [Diagnostics.ProcessStartInfo]::new()
$psi.FileName = $pythonExe
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.WorkingDirectory = (Get-Location).Path
$psi.Environment.Clear()
$windowsRoot = [Environment]::GetEnvironmentVariable("SystemRoot")
$psi.Environment["SystemRoot"] = $windowsRoot
$psi.Environment["WINDIR"] = $windowsRoot
@("-I", "-S", "-B", "-X", "utf8", "-c",
  "import json,sys;print(json.dumps({'flags':[sys.flags.isolated,sys.flags.no_site,sys.flags.dont_write_bytecode,sys.flags.utf8_mode],'path':sys.path},ensure_ascii=True,separators=(',',':')))"
) | ForEach-Object { [void]$psi.ArgumentList.Add($_) }
$process = [Diagnostics.Process]::Start($psi)
$stdout = $process.StandardOutput.ReadToEnd()
$stderr = $process.StandardError.ReadToEnd()
$process.WaitForExit()
$process.ExitCode
$stdout
$stderr.Length
$psi.Environment.Count
```
