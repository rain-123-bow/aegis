"""Project-local store binding for DebateSubgraph."""

from __future__ import annotations

from pathlib import Path

from aegis.modules.debate.errors import DebateErrorCode, DebateRuntimeError
from aegis.modules.debate.models import ProjectStoreBinding


def bind_project_stores(
    project_root: str | Path,
    *,
    debate_id: str,
    code_root: str | Path | None = None,
    archive_store_root: str | Path | None = None,
    knowledge_store_root: str | Path | None = None,
    causal_store_root: str | Path | None = None,
) -> ProjectStoreBinding:
    """Bind DebateSubgraph to project-local code/archive/knowledge/causal roots."""

    root = Path(project_root).resolve()
    roots = {
        "code_root": Path(code_root).resolve() if code_root else root / "code",
        "archive_store_root": (
            Path(archive_store_root).resolve()
            if archive_store_root
            else root / "archive"
        ),
        "knowledge_store_root": (
            Path(knowledge_store_root).resolve()
            if knowledge_store_root
            else root / "knowledge"
        ),
        "causal_store_root": (
            Path(causal_store_root).resolve()
            if causal_store_root
            else root / "causal"
        ),
    }
    for name, path in roots.items():
        _require_under_root(name, path.resolve(), root)

    missing = [name for name, path in roots.items() if not path.exists()]
    if missing:
        raise DebateRuntimeError(
            DebateErrorCode.PROJECT_STORE_NOT_FOUND,
            "DebateSubgraph requires project-local code/archive/knowledge/causal roots.",
            context={
                "project_root": str(root),
                "missing_roots": missing,
            },
        )

    candidate_root = (
        roots["causal_store_root"] / "candidates" / "debate" / debate_id
    ).resolve()
    _require_under_root("debate_candidate_root", candidate_root, roots["causal_store_root"].resolve())
    if candidate_root == roots["code_root"].resolve() or roots["code_root"].resolve() in candidate_root.parents:
        raise DebateRuntimeError(
            DebateErrorCode.PATH_POLICY_VIOLATION,
            "Debate candidate root must not overlap project code root.",
            context={
                "candidate_root": str(candidate_root),
                "code_root": str(roots["code_root"].resolve()),
            },
        )
    candidate_root.mkdir(parents=True, exist_ok=True)

    return ProjectStoreBinding(
        project_root=root,
        code_root=roots["code_root"],
        archive_store_root=roots["archive_store_root"],
        knowledge_store_root=roots["knowledge_store_root"],
        causal_store_root=roots["causal_store_root"],
        debate_candidate_root=candidate_root,
    )


def _require_under_root(name: str, path: Path, root: Path) -> None:
    if path != root and root not in path.parents:
        raise DebateRuntimeError(
            DebateErrorCode.PATH_POLICY_VIOLATION,
            f"{name} must resolve under project_root.",
            context={"path": str(path), "project_root": str(root)},
        )
