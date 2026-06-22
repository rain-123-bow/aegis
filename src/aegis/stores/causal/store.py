from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from aegis.models import utc_now
from aegis.stores.causal.models import (
    AdmissionResult,
    AdmissionTransaction,
    CausalContextPackage,
    CausalDependencyGroup,
    CausalNode,
    CausalNodeDraft,
    CausalQuery,
    CausalRef,
    CausalSearchResult,
    CausalStoreError,
    CausalStoreWarning,
    ExpandContextRequest,
    InvalidationRequest,
    InvalidationResult,
    RebuildIndexResult,
    RejectedNode,
    RevalidationQueueItem,
    RevalidationResolutionRequest,
    RevalidationResolutionResult,
    SupersessionRequest,
    SupersessionResult,
)


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
SCHEMA_VERSION = 1
EMBEDDING_DIMS = 64


class CausalStore:
    """SQLite-backed project-local causal node store."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def put_candidate(self, node: CausalNodeDraft) -> int:
        strict_hash = _strict_content_hash(node.content)
        causal_hash = _causal_identity_hash(node)
        semantic_fingerprint = _semantic_fingerprint(node)
        now = utc_now()
        node_uuid = str(uuid4())

        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                duplicate = conn.execute(
                    "SELECT node_id FROM causal_nodes WHERE causal_identity_hash = ? "
                    "AND status != 'invalidated'",
                    (causal_hash,),
                ).fetchone()
                if duplicate:
                    raise CausalStoreError(
                        "DUPLICATE_NODE",
                        f"causal node duplicates existing node {duplicate['node_id']}",
                    )
                near_duplicate = conn.execute(
                    "SELECT node_id FROM causal_nodes WHERE strict_content_hash = ? "
                    "AND causal_identity_hash != ? AND status != 'invalidated'",
                    (strict_hash, causal_hash),
                ).fetchone()
                if near_duplicate:
                    raise CausalStoreError(
                        "NEAR_DUPLICATE_REVIEW_REQUIRED",
                        f"causal node content overlaps existing node {near_duplicate['node_id']} with a different causal identity",
                    )

                self._validate_dependency_groups(conn, node.dependency_groups)
                cursor = conn.execute(
                    """
                    INSERT INTO causal_nodes (
                      node_uuid, created_at_utc, updated_at_utc, content, semantic_summary,
                      status, source_module, source_run_id, source_artifact_ref, root_kind,
                      strict_content_hash, causal_identity_hash, semantic_fingerprint
                    )
                    VALUES (?, ?, ?, ?, ?, 'candidate', ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        node_uuid,
                        now,
                        now,
                        node.content,
                        node.semantic_summary,
                        node.source_module,
                        node.source_run_id,
                        node.source_artifact_ref,
                        node.root_kind,
                        strict_hash,
                        causal_hash,
                        semantic_fingerprint,
                    ),
                )
                node_id = int(cursor.lastrowid)
                self._write_node_terms(conn, node_id, node.semantic_keys)
                self._write_node_refs(conn, node_id, node.node_refs)
                self._write_dependency_groups(conn, node_id, node.dependency_groups)
                self._upsert_recall_indexes(conn, node_id)
                return node_id
        except sqlite3.Error as exc:
            raise _sqlite_write_error("put_candidate", exc) from exc

    def get_node(self, node_id: int) -> CausalNode:
        with self._connect() as conn:
            return self._load_node(conn, node_id)

    def search_nodes(self, query: CausalQuery) -> CausalSearchResult:
        tokens = _tokenize(query.query)
        if not tokens:
            return CausalSearchResult(query=query.query, mode=query.mode, nodes=[])

        with self._connect() as conn:
            scored, warnings, degraded_recall = self._recall_candidates(conn, tokens)
            ordered_ids = [
                node_id for node_id, _score in sorted(scored.items(), key=lambda item: (-item[1], item[0]))
            ]
            nodes: list[CausalNode] = []
            rejected: list[RejectedNode] = []
            for node_id in ordered_ids:
                node = self._load_node(conn, node_id)
                reason = self._rejection_reason(conn, node, query.mode, query.required_scope)
                if reason:
                    if query.include_rejected:
                        rejected.append(RejectedNode(node_id=node_id, reason=reason))
                    continue
                nodes.append(node)
                if len(nodes) >= query.limit:
                    break
            return CausalSearchResult(
                query=query.query,
                mode=query.mode,
                nodes=nodes,
                rejected_nodes=rejected,
                warnings=warnings,
                degraded_recall=degraded_recall,
            )

    def expand_context(self, request: ExpandContextRequest) -> CausalContextPackage:
        selected: set[int] = set()
        paths: list[list[int]] = []
        rejected: list[RejectedNode] = []

        with self._connect() as conn:
            for node_id in request.node_ids:
                self._expand_node(
                    conn=conn,
                    node_id=node_id,
                    depth=request.depth,
                    mode=request.mode,
                    selected=selected,
                    paths=paths,
                    rejected=rejected,
                    path_prefix=[],
                )

        return CausalContextPackage(
            root_node_ids=request.node_ids,
            mode=request.mode,
            selected_nodes=sorted(selected),
            dependency_paths=paths,
            rejected_nodes=rejected,
        )

    def admit_nodes(self, request: AdmissionTransaction) -> AdmissionResult:
        if not request.node_ids:
            raise CausalStoreError("ADMISSION_REQUIRED", "admission requires at least one node")

        node_ids = list(dict.fromkeys(request.node_ids))
        admitted_at = utc_now()
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                self._validate_admission(conn, node_ids)
                for node_id in node_ids:
                    conn.execute(
                        "UPDATE causal_nodes SET status = 'admitted', updated_at_utc = ? WHERE node_id = ?",
                        (admitted_at, node_id),
                    )
                    conn.execute(
                        """
                        INSERT INTO causal_admission_records (
                          node_id, admitted_at_utc, admitted_by_module,
                          admission_run_id, rationale, evidence_ref
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            node_id,
                            admitted_at,
                            request.admitted_by_module,
                            request.admission_run_id,
                            request.rationale,
                            request.evidence_ref,
                        ),
                    )
                return AdmissionResult(admitted_node_ids=node_ids, admitted_at_utc=admitted_at)
        except sqlite3.Error as exc:
            raise _sqlite_write_error("admit_nodes", exc) from exc

    def invalidate_node(self, request: InvalidationRequest) -> InvalidationResult:
        invalidated_at = utc_now()
        try:
            with self._connect() as conn:
                self._ensure_node_exists(conn, request.node_id)
                conn.execute(
                    "UPDATE causal_nodes SET status = 'invalidated', updated_at_utc = ? WHERE node_id = ?",
                    (invalidated_at, request.node_id),
                )
                conn.execute(
                    """
                    INSERT INTO causal_invalidation_records (
                      node_id, invalidated_at_utc, invalidated_by_module,
                      invalidation_run_id, reason, invalidation_condition
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request.node_id,
                        invalidated_at,
                        request.invalidated_by_module,
                        request.invalidation_run_id,
                        request.reason,
                        request.invalidation_condition,
                    ),
                )
                queued = self._queue_reverse_dependents(
                    conn,
                    request.node_id,
                    "dependency_invalidated",
                    request.reason,
                )
                return InvalidationResult(
                    node_id=request.node_id,
                    invalidated_at_utc=invalidated_at,
                    queued_revalidation_node_ids=queued,
                )
        except sqlite3.Error as exc:
            raise _sqlite_write_error("invalidate_node", exc) from exc

    def supersede_node(self, request: SupersessionRequest) -> SupersessionResult:
        superseded_at = utc_now()
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                self._validate_supersession(conn, request)
                conn.execute(
                    "UPDATE causal_nodes SET status = 'superseded', updated_at_utc = ? WHERE node_id = ?",
                    (superseded_at, request.old_node_id),
                )
                conn.execute(
                    """
                    INSERT INTO causal_supersession_records (
                      old_node_id, new_node_id, superseded_at_utc, reason
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (request.old_node_id, request.new_node_id, superseded_at, request.reason),
                )
                queued = self._queue_reverse_dependents(
                    conn,
                    request.old_node_id,
                    "dependency_superseded",
                    request.reason,
                )
                return SupersessionResult(
                    old_node_id=request.old_node_id,
                    new_node_id=request.new_node_id,
                    superseded_at_utc=superseded_at,
                    queued_revalidation_node_ids=queued,
                )
        except sqlite3.Error as exc:
            raise _sqlite_write_error("supersede_node", exc) from exc

    def list_revalidation_queue(
        self,
        *,
        status: str | None = None,
        node_id: int | None = None,
    ) -> list[RevalidationQueueItem]:
        clauses: list[str] = []
        params: list[object] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if node_id is not None:
            clauses.append("node_id = ?")
            params.append(node_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM causal_revalidation_queue
                {where}
                ORDER BY queued_at_utc, queue_id
                """,
                params,
            ).fetchall()
            return [self._queue_item_from_row(row) for row in rows]

    def resolve_revalidation(
        self,
        request: RevalidationResolutionRequest,
    ) -> RevalidationResolutionResult:
        resolved_at = utc_now()
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT queue_id FROM causal_revalidation_queue WHERE queue_id = ?",
                    (request.queue_id,),
                ).fetchone()
                if not row:
                    raise CausalStoreError(
                        "NODE_NOT_FOUND",
                        f"revalidation queue item {request.queue_id} does not exist",
                    )
                conn.execute(
                    """
                    UPDATE causal_revalidation_queue
                    SET status = ?, resolved_at_utc = ?, resolution_rationale = ?
                    WHERE queue_id = ?
                    """,
                    (request.status, resolved_at, request.rationale, request.queue_id),
                )
                return RevalidationResolutionResult(
                    queue_id=request.queue_id,
                    status=request.status,
                    resolved_at_utc=resolved_at,
                )
        except sqlite3.Error as exc:
            raise _sqlite_write_error("resolve_revalidation", exc) from exc

    def rebuild_indexes(self) -> RebuildIndexResult:
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM causal_nodes_fts")
                conn.execute("DELETE FROM causal_embeddings")
                node_ids = [
                    int(row["node_id"]) for row in conn.execute("SELECT node_id FROM causal_nodes").fetchall()
                ]
                for node_id in node_ids:
                    self._upsert_recall_indexes(conn, node_id)
                return RebuildIndexResult(
                    rebuilt_fts_rows=len(node_ids),
                    rebuilt_embedding_rows=len(node_ids),
                )
        except sqlite3.Error as exc:
            raise _sqlite_write_error("rebuild_indexes", exc) from exc

    def _initialize(self) -> None:
        try:
            with self._connect() as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                self._reject_unsupported_schema_version(conn)
                conn.executescript(SCHEMA_SQL)
                applied = conn.execute(
                    "SELECT version FROM schema_migrations WHERE version = ?",
                    (SCHEMA_VERSION,),
                ).fetchone()
                if not applied:
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at_utc) VALUES (?, ?, ?)",
                        (SCHEMA_VERSION, "causal_store_v1", utc_now()),
                    )
        except sqlite3.Error as exc:
            raise _sqlite_write_error("initialize", exc) from exc

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _reject_unsupported_schema_version(self, conn: sqlite3.Connection) -> None:
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
        if not table_exists:
            return
        row = conn.execute("SELECT MAX(version) AS max_version FROM schema_migrations").fetchone()
        max_version = row["max_version"] if row else None
        if max_version is not None and int(max_version) > SCHEMA_VERSION:
            raise CausalStoreError(
                "UNSUPPORTED_SCHEMA_VERSION",
                f"database schema version {max_version} is newer than supported version {SCHEMA_VERSION}",
            )

    def _validate_dependency_groups(
        self,
        conn: sqlite3.Connection,
        dependency_groups: list[CausalDependencyGroup],
    ) -> None:
        seen_group_ids: set[str] = set()
        duplicate_ids: set[str] = set()
        for group in dependency_groups:
            if group.group_id in seen_group_ids:
                duplicate_ids.add(group.group_id)
            seen_group_ids.add(group.group_id)
        if duplicate_ids:
            raise CausalStoreError(
                "DUPLICATE_DEPENDENCY_GROUP",
                f"duplicate dependency group ids in node draft: {', '.join(sorted(duplicate_ids))}",
            )
        for group in dependency_groups:
            if conn.execute(
                "SELECT 1 FROM causal_dependency_groups WHERE group_id = ?",
                (group.group_id,),
            ).fetchone():
                raise CausalStoreError(
                    "DUPLICATE_DEPENDENCY_GROUP",
                    f"dependency group id {group.group_id} already exists",
                )
            for predecessor in group.causal_dependencies:
                if not conn.execute(
                    "SELECT 1 FROM causal_nodes WHERE node_id = ?",
                    (predecessor,),
                ).fetchone():
                    raise CausalStoreError(
                        "INVALID_DEPENDENCY",
                        f"dependency node {predecessor} does not exist",
                    )

    def _write_node_terms(
        self,
        conn: sqlite3.Connection,
        node_id: int,
        semantic_keys: list[str],
    ) -> None:
        terms = sorted(set(_tokenize(" ".join(semantic_keys))))
        for term in terms:
            conn.execute(
                "INSERT INTO causal_node_terms (node_id, term, weight) VALUES (?, ?, ?)",
                (node_id, term, 1.0),
            )

    def _write_node_refs(
        self,
        conn: sqlite3.Connection,
        node_id: int,
        refs: list[tuple[str, str]],
    ) -> None:
        for ref_type, ref_id in refs:
            conn.execute(
                "INSERT INTO causal_node_refs (node_id, ref_type, ref_id) VALUES (?, ?, ?)",
                (node_id, ref_type, ref_id),
            )

    def _write_dependency_groups(
        self,
        conn: sqlite3.Connection,
        node_id: int,
        groups: list[CausalDependencyGroup],
    ) -> None:
        for group in groups:
            conn.execute(
                """
                INSERT INTO causal_dependency_groups (
                  group_id, node_id, scope, conditions_json, assumptions_json,
                  confidence, invalidation_conditions_json, created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    group.group_id,
                    node_id,
                    group.scope,
                    json.dumps(group.conditions, sort_keys=True),
                    json.dumps(group.assumptions, sort_keys=True),
                    group.confidence,
                    json.dumps(group.invalidation_conditions, sort_keys=True),
                    utc_now(),
                ),
            )
            for predecessor in group.causal_dependencies:
                conn.execute(
                    """
                    INSERT INTO causal_dependency_nodes (group_id, predecessor_node_id)
                    VALUES (?, ?)
                    """,
                    (group.group_id, predecessor),
                )
            for ref in _group_validity_refs(group):
                conn.execute(
                    "INSERT INTO causal_group_refs (group_id, ref_type, ref_id) VALUES (?, ?, ?)",
                    (group.group_id, ref.ref_type, ref.ref_id),
                )

    def _load_node(self, conn: sqlite3.Connection, node_id: int) -> CausalNode:
        row = conn.execute("SELECT * FROM causal_nodes WHERE node_id = ?", (node_id,)).fetchone()
        if not row:
            raise CausalStoreError("NODE_NOT_FOUND", f"node {node_id} does not exist")
        semantic_keys = [
            str(term["term"])
            for term in conn.execute(
                "SELECT term FROM causal_node_terms WHERE node_id = ? ORDER BY term",
                (node_id,),
            ).fetchall()
        ]
        refs = [
            (str(ref["ref_type"]), str(ref["ref_id"]))
            for ref in conn.execute(
                "SELECT ref_type, ref_id FROM causal_node_refs WHERE node_id = ? ORDER BY ref_type, ref_id",
                (node_id,),
            ).fetchall()
        ]
        groups = self._load_groups(conn, node_id)
        return CausalNode(
            node_id=int(row["node_id"]),
            node_uuid=str(row["node_uuid"]),
            created_at_utc=str(row["created_at_utc"]),
            updated_at_utc=str(row["updated_at_utc"]),
            content=str(row["content"]),
            semantic_summary=str(row["semantic_summary"]),
            semantic_keys=semantic_keys,
            status=str(row["status"]),
            source_module=str(row["source_module"]),
            source_run_id=row["source_run_id"],
            source_artifact_ref=row["source_artifact_ref"],
            root_kind=row["root_kind"],
            strict_content_hash=str(row["strict_content_hash"]),
            causal_identity_hash=str(row["causal_identity_hash"]),
            semantic_fingerprint=row["semantic_fingerprint"],
            duplicate_of_node_id=row["duplicate_of_node_id"],
            node_refs=refs,
            dependency_groups=groups,
        )

    def _load_groups(self, conn: sqlite3.Connection, node_id: int) -> list[CausalDependencyGroup]:
        group_rows = conn.execute(
            "SELECT * FROM causal_dependency_groups WHERE node_id = ? ORDER BY group_id",
            (node_id,),
        ).fetchall()
        groups: list[CausalDependencyGroup] = []
        for row in group_rows:
            group_id = str(row["group_id"])
            dependencies = [
                int(dep["predecessor_node_id"])
                for dep in conn.execute(
                    """
                    SELECT predecessor_node_id FROM causal_dependency_nodes
                    WHERE group_id = ? ORDER BY predecessor_node_id
                    """,
                    (group_id,),
                ).fetchall()
            ]
            refs = conn.execute(
                "SELECT ref_type, ref_id FROM causal_group_refs WHERE group_id = ? ORDER BY ref_type, ref_id",
                (group_id,),
            ).fetchall()
            validity_refs = [
                CausalRef(ref_type=str(ref["ref_type"]), ref_id=str(ref["ref_id"]))
                for ref in refs
            ]
            knowledge_refs = [ref.ref_id for ref in validity_refs if ref.ref_type == "knowledge"]
            evidence_refs = [ref.ref_id for ref in validity_refs if ref.ref_type == "test"]
            groups.append(
                CausalDependencyGroup(
                    group_id=group_id,
                    causal_dependencies=dependencies,
                    validity_refs=validity_refs,
                    knowledge_refs=knowledge_refs,
                    evidence_refs=evidence_refs,
                    scope=str(row["scope"]),
                    conditions=json.loads(row["conditions_json"]),
                    assumptions=json.loads(row["assumptions_json"]),
                    confidence=str(row["confidence"]),
                    invalidation_conditions=json.loads(row["invalidation_conditions_json"]),
                )
            )
        return groups

    def _upsert_recall_indexes(self, conn: sqlite3.Connection, node_id: int) -> None:
        node = self._load_node(conn, node_id)
        scope_terms: list[str] = []
        condition_terms: list[str] = []
        invalidation_terms: list[str] = []
        for group in node.dependency_groups:
            scope_terms.append(group.scope)
            condition_terms.extend(group.conditions)
            condition_terms.extend(group.assumptions)
            invalidation_terms.extend(group.invalidation_conditions)
        conn.execute("DELETE FROM causal_nodes_fts WHERE rowid = ?", (node_id,))
        conn.execute(
            """
            INSERT INTO causal_nodes_fts (
              rowid, node_id, content, semantic_summary, semantic_keys,
              scope_terms, condition_terms, invalidation_terms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node_id,
                node_id,
                node.content,
                node.semantic_summary,
                " ".join(node.semantic_keys),
                " ".join(scope_terms),
                " ".join(condition_terms),
                " ".join(invalidation_terms),
            ),
        )
        vector = _embedding_for_text(
            " ".join([node.content, node.semantic_summary, *node.semantic_keys, *scope_terms])
        )
        conn.execute(
            """
            INSERT INTO causal_embeddings (
              node_id, embedding_model_id, embedding, indexed_at_utc, source_content_hash
            )
            VALUES (?, 'aegis-hash-embedding-v1', ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
              embedding = excluded.embedding,
              indexed_at_utc = excluded.indexed_at_utc,
              source_content_hash = excluded.source_content_hash
            """,
            (
                node_id,
                json.dumps(vector).encode("utf-8"),
                utc_now(),
                node.strict_content_hash,
            ),
        )

    def _recall_candidates(
        self,
        conn: sqlite3.Connection,
        tokens: list[str],
    ) -> tuple[dict[int, float], list[CausalStoreWarning], bool]:
        scores: dict[int, float] = defaultdict(float)
        warnings: list[CausalStoreWarning] = []
        degraded_recall = False
        placeholders = ",".join("?" for _ in tokens)
        for row in conn.execute(
            f"SELECT node_id, weight FROM causal_node_terms WHERE term IN ({placeholders})",
            tokens,
        ).fetchall():
            scores[int(row["node_id"])] += 2.0 * float(row["weight"])

        fts_query = " OR ".join(tokens)
        try:
            for row in conn.execute(
                "SELECT node_id FROM causal_nodes_fts WHERE causal_nodes_fts MATCH ?",
                (fts_query,),
            ).fetchall():
                scores[int(row["node_id"])] += 5.0
        except sqlite3.OperationalError:
            degraded_recall = True
            warnings.append(
                CausalStoreWarning(
                    code="FTS_INDEX_UNAVAILABLE",
                    message="FTS recall index was unavailable; search used term and embedding fallback only.",
                )
            )

        query_vector = _embedding_for_tokens(tokens)
        embedding_rows = conn.execute(
            """
            SELECT e.node_id, e.embedding, e.source_content_hash, n.strict_content_hash
            FROM causal_embeddings e
            JOIN causal_nodes n ON n.node_id = e.node_id
            """
        ).fetchall()
        for row in embedding_rows:
            if row["source_content_hash"] != row["strict_content_hash"]:
                continue
            vector = json.loads(bytes(row["embedding"]).decode("utf-8"))
            similarity = _cosine_similarity(query_vector, vector)
            if similarity > 0:
                scores[int(row["node_id"])] += similarity
        for node_id in list(scores):
            node = self._load_node(conn, node_id)
            searchable = " ".join([node.content, node.semantic_summary, *node.semantic_keys])
            searchable_tokens = set(_tokenize(searchable))
            scores[node_id] += 3.0 * len(searchable_tokens.intersection(tokens))
        return scores, warnings, degraded_recall

    def _rejection_reason(
        self,
        conn: sqlite3.Connection,
        node: CausalNode,
        mode: str,
        required_scope: str | None = None,
    ) -> str | None:
        if required_scope and node.dependency_groups:
            scopes = {_normalize_text(group.scope) for group in node.dependency_groups}
            if _normalize_text(required_scope) not in scopes:
                return "scope_mismatch"

        if mode == "admitted_only":
            if node.status != "admitted":
                return node.status
            if self._has_pending_revalidation(conn, node.node_id):
                return "pending_revalidation"
            if not self._has_valid_dependency_group(conn, node):
                return "dependency_not_admitted"
            return None

        if mode == "working_candidates":
            if node.status not in {"candidate", "admitted"}:
                return node.status
            return None

        if mode == "include_invalidated_as_counterevidence":
            if node.status not in {"admitted", "invalidated"}:
                return node.status
            return None

        if mode in {"historical", "human_review"}:
            return None

        return "invalid_retrieval_mode"

    def _has_pending_revalidation(self, conn: sqlite3.Connection, node_id: int) -> bool:
        return bool(
            conn.execute(
                """
                SELECT 1 FROM causal_revalidation_queue
                WHERE node_id = ? AND status IN ('pending', 'in_progress')
                """,
                (node_id,),
            ).fetchone()
        )

    def _has_valid_dependency_group(self, conn: sqlite3.Connection, node: CausalNode) -> bool:
        if not node.dependency_groups:
            return bool(node.root_kind and node.node_refs)
        for group in node.dependency_groups:
            valid = True
            for dependency in group.causal_dependencies:
                row = conn.execute(
                    "SELECT status FROM causal_nodes WHERE node_id = ?",
                    (dependency,),
                ).fetchone()
                if not row or row["status"] != "admitted" or self._has_pending_revalidation(conn, dependency):
                    valid = False
                    break
            if valid:
                return True
        return False

    def _expand_node(
        self,
        *,
        conn: sqlite3.Connection,
        node_id: int,
        depth: int,
        mode: str,
        selected: set[int],
        paths: list[list[int]],
        rejected: list[RejectedNode],
        path_prefix: list[int],
    ) -> None:
        node = self._load_node(conn, node_id)
        reason = self._rejection_reason(conn, node, mode)
        if reason:
            rejected.append(RejectedNode(node_id=node_id, reason=reason))
            return
        selected.add(node_id)
        if depth <= 0:
            return
        for group in node.dependency_groups:
            if not self._group_dependencies_are_usable(conn, group, mode):
                continue
            for predecessor in group.causal_dependencies:
                path = [*path_prefix, node_id, predecessor]
                paths.append(path)
                self._expand_node(
                    conn=conn,
                    node_id=predecessor,
                    depth=depth - 1,
                    mode=mode,
                    selected=selected,
                    paths=paths,
                    rejected=rejected,
                    path_prefix=[*path_prefix, node_id],
                )

    def _group_dependencies_are_usable(
        self,
        conn: sqlite3.Connection,
        group: CausalDependencyGroup,
        mode: str,
    ) -> bool:
        for predecessor in group.causal_dependencies:
            node = self._load_node(conn, predecessor)
            if self._rejection_reason(conn, node, mode):
                return False
        return True

    def _validate_admission(self, conn: sqlite3.Connection, node_ids: list[int]) -> None:
        admitted_set = set(node_ids)
        for node_id in node_ids:
            node = self._load_node(conn, node_id)
            if node.status == "admitted":
                raise CausalStoreError(
                    "ALREADY_ADMITTED",
                    f"node {node_id} is already admitted",
                )
            if node.status != "candidate":
                raise CausalStoreError(
                    "INVALID_STATUS_TRANSITION",
                    f"node {node_id} cannot be admitted from {node.status}",
                )
            if not node.dependency_groups:
                if not (node.root_kind and node.node_refs):
                    raise CausalStoreError(
                        "ROOT_SOURCE_REQUIRED",
                        f"root node {node_id} requires root_kind and trusted source ref",
                    )
                continue

            for group in node.dependency_groups:
                if not _group_validity_refs(group):
                    raise CausalStoreError(
                        "GROUP_REF_REQUIRED",
                        f"group {group.group_id} requires at least one validity-support ref",
                    )
                for dependency in group.causal_dependencies:
                    dependency_node = self._load_node(conn, dependency)
                    if dependency_node.status == "candidate" and dependency not in admitted_set:
                        raise CausalStoreError(
                            "DEPENDENCY_NOT_ADMITTED",
                            f"node {node_id} depends on candidate node {dependency}",
                        )
                    if dependency_node.status == "invalidated":
                        raise CausalStoreError(
                            "INVALIDATED_NODE_USED",
                            f"node {node_id} depends on invalidated node {dependency}",
                        )
                    if dependency_node.status == "deprecated":
                        raise CausalStoreError(
                            "DEPRECATED_DEPENDENCY_FORBIDDEN",
                            f"node {node_id} depends on deprecated node {dependency}",
                        )
                    if dependency_node.status == "superseded":
                        raise CausalStoreError(
                            "SUPERSEDED_NODE_USED",
                            f"node {node_id} depends on superseded node {dependency}",
                        )

        if self._would_create_cycle(conn, admitted_set):
            raise CausalStoreError("CYCLE_DETECTED", "admission would create a dependency cycle")

    def _validate_supersession(self, conn: sqlite3.Connection, request: SupersessionRequest) -> None:
        if request.old_node_id == request.new_node_id:
            raise CausalStoreError(
                "SELF_SUPERSESSION_FORBIDDEN",
                f"node {request.old_node_id} cannot supersede itself",
            )
        old_node = self._load_node(conn, request.old_node_id)
        new_node = self._load_node(conn, request.new_node_id)
        if old_node.status not in {"admitted", "deprecated"}:
            raise CausalStoreError(
                "INVALID_STATUS_TRANSITION",
                f"old node {request.old_node_id} cannot be superseded from {old_node.status}",
            )
        if new_node.status != "admitted":
            raise CausalStoreError(
                "SUPERSESSION_REPLACEMENT_NOT_ADMITTED",
                f"replacement node {request.new_node_id} must be admitted, not {new_node.status}",
            )

    def _would_create_cycle(self, conn: sqlite3.Connection, admitted_set: set[int]) -> bool:
        rows = conn.execute(
            "SELECT node_id FROM causal_nodes WHERE status = 'admitted'"
        ).fetchall()
        considered = {int(row["node_id"]) for row in rows} | admitted_set
        adjacency: dict[int, list[int]] = {node_id: [] for node_id in considered}
        for node_id in considered:
            for group in self._load_groups(conn, node_id):
                for predecessor in group.causal_dependencies:
                    if predecessor in considered:
                        adjacency[node_id].append(predecessor)

        visiting: set[int] = set()
        visited: set[int] = set()

        def dfs(node_id: int) -> bool:
            if node_id in visiting:
                return True
            if node_id in visited:
                return False
            visiting.add(node_id)
            for predecessor in adjacency.get(node_id, []):
                if dfs(predecessor):
                    return True
            visiting.remove(node_id)
            visited.add(node_id)
            return False

        return any(dfs(node_id) for node_id in considered)

    def _queue_reverse_dependents(
        self,
        conn: sqlite3.Connection,
        predecessor_node_id: int,
        trigger_type: str,
        reason: str,
    ) -> list[int]:
        rows = conn.execute(
            """
            SELECT DISTINCT dg.node_id
            FROM causal_dependency_groups dg
            JOIN causal_dependency_nodes dn ON dn.group_id = dg.group_id
            JOIN causal_nodes n ON n.node_id = dg.node_id
            WHERE dn.predecessor_node_id = ? AND n.status = 'admitted'
            ORDER BY dg.node_id
            """,
            (predecessor_node_id,),
        ).fetchall()
        queued: list[int] = []
        for row in rows:
            node_id = int(row["node_id"])
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO causal_revalidation_queue (
                  queue_id, node_id, triggered_by_node_id, trigger_type,
                  queued_at_utc, reason, status
                )
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    f"revalidation-{uuid4().hex[:12]}",
                    node_id,
                    predecessor_node_id,
                    trigger_type,
                    utc_now(),
                    reason,
                ),
            )
            if cursor.rowcount > 0:
                queued.append(node_id)
        return queued

    def _queue_item_from_row(self, row: sqlite3.Row) -> RevalidationQueueItem:
        return RevalidationQueueItem(
            queue_id=str(row["queue_id"]),
            node_id=int(row["node_id"]),
            triggered_by_node_id=row["triggered_by_node_id"],
            trigger_type=str(row["trigger_type"]),
            queued_at_utc=str(row["queued_at_utc"]),
            reason=str(row["reason"]),
            status=str(row["status"]),
            resolved_at_utc=row["resolved_at_utc"],
            resolution_rationale=row["resolution_rationale"],
        )

    def _ensure_node_exists(self, conn: sqlite3.Connection, node_id: int) -> None:
        if not conn.execute("SELECT 1 FROM causal_nodes WHERE node_id = ?", (node_id,)).fetchone():
            raise CausalStoreError("NODE_NOT_FOUND", f"node {node_id} does not exist")


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _tokenize(value: str) -> list[str]:
    tokens = [token.lower() for token in TOKEN_RE.findall(value) if token.strip()]
    for segment in CJK_RE.findall(value):
        tokens.append(segment)
        for size in (2, 3):
            if len(segment) >= size:
                tokens.extend(segment[index : index + size] for index in range(len(segment) - size + 1))
    return tokens


