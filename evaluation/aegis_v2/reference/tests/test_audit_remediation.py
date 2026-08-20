from __future__ import annotations

import base64
import copy
import re
import unittest
from pathlib import Path


REFERENCE_DIR = Path(__file__).resolve().parents[1]
AEGIS_V2_DIR = REFERENCE_DIR.parent
REPOSITORY_ROOT = AEGIS_V2_DIR.parents[1]

from evaluation.aegis_v2.reference.canonical import (
    jcs_bytes,
    load_json,
    loads_json,
    sha256_hex,
    sha256_hex_bytes,
    verify_self_hash,
    with_self_hash,
)
from evaluation.aegis_v2.reference.schema_validation import local_schema_bundle


MANIFEST_PATH = AEGIS_V2_DIR / "evaluation_manifest.v1.json"
SCHEMA_DIR = REPOSITORY_ROOT / "schemas" / "aegis" / "v2"


def property_suite(suite_id: str) -> dict:
    manifest = load_json(MANIFEST_PATH)
    suite = copy.deepcopy(
        next(
            item
            for item in manifest["property_suites"]
            if item["suite_id"] == suite_id
        )
    )
    return suite


def valid_trace(kind: str = "RECOVERY") -> dict:
    return {
        "schema_version": "ReferenceExecutionTrace.v1",
        "trace_kind": kind,
        "action_id": "ACTION-REFERENCE-001",
        "operation_id": "OPERATION-REFERENCE-001",
        "operation_class": "NON_IDEMPOTENT_JOURNALED",
        "observed_at_utc": "2026-07-27T08:00:00Z",
        "state": {
            "before_sha256": "0" * 64,
            "after_sha256": "1" * 64,
        },
        "effects": [
            {
                "effect_id": "EFFECT-REFERENCE-001",
                "action_id": "ACTION-REFERENCE-001",
                "operation_id": "OPERATION-REFERENCE-001",
                "sequence": 1,
                "payload_sha256": "2" * 64,
                "observation_time_utc": "2026-07-27T08:00:01Z",
            }
        ],
        "events": [
            {
                "event_id": "EVENT-REFERENCE-001",
                "action_id": "ACTION-REFERENCE-001",
                "operation_id": "OPERATION-REFERENCE-001",
                "sequence": 1,
                "event_kind": "EFFECT_COMMITTED",
                "observation_time_utc": "2026-07-27T08:00:01Z",
            }
        ],
        "recovery": {
            "observed_effect_count_before_crash": 1,
            "observed_effect_count_after_recovery": 1,
            "automatic_replay_performed": False,
        },
    }


