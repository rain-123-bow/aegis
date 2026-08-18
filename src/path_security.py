from __future__ import annotations

import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence


class PathSecurityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FileIdentity:
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True, slots=True)
class StablePathSpec:
    path: Path
    allowed_root: Path
    label: str
    directory: bool = False


def lexical_absolute(path: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.fspath(lexical_absolute(left))) == os.path.normcase(
        os.fspath(lexical_absolute(right))
    )


def is_within(path: str | Path, root: str | Path) -> bool:
    candidate = os.path.normcase(os.fspath(lexical_absolute(path)))
    boundary = os.path.normcase(os.fspath(lexical_absolute(root)))
    try:
        return os.path.commonpath((candidate, boundary)) == boundary
    except ValueError:
        return False


def require_no_reparse(
    root: str | Path,
    path: str | Path,
    *,
    label: str,
    allow_missing_final: bool = False,
) -> Path:
    boundary = lexical_absolute(root)
    candidate = lexical_absolute(path)
    if not is_within(candidate, boundary):
        raise PathSecurityError(f"{label} is outside its allowed root")

    relative = candidate.relative_to(boundary)
    components = (boundary, *(boundary / Path(*relative.parts[:index]) for index in range(1, len(relative.parts) + 1)))
    for index, current in enumerate(components):
        is_final = index == len(components) - 1
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            if allow_missing_final and is_final:
                continue
            raise PathSecurityError(f"{label} is missing: {current}") from None
        attributes = int(getattr(info, "st_file_attributes", 0))
        reparse_mask = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
        if stat.S_ISLNK(info.st_mode) or attributes & reparse_mask:
            raise PathSecurityError(f"{label} contains a symlink or reparse point: {current}")
    return candidate


def read_regular_file(
    path: str | Path,
    *,
    allowed_root: str | Path,
    label: str,
    max_bytes: int | None = None,
) -> tuple[bytes, FileIdentity]:
    checked = require_no_reparse(allowed_root, path, label=label)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(checked, flags)
    except OSError as error:
        raise PathSecurityError(f"cannot open {label}: {error}") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise PathSecurityError(f"{label} is not a regular file")
        _verify_open_handle_path(descriptor, checked, label)
        if max_bytes is not None and before.st_size > max_bytes:
            raise PathSecurityError(f"{label} exceeds the maximum size")
        chunks: list[bytes] = []
        remaining = max_bytes
        while True:
            request_size = 1024 * 1024
            if remaining is not None:
                request_size = min(request_size, remaining + 1)
            chunk = os.read(descriptor, request_size)
            if not chunk:
                break
            chunks.append(chunk)
            if remaining is not None:
                remaining -= len(chunk)
                if remaining < 0:
                    raise PathSecurityError(f"{label} exceeds the maximum size")
        after = os.fstat(descriptor)
        before_identity = _identity(before)
        after_identity = _identity(after)
        if before_identity != after_identity:
            raise PathSecurityError(f"{label} changed while it was read")
        content = b"".join(chunks)
        if len(content) != after.st_size:
            raise PathSecurityError(f"{label} size changed while it was read")
        return content, after_identity
    finally:
        os.close(descriptor)


@contextmanager
def hold_paths_stable(specs: Sequence[StablePathSpec]) -> Iterator[None]:
    """Hold Windows share locks that deny write/delete until the caller exits.

    Aegis production execution is Windows-local.  The non-Windows branch keeps
    descriptors open and relies on the before/after identity checks performed
    by the caller; it is present only for portable unit fixtures.
    """
    normalized: list[StablePathSpec] = []
    for spec in specs:
        path = require_no_reparse(
            spec.allowed_root,
            spec.path,
            label=spec.label,
        )
        if spec.directory:
            if not path.is_dir():
                raise PathSecurityError(f"{spec.label} is not a directory")
        elif not path.is_file():
            raise PathSecurityError(f"{spec.label} is not a regular file")
        normalized.append(
            StablePathSpec(path, lexical_absolute(spec.allowed_root), spec.label, spec.directory)
        )

    if os.name != "nt":
        descriptors: list[int] = []
        try:
            for spec in normalized:
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                if spec.directory:
                    flags |= getattr(os, "O_DIRECTORY", 0)
                descriptors.append(os.open(spec.path, flags))
            yield
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)
        return

    handles = _lock_windows_paths(normalized)
    try:
        yield
    finally:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        for handle in reversed(handles):
            kernel32.CloseHandle(handle)


