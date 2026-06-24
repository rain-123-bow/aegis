"""Project-local binding for Execution Subgraph v2."""

from __future__ import annotations

from pathlib import Path

from aegis.modules.execution.errors import ExecutionErrorCode, ExecutionRuntimeError
from aegis.modules.execution.models import ProjectStoreBinding


def bind_execution_project(
    project_root: str | Path,
    *,
    run_id: str,
    code_root: str | Path | None = None,
    archive_store_root: str | Path | None = None,
    knowledge_store_root: str | Path | None = None,
    causal_store_root: str | Path | None = None,
) -> ProjectStoreBinding:
    """Resolve project-local code/store roots and Execution artifact root."""

    root = Path(project_root).resolve()
    roots = {
        "code_root": Path(code_root).resolve() if code_root else root / "code",
        "archive_store_root": (
            Path(archive_store_root).resolve() if archive_store_root else root / "archive"
        ),
        "knowledge_store_root": (
            Path(knowledge_store_root).resolve() if knowledge_store_root else root / "knowledge"
        ),
        "causal_store_root": (
            Path(causal_store_root).resolve() if causal_store_root else root / "causal"
        ),
    }
    for name, path in roots.items():
        _require_under_root(name, path.resolve(), root)

    missing = [name for name, path in roots.items() if not path.exists()]
    if missing:
        raise ExecutionRuntimeError(
            ExecutionErrorCode.PROJECT_STORE_NOT_FOUND,
            "ExecutionSubgraph requires project-local code/archive/knowledge/causal roots.",
            context={"project_root": str(root), "missing_roots": missing},
        )

    artifact_root = (root / ".aegis" / "artifacts" / "execution" / run_id).resolve()
    _require_under_root("execution_artifact_root", artifact_root, root)
    if artifact_root == roots["code_root"] or roots["code_root"] in artifact_root.parents:
        raise ExecutionRuntimeError(
            ExecutionErrorCode.PATH_POLICY_VIOLATION,
            "Execution artifact root must not overlap project code root.",
            context={"artifact_root": str(artifact_root), "code_root": str(roots["code_root"])},
        )
    artifact_root.mkdir(parents=True, exist_ok=True)

    candidate_root = (roots["causal_store_root"] / "candidates" / "execution" / run_id).resolve()
    _require_under_root("candidate_write_root", candidate_root, roots["causal_store_root"])
    candidate_root.mkdir(parents=True, exist_ok=True)

    return ProjectStoreBinding(
        project_root=root,
        code_root=roots["code_root"],
        archive_store_root=str(roots["archive_store_root"]),
        knowledge_store_root=str(roots["knowledge_store_root"]),
        causal_store_root=str(roots["causal_store_root"]),
        candidate_write_root=str(candidate_root),
        execution_artifact_root=artifact_root,
    )


def _require_under_root(name: str, path: Path, root: Path) -> None:
    if path != root and root not in path.parents:
        raise ExecutionRuntimeError(
            ExecutionErrorCode.PATH_POLICY_VIOLATION,
            f"{name} must resolve under its allowed root.",
            context={"path": str(path), "root": str(root)},
        )
