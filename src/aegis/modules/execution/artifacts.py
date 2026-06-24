"""Artifact writer for Execution Subgraph v2."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from aegis.modules.execution.models import ArtifactRef, ProjectStoreBinding
from aegis.modules.execution.path_policy import (
    ExecutionPathPolicyError,
    forbid_under_root,
    require_under_root,
)


class ExecutionArtifactWriter:
    """Write Execution artifacts under the run artifact root."""

    def __init__(self, binding: ProjectStoreBinding) -> None:
        self.binding = binding

    def artifact_dir(self, relative_path: str | Path) -> Path:
        return require_under_root(
            self.binding.execution_artifact_root / relative_path,
            self.binding.execution_artifact_root,
            label="execution artifact path",
        )

    def write_json(self, path: str | Path, payload: Any, artifact_type: str) -> ArtifactRef:
        target = self._validate_artifact_path(path)
        content = json.dumps(self._to_jsonable(payload), ensure_ascii=True, indent=2, sort_keys=True)
        return self._write(target, content + "\n", artifact_type)

    def write_text(self, path: str | Path, content: str, artifact_type: str) -> ArtifactRef:
        target = self._validate_artifact_path(path)
        return self._write(target, content, artifact_type)

    def file_ref(self, path: str | Path, artifact_type: str, *, created_by_node: str) -> ArtifactRef:
        target = Path(path).resolve()
        readme = _readme_for(target)
        return ArtifactRef(
            artifact_id=f"{artifact_type}-{uuid4().hex[:8]}",
            artifact_type=artifact_type,
            path=str(target),
            readme_path=str(readme),
            sha256=_sha256_file(target),
            created_by_node=created_by_node,
        )

    def _validate_artifact_path(self, path: str | Path) -> Path:
        target = Path(path).resolve()
        if len(str(target)) >= 240:
            raise ExecutionPathPolicyError(
                "execution artifact path is too long for reliable Windows atomic writes"
            )
        forbid_under_root(
            target,
            self.binding.code_root,
            message="must not write runtime artifacts under code_root",
        )
        require_under_root(
            target,
            self.binding.execution_artifact_root,
            label="execution artifact path",
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def _write(self, target: Path, content: str, artifact_type: str) -> ArtifactRef:
        temp = target.parent / f".{uuid4().hex[:12]}.tmp"
        temp.write_text(content, encoding="utf-8", newline="\n")
        temp.replace(target)
        return ArtifactRef(
            artifact_id=f"{artifact_type}-{uuid4().hex[:8]}",
            artifact_type=artifact_type,
            path=str(target),
            readme_path=str(_readme_for(target)),
            sha256=_sha256_file(target),
            created_by_node="execution_subgraph",
        )

    def _to_jsonable(self, payload: Any) -> Any:
        if isinstance(payload, BaseModel):
            return payload.model_dump(mode="json")
        if isinstance(payload, list):
            return [self._to_jsonable(item) for item in payload]
        if isinstance(payload, tuple):
            return [self._to_jsonable(item) for item in payload]
        if isinstance(payload, dict):
            return {str(key): self._to_jsonable(value) for key, value in payload.items()}
        if isinstance(payload, Enum):
            return payload.value
        if isinstance(payload, Path):
            return str(payload)
        return payload


def _readme_for(path: Path) -> Path:
    if path.name.lower() == "readme.md":
        return path
    return path.parent / "README.md"


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


__all__ = ["ExecutionArtifactWriter", "ExecutionPathPolicyError"]
