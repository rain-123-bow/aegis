from __future__ import annotations

import re

from .models import WorkItem, WorkRoute

_WHITESPACE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Normalize a title into a stable single-line form."""

    if not isinstance(title, str):
        raise TypeError("title must be a string")
    return _WHITESPACE.sub(" ", title.strip()).lower()


def priority_score(item: WorkItem) -> int:
    """Compute a deterministic priority score.

    The score is deliberately simple and testable:

    - base score is risk * 10;
    - evidence adds confidence weight;
    - blocked items do not receive extra execution priority.
    """

    item.validate()
    if item.blocked:
        return 0
    return item.risk * 10 + min(len(item.evidence_refs), 3)


def classify_work_item(item: WorkItem) -> WorkRoute:
    """Classify a work item into a route for execution tests."""

    item.validate()
    if item.blocked:
        return WorkRoute.BLOCKED
    if item.risk >= 4:
        return WorkRoute.TEST_REQUIRED
    if item.risk >= 3 or not item.evidence_refs:
        return WorkRoute.REVIEW_REQUIRED
    return WorkRoute.DIRECT
