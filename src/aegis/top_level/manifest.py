"""Manifest and hash helpers for top-level handoff packages."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from aegis.top_level.models import (
    ModuleName,
    TopLevelPackageFile,
    TopLevelPackageManifest,
)


def sha256_file(path: str | Path) -> str:
    hasher = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def write_package_manifest(
    *,
    package_root: str | Path,
    run_id: str,
    producer_module: ModuleName,
    producer_module_instance_id: str,
) -> tuple[Path, str]:
    """Write package_manifest.json and return its path and sha256."""

    root = Path(package_root).resolve()
    readme = root / "README.md"
    if not readme.exists():
        raise ValueError("handoff package requires README.md")
    files: list[TopLevelPackageFile] = []
    manifest_path = root / "package_manifest.json"
    for item in sorted(path for path in root.rglob("*") if path.is_file()):
        if item == manifest_path:
            continue
        files.append(
            TopLevelPackageFile(
                rel_path=item.relative_to(root).as_posix(),
                sha256=sha256_file(item),
                size_bytes=item.stat().st_size,
                required=True,
            )
        )
    manifest = TopLevelPackageManifest(
        run_id=run_id,
        package_root=str(root),
        readme_path=str(readme.resolve()),
        producer_module=producer_module,
        producer_module_instance_id=producer_module_instance_id,
        files=files,
    )
    manifest_bytes = canonical_json_bytes(manifest.model_dump(mode="json"))
    manifest_path.write_bytes(manifest_bytes)
    return manifest_path, sha256_bytes(manifest_bytes)


def read_manifest(path: str | Path) -> TopLevelPackageManifest:
    return TopLevelPackageManifest.model_validate_json(Path(path).read_text(encoding="utf-8"))


def require_under_any_root(path: str | Path, roots: list[str | Path], *, label: str) -> Path:
    target = Path(path).resolve()
    for root in roots:
        resolved_root = Path(root).resolve()
        if target == resolved_root or target.is_relative_to(resolved_root):
            return target
    allowed = ", ".join(str(Path(root).resolve()) for root in roots)
    raise ValueError(f"{label} must stay under allowed roots: {allowed}")
