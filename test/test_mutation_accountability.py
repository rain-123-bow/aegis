from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mutation_accountability import record_frozen_input_mutation_reason


class MutationAccountabilityTests(unittest.TestCase):
    def test_records_user_reason_without_changing_terminal_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = root / "runtime"
            run_root = runtime / "runs" / "run-mutated"
            artifacts = run_root / "artifacts"
            artifacts.mkdir(parents=True)
            state = {
                "schema": "aegis.run_state.v10",
                "run_id": "run-mutated",
                "status": "terminated",
                "artifact_path": str(artifacts.resolve()),
                "termination_reason_code": "FROZEN_INPUT_MUTATION",
                "master_review_status": "REQUIRES_USER_REASON",
                "delivery_eligible": False,
            }
            state_path = run_root / "RUN_STATE.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            reason = root / "reason.md"
            reason.write_text("The user changed requirement R1 during node C.\n", encoding="utf-8")

            record_frozen_input_mutation_reason(
                runtime,
                "run-mutated",
                reason_path=reason,
                user_confirmation_id="user-confirmation-17",
            )

            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["master_review_status"], "USER_REASON_RECORDED")
            self.assertFalse(saved["delivery_eligible"])
            self.assertTrue(Path(saved["mutation_reason_record"]["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
