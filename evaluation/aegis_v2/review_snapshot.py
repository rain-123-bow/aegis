from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import rfc8785


class ReviewSnapshotError(Exception):
    """The snapshot or its bound repository/bundle state is invalid."""


@dataclass(frozen=True, slots=True)
class BundleIntegrityResult:
    """Offline bundle integrity result; it grants no review authority."""

    snapshot_content_id: str
    integrity_valid: bool
    git_provenance_state: str
    live_verification_state: str
    authorization_state: str


@dataclass(frozen=True, slots=True)
class LiveVerificationReceipt:
    """One point-in-time live verification boundary receipt."""

    boundary: str
    snapshot_content_id: str
    verification_started_at_utc: str
    verification_completed_at_utc: str
    repository_root_identity: dict[str, int | str]
    continuous_observation: bool
    authority_state: str
    persistence_state: str
    authorization_state: str


_SCHEMA_VERSION = "ReviewSnapshot.v1"
_SNAPSHOT_DOMAIN = b"AEGIS_REVIEW_SNAPSHOT_V1\x00"
_FILE_AGGREGATE_DOMAIN = (
    b"AEGIS_REVIEW_SNAPSHOT_FILE_AGGREGATE_V1\x00"
)
_GATE_WIDE_GIT_STATE_AGGREGATE_DOMAIN = (
    b"AEGIS_REVIEW_SNAPSHOT_GATE_WIDE_GIT_STATE_AGGREGATE_V1\x00"
)
_REVIEW_SUBJECT_STATE = "READY_FOR_FINAL_REVIEW"
_REVIEW_SUBJECT_STATUS_LINE = (
    b"Status: `READY_FOR_FINAL_REVIEW`"
)
_REVIEW_PROTOCOL = {
    "review_type": "FIRST_PRINCIPLES_IMPLEMENTATION_PLAN_REVIEW",
    "pass_condition": {
        "P0": 0,
        "P1": 0,
    },
    "live_verify_required_at": [
        "REVIEW_START",
        "REVIEW_END",
    ],
    "hash_mismatch_disposition": "INVALID_REVIEW",
    "implementation_or_test_execution_claims_allowed": False,
}
_REPOSITORY_EVIDENCE_COMMANDS = (
    (
        "GIT_ALLOWLIST_PATHSPEC_CACHED_DIFF_BINARY_V1",
        ("diff", "--cached", "--binary"),
        "allowlist_cached_diff_binary_sha256",
    ),
    (
        "GIT_ALLOWLIST_PATHSPEC_INDEX_LISTING_S_Z_V1",
        ("ls-files", "-s", "-z"),
        "allowlist_index_listing_s_z_sha256",
    ),
    (
        "GIT_ALLOWLIST_PATHSPEC_STATUS_PORCELAIN_V2_Z_V1",
        (
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
        ),
        "allowlist_git_status_porcelain_v2_z_sha256",
    ),
    (
        "GIT_ALLOWLIST_PATHSPEC_TRACKED_DIFF_BINARY_V1",
        ("diff", "--binary"),
        "allowlist_tracked_diff_binary_sha256",
    ),
)
_GATE_WIDE_GIT_STATE_COMMANDS = (
    (
        "GIT_GATE_WIDE_CACHED_DIFF_BINARY_V1",
        ("diff", "--cached", "--binary"),
    ),
    (
        "GIT_GATE_WIDE_INDEX_LISTING_S_Z_V1",
        ("ls-files", "-s", "-z"),
    ),
    (
        "GIT_GATE_WIDE_STATUS_PORCELAIN_V2_Z_V1",
        (
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
        ),
    ),
    (
        "GIT_GATE_WIDE_TRACKED_DIFF_BINARY_V1",
        ("diff", "--binary"),
    ),
)
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?Z$"
)
_GIT_OBJECT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_WINDOWS_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}
_TOP_LEVEL_KEYS = {
    "schema_version",
    "snapshot_instance_id",
    "capture_started_at_utc",
    "capture_completed_at_utc",
    "review_domain",
    "review_subject",
    "review_protocol",
    "files",
    "file_aggregate_sha256",
    "repository_context",
    "repository_evidence",
    "external_normative_sources",
    "snapshot_content_id",
}
_REVIEW_DOMAIN_KEYS = {
    "mode",
    "repository_paths",
    "required_focus_areas",
    "required_absent_paths",
}
_FILE_KEYS = {
    "repository_path",
    "source_kind",
    "byte_size",
    "sha256",
    "head_blob_oid",
    "head_blob_mode",
    "index_blob_oid",
    "index_blob_mode",
    "filesystem_kind",
}
_REPOSITORY_CONTEXT_KEYS = {
    "head_commit",
    "head_tree",
    "branch",
    "git_object_format",
    "gate_wide_git_state_aggregate_sha256",
    "allowlist_git_status_porcelain_v2_z_sha256",
    "allowlist_tracked_diff_binary_sha256",
    "allowlist_cached_diff_binary_sha256",
    "allowlist_index_listing_s_z_sha256",
}
_EXTERNAL_SOURCE_KEYS = {
    "source_id",
    "immutable_locator",
    "media_type",
    "retrieved_at_utc",
    "repository_path",
    "byte_size",
    "sha256",
}
_REVIEW_SUBJECT_KEYS = {
    "repository_path",
    "required_state",
    "observed_state",
}
_REVIEW_PROTOCOL_KEYS = {
    "review_type",
    "pass_condition",
    "live_verify_required_at",
    "hash_mismatch_disposition",
    "implementation_or_test_execution_claims_allowed",
}
_REPOSITORY_EVIDENCE_KEYS = {
    "command_id",
    "byte_size",
    "sha256",
}
_SOURCE_KINDS = {
    "HEAD_BLOB",
    "TRACKED_WORKTREE",
    "WORKTREE_UNTRACKED",
}
_REGULAR_GIT_MODES = {"100644", "100755"}
_MAX_SAFE_INTEGER = (1 << 53) - 1


