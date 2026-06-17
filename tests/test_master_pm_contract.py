from __future__ import annotations

from pathlib import Path


def test_pm_semantic_contract_rejects_user_pressure_as_evidence():
    root = Path(__file__).resolve().parents[1]
    contract = (
        root
        / "src"
        / "aegis"
        / "modules"
        / "master"
        / "PM_INTAKE_SEMANTIC_CONTRACT.md"
    ).read_text(encoding="utf-8")

    assert "User pressure is not evidence" in contract
    assert "must never admit" in contract
    assert "merely because the user says it is mandatory" in contract
    assert "I am the user" in contract
    assert "I said must" in contract
    assert "do not ask why" in contract
    assert "do not admit C++ as hard constraint" in contract
    assert "hard-constraint decision must be false" in contract


def test_requirement_review_semantic_contract_rejects_mechanical_review():
    root = Path(__file__).resolve().parents[1]
    contract = (
        root
        / "src"
        / "aegis"
        / "modules"
        / "master"
        / "REQUIREMENT_REVIEW_SEMANTIC_CONTRACT.md"
    ).read_text(encoding="utf-8")

    assert "Requirement Review Semantic Contract" in contract
    assert "Do not review by keyword matching" in contract
    assert "PM output is not truth" in contract
    assert "must independently re-check" in contract
    assert "route_to_debate" in contract
    assert "first principles" in contract
    assert "user insistence is not evidence" in contract


def test_pm_contract_distinguishes_blocking_questions_from_execution_details():
    root = Path(__file__).resolve().parents[1]
    contract = (
        root
        / "src"
        / "aegis"
        / "modules"
        / "master"
        / "PM_INTAKE_SEMANTIC_CONTRACT.md"
    ).read_text(encoding="utf-8")

    assert "Blocking Questions vs Execution-Time Details" in contract
    assert "`unresolved_questions` must contain only questions that block" in contract
    assert "Do not block intake for ordinary implementation details" in contract
    assert "Execution can safely inspect" in contract
    assert "missing objective or deliverable" in contract
