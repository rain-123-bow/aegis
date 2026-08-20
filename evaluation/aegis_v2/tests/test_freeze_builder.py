from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import jsonschema
import rfc8785
from referencing import Registry, Resource


MODULE_PATH = Path(__file__).resolve().parents[1] / "freeze_builder.py"
SPEC = importlib.util.spec_from_file_location("aegis_v2_freeze_builder", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
freeze_builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(freeze_builder)


EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
PRODUCER = {
    "thread_id": "producer-thread",
    "session_id": "producer-session",
    "turn_id": "producer-turn",
}
DISPOSITION_REVIEWER = {
    "reviewer_thread_id": "disposition-thread",
    "reviewer_session_id": "disposition-session",
    "reviewer_turn_id": "disposition-turn",
}
FINAL_LOCATOR = {
    "capture_source": "PREAUTHORIZED_APPEND_ONLY_CODEX_EVENT_SOURCE",
    "authority_source_id": "test-only-authority-source",
    "authority_policy_id": "test-only-authority-policy",
    "authority_event_id": "test-only-authority-event",
    "authority_event_sequence": 42,
    "authority_committed_at_utc": "2026-07-27T09:02:03Z",
    "codex_cli_version": "0.145.0",
    "codex_app_server_protocol_semantic_sha256": (
        "sha256:1bc09dedc506075562d4d49b702ecab6d947dd5a8c2a9014a5cde592a0938efb"
    ),
    "reviewer_task_path": "/root/phase0a_contract_reviewer",
    "parent_thread_id": PRODUCER["thread_id"],
    "parent_spawn_tool_call_id": "parent-spawn-tool-call",
    "parent_delivery_tool_call_id": "parent-delivery-tool-call",
    "reviewer_thread_id": "final-thread",
    "reviewer_session_id": "final-session",
    "reviewer_turn_id": "final-turn",
    "reviewer_item_id": "final-item",
    "reviewer_turn_started_at_unix_seconds": 1785142910,
    "reviewer_turn_completed_at_unix_seconds": 1785142922,
    "reviewer_item_started_at_unix_ms": 1785142918000,
    "reviewer_item_completed_at_unix_ms": 1785142921000,
    "reviewer_turn_status": "completed",
    "reviewer_item_type": "agentMessage",
    "reviewer_item_phase": "final_answer",
    "delivery_kind": "AGENT_MESSAGE_FINAL_ANSWER",
}


class SyntheticAuthorityReader:
    """Internal test seam; never represents a production authority source."""

    def __init__(self, expected_raw: bytes) -> None:
        self.expected_raw = expected_raw

    def __call__(self, locator: dict[str, object]) -> bytes:
        del locator
        return self.expected_raw


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed ({result.returncode}): "
            f"{result.stderr.decode('utf-8', 'replace')}"
        )
    return result


