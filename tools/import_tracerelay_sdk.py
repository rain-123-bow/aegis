from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from runtime_identity import (  # noqa: E402
    RuntimeIdentityError,
    hold_verified_git_runtime,
    trusted_git_environment,
)


COMPONENT_ROOT = PROJECT_ROOT / "third_party" / "TraceRelay"
SOURCE_REPOSITORY = "git@github.com:rain-123-bow/TraceRelay.git"
PROVENANCE_SCHEMA = "aegis.third_party_python_sdk_snapshot.v1"
SNAPSHOT_ROOT = Path("src/tracerelay")


class SnapshotImportError(RuntimeError):
    pass


def _git(
    git_command: Path,
    git_environment: dict[str, str],
    worktree: Path,
    *arguments: str,
) -> bytes:
    completed = subprocess.run(
        [
            str(git_command),
            "--no-replace-objects",
            "-c",
            f"core.hooksPath={os.devnull}",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "-C",
            str(worktree),
            *arguments,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=git_environment,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise SnapshotImportError(
            f"Git command failed: {' '.join(arguments)}: {detail}"
        )
    return completed.stdout


def _require_clean_upstream(
    git_command: Path,
    git_environment: dict[str, str],
    worktree: Path,
    source_commit: str,
) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise SnapshotImportError(
            "source commit must be a full lowercase Git object ID"
        )
    origin = _git(
        git_command, git_environment, worktree, "remote", "get-url", "origin"
    ).decode().strip()
    if origin != SOURCE_REPOSITORY:
        raise SnapshotImportError(f"TraceRelay origin differs: {origin}")
    head = _git(
        git_command, git_environment, worktree, "rev-parse", "HEAD"
    ).decode().strip()
    if head != source_commit:
        raise SnapshotImportError(f"TraceRelay HEAD differs: {head}")
    status = _git(
        git_command,
        git_environment,
        worktree,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if status:
        raise SnapshotImportError("TraceRelay worktree is not clean")


def _commit_tree_files(
    git_command: Path,
    git_environment: dict[str, str],
    worktree: Path,
    source_commit: str,
    selected_path: Path,
) -> list[tuple[Path, str]]:
    raw = _git(
        git_command,
        git_environment,
        worktree,
        "ls-tree",
        "-r",
        "-z",
        source_commit,
        "--",
        selected_path.as_posix(),
    )
    entries: list[tuple[Path, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split(" ")
            relative = Path(raw_path.decode("utf-8", errors="strict"))
        except (UnicodeError, ValueError) as error:
            raise SnapshotImportError(
                "TraceRelay commit tree contains an invalid entry"
            ) from error
        if mode not in {"100644", "100755"} or object_type != "blob":
            raise SnapshotImportError(
                f"TraceRelay commit tree entry is not a regular blob: {relative.as_posix()}"
            )
        entries.append((relative, object_id))
    ordered = sorted(entries, key=lambda item: item[0].as_posix().encode("utf-8"))
    return ordered


def _tracked_runtime_files(
    git_command: Path,
    git_environment: dict[str, str],
    worktree: Path,
    source_commit: str,
) -> list[tuple[Path, str]]:
    ordered = _commit_tree_files(
        git_command,
        git_environment,
        worktree,
        source_commit,
        SNAPSHOT_ROOT,
    )
    if not ordered:
        raise SnapshotImportError("TraceRelay runtime package has no tracked files")
    return ordered


def _descriptor(content: bytes, relative: Path) -> dict[str, object]:
    return {
        "path": relative.as_posix(),
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _manifest_sha256(files: list[dict[str, object]]) -> str:
    encoded = json.dumps(
        files,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def import_snapshot(
    worktree: Path,
    source_commit: str,
    *,
    git_command: Path,
    git_sha256: str,
    git_runtime_sha256: str,
) -> None:
    try:
        with hold_verified_git_runtime(
            git_command,
            expected_launcher_sha256=git_sha256,
            expected_runtime_sha256=git_runtime_sha256,
        ) as pinned_git:
            _import_snapshot_locked(
                worktree,
                source_commit,
                pinned_git=Path(pinned_git),
                git_environment=trusted_git_environment(pinned_git),
            )
    except RuntimeIdentityError as error:
        raise SnapshotImportError(str(error)) from error


def _import_snapshot_locked(
    worktree: Path,
    source_commit: str,
    *,
    pinned_git: Path,
    git_environment: dict[str, str],
) -> None:
    upstream = worktree.resolve(strict=True)
    _require_clean_upstream(
        pinned_git, git_environment, upstream, source_commit
    )
    tracked = _tracked_runtime_files(
        pinned_git, git_environment, upstream, source_commit
    )
    license_entries = _commit_tree_files(
        pinned_git,
        git_environment,
        upstream,
        source_commit,
        Path("LICENSE"),
    )
    if len(license_entries) != 1 or license_entries[0][0] != Path("LICENSE"):
        raise SnapshotImportError(
            "TraceRelay commit has no unique regular LICENSE blob"
        )

    COMPONENT_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="tracerelay-sdk-import-", dir=COMPONENT_ROOT
    ) as temporary_directory:
        temporary = Path(temporary_directory)
        descriptors: list[dict[str, object]] = []
        for relative, object_id in tracked:
            content = _git(
                pinned_git,
                git_environment,
                upstream,
                "cat-file",
                "blob",
                object_id,
            )
            destination = temporary / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            descriptors.append(_descriptor(content, relative))
        provenance = {
            "schema": PROVENANCE_SCHEMA,
            "component": "TraceRelay",
            "source_repository": SOURCE_REPOSITORY,
            "source_commit": source_commit,
            "source_tree_state": "clean",
            "snapshot_kind": "runtime-python-source",
            "snapshot_root": SNAPSHOT_ROOT.as_posix(),
            "snapshot_manifest_sha256": _manifest_sha256(descriptors),
            "files": descriptors,
        }
        provenance_path = temporary / "PROVENANCE.json"
        provenance_path.write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            errors="strict",
        )
        license_content = _git(
            pinned_git,
            git_environment,
            upstream,
            "cat-file",
            "blob",
            license_entries[0][1],
        )
        (temporary / "LICENSE").write_bytes(license_content)

        targets = {
            "src": COMPONENT_ROOT / "src",
            "PROVENANCE.json": COMPONENT_ROOT / "PROVENANCE.json",
            "LICENSE": COMPONENT_ROOT / "LICENSE",
        }
        backups = {
            name: COMPONENT_ROOT / f".{name}.previous" for name in targets
        }
        stale = [path for path in backups.values() if path.exists()]
        if stale:
            raise SnapshotImportError(
                f"stale import backup requires inspection: {stale[0]}"
            )
        moved_to_backup: list[str] = []
        installed_targets: list[str] = []
        try:
            for name, target in targets.items():
                if target.exists():
                    os.replace(target, backups[name])
                    moved_to_backup.append(name)
            for name, target in targets.items():
                os.replace(temporary / name, target)
                installed_targets.append(name)
        except BaseException:
            for name in reversed(installed_targets):
                target = targets[name]
                if target.is_dir():
                    shutil.rmtree(target)
                elif target.exists():
                    target.unlink()
            for name in reversed(moved_to_backup):
                backup = backups[name]
                if backup.exists():
                    os.replace(backup, targets[name])
            raise
        for backup in backups.values():
            if backup.is_dir():
                shutil.rmtree(backup)
            elif backup.exists():
                backup.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-worktree", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--git-command", type=Path, required=True)
    parser.add_argument("--git-sha256", required=True)
    parser.add_argument("--git-runtime-sha256", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    import_snapshot(
        arguments.upstream_worktree,
        arguments.source_commit,
        git_command=arguments.git_command,
        git_sha256=arguments.git_sha256,
        git_runtime_sha256=arguments.git_runtime_sha256,
    )
