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
    def test_planning_nodes_use_app_server_roles_and_close_before_executor(self) -> None:
        events: list[object] = []

        class FakePlanningCoordinator:
            def run_planning_agent(
                self,
                role_key: str,
                prompt: str,
                *,
                output_schema: dict[str, Any],
                developer_instructions: str,
            ) -> str:
                events.append(("planning", role_key, prompt, developer_instructions))
                return json.dumps(
                    {
                        "artifact_path": "C:/artifacts",
                        "reasoning_ledger_context_pack": "C:/artifacts/context.json",
                        "status": True,
                    }
                )

            def complete_planning_stage(self) -> None:
                events.append("planning_closed")

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
                "thread_id": "old-author",
                "role_description": "author role",
            },
            main.TEST_PLAN_REVIEWER_ROLE: {
                "thread_id": "old-reviewer",
                "role_description": "reviewer role",
            },
        }

        with (
            patch.object(main, "active_runtime_coordinator", return_value=coordinator),
            patch.object(main, "load_node_message_schema", return_value=schema),
            patch.object(main, "load_agent_config", side_effect=lambda role: configs[role]),
            patch.object(
                main,
                "send_prompt_to_thread",
                side_effect=AssertionError("legacy planning thread was used"),
            ),
        ):
            authored = main.test_plan_author_node(state)
            reviewed = main.test_plan_reviewer_node(authored)

        self.assertTrue(reviewed["status"])
        self.assertEqual(
            [event[1] for event in events if isinstance(event, tuple)],
            [main.TEST_PLAN_AUTHOR_ROLE, main.TEST_PLAN_REVIEWER_ROLE],
        )
        self.assertEqual(events[-1], "planning_closed")
        self.assertIn("author role", events[0][3])
        self.assertIn("Do not use Aegis-specific skills", events[0][3])

    def test_failed_plan_review_keeps_planning_app_server_open(self) -> None:
        closed = {"value": False}

        class FakePlanningCoordinator:
            def run_planning_agent(self, role_key: str, prompt: str, **kwargs: Any) -> str:
                del role_key, prompt, kwargs
                return json.dumps(
                    {
                        "artifact_path": "C:/artifacts",
                        "reasoning_ledger_context_pack": "C:/artifacts/context.json",
                        "status": False,
                    }
                )

            def finish_planning_stage(self) -> None:
                closed["value"] = True

        config = {"thread_id": "old-reviewer", "role_description": "reviewer role"}
        with (
            patch.object(
                main, "active_runtime_coordinator", return_value=FakePlanningCoordinator()
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
            project_seal_store.record_project_seal(
                root,
                git_head_before_record="a" * 40,
                project_id=bytes(range(16)),
                run_id=bytes(range(16, 32)),
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

            with patch.object(
                main.subprocess,
                "run",
                side_effect=AssertionError("direct subprocess path used"),
            ):
                result = coordinator.execute_node(
                    "A",
                    lambda state: {
                        **state,
                        "response": main.send_prompt_to_thread(
                            "thread-1", "prompt"
                        ),
                    },
                    {"status": True},
                )

            self.assertEqual(result["response"], "proxied response")
            self.assertEqual(len(relay.commands), 1)
            response_files = list(
                coordinator.run_state_path.parent.glob("responses/A-*.txt")
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
                        graph.invoke(
                            {"status": True}, config=config, durability="sync"
                        )
                    self.assertEqual(graph.get_state(config).next, ("B",))

                    fail_b["value"] = False
                    result = graph.invoke(None, config=config, durability="sync")

            self.assertEqual(calls, ["A", "B", "B", "C", "D", "E", "F"])
            self.assertEqual(result["current_node"], "F")

    def test_main_preflights_before_checkpoint_and_invokes_synchronously(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact_path = root / "artifacts"
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
                        "--artifact-path",
                        str(artifact_path),
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
            artifact_path = root / "artifacts"
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
                "schema": "aegis.run_state.v1",
                "run_id": "run-resume",
                "status": "failed",
                "project_root": str(root.resolve()),
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
                        "--artifact-path",
                        str(artifact_path),
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
            artifact_path = root / "artifacts"
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
                "schema": "aegis.run_state.v1",
                "run_id": "run-resume-after-planning",
                "status": "failed",
                "project_root": str(root.resolve()),
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
                        "--artifact-path",
                        str(artifact_path),
                        "--resume-run-id",
                        "run-resume-after-planning",
                        "--tracerelay-upstream-port",
                        "7899",
                    ]
                )

            self.assertEqual(events, ["preflight", "invoke", "complete"])


if __name__ == "__main__":
    unittest.main()