class GeneratorEnvelopeTests(unittest.TestCase):
    def test_formal_generator_emits_identity_only_envelopes(self) -> None:
        from evaluation.aegis_v2.reference.generator import (
            iter_property_envelopes,
        )

        suite = property_suite("PROPERTY-BLOCKER-CLOSURE-EXHAUSTIVE-V1")
        envelopes = list(iter_property_envelopes(suite))
        self.assertEqual(144, len(envelopes))
        self.assertEqual(set(range(1, 145)), {item["ordinal"] for item in envelopes})
        self.assertEqual(144, len({item["instance_id"] for item in envelopes}))
        self.assertEqual(144, len({jcs_bytes(item) for item in envelopes}))
        self.assertEqual(
            "PROPERTY-BLOCKER-CLOSURE-EXHAUSTIVE-V1-INSTANCE-000001",
            envelopes[0]["case_id"],
        )
        for envelope in envelopes:
            self.assertEqual(
                {
                    "schema_version",
                    "suite_id",
                    "ordinal",
                    "instance_id",
                    "case_id",
                    "assignment",
                    "envelope_sha256",
                },
                set(envelope),
            )
            self.assertTrue(
                verify_self_hash(
                    envelope, "envelope_sha256", prefix=True
                )
            )
            self.assertNotIn("expected", envelope)
            self.assertEqual(
                [],
                local_schema_bundle(str(SCHEMA_DIR.resolve())).errors(
                    envelope, "property_instance_envelope.v1.schema.json"
                ),
            )

    def test_explicit_domain_order_is_independent_of_json_member_order(self) -> None:
        from evaluation.aegis_v2.reference.generator import iter_assignments

        suite = {
            "suite_id": "PROPERTY-TEST-V1",
            "domain": {"b": ["B"], "a": ["A"]},
            "domain_order": ["a", "b"],
        }
        self.assertEqual(
            [{"a": "A", "b": "B"}],
            list(iter_assignments(suite)),
        )

    def test_domain_order_set_and_jcs_values_fail_closed(self) -> None:
        from evaluation.aegis_v2.reference.generator import iter_assignments

        invalid_orders = [
            ["a", "a"],
            ["a"],
            ["a", "b", "c"],
        ]
        for domain_order in invalid_orders:
            with self.subTest(domain_order=domain_order), self.assertRaisesRegex(
                ValueError,
                "domain_order",
            ):
                list(
                    iter_assignments(
                        {
                            "suite_id": "PROPERTY-TEST-V1",
                            "domain": {"b": ["B"], "a": ["A"]},
                            "domain_order": domain_order,
                        }
                    )
                )

        duplicate = {
            "suite_id": "PROPERTY-TEST-V1",
            "domain": {
                "value": [
                    {"a": 1, "b": 2},
                    {"b": 2, "a": 1},
                ]
            },
            "domain_order": ["value"],
        }
        with self.assertRaisesRegex(ValueError, "JCS-duplicate"):
            list(iter_assignments(duplicate))

    def test_property_envelope_accepts_jcs_object_member_order(self) -> None:
        from evaluation.aegis_v2.reference.generator import (
            iter_property_envelopes,
        )
        from evaluation.aegis_v2.reference.materialization import (
            validate_property_envelope,
        )

        suite = property_suite("PROPERTY-BLOCKER-CLOSURE-EXHAUSTIVE-V1")
        envelope = next(iter_property_envelopes(suite))
        canonical_round_trip = loads_json(jcs_bytes(envelope))

        validate_property_envelope(
            canonical_round_trip,
            suite,
            schema_dir=SCHEMA_DIR,
        )