def _sha256_id(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _canonical_bytes(value: Any, label: str) -> bytes:
    try:
        return rfc8785.dumps(value)
    except Exception as exc:
        raise ReviewSnapshotError(
            f"{label} is not RFC 8785 canonicalizable"
        ) from exc


def _require_exact_keys(
    value: Any,
    expected: set[str],
    label: str,
) -> dict[str, Any]:
    if type(value) is not dict:
        raise ReviewSnapshotError(f"{label} must be an object")
    if set(value) != expected:
        raise ReviewSnapshotError(f"{label} has unexpected or missing keys")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise ReviewSnapshotError(f"{label} must be an array")
    return value


def _require_string(value: Any, label: str) -> str:
    if type(value) is not str:
        raise ReviewSnapshotError(f"{label} must be a string")
    return value


def _require_nonempty_text(
    value: Any,
    label: str,
    *,
    ascii_only: bool = False,
) -> str:
    text = _require_string(value, label)
    if not text:
        raise ReviewSnapshotError(f"{label} must not be empty")
    try:
        encoded = text.encode("ascii" if ascii_only else "utf-8")
    except UnicodeError as exc:
        raise ReviewSnapshotError(f"{label} has invalid text") from exc
    if not encoded or any(byte < 0x20 or byte == 0x7F for byte in encoded):
        raise ReviewSnapshotError(f"{label} contains control characters")
    return text


def _require_size(value: Any, label: str) -> int:
    if type(value) is not int:
        raise ReviewSnapshotError(f"{label} must be an integer")
    if value < 0 or value > _MAX_SAFE_INTEGER:
        raise ReviewSnapshotError(f"{label} is outside the JCS domain")
    return value


def _require_digest(value: Any, label: str) -> str:
    digest = _require_string(value, label)
    if _SHA256_RE.fullmatch(digest) is None:
        raise ReviewSnapshotError(f"{label} is not a canonical SHA-256 id")
    return digest


def _validate_uuid4(value: Any, label: str) -> str:
    text = _require_string(value, label)
    try:
        parsed = uuid.UUID(text)
    except (ValueError, AttributeError) as exc:
        raise ReviewSnapshotError(f"{label} is not a UUID") from exc
    if (
        parsed.version != 4
        or parsed.variant != uuid.RFC_4122
        or str(parsed) != text
    ):
        raise ReviewSnapshotError(f"{label} must be a canonical UUIDv4")
    return text


def _validate_utc(value: Any, label: str) -> datetime:
    text = _require_string(value, label)
    if _UTC_RE.fullmatch(text) is None:
        raise ReviewSnapshotError(f"{label} must be canonical UTC")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ReviewSnapshotError(f"{label} is not a valid timestamp") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ReviewSnapshotError(f"{label} must be UTC")
    return parsed


def _utc_now_text() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _validate_repository_path(value: Any, label: str) -> str:
    path = _require_string(value, label)
    try:
        encoded = path.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ReviewSnapshotError(f"{label} must be ASCII") from exc
    if (
        not encoded
        or path.startswith("/")
        or path.endswith("/")
        or "\\" in path
        or any(byte < 0x20 or byte == 0x7F for byte in encoded)
    ):
        raise ReviewSnapshotError(f"{label} is not a canonical relative path")
    segments = path.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise ReviewSnapshotError(f"{label} is not a canonical relative path")
    for segment in segments:
        if (
            any(character in '<>:"|?*' for character in segment)
            or segment.endswith((" ", "."))
            or segment.casefold() == ".git"
            or segment.split(".", 1)[0].casefold() in _WINDOWS_RESERVED
        ):
            raise ReviewSnapshotError(
                f"{label} is not a portable canonical path"
            )
    return path


def _as_input_list(value: Any, label: str) -> list[Any]:
    if isinstance(value, (str, bytes, bytearray, dict)):
        raise ReviewSnapshotError(f"{label} must be a sequence")
    try:
        return list(value)
    except (TypeError, ValueError) as exc:
        raise ReviewSnapshotError(f"{label} must be a sequence") from exc


def _validate_path_list(
    value: Any,
    label: str,
    *,
    require_nonempty: bool,
    snapshot_value: bool,
) -> list[str]:
    items = (
        _require_list(value, label)
        if snapshot_value
        else _as_input_list(value, label)
    )
    paths = [
        _validate_repository_path(item, f"{label}[{index}]")
        for index, item in enumerate(items)
    ]
    if require_nonempty and not paths:
        raise ReviewSnapshotError(f"{label} must not be empty")
    if paths != sorted(paths, key=lambda item: item.encode("ascii")):
        raise ReviewSnapshotError(f"{label} must be in strict ASCII order")
    folded = [item.casefold() for item in paths]
    if len(set(folded)) != len(folded):
        raise ReviewSnapshotError(f"{label} contains a path collision")
    return paths


def _validate_focus_areas(
    value: Any,
    *,
    snapshot_value: bool,
) -> list[str]:
    label = "review_domain.required_focus_areas"
    items = (
        _require_list(value, label)
        if snapshot_value
        else _as_input_list(value, "required_focus_areas")
    )
    areas = [
        _require_nonempty_text(
            item,
            f"{label}[{index}]",
            ascii_only=True,
        )
        for index, item in enumerate(items)
    ]
    if not areas:
        raise ReviewSnapshotError(f"{label} must not be empty")
    if areas != sorted(areas, key=lambda item: item.encode("ascii")):
        raise ReviewSnapshotError(f"{label} must be in strict ASCII order")
    if len({area.casefold() for area in areas}) != len(areas):
        raise ReviewSnapshotError(f"{label} contains a collision")
    return areas


def _is_same_or_ancestor(
    possible_ancestor: str,
    possible_descendant: str,
) -> bool:
    ancestor_parts = possible_ancestor.casefold().split("/")
    descendant_parts = possible_descendant.casefold().split("/")
    return descendant_parts[: len(ancestor_parts)] == ancestor_parts


def _validate_absence_hierarchy(
    absent_paths: list[str],
    materialized_paths: list[str],
) -> None:
    for index, absent_path in enumerate(absent_paths):
        for other_absent in absent_paths[index + 1 :]:
            if _is_same_or_ancestor(
                absent_path,
                other_absent,
            ) or _is_same_or_ancestor(other_absent, absent_path):
                raise ReviewSnapshotError(
                    "required absent paths have an ancestry collision"
                )
        for materialized_path in materialized_paths:
            if _is_same_or_ancestor(
                absent_path,
                materialized_path,
            ) or _is_same_or_ancestor(materialized_path, absent_path):
                raise ReviewSnapshotError(
                    "a required absent path conflicts with materialized "
                    "review evidence"
                )


def _validate_review_protocol(value: Any) -> dict[str, Any]:
    protocol = _require_exact_keys(
        value,
        _REVIEW_PROTOCOL_KEYS,
        "review_protocol",
    )
    if (
        _require_string(
            protocol["review_type"],
            "review_protocol.review_type",
        )
        != _REVIEW_PROTOCOL["review_type"]
    ):
        raise ReviewSnapshotError("review_protocol.review_type is fixed")
    pass_condition = _require_exact_keys(
        protocol["pass_condition"],
        {"P0", "P1"},
        "review_protocol.pass_condition",
    )
    for severity in ("P0", "P1"):
        if (
            type(pass_condition[severity]) is not int
            or pass_condition[severity] != 0
        ):
            raise ReviewSnapshotError(
                f"review_protocol.pass_condition.{severity} must be zero"
            )
    live_verify = _require_list(
        protocol["live_verify_required_at"],
        "review_protocol.live_verify_required_at",
    )
    if (
        any(type(item) is not str for item in live_verify)
        or live_verify
        != _REVIEW_PROTOCOL["live_verify_required_at"]
    ):
        raise ReviewSnapshotError(
            "review_protocol.live_verify_required_at is fixed"
        )
    if (
        _require_string(
            protocol["hash_mismatch_disposition"],
            "review_protocol.hash_mismatch_disposition",
        )
        != _REVIEW_PROTOCOL["hash_mismatch_disposition"]
    ):
        raise ReviewSnapshotError(
            "review_protocol.hash_mismatch_disposition is fixed"
        )
    claims_allowed = protocol[
        "implementation_or_test_execution_claims_allowed"
    ]
    if type(claims_allowed) is not bool or claims_allowed is not False:
        raise ReviewSnapshotError(
            "review_protocol implementation/test claims must be disabled"
        )
    return protocol


def _validate_review_subject(
    value: Any,
    repository_paths: list[str],
) -> str:
    subject = _require_exact_keys(
        value,
        _REVIEW_SUBJECT_KEYS,
        "review_subject",
    )
    repository_path = _validate_repository_path(
        subject["repository_path"],
        "review_subject.repository_path",
    )
    if repository_path not in repository_paths:
        raise ReviewSnapshotError(
            "review_subject.repository_path is outside the allowlist"
        )
    for field in ("required_state", "observed_state"):
        if (
            _require_string(
                subject[field],
                f"review_subject.{field}",
            )
            != _REVIEW_SUBJECT_STATE
        ):
            raise ReviewSnapshotError(
                f"review_subject.{field} must be "
                f"{_REVIEW_SUBJECT_STATE}"
            )
    return repository_path


def _validate_review_subject_bytes(raw: bytes) -> None:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReviewSnapshotError(
            "review subject must be strict UTF-8"
        ) from exc
    if "\r" in text or not text.endswith("\n"):
        raise ReviewSnapshotError(
            "review subject must use LF and end in LF"
        )
    lines = text.split("\n")
    expected_status = _REVIEW_SUBJECT_STATUS_LINE.decode("ascii")
    if (
        len(lines) < 4
        or not lines[0].startswith("# ")
        or lines[0] == "# "
        or lines[1] != ""
        or lines[2] != expected_status
        or sum(line == expected_status for line in lines) != 1
    ):
        raise ReviewSnapshotError(
            "review subject must have one READY status at machine line 3"
        )


def _is_link_or_reparse(file_stat: os.stat_result) -> bool:
    if stat.S_ISLNK(file_stat.st_mode):
        return True
    attributes = getattr(file_stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse_flag and attributes & reparse_flag)


def _coerce_path(value: Any, label: str) -> Path:
    if not isinstance(value, (str, os.PathLike)):
        raise ReviewSnapshotError(f"{label} must be path-like")
    try:
        return Path(value)
    except (TypeError, ValueError, OSError) as exc:
        raise ReviewSnapshotError(f"{label} is invalid") from exc


def _require_plain_directory(path: Path, label: str) -> None:
    try:
        file_stat = path.lstat()
    except OSError as exc:
        raise ReviewSnapshotError(f"{label} is not accessible") from exc
    if _is_link_or_reparse(file_stat) or not stat.S_ISDIR(file_stat.st_mode):
        raise ReviewSnapshotError(f"{label} must be a plain directory")


def _stat_identity(file_stat: os.stat_result) -> tuple[int, int, int]:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        stat.S_IFMT(file_stat.st_mode),
    )


def _stat_stability(file_stat: os.stat_result) -> tuple[int, ...]:
    return (
        *_stat_identity(file_stat),
        file_stat.st_size,
        getattr(file_stat, "st_mtime_ns", 0),
        getattr(file_stat, "st_ctime_ns", 0),
    )


def _preflight_component(
    path: Path,
    label: str,
    *,
    directory: bool,
) -> os.stat_result:
    try:
        file_stat = path.lstat()
    except OSError as exc:
        raise ReviewSnapshotError(f"{label} is not accessible") from exc
    if _is_link_or_reparse(file_stat):
        raise ReviewSnapshotError(f"{label} traverses a link")
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(file_stat.st_mode):
        kind = "directory" if directory else "regular file"
        raise ReviewSnapshotError(f"{label} must be a {kind}")
    return file_stat


def _posix_open_relative_descriptor(
    root: Path,
    repository_path: str,
    label: str,
    *,
    leaf_directory: bool,
) -> int:
    if (
        os.name != "posix"
        or os.open not in os.supports_dir_fd
        or not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
    ):
        raise ReviewSnapshotError(
            "POSIX descriptor-relative traversal is unavailable"
        )
    root_stat = _preflight_component(
        root,
        f"{label} root",
        directory=True,
    )
    root_flags = (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        root_descriptor = os.open(root, root_flags)
    except OSError as exc:
        raise ReviewSnapshotError(
            f"{label} root cannot be opened safely"
        ) from exc
    descriptors = [root_descriptor]
    try:
        if _stat_identity(os.fstat(root_descriptor)) != _stat_identity(
            root_stat
        ):
            raise ReviewSnapshotError(f"{label} root changed before opening")
        current_path = root
        segments = repository_path.split("/")
        for index, segment in enumerate(segments):
            is_leaf = index == len(segments) - 1
            expect_directory = not is_leaf or leaf_directory
            current_path = current_path / segment
            preflight = _preflight_component(
                current_path,
                label,
                directory=expect_directory,
            )
            flags = (
                os.O_RDONLY
                | os.O_NOFOLLOW
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_BINARY", 0)
            )
            if expect_directory:
                flags |= os.O_DIRECTORY
            try:
                descriptor = os.open(
                    segment,
                    flags,
                    dir_fd=descriptors[-1],
                )
            except OSError as exc:
                raise ReviewSnapshotError(
                    f"{label} cannot be opened safely"
                ) from exc
            descriptors.append(descriptor)
            opened_stat = os.fstat(descriptor)
            if (
                _stat_identity(opened_stat)
                != _stat_identity(preflight)
                or (
                    expect_directory
                    and not stat.S_ISDIR(opened_stat.st_mode)
                )
                or (
                    not expect_directory
                    and not stat.S_ISREG(opened_stat.st_mode)
                )
            ):
                raise ReviewSnapshotError(f"{label} changed before opening")
        leaf_descriptor = descriptors.pop()
        return leaf_descriptor
    except Exception:
        raise
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


class _WindowsByHandleFileInformation(ctypes.Structure):
    _fields_ = [
        ("dwFileAttributes", ctypes.c_ulong),
        ("ftCreationTimeLow", ctypes.c_ulong),
        ("ftCreationTimeHigh", ctypes.c_ulong),
        ("ftLastAccessTimeLow", ctypes.c_ulong),
        ("ftLastAccessTimeHigh", ctypes.c_ulong),
        ("ftLastWriteTimeLow", ctypes.c_ulong),
        ("ftLastWriteTimeHigh", ctypes.c_ulong),
        ("dwVolumeSerialNumber", ctypes.c_ulong),
        ("nFileSizeHigh", ctypes.c_ulong),
        ("nFileSizeLow", ctypes.c_ulong),
        ("nNumberOfLinks", ctypes.c_ulong),
        ("nFileIndexHigh", ctypes.c_ulong),
        ("nFileIndexLow", ctypes.c_ulong),
    ]


def _windows_kernel32() -> Any:
    if os.name != "nt":
        raise ReviewSnapshotError("Windows handle traversal is unavailable")
    try:
        return ctypes.WinDLL("kernel32", use_last_error=True)
    except (AttributeError, OSError) as exc:
        raise ReviewSnapshotError(
            "Windows handle traversal is unavailable"
        ) from exc


def _windows_api_path(path: Path) -> str:
    absolute = os.path.abspath(str(path))
    if absolute.startswith("\\\\?\\"):
        return absolute
    if absolute.startswith("\\\\"):
        return "\\\\?\\UNC\\" + absolute[2:]
    return "\\\\?\\" + absolute


def _windows_open_path_handle(
    path: Path,
    *,
    directory: bool | None,
) -> int:
    kernel32 = _windows_kernel32()
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
    )
    create_file.restype = ctypes.c_void_p
    access = 0x00000080
    if directory is True:
        access |= 0x00000001
    elif directory is False:
        access |= 0x80000000
    flags = 0x00200000
    if directory is not False:
        flags |= 0x02000000
    handle = create_file(
        _windows_api_path(path),
        access,
        0x00000001 | 0x00000002 | 0x00000004,
        None,
        3,
        flags,
        None,
    )
    invalid = ctypes.c_void_p(-1).value
    if handle in {None, invalid}:
        error_number = ctypes.get_last_error()
        if error_number in {2, 3}:
            raise FileNotFoundError(error_number, os.strerror(error_number))
        raise OSError(error_number, os.strerror(error_number), path)
    return int(handle)


