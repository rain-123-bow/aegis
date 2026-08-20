from __future__ import annotations

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
    CreateItem,
    EdgeRelation,
    ItemType,
    LinkItems,
    ProjectLedgerConfig,
    ReasoningLedger,
    bootstrap_project_ledger,
    build_init_sql,
)


TEST_DSN = os.environ.get(
    "AEGIS_LEDGER_DSN",
    "postgresql://aegis:aegis@127.0.0.1:5432/aegis_ledger?connect_timeout=3",
)
TEST_SCHEMA = "aegis_test_ledger"


class ReasoningLedgerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
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

    def test_schema_is_real_postgresql_pgvector_schema(self) -> None:
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
        self.assertEqual(extension["extversion"], "0.6.0")
        self.assertEqual(
            [row["table_name"] for row in tables],
            ["reasoning_edge", "reasoning_event", "reasoning_item", "schema_metadata"],
        )

    def test_items_edges_tracing_impact_invalidation_search_and_export(self) -> None:
        self.ledger.add_item(
            CreateItem(
                id="input.req.initial",
                type=ItemType.INPUT,
                scope={"module": "global", "task": "initial"},
                content="Use PostgreSQL and pgvector as the project reasoning ledger.",
                artifact_path=".aegis/reasoning_ledger/artifacts/requirements/initial/README.md",
                confidence=1.0,
                embedding=[1, 0, 0],
                created_by="master_pm",
            )
        )
        self.ledger.add_item(
            CreateItem(
                id="fact.db.pgvector.enabled",
                type=ItemType.FACT,
                scope={"module": "ledger", "task": "bootstrap"},
                content="The aegis_ledger database has pgvector enabled.",
                confidence=1.0,
                embedding=[0.9, 0.1, 0],
                created_by="test_executor",
            )
        )
        self.ledger.add_item(
            CreateItem(
                id="claim.ledger.real_backend",
                type=ItemType.CLAIM,
                scope={"module": "ledger", "task": "implementation"},
                content="The reasoning ledger persists to a real PostgreSQL pgvector backend.",
                artifact_path=".aegis/reasoning_ledger/artifacts/claims/real_backend/README.md",
                confidence=0.95,
                embedding=[0.95, 0.05, 0],
                created_by="execution_implementer",
            )
        )
        edge_a = self.ledger.link_items(
            LinkItems(
                from_id="input.req.initial",
                to_id="claim.ledger.real_backend",
                relation=EdgeRelation.SUPPORTS,
                reason="user requirement selects PostgreSQL + pgvector",
                created_by="execution_implementer",
            )
        )
        self.ledger.link_items(
            LinkItems(
                from_id="fact.db.pgvector.enabled",
                to_id="claim.ledger.real_backend",
                relation=EdgeRelation.SUPPORTS,
                reason="database extension proves real vector backend is available",
                created_by="test_executor",
            )
        )

        claim = self.ledger.get_item("claim.ledger.real_backend")
        self.assertEqual(claim.level, 1)
        self.assertEqual(edge_a.relation, "supports")

        cause_items, cause_edges = self.ledger.trace_causes("claim.ledger.real_backend")
        self.assertEqual(
            {item.id for item in cause_items},
            {"input.req.initial", "fact.db.pgvector.enabled"},
        )
        self.assertEqual(len(cause_edges), 2)

        impact_items, impact_edges = self.ledger.analyze_impact("input.req.initial")
        self.assertEqual([item.id for item in impact_items], ["claim.ledger.real_backend"])
        self.assertEqual(len(impact_edges), 1)

        search_results = self.ledger.semantic_search([1, 0, 0], limit=2)
        self.assertEqual(search_results[0].item.id, "input.req.initial")
        self.assertLess(search_results[0].distance, search_results[1].distance)

        pack = self.ledger.retrieve_context_pack(
            task_id="task.ledger.implementation",
            agent_role="execution_implementer",
            query="real PostgreSQL ledger backend",
            query_embedding=[0.95, 0.05, 0],
            scope={"module": "ledger"},
            limit=3,
        )
        payload = pack.to_agent_payload()
        self.assertEqual(payload["project_id"], self.project_id)
        self.assertIn(
            ".aegis/reasoning_ledger/artifacts/claims/real_backend/README.md",
            payload["required_artifact_paths"],
        )

        stale_items = self.ledger.invalidate_item(
            "input.req.initial",
            reason="requirement changed",
            created_by="master_pm",
        )
        self.assertEqual([item.id for item in stale_items], ["claim.ledger.real_backend"])
        self.assertEqual(self.ledger.get_item("input.req.initial").status, "invalid")
        self.assertEqual(self.ledger.get_item("claim.ledger.real_backend").status, "stale")

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "snapshot.jsonl"
            snapshot = self.ledger.export_snapshot(output_path)
            self.assertEqual(len(snapshot["items"]), 3)
            self.assertEqual(len(snapshot["edges"]), 2)
            self.assertGreaterEqual(len(snapshot["events"]), 6)
            self.assertTrue(output_path.read_text(encoding="utf-8").strip())

    def test_supersede_and_index_rebuild_are_persisted(self) -> None:
        self.ledger.add_item(
            CreateItem(
                id="claim.old",
                type="claim",
                scope={"module": "ledger"},
                content="Old claim.",
                embedding=[0, 1, 0],
                created_by="reviewer",
            )
        )
        new_item = self.ledger.supersede_item(
            "claim.old",
            CreateItem(
                id="claim.new",
                type="claim",
                scope={"module": "ledger"},
                content="New claim.",
                embedding=[0, 0.9, 0.1],
                created_by="reviewer",
            ),
            reason="new evidence replaced old claim",
        )
        indexed_count = self.ledger.rebuild_index(created_by="test_executor")

        self.assertEqual(new_item.id, "claim.new")
        self.assertEqual(self.ledger.get_item("claim.old").status, "superseded")
        self.assertEqual(indexed_count, 2)


class ReasoningLedgerProjectFileTests(unittest.TestCase):
    def test_bootstrap_creates_project_owned_files(self) -> None:
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
            self.assertTrue((project_root / ".aegis" / "project.json").exists())
            self.assertTrue(config.migration_path.exists())
            self.assertIn("embedding vector(3)", result.migration_sql)
            self.assertTrue(
                (
                    project_root
                    / ".aegis"
                    / "reasoning_ledger"
                    / "artifacts"
                    / "claims"
                ).is_dir()
            )

    def test_build_init_sql_rejects_unsafe_schema_name(self) -> None:
        with self.assertRaises(ValueError):
            build_init_sql(schema="ledger;drop")


class MainCliSmokeTests(unittest.TestCase):
    def test_main_ledger_probe_uses_project_config(self) -> None:
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
                self.assertEqual(payload["database"], "aegis_ledger")
                self.assertEqual(payload["user"], "aegis")
                self.assertEqual(payload["vector"], "0.6.0")
            finally:
                with psycopg.connect(TEST_DSN, autocommit=True) as conn:
                    conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")


if __name__ == "__main__":
    unittest.main()
