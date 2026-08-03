from __future__ import annotations

import hashlib
import re
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUNDLED_EXECUTABLE = (
    PROJECT_ROOT
    / "third_party"
    / "AegisSealCore"
    / "windows-x64"
    / "aegis-seal.exe"
)
BUNDLED_SHA256 = "256b71015465a7a57b648753834583e095383d77d88d2140e5e970a174375023"

_MANIFEST_MAGIC = b"ASC1MF\r\n"
_SEAL_PATTERN = re.compile(r"ASC1:[0-9a-f]{64}")
_PROCESS_TIMEOUT_SECONDS = 300
_MAX_FILE_COUNT = 100_000
_MAX_PATH_BYTES = 32_768
_MAX_FILE_BYTES = 256 * 1024 * 1024
_MAX_TOTAL_BYTES = 1024 * 1024 * 1024


class AegisSealError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SealContext:
    project_id: bytes
    run_id: bytes
    sequence: int = 0
    previous_seal: bytes = bytes(32)

    def __post_init__(self) -> None:
        _require_bytes("project_id", self.project_id, 16)
        _require_bytes("run_id", self.run_id, 16)
        _require_bytes("previous_seal", self.previous_seal, 32)
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise ValueError("sequence must be an unsigned 64-bit integer")
        if self.sequence < 0 or self.sequence > 0xFFFF_FFFF_FFFF_FFFF:
            raise ValueError("sequence must be an unsigned 64-bit integer")
        if self.sequence == 0 and any(self.previous_seal):
            raise ValueError("sequence zero requires a zero previous seal")
        if self.sequence > 0 and not any(self.previous_seal):
            raise ValueError("positive sequence requires a previous seal")


def _require_bytes(name: str, value: bytes, size: int) -> None:
    if not isinstance(value, bytes) or len(value) != size:
        raise ValueError(f"{name} must contain exactly {size} bytes")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_bundled_executable(
    executable: Path = BUNDLED_EXECUTABLE,
) -> Path:
    executable = Path(executable).resolve()
    if not executable.is_file():
        raise AegisSealError(f"AegisSealCore executable is missing: {executable}")
    actual_sha256 = _sha256(executable)
    if actual_sha256 != BUNDLED_SHA256:
        raise AegisSealError(
            "AegisSealCore executable SHA-256 mismatch: "
            f"expected={BUNDLED_SHA256}, actual={actual_sha256}"
        )
    return executable


def _collect_core_files(project_root: Path) -> list[tuple[str, bytes]]:
    project_root = Path(project_root).resolve()
    if not project_root.is_dir():
        raise AegisSealError(f"project root is not a directory: {project_root}")

    entries: list[tuple[str, bytes]] = []
    for scope_name in ("src", "include"):
        scope = project_root / scope_name
        if not scope.exists():
            continue
        if not scope.is_dir():
            raise AegisSealError(f"core scope is not a directory: {scope}")
        for path in scope.rglob("*"):
            relative = path.relative_to(project_root)
            if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            if path.is_symlink():
                raise AegisSealError(f"core source must not be a symlink: {relative}")
            if path.is_dir():
                continue
            if not path.is_file():
                raise AegisSealError(f"unsupported core source type: {relative}")
            logical_path = relative.as_posix()
            try:
                logical_path.encode("utf-8", errors="strict")
            except UnicodeEncodeError as error:
                raise AegisSealError(
                    f"core source path is not valid UTF-8: {relative}"
                ) from error
            entries.append((logical_path, path.read_bytes()))

    if not entries:
        raise AegisSealError("project contains no src/ or include/ core files")
    entries.sort(key=lambda entry: entry[0].encode("utf-8"))
    return entries


def _write_manifest(
    manifest_path: Path,
    context: SealContext,
    entries: list[tuple[str, bytes]],
) -> None:
    if len(entries) > _MAX_FILE_COUNT:
        raise AegisSealError("core file count exceeds ASC-1 v1 limit")

    total_content_bytes = 0
    with manifest_path.open("xb") as output:
        output.write(_MANIFEST_MAGIC)
        output.write(context.project_id)
        output.write(context.run_id)
        output.write(struct.pack("<Q", context.sequence))
        output.write(context.previous_seal)
        output.write(struct.pack("<I", len(entries)))
        for logical_path, content in entries:
            path_bytes = logical_path.encode("utf-8")
            if len(path_bytes) > _MAX_PATH_BYTES:
                raise AegisSealError("core source path exceeds ASC-1 v1 limit")
            if len(content) > _MAX_FILE_BYTES:
                raise AegisSealError("core source exceeds ASC-1 v1 per-file limit")
            total_content_bytes += len(content)
            if total_content_bytes > _MAX_TOTAL_BYTES:
                raise AegisSealError("core sources exceed ASC-1 v1 total limit")
            output.write(struct.pack("<I", len(path_bytes)))
            output.write(path_bytes)
            output.write(struct.pack("<Q", len(content)))
            output.write(content)


def _run_seal_core(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    executable = verify_bundled_executable()
    try:
        return subprocess.run(
            [str(executable), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            check=False,
            timeout=_PROCESS_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as error:
        raise AegisSealError(f"AegisSealCore process failed: {error}") from error


def compute_project_seal(project_root: Path, context: SealContext) -> str:
    entries = _collect_core_files(project_root)
    with tempfile.TemporaryDirectory(prefix="aegis-seal-") as temporary_directory:
        manifest_path = Path(temporary_directory) / "project.asc1mf"
        _write_manifest(manifest_path, context, entries)
        completed = _run_seal_core(["compute", str(manifest_path)])

    seal = completed.stdout.rstrip("\r\n")
    if (
        completed.returncode != 0
        or completed.stderr
        or _SEAL_PATTERN.fullmatch(seal) is None
    ):
        raise AegisSealError(
            "AegisSealCore compute failed: "
            f"exit_code={completed.returncode}, "
            f"stdout={completed.stdout!r}, stderr={completed.stderr!r}"
        )
    return seal


def verify_project_seal(
    project_root: Path,
    context: SealContext,
    expected_seal: str,
) -> bool:
    if _SEAL_PATTERN.fullmatch(expected_seal) is None:
        raise ValueError("expected_seal must use canonical ASC1 lowercase form")

    entries = _collect_core_files(project_root)
    with tempfile.TemporaryDirectory(prefix="aegis-seal-") as temporary_directory:
        manifest_path = Path(temporary_directory) / "project.asc1mf"
        _write_manifest(manifest_path, context, entries)
        completed = _run_seal_core(
            ["verify", str(manifest_path), expected_seal]
        )

    output = completed.stdout.rstrip("\r\n")
    if completed.returncode == 0 and output == "MATCH" and not completed.stderr:
        return True
    if completed.returncode == 2 and output == "MISMATCH" and not completed.stderr:
        return False
    raise AegisSealError(
        "AegisSealCore verify failed: "
        f"exit_code={completed.returncode}, "
        f"stdout={completed.stdout!r}, stderr={completed.stderr!r}"
    )