def _windows_close_handle(handle: int) -> None:
    kernel32 = _windows_kernel32()
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (ctypes.c_void_p,)
    close_handle.restype = ctypes.c_int
    close_handle(ctypes.c_void_p(handle))


def _windows_handle_information(
    handle: int,
) -> _WindowsByHandleFileInformation:
    kernel32 = _windows_kernel32()
    get_information = kernel32.GetFileInformationByHandle
    get_information.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(_WindowsByHandleFileInformation),
    )
    get_information.restype = ctypes.c_int
    information = _WindowsByHandleFileInformation()
    if not get_information(
        ctypes.c_void_p(handle),
        ctypes.byref(information),
    ):
        error_number = ctypes.get_last_error()
        raise OSError(error_number, os.strerror(error_number))
    return information


def _windows_handle_final_path(handle: int) -> str:
    kernel32 = _windows_kernel32()
    get_final_path = kernel32.GetFinalPathNameByHandleW
    get_final_path.argtypes = (
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
    )
    get_final_path.restype = ctypes.c_ulong
    required = get_final_path(
        ctypes.c_void_p(handle),
        None,
        0,
        0,
    )
    if not required:
        error_number = ctypes.get_last_error()
        raise OSError(error_number, os.strerror(error_number))
    buffer = ctypes.create_unicode_buffer(required + 1)
    written = get_final_path(
        ctypes.c_void_p(handle),
        buffer,
        len(buffer),
        0,
    )
    if not written or written >= len(buffer):
        error_number = ctypes.get_last_error()
        raise OSError(error_number, os.strerror(error_number))
    value = buffer.value
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return os.path.normcase(os.path.abspath(value))


def _windows_validate_handle(
    handle: int,
    expected_path: Path,
    *,
    directory: bool | None,
    label: str,
) -> None:
    information = _windows_handle_information(handle)
    attributes = information.dwFileAttributes
    is_directory = bool(attributes & 0x00000010)
    if (
        attributes & 0x00000400
        or (directory is not None and is_directory != directory)
    ):
        raise ReviewSnapshotError(f"{label} traverses a reparse or wrong kind")
    expected = os.path.normcase(os.path.abspath(str(expected_path)))
    if _windows_handle_final_path(handle) != expected:
        raise ReviewSnapshotError(f"{label} escaped its bound root")


def _windows_open_relative_handle(
    root: Path,
    repository_path: str,
    label: str,
    *,
    leaf_directory: bool,
) -> int:
    handles: list[tuple[int, Path, bool]] = []
    try:
        _preflight_component(root, f"{label} root", directory=True)
        root_handle = _windows_open_path_handle(root, directory=True)
        _windows_validate_handle(
            root_handle,
            root,
            directory=True,
            label=f"{label} root",
        )
        handles.append((root_handle, root, True))
        current_path = root
        segments = repository_path.split("/")
        for index, segment in enumerate(segments):
            is_leaf = index == len(segments) - 1
            expect_directory = not is_leaf or leaf_directory
            current_path = current_path / segment
            _preflight_component(
                current_path,
                label,
                directory=expect_directory,
            )
            handle = _windows_open_path_handle(
                current_path,
                directory=expect_directory,
            )
            _windows_validate_handle(
                handle,
                current_path,
                directory=expect_directory,
                label=label,
            )
            handles.append((handle, current_path, expect_directory))
        for handle, expected_path, directory in handles:
            _windows_validate_handle(
                handle,
                expected_path,
                directory=directory,
                label=label,
            )
        leaf_handle, _, _ = handles.pop()
        return leaf_handle
    except ReviewSnapshotError:
        raise
    except OSError as exc:
        raise ReviewSnapshotError(
            f"{label} cannot be opened safely"
        ) from exc
    finally:
        for handle, _, _ in reversed(handles):
            _windows_close_handle(handle)


def _windows_open_relative_descriptor(
    root: Path,
    repository_path: str,
    label: str,
) -> int:
    leaf_handle = _windows_open_relative_handle(
        root,
        repository_path,
        label,
        leaf_directory=False,
    )
    try:
        import msvcrt

        return msvcrt.open_osfhandle(
            leaf_handle,
            os.O_RDONLY | getattr(os, "O_BINARY", 0),
        )
    except (OSError, ValueError) as exc:
        _windows_close_handle(leaf_handle)
        raise ReviewSnapshotError(
            f"{label} cannot bind its Windows handle"
        ) from exc


def _open_relative_regular_file(
    root: Path,
    repository_path: str,
    label: str,
) -> int:
    if os.name == "posix":
        return _posix_open_relative_descriptor(
            root,
            repository_path,
            label,
            leaf_directory=False,
        )
    if os.name == "nt":
        return _windows_open_relative_descriptor(
            root,
            repository_path,
            label,
        )
    raise ReviewSnapshotError(
        "safe descriptor-relative file traversal is unsupported"
    )


