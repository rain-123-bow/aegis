from __future__ import annotations

import copy
import io
import json
import re
import sys
import unittest
from pathlib import Path


REFERENCE_DIR = Path(__file__).resolve().parents[1]
AEGIS_V2_DIR = REFERENCE_DIR.parent
REPOSITORY_ROOT = AEGIS_V2_DIR.parents[1]

from evaluation.aegis_v2.reference.canonical import (
    content_id,
    load_json,
    sha256_hex_bytes,
    verify_self_hash,
    with_self_hash,
)
from evaluation.aegis_v2.reference.closure import (
    evaluate_closure,
    evaluate_closure_assignment,
)
from evaluation.aegis_v2.reference.comparator import (
    compare_outputs,
    compare_reference_traces,
)
from evaluation.aegis_v2.reference.cli import emit_jsonl
from evaluation.aegis_v2.reference.generator import (
    count_instances,
    instance_id,
    iter_assignments,
    iter_property_envelopes,
)
from evaluation.aegis_v2.reference.manifest import load_manifest, property_suite
from evaluation.aegis_v2.reference.schema_validation import local_schema_bundle
from evaluation.aegis_v2.reference.verdict import (
    FACT_MASK_BITS,
    evaluate_verdict_assignment,
)


MANIFEST_PATH = AEGIS_V2_DIR / "evaluation_manifest.v1.json"
SCHEMA_DIR = REPOSITORY_ROOT / "schemas" / "aegis" / "v2"
FIXTURE_CATALOG_PATH = AEGIS_V2_DIR / "fixture_catalog.v1.json"
SOURCE_MANIFEST_PATH = REFERENCE_DIR / "source_manifest.v1.json"


class GeneratorContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_manifest(MANIFEST_PATH)

    def test_verdict_cartesian_count_and_manifest_order(self) -> None:
        suite = property_suite(
            self.manifest, "PROPERTY-VERDICT-EXHAUSTIVE-V1"
        )
        self.assertEqual(552_960, count_instances(suite))

        iterator = iter_assignments(suite)
        first = next(iterator)
        last = first
        observed_count = 1
        for last in iterator:
            observed_count += 1

        self.assertEqual(552_960, observed_count)
        self.assertEqual(
            {name: values[0] for name, values in suite["domain"].items()},
            first,
        )
        self.assertEqual(
            {name: values[-1] for name, values in suite["domain"].items()},
            last,
        )
        self.assertEqual(
            instance_id(suite["suite_id"], first),
            instance_id(suite["suite_id"], copy.deepcopy(first)),
        )
        envelope = next(iter_property_envelopes(suite))
        self.assertEqual(
            [],
            local_schema_bundle(str(SCHEMA_DIR.resolve())).errors(
                envelope, "property_instance_envelope.v1.schema.json"
            ),
        )
        self.assertNotIn("expected", envelope)
        self.assertNotIn("runner_input", envelope)

    def test_blocker_closure_cartesian_count_and_order(self) -> None:
        suite = property_suite(
            self.manifest, "PROPERTY-BLOCKER-CLOSURE-EXHAUSTIVE-V1"
        )
        assignments = list(iter_assignments(suite))
        self.assertEqual(144, count_instances(suite))
        self.assertEqual(144, len(assignments))
        self.assertEqual(
            {name: values[0] for name, values in suite["domain"].items()},
            assignments[0],
        )
        self.assertEqual(
            {name: values[-1] for name, values in suite["domain"].items()},
            assignments[-1],
        )
        envelope = next(iter_property_envelopes(suite))
        self.assertEqual(
            [],
            local_schema_bundle(str(SCHEMA_DIR.resolve())).errors(
                envelope,
                "property_instance_envelope.v1.schema.json",
            ),
        )

    def test_jsonl_emission_is_byte_deterministic(self) -> None:
        suite = property_suite(
            self.manifest, "PROPERTY-BLOCKER-CLOSURE-EXHAUSTIVE-V1"
        )
        records = list(iter_property_envelopes(suite))[:2]
        first = io.BytesIO()
        second = io.BytesIO()
        emit_jsonl(records, first)
        emit_jsonl(copy.deepcopy(records), second)
        self.assertEqual(first.getvalue(), second.getvalue())
        self.assertEqual(2, first.getvalue().count(b"\n"))


class VerdictOracleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = {
            "cancel_state": "NOT_REQUESTED",
            "workflow_integrity": "VALID",
            "evidence_state": "COMPLETE",
            "coverage_state": "COMPLETE",
            "report_state": "APPROVED",
            "workflow_phase": "TERMINAL_EVALUATION",
            "fact_mask": "FACT-MASK-000",
        }

    def decision(self, **changes: str) -> dict:
        assignment = self.base | changes
        return evaluate_verdict_assignment(assignment)

    def test_fact_mask_mapping_is_complete_and_non_overlapping(self) -> None:
        self.assertEqual(7, len(FACT_MASK_BITS))
        self.assertEqual(set(range(7)), set(FACT_MASK_BITS.values()))

    def test_priority_conflicts_use_first_matching_level(self) -> None:
        requested = self.decision(
            cancel_state="REQUESTED",
            workflow_integrity="INVALID",
            evidence_state="INVALID",
            fact_mask="FACT-MASK-127",
        )
        self.assertEqual("CANCEL-REQUESTED", requested["priority_condition"])
        self.assertEqual("KERNEL_CANCEL_COORDINATOR", requested["decision"]["target_node"])

        integrity = self.decision(
            workflow_integrity="UNKNOWN", fact_mask="FACT-MASK-127"
        )
        self.assertEqual("INTEGRITY", integrity["priority_condition"])
        self.assertEqual(
            "INTERNAL_INTEGRITY_ERROR", integrity["decision"]["verdict"]
        )

        blocker_stagnation = self.decision(fact_mask="FACT-MASK-012")
        self.assertEqual(
            "BLOCKER-STAGNATION", blocker_stagnation["priority_condition"]
        )

        evidence = self.decision(
            evidence_state="STALE", fact_mask="FACT-MASK-096"
        )
        self.assertEqual("EVIDENCE-INVALID", evidence["priority_condition"])

        phase = self.decision(
            workflow_phase="PLAN_REVIEW",
            report_state="NOT_READY",
            coverage_state="INCOMPLETE",
        )
        self.assertEqual("PHASE-ROUTE", phase["priority_condition"])
        self.assertEqual("B", phase["decision"]["target_node"])

        gap = self.decision(fact_mask="FACT-MASK-096")
        self.assertEqual("REQUIRED-ENV-GAP", gap["priority_condition"])
        self.assertEqual("BLOCKED_ENVIRONMENT", gap["decision"]["verdict"])

        finding = self.decision(fact_mask="FACT-MASK-064")
        self.assertEqual("FINDING", finding["priority_condition"])
        self.assertEqual("FAIL_PRODUCT", finding["decision"]["verdict"])

        passed = self.decision()
        self.assertEqual("PASS", passed["priority_condition"])
        self.assertEqual("PASS", passed["decision"]["verdict"])

        fallback = self.decision(evidence_state="PARTIAL")
        self.assertEqual("FALLBACK", fallback["priority_condition"])
        self.assertEqual(
            "NEEDS_MASTER_USER_DISCUSSION", fallback["decision"]["verdict"]
        )

    def test_all_fourteen_priority_levels_are_reachable(self) -> None:
        from evaluation.aegis_v2.reference.materialize_verdict import (
            _verdict_candidate,
        )
        from evaluation.aegis_v2.reference.verdict import (
            evaluate_verdict_input,
        )

        assignments = [
            {"cancel_state": "REQUESTED"},
            {"cancel_state": "TERMINATED_WITH_ACTIVE_WORK"},
            {"cancel_state": "QUIESCENT"},
            {"workflow_integrity": "INVALID"},
            {"fact_mask": "FACT-MASK-001"},
            {"fact_mask": "FACT-MASK-012"},
            {"fact_mask": "FACT-MASK-004"},
            {"evidence_state": "INVALID"},
            {
                "workflow_phase": "TEST_EXECUTION",
                "report_state": "NOT_READY",
            },
            {"fact_mask": "FACT-MASK-032"},
            {"fact_mask": "FACT-MASK-064"},
            {},
            {"evidence_state": "PARTIAL"},
        ]
        observed = [
            self.decision(**assignment)["priority_rank"]
            for assignment in assignments
        ]
        self.assertEqual(
            [*range(1, 10), *range(11, 15)], observed
        )
        terminal_ef_invalid = _verdict_candidate(
            copy.deepcopy(self.base)
        )
        terminal_ef_invalid["final_review_id"] = None
        self.assertEqual(
            10,
            evaluate_verdict_input(terminal_ef_invalid)[
                "priority_rank"
            ],
        )

    def test_exact_reason_and_assertion_order_is_canonical(self) -> None:
        result = self.decision(cancel_state="QUIESCING")
        self.assertEqual(
            sorted(result["reason_ids"]), result["reason_ids"]
        )
        self.assertEqual(
            sorted(result["assertion_ids"]), result["assertion_ids"]
        )


class ClosureOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        case = next(
            item
            for item in manifest["cases"]
            if item["case_id"]
            == "EV-B20-BLOCKER-CLOSURE-INDEPENDENT-VALID"
        )
        cls.blocker = copy.deepcopy(case["input"]["subject"])
        contexts = {
            item["object_role"]: copy.deepcopy(item["value"])
            for item in case["input"]["context_objects"]
        }
        cls.event = contexts["CLOSURE-EVENT"]
        cls.evidence_records = {
            contexts["OWNER-EVIDENCE"]["evidence_id"]: contexts["OWNER-EVIDENCE"],
            contexts["REVIEWER-EVIDENCE"]["evidence_id"]: contexts[
                "REVIEWER-EVIDENCE"
            ],
        }

        catalog = json.loads(FIXTURE_CATALOG_PATH.read_text(encoding="utf-8"))
        sha = contexts["OWNER-EVIDENCE"]["content"]["sha256"]
        fixture = next(
            item for item in catalog["fixtures"] if item["raw_sha256"] == sha
        )
        raw = (REPOSITORY_ROOT / fixture["repository_path"]).read_bytes()
        cls.evidence_bytes = {
            contexts["OWNER-EVIDENCE"]["evidence_id"]: raw,
            contexts["REVIEWER-EVIDENCE"]["evidence_id"]: raw,
        }
        cls.propagation = {
            "source_blocker_content_id": content_id(cls.blocker),
            "severity": cls.blocker["severity"],
            "invalidated_artifact_ids": sorted(
                item["artifact_id"]
                for item in cls.blocker["affected_artifacts"]
            ),
            "invalidated_case_ids": sorted(cls.blocker["affected_case_ids"]),
            "prohibited_substitutes_used": [],
        }

    def test_144_assignment_oracle_requires_independence_and_two_evidence_sets(
        self,
    ) -> None:
        valid = {
            "origin_role": "B",
            "owner_role": "A",
            "reviewer_relation": "INDEPENDENT",
            "owner_evidence": "PRESENT_VALID",
            "reviewer_evidence": "PRESENT_VALID",
        }
        self.assertEqual("ACCEPT", evaluate_closure_assignment(valid)["outcome"])
        for field in (
            "reviewer_relation",
            "owner_evidence",
            "reviewer_evidence",
        ):
            mutated = copy.deepcopy(valid)
            mutated[field] = (
                "ORIGIN_OR_OWNER"
                if field == "reviewer_relation"
                else "MISSING_OR_INVALID"
            )
            self.assertEqual(
                "REJECT", evaluate_closure_assignment(mutated)["outcome"]
            )

    def test_full_closure_accepts_only_bound_independent_evidence(self) -> None:
        result = evaluate_closure(
            self.blocker,
            self.event,
            self.evidence_records,
            self.evidence_bytes,
            self.propagation,
            schema_dir=SCHEMA_DIR,
        )
        self.assertTrue(result["accepted"], result)
        self.assertEqual([], result["reason_ids"])

    def test_closure_mutations_are_detected_independently(self) -> None:
        same_physical_reviewer = copy.deepcopy(self.event)
        same_physical_reviewer["reviewer_identity"]["thread_id"] = (
            same_physical_reviewer["owner_identity"]["thread_id"]
        )
        same_physical_reviewer["reviewer_identity"]["session_id"] = (
            same_physical_reviewer["owner_identity"]["session_id"]
        )
        same_physical_reviewer = with_self_hash(
            same_physical_reviewer, "closure_event_content_id", prefix=True
        )
        result = evaluate_closure(
            self.blocker,
            same_physical_reviewer,
            self.evidence_records,
            self.evidence_bytes,
            self.propagation,
            schema_dir=SCHEMA_DIR,
        )
        self.assertIn("REASON-REVIEWER-PHYSICAL-IDENTITY-REUSED", result["reason_ids"])

        bad_bytes = dict(self.evidence_bytes)
        bad_bytes["EVIDENCE-OWNER-CORRECTION"] = b"single-byte mutation"
        result = evaluate_closure(
            self.blocker,
            self.event,
            self.evidence_records,
            bad_bytes,
            self.propagation,
            schema_dir=SCHEMA_DIR,
        )
        self.assertIn("REASON-OWNER-EVIDENCE-CONTENT-HASH-MISMATCH", result["reason_ids"])

        bad_propagation = copy.deepcopy(self.propagation)
        bad_propagation["invalidated_case_ids"] = []
        result = evaluate_closure(
            self.blocker,
            self.event,
            self.evidence_records,
            self.evidence_bytes,
            bad_propagation,
            schema_dir=SCHEMA_DIR,
        )
        self.assertIn("REASON-DEPENDENCY-CASE-PROPAGATION-MISMATCH", result["reason_ids"])