def _lock_windows_paths(specs: Sequence[StablePathSpec]) -> list[int]:
    import ctypes
    from ctypes import wintypes

    generic_read = 0x80000000
    file_read_attributes = 0x0080
    file_share_read = 0x00000001
    open_existing = 3
    file_flag_backup_semantics = 0x02000000
    file_flag_open_reparse_point = 0x00200000
    invalid_handle = ctypes.c_void_p(-1).value
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetFileAttributesW.restype = wintypes.DWORD

    directories: dict[str, tuple[Path, str]] = {}
    files: dict[str, tuple[Path, str]] = {}
    for spec in specs:
        if spec.directory:
            directories.setdefault(str(spec.path).casefold(), (spec.path, spec.label))
        else:
            files.setdefault(str(spec.path).casefold(), (spec.path, spec.label))
        parent = spec.path if spec.directory else spec.path.parent
        anchor = Path(parent.anchor)
        while parent != anchor:
            directories.setdefault(
                str(parent).casefold(),
                (parent, f"{spec.label} ancestor directory"),
            )
            parent = parent.parent

    handles: list[int] = []
    try:
        for path, label in (*directories.values(), *files.values()):
            directory = str(path).casefold() in directories
            access = file_read_attributes if directory else generic_read
            flags = file_flag_open_reparse_point | (
                file_flag_backup_semantics if directory else 0
            )
            handle = kernel32.CreateFileW(
                str(path),
                access,
                file_share_read,
                None,
                open_existing,
                flags,
                None,
            )
            if handle == invalid_handle:
                raise PathSecurityError(
                    f"cannot lock {label}: Windows error {ctypes.get_last_error()}"
                )
            handles.append(int(handle))
            final_path = _windows_final_path_from_raw_handle(int(handle))
            if not same_path(final_path, path):
                raise PathSecurityError(
                    f"locked {label} opened a different final path"
                )
            attributes = int(kernel32.GetFileAttributesW(str(path)))
            if attributes == 0xFFFFFFFF:
                raise PathSecurityError(
                    f"cannot inspect locked {label}: Windows error {ctypes.get_last_error()}"
                )
            if attributes & int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
                raise PathSecurityError(f"locked {label} became a reparse point")
    except BaseException:
        for handle in reversed(handles):
            kernel32.CloseHandle(handle)
        raise
    return handles


def _windows_final_path_from_raw_handle(handle: int) -> Path:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_final_path = kernel32.GetFinalPathNameByHandleW
    get_final_path.argtypes = (
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    )
    get_final_path.restype = wintypes.DWORD
    required = get_final_path(handle, None, 0, 0)
    if required == 0:
        raise PathSecurityError(
            f"cannot inspect locked path: Windows error {ctypes.get_last_error()}"
        )
    buffer = ctypes.create_unicode_buffer(required + 1)
    written = get_final_path(handle, buffer, len(buffer), 0)
    if written == 0 or written >= len(buffer):
        raise PathSecurityError(
            f"cannot inspect locked path: Windows error {ctypes.get_last_error()}"
        )
    value = buffer.value
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return Path(value)


def _identity(value: os.stat_result) -> FileIdentity:
    return FileIdentity(
        device=int(value.st_dev),
        inode=int(value.st_ino),
        size=int(value.st_size),
        modified_ns=int(value.st_mtime_ns),
        changed_ns=int(value.st_ctime_ns),
    )


def _verify_open_handle_path(descriptor: int, expected: Path, label: str) -> None:
    if os.name != "nt":
        final_path = Path(os.path.realpath(expected))
    else:
        final_path = _windows_final_path(descriptor)
    if not same_path(final_path, expected):
        raise PathSecurityError(f"{label} opened a different final path")


def _windows_final_path(descriptor: int) -> Path:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    get_final_path = ctypes.windll.kernel32.GetFinalPathNameByHandleW
    get_final_path.argtypes = (
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    )
    get_final_path.restype = wintypes.DWORD
    handle = wintypes.HANDLE(msvcrt.get_osfhandle(descriptor))
    required = get_final_path(handle, None, 0, 0)
    if required == 0:
        raise ctypes.WinError()
    buffer = ctypes.create_unicode_buffer(required + 1)
    written = get_final_path(handle, buffer, len(buffer), 0)
    if written == 0 or written >= len(buffer):
        raise ctypes.WinError()
    value = buffer.value
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return Path(value)
