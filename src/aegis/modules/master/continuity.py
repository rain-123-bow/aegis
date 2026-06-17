from __future__ import annotations

import hashlib
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from aegis.modules.master.models import ContinuityBaseline, ContinuityCheckResult


class ContinuityStore:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else self.default_db_path()

    @staticmethod
    def default_db_path() -> Path:
        import os

        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "Aegis" / "continuity" / "continuity.sqlite3"
        return Path.home() / ".aegis" / "continuity" / "continuity.sqlite3"

    def check_project(
        self,
        project_root: str | Path,
        *,
        recover_dirty: bool = False,
    ) -> ContinuityCheckResult:
        root = Path(project_root)
        remote_url = self._remote_url(root)
        if not remote_url:
            return ContinuityCheckResult(
                status="unknown_remote",
                can_proceed=False,
                project_root=str(root),
                blocked_reason="git remote origin is required for continuity recovery",
                message_to_user="Master cannot recover this project because no origin remote exists.",
            )

        current_commit = self._git(root, "rev-parse", "HEAD")
        fingerprint = self._tracked_fingerprint(root)
        project_key = self._project_key(remote_url, root)
        baseline = self._read_baseline(project_key)
        dirty_entries = self._dirty_entries(root)
        dirty = bool(dirty_entries)

        if dirty:
            if not recover_dirty:
                return ContinuityCheckResult(
                    status="dirty",
                    can_proceed=False,
                    project_root=str(root),
                    remote_url=remote_url,
                    baseline_commit=baseline.baseline_commit if baseline else None,
                    current_commit=current_commit,
                    tracked_fingerprint=fingerprint,
                    action_taken="block_for_quarantine_and_reclone",
                    blocked_reason="working tree differs from Aegis continuity baseline",
                    message_to_user=(
                        "Master detected local project changes before work. "
                        "The safe recovery action is quarantine and reclone."
                    ),
                )
            quarantine_path = self._quarantine_and_reclone(root, remote_url)
            current_commit = self._git(root, "rev-parse", "HEAD")
            fingerprint = self._tracked_fingerprint(root)
            self._write_baseline(project_key, root, remote_url, current_commit, fingerprint)
            return ContinuityCheckResult(
                status="dirty",
                can_proceed=True,
                project_root=str(root),
                remote_url=remote_url,
                baseline_commit=current_commit,
                current_commit=current_commit,
                tracked_fingerprint=fingerprint,
                action_taken="quarantine_and_reclone",
                quarantine_path=str(quarantine_path),
                message_to_user=(
                    "Master quarantined the modified project and recloned from origin. "
                    f"Quarantine path: {quarantine_path}"
                ),
            )

        if baseline is None:
            self._write_baseline(project_key, root, remote_url, current_commit, fingerprint)
            return ContinuityCheckResult(
                status="baseline_missing",
                can_proceed=True,
                project_root=str(root),
                remote_url=remote_url,
                baseline_commit=current_commit,
                current_commit=current_commit,
                tracked_fingerprint=fingerprint,
                action_taken="record_baseline",
                message_to_user="Master recorded the initial continuity baseline.",
            )

        self._write_baseline(project_key, root, remote_url, current_commit, fingerprint)
        return ContinuityCheckResult(
            status="clean",
            can_proceed=True,
            project_root=str(root),
            remote_url=remote_url,
            baseline_commit=baseline.baseline_commit,
            current_commit=current_commit,
            tracked_fingerprint=fingerprint,
            action_taken="none",
            message_to_user="Project continuity check passed.",
        )

    def _ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS continuity_baselines (
                    project_key TEXT PRIMARY KEY,
                    project_root TEXT NOT NULL,
                    remote_url TEXT NOT NULL,
                    baseline_commit TEXT NOT NULL,
                    tracked_fingerprint TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_closeout_ref TEXT
                )
                """
            )

    def _read_baseline(self, project_key: str) -> ContinuityBaseline | None:
        self._ensure_schema()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT project_key, project_root, remote_url, baseline_commit,
                       tracked_fingerprint, updated_at, last_closeout_ref
                FROM continuity_baselines
                WHERE project_key = ?
                """,
                (project_key,),
            ).fetchone()
        if row is None:
            return None
        return ContinuityBaseline(
            project_key=row[0],
            project_root=row[1],
            remote_url=row[2],
            baseline_commit=row[3],
            tracked_fingerprint=row[4],
            updated_at=row[5],
            last_closeout_ref=row[6],
        )

    def _write_baseline(
        self,
        project_key: str,
        project_root: Path,
        remote_url: str,
        baseline_commit: str,
        tracked_fingerprint: str,
    ) -> None:
        self._ensure_schema()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO continuity_baselines (
                    project_key, project_root, remote_url, baseline_commit,
                    tracked_fingerprint, updated_at, last_closeout_ref
                )
                VALUES (?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(project_key) DO UPDATE SET
                    project_root=excluded.project_root,
                    remote_url=excluded.remote_url,
                    baseline_commit=excluded.baseline_commit,
                    tracked_fingerprint=excluded.tracked_fingerprint,
                    updated_at=excluded.updated_at
                """,
                (
                    project_key,
                    str(project_root),
                    remote_url,
                    baseline_commit,
                    tracked_fingerprint,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def _quarantine_and_reclone(self, project_root: Path, remote_url: str) -> Path:
        quarantine_root = self.db_path.parent.parent / "quarantine"
        quarantine_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        quarantine_path = quarantine_root / f"{project_root.name}-{stamp}"
        suffix = 1
        while quarantine_path.exists():
            suffix += 1
            quarantine_path = quarantine_root / f"{project_root.name}-{stamp}-{suffix}"
        shutil.move(str(project_root), str(quarantine_path))
        try:
            self._git(project_root.parent, "clone", remote_url, str(project_root))
        except Exception:
            if not project_root.exists():
                shutil.move(str(quarantine_path), str(project_root))
            raise
        return quarantine_path

    def _remote_url(self, project_root: Path) -> str | None:
        try:
            return self._git(project_root, "config", "--get", "remote.origin.url")
        except RuntimeError:
            return None

    def _dirty_entries(self, project_root: Path) -> list[str]:
        raw = self._git(project_root, "status", "--porcelain", "--untracked-files=all")
        entries = []
        for line in raw.splitlines():
            path = line[3:].replace("\\", "/")
            if path.startswith(".aegis/"):
                continue
            entries.append(line)
        return entries

    @staticmethod
    def _project_key(remote_url: str, project_root: Path) -> str:
        raw = f"{remote_url}\n{project_root.resolve()}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _tracked_fingerprint(self, project_root: Path) -> str:
        names = self._git(project_root, "ls-files").splitlines()
        digest = hashlib.sha256()
        for name in sorted(names):
            path = project_root / name
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    @staticmethod
    def _git(cwd: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"git {' '.join(args)} failed: {stderr}")
        return result.stdout.strip()
