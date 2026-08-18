from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import aegis_runtime
import main
import project_seal_store
from aegis_test_support import (
    initialize_test_git_repository,
    write_test_runtime_scope_policy,
)


class FakeRelayProcessClient:
    def __init__(self, session_path: Path) -> None:
        self.session_path = session_path
        self.commands: list[list[str]] = []

    def start(self) -> dict[str, object]:
        return {"ok": True, "state": "IDLE"}

    def run_process(
        self,
        command: list[str],
        *,
        upstream_port: int,
        timeout_seconds: float,
        base_environment: object = None,
    ) -> aegis_runtime.EvidenceProcessResult:
        self.commands.append(list(command))
        output_index = command.index("--output-last-message") + 1
        Path(command[output_index]).write_text("proxied response", encoding="utf-8")
        registration = aegis_runtime.TraceRelayRegistration(
            session_id="session-main",
            proxy_host="127.0.0.1",
            proxy_port=45000,
            upstream_port=upstream_port,
            session_path=self.session_path,
        )
        verification = {
            "status": "VALID_COMPLETE",
            "final_hash": "ab" * 32,
        }
        completed = subprocess.CompletedProcess(command, 0, "", "")
        return aegis_runtime.EvidenceProcessResult(
            completed, registration, verification
        )


class PassthroughCoordinator:
    def execute_node(
        self,
        node_name: str,
        operation: Any,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        return operation(state)


class MainRuntimeIntegrationTests(unittest.TestCase):
    def test_default_runtime_root_is_project_scoped_and_outside_project_aegis(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src" / "module.py"
            source.parent.mkdir(parents=True)
            source.write_text("VALUE = 1\n", encoding="utf-8")
            write_test_runtime_scope_policy(root)
            head = initialize_test_git_repository(root)
            project_seal_store.record_project_seal(
                root,
                git_head_before_record=head,
                project_id=bytes(range(16)),
                seal_chain_id=bytes(range(16, 32)),
            )
            local_app_data = root / "local-app-data"
            with patch.dict(
                main.os.environ,
                {"LOCALAPPDATA": str(local_app_data)},
                clear=False,
            ):
                runtime_root = main.resolve_project_runtime_root(root, None)

            self.assertEqual(
                runtime_root,
                local_app_data
                / "Aegis"
                / "runtime"
                / bytes(range(16)).hex(),
            )
            self.assertFalse(runtime_root.is_relative_to(root / ".aegis"))

    def test_planning_nodes_close_before_executor_uses_its_own_app_server_turn(
        self,
    ) -> None:
        events: list[object] = []

        class FakePlanningCoordinator:
            def run_planning_agent(
                self,
                role_key: str,
                prompt: str,
                *,
                output_schema: dict[str, Any],
                developer_instructions: str,
                job_id: str | None = None,
            ) -> str:
                events.append(
                    ("planning", role_key, prompt, developer_instructions, job_id)
                )
                payload: dict[str, object] = {
                    "artifact_path": "C:/artifacts",
                    "reasoning_ledger_context_pack": "C:/artifacts/context.json",
                    "status": True,
                }
                if role_key == main.TEST_PLAN_REVIEWER_ROLE:
                    payload.update(
                        reviewed_plan_sha256="ab" * 32,
                        score=95,
                        error_count=0,
                        warning_count=1,
                        verdict="PASS",
                    )
                return json.dumps(payload)

            def prepare_planning_author(self, context_path: str) -> dict[str, object]:
                events.append(("prepare_author", context_path))
                return {
                    "schema": "aegis.planning_author_control.v1",
                    "round_id": "round-0001",
                    "job_id": "run:round-0001:author",
                    "plan_path": "C:/artifacts/round-0001/TEST_PLAN.md",
                    "skip_turn": False,
                }

            def freeze_planning_plan(self, round_id: str) -> dict[str, object]:
                events.append(("freeze", round_id))
                return {"plan_sha256": "ab" * 32}

            def prepare_planning_review(self) -> dict[str, object]:
                events.append("prepare_review")
                return {
                    "schema": "aegis.planning_review_control.v1",
                    "round_id": "round-0001",
                    "job_id": "run:round-0001:review",
                    "plan_path": "C:/artifacts/round-0001/TEST_PLAN.md",
                    "reviewed_plan_sha256": "ab" * 32,
                    "review_report_path": "C:/artifacts/round-0001/TEST_PLAN_REVIEW.md",
                }

            def record_planning_review(
                self, round_id: str, node_output: dict[str, object]
            ) -> bool:
                events.append(("record_review", round_id, node_output["score"]))
                return bool(
                    node_output["score"] >= 95
                    and node_output["error_count"] == 0
                    and node_output["verdict"] == "PASS"
                )

            def complete_planning_stage(self) -> None:
                events.append("planning_closed")

            def run_execution_agent(
                self,
                role_key: str,
                prompt: str,
                *,
                output_schema: dict[str, Any],
                developer_instructions: str,
                timeout_seconds: float,
            ) -> str:
                del output_schema, timeout_seconds
                events.append(("execution", role_key, prompt, developer_instructions))
                return json.dumps(
                    {
                        "artifact_path": "C:/artifacts",
                        "reasoning_ledger_context_pack": "C:/artifacts/context.json",
                        "status": True,
                    }
                )

        coordinator = FakePlanningCoordinator()
        state = {
            "artifact_path": "C:/artifacts",
            "reasoning_ledger_context_pack": "C:/artifacts/context.json",
            "status": True,
        }
        schema = {
            "type": "object",
            "properties": {
                "artifact_path": {"type": "string"},
                "reasoning_ledger_context_pack": {"type": "string"},
                "status": {"type": "boolean"},
            },
        }
        configs = {
            main.TEST_PLAN_AUTHOR_ROLE: {
                "role_key": main.TEST_PLAN_AUTHOR_ROLE,
                "thread_id": "old-author",
                "role_description": "author role",
            },
            main.TEST_PLAN_REVIEWER_ROLE: {
                "role_key": main.TEST_PLAN_REVIEWER_ROLE,
                "thread_id": "old-reviewer",
                "role_description": "reviewer role",
            },
            main.TEST_EXECUTOR_ROLE: {
                "role_key": main.TEST_EXECUTOR_ROLE,
                "thread_id": "old-executor",
                "role_description": "executor role",
            },
        }

        with (
            patch.object(main, "active_runtime_coordinator", return_value=coordinator),
            patch.object(main, "load_node_message_schema", return_value=schema),
            patch.object(
                main, "load_agent_config", side_effect=lambda role: configs[role]
            ),
            patch.object(
                main,
                "send_prompt_to_thread",
                side_effect=AssertionError("C used the legacy codex exec path"),
            ),
        ):
            authored = main.test_plan_author_node(state)
            reviewed = main.test_plan_reviewer_node(authored)
            executed = main.test_executor_node(reviewed)

        self.assertTrue(reviewed["status"])
        self.assertTrue(executed["status"])
        self.assertNotIn("score", reviewed)
        self.assertNotIn("reviewed_plan_sha256", reviewed)
        self.assertEqual(
            [
                event[1]
                for event in events
                if isinstance(event, tuple) and event[0] == "planning"
            ],
            [main.TEST_PLAN_AUTHOR_ROLE, main.TEST_PLAN_REVIEWER_ROLE],
        )
        self.assertLess(events.index("planning_closed"), len(events) - 1)
        self.assertEqual(events[-1][0], "execution")
        planning_events = [
            event
            for event in events
            if isinstance(event, tuple) and event[0] == "planning"
        ]
        self.assertIn("author role", planning_events[0][3])
        self.assertIn("Aegis Global Quality Law", planning_events[0][3])
        self.assertIn("Aegis Test Plan Author", planning_events[0][3])
        self.assertNotIn("Do not use Aegis-specific skills", planning_events[0][3])
        self.assertIn("planning_author_control", planning_events[0][2])
        self.assertIn("planning_review_control", planning_events[1][2])
        self.assertIn("executor role", events[-1][3])
        self.assertIn("Aegis Global Quality Law", events[-1][3])
        self.assertIn("Aegis Test Executor", events[-1][3])
        self.assertNotIn("Do not use Aegis-specific skills", events[-1][3])

    def test_c_through_f_use_app_server_turns_without_legacy_exec(self) -> None:
        execution_calls: list[tuple[str, str]] = []
        responses = {
            main.TEST_EXECUTOR_ROLE: True,
            main.TEST_RESULT_REVIEWER_ROLE: True,
            main.TEST_REPORT_WRITER_ROLE: True,
            main.FINAL_REVIEWER_ROLE: True,
        }

        class FakeCoordinator:
            def run_execution_agent(
                self,
                role_key: str,
                prompt: str,
                *,
                output_schema: dict[str, Any],
                developer_instructions: str,
                timeout_seconds: float,
            ) -> str:
                del output_schema, timeout_seconds
                execution_calls.append((role_key, developer_instructions))
                return json.dumps(
                    {
                        "artifact_path": "C:/artifacts",
                        "reasoning_ledger_context_pack": "C:/artifacts/context.json",
                        "status": responses[role_key],
                    }
                )

        state = {
            "artifact_path": "C:/artifacts",
            "reasoning_ledger_context_pack": "C:/artifacts/context.json",
            "status": True,
        }
        configs = {
            role: {"role_key": role, "role_description": f"{role} instructions"}
            for role in (
                main.TEST_EXECUTOR_ROLE,
                main.TEST_RESULT_REVIEWER_ROLE,
                main.TEST_REPORT_WRITER_ROLE,
                main.FINAL_REVIEWER_ROLE,
            )
        }

        with (
            patch.object(
                main, "active_runtime_coordinator", return_value=FakeCoordinator()
            ),
            patch.object(
                main, "load_agent_config", side_effect=lambda role: configs[role]
            ),
            patch.object(
                main,
                "load_agent_thread_map",
                side_effect=AssertionError("E/F loaded legacy thread IDs"),
            ),
            patch.object(
                main,
                "send_prompt_to_thread",
                side_effect=AssertionError("E/F used legacy codex exec"),
            ),
        ):
            executed = main.test_executor_node(state)
            reviewed = main.test_result_reviewer_node(executed)
            reported = main.test_report_writer_node(reviewed)
            finalized = main.final_reviewer_node(reported)

        self.assertTrue(finalized["status"])
        self.assertEqual(
            [role for role, _instructions in execution_calls],
            [
                main.TEST_EXECUTOR_ROLE,
                main.TEST_RESULT_REVIEWER_ROLE,
                main.TEST_REPORT_WRITER_ROLE,
                main.FINAL_REVIEWER_ROLE,
            ],
        )
        self.assertTrue(
            all("Aegis Global Quality Law" in value for _, value in execution_calls)
        )
        self.assertTrue(
            all(
                "Do not use Aegis-specific skills" not in value
                for _, value in execution_calls
            )
        )

    def test_c_through_f_reject_changes_to_the_control_envelope(self) -> None:
        state = {
            "artifact_path": "C:/artifacts",
            "reasoning_ledger_context_pack": "C:/artifacts/context.json",
            "status": True,
        }
        cases = (
            ("artifact_path", "C:/other"),
            ("reasoning_ledger_context_pack", "C:/other/context.json"),
            ("status", 1),
        )
        for node, role in (
            (main.test_executor_node, main.TEST_EXECUTOR_ROLE),
            (main.test_result_reviewer_node, main.TEST_RESULT_REVIEWER_ROLE),
            (main.test_report_writer_node, main.TEST_REPORT_WRITER_ROLE),
            (main.final_reviewer_node, main.FINAL_REVIEWER_ROLE),
        ):
            for field, value in cases:
                with self.subTest(node=node.__name__, field=field):
                    response = {**state, field: value}
                    with (
                        patch.object(
                            main,
                            "send_execution_prompt",
                            side_effect=lambda actual_role, _prompt: (
                                json.dumps(response)
                                if actual_role == role
                                else (_ for _ in ()).throw(AssertionError(actual_role))
                            ),
                        ),
                        patch.object(
                            main,
                            "load_agent_thread_map",
                            return_value={
                                main.TEST_REPORT_WRITER_ROLE: "legacy-e",
                                main.FINAL_REVIEWER_ROLE: "legacy-f",
                            },
                        ),
                        patch.object(
                            main,
                            "send_prompt_to_thread",
                            return_value=json.dumps(response),
                        ),
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError,
                            "changed coordinator-owned|non-boolean status",
                        ):
                            node(state)

    def test_compiled_graph_runs_d_fail_then_c_d_e_f_app_server_turns(self) -> None:
        execution_calls: list[str] = []
        reviewer_statuses = iter([False, True])
        state = {
            "artifact_path": "C:/artifacts",
            "reasoning_ledger_context_pack": "C:/artifacts/context.json",
            "status": True,
        }

        class FakeCoordinator:
            def run_execution_agent(
                self,
                role_key: str,
                prompt: str,
                *,
                output_schema: dict[str, Any],
                developer_instructions: str,
                timeout_seconds: float,
            ) -> str:
                del prompt, output_schema, developer_instructions, timeout_seconds
                execution_calls.append(role_key)
                status = (
                    next(reviewer_statuses)
                    if role_key == main.TEST_RESULT_REVIEWER_ROLE
                    else True
                )
                return json.dumps({**state, "status": status})

        configs = {
            role: {"role_key": role, "role_description": role}
            for role in (
                main.TEST_EXECUTOR_ROLE,
                main.TEST_RESULT_REVIEWER_ROLE,
                main.TEST_REPORT_WRITER_ROLE,
                main.FINAL_REVIEWER_ROLE,
            )
        }
        with (
            patch.object(
                main, "active_runtime_coordinator", return_value=FakeCoordinator()
            ),
            patch.object(
                main, "load_agent_config", side_effect=lambda role: configs[role]
            ),
            patch.object(
                main,
                "load_agent_thread_map",
                side_effect=AssertionError("E/F loaded legacy thread IDs"),
            ),
            patch.object(
                main,
                "send_prompt_to_thread",
                side_effect=AssertionError("E/F used legacy codex exec"),
            ),
        ):
            result = main.create_graph(
                start_node=main.TEST_RESULT_REVIEWER_NODE
            ).invoke(state)

        self.assertEqual(
            execution_calls,
            [
                main.TEST_RESULT_REVIEWER_ROLE,
                main.TEST_EXECUTOR_ROLE,
                main.TEST_RESULT_REVIEWER_ROLE,
                main.TEST_REPORT_WRITER_ROLE,
                main.FINAL_REVIEWER_ROLE,
            ],
        )
        self.assertEqual(result["current_node"], main.FINAL_REVIEWER_NODE)
        self.assertTrue(result["status"])

    def test_compiled_graph_stops_at_e_when_report_writer_fails(self) -> None:
        execution_calls: list[str] = []
        state = {
            "artifact_path": "C:/artifacts",
            "reasoning_ledger_context_pack": "C:/artifacts/context.json",
            "status": True,
        }

        class FakeCoordinator:
            def run_execution_agent(
                self,
                role_key: str,
                prompt: str,
                *,
                output_schema: dict[str, Any],
                developer_instructions: str,
                timeout_seconds: float,
            ) -> str:
                del prompt, output_schema, developer_instructions, timeout_seconds
                execution_calls.append(role_key)
                return json.dumps(
                    {
                        **state,
                        "status": role_key != main.TEST_REPORT_WRITER_ROLE,
                    }
                )

        configs = {
            role: {"role_key": role, "role_description": role}
            for role in (
                main.TEST_REPORT_WRITER_ROLE,
                main.FINAL_REVIEWER_ROLE,
            )
        }
        with (
            patch.object(
                main, "active_runtime_coordinator", return_value=FakeCoordinator()
            ),
            patch.object(
                main, "load_agent_config", side_effect=lambda role: configs[role]
            ),
        ):
            result = main.create_graph(
                start_node=main.TEST_REPORT_WRITER_NODE
            ).invoke(state)

        self.assertEqual(execution_calls, [main.TEST_REPORT_WRITER_ROLE])
        self.assertEqual(result["current_node"], main.TEST_REPORT_WRITER_NODE)
        self.assertFalse(result["status"])

    def test_review_model_status_cannot_bypass_coordinator_threshold(self) -> None:
        closed = {"value": False}

        class FakePlanningCoordinator:
            def prepare_planning_review(self) -> dict[str, object]:
                return {
                    "schema": "aegis.planning_review_control.v1",
                    "round_id": "round-0001",
                    "job_id": "run:round-0001:review",
                    "reviewed_plan_sha256": "ab" * 32,
                    "review_report_path": "C:/artifacts/review.md",
                }

            def run_planning_agent(self, *args: object, **kwargs: object) -> str:
                del args, kwargs
                return json.dumps(
                    {
                        "artifact_path": "C:/artifacts",
                        "reasoning_ledger_context_pack": "C:/artifacts/context.json",
                        "status": True,
                        "reviewed_plan_sha256": "ab" * 32,
                        "score": 94,
                        "error_count": 0,
                        "warning_count": 0,
                        "verdict": "PASS",
                    }
                )

            def record_planning_review(
                self, round_id: str, node_output: dict[str, object]
            ) -> bool:
                del round_id
                return bool(
                    node_output["score"] >= 95
                    and node_output["error_count"] == 0
                    and node_output["verdict"] == "PASS"
                )

            def complete_planning_stage(self) -> None:
                closed["value"] = True

        config = {"thread_id": "old-reviewer", "role_description": "reviewer role"}
        with (
            patch.object(
                main,
                "active_runtime_coordinator",
                return_value=FakePlanningCoordinator(),
            ),
            patch.object(main, "load_agent_config", return_value=config),
        ):
            result = main.test_plan_reviewer_node(
                {
                    "artifact_path": "C:/artifacts",
                    "reasoning_ledger_context_pack": "C:/artifacts/context.json",
                    "status": True,
                }
            )

        self.assertFalse(result["status"])
        self.assertFalse(closed["value"])

    def test_planning_completion_gate_failure_stops_before_executor(self) -> None:
        executor_calls: list[dict[str, Any]] = []

        class FakePlanningCoordinator:
            def prepare_planning_review(self) -> dict[str, object]:
                return {
                    "schema": "aegis.planning_review_control.v1",
                    "round_id": "round-0001",
                    "job_id": "run:round-0001:review",
                    "reviewed_plan_sha256": "ab" * 32,
                    "review_report_path": "C:/artifacts/review.md",
                    "skip_turn": False,
                }

            def run_planning_agent(self, *args: object, **kwargs: object) -> str:
                del args, kwargs
                return json.dumps(
                    {
                        "artifact_path": "C:/artifacts",
                        "reasoning_ledger_context_pack": "C:/artifacts/context.json",
                        "status": True,
                        "reviewed_plan_sha256": "ab" * 32,
                        "score": 95,
                        "error_count": 0,
                        "warning_count": 0,
                        "verdict": "PASS",
                    }
                )

            def record_planning_review(
                self, round_id: str, node_output: dict[str, object]
            ) -> bool:
                del round_id, node_output
                return True

            def complete_planning_stage(self) -> None:
                raise aegis_runtime.RuntimeStateError(
                    "planning stage has no approved handoff"
                )

        def executor(state: dict[str, Any]) -> dict[str, Any]:
            executor_calls.append(state)
            return state

        schema = {
            "type": "object",
            "properties": {
                "artifact_path": {"type": "string"},
                "reasoning_ledger_context_pack": {"type": "string"},
                "status": {"type": "boolean"},
            },
        }
        with (
            patch.object(
                main,
                "active_runtime_coordinator",
                return_value=FakePlanningCoordinator(),
            ),
            patch.object(main, "load_node_message_schema", return_value=schema),
            patch.object(
                main,
                "load_agent_config",
                return_value={"role_description": "reviewer role"},
            ),
            patch.object(main, "test_executor_node", side_effect=executor),
        ):
            graph = main.create_graph(start_node=main.TEST_PLAN_REVIEWER_NODE)
            with self.assertRaisesRegex(
                aegis_runtime.RuntimeStateError, "no approved handoff"
            ):
                graph.invoke(
                    {
                        "artifact_path": "C:/artifacts",
                        "reasoning_ledger_context_pack": "C:/artifacts/context.json",
                        "status": True,
                    }
                )

        self.assertEqual(executor_calls, [])

    def test_failed_plan_review_keeps_planning_app_server_open(self) -> None:
        closed = {"value": False}

        class FakePlanningCoordinator:
            def prepare_planning_review(self) -> dict[str, object]:
                return {
                    "schema": "aegis.planning_review_control.v1",
                    "round_id": "round-0001",
                    "job_id": "run:round-0001:review",
                    "reviewed_plan_sha256": "ab" * 32,
                    "review_report_path": "C:/artifacts/review.md",
                    "skip_turn": False,
                }

            def run_planning_agent(
                self, role_key: str, prompt: str, **kwargs: Any
            ) -> str:
                del role_key, prompt, kwargs
                return json.dumps(
                    {
                        "artifact_path": "C:/artifacts",
                        "reasoning_ledger_context_pack": "C:/artifacts/context.json",
                        "status": False,
                        "reviewed_plan_sha256": "ab" * 32,
                        "score": 90,
                        "error_count": 1,
                        "warning_count": 0,
                        "verdict": "FAIL",
                    }
                )

            def record_planning_review(
                self, round_id: str, node_output: dict[str, object]
            ) -> bool:
                del round_id, node_output
                return False

            def finish_planning_stage(self) -> None:
                closed["value"] = True

        config = {"thread_id": "old-reviewer", "role_description": "reviewer role"}
        with (
            patch.object(
                main,
                "active_runtime_coordinator",
                return_value=FakePlanningCoordinator(),
            ),
            patch.object(main, "load_agent_config", return_value=config),
        ):
            result = main.test_plan_reviewer_node(
                {
                    "artifact_path": "C:/artifacts",
                    "reasoning_ledger_context_pack": "C:/artifacts/context.json",
                    "status": True,
                }
            )

        self.assertFalse(result["status"])
        self.assertFalse(closed["value"])

    def test_node_codex_call_uses_the_active_runtime_coordinator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src" / "module.py"
            source.parent.mkdir(parents=True)
            source.write_text("VALUE = 1\n", encoding="utf-8")
            write_test_runtime_scope_policy(root)
            head = initialize_test_git_repository(root)
            project_seal_store.record_project_seal(
                root,
                git_head_before_record=head,
                project_id=bytes(range(16)),
                seal_chain_id=bytes(range(16, 32)),
            )
            relay = FakeRelayProcessClient(root / "session")
            coordinator = aegis_runtime.RuntimeCoordinator(
                project_root=root,
                artifact_path=root / "artifacts",
                run_id="20260805T000000.000000Z_" + "c" * 32,
                upstream_port=7899,
                relay_client=relay,
                start_node="A",
            )
            coordinator.preflight()

            with (
                patch.object(
                    main.subprocess,
                    "run",
                    side_effect=AssertionError("direct subprocess path used"),
                ),
                patch.object(
                    aegis_runtime,
                    "verify_expected_project_seal",
                    return_value=coordinator._seal,
                ),
            ):
                result = coordinator.execute_node(
                    "A",
                    lambda state: {
                        **state,
                        "response": main.send_prompt_to_thread("thread-1", "prompt"),
                    },
                    {"status": True},
                )
            coordinator._close_run_wide_freeze()

            self.assertEqual(result["response"], "proxied response")
            self.assertEqual(len(relay.commands), 1)
            response_files = list(
                coordinator.artifact_path.glob("responses/A-*.txt")
            )
            self.assertEqual(len(response_files), 1)
            self.assertEqual(
                response_files[0].read_text(encoding="utf-8"), "proxied response"
            )

    def test_sqlite_checkpoint_resumes_at_the_failed_node(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls: list[str] = []
            fail_b = {"value": True}

            def node(name: str):
                def operation(state: dict[str, Any]) -> dict[str, Any]:
                    calls.append(name)
                    if name == "B" and fail_b["value"]:
                        raise RuntimeError("B failed")
                    return {**state, "status": True, "current_node": name}

                return operation

            replacements = {
                "test_plan_author_node": node("A"),
                "test_plan_reviewer_node": node("B"),
                "test_executor_node": node("C"),
                "test_result_reviewer_node": node("D"),
                "test_report_writer_node": node("E"),
                "final_reviewer_node": node("F"),
            }
            config = {"configurable": {"thread_id": "run-checkpoint"}}

            with patch.multiple(main, **replacements):
                with aegis_runtime.open_graph_checkpointer(root) as checkpointer:
                    graph = main.create_graph(
                        checkpointer=checkpointer,
                        coordinator=PassthroughCoordinator(),
                    )
                    with self.assertRaisesRegex(RuntimeError, "B failed"):
                        graph.invoke({"status": True}, config=config, durability="sync")
                    self.assertEqual(graph.get_state(config).next, ("B",))

                    fail_b["value"] = False
                    result = graph.invoke(None, config=config, durability="sync")

            self.assertEqual(calls, ["A", "B", "B", "C", "D", "E", "F"])
            self.assertEqual(result["current_node"], "F")

    def test_main_preflights_before_checkpoint_and_invokes_synchronously(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_root = root / "runtime"
            artifact_path = runtime_root / "runs" / "run-new" / "artifacts"
            events: list[str] = []
            invocation: dict[str, Any] = {}

            class FakeCoordinator:
                planning_stage_status = "not_started"

                def preflight(self) -> None:
                    events.append("preflight")

                def prepare_planning_agents(
                    self, role_instructions: dict[str, str]
                ) -> None:
                    self.role_instructions = role_instructions
                    events.append("prepare_planning")

                def complete(self, state: dict[str, Any]) -> None:
                    events.append("complete")

                def fail(self, error: BaseException) -> None:
                    raise AssertionError(f"unexpected failure: {error}")

            class FakeGraph:
                def invoke(
                    self,
                    value: object,
                    *,
                    config: dict[str, object],
                    durability: str,
                ) -> dict[str, Any]:
                    events.append("invoke")
                    invocation.update(
                        value=value,
                        config=config,
                        durability=durability,
                    )
                    return {"status": True, "current_node": "F"}

            @contextmanager
            def checkpoint(_project_root: Path):
                events.append("checkpoint_open")
                yield object()
                events.append("checkpoint_close")

            coordinator = FakeCoordinator()
            with (
                patch.object(
                    main,
                    "initialize_state",
                    return_value={
                        "status": True,
                        "artifact_path": str(artifact_path),
                    },
                ),
                patch.object(main, "new_run_id", return_value="run-new"),
                patch.object(
                    main, "resolve_tracerelay_command", return_value="tracerelay.exe"
                ),
                patch.object(main, "TraceRelayClient", return_value=object()),
                patch.object(main, "RuntimeCoordinator", return_value=coordinator),
                patch.object(main, "open_graph_checkpointer", checkpoint),
                patch.object(main, "create_graph", return_value=FakeGraph()),
            ):
                result = main.main(
                    [
                        "--project-root",
                        str(root),
                        "--runtime-root",
                        str(runtime_root),
                        "--engineering-input-manifest",
                        str(root / "ENGINEERING_INPUT_MANIFEST.json"),
                        "--tracerelay-upstream-port",
                        "7899",
                    ]
                )

            self.assertEqual(
                events,
                [
                    "preflight",
                    "prepare_planning",
                    "checkpoint_open",
                    "invoke",
                    "checkpoint_close",
                    "complete",
                ],
            )
            self.assertEqual(invocation["durability"], "sync")
            self.assertEqual(
                invocation["config"], {"configurable": {"thread_id": "run-new"}}
            )
            self.assertEqual(result["current_node"], "F")

    def test_resume_uses_saved_start_node_and_no_new_input_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_root = root / "runtime"
            artifact_path = runtime_root / "runs" / "run-resume" / "artifacts"
            invocation: dict[str, Any] = {}
            created: dict[str, Any] = {}

            class FakeCoordinator:
                def preflight(self) -> None:
                    pass

                def complete(self, state: dict[str, Any]) -> None:
                    pass

                def fail(self, error: BaseException) -> None:
                    raise AssertionError(f"unexpected failure: {error}")

            class FakeGraph:
                def invoke(self, value: object, **kwargs: Any) -> dict[str, Any]:
                    invocation.update(value=value, **kwargs)
                    return {"status": True, "current_node": "F"}

            @contextmanager
            def checkpoint(_project_root: Path):
                yield object()

            def make_coordinator(**kwargs: Any) -> FakeCoordinator:
                created.update(kwargs)
                return FakeCoordinator()

            def make_graph(start_node: str, **kwargs: Any) -> FakeGraph:
                created["graph_start_node"] = start_node
                return FakeGraph()

            saved = {
                "schema": "aegis.run_state.v13",
                "run_id": "run-resume",
                "status": "failed",
                "project_root": str(root.resolve()),
                "runtime_root": str(runtime_root.resolve()),
                "artifact_path": str(artifact_path.resolve()),
                "start_node": "C",
                "graph_state": {"status": True, "current_node": "C"},
                "evidence_sessions": [],
                "created_at_utc": "2026-08-05T00:00:00.000000Z",
            }
            with (
                patch.object(
                    main,
                    "initialize_state",
                    return_value={
                        "status": True,
                        "artifact_path": str(artifact_path),
                    },
                ),
                patch.object(main, "load_run_state", return_value=saved),
                patch.object(
                    main, "resolve_tracerelay_command", return_value="tracerelay.exe"
                ),
                patch.object(main, "TraceRelayClient", return_value=object()),
                patch.object(main, "RuntimeCoordinator", side_effect=make_coordinator),
                patch.object(main, "open_graph_checkpointer", checkpoint),
                patch.object(main, "create_graph", side_effect=make_graph),
            ):
                main.main(
                    [
                        "--project-root",
                        str(root),
                        "--runtime-root",
                        str(runtime_root),
                        "--resume-run-id",
                        "run-resume",
                        "--tracerelay-upstream-port",
                        "7899",
                    ]
                )

            self.assertIsNone(invocation["value"])
            self.assertEqual(created["graph_start_node"], "C")
            self.assertEqual(created["prior_state"], saved)
            self.assertEqual(
                invocation["config"],
                {"configurable": {"thread_id": "run-resume"}},
            )

    def test_resume_after_completed_planning_does_not_restart_app_server(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_root = root / "runtime"
            artifact_path = (
                runtime_root
                / "runs"
                / "run-resume-after-planning"
                / "artifacts"
            )
            events: list[str] = []

            class FakeCoordinator:
                planning_stage_status = "completed"

                def preflight(self) -> None:
                    events.append("preflight")

                def prepare_planning_agents(
                    self, role_instructions: dict[str, str]
                ) -> None:
                    del role_instructions
                    raise AssertionError("completed planning stage was restarted")

                def complete(self, state: dict[str, Any]) -> None:
                    del state
                    events.append("complete")

                def fail(self, error: BaseException) -> None:
                    raise AssertionError(f"unexpected failure: {error}")

            class FakeGraph:
                def invoke(self, value: object, **kwargs: Any) -> dict[str, Any]:
                    self.value = value
                    self.kwargs = kwargs
                    events.append("invoke")
                    return {"status": True, "current_node": "F"}

            @contextmanager
            def checkpoint(_project_root: Path):
                yield object()

            saved = {
                "schema": "aegis.run_state.v13",
                "run_id": "run-resume-after-planning",
                "status": "failed",
                "project_root": str(root.resolve()),
                "runtime_root": str(runtime_root.resolve()),
                "artifact_path": str(artifact_path.resolve()),
                "start_node": "A",
                "graph_state": {"status": True, "current_node": "C"},
                "evidence_sessions": [
                    {
                        "node": "planning",
                        "verification_status": "VALID_COMPLETE",
                    }
                ],
                "planning_stage_status": "completed",
                "created_at_utc": "2026-08-05T00:00:00.000000Z",
            }
            with (
                patch.object(
                    main,
                    "initialize_state",
                    return_value={
                        "status": True,
                        "artifact_path": str(artifact_path),
                    },
                ),
                patch.object(main, "load_run_state", return_value=saved),
                patch.object(
                    main, "resolve_tracerelay_command", return_value="tracerelay.exe"
                ),
                patch.object(main, "TraceRelayClient", return_value=object()),
                patch.object(
                    main, "RuntimeCoordinator", return_value=FakeCoordinator()
                ),
                patch.object(main, "open_graph_checkpointer", checkpoint),
                patch.object(main, "create_graph", return_value=FakeGraph()),
            ):
                main.main(
                    [
                        "--project-root",
                        str(root),
                        "--runtime-root",
                        str(runtime_root),
                        "--resume-run-id",
                        "run-resume-after-planning",
                        "--tracerelay-upstream-port",
                        "7899",
                    ]
                )

            self.assertEqual(events, ["preflight", "invoke", "complete"])


if __name__ == "__main__":
    unittest.main()
