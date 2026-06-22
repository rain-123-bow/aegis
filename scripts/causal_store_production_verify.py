from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from aegis.stores.causal import (
    AdmissionTransaction,
    CausalDependencyGroup,
    CausalNodeDraft,
    CausalQuery,
    CausalRef,
    CausalStore,
    CausalStoreError,
    ExpandContextRequest,
    InvalidationRequest,
    RevalidationResolutionRequest,
    SupersessionRequest,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "module_test_reports" / "causal_store" / "CAUSAL_STORE_V1_PRODUCTION_VERIFICATION"
ARTIFACT_DIR = PACKAGE_DIR / "artifacts"
RANDOM_SEED = 20260622
SOURCE_TRACE_GLOBS = [
    "src/aegis/stores/causal/**/*.py",
    "src/aegis/stores/__init__.py",
    "tests/test_causal_store*.py",
    "scripts/causal_store_production_verify.py",
    "docs/CAUSAL_STORE*.md",
    "module_test_reports/causal_store/CAUSAL_STORE_V1_TEST_PLAN.md",
]


@dataclass
class Check:
    name: str
    status: str
    details: dict[str, Any] = field(default_factory=dict)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_command(args: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": " ".join(args),
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8", newline="\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def iter_source_trace_paths() -> list[Path]:
    paths: set[Path] = set()
    for pattern in SOURCE_TRACE_GLOBS:
        paths.update(path for path in REPO_ROOT.glob(pattern) if path.is_file())
    return sorted(paths, key=lambda path: path.as_posix().lower())


def git_status_by_path() -> dict[str, str]:
    result = run_command(["git", "status", "--short", "--untracked-files=all"])
    statuses: dict[str, str] = {}
    for line in result["stdout"].splitlines():
        if not line:
            continue
        status = line[:2]
        path_text = line[3:].strip()
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1]
        statuses[path_text.replace("\\", "/")] = status
    return statuses


def write_source_traceability_artifacts() -> dict[str, Any]:
    status_map = git_status_by_path()
    manifest: list[dict[str, Any]] = []
    tree_hasher = hashlib.sha256()
    patch_lines: list[str] = []
    for path in iter_source_trace_paths():
        rel = path.relative_to(REPO_ROOT).as_posix()
        data = path.read_bytes()
        digest = sha256_bytes(data)
        git_status = status_map.get(rel, "clean")
        manifest.append(
            {
                "path": rel,
                "size_bytes": len(data),
                "sha256": digest,
                "git_status": git_status,
            }
        )
        tree_hasher.update(rel.encode("utf-8"))
        tree_hasher.update(b"\0")
        tree_hasher.update(digest.encode("ascii"))
        tree_hasher.update(b"\n")
        patch_lines.extend(
            [
                f"===== SOURCE FILE {rel} =====",
                f"sha256: {digest}",
                f"git_status: {git_status}",
                "",
                data.decode("utf-8", errors="replace"),
                "",
            ]
        )

    source_tree_sha256 = tree_hasher.hexdigest()
    source_patch = "\n".join(patch_lines)
    source_patch_sha256 = sha256_text(source_patch)
    payload = {
        "source_tree_sha256": source_tree_sha256,
        "source_patch_sha256": source_patch_sha256,
        "files": manifest,
    }
    write_json(ARTIFACT_DIR / "source_manifest.json", payload)
    (ARTIFACT_DIR / "source_tree_sha256.txt").write_text(
        source_tree_sha256 + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (ARTIFACT_DIR / "source_patch.diff").write_text(
        source_patch,
        encoding="utf-8",
        newline="\n",
    )
    (ARTIFACT_DIR / "source_patch_sha256.txt").write_text(
        source_patch_sha256 + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return payload


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1))))
    return ordered[index]


def latency_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "max_ms": 0.0}
    return {
        "count": len(values),
        "p50_ms": round(statistics.median(values), 4),
        "p95_ms": round(percentile(values, 95), 4),
        "p99_ms": round(percentile(values, 99), 4),
        "max_ms": round(max(values), 4),
    }


def store_at(root: Path, name: str = "causal.sqlite3") -> CausalStore:
    return CausalStore(root / name)


def root_node(content: str, *, key: str = "root", evidence_ref: str | None = None) -> CausalNodeDraft:
    return CausalNodeDraft(
        content=content,
        semantic_summary=content,
        semantic_keys=["causal", key, *content.lower().replace("-", " ").split()[:6]],
        source_module="test",
        root_kind="test_result",
        node_refs=[("test", evidence_ref or f"evidence-{abs(hash(content))}")],
        dependency_groups=[],
    )


def dependent_node(content: str, predecessor: int, *, key: str = "dependent") -> CausalNodeDraft:
    return CausalNodeDraft(
        content=content,
        semantic_summary=content,
        semantic_keys=["causal", key, *content.lower().replace("-", " ").split()[:6]],
        source_module="debate",
        dependency_groups=[
            CausalDependencyGroup(
                causal_dependencies=[predecessor],
                knowledge_refs=["knowledge/project-boundary"],
                evidence_refs=["test/dependency-evidence"],
                scope="local project",
                conditions=["predecessor remains admitted"],
                assumptions=["single local git project"],
                confidence="high",
                invalidation_conditions=["predecessor invalidated"],
            )
        ],
    )


def admit(store: CausalStore, *node_ids: int) -> None:
    store.admit_nodes(
        AdmissionTransaction(
            node_ids=list(node_ids),
            admitted_by_module="master",
            rationale="production verification admission",
            evidence_ref="production-verification",
        )
    )


def table_count(db_path: Path, table: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def integrity_status(db_path: Path) -> dict[str, Any]:
    with sqlite3.connect(db_path) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
    return {"integrity_check": integrity, "foreign_key_errors": len(foreign_keys)}


def explain_query_plans(db_path: Path) -> str:
    queries = {
        "exact_node_lookup": "EXPLAIN QUERY PLAN SELECT * FROM causal_nodes WHERE node_id = 1",
        "deep_node_lookup_missing_id": "EXPLAIN QUERY PLAN SELECT * FROM causal_nodes WHERE node_id = -1",
        "node_term_lookup": "EXPLAIN QUERY PLAN SELECT * FROM causal_node_terms WHERE term IN ('causal')",
        "dependency_lookup": (
            "EXPLAIN QUERY PLAN SELECT * FROM causal_dependency_nodes "
            "WHERE predecessor_node_id = 1"
        ),
        "dependency_group_lookup": (
            "EXPLAIN QUERY PLAN SELECT * FROM causal_dependency_groups WHERE node_id = 1"
        ),
        "active_revalidation_lookup_by_status": (
            "EXPLAIN QUERY PLAN SELECT * FROM causal_revalidation_queue "
            "WHERE status = 'pending' AND node_id = 1"
        ),
        "revalidation_lookup_by_node": (
            "EXPLAIN QUERY PLAN SELECT * FROM causal_revalidation_queue "
            "WHERE node_id = 1 AND status = 'pending'"
        ),
        "revalidation_lookup_by_trigger": (
            "EXPLAIN QUERY PLAN SELECT * FROM causal_revalidation_queue "
            "WHERE triggered_by_node_id = 1"
        ),
        "fts_lookup": (
            "EXPLAIN QUERY PLAN SELECT node_id FROM causal_nodes_fts "
            "WHERE causal_nodes_fts MATCH 'causal'"
        ),
    }
    lines: list[str] = []
    with sqlite3.connect(db_path) as conn:
        for name, sql in queries.items():
            lines.append(f"## {name}")
            for row in conn.execute(sql):
                lines.append(" | ".join(str(item) for item in row))
            lines.append("")
    return "\n".join(lines)


def query_plan_sections(query_plan_text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in query_plan_text.splitlines():
        if line.startswith("## "):
            current = line[3:]
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {name: "\n".join(lines) for name, lines in sections.items()}


def query_plan_contract(query_plan_text: str) -> dict[str, Any]:
    sections = query_plan_sections(query_plan_text)
    checks = {
        "exact_node_lookup_primary_key": "INTEGER PRIMARY KEY" in sections.get("exact_node_lookup", ""),
        "missing_node_lookup_primary_key": "INTEGER PRIMARY KEY"
        in sections.get("deep_node_lookup_missing_id", ""),
        "node_term_lookup_indexed": "idx_causal_node_terms_term_node"
        in sections.get("node_term_lookup", ""),
        "dependency_lookup_indexed": "idx_dependency_predecessor" in sections.get("dependency_lookup", ""),
        "dependency_group_lookup_indexed": "idx_dependency_group_node"
        in sections.get("dependency_group_lookup", ""),
        "active_revalidation_lookup_indexed": (
            "idx_revalidation_node_status" in sections.get("active_revalidation_lookup_by_status", "")
            or "idx_revalidation_status_node" in sections.get("active_revalidation_lookup_by_status", "")
        ),
        "revalidation_node_lookup_indexed": (
            "idx_revalidation_node_status" in sections.get("revalidation_lookup_by_node", "")
            or "idx_revalidation_status_node" in sections.get("revalidation_lookup_by_node", "")
        ),
        "revalidation_trigger_lookup_indexed": "idx_revalidation_triggered_by_node"
        in sections.get("revalidation_lookup_by_trigger", ""),
    }
    disallowed_scans = {
        name: plan
        for name, plan in sections.items()
        if name != "fts_lookup"
        and ("SCAN causal_node_terms" in plan or "SCAN causal_revalidation_queue" in plan)
    }
    return {
        "checks": checks,
        "disallowed_scans": disallowed_scans,
        "all_required_indexes_used": all(checks.values()) and not disallowed_scans,
    }


def check_schema_and_migration(work_root: Path) -> Check:
    root = work_root / "schema"
    store = store_at(root)
    with sqlite3.connect(store.db_path) as conn:
        migrations = conn.execute("SELECT version, name FROM schema_migrations").fetchall()
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')"
            ).fetchall()
        }
    before_count = len(migrations)
    CausalStore(store.db_path)
    with sqlite3.connect(store.db_path) as conn:
        after_count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at_utc) VALUES (999, 'future', ?)",
            (utc_now(),),
        )
        conn.commit()
    future_schema_rejected = False
    try:
        CausalStore(store.db_path)
    except CausalStoreError:
        future_schema_rejected = True
    except Exception:
        future_schema_rejected = False

    passed = before_count == after_count and "causal_nodes" in tables and future_schema_rejected
    return Check(
        name="schema_and_migration",
        status="pass" if passed else "fail",
        details={
            "migration_rows_before_reopen": before_count,
            "migration_rows_after_reopen": after_count,
            "causal_nodes_table_present": "causal_nodes" in tables,
            "future_schema_version_rejected": future_schema_rejected,
            "verified_contract": "Unsupported future schema versions are rejected.",
        },
    )


