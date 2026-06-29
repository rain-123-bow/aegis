from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from aegis.models import StoreCandidate
from aegis.tools import ToolCallRequest, ToolGovernance


class ProjectStores:
    """Local project Knowledge / Causal candidate writer."""

    store_names = ("knowledge", "causal")

    def __init__(self, project_root: str | Path, governance: ToolGovernance | None = None):
        self.project_root = Path(project_root)
        self.governance = governance or ToolGovernance()

    @property
    def runtime_dir(self) -> Path:
        return self.project_root / ".aegis" / "runtime"

    @property
    def checkpoint_path(self) -> Path:
        return self.runtime_dir / "checkpoints.sqlite3"

    def ensure_layout(self) -> dict[str, str]:
        request = ToolCallRequest(
            calling_node="project_state_context_load",
            actor_role="master",
            tool_name="stores.ensure_layout",
            declared_intent="create local project state directories",
            expected_side_effects=["local_project_state"],
            project_scope=str(self.project_root),
        )

        def action() -> dict[str, str]:
            self.runtime_dir.mkdir(parents=True, exist_ok=True)
            paths = {}
            for name in self.store_names:
                path = self.project_root / name / "candidates"
                path.mkdir(parents=True, exist_ok=True)
                paths[name] = str(path)
            return paths

        result = self.governance.execute(request, action)
        if not result.executed:
            raise RuntimeError(result.decision.reason)
        return result.result

    def write_candidate(self, candidate: StoreCandidate) -> str:
        request = ToolCallRequest(
            calling_node="project_closeout",
            actor_role="master",
            tool_name="stores.write_candidate",
            arguments={"store": candidate.store, "candidate_id": candidate.candidate_id},
            declared_intent="write candidate to local project store",
            expected_side_effects=["local_project_state"],
            project_scope=str(self.project_root),
        )

        def action() -> str:
            path = self._candidate_path(candidate.store, candidate.candidate_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(candidate.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return str(path)

        result = self.governance.execute(request, action)
        if not result.executed:
            raise RuntimeError(result.decision.reason)
        return result.result

    def _candidate_path(self, store: Literal["knowledge", "causal"], candidate_id: str) -> Path:
        return self.project_root / store / "candidates" / f"{candidate_id}.json"

    def read_candidate(self, artifact_ref: str) -> dict[str, Any]:
        return json.loads(Path(artifact_ref).read_text(encoding="utf-8"))
