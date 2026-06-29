"""Project-local binding for Test Subgraph v2."""

from __future__ import annotations

from pathlib import Path

from aegis.modules.test.models import TestProjectBinding
from aegis.modules.test.path_io import mkdir, path_exists
from aegis.modules.test.path_policy import TestPathPolicyError


def bind_test_project(
    project_root: str | Path,
    *,
    run_id: str,
    code_root: str | Path | None = None,
    knowledge_store_root: str | Path | None = None,
    causal_store_root: str | Path | None = None,
) -> TestProjectBinding:
    """Resolve project-local code/store roots and Test artifact root."""

    root = Path(project_root).resolve()
    roots = {
        "code_root": Path(code_root).resolve() if code_root else root / "code",
        "knowledge_store_root": (
            Path(knowledge_store_root).resolve() if knowledge_store_root else root / "knowledge"
        ),
        "causal_store_root": Path(causal_store_root).resolve() if causal_store_root else root / "causal",
    }
    for name, path in roots.items():
        _require_under_root(name, path.resolve(), root)
    missing = [name for name, path in roots.items() if not path_exists(path)]
    if missing:
        raise TestPathPolicyError(
            "TestSubgraph requires project-local code/knowledge/causal roots: "
            + ", ".join(missing)
        )

    artifact_root = (root / ".aegis" / "artifacts" / "test" / run_id).resolve()
    _require_under_root("test_artifact_root", artifact_root, root)
    if artifact_root == roots["code_root"] or roots["code_root"] in artifact_root.parents:
        raise TestPathPolicyError("Test artifact root must not overlap code_root")
    mkdir(artifact_root)

    return TestProjectBinding(
        project_root=root,
        code_root=roots["code_root"],
        knowledge_store_root=str(roots["knowledge_store_root"]),
        causal_store_root=str(roots["causal_store_root"]),
        test_artifact_root=artifact_root,
    )


def _require_under_root(name: str, path: Path, root: Path) -> None:
    if path != root and root not in path.parents:
        raise TestPathPolicyError(f"{name} must resolve under {root}")
