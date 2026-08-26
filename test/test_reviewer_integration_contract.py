from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import main  # noqa: E402
import aegis_runtime  # noqa: E402


def _review_payload(*, category: str) -> dict[str, object]:
    return {
        "artifact_path": "C:/artifacts",
        "reasoning_ledger_context_pack": "C:/artifacts/context.json",
        "review_conclusion": "FAIL",
        "finding_categories": [category],
        "findings": [
            {
                "finding_id": "finding-0001",
                "category": category,
                "summary": "Evidence is incomplete.",
                "reasoning": "The required execution receipt is absent.",
                "evidence_ids": ["execution-receipt-0001"],
            }
        ],
        "review_output_artifacts": [
            {
                "artifact_id": "test-result-review",
                "path": "C:/artifacts/TEST_RESULT_REVIEW.md",
                "size": 128,
                "sha256": "ab" * 32,
            }
        ],
    }


class ReviewerIntegrationContractTests(unittest.TestCase):
    def test_master_reviewer_has_the_same_fact_only_contract(self) -> None:
        skill_path = PROJECT_ROOT / "skills" / "aegis_master_reviewer" / "SKILL.md"
        self.assertTrue(skill_path.is_file())
        skill = skill_path.read_text(encoding="utf-8")
        result_contract = skill.split("```json", 1)[1].split("```", 1)[0]
        for required in (
            "review_conclusion",
            "findings",
            "review_output_artifacts",
        ):
            self.assertIn(required, skill)
        self.assertNotIn('"finding_categories"', result_contract)
        self.assertIn("derives `finding_categories`", skill)
        for forbidden in (
            "RETURN_TO",
            "recipient",
            "route",
            "next node",
            "other agent",
            "A-F",
        ):
            self.assertNotIn(forbidden, skill)

    def test_agent_input_message_excludes_graph_control_state(self) -> None:
        message = json.loads(
            main.build_node_prompt(
                {
                    "artifact_path": "C:/artifacts",
                    "reasoning_ledger_context_pack": "C:/artifacts/context.json",
                    "status": False,
                    "current_node": "D",
                    "coordinator_review_stage": "TEST_EXECUTION",
                    "review_conclusion": "FAIL",
                }
            )
        )

        self.assertEqual(
            message,
            {
                "artifact_path": "C:/artifacts",
                "reasoning_ledger_context_pack": "C:/artifacts/context.json",
            },
        )

    def test_reviewer_output_schemas_expose_facts_not_routes(self) -> None:
        schemas = (
            main.planning_review_output_schema(),
            main.execution_reviewer_output_schema(main.TEST_RESULT_REVIEWER_ROLE),
            main.execution_reviewer_output_schema(main.FINAL_REVIEWER_ROLE),
        )

        for schema in schemas:
            encoded = json.dumps(schema, sort_keys=True)
            with self.subTest(schema_id=schema.get("$id")):
                self.assertIn("review_conclusion", schema["properties"])
                self.assertNotIn("finding_categories", schema["properties"])
                self.assertNotIn("status", schema["properties"])
                self.assertNotIn("uniqueItems", encoded)
                self.assertNotIn("disposition", encoded)
                self.assertNotIn("RETURN_TO", encoded)

    def test_model_reviewer_output_derives_finding_categories(self) -> None:
        raw_output = _review_payload(category="EXECUTION_INCOMPLETE")
        raw_output.pop("finding_categories")

        completed = main.complete_reviewer_model_output(raw_output)

        self.assertEqual(completed["finding_categories"], ["EXECUTION_INCOMPLETE"])
        self.assertEqual(
            main.validate_reviewer_envelope(
                main.TEST_RESULT_REVIEWER_ROLE,
                {
                    "artifact_path": "C:/artifacts",
                    "reasoning_ledger_context_pack": "C:/artifacts/context.json",
                },
                completed,
            )["finding_categories"],
            ["EXECUTION_INCOMPLETE"],
        )

    def test_runtime_completes_model_output_before_strict_validation(self) -> None:
        raw_output = _review_payload(category="EXECUTION_INCOMPLETE")
        raw_output.pop("finding_categories")

        validated, artifacts = aegis_runtime._validated_execution_response(
            "D", raw_output
        )

        self.assertIsNotNone(validated)
        assert validated is not None
        self.assertEqual(
            validated["finding_categories"], ["EXECUTION_INCOMPLETE"]
        )
        self.assertEqual(artifacts, raw_output["review_output_artifacts"])

    def test_reviewer_control_hides_role_node_and_workflow_topology(self) -> None:
        control = main.reviewer_input_control(
            {
                "schema": "aegis.execution_control.v1",
                "node": "D",
                "role": main.TEST_RESULT_REVIEWER_ROLE,
                "workflow_run_id": "run-1",
                "attempt_id": "attempt-0002",
                "project_root": "C:/project",
                "artifact_path": "C:/artifacts",
                "engineering_input_manifest": {"path": "C:/inputs.json"},
                "planning_handoff": {"path": "C:/handoff.json"},
                "approved_test_plan": {"path": "C:/plan.md"},
                "reasoning_ledger_context_pack": {"path": "C:/context.json"},
                "test_evidence_manifests": [
                    {
                        "attempt_id": "attempt-0001",
                        "path": "C:/evidence.json",
                        "sha256": "ab" * 32,
                        "test_ids": ["test-1"],
                    }
                ],
                "prior_role_outputs": [
                    {
                        "attempt_id": "attempt-0001",
                        "node": "C",
                        "artifacts": [
                            {
                                "artifact_id": "request",
                                "path": "C:/request.json",
                                "size": 12,
                                "sha256": "cd" * 32,
                            }
                        ],
                    }
                ],
            }
        )

        encoded = json.dumps(control, sort_keys=True)
        self.assertEqual(control["schema"], "aegis.review_input_control.v1")
        self.assertEqual(
            control["reviewed_artifacts"],
            [
                {
                    "artifact_id": "request",
                    "path": "C:/request.json",
                    "size": 12,
                    "sha256": "cd" * 32,
                }
            ],
        )
        for forbidden in (
            '"node"',
            '"role"',
            "workflow_run_id",
            "attempt_id",
            "prior_role_outputs",
            main.TEST_RESULT_REVIEWER_ROLE,
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, encoded)

    def test_reviewer_instructions_do_not_name_other_roles_or_graph(self) -> None:
        role_keys = (
            main.TEST_PLAN_REVIEWER_ROLE,
            main.TEST_RESULT_REVIEWER_ROLE,
            main.FINAL_REVIEWER_ROLE,
        )
        all_role_keys = {
            main.TEST_PLAN_AUTHOR_ROLE,
            main.TEST_PLAN_REVIEWER_ROLE,
            main.TEST_EXECUTOR_ROLE,
            main.TEST_RESULT_REVIEWER_ROLE,
            main.TEST_REPORT_WRITER_ROLE,
            main.FINAL_REVIEWER_ROLE,
        }
        for role_key in role_keys:
            config = main.load_agent_config(role_key)
            instructions = main.build_reviewer_role_instructions(config)
            for other_role in all_role_keys - {role_key}:
                with self.subTest(role=role_key, forbidden=other_role):
                    self.assertNotIn(other_role, instructions)
            for forbidden in (
                "A-F",
                "another role",
                "other agent",
                "其他智能体",
                "其他 agent",
                "下游",
                "上游节点",
                "当前节点",
            ):
                with self.subTest(role=role_key, forbidden=forbidden):
                    self.assertNotIn(forbidden, instructions)

    def test_evidence_reviewer_returns_fact_and_coordinator_derives_stage(self) -> None:
        captured_prompt: list[str] = []

        def respond(role_key: str, prompt: str) -> str:
            self.assertEqual(role_key, main.TEST_RESULT_REVIEWER_ROLE)
            captured_prompt.append(prompt)
            return json.dumps(_review_payload(category="EVIDENCE_MISSING"))

        state = {
            "artifact_path": "C:/artifacts",
            "reasoning_ledger_context_pack": "C:/artifacts/context.json",
            "status": True,
        }
        with (
            patch.object(main, "active_runtime_coordinator", return_value=None),
            patch.object(main, "send_execution_prompt", side_effect=respond),
        ):
            result = main.test_result_reviewer_node(state)

        self.assertEqual(
            json.loads(captured_prompt[0]),
            {
                "artifact_path": "C:/artifacts",
                "reasoning_ledger_context_pack": "C:/artifacts/context.json",
            },
        )
        self.assertEqual(result["review_conclusion"], "FAIL")
        self.assertEqual(result["coordinator_review_stage"], "TEST_EXECUTION")
        self.assertFalse(result["status"])

    def test_evidence_reviewer_cannot_choose_a_recipient(self) -> None:
        response = _review_payload(category="EVIDENCE_MISSING")
        response["disposition"] = "RETURN_TO_C"
        with (
            patch.object(main, "active_runtime_coordinator", return_value=None),
            patch.object(
                main,
                "send_execution_prompt",
                return_value=json.dumps(response),
            ),
        ):
            with self.assertRaisesRegex(ValueError, "unsupported fields"):
                main.test_result_reviewer_node(
                    {
                        "artifact_path": "C:/artifacts",
                        "reasoning_ledger_context_pack": "C:/artifacts/context.json",
                        "status": True,
                    }
                )

    def test_private_follow_up_stage_is_persisted_as_coordinator_state(self) -> None:
        outcome = aegis_runtime._workflow_outcome(
            "terminated",
            {
                "current_node": "D",
                "coordinator_review_stage": "TEST_PLAN_AUTHORING",
            },
        )

        self.assertEqual(outcome["workflow_state"], "REQUIRES_FOLLOW_UP")
        self.assertEqual(outcome["next_required_stage"], "TEST_PLAN_AUTHORING")
        self.assertFalse(outcome["delivery_eligible"])


if __name__ == "__main__":
    unittest.main()
