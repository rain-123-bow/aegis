# Aegis Recorder POSIX adapter contract

Status: `NORMATIVE_DRAFT_FOR_REREVIEW_10`

Scope: `LINUX_PROTECTED_BOOTSTRAP_V1` on x86-64 Linux or WSL2, kernel 5.11 or
newer, and the exact approved CPython 3.12.3 build below. It requires procfs `/proc/self/fd`,
`/proc/self/status`, `/proc/self/ns/{user,mnt}`, and
`/proc/self/mountinfo`, `openat2`,
`faccessat2(AT_EMPTY_PATH | AT_EACCESS)`,
`statx(AT_EMPTY_PATH, STATX_MNT_ID)`, `execveat(AT_EMPTY_PATH)`, `close_range`,
`getrandom`, and `renameat2(RENAME_NOREPLACE)`. WSL2 deployment and evidence
use only the distribution-native ext4 filesystem; `/mnt/c`, 9p/DrvFS, network
filesystems, macOS, BSD, non-Linux POSIX, and CPython 3.13 have no v1 fallback.
This adapter is Linux validation, not the Windows production profile and not
external authority.

## 1. Protected POSIX validation entry and output contract

Linux validation target launch has exactly one entry. An external
operator-controlled native launcher, selected and verified outside the
candidate and Recorder repository, executes the held interpreter object with:

```text
<APPROVED_ABSOLUTE_CPYTHON_ARGV0_BYTES>
-I
-S
-B
-X
utf8
/proc/self/fd/3
posix-proxy
--approval-record-sha256
<64_LOWERCASE_HEX>
--session-dir
<ABSOLUTE_ABSENT_SESSION_PATH_BYTES>
--target-cwd
<ABSOLUTE_TARGET_CWD_BYTES>
--
<ABSOLUTE_NATIVE_ELF_TARGET_BYTES>
<TARGET_ARG_BYTES_1> ... <TARGET_ARG_BYTES_N>
```

The line breaks separate argv elements; they are not shell syntax. `N` may be
zero. The approval hash, session path, target cwd, target path, and target argv
are raw OS argv bytes. A shell, PATH lookup, response/configuration file,
environment alias, `python -c`, `python -m`, ordinary console script, relative
path, or activated-environment convenience is outside this contract. Every
flag and option is mandatory in the displayed position. Reordering,
repetition, abbreviation, `=` spelling, an extra interpreter flag, an option
after `--`, or a missing `--` is a grammar error. Every element after `--`
belongs to target argv and is never parsed as a Recorder option.

The external operator trust store selects one exact
`AegisRecorderPosixApproval.v1` byte record. The candidate, repository, wheel,
Recorder, target, CLI arguments, environment, stdin, and cwd cannot choose or
rewrite its slot, bytes, path, ID, expected digest, key, launcher, adapter,
interpreter, wheel, final parent, or final name. The launcher reads no
candidate-facing configuration to make that selection. A direct
adapter/bootstrap invocation, candidate-created byte-identical record, local
self-hash, or Recorder journal field cannot prove that the external slot was
used.

The approval record is not JSON. It has this only byte grammar and fixed field
order:

```text
AegisRecorderPosixApproval.v1\n
record_size_hex=<16-lowercase-hex>\n
profile=POSIX_CPTHON_3_12_VALIDATION\n
mechanism=LINUX_PROTECTED_BOOTSTRAP_V1\n
machine=x86_64\n
python_version=3.12.3\n
python_platlibdir=lib\n
python_build_vpath=..\n
runtime_uid_dec=<canonical-uint32>\n
runtime_gid_dec=<canonical-uint32>\n
trust_owner_uid_dec=0\n
user_namespace_dev_hex=<16-lowercase-hex>\n
user_namespace_ino_hex=<16-lowercase-hex>\n
mount_namespace_dev_hex=<16-lowercase-hex>\n
mount_namespace_ino_hex=<16-lowercase-hex>\n
native_launcher_argv0_hex=<absolute-posix-bytes-hex>\n
native_launcher_dev_hex=<16-lowercase-hex>\n
native_launcher_ino_hex=<16-lowercase-hex>\n
native_launcher_sha256=<64-lowercase-hex>\n
native_adapter_argv0_hex=<absolute-posix-bytes-hex>\n
native_adapter_dev_hex=<16-lowercase-hex>\n
native_adapter_ino_hex=<16-lowercase-hex>\n
native_adapter_sha256=<64-lowercase-hex>\n
python_argv0_hex=<absolute-posix-bytes-hex>\n
python_dev_hex=<16-lowercase-hex>\n
python_ino_hex=<16-lowercase-hex>\n
python_sha256=1643dacd9feaedc58f3cc581e4d22577dfe25c09b10282936186ccf0f2e61118\n
python_pth_dev_hex=<16-lowercase-hex>\n
python_pth_ino_hex=<16-lowercase-hex>\n
python_pth_size_hex=000000000000000f\n
python_pth_sha256=489d6a4a7ff6f07d321bda6f61470f964de6fa753ee3e86078ea1b56ded7647a\n
python_elf_closure_manifest_sha256=<64-lowercase-hex>\n
wheel_sha256=<64-lowercase-hex>\n
bootstrap_sha256=<64-lowercase-hex>\n
code_manifest_sha256=<64-lowercase-hex>\n
stdlib_manifest_sha256=<64-lowercase-hex>\n
control_dir_hex=<absolute-posix-bytes-hex>\n
control_dir_dev_hex=<16-lowercase-hex>\n
control_dir_ino_hex=<16-lowercase-hex>\n
final_parent_hex=<absolute-posix-bytes-hex>\n
final_parent_dev_hex=<16-lowercase-hex>\n
final_parent_ino_hex=<16-lowercase-hex>\n
final_parent_fstype=ext4\n
final_name_hex=<single-component-posix-bytes-hex>\n
protected_root_hex=<absolute-posix-bytes-hex>\n
stdlib_root_hex=<absolute-posix-bytes-hex>\n
stdlib_root_dev_hex=<16-lowercase-hex>\n
stdlib_root_ino_hex=<16-lowercase-hex>\n
dynload_root_hex=<absolute-posix-bytes-hex>\n
dynload_root_dev_hex=<16-lowercase-hex>\n
dynload_root_ino_hex=<16-lowercase-hex>\n
stdlib_zip_candidate_hex=<absolute-posix-bytes-hex>\n
session_parent_root_hex=<absolute-posix-bytes-hex>\n
session_parent_root_dev_hex=<16-lowercase-hex>\n
session_parent_root_ino_hex=<16-lowercase-hex>\n
```

The notation `\n` above is one byte `0x0a`, including after the last field.
Every other record byte is ASCII. BOM, CR, NUL, TAB, space, escape, comment,
blank line, missing/duplicate/reordered/unknown field, leading/trailing byte,
or alternate spelling is invalid. `record_size_hex` includes the header, its
own fixed-width line, and final LF; it must equal `fstat(fd).st_size` and be in
`1..65536`. Parsing advances one cursor from offset zero by exact literal field
names and lengths; search, split-to-map, last-value-wins, or normalization is
forbidden. The final cursor must equal both declared and physical size.

SHA-256 fields are exactly 64 lowercase hexadecimal bytes. Device/inode fields
are exactly 16 lowercase hexadecimal bytes interpreted as unsigned 64-bit.
Canonical uint32 is `0` or a nonzero decimal first digit followed by decimal
digits, with no sign or leading zero and value at most `4294967295`. A POSIX
byte hex value is lowercase, even-length, decodes to `1..4096` bytes, and
contains no NUL. Absolute path bytes start with `/`; except for `/`, they have
no empty, `.`, or `..` component and no trailing `/`. The final name decodes
to `1..255` bytes and contains neither `/` nor the exact values `.` or `..`.
`protected_root_hex` must decode to the exact byte concatenation of final
parent, one `/`, and final name.

Let `P` be the byte dirname of `python_argv0_hex`. Its basename is exactly
`python3.12`; `stdlib_root` is exactly `P/lib/python3.12`; `dynload_root` is
exactly `P/lib/python3.12/lib-dynload`; and `stdlib_zip_candidate` is exactly
`P/lib/python312.zip` and absent. The approved getpath file is not
request-configurable: its path is exactly `python_argv0 + b"._pth"`, its
dev/ino/size/hash equal the four `python_pth_*` fields, and its complete bytes
are exactly the 15-byte ASCII/LF value:

```text
lib/python3.12\n
```

The file is regular, root-owned, runtime-nonwritable, single-link, mode `0444`,
and no path component is a link. CPython reads it by pathname before the first
bootstrap statement. The external launcher therefore authenticates the exact
path object immediately before `execveat`; the bootstrap later reopens it
no-follow, compares identity and exact bytes, and retains that FD. These
post-start checks detect only drift still observable when the bootstrap
reopens the file; they do not convert the pathname read into a held-FD read.
Root/operator replacement in that interval, including change-and-restore ABA
before the reopen, remains the explicit external trust boundary. A locally
conforming result proves neither pathname continuity nor absence of that ABA.

The initial CPython `sys.path` byte vector is exactly `[stdlib_root]`.
`sys.executable == python_argv0`,
`sys.prefix == sys.exec_prefix == sys.base_prefix == sys.base_exec_prefix == P`,
`sys._stdlib_dir == stdlib_root`, and `sys.platlibdir == "lib"`. Both
`dirname(P)/pyvenv.cfg` and `P/pyvenv.cfg` are absent.
`P/pybuilddir.txt` and `P/Modules/Setup.local` are absent; the fixed VPATH is
still bound because it determines the build prefix if that forbidden marker
ever appears. Every getpath `._pth` candidate
associated with the approved interpreter ELF closure is absent except the one
approved interpreter file above. An exact CPython patch/build, interpreter
digest, PLATLIBDIR, VPATH, derived layout, marker, or observable-path mismatch
blocks `execveat`; a new patch or build requires a new reviewed profile.