class MaterializerSeparationTests(unittest.TestCase):
    def test_verdict_materializer_outputs_full_valid_runner_input(self) -> None:
        from evaluation.aegis_v2.reference.generator import (
            iter_property_envelopes,
        )
        from evaluation.aegis_v2.reference.materialize_verdict import (
            materialize_verdict_bundle,
        )

        suite = property_suite("PROPERTY-VERDICT-EXHAUSTIVE-V1")
        envelope = next(iter_property_envelopes(suite))
        bundle = materialize_verdict_bundle(
            envelope, suite=suite, schema_dir=SCHEMA_DIR
        )
        self.assertTrue(
            verify_self_hash(bundle, "bundle_sha256", prefix=True)
        )
        self.assertEqual(envelope["instance_id"], bundle["instance_id"])
        self.assertNotIn("assignment", bundle)
        self.assertNotIn("expected", bundle)
        self.assertEqual([], bundle["sut_materialized_fixtures"])
        runner_input = bundle["runner_input"]
        self.assertEqual(
            "BINDING-VERDICT-FUNCTION-1-V1",
            runner_input["input_binding_id"],
        )
        self.assertEqual("VerdictInput.v1", runner_input["subject"]["schema_version"])
        validator = local_schema_bundle(str(SCHEMA_DIR.resolve()))
        self.assertEqual(
            [],
            validator.errors(
                bundle, "property_materialization_bundle.v1.schema.json"
            ),
        )
        self.assertEqual(
            [],
            validator.errors(
                runner_input, "evaluation_runner_input.v1.schema.json"
            ),
        )
        self.assertEqual(
            [],
            validator.errors(runner_input["subject"], "verdict_input.v1.schema.json"),
        )

    def test_closure_materializer_separates_fixture_bytes_and_expected(self) -> None:
        from evaluation.aegis_v2.reference.generator import (
            iter_property_envelopes,
        )
        from evaluation.aegis_v2.reference.materialize_closure import (
            materialize_closure_bundle,
        )

        suite = property_suite(
            "PROPERTY-BLOCKER-CLOSURE-EXHAUSTIVE-V1"
        )
        envelope = next(iter_property_envelopes(suite))
        bundle = materialize_closure_bundle(
            envelope, suite=suite, schema_dir=SCHEMA_DIR
        )
        self.assertTrue(
            verify_self_hash(bundle, "bundle_sha256", prefix=True)
        )
        self.assertNotIn("assignment", bundle)
        self.assertNotIn("expected", bundle)
        runner_input = bundle["runner_input"]
        self.assertEqual(
            "BINDING-BLOCKER-CLOSURE-GATE-1-V1",
            runner_input["input_binding_id"],
        )
        validator = local_schema_bundle(str(SCHEMA_DIR.resolve()))
        self.assertEqual(
            [],
            validator.errors(
                bundle, "property_materialization_bundle.v1.schema.json"
            ),
        )
        self.assertEqual(
            [],
            validator.errors(
                runner_input, "evaluation_runner_input.v1.schema.json"
            ),
        )
        fixtures = bundle["sut_materialized_fixtures"]
        self.assertGreaterEqual(len(fixtures), 6)
        for fixture in fixtures:
            raw = base64.b64decode(fixture["raw_base64"], validate=True)
            self.assertEqual(fixture["byte_size"], len(raw))
            self.assertEqual(
                fixture["raw_sha256"], sha256_hex_bytes(raw)
            )
            self.assertEqual(
                fixture["content_id"],
                f"sha256:{fixture['raw_sha256']}",
            )
        self.assertEqual(
            len(fixtures), len({item["fixture_id"] for item in fixtures})
        )

    def test_expected_record_is_a_third_disjoint_channel(self) -> None:
        from evaluation.aegis_v2.reference.closure import (
            expected_closure_record,
        )
        from evaluation.aegis_v2.reference.generator import (
            iter_property_envelopes,
        )
        from evaluation.aegis_v2.reference.verdict import (
            expected_verdict_record,
        )

        source_manifest = load_json(
            REFERENCE_DIR / "source_manifest.v1.json"
        )
        cases = (
            (
                "PROPERTY-VERDICT-EXHAUSTIVE-V1",
                "ORACLE-VERDICT-PRIORITY-TABLE-V1",
                expected_verdict_record,
            ),
            (
                "PROPERTY-BLOCKER-CLOSURE-EXHAUSTIVE-V1",
                "ORACLE-BLOCKER-CLOSURE-INDEPENDENCE-V1",
                expected_closure_record,
            ),
        )
        for suite_id, oracle_id, assembler in cases:
            suite = property_suite(suite_id)
            envelope = next(iter_property_envelopes(suite))
            oracle_entry = next(
                item
                for item in source_manifest["algorithm_entries"]
                if item["entry_id"] == oracle_id
            )
            record = assembler(
                envelope,
                sut_output_artifact_raw_sha256="a" * 64,
                oracle_source_manifest_entry_sha256=oracle_entry[
                    "entry_sha256"
                ],
            )
            with self.subTest(suite=suite_id):
                self.assertEqual(
                    {
                        "schema_version",
                        "suite_id",
                        "ordinal",
                        "instance_id",
                        "case_id",
                        "envelope_sha256",
                        "oracle_algorithm_id",
                        "oracle_source_manifest_entry_sha256",
                        "generated_after_sut_output_freeze",
                        "sut_output_artifact_raw_sha256",
                        "expected",
                        "record_sha256",
                    },
                    set(record),
                )
                self.assertTrue(
                    verify_self_hash(
                        record, "record_sha256", prefix=True
                    )
                )
                self.assertNotIn("runner_input", record)
                self.assertNotIn("assignment", record)
                self.assertEqual(
                    [],
                    local_schema_bundle(
                        str(SCHEMA_DIR.resolve())
                    ).errors(
                        record,
                        "property_expected_record.v1.schema.json",
                    ),
                )

    def test_materializers_do_not_import_oracle_or_expected_sources(self) -> None:
        for filename in ("materialize_verdict.py", "materialize_closure.py"):
            source = (REFERENCE_DIR / filename).read_text("utf-8")
            with self.subTest(filename=filename):
                self.assertNotRegex(source, r"from \.verdict import")
                self.assertNotRegex(source, r"from \.closure import")
                self.assertNotRegex(source, r"\bexpected\b")
                self.assertNotRegex(source, r"\baegis(?:\.|\b)")