class ComparatorTests(unittest.TestCase):
    def test_output_schema_self_hash_and_exact_array_order(self) -> None:
        expected = with_self_hash(
            {
                "schema_version": "SutDecision.v1",
                "outcome": "ACCEPT",
                "decision": None,
                "reason_ids": ["REASON-A", "REASON-B"],
                "assertion_ids": ["ASSERT-A", "ASSERT-B"],
            },
            "sut_decision_sha256",
        )
        equal = compare_outputs(expected, copy.deepcopy(expected), SCHEMA_DIR)
        self.assertTrue(equal["equal"], equal)

        reordered = copy.deepcopy(expected)
        reordered["reason_ids"].reverse()
        reordered = with_self_hash(reordered, "sut_decision_sha256")
        mismatch = compare_outputs(expected, reordered, SCHEMA_DIR)
        self.assertFalse(mismatch["equal"])
        self.assertIn(
            "REASON-ORDER-OR-VALUE-MISMATCH", mismatch["mismatch_ids"]
        )

        reordered = copy.deepcopy(expected)
        reordered["assertion_ids"].reverse()
        reordered = with_self_hash(reordered, "sut_decision_sha256")
        mismatch = compare_outputs(expected, reordered, SCHEMA_DIR)
        self.assertIn(
            "ASSERTION-ORDER-OR-VALUE-MISMATCH", mismatch["mismatch_ids"]
        )

        wrong_hash = copy.deepcopy(expected)
        wrong_hash["sut_decision_sha256"] = "0" * 64
        mismatch = compare_outputs(expected, wrong_hash, SCHEMA_DIR)
        self.assertIn(
            "SUT-DECISION-SELF-HASH-MISMATCH", mismatch["mismatch_ids"]
        )

    def test_recovery_trace_drops_only_observation_time_and_preserves_order(
        self,
    ) -> None:
        expected = {
            "schema_version": "ReferenceExecutionTrace.v1",
            "trace_kind": "RECOVERY",
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
                },
                {
                    "event_id": "EVENT-REFERENCE-002",
                    "action_id": "ACTION-REFERENCE-001",
                    "operation_id": "OPERATION-REFERENCE-001",
                    "sequence": 2,
                    "event_kind": "RECEIPT_COMMITTED",
                    "observation_time_utc": "2026-07-27T08:00:02Z",
                },
            ],
            "recovery": {
                "observed_effect_count_before_crash": 1,
                "observed_effect_count_after_recovery": 1,
                "automatic_replay_performed": False,
            },
        }
        actual = copy.deepcopy(expected)
        actual["observed_at_utc"] = "2026-07-27T08:00:10Z"
        comparison = compare_reference_traces(
            expected,
            actual,
            "DROP_OBSERVATION_TIME_ONLY_KEEP_ORDER_AND_IDENTITIES",
            "RECOVERY",
        )
        self.assertTrue(comparison["equal"], comparison)

        actual["events"].reverse()
        comparison = compare_reference_traces(
            expected,
            actual,
            "DROP_OBSERVATION_TIME_ONLY_KEEP_ORDER_AND_IDENTITIES",
            "RECOVERY",
        )
        self.assertFalse(comparison["equal"])

        side_effect_expected = copy.deepcopy(expected)
        side_effect_expected["trace_kind"] = "SIDE_EFFECT"
        duplicate_effect = copy.deepcopy(side_effect_expected)
        duplicate_effect["trace_kind"] = "SIDE_EFFECT"
        duplicate_effect["effects"].append(
            {
                **copy.deepcopy(duplicate_effect["effects"][0]),
                "effect_id": "EFFECT-REFERENCE-002",
                "sequence": 2,
            }
        )
        duplicate_effect["recovery"][
            "observed_effect_count_after_recovery"
        ] = 2
        comparison = compare_reference_traces(
            side_effect_expected,
            duplicate_effect,
            "DROP_OBSERVATION_TIME_ONLY_KEEP_ORDER_AND_IDENTITIES",
            "SIDE_EFFECT",
        )
        self.assertIn(
            "SIDE-EFFECT-NONIDEMPOTENT-MULTIPLE-EFFECTS",
            comparison["audit_issue_ids"],
        )


