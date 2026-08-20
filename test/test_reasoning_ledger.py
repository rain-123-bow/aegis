from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

import psycopg


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from reasoning_ledger import (  # noqa: E402
    EmbeddingProfile,
    EvidenceDescriptor,
    ProjectLedgerConfig,
    ReasoningLedger,
    RelationType,
    RevisionValidity,
    StatementRelation,
    StatementRevision,
    StatementType,
    bootstrap_project_ledger,
    build_init_sql,
    render_statement_embedding_input,
)


TEST_DSN = os.environ.get(
    "AEGIS_LEDGER_DSN",
    "postgresql://aegis:aegis@127.0.0.1:5432/aegis_ledger?connect_timeout=3",
)
TEST_SCHEMA = "aegis_test_ledger_v2"
CAPTURED_AT = "2026-08-20T00:00:00Z"


def require_test_database() -> None:
    try:
        with psycopg.connect(TEST_DSN, autocommit=True):
            pass
    except psycopg.OperationalError as error:
        raise unittest.SkipTest(
            f"PostgreSQL/pgvector integration database is unavailable: {error}"
        ) from error


class ReasoningLedgerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_test_database()
        with psycopg.connect(TEST_DSN, autocommit=True) as conn:
            conn.execute(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE")

    @classmethod
    def tearDownClass(cls) -> None:
        with psycopg.connect(TEST_DSN, autocommit=True) as conn:
            conn.execute(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE")

    def setUp(self) -> None:
        self.project_id = f"test_project_{uuid4().hex}"
        self.ledger = ReasoningLedger(
            TEST_DSN,
            project_id=self.project_id,
            schema=TEST_SCHEMA,
            embedding_dimensions=3,
        )
        self.ledger.migrate()

    def evidence(self, evidence_id: str, content: bytes = b"evidence") -> str:
        self.ledger.register_evidence(
            EvidenceDescriptor(
                evidence_id=evidence_id,
                path=f".aegis/reasoning_ledger/artifacts/evidence/{evidence_id}.bin",
                size=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                source_identity={"kind": "test_fixture", "id": evidence_id},
                captured_at=CAPTURED_AT,
                scope={"test": True},
                created_by="test",
            )
        )
        return evidence_id

    def statement(
        self,
        statement_id: str,
        content: str,
        *,
        statement_type: StatementType = StatementType.FACT,
    ) -> None:
        evidence_id = self.evidence(f"evidence.{statement_id}", content.encode())
        self.ledger.create_statement(
            StatementRevision(
                statement_id=statement_id,
                revision=1,
                statement_type=statement_type,
                content=content,
                structured_conditions={},
                validity=RevisionValidity.ACTIVE,
                scope={"module": "ledger"},
                confidence=1.0,
                created_by="test",
                evidence_ids=(evidence_id,),
            )
        )

    def relation(
        self,
        relation_id: str,
        from_id: str,
        to_id: str,
        relation_type: RelationType = RelationType.SUPPORTS,
    ) -> None:
        evidence_id = self.evidence(f"evidence.{relation_id}", relation_id.encode())
        self.ledger.create_relation(
            StatementRelation(
                relation_id=relation_id,
                from_statement_id=from_id,
                from_revision=1,
                to_statement_id=to_id,
                to_revision=1,
                relation_type=relation_type,
                applicable_conditions={},
                reason=f"{from_id} {relation_type.value} {to_id}",
                created_by="test",
                evidence_ids=(evidence_id,),
            )
        )

    def test_schema_is_v2_postgresql_pgvector_authority(self) -> None:
        with self.ledger.connect() as conn:
            extension = conn.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            ).fetchone()
            tables = conn.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                ORDER BY table_name
                """,
                (TEST_SCHEMA,),
            ).fetchall()
        self.assertIsNotNone(extension)
        self.assertEqual(
            {row["table_name"] for row in tables},
            {
                "current_projection",
                "embedding_profile",
                "evidence_descriptor",
                "ledger_event",
                "relation",
                "relation_evidence",
                "schema_metadata",
                "statement",
                "statement_embedding",
                "statement_revision",
                "statement_revision_evidence",
            },
        )

    def test_hybrid_retrieval_preserves_candidate_sources_and_causal_evidence(self) -> None:
        self.statement("fact.pg", "PostgreSQL stores immutable authority facts.")
        self.statement("constraint.vector", "Vector similarity is candidate generation only.", statement_type=StatementType.CONSTRAINT)
        self.statement("claim.ledger", "The ledger separates authority from indexes.", statement_type=StatementType.CLAIM)
        self.relation("relation.pg.claim", "fact.pg", "claim.ledger")
        self.relation(
            "relation.vector.claim",
            "constraint.vector",
            "claim.ledger",
            RelationType.REQUIRES,
        )
        profile = EmbeddingProfile(
            profile_id="test.profile.v1",
            provider="test",
            model="fixture",
            model_version="1",
            dimensions=3,
            normalization="L2",
            input_template_version="statement-v1",
            created_by="test",
        )
        self.ledger.register_embedding_profile(profile)
        embedded_text = render_statement_embedding_input(
            self.ledger.get_current_revision("claim.ledger"),
            template_version=profile.input_template_version,
        )
        self.ledger.store_embedding(
            statement_id="claim.ledger",
            revision=1,
            profile_id=profile.profile_id,
            embedding=[1, 0, 0],
            embedded_text_sha256=hashlib.sha256(
                embedded_text.encode("utf-8")
            ).hexdigest(),
        )
        lexical = self.ledger.lexical_search("authority indexes")
        semantic = self.ledger.semantic_search(
            [1, 0, 0], profile_id=profile.profile_id
        )
        self.assertEqual(lexical[0].revision.statement_id, "claim.ledger")
        self.assertEqual(semantic[0].revision.statement_id, "claim.ledger")

        pack = self.ledger.retrieve_context_pack(
            task_id="task.ledger",
            agent_role="engineering",
            query="authority indexes",
            query_embedding=[1, 0, 0],
            embedding_profile_id=profile.profile_id,
            scope={"module": "ledger"},
            limit=3,
        )
        claim = next(
            value
            for value in pack.candidates
            if value.revision.statement_id == "claim.ledger"
        )
        self.assertEqual(set(claim.sources), {"LEXICAL", "SEMANTIC"})
        self.assertEqual(
            {value.statement_id for value in pack.causal_revisions},
            {"fact.pg", "constraint.vector"},
        )
        self.assertTrue(pack.evidence_descriptors)
        self.assertIn("lexical_candidates", pack.retrieval_trace)

    def test_supersede_is_atomic_and_does_not_mutate_old_revision(self) -> None:
        self.statement("claim.versioned", "Old statement.", statement_type=StatementType.CLAIM)
        evidence_id = self.evidence("evidence.claim.versioned.2", b"new")
        result = self.ledger.supersede_statement(
            StatementRevision(
                statement_id="claim.versioned",
                revision=2,
                statement_type=StatementType.CLAIM,
                content="New statement.",
                structured_conditions={},
                validity=RevisionValidity.ACTIVE,
                scope={"module": "ledger"},
                confidence=1.0,
                created_by="reviewer",
                evidence_ids=(evidence_id,),
            ),
            reason="new evidence replaced the old claim",
        )
        self.assertEqual(result.revision, 2)
        self.assertEqual(self.ledger.get_current_revision("claim.versioned").revision, 2)
        snapshot = self.ledger.export_snapshot()
        old = next(
            row
            for row in snapshot["revisions"]
            if row["statement_id"] == "claim.versioned" and row["revision"] == 1
        )
        self.assertEqual(old["content"], "Old statement.")
        self.assertTrue(
            any(row["relation_type"] == "SUPERSEDES" for row in snapshot["relations"])
        )

    def test_relation_cycle_and_cross_project_reference_are_rejected(self) -> None:
        for statement_id in ("fact.a", "fact.b", "fact.c"):
            self.statement(statement_id, statement_id)
        self.relation("relation.a.b", "fact.a", "fact.b")
        self.relation("relation.b.c", "fact.b", "fact.c")
        evidence_id = self.evidence("evidence.relation.c.a", b"cycle")
        with self.assertRaisesRegex(ValueError, "cycle"):
            self.ledger.create_relation(
                StatementRelation(
                    relation_id="relation.c.a",
                    from_statement_id="fact.c",
                    from_revision=1,
                    to_statement_id="fact.a",
                    to_revision=1,
                    relation_type=RelationType.SUPPORTS,
                    applicable_conditions={},
                    reason="illegal circular support",
                    created_by="test",
                    evidence_ids=(evidence_id,),
                )
            )

        other = ReasoningLedger(
            TEST_DSN,
            project_id=f"other_{uuid4().hex}",
            schema=TEST_SCHEMA,
            embedding_dimensions=3,
        )
        other_evidence = EvidenceDescriptor(
            evidence_id="evidence.other",
            path=".aegis/reasoning_ledger/artifacts/evidence/other.bin",
            size=1,
            sha256=hashlib.sha256(b"x").hexdigest(),
            source_identity={"kind": "test_fixture"},
            captured_at=CAPTURED_AT,
            scope={},
            created_by="test",
        )
        other.register_evidence(other_evidence)
        other.create_statement(
            StatementRevision(
                statement_id="fact.other",
                revision=1,
                statement_type=StatementType.FACT,
                content="Other project.",
                structured_conditions={},
                validity=RevisionValidity.ACTIVE,
                scope={},
                confidence=1.0,
                created_by="test",
                evidence_ids=(other_evidence.evidence_id,),
            )
        )
        with self.assertRaisesRegex(KeyError, "missing revision"):
            self.ledger.create_relation(
                StatementRelation(
                    relation_id="relation.cross-project",
                    from_statement_id="fact.a",
                    from_revision=1,
                    to_statement_id="fact.other",
                    to_revision=1,
                    relation_type=RelationType.SUPPORTS,
                    applicable_conditions={},
                    reason="cross project link",
                    created_by="test",
                    evidence_ids=(evidence_id,),
                )
            )

    def test_authority_revision_update_is_rejected_by_database(self) -> None:
        self.statement("fact.immutable", "Immutable.")
        with self.assertRaises(psycopg.errors.RaiseException):
            with self.ledger.connect() as conn:
                conn.execute(
                    f"UPDATE {TEST_SCHEMA}.statement_revision SET content = 'changed' "
                    "WHERE project_id = %s AND statement_id = %s",
                    (self.project_id, "fact.immutable"),
                )


class ReasoningLedgerProjectFileTests(unittest.TestCase):
    def test_bootstrap_creates_project_owned_v2_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            result = bootstrap_project_ledger(
                project_root,
                project_id="demo_project",
                schema="demo_ledger",
                embedding_dimensions=3,
            )
            config = ProjectLedgerConfig.load(project_root)
            self.assertEqual(config.project_id, "demo_project")
            self.assertEqual(config.authority_schema_version, 2)
            self.assertFalse(config.approximate_vector_index)
            self.assertTrue(config.migration_path.exists())
            self.assertIn("embedding vector(3)", result.migration_sql)
            self.assertNotIn("USING hnsw", result.migration_sql)

    def test_project_config_rejects_unsupported_authority_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            bootstrap_project_ledger(
                project_root,
                project_id="demo_project",
                schema="demo_ledger",
                embedding_dimensions=3,
            )
            config_path = project_root / "config" / "reasoning_ledger.json"
            data = json.loads(config_path.read_text(encoding="utf-8"))

            invalid_values = (
                ("backend", "sqlite"),
                ("authority_schema_version", 1),
                ("approximate_vector_index", True),
                ("approximate_vector_index", "false"),
            )
            for field_name, invalid_value in invalid_values:
                with self.subTest(field_name=field_name):
                    invalid_data = json.loads(json.dumps(data))
                    invalid_data["ledger"][field_name] = invalid_value
                    config_path.write_text(
                        json.dumps(invalid_data),
                        encoding="utf-8",
                    )
                    with self.assertRaises(ValueError):
                        ProjectLedgerConfig.load(project_root)

            missing_data = json.loads(json.dumps(data))
            del missing_data["ledger"]["authority_schema_version"]
            config_path.write_text(json.dumps(missing_data), encoding="utf-8")
            with self.assertRaises(ValueError):
                ProjectLedgerConfig.load(project_root)

            extra_data = json.loads(json.dumps(data))
            extra_data["ledger"]["unrecognized_contract"] = True
            config_path.write_text(json.dumps(extra_data), encoding="utf-8")
            with self.assertRaises(ValueError):
                ProjectLedgerConfig.load(project_root)

    def test_project_config_rejects_invalid_operational_bounds(self) -> None:
        with self.assertRaises(ValueError):
            ProjectLedgerConfig(
                project_id="demo_project",
                project_root=Path.cwd(),
                embedding_dimensions=0,
            )
        with self.assertRaises(ValueError):
            ProjectLedgerConfig(
                project_id="demo_project",
                project_root=Path.cwd(),
                minimum_postgresql_major=15,
            )
        with self.assertRaises(ValueError):
            ProjectLedgerConfig(
                project_id="demo_project",
                project_root=Path.cwd(),
                minimum_pgvector_version="0.7.4",
            )

    def test_build_init_sql_rejects_unsafe_schema_name(self) -> None:
        with self.assertRaises(ValueError):
            build_init_sql(schema="ledger;drop")


class MainCliSmokeTests(unittest.TestCase):
    def test_main_ledger_probe_uses_project_config(self) -> None:
        require_test_database()
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            schema = f"aegis_cli_{uuid4().hex}"
            bootstrap_project_ledger(
                project_root,
                project_id=f"cli_project_{uuid4().hex}",
                schema=schema,
                embedding_dimensions=3,
            )
            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPO_ROOT / "src")
            env["AEGIS_LEDGER_DSN"] = TEST_DSN
            try:
                migrate = subprocess.run(
                    [
                        sys.executable,
                        str(REPO_ROOT / "src" / "main.py"),
                        "ledger",
                        "migrate",
                        "--project-root",
                        str(project_root),
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )
                self.assertEqual(migrate.returncode, 0, migrate.stderr)
                probe = subprocess.run(
                    [
                        sys.executable,
                        str(REPO_ROOT / "src" / "main.py"),
                        "ledger",
                        "probe",
                        "--project-root",
                        str(project_root),
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )
                self.assertEqual(probe.returncode, 0, probe.stderr)
                payload = json.loads(probe.stdout)
                self.assertIsNotNone(payload["vector"])
            finally:
                with psycopg.connect(TEST_DSN, autocommit=True) as conn:
                    conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")


if __name__ == "__main__":
    unittest.main()
