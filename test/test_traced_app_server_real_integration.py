from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aegis_runtime import RuntimeCoordinator, TraceRelayClient  # noqa: E402
from project_seal_store import record_project_seal  # noqa: E402


NODE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "artifact_path",
        "reasoning_ledger_context_pack",
        "status",
    ],
    "properties": {
        "artifact_path": {"type": "string", "minLength": 1},
        "reasoning_ledger_context_pack": {"type": "string", "minLength": 1},
        "status": {"type": "boolean"},
    },
}


@unittest.skipUnless(
    os.environ.get("TRACERELAY_COMMAND"),
    "set TRACERELAY_COMMAND to run the traced App Server acceptance",
)
class TracedAppServerRealIntegrationTests(unittest.TestCase):
    def test_two_persistent_roles_share_one_verified_relay_session(self) -> None:
        tracerelay_command = str(Path(os.environ["TRACERELAY_COMMAND"]).resolve())
        initial = subprocess.run(
            [tracerelay_command, "status"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=15,
        )
        initial_raw = initial.stdout.strip() or initial.stderr.strip()
        initial_status = json.loads(initial_raw.decode("utf-8", errors="replace"))
        if initial_status.get("state") != "NOT_RUNNING":
            self.skipTest("TraceRelay is already running; ownership is ambiguous")
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        short_id = uuid4().hex[:12]
        run_id = f"p-{short_id}"
        root = (
            Path(os.environ.get("AEGIS_APP_SERVER_ACCEPTANCE_ROOT", r"C:\code\aegis_artifacts"))
            / "as_pilot"
            / short_id
        ).resolve()
        project = root / "project"
        artifact_path = root / "artifacts"
        source = project / "src" / "acceptance_target.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("ACCEPTANCE_TARGET = True\n", encoding="utf-8")
        record_project_seal(
            project,
            git_head_before_record="a" * 40,
            project_id=bytes(range(16)),
            run_id=bytes(range(16, 32)),
        )
        context_path = artifact_path / "REASONING_LEDGER_CONTEXT_PACK.json"
        artifact_path.mkdir(parents=True, exist_ok=True)
        context_path.write_text("{}\n", encoding="utf-8")
        expected = {
            "artifact_path": str(artifact_path),
            "reasoning_ledger_context_pack": str(context_path),
            "status": True,
        }
        relay = TraceRelayClient(
            command=tracerelay_command,
            monitor_interval_seconds=0.05,
        )
        coordinator = RuntimeCoordinator(
            project_root=project,
            artifact_path=artifact_path,
            run_id=run_id,
            upstream_port=int(os.environ.get("TRACERELAY_UPSTREAM_PORT", "7899")),
            relay_client=relay,
            start_node="A",
        )
        owned = False
        try:
            coordinator.preflight()
            owned = True
            coordinator.prepare_planning_agents(
                {
                    "TEST_PLAN_AUTHOR": (
                        "Acceptance author. Do not call tools. Return only schema-valid JSON."
                    ),
                    "TEST_PLAN_REVIEWER": (
                        "Independent acceptance reviewer. Do not call tools. Return only "
                        "schema-valid JSON."
                    ),
                }
            )
            expected_json = json.dumps(expected, ensure_ascii=False, separators=(",", ":"))
            author_raw = coordinator.run_planning_agent(
                "TEST_PLAN_AUTHOR",
                f"Return exactly this JSON object: {expected_json}",
                output_schema=NODE_SCHEMA,
                developer_instructions="author",
            )
            reviewer_raw = coordinator.run_planning_agent(
                "TEST_PLAN_REVIEWER",
                (
                    "Verify that the author response matches the requested object, then return "
                    f"exactly the same JSON object. AUTHOR={author_raw}"
                ),
                output_schema=NODE_SCHEMA,
                developer_instructions="reviewer",
            )
            coordinator.complete_planning_stage()
            coordinator.complete(expected)

            self.assertEqual(json.loads(author_raw), expected)
            self.assertEqual(json.loads(reviewer_raw), expected)
            state = json.loads(coordinator.run_state_path.read_text(encoding="utf-8"))
            threads = {
                value["codex_thread_id"]
                for value in state["planning_agents"].values()
            }
            turns = {item["codex_turn_id"] for item in state["planning_turns"]}
            self.assertEqual(len(threads), 2)
            self.assertEqual(len(turns), 2)
            self.assertEqual(state["status"], "completed")
            self.assertEqual(state["planning_stage_status"], "completed")
            self.assertEqual(len(state["evidence_sessions"]), 1)
            evidence = state["evidence_sessions"][0]
            self.assertEqual(evidence["node"], "planning")
            self.assertEqual(evidence["verification_status"], "VALID_COMPLETE")
            self.assertTrue(all(Path(item["raw_response_path"]).is_file() for item in state["planning_turns"]))

            report = {
                "schema": "aegis.planning_app_server_acceptance.v1",
                "verdict": "PASS",
                "created_at_utc": stamp,
                "run_id": run_id,
                "run_state_path": str(coordinator.run_state_path),
                "codex_cli_path": state["codex_cli_path"],
                "codex_cli_version": state["codex_cli_version"],
                "codex_thread_ids": sorted(threads),
                "codex_turn_ids": sorted(turns),
                "evidence_session": evidence,
                "source_sha256": {
                    str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"): hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()
                    for path in (
                        PROJECT_ROOT / "src" / "codex_app_server_client.py",
                        PROJECT_ROOT / "src" / "tracerelay_client.py",
                        PROJECT_ROOT / "src" / "aegis_runtime.py",
                        PROJECT_ROOT / "src" / "main.py",
                    )
                },
            }
            report_path = root / "ACCEPTANCE_REPORT.json"
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"ACCEPTANCE_REPORT={report_path}")
        except BaseException as error:
            try:
                coordinator.fail(error)
            except BaseException:
                pass
            raise
        finally:
            if owned:
                subprocess.run(
                    [tracerelay_command, "stop"],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    timeout=30,
                )
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    status_result = subprocess.run(
                        [tracerelay_command, "status"],
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        check=False,
                        timeout=15,
                    )
                    status_raw = status_result.stdout.strip() or status_result.stderr.strip()
                    status = json.loads(status_raw.decode("utf-8", errors="replace"))
                    if status.get("state") == "NOT_RUNNING":
                        break
                    time.sleep(0.1)


if __name__ == "__main__":
    unittest.main()