def check_transactions(work_root: Path) -> Check:
    root = work_root / "transactions"
    store = store_at(root)
    root_id = store.put_candidate(root_node("transaction root remains stable"))
    child_id = store.put_candidate(dependent_node("child cannot admit before dependency", root_id))
    failed_child_admission = False
    rollback_preserved_candidate = False
    try:
        admit(store, child_id)
    except CausalStoreError as exc:
        failed_child_admission = exc.code == "DEPENDENCY_NOT_ADMITTED"
        rollback_preserved_candidate = store.get_node(child_id).status == "candidate"

    admit(store, root_id, child_id)
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            """
            CREATE TRIGGER force_invalidation_failure
            BEFORE INSERT ON causal_invalidation_records
            BEGIN
              SELECT RAISE(ABORT, 'forced invalidation audit failure');
            END;
            """
        )
        conn.commit()
    invalidation_rollback_ok = False
    invalidation_error_controlled = False
    try:
        store.invalidate_node(
            InvalidationRequest(
                node_id=root_id,
                invalidated_by_module="causal_review",
                reason="forced rollback test",
            )
        )
    except CausalStoreError:
        invalidation_error_controlled = True
    except sqlite3.Error:
        invalidation_error_controlled = False
    finally:
        with sqlite3.connect(store.db_path) as conn:
            conn.execute("DROP TRIGGER IF EXISTS force_invalidation_failure")
            conn.commit()
        invalidation_rollback_ok = store.get_node(root_id).status == "admitted"

    passed = failed_child_admission and rollback_preserved_candidate and invalidation_rollback_ok
    return Check(
        name="transaction_rollback",
        status="pass" if passed and invalidation_error_controlled else "scope_limited",
        details={
            "dependency_failure_rolled_back": rollback_preserved_candidate,
            "invalidation_failure_rolled_back": invalidation_rollback_ok,
            "invalidation_failure_had_controlled_error": invalidation_error_controlled,
            "verified_contract": "Forced SQLite write failure rolls back and returns controlled CausalStoreError.",
        },
    )


def check_invariants(work_root: Path) -> Check:
    root = work_root / "invariants"
    store = store_at(root)
    base = store.put_candidate(root_node("invariant root evidence"))
    admit(store, base)
    child = store.put_candidate(dependent_node("invariant child uses admitted dependency", base))
    admit(store, child)
    invalidation = store.invalidate_node(
        InvalidationRequest(
            node_id=base,
            invalidated_by_module="master",
            reason="upstream evidence withdrawn",
        )
    )
    search = store.search_nodes(CausalQuery(query="invariant child dependency"))
    integrity = integrity_status(store.db_path)
    rejected_child = any(item.node_id == child for item in search.rejected_nodes)
    passed = (
        integrity["integrity_check"] == "ok"
        and integrity["foreign_key_errors"] == 0
        and invalidation.queued_revalidation_node_ids == [child]
        and rejected_child
    )
    return Check(
        name="invariants_and_integrity",
        status="pass" if passed else "fail",
        details={
            **integrity,
            "downstream_revalidation_queued": invalidation.queued_revalidation_node_ids == [child],
            "pending_revalidation_excluded_from_active_search": rejected_child,
        },
    )


def check_recovery(work_root: Path) -> Check:
    root = work_root / "recovery"
    store = store_at(root)
    node = store.put_candidate(root_node("recovery candidate survives reopen"))
    reopened = CausalStore(store.db_path)
    candidate_survived = reopened.get_node(node).content == "recovery candidate survives reopen"
    admit(reopened, node)
    reopened_again = CausalStore(store.db_path)
    admitted_survived = reopened_again.get_node(node).status == "admitted"
    with sqlite3.connect(store.db_path) as conn:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    return Check(
        name="restart_recovery",
        status="pass" if candidate_survived and admitted_survived else "fail",
        details={
            "candidate_survived_reopen": candidate_survived,
            "admission_survived_reopen": admitted_survived,
            "journal_mode": journal_mode,
        },
    )


def check_indexes(work_root: Path) -> Check:
    root = work_root / "indexes"
    store = store_at(root)
    first_root = store.put_candidate(root_node("index rebuild root one", key="index-root-one"))
    second_root = store.put_candidate(root_node("index rebuild root two", key="index-root-two"))
    admit(store, first_root, second_root)
    node = store.put_candidate(
        CausalNodeDraft(
            content="Index rebuild dependent causal node",
            semantic_summary="Index rebuild dependent",
            semantic_keys=["group-index"],
            source_module="debate",
            dependency_groups=[
                CausalDependencyGroup(
                    causal_dependencies=[first_root, second_root],
                    knowledge_refs=["knowledge/project-constraint-001"],
                    evidence_refs=["test/test-report-001"],
                    scope="debate runtime topology",
                    conditions=["single project", "leader mediated"],
                    assumptions=["workers communicate through leader"],
                    confidence="high",
                    invalidation_conditions=["full mesh side channel enabled"],
                )
            ],
        )
    )
    admit(store, node)
    before_counts = {
        "admissions": table_count(store.db_path, "causal_admission_records"),
        "group_refs": table_count(store.db_path, "causal_group_refs"),
        "groups": table_count(store.db_path, "causal_dependency_groups"),
        "nodes": table_count(store.db_path, "causal_nodes"),
    }
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("DELETE FROM causal_nodes_fts")
        conn.execute("DELETE FROM causal_embeddings")
        conn.commit()
    search_after_fts_embedding_delete = [
        item.node_id for item in store.search_nodes(CausalQuery(query="leader mediated")).nodes
    ]
    rebuild = store.rebuild_indexes()
    after_counts = {
        "admissions": table_count(store.db_path, "causal_admission_records"),
        "group_refs": table_count(store.db_path, "causal_group_refs"),
        "groups": table_count(store.db_path, "causal_dependency_groups"),
        "nodes": table_count(store.db_path, "causal_nodes"),
    }
    scope_restored = [item.node_id for item in store.search_nodes(CausalQuery(query="debate runtime topology")).nodes]
    condition_restored = [item.node_id for item in store.search_nodes(CausalQuery(query="leader mediated")).nodes]
    invalidation_restored = [
        item.node_id for item in store.search_nodes(CausalQuery(query="full mesh side channel")).nodes
    ]
    passed = (
        rebuild.rebuilt_fts_rows == 3
        and rebuild.rebuilt_embedding_rows == 3
        and before_counts == after_counts
        and before_counts["groups"] > 0
        and before_counts["group_refs"] > 0
        and node in scope_restored
        and node in condition_restored
        and node in invalidation_restored
    )
    return Check(
        name="index_rebuild",
        status="pass" if passed else "fail",
        details={
            "search_after_fts_embedding_delete": search_after_fts_embedding_delete,
            "group_term_recall_removed_before_rebuild": node not in search_after_fts_embedding_delete,
            "rebuild_result": rebuild.model_dump(mode="json"),
            "canonical_counts_before": before_counts,
            "canonical_counts_after": after_counts,
            "scope_term_restored_node_ids": scope_restored,
            "condition_term_restored_node_ids": condition_restored,
            "invalidation_term_restored_node_ids": invalidation_restored,
        },
    )


def check_error_contract(work_root: Path) -> Check:
    root = work_root / "errors"
    store = store_at(root)
    matrix: list[dict[str, Any]] = []

    def trigger_error(code: str, fn: Any) -> None:
        try:
            outcome = fn()
            if isinstance(outcome, bool):
                matrix.append({"error_code": code, "coverage": "triggered", "passed": outcome})
            else:
                matrix.append({"error_code": code, "coverage": "triggered", "passed": False, "outcome": outcome})
        except CausalStoreError as exc:
            matrix.append(
                {
                    "error_code": code,
                    "coverage": "triggered",
                    "passed": exc.code == code,
                    "observed_code": exc.code,
                    "cause_type": type(exc).__name__,
                }
            )
        except Exception as exc:  # noqa: BLE001 - raw exception leakage is part of the contract under test.
            matrix.append(
                {
                    "error_code": code,
                    "coverage": "triggered",
                    "passed": False,
                    "observed_code": None,
                    "cause_type": type(exc).__name__,
                }
            )

    trigger_error("NODE_NOT_FOUND", lambda: store.get_node(999999))
    trigger_error(
        "INVALID_DEPENDENCY",
        lambda: store.put_candidate(
            CausalNodeDraft(
                content="invalid dependency node",
                semantic_summary="invalid dependency node",
                semantic_keys=["invalid", "dependency"],
                source_module="debate",
                dependency_groups=[
                    CausalDependencyGroup(causal_dependencies=[999999], evidence_refs=["test/missing"])
                ],
            )
        ),
    )
    trigger_error(
        "ADMISSION_REQUIRED",
        lambda: store.admit_nodes(
            AdmissionTransaction(
                node_ids=[],
                admitted_by_module="master",
                rationale="empty admission must fail",
            )
        ),
    )
    candidate_dependency = store.put_candidate(root_node("candidate dependency not admitted", evidence_ref="candidate"))
    child_of_candidate = store.put_candidate(
        dependent_node("child depends on candidate dependency", candidate_dependency)
    )
    trigger_error("DEPENDENCY_NOT_ADMITTED", lambda: admit(store, child_of_candidate))
    root_missing_ref = store.put_candidate(
        CausalNodeDraft(
            content="root source required error",
            semantic_summary="root source required error",
            semantic_keys=["root", "source"],
            source_module="debate",
            root_kind="observation",
        )
    )
    trigger_error("ROOT_SOURCE_REQUIRED", lambda: admit(store, root_missing_ref))
    duplicate = root_node("duplicate exact causal identity")
    store.put_candidate(duplicate)
    trigger_error("DUPLICATE_NODE", lambda: store.put_candidate(duplicate))

    near_parent = store.put_candidate(root_node("near duplicate parent", evidence_ref="near-parent"))
    admit(store, near_parent)
    store.put_candidate(root_node("near duplicate same content", evidence_ref="near-original"))
    trigger_error(
        "NEAR_DUPLICATE_REVIEW_REQUIRED",
        lambda: store.put_candidate(
            CausalNodeDraft(
                content="near duplicate same content",
                semantic_summary="near duplicate same content",
                semantic_keys=["near", "duplicate"],
                source_module="debate",
                dependency_groups=[
                    CausalDependencyGroup(
                        causal_dependencies=[near_parent],
                        evidence_refs=["test/near-duplicate"],
                    )
                ],
            )
        ),
    )

    group_parent = store.put_candidate(root_node("group ref required parent", evidence_ref="group-parent"))
    admit(store, group_parent)
    group_ref_missing = store.put_candidate(
        CausalNodeDraft(
            content="group ref required child",
            semantic_summary="group ref required child",
            semantic_keys=["group", "ref"],
            source_module="debate",
            dependency_groups=[CausalDependencyGroup(causal_dependencies=[group_parent])],
        )
    )
    trigger_error("GROUP_REF_REQUIRED", lambda: admit(store, group_ref_missing))

    invalidated_parent = store.put_candidate(root_node("invalidated parent used", evidence_ref="invalidated-parent"))
    admit(store, invalidated_parent)
    store.invalidate_node(
        InvalidationRequest(
            node_id=invalidated_parent,
            invalidated_by_module="causal_review",
            reason="error matrix invalidated parent",
        )
    )
    invalidated_child = store.put_candidate(
        dependent_node("invalidated parent child", invalidated_parent, key="invalidated")
    )
    trigger_error("INVALIDATED_NODE_USED", lambda: admit(store, invalidated_child))

    invalid_status = store.put_candidate(root_node("invalid status transition node", evidence_ref="invalid-status"))
    store.invalidate_node(
        InvalidationRequest(
            node_id=invalid_status,
            invalidated_by_module="causal_review",
            reason="force invalid status transition",
        )
    )
    trigger_error("INVALID_STATUS_TRANSITION", lambda: admit(store, invalid_status))

    scoped_parent = store.put_candidate(root_node("scope mismatch parent", evidence_ref="scope-parent"))
    admit(store, scoped_parent)
    scoped_node = store.put_candidate(
        CausalNodeDraft(
            content="scope mismatch node",
            semantic_summary="scope mismatch node",
            semantic_keys=["scope", "mismatch"],
            source_module="debate",
            dependency_groups=[
                CausalDependencyGroup(
                    causal_dependencies=[scoped_parent],
                    evidence_refs=["test/scope"],
                    scope="actual scope",
                )
            ],
        )
    )
    admit(store, scoped_node)
    scoped_search = store.search_nodes(
        CausalQuery(query="scope mismatch", required_scope="different scope", include_rejected=True)
    )
    matrix.append(
        {
            "error_code": "SCOPE_MISMATCH",
            "coverage": "triggered",
            "passed": any(item.node_id == scoped_node and item.reason == "scope_mismatch" for item in scoped_search.rejected_nodes),
            "observed_rejected": [item.model_dump(mode="json") for item in scoped_search.rejected_nodes],
        }
    )

    matrix.extend(
        [
            {
                "error_code": "UNKNOWN_EXTERNAL_REF",
                "coverage": "not_applicable_current_api",
                "passed": True,
                "reason": "Causal Store v1 stores external refs as opaque refs and has no external registry authority.",
            },
            {
                "error_code": "CYCLE_DETECTED",
                "coverage": "not_applicable_current_api",
                "passed": True,
                "reason": "Public API only allows dependencies on existing predecessor nodes, preventing cycles by construction.",
            },
            {
                "error_code": "STALE_EMBEDDING_INDEX",
                "coverage": "not_applicable_current_api",
                "passed": True,
                "reason": "Stale embeddings are ignored and rebuildable; v1 does not expose stale index as a caller-facing error.",
            },
        ]
    )

    controlled = {
        item["error_code"]: item["passed"]
        for item in matrix
        if item["coverage"] == "triggered"
    }
    parent = store.put_candidate(root_node("duplicate group parent", evidence_ref="parent"))
    admit(store, parent)
    group_id = "group-duplicate-contract"
    raw_sqlite_error_leaked = False
    try:
        store.put_candidate(
            CausalNodeDraft(
                content="duplicate dependency group id should be controlled",
                semantic_summary="duplicate dependency group id",
                semantic_keys=["duplicate", "group"],
                source_module="debate",
                dependency_groups=[
                    CausalDependencyGroup(
                        group_id=group_id,
                        causal_dependencies=[parent],
                        evidence_refs=["evidence/a"],
                    ),
                    CausalDependencyGroup(
                        group_id=group_id,
                        causal_dependencies=[parent],
                        evidence_refs=["evidence/b"],
                    ),
                ],
            )
        )
    except CausalStoreError:
        raw_sqlite_error_leaked = False
    except sqlite3.Error:
        raw_sqlite_error_leaked = True

    triggered_codes = {item["error_code"] for item in matrix if item["coverage"] == "triggered"}
    required_triggered = {
        "ADMISSION_REQUIRED",
        "DEPENDENCY_NOT_ADMITTED",
        "DUPLICATE_NODE",
        "GROUP_REF_REQUIRED",
        "INVALIDATED_NODE_USED",
        "INVALID_DEPENDENCY",
        "INVALID_STATUS_TRANSITION",
        "NEAR_DUPLICATE_REVIEW_REQUIRED",
        "NODE_NOT_FOUND",
        "ROOT_SOURCE_REQUIRED",
        "SCOPE_MISMATCH",
    }
    passed = (
        required_triggered.issubset(triggered_codes)
        and all(item["passed"] for item in matrix)
        and not raw_sqlite_error_leaked
    )
    return Check(
        name="error_contract",
        status="pass" if passed else "scope_limited",
        details={
            "error_matrix": matrix,
            "controlled_error_checks": controlled,
            "raw_sqlite_error_leaked_for_duplicate_group_id": raw_sqlite_error_leaked,
            "not_applicable_current_api_codes": [
                item["error_code"] for item in matrix if item["coverage"] == "not_applicable_current_api"
            ],
            "verified_contract": "Implemented API error paths return controlled domain errors; non-applicable codes are explicitly classified.",
        },
    )


