from __future__ import annotations

import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "test"))

import test_traced_app_server_real_integration as real_acceptance  # noqa: E402


class RegistrationCrashReportTests(unittest.TestCase):
    def valid_case(self, crash_mode: str) -> dict[str, object]:
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
            "persisted_process_pid": False,
            "persisted_process_creation_time_100ns": False,
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