def _group_validity_refs(group: CausalDependencyGroup) -> list[CausalRef]:
    refs: dict[tuple[str, str], CausalRef] = {}
    for ref in group.validity_refs:
        refs[(ref.ref_type, ref.ref_id)] = ref
    for ref_id in group.knowledge_refs:
        refs[("knowledge", ref_id)] = CausalRef(ref_type="knowledge", ref_id=ref_id)
    for ref_id in group.evidence_refs:
        refs[("test", ref_id)] = CausalRef(ref_type="test", ref_id=ref_id)
    return [refs[key] for key in sorted(refs)]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _strict_content_hash(content: str) -> str:
    return _sha256(_normalize_text(content))


def _causal_identity_hash(node: CausalNodeDraft) -> str:
    groups = [
        {
            "scope": _normalize_text(group.scope),
            "conditions": sorted(_normalize_text(item) for item in group.conditions),
            "assumptions": sorted(_normalize_text(item) for item in group.assumptions),
        }
        for group in node.dependency_groups
    ]
    payload = {
        "content": _normalize_text(node.content),
        "groups": groups,
        "root_kind": node.root_kind,
    }
    return _sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _semantic_fingerprint(node: CausalNodeDraft) -> str:
    tokens = sorted(set(_tokenize(" ".join([node.semantic_summary, *node.semantic_keys]))))
    return _sha256(" ".join(tokens)) if tokens else _strict_content_hash(node.content)