`trust_owner_uid_dec` is the fixed root UID `0`; both `runtime_uid_dec` and
`runtime_gid_dec` must be nonzero. The V1 supplementary-group set is exactly
empty and is not request- or record-configurable. The selected record
FD is a regular, read-only, seekable, single-link file owned by
`trust_owner_uid_dec`, with exact mode `0444`, initial offset zero, no
`O_APPEND`/`O_NONBLOCK`, and bounded size. Every consumer uses `pread` from
explicit offsets and proves the shared offset remains zero. Let
`H = SHA256(exact record bytes)`. `H` is the displayed approval hash and a
process-input binding only; it is not self-issued authority.

The external standard-library manifest has this fixed grammar:

```text
AegisRecorderPosixStdlibManifest.v1\n
record_size_hex=<16-lowercase-hex>\n
member_count_hex=<8-lowercase-hex>\n
member=<ascii-module-name>|<PY-or-SO>|<L-or-D>|<PRELOADED-or-SEED-or-LATE>|<relative-path-hex>|<16-lowercase-hex-size>|<64-lowercase-hex-sha256>\n
...
```

The same ASCII/LF/cursor/size rules apply. Maximum physical size is 1048576
bytes and member count is `1..512`. Rows are strictly increasing by ASCII
module-name bytes. A module name is `1..255` ASCII bytes: dot-separated,
nonempty identifiers whose first byte is `[A-Za-z_]` and remaining bytes are
`[A-Za-z0-9_]`. Module names, root-relative paths, and decoded paths are
unique. Only `PY|L` and `SO|D` kind/root pairs are legal. A `PY` path is exactly
either the module-name components joined by `/` plus `.py`, or those components
plus `/__init__.py`; the latter alone marks a package. An `SO` path is one
component equal to the final module-name component plus the fixed suffix
`.cpython-312-x86_64-linux-gnu.so`. Relative paths are nonempty, contain no
empty, `.`, or `..` component, and never start or end with `/`. Unknown
kind/root/stage, an alternate module/path mapping, or an extra row is invalid.
The stage relation is closed:

- exactly these three `PY|L|PRELOADED` rows exist:
  `encodings|encodings/__init__.py`,
  `encodings.aliases|encodings/aliases.py`, and
  `encodings.utf_8|encodings/utf_8.py`;
- exactly one `SO|D|SEED` row exists, with module `_hashlib` and path
  `_hashlib.cpython-312-x86_64-linux-gnu.so`; and
- every other row is `LATE`.

The
proper dotted prefixes of every member name must each exist exactly once as a
`PY|L` package row whose path is the prefix components plus `/__init__.py`.
A proper prefix mapped to an ordinary `.py` module, or a missing prefix, is
invalid.

The approval-bound bootstrap source contains three strictly sorted, duplicate-
free ASCII name tables: exact entry-preloaded non-filesystem modules, permitted
later builtin modules, and permitted later frozen modules. Its
`bootstrap_sha256` binds those tables. At entry, the actual non-filesystem
module-name/origin set must equal the first table.

Let `E_fs` be every entry-preloaded module whose origin is a filesystem path,
and `M_pre` be the three `PRELOADED` rows. The only cross-set exception is
exact equality and one-to-one mapping:

```text
names(E_fs) == names(M_pre)
origin(E_fs[name]) == stdlib_root + "/" + path(M_pre[name])
```

Each `E_fs` object has the frozen `SourceFileLoader` class, is retained by
object identity from the first bootstrap statement, and matches its row's
name/kind/root/path. The external launcher verifies every `M_pre` size/hash and
the exact root membership before CPython exec; the bootstrap rehashes them
after the seed. They are explicit pre-bootstrap external prerequisites, not
locally proved before execution. A `PRELOADED` row is never served by the
manifest finder, and deletion/replacement of its retained `sys.modules` object
fails closed. The same no-finder and identity-pinning rules apply to the
manually loaded `SEED` object.

`BuiltinImporter` and `FrozenImporter` are wrapped so they can answer only for
their respective later table. The entry-preloaded non-filesystem names, later
builtin names, later frozen names, `SEED` name, `LATE` names, and protected-
runtime names derived from the code manifest are pairwise disjoint. `M_pre`
names are also disjoint from every set except their exact `E_fs` counterparts.
Thus no later manifest row can be silently won by an earlier finder, and a
stdlib row cannot shadow a protected-runtime module. The unique `_hashlib`
`SEED` member is loaded explicitly at step 5.

The dedicated interpreter, stdlib, and dynload roots are
operator-provisioned, curated roots; a distribution's ambient
`/usr/lib/python3.12` tree is capability evidence only and cannot be used
directly. `P` contains exactly `python3.12`, `python3.12._pth`, and the `lib`
directory; `P/lib` contains exactly `python3.12`. The stdlib root contains
exactly the `L` manifest regular files, directories implied by their paths, and
the exact nested `lib-dynload` root; that nested root contains exactly the `D`
manifest files. Links, devices, `.pyc`, `__pycache__`, namespace packages, and
extra members are forbidden. `os` has no stdlib-manifest row and is present
exactly once in the approved later-frozen name table; the manifest finder can
never serve it.

The external interpreter/hash-seed ELF closure manifest is:

```text
AegisRecorderPosixElfClosureManifest.v1\n
record_size_hex=<16-lowercase-hex>\n
member_count_hex=<8-lowercase-hex>\n
member=<INTERPRETER-or-LOADER-or-NEEDED-or-HASH_SEED>|<absolute-path-hex>|<16-lowercase-hex-dev>|<16-lowercase-hex-ino>|<16-lowercase-hex-size>|<64-lowercase-hex-sha256>\n
...
```

It uses the same cursor/canonical/path rules, is at most 262144 bytes, and has
`1..64` rows strictly increasing by raw ASCII `(role, absolute path bytes)`.
Paths are unique. There is exactly one `INTERPRETER`, one `LOADER`, and one
`HASH_SEED` row. The hash seed path is the same approved `_hashlib` object as
the unique `SO|D|SEED` row. Every other unique transitive dependency of the
interpreter, seed, or another dependency has exactly one `NEEDED` row even
when shared by multiple parents. Unknown roles, missing/duplicate paths, or an
extra closure object fail. The operator slot selects these bytes, and
`python_elf_closure_manifest_sha256` binds them. The native launcher validates
the complete held closure before Python exec. The `INTERPRETER` row path,
dev/ino, and hash equal the approval `python_*` fields. The `HASH_SEED` path is
the exact byte join of approved dynload root, `/`, and the unique `_hashlib`
`SO|D|SEED` relative path; its size/hash equal that stdlib-manifest row. The
`LOADER` path equals the interpreter's exact `PT_INTERP` bytes. Every parsed
`DT_NEEDED` name must resolve in the operator-controlled runtime namespace to
the one held `NEEDED` row the launcher hashed; duplicate basenames, `RPATH`,
`RUNPATH`, `LD_*`, loader preload/audit state, or an unlisted resolved object
disables the profile. Actual pre-bootstrap loader resolution remains the
external prerequisite described next.
Linux's ELF loader still resolves approved dependency pathnames before the
bootstrap can run; root/operator mutation inside that external trust root
remains a declared prerequisite boundary, not Recorder-proved pre-loader
integrity.

The external trust-store slot also supplies and validates the launcher binary,
the adapter binary, wheel, interpreter ELF-closure manifest, stdlib manifest,
and every approval-bound object. It is outside the candidate, repository,
wheel, protected root, target cwd, and session roots. A runtime request may
provide only target argv bytes, target-cwd bytes, and an absent session name.
A deployment request provides no candidate-selected path or hash. Missing
slot/record, a nonconforming launcher, or any mismatch makes the profile
`DEPLOYMENT_UNAVAILABLE`; no repository-owned fallback exists. The repository
conformance harness always reports `authority_verified=false`. The
operator-controlled control plane verifies the launcher identity against its
independent slot before launch; `native_launcher_*` fields are bindings and
audit facts, never launcher self-authorization.

UID 0 means root in the exact externally approved user namespace, not merely a
numeric value in a caller-created namespace. Before selecting trust paths, the
launcher opens `/proc/self/ns/user` and `/proc/self/ns/mnt` read-only, retains
them through all preflight checks, and requires their `(st_dev, st_ino)` values
to equal the four approval namespace fields. The bootstrap reopens those two
procfs namespace objects before any new post-entry filesystem import and checks the same
identities. A caller-created user or mount namespace, identity drift, missing
procfs namespace object, or namespace field selected by the request disables
the profile.

Every external trust-store file, approved getpath file, curated stdlib/dynload member, launcher,
adapter, interpreter/ELF-closure member, wheel, manifest, and each of their path
ancestors is owned by `trust_owner_uid_dec` and has no group/other write bit.
At the runtime credentials, `faccessat2(held_fd, "", W_OK,
AT_EMPTY_PATH | AT_EACCESS)` must fail with `EACCES`; unexpected success or
another error rejects the object. Trust files/directories must still provide
the read/search/execute access required by their declared role. The runtime UID
cannot own one of those external objects or ancestors. Every executable trust
object has no setuid/setgid bit and no `security.capability` xattr.
Root/operator
mutation remains outside Recorder authority. The deployed protected root,
bootstrap, and code manifest are runtime-owned outputs; their held-object/hash/
repeated-membership checks and same-UID limitation are separate and are not
promoted to external trust-store protection. The external launcher itself runs
unprivileged: real/effective/saved/filesystem UID all equal
`runtime_uid_dec`; real/effective/saved/filesystem GID all equal
`runtime_gid_dec`; `getgroups(0, NULL)` returns zero and `getgroups` exposes no
supplementary GID; effective, permitted, inheritable, and ambient capabilities
are empty; and
`PR_GET_NO_NEW_PRIVS` is 1 before either fork. The launcher and native adapter
validate these facts before mutation/exec; the bootstrap independently checks
the UID/GID values and exact empty `posix.getgroups()` result. Failure is
`DEPLOYMENT_UNAVAILABLE` for the launcher or a preflight failure after entry.
There is no weaker “supplementary groups happen not to write accepted paths”
substitute: any supplementary group rejects the profile. Same-UID ptrace,
kernel compromise, and writes
through a pre-existing privileged handle remain explicit external boundaries;
the contract does not relabel them as protected.

