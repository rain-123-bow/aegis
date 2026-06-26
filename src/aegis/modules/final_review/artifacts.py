"""Artifact writer for Final Review Subgraph v2."""

from __future__ import annotations

import hashlib
import json
import os
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from aegis.modules.final_review.models import ArtifactRef, FinalReviewProjectBinding
from aegis.modules.final_review.path_io import fs_path, iter_files, mkdir, ref_path, require_under_root


class FinalReviewArtifactWriter:
    """Write Final Review artifacts under the run artifact root."""

    def __init__(self, binding: FinalReviewProjectBinding) -> None:
        self.binding = binding

    def artifact_dir(self, relative_path: str | Path) -> Path:
        return require_under_root(
            self.binding.final_review_artifact_root / relative_path,
            self.binding.final_review_artifact_root,
            label="final review artifact path",
        )

    def write_json(self, path: str | Path, payload: Any, artifact_type: str) -> ArtifactRef:
        content = json.dumps(self._to_jsonable(payload), ensure_ascii=True, indent=2, sort_keys=True)
        return self._write(self._validate_artifact_path(path), content + "\n", artifact_type)

    def write_jsonl(self, path: str | Path, rows: list[Any], artifact_type: str) -> ArtifactRef:
        content = "".join(
            json.dumps(self._to_jsonable(row), ensure_ascii=True, sort_keys=True) + "\n"
            for row in rows
        )
        return self._write(self._validate_artifact_path(path), content, artifact_type)

    def write_text(self, path: str | Path, content: str, artifact_type: str) -> ArtifactRef:
        return self._write(self._validate_artifact_path(path), content, artifact_type)

    def file_ref(self, path: str | Path, artifact_type: str, *, created_by_node: str) -> ArtifactRef:
        target = Path(path).resolve()
        require_under_root(
            target,
            self.binding.final_review_artifact_root,
            label="final review file ref",
        )
        return ArtifactRef(
            artifact_id=f"{artifact_type}-{uuid4().hex[:8]}",
            artifact_type=artifact_type,
            path=ref_path(target),
            readme_path=ref_path(_readme_for(target)),
            sha256=sha256_path(target),
            created_by_node=created_by_node,
        )

    def _validate_artifact_path(self, path: str | Path) -> Path:
        target = Path(path).resolve()
        require_under_root(
            target,
            self.binding.final_review_artifact_root,
            label="final review artifact path",
        )
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
            sha256=sha256_path(target),
            created_by_node="final_review_subgraph",
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


def sha256_path(path: str | Path) -> str:
    target = Path(path)
    if target.is_dir():
        hasher = hashlib.sha256()
        for item in iter_files(target):
            hasher.update(item.relative_to(target).as_posix().encode("utf-8"))
            hasher.update(sha256_file(item).encode("ascii"))
        return hasher.hexdigest()
    return sha256_file(target)


def sha256_file(path: str | Path) -> str:
    hasher = hashlib.sha256()
    with open(fs_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