def _read_regular_file(
    root: Path,
    repository_path: str,
    label: str,
) -> bytes:
    descriptor = _open_relative_regular_file(
        root,
        repository_path,
        label,
    )
    try:
        opened_stat = os.fstat(descriptor)
        if not stat.S_ISREG(opened_stat.st_mode):
            raise ReviewSnapshotError(f"{label} must be a regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        final_stat = os.fstat(descriptor)
    except ReviewSnapshotError:
        raise
    except OSError as exc:
        raise ReviewSnapshotError(f"{label} cannot be read safely") from exc
    finally:
        os.close(descriptor)
    if _stat_stability(opened_stat) != _stat_stability(final_stat):
        raise ReviewSnapshotError(f"{label} changed while being read")
    raw = b"".join(chunks)
    if len(raw) != final_stat.st_size:
        raise ReviewSnapshotError(f"{label} returned an unstable byte count")
    return raw


def _ensure_absent(
    root: Path,
    repository_path: str,
    label: str,
) -> None:
    if os.name == "posix":
        _ensure_absent_posix(root, repository_path, label)
        return
    if os.name == "nt":
        _ensure_absent_windows(root, repository_path, label)
        return
    raise ReviewSnapshotError(
        "safe descriptor-relative absence verification is unsupported"
    )


def _ensure_absent_posix(
    root: Path,
    repository_path: str,
    label: str,
) -> None:
    if (
        os.open not in os.supports_dir_fd
        or not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
    ):
        raise ReviewSnapshotError(
            "POSIX descriptor-relative absence verification is unavailable"
        )
    root_stat = _preflight_component(
        root,
        f"{label} root",
        directory=True,
    )
    try:
        root_descriptor = os.open(
            root,
            os.O_RDONLY
            | os.O_DIRECTORY
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise ReviewSnapshotError(
            f"{label} root cannot be opened safely"
        ) from exc
    descriptors = [root_descriptor]
    try:
        if _stat_identity(os.fstat(root_descriptor)) != _stat_identity(
            root_stat
        ):
            raise ReviewSnapshotError(f"{label} root changed before opening")
        segments = repository_path.split("/")
        for index, segment in enumerate(segments):
            is_leaf = index == len(segments) - 1
            flags = (
                os.O_RDONLY
                | os.O_NOFOLLOW
                | getattr(os, "O_CLOEXEC", 0)
            )
            if not is_leaf:
                flags |= os.O_DIRECTORY
            try:
                descriptor = os.open(
                    segment,
                    flags,
                    dir_fd=descriptors[-1],
                )
            except FileNotFoundError:
                return
            except NotADirectoryError:
                if is_leaf:
                    return
                return
            except OSError as exc:
                if exc.errno == errno.ELOOP:
                    raise ReviewSnapshotError(
                        f"{label} traverses a link"
                    ) from exc
                raise ReviewSnapshotError(
                    f"{label} cannot be checked safely"
                ) from exc
            descriptors.append(descriptor)
            opened_stat = os.fstat(descriptor)
            if _is_link_or_reparse(opened_stat):
                raise ReviewSnapshotError(f"{label} traverses a link")
            if is_leaf:
                raise ReviewSnapshotError(f"{label} must be absent")
            if not stat.S_ISDIR(opened_stat.st_mode):
                return
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _ensure_absent_windows(
    root: Path,
    repository_path: str,
    label: str,
) -> None:
    handles: list[tuple[int, Path, bool | None]] = []
    try:
        _preflight_component(root, f"{label} root", directory=True)
        root_handle = _windows_open_path_handle(root, directory=True)
        _windows_validate_handle(
            root_handle,
            root,
            directory=True,
            label=f"{label} root",
        )
        handles.append((root_handle, root, True))
        current_path = root
        segments = repository_path.split("/")
        for index, segment in enumerate(segments):
            is_leaf = index == len(segments) - 1
            current_path = current_path / segment
            expected_kind: bool | None = None if is_leaf else True
            try:
                handle = _windows_open_path_handle(
                    current_path,
                    directory=expected_kind,
                )
            except FileNotFoundError:
                for held_handle, expected_path, directory in handles:
                    _windows_validate_handle(
                        held_handle,
                        expected_path,
                        directory=directory,
                        label=label,
                    )
                return
            _windows_validate_handle(
                handle,
                current_path,
                directory=expected_kind,
                label=label,
            )
            handles.append((handle, current_path, expected_kind))
            if is_leaf:
                raise ReviewSnapshotError(f"{label} must be absent")
        raise ReviewSnapshotError(f"{label} must be absent")
    except ReviewSnapshotError:
        raise
    except OSError as exc:
        if getattr(exc, "winerror", None) in {267}:
            return
        raise ReviewSnapshotError(f"{label} cannot be checked safely") from exc
    finally:
        for handle, _, _ in reversed(handles):
            _windows_close_handle(handle)


def _git_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }
    environment.update(
        {
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_PAGER": "cat",
            "GIT_TERMINAL_PROMPT": "0",
            "LANG": "C",
            "LANGUAGE": "C",
            "LC_ALL": "C",
        }
    )
    environment["GCM_INTERACTIVE"] = "Never"
    environment["PAGER"] = "cat"
    return environment


def _harden_git_arguments(arguments: tuple[str, ...]) -> list[str]:
    if not arguments:
        raise ReviewSnapshotError("git command is missing")
    command = arguments[0]
    remainder = list(arguments[1:])
    if command == "diff":
        remainder = [
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            *remainder,
        ]
    elif command == "status":
        remainder = ["--no-renames", *remainder]
    return [
        "git",
        "-c",
        "color.ui=false",
        "-c",
        "core.fsmonitor=false",
        command,
        *remainder,
    ]


def _run_git_result(root: Path, *arguments: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            _harden_git_arguments(tuple(arguments)),
            cwd=root,
            env=_git_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            check=False,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise ReviewSnapshotError("git command could not be executed") from exc


def _run_git(root: Path, *arguments: str) -> bytes:
    result = _run_git_result(root, *arguments)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise ReviewSnapshotError(
            f"git {' '.join(arguments)} failed ({result.returncode}): "
            f"{stderr}"
        )
    return result.stdout


def _repository_root(value: Any) -> Path:
    supplied = _coerce_path(value, "repository_root")
    _require_plain_directory(supplied, "repository_root")
    try:
        resolved = supplied.resolve(strict=True)
    except OSError as exc:
        raise ReviewSnapshotError("repository_root cannot be resolved") from exc
    top_raw = _run_git(resolved, "rev-parse", "--show-toplevel")
    try:
        top_text = os.fsdecode(top_raw.rstrip(b"\r\n"))
        top = Path(top_text).resolve(strict=True)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ReviewSnapshotError("git returned an invalid repository root") from exc
    if os.path.normcase(str(top)) != os.path.normcase(str(resolved)):
        raise ReviewSnapshotError("repository_root must be the worktree root")
    return resolved


def _validate_git_object_format(value: Any, label: str) -> str:
    object_format = _require_string(value, label)
    if object_format not in {"sha1", "sha256"}:
        raise ReviewSnapshotError(f"{label} is unsupported")
    return object_format


def _validate_git_oid(
    value: Any,
    object_format: str,
    label: str,
) -> str:
    object_id = _require_string(value, label)
    expected_length = 40 if object_format == "sha1" else 64
    if (
        len(object_id) != expected_length
        or re.fullmatch(r"[0-9a-f]+", object_id) is None
    ):
        raise ReviewSnapshotError(
            f"{label} does not match Git object format {object_format}"
        )
    return object_id


def _decode_git_identity(
    raw: bytes,
    object_format: str,
    label: str,
) -> str:
    try:
        value = raw.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise ReviewSnapshotError(f"{label} is not ASCII") from exc
    return _validate_git_oid(value, object_format, label)


def _ensure_no_unmerged_index(root: Path) -> None:
    if _run_git(root, "ls-files", "-u", "-z"):
        raise ReviewSnapshotError("repository index contains unmerged entries")


def _materialized_reviewer_paths(
    repository_paths: list[str],
    external_sources: list[dict[str, Any]],
) -> list[str]:
    combined = [
        *repository_paths,
        *(entry["repository_path"] for entry in external_sources),
    ]
    folded = [item.casefold() for item in combined]
    if len(set(folded)) != len(combined):
        raise ReviewSnapshotError(
            "materialized reviewer paths contain a collision"
        )
    return sorted(combined, key=lambda item: item.encode("ascii"))


def _allowlist_evidence_commands(
    materialized_paths: list[str],
) -> tuple[tuple[str, tuple[str, ...], str], ...]:
    literal_pathspec = tuple(
        f":(literal){repository_path}"
        for repository_path in materialized_paths
    )
    return tuple(
        (
            command_id,
            (*arguments, "--", *literal_pathspec),
            context_field,
        )
        for command_id, arguments, context_field in (
            _REPOSITORY_EVIDENCE_COMMANDS
        )
    )


def _capture_gate_wide_git_state_aggregate(root: Path) -> str:
    records: list[dict[str, Any]] = []
    for command_id, arguments in _GATE_WIDE_GIT_STATE_COMMANDS:
        raw = _run_git(root, *arguments)
        records.append(
            {
                "command_id": command_id,
                "byte_size": len(raw),
                "sha256": _sha256_id(raw),
            }
        )
    return _sha256_id(
        _GATE_WIDE_GIT_STATE_AGGREGATE_DOMAIN
        + _canonical_bytes(records, "gate-wide Git state records")
    )


def _capture_repository_state(
    root: Path,
    materialized_paths: list[str],
) -> tuple[
    dict[str, str],
    list[dict[str, Any]],
    dict[str, bytes],
]:
    _ensure_no_unmerged_index(root)
    try:
        object_format = _run_git(
            root,
            "rev-parse",
            "--show-object-format",
        ).decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise ReviewSnapshotError("Git object format is not ASCII") from exc
    _validate_git_object_format(
        object_format,
        "repository_context.git_object_format",
    )
    try:
        branch = _run_git(
            root,
            "symbolic-ref",
            "--quiet",
            "--short",
            "HEAD",
        ).decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ReviewSnapshotError("Git branch is not UTF-8") from exc
    _require_nonempty_text(branch, "repository_context.branch")
    raw_by_command_id: dict[str, bytes] = {}
    evidence: list[dict[str, Any]] = []
    evidence_hashes: dict[str, str] = {}
    for command_id, arguments, context_field in (
        _allowlist_evidence_commands(materialized_paths)
    ):
        raw = _run_git(root, *arguments)
        digest = _sha256_id(raw)
        raw_by_command_id[command_id] = raw
        evidence_hashes[context_field] = digest
        evidence.append(
            {
                "command_id": command_id,
                "byte_size": len(raw),
                "sha256": digest,
            }
        )
    context: dict[str, str] = {
        "head_commit": _decode_git_identity(
            _run_git(root, "rev-parse", "--verify", "HEAD"),
            object_format,
            "repository_context.head_commit",
        ),
        "head_tree": _decode_git_identity(
            _run_git(root, "rev-parse", "--verify", "HEAD^{tree}"),
            object_format,
            "repository_context.head_tree",
        ),
        "branch": branch,
        "git_object_format": object_format,
        "gate_wide_git_state_aggregate_sha256": (
            _capture_gate_wide_git_state_aggregate(root)
        ),
        **evidence_hashes,
    }
    _ensure_no_unmerged_index(root)
    return context, evidence, raw_by_command_id


def _parse_head_blob_identity(
    root: Path,
    repository_path: str,
    object_format: str,
) -> tuple[str | None, str | None]:
    raw = _run_git(
        root,
        "ls-tree",
        "-z",
        "HEAD",
        "--",
        repository_path,
    )
    records = [record for record in raw.split(b"\x00") if record]
    if not records:
        return None, None
    if len(records) != 1:
        raise ReviewSnapshotError(
            f"HEAD has ambiguous identity for {repository_path}"
        )
    try:
        metadata, observed_path = records[0].split(b"\t", 1)
        mode_raw, object_type, object_id_raw = metadata.split(b" ", 2)
        mode = mode_raw.decode("ascii")
        object_id = object_id_raw.decode("ascii")
        observed = observed_path.decode("ascii")
    except (ValueError, UnicodeError) as exc:
        raise ReviewSnapshotError(
            f"HEAD identity is malformed for {repository_path}"
        ) from exc
    if (
        object_type != b"blob"
        or observed != repository_path
        or mode not in _REGULAR_GIT_MODES
    ):
        raise ReviewSnapshotError(
            f"HEAD identity is not a regular blob for {repository_path}"
        )
    return (
        _validate_git_oid(
            object_id,
            object_format,
            f"HEAD blob oid for {repository_path}",
        ),
        mode,
    )


def _parse_index_blob_identity(
    root: Path,
    repository_path: str,
    object_format: str,
) -> tuple[str | None, str | None]:
    raw = _run_git(
        root,
        "ls-files",
        "-s",
        "-z",
        "--",
        repository_path,
    )
    records = [record for record in raw.split(b"\x00") if record]
    if not records:
        return None, None
    if len(records) != 1:
        raise ReviewSnapshotError(
            f"index has unmerged or ambiguous identity for {repository_path}"
        )
    try:
        metadata, observed_path = records[0].split(b"\t", 1)
        mode_raw, object_id_raw, stage = metadata.split(b" ", 2)
        mode = mode_raw.decode("ascii")
        object_id = object_id_raw.decode("ascii")
        observed = observed_path.decode("ascii")
    except (ValueError, UnicodeError) as exc:
        raise ReviewSnapshotError(
            f"index identity is malformed for {repository_path}"
        ) from exc
    if (
        stage != b"0"
        or observed != repository_path
        or mode not in _REGULAR_GIT_MODES
    ):
        raise ReviewSnapshotError(
            f"index identity is not a stage-0 regular blob for "
            f"{repository_path}"
        )
    return (
        _validate_git_oid(
            object_id,
            object_format,
            f"index blob oid for {repository_path}",
        ),
        mode,
    )


def _file_provenance(
    root: Path,
    repository_path: str,
    object_format: str,
) -> dict[str, str | None]:
    head_oid, head_mode = _parse_head_blob_identity(
        root,
        repository_path,
        object_format,
    )
    index_oid, index_mode = _parse_index_blob_identity(
        root,
        repository_path,
        object_format,
    )
    return {
        "head_blob_oid": head_oid,
        "head_blob_mode": head_mode,
        "index_blob_oid": index_oid,
        "index_blob_mode": index_mode,
        "filesystem_kind": "REGULAR_FILE",
    }


def _source_kind(
    root: Path,
    repository_path: str,
    raw: bytes,
) -> str:
    tracked = _run_git_result(
        root,
        "ls-files",
        "--error-unmatch",
        "--",
        repository_path,
    )
    if tracked.returncode == 1:
        return "WORKTREE_UNTRACKED"
    if tracked.returncode != 0:
        raise ReviewSnapshotError(
            f"cannot classify repository path {repository_path}"
        )
    head_blob = _run_git_result(root, "show", f"HEAD:{repository_path}")
    if head_blob.returncode == 0 and head_blob.stdout == raw:
        return "HEAD_BLOB"
    return "TRACKED_WORKTREE"


def _validate_repository_context(value: Any) -> dict[str, Any]:
    context = _require_exact_keys(
        value,
        _REPOSITORY_CONTEXT_KEYS,
        "repository_context",
    )
    object_format = _validate_git_object_format(
        context["git_object_format"],
        "repository_context.git_object_format",
    )
    for field in ("head_commit", "head_tree"):
        _validate_git_oid(
            context[field],
            object_format,
            f"repository_context.{field}",
        )
    _require_nonempty_text(context["branch"], "repository_context.branch")
    for field in (
        "gate_wide_git_state_aggregate_sha256",
        "allowlist_git_status_porcelain_v2_z_sha256",
        "allowlist_tracked_diff_binary_sha256",
        "allowlist_cached_diff_binary_sha256",
        "allowlist_index_listing_s_z_sha256",
    ):
        _require_digest(context[field], f"repository_context.{field}")
    return context


def _validate_repository_evidence(
    value: Any,
    repository_context: dict[str, Any],
) -> list[dict[str, Any]]:
    entries = _require_list(value, "repository_evidence")
    if len(entries) != len(_REPOSITORY_EVIDENCE_COMMANDS):
        raise ReviewSnapshotError(
            "repository_evidence must contain the fixed command set"
        )
    for index, specification in enumerate(
        _REPOSITORY_EVIDENCE_COMMANDS
    ):
        command_id, _, context_field = specification
        entry_label = f"repository_evidence[{index}]"
        entry = _require_exact_keys(
            entries[index],
            _REPOSITORY_EVIDENCE_KEYS,
            entry_label,
        )
        if (
            _require_string(
                entry["command_id"],
                f"{entry_label}.command_id",
            )
            != command_id
        ):
            raise ReviewSnapshotError(
                "repository_evidence command order is not canonical"
            )
        _require_size(entry["byte_size"], f"{entry_label}.byte_size")
        digest = _require_digest(
            entry["sha256"],
            f"{entry_label}.sha256",
        )
        if digest != repository_context[context_field]:
            raise ReviewSnapshotError(
                f"{entry_label} does not bind repository_context"
            )
    return entries


def _validate_blob_identity_pair(
    entry: dict[str, Any],
    prefix: str,
    object_format: str,
    entry_label: str,
) -> tuple[str | None, str | None]:
    oid = entry[f"{prefix}_blob_oid"]
    mode = entry[f"{prefix}_blob_mode"]
    if oid is None or mode is None:
        if oid is not None or mode is not None:
            raise ReviewSnapshotError(
                f"{entry_label}.{prefix} blob identity is incomplete"
            )
        return None, None
    validated_oid = _validate_git_oid(
        oid,
        object_format,
        f"{entry_label}.{prefix}_blob_oid",
    )
    validated_mode = _require_string(
        mode,
        f"{entry_label}.{prefix}_blob_mode",
    )
    if validated_mode not in _REGULAR_GIT_MODES:
        raise ReviewSnapshotError(
            f"{entry_label}.{prefix}_blob_mode is not a regular file"
        )
    return validated_oid, validated_mode


def _validate_external_sources(
    value: Any,
    *,
    snapshot_value: bool,
) -> list[dict[str, Any]]:
    label = "external_normative_sources"
    entries = (
        _require_list(value, label)
        if snapshot_value
        else _as_input_list(value, label)
    )
    validated: list[dict[str, Any]] = []
    source_ids: list[str] = []
    repository_paths: list[str] = []
    for index, candidate in enumerate(entries):
        entry_label = f"{label}[{index}]"
        entry = _require_exact_keys(
            candidate,
            _EXTERNAL_SOURCE_KEYS,
            entry_label,
        )
        source_id = _require_nonempty_text(
            entry["source_id"],
            f"{entry_label}.source_id",
        )
        repository_path = _validate_repository_path(
            entry["repository_path"],
            f"{entry_label}.repository_path",
        )
        digest = _require_digest(
            entry["sha256"],
            f"{entry_label}.sha256",
        )
        locator = _require_string(
            entry["immutable_locator"],
            f"{entry_label}.immutable_locator",
        )
        if locator != "urn:sha256:" + digest.removeprefix("sha256:"):
            raise ReviewSnapshotError(
                f"{entry_label}.immutable_locator is not immutable"
            )
        _require_nonempty_text(
            entry["media_type"],
            f"{entry_label}.media_type",
            ascii_only=True,
        )
        _validate_utc(
            entry["retrieved_at_utc"],
            f"{entry_label}.retrieved_at_utc",
        )
        _require_size(entry["byte_size"], f"{entry_label}.byte_size")
        source_ids.append(source_id)
        repository_paths.append(repository_path)
        validated.append(
            {
                "source_id": source_id,
                "immutable_locator": locator,
                "media_type": entry["media_type"],
                "retrieved_at_utc": entry["retrieved_at_utc"],
                "repository_path": repository_path,
                "byte_size": entry["byte_size"],
                "sha256": digest,
            }
        )
    if source_ids != sorted(source_ids, key=lambda item: item.encode("utf-8")):
        raise ReviewSnapshotError(
            "external_normative_sources must be in source_id order"
        )
    if len({item.casefold() for item in source_ids}) != len(source_ids):
        raise ReviewSnapshotError(
            "external_normative_sources contains duplicate source_id"
        )
    if len({item.casefold() for item in repository_paths}) != len(
        repository_paths
    ):
        raise ReviewSnapshotError(
            "external_normative_sources contains a path collision"
        )
    return validated


def _validate_snapshot_structure(snapshot: Any) -> dict[str, Any]:
    value = _require_exact_keys(snapshot, _TOP_LEVEL_KEYS, "snapshot")
    if _require_string(value["schema_version"], "schema_version") != (
        _SCHEMA_VERSION
    ):
        raise ReviewSnapshotError("schema_version is unsupported")
    _validate_uuid4(value["snapshot_instance_id"], "snapshot_instance_id")
    started = _validate_utc(
        value["capture_started_at_utc"],
        "capture_started_at_utc",
    )
    completed = _validate_utc(
        value["capture_completed_at_utc"],
        "capture_completed_at_utc",
    )
    if completed < started:
        raise ReviewSnapshotError("capture completion precedes capture start")

    domain = _require_exact_keys(
        value["review_domain"],
        _REVIEW_DOMAIN_KEYS,
        "review_domain",
    )
    if _require_string(domain["mode"], "review_domain.mode") != (
        "ALLOWLIST_ONLY"
    ):
        raise ReviewSnapshotError("review_domain.mode is unsupported")
    repository_paths = _validate_path_list(
        domain["repository_paths"],
        "review_domain.repository_paths",
        require_nonempty=True,
        snapshot_value=True,
    )
    _validate_focus_areas(
        domain["required_focus_areas"],
        snapshot_value=True,
    )
    absent_paths = _validate_path_list(
        domain["required_absent_paths"],
        "review_domain.required_absent_paths",
        require_nonempty=False,
        snapshot_value=True,
    )
    _validate_review_subject(value["review_subject"], repository_paths)
    _validate_review_protocol(value["review_protocol"])
    repository_context = _validate_repository_context(
        value["repository_context"]
    )
    object_format = repository_context["git_object_format"]

    files = _require_list(value["files"], "files")
    if len(files) != len(repository_paths):
        raise ReviewSnapshotError("files do not cover the review allowlist")
    observed_paths: list[str] = []
    for index, candidate in enumerate(files):
        entry_label = f"files[{index}]"
        entry = _require_exact_keys(candidate, _FILE_KEYS, entry_label)
        observed_paths.append(
            _validate_repository_path(
                entry["repository_path"],
                f"{entry_label}.repository_path",
            )
        )
        source_kind = _require_string(
            entry["source_kind"],
            f"{entry_label}.source_kind",
        )
        if source_kind not in _SOURCE_KINDS:
            raise ReviewSnapshotError(f"{entry_label}.source_kind is invalid")
        _require_size(entry["byte_size"], f"{entry_label}.byte_size")
        _require_digest(entry["sha256"], f"{entry_label}.sha256")
        head_oid, _ = _validate_blob_identity_pair(
            entry,
            "head",
            object_format,
            entry_label,
        )
        index_oid, _ = _validate_blob_identity_pair(
            entry,
            "index",
            object_format,
            entry_label,
        )
        if (
            _require_string(
                entry["filesystem_kind"],
                f"{entry_label}.filesystem_kind",
            )
            != "REGULAR_FILE"
        ):
            raise ReviewSnapshotError(
                f"{entry_label}.filesystem_kind must be REGULAR_FILE"
            )
        if source_kind == "HEAD_BLOB" and head_oid is None:
            raise ReviewSnapshotError(
                f"{entry_label} lacks HEAD provenance"
            )
        if (
            source_kind == "TRACKED_WORKTREE"
            and index_oid is None
        ):
            raise ReviewSnapshotError(
                f"{entry_label} lacks index provenance"
            )
        if (
            source_kind == "WORKTREE_UNTRACKED"
            and index_oid is not None
        ):
            raise ReviewSnapshotError(
                f"{entry_label} has contradictory index provenance"
            )
    if observed_paths != repository_paths:
        raise ReviewSnapshotError("files are not the ordered allowlist")

    _require_digest(value["file_aggregate_sha256"], "file_aggregate_sha256")
    expected_aggregate = _sha256_id(
        _FILE_AGGREGATE_DOMAIN + _canonical_bytes(files, "files")
    )
    if value["file_aggregate_sha256"] != expected_aggregate:
        raise ReviewSnapshotError("file_aggregate_sha256 does not match")

    _validate_repository_evidence(
        value["repository_evidence"],
        repository_context,
    )
    external_sources = _validate_external_sources(
        value["external_normative_sources"],
        snapshot_value=True,
    )
    _materialized_reviewer_paths(repository_paths, external_sources)
    _validate_absence_hierarchy(
        absent_paths,
        [
            *repository_paths,
            *(
                entry["repository_path"]
                for entry in external_sources
            ),
        ],
    )

    content_id = _require_digest(
        value["snapshot_content_id"],
        "snapshot_content_id",
    )
    if content_id != snapshot_content_id(value):
        raise ReviewSnapshotError("snapshot_content_id does not match")
    return value


def _canonical_clone(snapshot: dict[str, Any]) -> dict[str, Any]:
    canonical = _canonical_bytes(snapshot, "snapshot")
    try:
        cloned = json.loads(canonical)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise ReviewSnapshotError("snapshot cannot be frozen") from exc
    if type(cloned) is not dict:
        raise ReviewSnapshotError("snapshot must be an object")
    return cloned


def _verify_live_snapshot(
    snapshot: dict[str, Any],
    root: Path,
) -> dict[str, bytes]:
    domain = snapshot["review_domain"]
    materialized_paths = _materialized_reviewer_paths(
        domain["repository_paths"],
        snapshot["external_normative_sources"],
    )
    for repository_path in domain["required_absent_paths"]:
        _ensure_absent(
            root,
            repository_path,
            f"required absent path {repository_path}",
        )

    expected_context = snapshot["repository_context"]
    expected_evidence = snapshot["repository_evidence"]
    before_context, before_evidence, before_raw = (
        _capture_repository_state(root, materialized_paths)
    )
    if (
        before_context != expected_context
        or before_evidence != expected_evidence
    ):
        raise ReviewSnapshotError("repository context changed")

    object_format = expected_context["git_object_format"]
    review_subject_path = snapshot["review_subject"]["repository_path"]
    for entry in snapshot["files"]:
        repository_path = entry["repository_path"]
        raw = _read_regular_file(
            root,
            repository_path,
            f"review file {repository_path}",
        )
        if len(raw) != entry["byte_size"] or _sha256_id(raw) != entry["sha256"]:
            raise ReviewSnapshotError(
                f"review file {repository_path} changed"
            )
        if _source_kind(root, repository_path, raw) != entry["source_kind"]:
            raise ReviewSnapshotError(
                f"review file {repository_path} changed source kind"
            )
        expected_provenance = {
            field: entry[field]
            for field in (
                "head_blob_oid",
                "head_blob_mode",
                "index_blob_oid",
                "index_blob_mode",
                "filesystem_kind",
            )
        }
        if (
            _file_provenance(
                root,
                repository_path,
                object_format,
            )
            != expected_provenance
        ):
            raise ReviewSnapshotError(
                f"review file {repository_path} changed provenance"
            )
        if repository_path == review_subject_path:
            _validate_review_subject_bytes(raw)

    for entry in snapshot["external_normative_sources"]:
        repository_path = entry["repository_path"]
        raw = _read_regular_file(
            root,
            repository_path,
            f"external source {repository_path}",
        )
        if len(raw) != entry["byte_size"] or _sha256_id(raw) != entry["sha256"]:
            raise ReviewSnapshotError(
                f"external source {repository_path} changed"
            )

    for repository_path in domain["required_absent_paths"]:
        _ensure_absent(
            root,
            repository_path,
            f"required absent path {repository_path}",
        )
    after_context, after_evidence, after_raw = (
        _capture_repository_state(root, materialized_paths)
    )
    if (
        after_context != expected_context
        or after_context != before_context
        or after_evidence != expected_evidence
        or after_evidence != before_evidence
        or after_raw != before_raw
    ):
        raise ReviewSnapshotError("repository context changed during verify")
    return after_raw


def snapshot_content_id(snapshot: dict[str, Any]) -> str:
    """Return the RFC 8785 self-hash, excluding only its own field."""

    try:
        if type(snapshot) is not dict:
            raise ReviewSnapshotError("snapshot must be an object")
        if "snapshot_content_id" not in snapshot:
            raise ReviewSnapshotError("snapshot_content_id is missing")
        unsigned = {
            key: value
            for key, value in snapshot.items()
            if key != "snapshot_content_id"
        }
        return _sha256_id(
            _SNAPSHOT_DOMAIN + _canonical_bytes(unsigned, "snapshot")
        )
    except ReviewSnapshotError:
        raise
    except Exception as exc:
        raise ReviewSnapshotError(
            "snapshot content id could not be calculated"
        ) from exc


def build_snapshot(
    repository_root: str | os.PathLike[str],
    repository_paths: Iterable[str],
    *,
    snapshot_instance_id: str,
    capture_started_at_utc: str,
    capture_completed_at_utc: str,
    required_focus_areas: Iterable[str],
    review_subject_path: str,
    required_absent_paths: Iterable[str] = (),
    external_normative_sources: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Capture a fail-closed, allowlist-only review snapshot."""

    try:
        instance_id = _validate_uuid4(
            snapshot_instance_id,
            "snapshot_instance_id",
        )
        started = _validate_utc(
            capture_started_at_utc,
            "capture_started_at_utc",
        )
        completed = _validate_utc(
            capture_completed_at_utc,
            "capture_completed_at_utc",
        )
        if completed < started:
            raise ReviewSnapshotError(
                "capture completion precedes capture start"
            )
        paths = _validate_path_list(
            repository_paths,
            "repository_paths",
            require_nonempty=True,
            snapshot_value=False,
        )
        focus_areas = _validate_focus_areas(
            required_focus_areas,
            snapshot_value=False,
        )
        subject_path = _validate_repository_path(
            review_subject_path,
            "review_subject_path",
        )
        if subject_path not in paths:
            raise ReviewSnapshotError(
                "review_subject_path must be in repository_paths"
            )
        absent_paths = _validate_path_list(
            required_absent_paths,
            "required_absent_paths",
            require_nonempty=False,
            snapshot_value=False,
        )
        external_sources = _validate_external_sources(
            external_normative_sources,
            snapshot_value=False,
        )
        materialized_paths = _materialized_reviewer_paths(
            paths,
            external_sources,
        )
        _validate_absence_hierarchy(
            absent_paths,
            [
                *paths,
                *(
                    entry["repository_path"]
                    for entry in external_sources
                ),
            ],
        )

        root = _repository_root(repository_root)
        before_context, before_evidence, before_evidence_raw = (
            _capture_repository_state(root, materialized_paths)
        )
        for repository_path in absent_paths:
            _ensure_absent(
                root,
                repository_path,
                f"required absent path {repository_path}",
            )

        captured_bytes: dict[str, bytes] = {}
        files: list[dict[str, Any]] = []
        for repository_path in paths:
            raw = _read_regular_file(
                root,
                repository_path,
                f"review file {repository_path}",
            )
            captured_bytes[repository_path] = raw
            if repository_path == subject_path:
                _validate_review_subject_bytes(raw)
            files.append(
                {
                    "repository_path": repository_path,
                    "source_kind": _source_kind(
                        root,
                        repository_path,
                        raw,
                    ),
                    "byte_size": len(raw),
                    "sha256": _sha256_id(raw),
                    **_file_provenance(
                        root,
                        repository_path,
                        before_context["git_object_format"],
                    ),
                }
            )
        for entry in external_sources:
            repository_path = entry["repository_path"]
            raw = _read_regular_file(
                root,
                repository_path,
                f"external source {repository_path}",
            )
            if (
                len(raw) != entry["byte_size"]
                or _sha256_id(raw) != entry["sha256"]
            ):
                raise ReviewSnapshotError(
                    f"external source {repository_path} does not match metadata"
                )
            captured_bytes[repository_path] = raw

        for repository_path, expected_raw in captured_bytes.items():
            observed_raw = _read_regular_file(
                root,
                repository_path,
                f"captured source {repository_path}",
            )
            if observed_raw != expected_raw:
                raise ReviewSnapshotError(
                    f"captured source {repository_path} changed"
                )
        for repository_path in absent_paths:
            _ensure_absent(
                root,
                repository_path,
                f"required absent path {repository_path}",
            )
        (
            after_context,
            after_evidence,
            after_evidence_raw,
        ) = _capture_repository_state(root, materialized_paths)
        if (
            after_context != before_context
            or after_evidence != before_evidence
            or after_evidence_raw != before_evidence_raw
        ):
            raise ReviewSnapshotError(
                "repository context changed during capture"
            )

        snapshot: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "snapshot_instance_id": instance_id,
            "capture_started_at_utc": capture_started_at_utc,
            "capture_completed_at_utc": capture_completed_at_utc,
            "review_domain": {
                "mode": "ALLOWLIST_ONLY",
                "repository_paths": paths,
                "required_focus_areas": focus_areas,
                "required_absent_paths": absent_paths,
            },
            "review_subject": {
                "repository_path": subject_path,
                "required_state": _REVIEW_SUBJECT_STATE,
                "observed_state": _REVIEW_SUBJECT_STATE,
            },
            "review_protocol": {
                "review_type": _REVIEW_PROTOCOL["review_type"],
                "pass_condition": {
                    "P0": 0,
                    "P1": 0,
                },
                "live_verify_required_at": [
                    "REVIEW_START",
                    "REVIEW_END",
                ],
                "hash_mismatch_disposition": (
                    _REVIEW_PROTOCOL["hash_mismatch_disposition"]
                ),
                "implementation_or_test_execution_claims_allowed": False,
            },
            "files": files,
            "file_aggregate_sha256": _sha256_id(
                _FILE_AGGREGATE_DOMAIN
                + _canonical_bytes(files, "files")
            ),
            "repository_context": before_context,
            "repository_evidence": before_evidence,
            "external_normative_sources": external_sources,
            "snapshot_content_id": "",
        }
        snapshot["snapshot_content_id"] = snapshot_content_id(snapshot)
        _validate_snapshot_structure(snapshot)
        _verify_live_snapshot(snapshot, root)
        return snapshot
    except ReviewSnapshotError:
        raise
    except Exception as exc:
        raise ReviewSnapshotError("snapshot capture failed") from exc


def verify_snapshot(
    snapshot: dict[str, Any],
    repository_root: str | os.PathLike[str],
    *,
    boundary: str,
) -> LiveVerificationReceipt:
    """Verify the manifest and its live Git worktree binding."""

    verification_started_at_utc = _utc_now_text()
    try:
        if type(boundary) is not str or boundary not in {
            "REVIEW_START",
            "REVIEW_END",
        }:
            raise ReviewSnapshotError(
                "boundary must be REVIEW_START or REVIEW_END"
            )
        _validate_snapshot_structure(snapshot)
        frozen = _canonical_clone(snapshot)
        _validate_snapshot_structure(frozen)
        root = _repository_root(repository_root)
        root_stat = root.stat()
        if _is_link_or_reparse(root_stat) or not stat.S_ISDIR(
            root_stat.st_mode
        ):
            raise ReviewSnapshotError(
                "repository root identity is not a plain directory"
            )
        _verify_live_snapshot(frozen, root)
        verification_completed_at_utc = _utc_now_text()
        return LiveVerificationReceipt(
            boundary=boundary,
            snapshot_content_id=frozen["snapshot_content_id"],
            verification_started_at_utc=verification_started_at_utc,
            verification_completed_at_utc=verification_completed_at_utc,
            repository_root_identity={
                "resolved_path": str(root),
                "st_dev": root_stat.st_dev,
                "st_ino": root_stat.st_ino,
            },
            continuous_observation=False,
            authority_state="UNVERIFIED",
            persistence_state="UNVERIFIED",
            authorization_state="NOT_AUTHORIZED",
        )
    except ReviewSnapshotError:
        raise
    except Exception as exc:
        raise ReviewSnapshotError("snapshot verification failed") from exc


def _referenced_objects(
    snapshot: dict[str, Any],
) -> dict[str, int]:
    referenced: dict[str, int] = {}
    for entry in (
        snapshot["files"]
        + snapshot["external_normative_sources"]
        + snapshot["repository_evidence"]
    ):
        digest = entry["sha256"]
        size = entry["byte_size"]
        previous = referenced.setdefault(digest, size)
        if previous != size:
            raise ReviewSnapshotError(
                "one digest is bound to conflicting byte sizes"
            )
    return referenced


@dataclass(frozen=True, slots=True)
class _DirectoryEntryStat:
    st_mode: int
    st_file_attributes: int = 0


class _WindowsFileIdBothDirectoryInfo(ctypes.Structure):
    _fields_ = [
        ("NextEntryOffset", ctypes.c_ulong),
        ("FileIndex", ctypes.c_ulong),
        ("CreationTime", ctypes.c_longlong),
        ("LastAccessTime", ctypes.c_longlong),
        ("LastWriteTime", ctypes.c_longlong),
        ("ChangeTime", ctypes.c_longlong),
        ("EndOfFile", ctypes.c_longlong),
        ("AllocationSize", ctypes.c_longlong),
        ("FileAttributes", ctypes.c_ulong),
        ("FileNameLength", ctypes.c_ulong),
        ("EaSize", ctypes.c_ulong),
        ("ShortNameLength", ctypes.c_ubyte),
        ("ShortName", ctypes.c_wchar * 12),
        ("FileId", ctypes.c_longlong),
        ("FileName", ctypes.c_wchar * 1),
    ]


def _posix_open_bound_directory(
    root: Path,
    repository_path: str | None,
    label: str,
) -> int:
    if repository_path is not None:
        return _posix_open_relative_descriptor(
            root,
            repository_path,
            label,
            leaf_directory=True,
        )
    root_stat = _preflight_component(root, label, directory=True)
    try:
        descriptor = os.open(
            root,
            os.O_RDONLY
            | os.O_DIRECTORY
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise ReviewSnapshotError(
            f"{label} cannot be opened safely"
        ) from exc
    opened_stat = os.fstat(descriptor)
    if _stat_identity(opened_stat) != _stat_identity(root_stat):
        os.close(descriptor)
        raise ReviewSnapshotError(f"{label} changed before opening")
    return descriptor


def _posix_directory_entries(
    root: Path,
    repository_path: str | None,
    label: str,
) -> dict[str, Any]:
    if os.scandir not in os.supports_fd:
        raise ReviewSnapshotError(
            "POSIX descriptor-bound directory enumeration is unavailable"
        )
    descriptor = _posix_open_bound_directory(
        root,
        repository_path,
        label,
    )
    try:
        before_stat = os.fstat(descriptor)
        with os.scandir(descriptor) as iterator:
            entries = {
                entry.name: entry.stat(follow_symlinks=False)
                for entry in iterator
            }
        after_stat = os.fstat(descriptor)
    except OSError as exc:
        raise ReviewSnapshotError(f"{label} cannot be enumerated") from exc
    finally:
        os.close(descriptor)
    if _stat_stability(before_stat) != _stat_stability(after_stat):
        raise ReviewSnapshotError(f"{label} changed while enumerating")
    return entries


def _windows_open_bound_directory(
    root: Path,
    repository_path: str | None,
    label: str,
) -> tuple[int, Path]:
    if repository_path is not None:
        expected_path = root.joinpath(*repository_path.split("/"))
        return (
            _windows_open_relative_handle(
                root,
                repository_path,
                label,
                leaf_directory=True,
            ),
            expected_path,
        )
    _preflight_component(root, label, directory=True)
    handle = _windows_open_path_handle(root, directory=True)
    try:
        _windows_validate_handle(
            handle,
            root,
            directory=True,
            label=label,
        )
    except Exception:
        _windows_close_handle(handle)
        raise
    return handle, root


def _windows_directory_entries(
    root: Path,
    repository_path: str | None,
    label: str,
) -> dict[str, Any]:
    handle, expected_path = _windows_open_bound_directory(
        root,
        repository_path,
        label,
    )
    try:
        kernel32 = _windows_kernel32()
        get_information = kernel32.GetFileInformationByHandleEx
        get_information.argtypes = (
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_ulong,
        )
        get_information.restype = ctypes.c_int
        entries: dict[str, Any] = {}
        folded_names: set[str] = set()
        restart = True
        while True:
            buffer = ctypes.create_string_buffer(64 * 1024)
            information_class = 11 if restart else 10
            ctypes.set_last_error(0)
            succeeded = get_information(
                ctypes.c_void_p(handle),
                information_class,
                buffer,
                len(buffer),
            )
            if not succeeded:
                error_number = ctypes.get_last_error()
                if error_number == 18:
                    break
                if error_number == 234:
                    raise ReviewSnapshotError(
                        f"{label} contains an entry too large to enumerate"
                    )
                raise OSError(error_number, os.strerror(error_number))
            restart = False
            offset = 0
            while True:
                if (
                    offset
                    + _WindowsFileIdBothDirectoryInfo.FileName.offset
                    > len(buffer)
                ):
                    raise ReviewSnapshotError(
                        f"{label} returned malformed directory data"
                    )
                record = _WindowsFileIdBothDirectoryInfo.from_buffer(
                    buffer,
                    offset,
                )
                name_length = int(record.FileNameLength)
                name_offset = (
                    offset
                    + _WindowsFileIdBothDirectoryInfo.FileName.offset
                )
                name_end = name_offset + name_length
                if (
                    name_length % 2
                    or name_end > len(buffer)
                    or name_length == 0
                ):
                    raise ReviewSnapshotError(
                        f"{label} returned malformed directory data"
                    )
                name = bytes(buffer[name_offset:name_end]).decode(
                    "utf-16-le",
                    "strict",
                )
                if name not in {".", ".."}:
                    folded = name.casefold()
                    if name in entries or folded in folded_names:
                        raise ReviewSnapshotError(
                            f"{label} contains a name collision"
                        )
                    attributes = int(record.FileAttributes)
                    mode = (
                        stat.S_IFDIR | 0o555
                        if attributes & 0x00000010
                        else stat.S_IFREG | 0o444
                    )
                    entries[name] = _DirectoryEntryStat(
                        st_mode=mode,
                        st_file_attributes=attributes,
                    )
                    folded_names.add(folded)
                next_offset = int(record.NextEntryOffset)
                if next_offset == 0:
                    break
                if next_offset < name_end - offset:
                    raise ReviewSnapshotError(
                        f"{label} returned malformed directory offsets"
                    )
                offset += next_offset
        _windows_validate_handle(
            handle,
            expected_path,
            directory=True,
            label=label,
        )
        return entries
    except ReviewSnapshotError:
        raise
    except (OSError, UnicodeError) as exc:
        raise ReviewSnapshotError(f"{label} cannot be enumerated") from exc
    finally:
        _windows_close_handle(handle)


def _directory_entries(
    root: Path,
    repository_path: str | None,
    label: str,
) -> dict[str, Any]:
    if os.name == "posix":
        return _posix_directory_entries(root, repository_path, label)
    if os.name == "nt":
        return _windows_directory_entries(root, repository_path, label)
    raise ReviewSnapshotError(
        "safe handle-bound directory enumeration is unsupported"
    )


def _verify_bundle_tree(
    bundle: Path,
    expected_hex_digests: set[str],
) -> None:
    root_entries = _directory_entries(bundle, None, "bundle")
    if set(root_entries) != {"manifest.json", "objects"}:
        raise ReviewSnapshotError("bundle has an unexpected root entry")
    manifest_stat = root_entries["manifest.json"]
    if _is_link_or_reparse(manifest_stat) or not stat.S_ISREG(
        manifest_stat.st_mode
    ):
        raise ReviewSnapshotError("manifest.json must be a regular file")
    objects_stat = root_entries["objects"]
    if _is_link_or_reparse(objects_stat) or not stat.S_ISDIR(
        objects_stat.st_mode
    ):
        raise ReviewSnapshotError("objects must be a plain directory")

    object_entries = _directory_entries(bundle, "objects", "objects")
    if set(object_entries) != {"sha256"}:
        raise ReviewSnapshotError("objects has an unexpected entry")
    sha_stat = object_entries["sha256"]
    if _is_link_or_reparse(sha_stat) or not stat.S_ISDIR(sha_stat.st_mode):
        raise ReviewSnapshotError("objects/sha256 must be a plain directory")

    digest_entries = _directory_entries(
        bundle,
        "objects/sha256",
        "objects/sha256",
    )
    if set(digest_entries) != expected_hex_digests:
        raise ReviewSnapshotError("object store is incomplete or has extras")
    for name, file_stat in digest_entries.items():
        if (
            re.fullmatch(r"[0-9a-f]{64}", name) is None
            or _is_link_or_reparse(file_stat)
            or not stat.S_ISREG(file_stat.st_mode)
        ):
            raise ReviewSnapshotError("object store entry is invalid")


def _parse_canonical_manifest(raw: bytes) -> dict[str, Any]:
    if not raw.endswith(b"\n"):
        raise ReviewSnapshotError("manifest.json must end in one LF")
    payload = raw[:-1]
    try:
        snapshot = json.loads(
            payload.decode("utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"invalid JSON constant: {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ReviewSnapshotError("manifest.json is invalid JSON") from exc
    if type(snapshot) is not dict:
        raise ReviewSnapshotError("manifest.json must contain an object")
    if _canonical_bytes(snapshot, "manifest.json") + b"\n" != raw:
        raise ReviewSnapshotError("manifest.json is not canonical JCS plus LF")
    _validate_snapshot_structure(snapshot)
    return snapshot


def _git_blob_oid(raw: bytes, object_format: str) -> str:
    preimage = (
        b"blob "
        + str(len(raw)).encode("ascii")
        + b"\x00"
        + raw
    )
    return hashlib.new(object_format, preimage).hexdigest()


def _verify_offline_index_provenance(
    snapshot: dict[str, Any],
    raw_index_listing: bytes,
) -> None:
    object_format = snapshot["repository_context"]["git_object_format"]
    selected_paths = {
        entry["repository_path"].encode("ascii"): entry
        for entry in snapshot["files"]
    }
    observed: dict[bytes, tuple[str, str]] = {}
    for record in raw_index_listing.split(b"\x00"):
        if not record:
            continue
        try:
            metadata, path = record.split(b"\t", 1)
            mode_raw, oid_raw, stage = metadata.split(b" ", 2)
            mode = mode_raw.decode("ascii")
            oid = oid_raw.decode("ascii")
        except (ValueError, UnicodeError) as exc:
            raise ReviewSnapshotError(
                "repository index evidence is malformed"
            ) from exc
        if stage != b"0":
            raise ReviewSnapshotError(
                "repository index evidence contains an unmerged entry"
            )
        if path not in selected_paths:
            continue
        if path in observed:
            raise ReviewSnapshotError(
                "repository index evidence contains a duplicate review path"
            )
        if mode not in _REGULAR_GIT_MODES:
            raise ReviewSnapshotError(
                "repository index evidence has non-regular provenance"
            )
        observed[path] = (
            _validate_git_oid(
                oid,
                object_format,
                "repository index evidence object id",
            ),
            mode,
        )
    for path, entry in selected_paths.items():
        expected = (
            entry["index_blob_oid"],
            entry["index_blob_mode"],
        )
        actual = observed.get(path, (None, None))
        if actual != expected:
            raise ReviewSnapshotError(
                "repository index evidence does not match file provenance"
            )


def _verify_offline_file_provenance(
    snapshot: dict[str, Any],
    raw_by_digest: dict[str, bytes],
) -> None:
    object_format = snapshot["repository_context"]["git_object_format"]
    subject_path = snapshot["review_subject"]["repository_path"]
    for entry in snapshot["files"]:
        raw = raw_by_digest[entry["sha256"]]
        if entry["source_kind"] == "HEAD_BLOB" and (
            _git_blob_oid(raw, object_format)
            != entry["head_blob_oid"]
        ):
            raise ReviewSnapshotError(
                "HEAD_BLOB content does not match HEAD provenance"
            )
        if entry["repository_path"] == subject_path:
            _validate_review_subject_bytes(raw)
    evidence_by_id = {
        entry["command_id"]: raw_by_digest[entry["sha256"]]
        for entry in snapshot["repository_evidence"]
    }
    _verify_offline_index_provenance(
        snapshot,
        evidence_by_id[
            "GIT_ALLOWLIST_PATHSPEC_INDEX_LISTING_S_Z_V1"
        ],
    )


def _verify_snapshot_bundle_contents(
    bundle: Path,
    *,
    require_instance_directory_name: bool,
) -> dict[str, Any]:
    _require_plain_directory(bundle, "bundle_path")
    manifest_raw = _read_regular_file(
        bundle,
        "manifest.json",
        "manifest.json",
    )
    snapshot = _parse_canonical_manifest(manifest_raw)
    if (
        require_instance_directory_name
        and bundle.name != snapshot["snapshot_instance_id"]
    ):
        raise ReviewSnapshotError(
            "bundle directory name does not match snapshot_instance_id"
        )
    referenced = _referenced_objects(snapshot)
    expected_hex = {
        digest.removeprefix("sha256:") for digest in referenced
    }
    _verify_bundle_tree(bundle, expected_hex)
    raw_by_digest: dict[str, bytes] = {}
    for digest, expected_size in referenced.items():
        hex_digest = digest.removeprefix("sha256:")
        raw = _read_regular_file(
            bundle,
            f"objects/sha256/{hex_digest}",
            f"object {digest}",
        )
        if len(raw) != expected_size or _sha256_id(raw) != digest:
            raise ReviewSnapshotError(f"object {digest} does not match")
        raw_by_digest[digest] = raw
    _verify_offline_file_provenance(snapshot, raw_by_digest)
    _verify_bundle_tree(bundle, expected_hex)
    return snapshot


def _verify_snapshot_bundle_path(bundle: Path) -> None:
    _verify_snapshot_bundle_contents(
        bundle,
        require_instance_directory_name=True,
    )


def _verify_staging_snapshot_bundle_path(bundle: Path) -> None:
    _verify_snapshot_bundle_contents(
        bundle,
        require_instance_directory_name=False,
    )


def verify_snapshot_bundle(
    bundle_path: str | os.PathLike[str],
    *,
    expected_snapshot_content_id: str,
) -> BundleIntegrityResult:
    """Verify a self-contained snapshot bundle without a worktree."""

    try:
        expected_content_id = _require_digest(
            expected_snapshot_content_id,
            "expected_snapshot_content_id",
        )
        bundle = _coerce_path(bundle_path, "bundle_path")
        snapshot = _verify_snapshot_bundle_contents(
            bundle,
            require_instance_directory_name=True,
        )
        observed_content_id = snapshot["snapshot_content_id"]
        if observed_content_id != expected_content_id:
            raise ReviewSnapshotError(
                "bundle snapshot_content_id differs from expected value"
            )
        return BundleIntegrityResult(
            snapshot_content_id=observed_content_id,
            integrity_valid=True,
            git_provenance_state="UNVERIFIED",
            live_verification_state="UNVERIFIED",
            authorization_state="NOT_AUTHORIZED",
        )
    except ReviewSnapshotError:
        raise
    except Exception as exc:
        raise ReviewSnapshotError("bundle verification failed") from exc


def _plain_directory_identity(
    path: Path,
    label: str,
) -> tuple[int, int, int]:
    try:
        file_stat = path.lstat()
    except OSError as exc:
        raise ReviewSnapshotError(f"{label} is not accessible") from exc
    if _is_link_or_reparse(file_stat) or not stat.S_ISDIR(
        file_stat.st_mode
    ):
        raise ReviewSnapshotError(f"{label} must be a plain directory")
    return _stat_identity(file_stat)


def _retained_staging_detail(
    staging_bundle: Path,
    expected_identity: tuple[int, int, int] | None,
) -> str:
    try:
        file_stat = staging_bundle.lstat()
    except FileNotFoundError:
        return (
            "staging bundle disappeared before it could be retained: "
            f"{staging_bundle}"
        )
    except OSError:
        return (
            "staging bundle could not be inspected and was left untouched: "
            f"{staging_bundle}"
        )
    if (
        expected_identity is None
        or _is_link_or_reparse(file_stat)
        or not stat.S_ISDIR(file_stat.st_mode)
        or _stat_identity(file_stat) != expected_identity
    ):
        return (
            "staging bundle path identity changed and was left untouched: "
            f"{staging_bundle}"
        )
    return f"staging bundle retained at: {staging_bundle}"


def _linux_rename_directory_no_replace(
    source: Path,
    target: Path,
) -> None:
    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except (AttributeError, OSError) as exc:
        raise ReviewSnapshotError(
            "Linux atomic no-replace publication is unavailable"
        ) from exc
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    source_raw = os.fsencode(source)
    target_raw = os.fsencode(target)
    ctypes.set_errno(0)
    result = renameat2(
        -100,
        source_raw,
        -100,
        target_raw,
        1,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise FileExistsError(
            error_number,
            os.strerror(error_number),
            target,
        )
    if error_number in {errno.EINVAL, errno.ENOSYS, errno.ENOTSUP}:
        raise ReviewSnapshotError(
            "Linux atomic no-replace publication is unsupported"
        )
    raise OSError(
        error_number,
        os.strerror(error_number),
        target,
    )


def _rename_directory_no_replace(
    source: Path,
    target: Path,
) -> None:
    if os.name == "nt":
        os.rename(source, target)
        return
    if os.name == "posix" and sys.platform.startswith("linux"):
        _linux_rename_directory_no_replace(source, target)
        return
    raise ReviewSnapshotError(
        "atomic no-replace publication is unsupported on this platform"
    )


def write_snapshot_bundle(
    snapshot: dict[str, Any],
    repository_root: str | os.PathLike[str],
    destination_root: str | os.PathLike[str],
) -> Path:
    """Create a new deduplicated, self-contained snapshot bundle."""

    staging_bundle: Path | None = None
    staging_bundle_identity: tuple[int, int, int] | None = None
    target: Path | None = None
    target_published = False
    try:
        _validate_snapshot_structure(snapshot)
        frozen = _canonical_clone(snapshot)
        _validate_snapshot_structure(frozen)
        root = _repository_root(repository_root)
        first_evidence_raw = _verify_live_snapshot(frozen, root)

        destination = _coerce_path(destination_root, "destination_root")
        _require_plain_directory(destination, "destination_root")
        destination = destination.resolve(strict=True)
        target = destination / frozen["snapshot_instance_id"]
        if os.path.lexists(target):
            raise ReviewSnapshotError("snapshot bundle already exists")

        staging_bundle = Path(
            tempfile.mkdtemp(
                prefix=".review-snapshot-",
                dir=destination,
            )
        )
        staging_bundle_identity = _plain_directory_identity(
            staging_bundle,
            "staging bundle",
        )
        sha_directory = staging_bundle / "objects" / "sha256"
        sha_directory.mkdir(parents=True, exist_ok=False)
        manifest_raw = _canonical_bytes(frozen, "snapshot") + b"\n"
        with (staging_bundle / "manifest.json").open("xb") as manifest:
            manifest.write(manifest_raw)
            manifest.flush()
            os.fsync(manifest.fileno())

        written: set[str] = set()
        for entry in (
            frozen["files"] + frozen["external_normative_sources"]
        ):
            repository_path = entry["repository_path"]
            raw = _read_regular_file(
                root,
                repository_path,
                f"bundle source {repository_path}",
            )
            digest = _sha256_id(raw)
            if len(raw) != entry["byte_size"] or digest != entry["sha256"]:
                raise ReviewSnapshotError(
                    f"bundle source {repository_path} changed"
                )
            if digest in written:
                continue
            object_path = sha_directory / digest.removeprefix("sha256:")
            with object_path.open("xb") as object_file:
                object_file.write(raw)
                object_file.flush()
                os.fsync(object_file.fileno())
            written.add(digest)

        for entry in frozen["repository_evidence"]:
            raw = first_evidence_raw[entry["command_id"]]
            digest = _sha256_id(raw)
            if len(raw) != entry["byte_size"] or digest != entry["sha256"]:
                raise ReviewSnapshotError(
                    f"repository evidence {entry['command_id']} changed"
                )
            if digest in written:
                continue
            object_path = sha_directory / digest.removeprefix("sha256:")
            with object_path.open("xb") as object_file:
                object_file.write(raw)
                object_file.flush()
                os.fsync(object_file.fileno())
            written.add(digest)

        final_evidence_raw = _verify_live_snapshot(frozen, root)
        if final_evidence_raw != first_evidence_raw:
            raise ReviewSnapshotError(
                "repository evidence changed while creating bundle"
            )
        _verify_staging_snapshot_bundle_path(staging_bundle)

        if os.path.lexists(target):
            raise ReviewSnapshotError("snapshot bundle already exists")
        try:
            _rename_directory_no_replace(staging_bundle, target)
        except FileExistsError as exc:
            raise ReviewSnapshotError(
                "snapshot bundle already exists"
            ) from exc
        target_published = True
        _verify_snapshot_bundle_path(target)
        return target
    except ReviewSnapshotError as exc:
        if staging_bundle is not None and not target_published:
            detail = _retained_staging_detail(
                staging_bundle,
                staging_bundle_identity,
            )
            raise ReviewSnapshotError(f"{exc}; {detail}") from exc
        raise
    except Exception as exc:
        message = "bundle creation failed"
        if staging_bundle is not None and not target_published:
            detail = _retained_staging_detail(
                staging_bundle,
                staging_bundle_identity,
            )
            message = f"{message}; {detail}"
        raise ReviewSnapshotError(message) from exc
