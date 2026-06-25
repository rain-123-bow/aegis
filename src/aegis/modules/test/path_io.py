"""Filesystem helpers for Test Subgraph paths."""

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


def ref_path(path: str | Path) -> str:
    resolved = str(Path(path).resolve())
    if os.name == "nt" and len(resolved) >= 240:
        return fs_path(path)
    return resolved


def comparable_path(path: str | Path) -> str:
    resolved = normal_path_string(str(Path(path).resolve()))
    return os.path.normcase(resolved)


def normal_path_string(path: str) -> str:
    resolved = path
    if resolved.startswith("\\\\?\\UNC\\"):
        resolved = "\\\\" + resolved.removeprefix("\\\\?\\UNC\\")
    elif resolved.startswith("\\\\?\\"):
        resolved = resolved.removeprefix("\\\\?\\")
    return resolved


def same_path(left: str | Path, right: str | Path) -> bool:
    return comparable_path(left) == comparable_path(right)


def path_exists(path: str | Path) -> bool:
    return os.path.exists(fs_path(path))


def path_is_file(path: str | Path) -> bool:
    return os.path.isfile(fs_path(path))


def path_is_dir(path: str | Path) -> bool:
    return os.path.isdir(fs_path(path))


def mkdir(path: str | Path) -> None:
    os.makedirs(fs_path(path), exist_ok=True)


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


__all__ = [
    "comparable_path",
    "fs_path",
    "iter_files",
    "mkdir",
    "normal_path_string",
    "path_exists",
    "path_is_dir",
    "path_is_file",
    "read_bytes",
    "read_text",
    "ref_path",
    "same_path",
    "write_text",
]
