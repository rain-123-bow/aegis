"""Project-local runtime lock for one Aegis process per project root."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from uuid import uuid4

from aegis.models import utc_now


class RuntimeLockError(RuntimeError):
    """Raised when a project runtime lock cannot be acquired."""


def canonical_project_root(path: str | Path) -> str:
    """Return a stable platform-normalized project-root identity."""

    return os.path.normcase(str(Path(path).resolve()))


class RuntimeProjectLock:
    """Atomic project-local runtime lock.

    The lock is intentionally conservative. Existing lock files are not stolen
    because stale-lock recovery is a separate user-approved operation.
    """

    def __init__(self, project_root: str | Path, *, aegis_instance_id: str | None = None) -> None:
        self.project_root = Path(project_root).resolve()
        self.aegis_instance_id = aegis_instance_id or f"aegis-{uuid4().hex[:12]}"
        self.runtime_root = self.project_root / ".aegis" / "runtime"
        self.lock_path = self.runtime_root / "aegis_runtime.lock"
        self.instance_path = self.runtime_root / "runtime_instance.json"
        self._acquired = False

    def acquire(self) -> None:
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "top_level.runtime_instance.v1",
            "aegis_instance_id": self.aegis_instance_id,
            "project_root_resolved": canonical_project_root(self.project_root),
            "process_id": os.getpid(),
            "lock_owner_host": socket.gethostname(),
            "created_at_utc": utc_now(),
            "runtime_status": "initializing",
        }
        try:
            fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeLockError(
                f"project root already locked by an Aegis runtime: {self.lock_path}"
            ) from exc
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=True, sort_keys=True)
                handle.write("\n")
            self.instance_path.write_text(
                json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        except Exception:
            try:
                self.lock_path.unlink()
            finally:
                raise
        self._acquired = True

    def mark_ready(self) -> None:
        if not self._acquired:
            raise RuntimeLockError("runtime lock must be acquired before mark_ready")
        payload = json.loads(self.instance_path.read_text(encoding="utf-8"))
        payload["runtime_status"] = "ready"
        self.instance_path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def release(self) -> None:
        if not self._acquired:
            return
        if self.lock_path.exists():
            self.lock_path.unlink()
        self._acquired = False

    def __enter__(self) -> "RuntimeProjectLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