For every launch, the native launcher opens each approval-bound trust path and
each requested target, target-cwd, and session-parent absolute path from a held
`/` dirfd with `openat2`. It strips exactly one leading slash and uses:

```text
RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS
```

Empty components, `.`, `..`, NUL, symlinks, magic links, wrong type, writable
trust-anchor files, digest mismatch, and unsupported filesystems fail before
the bootstrap. `/proc/self/fd/N` is allowed only for the fixed inherited
descriptors below; it is never accepted as an operator path.

Before constructing the descriptor table, the launcher derives `P` and every
getpath path above from the approved interpreter path. It proves the exact
`P`/stdlib/dynload membership, authenticates `python3.12._pth` by
dev/ino/size/hash and exact 15 bytes, and proves the ZIP, both `pyvenv.cfg`
candidates, both build markers, and every competing ELF-closure `._pth`
candidate absent. It also proves the held interpreter is the exact approved
CPython 3.12.3 digest/build. Failure returns `DEPLOYMENT_UNAVAILABLE` without
calling `execveat`; a bootstrap-side rejection is not a substitute for these
pre-exec checks.

For every approval-bound final parent, protected root, and session/evidence
parent, the external launcher uses the held descriptor with
`statx(fd, "", AT_EMPTY_PATH | AT_STATX_SYNC_AS_STAT, STATX_MNT_ID, ...)`.
`STATX_MNT_ID` must be returned. It reads `/proc/self/mountinfo` to EOF with a
maximum of 8388608 bytes; zero bytes, a missing final LF, CR, NUL, or a line
longer than 65536 bytes is invalid. A cursor parser accepts the documented
space-separated mountinfo grammar, ignores syntactically valid optional
fields, and requires exactly one row whose canonical unsigned-decimal mount-ID
field equals `stx_mnt_id`; that row's filesystem-type field after the exact
` - ` separator must be the ASCII token `ext4`.
`fstatfs(fd).f_type` must also equal `0xef53` (`EXT4_SUPER_MAGIC`). Missing,
duplicate, truncated, oversized, malformed, or changed observations fail
closed. The static deployment adapter repeats this predicate before its first
mutation and immediately before publication and requires the same mount ID at
both observations. This dual predicate distinguishes the current WSL ext4 root
from `/mnt/c`/9p even though `stat -f` labels ext-family magic `0xef53` as
`ext2/ext3`.

Immediately before `execveat`, the launcher freezes this descriptor table:

| FD | Exact role |
|---:|---|
| 0 | blocking client-input FIFO/socket, read-compatible |
| 1 | blocking client-output FIFO/socket, write-compatible |
| 2 | distinct blocking target-stderr FIFO/socket, write-compatible |
| 3 | approved bootstrap regular file, read-only |
| 4 | protected-runtime root directory |
| 5 | requested target-cwd directory |
| 6 | requested native ELF target regular file, read-only |
| 7 | absent-session parent directory |
| 8 | trusted standard-library directory |
| 9 | trusted `lib-dynload` directory |
| 10 | externally selected approval-record bytes, read-only |
| 11 | externally selected stdlib-manifest bytes, read-only |
| 12 | approved interpreter regular-file exec descriptor, `FD_CLOEXEC` |

Roles, access flags, blocking state, types, and illegal aliases are checked.
Regular input FDs are `O_RDONLY`, seekable, nonappend, blocking, at offset zero,
and read only with `pread`; validation must leave their shared offset zero.
Directory FDs are `O_RDONLY|O_DIRECTORY`, are never enumerated through their
trusted open-file description, and use a separately opened relative `"."`
description for enumeration. Data pipes are blocking, nonseekable, and exactly
direction-compatible. FDs that cross exec have `FD_CLOEXEC` clear before exec;
FD 12 alone has it set.

Every exact-FD observation uses the same self-accounting rule. A native process
first applies the required `close_range`, then opens `/proc/self/fd` with
`O_RDONLY|O_DIRECTORY|O_CLOEXEC`; that probe FD must be the next integer.
`getdents64` must return exactly the expected persistent decimal names plus the
probe FD, `.` and `..`, with no duplicate/nonnumeric name. The probe closes and
`fcntl(F_GETFD)` must return `EBADF` before continuation. Thus runtime-launcher
pre-exec observes persistent `0..12` plus probe 13; deployment-launcher
pre-exec observes `0..7` plus probe 8; and adapter post-exec observes `0..6`
plus probe 7.

After `fork`, the native launcher requires an empty pending-signal set, empties
the signal mask, disables any alternate signal stack, sets every catchable
Linux signal disposition to `SIG_DFL`, and explicitly clears
`SA_NOCLDWAIT|SA_NOCLDSTOP` for `SIGCHLD`. It never attempts to change
`SIGKILL` or `SIGSTOP`. Any failure blocks exec. The launcher then `fchdir(4)`,
sets `umask(077)`, closes every descriptor above 12 with
`close_range(..., CLOSE_RANGE_UNSHARE)`, and requires the pre-exec descriptor
set to equal `0..12`. It then calls exactly:

```text
execveat(12, "", argv, ["LC_ALL=C"], AT_EMPTY_PATH)
```

FD 12 is `FD_CLOEXEC`: it is the source of the interpreter image and is closed
by successful `execveat`. The bootstrap therefore requires its first-statement
descriptor set to equal `0..11`; any surviving or newly persistent descriptor
at 12 or above is a preflight failure. The launcher checks `0..12` before
`execveat`; the bootstrap checks `0..11` after interpreter startup. These are
different, fixed observation points.

The single `LC_ALL=C` byte mapping is deliberate. On the accepted WSL
CPython 3.12.3 profile it prevents locale-coercion from injecting `LC_CTYPE`
while `-X utf8` still yields filesystem encoding `utf-8` with
`surrogateescape`. `PATH`, `HOME`, `PYTHON*`, `LD_*`, inherited locale, and
every other environment entry are absent.

The bootstrap uses `sys.orig_argv` only after entering its top-level
`BaseException` barrier. Before the retained-FD `os` module is available, every
element is encoded only with builtin
`element.encode("utf-8", "surrogateescape")`; after `os` loads, the result must
also equal `os.fsencode(element)`. These exact POSIX bytes are the
launch-grammar authority.
They must reconstruct the prefix and application argv above byte-for-byte.
Re-encoding must round-trip each original OS argv byte; decoded display text,
Unicode normalization, locale replacement, `realpath`, and shell
reconstruction are never argv identity. NUL is forbidden by the OS argv
boundary. The exact target elements become the `requested_argv`
`OsStringIdentity` values; the exact session element becomes the
`session_path` identity defined below.

The bootstrap's first executable statement enters the same top-level
`BaseException` and zero-diagnostic boundary required by
`SUPERVISOR_CONTRACT.md`. Before importing any `aegis_recorder` module it:

1. binds only preloaded `sys`, builtins, builtin `posix`, builtin `_imp`,
   builtin `_signal`, and the already-loaded frozen import objects. Any
   new filesystem import after the first statement and before step 5 is a
   contract failure. From step 5 until
   step 7, the unique retained-procfd `_hashlib` seed load specified below is
   the only filesystem-backed import; any other filesystem import is a
   contract failure. It requires the exact approved CPython
   3.12.3 implementation/build, `sys.flags.isolated == 1`,
   `sys.flags.ignore_environment == 1`, `sys.flags.no_site == 1`,
   `sys.flags.no_user_site == 1`, `sys.flags.safe_path == 1`,
   `sys.flags.dont_write_bytecode == 1`, UTF-8 mode, UTF-8 filesystem encoding,
   and `surrogateescape`, then sets and confirms
   `sys.dont_write_bytecode = True`;
2. retains the initial `sys.path`, `sys.meta_path`, path hooks, importer cache,
   and preloaded-module metadata. Using only `str.encode("utf-8",
   "surrogateescape")`, it reconstructs `sys.orig_argv` bytes and validates the
   fixed grammar far enough to obtain syntactically valid `H`. It requires the
   post-`execveat` descriptor set to equal `0..11`: builtin
   `posix.listdir("/proc/self/fd")` must return exactly decimal names `0..12`,
   where 12 is CPython's transient enumeration FD, and `posix.fstat(12)` must
   then raise `EBADF`. It validates all predicates
   available from builtin `posix`, requires `posix.environ` to contain exactly
   `LC_ALL=C`, and requires cwd identity to equal FD 4;
3. validates the CPython post-start signal profile with builtin `_signal`:
   empty mask and pending set; `SIGCHLD`, `SIGTERM`, `SIGHUP`, and `SIGQUIT`
   are `SIG_DFL`; `SIGINT` is `_signal.default_int_handler`; and CPython's
   `SIGPIPE` plus `SIGXFSZ` where present are `SIG_IGN`. It forks one preflight
   child that calls `_exit(0)` and requires blocking `waitpid(exact_pid, 0)` to
   return that PID and status zero. `ECHILD`, a different PID/status, a handler,
   or a blocked signal fails before session creation. This independently
   detects inherited `SIGCHLD=SIG_IGN` or `SA_NOCLDWAIT`;
