"""Artifact writing for DebateSubgraph."""

from __future__ import annotations

import json
import time
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from aegis.modules.debate.errors import DebateErrorCode, DebateRuntimeError
from aegis.modules.debate.models import DebateRuntimeConfig, ProjectStoreBinding


_ARTIFACT_LOCK_GUARD = Lock()
_ARTIFACT_WRITE_LOCKS: dict[str, Lock] = {}


class DebateArtifactWriter:
    """Write Debate artifacts without touching project code."""

    def __init__(
        self,
        binding: ProjectStoreBinding,
        config: DebateRuntimeConfig | None = None,
    ) -> None:
        self.binding = binding
        self.config = config or DebateRuntimeConfig()

    def artifact_path(self, relative_path: str | Path) -> Path:
        """Return a path below the Debate candidate artifact root."""

        return (self.binding.debate_candidate_root / relative_path).resolve()

    def write_json(self, path: str | Path, payload: Any) -> Path:
        """Write JSON after enforcing path policy and artifact size limits."""

        target = self._validate_write_path(path)
        serializable = self._to_jsonable(payload)
        encoded = json.dumps(
            serializable,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        self._ensure_size(encoded.encode("utf-8"), target)
        self._atomic_write(target, encoded)
        return target

    def write_text(self, path: str | Path, content: str) -> Path:
        """Write text after enforcing path policy and artifact size limits."""

        target = self._validate_write_path(path)
        self._ensure_size(content.encode("utf-8"), target)
        self._atomic_write(target, content)
        return target

    def _validate_write_path(self, path: str | Path) -> Path:
        target = Path(path).resolve()
        candidate_root = self.binding.debate_candidate_root.resolve()
        code_root = self.binding.code_root.resolve()
        if target == code_root or code_root in target.parents:
            raise DebateRuntimeError(
                DebateErrorCode.PATH_POLICY_VIOLATION,
                "DebateSubgraph must not write to project code root.",
                context={"path": str(target), "code_root": str(code_root)},
            )
        if target != candidate_root and candidate_root not in target.parents:
            raise DebateRuntimeError(
                DebateErrorCode.PATH_POLICY_VIOLATION,
                "DebateSubgraph may only write under its causal candidate root.",
                context={
                    "path": str(target),
                    "candidate_root": str(candidate_root),
                },
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def _ensure_size(self, content: bytes, target: Path) -> None:
        if len(content) > self.config.max_artifact_bytes:
            raise DebateRuntimeError(
                DebateErrorCode.PATH_POLICY_VIOLATION,
                "Debate artifact exceeds configured max_artifact_bytes.",
                context={
                    "path": str(target),
                    "size": len(content),
                    "max_artifact_bytes": self.config.max_artifact_bytes,
                },
            )

    def _atomic_write(self, target: Path, content: str) -> None:
        lock = _target_lock(target)
        with lock:
            temp = target.parent / f".{uuid4().hex[:12]}.tmp"
            temp.write_text(content, encoding="utf-8", newline="\n")
            last_error: OSError | None = None
            for attempt in range(12):
                try:
                    temp.replace(target)
                    return
                except PermissionError as exc:
                    last_error = exc
                    time.sleep(0.025 * (attempt + 1))
            try:
                temp.unlink(missing_ok=True)
            finally:
                raise DebateRuntimeError(
                    DebateErrorCode.PATH_POLICY_VIOLATION,
                    "Debate artifact atomic replace failed after retry.",
                    context={
                        "path": str(target),
                        "error": str(last_error) if last_error else "unknown",
                    },
                ) from last_error

    def _to_jsonable(self, payload: Any) -> Any:
        if isinstance(payload, BaseModel):
            return payload.model_dump(mode="json")
        if isinstance(payload, list):
            return [self._to_jsonable(item) for item in payload]
        if isinstance(payload, tuple):
            return [self._to_jsonable(item) for item in payload]
        if isinstance(payload, dict):
            return {
                str(key): self._to_jsonable(value)
                for key, value in payload.items()
            }
        if isinstance(payload, Enum):
            return payload.value
        if isinstance(payload, Path):
            return str(payload)
        return payload


def _target_lock(target: Path) -> Lock:
    key = str(target.resolve()).casefold()
    with _ARTIFACT_LOCK_GUARD:
        lock = _ARTIFACT_WRITE_LOCKS.get(key)
        if lock is None:
            lock = Lock()
            _ARTIFACT_WRITE_LOCKS[key] = lock
        return lock
