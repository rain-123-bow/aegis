from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import rfc8785


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = Path(__file__).resolve().parents[1] / (
    "build_evaluation_manifest.py"
)
SPEC = importlib.util.spec_from_file_location(
    "aegis_v2_build_evaluation_manifest",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
build_evaluation_manifest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_evaluation_manifest)


def load_json(relative_path: str) -> dict:
    return json.loads(
        (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    )


def self_hash(
    value: dict,
    field: str,
    *,
    prefixed: bool,
) -> str:
    preimage = copy.deepcopy(value)
    preimage.pop(field, None)
    digest = hashlib.sha256(rfc8785.dumps(preimage)).hexdigest()
    return f"sha256:{digest}" if prefixed else digest


def serialized(value: dict) -> bytes:
    return rfc8785.dumps(value) + b"\n"


class RepositoryInputs:
    def __init__(self) -> None:
        self.template = load_json(
            "evaluation/aegis_v2/evaluation_manifest.v1.json"
        )
        self.schema_documents = {
            path.relative_to(REPOSITORY_ROOT).as_posix(): json.loads(
                path.read_text(encoding="utf-8")
            )
            for path in sorted(
                (REPOSITORY_ROOT / "schemas/aegis/v2").glob(
                    "*.schema.json"
                )
            )
        }
        self.schema_raw_documents = {
            relative_path: (
                REPOSITORY_ROOT / relative_path
            ).read_bytes()
            for relative_path in self.schema_documents
        }
        schema_bundle_path = (
            REPOSITORY_ROOT / "schemas/aegis/v2/schema_bundle.v1.json"
        )
        self.schema_bundle = json.loads(
            schema_bundle_path.read_text(encoding="utf-8")
        )
        self.schema_bundle_raw = schema_bundle_path.read_bytes()
        self.evaluation_schema = self.schema_documents[
            "schemas/aegis/v2/evaluation_manifest.v1.schema.json"
        ]
        self.runner_schema = self.schema_documents[
            "schemas/aegis/v2/evaluation_runner_contract.v1.schema.json"
        ]
        self.source_manifest_schema = self.schema_documents[
            "schemas/aegis/v2/reference_source_manifest.v1.schema.json"
        ]
        self.common_schema = self.schema_documents[
            "schemas/aegis/v2/common.v1.schema.json"
        ]
        fixture_catalog_path = (
            REPOSITORY_ROOT
            / "evaluation/aegis_v2/fixture_catalog.v1.json"
        )
        self.fixture_catalog = load_json(
            "evaluation/aegis_v2/fixture_catalog.v1.json"
        )
        self.fixture_catalog_raw = fixture_catalog_path.read_bytes()
        risk_register_path = (
            REPOSITORY_ROOT
            / "evaluation/aegis_v2/risk_register.v1.json"
        )
        self.risk_register = load_json(
            "evaluation/aegis_v2/risk_register.v1.json"
        )
        self.risk_register_raw = risk_register_path.read_bytes()
        source_manifest_path = (
            REPOSITORY_ROOT
            / "evaluation/aegis_v2/reference/source_manifest.v1.json"
        )
        self.source_manifest = load_json(
            "evaluation/aegis_v2/reference/source_manifest.v1.json"
        )
        self.source_manifest_raw = source_manifest_path.read_bytes()
        self.fixture_blobs = {
            fixture["repository_path"]: (
                REPOSITORY_ROOT / fixture["repository_path"]
            ).read_bytes()
            for fixture in self.fixture_catalog["fixtures"]
        }
        source_paths = {
            item["repository_path"]
            for item in [
                *self.source_manifest["source_files"],
                *self.source_manifest["assurance_files"],
            ]
        }
        source_paths.update(
            self.source_manifest["runtime_binding"][binding][
                "repository_path"
            ]
            for binding in ("pyproject", "lock", "schema_bundle")
        )
        self.source_blobs = {
            repository_path: (
                REPOSITORY_ROOT / repository_path
            ).read_bytes()
            for repository_path in source_paths
        }

    def clone(self) -> RepositoryInputs:
        return copy.deepcopy(self)

    def _refresh_artifact_raw_bytes(self) -> None:
        self.fixture_catalog["catalog_sha256"] = self_hash(
            self.fixture_catalog,
            "catalog_sha256",
            prefixed=False,
        )
        self.fixture_catalog_raw = serialized(self.fixture_catalog)
        self.risk_register["register_sha256"] = self_hash(
            self.risk_register,
            "register_sha256",
            prefixed=True,
        )
        self.risk_register_raw = serialized(self.risk_register)

    def _refresh_schema_bundle(self) -> None:
        for entry in self.schema_bundle["schemas"]:
            schema = self.schema_documents[entry["path"]]
            canonical = rfc8785.dumps(schema)
            entry["byte_size"] = len(canonical)
            entry["sha256"] = (
                f"sha256:{hashlib.sha256(canonical).hexdigest()}"
            )
            self.schema_raw_documents[entry["path"]] = serialized(
                schema
            )
        self.schema_bundle["bundle_sha256"] = self_hash(
            self.schema_bundle,
            "bundle_sha256",
            prefixed=True,
        )
        self.schema_bundle_raw = serialized(self.schema_bundle)

    def replace_source_blob(
        self,
        repository_path: str,
        raw: bytes,
    ) -> None:
        self.source_blobs[repository_path] = raw
        source_record = next(
            item
            for item in self.source_manifest["source_files"]
            if item["repository_path"] == repository_path
        )
        source_record["byte_size"] = len(raw)
        source_record["raw_sha256"] = hashlib.sha256(raw).hexdigest()
        for entry in self.source_manifest["algorithm_entries"]:
            changed = False
            for binding in entry["owned_source_files"]:
                if binding["repository_path"] == repository_path:
                    binding["byte_size"] = len(raw)
                    binding["raw_sha256"] = hashlib.sha256(
                        raw
                    ).hexdigest()
                    changed = True
            if changed:
                entry["entry_sha256"] = self_hash(
                    entry,
                    "entry_sha256",
                    prefixed=False,
                )
        entries = {
            entry["entry_id"]: entry
            for entry in self.source_manifest["algorithm_entries"]
        }
        for specification in self.source_manifest["comparator_specs"]:
            specification["algorithm_entry_sha256"] = entries[
                specification["algorithm_entry_id"]
            ]["entry_sha256"]
            trace_entry_id = specification[
                "trace_algorithm_entry_id"
            ]
            specification["trace_algorithm_entry_sha256"] = (
                entries[trace_entry_id]["entry_sha256"]
                if trace_entry_id is not None
                else None
            )
            specification["spec_sha256"] = self_hash(
                specification,
                "spec_sha256",
                prefixed=False,
            )
        self.source_manifest["manifest_sha256"] = self_hash(
            self.source_manifest,
            "manifest_sha256",
            prefixed=False,
        )
        self.source_manifest_raw = serialized(self.source_manifest)

    def refresh_source_manifest_hashes(self) -> None:
        for entry in self.source_manifest["algorithm_entries"]:
            entry["entry_sha256"] = self_hash(
                entry,
                "entry_sha256",
                prefixed=False,
            )
        entries = {
            entry["entry_id"]: entry
            for entry in self.source_manifest["algorithm_entries"]
        }
        for specification in self.source_manifest["comparator_specs"]:
            specification["algorithm_entry_sha256"] = entries[
                specification["algorithm_entry_id"]
            ]["entry_sha256"]
            trace_entry_id = specification[
                "trace_algorithm_entry_id"
            ]
            specification["trace_algorithm_entry_sha256"] = (
                entries[trace_entry_id]["entry_sha256"]
                if trace_entry_id is not None
                else None
            )
            specification["spec_sha256"] = self_hash(
                specification,
                "spec_sha256",
                prefixed=False,
            )
        self.source_manifest["manifest_sha256"] = self_hash(
            self.source_manifest,
            "manifest_sha256",
            prefixed=False,
        )
        self.source_manifest_raw = serialized(self.source_manifest)

    def render(self) -> dict:
        return build_evaluation_manifest.render_evaluation_manifest(
            template=self.template,
            evaluation_schema=self.evaluation_schema,
            runner_schema=self.runner_schema,
            source_manifest_schema=self.source_manifest_schema,
            common_schema=self.common_schema,
            schema_documents=self.schema_documents,
            schema_raw_documents=self.schema_raw_documents,
            schema_bundle=self.schema_bundle,
            schema_bundle_raw=self.schema_bundle_raw,
            source_manifest=self.source_manifest,
            source_manifest_raw=self.source_manifest_raw,
            source_blobs=self.source_blobs,
            fixture_catalog=self.fixture_catalog,
            fixture_catalog_raw=self.fixture_catalog_raw,
            fixture_blobs=self.fixture_blobs,
            risk_register=self.risk_register,
            risk_register_raw=self.risk_register_raw,
        )


class EvaluationManifestRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = RepositoryInputs()

    @staticmethod
    def add_same_case_trace_leak(manifest: dict) -> None:
        case = next(
            item
            for item in manifest["cases"]
            if item["oracle"]["reference_trace_fixture_id"] is not None
        )
        trace_fixture_id = case["oracle"]["reference_trace_fixture_id"]
        fixture_refs = case["input"]["fixture_refs"]
        if trace_fixture_id in fixture_refs:
            raise AssertionError("test manifest already contains trace leak")
        fixture_refs.append(trace_fixture_id)
        fixture_refs.sort()
        case["case_sha256"] = self_hash(
            case,
            "case_sha256",
            prefixed=True,
        )
        manifest["manifest_sha256"] = self_hash(
            manifest,
            "manifest_sha256",
            prefixed=True,
        )

    def test_render_is_idempotent_and_derivations_are_unique(self) -> None:
        inputs = self.inputs.clone()
        self.add_same_case_trace_leak(inputs.template)
        original = copy.deepcopy(inputs.template)

        first = inputs.render()
        self.assertEqual(original, inputs.template)
        inputs.template = first
        second = inputs.render()

        self.assertEqual(first, second)
        property_runners = [
            contract
            for contract in first["runner_contracts"]
            if contract["fixture_mount"]["source"]
            == "PROPERTY_INSTANCE_MATERIALIZATION"
        ]
        self.assertEqual(2, len(property_runners))
        self.assertEqual(
            2,
            len(
                {
                    contract["runner_contract_id"]
                    for contract in property_runners
                }
            ),
        )
        self.assertEqual(27, len(first["runner_conformance_cases"]))
        self.assertEqual(
            27,
            len(
                {
                    case["case_id"]
                    for case in first["runner_conformance_cases"]
                }
            ),
        )
        original_overlap_count = sum(
            case["oracle"]["reference_trace_fixture_id"]
            in case["input"]["fixture_refs"]
            for case in original["cases"]
            if case["oracle"]["reference_trace_fixture_id"] is not None
        )
        self.assertGreater(original_overlap_count, 0)
        for case in first["cases"]:
            with self.subTest(case_id=case["case_id"]):
                self.assertNotIn(
                    case["oracle"]["reference_trace_fixture_id"],
                    case["input"]["fixture_refs"],
                )

    def test_missing_real_materializer_entry_fails_closed(self) -> None:
        inputs = self.inputs.clone()
        inputs.source_manifest["algorithm_entries"] = [
            entry
            for entry in inputs.source_manifest["algorithm_entries"]
            if entry["entry_id"]
            != "MATERIALIZER-BLOCKER-CLOSURE-RUNNER-INPUT-V1"
        ]
        inputs.source_manifest["manifest_sha256"] = self_hash(
            inputs.source_manifest,
            "manifest_sha256",
            prefixed=False,
        )
        inputs.source_manifest_raw = serialized(inputs.source_manifest)

        with self.assertRaisesRegex(
            build_evaluation_manifest.ManifestBuildError,
            "materializer.*missing",
        ):
            inputs.render()

    def test_materializer_entrypoint_must_resolve_to_real_source_symbol(
        self,
    ) -> None:
        inputs = self.inputs.clone()
        entry = next(
            item
            for item in inputs.source_manifest["algorithm_entries"]
            if item["entry_id"]
            == "MATERIALIZER-VERDICT-RUNNER-INPUT-V1"
        )
        entry["entrypoints"] = [
            (
                "evaluation.aegis_v2.reference.materialize_verdict."
                "missing_materializer_symbol"
            )
        ]
        entry["entry_sha256"] = self_hash(
            entry,
            "entry_sha256",
            prefixed=False,
        )
        inputs.source_manifest["manifest_sha256"] = self_hash(
            inputs.source_manifest,
            "manifest_sha256",
            prefixed=False,
        )
        inputs.source_manifest_raw = serialized(inputs.source_manifest)

        with self.assertRaisesRegex(
            build_evaluation_manifest.ManifestBuildError,
            "entrypoint symbol missing",
        ):
            inputs.render()

    def test_every_algorithm_entrypoint_and_owned_closure_is_real(
        self,
    ) -> None:
        bad_entrypoint = self.inputs.clone()
        entry = next(
            item
            for item in bad_entrypoint.source_manifest[
                "algorithm_entries"
            ]
            if item["entry_id"]
            == "GENERATOR-VERDICT-CARTESIAN-V1"
        )
        entry["entrypoints"][0] = (
            "evaluation.aegis_v2.reference.coverage."
            "missing_coverage_symbol"
        )
        entry["entry_sha256"] = self_hash(
            entry,
            "entry_sha256",
            prefixed=False,
        )
        bad_entrypoint.source_manifest["manifest_sha256"] = self_hash(
            bad_entrypoint.source_manifest,
            "manifest_sha256",
            prefixed=False,
        )
        bad_entrypoint.source_manifest_raw = serialized(
            bad_entrypoint.source_manifest
        )

        with self.assertRaisesRegex(
            build_evaluation_manifest.ManifestBuildError,
            "entrypoint symbol missing",
        ):
            bad_entrypoint.render()

        bad_closure = self.inputs.clone()
        entry = next(
            item
            for item in bad_closure.source_manifest[
                "algorithm_entries"
            ]
            if item["entry_id"]
            == "GENERATOR-VERDICT-CARTESIAN-V1"
        )
        direct = set(entry["direct_source_files"])
        entry["owned_source_files"] = [
            binding
            for binding in entry["owned_source_files"]
            if binding["repository_path"] in direct
        ]
        entry["entry_sha256"] = self_hash(
            entry,
            "entry_sha256",
            prefixed=False,
        )
        bad_closure.source_manifest["manifest_sha256"] = self_hash(
            bad_closure.source_manifest,
            "manifest_sha256",
            prefixed=False,
        )
        bad_closure.source_manifest_raw = serialized(
            bad_closure.source_manifest
        )

        with self.assertRaisesRegex(
            build_evaluation_manifest.ManifestBuildError,
            "owned source closure mismatch",
        ):
            bad_closure.render()

    def test_comparator_specs_bind_exact_algorithm_entry_hashes(
        self,
    ) -> None:
        inputs = self.inputs.clone()
        specification = inputs.source_manifest["comparator_specs"][0]
        specification["algorithm_entry_sha256"] = "0" * 64
        specification["spec_sha256"] = self_hash(
            specification,
            "spec_sha256",
            prefixed=False,
        )
        inputs.source_manifest["manifest_sha256"] = self_hash(
            inputs.source_manifest,
            "manifest_sha256",
            prefixed=False,
        )
        inputs.source_manifest_raw = serialized(inputs.source_manifest)

        with self.assertRaisesRegex(
            build_evaluation_manifest.ManifestBuildError,
            "algorithm entry hash mismatch",
        ):
            inputs.render()

    def test_source_policy_rejects_production_and_dynamic_imports(
        self,
    ) -> None:
        repository_path = (
            "evaluation/aegis_v2/reference/generator.py"
        )
        mutations = {
            "production": b"\nimport aegis\n",
            "dynamic": b"\n__import__('aegis')\n",
            "dynamic alias": (
                b"\nfrom importlib import import_module\n"
                b"import_module('aegis')\n"
            ),
            "network": (
                b"\nimport urllib.request\n"
                b"urllib.request.urlopen('https://invalid.example')\n"
            ),
            "shell": (
                b"\nimport subprocess\n"
                b"subprocess.run(['invalid-command'])\n"
            ),
            "dynamic reference": b"\nloader = __import__\n",
            "async network": b"\nimport asyncio\n",
            "OS execution alias": (
                b"\nfrom os import system as harmless_name\n"
            ),
            "aliased OS execution": (
                b"\nimport os as harmless\n"
                b"harmless.system('invalid-command')\n"
            ),
            "aliased builtins dynamic import": (
                b"\nimport builtins as harmless\n"
                b"harmless.__import__('aegis')\n"
            ),
            "indirect builtins dynamic import": (
                b"\ngetattr(__builtins__, '__import__')('aegis')\n"
            ),
            "browser network": (
                b"\nimport webbrowser\n"
                b"webbrowser.open('https://invalid.example')\n"
            ),
        }
        for label, suffix in mutations.items():
            with self.subTest(label=label):
                inputs = self.inputs.clone()
                inputs.replace_source_blob(
                    repository_path,
                    inputs.source_blobs[repository_path] + suffix,
                )
                with self.assertRaisesRegex(
                    build_evaluation_manifest.ManifestBuildError,
                    "forbidden production|forbidden dynamic|"
                    "dynamic loader|dynamic primitive|network-capable|"
                    "shell-capable|OS execution|"
                    "undeclared standard-library",
                ):
                    inputs.render()

    def test_source_manifest_arrays_require_canonical_order(self) -> None:
        mutations = {}

        source_files = self.inputs.clone()
        source_files.source_manifest["source_files"] = list(
            reversed(source_files.source_manifest["source_files"])
        )
        source_files.refresh_source_manifest_hashes()
        mutations["source_files"] = source_files

        assurance_files = self.inputs.clone()
        assurance_files.source_manifest["assurance_files"] = list(
            reversed(assurance_files.source_manifest["assurance_files"])
        )
        assurance_files.refresh_source_manifest_hashes()
        mutations["assurance_files"] = assurance_files

        algorithm_entries = self.inputs.clone()
        algorithm_entries.source_manifest["algorithm_entries"] = list(
            reversed(
                algorithm_entries.source_manifest["algorithm_entries"]
            )
        )
        algorithm_entries.refresh_source_manifest_hashes()
        mutations["algorithm_entries"] = algorithm_entries

        comparator_specs = self.inputs.clone()
        comparator_specs.source_manifest["comparator_specs"] = list(
            reversed(
                comparator_specs.source_manifest["comparator_specs"]
            )
        )
        comparator_specs.refresh_source_manifest_hashes()
        mutations["comparator_specs"] = comparator_specs

        entrypoints = self.inputs.clone()
        entry = next(
            item
            for item in entrypoints.source_manifest["algorithm_entries"]
            if len(item["entrypoints"]) > 1
        )
        entry["entrypoints"] = list(reversed(entry["entrypoints"]))
        entrypoints.refresh_source_manifest_hashes()
        mutations["entrypoints"] = entrypoints

        direct_sources = self.inputs.clone()
        entry = next(
            item
            for item in direct_sources.source_manifest[
                "algorithm_entries"
            ]
            if len(item["direct_source_files"]) > 1
        )
        entry["direct_source_files"] = list(
            reversed(entry["direct_source_files"])
        )
        direct_sources.refresh_source_manifest_hashes()
        mutations["direct source files"] = direct_sources

        owned_sources = self.inputs.clone()
        entry = next(
            item
            for item in owned_sources.source_manifest[
                "algorithm_entries"
            ]
            if len(item["owned_source_files"]) > 1
        )
        entry["owned_source_files"] = list(
            reversed(entry["owned_source_files"])
        )
        owned_sources.refresh_source_manifest_hashes()
        mutations["owned source paths"] = owned_sources

        for label, inputs in mutations.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    build_evaluation_manifest.ManifestBuildError,
                    "not sorted",
                ):
                    inputs.render()

    def test_source_policy_rejects_sys_registry_and_reflection(self) -> None:
        repository_path = "evaluation/aegis_v2/reference/cli.py"
        mutations = {
            "sys modules builtins": (
                b"\nsys.modules['builtins'].__import__('aegis')\n"
            ),
            "sys modules OS": (
                b"\nsys.modules['os'].system('invalid-command')\n"
            ),
            "sys modules get": (
                b"\nsys.modules.get('builtins').__import__('aegis')\n"
            ),
            "aliased sys modules": (
                b"\nimport sys as harmless\n"
                b"harmless.modules['os'].system('invalid-command')\n"
            ),
            "sys path": b"\nsys.path.append('untrusted')\n",
            "sys meta path": b"\nsys.meta_path.clear()\n",
            "sys path hooks": b"\nsys.path_hooks.clear()\n",
            "sys importer cache": (
                b"\nsys.path_importer_cache.clear()\n"
            ),
            "object reflection": b"\n(lambda: None).__globals__\n",
        }
        for label, suffix in mutations.items():
            with self.subTest(label=label):
                inputs = self.inputs.clone()
                inputs.replace_source_blob(
                    repository_path,
                    inputs.source_blobs[repository_path] + suffix,
                )
                with self.assertRaisesRegex(
                    build_evaluation_manifest.ManifestBuildError,
                    "runtime import registry|reflection|sys member",
                ):
                    inputs.render()

    def test_source_manifest_must_satisfy_its_schema(self) -> None:
        inputs = self.inputs.clone()
        entry = next(
            item
            for item in inputs.source_manifest["algorithm_entries"]
            if item["entry_id"]
            == "MATERIALIZER-BLOCKER-CLOSURE-RUNNER-INPUT-V1"
        )
        entry["separation_policy"] = None
        entry["entry_sha256"] = self_hash(
            entry,
            "entry_sha256",
            prefixed=False,
        )
        inputs.source_manifest["manifest_sha256"] = self_hash(
            inputs.source_manifest,
            "manifest_sha256",
            prefixed=False,
        )
        inputs.source_manifest_raw = serialized(inputs.source_manifest)

        with self.assertRaisesRegex(
            build_evaluation_manifest.ManifestBuildError,
            "source manifest schema validation failed",
        ):
            inputs.render()

    def test_risk_register_must_satisfy_frozen_schema_fragment(
        self,
    ) -> None:
        inputs = self.inputs.clone()
        inputs.risk_register["schema_version"] = "BogusRisk.v1"
        inputs._refresh_artifact_raw_bytes()

        with self.assertRaisesRegex(
            build_evaluation_manifest.ManifestBuildError,
            "risk register schema validation failed",
        ):
            inputs.render()

    def test_schema_documents_are_bound_to_frozen_bundle(self) -> None:
        inputs = self.inputs.clone()
        inputs.evaluation_schema["properties"]["manifest_kind"][
            "const"
        ] = "EVIL_CORPUS_KIND"

        with self.assertRaisesRegex(
            build_evaluation_manifest.ManifestBuildError,
            "value does not match supplied raw bytes|"
            "schema JCS (?:byte-size|hash) mismatch",
        ):
            inputs.render()

    def test_rendered_manifest_must_satisfy_offline_schema_bundle(
        self,
    ) -> None:
        inputs = self.inputs.clone()
        original = build_evaluation_manifest._validate_schema_instance
        with mock.patch.object(
            build_evaluation_manifest,
            "_validate_schema_instance",
            wraps=original,
        ) as validator:
            inputs.render()
        validated_sources = [
            call.kwargs["source"]
            for call in validator.call_args_list
        ]
        self.assertIn(
            "rendered evaluation manifest",
            validated_sources,
        )

    def test_schema_bundle_rejects_unresolved_network_reference(
        self,
    ) -> None:
        inputs = self.inputs.clone()
        inputs.evaluation_schema["allOf"] = [
            {"$ref": "https://invalid.example/aegis-schema.json"}
        ]
        inputs._refresh_schema_bundle()

        with self.assertRaisesRegex(
            build_evaluation_manifest.ManifestBuildError,
            "offline schema closure failure",
        ):
            inputs.render()

    def test_fixture_preimages_and_bidirectional_closure_fail_closed(
        self,
    ) -> None:
        mutations = {}

        reverse = self.inputs.clone()
        reverse.fixture_catalog["fixtures"][0]["case_ids"].append(
            "EV-NOT-REFERENCED"
        )
        reverse._refresh_artifact_raw_bytes()
        mutations["reverse closure"] = reverse

        byte_tamper = self.inputs.clone()
        path = byte_tamper.fixture_catalog["fixtures"][0][
            "repository_path"
        ]
        byte_tamper.fixture_blobs[path] += b" "
        mutations["bytes"] = byte_tamper

        hash_tamper = self.inputs.clone()
        path = hash_tamper.fixture_catalog["fixtures"][0][
            "repository_path"
        ]
        raw = bytearray(hash_tamper.fixture_blobs[path])
        raw[-1] ^= 1
        hash_tamper.fixture_blobs[path] = bytes(raw)
        mutations["raw hash"] = hash_tamper

        duplicate_id = self.inputs.clone()
        duplicate_id.fixture_catalog["fixtures"][1]["fixture_id"] = (
            duplicate_id.fixture_catalog["fixtures"][0]["fixture_id"]
        )
        duplicate_id._refresh_artifact_raw_bytes()
        mutations["duplicate ID"] = duplicate_id

        duplicate_logical_path = self.inputs.clone()
        duplicate_logical_path.fixture_catalog["fixtures"][1][
            "logical_runtime_paths"
        ][0] = duplicate_logical_path.fixture_catalog["fixtures"][0][
            "logical_runtime_paths"
        ][0]
        duplicate_logical_path._refresh_artifact_raw_bytes()
        mutations["duplicate logical path"] = duplicate_logical_path

        cas_path = self.inputs.clone()
        fixture = cas_path.fixture_catalog["fixtures"][0]
        original_path = fixture["repository_path"]
        parts = original_path.split("/")
        parts[3] = "0" * 64
        fixture["repository_path"] = "/".join(parts)
        cas_path.fixture_blobs[fixture["repository_path"]] = (
            cas_path.fixture_blobs.pop(original_path)
        )
        cas_path._refresh_artifact_raw_bytes()
        mutations["CAS path"] = cas_path

        jcs_hash = self.inputs.clone()
        fixture = next(
            item
            for item in jcs_hash.fixture_catalog["fixtures"]
            if item["jcs_sha256"] is not None
        )
        fixture["jcs_sha256"] = "0" * 64
        jcs_hash._refresh_artifact_raw_bytes()
        mutations["JCS hash"] = jcs_hash

        bad_path = self.inputs.clone()
        bad_path.fixture_catalog["fixtures"][0]["repository_path"] = (
            "../fixture-escape.json"
        )
        bad_path._refresh_artifact_raw_bytes()
        mutations["path"] = bad_path

        for label, inputs in mutations.items():
            with self.subTest(label=label):
                with self.assertRaises(
                    build_evaluation_manifest.ManifestBuildError
                ):
                    inputs.render()

    def test_fixture_catalog_arrays_require_canonical_order(self) -> None:
        mutations = {}

        fixtures = self.inputs.clone()
        fixtures.fixture_catalog["fixtures"] = list(
            reversed(fixtures.fixture_catalog["fixtures"])
        )
        fixtures._refresh_artifact_raw_bytes()
        mutations["fixtures"] = fixtures

        logical_paths = self.inputs.clone()
        fixture = next(
            item
            for item in logical_paths.fixture_catalog["fixtures"]
            if len(item["logical_runtime_paths"]) > 1
        )
        fixture["logical_runtime_paths"] = list(
            reversed(fixture["logical_runtime_paths"])
        )
        logical_paths._refresh_artifact_raw_bytes()
        mutations["logical_runtime_paths"] = logical_paths

        case_ids = self.inputs.clone()
        fixture = next(
            item
            for item in case_ids.fixture_catalog["fixtures"]
            if len(item["case_ids"]) > 1
        )
        fixture["case_ids"] = list(reversed(fixture["case_ids"]))
        case_ids._refresh_artifact_raw_bytes()
        mutations["case_ids"] = case_ids

        for label, inputs in mutations.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    build_evaluation_manifest.ManifestBuildError,
                    "not sorted",
                ):
                    inputs.render()

    def test_fixture_catalog_logical_paths_must_match_schema(self) -> None:
        inputs = self.inputs.clone()
        inputs.fixture_catalog["fixtures"][0][
            "logical_runtime_paths"
        ][0] = r"..\escape.json"
        inputs._refresh_artifact_raw_bytes()

        with self.assertRaisesRegex(
            build_evaluation_manifest.ManifestBuildError,
            "fixture catalog schema validation failed",
        ):
            inputs.render()

    def test_case_fixture_paths_must_stay_under_runner_root(self) -> None:
        ordinary = self.inputs.clone()
        fixture_id = ordinary.template["cases"][0]["input"][
            "fixture_refs"
        ][0]
        fixture = next(
            item
            for item in ordinary.fixture_catalog["fixtures"]
            if item["fixture_id"] == fixture_id
        )
        fixture["logical_runtime_paths"][0] = (
            r"C:\outside-runner-root\escaped.json"
        )
        ordinary._refresh_artifact_raw_bytes()

        with self.assertRaisesRegex(
            build_evaluation_manifest.ManifestBuildError,
            "escapes runner root",
        ):
            ordinary.render()

        conformance = self.inputs.clone()
        fixture = next(
            item
            for item in conformance.fixture_catalog["fixtures"]
            if item["fixture_id"]
            == "AEGIS-FIXTURE-V1-EVALUATOR-ISOLATION-CERTIFICATE"
        )
        fixture["logical_runtime_paths"][0] = (
            r"C:\outside-runner-root\certificate.json"
        )
        conformance._refresh_artifact_raw_bytes()
        with self.assertRaisesRegex(
            build_evaluation_manifest.ManifestBuildError,
            "escapes runner root",
        ):
            conformance.render()

        for label, path in {
            "dot": (
                r"C:\aegis-runtime\runs\run-101\path\..\escape.json"
            ),
            "ADS": (
                r"C:\aegis-runtime\runs\run-101\path\file.json:stream"
            ),
        }.items():
            with self.subTest(label=label):
                with self.assertRaises(
                    build_evaluation_manifest.ManifestBuildError
                ):
                    build_evaluation_manifest._normalize_windows_runtime_path(
                        path,
                        source="test path",
                    )

    def test_frozen_corpus_baselines_reject_shrinkage(self) -> None:
        ordinary_cases = self.inputs.clone()
        removed_case_id = ordinary_cases.template["cases"].pop()[
            "case_id"
        ]
        for fixture in ordinary_cases.fixture_catalog["fixtures"]:
            fixture["case_ids"] = [
                case_id
                for case_id in fixture["case_ids"]
                if case_id != removed_case_id
            ]
        ordinary_cases._refresh_artifact_raw_bytes()

        fixtures = self.inputs.clone()
        fixtures.fixture_catalog["fixtures"].pop()
        fixtures._refresh_artifact_raw_bytes()

        denominators = self.inputs.clone()
        denominators.template["denominator_groups"].pop()

        static_runners = self.inputs.clone()
        static_contract = next(
            contract
            for contract in static_runners.template["runner_contracts"]
            if contract.get("fixture_mount", {}).get("source")
            != "PROPERTY_INSTANCE_MATERIALIZATION"
        )
        static_runners.template["runner_contracts"].remove(
            static_contract
        )

        for label, inputs in {
            "ordinary cases": ordinary_cases,
            "fixtures": fixtures,
            "denominators": denominators,
            "static runners": static_runners,
        }.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    build_evaluation_manifest.ManifestBuildError,
                    "baseline",
                ):
                    inputs.render()

    def test_case_baseline_rejects_same_id_expected_rewrite(self) -> None:
        inputs = self.inputs.clone()
        case = next(
            item
            for item in inputs.template["cases"]
            if item["case_id"] == "EV-AB-ADJACENT-IDENTITY-REUSE"
        )
        case["expected"]["outcome"] = "ACCEPT"

        with self.assertRaisesRegex(
            build_evaluation_manifest.ManifestBuildError,
            "case corpus baseline mismatch",
        ):
            inputs.render()

    def test_property_domain_and_denominator_content_are_frozen(
        self,
    ) -> None:
        property_domain = self.inputs.clone()
        suite = next(
            item
            for item in property_domain.template["property_suites"]
            if item["suite_id"]
            == "PROPERTY-BLOCKER-CLOSURE-EXHAUSTIVE-V1"
        )
        suite["domain"]["owner_role"].pop()
        expected_count = 1
        for values in suite["domain"].values():
            expected_count *= len(values)
        suite["expected_instance_count"] = expected_count

        denominator = self.inputs.clone()
        group = next(
            item
            for item in denominator.template["denominator_groups"]
            if item["group_id"] == "DENOM-ACTIVE-MUST-DETECT"
        )
        group["release_requirement"] = (
            "ALL_EFFECTIVE_ACTIVE_REFERENCE_EXACT"
        )

        for label, inputs in {
            "property domain": property_domain,
            "denominator": denominator,
        }.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    build_evaluation_manifest.ManifestBuildError,
                    "baseline mismatch",
                ):
                    inputs.render()

    def test_conformance_binding_is_resolved_by_stable_id(self) -> None:
        inputs = self.inputs.clone()
        inputs.template["runner_contracts"] = list(
            reversed(inputs.template["runner_contracts"])
        )
        inputs.template["runner_contracts"].insert(
            0,
            inputs.template["runner_contracts"].pop(5),
        )

        rendered = inputs.render()
        matching = [
            contract
            for contract in rendered["runner_contracts"]
            if contract["fixture_mount"]["source"] == "STATIC_CATALOG"
            and any(
                binding["input_binding_id"]
                == "BINDING-ISOLATION-GATE-1-V1"
                for binding in contract["input_bindings"]
            )
        ]
        self.assertEqual(1, len(matching))
        for case in rendered["runner_conformance_cases"]:
            self.assertEqual(
                matching[0]["runner_contract_id"],
                case["invocation"]["runner_contract_id"],
            )
            self.assertEqual(
                "BINDING-ISOLATION-GATE-1-V1",
                case["invocation"]["input_binding_id"],
            )

    def test_every_derived_self_hash_uses_python_rfc8785(self) -> None:
        rendered = self.inputs.clone().render()
        representatives = [
            (
                rendered,
                "manifest_sha256",
                True,
            ),
            (
                rendered["runner_contracts"][0],
                "runner_contract_id",
                True,
            ),
            (
                rendered["property_suites"][0],
                "suite_sha256",
                True,
            ),
            (
                rendered["runner_conformance_cases"][0],
                "case_sha256",
                True,
            ),
            (
                rendered["cases"][0],
                "case_sha256",
                True,
            ),
        ]
        for value, field, prefixed in representatives:
            with self.subTest(field=field):
                self.assertEqual(
                    self_hash(value, field, prefixed=prefixed),
                    value[field],
                )

    def test_cli_defaults_to_check_and_writes_only_when_explicit(self) -> None:
        inputs = self.inputs.clone()
        self.add_same_case_trace_leak(inputs.template)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {
                "evaluation/aegis_v2/evaluation_manifest.v1.json": (
                    serialized(inputs.template)
                ),
                "evaluation/aegis_v2/reference/source_manifest.v1.json": (
                    inputs.source_manifest_raw
                ),
                "evaluation/aegis_v2/fixture_catalog.v1.json": (
                    inputs.fixture_catalog_raw
                ),
                "evaluation/aegis_v2/risk_register.v1.json": (
                    inputs.risk_register_raw
                ),
            }
            paths.update(
                {
                    relative_path: raw
                    for relative_path, raw in (
                        inputs.schema_raw_documents.items()
                    )
                }
            )
            paths[
                "schemas/aegis/v2/schema_bundle.v1.json"
            ] = inputs.schema_bundle_raw
            paths.update(inputs.source_blobs)
            paths.update(inputs.fixture_blobs)
            for relative_path, raw in paths.items():
                target = root / Path(*relative_path.split("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)

            manifest_path = (
                root
                / "evaluation"
                / "aegis_v2"
                / "evaluation_manifest.v1.json"
            )
            before = manifest_path.read_bytes()
            self.assertEqual(
                1,
                build_evaluation_manifest.main(
                    ["--repo-root", str(root)]
                ),
            )
            self.assertEqual(before, manifest_path.read_bytes())
            self.assertEqual(
                1,
                build_evaluation_manifest.main(
                    ["--repo-root", str(root), "--write"]
                ),
            )
            self.assertEqual(before, manifest_path.read_bytes())
            self.assertEqual(
                1,
                build_evaluation_manifest.main(
                    ["--repo-root", str(root)]
                ),
            )

    def test_repository_reader_rejects_windows_junction_escape(
        self,
    ) -> None:
        if os.name != "nt":
            self.skipTest("Windows reparse-point contract")
        import _winapi

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "root"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "secret.json").write_bytes(b"{}")
            junction = root / "linked"
            _winapi.CreateJunction(str(outside), str(junction))

            with self.assertRaisesRegex(
                build_evaluation_manifest.ManifestBuildError,
                "reparse point",
            ):
                build_evaluation_manifest._read_repository_blob(
                    root.resolve(strict=True),
                    "linked/secret.json",
                )

    def test_repository_snapshot_detects_input_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(strict=True)
            path = root / "input.json"
            path.write_bytes(b"old")
            snapshot = {
                "input.json": build_evaluation_manifest._read_repository_blob(
                    root,
                    "input.json",
                )
            }
            path.write_bytes(b"new")

            with self.assertRaisesRegex(
                build_evaluation_manifest.ManifestBuildError,
                "changed before snapshot commit",
            ):
                build_evaluation_manifest._verify_repository_snapshot(
                    root,
                    snapshot,
                )

    def test_schema_directory_membership_is_independent_of_bundle(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(strict=True)
            schema_directory = root / "schemas" / "aegis" / "v2"
            schema_directory.mkdir(parents=True)
            schema_path = schema_directory / "extra.schema.json"
            schema_path.write_bytes(b"{}")

            with self.assertRaisesRegex(
                build_evaluation_manifest.ManifestBuildError,
                "schema directory membership mismatch",
            ):
                build_evaluation_manifest._validate_schema_directory_membership(
                    root,
                    set(),
                )

    def test_schema_directory_guard_rejects_handle_reparse_bit(
        self,
    ) -> None:
        if os.name != "nt":
            self.skipTest("Windows handle attribute contract")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(strict=True)
            (root / "schemas" / "aegis" / "v2").mkdir(parents=True)
            with mock.patch.object(
                build_evaluation_manifest,
                "_windows_handle_is_reparse",
                return_value=True,
            ):
                with self.assertRaisesRegex(
                    build_evaluation_manifest.ManifestBuildError,
                    "handle is a reparse point",
                ):
                    build_evaluation_manifest._schema_directory_membership(
                        root
                    )

    def test_main_normalizes_malformed_input_to_json_invalid(self) -> None:
        class CapturedStdout:
            def __init__(self) -> None:
                self.buffer = io.BytesIO()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = (
                root
                / "evaluation"
                / "aegis_v2"
                / "evaluation_manifest.v1.json"
            )
            target.parent.mkdir(parents=True)
            target.write_bytes(b"{}")
            capture = CapturedStdout()
            original_stdout = sys.stdout
            try:
                sys.stdout = capture
                exit_code = build_evaluation_manifest.main(
                    ["--repo-root", str(root)]
                )
            finally:
                sys.stdout = original_stdout
            report = json.loads(capture.buffer.getvalue())
            self.assertEqual(1, exit_code)
            self.assertEqual("INVALID", report["state"])
            self.assertEqual(
                "EvaluationManifestBuildReport.v1",
                report["schema_version"],
            )
            self.assertEqual(
                "FROZEN_SOURCE_CHANGE_REVIEW_GATE_ONLY",
                report["assurance_boundaries"]["source_ast_policy"],
            )
            self.assertEqual(
                "OS_ISOLATION_REQUIRED",
                report["assurance_boundaries"][
                    "network_filesystem_shell_runtime"
                ],
            )

    def test_candidate_byte_renderer_is_pure_and_jcs_lf(self) -> None:
        rendered = self.inputs.clone().render()
        raw = build_evaluation_manifest.render_evaluation_manifest_bytes(
            rendered
        )
        self.assertEqual(b"\n", raw[-1:])
        self.assertEqual(rendered, json.loads(raw))


if __name__ == "__main__":
    unittest.main()
