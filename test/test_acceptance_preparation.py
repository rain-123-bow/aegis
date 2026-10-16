from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "test"))

import acceptance_preparation as preparation  # noqa: E402
import test_traced_app_server_real_integration as real_acceptance  # noqa: E402


CASES = {
    "control-plane": "as_pilot",
    "hard-crash": "as_crash_recovery",
    "registration-crash": "as_registration_crash",
}
REJECTION_ERRORS = (ValueError, RuntimeError, OSError)


class AcceptancePreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="aegis-preparation-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()
        self.root = self.directory / "acceptance"
        self.config = self.directory / "config.toml"
        self.config.write_bytes(b'model = "synthetic-model"\n')

    def initialize_trust(self, project: Path) -> None:
        project_key = json.dumps(os.path.normcase(str(project.resolve())))
        self.config.write_bytes(
            self.config.read_bytes()
            + f'\n[projects.{project_key}]\ntrust_level = "trusted"\n'.encode("utf-8")
        )

    def prepare(
        self,
        cases: tuple[str, ...] = tuple(CASES),
        initialize_project: Callable[[Path], None] | None = None,
    ) -> Path:
        if initialize_project is None:
            initialize_project = self.initialize_trust
        return preparation.prepare_acceptance(
            self.root,
            cases,
            config_path=self.config,
            initialize_project=initialize_project,
        )

    def environment(self, manifest: Path) -> dict[str, str]:
        return {
            "AEGIS_APP_SERVER_ACCEPTANCE_ROOT": str(self.root),
            "AEGIS_APP_SERVER_PREPARED_MANIFEST": str(manifest),
            "AEGIS_APP_SERVER_PREPARED_SHA256": hashlib.sha256(
                manifest.read_bytes()
            ).hexdigest(),
        }

    def payload(self, manifest: Path) -> dict:
        return json.loads(manifest.read_text(encoding="utf-8"))

    def rewrite_manifest(self, manifest: Path, payload: dict) -> dict[str, str]:
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        return self.environment(manifest)

    def assert_rejected_without_claim(
        self,
        environment: dict[str, str],
        *,
        case: str = "hard-crash",
    ) -> None:
        before = sorted(self.root.rglob("CLAIMED")) if self.root.exists() else []
        with self.assertRaises(REJECTION_ERRORS):
            preparation.resolve_acceptance_fixture(case, environment=environment)
        after = sorted(self.root.rglob("CLAIMED")) if self.root.exists() else []
        self.assertEqual(after, before)

    def test_all_projects_are_initialized_before_config_is_frozen(self) -> None:
        initialized: list[Path] = []

        def initialize(project: Path) -> None:
            self.assertTrue(project.is_absolute())
            self.assertTrue(project.is_dir())
            self.assertFalse((self.root / "PREPARED_ACCEPTANCE.json").exists())
            initialized.append(project)
            (project / "INITIALIZED").write_bytes(b"prepared before freeze")
            self.initialize_trust(project)

        manifest = self.prepare(initialize_project=initialize)
        payload = self.payload(manifest)
        self.assertEqual(manifest, self.root / "PREPARED_ACCEPTANCE.json")
        self.assertEqual(payload["schema"], "aegis.prepared_acceptance.v1")
        self.assertEqual(Path(payload["root"]), self.root)
        self.assertEqual(set(payload["cases"]), set(CASES))
        self.assertEqual(len(initialized), len(CASES))
        self.assertEqual(len(set(initialized)), len(CASES))
        self.assertEqual(
            set(initialized),
            {Path(item["project"]) for item in payload["cases"].values()},
        )
        final_bytes = self.config.read_bytes()
        self.assertEqual(
            payload["config_descriptor"],
            {
                "path": str(self.config),
                "size": len(final_bytes),
                "sha256": hashlib.sha256(final_bytes).hexdigest(),
            },
        )
        for case, category in CASES.items():
            entry = payload["cases"][case]
            self.assertRegex(entry["short_id"], r"^[0-9a-f]{12}$")
            expected_root = self.root / category / entry["short_id"]
            self.assertEqual(Path(entry["root"]), expected_root)
            self.assertEqual(Path(entry["project"]), expected_root / "project")

    def test_initialization_failure_does_not_publish_frozen_manifest(self) -> None:
        initialized: list[Path] = []

        def initialize(project: Path) -> None:
            initialized.append(project)
            raise RuntimeError("synthetic trust initialization failure")

        with self.assertRaisesRegex(RuntimeError, "synthetic trust"):
            self.prepare(initialize_project=initialize)
        self.assertEqual(len(initialized), 1)
        self.assertFalse((self.root / "PREPARED_ACCEPTANCE.json").exists())

    def test_initializer_without_project_trust_cannot_freeze_config(self) -> None:
        original = self.config.read_bytes()
        with self.assertRaises(REJECTION_ERRORS):
            self.prepare(initialize_project=lambda project: None)
        self.assertFalse((self.root / "PREPARED_ACCEPTANCE.json").exists())
        self.assertEqual(self.config.read_bytes(), original)

    def test_initializer_model_change_cannot_become_new_config_baseline(self) -> None:
        def initialize(project: Path) -> None:
            self.initialize_trust(project)
            self.config.write_bytes(
                self.config.read_bytes().replace(b"synthetic-model", b"changed-model")
            )

        with self.assertRaises(REJECTION_ERRORS):
            self.prepare(initialize_project=initialize)
        self.assertFalse((self.root / "PREPARED_ACCEPTANCE.json").exists())
        self.assertIn(b"changed-model", self.config.read_bytes())

    def test_initializer_cannot_change_nontrust_boolean_to_equal_integer(self) -> None:
        self.config.write_bytes(
            self.config.read_bytes() + b"\n[features]\nsynthetic = true\n"
        )

        def initialize(project: Path) -> None:
            self.initialize_trust(project)
            self.config.write_bytes(
                self.config.read_bytes().replace(b"synthetic = true", b"synthetic = 1")
            )

        with self.assertRaises(REJECTION_ERRORS):
            self.prepare(("hard-crash",), initialize)
        self.assertFalse((self.root / "PREPARED_ACCEPTANCE.json").exists())
        self.assertIn(b"synthetic = 1", self.config.read_bytes())

    def test_initializer_cannot_trust_an_unselected_project(self) -> None:
        foreign = self.directory / "foreign-project"

        def initialize(project: Path) -> None:
            self.initialize_trust(project)
            self.initialize_trust(foreign)

        with self.assertRaises(REJECTION_ERRORS):
            self.prepare(("hard-crash",), initialize)
        self.assertFalse((self.root / "PREPARED_ACCEPTANCE.json").exists())

    def test_initializer_cannot_change_existing_other_project_settings(self) -> None:
        self.config.write_bytes(
            self.config.read_bytes()
            + b'\n[projects.existing]\ntrust_level = "untrusted"\n'
        )

        def initialize(project: Path) -> None:
            self.initialize_trust(project)
            self.config.write_bytes(
                self.config.read_bytes().replace(b'"untrusted"', b'"trusted"')
            )

        with self.assertRaises(REJECTION_ERRORS):
            self.prepare(("hard-crash",), initialize)
        self.assertFalse((self.root / "PREPARED_ACCEPTANCE.json").exists())

    def test_existing_exact_project_trust_is_rejected_before_initializer(self) -> None:
        short_id = "0123456789ab"
        project = self.root / "as_crash_recovery" / short_id / "project"
        project_key = json.dumps(os.path.normcase(str(project.resolve())))
        self.config.write_bytes(
            self.config.read_bytes()
            + f'\n[projects.{project_key}]\ntrust_level = "untrusted"\n'.encode("utf-8")
        )
        original = self.config.read_bytes()
        initialize = MagicMock(wraps=self.initialize_trust)
        with (
            patch.object(preparation, "uuid4", return_value=SimpleNamespace(hex=short_id)),
            self.assertRaises(REJECTION_ERRORS),
        ):
            self.prepare(("hard-crash",), initialize)
        initialize.assert_not_called()
        self.assertEqual(self.config.read_bytes(), original)
        self.assertFalse((self.root / "PREPARED_ACCEPTANCE.json").exists())

    def test_new_project_trust_cannot_include_extra_settings(self) -> None:
        def initialize(project: Path) -> None:
            self.initialize_trust(project)
            self.config.write_bytes(self.config.read_bytes() + b'extra = "changed"\n')

        with self.assertRaises(REJECTION_ERRORS):
            self.prepare(("hard-crash",), initialize)
        self.assertFalse((self.root / "PREPARED_ACCEPTANCE.json").exists())

    def test_initializer_cannot_substitute_parent_directory_trust(self) -> None:
        def initialize(project: Path) -> None:
            self.initialize_trust(project.parent)

        with self.assertRaises(REJECTION_ERRORS):
            self.prepare(("hard-crash",), initialize)
        self.assertFalse((self.root / "PREPARED_ACCEPTANCE.json").exists())

    def test_repeated_preparation_preserves_prior_manifest_and_project(self) -> None:
        manifest = self.prepare()
        prior = manifest.read_bytes()
        project = Path(self.payload(manifest)["cases"]["hard-crash"]["project"])
        sentinel = project / "HISTORICAL_EVIDENCE"
        sentinel.write_bytes(b"do not overwrite")
        initialized: list[Path] = []
        with self.assertRaises(REJECTION_ERRORS):
            self.prepare(initialize_project=initialized.append)
        self.assertEqual(initialized, [])
        self.assertEqual(manifest.read_bytes(), prior)
        self.assertEqual(sentinel.read_bytes(), b"do not overwrite")

    def test_invalid_requested_case_is_rejected_before_initialization(self) -> None:
        initialized: list[Path] = []
        with self.assertRaises(REJECTION_ERRORS):
            self.prepare(("hard-crash", "unknown"), initialized.append)
        self.assertEqual(initialized, [])
        self.assertFalse((self.root / "PREPARED_ACCEPTANCE.json").exists())

    def test_prepared_cases_consume_the_preselected_roots(self) -> None:
        manifest = self.prepare()
        payload = self.payload(manifest)
        environment = self.environment(manifest)
        config_before = self.config.read_bytes()
        for case in CASES:
            with self.subTest(case=case):
                root = preparation.resolve_acceptance_fixture(
                    case, environment=environment
                )
                self.assertEqual(root, Path(payload["cases"][case]["root"]))
                self.assertTrue((root / "CLAIMED").is_file())
        self.assertEqual(self.config.read_bytes(), config_before)

    def test_registration_modes_share_one_selected_project(self) -> None:
        manifest = self.prepare(("registration-crash",))
        selected = preparation.resolve_acceptance_fixture(
            "registration-crash", environment=self.environment(manifest)
        )
        expected_project = Path(
            self.payload(manifest)["cases"]["registration-crash"]["project"]
        )
        mode_artifacts = [
            selected / mode / "artifacts"
            for mode in (
                "after_register_before_popen",
                "after_popen_before_identity_checkpoint",
            )
        ]
        self.assertEqual(selected / "project", expected_project)
        self.assertEqual({path.parents[1] for path in mode_artifacts}, {selected})
        self.assertEqual(len(list(self.root.rglob("CLAIMED"))), 1)

    def test_second_consumption_rejects_without_changing_claim_or_evidence(self) -> None:
        manifest = self.prepare()
        environment = self.environment(manifest)
        root = preparation.resolve_acceptance_fixture(
            "hard-crash", environment=environment
        )
        prior_claim = (root / "CLAIMED").read_bytes()
        evidence = root / "HISTORICAL_REPORT.json"
        evidence.write_bytes(b'{"preserved": true}')
        self.assert_rejected_without_claim(environment)
        self.assertEqual((root / "CLAIMED").read_bytes(), prior_claim)
        self.assertEqual(evidence.read_bytes(), b'{"preserved": true}')

    def test_config_change_after_freeze_is_rejected_even_for_project_trust(self) -> None:
        manifest = self.prepare()
        environment = self.environment(manifest)
        self.config.write_bytes(
            self.config.read_bytes() + b'\n[projects.synthetic]\ntrust_level = "trusted"\n'
        )
        changed_bytes = self.config.read_bytes()
        self.assert_rejected_without_claim(environment)
        self.assertEqual(self.config.read_bytes(), changed_bytes)

    def test_same_size_config_drift_is_rejected(self) -> None:
        manifest = self.prepare()
        environment = self.environment(manifest)
        original = self.config.read_bytes()
        self.config.write_bytes(original.replace(b"synthetic", b"different"))
        self.assertEqual(len(self.config.read_bytes()), len(original))
        self.assert_rejected_without_claim(environment)

    def test_missing_config_is_rejected_without_recreating_it(self) -> None:
        manifest = self.prepare()
        environment = self.environment(manifest)
        self.config.unlink()
        self.assert_rejected_without_claim(environment)
        self.assertFalse(self.config.exists())

    def test_manifest_byte_change_is_rejected_even_when_json_is_equivalent(self) -> None:
        manifest = self.prepare()
        environment = self.environment(manifest)
        manifest.write_bytes(manifest.read_bytes() + b"\n")
        self.assert_rejected_without_claim(environment)

    def test_missing_manifest_hash_does_not_fall_back_to_new_fixture(self) -> None:
        manifest = self.prepare()
        environment = self.environment(manifest)
        del environment["AEGIS_APP_SERVER_PREPARED_SHA256"]
        self.assert_rejected_without_claim(environment)

    def test_manifest_hash_without_manifest_path_does_not_fall_back(self) -> None:
        environment = {
            "AEGIS_APP_SERVER_ACCEPTANCE_ROOT": str(self.root),
            "AEGIS_APP_SERVER_PREPARED_SHA256": "a" * 64,
        }
        self.assert_rejected_without_claim(environment)
        self.assertFalse(self.root.exists())

    def test_wrong_manifest_hash_is_rejected(self) -> None:
        manifest = self.prepare()
        environment = self.environment(manifest)
        environment["AEGIS_APP_SERVER_PREPARED_SHA256"] = "0" * 64
        self.assert_rejected_without_claim(environment)

    def test_missing_manifest_does_not_fall_back_to_new_fixture(self) -> None:
        manifest = self.prepare()
        environment = self.environment(manifest)
        manifest.unlink()
        self.assert_rejected_without_claim(environment)

    def test_wrong_acceptance_root_is_rejected(self) -> None:
        manifest = self.prepare()
        environment = self.environment(manifest)
        elsewhere = self.directory / "other-acceptance"
        environment["AEGIS_APP_SERVER_ACCEPTANCE_ROOT"] = str(elsewhere)
        self.assert_rejected_without_claim(environment)
        self.assertFalse(elsewhere.exists())

    def test_missing_case_in_bound_manifest_does_not_fall_back(self) -> None:
        manifest = self.prepare(("control-plane",))
        environment = self.environment(manifest)
        self.assert_rejected_without_claim(environment)
        self.assertFalse((self.root / "as_crash_recovery").exists())

    def test_wrong_schema_is_rejected_despite_matching_manifest_hash(self) -> None:
        manifest = self.prepare()
        payload = self.payload(manifest)
        payload["schema"] = "aegis.prepared_acceptance.v0"
        self.assert_rejected_without_claim(self.rewrite_manifest(manifest, payload))

    def test_foreign_fixture_root_is_rejected_despite_matching_manifest_hash(self) -> None:
        manifest = self.prepare()
        payload = self.payload(manifest)
        foreign = self.directory / "historical" / "project"
        foreign.mkdir(parents=True)
        sentinel = foreign / "EVIDENCE"
        sentinel.write_bytes(b"historical")
        entry = payload["cases"]["hard-crash"]
        entry["root"] = str(foreign.parent)
        entry["project"] = str(foreign)
        self.assert_rejected_without_claim(self.rewrite_manifest(manifest, payload))
        self.assertEqual(sentinel.read_bytes(), b"historical")
        self.assertFalse((foreign.parent / "CLAIMED").exists())

    def test_other_cases_project_is_rejected_despite_matching_manifest_hash(self) -> None:
        manifest = self.prepare()
        payload = self.payload(manifest)
        payload["cases"]["hard-crash"]["project"] = payload["cases"][
            "control-plane"
        ]["project"]
        self.assert_rejected_without_claim(self.rewrite_manifest(manifest, payload))

    def test_case_category_swap_is_rejected_despite_matching_manifest_hash(self) -> None:
        manifest = self.prepare()
        payload = self.payload(manifest)
        payload["cases"]["hard-crash"] = payload["cases"]["control-plane"]
        self.assert_rejected_without_claim(self.rewrite_manifest(manifest, payload))

    def test_short_id_path_escape_is_rejected_despite_matching_manifest_hash(self) -> None:
        manifest = self.prepare()
        payload = self.payload(manifest)
        payload["cases"]["hard-crash"]["short_id"] = "../../historical"
        self.assert_rejected_without_claim(self.rewrite_manifest(manifest, payload))

    def test_missing_prepared_project_is_rejected_without_recreation(self) -> None:
        manifest = self.prepare()
        environment = self.environment(manifest)
        project = Path(self.payload(manifest)["cases"]["hard-crash"]["project"])
        project.rmdir()
        self.assert_rejected_without_claim(environment)
        self.assertFalse(project.exists())

    def test_legacy_selection_still_uses_fresh_case_paths(self) -> None:
        environment = {"AEGIS_APP_SERVER_ACCEPTANCE_ROOT": str(self.root)}
        for case, category in CASES.items():
            with self.subTest(case=case):
                first = preparation.resolve_acceptance_fixture(
                    case, environment=environment
                )
                second = preparation.resolve_acceptance_fixture(
                    case, environment=environment
                )
                self.assertNotEqual(first, second)
                self.assertEqual(first.parent, self.root / category)
                self.assertEqual(second.parent, self.root / category)
                self.assertRegex(first.name, r"^[0-9a-f]{12}$")
                self.assertRegex(second.name, r"^[0-9a-f]{12}$")

    def test_resolver_uses_process_environment_when_argument_is_omitted(self) -> None:
        manifest = self.prepare()
        expected = Path(self.payload(manifest)["cases"]["hard-crash"]["root"])
        with patch.dict(os.environ, self.environment(manifest), clear=True):
            selected = preparation.resolve_acceptance_fixture("hard-crash")
        self.assertEqual(selected, expected)


class CodexProjectInitializerTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="aegis-initializer-test-")
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name).resolve() / "project"
        self.project.mkdir()
        self.client = MagicMock()
        self.client.__enter__.return_value = self.client

        def close_client(*_args: object) -> bool:
            self.client.close()
            return False

        self.client.__exit__.side_effect = close_client

    def test_initializer_uses_hidden_git_and_ephemeral_full_access_without_turns(self) -> None:
        for effort in ("low", "medium", "high"):
            with self.subTest(reasoning_effort=effort):
                self.client.reset_mock()
                self.client.start_thread.return_value = SimpleNamespace(
                    model="arbitrary-configured-model", reasoning_effort=effort
                )
                with (
                    patch("subprocess.run") as run,
                    patch(
                        "codex_app_server_client.AppServerClient",
                        return_value=self.client,
                    ) as factory,
                ):
                    preparation.initialize_codex_project(self.project)
                run.assert_called_once()
                command = run.call_args.args[0]
                options = run.call_args.kwargs
                self.assertIsInstance(command, (list, tuple))
                self.assertIn("init", command)
                self.assertTrue(
                    str(self.project) in command
                    or Path(options.get("cwd", ".")) == self.project
                )
                self.assertIs(options.get("check"), True)
                self.assertFalse(options.get("shell", False))
                if os.name == "nt":
                    self.assertTrue(
                        options.get("creationflags", 0) & subprocess.CREATE_NO_WINDOW
                    )
                factory.assert_called_once_with(cwd=self.project)
                self.client.start_thread.assert_called_once_with(
                    ephemeral=True,
                    sandbox="danger-full-access",
                    approval_policy="never",
                )
                self.client.start_turn.assert_not_called()
                self.client.close.assert_called_once()

    def test_initializer_rejects_excessive_reasoning_effort_and_closes_client(self) -> None:
        self.client.start_thread.return_value = SimpleNamespace(
            model="arbitrary-configured-model", reasoning_effort="xhigh"
        )
        with (
            patch("subprocess.run"),
            patch("codex_app_server_client.AppServerClient", return_value=self.client),
            self.assertRaises(REJECTION_ERRORS),
        ):
            preparation.initialize_codex_project(self.project)
        self.client.start_turn.assert_not_called()
        self.client.close.assert_called_once()

    def test_thread_initialization_failure_closes_client_without_starting_turn(self) -> None:
        self.client.start_thread.side_effect = RuntimeError("synthetic thread failure")
        with (
            patch("subprocess.run"),
            patch("codex_app_server_client.AppServerClient", return_value=self.client),
            self.assertRaisesRegex(RuntimeError, "synthetic thread failure"),
        ):
            preparation.initialize_codex_project(self.project)
        self.client.start_turn.assert_not_called()
        self.client.close.assert_called_once()


