from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import subprocess
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterator
from uuid import uuid4

from aegis_seal_core import SealContext, compute_project_seal, verify_project_seal
from path_security import (
    PathSecurityError,
    StablePathSpec,
    hold_paths_stable,
    read_regular_file,
)
from runtime_behavior_scope import (
    SCOPE_POLICY_RELATIVE_PATH,
    RuntimeBehaviorScopeError,
    resolve_runtime_behavior_scope,
    runtime_behavior_path_is_selected,
)
from runtime_identity import (
    RuntimeIdentityError,
    hold_verified_git_runtime,
    trusted_git_environment,
)


SEAL_RECORD_RELATIVE_PATH = Path(
    ".aegis/reasoning_ledger/artifacts/facts/project-seal.json"
)
SEAL_CHAIN_SCHEMA = "aegis.project_seal_chain.v2"

_HEX_16_PATTERN = re.compile(r"[0-9a-f]{32}")
_HEX_32_PATTERN = re.compile(r"[0-9a-f]{64}")
_GIT_HEAD_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_SEAL_PATTERN = re.compile(r"ASC1:[0-9a-f]{64}")
_RECORD_FIELDS = {
    "project_id_hex",
    "seal_chain_id_hex",
    "sequence",
    "previous_seal_hex",
    "expected_seal",
    "created_at_utc",
    "git_head_before_record",
    "scope_policy_version",
    "scope_policy_sha256",
    "resolved_manifest_sha256",
    "runtime_authority_id",
}


class ProjectSealStoreError(RuntimeError):
    pass


class ProjectSealMismatchError(ProjectSealStoreError):
    pass


Runner = Callable[..., subprocess.CompletedProcess[bytes]]
_FALLBACK_LOCKS: dict[str, threading.Lock] = {}
_FALLBACK_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True, slots=True)
class StoredProjectSeal:
    project_id: bytes
    seal_chain_id: bytes
    sequence: int
    previous_seal: bytes
    expected_seal: str
    created_at_utc: str
    git_head_before_record: str
    scope_policy_version: int
    scope_policy_sha256: str
    resolved_manifest_sha256: str
    runtime_authority_id: str

    @property
    def context(self) -> SealContext:
        return SealContext(
            project_id=self.project_id,
            seal_chain_id=self.seal_chain_id,
            sequence=self.sequence,
            previous_seal=self.previous_seal,
        )

    def as_json_data(self) -> dict[str, object]:
        return {
            "project_id_hex": self.project_id.hex(),
            "seal_chain_id_hex": self.seal_chain_id.hex(),
            "sequence": self.sequence,
            "previous_seal_hex": self.previous_seal.hex(),
            "expected_seal": self.expected_seal,
            "created_at_utc": self.created_at_utc,
            "git_head_before_record": self.git_head_before_record,
            "scope_policy_version": self.scope_policy_version,
            "scope_policy_sha256": self.scope_policy_sha256,
            "resolved_manifest_sha256": self.resolved_manifest_sha256,
            "runtime_authority_id": self.runtime_authority_id,
        }


@dataclass(frozen=True, slots=True)
class ProjectSealChain:
    records: tuple[StoredProjectSeal, ...]


def seal_record_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / SEAL_RECORD_RELATIVE_PATH


def load_project_seal_chain(project_root: str | Path) -> ProjectSealChain:
    root = Path(project_root).resolve()
    path = seal_record_path(root)
    try:
        encoded, _identity = read_regular_file(
            path,
            allowed_root=root,
            label="project seal record",
            max_bytes=4 * 1024 * 1024,
        )
        payload = json.loads(encoded.decode("utf-8", errors="strict"))
    except PathSecurityError as error:
        raise ProjectSealStoreError(str(error)) from error
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ProjectSealStoreError(
            f"project seal record cannot be read: {path}: {error}"
        ) from error

    if not isinstance(payload, dict) or set(payload) != {"schema", "records"}:
        raise ProjectSealStoreError("project seal record has invalid top-level fields")
    if payload["schema"] != SEAL_CHAIN_SCHEMA:
        raise ProjectSealStoreError("project seal record has an unsupported schema")
    raw_records = payload["records"]
    if not isinstance(raw_records, list) or not raw_records:
        raise ProjectSealStoreError("project seal chain must contain at least one record")

    records = tuple(
        _parse_record(raw_record, index)
        for index, raw_record in enumerate(raw_records)
    )
    _validate_chain(records)
    return ProjectSealChain(records)


