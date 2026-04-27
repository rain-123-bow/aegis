from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonStore:
    """Small JSON-backed store for Phase 1.

    This is intentionally simple and local. It is not a distributed database.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"domains": {}, "agents": {}, "messages": {}}
        with self.path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("domains", {})
        data.setdefault("agents", {})
        data.setdefault("messages", {})
        return data

    def save(self, data: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        tmp.replace(self.path)
