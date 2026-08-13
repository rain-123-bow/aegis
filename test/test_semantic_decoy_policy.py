from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from reasoning_ledger.semantic_decoy import (  # noqa: E402
    DECISION_SCHEMA,
    MANIFEST_SCHEMA,
    DecoyClassification,
    SemanticDecoyContractError,
    evaluate_semantic_decoy_artifacts,
    evaluate_semantic_decoy_files,
    parse_semantic_decoy_decision,
)


class SemanticDecoyPolicyTests(unittest.TestCase):
    def decision(self, *, enabled: bool = True) -> dict[str, object]:
        return {
            "schema": DECISION_SCHEMA,
            "task_id": "task.camera.pipeline",
            "phase": "pre_requirement_draft",
            "enabled": enabled,
            "decision_source": (
                "developer_explicit_confirmation"
                if enabled
                else "default_disabled"
            ),
            "response_summary": "Developer explicitly enabled semantic decoys."
            if enabled
            else "No unambiguous enablement was provided; default remains disabled.",
            "asked_at_utc": "2026-08-13T01:00:00Z",
            "answered_at_utc": "2026-08-13T01:01:00Z",
        }

    def entry(
        self,
        *,
        classification: str = DecoyClassification.DECOY_UNREACHABLE.value,
    ) -> dict[str, object]:
        return {
            "decoy_id": "decoy.camera.over_20_fps",
            "classification": classification,
            "code_anchors": ["src/camera.py#process_frame:fps_gt_20"],
            "predicate": "measured_fps > 20",
            "true_semantics": "Deployment hardware cannot exceed 20 FPS.",
            "surface_semantics": [
                "Treat the branch as a high-rate recovery controller."
            ],
            "constraint_item_ids": ["fact.camera.production_max_fps"],
            "invalidation_conditions": [
                "camera hardware, firmware, driver, or capture mode changes"
            ],
        }

    def manifest(self, *, entries: list[dict[str, object]] | None = None) -> dict[str, object]:
        return {
            "schema": MANIFEST_SCHEMA,
            "task_id": "task.camera.pipeline",
            "decision_sha256": "a" * 64,
            "requirement_document_sha256": "b" * 64,
            "context_pack_sha256": "d" * 64,
            "project_seal": "ASC1:" + "c" * 64,
            "entries": entries if entries is not None else [self.entry()],
        }

    def context_pack(self, *, status: str = "active", evidence: bool = True) -> dict[str, object]:
        return {
            "task_id": "task.camera.pipeline",
            "metadata": {"project_seal": "ASC1:" + "c" * 64},
            "items": [
                {
                    "id": "fact.camera.production_max_fps",
                    "type": "fact",
                    "status": status,
                    "evidence_path": (
                        ".aegis/reasoning_ledger/artifacts/evidence/camera/max-fps.md"
                        if evidence
                        else None
                    ),
                }
            ],
            "cause_items": [],
            "edges": [],
            "warnings": [],
        }

    def evaluate(
        self,
        *,
        decision: dict[str, object] | None = None,
        manifest: dict[str, object] | None = None,
        context_pack: dict[str, object] | None = None,
        recorded_decision_sha256: str | None = None,
        recorded_requirement_document_sha256: str | None = None,
        recorded_context_pack_sha256: str | None = None,
        current_project_seal: str = "ASC1:" + "c" * 64,
    ):
        decision_data = decision if decision is not None else self.decision()
        context_data = (
            context_pack if context_pack is not None else self.context_pack()
        )
        decision_bytes = json.dumps(decision_data, sort_keys=True).encode("utf-8")
        context_bytes = json.dumps(context_data, sort_keys=True).encode("utf-8")
        requirement_bytes = b"# Confirmed Requirements\n"
        manifest_data = deepcopy(
            manifest if manifest is not None else self.manifest()
        )
        manifest_data["decision_sha256"] = (
            recorded_decision_sha256
            if recorded_decision_sha256 is not None
            else hashlib.sha256(decision_bytes).hexdigest()
        )
        manifest_data["requirement_document_sha256"] = (
            recorded_requirement_document_sha256
            if recorded_requirement_document_sha256 is not None
            else hashlib.sha256(requirement_bytes).hexdigest()
        )
        manifest_data["context_pack_sha256"] = (
            recorded_context_pack_sha256
            if recorded_context_pack_sha256 is not None
            else hashlib.sha256(context_bytes).hexdigest()
        )
        return evaluate_semantic_decoy_artifacts(
            json.dumps(manifest_data, sort_keys=True).encode("utf-8"),
            decision_bytes=decision_bytes,
            requirement_document_bytes=requirement_bytes,
            context_pack_bytes=context_bytes,
            current_project_seal=current_project_seal,
        )

    def test_only_explicit_developer_confirmation_can_enable(self) -> None:
        enabled = parse_semantic_decoy_decision(self.decision())
        disabled = parse_semantic_decoy_decision(self.decision(enabled=False))

        self.assertTrue(enabled.enabled)
        self.assertFalse(disabled.enabled)

        invalid_source = self.decision()
        invalid_source["decision_source"] = "default_disabled"
        with self.assertRaises(SemanticDecoyContractError):
            parse_semantic_decoy_decision(invalid_source)

        wrong_type = self.decision()
        wrong_type["enabled"] = "true"
        with self.assertRaises(SemanticDecoyContractError):
            parse_semantic_decoy_decision(wrong_type)

    def test_valid_active_constraint_authorizes_internal_test_exemption(self) -> None:
        result = self.evaluate()

        self.assertTrue(result.policy_enabled)
        self.assertTrue(result.all_declared_decoys_structurally_valid)
        self.assertEqual(
            result.structurally_eligible_decoy_ids,
            ("decoy.camera.over_20_fps",),
        )
        self.assertEqual(
            result.entries[0].effective_classification,
            DecoyClassification.DECOY_UNREACHABLE,
        )
        self.assertFalse(result.entries[0].internal_logic_test_required)
        self.assertTrue(result.entries[0].perimeter_tests_required)
        self.assertEqual(result.blocking_reasons, ())

    def test_stale_or_unproven_constraint_loses_test_exemption(self) -> None:
        missing_item = self.context_pack()
        missing_item["items"] = []
        for label, pack in (
            ("stale", self.context_pack(status="stale")),
            ("missing evidence", self.context_pack(evidence=False)),
            ("missing item", missing_item),
        ):
            with self.subTest(label=label):
                result = self.evaluate(context_pack=pack)
                entry = result.entries[0]
                self.assertEqual(
                    entry.effective_classification,
                    DecoyClassification.UNKNOWN_STALE,
                )
                self.assertTrue(entry.internal_logic_test_required)
                self.assertTrue(entry.perimeter_tests_required)
                self.assertFalse(result.all_declared_decoys_structurally_valid)
                self.assertTrue(result.blocking_reasons)

    def test_identical_context_item_repeated_as_a_cause_is_not_ambiguous(self) -> None:
        pack = self.context_pack()
        pack["cause_items"] = deepcopy(pack["items"])

        result = self.evaluate(context_pack=pack)

        self.assertTrue(result.all_declared_decoys_structurally_valid)
        self.assertEqual(
            result.entries[0].effective_classification,
            DecoyClassification.DECOY_UNREACHABLE,
        )

        conflicting = self.context_pack()
        conflicting_item = deepcopy(conflicting["items"][0])
        conflicting_item["status"] = "stale"
        conflicting["cause_items"] = [conflicting_item]
        result = self.evaluate(context_pack=conflicting)
        self.assertEqual(
            result.entries[0].effective_classification,
            DecoyClassification.UNKNOWN_STALE,
        )

    def test_hash_or_seal_mismatch_downgrades_every_declared_decoy(self) -> None:
        cases = (
            {"recorded_decision_sha256": "d" * 64},
            {"recorded_requirement_document_sha256": "e" * 64},
            {"current_project_seal": "ASC1:" + "f" * 64},
            {"recorded_context_pack_sha256": "0" * 64},
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                result = self.evaluate(**arguments)
                self.assertEqual(
                    result.entries[0].effective_classification,
                    DecoyClassification.UNKNOWN_STALE,
                )
                self.assertTrue(result.entries[0].internal_logic_test_required)
                self.assertFalse(result.all_declared_decoys_structurally_valid)

    def test_context_pack_must_name_the_task_and_current_project_seal(self) -> None:
        wrong_task = self.context_pack()
        wrong_task["task_id"] = "task.other"
        wrong_seal = self.context_pack()
        wrong_seal["metadata"] = {"project_seal": "ASC1:" + "f" * 64}

        for label, context_pack in (
            ("wrong task", wrong_task),
            ("wrong seal", wrong_seal),
        ):
            with self.subTest(label=label):
                result = self.evaluate(context_pack=context_pack)
                self.assertFalse(result.all_declared_decoys_structurally_valid)
                self.assertEqual(
                    result.entries[0].effective_classification,
                    DecoyClassification.UNKNOWN_STALE,
                )

    def test_file_evaluator_computes_binding_hashes_from_exact_bytes(self) -> None:
        decision = self.decision()
        context_pack = self.context_pack()
        requirement_bytes = b"# Confirmed Requirements\n"
        decision_bytes = (
            json.dumps(decision, indent=2, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        context_bytes = (
            json.dumps(context_pack, indent=2, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        manifest = self.manifest()
        manifest["decision_sha256"] = hashlib.sha256(decision_bytes).hexdigest()
        manifest["requirement_document_sha256"] = hashlib.sha256(
            requirement_bytes
        ).hexdigest()
        manifest["context_pack_sha256"] = hashlib.sha256(context_bytes).hexdigest()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "SEMANTIC_DECOY_MANIFEST.json"
            decision_path = root / "SEMANTIC_DECOY_DECISION.json"
            requirement_path = root / "REQUIREMENT_DESIGN_FINAL.md"
            context_path = root / "REASONING_LEDGER_CONTEXT_PACK.json"
            manifest_path.write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
            )
            decision_path.write_bytes(decision_bytes)
            requirement_path.write_bytes(requirement_bytes)
            context_path.write_bytes(context_bytes)

            result = evaluate_semantic_decoy_files(
                manifest_path,
                decision_path=decision_path,
                requirement_document_path=requirement_path,
                context_pack_path=context_path,
                current_project_seal="ASC1:" + "c" * 64,
            )
            self.assertTrue(result.all_declared_decoys_structurally_valid)

            requirement_path.write_bytes(requirement_bytes + b"changed\n")
            result = evaluate_semantic_decoy_files(
                manifest_path,
                decision_path=decision_path,
                requirement_document_path=requirement_path,
                context_pack_path=context_path,
                current_project_seal="ASC1:" + "c" * 64,
            )
            self.assertFalse(result.all_declared_decoys_structurally_valid)

    def test_file_evaluator_rejects_ambiguous_duplicate_json_keys(self) -> None:
        context_pack = self.context_pack()
        requirement_bytes = b"# Confirmed Requirements\n"
        context_bytes = json.dumps(context_pack).encode("utf-8")
        decision_bytes = json.dumps(self.decision()).encode("utf-8")
        duplicate_decision_bytes = decision_bytes.replace(
            b'"enabled": true',
            b'"enabled": false, "enabled": true',
        )
        manifest = self.manifest()
        manifest["decision_sha256"] = hashlib.sha256(
            duplicate_decision_bytes
        ).hexdigest()
        manifest["requirement_document_sha256"] = hashlib.sha256(
            requirement_bytes
        ).hexdigest()
        manifest["context_pack_sha256"] = hashlib.sha256(context_bytes).hexdigest()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "SEMANTIC_DECOY_MANIFEST.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            (root / "SEMANTIC_DECOY_DECISION.json").write_bytes(
                duplicate_decision_bytes
            )
            (root / "REQUIREMENT_DESIGN_FINAL.md").write_bytes(requirement_bytes)
            (root / "REASONING_LEDGER_CONTEXT_PACK.json").write_bytes(context_bytes)

            with self.assertRaises(SemanticDecoyContractError):
                evaluate_semantic_decoy_files(
                    root / "SEMANTIC_DECOY_MANIFEST.json",
                    decision_path=root / "SEMANTIC_DECOY_DECISION.json",
                    requirement_document_path=root / "REQUIREMENT_DESIGN_FINAL.md",
                    context_pack_path=root / "REASONING_LEDGER_CONTEXT_PACK.json",
                    current_project_seal="ASC1:" + "c" * 64,
                )

    def test_disabled_policy_rejects_a_declared_decoy(self) -> None:
        result = self.evaluate(decision=self.decision(enabled=False))

        self.assertFalse(result.policy_enabled)
        self.assertFalse(result.all_declared_decoys_structurally_valid)
        self.assertEqual(
            result.entries[0].effective_classification,
            DecoyClassification.UNKNOWN_STALE,
        )
        self.assertTrue(result.entries[0].internal_logic_test_required)
        self.assertTrue(result.blocking_reasons)

    def test_real_code_always_requires_normal_business_tests(self) -> None:
        real_entry = self.entry(classification=DecoyClassification.REAL.value)
        real_entry["constraint_item_ids"] = []
        real_entry["invalidation_conditions"] = []
        real_entry["surface_semantics"] = []
        result = self.evaluate(manifest=self.manifest(entries=[real_entry]))

        self.assertEqual(
            result.entries[0].effective_classification,
            DecoyClassification.REAL,
        )
        self.assertTrue(result.entries[0].internal_logic_test_required)
        self.assertFalse(result.entries[0].perimeter_tests_required)

    def test_manifest_has_an_exact_schema_and_unique_decoy_ids(self) -> None:
        extra_field = self.manifest()
        extra_field["extra"] = True
        with self.assertRaises(SemanticDecoyContractError):
            self.evaluate(manifest=extra_field)

        duplicate = self.entry()
        with self.assertRaises(SemanticDecoyContractError):
            self.evaluate(manifest=self.manifest(entries=[self.entry(), duplicate]))


if __name__ == "__main__":
    unittest.main()