class AcceptancePreparationHarnessContractTests(unittest.TestCase):
    def test_all_real_case_entries_resolve_prepared_identity_before_subprocess(self) -> None:
        methods = {
            "control-plane": "test_planning_and_per_turn_execution_control_planes",
            "hard-crash": (
                "test_hard_crash_cleans_exact_session_and_terminates_original_run"
            ),
            "registration-crash": (
                "test_registration_intent_recovers_both_real_pre_checkpoint_crashes"
            ),
        }
        for case, method_name in methods.items():
            with self.subTest(case=case):
                test_case = real_acceptance.TracedAppServerRealIntegrationTests(
                    method_name
                )
                with (
                    patch.object(
                        real_acceptance,
                        "resolve_acceptance_fixture",
                        side_effect=RuntimeError("synthetic fixture binding rejected"),
                        create=True,
                    ) as resolve,
                    patch.object(
                        real_acceptance.subprocess,
                        "run",
                        side_effect=AssertionError("subprocess started before binding"),
                    ) as run,
                    self.assertRaisesRegex(RuntimeError, "synthetic fixture binding"),
                ):
                    getattr(test_case, method_name)()
                resolve.assert_called_once_with(case)
                run.assert_not_called()

    def test_report_source_binding_includes_preparation_helper_bytes(self) -> None:
        relative_path = "test/acceptance_preparation.py"
        sources = real_acceptance._source_sha256(
            "test/test_traced_app_server_real_integration.py"
        )
        self.assertIn(relative_path, sources)
        self.assertEqual(
            sources[relative_path],
            hashlib.sha256((PROJECT_ROOT / relative_path).read_bytes()).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
