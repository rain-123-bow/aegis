"""Small target package for Aegis Execution Department tests."""

from .classifier import classify_work_item, normalize_title, priority_score
from .models import WorkItem, WorkRoute

__all__ = [
    "WorkItem",
    "WorkRoute",
    "classify_work_item",
    "normalize_title",
    "priority_score",
]