4. verifies FD 10 and FD 11 type, owner, mode, size, seekability, offset, and
   inherited-FD rules available without a filesystem module; reads both only
   with `posix.pread`; and uses bootstrap-inline fixed cursor parsers to validate
   the complete approval and stdlib-manifest byte grammars. These parsers
   implement no hash algorithm and accept no algorithm identifier from input.
   After parsing, it derives `P` and the fixed getpath-object paths, walks from
   a transient `/` FD with no-follow component opens, and reopens the approved
   `python3.12._pth`. It requires the recorded dev/ino, regular/single-link
   mode, exact size 15, and exact bytes `lib/python3.12\n`, retains that FD, and
   proves the forbidden marker and competing-`._pth` paths absent. It then
   opens `/proc/self/ns/user` and `/proc/self/ns/mnt` with
   builtin `posix`, checks the exact approval dev/ino pairs, closes them, and
   repeats the same listdir/transient-12 probe. A bounded builtin-`posix`
   read of `/proc/self/status` must contain unique `Uid:`, `Gid:`, `Groups:`,
   `CapInh`, `CapPrm`, `CapEff`, `CapAmb`, and `NoNewPrivs` rows. The four
   real/effective/saved/filesystem UID/GID values all equal the parsed approval
   runtime IDs; `Groups:` is exactly `Groups:\t \n`; all four capability values
   are zero; and `NoNewPrivs` is 1. UID/GID rows contain four canonical unsigned
   decimals separated by one tab. Capability values are exactly 16 lowercase
   hexadecimal digits, and `NoNewPrivs` is the one byte `1`. Other kernel rows
   are ignored only after their one-line structure is bounded. It reads at most
   65536 bytes, caps every line at 4096 bytes, requires EOF and a final LF, and
   rejects missing/duplicate/malformed required rows, CR, NUL, or truncation.
   It separately requires builtin `posix.getgroups()` to return the exact empty
   list, closes the transient status FD, and again repeats the exact
   listdir/transient-12 probe;
5. locates the one required `_hashlib` `SO|D|SEED` row. It opens every path
   component relative to held FD 9 with `O_NOFOLLOW|O_CLOEXEC`, retains the
   final regular FD, checks type and declared size, and loads that exact object
   only through `/proc/self/fd/<held-fd>` using builtin
   `_imp.create_dynamic`/`_imp.exec_dynamic` and a frozen `ModuleSpec`.
   Ordinary `ExtensionFileLoader` is forbidden. The external native launcher
   must already have verified this seed, its manifest, and its ELF dependency
   closure from the operator trust slot. The bootstrap cannot independently
   authenticate the hash seed before executing it and makes no such claim. It
   retains the created module object identity and executable FD until process
   exit; absence of that external prerequisite disables the profile;
6. uses only the seed's standard-library `openssl_sha256` implementation to
   hash the exact approval bytes, exact manifest bytes, the retained seed FD,
   FD 3, `/proc/self/exe`, the protected code manifest, and all approval-bound
   trees, including the retained getpath file. It requires the approval digest
   to equal argv `H`, the manifest digest to equal the approval field, every
   object size/hash/dev/ino to match, the retained getpath-file digest to equal
   `python_pth_sha256`, the initial `sys.path` byte vector to equal
   `[stdlib_root]`, all frozen prefix/executable/stdlib fields to equal the
   derived values, the ZIP candidate and override markers to be absent, and the
   complete `P`/stdlib/dynload membership to equal the closed layout. It verifies
   each retained `E_fs` module object still has its entry identity, exact frozen
   loader class, and exact `M_pre` origin. For every `M_pre` row it opens the
   path no-follow relative to FD 8, retains the regular FD, and verifies its
   type/size/hash and retains the source FD until process exit. This post-start
   check detects drift but does not prove bytes that already executed. It then
   sets FDs 3 through 11 non-inheritable and proves the state;
7. verifies the entry-preloaded non-filesystem, `E_fs`/`M_pre`,
   later-builtin, later-frozen, `SEED`, `LATE`, and protected-runtime name sets
   and parent-package relations above. It
   replaces `sys.path` with an empty list, clears the path importer cache,
   removes `PathFinder` and every path/zip finder, wraps the builtin/frozen
   finders with the two exact approval-bound name tables, and installs one
   manifest-backed finder for `LATE` rows only. Every later path, finder, hook,
   cache, retained-`PRELOADED`/`SEED` object, or module-name-table mutation
   fails;
8. for each `LATE` `.py`, the finder opens every component relative to FD 8/9
   with no-follow semantics, retains the regular FD, hashes before execution,
   reads exact bytes with `pread`, calls builtin `compile`, and executes those
   bytes. For each `LATE` `.so`, it hashes and retains the regular FD before the
   same `_imp` procfd dynamic-load path. `SourceFileLoader`,
   `SourcelessFileLoader`, `ExtensionFileLoader`, path reopen,
   `spec_from_file_location(path)`, zip, namespace, `.pyc`, and an unlisted
   transitive import are forbidden. Protected-runtime source FDs remain open
   until process exit;
9. uses only those retained-FD imports to validate the remaining access flags,
   blocking/alias predicates, exact cwd/environment, approval relations,
   interpreter/closure facts, preloaded-module origins, and protected-runtime
   manifest. CPython's interpreter image, dynamic ELF closure, and preloaded
   `encodings` modules executed before the first bootstrap statement remain an
   externally approved launcher prerequisite; a post-start hash is drift
   detection, not pre-loader protection;
10. rechecks exact argv bytes, proves session-parent, target-cwd, and target
    path arguments identify held FD 7, FD 5, and FD 6, confirms the signal mask
    is still empty and `SIGCHLD` still default, then imports and calls the
    private POSIX adapter exactly once.

Recorder keeps `SIGCHLD` default. Immediately before transport writes it
confirms Python's `SIGPIPE` ignore state so pipe loss is an `EPIPE`, not an
asynchronous process death. `Popen(..., restore_signals=True)` must restore
target `SIGPIPE` to default. A native target fixture must observe an empty mask,
default `SIGCHLD`, `SIGTERM`, and `SIGPIPE`, and its actual exit 7 must be
reported as 7 rather than zero.

### Linux protected-root provisioning prerequisite

The external native deployment adapter is a separate, static non-PIE x86-64
ELF object. The launcher audits the held bytes with checked unsigned arithmetic
before `execveat`. The only accepted ELF header has:

- exact ELF magic, `ELFCLASS64`, `ELFDATA2LSB`, `EV_CURRENT`,
  `ELFOSABI_SYSV`, ABI version zero, and zero `e_ident` padding;
- `e_type=ET_EXEC`, `e_machine=EM_X86_64`, `e_version=EV_CURRENT`,
  `e_flags=0`, `e_ehsize=64`, `e_phentsize=56`, and `e_phnum=2..64` without
  extended numbering;
- `e_phoff>=64`, with the complete program-header table inside the held file
  and no addition or multiplication overflow; and
- no section-header table:
  `e_shoff=e_shentsize=e_shnum=e_shstrndx=0`.

Only `PT_LOAD`, `PT_PHDR`, `PT_TLS`, `PT_GNU_STACK`, and `PT_GNU_RELRO` program
headers are allowed. There are `1..16` `PT_LOAD` rows, exactly one
`PT_GNU_STACK`, and at most one of each other allowed type. `PT_INTERP`,
`PT_DYNAMIC`, every unknown type, and therefore every dynamic tag or
`DT_NEEDED` are absent. Every header has only `PF_R|PF_W|PF_X` flag bits.
Every file/memory endpoint is checked for overflow; each positive file range is
inside the held file.

`PT_LOAD` rows are strictly increasing by both file offset and virtual address,
have nonoverlapping positive file ranges and nonoverlapping raw memory ranges,
`0<p_filesz<=p_memsz`, `p_align=4096`, both `p_offset` and `p_vaddr` exactly
4096-aligned, and `p_paddr=p_vaddr`. For each load the audited kernel mapping
interval is `[p_vaddr, align_up(p_vaddr+p_memsz, 4096))`, using checked
arithmetic. Those page intervals are pairwise disjoint. Every load is readable;
no load is both writable and executable. At least one is executable, and
`e_entry` lies in exactly one readable executable load's file-backed interval.
`PT_PHDR`, when present, describes exactly the program-header table,
has `p_offset=e_phoff`, `p_filesz=p_memsz=e_phnum*56`, `p_align=8`, and exactly
`PF_R`. Its virtual/physical address is the load-address translation of the
table bytes inside one readable `PT_LOAD`. `PT_TLS`, when present, has exactly
`PF_R`, `p_filesz<=p_memsz`, a power-of-two alignment in `1..4096`, and
`p_paddr=p_vaddr`. Its file template and complete memory interval lie inside
one readable non-executable load, and its offset/address pair is that load's
exact translation. `PT_GNU_RELRO`, when present, has exactly `PF_R`,
`0<p_filesz=p_memsz`, `p_align=1`, and `p_paddr=p_vaddr`; its offset/address
pair and complete interval lie inside one readable non-executable load.
`PT_GNU_STACK` has exactly `PF_R|PF_W`, zero
offset/address/file/memory sizes, and alignment 16. The audited runtime page
size is exactly 4096.

The adapter file is regular, single-link, non-setuid and non-setgid. Its exact
dev/ino/hash must match the externally selected approval. Dynamic adapter
loading, ambient shared libraries, `LD_*`, PATH, or an installed dependency are
outside V1. The launcher itself and the Python interpreter dynamic ELF closure
remain operator-trust prerequisites and cannot be locally self-authorized.

REC-020 forbids a project-authored SHA-256 implementation. The external native
launcher and static adapter use an operator-approved upstream OpenSSL SHA-256
implementation; the adapter links that implementation statically and therefore
still has no `PT_INTERP` or `DT_NEEDED`. It uses the fixed low-level
`SHA256_Init`/`SHA256_Update`/`SHA256_Final` path and loads no OpenSSL config or
provider. Algorithm names, constants, digest lengths, and providers are not
selected from the approval, wheel, environment, or candidate input. AF_ALG, a
command-line hashing tool, shell delegation, and a repository-local fallback
are forbidden. Conformance compares empty input, NIST known-answer vectors,
one-byte updates, boundary chunking, maximum records, and large wheel/member
streams against independent Python `hashlib.sha256`.

Immediately before adapter `execveat`, the external launcher freezes:

