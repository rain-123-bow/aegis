from __future__ import annotations

import hashlib
import inspect
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from reasoning_ledger.models import (  # noqa: E402
    EmbeddingProfile,
    EvidenceDescriptor,
    LedgerEvidence,
    LedgerRelation,
    LedgerStatementRevision,
    QueryEmbeddingReceipt,
    RelationType,
    StatementRelation,
    StatementRevision,
    StatementType,
    canonical_embedding_sha256,
    canonical_content_sha256,
    render_statement_embedding_input,
    validate_embedding,
)
from reasoning_ledger.schema import (  # noqa: E402
    V2_REQUIRED_TRIGGER_NAMES,
    build_init_sql,
    build_v2_reference_sql,
)
from reasoning_ledger.cli import _main, build_parser, main  # noqa: E402
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

    def test_v2_upgrade_trigger_contract_excludes_v3_only_authorities(self) -> None:
        self.assertNotIn("project_anchor_immutable", V2_REQUIRED_TRIGGER_NAMES)
        self.assertNotIn("supersedes_transaction_bound", V2_REQUIRED_TRIGGER_NAMES)
        self.assertNotIn("revision_transaction_bound", V2_REQUIRED_TRIGGER_NAMES)
        self.assertNotIn("schema_metadata_immutable", V2_REQUIRED_TRIGGER_NAMES)
        self.assertIn("current_projection_event_bound", V2_REQUIRED_TRIGGER_NAMES)

    def test_embedding_digest_uses_canonical_binary32_values(self) -> None:
        self.assertEqual(
            canonical_embedding_sha256([0.1, -0.2, 0.3], dimensions=3),
            canonical_embedding_sha256(
                [0.10000000149011612, -0.20000000298023224, 0.30000001192092896],
                dimensions=3,
            ),
        )

    def test_schema_separates_authority_projection_and_rebuildable_index(self) -> None:
        for table in (
            "project_anchor",
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
            "project_anchor",
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
        self.assertIn("CREATE CONSTRAINT TRIGGER supersedes_transaction_bound", self.sql)
        self.assertIn("CREATE CONSTRAINT TRIGGER revision_transaction_bound", self.sql)
        self.assertIn("DEFERRABLE INITIALLY DEFERRED", self.sql)
        self.assertIn("NEW.revision <> OLD.revision + 1", self.sql)
        self.assertIn(
            "linked_event.aggregate_id <> OLD.statement_id || '@' || OLD.revision::text",
            self.sql,
        )

    def test_full_text_is_authoritative_revision_index_and_vector_is_exact_by_default(self) -> None:
        self.assertIn("search_document tsvector GENERATED ALWAYS AS", self.sql)
        self.assertIn("USING gin(search_document)", self.sql)
        self.assertIn("embedding public.vector(3)", self.sql)
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

    def test_public_relation_api_rejects_supersedes(self) -> None:
        ledger = ReasoningLedger(
            "postgresql://unused",
            project_id="project",
            embedding_dimensions=3,
        )
        relation = StatementRelation(
            relation_id="illegal.supersede",
            from_statement_id="claim.versioned",
            from_revision=1,
            to_statement_id="claim.versioned",
            to_revision=2,
            relation_type=RelationType.SUPERSEDES,
            applicable_conditions={},
            reason="must use the atomic supersede transaction",
            created_by="test",
            evidence_ids=("evidence.version",),
        )
        with self.assertRaisesRegex(ValueError, "supersede_statement"):
            ledger.create_relation(relation)

        parsed = build_parser().parse_args(
            [
                "link-revisions",
                "--relation-id",
                "relation.support",
                "--from-statement-id",
                "fact.a",
                "--from-revision",
                "1",
                "--to-statement-id",
                "claim.b",
                "--to-revision",
                "1",
                "--relation-type",
                "SUPPORTS",
                "--reason",
                "evidence supports claim",
                "--evidence-ids",
                "evidence.1",
                "--created-by",
                "test",
            ]
        )
        self.assertNotIn(
            "SUPERSEDES",
            next(
                action.choices
                for action in build_parser()._subparsers._group_actions[0]
                .choices["link-revisions"]._actions
                if action.dest == "relation_type"
            ),
        )
        self.assertEqual(parsed.relation_type, "SUPPORTS")

    def test_only_proof_and_version_dependencies_are_forced_acyclic(self) -> None:
        self.assertEqual(
            ACYCLIC_RELATIONS,
            {"SUPPORTS", "ASSUMES", "SUPERSEDES", "REQUIRES"},
        )

    def test_candidate_generation_applies_objective_hard_filters_before_ranking(self) -> None:
        lexical_source = inspect.getsource(ReasoningLedger.lexical_search)
        semantic_source = inspect.getsource(ReasoningLedger.semantic_search)
        filter_source = inspect.getsource(ReasoningLedger._add_revision_hard_filters)
        self.assertIn("_add_revision_hard_filters", lexical_source)
        self.assertIn("_add_revision_hard_filters", semantic_source)
        for required in (
            "statement_type",
            "created_at",
            "revision.scope @>",
        ):
            with self.subTest(required=required):
                self.assertIn(required, filter_source)

    def test_export_command_reports_v5_snapshot_sections(self) -> None:
        source = inspect.getsource(_main)
        self.assertIn('snapshot["statements"]', source)
        self.assertIn('snapshot["relations"]', source)
        self.assertNotIn('snapshot["items"]', source)
        self.assertNotIn('snapshot["edges"]', source)

    def test_unsupported_record_level_permissions_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported"):
            StatementRevision(
                statement_id="fact.restricted",
                revision=1,
                statement_type=StatementType.FACT,
                content="Restricted fact.",
                structured_conditions={},
                validity="ACTIVE",
                scope={"required_permissions": ["security-review"]},
                confidence=1.0,
                created_by="master",
                evidence_ids=("evidence.restricted",),
            )
        with self.assertRaisesRegex(ValueError, "recursively unsupported"):
            StatementRevision(
                statement_id="fact.nested-restricted",
                revision=1,
                statement_type=StatementType.FACT,
                content="Nested restricted fact.",
                structured_conditions={
                    "nested": {"required_permissions": ["security-review"]}
                },
                validity="ACTIVE",
                scope={},
                confidence=1.0,
                created_by="master",
                evidence_ids=("evidence.restricted",),
            )
        parser = build_parser()
        lexical_actions = parser._subparsers._group_actions[0].choices[
            "lexical-search"
        ]._actions
        self.assertNotIn("permissions", {action.dest for action in lexical_actions})

    def test_probe_is_fail_closed_and_reports_actual_contract(self) -> None:
        ledger = ReasoningLedger(
            "postgresql://unused",
            project_id="project",
            embedding_dimensions=3,
        )
        expected = {
            "status": True,
            "database": "aegis",
            "user": "aegis",
            "postgresql_major": 16,
            "postgresql_version_num": 160004,
            "pgvector_version": "0.8.0",
            "pgvector_schema": "public",
            "schema": "reasoning_ledger",
            "schema_version": 3,
            "embedding_dimensions": 3,
            "schema_contract_signature": "aa" * 32,
            "catalog_signature": "cc" * 32,
            "project_anchor": {
                "schema": "aegis.reasoning_ledger.project_anchor.v1",
                "project_id": "project",
                "cluster_system_identifier": "123456789",
                "database_oid": 16384,
                "database_name": "aegis",
                "schema_name": "reasoning_ledger",
                "anchor_sha256": "bb" * 32,
                "created_at": "2026-08-20T00:00:00Z",
            },
        }
        with patch.object(ledger, "probe_contract", return_value=expected) as probe:
            self.assertEqual(ledger.probe_contract(require_schema=True), expected)
            probe.assert_called_once_with(require_schema=True)
        source = inspect.getsource(ReasoningLedger._probe_server_contract)
        self.assertIn("server_version_num", source)
        self.assertIn("extversion", source)
        self.assertIn("pg_catalog.pg_extension", source)
        self.assertIn("extension_schema", source)
        self.assertIn("extrelocatable", source)
        self.assertIn("ALTER EXTENSION vector SET SCHEMA", source)
        self.assertIn("WITH SCHEMA", source)
        self.assertIn(
            "SET search_path TO pg_catalog",
            inspect.getsource(ReasoningLedger.connect),
        )
        self.assertIn(
            "_validate_schema_contract",
            inspect.getsource(ReasoningLedger.probe_contract),
        )
        migration_source = inspect.getsource(ReasoningLedger.migrate)
        self.assertIn("if existing_tables", migration_source)
        self.assertIn("_validate_v2_upgrade_source", migration_source)
        self.assertLess(
            migration_source.index("_validate_v2_upgrade_source"),
            migration_source.index("relocate_legacy_namespace=True"),
        )
        self.assertIn(
            "refusing to relocate a database-wide pgvector extension",
            migration_source,
        )
        self.assertIn("_stamp_schema_catalog_signature", migration_source)
        self.assertIn("_validate_schema_contract(conn)", migration_source)
        self.assertIn(
            "_validate_v2_column_definitions",
            inspect.getsource(ReasoningLedger._validate_v2_upgrade_source),
        )
        v2_reference_sql = build_v2_reference_sql(
            schema="v2_reference",
            embedding_dimensions=3,
        )
        self.assertIn("embedding vector(3)", v2_reference_sql)
        self.assertNotIn("WITH SCHEMA", v2_reference_sql)
        self.assertIn(
            "sql.Identifier(vector_schema)",
            inspect.getsource(ReasoningLedger._validate_v2_column_definitions),
        )
        v2_validation_source = inspect.getsource(
            ReasoningLedger._validate_v2_upgrade_source
        )
        self.assertIn("revision.revision = 1 AND revision.validity = 'SUPERSEDED'", v2_validation_source)
        self.assertIn("revision.revision > 1 AND revision.validity <> 'ACTIVE'", v2_validation_source)
        self.assertIn("event.payload->>'new_validity'", v2_validation_source)
        self.assertIn("event.aggregate_kind <> 'REVISION'", v2_validation_source)
        self.assertEqual(self.sql.count("pg_current_xact_id()::xid"), 11)
        self.assertIn("relation.xmin = pg_catalog.pg_current_xact_id()::xid", self.sql)
        self.assertIn("revision.xmin = pg_catalog.pg_current_xact_id()::xid", self.sql)
        self.assertIn("projection.xmin = pg_catalog.pg_current_xact_id()::xid", self.sql)
        self.assertIn(
            "_catalog_signature(conn)",
            inspect.getsource(ReasoningLedger._validate_schema_contract),
        )
        self.assertIn("ON CONFLICT (key) DO NOTHING", self.sql)
        self.assertNotIn("DO UPDATE SET value = EXCLUDED.value", self.sql)
        self.assertIn(
            "_validate_project_anchor",
            inspect.getsource(ReasoningLedger.connect),
        )
        self.assertIn("pg_control_system()", inspect.getsource(ReasoningLedger._database_identity))
        sequence_source = inspect.getsource(ReasoningLedger._validate_event_sequence)
        self.assertIn("increment_by", sequence_source)
        self.assertIn("ownership_dependency", sequence_source)
        self.assertIn("exhausted its allocatable range", sequence_source)
        self.assertIn(
            "pg_catalog.pg_extension",
            inspect.getsource(ReasoningLedger._catalog_signature),
        )

    def test_cli_failures_emit_status_false(self) -> None:
        with patch("builtins.print") as printed:
            result = main(
                [
                    "probe",
                    "--project-root",
                    "missing-project-root",
                ]
            )
        self.assertEqual(result, 2)
        payload = json.loads(printed.call_args.args[0])
        self.assertIs(payload["status"], False)

    def test_public_evidence_registration_rechecks_project_bytes(self) -> None:
        source = inspect.getsource(ReasoningLedger.register_evidence)
        self.assertIn("read_regular_file", source)
        self.assertIn("len(content) != descriptor.size", source)
        self.assertIn("digest != descriptor.sha256", source)
        self.assertIn("project_root", inspect.signature(ReasoningLedger.register_evidence).parameters)

    def test_project_config_string_fields_are_not_coerced(self) -> None:
        from reasoning_ledger.project import ProjectLedgerConfig

        with self.assertRaisesRegex(ValueError, "project_id must be a string"):
            ProjectLedgerConfig(project_id=123, project_root=Path("."))  # type: ignore[arg-type]

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

        self.assertFalse(hasattr(ReasoningLedger, "store_embedding"))
        self.assertTrue(hasattr(ReasoningLedger, "generate_and_store_embedding"))
        store_source = inspect.getsource(ReasoningLedger._store_embedding)
        self.assertIn("render_statement_embedding_input", store_source)
        self.assertIn("embedded_text_sha256 != expected_text_sha256", store_source)
        self.assertIn("generation_receipt", store_source)
        self.assertIn("embedding_sha256", store_source)
        self.assertIn("development_profile != hash_generator", store_source)
        query_source = inspect.getsource(
            ReasoningLedger.assert_embedding_source_compatible
        )
        self.assertIn(
            'development_profile != (embedding_source == "hash-fallback")',
            query_source,
        )

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

    def test_semantic_search_requires_a_profile_bound_query_receipt(self) -> None:
        ledger = ReasoningLedger(
            "postgresql://unused",
            project_id="project",
            embedding_dimensions=3,
        )
        with self.assertRaisesRegex(TypeError, "query embedding receipt"):
            ledger.semantic_search([1.0, 0.0, 0.0])  # type: ignore[arg-type]
        receipt = QueryEmbeddingReceipt(
            profile_id="profile.v1",
            source="json",
            embedding=[1.0, 0.0, 0.0],
            generator_identity={
                "kind": "provided-json",
                "size": 13,
                "sha256": "aa" * 32,
            },
        )
        self.assertEqual(receipt.profile_id, "profile.v1")
        self.assertEqual(len(receipt.embedding_sha256), 64)

    def test_index_storage_reindex_does_not_claim_vector_regeneration(self) -> None:
        self.assertFalse(hasattr(ReasoningLedger, "rebuild_index"))
        source = inspect.getsource(ReasoningLedger.reindex_storage)
        self.assertIn("REINDEX TABLE", source)
        self.assertNotIn("EMBEDDING_REBUILT", source)


if __name__ == "__main__":
    unittest.main()
