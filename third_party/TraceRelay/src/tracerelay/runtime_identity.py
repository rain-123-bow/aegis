"""Fail-closed identity for the detached TraceRelay runtime."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from ctypes import wintypes
from pathlib import Path
from typing import Any, Mapping


RUNTIME_IDENTITY_SCHEMA = "tracerelay.runtime_identity.v1"
_HEX_32 = re.compile(r"[0-9a-f]{32}")
_HEX_64 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class RuntimeExpectation:
    runtime_nonce: str
    sdk_manifest_sha256: str
    python_executable_sha256: str

    @classmethod
    def create(
        cls,
        *,
        runtime_nonce: object,
        sdk_manifest_sha256: object,
        python_executable_sha256: object,
    ) -> RuntimeExpectation:
        if not isinstance(runtime_nonce, str) or _HEX_32.fullmatch(runtime_nonce) is None:
            raise ValueError("runtime nonce must be 32 lowercase hexadecimal characters")
        for name, value in (
            ("SDK manifest SHA-256", sdk_manifest_sha256),
            ("Python executable SHA-256", python_executable_sha256),
        ):
            if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
                raise ValueError(f"{name} must be 64 lowercase hexadecimal characters")
        return cls(runtime_nonce, sdk_manifest_sha256, python_executable_sha256)

    def command_arguments(self) -> list[str]:
        return [
            "--runtime-nonce",
            self.runtime_nonce,
            "--expected-sdk-manifest-sha256",
            self.sdk_manifest_sha256,
            "--expected-python-sha256",
            self.python_executable_sha256,
        ]


def capture_process_identity(
    role: str,
    process_id: int,
    expectation: RuntimeExpectation,
) -> dict[str, object]:
    if role not in {"supervisor", "service"}:
        raise ValueError("runtime process role must be supervisor or service")
    if isinstance(process_id, bool) or not isinstance(process_id, int) or process_id <= 0:
        raise ValueError("runtime process ID must be a positive integer")
    if process_id != os.getpid():
        raise ValueError("a process may capture only its own runtime identity")
    executable = Path(sys.executable).resolve(strict=True)
    executable_sha256 = _sha256_file(executable)
    sdk_manifest_sha256 = package_manifest_sha256()
    flags = {
        "isolated": bool(sys.flags.isolated),
        "dont_write_bytecode": bool(sys.flags.dont_write_bytecode),
        "safe_path": bool(sys.flags.safe_path),
    }
    if flags != {
        "isolated": True,
        "dont_write_bytecode": True,
        "safe_path": True,
    }:
        raise RuntimeError("TraceRelay runtime requires Python -I -B safe-path isolation")
    if executable_sha256 != expectation.python_executable_sha256:
        raise RuntimeError("TraceRelay Python executable differs from the expected digest")
    if sdk_manifest_sha256 != expectation.sdk_manifest_sha256:
        raise RuntimeError("TraceRelay SDK source differs from the expected manifest")
    return {
        "role": role,
        "pid": process_id,
        "creation_time_100ns": process_creation_time_100ns(process_id),
        "python_executable": str(executable),
        "python_executable_sha256": executable_sha256,
        "sdk_manifest_sha256": sdk_manifest_sha256,
        "python_flags": flags,
    }


def build_managed_runtime_identity(
    expectation: RuntimeExpectation,
    supervisor: Mapping[str, object],
    service: Mapping[str, object],
) -> dict[str, object]:
    _validate_process_identity(supervisor, "supervisor", expectation)
    _validate_process_identity(service, "service", expectation)
    return {
        "schema": RUNTIME_IDENTITY_SCHEMA,
        "runtime_nonce": expectation.runtime_nonce,
        "sdk_manifest_sha256": expectation.sdk_manifest_sha256,
        "python_executable_sha256": expectation.python_executable_sha256,
        "processes": {
            "supervisor": dict(supervisor),
            "service": dict(service),
        },
    }


def matches_expectation(
    value: object,
    expectation: RuntimeExpectation,
) -> bool:
    try:
        validate_runtime_identity(value, expectation)
    except (TypeError, ValueError):
        return False
    return True


def validate_runtime_identity(
    value: object,
    expectation: RuntimeExpectation,
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "runtime_nonce",
        "sdk_manifest_sha256",
        "python_executable_sha256",
        "processes",
    }:
        raise ValueError("TraceRelay runtime identity fields are invalid")
    if (
        value.get("schema") != RUNTIME_IDENTITY_SCHEMA
        or value.get("runtime_nonce") != expectation.runtime_nonce
        or value.get("sdk_manifest_sha256") != expectation.sdk_manifest_sha256
        or value.get("python_executable_sha256")
        != expectation.python_executable_sha256
    ):
        raise ValueError("TraceRelay runtime identity differs from its expectation")
    processes = value.get("processes")
    if not isinstance(processes, dict) or set(processes) != {"supervisor", "service"}:
        raise ValueError("TraceRelay runtime process identities are invalid")
    for role in ("supervisor", "service"):
        process = processes.get(role)
        if not isinstance(process, dict):
            raise ValueError("TraceRelay runtime process identity must be an object")
        _validate_process_identity(process, role, expectation)
    return dict(value)


def package_manifest_sha256() -> str:
    package_root = Path(__file__).resolve(strict=True).parent
    descriptors: list[dict[str, object]] = []
    for path in sorted(
        package_root.rglob("*.py"),
        key=lambda candidate: candidate.relative_to(package_root).as_posix().encode(
            "utf-8"
        ),
    ):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("TraceRelay package source contains a non-regular file")
        relative = path.relative_to(package_root).as_posix()
        content = path.read_bytes()
        descriptors.append(
            {
                "path": f"src/tracerelay/{relative}",
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    if not descriptors:
        raise RuntimeError("TraceRelay package source manifest is empty")
    encoded = json.dumps(
        descriptors,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def process_creation_time_100ns(process_id: int) -> int:
    if os.name != "nt":
        raise RuntimeError("TraceRelay runtime identity only supports Windows")
    query_limited_information = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    open_process.restype = wintypes.HANDLE
    get_process_times = kernel32.GetProcessTimes
    get_process_times.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    )
    get_process_times.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    handle = open_process(query_limited_information, False, process_id)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    creation = wintypes.FILETIME()
    exit_time = wintypes.FILETIME()
    kernel_time = wintypes.FILETIME()
    user_time = wintypes.FILETIME()
    try:
        if not get_process_times(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        value = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        if value <= 0:
            raise RuntimeError("TraceRelay process creation time is invalid")
        return int(value)
    finally:
        close_handle(handle)


def _validate_process_identity(
    value: Mapping[str, Any],
    role: str,
    expectation: RuntimeExpectation,
) -> None:
    if set(value) != {
        "role",
        "pid",
        "creation_time_100ns",
        "python_executable",
        "python_executable_sha256",
        "sdk_manifest_sha256",
        "python_flags",
    }:
        raise ValueError("TraceRelay process identity fields are invalid")
    if value.get("role") != role:
        raise ValueError("TraceRelay process role differs")
    for name in ("pid", "creation_time_100ns"):
        item = value.get(name)
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise ValueError(f"TraceRelay process {name} is invalid")
    executable = value.get("python_executable")
    if not isinstance(executable, str) or not Path(executable).is_absolute():
        raise ValueError("TraceRelay Python executable path is invalid")
    if (
        value.get("python_executable_sha256")
        != expectation.python_executable_sha256
        or value.get("sdk_manifest_sha256") != expectation.sdk_manifest_sha256
        or value.get("python_flags")
        != {
            "isolated": True,
            "dont_write_bytecode": True,
            "safe_path": True,
        }
    ):
        raise ValueError("TraceRelay process runtime identity differs")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