| FD | Exact deployment role |
|---:|---|
| 0 | read-only `/dev/null` |
| 1 | blocking deployment-report pipe, write end |
| 2 | separate blocking stderr-capture pipe, write end |
| 3 | approval record, regular read-only, offset zero |
| 4 | approved wheel, regular read-only, offset zero |
| 5 | approved final-parent directory |
| 6 | approved control directory |
| 7 | transient approved adapter executable, `FD_CLOEXEC` |

There is no other FD. The launcher creates a fork child with empty pending
signals, applies the same empty-mask/default-disposition/disabled-alt-stack
profile as the runtime launcher, maps the table, `fchdir(6)`, sets
`umask(077)`, closes `8..UINT_MAX` with `CLOSE_RANGE_UNSHARE`, and calls:

```text
execveat(7, "", argv, [], AT_EMPTY_PATH)
```

The only adapter argv is:

```text
<APPROVED_NATIVE_ADAPTER_ARGV0_BYTES>
deploy
--approval-sha256
<64-lowercase-hex-H>
```

The environment has zero entries. Adapter `main` must observe exactly FDs
`0..6`; FD 3/4 offsets remain zero; cwd dev/ino equals FD 6; and every
type/access/blocking/seekability/alias predicate matches. It sets FDs 3..6
non-inheritable immediately. Before any filesystem mutation, it independently
validates the empty signal mask, default catchable dispositions,
`SIGCHLD=SIG_DFL`, and absent `SA_NOCLDWAIT|SA_NOCLDSTOP`. It then sets its own
`SIGPIPE=SIG_IGN` so a broken report pipe yields a counted write error. The
final parent/name, wheel hash, expected runtime digests, and every deployment
decision come only from FD 3/4 and the held FD 5; argv, cwd, stdin, environment,
and wheel members cannot override them.

After adapter `main` begins, every controlled result except report-channel
failure attempts exactly one fixed-order ASCII JSON object plus one LF on FD 1
and writes zero bytes to FD 2. The field set/order is:

```json
{"approval_record_sha256":null,"exit_code":64,"final_identity":null,"final_root_hex":null,"post_publish_identity_confirmed":false,"published":false,"reason_id":"INVALID_INVOCATION","schema_version":"AegisRecorderPosixDeploymentReport.v1","staging_identity":null,"staging_name_hex":null,"status":"FAILED"}
```

A non-null identity is exactly:

```json
{"st_dev_hex":"<16-lowercase-hex>","st_ino_hex":"<16-lowercase-hex>"}
```

There is no whitespace, BOM, non-ASCII byte, alternate escape, extra field, or
second line. `approval_record_sha256` is argv `H` after syntax acceptance,
otherwise null. `final_root_hex` becomes the exact approved hex only after the
record hash and grammar pass. Staging name/identity become non-null only after
their create/open observations. `published` is true only when `renameat2`
returns success, never because a name exists. `final_identity` preserves any
successfully reopened final dev/ino, including a mismatch.
`post_publish_identity_confirmed` is true only after staging/final identity,
complete final membership, and parent `fsync` all pass. `status="SUCCEEDED"`
iff exit 0, reason `DEPLOYED`, `published=true`, and post-publication identity
is confirmed; every healthy-channel nonzero exit has `status="FAILED"` and the
same numeric `exit_code` as the process wait status.

Exact adapter exits are:

| Exit | Allowed reason |
|---:|---|
| 0 | `DEPLOYED` |
| 1 | `APPROVAL_INVALID`, `APPROVAL_MISMATCH`, `PLATFORM_UNSUPPORTED`, `FD_CONTRACT_INVALID`, `CREDENTIAL_CONTRACT_INVALID`, `SIGNAL_CONTRACT_INVALID`, `WHEEL_INVALID`, `STAGING_FAILED`, `PUBLISH_FAILED`, `PUBLISHED_IDENTITY_UNCONFIRMED`, `PARENT_FSYNC_FAILED` |
| 64 | `INVALID_INVOCATION` |
| 70 | `INTERNAL_FAILURE` |
| 74 | no report object; `REPORT_CHANNEL_FAILED` is the launcher-side classification |

The adapter evaluates one frozen precedence. It first validates FD 1 enough to
support a report; failure is immediate 74. It then selects, in order:
invocation grammar; complete FD table/identity/access; credential state;
signal state;
approval grammar and H; approval-to-held-object relations; platform/syscall/
OpenSSL/mount capabilities; complete wheel; randomness/staging/extraction and
prepublication rechecks; no-replace rename; final reopen/identity/membership;
parent fsync; success. The corresponding reasons are respectively
`INVALID_INVOCATION`, `FD_CONTRACT_INVALID`, `CREDENTIAL_CONTRACT_INVALID`
then `SIGNAL_CONTRACT_INVALID`, `APPROVAL_INVALID`, `APPROVAL_MISMATCH`,
`PLATFORM_UNSUPPORTED`,
`WHEEL_INVALID`, `STAGING_FAILED`, `PUBLISH_FAILED`,
`PUBLISHED_IDENTITY_UNCONFIRMED`, `PARENT_FSYNC_FAILED`, and `DEPLOYED`.
An unexpected contained defect is `INTERNAL_FAILURE`; it never substitutes for
a known branch. Once rename succeeds, every later failure reports
`published=true`. A report write/close failure overrides the intended result
only with process exit 74 and no report object.

Exit 74 is used only for FD 1 type/direction failure or terminal-report
zero-progress, short/error, or close failure. Captured stdout may be any exact
prefix, including empty or complete, of the intended row; the launcher never
parses exit-74 bytes as a report. Exit 70 is accepted only with one complete
canonical row whose embedded exit code is 70. No retry, second channel, stderr
fallback, or fabricated suffix exists. Adapter image/ELF/`execveat` failure
before `main` is an external-launcher result, not an invented adapter report.

The protected root is provisioned only by the approval-bound external native
deployment adapter. Recorder does not ship or self-authorize that adapter; it
ships only a conformance harness. The adapter runs on a distribution-native
filesystem and reads the approved wheel through a held regular-file
descriptor. It accepts only the deterministic `ZIP_STORED` wheel frozen in
`IMPLEMENTATION_PLAN_FINAL.md`. It independently cursor-parses EOCD, central,
and local headers and requires one disk, exact member count/order, UTF-8-only
flag, method 0, zero extra/comment fields, no data descriptor/encryption/ZIP64,
matching local/central name/CRC32/size/offset facts, nonoverlapping bounded
member ranges, EOCD ending at physical EOF, and every frozen path/mode/time/
`RECORD` relation. It applies the plan's exact 64-MiB physical/uncompressed,
512-member, 16-MiB member, and 512-byte path limits with checked unsigned
arithmetic before allocation. CRC32 is only a ZIP structural check; approved
wheel/member SHA-256 values remain the content bindings. Unknown flags,
duplicate or overlapping ranges, a trailing byte, or any parser arithmetic
overflow fails before staging creation.

After complete wheel validation, the adapter obtains exactly 16 kernel-random
bytes through a counted `getrandom(..., GRND_NONBLOCK)` loop. `EINTR` retries
the unchanged remainder; zero progress, `EAGAIN`, or any other error fails
without an unbounded entropy wait. The only staging name is
`.aegis-staging-` plus those 16 bytes as 32 lowercase hexadecimal characters.
One `mkdirat(..., 0700)` create-new attempt is made beneath the held
final-parent dirfd; collision is `STAGING_FAILED`, with no retry, deletion, or
fallback to time/PID, `/dev/urandom`, a PRNG, or caller input. Every allowlisted
regular file is create-new with `O_NOFOLLOW`, fully written, `fsync`ed,
reopened, reread, and rehashed. Every directory is enumerated and `fsync`ed.
Links, devices, extras, `.pyc`, `__pycache__`, `.dist-info`, scripts,
type/size/hash drift, and a pre-existing final name fail closed.

Publication is exactly:

```text
renameat2(
  held_final_parent,
  staging_name,
  held_final_parent,
  final_name,
  RENAME_NOREPLACE)
```

No `rename` or replacement fallback exists. After success, the adapter reopens
the final name relative to the held parent with no-follow semantics, requires
its `(st_dev, st_ino)` to equal the retained pre-rename staging directory,
rehashes the complete final member snapshot, and `fsync`s the final parent.
Only that sequence returns `DEPLOYED`. A post-publication mismatch is
`PUBLISHED_IDENTITY_UNCONFIRMED`, `published=true`, and failure. No failure
deletes, replaces, repairs, rolls back, or reuses staging/final state.

Linux has no held-directory-FD rename-source API equivalent to the Windows
handle-source operation: `renameat2` selects `staging_name` relative to the
parent. The retained staging FD detects a substituted source after publication
but cannot prevent a same-UID substitution race. This is an explicit
validation-only boundary, never a same-user security claim.

After provisioning, the runtime proxy performs no protected-root write. The
clean pre-launch, first launch, and second launch snapshots must contain the
identical recursive member name/type/size/hash set, and those launches must
create no `.pyc` or `__pycache__`. This is a bounded three-snapshot check. It
does not claim general filesystem write protection or prevent same-user
replacement outside the inspected gates.

The installed `aegis-recorder` console entry and ordinary
`python -m aegis_recorder` entry expose only `verify` and `validate-report` on
every OS. They never dispatch `proxy` or `posix-proxy`, never import the
private POSIX adapter, and never re-exec into it. On every OS, either public
proxy request exits with exactly:

| Platform and public condition | Exit | stdout | stderr |
|---|---:|---|---|
| POSIX public `proxy` or `posix-proxy`, with any suffix including `--help` | 64 | empty | `aegis-recorder: POSIX proxy requires the protected bootstrap` plus LF |
| Windows public `proxy` or `posix-proxy`, with any suffix including `--help` | 64 | empty | `aegis-recorder: Windows proxy requires the protected bootstrap` plus LF |

Each stderr row is ASCII and contains exactly one final LF. The Windows row is
the same public `proxy` diagnostic frozen by `SUPERVISOR_CONTRACT.md`;
`posix-proxy` cannot create a public-parser bypass on Windows.

