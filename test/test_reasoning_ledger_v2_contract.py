from __future__ import annotations

import hashlib
import inspect
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from reasoning_ledger.models import (  # noqa: E402
    EmbeddingProfile,
    EvidenceDescriptor,
    LedgerEvidence,
    LedgerRelation,
    LedgerStatementRevision,
    RelationType,
    StatementRevision,
    StatementType,
    canonical_content_sha256,
    render_statement_embedding_input,
    validate_embedding,
)
from reasoning_ledger.schema import build_init_sql  # noqa: E402
from reasoning_ledger.cli import _main, build_parser  # noqa: E402
from reasoning_ledger.store import (  # noqa: E402
    ACYCLIC_RELATIONS,
    SERIALIZATION_FAILURE_SQLSTATES,
    ReasoningLedger,
)


class ReasoningLedgerV2ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sql = build_init_sql(
            schema="reasoning_ledger",
            embedding_dimensions=3,
        )

    def test_schema_separates_authority_projection_and_rebuildable_index(self) -> None:
        for table in (
            "statement",
            "statement_revision",
            "evidence_descriptor",
            "statement_revision_evidence",
            "relation",
            "relation_evidence",
            "ledger_event",
            "current_projection",
            "embedding_profile",
            "statement_embedding",
        ):
            with self.subTest(table=table):
                self.assertIn(
                    f"CREATE TABLE IF NOT EXISTS reasoning_ledger.{table}",
                    self.sql,
                )
        self.assertNotIn("CREATE TABLE IF NOT EXISTS reasoning_ledger.reasoning_item", self.sql)

    def test_authority_rows_are_immutable_and_project_isolation_is_in_keys(self) -> None:
        self.assertIn("reject_authority_mutation", self.sql)
        for table in (
            "statement_revision",
            "evidence_descriptor",
            "relation",
            "ledger_event",
        ):
            with self.subTest(table=table):
                self.assertIn(f"ON reasoning_ledger.{table}", self.sql)
        self.assertIn("PRIMARY KEY (project_id, statement_id, revision)", self.sql)
        self.assertIn(
            "FOREIGN KEY (project_id, from_statement_id, from_revision)",
            self.sql,
        )
        self.assertIn(
            "FOREIGN KEY (project_id, to_statement_id, to_revision)",
            self.sql,
        )
        self.assertIn("validate_current_projection_event", self.sql)
        self.assertIn("NEW.projection_event_id <= OLD.projection_event_id", self.sql)

    def test_full_text_is_authoritative_revision_index_and_vector_is_exact_by_default(self) -> None:
        self.assertIn("search_document tsvector GENERATED ALWAYS AS", self.sql)
        self.assertIn("USING gin(search_document)", self.sql)
        self.assertIn("embedding vector(3)", self.sql)
        self.assertNotIn("USING hnsw", self.sql)

    def test_first_principles_types_and_relations_are_complete(self) -> None:
        self.assertEqual(
            {value.value for value in StatementType},
            {
                "OBSERVATION",
                "FACT",
                "CONSTRAINT",
                "REQUIREMENT",
                "DECISION",
                "RULE",
                "HYPOTHESIS",
                "CLAIM",
            },
        )
        self.assertEqual(
            {value.value for value in RelationType},
            {
                "SUPPORTS",
                "REFUTES",
                "ASSUMES",
                "SUPERSEDES",
                "CAUSES",
                "ENABLES",
                "PREVENTS",
                "REQUIRES",
            },
        )

    def test_evidence_descriptor_binds_bytes_and_source_identity(self) -> None:
        descriptor = EvidenceDescriptor(
            evidence_id="evidence.requirement.1",
            path="docs/REQUIREMENTS.md",
            size=128,
            sha256="ab" * 32,
            source_identity={"kind": "git_blob", "oid": "cd" * 20},
            captured_at="2026-08-20T00:00:00Z",
            scope={"document": "requirements"},
            created_by="master",
        )
        self.assertEqual(descriptor.path, "docs/REQUIREMENTS.md")
        self.assertEqual(descriptor.sha256, "ab" * 32)

        with self.assertRaisesRegex(ValueError, "sha256"):
            EvidenceDescriptor(
                evidence_id="evidence.invalid",
                path="docs/REQUIREMENTS.md",
                size=128,
                sha256="invalid",
                source_identity={"kind": "git_blob"},
                captured_at="2026-08-20T00:00:00Z",
                scope={},
                created_by="master",
            )

    def test_revision_hash_is_canonical_and_embedding_profile_is_explicit(self) -> None:
        revision = StatementRevision(
            statement_id="fact.runtime.scope",
            revision=1,
            statement_type=StatementType.FACT,
            content="Runtime scope is frozen.",
            structured_conditions={"platform": "windows"},
            validity="ACTIVE",
            scope={"module": "runtime"},
            confidence=1.0,
            created_by="master",
            evidence_ids=("evidence.runtime.scope",),
        )
        expected = canonical_content_sha256(
            {
                "statement_type": "FACT",
                "content": revision.content,
                "structured_conditions": {"platform": "windows"},
                "validity": "ACTIVE",
                "scope": {"module": "runtime"},
                "confidence": 1.0,
                "evidence_ids": ["evidence.runtime.scope"],
            }
        )
        self.assertEqual(revision.content_sha256, expected)

        profile = EmbeddingProfile(
            profile_id="openai.text-embedding-3-small.v1",
            provider="openai",
            model="text-embedding-3-small",
            model_version="2026-08-20",
            dimensions=1536,
            normalization="L2",
            input_template_version="statement-v1",
            created_by="master",
        )
        self.assertEqual(profile.dimensions, 1536)
        self.assertEqual(len(profile.content_sha256), hashlib.sha256().digest_size * 2)

    def test_supersede_and_cycle_checks_share_serializable_transactions(self) -> None:
        supersede_source = inspect.getsource(ReasoningLedger.supersede_statement)
        relation_source = inspect.getsource(ReasoningLedger.create_relation)
        transaction_source = inspect.getsource(ReasoningLedger._run_serializable)

        self.assertIn("_insert_revision(conn, revision)", supersede_source)
        self.assertIn("_insert_relation(conn, relation)", supersede_source)
        self.assertIn("_run_serializable(operation)", supersede_source)
        self.assertIn("_would_create_cycle(conn, relation)", relation_source)
        self.assertIn("_run_serializable(operation)", relation_source)
        self.assertIn(
            "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE",
            transaction_source,
        )
        self.assertIn("40001", SERIALIZATION_FAILURE_SQLSTATES)

    def test_only_proof_and_version_dependencies_are_forced_acyclic(self) -> None:
        self.assertEqual(
            ACYCLIC_RELATIONS,
            {"SUPPORTS", "ASSUMES", "SUPERSEDES", "REQUIRES"},
        )

    def test_candidate_generation_applies_hard_filters_before_ranking(self) -> None:
        lexical_source = inspect.getsource(ReasoningLedger.lexical_search)
        semantic_source = inspect.getsource(ReasoningLedger.semantic_search)
        filter_source = inspect.getsource(ReasoningLedger._add_revision_hard_filters)
        self.assertIn("_add_revision_hard_filters", lexical_source)
        self.assertIn("_add_revision_hard_filters", semantic_source)
        for required in (
            "statement_type",
            "created_at",
            "required_permissions",
            "revision.scope @>",
        ):
            with self.subTest(required=required):
                self.assertIn(required, filter_source)

    def test_export_command_reports_v2_snapshot_sections(self) -> None:
        source = inspect.getsource(_main)
        self.assertIn('snapshot["statements"]', source)
        self.assertIn('snapshot["relations"]', source)
        self.assertNotIn('snapshot["items"]', source)
        self.assertNotIn('snapshot["edges"]', source)

    def test_context_closure_rejects_any_permission_boundary_bypass(self) -> None:
        captured = "2026-08-20T00:00:00Z"
        revision = LedgerStatementRevision(
            project_id="project",
            statement_id="fact.restricted",
            revision=1,
            statement_type="FACT",
            content="Restricted fact.",
            structured_conditions={},
            validity="ACTIVE",
            current_validity="ACTIVE",
            scope={"required_permissions": ["security-review"]},
            confidence=1.0,
            content_sha256="aa" * 32,
            created_by="master",
            created_at=captured,
            evidence_ids=("evidence.restricted",),
        )
        relation = LedgerRelation(
            project_id="project",
            relation_id="relation.restricted",
            from_statement_id="fact.restricted",
            from_revision=1,
            to_statement_id="claim.target",
            to_revision=1,
            relation_type="SUPPORTS",
            applicable_conditions={"required_permissions": ["security-review"]},
            reason="Restricted support.",
            content_sha256="bb" * 32,
            created_by="master",
            created_at=captured,
            evidence_ids=("evidence.restricted",),
        )
        evidence = LedgerEvidence(
            project_id="project",
            evidence_id="evidence.restricted",
            path="evidence/restricted.md",
            size=1,
            sha256="cc" * 32,
            source_identity={"kind": "fixture"},
            captured_at=captured,
            scope={"required_permissions": ["security-review"]},
            content_sha256="dd" * 32,
            created_by="master",
            created_at=captured,
        )
        ledger = ReasoningLedger(
            "postgresql://unused",
            project_id="project",
            embedding_dimensions=3,
        )

        with self.assertRaises(PermissionError):
            ledger._assert_context_permissions(
                revisions=(revision,),
                relations=(relation,),
                evidence=(evidence,),
                permissions=(),
            )
        ledger._assert_context_permissions(
            revisions=(revision,),
            relations=(relation,),
            evidence=(evidence,),
            permissions=("security-review",),
        )

    def test_public_store_api_cannot_weaken_database_baseline(self) -> None:
        with self.assertRaises(ValueError):
            ReasoningLedger(
                "postgresql://unused",
                project_id="project",
                minimum_postgresql_major=15,
            )
        with self.assertRaises(ValueError):
            ReasoningLedger(
                "postgresql://unused",
                project_id="project",
                minimum_pgvector_version="0.7.4",
            )

    def test_embedding_storage_is_bound_to_a_supported_authority_template(self) -> None:
        revision = LedgerStatementRevision(
            project_id="project",
            statement_id="fact.runtime.scope",
            revision=1,
            statement_type="FACT",
            content="Runtime scope is frozen.",
            structured_conditions={"platform": "windows"},
            validity="ACTIVE",
            current_validity="ACTIVE",
            scope={"module": "runtime"},
            confidence=1.0,
            content_sha256="aa" * 32,
            created_by="master",
            created_at="2026-08-20T00:00:00Z",
            evidence_ids=("evidence.runtime.scope",),
        )
        rendered = render_statement_embedding_input(
            revision,
            template_version="statement-v1",
        )
        self.assertIn("Runtime scope is frozen.", rendered)
        self.assertEqual(
            rendered,
            render_statement_embedding_input(
                revision,
                template_version="statement-v1",
            ),
        )
        with self.assertRaises(ValueError):
            render_statement_embedding_input(
                revision,
                template_version="unknown-template",
            )

        store_source = inspect.getsource(ReasoningLedger.store_embedding)
        self.assertIn("render_statement_embedding_input", store_source)
        self.assertIn("embedded_text_sha256 != expected_text_sha256", store_source)

        parsed = build_parser().parse_args(
            [
                "embedding-input",
                "--statement-id",
                "fact.runtime.scope",
                "--revision",
                "1",
                "--profile-id",
                "profile.v1",
            ]
        )
        self.assertEqual(parsed.command, "embedding-input")

    def test_embedding_vectors_reject_non_finite_values(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_embedding([0.0, value], dimensions=2)


if __name__ == "__main__":
    unittest.main()