def _embedding_for_text(value: str) -> list[float]:
    return _embedding_for_tokens(_tokenize(value))


def _embedding_for_tokens(tokens: Iterable[str]) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMS
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % EMBEDDING_DIMS
        vector[index] += 1.0
    norm = math.sqrt(sum(item * item for item in vector))
    if norm == 0:
        return vector
    return [item / norm for item in vector]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def _sqlite_write_error(operation: str, exc: sqlite3.Error) -> CausalStoreError:
    message = str(exc)
    if "UNIQUE constraint failed: causal_nodes.node_id" in message:
        return CausalStoreError(
            "DUPLICATE_NODE_ID",
            f"{operation} attempted to write a duplicate causal node id: {message}",
        )
    if (
        "UNIQUE constraint failed: causal_nodes.node_uuid" in message
        or "UNIQUE constraint failed: causal_nodes.causal_identity_hash" in message
        or "idx_nodes_active_causal_identity_hash" in message
    ):
        return CausalStoreError(
            "DUPLICATE_NODE",
            f"{operation} attempted to write a duplicate causal node identity: {message}",
        )
    if "database is locked" in message.lower():
        return CausalStoreError(
            "DATABASE_BUSY",
            f"{operation} could not acquire the SQLite persistence lock before timeout: {message}",
        )
    return CausalStoreError(
        "SQLITE_WRITE_FAILED",
        f"{operation} failed at the SQLite persistence boundary: {exc}",
    )


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS causal_nodes (
  node_id INTEGER PRIMARY KEY,
  node_uuid TEXT NOT NULL UNIQUE,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  content TEXT NOT NULL,
  semantic_summary TEXT NOT NULL,
  status TEXT NOT NULL,
  source_module TEXT NOT NULL,
  source_run_id TEXT,
  source_artifact_ref TEXT,
  root_kind TEXT,
  strict_content_hash TEXT NOT NULL,
  causal_identity_hash TEXT NOT NULL,
  semantic_fingerprint TEXT,
  duplicate_of_node_id INTEGER,
  CHECK (status IN ('candidate', 'admitted', 'invalidated', 'deprecated', 'superseded')),
  CHECK (source_module IN ('master', 'debate', 'execution', 'test', 'final_review', 'causal_review')),
  CHECK (root_kind IS NULL OR root_kind IN ('observation', 'test_result', 'user_constraint', 'design_decision', 'external_evidence')),
  FOREIGN KEY (duplicate_of_node_id) REFERENCES causal_nodes(node_id)
);