After the bootstrap's first statement, every controlled private-entry result
before the output-isolation boundary is:

| Condition | Exit | stdout | stderr |
|---|---:|---|---|
| missing, extra, reordered, repeated, noncanonical, or otherwise invalid protected argv | 64 | empty | empty |
| failed CPython/flag, argv-byte, interpreter/bootstrap, import-provenance, protected-root, target/cwd, executable-identity, environment, or fixed-descriptor preflight before session creation | 10 | empty | empty |
| session-directory creation or any journal create, lock, header append, entry append, offset check, directory `fsync`, or journal `fsync` failure through durable `CHILD_SPAWN_REQUESTED` | 11 | empty | empty |

Every contained exception before the first session-directory `mkdir` maps to
class 10 unless the argv grammar already selected class 64. Every contained
exception from that first `mkdir` attempt through the successful
`CHILD_SPAWN_REQUESTED` durability call maps to class 11. Neither path emits a
traceback, exception representation, candidate-controlled path, errno text,
JSON, warning, logging fallback, or locale-dependent bytes.

Interpreter image loading, bootstrap opening/decoding, syntax failure, or
another failure before the first bootstrap statement is an external launcher
precondition. Recorder assigns it no exit class and makes no stdout/stderr
claim.

One bootstrap process may call the private adapter once and may attempt one
session name. The create-new session directory is the duplicate-start gate.
Concurrent or later invocation with the same `--session-dir` observes the
existing name, exits class 11 with empty stdout/stderr, never attaches,
resumes, repairs, deletes, or chooses another name, and never starts a second
target. A failed attempt that created the directory also reserves that name
for explicit operator inspection. Independent absent session names are
independent invocations.

The output-isolation boundary occurs immediately after
`CHILD_SPAWN_REQUESTED` is durably flushed and before `Popen` is called. From
that boundary until process exit:

- Recorder stdout contains only exact target-stdout bytes relayed under the
  journal protocol;
- Recorder stderr contains only exact target-stderr bytes relayed under the
  journal protocol;
- the Recorder emits no usage, diagnostic, traceback, status JSON, or final
  status suffix to either stream;
- a failed spawn with no target-produced bytes therefore leaves both streams
  empty;
- control details are journal entries when the journal remains usable, and the
  final process status is only the exit class.

Post-boundary proxy exit classes are `0 CLEAN`, `11 JOURNAL_FAILED`,
`12 SPAWN_OR_CONTAINMENT_FAILED`, `13 FRAMING_FAILED`,
`14 TRANSPORT_FAILED_OR_UNKNOWN`, `15 CHILD_NONZERO`, and
`16 SUPERVISION_FAILED`. The first fatal cause wins; an unconfirmed
termination forces class 16. Class 10 and class 64 are impossible after the
boundary. No class, bootstrap invocation, successful run, or local evidence
promotes this adapter above `POSIX_CPTHON_3_12_VALIDATION`; it never satisfies
the Windows production profile or external authority.

## 2. Supported path and descriptor profile

The proxy accepts one absolute, absent `--session-dir`. It splits the path into
an existing session-parent directory and one session-name component. The session
name must match:

```text
[A-Za-z0-9][A-Za-z0-9._-]{0,127}
```

Empty names, separators, `.` and `..` are rejected. The session parent must
already exist, be owned by the effective user, and have no group or other
write bit. The implementation never resolves the session or journal again by
an absolute string after it has retained their directory/file descriptors.

Before creation, the accepted argument is encoded with the active filesystem
encoding and `surrogateescape`; a bytes argument is retained unchanged. Those
exact absolute POSIX bytes become the `session_path` `OsStringIdentity` in
`SESSION_STARTED`. `session_path_sha256` is computed with
`SESSION_PATH_DOMAIN` from the journal protocol. `realpath`, decoded display
text, and any later alternate Windows or WSL `/mnt` spelling used to locate a
copied artifact are never hash inputs. The retained descriptor identities
below establish namespace continuity; the path digest establishes only
cross-artifact identity.

Every component from `/` through the session parent is opened one component at a
time relative to the retained parent descriptor with:

```text
O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW
```

For each opened component, `fstat(fd)` and
`stat(name, dir_fd=parent_fd, follow_symlinks=False)` must identify the same
directory `(st_dev, st_ino)`. A symlink, non-directory, changed identity,
unsupported `O_NOFOLLOW`/`dir_fd`, or failed check stops before session
creation. The final opened session-parent identity must equal inherited FD 7.
Mount points are allowed only on the approved native filesystem and their
device/inode transitions are recorded. The retained-descriptor walk prevents
later operations from following a replacement path string; it does not
establish authority against the same user, administrator, kernel, or storage
device.

The three proxy data descriptors must be distinct FIFOs or sockets, blocking,
and direction-compatible. A TTY, regular file, shared descriptor, text
wrapper, nonblocking descriptor, or failed descriptor check is rejected before
target spawn. All relay I/O uses `os.read` and `os.write` on bytes.

## 3. Create-new namespace and journal

The session directory is created relative to the retained session-parent
descriptor FD 7:

```python
os.mkdir(session_name, 0o700, dir_fd=session_parent_fd)
```

`FileExistsError` is terminal. No existing directory is reused. The new
directory is immediately opened with
`O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW`. Its `fstat` result must be a
directory, have the effective UID, have no group/other permission, and match
the no-follow parent-directory lookup.

The journal is opened relative to the retained session descriptor:

```text
name  = journal.aegisrec
flags = O_WRONLY | O_APPEND | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW
mode  = 0600
```

`O_TRUNC` is forbidden. Absence of any required flag is unsupported. The
returned descriptor must be non-inheritable. `fstat` must prove a regular file,
effective-user ownership, mode no broader than `0600`, and `st_nlink == 1`.
The no-follow directory lookup must match its device/inode.

The Writer then obtains:

```python
fcntl.flock(journal_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
```

The create-new namespace is the primary single-writer gate. The lock detects
an implementation or operator that illegally reopens the new journal. Failure
to acquire it stops before any child launch.

## 4. Directory and file persistence order

Before target spawn, the following calls must return successfully in order:

1. create the session directory;
2. `fsync(session_parent_fd)` to persist its directory entry;
3. open and validate the retained session-directory descriptor;
4. create and validate the journal;
5. write the complete fixed journal header through the sole counted append
   path;
6. `fsync(journal_fd)`;
7. `fsync(session_dir_fd)` to persist the journal name;
8. append and `fsync(journal_fd)` the complete `SESSION_STARTED` entry;
9. append and `fsync(journal_fd)` `CHILD_SPAWN_REQUESTED`.

No `fdatasync`, Python buffered file, implicit flush, close-only persistence,
or directory-path reopen substitutes for these calls. Successful `fsync`
means only that the OS call returned success. It does not prove physical media,
controller-cache, WSL host-filesystem, power-loss, or independent-authority
durability.

Every later committed entry follows:

```text
verify expected append offset
→ counted os.write loop on the O_APPEND descriptor
→ verify resulting offset
→ os.fsync(journal_fd)
```

The journal lock covers sequence allocation, previous digest, append
timestamps, expected offset, all `os.write` calls for one entry, and its
`fsync`. It is released before any pipe I/O, process wait, signal, deadline
wait, or relay join.

## 5. Write and fsync errors

For a nonempty remainder:

- a positive `os.write` result advances the exact accepted count;
- a zero result is a fatal zero-progress failure;
- `EINTR` means the failing call transferred no bytes and may be retried;
- a returned short positive count is retained and the remainder is written;
- `EPIPE`, `EAGAIN`, `EWOULDBLOCK`, `EBADF`, `EIO`, `ENOSPC`, `EDQUOT`, or any
  other error ends that write loop;
- the exact accepted prefix is the sum of prior positive return values;
- a destination failure becomes `FORWARD_FAILED` only with that exact prefix;
- no failed or unresolved observation is retried or replayed.

`SIGPIPE` is ignored in the Recorder process so that `EPIPE` is observed and
journalled rather than terminating the process asynchronously.

Any journal zero write, short-write loop failure, offset mismatch, write
exception, `fsync` exception, directory-`fsync` exception, or lock failure
poisons the journal. `fsync` errors, including `EINTR`, are not converted into
success by a retry. After poison:

- no new transport operation starts;
- no clean terminal entry is attempted;
- emergency process-group containment may proceed without evidence;
- the proxy exits nonzero;
- the Verifier can claim only the observable last valid prefix, partial-tail
  structure, and missing lifecycle terminals. It never infers a persistence
  failure cause or a persistence-specific reason from the absent suffix.

Closing errors are reported by the proxy. They cannot rewrite a previously
committed entry or synthesize a new clean entry.

## 6. Spawn boundary

The requested target argv-zero and cwd remain the exact absolute POSIX byte
paths from the protected grammar. Execution and cwd selection use the held
FD 6 and FD 5 objects, not those strings. V1 accepts only a native ELF target;
scripts and shebang dispatch are unsupported. `shell=True`, PATH search,
`preexec_fn`, candidate cwd, inherited `PYTHONPATH`/`PYTHONHOME`, and implicit
environment inheritance are forbidden.

After durable `CHILD_SPAWN_REQUESTED`, the adapter calls `Popen` with:

```text
args=[requested_target_bytes, *requested_arg_bytes]
executable=b"/proc/self/fd/6"
shell=False
cwd=b"/proc/self/fd/5"
env={b"LC_ALL": b"C"}
stdin/stdout/stderr=<owned binary pipes>
close_fds=True
pass_fds=(5, 6)
start_new_session=True
restore_signals=True
text=False
bufsize=0
```

`start_new_session=True` requires `setsid()` before target execution. The
direct target therefore starts as session leader and process-group leader with
`pgid == pid`. `preexec_fn` is forbidden because the Recorder is
multithreaded. Only descriptors 0, 1, 2, 5, and 6 reach the target entry;
bootstrap, protected runtime, session parent, stdlib, approval record, and
journal descriptors do not. The target can observe its inherited cwd and
executable capability descriptors; that is a deliberate validation-profile
tradeoff required to bind `Popen` without a pathname reopen.