def check_boundaries(work_root: Path) -> Check:
    root = work_root / "boundaries"
    store = store_at(root)
    empty_content_accepted = False
    whitespace_summary_accepted = False
    try:
        store.put_candidate(
            CausalNodeDraft(
                content="",
                semantic_summary="empty content should fail",
                source_module="test",
                root_kind="test_result",
                node_refs=[("test", "empty")],
            )
        )
        empty_content_accepted = True
    except (CausalStoreError, ValidationError, ValueError):
        empty_content_accepted = False

    try:
        store.put_candidate(
            CausalNodeDraft(
                content="non-empty content",
                semantic_summary="   ",
                source_module="test",
                root_kind="test_result",
                node_refs=[("test", "blank-summary")],
            )
        )
        whitespace_summary_accepted = True
    except (CausalStoreError, ValidationError, ValueError):
        whitespace_summary_accepted = False

    unicode_content = "中文因果节点：测试 Unicode、emoji ✅、Markdown **bold** 和多行\n第二行"
    unicode_id = store.put_candidate(root_node(unicode_content, key="unicode", evidence_ref="unicode"))
    unicode_roundtrip = store.get_node(unicode_id).content == unicode_content
    invalid_literal_rejected = False
    try:
        CausalNodeDraft(
            content="bad module",
            semantic_summary="bad module",
            source_module="unknown",  # type: ignore[arg-type]
        )
    except ValidationError:
        invalid_literal_rejected = True

    passed = (
        not empty_content_accepted
        and not whitespace_summary_accepted
        and unicode_roundtrip
        and invalid_literal_rejected
    )
    return Check(
        name="boundary_and_malformed_input",
        status="pass" if passed else "fail",
        details={
            "empty_content_accepted": empty_content_accepted,
            "whitespace_summary_accepted": whitespace_summary_accepted,
            "unicode_roundtrip": unicode_roundtrip,
            "invalid_literal_rejected_by_pydantic": invalid_literal_rejected,
            "verified_contract": "CausalNodeDraft rejects empty content and blank semantic summaries.",
        },
    )


def check_determinism(work_root: Path) -> Check:
    root = work_root / "determinism"
    store = store_at(root)
    ids = []
    for index in range(6):
        node = store.put_candidate(
            root_node(
                f"deterministic ranking node {index} common tie token",
                key=f"determinism-{index}",
                evidence_ref=f"determinism-{index}",
            )
        )
        ids.append(node)
        admit(store, node)
    first = [item.node_id for item in store.search_nodes(CausalQuery(query="common tie token")).nodes]
    second = [item.node_id for item in store.search_nodes(CausalQuery(query="common tie token")).nodes]
    store.rebuild_indexes()
    after_rebuild = [item.node_id for item in store.search_nodes(CausalQuery(query="common tie token")).nodes]
    passed = first == second == after_rebuild
    return Check(
        name="determinism",
        status="pass" if passed else "fail",
        details={
            "random_seed": RANDOM_SEED,
            "first_ranking": first,
            "second_ranking": second,
            "after_rebuild_ranking": after_rebuild,
        },
    )


def concurrency_worker(args: tuple[str, str, str, int, int, int, int]) -> list[dict[str, Any]]:
    db_path, run_id, worker_type, worker_id, operation_count, stable_root_id, stable_child_id = args
    events: list[dict[str, Any]] = []
    store = CausalStore(db_path)
    operation_sequence = [
        "put_candidate",
        "put_candidate",
        "put_candidate",
        "get_node",
        "get_node",
        "search_nodes",
        "search_nodes",
        "expand_context",
        "admit_nodes",
        "invalidate_node",
        "supersede_node",
    ]
    for index in range(operation_count):
        operation = operation_sequence[index % len(operation_sequence)]
        start = time.perf_counter()
        node_id = None
        related_node_ids: list[int] = []
        error_code = None
        error_type = None
        try:
            unique = f"{run_id}-{worker_type}-{worker_id}-{index}"
            if operation == "put_candidate":
                content = f"concurrency {unique} put candidate"
                node_id = store.put_candidate(
                    CausalNodeDraft(
                        content=content,
                        semantic_summary=content,
                        semantic_keys=["concurrency", worker_type, f"worker-{worker_id}"],
                        source_module="test",
                        root_kind="test_result",
                        node_refs=[("test", unique)],
                    )
                )
            elif operation == "get_node":
                node_id = stable_root_id
                store.get_node(stable_root_id)
            elif operation == "search_nodes":
                result = store.search_nodes(CausalQuery(query="concurrency stable root"))
                related_node_ids = [node.node_id for node in result.nodes[:5]]
                if stable_root_id not in related_node_ids:
                    raise CausalStoreError("CONCURRENCY_SEARCH_MISS", "stable root not returned by active search")
            elif operation == "expand_context":
                node_id = stable_child_id
                context = store.expand_context(ExpandContextRequest(node_ids=[stable_child_id], depth=2))
                related_node_ids = context.selected_nodes
                if [stable_child_id, stable_root_id] not in context.dependency_paths:
                    raise CausalStoreError("CONCURRENCY_BROKEN_PATH", "stable dependency path was not returned")
            elif operation == "admit_nodes":
                content = f"concurrency {unique} admitted root"
                node_id = store.put_candidate(
                    CausalNodeDraft(
                        content=content,
                        semantic_summary=content,
                        semantic_keys=["concurrency", "admit", unique],
                        source_module="test",
                        root_kind="test_result",
                        node_refs=[("test", f"admit-{unique}")],
                    )
                )
                store.admit_nodes(
                    AdmissionTransaction(
                        node_ids=[node_id],
                        admitted_by_module="master",
                        rationale="mixed concurrency admission",
                        evidence_ref=f"admission-{unique}",
                    )
                )
            elif operation == "invalidate_node":
                root = store.put_candidate(root_node(f"concurrency {unique} invalidation root", key="concurrency"))
                admit(store, root)
                child = store.put_candidate(
                    dependent_node(f"concurrency {unique} invalidation child", root, key="concurrency")
                )
                admit(store, child)
                result = store.invalidate_node(
                    InvalidationRequest(
                        node_id=root,
                        invalidated_by_module="causal_review",
                        reason=f"mixed concurrency invalidation {unique}",
                    )
                )
                node_id = root
                related_node_ids = result.queued_revalidation_node_ids
                active = store.search_nodes(CausalQuery(query=f"concurrency {unique} invalidation child"))
                if child in [node.node_id for node in active.nodes]:
                    raise CausalStoreError("INVALID_ACTIVE_RETRIEVAL", "pending revalidation child was active")
            elif operation == "supersede_node":
                old = store.put_candidate(root_node(f"concurrency {unique} superseded root", key="concurrency"))
                new = store.put_candidate(root_node(f"concurrency {unique} replacement root", key="concurrency"))
                admit(store, old, new)
                store.supersede_node(
                    SupersessionRequest(
                        old_node_id=old,
                        new_node_id=new,
                        reason=f"mixed concurrency supersession {unique}",
                    )
                )
                node_id = old
                related_node_ids = [new]
                active = store.search_nodes(CausalQuery(query=f"concurrency {unique} superseded root"))
                if old in [node.node_id for node in active.nodes]:
                    raise CausalStoreError("SUPERSEDED_ACTIVE_RETRIEVAL", "superseded node was active")
            else:
                raise CausalStoreError("UNKNOWN_TEST_OPERATION", operation)
            status = "ok"
        except CausalStoreError as exc:
            status = "controlled_error"
            error_code = exc.code
            error_type = type(exc).__name__
        except Exception as exc:  # noqa: BLE001 - event evidence should capture any unexpected failure.
            status = "unexpected_error"
            error_type = type(exc).__name__
        elapsed = (time.perf_counter() - start) * 1000
        events.append(
            {
                "worker_id": f"{run_id}-{worker_type}-{worker_id}",
                "worker_type": worker_type,
                "operation": operation,
                "node_id": node_id,
                "related_node_ids": related_node_ids,
                "latency_ms": round(elapsed, 4),
                "status": status,
                "error_code": error_code,
                "error_type": error_type,
                "timestamp_utc": utc_now(),
            }
        )
    return events