def record_project_seal(
    project_root: str | Path,
    *,
    git_head_before_record: str,
    project_id: bytes | None = None,
    seal_chain_id: bytes | None = None,
    runner: Runner = subprocess.run,
    git_executable: str | None = None,
) -> StoredProjectSeal:
    root = Path(project_root).resolve()
    if _GIT_HEAD_PATTERN.fullmatch(git_head_before_record) is None:
        raise ValueError("git_head_before_record must be a lowercase SHA-1 or SHA-256")

    with _project_seal_lock(root):
        path = seal_record_path(root)
        if path.exists():
            chain = load_project_seal_chain(root)
            last = chain.records[-1]
            if project_id is not None and project_id != last.project_id:
                raise ValueError("project_id cannot change within a seal chain")
            if seal_chain_id is not None and seal_chain_id != last.seal_chain_id:
                raise ValueError("seal_chain_id cannot change within a seal chain")
            context = SealContext(
                project_id=last.project_id,
                seal_chain_id=last.seal_chain_id,
                sequence=last.sequence + 1,
                previous_seal=bytes.fromhex(last.expected_seal.removeprefix("ASC1:")),
            )
            previous_records = chain.records
        else:
            if project_id is None:
                raise ValueError("project_id is required when creating a seal chain")
            context = SealContext(
                project_id=project_id,
                seal_chain_id=(
                    seal_chain_id if seal_chain_id is not None else uuid4().bytes
                ),
            )
            previous_records = ()

        resolved_scope = resolve_runtime_behavior_scope(root, context.project_id)
        actual_head = _verify_scope_matches_git_commit(
            root,
            context.project_id,
            resolved_scope.entries,
            policy_sha256=resolved_scope.policy_sha256,
            expected_git_sha256=resolved_scope.git_sha256,
            expected_git_runtime_sha256=resolved_scope.git_runtime_sha256,
            runner=runner,
            git_executable=git_executable,
        )
        if actual_head != git_head_before_record:
            raise ProjectSealStoreError(
                "git_head_before_record does not match the repository HEAD"
            )
        if previous_records:
            last = previous_records[-1]
            if resolved_scope.policy_version < last.scope_policy_version:
                raise ProjectSealStoreError("runtime scope policy version regressed")
            if (
                resolved_scope.policy_sha256 != last.scope_policy_sha256
                and resolved_scope.policy_version <= last.scope_policy_version
            ):
                raise ProjectSealStoreError(
                    "changed runtime scope policy requires a higher version"
                )
        expected_seal = compute_project_seal(context, resolved_scope.seal_entries())
        record = StoredProjectSeal(
            project_id=context.project_id,
            seal_chain_id=context.seal_chain_id,
            sequence=context.sequence,
            previous_seal=context.previous_seal,
            expected_seal=expected_seal,
            created_at_utc=_utc_now_text(),
            git_head_before_record=actual_head,
            scope_policy_version=resolved_scope.policy_version,
            scope_policy_sha256=resolved_scope.policy_sha256,
            resolved_manifest_sha256=resolved_scope.manifest_sha256,
            runtime_authority_id=resolved_scope.runtime_authority_id,
        )
        _atomic_write_chain(path, (*previous_records, record))
        return record