On `Popen` exception, the Writer records `CHILD_SPAWN_FAILED` when the journal
remains usable. On return, it verifies `pid > 1`, `pid != getpid()`,
`pid != getpgrp()`, and `getpgid(pid) == pid` while the target is live, then
records `CHILD_SPAWNED` with `containment_type=POSIX_PROCESS_GROUP`. A target
that exits before `getpgid` is still a completed spawn; its wait status is
collected and the inability to observe the live group is recorded.

The durable `CHILD_SPAWNED` atomically activates exactly the three protocol
pairs `CLIENT_TO_SERVER`, `SERVER_TO_CLIENT`, and `CHILD_STDERR`. POSIX has no
per-pair or independent open result. Before that entry, physical descriptors
may exist but no protocol relay read, write, or logical close may begin.

A crash after `Popen` returns and before a durable spawn terminal leaves a
spawn attempt with unknown outcome. It is never auto-retried. POSIX v1 has no
independent guard and cannot reclaim that process after the Recorder itself
dies.

## 7. Runtime and termination state machine

States:

```text
PRE_SPAWN
→ SPAWN_UNKNOWN | RUNNING
→ DRAINING_OUTPUT | TERMINATING
→ KILLING
→ REAPING
→ TERMINATED_CONFIRMED | TERMINATION_UNCONFIRMED
```

Normal direct-target exit enters `DRAINING_OUTPUT`. The adapter stops client
stdin but does not signal the process group. Target stdout and stderr drain to
EOF. An open/cancelled client stdin is a non-clean source terminal even when
its current frame buffer is empty.

Fatal shutdown or drain timeout performs:

1. durably append `TERMINATION_REQUESTED` with reason exactly
   `FATAL_SHUTDOWN` or `DRAIN_TIMEOUT`, matching the state transition that
   selected this path;
2. durably append `CHILD_SIGNAL_ATTEMPT_STARTED` for `SIGTERM`, referencing
   that exact `TERMINATION_REQUESTED`;
3. call `os.killpg(pgid, SIGTERM)`;
4. durably append exactly one `CHILD_SIGNAL_SUCCEEDED` or
   `CHILD_SIGNAL_FAILED`, referencing both the same
   `TERMINATION_REQUESTED` and its signal attempt;
5. wait at most five monotonic seconds for target exit and group disappearance;
6. if the group remains, durably append `KILL_REQUESTED` with reason
   `SIGTERM_GRACE_EXPIRED`;
7. durably append a `CHILD_SIGNAL_ATTEMPT_STARTED` for `SIGKILL`, referencing
   that exact `KILL_REQUESTED`;
8. call `os.killpg(pgid, SIGKILL)`;
9. durably append exactly one `CHILD_SIGNAL_SUCCEEDED` or
   `CHILD_SIGNAL_FAILED`, referencing both the same `KILL_REQUESTED` and its
   signal attempt;
10. reap the direct child;
11. spend at most two additional monotonic seconds confirming both direct-child
   reaping and `killpg(pgid, 0) -> ESRCH`.

Every request and attempt above is committed and `fsync`-complete before its
following signal call. A returned `os.killpg` result always receives its
terminal entry before another journalled lifecycle operation starts.
`CHILD_SIGNAL_SUCCEEDED` means only that `os.killpg` returned success; process
exit and group disappearance remain separate observations. `ESRCH`, `EPERM`,
and every other `os.killpg` exception produce `CHILD_SIGNAL_FAILED` with
`POSIX:<unsigned-decimal-errno>`. A process crash or journal poison may leave a
durable request or attempt without its terminal, but then `SESSION_ENDED` is
forbidden and the Verifier reports the corresponding not-attempted or
unknown-outcome state.

Before every group signal, `pgid` must equal the recorded direct-target PID,
be greater than 1, and differ from the Recorder process group. `ESRCH` is
recorded as group-not-observed; it is not silently converted into proof that
all historical descendants exited. `EPERM` and other errors are failures.

If the journal is poisoned, the same `SIGTERM`/`SIGKILL` containment may occur
without new entries. Its effects are not claimed by the journal and clean
shutdown is forbidden.

`TERMINATED_CONFIRMED` requires:

- the direct target has been reaped;
- the process group was observed absent inside the confirmation window;
- all relay threads returned;
- each relay closed only its own descriptors.

Otherwise the outcome is `TERMINATION_UNCONFIRMED`, proxy class 16, with no
clean session claim.

## 8. POSIX limits

A process group is weaker than a Windows kill-on-close Job:

- a descendant can call `setsid()` or change process group and escape;
- Recorder death does not automatically kill the group;
- PID/PGID reuse cannot be ruled out indefinitely;
- `kill` and `wait` kernel-call duration is outside a Python hard guarantee;
- WSL filesystem flush remains an OS-return-only boundary.

The POSIX adapter therefore validates portable protocol, relay, persistence,
and ordinary process-group behavior. It cannot satisfy the Windows production
containment gate or external authority.

## 9. Required tests

Tests use a WSL-native filesystem, not `/mnt/c`, for protected deployment and
session evidence.

- missing external launcher/approval record, a caller- or repository-selected
  expected digest, and every unsupported syscall/filesystem/profile fail before
  staging, session creation, or target launch; no fallback exists;
- the trust-slot selector is instrumented to prove it never reads
  candidate-facing argv, env, stdin, cwd, config, record path/ID/hash, wheel
  path, adapter path, interpreter path, final parent, or final name; direct
  invocation and a candidate-created identical record cannot produce a
  launcher-accepted result;
- the canonical direct-`P` layout is executed from the held CPython FD with the
  one-line `python3.12._pth`. An out-of-band syscall tracer identifies the
  bootstrap's first fixed FD-enumeration probe without adding a child FD and
  proves no earlier `write(2)` byte. The first statement observes
  `sys.path == [stdlib_root]`, every frozen prefix/executable/stdlib value, and
  exactly the three filesystem-backed `encodings` objects;
- missing `python3.12._pth`, an extra/reordered/comment/`import site`/blank/
  whitespace line, CRLF, BOM, NUL, missing final LF, wrong identity/size/hash/
  owner/mode/link count, either `pyvenv.cfg`, either build marker, or a
  competing ELF-closure `._pth` candidate is rejected before `execveat`.
  replacement still present when the bootstrap reopens the approved getpath
  file is detected by its identity/byte/hash recheck and cannot produce a
  PASS. A separate change-and-restore fixture supplies a comment-prefixed but
  getpath-equivalent file for CPython's pathname read, restores the approved
  inode/bytes before reopen, and proves that all local observations may still
  match. That fixture must be reported as an external-boundary demonstration;
  it cannot be labelled pathname-continuity detection or a security PASS;
- CPython patch-version, interpreter digest, PLATLIBDIR, VPATH, direct-`P`
  layout, prefix, executable, `_stdlib_dir`, or initial-path drift is rejected.
  An extra stdlib `os.py` fails exact membership, and later `os` can be served
  only by the approval-bound frozen finder;
- zero/root or mismatched runtime UID/GID, any supplementary group, a
  non-root-owned external trust object/ancestor, group/other write permission,
  successful runtime-credential `W_OK`, a set-id/file-capability executable,
  nonempty process capabilities, or absent `no_new_privs` fails before
  adapter mutation or runtime exec; bootstrap `/proc/self/status` mutations
  cover each UID/GID slot, exact `Groups:\t \n` row, `posix.getgroups()`,
  every capability field, duplicate/missing row, malformed number, CR/NUL,
  missing LF, truncation, and wrong `NoNewPrivs`;
- caller-created or changed user/mount namespaces, wrong namespace dev/ino,
  missing procfs namespace objects, or namespace values influenced by
  candidate-facing input fail before trust-path acceptance or bootstrap import;
- approval and stdlib-manifest tests reject BOM, CRLF, non-ASCII, NUL,
  whitespace, trailing bytes, missing/duplicate/reordered/unknown fields,
  wrong record size/count, uppercase/odd/invalid hex, noncanonical decimal,
  overflow, invalid path components, inconsistent protected-root derivation,
  invalid module/package/extension/stage mappings, missing or non-package
  dotted parents, missing/extra/wrong-origin `PRELOADED` rows, missing/duplicate
  `SEED`, builtin/frozen/preloaded/protected-runtime finder collisions,
  deletion/replacement of retained preloaded objects, finder service of a
  `PRELOADED` row, unsorted/duplicate/extra manifest rows, and every size/count
  limit breach;
- ELF-closure manifest tests reject wrong interpreter/hash-seed/loader
  relations, missing/shared/duplicate/unlisted resolved dependencies, duplicate
  basenames, `RPATH`/`RUNPATH`, loader preload/audit state, wrong size/hash/
  dev/ino, and every grammar/order/limit violation;
- the native adapter ELF audit mutates every frozen `e_ident`/ELF-header field,
  table count/size/range, section-table-zero predicate, allowed program-header
  type/count/flags/order/alignment/range relation, raw and page-rounded load
  overlap including the half-page replacement vector, entry mapping,
  `PT_PHDR`, `PT_TLS`, `PT_GNU_RELRO`, and exact non-executable
  `PT_GNU_STACK`; it also rejects `ET_DYN`, `PT_INTERP`, `PT_DYNAMIC`, unknown
  headers, set-id bits, link count, overflow, and out-of-file ranges. A positive
  fixture passes the audit and executes from its held FD;
- native hashing conformance rejects project-authored/AF_ALG/command/provider
  selection paths and exercises fixed statically linked OpenSSL SHA-256 against
  independent known-answer and streamed-boundary oracles;
- staging-name tests inject `getrandom` EINTR, short positive returns, zero,
  hard errors, deterministic bytes, and a pre-existing collision; only the
  counted exact 16-byte/lowercase-hex name is attempted and no fallback/retry
  namespace is created;
