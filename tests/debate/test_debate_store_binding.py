from __future__ import annotations

from pathlib import Path

import pytest

from aegis.modules.debate import DebateRuntimeConfig, bind_project_stores
from aegis.modules.debate.errors import DebateRuntimeError
from aegis.modules.debate.artifacts import DebateArtifactWriter


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "code").mkdir(parents=True)
    (root / "archive").mkdir()
    (root / "knowledge").mkdir()
    (root / "causal").mkdir()
    return root


def test_project_store_binding_default_layout(tmp_path: Path) -> None:
    root = _project(tmp_path)
    binding = bind_project_stores(root, debate_id="debate-1")

    assert binding.project_root == root.resolve()
    assert binding.code_root == (root / "code").resolve()
    assert binding.debate_candidate_root == (
        root / "causal" / "candidates" / "debate" / "debate-1"
    ).resolve()


def test_project_store_binding_non_default_layout(tmp_path: Path) -> None:
    root = tmp_path / "project"
    code = root / "src-code"
    stores = root / ".state"
    code.mkdir(parents=True)
    for name in ("archive", "knowledge", "causal"):
        (stores / name).mkdir(parents=True)

    binding = bind_project_stores(
        root,
        debate_id="debate-2",
        code_root=code,
        archive_store_root=stores / "archive",
        knowledge_store_root=stores / "knowledge",
        causal_store_root=stores / "causal",
    )

    assert binding.code_root == code.resolve()
    assert binding.causal_store_root == (stores / "causal").resolve()


def test_artifact_writer_rejects_code_root_write(tmp_path: Path) -> None:
    root = _project(tmp_path)
    binding = bind_project_stores(root, debate_id="debate-3")
    writer = DebateArtifactWriter(binding=binding, config=DebateRuntimeConfig())

    with pytest.raises(DebateRuntimeError) as failure:
        writer.write_json(root / "code" / "bad.json", {"bad": True})
    assert failure.value.code == "PATH_POLICY_VIOLATION"


def test_artifact_writer_rejects_escape_path(tmp_path: Path) -> None:
    root = _project(tmp_path)
    binding = bind_project_stores(root, debate_id="debate-4")
    writer = DebateArtifactWriter(binding=binding, config=DebateRuntimeConfig())

    with pytest.raises(DebateRuntimeError) as failure:
        writer.write_json(tmp_path / "outside.json", {"bad": True})
    assert failure.value.code == "PATH_POLICY_VIOLATION"
