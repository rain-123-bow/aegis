from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .models import (
    ContextPack,
    CreateItem,
    EdgeRelation,
    EventType,
    ItemStatus,
    LedgerEdge,
    LedgerEvent,
    LedgerItem,
    LinkItems,
    SearchResult,
    enum_value,
    normalize_relative_path,
    validate_embedding,
)
from .schema import build_init_sql, validate_identifier


DEPENDENCY_RELATIONS = (
    EdgeRelation.SUPPORTS.value,
    EdgeRelation.REFUTES.value,
    EdgeRelation.ASSUMES.value,
)


def _vector_literal(embedding: Sequence[float] | None, dimensions: int | None = None) -> str | None:
    values = validate_embedding(embedding, dimensions=dimensions)
    if values is None:
        return None
    return "[" + ",".join(str(value) for value in values) + "]"


class ReasoningLedger:
    def __init__(
        self,
        dsn: str | None = None,
        *,
        project_id: str,
        schema: str = "reasoning_ledger",
        embedding_dimensions: int = 1536,
    ) -> None:
        if not project_id:
            raise ValueError("project_id must not be empty")
        self.dsn = dsn or os.environ.get("AEGIS_LEDGER_DSN")
        if not self.dsn:
            raise RuntimeError("missing PostgreSQL DSN; set AEGIS_LEDGER_DSN or pass dsn")
        self.project_id = project_id
        self.schema = validate_identifier(schema)
        self.embedding_dimensions = embedding_dimensions

    def connect(self) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def migrate(self) -> None:
        with self.connect() as conn:
            conn.execute(build_init_sql(schema=self.schema, embedding_dimensions=self.embedding_dimensions))

    def add_item(self, item: CreateItem) -> LedgerItem:
        embedding = _vector_literal(item.embedding, self.embedding_dimensions)
        artifact_path = normalize_relative_path(item.artifact_path)
        evidence_path = normalize_relative_path(item.evidence_path)
        params = {
            "project_id": self.project_id,
            "id": item.id,
            "type": enum_value(item.type),
            "status": enum_value(item.status),
            "scope": Jsonb(dict(item.scope)),
            "content": item.content,
            "artifact_path": artifact_path,
            "source": item.source,
            "evidence_path": evidence_path,
            "confidence": item.confidence,
            "level": item.level,
            "version": item.version,
            "embedding": embedding,
            "metadata": Jsonb(dict(item.metadata)),
            "created_by": item.created_by,
        }
        query = sql.SQL(
            """
            INSERT INTO {item_table} (
              project_id, id, type, status, scope, content, artifact_path, source,
              evidence_path, confidence, level, version, embedding, metadata, created_by
            )
            VALUES (
              %(project_id)s, %(id)s, %(type)s, %(status)s, %(scope)s, %(content)s,
              %(artifact_path)s, %(source)s, %(evidence_path)s, %(confidence)s,
              %(level)s, %(version)s, %(embedding)s::vector, %(metadata)s, %(created_by)s
            )
            RETURNING *
            """
        ).format(item_table=self._table("reasoning_item"))
        with self.connect() as conn:
            with conn.transaction():
                row = conn.execute(query, params).fetchone()
                self._insert_event(
                    conn,
                    target_kind="item",
                    target_id=item.id,
                    event_type=EventType.CREATED,
                    reason="item created",
                    created_by=item.created_by,
                    payload={"type": enum_value(item.type), "status": enum_value(item.status)},
                )
                return LedgerItem.from_row(row)

    def get_item(self, item_id: str) -> LedgerItem:
        query = sql.SQL(
            """
            SELECT *
            FROM {item_table}
            WHERE project_id = %s AND id = %s
            """
        ).format(item_table=self._table("reasoning_item"))
        with self.connect() as conn:
            row = conn.execute(query, (self.project_id, item_id)).fetchone()
        if row is None:
            raise KeyError(f"item not found: {item_id}")
        return LedgerItem.from_row(row)

    def list_items(
        self,
        *,
        statuses: Sequence[ItemStatus | str] = (ItemStatus.ACTIVE,),
        item_types: Sequence[str] | None = None,
        scope: Mapping[str, Any] | None = None,
        limit: int = 50,
    ) -> list[LedgerItem]:
        status_values = [enum_value(value) for value in statuses]
        clauses = [sql.SQL("project_id = %(project_id)s"), sql.SQL("status = ANY(%(statuses)s)")]
        params: dict[str, Any] = {
            "project_id": self.project_id,
            "statuses": status_values,
            "limit": limit,
        }
        if item_types:
            clauses.append(sql.SQL("type = ANY(%(item_types)s)"))
            params["item_types"] = [str(value) for value in item_types]
        if scope:
            clauses.append(sql.SQL("scope @> %(scope)s"))
            params["scope"] = Jsonb(dict(scope))

        query = sql.SQL(
            """
            SELECT *
            FROM {item_table}
            WHERE {where}
            ORDER BY level ASC, updated_at DESC, id ASC
            LIMIT %(limit)s
            """
        ).format(
            item_table=self._table("reasoning_item"),
            where=sql.SQL(" AND ").join(clauses),
        )
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [LedgerItem.from_row(row) for row in rows]

    def link_items(self, link: LinkItems) -> LedgerEdge:
        self._assert_items_exist(link.from_id, link.to_id)
        relation = enum_value(link.relation)
        if self._would_create_cycle(link.from_id, link.to_id):
            raise ValueError(f"edge would create a cycle: {link.from_id} -> {link.to_id}")
        params = {
            "project_id": self.project_id,
            "from_id": link.from_id,
            "to_id": link.to_id,
            "relation": relation,
            "reason": link.reason,
            "confidence": link.confidence,
            "metadata": Jsonb(dict(link.metadata)),
            "created_by": link.created_by,
        }
        query = sql.SQL(
            """
            INSERT INTO {edge_table} (
              project_id, from_id, to_id, relation, reason, confidence, metadata, created_by
            )
            VALUES (
              %(project_id)s, %(from_id)s, %(to_id)s, %(relation)s, %(reason)s,
              %(confidence)s, %(metadata)s, %(created_by)s
            )
            RETURNING *
            """
        ).format(edge_table=self._table("reasoning_edge"))
        with self.connect() as conn:
            with conn.transaction():
                row = conn.execute(query, params).fetchone()
                edge = LedgerEdge.from_row(row)
                self._insert_event(
                    conn,
                    target_kind="edge",
                    target_id=str(edge.id),
                    event_type=EventType.LINKED,
                    reason=link.reason,
                    created_by=link.created_by,
                    payload={
                        "from_id": link.from_id,
                        "to_id": link.to_id,
                        "relation": relation,
                    },
                )
                if relation in DEPENDENCY_RELATIONS:
                    self._recompute_levels_upward(conn, [link.to_id])
                return edge

    def invalidate_item(self, item_id: str, *, reason: str, created_by: str) -> list[LedgerItem]:
        if not reason:
            raise ValueError("reason must not be empty")
        with self.connect() as conn:
            with conn.transaction():
                conn.execute(
                    sql.SQL(
                        """
                        UPDATE {item_table}
                        SET status = 'invalid'
                        WHERE project_id = %s AND id = %s
                        """
                    ).format(item_table=self._table("reasoning_item")),
                    (self.project_id, item_id),
                )
                self._insert_event(
                    conn,
                    target_kind="item",
                    target_id=item_id,
                    event_type=EventType.INVALIDATED,
                    reason=reason,
                    created_by=created_by,
                    payload={},
                )
                impacted_ids = self._dependent_ids(conn, item_id)
                if impacted_ids:
                    conn.execute(
                        sql.SQL(
                            """
                            UPDATE {item_table}
                            SET status = 'stale'
                            WHERE project_id = %s
                              AND id = ANY(%s)
                              AND status = 'active'
                            """
                        ).format(item_table=self._table("reasoning_item")),
                        (self.project_id, impacted_ids),
                    )
                    for impacted_id in impacted_ids:
                        self._insert_event(
                            conn,
                            target_kind="item",
                            target_id=impacted_id,
                            event_type=EventType.MARKED_STALE,
                            reason=f"upstream item invalidated: {item_id}",
                            created_by=created_by,
                            payload={"invalidated_upstream": item_id},
                        )
                rows = conn.execute(
                    sql.SQL(
                        """
                        SELECT *
                        FROM {item_table}
                        WHERE project_id = %s AND id = ANY(%s)
                        ORDER BY level ASC, id ASC
                        """
                    ).format(item_table=self._table("reasoning_item")),
                    (self.project_id, impacted_ids),
                ).fetchall()
                return [LedgerItem.from_row(row) for row in rows]

    def revalidate_item(self, item_id: str, *, reason: str, created_by: str) -> LedgerItem:
        with self.connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    sql.SQL(
                        """
                        UPDATE {item_table}
                        SET status = 'active'
                        WHERE project_id = %s AND id = %s
                        RETURNING *
                        """
                    ).format(item_table=self._table("reasoning_item")),
                    (self.project_id, item_id),
                ).fetchone()
                if row is None:
                    raise KeyError(f"item not found: {item_id}")
                self._insert_event(
                    conn,
                    target_kind="item",
                    target_id=item_id,
                    event_type=EventType.REVALIDATED,
                    reason=reason,
                    created_by=created_by,
                    payload={},
                )
                return LedgerItem.from_row(row)

    def supersede_item(self, old_item_id: str, new_item: CreateItem, *, reason: str) -> LedgerItem:
        if old_item_id == new_item.id:
            raise ValueError("old and new item ids must differ")
        with self.connect() as conn:
            with conn.transaction():
                conn.execute(
                    sql.SQL(
                        """
                        UPDATE {item_table}
                        SET status = 'superseded'
                        WHERE project_id = %s AND id = %s
                        """
                    ).format(item_table=self._table("reasoning_item")),
                    (self.project_id, old_item_id),
                )
                self._insert_event(
                    conn,
                    target_kind="item",
                    target_id=old_item_id,
                    event_type=EventType.SUPERSEDED,
                    reason=reason,
                    created_by=new_item.created_by,
                    payload={"superseded_by": new_item.id},
                )
        created = self.add_item(new_item)
        self.link_items(
            LinkItems(
                from_id=old_item_id,
                to_id=new_item.id,
                relation=EdgeRelation.SUPERSEDES,
                reason=reason,
                created_by=new_item.created_by,
            )
        )
        return created

    def trace_causes(
        self,
        item_id: str,
        *,
        max_depth: int = 8,
        relations: Sequence[EdgeRelation | str] = DEPENDENCY_RELATIONS,
    ) -> tuple[list[LedgerItem], list[LedgerEdge]]:
        relation_values = [enum_value(value) for value in relations]
        query = sql.SQL(
            """
            WITH RECURSIVE walk(depth, item_id) AS (
              SELECT 0, %s::text
              UNION ALL
              SELECT walk.depth + 1, edge.from_id
              FROM walk
              JOIN {edge_table} edge
                ON edge.project_id = %s
               AND edge.to_id = walk.item_id
               AND edge.status = 'active'
               AND edge.relation = ANY(%s)
              WHERE walk.depth < %s
            ),
            edge_rows AS (
              SELECT DISTINCT edge.*
              FROM walk
              JOIN {edge_table} edge
                ON edge.project_id = %s
               AND edge.to_id = walk.item_id
               AND edge.status = 'active'
               AND edge.relation = ANY(%s)
            )
            SELECT 'item' AS row_kind, item.*, NULL::bigint AS edge_id,
                   NULL::text AS from_id, NULL::text AS to_id, NULL::text AS relation,
                   NULL::text AS edge_status, NULL::text AS reason,
                   NULL::double precision AS edge_confidence, NULL::jsonb AS edge_metadata,
                   NULL::text AS edge_created_by, NULL::timestamptz AS edge_created_at
            FROM {item_table} item
            WHERE item.project_id = %s
              AND item.id IN (SELECT item_id FROM walk WHERE item_id <> %s)
            UNION ALL
            SELECT 'edge' AS row_kind, NULL::text AS project_id, NULL::text AS id,
                   NULL::text AS type, NULL::text AS status, NULL::jsonb AS scope,
                   NULL::text AS content, NULL::text AS artifact_path, NULL::text AS source,
                   NULL::text AS evidence_path, NULL::double precision AS confidence,
                   NULL::integer AS level, NULL::integer AS version, NULL::vector AS embedding,
                   NULL::jsonb AS metadata, NULL::text AS created_by, NULL::timestamptz AS created_at,
                   NULL::timestamptz AS updated_at, edge.id AS edge_id, edge.from_id, edge.to_id,
                   edge.relation, edge.status AS edge_status, edge.reason,
                   edge.confidence AS edge_confidence, edge.metadata AS edge_metadata,
                   edge.created_by AS edge_created_by, edge.created_at AS edge_created_at
            FROM edge_rows edge
            """
        ).format(
            edge_table=self._table("reasoning_edge"),
            item_table=self._table("reasoning_item"),
        )
        with self.connect() as conn:
            rows = conn.execute(
                query,
                (
                    item_id,
                    self.project_id,
                    relation_values,
                    max_depth,
                    self.project_id,
                    relation_values,
                    self.project_id,
                    item_id,
                ),
            ).fetchall()
        return self._split_mixed_rows(rows)

    def analyze_impact(
        self,
        item_id: str,
        *,
        max_depth: int = 8,
        relations: Sequence[EdgeRelation | str] = DEPENDENCY_RELATIONS,
    ) -> tuple[list[LedgerItem], list[LedgerEdge]]:
        relation_values = [enum_value(value) for value in relations]
        query = sql.SQL(
            """
            WITH RECURSIVE walk(depth, item_id) AS (
              SELECT 0, %s::text
              UNION ALL
              SELECT walk.depth + 1, edge.to_id
              FROM walk
              JOIN {edge_table} edge
                ON edge.project_id = %s
               AND edge.from_id = walk.item_id
               AND edge.status = 'active'
               AND edge.relation = ANY(%s)
              WHERE walk.depth < %s
            ),
            edge_rows AS (
              SELECT DISTINCT edge.*
              FROM walk
              JOIN {edge_table} edge
                ON edge.project_id = %s
               AND edge.from_id = walk.item_id
               AND edge.status = 'active'
               AND edge.relation = ANY(%s)
            )
            SELECT 'item' AS row_kind, item.*, NULL::bigint AS edge_id,
                   NULL::text AS from_id, NULL::text AS to_id, NULL::text AS relation,
                   NULL::text AS edge_status, NULL::text AS reason,
                   NULL::double precision AS edge_confidence, NULL::jsonb AS edge_metadata,
                   NULL::text AS edge_created_by, NULL::timestamptz AS edge_created_at
            FROM {item_table} item
            WHERE item.project_id = %s
              AND item.id IN (SELECT item_id FROM walk WHERE item_id <> %s)
            UNION ALL
            SELECT 'edge' AS row_kind, NULL::text AS project_id, NULL::text AS id,
                   NULL::text AS type, NULL::text AS status, NULL::jsonb AS scope,
                   NULL::text AS content, NULL::text AS artifact_path, NULL::text AS source,
                   NULL::text AS evidence_path, NULL::double precision AS confidence,
                   NULL::integer AS level, NULL::integer AS version, NULL::vector AS embedding,
                   NULL::jsonb AS metadata, NULL::text AS created_by, NULL::timestamptz AS created_at,
                   NULL::timestamptz AS updated_at, edge.id AS edge_id, edge.from_id, edge.to_id,
                   edge.relation, edge.status AS edge_status, edge.reason,
                   edge.confidence AS edge_confidence, edge.metadata AS edge_metadata,
                   edge.created_by AS edge_created_by, edge.created_at AS edge_created_at
            FROM edge_rows edge
            """
        ).format(
            edge_table=self._table("reasoning_edge"),
            item_table=self._table("reasoning_item"),
        )
        with self.connect() as conn:
            rows = conn.execute(
                query,
                (
                    item_id,
                    self.project_id,
                    relation_values,
                    max_depth,
                    self.project_id,
                    relation_values,
                    self.project_id,
                    item_id,
                ),
            ).fetchall()
        return self._split_mixed_rows(rows)

    def semantic_search(
        self,
        query_embedding: Sequence[float],
        *,
        limit: int = 10,
        statuses: Sequence[ItemStatus | str] = (ItemStatus.ACTIVE,),
        item_types: Sequence[str] | None = None,
        scope: Mapping[str, Any] | None = None,
    ) -> list[SearchResult]:
        vector = _vector_literal(query_embedding, self.embedding_dimensions)
        clauses = [
            sql.SQL("project_id = %(project_id)s"),
            sql.SQL("embedding IS NOT NULL"),
            sql.SQL("status = ANY(%(statuses)s)"),
        ]
        params: dict[str, Any] = {
            "project_id": self.project_id,
            "embedding": vector,
            "statuses": [enum_value(value) for value in statuses],
            "limit": limit,
        }
        if item_types:
            clauses.append(sql.SQL("type = ANY(%(item_types)s)"))
            params["item_types"] = [str(value) for value in item_types]
        if scope:
            clauses.append(sql.SQL("scope @> %(scope)s"))
            params["scope"] = Jsonb(dict(scope))
        query = sql.SQL(
            """
            SELECT *, embedding <=> %(embedding)s::vector AS distance
            FROM {item_table}
            WHERE {where}
            ORDER BY embedding <=> %(embedding)s::vector ASC, id ASC
            LIMIT %(limit)s
            """
        ).format(
            item_table=self._table("reasoning_item"),
            where=sql.SQL(" AND ").join(clauses),
        )
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            SearchResult(item=LedgerItem.from_row(row), distance=float(row["distance"]))
            for row in rows
        ]

    def retrieve_context_pack(
        self,
        *,
        task_id: str,
        agent_role: str,
        query: str,
        query_embedding: Sequence[float] | None = None,
        scope: Mapping[str, Any] | None = None,
        limit: int = 12,
        include_causes: bool = True,
    ) -> ContextPack:
        if query_embedding is not None:
            items = [
                result.item
                for result in self.semantic_search(
                    query_embedding,
                    limit=limit,
                    statuses=(ItemStatus.ACTIVE, ItemStatus.STALE),
                    scope=scope,
                )
            ]
        else:
            items = self.list_items(
                statuses=(ItemStatus.ACTIVE, ItemStatus.STALE),
                scope=scope,
                limit=limit,
            )

        cause_by_id: dict[str, LedgerItem] = {}
        edge_by_id: dict[int, LedgerEdge] = {}
        warnings: list[str] = []
        for item in items:
            if enum_value(item.status) != ItemStatus.ACTIVE.value:
                warnings.append(f"item {item.id} status is {item.status}")
            if include_causes:
                causes, edges = self.trace_causes(item.id)
                for cause in causes:
                    cause_by_id[cause.id] = cause
                    if enum_value(cause.status) != ItemStatus.ACTIVE.value:
                        warnings.append(f"cause item {cause.id} status is {cause.status}")
                for edge in edges:
                    edge_by_id[edge.id] = edge

        artifact_paths = [
            path
            for path in [item.artifact_path for item in items] + [item.artifact_path for item in cause_by_id.values()]
            if path
        ]
        return ContextPack(
            project_id=self.project_id,
            task_id=task_id,
            agent_role=agent_role,
            query=query,
            items=items,
            cause_items=list(cause_by_id.values()),
            edges=list(edge_by_id.values()),
            warnings=list(dict.fromkeys(warnings)),
            artifact_paths=list(dict.fromkeys(artifact_paths)),
        )

    def export_snapshot(self, output_path: str | Path | None = None) -> dict[str, list[dict[str, Any]]]:
        with self.connect() as conn:
            item_rows = conn.execute(
                sql.SQL("SELECT * FROM {item_table} WHERE project_id = %s ORDER BY id").format(
                    item_table=self._table("reasoning_item")
                ),
                (self.project_id,),
            ).fetchall()
            edge_rows = conn.execute(
                sql.SQL("SELECT * FROM {edge_table} WHERE project_id = %s ORDER BY id").format(
                    edge_table=self._table("reasoning_edge")
                ),
                (self.project_id,),
            ).fetchall()
            event_rows = conn.execute(
                sql.SQL("SELECT * FROM {event_table} WHERE project_id = %s ORDER BY id").format(
                    event_table=self._table("reasoning_event")
                ),
                (self.project_id,),
            ).fetchall()
        snapshot = {
            "items": [LedgerItem.from_row(row).to_dict() for row in item_rows],
            "edges": [LedgerEdge.from_row(row).to_dict() for row in edge_rows],
            "events": [LedgerEvent.from_row(row).to_dict() for row in event_rows],
        }
        if output_path is not None:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as output_file:
                for section, rows in snapshot.items():
                    for row in rows:
                        output_file.write(json.dumps({"section": section, "row": row}, ensure_ascii=False) + "\n")
        return snapshot

    def rebuild_index(self, *, created_by: str = "reasoning_ledger") -> int:
        with self.connect() as conn:
            with conn.transaction():
                conn.execute(
                    sql.SQL("DROP INDEX IF EXISTS {index_name}").format(
                        index_name=sql.Identifier(self.schema, "reasoning_item_embedding_hnsw_idx")
                    )
                )
                conn.execute(
                    sql.SQL(
                        """
                        CREATE INDEX reasoning_item_embedding_hnsw_idx
                        ON {item_table}
                        USING hnsw (embedding vector_cosine_ops)
                        WHERE embedding IS NOT NULL
                        """
                    ).format(item_table=self._table("reasoning_item"))
                )
                count = conn.execute(
                    sql.SQL(
                        """
                        SELECT count(*) AS count
                        FROM {item_table}
                        WHERE project_id = %s AND embedding IS NOT NULL
                        """
                    ).format(item_table=self._table("reasoning_item")),
                    (self.project_id,),
                ).fetchone()["count"]
                self._insert_event(
                    conn,
                    target_kind="index",
                    target_id="reasoning_item_embedding_hnsw_idx",
                    event_type=EventType.INDEX_REBUILT,
                    reason="embedding index rebuilt",
                    created_by=created_by,
                    payload={"indexed_items": int(count)},
                )
                return int(count)

    def _assert_items_exist(self, *item_ids: str) -> None:
        query = sql.SQL(
            """
            SELECT id
            FROM {item_table}
            WHERE project_id = %s AND id = ANY(%s)
            """
        ).format(item_table=self._table("reasoning_item"))
        with self.connect() as conn:
            rows = conn.execute(query, (self.project_id, list(item_ids))).fetchall()
        found = {row["id"] for row in rows}
        missing = [item_id for item_id in item_ids if item_id not in found]
        if missing:
            raise KeyError(f"missing item(s): {', '.join(missing)}")

    def _would_create_cycle(self, from_id: str, to_id: str) -> bool:
        query = sql.SQL(
            """
            WITH RECURSIVE walk(item_id) AS (
              SELECT %s::text
              UNION
              SELECT edge.to_id
              FROM walk
              JOIN {edge_table} edge
                ON edge.project_id = %s
               AND edge.from_id = walk.item_id
               AND edge.status = 'active'
            )
            SELECT EXISTS(SELECT 1 FROM walk WHERE item_id = %s) AS cycle
            """
        ).format(edge_table=self._table("reasoning_edge"))
        with self.connect() as conn:
            row = conn.execute(query, (to_id, self.project_id, from_id)).fetchone()
        return bool(row["cycle"])

    def _dependent_ids(self, conn: psycopg.Connection[dict[str, Any]], item_id: str) -> list[str]:
        rows = conn.execute(
            sql.SQL(
                """
                WITH RECURSIVE walk(item_id) AS (
                  SELECT %s::text
                  UNION
                  SELECT edge.to_id
                  FROM walk
                  JOIN {edge_table} edge
                    ON edge.project_id = %s
                   AND edge.from_id = walk.item_id
                   AND edge.status = 'active'
                   AND edge.relation = ANY(%s)
                )
                SELECT item_id
                FROM walk
                WHERE item_id <> %s
                ORDER BY item_id
                """
            ).format(edge_table=self._table("reasoning_edge")),
            (item_id, self.project_id, list(DEPENDENCY_RELATIONS), item_id),
        ).fetchall()
        return [row["item_id"] for row in rows]

    def _recompute_levels_upward(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        start_ids: Iterable[str],
    ) -> None:
        pending = list(dict.fromkeys(start_ids))
        seen: set[str] = set()
        while pending:
            item_id = pending.pop(0)
            if item_id in seen:
                continue
            seen.add(item_id)
            row = conn.execute(
                sql.SQL(
                    """
                    SELECT COALESCE(max(parent.level) + 1, 0) AS level
                    FROM {edge_table} edge
                    JOIN {item_table} parent
                      ON parent.project_id = edge.project_id
                     AND parent.id = edge.from_id
                    WHERE edge.project_id = %s
                      AND edge.to_id = %s
                      AND edge.status = 'active'
                      AND edge.relation = ANY(%s)
                    """
                ).format(
                    edge_table=self._table("reasoning_edge"),
                    item_table=self._table("reasoning_item"),
                ),
                (self.project_id, item_id, list(DEPENDENCY_RELATIONS)),
            ).fetchone()
            new_level = int(row["level"])
            conn.execute(
                sql.SQL(
                    """
                    UPDATE {item_table}
                    SET level = %s
                    WHERE project_id = %s AND id = %s AND level <> %s
                    """
                ).format(item_table=self._table("reasoning_item")),
                (new_level, self.project_id, item_id, new_level),
            )
            children = conn.execute(
                sql.SQL(
                    """
                    SELECT to_id
                    FROM {edge_table}
                    WHERE project_id = %s
                      AND from_id = %s
                      AND status = 'active'
                      AND relation = ANY(%s)
                    """
                ).format(edge_table=self._table("reasoning_edge")),
                (self.project_id, item_id, list(DEPENDENCY_RELATIONS)),
            ).fetchall()
            pending.extend(row["to_id"] for row in children)

    def _insert_event(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        *,
        target_kind: str,
        target_id: str,
        event_type: EventType | str,
        reason: str,
        created_by: str,
        payload: Mapping[str, Any],
    ) -> None:
        conn.execute(
            sql.SQL(
                """
                INSERT INTO {event_table} (
                  project_id, target_kind, target_id, event_type, reason, payload, created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
            ).format(event_table=self._table("reasoning_event")),
            (
                self.project_id,
                target_kind,
                target_id,
                enum_value(event_type),
                reason,
                Jsonb(dict(payload)),
                created_by,
            ),
        )

    def _split_mixed_rows(self, rows: Sequence[Mapping[str, Any]]) -> tuple[list[LedgerItem], list[LedgerEdge]]:
        items: list[LedgerItem] = []
        edges: list[LedgerEdge] = []
        for row in rows:
            if row["row_kind"] == "item":
                items.append(LedgerItem.from_row(row))
            else:
                edges.append(
                    LedgerEdge(
                        id=int(row["edge_id"]),
                        project_id=self.project_id,
                        from_id=str(row["from_id"]),
                        to_id=str(row["to_id"]),
                        relation=str(row["relation"]),
                        status=str(row["edge_status"]),
                        reason=str(row["reason"]),
                        confidence=row["edge_confidence"],
                        metadata=dict(row["edge_metadata"] or {}),
                        created_by=str(row["edge_created_by"]),
                        created_at=row["edge_created_at"],
                    )
                )
        return items, edges

    def _table(self, table_name: str) -> sql.Composed:
        return sql.SQL("{}.{}").format(sql.Identifier(self.schema), sql.Identifier(table_name))
