from __future__ import annotations

import threading
import time
import unittest
from typing import Any

from experiments.codex_app_server_collaboration.collaboration_graph import (
    AgentExecution,
    run_collaboration,
)


class _GraphExecutor:
    def __init__(self) -> None:
        self.review_barrier = threading.Barrier(2)

    def execute(
        self,
        *,
        role: str,
        prompt: str,
        output_schema: dict[str, Any],
        client_message_id: str,
    ) -> AgentExecution:
        del prompt, client_message_id
        fixed_values = {
            name: schema["enum"][0]
            for name, schema in output_schema["properties"].items()
            if isinstance(schema.get("enum"), list) and len(schema["enum"]) == 1
        }
        started_at = time.monotonic()
        if role.startswith("reviewer_"):
            self.review_barrier.wait(timeout=2)
            time.sleep(0.02)
            payload = {
                **fixed_values,
                "verdict": "PASS",
                "findings": [],
            }
        elif role == "producer":
            payload = {**fixed_values, "proposal": "synthetic proposal"}
        else:
            receipt_schema = output_schema["properties"]["reviewer_receipts"]
            payload = {
                **fixed_values,
                "reviewer_receipts": list(receipt_schema["items"]["enum"]),
                "verdict": "PASS",
                "summary": "both independent reviews were received",
            }
        completed_at = time.monotonic()
        return AgentExecution(
            role=role,
            codex_thread_id=f"thread-{role}",
            codex_turn_id=f"turn-{role}",
            status="completed",
            payload=payload,
            started_at=started_at,
            completed_at=completed_at,
            model="fake-model",
            reasoning_effort="low",
        )


class CollaborationGraphTests(unittest.TestCase):
    def test_graph_fans_out_reviewers_and_fans_in_all_receipts(self) -> None:
        result = run_collaboration(_GraphExecutor(), graph_run_id="graph-run-test")

        self.assertEqual(result["producer"]["payload"]["role"], "producer")
        self.assertEqual(len(result["reviews"]), 2)
        self.assertEqual(
            {review["payload"]["role"] for review in result["reviews"]},
            {"reviewer_boundary", "reviewer_evidence"},
        )
        self.assertEqual(result["final"]["payload"]["verdict"], "PASS")
        self.assertEqual(
            set(result["final"]["payload"]["reviewer_receipts"]),
            {
                review["payload"]["review_receipt"]
                for review in result["reviews"]
            },
        )


if __name__ == "__main__":
    unittest.main()
