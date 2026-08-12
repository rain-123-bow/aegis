from __future__ import annotations

import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "test"))

import test_traced_app_server_real_integration as real_acceptance


class RegistrationCrashReportTests(unittest.TestCase):
    def valid_case(self, crash_mode: str) -> dict[str, object]:
        operation_id = (
            "1" * 32
            if crash_mode == "after_register_before_popen"
            else "2" * 32
        )
        session_id = f"session-{operation_id}"
        session_path = Path("C:/TraceRelay/sessions") / session_id
        marker: dict[str, object] = {
            "crash_mode": crash_mode,
            "popen_started": crash_mode == "after_popen_before_identity_checkpoint",
        }
        if crash_mode == "after_popen_before_identity_checkpoint":
            marker["observed_process_pid"] = 1234
        return {
            "crash_mode": crash_mode,
            "worker_exit_code": 91,
            "operation_id": operation_id,
            "session_id": session_id,
            "session_path": str(session_path),
            "marker": marker,
            "recovery_cli_commands": [
                ["resolve-registration", "--operation-id", operation_id],
                ["close"],
                ["verify", str(session_path)],
            ],
            "verification": {"status": "VALID_COMPLETE"},
            "application_verification_status": "INVALID",
            "persisted_process_pid": None,
            "persisted_process_creation_time_100ns": None,
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
            "invalid_journal": [
                {**valid_cases[0], "verification": {"status": "VALID_INCOMPLETE"}},
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


if __name__ == "__main__":
    unittest.main()
