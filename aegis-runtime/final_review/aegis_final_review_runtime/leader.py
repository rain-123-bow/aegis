from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import (
    FinalReviewInputPackage,
    FinalReviewRequest,
    FinalReviewResult,
    ResourcePolicy,
    ReviewedRefs,
)


class FinalReviewLeader:
    __test__ = False
    """Deterministic demo Final Review Leader.

    This runtime proves the Final Review Department contract at demo level.
    It does not call real models, create workers, run tests, modify code, or
    merge global causal truth.
    """

    def __init__(self, private_root: str | Path | None = None):
        self.private_root = Path(private_root or ".aegis-final-review-runtime").resolve()
        self.private_root.mkdir(parents=True, exist_ok=True)

    def run(self, request_payload: dict[str, Any]) -> FinalReviewResult:
        request = FinalReviewRequest.from_dict(request_payload)
        run_root = self.private_root / f"final-review-run-{uuid4().hex}"
        run_root.mkdir(parents=True, exist_ok=False)
        self._write_json(run_root / "final_review_request.json", request.to_dict())

        # Resource policy is the pre-review gate. No substantive review happens
        # before this check succeeds.
        if request.resource_policy.status != "satisfied":
            result = self._make_result(
                request=request,
                decision="blocked_resource_policy",
                why="Required final_review_leader resource policy is not satisfied.",
                accepted_scope=[],
                blocked_scope=["final_review"],
                known_limits=[],
                missing_evidence=[],
                governance_blockers=[],
                recommended_master_action="Provide or repair root model and reasoning-budget policy.",
            )
            self._write_json(run_root / "final_review_result.json", result.to_dict())
            return result

        package = request.final_review_input_package
        missing = package.missing_required()
        object_consistent = package.refs_consistent()

        if package.governance_blockers:
            decision = "governance_blocker_to_master"
            why = "Governance or policy blocker requires Master decision."
            recommended = "Master must decide governance boundary before acceptance."
            accepted_scope: list[str] = []
            blocked_scope = package.governance_blockers
            missing_evidence = list(package.missing_evidence)
            known_limits = list(package.known_limits)
            governance_blockers = list(package.governance_blockers)
        elif not object_consistent or package.execution_defects:
            decision = "reject_to_execution_via_master"
            why = "Execution-owned candidate or object consistency issue blocks final acceptance."
            recommended = "Master should route to Execution for correction or mapping evidence."
            accepted_scope = []
            blocked_scope = package.execution_defects or ["object_consistency"]
            missing_evidence = list(package.missing_evidence)
            if not object_consistent and "final-to-tested object mapping" not in missing_evidence:
                missing_evidence.append("final-to-tested object mapping")
            known_limits = list(package.known_limits)
            governance_blockers = []
        elif package.test_evidence_deficiencies:
            decision = "request_test_expansion_via_master"
            why = "Test evidence or coverage is insufficient for final acceptance."
            recommended = "Master should route to Test for expanded validation or stronger evidence."
            accepted_scope = []
            blocked_scope = package.test_evidence_deficiencies
            missing_evidence = list(package.missing_evidence or package.test_evidence_deficiencies)
            known_limits = list(package.known_limits)
            governance_blockers = []
        elif missing or package.evidence_contradictions or package.missing_evidence:
            decision = "request_more_evidence_via_master"
            why = "Required evidence is missing, stale, contradictory, or not reproducible enough."
            recommended = "Master should request missing or corrected evidence from the proper owner."
            accepted_scope = []
            blocked_scope = package.evidence_contradictions
            missing_evidence = sorted(set(missing + package.missing_evidence + package.evidence_contradictions))
            known_limits = list(package.known_limits)
            governance_blockers = []
        elif package.known_limits or package.blocked_scope:
            decision = "accept_for_master_with_scope_limit"
            why = "Package is reviewable for Master only under explicit scope limits."
            recommended = "Master should decide whether scoped acceptance is acceptable."
            accepted_scope = package.accepted_scope or package.task_scope
            blocked_scope = list(package.blocked_scope)
            known_limits = list(package.known_limits)
            missing_evidence = []
            governance_blockers = []
        else:
            decision = "accept_for_master"
            why = "Final code, implementation candidate, tested candidate, Execution evidence, and Test evidence are consistent for the declared scope."
            recommended = "Master should review the recommendation and decide the next governance action."
            accepted_scope = package.accepted_scope or package.task_scope
            blocked_scope = []
            known_limits = []
            missing_evidence = []
            governance_blockers = []

        result = self._make_result(
            request=request,
            decision=decision,
            why=why,
            accepted_scope=accepted_scope,
            blocked_scope=blocked_scope,
            known_limits=known_limits,
            missing_evidence=missing_evidence,
            governance_blockers=governance_blockers,
            recommended_master_action=recommended,
        )
        self._write_json(run_root / "final_review_result.json", result.to_dict())
        return result

    def _make_result(
        self,
        *,
        request: FinalReviewRequest,
        decision: str,
        why: str,
        accepted_scope: list[str],
        blocked_scope: list[str],
        known_limits: list[str],
        missing_evidence: list[str],
        governance_blockers: list[str],
        recommended_master_action: str,
    ) -> FinalReviewResult:
        package = request.final_review_input_package
        return FinalReviewResult(
            final_review_result_id=f"final-review-result-{uuid4().hex}",
            request_id=request.request_id,
            decision=decision,  # type: ignore[arg-type]
            target="master",
            why=why,
            final_code_ref=package.final_code_ref,
            implementation_candidate_ref=package.implementation_candidate_ref,
            tested_candidate_ref=package.tested_candidate_ref,
            reviewed_refs=package.reviewed_refs,
            accepted_scope=accepted_scope,
            blocked_scope=blocked_scope,
            known_limits=known_limits,
            missing_evidence=missing_evidence,
            governance_blockers=governance_blockers,
            resource_policy=request.resource_policy,
            causal_boundary="Final Review output is a recommendation to Master; it is not global causal truth.",
            recommended_master_action=recommended_master_action,
        )

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
