from __future__ import annotations

import copy
import hashlib
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "test"))

import runtime_codex_acceptance


class RuntimeCodexAcceptanceReportTests(unittest.TestCase):
    def valid_report(self) -> dict[str, object]:
        tracerelay_command = list(
            runtime_codex_acceptance.resolve_tracerelay_command()
        )
        return {
            "verdict": "PASS",
            "source_sha256": runtime_codex_acceptance._source_sha256(),
            "tracerelay_command": tracerelay_command,
            "tracerelay_python_sha256": hashlib.sha256(
                Path(tracerelay_command[0]).read_bytes()
            ).hexdigest(),
        }

    def test_report_binding_accepts_the_current_execution_sources(self) -> None:
        runtime_codex_acceptance._validate_report_source_binding(self.valid_report())

    def test_report_binding_requires_pass_and_every_source_hash(self) -> None:
        missing_verdict = self.valid_report()
        missing_verdict.pop("verdict")
        with self.assertRaisesRegex(AssertionError, "verdict"):
            runtime_codex_acceptance._validate_report_source_binding(missing_verdict)

        for source_path in runtime_codex_acceptance.REQUIRED_SOURCE_BINDINGS:
            with self.subTest(source_path=source_path):
                missing_source = self.valid_report()
                source_sha256 = copy.deepcopy(missing_source["source_sha256"])
                assert isinstance(source_sha256, dict)
                source_sha256.pop(source_path)
                missing_source["source_sha256"] = source_sha256
                with self.assertRaisesRegex(AssertionError, "source_sha256"):
                    runtime_codex_acceptance._validate_report_source_binding(
                        missing_source
                    )

    def test_report_binding_rejects_malformed_or_mismatched_hashes(self) -> None:
        source_path = runtime_codex_acceptance.REQUIRED_SOURCE_BINDINGS[0]
        for invalid_hash in ("not-a-sha256", "0" * 64):
            with self.subTest(invalid_hash=invalid_hash):
                report = self.valid_report()
                source_sha256 = copy.deepcopy(report["source_sha256"])
                assert isinstance(source_sha256, dict)
                source_sha256[source_path] = invalid_hash
                report["source_sha256"] = source_sha256
                with self.assertRaisesRegex(AssertionError, "source_sha256"):
                    runtime_codex_acceptance._validate_report_source_binding(report)

    def test_report_binding_requires_the_current_tracerelay_python_hash(self) -> None:
        for missing_field in (
            "tracerelay_command",
            "tracerelay_python_sha256",
        ):
            with self.subTest(missing_field=missing_field):
                report = self.valid_report()
                report.pop(missing_field)
                with self.assertRaisesRegex(AssertionError, "TraceRelay"):
                    runtime_codex_acceptance._validate_report_source_binding(report)

        mismatched = self.valid_report()
        mismatched["tracerelay_python_sha256"] = "0" * 64
        with self.assertRaisesRegex(AssertionError, "TraceRelay Python"):
            runtime_codex_acceptance._validate_report_source_binding(mismatched)


if __name__ == "__main__":
    unittest.main()