class TemporaryRepository:
    def __init__(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary_directory.name).resolve()
        run_git(self.root, "init", "--initial-branch=main")
        run_git(self.root, "config", "user.name", "Freeze Test")
        run_git(self.root, "config", "user.email", "freeze@example.invalid")

        self.write(".gitignore", b"*.cache\n")
        self.write(".gitattributes", b"* text=auto\n*.json text eol=lf\n")
        self.write(
            "docs/aegis_v2_requirements.md",
            b"# Requirements\n\nFrozen before implementation.\n",
        )
        self.write(
            "docs/aegis_v2_upgrade_plan.md",
            b"# Plan\n\nFrozen before implementation.\n",
        )
        self.write(
            "docs/aegis_v2_codex_static_evidence.md",
            b"# Static evidence\n\nNo live capability claim.\n",
        )
        self.write(
            "docs/aegis_v2_phase0_contract.md",
            b"# Phase 0A contract\n\nNormative test contract.\n",
        )
        self.write(
            "docs/decisions/0001-aegis-v2-dual-plane.md",
            b"# ADR 0001\n\nDual-plane architecture.\n",
        )
        self.write(
            "pyproject.toml",
            b"[project]\nname = \"freeze-test\"\nversion = \"0.0.0\"\n",
        )
        self.write(
            "pylock.windows-py313.toml",
            b"lock-version = \"1.0\"\n",
        )
        schema_path = "schemas/aegis/v2/sample.schema.json"
        second_schema_path = "schemas/aegis/v2/second.schema.json"
        self.write_json(
            schema_path,
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://example.invalid/sample.schema.json",
                "type": "object",
            },
        )
        self.write_json(
            second_schema_path,
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://example.invalid/second.schema.json",
                "type": "array",
            },
        )
        self.write_json(
            "schemas/aegis/v2/schema_bundle.v1.json",
            {
                "schemas": [
                    {
                        "path": schema_path,
                    },
                    {
                        "path": second_schema_path,
                    },
                ],
            },
        )
        self.write_json(
            "evaluation/aegis_v2/evaluation_manifest.v1.json",
            {
                "parent_manifest_hash": None,
                "parent_manifest_locator": None,
            },
        )
        fixture_path = "evaluation/aegis_v2/fixtures/sample/input.txt"
        second_fixture_path = (
            "evaluation/aegis_v2/fixtures/sample/second.txt"
        )
        self.write(fixture_path, b"frozen fixture\n")
        self.write(second_fixture_path, b"second frozen fixture\n")
        self.write_json(
            "evaluation/aegis_v2/fixture_catalog.v1.json",
            {
                "fixtures": [
                    {
                        "repository_path": fixture_path,
                    },
                    {
                        "repository_path": second_fixture_path,
                    },
                ],
            },
        )
        self.write_json(
            "evaluation/aegis_v2/risk_register.v1.json",
            {"entries": []},
        )
        source_paths = sorted(
            freeze_builder._REQUIRED_REFERENCE_SOURCE_PATHS
        )
        assurance_paths = sorted(
            freeze_builder._REQUIRED_REFERENCE_ASSURANCE_PATHS
        )
        for path in source_paths:
            self.write(path, b"# frozen reference source\n")
        for path in assurance_paths:
            self.write(path, b"# frozen assurance source\n")
        self.write_json(
            "evaluation/aegis_v2/reference/source_manifest.v1.json",
            {
                "source_files": [
                    {"repository_path": path}
                    for path in source_paths
                ],
                "assurance_files": [
                    {"repository_path": path}
                    for path in assurance_paths
                ],
            },
        )
        self.write(
            "review/disposition.md",
            b"# Outside-domain disposition\n\nIndependent fixture review.\n",
        )
        self.write(
            "review/final.md",
            b"# Phase 0A review\n\n## Final\n\nPASS\n\nOpen blockers: 0\n",
        )
        self.write("README.md", b"# Legacy repository\n")
        self.write("tracked_modified.txt", b"base modified bytes\n")
        self.write("tracked_deleted.txt", b"base deleted bytes\n")
        self.write(
            "src/legacy.py",
            b"def legacy_value():\n    return 'pre-v2'\n",
        )
        run_git(self.root, "add", "--all")
        run_git(self.root, "commit", "-m", "base")

        self.write("tracked_modified.txt", b"worktree modified bytes\n")
        (self.root / "tracked_deleted.txt").unlink()
        self.write("untracked.txt", b"untracked exact bytes\n")
        self.write("ignored.cache", b"must not enter the inventory\n")

    def close(self) -> None:
        self._temporary_directory.cleanup()

    def write(self, relative_path: str, raw: bytes) -> None:
        destination = self.root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)

    def write_json(self, relative_path: str, value: object) -> None:
        self.write(
            relative_path,
            json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8")
            + b"\n",
        )

    @property
    def allowed_domain(self) -> list[str]:
        return list(
            freeze_builder._derive_required_phase0a_repository_inputs(
                self.root
            )
        )

    @property
    def freeze_input_specs(self) -> list[dict[str, object]]:
        required = (
            freeze_builder._derive_required_phase0a_repository_inputs(
                self.root
            )
        )
        return [
            {
                "logical_path": f"repo:/{path}",
                "locator": {
                    "kind": "REPOSITORY",
                    "repository_path": path,
                },
                "artifact_kind": artifact_kind,
                "byte_domain": byte_domain,
            }
            for path, (artifact_kind, byte_domain) in required.items()
        ]

    def outside_dispositions(self) -> dict[str, dict[str, object]]:
        base_equal = {
            ".gitignore",
            "README.md",
            "review/disposition.md",
            "review/final.md",
            "src/legacy.py",
        }
        paths = base_equal | {
            "tracked_modified.txt",
            "tracked_deleted.txt",
            "untracked.txt",
        }
        result: dict[str, dict[str, object]] = {}
        for path in paths:
            result[path] = {
                "disposition": (
                    "BASE_EQUAL" if path in base_equal else "PREEXISTING_NON_V2"
                ),
                "executable_v2_classification": "NOT_V2_IMPLEMENTATION",
                "rationale": f"{path} predates and does not implement Aegis v2.",
                **DISPOSITION_REVIEWER,
                "disposition_artifact_locator": {
                    "kind": "REPOSITORY",
                    "repository_path": "review/disposition.md",
                },
            }
        return result

    def build_candidate(self, **overrides: object) -> dict[str, object]:
        arguments: dict[str, object] = {
            "repo_root": self.root,
            "freeze_input_specs": self.freeze_input_specs,
            "allowed_phase0a_file_domain": self.allowed_domain,
            "outside_domain_dispositions": self.outside_dispositions(),
            "freeze_producer_identity": PRODUCER,
            "freeze_time_utc": "2026-07-27T09:00:00Z",
            "proof_event_id": "019fa1ff-8282-7abc-89ba-fc8739ed8bf1",
            "proven_at_utc": "2026-07-27T09:01:00Z",
            "freeze_base_ref": "HEAD",
        }
        arguments.update(overrides)
        return freeze_builder.build_freeze_candidate(**arguments)

    def final_event(
        self,
        candidate: dict[str, object],
        **overrides: object,
    ) -> dict[str, object]:
        review_bytes = (self.root / "review/final.md").read_bytes()
        event: dict[str, object] = {
            "schema_version": "Phase0ReviewFinalEvent.v1",
            "authority_locator": copy.deepcopy(FINAL_LOCATOR),
            "freeze_root_id": candidate["freeze_root_id"],
            "code_absence_proof_id": candidate["code_absence_proof"][
                "code_absence_proof_id"
            ],
            "review_artifact": {
                "logical_path": "repo:/review/final.md",
                "locator": {
                    "kind": "REPOSITORY",
                    "repository_path": "review/final.md",
                },
                "byte_size": len(review_bytes),
                "raw_sha256": hashlib.sha256(review_bytes).hexdigest(),
            },
            "verdict": "PASS",
            "open_blocker_ids": [],
            "reviewed_at_utc": "2026-07-27T09:02:00Z",
        }
        event.update(overrides)
        return event


class FreezeBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = TemporaryRepository()
        self.reviewer_event_path = self.repository.root.with_name(
            self.repository.root.name + "-reviewer-final-event.json"
        )
        self.addCleanup(self.reviewer_event_path.unlink, missing_ok=True)

    def tearDown(self) -> None:
        self.repository.close()

    def test_candidate_captures_complete_inventory_and_cas_without_staging(self) -> None:
        candidate = self.repository.build_candidate()
        proof = candidate["code_absence_proof"]
        inventory = proof["worktree_inventory"]

        expected_paths = sorted(
            set(self.repository.allowed_domain)
            | {
                ".gitignore",
                "README.md",
                "review/disposition.md",
                "review/final.md",
                "src/legacy.py",
                "tracked_deleted.txt",
                "tracked_modified.txt",
                "untracked.txt",
            }
        )
        self.assertEqual(
            [entry["repository_relative_path"] for entry in inventory],
            expected_paths,
        )
        self.assertNotIn("ignored.cache", expected_paths)
        self.assertEqual(
            proof["tracked_entry_count"],
            len(expected_paths) - 1,
        )
        self.assertEqual(proof["nonignored_untracked_entry_count"], 1)

        by_path = {
            entry["repository_relative_path"]: entry for entry in inventory
        }
        self.assertEqual(
            by_path["tracked_modified.txt"]["entry_kind"],
            "TRACKED_MODIFIED",
        )
        self.assertEqual(
            by_path["tracked_deleted.txt"]["entry_kind"],
            "TRACKED_DELETED",
        )
        self.assertEqual(
            by_path["untracked.txt"]["entry_kind"],
            "UNTRACKED_NONIGNORED",
        )
        self.assertIsNone(by_path["tracked_deleted.txt"]["worktree_bytes"])
        self.assertIsNone(by_path["untracked.txt"]["base_bytes"])

        for entry in inventory:
            frozen = entry["worktree_bytes"]
            if frozen is None:
                continue
            self.assertEqual(frozen["source_kind"], "GIT_BLOB")
            blob = run_git(
                self.repository.root,
                "cat-file",
                "blob",
                frozen["git_blob_id"],
            ).stdout
            self.assertEqual(hashlib.sha256(blob).hexdigest(), frozen["raw_sha256"])
            self.assertEqual(len(blob), frozen["byte_size"])

        capture = proof["tracked_tree_capture"]
        self.assertEqual(
            capture["argv"],
            [
                "git",
                "ls-tree",
                "-rz",
                "--full-tree",
                candidate["freeze_base_commit"],
            ],
        )
        raw_capture = base64.b64decode(capture["raw_stdout_base64"], validate=True)
        self.assertEqual(len(raw_capture), capture["stdout_byte_size"])
        self.assertEqual(
            hashlib.sha256(raw_capture).hexdigest(),
            capture["stdout_sha256"],
        )
        self.assertEqual(capture["stderr_sha256"], EMPTY_SHA256)
        self.assertEqual(
            run_git(self.repository.root, "diff", "--cached", "--name-only").stdout,
            b"",
        )
        freeze_builder.verify_freeze_candidate(
            candidate,
            repo_root=self.repository.root,
        )

    def test_freeze_inputs_bind_raw_and_semantic_json_domains_and_sort(self) -> None:
        candidate = self.repository.build_candidate(
            freeze_input_specs=list(reversed(self.repository.freeze_input_specs))
        )
        leaves = candidate["freeze_inputs"]
        self.assertEqual(
            [leaf["logical_path"] for leaf in leaves],
            sorted(leaf["logical_path"] for leaf in leaves),
        )
        schema_leaf = next(
            leaf
            for leaf in leaves
            if leaf["logical_path"]
            == "repo:/schemas/aegis/v2/sample.schema.json"
        )
        raw = (
            self.repository.root
            / "schemas"
            / "aegis"
            / "v2"
            / "sample.schema.json"
        ).read_bytes()
        parsed = json.loads(raw)
        self.assertEqual(schema_leaf["byte_size"], len(raw))
        self.assertEqual(
            schema_leaf["raw_sha256"],
            hashlib.sha256(raw).hexdigest(),
        )
        self.assertEqual(
            schema_leaf["semantic_jcs_sha256"],
            hashlib.sha256(rfc8785.dumps(parsed)).hexdigest(),
        )
        leaf_preimage = dict(schema_leaf)
        del leaf_preimage["leaf_sha256"]
        self.assertEqual(
            schema_leaf["leaf_sha256"],
            hashlib.sha256(rfc8785.dumps(leaf_preimage)).hexdigest(),
        )
        root_preimage = [
            {
                "logical_path": leaf["logical_path"],
                "leaf_sha256": leaf["leaf_sha256"],
            }
            for leaf in leaves
        ]
        self.assertEqual(
            candidate["freeze_root_id"],
            "sha256:" + hashlib.sha256(rfc8785.dumps(root_preimage)).hexdigest(),
        )

    def test_exact_domain_rejects_globs_missing_leaf_and_missing_disposition(self) -> None:
        with self.subTest("glob"):
            domain = [*self.repository.allowed_domain, "schemas/**/*.json"]
            with self.assertRaisesRegex(freeze_builder.FreezeError, "glob"):
                self.repository.build_candidate(
                    allowed_phase0a_file_domain=domain
                )

        with self.subTest("allowed path without leaf"):
            domain = sorted([*self.repository.allowed_domain, "README.md"])
            with self.assertRaisesRegex(
                freeze_builder.FreezeError,
                "freeze input|normative Phase 0A",
            ):
                self.repository.build_candidate(
                    allowed_phase0a_file_domain=domain
                )

        with self.subTest("outside-domain omission"):
            dispositions = self.repository.outside_dispositions()
            del dispositions["untracked.txt"]
            with self.assertRaisesRegex(freeze_builder.FreezeError, "complement"):
                self.repository.build_candidate(
                    outside_domain_dispositions=dispositions
                )

    def test_normative_domain_cannot_be_shrunk_and_reclassified_as_outside(
        self,
    ) -> None:
        specs = [
            spec
            for spec in self.repository.freeze_input_specs
            if spec["locator"].get("repository_path")
            != "docs/aegis_v2_requirements.md"
        ]
        domain = [
            path
            for path in self.repository.allowed_domain
            if path != "docs/aegis_v2_requirements.md"
        ]
        dispositions = self.repository.outside_dispositions()
        dispositions["docs/aegis_v2_requirements.md"] = {
            "disposition": "BASE_EQUAL",
            "executable_v2_classification": "NOT_V2_IMPLEMENTATION",
            "rationale": "A required plan cannot be reclassified outside the root.",
            **DISPOSITION_REVIEWER,
            "disposition_artifact_locator": {
                "kind": "REPOSITORY",
                "repository_path": "review/disposition.md",
            },
        }

        with self.assertRaisesRegex(
            freeze_builder.FreezeError,
            "normative Phase 0A repository domain",
        ):
            self.repository.build_candidate(
                freeze_input_specs=specs,
                allowed_phase0a_file_domain=domain,
                outside_domain_dispositions=dispositions,
            )

    def test_schema_bundle_cannot_hide_an_existing_schema_as_outside(
        self,
    ) -> None:
        hidden = "schemas/aegis/v2/second.schema.json"
        self.repository.write_json(
            "schemas/aegis/v2/schema_bundle.v1.json",
            {
                "schemas": [
                    {
                        "path": "schemas/aegis/v2/sample.schema.json",
                    }
                ],
            },
        )
        dispositions = self.repository.outside_dispositions()
        dispositions[hidden] = {
            "disposition": "BASE_EQUAL",
            "executable_v2_classification": "NOT_V2_IMPLEMENTATION",
            "rationale": "An existing versioned schema cannot leave the root.",
            **DISPOSITION_REVIEWER,
            "disposition_artifact_locator": {
                "kind": "REPOSITORY",
                "repository_path": "review/disposition.md",
            },
        }

        with self.assertRaisesRegex(
            freeze_builder.FreezeError,
            "schema.*closure|schema.*membership",
        ):
            self.repository.build_candidate(
                outside_domain_dispositions=dispositions,
            )

    def test_fixture_catalog_cannot_hide_an_existing_fixture_as_outside(
        self,
    ) -> None:
        hidden = "evaluation/aegis_v2/fixtures/sample/second.txt"
        self.repository.write_json(
            "evaluation/aegis_v2/fixture_catalog.v1.json",
            {
                "fixtures": [
                    {
                        "repository_path": (
                            "evaluation/aegis_v2/fixtures/sample/input.txt"
                        ),
                    }
                ],
            },
        )
        dispositions = self.repository.outside_dispositions()
        dispositions[hidden] = {
            "disposition": "BASE_EQUAL",
            "executable_v2_classification": "NOT_V2_IMPLEMENTATION",
            "rationale": "An existing fixture cannot leave the root.",
            **DISPOSITION_REVIEWER,
            "disposition_artifact_locator": {
                "kind": "REPOSITORY",
                "repository_path": "review/disposition.md",
            },
        }

        with self.assertRaisesRegex(
            freeze_builder.FreezeError,
            "fixture.*closure|fixture.*membership",
        ):
            self.repository.build_candidate(
                outside_domain_dispositions=dispositions,
            )

    def test_manifest_head_cannot_hide_existing_parent_cas_as_outside(
        self,
    ) -> None:
        parent_hash = "sha256:" + "a" * 64
        parent_path = (
            "evaluation/aegis_v2/manifests/sha256/"
            + "a" * 64
            + ".json"
        )
        self.repository.write_json(
            parent_path,
            {
                "parent_manifest_hash": None,
                "parent_manifest_locator": None,
            },
        )
        self.repository.write_json(
            "evaluation/aegis_v2/evaluation_manifest.v1.json",
            {
                "parent_manifest_hash": parent_hash,
                "parent_manifest_locator": {
                    "declared_manifest_sha256": parent_hash,
                    "repository_path": parent_path,
                },
            },
        )
        run_git(
            self.repository.root,
            "add",
            parent_path,
            "evaluation/aegis_v2/evaluation_manifest.v1.json",
        )
        run_git(self.repository.root, "commit", "-m", "add manifest parent")
        self.repository.write_json(
            "evaluation/aegis_v2/evaluation_manifest.v1.json",
            {
                "parent_manifest_hash": None,
                "parent_manifest_locator": None,
            },
        )
        dispositions = self.repository.outside_dispositions()
        dispositions[parent_path] = {
            "disposition": "BASE_EQUAL",
            "executable_v2_classification": "NOT_V2_IMPLEMENTATION",
            "rationale": "A reachable parent CAS cannot leave the root.",
            **DISPOSITION_REVIEWER,
            "disposition_artifact_locator": {
                "kind": "REPOSITORY",
                "repository_path": "review/disposition.md",
            },
        }

        with self.assertRaisesRegex(
            freeze_builder.FreezeError,
            "parent manifest.*closure|parent manifest.*membership",
        ):
            self.repository.build_candidate(
                outside_domain_dispositions=dispositions,
            )

    def test_rejects_crlf_bom_and_duplicate_json_members(self) -> None:
        malformed = {
            "CRLF": b"# Plan\r\n\r\nNot canonical.\r\n",
            "BOM": b"\xef\xbb\xbf# Plan\n",
        }
        for name, raw in malformed.items():
            with self.subTest(name):
                self.repository.write("docs/aegis_v2_upgrade_plan.md", raw)
                with self.assertRaises(freeze_builder.FreezeError):
                    self.repository.build_candidate()
                self.repository.write(
                    "docs/aegis_v2_upgrade_plan.md",
                    b"# Plan\n\nFrozen before implementation.\n",
                )

        self.repository.write(
            "schemas/aegis/v2/sample.schema.json",
            b'{"same":1,"same":2}\n',
        )
        with self.assertRaisesRegex(freeze_builder.FreezeError, "duplicate"):
            self.repository.build_candidate()

    def test_external_leaf_requires_verified_acquisition_evidence(self) -> None:
        external_path = self.repository.root.with_name(
            self.repository.root.name + "-reference.py"
        )
        external_raw = b"def independent_oracle(value):\n    return bool(value)\n"
        external_path.write_bytes(external_raw)
        self.addCleanup(lambda: external_path.unlink(missing_ok=True))
        external_spec = {
            "logical_path": "external:/reference/oracle.py",
            "locator": {
                "kind": "EXTERNAL_ACQUISITION",
                "absolute_path": str(external_path),
                "acquisition_evidence_id": "sha256:" + "a" * 64,
                "acquisition_event_id": "019fa1ff-8282-7abc-89ba-fc8739ed8bf2",
            },
            "artifact_kind": "EVALUATION_REFERENCE_SOURCE",
            "byte_domain": "GIT_BLOB_BYTES",
        }
        specs = [*self.repository.freeze_input_specs, external_spec]
        with self.assertRaisesRegex(
            freeze_builder.FreezeError,
            "external acquisition verifier",
        ):
            self.repository.build_candidate(freeze_input_specs=specs)

        verified_locators: list[dict[str, object]] = []

        def verify_external(
            locator: dict[str, object],
            raw: bytes,
        ) -> bool:
            verified_locators.append(locator)
            return (
                locator["absolute_path"] == str(external_path)
                and raw == external_raw
            )

        candidate = self.repository.build_candidate(
            freeze_input_specs=specs,
            external_acquisition_verifier=verify_external,
        )
        external_leaf = next(
            leaf
            for leaf in candidate["freeze_inputs"]
            if leaf["logical_path"] == "external:/reference/oracle.py"
        )
        self.assertEqual(external_leaf["raw_sha256"], hashlib.sha256(external_raw).hexdigest())
        self.assertGreaterEqual(len(verified_locators), 2)

    def test_staged_state_is_rejected_instead_of_falling_out_of_inventory(self) -> None:
        run_git(self.repository.root, "add", "tracked_modified.txt")
        with self.assertRaisesRegex(freeze_builder.FreezeError, "index differs"):
            self.repository.build_candidate()

    def test_outside_disposition_same_agent_different_turn_is_not_independent(
        self,
    ) -> None:
        dispositions = self.repository.outside_dispositions()
        dispositions["README.md"] = {
            **dispositions["README.md"],
            "reviewer_thread_id": PRODUCER["thread_id"],
            "reviewer_session_id": PRODUCER["session_id"],
            "reviewer_turn_id": "a-different-turn",
        }
        with self.assertRaisesRegex(freeze_builder.FreezeError, "independent"):
            self.repository.build_candidate(
                outside_domain_dispositions=dispositions
            )

    def test_content_scan_ignores_a_filename_but_rejects_hidden_implementation(self) -> None:
        self.repository.write("kernel.py", b"def add(left, right):\n    return left + right\n")
        dispositions = self.repository.outside_dispositions()
        dispositions["kernel.py"] = {
            "disposition": "PREEXISTING_NON_V2",
            "executable_v2_classification": "NOT_V2_IMPLEMENTATION",
            "rationale": "The filename is not evidence of a v2 implementation.",
            **DISPOSITION_REVIEWER,
            "disposition_artifact_locator": {
                "kind": "REPOSITORY",
                "repository_path": "review/disposition.md",
            },
        }
        candidate = self.repository.build_candidate(
            outside_domain_dispositions=dispositions
        )
        self.assertIn(
            "kernel.py",
            {
                item["repository_relative_path"]
                for item in candidate["code_absence_proof"]["worktree_inventory"]
            },
        )

        self.repository.write(
            "ordinary_name.py",
            (
                b"from langgraph.graph import StateGraph\n"
                b"class AegisV2Kernel:\n"
                b"    def build(self, state):\n"
                b"        return StateGraph(state).compile()\n"
            ),
        )
        dispositions["ordinary_name.py"] = {
            "disposition": "PREEXISTING_NON_V2",
            "executable_v2_classification": "NOT_V2_IMPLEMENTATION",
            "rationale": "This false assertion must not bypass content scanning.",
            **DISPOSITION_REVIEWER,
            "disposition_artifact_locator": {
                "kind": "REPOSITORY",
                "repository_path": "review/disposition.md",
            },
        }
        with self.assertRaisesRegex(
            freeze_builder.ProhibitedImplementationError,
            "AEGIS_V2_KERNEL|EQUIVALENT_EXECUTABLE_IMPLEMENTATION",
        ):
            self.repository.build_candidate(
                outside_domain_dispositions=dispositions
            )

    def test_candidate_verification_rejects_object_and_worktree_tampering(self) -> None:
        candidate = self.repository.build_candidate()
        tampered = copy.deepcopy(candidate)
        tampered["freeze_inputs"][0]["raw_sha256"] = "0" * 64
        with self.assertRaises(freeze_builder.FreezeError):
            freeze_builder.verify_freeze_candidate(
                tampered,
                repo_root=self.repository.root,
            )

        self.repository.write(
            "schemas/aegis/v2/sample.schema.json",
            b'{"answer":43,"name":"aegis"}\n',
        )
        with self.assertRaisesRegex(freeze_builder.FreezeError, "changed|mismatch"):
            freeze_builder.verify_freeze_candidate(
                candidate,
                repo_root=self.repository.root,
            )

    def test_finalize_consumes_exact_reviewer_event_and_validates_record(self) -> None:
        candidate = self.repository.build_candidate()
        event = self.repository.final_event(candidate)
        event_path = self.reviewer_event_path
        event_path.write_bytes(rfc8785.dumps(event))

        with self.assertRaisesRegex(
            freeze_builder.FreezeError,
            "AUTHORITY_UNVERIFIED",
        ):
            freeze_builder.finalize_freeze_record(
                candidate,
                repo_root=self.repository.root,
                reviewer_final_event_path=event_path,
                recorded_at_utc="2026-07-27T09:03:00Z",
            )
        reader = SyntheticAuthorityReader(event_path.read_bytes())
        record = (
            freeze_builder._finalize_freeze_record_with_test_authority_reader(
                candidate,
                repo_root=self.repository.root,
                reviewer_final_event_path=event_path,
                recorded_at_utc="2026-07-27T09:03:00Z",
                authority_event_reader=reader,
            )
        )
        self.assertEqual(record["freeze_state"], "TEST_ONLY_STRUCTURAL_RECORD")
        self.assertEqual(
            base64.b64decode(
                record["authority_anchor"]["anchor_event_raw_base64"],
                validate=True,
            ),
            event_path.read_bytes(),
        )
        self.assertEqual(
            record["review_anchor"]["reviewed_freeze_root_id"],
            candidate["freeze_root_id"],
        )
        self.assertEqual(record["freeze_producer_identity"], PRODUCER)
        preimage = dict(record)
        del preimage["freeze_record_id"]
        self.assertEqual(
            record["freeze_record_id"],
            "sha256:" + hashlib.sha256(rfc8785.dumps(preimage)).hexdigest(),
        )
        with self.assertRaisesRegex(
            freeze_builder.FreezeError,
            "AUTHORITY_UNVERIFIED",
        ):
            freeze_builder.verify_freeze_record(
                record,
                repo_root=self.repository.root,
            )
        freeze_builder._verify_freeze_record_with_test_authority_reader(
            record,
            repo_root=self.repository.root,
            authority_event_reader=reader,
        )
        with self.assertRaisesRegex(
            freeze_builder.FreezeError,
            "external freeze_producer_identity does not match",
        ):
            freeze_builder._verify_freeze_record_with_test_authority_reader(
                record,
                repo_root=self.repository.root,
                freeze_producer_identity={
                    **PRODUCER,
                    "turn_id": "different-turn",
                },
                authority_event_reader=reader,
            )

        schema_directory = MODULE_PATH.parents[2] / "schemas" / "aegis" / "v2"
        resources = []
        schemas = []
        for schema_path in sorted(schema_directory.glob("*.schema.json")):
            schema = json.loads(schema_path.read_bytes())
            schemas.append(schema)
            resources.append((schema["$id"], Resource.from_contents(schema)))
        registry = Registry().with_resources(resources)
        freeze_schema = next(
            schema
            for schema in schemas
            if schema["title"] == "Phase0FreezeRecord.v1"
        )
        validator = jsonschema.Draft202012Validator(
            freeze_schema,
            registry=registry,
            format_checker=jsonschema.FormatChecker(),
        )
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(record)

    def test_public_finalize_has_no_caller_authority_override(self) -> None:
        candidate = self.repository.build_candidate()
        event = self.repository.final_event(candidate)
        event_path = self.reviewer_event_path
        event_path.write_bytes(rfc8785.dumps(event))

        with self.assertRaisesRegex(TypeError, "authority_event_reader"):
            freeze_builder.finalize_freeze_record(
                candidate,
                repo_root=self.repository.root,
                reviewer_final_event_path=event_path,
                recorded_at_utc="2026-07-27T09:03:00Z",
                authority_event_reader=SyntheticAuthorityReader(
                    event_path.read_bytes()
                ),
            )

    def test_internal_authority_reader_rejects_boolean_verdict(self) -> None:
        candidate = self.repository.build_candidate()
        event = self.repository.final_event(candidate)
        event_path = self.reviewer_event_path
        event_path.write_bytes(rfc8785.dumps(event))

        with self.assertRaisesRegex(
            freeze_builder.FreezeError,
            "exact authoritative event bytes",
        ):
            freeze_builder._finalize_freeze_record_with_test_authority_reader(
                candidate,
                repo_root=self.repository.root,
                reviewer_final_event_path=event_path,
                recorded_at_utc="2026-07-27T09:03:00Z",
                authority_event_reader=lambda locator: True,
            )

    def test_internal_authority_reader_rejects_echo_mismatch(self) -> None:
        candidate = self.repository.build_candidate()
        event = self.repository.final_event(candidate)
        event_path = self.reviewer_event_path
        event_path.write_bytes(rfc8785.dumps(event))

        with self.assertRaisesRegex(
            freeze_builder.FreezeError,
            "do not match the exact event",
        ):
            freeze_builder._finalize_freeze_record_with_test_authority_reader(
                candidate,
                repo_root=self.repository.root,
                reviewer_final_event_path=event_path,
                recorded_at_utc="2026-07-27T09:03:00Z",
                authority_event_reader=SyntheticAuthorityReader(b"forged"),
            )

    def test_finalize_requires_complete_platform_event_locator(self) -> None:
        candidate = self.repository.build_candidate()
        required_fields = (
            "authority_source_id",
            "authority_policy_id",
            "authority_event_id",
            "authority_event_sequence",
            "authority_committed_at_utc",
            "codex_cli_version",
            "codex_app_server_protocol_semantic_sha256",
            "parent_spawn_tool_call_id",
            "parent_delivery_tool_call_id",
            "reviewer_item_id",
            "reviewer_turn_completed_at_unix_seconds",
            "reviewer_item_completed_at_unix_ms",
            "reviewer_turn_status",
            "reviewer_item_type",
            "reviewer_item_phase",
        )
        for field in required_fields:
            with self.subTest(field=field):
                locator = copy.deepcopy(FINAL_LOCATOR)
                del locator[field]
                event = self.repository.final_event(
                    candidate,
                    authority_locator=locator,
                )
                event_path = self.reviewer_event_path
                event_path.write_bytes(rfc8785.dumps(event))
                with self.assertRaisesRegex(
                    freeze_builder.FreezeError,
                    "keys mismatch",
                ):
                    freeze_builder._finalize_freeze_record_with_test_authority_reader(
                        candidate,
                        repo_root=self.repository.root,
                        reviewer_final_event_path=event_path,
                        recorded_at_utc="2026-07-27T09:03:00Z",
                        authority_event_reader=SyntheticAuthorityReader(
                            event_path.read_bytes()
                        ),
                    )

    def test_finalize_rejects_nonfinal_or_unordered_platform_locator(
        self,
    ) -> None:
        candidate = self.repository.build_candidate()
        mutations = (
            (
                "local app-server",
                {"capture_source": "CODEX_LOCAL_APP_SERVER_HISTORY"},
                "capture_source",
            ),
            (
                "commentary item",
                {"reviewer_item_phase": "commentary"},
                "reviewer_item_phase",
            ),
            (
                "wrong item type",
                {"reviewer_item_type": "reasoning"},
                "reviewer_item_type",
            ),
            (
                "unfinished turn",
                {"reviewer_turn_status": "inProgress"},
                "reviewer_turn_status",
            ),
            (
                "negative authority sequence",
                {"authority_event_sequence": -1},
                "authority_event_sequence",
            ),
            (
                "item completion before start",
                {"reviewer_item_completed_at_unix_ms": 1785142917000},
                "completion predates",
            ),
            (
                "authority commit before item completion",
                {"authority_committed_at_utc": "2026-07-27T09:02:00Z"},
                "authority commit predates",
            ),
        )
        for name, changes, expected in mutations:
            with self.subTest(name=name):
                locator = {**FINAL_LOCATOR, **changes}
                event = self.repository.final_event(
                    candidate,
                    authority_locator=locator,
                )
                event_path = self.reviewer_event_path
                event_path.write_bytes(rfc8785.dumps(event))
                with self.assertRaisesRegex(
                    freeze_builder.FreezeError,
                    expected,
                ):
                    freeze_builder._finalize_freeze_record_with_test_authority_reader(
                        candidate,
                        repo_root=self.repository.root,
                        reviewer_final_event_path=event_path,
                        recorded_at_utc="2026-07-27T09:03:00Z",
                        authority_event_reader=SyntheticAuthorityReader(
                            event_path.read_bytes()
                        ),
                    )

    def test_finalize_rejects_duplicate_noncanonical_mismatch_and_artifact_tamper(
        self,
    ) -> None:
        candidate = self.repository.build_candidate()
        event = self.repository.final_event(candidate)
        event_path = self.reviewer_event_path

        with self.subTest("duplicate event member"):
            canonical = rfc8785.dumps(event).decode("utf-8")
            duplicate = canonical.replace(
                '{"authority_locator":',
                '{"verdict":"PASS","authority_locator":',
                1,
            )
            event_path.write_text(duplicate, encoding="utf-8", newline="")
            with self.assertRaisesRegex(freeze_builder.FreezeError, "duplicate"):
                freeze_builder._finalize_freeze_record_with_test_authority_reader(
                    candidate,
                    repo_root=self.repository.root,
                    reviewer_final_event_path=event_path,
                    recorded_at_utc="2026-07-27T09:03:00Z",
                    authority_event_reader=SyntheticAuthorityReader(
                        event_path.read_bytes()
                    ),
                )

        with self.subTest("noncanonical event bytes"):
            event_path.write_bytes(json.dumps(event).encode("utf-8"))
            with self.assertRaisesRegex(freeze_builder.FreezeError, "canonical"):
                freeze_builder._finalize_freeze_record_with_test_authority_reader(
                    candidate,
                    repo_root=self.repository.root,
                    reviewer_final_event_path=event_path,
                    recorded_at_utc="2026-07-27T09:03:00Z",
                    authority_event_reader=SyntheticAuthorityReader(
                        event_path.read_bytes()
                    ),
                )

        with self.subTest("mismatched proof"):
            mismatched = self.repository.final_event(
                candidate,
                code_absence_proof_id="sha256:" + "0" * 64,
            )
            event_path.write_bytes(rfc8785.dumps(mismatched))
            with self.assertRaisesRegex(freeze_builder.FreezeError, "proof"):
                freeze_builder._finalize_freeze_record_with_test_authority_reader(
                    candidate,
                    repo_root=self.repository.root,
                    reviewer_final_event_path=event_path,
                    recorded_at_utc="2026-07-27T09:03:00Z",
                    authority_event_reader=SyntheticAuthorityReader(
                        event_path.read_bytes()
                    ),
                )

        with self.subTest("review artifact changed after event"):
            event_path.write_bytes(rfc8785.dumps(event))
            self.repository.write("review/final.md", b"tampered\n")
            with self.assertRaisesRegex(
                freeze_builder.FreezeError,
                "review artifact|current worktree bytes changed",
            ):
                freeze_builder._finalize_freeze_record_with_test_authority_reader(
                    candidate,
                    repo_root=self.repository.root,
                    reviewer_final_event_path=event_path,
                    recorded_at_utc="2026-07-27T09:03:00Z",
                    authority_event_reader=SyntheticAuthorityReader(
                        event_path.read_bytes()
                    ),
                )

    def test_finalize_rejects_nonindependent_reviewer_identity(self) -> None:
        candidate = self.repository.build_candidate()
        event = self.repository.final_event(candidate)
        event["authority_locator"] = {
            **FINAL_LOCATOR,
            "reviewer_thread_id": PRODUCER["thread_id"],
            "reviewer_session_id": PRODUCER["session_id"],
            "reviewer_turn_id": "a-different-turn",
        }
        event_path = self.reviewer_event_path
        event_path.write_bytes(rfc8785.dumps(event))
        with self.assertRaisesRegex(freeze_builder.FreezeError, "independent"):
            freeze_builder._finalize_freeze_record_with_test_authority_reader(
                candidate,
                repo_root=self.repository.root,
                reviewer_final_event_path=event_path,
                recorded_at_utc="2026-07-27T09:03:00Z",
                authority_event_reader=SyntheticAuthorityReader(
                    event_path.read_bytes()
                ),
            )

    def test_finalize_rejects_reparse_in_original_event_path(self) -> None:
        candidate = self.repository.build_candidate()
        event = self.repository.final_event(candidate)
        event_path = self.reviewer_event_path
        event_path.write_bytes(rfc8785.dumps(event))

        with (
            mock.patch.object(
                freeze_builder,
                "_absolute_path_has_link_or_junction",
                return_value=True,
            ) as boundary,
            self.assertRaisesRegex(
                freeze_builder.FreezeError,
                "reparse|symlink|junction",
            ),
        ):
            freeze_builder._finalize_freeze_record_with_test_authority_reader(
                candidate,
                repo_root=self.repository.root,
                reviewer_final_event_path=event_path,
                recorded_at_utc="2026-07-27T09:03:00Z",
                authority_event_reader=SyntheticAuthorityReader(
                    event_path.read_bytes()
                ),
            )
        boundary.assert_called_once_with(event_path)

    def test_absolute_boundary_detects_generic_windows_reparse_bit(
        self,
    ) -> None:
        event_path = self.repository.root / "boundary-event.json"
        event_path.write_bytes(b"{}\n")
        original_lstat = freeze_builder.os.lstat

        def lstat_with_reparse(path, *args, **kwargs):
            metadata = original_lstat(path, *args, **kwargs)
            if Path(path) == self.repository.root:
                return mock.Mock(
                    st_mode=metadata.st_mode,
                    st_file_attributes=0x400,
                )
            return metadata

        with mock.patch.object(
            freeze_builder.os,
            "lstat",
            side_effect=lstat_with_reparse,
        ):
            self.assertTrue(
                freeze_builder._absolute_path_has_link_or_junction(
                    event_path
                )
            )


if __name__ == "__main__":
    unittest.main()
