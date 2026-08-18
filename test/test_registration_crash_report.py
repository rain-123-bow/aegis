from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
import time
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "test"))

import test_traced_app_server_real_integration as real_acceptance  # noqa: E402


class RegistrationCrashReportTests(unittest.TestCase):
    def test_wait_failure_is_not_reported_as_process_termination(self) -> None:
        class Function:
            def __init__(self, result: object) -> None:
                self.result = result

            def __call__(self, *_args: object) -> object:
                return self.result

        class Kernel32:
            def __init__(self) -> None:
                self.OpenProcess = Function(123)
                self.WaitForSingleObject = Function(0xFFFFFFFF)
                self.CloseHandle = Function(1)

        with patch.object(
            ctypes, "WinDLL", return_value=Kernel32()
        ):
            with self.assertRaises(OSError):
                real_acceptance._windows_process_is_running(1234)

    def test_creation_time_inspection_failure_is_not_termination(self) -> None:
        with (
            patch.object(
                real_acceptance,
                "_windows_process_is_running",
                return_value=True,
            ),
            patch.object(
                real_acceptance,
                "_windows_process_creation_time_100ns",
                side_effect=RuntimeError("synthetic identity inspection failure"),
            ),
            self.assertRaisesRegex(RuntimeError, "identity inspection failure"),
        ):
            real_acceptance._windows_process_identity_is_running(1234, 5678)

    @unittest.skipUnless(os.name == "nt", "process identity test is Windows-only")
    def test_direct_child_enumerator_binds_live_process_identity(self) -> None:
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 5
            while (
                child.pid
                not in real_acceptance._windows_direct_child_pids(os.getpid())
                and time.monotonic() < deadline
            ):
                time.sleep(0.02)
            self.assertIn(
                child.pid,
                real_acceptance._windows_direct_child_pids(os.getpid()),
            )
            creation_time = real_acceptance._windows_process_creation_time_100ns(
                child.pid
            )
            parent_creation_time = (
                real_acceptance._windows_process_creation_time_100ns(os.getpid())
            )
            image_path = real_acceptance._windows_process_image_path(child.pid)
            self.assertTrue(
                real_acceptance._windows_process_identity_is_running(
                    child.pid, creation_time
                )
            )
            self.assertGreater(creation_time, parent_creation_time)
            self.assertTrue(
                real_acceptance._same_windows_executable_path(
                    image_path, Path(sys.executable)
                )
            )
            self.assertIn(
                "time.sleep(30)",
                real_acceptance._windows_process_command_line(child.pid),
            )
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)

    def valid_case(self, crash_mode: str) -> dict[str, object]:
        codex_identity = real_acceptance._capture_codex_cli_identity(sys.executable)
        codex_cli_path = codex_identity["codex_cli_path"]
        operation_id = (
            "1" * 32
            if crash_mode == "after_register_before_popen"
            else "2" * 32
        )
        timestamp = (
            "20260812T120000.000001Z"
            if crash_mode == "after_register_before_popen"
            else "20260812T120000.000002Z"
        )
        session_id = f"{timestamp}_{operation_id}"
        session_path = Path("C:/TraceRelay/sessions") / session_id
        marker: dict[str, object] = {
            "crash_mode": crash_mode,
            "popen_started": crash_mode == "after_popen_before_identity_checkpoint",
        }
        if crash_mode == "after_popen_before_identity_checkpoint":
            marker.update(
                observed_process_pid=1234,
                observed_process_creation_time_100ns=123_456_789,
                observed_process_active_before_crash=True,
                observed_child_pid=5678,
                observed_child_creation_time_100ns=987_654_321,
                expected_child_image_path=str(Path(sys.executable).resolve()),
                observed_child_image_path=str(Path(sys.executable).resolve()),
                observed_child_active_before_crash=True,
                observed_descendant_processes=[
                    {
                        "pid": 6789,
                        "parent_pid": 5678,
                        "creation_time_100ns": 1_000_000_000,
                        "image_path": str(Path(sys.executable).resolve()),
                        "command_line": "node codex.js app-server --listen stdio://",
                        "active_before_crash": True,
                    }
                ],
                job_name=real_acceptance._windows_job_name(operation_id),
                job_creation_frozen=True,
                frozen_job_member_processes=[
                    {
                        "pid": 1234,
                        "parent_pid": 1111,
                        "creation_time_100ns": 123_456_789,
                        "image_path": str(Path(sys.executable).resolve()),
                        "command_line": (
                            "python windows_job_runner.py --job-name "
                            f"Local\\Aegis-test -- {codex_cli_path} app-server"
                        ),
                        "active_before_crash": True,
                        "suspended_before_crash": False,
                    },
                    {
                        "pid": 5678,
                        "parent_pid": 1234,
                        "creation_time_100ns": 987_654_321,
                        "image_path": str(Path(sys.executable).resolve()),
                        "command_line": (
                            f"cmd.exe /c {codex_cli_path} app-server"
                        ),
                        "active_before_crash": True,
                        "suspended_before_crash": True,
                    },
                    {
                        "pid": 6789,
                        "parent_pid": 5678,
                        "creation_time_100ns": 1_000_000_000,
                        "image_path": str(Path(sys.executable).resolve()),
                        "command_line": "node codex.js app-server --listen stdio://",
                        "active_before_crash": True,
                        "suspended_before_crash": True,
                    },
                ],
            )
        return {
            "crash_mode": crash_mode,
            "worker_exit_code": 91,
            "operation_id": operation_id,
            "session_id": session_id,
            "session_path": str(session_path),
            "marker": marker,
            "recovery_cli_commands": [
                ["resolve-registration", "--operation-id", operation_id],
                ["close", "--runtime-nonce", "a" * 32],
                ["verify", str(session_path)],
            ],
            "verification": {
                "final_hash": "0" * 64,
                "observed_bytes": {
                    "client_to_upstream": 0,
                    "upstream_to_client": 0,
                },
                "observed_connection_count": 0,
                "record_count": 0,
                "sent_error_bytes": {
                    "client_to_upstream": 0,
                    "upstream_to_client": 0,
                },
                "sent_success_bytes": {
                    "client_to_upstream": 0,
                    "upstream_to_client": 0,
                },
                "status": "VALID_COMPLETE",
                "unknown_bytes": {
                    "client_to_upstream": 0,
                    "upstream_to_client": 0,
                },
            },
            "application_verification_status": "INVALID",
            "final_run_status": "terminated",
            "termination_reason_code": "FREEZE_CONTINUITY_LOST",
            "persisted_process_pid": None,
            "persisted_process_creation_time_100ns": None,
            "observed_process_terminated": (
                True
                if crash_mode == "after_popen_before_identity_checkpoint"
                else None
            ),
            "observed_child_terminated": (
                True
                if crash_mode == "after_popen_before_identity_checkpoint"
                else None
            ),
            "observed_descendants_terminated": (
                True
                if crash_mode == "after_popen_before_identity_checkpoint"
                else None
            ),
            "frozen_job_members_terminated": (
                True
                if crash_mode == "after_popen_before_identity_checkpoint"
                else None
            ),
            **codex_identity,
        }

    def test_report_is_published_only_after_both_required_cases_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_path = Path(temporary_directory) / "REGISTRATION_CRASH_REPORT.json"
            cases = [
                self.valid_case(mode)
                for mode in real_acceptance.REQUIRED_REGISTRATION_CRASH_MODES
            ]

            report = real_acceptance._publish_registration_crash_report(
                report_path,
                cases=cases,
                tracerelay_command=Path(sys.executable),
            )

            self.assertEqual(
                report["schema"], "aegis.registration_crash_acceptance.v7"
            )
            self.assertEqual(report["verdict"], "PASS")
            self.assertTrue(report_path.is_file())

    def test_already_idle_recovery_does_not_require_redundant_close(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_path = Path(temporary_directory) / "REGISTRATION_CRASH_REPORT.json"
            cases = [
                self.valid_case(mode)
                for mode in real_acceptance.REQUIRED_REGISTRATION_CRASH_MODES
            ]
            for case in cases:
                commands = case["recovery_cli_commands"]
                assert isinstance(commands, list)
                commands.pop(1)

            report = real_acceptance._publish_registration_crash_report(
                report_path,
                cases=cases,
                tracerelay_command=Path(sys.executable),
            )

            self.assertEqual(report["verdict"], "PASS")
            self.assertTrue(report_path.is_file())

    def test_first_or_second_case_failure_cannot_publish_a_pass_report(self) -> None:
        for failed_mode in real_acceptance.REQUIRED_REGISTRATION_CRASH_MODES:
            with self.subTest(failed_mode=failed_mode):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    report_path = (
                        Path(temporary_directory) / "REGISTRATION_CRASH_REPORT.json"
                    )

                    def run_case(crash_mode: str) -> dict[str, object]:
                        if crash_mode == failed_mode:
                            raise AssertionError(f"injected failure: {failed_mode}")
                        return self.valid_case(crash_mode)

                    with self.assertRaisesRegex(AssertionError, "injected failure"):
                        cases = real_acceptance._collect_registration_crash_cases(
                            run_case
                        )
                        real_acceptance._publish_registration_crash_report(
                            report_path,
                            cases=cases,
                            tracerelay_command=Path(sys.executable),
                        )
                    self.assertFalse(report_path.exists())

    def test_incomplete_or_invalid_case_set_cannot_publish_pass(self) -> None:
        valid_cases = [
            self.valid_case(mode)
            for mode in real_acceptance.REQUIRED_REGISTRATION_CRASH_MODES
        ]
        invalid_sets = {
            "missing": valid_cases[:1],
            "duplicate": [valid_cases[0], valid_cases[0]],
            "wrong_exit": [{**valid_cases[0], "worker_exit_code": 1}, valid_cases[1]],
            "bad_operation": [
                {**valid_cases[0], "operation_id": "not-an-operation"},
                valid_cases[1],
            ],
            "duplicate_operation": [
                valid_cases[0],
                {**valid_cases[1], "operation_id": valid_cases[0]["operation_id"]},
            ],
            "wrong_session_path": [
                {**valid_cases[0], "session_path": "C:/TraceRelay/sessions/other"},
                valid_cases[1],
            ],
            "noncanonical_session": [
                {
                    **valid_cases[0],
                    "session_id": "session-" + "1" * 32,
                    "session_path": "C:/TraceRelay/sessions/session-" + "1" * 32,
                    "recovery_cli_commands": [
                        [
                            "resolve-registration",
                            "--operation-id",
                            valid_cases[0]["operation_id"],
                        ],
                        ["close"],
                        ["verify", "C:/TraceRelay/sessions/session-" + "1" * 32],
                    ],
                },
                valid_cases[1],
            ],
            "invalid_session_timestamp": [
                {
                    **valid_cases[0],
                    "session_id": "20261340T256199.000001Z_" + "1" * 32,
                    "session_path": (
                        "C:/TraceRelay/sessions/20261340T256199.000001Z_"
                        + "1" * 32
                    ),
                    "recovery_cli_commands": [
                        [
                            "resolve-registration",
                            "--operation-id",
                            valid_cases[0]["operation_id"],
                        ],
                        ["close"],
                        [
                            "verify",
                            "C:/TraceRelay/sessions/20261340T256199.000001Z_"
                            + "1" * 32,
                        ],
                    ],
                },
                valid_cases[1],
            ],
            "duplicate_session": [
                valid_cases[0],
                {
                    **valid_cases[1],
                    "session_id": valid_cases[0]["session_id"],
                    "session_path": valid_cases[0]["session_path"],
                    "recovery_cli_commands": [
                        [
                            "resolve-registration",
                            "--operation-id",
                            valid_cases[1]["operation_id"],
                        ],
                        ["close"],
                        ["verify", valid_cases[0]["session_path"]],
                    ],
                },
            ],
            "marker_mismatch": [
                {**valid_cases[0], "marker": deepcopy(valid_cases[1]["marker"])},
                valid_cases[1],
            ],
            "new_register": [
                {
                    **valid_cases[0],
                    "recovery_cli_commands": [
                        *valid_cases[0]["recovery_cli_commands"],
                        ["register"],
                    ],
                },
                valid_cases[1],
            ],
            "invalid_runtime_nonce": [
                {
                    **valid_cases[0],
                    "recovery_cli_commands": [
                        valid_cases[0]["recovery_cli_commands"][0],
                        ["close", "--runtime-nonce", "not-a-runtime-nonce"],
                        valid_cases[0]["recovery_cli_commands"][2],
                    ],
                },
                valid_cases[1],
            ],
            "invalid_journal": [
                {
                    **valid_cases[0],
                    "verification": {
                        **valid_cases[0]["verification"],
                        "status": "VALID_INCOMPLETE",
                    },
                },
                valid_cases[1],
            ],
            "valid_application": [
                {
                    **valid_cases[0],
                    "application_verification_status": "VALID_COMPLETE",
                },
                valid_cases[1],
            ],
            "fake_pid": [{**valid_cases[0], "persisted_process_pid": 123}, valid_cases[1]],
            "fake_filetime": [
                {
                    **valid_cases[0],
                    "persisted_process_creation_time_100ns": 123,
                },
                valid_cases[1],
            ],
            "orphaned_process": [
                valid_cases[0],
                {**valid_cases[1], "observed_process_terminated": False},
            ],
            "orphaned_child": [
                valid_cases[0],
                {**valid_cases[1], "observed_child_terminated": False},
            ],
            "orphaned_descendant": [
                valid_cases[0],
                {**valid_cases[1], "observed_descendants_terminated": False},
            ],
            "orphaned_frozen_job_member": [
                valid_cases[0],
                {**valid_cases[1], "frozen_job_members_terminated": False},
            ],
            "job_not_frozen": [
                valid_cases[0],
                {
                    **valid_cases[1],
                    "marker": {
                        **valid_cases[1]["marker"],
                        "job_creation_frozen": False,
                    },
                },
            ],
            "incomplete_job_membership": [
                valid_cases[0],
                {
                    **valid_cases[1],
                    "marker": {
                        **valid_cases[1]["marker"],
                        "frozen_job_member_processes": valid_cases[1]["marker"][
                            "frozen_job_member_processes"
                        ][:-1],
                    },
                },
            ],
            "unproven_runner_identity": [
                valid_cases[0],
                {
                    **valid_cases[1],
                    "marker": {
                        **valid_cases[1]["marker"],
                        "observed_process_active_before_crash": False,
                    },
                },
            ],
            "unproven_child_identity": [
                valid_cases[0],
                {
                    **valid_cases[1],
                    "marker": {
                        **valid_cases[1]["marker"],
                        "observed_child_creation_time_100ns": 0,
                    },
                },
            ],
            "child_predates_runner": [
                valid_cases[0],
                {
                    **valid_cases[1],
                    "marker": {
                        **valid_cases[1]["marker"],
                        "observed_child_creation_time_100ns": 123_456_788,
                    },
                },
            ],
            "wrong_child_image": [
                valid_cases[0],
                {
                    **valid_cases[1],
                    "marker": {
                        **valid_cases[1]["marker"],
                        "observed_child_image_path": str(
                            (Path(sys.executable).parent / "other.exe").resolve()
                        ),
                    },
                },
            ],
            "unbound_app_server_command": [
                valid_cases[0],
                {
                    **valid_cases[1],
                    "marker": {
                        **valid_cases[1]["marker"],
                        "observed_descendant_processes": [
                            {
                                **valid_cases[1]["marker"][
                                    "observed_descendant_processes"
                                ][0],
                                "command_line": "node unrelated.js",
                            }
                        ],
                    },
                },
            ],
        }
        for label, cases in invalid_sets.items():
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    report_path = (
                        Path(temporary_directory) / "REGISTRATION_CRASH_REPORT.json"
                    )
                    with self.assertRaises(AssertionError):
                        real_acceptance._publish_registration_crash_report(
                            report_path,
                            cases=cases,
                            tracerelay_command=Path(sys.executable),
                        )
                    self.assertFalse(report_path.exists())

    def test_wrong_field_types_cannot_publish_pass(self) -> None:
        valid_cases = [
            self.valid_case(mode)
            for mode in real_acceptance.REQUIRED_REGISTRATION_CRASH_MODES
        ]
        invalid_values: dict[str, object] = {
            "crash_mode": 1,
            "worker_exit_code": "91",
            "operation_id": 1,
            "session_id": 1,
            "session_path": 1,
            "marker": [],
            "recovery_cli_commands": "resolve-registration",
            "verification": [],
            "application_verification_status": True,
            "final_run_status": "completed",
            "termination_reason_code": "FROZEN_INPUT_MUTATION",
            "persisted_process_pid": False,
            "persisted_process_creation_time_100ns": False,
            "observed_process_terminated": False,
            "observed_child_terminated": False,
            "observed_descendants_terminated": False,
            "frozen_job_members_terminated": False,
            "codex_cli_path": 1,
            "codex_cli_version": "",
            "codex_cli_sha256": "not-a-sha256",
        }
        for field, invalid_value in invalid_values.items():
            with self.subTest(field=field):
                cases = deepcopy(valid_cases)
                cases[0][field] = invalid_value
                with tempfile.TemporaryDirectory() as temporary_directory:
                    report_path = (
                        Path(temporary_directory) / "REGISTRATION_CRASH_REPORT.json"
                    )
                    with self.assertRaises(AssertionError):
                        real_acceptance._publish_registration_crash_report(
                            report_path,
                            cases=cases,
                            tracerelay_command=Path(sys.executable),
                        )
                    self.assertFalse(report_path.exists())

    def test_each_required_case_and_nested_field_is_mandatory(self) -> None:
        valid_cases = [
            self.valid_case(mode)
            for mode in real_acceptance.REQUIRED_REGISTRATION_CRASH_MODES
        ]
        missing_variants: list[tuple[str, list[dict[str, object]]]] = []
        for field in real_acceptance.REGISTRATION_CRASH_CASE_FIELDS:
            cases = deepcopy(valid_cases)
            cases[0].pop(field)
            missing_variants.append((f"case.{field}", cases))
        for field in valid_cases[0]["marker"]:
            cases = deepcopy(valid_cases)
            marker = cases[0]["marker"]
            assert isinstance(marker, dict)
            marker.pop(field)
            missing_variants.append((f"marker.{field}", cases))
        for field in valid_cases[1]["marker"]:
            cases = deepcopy(valid_cases)
            marker = cases[1]["marker"]
            assert isinstance(marker, dict)
            marker.pop(field)
            missing_variants.append((f"popen_marker.{field}", cases))
        for field in real_acceptance.REGISTRATION_CRASH_VERIFICATION_FIELDS:
            cases = deepcopy(valid_cases)
            verification = cases[0]["verification"]
            assert isinstance(verification, dict)
            verification.pop(field)
            missing_variants.append((f"verification.{field}", cases))
        for byte_field in (
            "observed_bytes",
            "sent_error_bytes",
            "sent_success_bytes",
            "unknown_bytes",
        ):
            for direction in real_acceptance.REGISTRATION_CRASH_BYTE_DIRECTIONS:
                cases = deepcopy(valid_cases)
                verification = cases[0]["verification"]
                assert isinstance(verification, dict)
                byte_counts = verification[byte_field]
                assert isinstance(byte_counts, dict)
                byte_counts.pop(direction)
                missing_variants.append((f"{byte_field}.{direction}", cases))

        for label, cases in missing_variants:
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    report_path = (
                        Path(temporary_directory) / "REGISTRATION_CRASH_REPORT.json"
                    )
                    with self.assertRaises(AssertionError):
                        real_acceptance._publish_registration_crash_report(
                            report_path,
                            cases=cases,
                            tracerelay_command=Path(sys.executable),
                        )
                    self.assertFalse(report_path.exists())


if __name__ == "__main__":
    unittest.main()
