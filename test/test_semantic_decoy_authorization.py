from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from project_seal_store import record_project_seal  # noqa: E402
from reasoning_ledger.semantic_decoy import (  # noqa: E402
    DECISION_SCHEMA,
    MANIFEST_SCHEMA,
    REQUIREMENT_BINDING_SCHEMA,
    REVIEW_RECEIPT_SCHEMA,
    DecoyClassification,
    SemanticDecoyContractError,
    evaluate_semantic_decoy_files,
)


class SemanticDecoyAuthorizationTests(unittest.TestCase):
    def prepare(
        self,
        root: Path,
        *,
        requirement_enabled: bool = True,
        context_warning: bool = False,
        active_refute: bool = False,
        implementation_identity: str = "thread.impl-reviewer",
        test_identity: str = "thread.test-reviewer",
        test_predicate: str = "measured_fps > 20",
        declared_seal: str | None = None,
    ) -> dict[str, Path]:
        project = root / "project"
        source = project / "src" / "camera.py"
        source.parent.mkdir(parents=True)
        source.write_text("MAX_FPS = 20\n", encoding="utf-8")
        evidence = (
            project
            / ".aegis"
            / "reasoning_ledger"
            / "artifacts"
            / "evidence"
            / "camera"
            / "max-fps.md"
        )
        evidence.parent.mkdir(parents=True)
        evidence.write_text("Deployment camera is limited to 20 FPS.\n", encoding="utf-8")
        actual_seal = record_project_seal(
            project,
            git_head_before_record="a" * 40,
            project_id=bytes(range(16)),
            run_id=bytes(range(16, 32)),
        ).expected_seal
        bound_seal = declared_seal or actual_seal

        artifacts = root / "artifacts"
        artifacts.mkdir()
        decision_path = artifacts / "SEMANTIC_DECOY_DECISION.json"
        requirement_path = artifacts / "REQUIREMENT_DESIGN_FINAL.md"
        context_path = artifacts / "REASONING_LEDGER_CONTEXT_PACK.json"
        manifest_path = artifacts / "SEMANTIC_DECOY_MANIFEST.json"
        implementation_plan_path = artifacts / "IMPLEMENTATION_PLAN_FINAL.md"
        implementation_review_path = (
            artifacts / "SEMANTIC_DECOY_IMPLEMENTATION_REVIEW.json"
        )
        test_plan_path = artifacts / "APPROVED_TEST_PLAN.md"
        test_review_path = artifacts / "SEMANTIC_DECOY_TEST_REVIEW.json"

        decision = {
            "schema": DECISION_SCHEMA,
            "task_id": "task.camera.pipeline",
            "phase": "pre_requirement_draft",
            "enabled": True,
            "decision_source": "developer_explicit_confirmation",
            "response_summary": "Developer explicitly enabled semantic decoys.",
            "asked_at_utc": "2026-08-13T01:00:00Z",
            "answered_at_utc": "2026-08-13T01:01:00Z",
        }
        decision_bytes = self.json_bytes(decision)
        decision_path.write_bytes(decision_bytes)
        decision_sha = hashlib.sha256(decision_bytes).hexdigest()

        requirement_binding = {
            "schema": REQUIREMENT_BINDING_SCHEMA,
            "task_id": "task.camera.pipeline",
            "enabled": requirement_enabled,
            "decision_source": "developer_explicit_confirmation",
            "decision_path": "SEMANTIC_DECOY_DECISION.json",
            "decision_sha256": decision_sha,
        }
        requirement_bytes = (
            "# Confirmed Requirements\n\n"
            "## 17. Code Obfuscation and Semantic Decoy Decision\n\n"
            "```semantic-decoy-decision-binding\n"
            + json.dumps(requirement_binding, sort_keys=True)
            + "\n```\n"
        ).encode("utf-8")
        requirement_path.write_bytes(requirement_bytes)

        item = {
            "id": "fact.camera.production_max_fps",
            "type": "fact",
            "status": "active",
            "version": 3,
            "created_by": "implementation-author",
            "evidence_path": (
                ".aegis/reasoning_ledger/artifacts/evidence/camera/max-fps.md"
            ),
        }
        edges: list[dict[str, object]] = []
        if active_refute:
            edges.append(
                {
                    "from_id": "claim.camera.can_exceed_20",
                    "to_id": item["id"],
                    "relation": "refutes",
                    "status": "active",
                }
            )
        context = {
            "task_id": "task.camera.pipeline",
            "metadata": {"project_seal": bound_seal},
            "items": [item],
            "cause_items": [],
            "edges": edges,
            "warnings": ["constraint retrieval warning"] if context_warning else [],
        }
        context_bytes = self.json_bytes(context)
        context_path.write_bytes(context_bytes)

        frozen_at = "2026-08-13T02:00:00Z"
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "task_id": "task.camera.pipeline",
            "decision_sha256": decision_sha,
            "requirement_document_sha256": hashlib.sha256(
                requirement_bytes
            ).hexdigest(),
            "context_pack_sha256": hashlib.sha256(context_bytes).hexdigest(),
            "project_seal": bound_seal,
            "frozen_at_utc": frozen_at,
            "entries": [
                {
                    "decoy_id": "decoy.camera.over_20_fps",
                    "classification": "DECOY_UNREACHABLE",
                    "code_anchors": ["src/camera.py#process_frame:fps_gt_20"],
                    "predicate": "measured_fps > 20",
                    "true_semantics": "Deployment hardware cannot exceed 20 FPS.",
                    "surface_semantics": ["High-rate recovery controller"],
                    "constraint_item_ids": [item["id"]],
                    "invalidation_conditions": [
                        "hardware, firmware, driver, or mode changes"
                    ],
                }
            ],
        }
        manifest_bytes = self.json_bytes(manifest)
        manifest_path.write_bytes(manifest_bytes)

        implementation_plan_bytes = b"# Approved implementation plan\n"
        test_plan_bytes = b"# Approved test plan\n"
        implementation_plan_path.write_bytes(implementation_plan_bytes)
        test_plan_path.write_bytes(test_plan_bytes)
        evidence_sha = hashlib.sha256(evidence.read_bytes()).hexdigest()

        common_receipt = {
            "schema": REVIEW_RECEIPT_SCHEMA,
            "task_id": "task.camera.pipeline",
            "frozen_at_utc": frozen_at,
            "reviewed_at_utc": "2026-08-13T03:00:00Z",
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "decision_sha256": decision_sha,
            "requirement_document_sha256": hashlib.sha256(
                requirement_bytes
            ).hexdigest(),
            "context_pack_sha256": hashlib.sha256(context_bytes).hexdigest(),
            "project_seal": bound_seal,
            "verdict": "PASS",
            "entries": [
                {
                    "decoy_id": "decoy.camera.over_20_fps",
                    "predicate": "measured_fps > 20",
                    "constraints": [
                        {
                            "item_id": item["id"],
                            "version": 3,
                            "evidence_path": item["evidence_path"],
                            "evidence_sha256": evidence_sha,
                        }
                    ],
                    "verdict": "PASS",
                }
            ],
        }
        implementation_receipt = {
            **common_receipt,
            "stage": "implementation_plan",
            "reviewer_role": "implementation_plan_reviewer",
            "reviewer_identity": implementation_identity,
            "reviewed_artifact_name": "IMPLEMENTATION_PLAN_FINAL.md",
            "reviewed_artifact_sha256": hashlib.sha256(
                implementation_plan_bytes
            ).hexdigest(),
        }
        test_receipt = {
            **common_receipt,
            "stage": "test_plan",
            "reviewer_role": "test_plan_reviewer",
            "reviewer_identity": test_identity,
            "reviewed_artifact_name": "APPROVED_TEST_PLAN.md",
            "reviewed_artifact_sha256": hashlib.sha256(test_plan_bytes).hexdigest(),
            "entries": [
                {
                    **common_receipt["entries"][0],
                    "predicate": test_predicate,
                }
            ],
        }
        implementation_review_path.write_bytes(
            self.json_bytes(implementation_receipt)
        )
        test_review_path.write_bytes(self.json_bytes(test_receipt))
        return {
            "project": project,
            "source": source,
            "evidence": evidence,
            "manifest": manifest_path,
            "requirement": requirement_path,
            "context": context_path,
            "implementation_plan": implementation_plan_path,
            "implementation_review": implementation_review_path,
            "test_plan": test_plan_path,
            "test_review": test_review_path,
        }

    def evaluate(self, paths: dict[str, Path]):
        return evaluate_semantic_decoy_files(
            paths["manifest"],
            requirement_document_path=paths["requirement"],
            context_pack_path=paths["context"],
            implementation_plan_path=paths["implementation_plan"],
            implementation_review_path=paths["implementation_review"],
            approved_test_plan_path=paths["test_plan"],
            test_review_path=paths["test_review"],
            project_root=paths["project"],
        )

    @staticmethod
    def json_bytes(value: object) -> bytes:
        return (json.dumps(value, sort_keys=True) + "\n").encode("utf-8")

    def test_two_bound_independent_reviews_grant_the_internal_exemption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.evaluate(self.prepare(Path(directory)))

        self.assertTrue(result.authorization_complete)
        self.assertEqual(
            result.entries[0].effective_classification,
            DecoyClassification.DECOY_UNREACHABLE,
        )
        self.assertFalse(result.entries[0].internal_logic_test_required)
        self.assertEqual(result.blocking_reasons, ())

    def test_missing_reviewer_receipt_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self.prepare(Path(directory))
            paths["implementation_review"].unlink()

            with self.assertRaises(SemanticDecoyContractError):
                self.evaluate(paths)

    def test_one_or_non_independent_reviewer_cannot_grant_exemption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self.prepare(
                Path(directory),
                implementation_identity="thread.same",
                test_identity="thread.same",
            )
            result = self.evaluate(paths)

        self.assertFalse(result.authorization_complete)
        self.assertTrue(result.entries[0].internal_logic_test_required)
        self.assertEqual(
            result.entries[0].effective_classification,
            DecoyClassification.UNKNOWN_STALE,
        )

    def test_active_refute_or_context_warning_blocks_authorization(self) -> None:
        for label, arguments in (
            ("active refute", {"active_refute": True}),
            ("warning", {"context_warning": True}),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                result = self.evaluate(self.prepare(Path(directory), **arguments))
                self.assertFalse(result.authorization_complete)
                self.assertTrue(result.entries[0].internal_logic_test_required)

    def test_fake_self_consistent_seal_does_not_replace_the_project_seal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self.prepare(Path(directory), declared_seal="ASC1:" + "c" * 64)
            result = self.evaluate(paths)

        self.assertFalse(result.authorization_complete)
        self.assertTrue(result.entries[0].internal_logic_test_required)

    def test_source_change_after_recorded_seal_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self.prepare(Path(directory))
            paths["source"].write_text("MAX_FPS = 30\n", encoding="utf-8")

            with self.assertRaises(SemanticDecoyContractError):
                self.evaluate(paths)

    def test_requirement_decision_conflict_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self.prepare(Path(directory), requirement_enabled=False)

            with self.assertRaises(SemanticDecoyContractError):
                self.evaluate(paths)

    def test_requirement_binding_missing_duplicate_or_mismatched_fails_closed(self) -> None:
        mutations = {
            "missing section": b"# Confirmed Requirements\n",
            "duplicate section": None,
            "wrong task": ("task.camera.pipeline", "task.other"),
            "wrong decision sha": None,
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                paths = self.prepare(Path(directory))
                original = paths["requirement"].read_bytes()
                if label == "duplicate section":
                    changed = original + original.split(b"\n\n", 1)[1]
                elif label == "wrong decision sha":
                    changed = original.replace(
                        hashlib.sha256(
                            (
                                paths["requirement"].parent
                                / "SEMANTIC_DECOY_DECISION.json"
                            ).read_bytes()
                        ).hexdigest().encode("ascii"),
                        b"0" * 64,
                    )
                elif isinstance(mutation, tuple):
                    changed = original.replace(
                        mutation[0].encode("utf-8"),
                        mutation[1].encode("utf-8"),
                    )
                else:
                    changed = mutation
                assert isinstance(changed, bytes)
                paths["requirement"].write_bytes(changed)

                with self.assertRaises(SemanticDecoyContractError):
                    self.evaluate(paths)

    def test_review_predicate_conflict_cannot_grant_exemption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self.prepare(
                Path(directory),
                test_predicate="measured_fps >= 20",
            )
            result = self.evaluate(paths)

        self.assertFalse(result.authorization_complete)
        self.assertTrue(result.entries[0].internal_logic_test_required)

    def test_evidence_change_after_reviews_cannot_grant_exemption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = self.prepare(Path(directory))
            paths["evidence"].write_text(
                "Deployment camera limit is no longer confirmed.\n",
                encoding="utf-8",
            )
            result = self.evaluate(paths)

        self.assertFalse(result.authorization_complete)
        self.assertTrue(result.entries[0].internal_logic_test_required)


if __name__ == "__main__":
    unittest.main()
