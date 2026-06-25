"""Path policy for Test Subgraph v2."""

from __future__ import annotations

from pathlib import Path


class TestPathPolicyError(ValueError):
    """Raised when Test Subgraph path policy is violated."""


def require_under_root(path: str | Path, root: str | Path, *, label: str) -> Path:
    target = Path(path).resolve()
    allowed_root = Path(root).resolve()
    if target != allowed_root and allowed_root not in target.parents:
        raise TestPathPolicyError(f"{label} must resolve under {allowed_root}")
    return target


def forbid_under_root(path: str | Path, root: str | Path, *, message: str) -> Path:
    target = Path(path).resolve()
    forbidden_root = Path(root).resolve()
    if target == forbidden_root or forbidden_root in target.parents:
        raise TestPathPolicyError(message)
    return target