CREATE TABLE IF NOT EXISTS causal_node_terms (
  node_id INTEGER NOT NULL,
  term TEXT NOT NULL,
  weight REAL NOT NULL,
  PRIMARY KEY (node_id, term),
  FOREIGN KEY (node_id) REFERENCES causal_nodes(node_id)
);

CREATE TABLE IF NOT EXISTS causal_dependency_groups (
  group_id TEXT PRIMARY KEY,
  node_id INTEGER NOT NULL,
  scope TEXT NOT NULL,
  conditions_json TEXT NOT NULL,
  assumptions_json TEXT NOT NULL,
  confidence TEXT NOT NULL,
  invalidation_conditions_json TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  CHECK (confidence IN ('high', 'medium', 'low')),
  FOREIGN KEY (node_id) REFERENCES causal_nodes(node_id)
);

CREATE TABLE IF NOT EXISTS causal_dependency_nodes (
  group_id TEXT NOT NULL,
  predecessor_node_id INTEGER NOT NULL,
  PRIMARY KEY (group_id, predecessor_node_id),
  FOREIGN KEY (group_id) REFERENCES causal_dependency_groups(group_id),
  FOREIGN KEY (predecessor_node_id) REFERENCES causal_nodes(node_id)
);

CREATE TABLE IF NOT EXISTS causal_node_refs (
  node_id INTEGER NOT NULL,
  ref_type TEXT NOT NULL,
  ref_id TEXT NOT NULL,
  PRIMARY KEY (node_id, ref_type, ref_id),
  CHECK (ref_type IN ('archive', 'knowledge', 'test', 'external', 'artifact')),
  FOREIGN KEY (node_id) REFERENCES causal_nodes(node_id)
);