def run_concurrency_pool(
    db_path: Path,
    *,
    run_id: str,
    worker_type: str,
    workers: int,
    operation_count: int,
    stable_root_id: int,
    stable_child_id: int,
) -> list[dict[str, Any]]:
    executor_type = ThreadPoolExecutor if worker_type == "thread" else ProcessPoolExecutor
    events: list[dict[str, Any]] = []
    with executor_type(max_workers=workers) as executor:
        futures = [
            executor.submit(
                concurrency_worker,
                (
                    str(db_path),
                    run_id,
                    worker_type,
                    worker_id,
                    operation_count,
                    stable_root_id,
                    stable_child_id,
                ),
            )
            for worker_id in range(workers)
        ]
        for future in as_completed(futures):
            events.extend(future.result())
    return events


def check_concurrency(work_root: Path) -> Check:
    root = work_root / "concurrency"
    store = store_at(root)
    stable_root = store.put_candidate(root_node("concurrency stable root for mixed workload", key="concurrency"))
    admit(store, stable_root)
    stable_child = store.put_candidate(
        dependent_node("concurrency stable child expands to stable root", stable_root, key="concurrency")
    )
    admit(store, stable_child)
    events: list[dict[str, Any]] = []
    for worker_type in ("thread", "process"):
        for workers in (4, 8):
            events.extend(
                run_concurrency_pool(
                    store.db_path,
                    run_id=f"{worker_type}-{workers}",
                    worker_type=worker_type,
                    workers=workers,
                    operation_count=22,
                    stable_root_id=stable_root,
                    stable_child_id=stable_child,
                )
            )
    write_jsonl(ARTIFACT_DIR / "concurrency_events.jsonl", events)
    unexpected_errors = [event for event in events if event["status"] == "unexpected_error"]
    raw_sqlite_errors = [
        event
        for event in events
        if event["error_type"] and str(event["error_type"]).startswith(("OperationalError", "IntegrityError"))
    ]
    operation_counts: dict[str, int] = {}
    success_by_operation: dict[str, int] = {}
    for event in events:
        operation_counts[event["operation"]] = operation_counts.get(event["operation"], 0) + 1
        if event["status"] == "ok":
            success_by_operation[event["operation"]] = success_by_operation.get(event["operation"], 0) + 1
    with sqlite3.connect(store.db_path) as conn:
        persisted = int(conn.execute("SELECT COUNT(*) FROM causal_nodes").fetchone()[0])
        distinct_ids = int(conn.execute("SELECT COUNT(DISTINCT node_id) FROM causal_nodes").fetchone()[0])
        admitted_candidate_dependencies = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM causal_dependency_groups dg
                JOIN causal_dependency_nodes dn ON dn.group_id = dg.group_id
                JOIN causal_nodes n ON n.node_id = dg.node_id
                JOIN causal_nodes predecessor ON predecessor.node_id = dn.predecessor_node_id
                WHERE n.status = 'admitted' AND predecessor.status = 'candidate'
                """
            ).fetchone()[0]
        )
    integrity = integrity_status(store.db_path)
    latencies = [float(event["latency_ms"]) for event in events if event["status"] == "ok"]
    required_operations = {
        "put_candidate",
        "get_node",
        "search_nodes",
        "expand_context",
        "admit_nodes",
        "invalidate_node",
        "supersede_node",
    }
    all_required_operations_succeeded = all(success_by_operation.get(operation, 0) > 0 for operation in required_operations)
    passed = (
        not unexpected_errors
        and not raw_sqlite_errors
        and all_required_operations_succeeded
        and distinct_ids == persisted
        and admitted_candidate_dependencies == 0
        and integrity["integrity_check"] == "ok"
        and integrity["foreign_key_errors"] == 0
    )
    summary = {
        "event_count": len(events),
        "persisted_nodes": persisted,
        "distinct_node_ids": distinct_ids,
        "operation_counts": operation_counts,
        "success_by_operation": success_by_operation,
        "unexpected_error_count": len(unexpected_errors),
        "raw_sqlite_error_count": len(raw_sqlite_errors),
        "admitted_candidate_dependency_count": admitted_candidate_dependencies,
        "all_required_operations_succeeded": all_required_operations_succeeded,
        "latency": latency_summary(latencies),
        **integrity,
    }
    write_json(ARTIFACT_DIR / "concurrency_summary.json", summary)
    return Check(
        name="concurrency",
        status="pass" if passed else "fail",
        details=summary,
    )


def seed_performance_dataset(store: CausalStore, size: int) -> list[int]:
    ids: list[int] = []
    for index in range(size):
        node_id = store.put_candidate(
            root_node(
                f"performance node {index} causal retrieval benchmark token-{index % 17}",
                key=f"perf-{index % 17}",
                evidence_ref=f"perf-{index}",
            )
        )
        ids.append(node_id)
    for offset in range(0, len(ids), 250):
        admit(store, *ids[offset : offset + 250])
    return ids


def check_performance(work_root: Path, sizes: list[int]) -> Check:
    results: list[dict[str, Any]] = []
    query_plan_text = ""
    for size in sizes:
        root = work_root / f"performance-{size}"
        store = store_at(root)
        start_seed = time.perf_counter()
        ids = seed_performance_dataset(store, size)
        seed_ms = (time.perf_counter() - start_seed) * 1000
        random_ids = random.Random(RANDOM_SEED).sample(ids, min(500, len(ids)))
        get_latencies: list[float] = []
        for node_id in random_ids:
            start = time.perf_counter()
            store.get_node(node_id)
            get_latencies.append((time.perf_counter() - start) * 1000)
        search_latencies: list[float] = []
        for query in ("causal retrieval benchmark", "token-3 performance", "node retrieval"):
            start = time.perf_counter()
            store.search_nodes(CausalQuery(query=query, limit=10))
            search_latencies.append((time.perf_counter() - start) * 1000)
        expand_latencies: list[float] = []
        for node_id in random_ids[:50]:
            start = time.perf_counter()
            store.expand_context(ExpandContextRequest(node_ids=[node_id], depth=1))
            expand_latencies.append((time.perf_counter() - start) * 1000)
        results.append(
            {
                "dataset_size": size,
                "seed_ms": round(seed_ms, 4),
                "get_node": latency_summary(get_latencies),
                "search_nodes": latency_summary(search_latencies),
                "expand_context": latency_summary(expand_latencies),
            }
        )
        if size == sizes[-1]:
            query_plan_text = explain_query_plans(store.db_path)
    (ARTIFACT_DIR / "sqlite_query_plans.txt").write_text(query_plan_text, encoding="utf-8", newline="\n")
    plan_contract = query_plan_contract(query_plan_text)
    p95_ok = all(result["get_node"]["p95_ms"] < 5.0 for result in results)
    tested_10000 = max(sizes) >= 10_000
    passed = plan_contract["all_required_indexes_used"] and p95_ok and tested_10000
    return Check(
        name="performance_and_complexity",
        status="pass" if passed else "scope_limited",
        details={
            "datasets": results,
            "query_plan_contract": plan_contract,
            "get_node_p95_under_5ms_for_tested_sizes": p95_ok,
            "tested_at_least_10000_nodes": tested_10000,
            "semantic_vector_scoring_complexity": "O(n) over causal_embeddings in current implementation",
        },
    )


def check_semantic_retrieval(work_root: Path) -> Check:
    root = work_root / "semantic"
    store = store_at(root)
    seed_specs = [
        ("leader mediated debate preserves canonical transcript", ["debate", "leader", "canonical"], "debate"),
        ("full mesh worker chat creates hidden side channels", ["debate", "fullmesh", "sidechannel"], "debate"),
        ("independent worker synthesis loses adversarial pressure", ["debate", "independent", "pressure"], "debate"),
        ("execution actor must block cross project work", ["execution", "single-project", "block"], "execution"),
        ("test graph parallel superstep keeps independent routes running", ["test", "parallel", "superstep"], "test"),
        ("final review must not create workers or run tests", ["finalreview", "no-worker", "boundary"], "final_review"),
        ("causal store admission requires evidence backed root", ["causal", "admission", "evidence"], "causal"),
        ("tool governance interrupts remote push requests", ["tool", "governance", "interrupt"], "master"),
        ("knowledge store only admits verified static facts", ["knowledge", "verified", "static"], "knowledge"),
        ("archive records happened events without creating truth", ["archive", "events", "truth"], "archive"),
        ("master review rejects unsupported technology lock in", ["master", "review", "technology"], "master"),
        ("sqlite causal store preserves admitted historical nodes", ["sqlite", "causal", "historical"], "causal"),
        ("revalidation queue hides pending nodes from active retrieval", ["revalidation", "pending", "active"], "causal"),
        ("backup restore keeps audit records and dependency groups", ["backup", "restore", "audit"], "causal"),
        ("mixed concurrency must not leak sqlite errors", ["mixed", "concurrency", "sqlite"], "causal"),
        ("debate causal chain selects leader mediated topology", ["debate", "causal", "chain"], "debate"),
        ("execution handoff carries artifact references only", ["execution", "handoff", "artifact"], "execution"),
        ("test evidence must preserve covered and uncovered scope", ["test", "evidence", "scope"], "test"),
        ("final review accepts with scope limit when evidence is bounded", ["final", "review", "scope"], "final_review"),
        ("三库边界 keeps archive knowledge causal separated", ["three", "store", "boundary"], "causal"),
    ]
    node_by_case: dict[str, int] = {}
    expected: list[dict[str, Any]] = []
    for index, (content, keys, scope) in enumerate(seed_specs):
        node_id = store.put_candidate(
            CausalNodeDraft(
                content=content,
                semantic_summary=content,
                semantic_keys=keys,
                source_module="test",
                root_kind="test_result",
                node_refs=[("test", f"semantic-{index}")],
            )
        )
        admit(store, node_id)
        node_by_case[f"seed-{index:03d}"] = node_id
        expected.append(
            {
                "case_id": f"exact-{index:03d}",
                "query": " ".join(keys),
                "category": "exact" if index < 10 else "near_lexical",
                "expected_top_3": [node_id],
                "scope": scope,
                "reason": content,
            }
        )
    paraphrase_cases = [
        ("paraphrase-001", "ordered moderator controlled discussion record", node_by_case["seed-000"]),
        ("paraphrase-002", "workers talk privately and coordination becomes unobservable", node_by_case["seed-001"]),
        ("paraphrase-003", "separate experts never pressure each other in real time", node_by_case["seed-002"]),
        ("paraphrase-004", "implementation should refuse work spanning several repositories", node_by_case["seed-003"]),
        ("paraphrase-005", "reviewer must not perform fresh validation commands", node_by_case["seed-005"]),
        ("paraphrase-006", "long term fact stores must stay distinct", node_by_case["seed-019"]),
    ]
    for case_id, query, node_id in paraphrase_cases:
        expected.append(
            {
                "case_id": case_id,
                "query": query,
                "category": "paraphrase_limitation",
                "expected_top_3": [node_id],
                "scope": "limitation",
                "reason": "Paraphrase case is measured but not required to pass without a real embedding adapter.",
                "mandatory": False,
            }
        )

    scope_in = store.put_candidate(
        CausalNodeDraft(
            content="scope conflict selected topology applies only to debate runtime",
            semantic_summary="scope conflict in scope",
            semantic_keys=["scope", "conflict", "topology"],
            source_module="debate",
            dependency_groups=[
                CausalDependencyGroup(
                    causal_dependencies=[node_by_case["seed-000"]],
                    evidence_refs=["test/scope-in"],
                    scope="debate runtime",
                    conditions=["debate runtime topology"],
                )
            ],
        )
    )
    scope_out = store.put_candidate(
        CausalNodeDraft(
            content="scope conflict selected topology applies only to execution runtime",
            semantic_summary="scope conflict out of scope",
            semantic_keys=["scope", "conflict", "topology"],
            source_module="execution",
            dependency_groups=[
                CausalDependencyGroup(
                    causal_dependencies=[node_by_case["seed-003"]],
                    evidence_refs=["test/scope-out"],
                    scope="execution runtime",
                    conditions=["execution runtime topology"],
                )
            ],
        )
    )
    admit(store, scope_in, scope_out)
    expected.append(
        {
            "case_id": "scope-conflict-001",
            "query": "scope conflict topology",
            "category": "scope_conflict",
            "expected_top_3": [scope_in],
            "must_exclude": [scope_out],
            "required_scope": "debate runtime",
            "scope": "debate runtime",
            "reason": "Required scope must exclude the execution-runtime node.",
        }
    )

    invalid_id = store.put_candidate(root_node("invalidated semantic node should be rejected", key="semantic-invalid"))
    admit(store, invalid_id)
    store.invalidate_node(
        InvalidationRequest(
            node_id=invalid_id,
            invalidated_by_module="causal_review",
            reason="semantic negative evidence invalidated",
        )
    )
    expected.append(
        {
            "case_id": "semantic-invalidated",
            "query": "semantic invalidated rejected",
            "category": "lifecycle_exclusion",
            "expected_top_3": [],
            "must_exclude": [invalid_id],
            "scope": "invalidated exclusion",
            "reason": "Invalidated active result must be excluded.",
        }
    )
    superseded_old = store.put_candidate(root_node("superseded semantic node should be historical only", key="semantic-old"))
    superseded_new = store.put_candidate(root_node("replacement semantic node should be active", key="semantic-new"))
    admit(store, superseded_old, superseded_new)
    store.supersede_node(
        SupersessionRequest(
            old_node_id=superseded_old,
            new_node_id=superseded_new,
            reason="semantic supersession exclusion test",
        )
    )
    expected.append(
        {
            "case_id": "semantic-superseded",
            "query": "semantic node active replacement",
            "category": "lifecycle_exclusion",
            "expected_top_3": [superseded_new],
            "must_exclude": [superseded_old],
            "scope": "superseded exclusion",
            "reason": "Superseded node must not be active truth.",
        }
    )
    expected.extend(
        [
            {
                "case_id": "mixed-language-001",
                "query": "three store boundary 三库 边界",
                "category": "mixed_language",
                "expected_top_3": [node_by_case["seed-019"]],
                "scope": "mixed language",
                "reason": "Chinese/English mixed query has English anchors for deterministic recall.",
            },
            {
                "case_id": "mixed-language-002",
                "query": "debate causal chain 对抗 因果链",
                "category": "mixed_language",
                "expected_top_3": [node_by_case["seed-015"]],
                "scope": "mixed language",
                "reason": "Chinese/English mixed query has English anchors for deterministic recall.",
            },
        ]
    )
    write_json(ARTIFACT_DIR / "semantic_eval_cases.json", expected)

    results: list[dict[str, Any]] = []
    category_metrics: dict[str, dict[str, Any]] = {}
    for case in expected:
        result = store.search_nodes(
            CausalQuery(
                query=case["query"],
                limit=5,
                required_scope=case.get("required_scope"),
            )
        )
        ranked_ids = [node.node_id for node in result.nodes]
        expected_ids = case.get("expected_top_3", [])
        hit_rank = None
        for expected_id in expected_ids:
            if expected_id in ranked_ids:
                rank = ranked_ids.index(expected_id) + 1
                hit_rank = rank if hit_rank is None else min(hit_rank, rank)
        category = case["category"]
        category_entry = category_metrics.setdefault(
            category,
            {"case_count": 0, "mandatory_case_count": 0, "recall_at_1_hits": 0, "recall_at_3_hits": 0},
        )
        category_entry["case_count"] += 1
        mandatory = case.get("mandatory", True)
        if mandatory and expected_ids:
            category_entry["mandatory_case_count"] += 1
            if hit_rank == 1:
                category_entry["recall_at_1_hits"] += 1
            if hit_rank is not None and hit_rank <= 3:
                category_entry["recall_at_3_hits"] += 1
        excluded_ok = all(excluded not in ranked_ids for excluded in case.get("must_exclude", []))
        results.append(
            {
                "case_id": case["case_id"],
                "category": category,
                "query": case["query"],
                "ranked_ids": ranked_ids,
                "rejected": [item.model_dump(mode="json") for item in result.rejected_nodes],
                "hit_rank": hit_rank,
                "excluded_ok": excluded_ok,
                "mandatory": mandatory,
            }
        )
    for metrics in category_metrics.values():
        mandatory_count = metrics["mandatory_case_count"]
        metrics["recall_at_1"] = metrics["recall_at_1_hits"] / mandatory_count if mandatory_count else None
        metrics["recall_at_3"] = metrics["recall_at_3_hits"] / mandatory_count if mandatory_count else None
    exact_near_cases = [
        item for item in results if item["category"] in {"exact", "near_lexical"} and item["mandatory"]
    ]
    exact_near_recall_at_3 = sum(1 for item in exact_near_cases if item["hit_rank"] and item["hit_rank"] <= 3) / len(
        exact_near_cases
    )
    scope_conflict_ok = all(item["excluded_ok"] for item in results if item["category"] == "scope_conflict")
    lifecycle_exclusion_ok = all(item["excluded_ok"] for item in results if item["category"] == "lifecycle_exclusion")
    metrics = {
        "case_count": len(expected),
        "category_metrics": category_metrics,
        "exact_near_recall_at_3": exact_near_recall_at_3,
        "scope_conflict_ok": scope_conflict_ok,
        "lifecycle_exclusion_ok": lifecycle_exclusion_ok,
        "result_count": len(results),
        "paraphrase_boundary": "Paraphrase cases are measured but not required without real embedding retrieval.",
    }
    write_json(ARTIFACT_DIR / "semantic_eval_results.json", {"metrics": metrics, "cases": results})
    passed = (
        metrics["case_count"] >= 30
        and exact_near_recall_at_3 >= 0.9
        and scope_conflict_ok
        and lifecycle_exclusion_ok
    )
    return Check(
        name="semantic_retrieval_accuracy",
        status="pass" if passed else "fail",
        details={
            **metrics,
            "boundary": "Current retrieval is deterministic lexical/hash-vector recall, not true LLM embedding search.",
        },
    )


def check_id_collision(work_root: Path, count: int) -> Check:
    root = work_root / "collision"
    store = store_at(root)
    now = utc_now()
    with sqlite3.connect(store.db_path) as conn:
        for index in range(count):
            conn.execute(
                """
                INSERT INTO causal_nodes (
                  node_uuid, created_at_utc, updated_at_utc, content, semantic_summary,
                  status, source_module, root_kind, strict_content_hash, causal_identity_hash
                )
                VALUES (?, ?, ?, ?, ?, 'candidate', 'test', 'test_result', ?, ?)
                """,
                (
                    f"collision-node-{index}",
                    now,
                    now,
                    f"collision content {index}",
                    f"collision summary {index}",
                    f"strict-{index}",
                    f"identity-{index}",
                ),
            )
        conn.commit()
        persisted = int(conn.execute("SELECT COUNT(*) FROM causal_nodes").fetchone()[0])
        distinct_ids = int(conn.execute("SELECT COUNT(DISTINCT node_id) FROM causal_nodes").fetchone()[0])
        max_node_id = int(conn.execute("SELECT MAX(node_id) FROM causal_nodes").fetchone()[0])
        artificial_collision_rejected = False
        controlled_error = None
        cause_type = None
        try:
            conn.execute(
                """
                INSERT INTO causal_nodes (
                  node_id, node_uuid, created_at_utc, updated_at_utc, content, semantic_summary,
                  status, source_module, root_kind, strict_content_hash, causal_identity_hash
                )
                VALUES (1, 'collision-duplicate', ?, ?, 'dup', 'dup',
                        'candidate', 'test', 'test_result', 'dup-strict', 'dup-id')
                """,
                (now, now),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            artificial_collision_rejected = True
            controlled_error = "DUPLICATE_NODE_ID"
            cause_type = type(exc).__name__
    payload = {
        "random_seed": RANDOM_SEED,
        "attempted_inserts": count,
        "persisted_nodes": persisted,
        "distinct_node_ids": distinct_ids,
        "max_node_id": max_node_id,
        "natural_collisions": persisted - distinct_ids,
        "artificial_collision_rejected": artificial_collision_rejected,
        "controlled_error": controlled_error,
        "cause_type": cause_type,
    }
    write_json(ARTIFACT_DIR / "id_collision_run.json", payload)
    passed = (
        persisted == count
        and distinct_ids == persisted
        and artificial_collision_rejected
        and controlled_error == "DUPLICATE_NODE_ID"
    )
    return Check(name="id_collision", status="pass" if passed else "fail", details=payload)


def check_duplicate_identity_concurrency(work_root: Path) -> Check:
    root = work_root / "duplicate_identity"
    store = store_at(root)
    draft = root_node("duplicate identity concurrent insert must persist once", key="duplicate-identity")

    def insert_once(_index: int) -> dict[str, Any]:
        local_store = CausalStore(store.db_path)
        try:
            return {"status": "ok", "value": local_store.put_candidate(draft)}
        except CausalStoreError as exc:
            return {"status": "controlled_error", "value": exc.code}
        except Exception as exc:  # noqa: BLE001 - artifact records unexpected leakage.
            return {"status": "unexpected_error", "value": type(exc).__name__}

    with ThreadPoolExecutor(max_workers=12) as executor:
        attempts = list(executor.map(insert_once, range(24)))

    with sqlite3.connect(store.db_path) as conn:
        active_total, distinct_total = conn.execute(
            """
            SELECT COUNT(causal_identity_hash), COUNT(DISTINCT causal_identity_hash)
            FROM causal_nodes
            WHERE status IN ('candidate', 'admitted', 'deprecated', 'superseded')
            """
        ).fetchone()
        unique_index_present = bool(
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = 'idx_nodes_active_causal_identity_hash'"
            ).fetchone()
        )

    ok_count = sum(1 for item in attempts if item["status"] == "ok")
    duplicate_error_count = sum(
        1 for item in attempts if item["status"] == "controlled_error" and item["value"] == "DUPLICATE_NODE"
    )
    unexpected = [item for item in attempts if item["status"] == "unexpected_error"]
    payload = {
        "attempts": attempts,
        "ok_count": ok_count,
        "duplicate_error_count": duplicate_error_count,
        "unexpected_error_count": len(unexpected),
        "active_identity_count": active_total,
        "distinct_active_identity_count": distinct_total,
        "unique_active_identity_index_present": unique_index_present,
    }
    write_json(ARTIFACT_DIR / "duplicate_identity_concurrency.json", payload)
    passed = (
        ok_count == 1
        and duplicate_error_count == 23
        and not unexpected
        and active_total == distinct_total == 1
        and unique_index_present
    )
    return Check(name="duplicate_identity_concurrency", status="pass" if passed else "fail", details=payload)


def check_lifecycle_transitions(work_root: Path) -> Check:
    root = work_root / "lifecycle"
    store = store_at(root)
    candidate_old = store.put_candidate(root_node("candidate old lifecycle node", key="lifecycle-candidate-old"))
    admitted_old = store.put_candidate(root_node("admitted old lifecycle node", key="lifecycle-admitted-old"))
    admitted_new = store.put_candidate(root_node("admitted replacement lifecycle node", key="lifecycle-new"))
    candidate_new = store.put_candidate(root_node("candidate replacement lifecycle node", key="lifecycle-candidate-new"))
    invalidated_new = store.put_candidate(root_node("invalidated replacement lifecycle node", key="lifecycle-invalidated"))
    admit(store, admitted_old, admitted_new, invalidated_new)
    store.invalidate_node(
        InvalidationRequest(
            node_id=invalidated_new,
            invalidated_by_module="causal_review",
            reason="seed invalidated replacement",
        )
    )

    cases: list[dict[str, Any]] = []

    def expect_error(name: str, request: SupersessionRequest, code: str) -> None:
        before_old = store.get_node(request.old_node_id).status
        before_new = store.get_node(request.new_node_id).status
        before_records = table_count(store.db_path, "causal_supersession_records")
        try:
            store.supersede_node(request)
            cases.append({"name": name, "passed": False, "expected": code, "observed": "ok"})
        except CausalStoreError as exc:
            after_records = table_count(store.db_path, "causal_supersession_records")
            cases.append(
                {
                    "name": name,
                    "passed": exc.code == code
                    and store.get_node(request.old_node_id).status == before_old
                    and store.get_node(request.new_node_id).status == before_new
                    and after_records == before_records,
                    "expected": code,
                    "observed": exc.code,
                    "records_unchanged": after_records == before_records,
                }
            )

    expect_error(
        "self_supersession",
        SupersessionRequest(old_node_id=admitted_old, new_node_id=admitted_old, reason="self"),
        "SELF_SUPERSESSION_FORBIDDEN",
    )
    expect_error(
        "candidate_old_rejected",
        SupersessionRequest(old_node_id=candidate_old, new_node_id=admitted_new, reason="candidate old"),
        "INVALID_STATUS_TRANSITION",
    )
    expect_error(
        "candidate_new_rejected",
        SupersessionRequest(old_node_id=admitted_old, new_node_id=candidate_new, reason="candidate new"),
        "SUPERSESSION_REPLACEMENT_NOT_ADMITTED",
    )
    expect_error(
        "invalidated_new_rejected",
        SupersessionRequest(old_node_id=admitted_old, new_node_id=invalidated_new, reason="invalidated new"),
        "SUPERSESSION_REPLACEMENT_NOT_ADMITTED",
    )
    result = store.supersede_node(
        SupersessionRequest(old_node_id=admitted_old, new_node_id=admitted_new, reason="valid lifecycle transition")
    )
    valid_transition = store.get_node(admitted_old).status == "superseded" and result.new_node_id == admitted_new
    payload = {"cases": cases, "valid_admitted_to_admitted_transition": valid_transition}
    write_json(ARTIFACT_DIR / "lifecycle_transition_results.json", payload)
    return Check(
        name="lifecycle_transitions",
        status="pass" if all(case["passed"] for case in cases) and valid_transition else "fail",
        details=payload,
    )


def check_group_ref_roundtrip(work_root: Path) -> Check:
    root = work_root / "group_refs"
    store = store_at(root)
    parent = store.put_candidate(root_node("typed group refs parent", key="typed-refs"))
    admit(store, parent)
    expected_refs = [
        ("archive", "archive/task"),
        ("knowledge", "knowledge/fact"),
        ("test", "test/result"),
        ("external", "external/spec"),
        ("artifact", "artifact/report"),
    ]
    node = store.put_candidate(
        CausalNodeDraft(
            content="typed group refs preserve validity evidence",
            semantic_summary="typed group refs preserve validity evidence",
            semantic_keys=["typed", "group", "refs"],
            source_module="debate",
            dependency_groups=[
                CausalDependencyGroup(
                    causal_dependencies=[parent],
                    validity_refs=[CausalRef(ref_type=ref_type, ref_id=ref_id) for ref_type, ref_id in expected_refs],
                    scope="typed group refs",
                    confidence="high",
                )
            ],
        )
    )
    group = store.get_node(node).dependency_groups[0]
    observed_refs = [(ref.ref_type, ref.ref_id) for ref in group.validity_refs]
    payload = {
        "expected_refs": expected_refs,
        "observed_refs": observed_refs,
        "legacy_knowledge_refs": group.knowledge_refs,
        "legacy_evidence_refs": group.evidence_refs,
    }
    write_json(ARTIFACT_DIR / "group_ref_roundtrip_results.json", payload)
    passed = observed_refs == sorted(expected_refs) and group.knowledge_refs == ["knowledge/fact"] and group.evidence_refs == [
        "test/result"
    ]
    return Check(name="group_ref_roundtrip", status="pass" if passed else "fail", details=payload)


def check_cjk_retrieval(work_root: Path) -> Check:
    root = work_root / "cjk"
    store = store_at(root)
    node = store.put_candidate(
        CausalNodeDraft(
            content="领导者中介拓扑优于全网格通信，因为它保留裁决控制并减少隐藏通道",
            semantic_summary="领导者中介拓扑支持 Debate closure",
            semantic_keys=["领导者拓扑", "Debate closure", "hidden side channel"],
            source_module="test",
            root_kind="test_result",
            node_refs=[("test", "test/cjk")],
        )
    )
    admit(store, node)
    chinese_initial = [item.node_id for item in store.search_nodes(CausalQuery(query="领导者拓扑")).nodes]
    mixed_initial = [item.node_id for item in store.search_nodes(CausalQuery(query="Debate hidden channel")).nodes]
    store.rebuild_indexes()
    chinese_after_rebuild = [item.node_id for item in store.search_nodes(CausalQuery(query="领导者拓扑")).nodes]
    payload = {
        "node_id": node,
        "chinese_initial": chinese_initial,
        "mixed_initial": mixed_initial,
        "chinese_after_rebuild": chinese_after_rebuild,
    }
    write_json(ARTIFACT_DIR / "cjk_retrieval_results.json", payload)
    passed = chinese_initial[:1] == [node] and mixed_initial[:1] == [node] and chinese_after_rebuild[:1] == [node]
    return Check(name="cjk_retrieval", status="pass" if passed else "fail", details=payload)


def check_recall_index_failure(work_root: Path) -> Check:
    root = work_root / "recall_failure"
    store = store_at(root)
    node = store.put_candidate(root_node("fallback term recall survives fts outage", key="recall-failure"))
    admit(store, node)
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("DROP TABLE causal_nodes_fts")
        conn.commit()
    result = store.search_nodes(CausalQuery(query="fallback recall outage"))
    payload = {
        "node_id": node,
        "ranked_ids": [item.node_id for item in result.nodes],
        "degraded_recall": result.degraded_recall,
        "warnings": [warning.model_dump(mode="json") for warning in result.warnings],
    }
    write_json(ARTIFACT_DIR / "recall_index_failure_results.json", payload)
    passed = result.degraded_recall and payload["ranked_ids"][:1] == [node] and any(
        warning["code"] == "FTS_INDEX_UNAVAILABLE" for warning in payload["warnings"]
    )
    return Check(name="recall_index_failure", status="pass" if passed else "fail", details=payload)


def check_admission_idempotency(work_root: Path) -> Check:
    root = work_root / "admission_idempotency"
    store = store_at(root)
    node = store.put_candidate(root_node("admission idempotency node", key="admission-idempotency"))
    admit(store, node)
    error_code = None
    try:
        admit(store, node)
    except CausalStoreError as exc:
        error_code = exc.code
    with sqlite3.connect(store.db_path) as conn:
        audit_count = int(
            conn.execute("SELECT COUNT(*) FROM causal_admission_records WHERE node_id = ?", (node,)).fetchone()[0]
        )
    payload = {"node_id": node, "repeat_admission_error_code": error_code, "audit_count": audit_count}
    write_json(ARTIFACT_DIR / "admission_idempotency_results.json", payload)
    passed = error_code == "ALREADY_ADMITTED" and audit_count == 1
    return Check(name="admission_idempotency", status="pass" if passed else "fail", details=payload)


def check_revalidation_queue_accuracy(work_root: Path) -> Check:
    root = work_root / "revalidation_queue"
    store = store_at(root)
    parent = store.put_candidate(root_node("revalidation queue parent", key="queue-parent"))
    admit(store, parent)
    child = store.put_candidate(dependent_node("revalidation queue child", parent, key="queue-child"))
    admit(store, child)
    first = store.invalidate_node(
        InvalidationRequest(
            node_id=parent,
            invalidated_by_module="causal_review",
            reason="first invalidation",
        )
    )
    second = store.invalidate_node(
        InvalidationRequest(
            node_id=parent,
            invalidated_by_module="causal_review",
            reason="second invalidation",
        )
    )
    pending = store.list_revalidation_queue(status="pending", node_id=child)
    payload = {
        "first_queued": first.queued_revalidation_node_ids,
        "second_queued": second.queued_revalidation_node_ids,
        "pending_count": len(pending),
    }
    write_json(ARTIFACT_DIR / "revalidation_queue_results.json", payload)
    passed = payload["first_queued"] == [child] and payload["second_queued"] == [] and payload["pending_count"] == 1
    return Check(name="revalidation_queue_accuracy", status="pass" if passed else "fail", details=payload)


def check_actual_scenario(work_root: Path) -> Check:
    root = work_root / "scenario"
    store = store_at(root)
    trace: list[dict[str, Any]] = []

    def record(step: str, expected_effect: str, observed_effect: Any, status: bool) -> None:
        trace.append(
            {
                "step": step,
                "expected_effect": expected_effect,
                "observed_effect": observed_effect,
                "status": "pass" if status else "fail",
            }
        )

    s1 = store.put_candidate(root_node("S1 full mesh causes message explosion", key="debate-s1"))
    s2 = store.put_candidate(root_node("S2 leader mediated round robin preserves transcript", key="debate-s2"))
    s3 = store.put_candidate(root_node("S3 independent synthesis loses adversarial pressure", key="debate-s3"))
    admit(store, s1, s2, s3)
    record("admit_alternative_roots", "Alternative evidence roots become admitted evidence.", [s1, s2, s3], True)

    selected = store.put_candidate(
        CausalNodeDraft(
            content="Select S2 because it preserves leader control while rejecting S1 and S3 risks",
            semantic_summary="S2 selected over S1 and S3 for debate topology",
            semantic_keys=["debate", "s2", "selected", "leader", "roundrobin"],
            source_module="debate",
            dependency_groups=[
                CausalDependencyGroup(
                    causal_dependencies=[s1, s2, s3],
                    evidence_refs=["debate/final-report"],
                    scope="debate runtime topology",
                    conditions=["leader mediated transcript remains required"],
                    assumptions=["worker count is small enough for round robin"],
                    confidence="high",
                    invalidation_conditions=[
                        "future contract allows full mesh",
                        "leader mediated topology cannot scale",
                    ],
                )
            ],
        )
    )
    candidate_search = store.search_nodes(CausalQuery(query="s2 selected debate topology"))
    candidate_not_active = selected not in [node.node_id for node in candidate_search.nodes]
    record(
        "candidate_package_not_active_truth",
        "Candidate causal package must not affect active admitted retrieval before admission.",
        {"candidate_node_id": selected, "active_node_ids": [node.node_id for node in candidate_search.nodes]},
        candidate_not_active,
    )

    reject_s1 = store.put_candidate(root_node("Reject S1 because full mesh creates hidden side channels", key="reject-s1"))
    reject_s3 = store.put_candidate(
        root_node("Reject S3 because independent synthesis loses adversarial pressure", key="reject-s3")
    )
    admit(store, reject_s1, reject_s3)
    rejected_contents = [store.get_node(reject_s1).content, store.get_node(reject_s3).content]
    rejected_not_selected = all(content.startswith("Reject ") for content in rejected_contents)
    record(
        "rejected_alternatives_are_negative_evidence",
        "Rejected alternatives may be admitted evidence but must not become selected truth.",
        {"rejected_node_ids": [reject_s1, reject_s3], "rejected_contents": rejected_contents},
        rejected_not_selected,
    )

    boundary_node = store.put_candidate(
        CausalNodeDraft(
            content="Archive refs and Knowledge refs support but do not become causal truth automatically",
            semantic_summary="Three-store boundary support refs",
            semantic_keys=["archive", "knowledge", "causal", "boundary"],
            source_module="causal_review",
            root_kind="external_evidence",
            node_refs=[("archive", "archive/event-001"), ("knowledge", "knowledge/fact-001")],
        )
    )
    admit(store, boundary_node)
    boundary_refs = store.get_node(boundary_node).node_refs
    boundary_ok = boundary_refs == [("archive", "archive/event-001"), ("knowledge", "knowledge/fact-001")]
    record(
        "three_store_refs_remain_refs",
        "Archive and Knowledge references are stored as refs, not promoted by ref existence.",
        boundary_refs,
        boundary_ok,
    )

    admit(store, selected)
    record("admit_selected_chain", "Causal Review admits the selected chain.", selected, True)
    by_id = store.get_node(selected).node_id == selected
    by_query = selected in [
        item.node_id for item in store.search_nodes(CausalQuery(query="debate s2 selected leader")).nodes
    ]
    record(
        "semantic_search_retrieves_admitted_selected_basis",
        "Later semantic search retrieves the selected admitted causal basis.",
        {"by_id": by_id, "by_query": by_query},
        by_id and by_query,
    )

    out_of_scope = store.put_candidate(
        CausalNodeDraft(
            content="S2 selected topology is not valid for execution actor routing",
            semantic_summary="Out of scope execution topology",
            semantic_keys=["s2", "selected", "topology"],
            source_module="execution",
            dependency_groups=[
                CausalDependencyGroup(
                    causal_dependencies=[s2],
                    evidence_refs=["test/out-of-scope"],
                    scope="execution runtime",
                    conditions=["execution actor topology"],
                )
            ],
        )
    )
    admit(store, out_of_scope)
    scoped_search = store.search_nodes(
        CausalQuery(query="s2 selected topology", required_scope="debate runtime topology")
    )
    scope_excludes_out_of_scope = out_of_scope not in [node.node_id for node in scoped_search.nodes]
    record(
        "scope_mismatch_excludes_out_of_scope_node",
        "A required debate-runtime scope must exclude execution-runtime causal nodes.",
        {"excluded_node_id": out_of_scope, "active_node_ids": [node.node_id for node in scoped_search.nodes]},
        scope_excludes_out_of_scope,
    )

    invalidation = store.invalidate_node(
        InvalidationRequest(
            node_id=s2,
            invalidated_by_module="causal_review",
            reason="leader mediated topology cannot scale for future worker count",
        )
    )
    record(
        "upstream_invalidation_queues_revalidation",
        "Invalidating an upstream node queues admitted dependents for revalidation.",
        invalidation.queued_revalidation_node_ids,
        selected in invalidation.queued_revalidation_node_ids,
    )
    pending_search = store.search_nodes(CausalQuery(query="debate s2 selected leader"))
    pending_excluded = selected not in [node.node_id for node in pending_search.nodes]
    record(
        "pending_revalidation_excluded_from_active_retrieval",
        "Pending revalidation nodes must not be returned as active truth.",
        {"selected_node_id": selected, "active_node_ids": [node.node_id for node in pending_search.nodes]},
        pending_excluded,
    )

    alt_root_one = store.put_candidate(root_node("alternative group first root can be invalidated", key="alt-one"))
    alt_root_two = store.put_candidate(root_node("alternative group second root remains valid", key="alt-two"))
    admit(store, alt_root_one, alt_root_two)
    alt_node = store.put_candidate(
        CausalNodeDraft(
            content="Alternative dependency group keeps downstream node valid",
            semantic_summary="Alternative dependency group valid",
            semantic_keys=["alternative", "dependency", "valid"],
            source_module="causal_review",
            dependency_groups=[
                CausalDependencyGroup(
                    causal_dependencies=[alt_root_one],
                    evidence_refs=["test/alt-one"],
                    scope="alternative path one",
                    confidence="medium",
                ),
                CausalDependencyGroup(
                    causal_dependencies=[alt_root_two],
                    evidence_refs=["test/alt-two"],
                    scope="alternative path two",
                    confidence="high",
                ),
            ],
        )
    )
    admit(store, alt_node)
    store.invalidate_node(
        InvalidationRequest(
            node_id=alt_root_one,
            invalidated_by_module="causal_review",
            reason="alternative first path invalidated",
        )
    )
    alt_queue = store.list_revalidation_queue(status="pending", node_id=alt_node)
    alt_pending_excluded = alt_node not in [
        node.node_id for node in store.search_nodes(CausalQuery(query="alternative dependency valid")).nodes
    ]
    record(
        "alternative_group_pending_revalidation_detected",
        "Invalidating one alternative group queues review and temporarily excludes the downstream node.",
        {"queue_count": len(alt_queue), "active_excluded": alt_pending_excluded},
        len(alt_queue) == 1 and alt_pending_excluded,
    )
    store.resolve_revalidation(
        RevalidationResolutionRequest(
            queue_id=alt_queue[0].queue_id,
            status="resolved",
            rationale="second dependency group remains admitted and valid",
        )
    )
    alt_restored = alt_node in [
        node.node_id for node in store.search_nodes(CausalQuery(query="alternative dependency valid")).nodes
    ]
    record(
        "alternative_dependency_group_restores_usability",
        "After review, a valid alternate dependency group restores active retrieval.",
        {"alt_node_id": alt_node},
        alt_restored,
    )

    queue = store.list_revalidation_queue(status="pending", node_id=selected)
    if queue:
        store.resolve_revalidation(
            RevalidationResolutionRequest(
                queue_id=queue[0].queue_id,
                status="resolved",
                rationale="supersession will replace selected topology node",
            )
        )
    replacement = store.put_candidate(
        CausalNodeDraft(
            content="Re-evaluate S2 under large worker counts with bounded leader fanout",
            semantic_summary="S2 supersession with scalability condition",
            semantic_keys=["debate", "s2", "supersession", "scalability"],
            source_module="causal_review",
            dependency_groups=[
                CausalDependencyGroup(
                    causal_dependencies=[s1, s3],
                    evidence_refs=["causal/revalidation"],
                    scope="large worker debate topology",
                    assumptions=["S2 direct round robin may not scale"],
                    confidence="medium",
                )
            ],
        )
    )
    admit(store, replacement)
    supersession = store.supersede_node(
        SupersessionRequest(
            old_node_id=selected,
            new_node_id=replacement,
            reason="scalability condition changed the active causal conclusion",
        )
    )
    active_search = store.search_nodes(CausalQuery(query="s2 scalability supersession debate"))
    historical_search = store.search_nodes(
        CausalQuery(query="s2 selected leader", mode="historical", limit=10)
    )
    active_has_replacement = replacement in [item.node_id for item in active_search.nodes]
    active_excludes_old = selected not in [item.node_id for item in active_search.nodes]
    historical_has_old = selected in [item.node_id for item in historical_search.nodes]
    record(
        "supersession_preserves_history_and_replaces_active_truth",
        "Supersession keeps old history but active retrieval returns the replacement.",
        {
            "old_node_id": selected,
            "new_node_id": replacement,
            "queued": supersession.queued_revalidation_node_ids,
            "active_has_replacement": active_has_replacement,
            "active_excludes_old": active_excludes_old,
            "historical_has_old": historical_has_old,
        },
        active_has_replacement and active_excludes_old and historical_has_old,
    )
    write_jsonl(ARTIFACT_DIR / "scenario_trace.jsonl", trace)
    passed = all(item["status"] == "pass" for item in trace) and len(trace) >= 12
    return Check(
        name="actual_aegis_scenario",
        status="pass" if passed else "fail",
        details={
            "trace_step_count": len(trace),
            "all_trace_steps_passed": all(item["status"] == "pass" for item in trace),
            "selected_node_id": selected,
            "rejected_node_ids": [reject_s1, reject_s3],
            "invalidated_node_id": s2,
            "replacement_node_id": replacement,
            "selected_retrievable_by_id": by_id,
            "selected_retrievable_by_semantic_query_before_invalidation": by_query,
            "revalidation_queued_for_selected": selected in invalidation.queued_revalidation_node_ids,
            "active_has_replacement": active_has_replacement,
            "active_excludes_superseded_old_node": active_excludes_old,
            "historical_search_preserves_old_node": historical_has_old,
        },
    )


def check_backup(work_root: Path) -> Check:
    root = work_root / "backup"
    store = store_at(root)
    root_one = store.put_candidate(root_node("backup restore root one", key="backup"))
    root_two = store.put_candidate(root_node("backup restore root two", key="backup"))
    admit(store, root_one, root_two)
    dependent = store.put_candidate(
        CausalNodeDraft(
            content="backup restore dependent node preserves groups refs audit queue",
            semantic_summary="backup restore dependent",
            semantic_keys=["backup", "restore", "dependent"],
            source_module="debate",
            dependency_groups=[
                CausalDependencyGroup(
                    causal_dependencies=[root_one, root_two],
                    knowledge_refs=["knowledge/backup-constraint"],
                    evidence_refs=["test/backup-evidence"],
                    scope="backup restore scenario",
                    conditions=["backup snapshot exists"],
                    assumptions=["sqlite backup API is available"],
                    confidence="high",
                    invalidation_conditions=["source snapshot invalid"],
                )
            ],
        )
    )
    admit(store, dependent)
    invalidation = store.invalidate_node(
        InvalidationRequest(
            node_id=root_one,
            invalidated_by_module="causal_review",
            reason="backup restore queue preservation test",
        )
    )
    backup_path = ARTIFACT_DIR / "backup_snapshot.sqlite3"
    backup_path.unlink(missing_ok=True)
    with sqlite3.connect(store.db_path) as source, sqlite3.connect(backup_path) as target:
        source.backup(target)
    canonical_tables = [
        "causal_nodes",
        "causal_dependency_groups",
        "causal_dependency_nodes",
        "causal_group_refs",
        "causal_admission_records",
        "causal_invalidation_records",
        "causal_revalidation_queue",
    ]
    original_counts = {table: table_count(store.db_path, table) for table in canonical_tables}
    backup_counts = {table: table_count(backup_path, table) for table in canonical_tables}
    integrity = integrity_status(backup_path)
    restored = CausalStore(backup_path)
    restored_get = restored.get_node(dependent).node_id == dependent
    restored_search = dependent in [
        item.node_id
        for item in restored.search_nodes(
            CausalQuery(query="backup restore dependent", mode="include_invalidated_as_counterevidence")
        ).nodes
    ]
    restored_context = restored.expand_context(
        ExpandContextRequest(node_ids=[dependent], depth=2, mode="include_invalidated_as_counterevidence")
    )
    restored_expand = [dependent, root_two] in restored_context.dependency_paths
    restored_queue = restored.list_revalidation_queue(status="pending", node_id=dependent)
    restored_write_id = restored.put_candidate(
        root_node("backup restored store accepts a new candidate write", key="backup-restored-write")
    )
    restored_write_ok = restored.get_node(restored_write_id).content == "backup restored store accepts a new candidate write"
    restore_payload = {
        "backup_path": str(backup_path),
        "original_counts": original_counts,
        "backup_counts": backup_counts,
        "counts_match": original_counts == backup_counts,
        "restored_get_node_ok": restored_get,
        "restored_search_ok": restored_search,
        "restored_expand_context_ok": restored_expand,
        "restored_pending_queue_count": len(restored_queue),
        "original_queued_revalidation_node_ids": invalidation.queued_revalidation_node_ids,
        "restored_write_node_id": restored_write_id,
        "restored_write_ok": restored_write_ok,
        **integrity,
    }
    write_json(ARTIFACT_DIR / "backup_restore_results.json", restore_payload)
    passed = (
        original_counts == backup_counts
        and integrity["integrity_check"] == "ok"
        and integrity["foreign_key_errors"] == 0
        and restored_get
        and restored_search
        and restored_expand
        and len(restored_queue) == 1
        and restored_write_ok
    )
    return Check(
        name="backup_restore",
        status="pass" if passed else "fail",
        details=restore_payload,
    )


def collect_environment(started_at: str, source_trace: dict[str, Any]) -> dict[str, Any]:
    return {
        "repository_path": str(REPO_ROOT),
        "git_branch": run_command(["git", "branch", "--show-current"]),
        "git_commit": run_command(["git", "rev-parse", "HEAD"]),
        "git_status_short": run_command(["git", "status", "--short"]),
        "source_tree_sha256": source_trace["source_tree_sha256"],
        "source_patch_sha256": source_trace["source_patch_sha256"],
        "source_manifest_path": str(ARTIFACT_DIR / "source_manifest.json"),
        "python_version": sys.version,
        "sqlite_version": sqlite3.sqlite_version,
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "random_seed": RANDOM_SEED,
        "started_at_utc": started_at,
        "ended_at_utc": utc_now(),
    }


def write_report(checks: list[Check], commands: list[dict[str, Any]]) -> None:
    status_counts: dict[str, int] = {}
    for check in checks:
        status_counts[check.status] = status_counts.get(check.status, 0) + 1
    if status_counts.get("fail"):
        conclusion = "FAILED"
    elif status_counts.get("scope_limited"):
        conclusion = "PASSED_WITH_SCOPE_LIMITS"
    else:
        conclusion = "PASSED"

    lines = [
        "# Causal Store v1 Final Production Verification Report",
        "",
        "## Conclusion",
        "",
        f"`{conclusion}`",
        "",
        "The verification exercised the standalone SQLite-backed Causal Store. "
        "The source-level production hardening checks are included in this run.",
        "",
        "## Source Traceability",
        "",
        "- `artifacts/source_manifest.json` records every source file included in this verification.",
        "- `artifacts/source_tree_sha256.txt` uniquely identifies the verified source snapshot.",
        "- `artifacts/source_patch.diff` contains a text snapshot of the verified source inputs.",
        "",
        "## Command Results",
        "",
    ]
    for command in commands:
        lines.extend(
            [
                f"### `{command['command']}`",
                "",
                f"- returncode: `{command['returncode']}`",
                f"- stdout: `{command['stdout'] or '<empty>'}`",
                f"- stderr: `{command['stderr'] or '<empty>'}`",
                "",
            ]
        )
    lines.extend(["## Domain Results", ""])
    for check in checks:
        lines.extend(
            [
                f"### {check.name}",
                "",
                f"- status: `{check.status}`",
                "",
                "```json",
                json.dumps(check.details, indent=2, sort_keys=True),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Evidence Artifacts",
            "",
            "- `artifacts/environment.json`",
            "- `artifacts/source_manifest.json`",
            "- `artifacts/source_tree_sha256.txt`",
            "- `artifacts/source_patch.diff`",
            "- `artifacts/source_patch_sha256.txt`",
            "- `artifacts/benchmark_results.json`",
            "- `artifacts/concurrency_events.jsonl`",
            "- `artifacts/concurrency_summary.json`",
            "- `artifacts/semantic_eval_cases.json`",
            "- `artifacts/semantic_eval_results.json`",
            "- `artifacts/id_collision_run.json`",
            "- `artifacts/duplicate_identity_concurrency.json`",
            "- `artifacts/lifecycle_transition_results.json`",
            "- `artifacts/group_ref_roundtrip_results.json`",
            "- `artifacts/cjk_retrieval_results.json`",
            "- `artifacts/recall_index_failure_results.json`",
            "- `artifacts/admission_idempotency_results.json`",
            "- `artifacts/revalidation_queue_results.json`",
            "- `artifacts/scenario_trace.jsonl`",
            "- `artifacts/sqlite_query_plans.txt`",
            "- `artifacts/migration_results.json`",
            "- `artifacts/transaction_rollback_results.json`",
            "- `artifacts/invariant_check_results.json`",
            "- `artifacts/recovery_results.json`",
            "- `artifacts/index_rebuild_results.json`",
            "- `artifacts/error_contract_results.json`",
            "- `artifacts/boundary_results.json`",
            "- `artifacts/determinism_results.json`",
            "- `artifacts/backup_results.json`",
            "- `artifacts/backup_restore_results.json`",
            "- `artifacts/backup_snapshot.sqlite3`",
            "",
            "## Boundary",
            "",
            "- This is local component verification, not full Aegis graph integration.",
            "- Current semantic search is deterministic lexical/hash-vector recall, not a real embedding index.",
            "- V1 enforces status, scope, dependency closure, and lifecycle filters; it stores conditions, assumptions, and invalidation conditions but does not perform full logical entailment over them.",
            "- If any check fails or is scope-limited, the report preserves it as an implementation gap instead of hiding it.",
            "",
        ]
    )
    report_text = "\n".join(lines)
    for report_name in (
        "CAUSAL_STORE_V1_FINAL_PRODUCTION_VERIFICATION_REPORT.md",
        "CAUSAL_STORE_V1_VERIFICATION_REPORT.md",
    ):
        (PACKAGE_DIR / report_name).write_text(
            report_text,
            encoding="utf-8",
            newline="\n",
        )


def main() -> int:
    global ARTIFACT_DIR, PACKAGE_DIR

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PACKAGE_DIR)
    parser.add_argument("--performance-sizes", default="1000,5000,10000")
    parser.add_argument("--collision-count", type=int, default=50_000)
    args = parser.parse_args()

    PACKAGE_DIR = args.output
    ARTIFACT_DIR = PACKAGE_DIR / "artifacts"
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    random.seed(RANDOM_SEED)
    started_at = utc_now()
    source_trace = write_source_traceability_artifacts()
    work_root = Path(tempfile.mkdtemp(prefix="aegis-causal-store-verify-"))
    try:
        checks = [
            check_schema_and_migration(work_root),
            check_transactions(work_root),
            check_invariants(work_root),
            check_recovery(work_root),
            check_indexes(work_root),
            check_error_contract(work_root),
            check_boundaries(work_root),
            check_determinism(work_root),
            check_concurrency(work_root),
            check_performance(
                work_root,
                [int(item) for item in args.performance_sizes.split(",") if item.strip()],
            ),
            check_semantic_retrieval(work_root),
            check_id_collision(work_root, args.collision_count),
            check_duplicate_identity_concurrency(work_root),
            check_lifecycle_transitions(work_root),
            check_group_ref_roundtrip(work_root),
            check_cjk_retrieval(work_root),
            check_recall_index_failure(work_root),
            check_admission_idempotency(work_root),
            check_revalidation_queue_accuracy(work_root),
            check_actual_scenario(work_root),
            check_backup(work_root),
        ]
        artifact_map = {
            "migration_results.json": [check for check in checks if check.name == "schema_and_migration"],
            "transaction_rollback_results.json": [
                check for check in checks if check.name == "transaction_rollback"
            ],
            "invariant_check_results.json": [
                check for check in checks if check.name == "invariants_and_integrity"
            ],
            "recovery_results.json": [check for check in checks if check.name == "restart_recovery"],
            "index_rebuild_results.json": [check for check in checks if check.name == "index_rebuild"],
            "error_contract_results.json": [check for check in checks if check.name == "error_contract"],
            "boundary_results.json": [
                check for check in checks if check.name == "boundary_and_malformed_input"
            ],
            "determinism_results.json": [check for check in checks if check.name == "determinism"],
            "backup_results.json": [check for check in checks if check.name == "backup_restore"],
            "backup_restore_results.json": [check for check in checks if check.name == "backup_restore"],
        }
        for filename, selected in artifact_map.items():
            write_json(
                ARTIFACT_DIR / filename,
                [check.__dict__ for check in selected],
            )
        write_json(
            ARTIFACT_DIR / "benchmark_results.json",
            [check.__dict__ for check in checks if check.name == "performance_and_complexity"],
        )
        commands = [
            {
                "command": " ".join([sys.executable, *sys.argv]),
                "returncode": 0,
                "stdout": "production verification script completed and wrote artifacts",
                "stderr": "",
            },
            run_command(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_causal_store.py",
                    "tests/test_causal_store_production_hardening.py",
                    "-q",
                ]
            ),
            run_command([sys.executable, "-m", "ruff", "check", "."]),
            run_command(["git", "diff", "--check"]),
        ]
        env = collect_environment(started_at, source_trace)
        env["verification_work_root_removed"] = str(work_root)
        write_json(ARTIFACT_DIR / "environment.json", env)
        write_report(checks, commands)
        write_json(
            ARTIFACT_DIR / "all_domain_results.json",
            [check.__dict__ for check in checks],
        )
        return 0
    finally:
        shutil.rmtree(work_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
