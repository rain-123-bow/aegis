from __future__ import annotations

import pytest

from aegis_execution_sandbox import WorkItem, WorkRoute, classify_work_item, normalize_title, priority_score


def test_normalize_title_collapses_whitespace_and_lowercases():
    assert normalize_title("  Fix   Login   Bug  ") == "fix login bug"


def test_priority_score_uses_risk_and_caps_evidence_weight():
    item = WorkItem(title="Improve parser", risk=2, evidence_refs=("log:A", "test:B", "issue:C", "trace:D"))
    assert priority_score(item) == 23


def test_blocked_item_has_zero_score_and_blocked_route():
    item = WorkItem(title="Deploy unsafe change", risk=5, evidence_refs=("ticket:1",), blocked=True)
    assert priority_score(item) == 0
    assert classify_work_item(item) == WorkRoute.BLOCKED


def test_high_risk_item_requires_test():
    item = WorkItem(title="Change auth boundary", risk=4, evidence_refs=("design:auth",))
    assert classify_work_item(item) == WorkRoute.TEST_REQUIRED


def test_medium_risk_item_requires_review():
    item = WorkItem(title="Refactor parser", risk=3, evidence_refs=("issue:parser",))
    assert classify_work_item(item) == WorkRoute.REVIEW_REQUIRED


def test_low_risk_item_without_evidence_requires_review():
    item = WorkItem(title="Rename helper", risk=1)
    assert classify_work_item(item) == WorkRoute.REVIEW_REQUIRED


def test_low_risk_item_with_evidence_is_direct():
    item = WorkItem(title="Fix typo", risk=1, evidence_refs=("issue:typo",))
    assert classify_work_item(item) == WorkRoute.DIRECT


def test_invalid_risk_is_rejected():
    with pytest.raises(ValueError, match="risk"):
        WorkItem(title="Bad", risk=9).validate()
