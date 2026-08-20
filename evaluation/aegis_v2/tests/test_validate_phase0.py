from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import rfc8785


MODULE_PATH = Path(__file__).resolve().parents[1] / "validate_phase0.py"
SPEC = importlib.util.spec_from_file_location("aegis_v2_validate_phase0", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
validate_phase0 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_phase0)


def write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def with_self_hash(
    value: dict,
    field: str,
    *,
    prefixed: bool,
) -> dict:
    result = copy.deepcopy(value)
    result.pop(field, None)
    digest = hashlib.sha256(rfc8785.dumps(result)).hexdigest()
    result[field] = f"sha256:{digest}" if prefixed else digest
    return result


class StrictJsonTests(unittest.TestCase):
    def test_rejects_duplicate_member_bom_and_crlf(self) -> None:
        malformed = {
            "duplicate": b'{"same":1,"same":2}\n',
            "BOM": b"\xef\xbb\xbf{\"ok\":true}\n",
            "CRLF": b'{\r\n"ok":true\r\n}\r\n',
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for label, raw in malformed.items():
                with self.subTest(label):
                    path = root / f"{label}.json"
                    path.write_bytes(raw)
                    with self.assertRaises(validate_phase0.ValidationError):
                        validate_phase0.load_strict_json(path)

    def test_supersession_schema_requires_complete_provenance(self) -> None:
        schema_path = (
            MODULE_PATH.parents[2]
            / "schemas"
            / "aegis"
            / "v2"
            / "evaluation_manifest.v1.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        event = schema["$defs"]["supersessionEvent"]
        self.assertTrue(
            {
                "rationale",
                "parent_manifest_hash",
                "user_decision",
                "independent_review",
            }
            <= set(event["required"])
        )
        self.assertIn(
            "event",
            event["properties"]["independent_review"]["required"],
        )


class RepositoryPathBoundaryTests(unittest.TestCase):
    def test_noncanonical_repository_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "nested" / "fixture.json"
            write(target, b"{}\n")

            with self.assertRaisesRegex(
                validate_phase0.ValidationError,
                "non-canonical",
            ):
                validate_phase0._repository_path(
                    root,
                    "nested//fixture.json",
                    source="test fixture",
                )

    def test_intermediate_reparse_component_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "nested"
            nested.mkdir()
            target = nested / "fixture.json"
            target.write_text("{}\n", encoding="utf-8", newline="\n")
            original_lstat = validate_phase0.os.lstat

            def lstat_with_reparse(path):
                metadata = original_lstat(path)
                if Path(path) == nested:
                    return mock.Mock(
                        st_mode=metadata.st_mode,
                        st_file_attributes=0x400,
                    )
                return metadata

            with (
                mock.patch.object(
                    validate_phase0.os,
                    "lstat",
                    side_effect=lstat_with_reparse,
                ),
                self.assertRaisesRegex(
                    validate_phase0.ValidationError,
                    "reparse",
                ),
            ):
                validate_phase0._repository_path(
                    root,
                    "nested/fixture.json",
                    source="test fixture",
                )

    def test_schema_enumeration_rejects_reparse_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schema_directory = root / "schemas" / "aegis" / "v2"
            schema_directory.mkdir(parents=True)
            write(
                schema_directory / "sample.schema.json",
                (
                    b'{"$id":"https://example.invalid/sample.schema.json",'
                    b'"$schema":"https://json-schema.org/draft/2020-12/schema",'
                    b'"type":"object"}\n'
                ),
            )
            original_lstat = validate_phase0.os.lstat

            def lstat_with_reparse(path, *args, **kwargs):
                metadata = original_lstat(path, *args, **kwargs)
                if Path(path) == schema_directory:
                    return mock.Mock(
                        st_mode=metadata.st_mode,
                        st_file_attributes=0x400,
                    )
                return metadata

            with (
                mock.patch.object(
                    validate_phase0.os,
                    "lstat",
                    side_effect=lstat_with_reparse,
                ),
                self.assertRaisesRegex(
                    validate_phase0.ValidationError,
                    "reparse",
                ),
            ):
                validate_phase0._OfflineSchemas(root)

    def test_top_level_validator_rejects_reparse_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            manifest_path = (
                root
                / "evaluation"
                / "aegis_v2"
                / "evaluation_manifest.v1.json"
            )
            write(manifest_path, b"{}\n")
            original_lstat = validate_phase0.os.lstat

            def lstat_with_reparse(path, *args, **kwargs):
                metadata = original_lstat(path, *args, **kwargs)
                if Path(path) == manifest_path:
                    return mock.Mock(
                        st_mode=metadata.st_mode,
                        st_file_attributes=0x400,
                    )
                return metadata

            with (
                mock.patch.object(
                    validate_phase0,
                    "_OfflineSchemas",
                    return_value=mock.Mock(),
                ),
                mock.patch.object(
                    validate_phase0,
                    "_validate_schema_bundle",
                    return_value={},
                ),
                mock.patch.object(
                    validate_phase0,
                    "_validate_lock",
                    return_value={},
                ),
                mock.patch.object(
                    validate_phase0.os,
                    "lstat",
                    side_effect=lstat_with_reparse,
                ),
                self.assertRaisesRegex(
                    validate_phase0.ValidationError,
                    "reparse",
                ),
            ):
                validate_phase0.validate_repository(root)


class FreezeRepositoryDomainTests(unittest.TestCase):
    def test_final_record_domain_cannot_omit_required_repository_leaf(
        self,
    ) -> None:
        root = MODULE_PATH.parents[2]
        required = (
            validate_phase0._derive_required_phase0a_repository_inputs(
                root
            )
        )
        omitted = "docs/aegis_v2_requirements.md"
        leaves = [
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
            if path != omitted
        ]
        record = {
            "freeze_inputs": leaves,
            "code_absence_proof": {
                "allowed_phase0a_file_domain": [
                    path for path in required if path != omitted
                ],
            },
        }

        with self.assertRaisesRegex(
            validate_phase0.ValidationError,
            "normative Phase 0A repository domain.*aegis_v2_requirements",
        ):
            validate_phase0._validate_freeze_repository_domain(
                root,
                record,
            )

    def test_dynamic_directory_orphans_cannot_leave_final_record_domain(
        self,
    ) -> None:
        root = MODULE_PATH.parents[2]
        original = validate_phase0._repository_tree_files
        cases = (
            (
                "fixture",
                "evaluation/aegis_v2/fixtures",
                Path("evaluation/aegis_v2/fixtures/orphan.json"),
            ),
            (
                "parent manifest",
                "evaluation/aegis_v2/manifests/sha256",
                Path(
                    "evaluation/aegis_v2/manifests/sha256"
                )
                / ("f" * 64 + ".json"),
            ),
        )
        for label, target_directory, orphan_relative in cases:
            def with_orphan(
                repository_root: Path,
                relative_directory: str,
                *,
                source: str,
                optional: bool = False,
            ):
                paths = list(
                    original(
                        repository_root,
                        relative_directory,
                        source=source,
                        optional=optional,
                    )
                )
                if relative_directory == target_directory:
                    paths.append(repository_root / orphan_relative)
                return iter(paths)

            with (
                self.subTest(label=label),
                mock.patch.object(
                    validate_phase0,
                    "_repository_tree_files",
                    side_effect=with_orphan,
                ),
                self.assertRaisesRegex(
                    validate_phase0.ValidationError,
                    label.replace(" ", ".*") + ".*closure",
                ),
            ):
                validate_phase0._derive_required_phase0a_repository_inputs(
                    root
                )


class FailClosedMutationTests(unittest.TestCase):
    def test_self_hash_tamper_is_rejected(self) -> None:
        value = {
            "case_id": "CASE-1",
            "title": "original",
        }
        value["case_sha256"] = (
            "sha256:"
            + hashlib.sha256(rfc8785.dumps(value)).hexdigest()
        )
        validate_phase0._verify_self_hash(
            value,
            "case_sha256",
            source="temporary case",
            prefixed=True,
        )

        tampered = copy.deepcopy(value)
        tampered["title"] = "changed without rehash"
        with self.assertRaisesRegex(
            validate_phase0.ValidationError,
            "case_sha256.*mismatch",
        ):
            validate_phase0._verify_self_hash(
                tampered,
                "case_sha256",
                source="temporary case",
                prefixed=True,
            )

    def test_schema_bundle_omission_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schema_directory = root / "schemas" / "aegis" / "v2"
            schema_a = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://example.invalid/a.schema.json",
                "type": "object",
            }
            schema_b = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://example.invalid/b.schema.json",
                "type": "array",
            }
            write(
                schema_directory / "a.schema.json",
                json.dumps(schema_a, indent=2).encode() + b"\n",
            )
            write(
                schema_directory / "b.schema.json",
                json.dumps(schema_b, indent=2).encode() + b"\n",
            )
            raw_a = (schema_directory / "a.schema.json").read_bytes()
            bundle = {
                "schema_version": "SchemaBundle.v1",
                "bundle_id": "TEST-BUNDLE",
                "hash_contract": {
                    "algorithm": "SHA-256",
                    "canonicalization": "RFC8785-JCS",
                    "scope": "WHOLE_BUNDLE_WITH_BUNDLE_SHA256_OMITTED",
                    "schema_entry_byte_size_preimage": (
                        "EXACT_UTF8_LF_NO_BOM_BYTES"
                    ),
                    "schema_entry_sha256_preimage": "RFC8785_JCS_UTF8",
                },
                "resolution_policy": {},
                "codex_protocol_contract": {},
                "schemas": [
                    {
                        "path": "schemas/aegis/v2/a.schema.json",
                        "byte_size": len(raw_a),
                        "sha256": (
                            "sha256:"
                            + hashlib.sha256(rfc8785.dumps(schema_a)).hexdigest()
                        ),
                    }
                ],
                "bundle_sha256": "sha256:" + "0" * 64,
            }
            write(
                schema_directory / "schema_bundle.v1.json",
                json.dumps(bundle, indent=2).encode() + b"\n",
            )
            schemas = validate_phase0._OfflineSchemas(root)
            with self.assertRaisesRegex(
                validate_phase0.ValidationError,
                "schema bundle membership mismatch",
            ):
                validate_phase0._validate_schema_bundle(root, schemas)

    def test_schema_bundle_accepts_one_jcs_entry_preimage_domain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schema_directory = root / "schemas" / "aegis" / "v2"
            schemas_by_name = {
                "a.schema.json": {
                    "$schema": (
                        "https://json-schema.org/draft/2020-12/schema"
                    ),
                    "$id": "https://example.invalid/a.schema.json",
                    "type": "object",
                },
                "b.schema.json": {
                    "$schema": (
                        "https://json-schema.org/draft/2020-12/schema"
                    ),
                    "$id": "https://example.invalid/b.schema.json",
                    "type": "array",
                },
            }
            entries = []
            for filename, schema in schemas_by_name.items():
                write(
                    schema_directory / filename,
                    json.dumps(schema, indent=2).encode() + b"\n",
                )
                canonical = rfc8785.dumps(schema)
                entries.append(
                    {
                        "path": f"schemas/aegis/v2/{filename}",
                        "byte_size": len(canonical),
                        "sha256": (
                            "sha256:"
                            + hashlib.sha256(canonical).hexdigest()
                        ),
                    }
                )
            bundle = {
                "schema_version": "SchemaBundle.v1",
                "bundle_id": "TEST-BUNDLE",
                "hash_contract": {
                    "algorithm": "SHA-256",
                    "canonicalization": "RFC8785-JCS",
                    "scope": "WHOLE_BUNDLE_WITH_BUNDLE_SHA256_OMITTED",
                    "schema_entry_byte_size_preimage": "RFC8785_JCS_UTF8",
                    "schema_entry_sha256_preimage": "RFC8785_JCS_UTF8",
                },
                "resolution_policy": {},
                "codex_protocol_contract": {},
                "schemas": entries,
            }
            bundle["bundle_sha256"] = (
                "sha256:"
                + hashlib.sha256(rfc8785.dumps(bundle)).hexdigest()
            )
            write(
                schema_directory / "schema_bundle.v1.json",
                json.dumps(bundle, indent=2).encode() + b"\n",
            )

            schemas = validate_phase0._OfflineSchemas(root)
            observed = validate_phase0._validate_schema_bundle(
                root,
                schemas,
            )
            self.assertEqual(bundle, observed)

    def test_fixture_byte_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = b'{"answer":42}\n'
            digest = hashlib.sha256(raw).hexdigest()
            relative = (
                f"evaluation/aegis_v2/fixtures/{digest}/sample/input.json"
            )
            fixture_path = root / Path(*relative.split("/"))
            write(fixture_path, raw)
            fixture = {
                "repository_path": relative,
                "byte_size": len(raw),
                "raw_sha256": digest,
                "jcs_sha256": hashlib.sha256(
                    rfc8785.dumps({"answer": 42})
                ).hexdigest(),
                "media_type": "application/json",
            }
            validate_phase0._verify_fixture_preimage(
                root,
                "FIXTURE-1",
                fixture,
            )

            fixture_path.write_bytes(raw + b" ")
            with self.assertRaisesRegex(
                validate_phase0.ValidationError,
                "fixture FIXTURE-1 size mismatch",
            ):
                validate_phase0._verify_fixture_preimage(
                    root,
                    "FIXTURE-1",
                    fixture,
                )

    def test_json_fixture_with_null_jcs_may_contain_deliberate_invalid_json(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = b'{"truncated":'
            digest = hashlib.sha256(raw).hexdigest()
            relative = (
                f"evaluation/aegis_v2/fixtures/{digest}/sample/truncated.json"
            )
            write(root / Path(*relative.split("/")), raw)
            fixture = {
                "repository_path": relative,
                "byte_size": len(raw),
                "raw_sha256": digest,
                "jcs_sha256": None,
                "media_type": "application/json",
            }

            validate_phase0._verify_fixture_preimage(
                root,
                "FIXTURE-INVALID-JSON",
                fixture,
            )

    def test_fixture_logical_paths_reject_windows_casefold_collision(self) -> None:
        fixtures = {
            "FIXTURE-A": {
                "fixture_id": "FIXTURE-A",
                "repository_path": (
                    "evaluation/aegis_v2/fixtures/a/fixture-a.json"
                ),
                "logical_runtime_paths": [
                    "C:\\AegisRuntime\\Run\\Payload.json",
                ],
                "case_ids": ["EV-A"],
            },
            "FIXTURE-B": {
                "fixture_id": "FIXTURE-B",
                "repository_path": (
                    "evaluation/aegis_v2/fixtures/b/fixture-b.json"
                ),
                "logical_runtime_paths": [
                    "c:\\aegisruntime\\run\\payload.json",
                ],
                "case_ids": ["EV-B"],
            },
        }

        with self.assertRaisesRegex(
            validate_phase0.ValidationError,
            "case-insensitive logical runtime path collision",
        ):
            validate_phase0._validate_fixture_path_namespace(fixtures)

    def test_fixture_arrays_must_use_frozen_unicode_order(self) -> None:
        fixtures = {
            "FIXTURE-A": {
                "fixture_id": "FIXTURE-A",
                "repository_path": (
                    "evaluation/aegis_v2/fixtures/a/fixture-a.json"
                ),
                "logical_runtime_paths": [
                    "C:\\AegisRuntime\\z.json",
                    "C:\\AegisRuntime\\a.json",
                ],
                "case_ids": ["EV-Z", "EV-A"],
            },
        }

        with self.assertRaisesRegex(
            validate_phase0.ValidationError,
            "logical_runtime_paths must be Unicode-code-point sorted",
        ):
            validate_phase0._validate_fixture_path_namespace(fixtures)

    def test_reference_trace_fixture_cannot_enter_sut_fixture_mount(self) -> None:
        fixtures = {
            "TRACE-FIXTURE": {
                "artifact_kind": "REFERENCE_TRACE",
            },
        }
        case = {
            "case_id": "EV-TRACE-LEAK",
            "input": {
                "fixture_refs": ["TRACE-FIXTURE"],
            },
            "oracle": {
                "reference_trace_fixture_id": "TRACE-FIXTURE",
            },
        }

        with self.assertRaisesRegex(
            validate_phase0.ValidationError,
            "oracle-only fixture enters the SUT mount",
        ):
            validate_phase0._validate_fixture_visibility(
                [case],
                [],
                fixtures,
            )


class CrossArtifactRelationTests(unittest.TestCase):
    CATALOG_DIGEST = "c" * 64

    @staticmethod
    def comparator_spec(
        comparator_id: str,
        digest: str,
    ) -> dict:
        return {
            "comparator_id": comparator_id,
            "spec_sha256": digest,
        }

    def runner(self) -> dict:
        return with_self_hash(
            {
                "fixture_mount": {
                    "source": "STATIC_CATALOG",
                    "catalog_id": (
                        f"sha256:{self.CATALOG_DIGEST}"
                    ),
                    "catalog_sha256": self.CATALOG_DIGEST,
                },
                "input_bindings": [
                    {
                        "input_binding_id": "BINDING-TEST-V1",
                        "comparator": {
                            "comparator_id": "COMPARATOR-A-V1",
                            "spec_sha256": "a" * 64,
                        },
                    }
                ],
            },
            "runner_contract_id",
            prefixed=True,
        )

    @staticmethod
    def denominator() -> dict:
        return with_self_hash(
            {
                "group_id": "DENOM-TEST-V1",
                "description": "test",
                "release_requirement": (
                    "ALL_EFFECTIVE_ACTIVE_MUST_DETECT_EXACT"
                ),
            },
            "group_sha256",
            prefixed=True,
        )

    @staticmethod
    def decision() -> dict:
        return with_self_hash(
            {
                "schema_version": "SutDecision.v1",
                "outcome": "REJECT",
                "decision": None,
                "reason_ids": ["REASON-TEST"],
                "assertion_ids": ["ASSERT-TEST"],
            },
            "sut_decision_sha256",
            prefixed=False,
        )

    def manifest(
        self,
        *,
        regular_cases: list[dict],
        conformance_cases: list[dict],
    ) -> tuple[dict, dict]:
        runner = self.runner()
        value = {
            "runner_contracts": [runner],
            "denominator_groups": [self.denominator()],
            "cases": regular_cases,
            "runner_conformance_cases": conformance_cases,
            "supersession_events": [],
            "property_suites": [],
        }
        return (
            with_self_hash(
                value,
                "manifest_sha256",
                prefixed=True,
            ),
            runner,
        )

    def test_case_comparator_must_equal_resolved_runner_binding(self) -> None:
        runner = self.runner()
        decision = self.decision()
        case = with_self_hash(
            {
                "case_id": "EV-COMPARATOR-SUBSTITUTION",
                "runner_contract_id": runner["runner_contract_id"],
                "input": {
                    "runner_contract_id": runner["runner_contract_id"],
                    "case_id": "EV-COMPARATOR-SUBSTITUTION",
                    "input_binding_id": "BINDING-TEST-V1",
                },
                "expected": decision,
                "oracle": {
                    "comparator_id": "COMPARATOR-B-V1",
                    "mode": "EXACT_SUT_DECISION",
                    "expected_sut_decision_sha256": (
                        decision["sut_decision_sha256"]
                    ),
                    "reference_trace_fixture_id": None,
                    "trace_normalization": "NONE",
                    "invariant_ids": ["ASSERT-TEST"],
                },
                "denominator_group_ids": ["DENOM-TEST-V1"],
            },
            "case_sha256",
            prefixed=True,
        )
        manifest, _ = self.manifest(
            regular_cases=[case],
            conformance_cases=[],
        )
        manifest["runner_contracts"] = [runner]
        manifest = with_self_hash(
            manifest,
            "manifest_sha256",
            prefixed=True,
        )
        comparators = {
            "COMPARATOR-A-V1": self.comparator_spec(
                "COMPARATOR-A-V1",
                "a" * 64,
            ),
            "COMPARATOR-B-V1": self.comparator_spec(
                "COMPARATOR-B-V1",
                "b" * 64,
            ),
        }

        with self.assertRaisesRegex(
            validate_phase0.ValidationError,
            "case comparator mismatch",
        ):
            validate_phase0._validate_manifest_relations(
                manifest,
                catalog_digest=self.CATALOG_DIGEST,
                algorithms={},
                comparator_specs=comparators,
            )

    def test_conformance_invocation_identity_must_match_outer_case(self) -> None:
        runner = self.runner()
        invocation = with_self_hash(
            {
                "schema_version": "RunnerConformanceInvocation.v1",
                "case_id": "EV-DIFFERENT-CASE",
                "runner_contract_id": runner["runner_contract_id"],
                "input_binding_id": "BINDING-TEST-V1",
                "input_variant": {
                    "fixture_refs": [],
                },
            },
            "invocation_jcs_sha256",
            prefixed=False,
        )
        case = with_self_hash(
            {
                "case_id": "EV-CONFORMANCE-IDENTITY",
                "denominator_group_ids": ["DENOM-TEST-V1"],
                "invocation": invocation,
            },
            "case_sha256",
            prefixed=True,
        )
        manifest, _ = self.manifest(
            regular_cases=[],
            conformance_cases=[case],
        )

        with self.assertRaisesRegex(
            validate_phase0.ValidationError,
            "conformance invocation case_id mismatch",
        ):
            validate_phase0._validate_manifest_relations(
                manifest,
                catalog_digest=self.CATALOG_DIGEST,
                algorithms={},
                comparator_specs={
                    "COMPARATOR-A-V1": self.comparator_spec(
                        "COMPARATOR-A-V1",
                        "a" * 64,
                    )
                },
            )

    def test_property_domain_order_is_explicit_and_set_exact(self) -> None:
        suite = with_self_hash(
            {
                "suite_id": "PROPERTY-ORDER-V1",
                "sut_runner_contract_id": "sha256:" + "1" * 64,
                "domain": {
                    "first": ["A"],
                    "second": ["B"],
                },
                "domain_order": ["second", "first"],
                "generator": {
                    "algorithm_id": "GENERATOR-V1",
                    "source_manifest_entry_sha256": "1" * 64,
                },
                "input_materializer": {
                    "algorithm_id": "MATERIALIZER-V1",
                    "source_manifest_entry_sha256": "2" * 64,
                    "input_binding_id": "BINDING-PROPERTY-V1",
                },
                "reference_oracle": {
                    "algorithm_id": "ORACLE-V1",
                    "source_manifest_entry_sha256": "3" * 64,
                },
                "expected_instance_count": 1,
            },
            "suite_sha256",
            prefixed=True,
        )
        runners = {
            suite["sut_runner_contract_id"]: {
                "input_bindings": [
                    {
                        "input_binding_id": "BINDING-PROPERTY-V1",
                    }
                ]
            }
        }
        algorithms = {
            "GENERATOR-V1": {"entry_sha256": "1" * 64},
            "MATERIALIZER-V1": {"entry_sha256": "2" * 64},
            "ORACLE-V1": {"entry_sha256": "3" * 64},
        }

        self.assertEqual(
            1,
            validate_phase0._validate_property_suites(
                {"property_suites": [suite]},
                runners,
                algorithms,
            ),
        )

        for invalid_order in (
            ["first", "first"],
            ["first"],
            ["first", "second", "third"],
        ):
            invalid = copy.deepcopy(suite)
            invalid["domain_order"] = invalid_order
            invalid = with_self_hash(
                invalid,
                "suite_sha256",
                prefixed=True,
            )
            with self.subTest(invalid_order=invalid_order), self.assertRaisesRegex(
                validate_phase0.ValidationError,
                "domain_order",
            ):
                validate_phase0._validate_property_suites(
                    {"property_suites": [invalid]},
                    runners,
                    algorithms,
                )


class ReferenceSourceClosureTests(unittest.TestCase):
    def test_algorithm_file_binding_matches_source_without_role_metadata(self) -> None:
        source = {
            "repository_path": "evaluation/aegis_v2/reference/canonical.py",
            "byte_size": 42,
            "raw_sha256": "a" * 64,
            "role": "CANONICALIZATION",
        }
        owned = {
            "repository_path": source["repository_path"],
            "byte_size": source["byte_size"],
            "raw_sha256": source["raw_sha256"],
        }

        self.assertTrue(
            validate_phase0._same_file_binding(owned, source)
        )
        owned["byte_size"] += 1
        self.assertFalse(
            validate_phase0._same_file_binding(owned, source)
        )

    def test_runtime_binding_matches_frozen_files_lock_and_imports(self) -> None:
        root = MODULE_PATH.parents[2]
        source_manifest = validate_phase0.load_strict_json(
            root / validate_phase0.REFERENCE_MANIFEST_PATH
        )
        schema_bundle = validate_phase0.load_strict_json(
            root / validate_phase0.SCHEMA_BUNDLE_PATH
        )
        lock = validate_phase0._validate_lock(root)
        imported_by_source = {
            binding["repository_path"]: validate_phase0._source_imports(
                root / Path(*binding["repository_path"].split("/"))
            )
            for binding in source_manifest["source_files"]
            if binding["repository_path"].endswith(".py")
        }

        validate_phase0._validate_reference_runtime_binding(
            root,
            source_manifest,
            schema_bundle=schema_bundle,
            lock=lock,
            imported_by_source=imported_by_source,
        )

    def test_algorithm_cannot_import_globally_declared_unowned_source(self) -> None:
        source_files = {
            "evaluation/aegis_v2/reference/__init__.py": {},
            "evaluation/aegis_v2/reference/direct.py": {},
            "evaluation/aegis_v2/reference/borrowed.py": {},
        }
        entry = {
            "entrypoints": [
                "evaluation.aegis_v2.reference.direct.evaluate",
            ],
            "direct_source_files": [
                "evaluation/aegis_v2/reference/direct.py",
            ],
        }
        owned_paths = {
            "evaluation/aegis_v2/reference/__init__.py",
            "evaluation/aegis_v2/reference/direct.py",
        }
        imported_by_source = {
            "evaluation/aegis_v2/reference/direct.py": (
                set(),
                {".borrowed"},
                False,
            ),
        }

        with self.assertRaisesRegex(
            validate_phase0.ValidationError,
            "transitive source closure",
        ):
            validate_phase0._validate_algorithm_source_closure(
                "ALGORITHM-DIRECT-V1",
                entry,
                owned_paths=owned_paths,
                source_paths=set(source_files),
                imported_by_source=imported_by_source,
            )

    def test_entrypoint_must_resolve_to_direct_owned_source(self) -> None:
        source_paths = {
            "evaluation/aegis_v2/reference/__init__.py",
            "evaluation/aegis_v2/reference/direct.py",
            "evaluation/aegis_v2/reference/indirect.py",
        }
        entry = {
            "entrypoints": [
                "evaluation.aegis_v2.reference.indirect.evaluate",
            ],
            "direct_source_files": [
                "evaluation/aegis_v2/reference/direct.py",
            ],
        }

        with self.assertRaisesRegex(
            validate_phase0.ValidationError,
            "entrypoint source is not direct",
        ):
            validate_phase0._validate_algorithm_source_closure(
                "ALGORITHM-DIRECT-V1",
                entry,
                owned_paths=source_paths,
                source_paths=source_paths,
                imported_by_source={},
            )


class ManifestHistoryTests(unittest.TestCase):
    class AcceptAllSchemas:
        @staticmethod
        def validate(*args, **kwargs) -> None:
            return None

    @staticmethod
    def case(case_id: str, digest_character: str) -> dict:
        return {
            "case_id": case_id,
            "case_sha256": "sha256:" + digest_character * 64,
        }

    def test_replay_supersession_derives_effective_active_set(self) -> None:
        root_case = self.case("EV-ROOT", "a")
        replacement = self.case("EV-REPLACEMENT", "b")
        root_hash = "sha256:" + "1" * 64
        head_hash = "sha256:" + "2" * 64
        chain = [
            {
                "manifest_sha256": root_hash,
                "parent_manifest_hash": None,
                "cases": [root_case],
                "runner_conformance_cases": [],
                "supersession_events": [],
            },
            {
                "manifest_sha256": head_hash,
                "parent_manifest_hash": root_hash,
                "cases": [replacement],
                "runner_conformance_cases": [],
                "supersession_events": [
                    {
                        "event_id": (
                            "019fa2e4-d476-7c03-9962-b07c007a1f19"
                        ),
                        "parent_manifest_hash": root_hash,
                        "target_case_id": root_case["case_id"],
                        "target_case_sha256": root_case["case_sha256"],
                        "replacement_case_ids": [replacement["case_id"]],
                    }
                ],
            },
        ]

        cases, active = validate_phase0._replay_manifest_history(chain)
        self.assertEqual(
            {"EV-ROOT", "EV-REPLACEMENT"},
            set(cases),
        )
        self.assertEqual({"EV-REPLACEMENT"}, active)

    def test_replay_rejects_reintroduced_historical_case_id(self) -> None:
        root_case = self.case("EV-ROOT", "a")
        root_hash = "sha256:" + "1" * 64
        chain = [
            {
                "manifest_sha256": root_hash,
                "parent_manifest_hash": None,
                "cases": [root_case],
                "runner_conformance_cases": [],
                "supersession_events": [],
            },
            {
                "manifest_sha256": "sha256:" + "2" * 64,
                "parent_manifest_hash": root_hash,
                "cases": [copy.deepcopy(root_case)],
                "runner_conformance_cases": [],
                "supersession_events": [],
            },
        ]

        with self.assertRaisesRegex(
            validate_phase0.ValidationError,
            "duplicate historical case_id",
        ):
            validate_phase0._replay_manifest_history(chain)

    def test_replay_rejects_wrong_target_hash(self) -> None:
        root_case = self.case("EV-ROOT", "a")
        replacement = self.case("EV-REPLACEMENT", "b")
        root_hash = "sha256:" + "1" * 64
        chain = [
            {
                "manifest_sha256": root_hash,
                "parent_manifest_hash": None,
                "cases": [root_case],
                "runner_conformance_cases": [],
                "supersession_events": [],
            },
            {
                "manifest_sha256": "sha256:" + "2" * 64,
                "parent_manifest_hash": root_hash,
                "cases": [replacement],
                "runner_conformance_cases": [],
                "supersession_events": [
                    {
                        "event_id": (
                            "019fa2e4-d476-7c03-9962-b07c007a1f19"
                        ),
                        "parent_manifest_hash": root_hash,
                        "target_case_id": root_case["case_id"],
                        "target_case_sha256": "sha256:" + "f" * 64,
                        "replacement_case_ids": [replacement["case_id"]],
                    }
                ],
            },
        ]

        with self.assertRaisesRegex(
            validate_phase0.ValidationError,
            "target case hash mismatch",
        ):
            validate_phase0._replay_manifest_history(chain)

    def test_parent_locator_raw_bytes_are_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = with_self_hash(
                {
                    "parent_manifest_hash": None,
                    "parent_manifest_locator": None,
                    "cases": [],
                    "runner_conformance_cases": [],
                    "supersession_events": [],
                },
                "manifest_sha256",
                prefixed=True,
            )
            parent_digest = parent["manifest_sha256"].removeprefix("sha256:")
            relative = (
                "evaluation/aegis_v2/manifests/sha256/"
                f"{parent_digest}.json"
            )
            raw = json.dumps(parent, indent=2).encode("utf-8") + b"\n"
            write(root / Path(*relative.split("/")), raw)
            head = with_self_hash(
                {
                    "parent_manifest_hash": parent["manifest_sha256"],
                    "parent_manifest_locator": {
                        "repository_path": relative,
                        "declared_manifest_sha256": parent["manifest_sha256"],
                        "raw_sha256": "0" * 64,
                        "byte_size": len(raw),
                        "content_addressed_store_key": (
                            parent["manifest_sha256"]
                        ),
                    },
                    "cases": [],
                    "runner_conformance_cases": [],
                    "supersession_events": [],
                },
                "manifest_sha256",
                prefixed=True,
            )

            with self.assertRaisesRegex(
                validate_phase0.ValidationError,
                "parent manifest raw_sha256 mismatch",
            ):
                validate_phase0._load_manifest_chain(
                    root,
                    self.AcceptAllSchemas(),
                    head,
                )


class ValidateRepositoryWiringTests(unittest.TestCase):
    def test_schema_bundle_and_lock_are_routed_to_reference_validation(self) -> None:
        manifest = {
            "freeze": {
                "schema_version": "PendingFreeze.v1",
                "state": "PENDING",
            },
        }
        schema_bundle = {"bundle_id": "schema-bundle"}
        lock = {"lock_id": "python-lock"}
        schemas = mock.Mock()
        schemas.by_path = {}

        def load_chain(root: Path, offline_schemas, head: dict) -> list[dict]:
            self.assertIs(offline_schemas, schemas)
            self.assertIs(head, manifest)
            return [head]

        def validate_reference_sources(
            root: Path,
            offline_schemas,
            head: dict,
            *,
            schema_bundle: dict,
            lock: dict,
        ) -> tuple[dict, dict, dict]:
            self.assertIs(offline_schemas, schemas)
            self.assertIs(head, manifest)
            self.assertEqual({"bundle_id": "schema-bundle"}, schema_bundle)
            self.assertEqual({"lock_id": "python-lock"}, lock)
            return {}, {}, {}

        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(
                validate_phase0,
                "_OfflineSchemas",
                return_value=schemas,
            ),
            mock.patch.object(
                validate_phase0,
                "_validate_schema_bundle",
                return_value=schema_bundle,
            ),
            mock.patch.object(
                validate_phase0,
                "_validate_lock",
                return_value=lock,
            ),
            mock.patch.object(
                validate_phase0,
                "_load_repository_json",
                return_value=manifest,
            ),
            mock.patch.object(
                validate_phase0,
                "_load_manifest_chain",
                side_effect=load_chain,
            ),
            mock.patch.object(
                validate_phase0,
                "_replay_manifest_history",
                return_value=({}, set()),
            ),
            mock.patch.object(
                validate_phase0,
                "_validate_reference_sources",
                side_effect=validate_reference_sources,
            ),
            mock.patch.object(
                validate_phase0,
                "_validate_fixture_catalog",
                return_value=({"catalog_sha256": "catalog"}, {}),
            ),
            mock.patch.object(
                validate_phase0,
                "_validate_manifest_relations",
                return_value=({}, set(), 0),
            ),
            mock.patch.object(
                validate_phase0,
                "_validate_risk_register",
                return_value={"entries": []},
            ),
        ):
            report = validate_phase0.validate_repository(Path(directory))

        self.assertFalse(report["valid"])
        self.assertTrue(report["structural_valid"])
        self.assertFalse(report["phase_complete"])
        self.assertEqual(
            report["validation_scope"],
            "PHASE_0A_STATIC_STRUCTURE_AND_FREEZE_AUTHORITY",
        )
        self.assertEqual(
            report["blockers"],
            [
                "AUTHORITY_UNVERIFIED",
                "PHASE_0A_PENDING_FREEZE_EVIDENCE",
            ],
        )
        self.assertEqual(report["checks"]["freeze_state"], "PENDING")
        self.assertFalse(report["checks"]["authority_event_verified"])

    def test_pending_report_returns_nonzero_from_cli(self) -> None:
        report = {
            "valid": False,
            "structural_valid": True,
            "phase_complete": False,
            "validation_scope": (
                "PHASE_0A_STATIC_STRUCTURE_AND_FREEZE_AUTHORITY"
            ),
            "blockers": [
                "AUTHORITY_UNVERIFIED",
                "PHASE_0A_PENDING_FREEZE_EVIDENCE",
            ],
            "errors": [],
            "checks": {},
        }

        class Stdout:
            def __init__(self) -> None:
                import io

                self.buffer = io.BytesIO()

        stdout = Stdout()
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(
                validate_phase0,
                "validate_repository",
                return_value=report,
            ),
            mock.patch.object(validate_phase0.sys, "stdout", stdout),
        ):
            exit_code = validate_phase0.main(
                ["--repo-root", directory],
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(
            json.loads(stdout.buffer.getvalue()),
            report,
        )

    def test_frozen_record_without_external_proof_is_overall_invalid(
        self,
    ) -> None:
        manifest = {
            "freeze": {"schema_version": "Phase0FreezeRecord.v1"},
        }
        schemas = mock.Mock()
        schemas.by_path = {}

        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(
                validate_phase0,
                "_OfflineSchemas",
                return_value=schemas,
            ),
            mock.patch.object(
                validate_phase0,
                "_validate_schema_bundle",
                return_value={},
            ),
            mock.patch.object(
                validate_phase0,
                "_validate_lock",
                return_value={},
            ),
            mock.patch.object(
                validate_phase0,
                "_load_repository_json",
                return_value=manifest,
            ),
            mock.patch.object(
                validate_phase0,
                "_load_manifest_chain",
                return_value=[manifest],
            ),
            mock.patch.object(
                validate_phase0,
                "_replay_manifest_history",
                return_value=({}, set()),
            ),
            mock.patch.object(
                validate_phase0,
                "_validate_reference_sources",
                return_value=({}, {}, {}),
            ),
            mock.patch.object(
                validate_phase0,
                "_validate_fixture_catalog",
                return_value=({"catalog_sha256": "catalog"}, {}),
            ),
            mock.patch.object(
                validate_phase0,
                "_validate_manifest_relations",
                return_value=({}, set(), 0),
            ),
            mock.patch.object(
                validate_phase0,
                "_validate_risk_register",
                return_value={"entries": []},
            ),
            mock.patch.object(
                validate_phase0,
                "_validate_freeze_record_relations",
            ) as structural_validation,
            self.assertRaisesRegex(
                validate_phase0.ValidationError,
                "AUTHORITY_UNVERIFIED",
            ),
        ):
            validate_phase0.validate_repository(Path(directory))

        structural_validation.assert_called_once()