class IndependenceBoundaryTests(unittest.TestCase):
    def test_reference_model_never_imports_sut_package(self) -> None:
        imported = {
            name
            for name in sys.modules
            if name == "aegis" or name.startswith("aegis.")
        }
        self.assertEqual(set(), imported)

    def test_reference_sources_contain_no_sut_import(self) -> None:
        forbidden = re.compile(
            r"^\s*(?:from\s+aegis(?:\.|\s)|import\s+aegis(?:\.|\s|$))",
            re.MULTILINE,
        )
        for path in sorted(REFERENCE_DIR.glob("*.py")):
            with self.subTest(path=path.name):
                self.assertIsNone(forbidden.search(path.read_text("utf-8")))


class SourceManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_manifest = load_json(SOURCE_MANIFEST_PATH)
        cls.evaluation_manifest = load_manifest(MANIFEST_PATH)

    def test_all_bound_raw_files_and_self_hashes_verify(self) -> None:
        for binding in (
            self.source_manifest["source_files"]
            + self.source_manifest["assurance_files"]
        ):
            path = REPOSITORY_ROOT / binding["repository_path"]
            raw = path.read_bytes()
            with self.subTest(path=binding["repository_path"]):
                self.assertEqual(binding["byte_size"], len(raw))
                self.assertEqual(
                    binding["raw_sha256"], sha256_hex_bytes(raw)
                )

        for entry in self.source_manifest["algorithm_entries"]:
            with self.subTest(entry=entry["entry_id"]):
                self.assertTrue(verify_self_hash(entry, "entry_sha256"))
                self.assertEqual(
                    "FORBIDDEN",
                    entry["import_policy"]["production_imports"],
                )
                self.assertIn(
                    "aegis",
                    entry["import_policy"]["production_package_roots"],
                )
                for binding in entry["owned_source_files"]:
                    path = REPOSITORY_ROOT / binding["repository_path"]
                    raw = path.read_bytes()
                    self.assertEqual(binding["byte_size"], len(raw))
                    self.assertEqual(
                        binding["raw_sha256"], sha256_hex_bytes(raw)
                    )

        self.assertTrue(
            verify_self_hash(self.source_manifest, "manifest_sha256")
        )

    def test_sixteen_comparator_spec_preimages_are_complete(self) -> None:
        specs = self.source_manifest["comparator_specs"]
        entries_by_id = {
            entry["entry_id"]: entry
            for entry in self.source_manifest["algorithm_entries"]
        }
        observed_ids = {spec["comparator_id"] for spec in specs}
        expected_ids = {
            binding["comparator"]["comparator_id"]
            for contract in self.evaluation_manifest["runner_contracts"]
            for binding in contract["input_bindings"]
        }
        self.assertEqual(16, len(specs))
        self.assertEqual(16, len(observed_ids))
        self.assertEqual(expected_ids, observed_ids)
        for spec in specs:
            with self.subTest(comparator=spec["comparator_id"]):
                self.assertTrue(verify_self_hash(spec, "spec_sha256"))
                algorithm_entry = entries_by_id[
                    spec["algorithm_entry_id"]
                ]
                self.assertEqual(
                    algorithm_entry["entry_sha256"],
                    spec["algorithm_entry_sha256"],
                )
                if spec["trace_normalization"] == "NONE":
                    self.assertIsNone(spec["trace_algorithm_entry_id"])
                    self.assertIsNone(
                        spec["trace_algorithm_entry_sha256"]
                    )
                else:
                    trace_entry = entries_by_id[
                        spec["trace_algorithm_entry_id"]
                    ]
                    self.assertEqual(
                        trace_entry["entry_sha256"],
                        spec["trace_algorithm_entry_sha256"],
                    )
                bindings = [
                    binding
                    for contract in self.evaluation_manifest[
                        "runner_contracts"
                    ]
                    for binding in contract["input_bindings"]
                    if binding["comparator"]["comparator_id"]
                    == spec["comparator_id"]
                ]
                expected_modes = {
                    (
                        binding["comparator"]["kind"],
                        binding["comparator"]["exact_array_order"],
                        binding["comparator"]["exact_reason_order"],
                        binding["oracle"]["state_oracle"],
                        binding["oracle"]["side_effect_oracle"],
                        binding["oracle"]["event_oracle"],
                    )
                    for binding in bindings
                }
                self.assertEqual(1, len(expected_modes))
                self.assertEqual(
                    next(iter(expected_modes)),
                    (
                        spec["kind"],
                        spec["exact_array_order"],
                        spec["exact_reason_order"],
                        spec["state_oracle"],
                        spec["side_effect_oracle"],
                        spec["event_oracle"],
                    ),
                )
                trace_modes = {
                    case["oracle"]["trace_normalization"]
                    for case in self.evaluation_manifest["cases"]
                    if case["oracle"]["comparator_id"]
                    == spec["comparator_id"]
                }
                if not trace_modes:
                    trace_modes = {"NONE"}
                self.assertEqual(
                    {spec["trace_normalization"]}, trace_modes
                )

        schema_validation_path = (
            "evaluation/aegis_v2/reference/schema_validation.py"
        )
        for entry_id in (
            "ORACLE-BLOCKER-CLOSURE-INDEPENDENCE-V1",
            "COMPARATOR-SUT-DECISION-EXACT-JCS-V1",
            "COMPARATOR-REFERENCE-TRACE-AUDITABLE-V1",
        ):
            entry = next(
                item
                for item in self.source_manifest["algorithm_entries"]
                if item["entry_id"] == entry_id
            )
            owned_paths = {
                item["repository_path"]
                for item in entry["owned_source_files"]
            }
            self.assertIn(schema_validation_path, owned_paths)


if __name__ == "__main__":
    unittest.main()