class ClosureChainTests(unittest.TestCase):
    def setUp(self) -> None:
        from evaluation.aegis_v2.reference.generator import (
            iter_property_envelopes,
        )
        from evaluation.aegis_v2.reference.materialize_closure import (
            materialize_closure_bundle,
        )

        suite = property_suite(
            "PROPERTY-BLOCKER-CLOSURE-EXHAUSTIVE-V1"
        )
        self.bundle = materialize_closure_bundle(
            next(iter_property_envelopes(suite)),
            suite=suite,
            schema_dir=SCHEMA_DIR,
        )

    def evaluate(self, bundle: dict) -> dict:
        from evaluation.aegis_v2.reference.closure import (
            evaluate_materialized_closure,
        )

        return evaluate_materialized_closure(bundle, schema_dir=SCHEMA_DIR)

    def rehash(self, bundle: dict) -> dict:
        bundle["sut_materialized_fixtures_jcs_sha256"] = sha256_hex(
            bundle["sut_materialized_fixtures"]
        )
        return with_self_hash(bundle, "bundle_sha256", prefix=True)

    def context(self, bundle: dict) -> dict[str, list[dict]]:
        indexed: dict[str, list[dict]] = {}
        for item in bundle["runner_input"]["context_objects"]:
            indexed.setdefault(item["object_role"], []).append(item["value"])
        return indexed

    def test_complete_registry_to_revision_chain_accepts(self) -> None:
        result = self.evaluate(self.bundle)
        self.assertTrue(result["accepted"], result)

    def test_missing_extra_and_mismatched_chain_links_reject(self) -> None:
        mutations: list[tuple[str, callable]] = [
            (
                "registry",
                lambda b: b["runner_input"]["context_objects"].__setitem__(
                    slice(None),
                    [
                        item
                        for item in b["runner_input"]["context_objects"]
                        if item["object_role"] != "AGENT-REGISTRY"
                    ],
                ),
            ),
            (
                "extra receipt",
                lambda b: b["runner_input"]["context_objects"].append(
                    copy.deepcopy(
                        next(
                            item
                            for item in b["runner_input"]["context_objects"]
                            if item["object_role"] == "OWNER-COMPLETE-RECEIPT"
                        )
                    )
                ),
            ),
            (
                "dispatch",
                lambda b: next(
                    item["value"]
                    for item in b["runner_input"]["context_objects"]
                    if item["object_role"] == "OWNER-DISPATCH"
                ).__setitem__(
                    "action_id", "019fa1ff-ffff-7fff-8fff-ffffffffffff"
                ),
            ),
            (
                "revision",
                lambda b: b["runner_input"]["context_objects"].__setitem__(
                    slice(None),
                    [
                        item
                        for item in b["runner_input"]["context_objects"]
                        if item["object_role"] != "OWNER-EVIDENCE-REVISION-1"
                    ],
                ),
            ),
        ]
        for label, mutate in mutations:
            candidate = copy.deepcopy(self.bundle)
            mutate(candidate)
            with self.subTest(label=label):
                result = self.evaluate(self.rehash(candidate))
                self.assertFalse(result["accepted"], result)

    def test_typed_owner_and_reviewer_preimages_are_distinct_and_bound(self) -> None:
        fixtures = {
            item["fixture_id"]: base64.b64decode(
                item["raw_base64"], validate=True
            )
            for item in self.bundle["sut_materialized_fixtures"]
        }
        owner = fixtures["FIXTURE-OWNER-CORRECTION-PREIMAGE"]
        reviewer = fixtures["FIXTURE-INDEPENDENT-REVIEW-PREIMAGE"]
        self.assertNotEqual(owner, reviewer)
        self.assertEqual(
            "OwnerCorrectionEvidence.v1",
            load_json_bytes(owner)["schema_version"],
        )
        self.assertEqual(
            "IndependentReviewEvidence.v1",
            load_json_bytes(reviewer)["schema_version"],
        )

        candidate = copy.deepcopy(self.bundle)
        owner_fixture = next(
            item
            for item in candidate["sut_materialized_fixtures"]
            if item["fixture_id"] == "FIXTURE-OWNER-CORRECTION-PREIMAGE"
        )
        owner_fixture["raw_base64"] = base64.b64encode(reviewer).decode(
            "ascii"
        )
        owner_fixture["byte_size"] = len(reviewer)
        owner_fixture["raw_sha256"] = sha256_hex_bytes(reviewer)
        owner_fixture["jcs_sha256"] = sha256_hex(load_json_bytes(reviewer))
        owner_fixture["content_id"] = f"sha256:{owner_fixture['raw_sha256']}"
        result = self.evaluate(self.rehash(candidate))
        self.assertFalse(result["accepted"], result)
        self.assertTrue(
            any("OWNER-OBLIGATION" in item for item in result["reason_ids"]),
            result,
        )

    def test_prohibited_substitute_self_report_and_event_reorder_reject(self) -> None:
        candidate = copy.deepcopy(self.bundle)
        owner_fixture = next(
            item
            for item in candidate["sut_materialized_fixtures"]
            if item["fixture_id"] == "FIXTURE-OWNER-CORRECTION-PREIMAGE"
        )
        payload = load_json_bytes(
            base64.b64decode(owner_fixture["raw_base64"], validate=True)
        )
        payload["prohibited_substitutes_used"] = []
        raw = jcs_bytes(payload)
        owner_fixture["raw_base64"] = base64.b64encode(raw).decode("ascii")
        owner_fixture["byte_size"] = len(raw)
        owner_fixture["raw_sha256"] = sha256_hex_bytes(raw)
        owner_fixture["jcs_sha256"] = sha256_hex(payload)
        owner_fixture["content_id"] = f"sha256:{owner_fixture['raw_sha256']}"
        result = self.evaluate(self.rehash(candidate))
        self.assertFalse(result["accepted"], result)
        self.assertIn(
            "REASON-PROHIBITED-SUBSTITUTE-SELF-REPORT-FORBIDDEN",
            result["reason_ids"],
        )

        candidate = copy.deepcopy(self.bundle)
        event = next(
            item["value"]
            for item in candidate["runner_input"]["context_objects"]
            if item["object_role"] == "CLOSURE-EVENT"
        )
        event["recorded_event_id"] = (
            "019fa1ff-0000-7000-8000-000000000001"
        )
        event = with_self_hash(
            event, "closure_event_content_id", prefix=True
        )
        next(
            item
            for item in candidate["runner_input"]["context_objects"]
            if item["object_role"] == "CLOSURE-EVENT"
        )["value"] = event
        result = self.evaluate(self.rehash(candidate))
        self.assertIn(
            "REASON-CLOSURE-EVENT-ORDER-NOT-APPEND-ONLY",
            result["reason_ids"],
        )