CREATE TABLE IF NOT EXISTS causal_group_refs (
  group_id TEXT NOT NULL,
  ref_type TEXT NOT NULL,
  ref_id TEXT NOT NULL,
  PRIMARY KEY (group_id, ref_type, ref_id),
  CHECK (ref_type IN ('archive', 'knowledge', 'test', 'external', 'artifact')),
  FOREIGN KEY (group_id) REFERENCES causal_dependency_groups(group_id)
);

CREATE TABLE IF NOT EXISTS causal_admission_records (
  node_id INTEGER NOT NULL,
  admitted_at_utc TEXT NOT NULL,
  admitted_by_module TEXT NOT NULL,
  admission_run_id TEXT,
  rationale TEXT NOT NULL,
  evidence_ref TEXT,
  CHECK (admitted_by_module IN ('master', 'causal_review')),
  FOREIGN KEY (node_id) REFERENCES causal_nodes(node_id)
);

CREATE TABLE IF NOT EXISTS causal_invalidation_records (
  node_id INTEGER NOT NULL,
  invalidated_at_utc TEXT NOT NULL,
  invalidated_by_module TEXT NOT NULL,
  invalidation_run_id TEXT,
  reason TEXT NOT NULL,
  invalidation_condition TEXT,
  CHECK (invalidated_by_module IN ('master', 'causal_review')),
  FOREIGN KEY (node_id) REFERENCES causal_nodes(node_id)
);

