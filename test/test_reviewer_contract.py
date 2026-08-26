from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from reviewer_contract import (  # noqa: E402
    FINAL_REVIEWER,
    MASTER_REVIEWER,
    TEST_PLAN_REVIEWER,
    TEST_RESULT_REVIEWER,
    ReviewContractError,
    coordinator_review_stage,
    reviewer_output_schema,
    validate_reviewer_output,
)


def _finding(category: str) -> dict[str, object]:
    return {
        "finding_id": f"finding-{category.lower()}",
        "category": category,
        "summary": "The reviewed material violates its evidence contract.",
        "reasoning": "The indexed evidence does not close the stated conclusion.",
        "evidence_ids": ["evidence-0001"],
    }


def _payload(
    *,
    conclusion: str,
    categories: list[str],
) -> dict[str, object]:
    return {
        "artifact_path": "C:/artifacts",
        "reasoning_ledger_context_pack": "C:/artifacts/context.json",
        "review_conclusion": conclusion,
        "finding_categories": categories,
        "findings": [_finding(category) for category in categories],
        "review_output_artifacts": [
            {
                "artifact_id": "review-report",
                "path": "C:/artifacts/reviewer-output/review.md",
                "size": 128,
                "sha256": "ab" * 32,
            }
        ],
    }


class ReviewerContractTests(unittest.TestCase):
    def test_reviewer_schema_contains_no_routing_or_node_status_semantics(self) -> None:
        schema = reviewer_output_schema(TEST_RESULT_REVIEWER)
        properties = schema["properties"]

        self.assertEqual(
            set(properties),
            {
                "artifact_path",
                "reasoning_ledger_context_pack",
                "review_conclusion",
                "finding_categories",
                "findings",
                "review_output_artifacts",
            },
        )
        encoded = json.dumps(schema, sort_keys=True)
        for forbidden in (
            "RETURN_TO",
            "CONTINUE",
            "TERMINATE",
            "disposition",
            "graph_node",
            "TEST_PLAN_AUTHOR",
            "TEST_EXECUTOR",
            '"status"',
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, encoded)

    def test_reviewer_schema_declares_collection_uniqueness(self) -> None:
        schema = reviewer_output_schema(TEST_RESULT_REVIEWER)
        properties = schema["properties"]

        self.assertIs(properties["finding_categories"]["uniqueItems"], True)
        self.assertIs(
            properties["findings"]["items"]["properties"]["evidence_ids"][
                "uniqueItems"
            ],
            True,
        )

    def test_reviewer_cannot_return_a_routing_instruction(self) -> None:
        payload = _payload(conclusion="FAIL", categories=["TEST_PLAN_DEFECT"])
        payload["disposition"] = "RETURN_TO_A"

        with self.assertRaisesRegex(ReviewContractError, "unsupported fields"):
            validate_reviewer_output(TEST_RESULT_REVIEWER, payload)

    def test_reviewer_cannot_embed_a_routing_instruction_in_a_finding(self) -> None:
        payload = _payload(conclusion="FAIL", categories=["TEST_PLAN_DEFECT"])
        payload["findings"][0]["reasoning"] = "RETURN_TO_A after this review."

        with self.assertRaisesRegex(ReviewContractError, "workflow semantics"):
            validate_reviewer_output(TEST_RESULT_REVIEWER, payload)

    def test_complete_review_can_reject_the_material(self) -> None:
        payload = _payload(
            conclusion="FAIL",
            categories=["EXECUTION_INCOMPLETE", "EVIDENCE_MISSING"],
        )

        validated = validate_reviewer_output(TEST_RESULT_REVIEWER, payload)

        self.assertEqual(validated["review_conclusion"], "FAIL")
        self.assertEqual(
            validated["finding_categories"],
            ["EVIDENCE_MISSING", "EXECUTION_INCOMPLETE"],
        )

    def test_pass_cannot_hide_findings(self) -> None:
        payload = _payload(conclusion="PASS", categories=[])
        payload["findings"] = [_finding("EVIDENCE_MISSING")]

        with self.assertRaisesRegex(ReviewContractError, "PASS.*findings"):
            validate_reviewer_output(TEST_RESULT_REVIEWER, payload)

    def test_fail_requires_each_category_to_have_a_finding(self) -> None:
        payload = _payload(
            conclusion="FAIL",
            categories=["TEST_PLAN_DEFECT", "EVIDENCE_MISSING"],
        )
        payload["findings"] = [_finding("TEST_PLAN_DEFECT")]

        with self.assertRaisesRegex(ReviewContractError, "finding categories"):
            validate_reviewer_output(TEST_RESULT_REVIEWER, payload)

    def test_coordinator_privately_prioritizes_plan_repair(self) -> None:
        payload = validate_reviewer_output(
            TEST_RESULT_REVIEWER,
            _payload(
                conclusion="FAIL",
                categories=["EXECUTION_INCOMPLETE", "TEST_PLAN_DEFECT"],
            ),
        )

        self.assertEqual(
            coordinator_review_stage(TEST_RESULT_REVIEWER, payload),
            "TEST_PLAN_AUTHORING",
        )

    def test_coordinator_privately_maps_engineering_defect_to_master(self) -> None:
        for role in (TEST_PLAN_REVIEWER, TEST_RESULT_REVIEWER):
            with self.subTest(role=role):
                payload = validate_reviewer_output(
                    role,
                    _payload(
                        conclusion="FAIL",
                        categories=["IMPLEMENTATION_PLAN_DEFECT"],
                    ),
                )
                self.assertEqual(
                    coordinator_review_stage(role, payload),
                    "MASTER_PROCESSING",
                )

    def test_coordinator_privately_maps_evidence_defect_to_execution(self) -> None:
        payload = validate_reviewer_output(
            TEST_RESULT_REVIEWER,
            _payload(conclusion="FAIL", categories=["EVIDENCE_MISSING"]),
        )

        self.assertEqual(
            coordinator_review_stage(TEST_RESULT_REVIEWER, payload),
            "TEST_EXECUTION",
        )

    def test_final_and_master_reviewers_share_semantic_not_routing_contract(self) -> None:
        final_payload = validate_reviewer_output(
            FINAL_REVIEWER,
            _payload(conclusion="FAIL", categories=["GOVERNANCE_DEFECT"]),
        )
        master_payload = validate_reviewer_output(
            MASTER_REVIEWER,
            _payload(conclusion="PASS", categories=[]),
        )

        self.assertEqual(
            coordinator_review_stage(FINAL_REVIEWER, final_payload), "END"
        )
        self.assertEqual(
            coordinator_review_stage(MASTER_REVIEWER, master_payload), "END"
        )


if __name__ == "__main__":
    unittest.main()