def verify_expected_project_seal(
    project_root: str | Path,
    *,
    git_executable: str | None = None,
    git_runtime_lock_held: bool = False,
) -> StoredProjectSeal:
    root = Path(project_root).resolve()
    record = load_project_seal_chain(root).records[-1]
    resolved_scope = resolve_runtime_behavior_scope(root, record.project_id)
    if not git_runtime_lock_held:
        git = git_executable or shutil.which("git")
        if not git:
            raise ProjectSealMismatchError("git executable is unavailable")
        try:
            with hold_verified_git_runtime(
                git,
                expected_launcher_sha256=resolved_scope.git_sha256,
                expected_runtime_sha256=resolved_scope.git_runtime_sha256,
            ) as locked_git:
                with _hold_repository_git_inputs(root):
                    return verify_expected_project_seal(
                        root,
                        git_executable=locked_git,
                        git_runtime_lock_held=True,
                    )
        except RuntimeIdentityError as error:
            raise ProjectSealMismatchError(str(error)) from error
    if (
        resolved_scope.policy_version != record.scope_policy_version
        or resolved_scope.policy_sha256 != record.scope_policy_sha256
        or resolved_scope.manifest_sha256 != record.resolved_manifest_sha256
        or resolved_scope.runtime_authority_id != record.runtime_authority_id
    ):
        raise ProjectSealMismatchError(
            f"project runtime behavior scope does not match the recorded seal: {root}"
        )
    if not verify_project_seal(
        record.context, resolved_scope.seal_entries(), record.expected_seal
    ):
        raise ProjectSealMismatchError(
            f"project source does not match the recorded seal: {root}"
        )
    try:
        actual_head = _verify_scope_matches_git_commit(
            root,
            record.project_id,
            resolved_scope.entries,
            policy_sha256=resolved_scope.policy_sha256,
            expected_git_sha256=resolved_scope.git_sha256,
            expected_git_runtime_sha256=resolved_scope.git_runtime_sha256,
            runner=subprocess.run,
            git_executable=git_executable,
            git_runtime_lock_held=True,
        )
    except ProjectSealStoreError as error:
        raise ProjectSealMismatchError(str(error)) from error
    if actual_head != record.git_head_before_record:
        raise ProjectSealMismatchError(
            "repository HEAD differs from the commit bound to the project seal"
        )
    return record


@contextmanager
def hold_verified_project_git_runtime(
    project_root: str | Path,
    *,
    git_executable: str | None = None,
) -> Iterator[str]:
    """Hold the project-authorized Git runtime immutable across related checks."""
    root = Path(project_root).resolve()
    record = load_project_seal_chain(root).records[-1]
    try:
        resolved_scope = resolve_runtime_behavior_scope(root, record.project_id)
    except RuntimeBehaviorScopeError as error:
        raise ProjectSealStoreError(str(error)) from error
    git = git_executable or shutil.which("git")
    if not git:
        raise ProjectSealStoreError("git executable is unavailable")
    try:
        with hold_verified_git_runtime(
            git,
            expected_launcher_sha256=resolved_scope.git_sha256,
            expected_runtime_sha256=resolved_scope.git_runtime_sha256,
        ) as locked_git:
            with _hold_repository_git_inputs(root, include_witness_inputs=True):
                yield locked_git
    except RuntimeIdentityError as error:
        raise ProjectSealStoreError(str(error)) from error