CREATE TABLE IF NOT EXISTS causal_supersession_records (
  old_node_id INTEGER NOT NULL,
  new_node_id INTEGER NOT NULL,
  superseded_at_utc TEXT NOT NULL,
  reason TEXT NOT NULL,
  FOREIGN KEY (old_node_id) REFERENCES causal_nodes(node_id),
  FOREIGN KEY (new_node_id) REFERENCES causal_nodes(node_id)
);

CREATE TABLE IF NOT EXISTS causal_revalidation_queue (
  queue_id TEXT PRIMARY KEY,
  node_id INTEGER NOT NULL,
  triggered_by_node_id INTEGER,
  trigger_type TEXT NOT NULL,
  queued_at_utc TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL,
  resolved_at_utc TEXT,
  resolution_rationale TEXT,
  CHECK (trigger_type IN (
    'dependency_invalidated',
    'dependency_superseded',
    'dependency_deprecated',
    'scope_rule_changed',
    'knowledge_ref_changed',
    'evidence_ref_changed',
    'manual_review'
  )),
  CHECK (status IN ('pending', 'in_progress', 'resolved', 'dismissed')),
  FOREIGN KEY (node_id) REFERENCES causal_nodes(node_id),
  FOREIGN KEY (triggered_by_node_id) REFERENCES causal_nodes(node_id)
);