class FreezeIdentityBindingTests(unittest.TestCase):
    @staticmethod
    def record() -> dict:
        locator = {
            "capture_source": "PREAUTHORIZED_APPEND_ONLY_CODEX_EVENT_SOURCE",
            "authority_source_id": "test-only-authority-source",
            "authority_policy_id": "test-only-authority-policy",
            "authority_event_id": "test-only-authority-event",
            "authority_event_sequence": 42,
            "authority_committed_at_utc": "2026-07-27T09:02:03Z",
            "codex_cli_version": "0.145.0",
            "codex_app_server_protocol_semantic_sha256": (
                "sha256:"
                "1bc09dedc506075562d4d49b702ecab6d947dd5a8c2a9014a5cde592a0938efb"
            ),
            "reviewer_task_path": "/root/reviewer",
            "parent_thread_id": "producer-thread",
            "parent_spawn_tool_call_id": "parent-spawn-tool-call",
            "parent_delivery_tool_call_id": "parent-delivery-tool-call",
            "reviewer_thread_id": "reviewer-thread",
            "reviewer_session_id": "reviewer-session",
            "reviewer_turn_id": "reviewer-turn",
            "reviewer_item_id": "reviewer-final-item",
            "reviewer_turn_started_at_unix_seconds": 1,
            "reviewer_turn_completed_at_unix_seconds": 3,
            "reviewer_item_started_at_unix_ms": 2000,
            "reviewer_item_completed_at_unix_ms": 3000,
            "reviewer_turn_status": "completed",
            "reviewer_item_type": "agentMessage",
            "reviewer_item_phase": "final_answer",
            "delivery_kind": "AGENT_MESSAGE_FINAL_ANSWER",
        }
        artifact = {
            "logical_path": "repo:/review.md",
            "locator": {
                "kind": "REPOSITORY",
                "repository_path": "review.md",
            },
            "byte_size": 1,
            "raw_sha256": "a" * 64,
        }
        event = {
            "schema_version": "Phase0ReviewFinalEvent.v1",
            "authority_locator": copy.deepcopy(locator),
            "freeze_root_id": "sha256:" + "1" * 64,
            "code_absence_proof_id": "sha256:" + "2" * 64,
            "review_artifact": copy.deepcopy(artifact),
            "verdict": "PASS",
            "open_blocker_ids": [],
            "reviewed_at_utc": "2026-07-27T09:02:00Z",
        }
        return {
            "freeze_producer_identity": {
                "thread_id": "producer-thread",
                "session_id": "producer-session",
                "turn_id": "producer-turn",
            },
            "freeze_root_id": event["freeze_root_id"],
            "code_absence_proof": {
                "code_absence_proof_id": event["code_absence_proof_id"],
                "outside_domain_entries": [],
            },
            "review_anchor": {
                "review_outcome": "PASS",
                "open_blocker_ids": [],
                "capture_source": locator["capture_source"],
                "authority_source_id": locator["authority_source_id"],
                "authority_policy_id": locator["authority_policy_id"],
                "authority_event_id": locator["authority_event_id"],
                "authority_event_sequence": locator["authority_event_sequence"],
                "authority_committed_at_utc": locator[
                    "authority_committed_at_utc"
                ],
                "codex_cli_version": locator["codex_cli_version"],
                "codex_app_server_protocol_semantic_sha256": locator[
                    "codex_app_server_protocol_semantic_sha256"
                ],
                "reviewer_task_path": locator["reviewer_task_path"],
                "parent_thread_id": locator["parent_thread_id"],
                "parent_spawn_tool_call_id": locator[
                    "parent_spawn_tool_call_id"
                ],
                "parent_delivery_tool_call_id": locator[
                    "parent_delivery_tool_call_id"
                ],
                "reviewer_thread_id": locator["reviewer_thread_id"],
                "reviewer_session_id": locator["reviewer_session_id"],
                "reviewer_turn_id": locator["reviewer_turn_id"],
                "reviewer_item_id": locator["reviewer_item_id"],
                "reviewer_turn_started_at_unix_seconds": locator[
                    "reviewer_turn_started_at_unix_seconds"
                ],
                "reviewer_turn_completed_at_unix_seconds": locator[
                    "reviewer_turn_completed_at_unix_seconds"
                ],
                "reviewer_item_started_at_unix_ms": locator[
                    "reviewer_item_started_at_unix_ms"
                ],
                "reviewer_item_completed_at_unix_ms": locator[
                    "reviewer_item_completed_at_unix_ms"
                ],
                "reviewer_turn_status": locator["reviewer_turn_status"],
                "reviewer_item_type": locator["reviewer_item_type"],
                "reviewer_item_phase": locator["reviewer_item_phase"],
                "delivery_kind": locator["delivery_kind"],
                "review_artifact": copy.deepcopy(artifact),
                "reviewed_freeze_root_id": event["freeze_root_id"],
                "reviewed_code_absence_proof_id": (
                    event["code_absence_proof_id"]
                ),
                "reviewed_at_utc": event["reviewed_at_utc"],
            },
            "authority_anchor": {
                "authority_locator": copy.deepcopy(locator),
                "anchor_event_preimage": event,
            },
        }

    def test_freeze_reviewer_must_be_distinct_from_persisted_producer(
        self,
    ) -> None:
        record = self.record()
        record["review_anchor"]["reviewer_thread_id"] = "producer-thread"
        record["review_anchor"]["reviewer_session_id"] = "producer-session"
        record["authority_anchor"]["authority_locator"][
            "reviewer_thread_id"
        ] = "producer-thread"
        record["authority_anchor"]["authority_locator"][
            "reviewer_session_id"
        ] = "producer-session"
        record["authority_anchor"]["anchor_event_preimage"][
            "authority_locator"
        ] = copy.deepcopy(record["authority_anchor"]["authority_locator"])

        with self.assertRaisesRegex(
            validate_phase0.ValidationError,
            "reviewer is not independent",
        ):
            validate_phase0._validate_freeze_identity_bindings(record)

    def test_freeze_event_must_bind_exact_reviewed_root(self) -> None:
        record = self.record()
        record["authority_anchor"]["anchor_event_preimage"][
            "freeze_root_id"
        ] = "sha256:" + "f" * 64

        with self.assertRaisesRegex(
            validate_phase0.ValidationError,
            "final event binding mismatch",
        ):
            validate_phase0._validate_freeze_identity_bindings(record)


if __name__ == "__main__":
    unittest.main()
