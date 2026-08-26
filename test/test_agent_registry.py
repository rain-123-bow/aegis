from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import agent_registry
from agent_registry import DynamicAgentRegistry, RegistryError


class DynamicAgentRegistryTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows process semantics only")
    def test_exited_windows_owner_is_not_alive_while_handle_remains_open(self) -> None:
        with subprocess.Popen(
            [sys.executable, "-c", "raise SystemExit(259)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ) as process:
            identity = agent_registry._process_identity(process.pid)
            self.assertEqual(process.wait(timeout=10), 259)

            self.assertFalse(
                agent_registry._process_owner_is_alive(process.pid, identity)
            )

    def test_project_lease_rejects_parallel_instance_even_for_same_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            first = DynamicAgentRegistry(runtime_root, project_id="project-1")
            second = DynamicAgentRegistry(runtime_root, project_id="project-1")

            first.acquire_project_lease("run-1")
            with self.assertRaisesRegex(RegistryError, "active coordinator"):
                second.acquire_project_lease("run-1")
            with self.assertRaisesRegex(RegistryError, "active coordinator"):
                second.acquire_project_lease("run-2")

            first.release_project_lease("run-1")
            second.acquire_project_lease("run-2")

    def test_dead_owner_can_be_recovered_by_compare_and_swap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            first = DynamicAgentRegistry(runtime_root, project_id="project-1")
            second = DynamicAgentRegistry(runtime_root, project_id="project-1")
            first.acquire_project_lease("run-1")
            with patch.object(
                agent_registry, "_process_owner_is_alive", return_value=False
            ):
                second.acquire_project_lease("run-1")
            with self.assertRaisesRegex(RegistryError, "another coordinator"):
                first.release_project_lease("run-1")
            second.heartbeat_project_lease("run-1")
            second.release_project_lease("run-1")

    def test_owner_probe_error_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            first = DynamicAgentRegistry(runtime_root, project_id="project-1")
            second = DynamicAgentRegistry(runtime_root, project_id="project-1")
            first.acquire_project_lease("run-1")
            with (
                patch.object(
                    agent_registry,
                    "_process_identity",
                    side_effect=RegistryError("access denied"),
                ),
                self.assertRaisesRegex(RegistryError, "access denied"),
            ):
                second.acquire_project_lease("run-2")
            first.heartbeat_project_lease("run-1")
            first.release_project_lease("run-1")

    def test_concurrent_allocations_do_not_overwrite_each_other(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            barrier = threading.Barrier(2)
            errors: list[BaseException] = []

            def allocate(role: str, digest: str) -> None:
                try:
                    registry = DynamicAgentRegistry(
                        runtime_root, project_id="project-1"
                    )
                    barrier.wait(timeout=5)
                    allocation = registry.begin_allocation(
                        role,
                        developer_instructions_sha256=digest * 64,
                        skill_bindings=[],
                    )
                    registry.activate(
                        role,
                        agent_id=str(allocation["agent_id"]),
                        thread_id=f"thread-{role.lower()}",
                        model="gpt-5.6-sol",
                        reasoning_effort="high",
                    )
                except BaseException as error:  # pragma: no cover - surfaced below
                    errors.append(error)

            threads = [
                threading.Thread(target=allocate, args=("ROLE_A", "a")),
                threading.Thread(target=allocate, args=("ROLE_B", "b")),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

            self.assertFalse(errors)
            reloaded = DynamicAgentRegistry(runtime_root, project_id="project-1")
            self.assertIsNotNone(reloaded.active("ROLE_A"))
            self.assertIsNotNone(reloaded.active("ROLE_B"))

    def test_active_thread_survives_registry_reload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            registry = DynamicAgentRegistry(runtime_root, project_id="project-1")

            allocation = registry.begin_allocation(
                "FINAL_REVIEWER",
                developer_instructions_sha256="a" * 64,
                skill_bindings=[
                    {
                        "name": "aegis-final-reviewer",
                        "version": "1",
                        "sha256": "b" * 64,
                    }
                ],
            )
            activated = registry.activate(
                "FINAL_REVIEWER",
                agent_id=str(allocation["agent_id"]),
                thread_id="thread-final",
                model="gpt-5.6-sol",
                reasoning_effort="high",
            )

            reloaded = DynamicAgentRegistry(runtime_root, project_id="project-1")
            self.assertEqual(reloaded.active("FINAL_REVIEWER"), activated)
            self.assertEqual(
                reloaded.path,
                runtime_root / "project_state" / "dynamic_agent_registry.json",
            )

    def test_registry_rejects_project_mismatch_and_cross_role_thread_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            registry = DynamicAgentRegistry(runtime_root, project_id="project-1")
            allocation = registry.begin_allocation(
                "TEST_EXECUTOR",
                developer_instructions_sha256="a" * 64,
                skill_bindings=[],
            )
            registry.activate(
                "TEST_EXECUTOR",
                agent_id=str(allocation["agent_id"]),
                thread_id="thread-1",
                model="gpt-5.6-sol",
                reasoning_effort="high",
            )
            second = registry.begin_allocation(
                "FINAL_REVIEWER",
                developer_instructions_sha256="c" * 64,
                skill_bindings=[],
            )
            with self.assertRaisesRegex(RegistryError, "already belongs"):
                registry.activate(
                    "FINAL_REVIEWER",
                    agent_id=str(second["agent_id"]),
                    thread_id="thread-1",
                    model="gpt-5.6-sol",
                    reasoning_effort="high",
                )
            with self.assertRaisesRegex(RegistryError, "project identity"):
                DynamicAgentRegistry(runtime_root, project_id="project-2")

    def test_retired_thread_is_preserved_when_replacement_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = DynamicAgentRegistry(Path(directory), project_id="project-1")
            first = registry.begin_allocation(
                "TEST_PLAN_AUTHOR",
                developer_instructions_sha256="a" * 64,
                skill_bindings=[],
            )
            registry.activate(
                "TEST_PLAN_AUTHOR",
                agent_id=str(first["agent_id"]),
                thread_id="thread-old",
                model="gpt-5.6-sol",
                reasoning_effort="high",
            )
            retired = registry.retire(
                "TEST_PLAN_AUTHOR", reason="thread unavailable"
            )
            replacement = registry.begin_allocation(
                "TEST_PLAN_AUTHOR",
                developer_instructions_sha256="b" * 64,
                skill_bindings=[],
                replaces_thread_id="thread-old",
            )

            self.assertEqual(retired["lifecycle"], "retired")
            self.assertIsNone(registry.active("TEST_PLAN_AUTHOR"))
            self.assertEqual(replacement["replaces_thread_id"], "thread-old")
            self.assertEqual(
                registry.retired("TEST_PLAN_AUTHOR")[0]["thread_id"],
                "thread-old",
            )


if __name__ == "__main__":
    unittest.main()