def _parse_record(value: Any, index: int) -> StoredProjectSeal:
    if not isinstance(value, dict) or set(value) != _RECORD_FIELDS:
        raise ProjectSealStoreError(f"seal record {index} has invalid fields")

    project_id_hex = _require_pattern(
        value["project_id_hex"], _HEX_16_PATTERN, "project_id_hex", index
    )
    seal_chain_id_hex = _require_pattern(
        value["seal_chain_id_hex"],
        _HEX_16_PATTERN,
        "seal_chain_id_hex",
        index,
    )
    previous_seal_hex = _require_pattern(
        value["previous_seal_hex"], _HEX_32_PATTERN, "previous_seal_hex", index
    )
    expected_seal = _require_pattern(
        value["expected_seal"], _SEAL_PATTERN, "expected_seal", index
    )
    git_head = _require_pattern(
        value["git_head_before_record"],
        _GIT_HEAD_PATTERN,
        "git_head_before_record",
        index,
    )
    sequence = value["sequence"]
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise ProjectSealStoreError(f"seal record {index} has an invalid sequence")
    scope_policy_version = value["scope_policy_version"]
    if (
        isinstance(scope_policy_version, bool)
        or not isinstance(scope_policy_version, int)
        or scope_policy_version < 1
    ):
        raise ProjectSealStoreError(
            f"seal record {index} has an invalid scope_policy_version"
        )
    scope_policy_sha256 = _require_pattern(
        value["scope_policy_sha256"],
        _HEX_32_PATTERN,
        "scope_policy_sha256",
        index,
    )
    resolved_manifest_sha256 = _require_pattern(
        value["resolved_manifest_sha256"],
        _HEX_32_PATTERN,
        "resolved_manifest_sha256",
        index,
    )
    runtime_authority_id = _require_pattern(
        value["runtime_authority_id"],
        _HEX_16_PATTERN,
        "runtime_authority_id",
        index,
    )
    created_at_utc = value["created_at_utc"]
    if not isinstance(created_at_utc, str) or not created_at_utc.endswith("Z"):
        raise ProjectSealStoreError(
            f"seal record {index} has an invalid created_at_utc"
        )
    try:
        datetime.fromisoformat(created_at_utc.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise ProjectSealStoreError(
            f"seal record {index} has an invalid created_at_utc"
        ) from error

    try:
        return StoredProjectSeal(
            project_id=bytes.fromhex(project_id_hex),
            seal_chain_id=bytes.fromhex(seal_chain_id_hex),
            sequence=sequence,
            previous_seal=bytes.fromhex(previous_seal_hex),
            expected_seal=expected_seal,
            created_at_utc=created_at_utc,
            git_head_before_record=git_head,
            scope_policy_version=scope_policy_version,
            scope_policy_sha256=scope_policy_sha256,
            resolved_manifest_sha256=resolved_manifest_sha256,
            runtime_authority_id=runtime_authority_id,
        )
    except ValueError as error:
        raise ProjectSealStoreError(f"seal record {index} is invalid: {error}") from error


def _require_pattern(
    value: Any, pattern: re.Pattern[str], field: str, index: int
) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ProjectSealStoreError(f"seal record {index} has an invalid {field}")
    return value


def _validate_chain(records: tuple[StoredProjectSeal, ...]) -> None:
    first = records[0]
    if first.sequence != 0 or first.previous_seal != bytes(32):
        raise ProjectSealStoreError(
            "first seal record must use sequence zero and a zero previous seal"
        )
    for index, record in enumerate(records):
        if record.sequence != index:
            raise ProjectSealStoreError("seal sequence must be contiguous from zero")
        if (
            record.project_id != first.project_id
            or record.seal_chain_id != first.seal_chain_id
            or record.runtime_authority_id != first.runtime_authority_id
        ):
            raise ProjectSealStoreError(
                "project_id and seal_chain_id must remain fixed"
            )
        if index == 0:
            continue
        expected_previous = bytes.fromhex(records[index - 1].expected_seal[5:])
        if record.previous_seal != expected_previous:
            raise ProjectSealStoreError(
                f"seal record {index} previous seal does not match record {index - 1}"
            )


def _atomic_write_chain(
    path: Path, records: tuple[StoredProjectSeal, ...]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(
            {
                "schema": SEAL_CHAIN_SCHEMA,
                "records": [record.as_json_data() for record in records],
            },
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _verify_scope_matches_git_commit(
    root: Path,
    project_id: bytes,
    entries: tuple[Any, ...],
    *,
    policy_sha256: str,
    expected_git_sha256: str,
    expected_git_runtime_sha256: str,
    runner: Runner,
    git_executable: str | None,
    git_runtime_lock_held: bool = False,
) -> str:
    git = git_executable or shutil.which("git")
    if not git:
        raise ProjectSealStoreError("git executable is unavailable")
    if not git_runtime_lock_held:
        try:
            with hold_verified_git_runtime(
                git,
                expected_launcher_sha256=expected_git_sha256,
                expected_runtime_sha256=expected_git_runtime_sha256,
            ) as locked_git:
                with _hold_repository_git_inputs(root):
                    return _verify_scope_matches_git_commit(
                        root,
                        project_id,
                        entries,
                        policy_sha256=policy_sha256,
                        expected_git_sha256=expected_git_sha256,
                        expected_git_runtime_sha256=expected_git_runtime_sha256,
                        runner=runner,
                        git_executable=locked_git,
                        git_runtime_lock_held=True,
                    )
        except RuntimeIdentityError as error:
            raise ProjectSealStoreError(str(error)) from error
    try:
        git_environment = trusted_git_environment(git)
    except RuntimeIdentityError as error:
        raise ProjectSealStoreError(str(error)) from error
    git_prefix = _trusted_local_git_prefix(git, root)
    head = _run_git_bytes(
        runner,
        [*git_prefix, "rev-parse", "--verify", "HEAD^{commit}"],
        "read repository HEAD",
        environment=git_environment,
        working_directory=root,
    ).decode("ascii", errors="strict").strip()
    if _GIT_HEAD_PATTERN.fullmatch(head) is None:
        raise ProjectSealStoreError("repository HEAD is not a canonical commit ID")

    changed = set(
        _nul_paths(
            _run_git_bytes(
                runner,
                [
                    *git_prefix,
                    "diff",
                    "--no-ext-diff",
                    "--no-textconv",
                    "--name-only",
                    "-z",
                    "HEAD",
                    "--",
                ],
                "read tracked working-tree changes",
                environment=git_environment,
                working_directory=root,
            )
        )
    )
    changed.update(
        _nul_paths(
            _run_git_bytes(
                runner,
                [
                    *git_prefix,
                    "ls-files",
                    "--others",
                    "--exclude-standard",
                    "-z",
                ],
                "read untracked working-tree files",
                environment=git_environment,
                working_directory=root,
            )
        )
    )
    dirty_scoped = sorted(
        path
        for path in changed
        if runtime_behavior_path_is_selected(root, project_id, path)
    )
    if dirty_scoped:
        raise ProjectSealStoreError(
            "runtime behavior scope contains uncommitted paths: "
            + ", ".join(dirty_scoped)
        )

    for entry in entries:
        committed_bytes = _run_git_bytes(
            runner,
            [*git_prefix, "cat-file", "blob", f"{head}:{entry.path}"],
            f"read committed runtime file {entry.path}",
            environment=git_environment,
            working_directory=root,
        )
        try:
            working_bytes, _identity = read_regular_file(
                root / entry.path,
                allowed_root=root,
                label=f"runtime file {entry.path}",
                max_bytes=512 * 1024 * 1024,
            )
        except PathSecurityError as error:
            raise ProjectSealStoreError(str(error)) from error
        if (
            working_bytes != committed_bytes
            or len(committed_bytes) != entry.size
            or hashlib.sha256(committed_bytes).hexdigest() != entry.sha256
        ):
            raise ProjectSealStoreError(
                f"runtime file bytes differ from repository HEAD: {entry.path}"
            )

    policy_bytes = _run_git_bytes(
        runner,
        [
            *git_prefix,
            "cat-file",
            "blob",
            f"{head}:{SCOPE_POLICY_RELATIVE_PATH.as_posix()}",
        ],
        "read committed runtime scope policy",
        environment=git_environment,
        working_directory=root,
    )
    try:
        policy = json.loads(policy_bytes.decode("utf-8", errors="strict"))
        canonical_policy = json.dumps(
            policy,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ProjectSealStoreError(
            "committed runtime scope policy is invalid JSON"
        ) from error
    if hashlib.sha256(canonical_policy).hexdigest() != policy_sha256:
        raise ProjectSealStoreError(
            "runtime scope policy does not match the repository HEAD"
        )
    return head


def _run_git_bytes(
    runner: Runner,
    command: list[str],
    description: str,
    *,
    environment: dict[str, str],
    working_directory: Path,
) -> bytes:
    try:
        completed = runner(
            command,
            capture_output=True,
            text=False,
            cwd=working_directory,
            env=environment,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ProjectSealStoreError(f"{description} failed: {error}") from error
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace")
        raise ProjectSealStoreError(
            f"{description} failed: exit_code={completed.returncode}, stderr={stderr!r}"
        )
    return completed.stdout


def _trusted_local_git_prefix(git: str, root: Path) -> list[str]:
    return [
        git,
        "--no-pager",
        f"--git-dir={root / '.git'}",
        f"--work-tree={root}",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=NUL",
        "-c",
        "core.attributesFile=NUL",
        "-c",
        "protocol.file.allow=never",
    ]


@contextmanager
def _hold_repository_git_inputs(
    root: Path,
    *,
    include_witness_inputs: bool = False,
) -> Iterator[None]:
    git_directory = root / ".git"
    specs = [
        StablePathSpec(
            path=git_directory,
            allowed_root=root,
            label="repository Git metadata root",
            directory=True,
        )
    ]
    candidates = [
        git_directory / "HEAD",
        git_directory / "config",
        git_directory / "config.worktree",
        git_directory / "index",
        git_directory / "packed-refs",
        git_directory / "shallow",
        git_directory / "commondir",
        git_directory / "gitdir",
        git_directory / "info" / "grafts",
        git_directory / "objects" / "info" / "alternates",
    ]
    refs = git_directory / "refs"
    if refs.is_dir():
        candidates.extend(path for path in refs.rglob("*") if path.is_file())
    if include_witness_inputs:
        candidates.extend(
            (
                root / "config" / "seal_witness.json",
                root / "config" / "git_ssh_known_hosts",
            )
        )
    for path in candidates:
        if path.is_file():
            specs.append(
                StablePathSpec(
                    path=path,
                    allowed_root=root,
                    label="repository Git control input",
                )
            )
    try:
        with hold_paths_stable(specs):
            if not include_witness_inputs or not (
                root / "config" / "seal_witness.json"
            ).is_file():
                yield
                return
            identity_spec = _sealed_ssh_identity_spec(root)
            with hold_paths_stable((identity_spec,)):
                yield
    except PathSecurityError as error:
        raise ProjectSealStoreError(str(error)) from error


def _sealed_ssh_identity_spec(root: Path) -> StablePathSpec:
    config_path = root / "config" / "seal_witness.json"
    try:
        content, _identity = read_regular_file(
            config_path,
            allowed_root=root,
            label="remote seal witness config",
            max_bytes=1024 * 1024,
        )
        config = json.loads(content.decode("utf-8", errors="strict"))
        identity = config["ssh_identity"]
        identity_path_value = identity["path"]
    except (PathSecurityError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ProjectSealStoreError(
            "remote seal witness SSH identity descriptor cannot be locked"
        ) from error
    if not isinstance(identity_path_value, str):
        raise ProjectSealStoreError(
            "remote seal witness SSH identity descriptor cannot be locked"
        )
    identity_path = Path(identity_path_value)
    if not identity_path.is_absolute():
        raise ProjectSealStoreError(
            "remote seal witness SSH identity path must be absolute"
        )
    return StablePathSpec(
        path=identity_path,
        allowed_root=Path(identity_path.anchor),
        label="sealed SSH identity file",
    )


def _nul_paths(value: bytes) -> tuple[str, ...]:
    try:
        return tuple(
            part.decode("utf-8", errors="strict").replace("\\", "/")
            for part in value.split(b"\0")
            if part
        )
    except UnicodeError as error:
        raise ProjectSealStoreError("Git returned a non-UTF-8 path") from error


@contextmanager
def _project_seal_lock(root: Path) -> Iterator[None]:
    lock_key = hashlib.sha256(str(root).casefold().encode("utf-8")).hexdigest()
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel32.WaitForSingleObject.restype = ctypes.c_uint32
        kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
        kernel32.ReleaseMutex.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        handle = kernel32.CreateMutexW(
            None, False, f"Local\\AegisProjectSeal-{lock_key}"
        )
        if not handle:
            raise ProjectSealStoreError("cannot create project seal mutex")
        wait_result = kernel32.WaitForSingleObject(handle, 120_000)
        if wait_result not in {0x00000000, 0x00000080}:
            kernel32.CloseHandle(handle)
            raise ProjectSealStoreError("timed out acquiring project seal mutex")
        try:
            yield
        finally:
            kernel32.ReleaseMutex(handle)
            kernel32.CloseHandle(handle)
        return

    with _FALLBACK_LOCKS_GUARD:
        lock = _FALLBACK_LOCKS.setdefault(lock_key, threading.Lock())
    if not lock.acquire(timeout=120):
        raise ProjectSealStoreError("timed out acquiring project seal lock")
    try:
        yield
    finally:
        lock.release()


def _utc_now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
