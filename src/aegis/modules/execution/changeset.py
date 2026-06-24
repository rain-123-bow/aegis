"""Implementation changeset validation."""

from __future__ import annotations

import hashlib
from pathlib import Path

from aegis.modules.execution.models import (
    ChangedFile,
    ExpectedFileChange,
    FileTreeEntry,
    FileTreeSnapshot,
    ImplementationChangeSet,
)


def scan_code_tree(code_root: str | Path) -> FileTreeSnapshot:
    """Capture a deterministic file snapshot under code_root."""

    root = Path(code_root).resolve()
    entries: list[FileTreeEntry] = []
    if root.exists():
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            rel = path.relative_to(root).as_posix()
            entries.append(
                FileTreeEntry(
                    path=rel,
                    sha256=_sha256_file(path),
                    size_bytes=path.stat().st_size,
                )
            )
    return FileTreeSnapshot(root=str(root), entries=entries)


def diff_code_tree_snapshots(
    before: FileTreeSnapshot,
    after: FileTreeSnapshot,
) -> list[ChangedFile]:
    """Compute changed files from two scanner snapshots."""

    before_by_path = {entry.path: entry for entry in before.entries}
    after_by_path = {entry.path: entry for entry in after.entries}
    changed: list[ChangedFile] = []
    for rel_path in sorted(set(before_by_path) | set(after_by_path)):
        before_entry = before_by_path.get(rel_path)
        after_entry = after_by_path.get(rel_path)
        if before_entry is None and after_entry is not None:
            changed.append(
                ChangedFile(
                    path=rel_path,
                    change_type="added",
                    within_code_root=True,
                    sha256_before=None,
                    sha256_after=after_entry.sha256,
                )
            )
        elif before_entry is not None and after_entry is None:
            changed.append(
                ChangedFile(
                    path=rel_path,
                    change_type="deleted",
                    within_code_root=True,
                    sha256_before=before_entry.sha256,
                    sha256_after=None,
                )
            )
        elif (
            before_entry is not None
            and after_entry is not None
            and before_entry.sha256 != after_entry.sha256
        ):
            changed.append(
                ChangedFile(
                    path=rel_path,
                    change_type="modified",
                    within_code_root=True,
                    sha256_before=before_entry.sha256,
                    sha256_after=after_entry.sha256,
                )
            )
    return changed


def validate_implementation_changeset(
    changeset: ImplementationChangeSet,
    expected_changes: list[ExpectedFileChange],
) -> ImplementationChangeSet:
    """Match changed files to expected change ids and block unexpected writes."""

    expected_by_path = {change.path.replace("\\", "/"): change for change in expected_changes}
    changed: list[ChangedFile] = []
    unexpected: list[str] = []
    forbidden: list[str] = []

    for item in changeset.changed_files:
        normalized = item.path.replace("\\", "/")
        if not item.within_code_root:
            forbidden.append(item.path)
            changed.append(item.model_copy(update={"expected_by_plan": False}))
            continue
        expected = expected_by_path.get(normalized)
        if expected and item.change_type in expected.allowed_change_types:
            changed.append(
                item.model_copy(
                    update={
                        "expected_by_plan": True,
                        "expected_change_id": expected.change_id,
                    }
                )
            )
        else:
            unexpected.append(item.path)
            changed.append(item.model_copy(update={"expected_by_plan": False}))

    return changeset.model_copy(
        update={
            "changed_files": changed,
            "unexpected_changes": unexpected,
            "forbidden_changes": forbidden,
            "status": "blocked" if unexpected or forbidden else "accepted",
        }
    )


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
