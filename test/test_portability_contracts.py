from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TEST_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(TEST_ROOT))

import acceptance_preparation
import runtime_codex_acceptance


def load_database_tests():
    spec = importlib.util.spec_from_file_location("isolated_ledger_tests", TEST_ROOT / "test_reasoning_ledger.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PortabilityContractTests(unittest.TestCase):
    def test_acceptance_default_stays_in_current_users_temp_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original_absolute = acceptance_preparation._absolute

            def checked_absolute(value):
                path = original_absolute(value)
                self.assertTrue(path.is_relative_to(Path(directory).resolve()))
                return path

            with (
                patch("tempfile.gettempdir", return_value=directory),
                patch.object(acceptance_preparation, "_absolute", side_effect=checked_absolute),
            ):
                fixture = acceptance_preparation.resolve_acceptance_fixture("control-plane", environment={})
            self.assertTrue(fixture.is_relative_to(Path(directory).resolve()))

    def test_prepared_acceptance_requires_an_explicit_root(self) -> None:
        with self.assertRaisesRegex(ValueError, "explicit.*root"):
            acceptance_preparation.resolve_acceptance_fixture(
                "control-plane", environment={"AEGIS_APP_SERVER_PREPARED_SHA256": "0" * 64},
            )

    def test_retired_acceptance_entry_fails_before_any_runtime_or_project_access(self) -> None:
        with (
            patch.object(runtime_codex_acceptance, "resolve_tracerelay_command", side_effect=AssertionError("runtime accessed")),
            patch.object(runtime_codex_acceptance, "_prepare_project", side_effect=AssertionError("project changed")),
            self.assertRaisesRegex(RuntimeError, "retired.*test_traced_app_server_real_integration"),
        ):
            runtime_codex_acceptance.run_acceptance(argparse.Namespace(tracerelay_python=None))

    def test_database_tests_do_not_reuse_business_credentials(self) -> None:
        with patch.dict(os.environ, {"AEGIS_LEDGER_DSN": "business-database-must-not-be-used"}, clear=True):
            module = load_database_tests()
        self.assertIsNone(module.TEST_DSN)
        with patch.object(module.psycopg, "connect") as connect, self.assertRaises(unittest.SkipTest):
            module.require_test_database()
        connect.assert_not_called()

    def test_database_test_schema_is_unique_and_explicit_dsn_is_used(self) -> None:
        with patch.dict(os.environ, {"AEGIS_TEST_LEDGER_DSN": "explicit-test-dsn"}, clear=True):
            first, second = load_database_tests(), load_database_tests()
        self.assertEqual(first.TEST_DSN, "explicit-test-dsn")
        self.assertNotEqual(first.TEST_SCHEMA, second.TEST_SCHEMA)
        self.assertRegex(first.TEST_SCHEMA, r"^aegis_test_ledger_v3_[0-9a-f]{12}$")

    def test_explicit_but_unavailable_test_database_is_a_failure(self) -> None:
        with patch.dict(os.environ, {"AEGIS_TEST_LEDGER_DSN": "explicit-test-dsn"}, clear=True):
            module = load_database_tests()
        try:
            with (
                patch.object(module.psycopg, "connect", side_effect=module.psycopg.OperationalError("fixture offline")),
                self.assertRaisesRegex(RuntimeError, "configured.*database.*unavailable"),
            ):
                module.require_test_database()
        except unittest.SkipTest:
            self.fail("an explicitly configured but broken database must fail, not skip")


if __name__ == "__main__":
    unittest.main()
