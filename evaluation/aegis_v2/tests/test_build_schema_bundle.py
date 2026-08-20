from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import rfc8785


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "build_schema_bundle.py"
)
SPEC = importlib.util.spec_from_file_location(
    "aegis_v2_build_schema_bundle",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
build_schema_bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_schema_bundle)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        + b"\n"
    )


def template_bundle() -> dict:
    return {
        "schema_version": "SchemaBundle.v1",
        "bundle_id": "AEGIS-V2-SCHEMA-BUNDLE-ROOT",
        "hash_contract": {
            "algorithm": "SHA-256",
            "canonicalization": "RFC8785-JCS",
            "scope": "WHOLE_BUNDLE_WITH_BUNDLE_SHA256_OMITTED",
            "schema_entry_byte_size_preimage": "RFC8785_JCS_UTF8",
            "schema_entry_sha256_preimage": "RFC8785_JCS_UTF8",
        },
        "resolution_policy": {
            "all_schema_ids_preloaded_locally": True,
            "network_resolution_allowed": False,
            "unknown_schema_id_action": "REJECT",
        },
        "codex_protocol_contract": {
            "codex_cli_version": "0.145.0",
            "generated_bundle_jcs_sha256": (
                "sha256:"
                "1bc09dedc506075562d4d49b702ecab6d947dd5a8c2a9014a5cde592a0938efb"
            ),
            "raw_bundle_hash_is_compatibility_key": False,
        },
        "schemas": [],
        "bundle_sha256": "sha256:" + "0" * 64,
    }


def write_single_schema(root: Path) -> None:
    write_json(
        root / "schemas" / "aegis" / "v2" / "only.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://example.invalid/only.schema.json",
            "type": "boolean",
        },
    )


def resign_bundle(bundle: dict) -> None:
    unsigned = copy.deepcopy(bundle)
    unsigned.pop("bundle_sha256")
    bundle["bundle_sha256"] = (
        "sha256:" + hashlib.sha256(rfc8785.dumps(unsigned)).hexdigest()
    )


def run_check(root: Path) -> tuple[int, dict]:
    class CapturedStdout:
        def __init__(self) -> None:
            self.buffer = io.BytesIO()

    captured = CapturedStdout()
    with mock.patch.object(sys, "stdout", captured):
        exit_code = build_schema_bundle.main(
            ["--repo-root", str(root), "--check"]
        )
    return exit_code, json.loads(captured.buffer.getvalue())


