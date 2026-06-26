"""Filesystem helpers for Final Review Subgraph paths."""

from __future__ import annotations

import os
from pathlib import Path


def fs_path(path: str | Path) -> str:
    resolved = str(Path(path).resolve())
    if os.name != "nt" or resolved.startswith("\\\\?\\"):
        return resolved
    if resolved.startswith("\\\\"):
        return "\\\\?\\UNC\\" + resolved.lstrip("\\")
    return "\\\\?\\" + resolved


def normal_path_string(path: str) -> str:
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path.removeprefix("\\\\?\\UNC\\")
    if path.startswith("\\\\?\\"):
        return path.removeprefix("\\\\?\\")
    return path


def ref_path(path: str | Path) -> str:
    resolved = str(Path(path).resolve())
    if os.name == "nt" and len(resolved) >= 240:
        return fs_path(path)
    return resolved


def mkdir(path: str | Path) -> None:
    os.makedirs(fs_path(path), exist_ok=True)


def path_exists(path: str | Path) -> bool:
    return os.path.exists(fs_path(path))


def read_text(path: str | Path) -> str:
    with open(fs_path(path), encoding="utf-8") as handle:
        return handle.read()


def read_bytes(path: str | Path) -> bytes:
    with open(fs_path(path), "rb") as handle:
        return handle.read()


def write_text(path: str | Path, content: str) -> None:
    target = Path(path)
    mkdir(target.parent)
    with open(fs_path(target), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def iter_files(root: str | Path) -> list[Path]:
    base = Path(root).resolve()
    if not path_exists(base):
        return []
    files: list[Path] = []
    for current, _, names in os.walk(fs_path(base)):
        for name in names:
            files.append(Path(normal_path_string(os.path.join(current, name))))
    return sorted(files, key=lambda item: item.as_posix())


def require_under_root(path: str | Path, root: str | Path, *, label: str) -> Path:
    resolved = Path(path).resolve()
    resolved_root = Path(root).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"{label} must stay under {resolved_root}") from exc
    return resolved