CREATE TABLE IF NOT EXISTS causal_embeddings (
  node_id INTEGER PRIMARY KEY,
  embedding_model_id TEXT NOT NULL,
  embedding BLOB NOT NULL,
  indexed_at_utc TEXT NOT NULL,
  source_content_hash TEXT NOT NULL,
  FOREIGN KEY (node_id) REFERENCES causal_nodes(node_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS causal_nodes_fts USING fts5(
  node_id UNINDEXED,
  content,
  semantic_summary,
  semantic_keys,
  scope_terms,
  condition_terms,
  invalidation_terms
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_revalidation_dedupe_pending
ON causal_revalidation_queue(node_id, triggered_by_node_id, trigger_type)
WHERE status IN ('pending', 'in_progress');

CREATE INDEX IF NOT EXISTS idx_causal_node_terms_term_node
ON causal_node_terms(term, node_id);

CREATE INDEX IF NOT EXISTS idx_dependency_predecessor
ON causal_dependency_nodes(predecessor_node_id);

CREATE INDEX IF NOT EXISTS idx_dependency_group_node
ON causal_dependency_groups(node_id);

CREATE INDEX IF NOT EXISTS idx_revalidation_status_node
ON causal_revalidation_queue(status, node_id);

CREATE INDEX IF NOT EXISTS idx_revalidation_node_status
ON causal_revalidation_queue(node_id, status);

CREATE INDEX IF NOT EXISTS idx_revalidation_triggered_by_node
ON causal_revalidation_queue(triggered_by_node_id);

CREATE INDEX IF NOT EXISTS idx_nodes_status
ON causal_nodes(status);

CREATE INDEX IF NOT EXISTS idx_nodes_duplicate_of
ON causal_nodes(duplicate_of_node_id);

CREATE INDEX IF NOT EXISTS idx_nodes_strict_content_hash
ON causal_nodes(strict_content_hash);

CREATE INDEX IF NOT EXISTS idx_nodes_causal_identity_hash
ON causal_nodes(causal_identity_hash);

CREATE UNIQUE INDEX IF NOT EXISTS idx_nodes_active_causal_identity_hash
ON causal_nodes(causal_identity_hash)
WHERE status IN ('candidate', 'admitted', 'deprecated', 'superseded');
"""