def load_json_bytes(raw: bytes) -> dict:
    value = loads_json(raw)
    if not isinstance(value, dict):
        raise AssertionError("fixture JSON must be an object")
    return value


class TraceOracleTests(unittest.TestCase):
    def test_expected_and_actual_validate_before_normalization(self) -> None:
        from evaluation.aegis_v2.reference.comparator import (
            compare_reference_traces,
        )

        expected = valid_trace()
        actual = copy.deepcopy(expected)
        actual["recovery"]["observed_effect_count_after_recovery"] = True
        comparison = compare_reference_traces(
            expected,
            actual,
            "DROP_OBSERVATION_TIME_ONLY_KEEP_ORDER_AND_IDENTITIES",
            "RECOVERY",
        )
        self.assertFalse(comparison["equal"])
        self.assertTrue(comparison["actual_validation_errors"])
        self.assertTrue(
            any("boolean" in item for item in comparison["actual_validation_errors"])
        )

    def test_recursive_identity_and_pointer_whitelist_are_strict(self) -> None:
        from evaluation.aegis_v2.reference.comparator import (
            compare_reference_traces,
            normalize_reference_trace,
        )

        expected = valid_trace()
        actual = copy.deepcopy(expected)
        actual["events"][0]["operation_id"] = "OPERATION-OTHER"
        result = compare_reference_traces(
            expected,
            actual,
            "DROP_OBSERVATION_TIME_ONLY_KEEP_ORDER_AND_IDENTITIES",
            "RECOVERY",
        )
        self.assertFalse(result["equal"])
        self.assertTrue(
            any("operation_id" in item for item in result["actual_validation_errors"])
        )

        unexpected = copy.deepcopy(expected)
        unexpected["state"]["observed_at_utc"] = "2026-07-27T09:00:00Z"
        with self.assertRaisesRegex(ValueError, "not whitelisted"):
            normalize_reference_trace(
                unexpected,
                "DROP_OBSERVATION_TIME_ONLY_KEEP_ORDER_AND_IDENTITIES",
            )

    def test_state_effect_and_event_oracles_are_independent(self) -> None:
        from evaluation.aegis_v2.reference.comparator import (
            compare_reference_traces,
        )

        expected = valid_trace()
        state_changed = copy.deepcopy(expected)
        state_changed["state"]["after_sha256"] = "f" * 64
        result = compare_reference_traces(
            expected,
            state_changed,
            "DROP_OBSERVATION_TIME_ONLY_KEEP_ORDER_AND_IDENTITIES",
            "RECOVERY",
        )
        self.assertFalse(result["state_equal"])
        self.assertTrue(result["effect_equal"])
        self.assertTrue(result["event_equal"])

        expected = valid_trace("SIDE_EFFECT")
        effect_changed = copy.deepcopy(expected)
        effect_changed["effects"].append(
            {
                **copy.deepcopy(effect_changed["effects"][0]),
                "effect_id": "EFFECT-REFERENCE-002",
                "sequence": 2,
            }
        )
        effect_changed["recovery"][
            "observed_effect_count_after_recovery"
        ] = 2
        result = compare_reference_traces(
            expected,
            effect_changed,
            "DROP_OBSERVATION_TIME_ONLY_KEEP_ORDER_AND_IDENTITIES",
            "SIDE_EFFECT",
        )
        self.assertFalse(result["effect_equal"])
        self.assertIn(
            "SIDE-EFFECT-NONIDEMPOTENT-MULTIPLE-EFFECTS",
            result["audit_issue_ids"],
        )

        event_changed = copy.deepcopy(expected)
        event_changed["events"].append(
            {
                **copy.deepcopy(event_changed["events"][0]),
                "event_id": "EVENT-REFERENCE-002",
                "sequence": 2,
                "event_kind": "RECEIPT_COMMITTED",
            }
        )
        result = compare_reference_traces(
            expected,
            event_changed,
            "DROP_OBSERVATION_TIME_ONLY_KEEP_ORDER_AND_IDENTITIES",
            "RECOVERY",
        )
        self.assertFalse(result["event_equal"])


