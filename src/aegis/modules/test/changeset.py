"""Code tree diff scanner for Test Subgraph v2."""

from __future__ import annotations

import hashlib
from pathlib import Path

from aegis.modules.test.models import TestRunChangeSet, TestRunChangedFile
from aegis.modules.test.path_io import fs_path, iter_files, path_exists


def scan_code_tree(root: str | Path) -> dict[str, str]:
    base = Path(root).resolve()
    if not path_exists(base):
        return {}
    entries: dict[str, str] = {}
    for path in iter_files(base):
        entries[path.relative_to(base).as_posix()] = _sha256_file(path)
    return entries


def tree_hash(snapshot: dict[str, str]) -> str:
    hasher = hashlib.sha256()
    for rel, sha in sorted(snapshot.items()):
        hasher.update(rel.encode("utf-8"))
        hasher.update(sha.encode("ascii"))
    return hasher.hexdigest()


def diff_code_tree(before: dict[str, str], after: dict[str, str]) -> TestRunChangeSet:
    changed: list[TestRunChangedFile] = []
    all_paths = sorted(set(before) | set(after))
    for rel in all_paths:
        old = before.get(rel)
        new = after.get(rel)
        if old == new:
            continue
        if old is None:
            change_type = "added"
        elif new is None:
            change_type = "deleted"
        else:
            change_type = "modified"
        changed.append(
            TestRunChangedFile(
                path=rel,
                change_type=change_type,  # type: ignore[arg-type]
                within_code_root=True,
                allowed_runtime_change=False,
                sha256_before=old,
                sha256_after=new,
            )
        )
    forbidden = [item.path for item in changed if not item.allowed_runtime_change]
    return TestRunChangeSet(
        before_code_tree_hash=tree_hash(before),
        after_code_tree_hash=tree_hash(after),
        changed_files=changed,
        forbidden_code_changes=forbidden,
        allowed_runtime_changes=[],
        status="blocked" if forbidden else "clean",
    )


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(fs_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