class SchemaBundleRenderTests(unittest.TestCase):
    def test_render_covers_all_schemas_sorted_with_jcs_preimages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schema_dir = root / "schemas" / "aegis" / "v2"
            schema_b = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://example.invalid/b.schema.json",
                "type": "object",
                "properties": {"emoji": {"const": "😀"}},
            }
            schema_a = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://example.invalid/a.schema.json",
                "type": "array",
            }
            write_json(schema_dir / "b.schema.json", schema_b)
            write_json(schema_dir / "a.schema.json", schema_a)

            rendered = build_schema_bundle.render_schema_bundle(
                repository_root=root,
                template=template_bundle(),
            )

            expected_paths = [
                "schemas/aegis/v2/a.schema.json",
                "schemas/aegis/v2/b.schema.json",
            ]
            self.assertEqual(
                expected_paths,
                [entry["path"] for entry in rendered["schemas"]],
            )
            for entry, schema in zip(
                rendered["schemas"],
                (schema_a, schema_b),
                strict=True,
            ):
                canonical = rfc8785.dumps(schema)
                self.assertEqual(len(canonical), entry["byte_size"])
                self.assertEqual(
                    "sha256:" + hashlib.sha256(canonical).hexdigest(),
                    entry["sha256"],
                )
            self.assertEqual(
                "RFC8785_JCS_UTF8",
                rendered["hash_contract"][
                    "schema_entry_byte_size_preimage"
                ],
            )
            self.assertEqual(
                "RFC8785_JCS_UTF8",
                rendered["hash_contract"][
                    "schema_entry_sha256_preimage"
                ],
            )
            unsigned = copy.deepcopy(rendered)
            unsigned.pop("bundle_sha256")
            self.assertEqual(
                "sha256:" + hashlib.sha256(rfc8785.dumps(unsigned)).hexdigest(),
                rendered["bundle_sha256"],
            )

    def test_render_is_idempotent_and_does_not_mutate_template(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_single_schema(root)
            template = template_bundle()
            original = copy.deepcopy(template)
            first = build_schema_bundle.render_schema_bundle(
                repository_root=root,
                template=template,
            )
            second = build_schema_bundle.render_schema_bundle(
                repository_root=root,
                template=first,
            )
            self.assertEqual(original, template)
            self.assertEqual(first, second)
            self.assertTrue(
                build_schema_bundle.bundle_matches_expected(
                    observed=first,
                    expected=second,
                )
            )

    def test_rejects_duplicate_member_bom_and_crlf(self) -> None:
        malformed = {
            "duplicate.schema.json": (
                b'{"$id":"https://example.invalid/x",'
                b'"type":"object","type":"array"}\n'
            ),
            "bom.schema.json": (
                b"\xef\xbb\xbf"
                b'{"$id":"https://example.invalid/x","type":"object"}\n'
            ),
            "crlf.schema.json": (
                b'{\r\n"$id":"https://example.invalid/x",'
                b'\r\n"type":"object"\r\n}\r\n'
            ),
        }
        for filename, raw in malformed.items():
            with self.subTest(filename=filename):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    path = (
                        root
                        / "schemas"
                        / "aegis"
                        / "v2"
                        / filename
                    )
                    path.parent.mkdir(parents=True)
                    path.write_bytes(raw)
                    with self.assertRaises(
                        build_schema_bundle.BundleBuildError
                    ):
                        build_schema_bundle.render_schema_bundle(
                            repository_root=root,
                            template=template_bundle(),
                        )

    def test_check_reports_stale_observed_bundle(self) -> None:
        expected = template_bundle()
        observed = copy.deepcopy(expected)
        observed["bundle_sha256"] = "sha256:" + "1" * 64
        self.assertFalse(
            build_schema_bundle.bundle_matches_expected(
                observed=observed,
                expected=expected,
            )
        )

    def test_check_rejects_resigned_static_tampering_as_invalid(self) -> None:
        def change_schema_version(bundle: dict) -> None:
            bundle["schema_version"] = "SchemaBundle.v999"

        def allow_network_resolution(bundle: dict) -> None:
            bundle["resolution_policy"][
                "network_resolution_allowed"
            ] = True

        cases = {
            "schema_version": change_schema_version,
            "network_resolution_allowed": allow_network_resolution,
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    write_single_schema(root)
                    observed = (
                        build_schema_bundle.render_schema_bundle(
                            repository_root=root,
                            template=template_bundle(),
                        )
                    )
                    mutate(observed)
                    resign_bundle(observed)
                    write_json(
                        root / build_schema_bundle.BUNDLE_PATH,
                        observed,
                    )

                    exit_code, report = run_check(root)

                    self.assertEqual("INVALID", report["state"])
                    self.assertEqual(1, exit_code)

    def test_render_rejects_static_policy_shape_or_value_damage(
        self,
    ) -> None:
        valid_policy = template_bundle()["resolution_policy"]
        missing_field = copy.deepcopy(valid_policy)
        missing_field.pop("all_schema_ids_preloaded_locally")
        extra_field = copy.deepcopy(valid_policy)
        extra_field["network_resolution"] = "FORBIDDEN"
        wrong_field = copy.deepcopy(valid_policy)
        wrong_field["unknown_schema_id_action"] = "ALLOW"
        wrong_type = copy.deepcopy(valid_policy)
        wrong_type["network_resolution_allowed"] = 0

        cases = {
            "missing_field": missing_field,
            "extra_field": extra_field,
            "wrong_field": wrong_field,
            "wrong_type": wrong_type,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_single_schema(root)
            for name, policy in cases.items():
                with self.subTest(name=name):
                    damaged = template_bundle()
                    damaged["resolution_policy"] = policy

                    with self.assertRaisesRegex(
                        build_schema_bundle.BundleBuildError,
                        "resolution_policy",
                    ):
                        build_schema_bundle.render_schema_bundle(
                            repository_root=root,
                            template=damaged,
                        )

    def test_render_rejects_instead_of_inheriting_static_damage(
        self,
    ) -> None:
        cases = {
            "schema_version": ("schema_version", "SchemaBundle.v999"),
            "bundle_id": ("bundle_id", "ATTACKER-BUNDLE"),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_single_schema(root)
            for name, (field, value) in cases.items():
                with self.subTest(name=name):
                    damaged = template_bundle()
                    damaged[field] = value

                    with self.assertRaisesRegex(
                        build_schema_bundle.BundleBuildError,
                        field,
                    ):
                        build_schema_bundle.render_schema_bundle(
                            repository_root=root,
                            template=damaged,
                        )


if __name__ == "__main__":
    unittest.main()
