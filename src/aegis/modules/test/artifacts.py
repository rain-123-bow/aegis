"""Artifact writer for Test Subgraph v2."""

from __future__ import annotations

import hashlib
import json
import os
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from aegis.modules.test.models import ArtifactRef, TestProjectBinding
from aegis.modules.test.path_io import fs_path, iter_files, mkdir, path_is_dir, ref_path
from aegis.modules.test.path_policy import TestPathPolicyError, forbid_under_root, require_under_root


class TestArtifactWriter:
    """Write Test artifacts under the run artifact root."""

    def __init__(self, binding: TestProjectBinding) -> None:
        self.binding = binding

    def artifact_dir(self, relative_path: str | Path) -> Path:
        return require_under_root(
            self.binding.test_artifact_root / relative_path,
            self.binding.test_artifact_root,
            label="test artifact path",
        )

    def write_json(self, path: str | Path, payload: Any, artifact_type: str) -> ArtifactRef:
        target = self._validate_artifact_path(path)
        content = json.dumps(self._to_jsonable(payload), ensure_ascii=True, indent=2, sort_keys=True)
        return self._write(target, content + "\n", artifact_type)

    def write_jsonl(self, path: str | Path, rows: list[Any], artifact_type: str) -> ArtifactRef:
        target = self._validate_artifact_path(path)
        content = "".join(
            json.dumps(self._to_jsonable(row), ensure_ascii=True, sort_keys=True) + "\n"
            for row in rows
        )
        return self._write(target, content, artifact_type)

    def write_text(self, path: str | Path, content: str, artifact_type: str) -> ArtifactRef:
        target = self._validate_artifact_path(path)
        return self._write(target, content, artifact_type)

    def file_ref(self, path: str | Path, artifact_type: str, *, created_by_node: str) -> ArtifactRef:
        target = Path(path).resolve()
        readme = _readme_for(target)
        return ArtifactRef(
            artifact_id=f"{artifact_type}-{uuid4().hex[:8]}",
            artifact_type=artifact_type,
            path=ref_path(target),
            readme_path=ref_path(readme),
            sha256=_sha256_path(target),
            created_by_node=created_by_node,
        )

    def _validate_artifact_path(self, path: str | Path) -> Path:
        target = Path(path).resolve()
        forbid_under_root(
            target,
            self.binding.code_root,
            message="must not write Test runtime artifacts under code_root",
        )
        require_under_root(target, self.binding.test_artifact_root, label="test artifact path")
        mkdir(target.parent)
        return target

    def _write(self, target: Path, content: str, artifact_type: str) -> ArtifactRef:
        mkdir(target.parent)
        temp = target.parent / f".{uuid4().hex[:12]}.tmp"
        with open(fs_path(temp), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(fs_path(temp), fs_path(target))
        return ArtifactRef(
            artifact_id=f"{artifact_type}-{uuid4().hex[:8]}",
            artifact_type=artifact_type,
            path=ref_path(target),
            readme_path=ref_path(_readme_for(target)),
            sha256=_sha256_path(target),
            created_by_node="test_subgraph",
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


def _sha256_path(path: Path) -> str:
    if path_is_dir(path):
        hasher = hashlib.sha256()
        for item in iter_files(path):
            hasher.update(item.relative_to(path).as_posix().encode("utf-8"))
            hasher.update(_sha256_file(item).encode("ascii"))
        return hasher.hexdigest()
    return _sha256_file(path)


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(fs_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


__all__ = ["TestArtifactWriter", "TestPathPolicyError"]