class FrozenBindingTests(unittest.TestCase):
    def test_source_manifest_schema_accepts_complete_runtime_fixture(self) -> None:
        manifest = load_json(REFERENCE_DIR / "source_manifest.v1.json")
        self.assertEqual(
            [],
            local_schema_bundle(str(SCHEMA_DIR.resolve())).errors(
                manifest,
                "reference_source_manifest.v1.schema.json",
            ),
        )
        for binding_name in ("pyproject", "lock", "schema_bundle"):
            binding = manifest["runtime_binding"][binding_name]
            raw = (
                REPOSITORY_ROOT / binding["repository_path"]
            ).read_bytes()
            self.assertEqual(len(raw), binding["byte_size"])
            self.assertEqual(
                sha256_hex_bytes(raw), binding["raw_sha256"]
            )

    def test_source_manifest_has_runtime_lock_schema_and_sorted_ids(self) -> None:
        manifest = load_json(REFERENCE_DIR / "source_manifest.v1.json")
        self.assertEqual(
            "pylock.windows-py313.toml",
            manifest["runtime_binding"]["lock"]["repository_path"],
        )
        self.assertEqual(
            "AEGIS-V2-SCHEMA-BUNDLE-ROOT",
            manifest["runtime_binding"]["schema_bundle"]["bundle_id"],
        )
        self.assertIn(
            "referencing",
            {
                item["name"]
                for item in manifest["runtime_binding"][
                    "resolved_distributions"
                ]
            },
        )
        self.assertEqual(
            sorted(item["entry_id"] for item in manifest["algorithm_entries"]),
            [item["entry_id"] for item in manifest["algorithm_entries"]],
        )
        self.assertEqual(
            sorted(item["comparator_id"] for item in manifest["comparator_specs"]),
            [item["comparator_id"] for item in manifest["comparator_specs"]],
        )

    def test_entry_and_spec_bindings_are_bidirectional(self) -> None:
        from evaluation.aegis_v2.reference.manifest import (
            verify_bidirectional_bindings,
        )

        source_manifest = load_json(
            REFERENCE_DIR / "source_manifest.v1.json"
        )
        evaluation_manifest = load_json(MANIFEST_PATH)
        result = verify_bidirectional_bindings(
            source_manifest, evaluation_manifest
        )
        self.assertTrue(result["valid"], result)
        self.assertEqual([], result["unreferenced_entry_ids"])
        self.assertEqual([], result["missing_entry_ids"])
        self.assertEqual([], result["hash_mismatch_ids"])


class CoverageAccountingTests(unittest.TestCase):
    def test_coverage_accounting_has_exact_denominators(self) -> None:
        from evaluation.aegis_v2.reference.coverage import (
            build_coverage_accounting,
        )

        accounting = build_coverage_accounting()
        self.assertEqual(552_960, accounting["verdict_assignment_denominator"])
        self.assertEqual(144, accounting["closure_assignment_denominator"])
        self.assertEqual(91, accounting["priority_pair_denominator"])
        self.assertEqual(
            91,
            accounting["priority_pair_reachable"]
            + accounting["priority_pair_contract_incompatible"],
        )
        self.assertGreater(accounting["invalid_closure_cases"], 0)
        self.assertGreater(accounting["ef_chain_cases"], 0)
        self.assertGreater(accounting["cancellation_cases"], 0)
        self.assertNotIn("EXHAUSTIVE_SEMANTIC_STATE_SPACE", jcs_bytes(accounting).decode())


if __name__ == "__main__":
    unittest.main()