- wheel tests mutate every accepted EOCD/central/local relation, flag, method,
  CRC, size, offset, range overlap, count/order, path, mode/time, `RECORD` row,
  ZIP64/data-descriptor/encryption marker, extra/comment, and trailing byte;
  every case fails before `getrandom` or staging creation;
- adapter conformance fixes pre-exec FDs `0..7`, post-exec FDs `0..6`, empty
  environment, cwd FD 6, offset-zero `pread` inputs, static held-object exec,
  exact report rows, and exits 0/1/64/70/74. Report loss before byte zero, at
  every interior offset, after a complete-looking prefix, and on close is exit
  74 with empty stderr and never a report object;
- external probes cover `openat2` symlink/magic-link rejection,
  `faccessat2(AT_EMPTY_PATH | AT_EACCESS)` runtime-write rejection,
  `statx(AT_EMPTY_PATH, STATX_MNT_ID)` to exact mountinfo `ext4` binding,
  `execveat(AT_EMPTY_PATH)`, fixed procfd bootstrap execution, `close_range`,
  `getrandom`, and `renameat2(RENAME_NOREPLACE)`;
- mountinfo tests reject missing/duplicate/mismatched mount IDs, malformed
  separators or decimal fields, missing LF, CR/NUL, oversized files/lines,
  non-`ext4` types, wrong `fstatfs` magic, and mount-ID change between the
  adapter's pre-mutation and pre-publication observations;
- the exact `execveat` plus `/proc/self/fd/3` bootstrap form is the only entry
  that can call the private POSIX adapter or launch a target;
- installed console and ordinary module requests for `proxy` and
  `posix-proxy`, including `--help`, reject before private-adapter import with
  exact exit/stdout/stderr bytes on POSIX; the existing Windows public
  diagnostic remains byte-exact;
- missing, extra, reordered, repeated, or ambiently substituted
  `-I -S -B -X utf8`, relative interpreter/bootstrap/target, option aliases,
  `=` spelling, response files, an option after `--`, and a missing `--` are
  rejected before Recorder import or session creation as applicable;
- `sys.orig_argv` byte fixtures cover empty target arguments, spaces, tabs,
  non-ASCII UTF-8, undecodable bytes round-tripped through
  `surrogateescape`, leading hyphens after `--`, and distinct byte sequences
  with similar display text; journal identities retain the exact
  `os.fsencode` bytes;
- `PYTHONPATH`, `PYTHONHOME`, user-site, current-directory, script-directory,
  and candidate-directory shadow packages cannot supply `aegis_recorder` or a
  standard-library dependency;
- the launcher environment is exactly `LC_ALL=C`; empty or extra environments,
  locale coercion to `LC_CTYPE`, `PATH`, `HOME`, `PYTHON*`, and `LD_*` fail;
- every missing, extra, aliased, writable, nonblocking, wrong-direction, or
  wrong-type fixed descriptor fails; bootstrap, runtime, target cwd/executable,
  session parent, stdlib, stdlib manifest, and approval identities must equal
  their held FDs; wrong seekability, shared offset, entry offset, or CLOEXEC
  state also fails and every `pread` leaves offset zero;
- native `getdents64` and CPython `posix.listdir` FD probes cover missing,
  extra, duplicate, nonnumeric, reordered, unexpectedly persistent probe, and
  wrong next-FD cases at all four pre/post-exec observation points;
- inherited `SIGCHLD=SIG_IGN`, `SA_NOCLDWAIT`, `SA_NOCLDSTOP`, a blocked
  `SIGCHLD`/`SIGTERM`, a custom `SIGTERM` handler, nonempty pending set, or
  alternate stack fails before session creation. The preflight child must reap
  with its exact PID/status; a native target exit 7 must remain 7, never the
  `ECHILD`-derived zero used by CPython;
- missing/extra protected-root members, wrong hash/size/type, symlink,
  case collision, bytecode/cache, forbidden standard-library origin,
  unlisted runtime import, and path mutation fail before Recorder import;
- replacing a bootstrap/runtime source pathname after open still executes the
  retained bytes; an observed in-place modification of the retained inode
  fails its repeated hash check;
- before the externally approved `_hashlib` seed loads, a spy permits no new
  filesystem import; the exact three already-loaded `encodings` source objects
  must match their `PRELOADED` rows and remain identity-pinned. After the seed
  loads, every `LATE` stdlib `.py` and `.so` is hashed before execution from a
  retained FD; replacing its pathname cannot change executed bytes. Any later
  `SourceFileLoader`, `SourcelessFileLoader`,
  `ExtensionFileLoader`, ordinary pathname reopen, zip/namespace loader, or
  unlisted transitive import fails. Tests separately retain the honest boundary
  that the getpath file, seed, Python ELF closure, and preloaded encodings are
  external prerequisites rather than locally proved pre-loader facts;
- pre-existing final, rename competitor, source substitution, final reopen
  mismatch, member drift, and parent-`fsync` failure never return `DEPLOYED`;
  every post-rename uncertainty is `published=true` failure with no cleanup;
- the clean pre-launch, first-launch, and second-launch protected-root
  snapshots are identical; both launches create no bytecode or cache path,
  while a mutation outside the inspected gates remains outside the claim;
- simultaneous and sequential starts using one session name produce exactly
  one create-new winner and at most one target; every loser is class 11 with
  empty stdout/stderr and leaves the existing session untouched;
- every malformed argv class, pre-session preflight failure, and journal-setup
  failure matches the exact exit/stdout/stderr table;
- after durable `CHILD_SPAWN_REQUESTED`, injected spawn, journal, framing,
  transport, child-return, and supervision failures add no Recorder byte to
  stdout or stderr; observed outputs equal only relayed target bytes;
- every private POSIX run journals
  `platform_profile=POSIX_CPTHON_3_12_VALIDATION`; public rejected requests
  create no session or journal, and no POSIX run can produce a Windows
  production-profile claim;
- every ancestor is opened no-follow by descriptor;
- symlink in every path position is rejected;
- existing session and existing journal are rejected;
- journal hard-link count other than one is rejected;
- second process fails the nonblocking lock;
- header-file-directory `fsync` order is witnessed by injected call records;
- each write and `fsync` failure poisons before later forwarding;
- positive partial write plus `EPIPE` records the exact prefix;
- a `Popen` spy requires the exact frozen bytes call, and the target observes
  only descriptors 0/1/2/5/6, cwd inode FD 5, executable object FD 6, empty
  signal mask, and default target `SIGCHLD`/`SIGTERM`/`SIGPIPE`;
- child verifies `getsid(0) == getpid()` and `getpgrp() == getpid()`;
- normal fast exit drains final stdout/stderr bytes;
- SIGTERM-compliant child is reaped without SIGKILL;
- SIGTERM-ignoring child and same-group descendant receive SIGKILL;
- `TERMINATION_REQUESTED` is durable before the SIGTERM attempt, and the
  attempt and terminal reference that exact request;
- `KILL_REQUESTED` is durable before the SIGKILL attempt, and the attempt and
  terminal reference that exact request;
- crash points after each request, attempt, and signal return preserve the
  distinct not-attempted, unknown-outcome, and complete-terminal states;
- escaped-session descendant demonstrates the declared containment limit and
  cannot produce a production PASS;
- Recorder hard-kill after spawn attempt leaves unknown spawn evidence and no
  automatic replay;
- confirmation timeout returns class 16 and never claims disappearance.
- a same-UID write after the last verification gate is an explicit unprotected
  demonstration and cannot be labelled a security PASS.

## 10. Informative source provenance

The byte contracts and predicates above are complete and normative. The URLs
below are reviewer navigation only: no live or cached web content is
incorporated by reference, and later changes at those URLs cannot change this
contract. A fact imported from an external source must be restated above and
covered by a frozen implementation test before it can affect acceptance.

- POSIX `open`: https://pubs.opengroup.org/onlinepubs/9699919799/functions/open.html
- POSIX `write`: https://pubs.opengroup.org/onlinepubs/9699919799/functions/write.html
- POSIX `fsync`: https://pubs.opengroup.org/onlinepubs/9699919799/functions/fsync.html
- POSIX `kill`: https://pubs.opengroup.org/onlinepubs/9699919799/functions/kill.html
- Linux `openat2`: https://man7.org/linux/man-pages/man2/openat2.2.html
- Linux `faccessat2`:
  https://man7.org/linux/man-pages/man2/access.2.html
- Linux `statx`: https://man7.org/linux/man-pages/man2/statx.2.html
- Linux mount information:
  https://man7.org/linux/man-pages/man5/proc_pid_mountinfo.5.html
- Linux `execveat`: https://man7.org/linux/man-pages/man2/execveat.2.html
- Linux `close_range`:
  https://man7.org/linux/man-pages/man2/close_range.2.html
- Linux `getdents64`:
  https://man7.org/linux/man-pages/man2/getdents.2.html
- Linux `getrandom`:
  https://man7.org/linux/man-pages/man2/getrandom.2.html
- Linux `renameat2`: https://man7.org/linux/man-pages/man2/renameat2.2.html
- Linux procfs file descriptors:
  https://man7.org/linux/man-pages/man5/proc_pid_fd.5.html
- Linux signals: https://man7.org/linux/man-pages/man7/signal.7.html
- Linux `waitpid`: https://man7.org/linux/man-pages/man2/waitpid.2.html
- Linux `PR_SET_NO_NEW_PRIVS`:
  https://man7.org/linux/man-pages/man2/PR_SET_NO_NEW_PRIVS.2const.html
- Linux capabilities:
  https://man7.org/linux/man-pages/man7/capabilities.7.html
- OpenSSL SHA-256:
  https://docs.openssl.org/master/man3/SHA256_Init/
- Python 3.12 command line:
  https://docs.python.org/3.12/using/cmdline.html
- CPython 3.12.3 frozen getpath algorithm:
  https://github.com/python/cpython/blob/v3.12.3/Modules/getpath.py
- Python 3.12 subprocess:
  https://docs.python.org/3.12/library/subprocess.html
