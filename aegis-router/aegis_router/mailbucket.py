from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from time import time
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .errors import ConflictError, InvalidRequestError, PermissionDeniedError
from .path_resolution import make_dev_protected_path_token

_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")


def _safe_component(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidRequestError(f"{field_name} must be a non-empty string")
    if value in {".", ".."} or "/" in value or "\\" in value or not _SAFE_COMPONENT.fullmatch(value):
        raise InvalidRequestError(f"{field_name} contains unsafe filename characters")
    return value


def _resolve_under_root(root: Path, relative_path: str | Path, field_name: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise PermissionDeniedError(f"{field_name} must stay inside the mailbucket message folder")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise InvalidRequestError(f"{field_name} contains unsafe path components")
    resolved = (root / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        raise PermissionDeniedError(f"{field_name} resolved outside the mailbucket message folder")
    return resolved


def _timestamp_for_folder(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(timezone.utc)
    return timestamp.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def create_mailbucket_message(
    *,
    sender: str,
    receiver: str,
    shared_mailbucket_root: str | Path,
    readme_text: str,
    attachments: Mapping[str, str | Path] | None = None,
    nonce: str | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Create one temporary mailbucket message folder.

    The helper materializes files only. It does not interpret README.md or
    attachment semantics, and it does not create any retention policy.
    """
    safe_sender = _safe_component(sender, "sender")
    safe_receiver = _safe_component(receiver, "receiver")
    safe_nonce = _safe_component(nonce or uuid4().hex, "nonce")
    if not isinstance(readme_text, str) or not readme_text:
        raise InvalidRequestError("readme_text is required to create README.md")

    shared_root = Path(shared_mailbucket_root).resolve()
    shared_root.mkdir(parents=True, exist_ok=True)
    folder_name = f"{safe_sender}__{safe_receiver}__{_timestamp_for_folder(timestamp)}__{safe_nonce}"
    folder_path = (shared_root / folder_name).resolve()
    if shared_root not in folder_path.parents:
        raise PermissionDeniedError("mailbucket message folder must be under the shared root")
    if folder_path.exists():
        raise ConflictError(f"mailbucket message folder already exists: {folder_name}")

    folder_path.mkdir()
    (folder_path / "README.md").write_text(readme_text, encoding="utf-8")

    copied_attachments: list[str] = []
    for destination_name, source_path in (attachments or {}).items():
        destination = _resolve_under_root(folder_path, destination_name, "attachment destination")
        source = Path(source_path)
        if not source.is_file():
            raise InvalidRequestError(f"attachment source must be a regular file: {source_path}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied_attachments.append(str(destination.relative_to(folder_path)))

    protected_path = make_dev_protected_path_token(folder_name)
    return {
        "folder_name": folder_name,
        "folder_path": str(folder_path),
        "protected_path": protected_path,
        "resolver_material": {folder_name: folder_name},
        "attachments": copied_attachments,
    }


def cleanup_expired_mailbucket_messages(
    *,
    shared_mailbucket_root: str | Path,
    grace_period_seconds: int | float,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Delete expired public mailbucket folders using structural time only."""
    if not isinstance(grace_period_seconds, (int, float)) or grace_period_seconds < 0:
        raise InvalidRequestError("grace_period_seconds must be a non-negative number")

    shared_root = Path(shared_mailbucket_root).resolve()
    result: dict[str, Any] = {"root": str(shared_root), "deleted": [], "skipped": []}
    if not shared_root.exists():
        return result
    if not shared_root.is_dir():
        raise InvalidRequestError("shared_mailbucket_root must be a directory")

    now_ts = (now.astimezone(timezone.utc).timestamp() if now is not None else time())
    for entry in sorted(shared_root.iterdir(), key=lambda path: path.name):
        if entry.is_symlink():
            result["skipped"].append({"path": str(entry), "reason": "symlink"})
            continue
        if not entry.is_dir():
            result["skipped"].append({"path": str(entry), "reason": "not_directory"})
            continue
        resolved = entry.resolve()
        if shared_root not in resolved.parents:
            result["skipped"].append({"path": str(entry), "reason": "outside_root"})
            continue
        age_seconds = now_ts - entry.stat().st_mtime
        if age_seconds < grace_period_seconds:
            result["skipped"].append({"path": str(resolved), "reason": "within_grace_period"})
            continue
        shutil.rmtree(resolved)
        result["deleted"].append(str(resolved))
    return result
