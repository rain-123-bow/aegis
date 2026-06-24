from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from aegis.modules.debate import (
    DebateErrorCode,
    DebateInputPackage,
    DebateOutputPackage,
    DebateRuntimeConfig,
    FirstPrinciplesNecessityCheck,
)


def test_debate_input_package_requires_candidate_positions(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        DebateInputPackage(
            request_id="req-1",
            source_module="master",
            project_root=str(tmp_path),
            decision_problem="Choose implementation route",
            decision_scope="local project",
            required_outcome="choose_one",
            candidate_positions=[],
        )


def test_debate_output_package_preserves_boundary_false(tmp_path: Path) -> None:
    output = DebateOutputPackage(
        debate_id="debate-1",
        request_id="req-1",
        status="completed",
        decision_type="choose_one",
        selected_stance_ids=["s2"],
        rejected_stance_ids=["s1"],
        causal_candidate_ref=str(tmp_path / "candidate.json"),
        causal_store_candidate_id="pkg-1",
        final_report_ref=str(tmp_path / "final_report.md"),
        manifest_ref=str(tmp_path / "manifest.json"),
    )

    assert output.boundary.wrote_causal_truth is False
    assert output.boundary.wrote_knowledge_truth is False
    assert output.boundary.modified_code is False


def test_runtime_config_rejects_unbounded_rounds() -> None:
    with pytest.raises(ValidationError):
        DebateRuntimeConfig(max_rounds=0)


def test_first_principles_project_fact_requires_ref() -> None:
    with pytest.raises(ValidationError):
        FirstPrinciplesNecessityCheck(
            statement="This project must use Python 3.13",
            category="governance_invariant",
            depends_on_project_fact=True,
            accepted=True,
        )


def test_error_code_enum_contains_public_contract_codes() -> None:
    assert DebateErrorCode.PATH_POLICY_VIOLATION.value == "PATH_POLICY_VIOLATION"
    assert DebateErrorCode.INSUFFICIENT_CONTESTED_STANCES.value == "INSUFFICIENT_CONTESTED_STANCES"
