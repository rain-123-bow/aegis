from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class WorkRoute(str, Enum):
    """Deterministic execution route for a sandbox work item."""

    DIRECT = "direct"
    REVIEW_REQUIRED = "review_required"
    TEST_REQUIRED = "test_required"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class WorkItem:
    """Input object for the sandbox classifier.

    The model is intentionally small so Aegis execution tests can reason about
    changed behavior without needing a large business domain.
    """

    title: str
    description: str = ""
    risk: int = 1
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    blocked: bool = False

    def validate(self) -> None:
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("work item title must be a non-empty string")
        if not isinstance(self.description, str):
            raise ValueError("work item description must be a string")
        if not isinstance(self.risk, int) or not 1 <= self.risk <= 5:
            raise ValueError("work item risk must be an integer from 1 to 5")
        if any(not isinstance(item, str) or not item.strip() for item in self.evidence_refs):
            raise ValueError("evidence refs must be non-empty strings")
