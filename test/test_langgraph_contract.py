from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_REGISTRY_PATH = REPO_ROOT / "config" / "agent_registry.json"
AGENT_MANIFEST_PATH = REPO_ROOT / ".aegis" / "master" / "subagents" / "MASTER_SUBAGENTS_MANIFEST.json"
sys.path.insert(0, str(REPO_ROOT / "src"))

from langgraph_contract import (  # noqa: E402
    AUTHOR_PATCH_CLAIM,
    NODE_A,
    NODE_B,
    ROUTE_END,
    TEST_PLAN_BLOCKER_CLOSURE,
    TEST_PLAN_REVIEW_BLOCKERS,
    TEST_PLAN_REVIEW_RESULT,
    ContractViolation,
    before_author_hashes,
    gate_author,
    gate_reviewer,
    strict_json_object,
    validate_agent_output,
)


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class LangGraphContractTests(unittest.TestCase):
    def test_agent_configs_have_no_prebound_threads(self) -> None:
        registry = json.loads(AGENT_REGISTRY_PATH.read_text(encoding="utf-8"))
        manifest = json.loads(AGENT_MANIFEST_PATH.read_text(encoding="utf-8"))
        graph_agents = [agent for agent in manifest["subagents"] if agent["graph_node"] is not None]

        self.assertTrue(registry["agents"])
        self.assertTrue(all(agent["thread_id"] is None for agent in registry["agents"]))
        self.assertEqual(len(graph_agents), len(registry["agents"]))
        self.assertTrue(all(agent["thread_id"] is None for agent in graph_agents))
        self.assertTrue(all(agent["status"] == "pending_creation" for agent in graph_agents))

    def test_strict_json_rejects_extra_text(self) -> None:
        self.assertEqual(strict_json_object('{"status": true}', source="x"), {"status": True})
        with self.assertRaises(ContractViolation):
            strict_json_object('{"status": true}\nexplain', source="x")

    def test_agent_cannot_write_protected_gate_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state = {"artifact_path": temp_dir, "status": True}
            with self.assertRaises(ContractViolation):
                validate_agent_output(
                    state,
                    {"artifact_path": temp_dir, "status": True, "open_blockers": []},
                    node_name=NODE_A,
                )

    def test_author_missing_required_diff_does_not_reach_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "TEST_PLAN.md").write_text("old\n", encoding="utf-8")
            state = {
                "artifact_path": temp_dir,
                "status": True,
                "open_blockers": [
                    {
                        "blocker_id": "REQ-FUNC-025-P0",
                        "stable_id": "REQ-FUNC-025-P0",
                        "severity": "P0",
                        "finding": "missing dedicated P0 test",
                        "required_files": ["TEST_PLAN.md"],
                        "status": "open",
                    }
                ],
                "max_test_plan_review_failures": 5,
            }
            before = before_author_hashes(state)
            write_json(
                root / AUTHOR_PATCH_CLAIM,
                {
                    "resolution_type": "patch",
                    "blocker_claims": [
                        {
                            "blocker_id": "REQ-FUNC-025-P0",
                            "modified_files": ["TEST_PLAN.md"],
                            "new_or_modified_test_ids": ["TP-NEW"],
                            "evidence_contract": ["eventfd/poll wakeup"],
                        }
                    ],
                },
            )
            result = gate_author(state, {"artifact_path": temp_dir, "status": True}, before_hashes=before)
            self.assertEqual(result["gate_route"], NODE_A)
            self.assertFalse(result["gate_status"])
            self.assertIn("required_files missing substantive diff", result["gate_violations"][0])

    def test_reviewer_blocker_routes_to_author_and_forces_effective_score_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            blocker = {
                "blocker_id": "REQ-FUNC-025-P0",
                "severity": "P0",
                "finding": "missing dedicated P0 test",
                "required_files": ["TEST_PLAN.md"],
            }
            write_json(root / TEST_PLAN_REVIEW_RESULT, {"status": False, "score": 40, "open_blockers": [blocker]})
            write_json(root / TEST_PLAN_REVIEW_BLOCKERS, {"open_blockers": [blocker]})
            result = gate_reviewer({"artifact_path": temp_dir, "status": True}, {"artifact_path": temp_dir, "status": False}, node_name=NODE_B)
            self.assertEqual(result["gate_route"], NODE_A)
            self.assertFalse(result["gate_status"])
            self.assertEqual(result["effective_score"], 0)
            self.assertEqual(result["test_plan_author_review_failures"], 1)

    def test_reviewer_pass_requires_closure_for_previous_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            previous = {
                "blocker_id": "REQ-FUNC-025-P0",
                "stable_id": "REQ-FUNC-025-P0",
                "severity": "P0",
                "finding": "missing dedicated P0 test",
                "required_files": ["TEST_PLAN.md"],
                "status": "open",
            }
            write_json(root / TEST_PLAN_REVIEW_RESULT, {"status": True, "score": 95, "open_blockers": []})
            write_json(root / TEST_PLAN_REVIEW_BLOCKERS, {"open_blockers": []})
            result = gate_reviewer(
                {"artifact_path": temp_dir, "status": True, "open_blockers": [previous]},
                {"artifact_path": temp_dir, "status": True},
                node_name=NODE_B,
            )
            self.assertEqual(result["gate_route"], ROUTE_END)
            self.assertFalse(result["gate_status"])

            write_json(root / TEST_PLAN_BLOCKER_CLOSURE, {"closed_blocker_ids": ["REQ-FUNC-025-P0"]})
            result = gate_reviewer(
                {"artifact_path": temp_dir, "status": True, "open_blockers": [previous]},
                {"artifact_path": temp_dir, "status": True},
                node_name=NODE_B,
            )
            self.assertEqual(result["gate_route"], "C")
            self.assertTrue(result["gate_status"])

    def test_reviewer_score_below_95_cannot_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_json(root / TEST_PLAN_REVIEW_RESULT, {"status": True, "score": 94, "open_blockers": []})
            write_json(root / TEST_PLAN_REVIEW_BLOCKERS, {"open_blockers": []})

            result = gate_reviewer(
                {"artifact_path": temp_dir, "status": True},
                {"artifact_path": temp_dir, "status": True},
                node_name=NODE_B,
            )

            self.assertEqual(result["gate_route"], ROUTE_END)
            self.assertFalse(result["gate_status"])
            self.assertIn("score 94 below threshold 95", result["stop_reason"])


if __name__ == "__main__":
    unittest.main()
