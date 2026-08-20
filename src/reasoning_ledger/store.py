from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TypeVar

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .models import (
    AuthorityContextPack,
    CandidateHit,
    EmbeddingProfile,
    EvidenceDescriptor,
    LedgerAuthorityEvent,
    LedgerEvidence,
    LedgerRelation,
    LedgerStatementRevision,
    RelationType,
    RevisionValidity,
    StatementRelation,
    StatementRevision,
    SUPPORTED_EMBEDDING_INPUT_TEMPLATE_VERSION,
    enum_value,
    json_ready,
    render_statement_embedding_input,
    validate_embedding,
)
from .project import (
    MINIMUM_SUPPORTED_PGVECTOR_VERSION,
    MINIMUM_SUPPORTED_POSTGRESQL_MAJOR,
    _parse_version,
)
from .schema import build_init_sql, validate_identifier


T = TypeVar("T")

CAUSAL_RELATIONS = (
    RelationType.SUPPORTS.value,
    RelationType.ASSUMES.value,
    RelationType.CAUSES.value,
    RelationType.ENABLES.value,
    RelationType.REQUIRES.value,
)
CONFLICT_RELATIONS = (
    RelationType.REFUTES.value,
    RelationType.PREVENTS.value,
)
ACYCLIC_RELATIONS = frozenset(
    {
        RelationType.SUPPORTS.value,
        RelationType.ASSUMES.value,
        RelationType.SUPERSEDES.value,
        RelationType.REQUIRES.value,
    }
)
SERIALIZATION_FAILURE_SQLSTATES = frozenset({"40001", "40P01"})


def _vector_literal(
    embedding: Sequence[float] | None,
    dimensions: int | None = None,
) -> str | None:
    values = validate_embedding(embedding, dimensions=dimensions)
    if values is None:
        return None
    return "[" + ",".join(str(value) for value in values) + "]"


class ReasoningLedger:
    """Project-isolated immutable reasoning authority with rebuildable indexes."""

    def __init__(
        self,
        dsn: str | None = None,
        *,
        project_id: str,
        schema: str = "reasoning_ledger",
        embedding_dimensions: int = 1536,
        serialization_retries: int = 3,
        minimum_postgresql_major: int = 16,
        minimum_pgvector_version: str = "0.8.0",
    ) -> None:
        if not project_id:
            raise ValueError("project_id must not be empty")
        if embedding_dimensions <= 0:
            raise ValueError("embedding_dimensions must be > 0")
        if serialization_retries < 1:
            raise ValueError("serialization_retries must be >= 1")
        if (
            isinstance(minimum_postgresql_major, bool)
            or not isinstance(minimum_postgresql_major, int)
            or minimum_postgresql_major < MINIMUM_SUPPORTED_POSTGRESQL_MAJOR
        ):
            raise ValueError(
                "minimum_postgresql_major cannot weaken the supported baseline"
            )
        if not isinstance(minimum_pgvector_version, str) or _parse_version(
            minimum_pgvector_version,
            field_name="minimum_pgvector_version",
        ) < MINIMUM_SUPPORTED_PGVECTOR_VERSION:
            raise ValueError(
                "minimum_pgvector_version cannot weaken the supported baseline"
            )
        self.dsn = dsn or os.environ.get("AEGIS_LEDGER_DSN")
        if not self.dsn:
            raise RuntimeError("missing PostgreSQL DSN; set AEGIS_LEDGER_DSN or pass dsn")
        self.project_id = project_id
        self.schema = validate_identifier(schema)
        self.embedding_dimensions = embedding_dimensions
        self.serialization_retries = serialization_retries
        self.minimum_postgresql_major = minimum_postgresql_major
        self.minimum_pgvector_version = minimum_pgvector_version

    def connect(self) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def migrate(self) -> None:
        with self.connect() as conn:
            server_version = int(
                conn.execute("SHOW server_version_num").fetchone()["server_version_num"]
            )
            server_major = server_version // 10000
            if server_major < self.minimum_postgresql_major:
                raise RuntimeError(
                    "PostgreSQL major version is below the reasoning-ledger baseline: "
                    f"{server_major} < {self.minimum_postgresql_major}"
                )
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            vector_version = str(
                conn.execute(
                    "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
                ).fetchone()["extversion"]
            )
            if self._version_tuple(vector_version) < self._version_tuple(
                self.minimum_pgvector_version
            ):
                raise RuntimeError(
                    "pgvector version is below the reasoning-ledger baseline: "
                    f"{vector_version} < {self.minimum_pgvector_version}"
                )
            conn.execute(
                build_init_sql(
                    schema=self.schema,
                    embedding_dimensions=self.embedding_dimensions,
                )
            )

    def register_evidence(self, descriptor: EvidenceDescriptor) -> LedgerEvidence:
        with self.connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    sql.SQL(
                        """
                        INSERT INTO {table} (
                          project_id, evidence_id, path, size, sha256,
                          source_identity, captured_at, scope, content_sha256, created_by
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING *
                        """
                    ).format(table=self._table("evidence_descriptor")),
                    (
                        self.project_id,
                        descriptor.evidence_id,
                        descriptor.path,
                        descriptor.size,
                        descriptor.sha256,
                        Jsonb(dict(descriptor.source_identity)),
                        descriptor.captured_at,
                        Jsonb(dict(descriptor.scope)),
                        descriptor.content_sha256,
                        descriptor.created_by,
                    ),
                ).fetchone()
                self._insert_event(
                    conn,
                    aggregate_kind="EVIDENCE",
                    aggregate_id=descriptor.evidence_id,
                    event_type="EVIDENCE_REGISTERED",
                    reason="evidence descriptor registered",
                    created_by=descriptor.created_by,
                    payload={"content_sha256": descriptor.content_sha256},
                )
        assert row is not None
        return LedgerEvidence.from_row(row)

    def register_embedding_profile(
        self, profile: EmbeddingProfile
    ) -> EmbeddingProfile:
        if profile.dimensions != self.embedding_dimensions:
            raise ValueError(
                "embedding profile dimensions differ from configured vector dimensions"
            )
        if (
            profile.input_template_version
            != SUPPORTED_EMBEDDING_INPUT_TEMPLATE_VERSION
        ):
            raise ValueError(
                "embedding profile uses an unsupported authority input template"
            )
        with self.connect() as conn:
            with conn.transaction():
                conn.execute(
                    sql.SQL(
                        """
                        INSERT INTO {table} (
                          project_id, profile_id, provider, model, model_version,
                          dimensions, normalization, input_template_version,
                          content_sha256, created_by
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """
                    ).format(table=self._table("embedding_profile")),
                    (
                        self.project_id,
                        profile.profile_id,
                        profile.provider,
                        profile.model,
                        profile.model_version,
                        profile.dimensions,
                        profile.normalization,
                        profile.input_template_version,
                        profile.content_sha256,
                        profile.created_by,
                    ),
                )
                self._insert_event(
                    conn,
                    aggregate_kind="INDEX",
                    aggregate_id=profile.profile_id,
                    event_type="EMBEDDING_PROFILE_REGISTERED",
                    reason="embedding profile registered",
                    created_by=profile.created_by,
                    payload={"content_sha256": profile.content_sha256},
                )
        return profile

    def create_statement(
        self, revision: StatementRevision
    ) -> LedgerStatementRevision:
        if revision.revision != 1:
            raise ValueError("initial statement revision must be 1")
        if enum_value(revision.validity).upper() == RevisionValidity.SUPERSEDED.value:
            raise ValueError("initial statement revision cannot be superseded")
        with self.connect() as conn:
            with conn.transaction():
                self._assert_evidence_exists(conn, revision.evidence_ids)
                conn.execute(
                    sql.SQL(
                        """
                        INSERT INTO {table} (project_id, statement_id, created_by)
                        VALUES (%s, %s, %s)
                        """
                    ).format(table=self._table("statement")),
                    (self.project_id, revision.statement_id, revision.created_by),
                )
                self._insert_event(
                    conn,
                    aggregate_kind="STATEMENT",
                    aggregate_id=revision.statement_id,
                    event_type="STATEMENT_CREATED",
                    reason="statement created",
                    created_by=revision.created_by,
                    payload={},
                )
                self._insert_revision(conn, revision)
                event_id = self._insert_event(
                    conn,
                    aggregate_kind="REVISION",
                    aggregate_id=self._revision_key(
                        revision.statement_id, revision.revision
                    ),
                    event_type="REVISION_CREATED",
                    reason="initial statement revision created",
                    created_by=revision.created_by,
                    payload={
                        "content_sha256": revision.content_sha256,
                        "validity": enum_value(revision.validity).upper(),
                    },
                )
                conn.execute(
                    sql.SQL(
                        """
                        INSERT INTO {table} (
                          project_id, statement_id, revision, validity,
                          projection_event_id
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        """
                    ).format(table=self._table("current_projection")),
                    (
                        self.project_id,
                        revision.statement_id,
                        revision.revision,
                        enum_value(revision.validity).upper(),
                        event_id,
                    ),
                )
                row = self._fetch_revision(
                    conn, revision.statement_id, revision.revision
                )
        return LedgerStatementRevision.from_row(row)

    def supersede_statement(
        self,
        revision: StatementRevision,
        *,
        reason: str,
        relation_id: str | None = None,
    ) -> LedgerStatementRevision:
        if revision.revision <= 1:
            raise ValueError("superseding revision must be greater than 1")
        if enum_value(revision.validity).upper() != RevisionValidity.ACTIVE.value:
            raise ValueError("superseding revision must become active")
        if not reason.strip():
            raise ValueError("supersede reason must not be empty")

        def operation(conn: psycopg.Connection[dict[str, Any]]) -> LedgerStatementRevision:
            self._lock_project_graph(conn)
            projection = conn.execute(
                sql.SQL(
                    """
                    SELECT revision
                    FROM {table}
                    WHERE project_id = %s AND statement_id = %s
                    FOR UPDATE
                    """
                ).format(table=self._table("current_projection")),
                (self.project_id, revision.statement_id),
            ).fetchone()
            if projection is None:
                raise KeyError(f"statement not found: {revision.statement_id}")
            old_revision = int(projection["revision"])
            if revision.revision != old_revision + 1:
                raise ValueError(
                    "superseding revision must immediately follow the current revision"
                )
            self._assert_evidence_exists(conn, revision.evidence_ids)
            self._insert_revision(conn, revision)
            self._insert_event(
                conn,
                aggregate_kind="REVISION",
                aggregate_id=self._revision_key(
                    revision.statement_id, revision.revision
                ),
                event_type="REVISION_CREATED",
                reason=reason,
                created_by=revision.created_by,
                payload={"content_sha256": revision.content_sha256},
            )
            relation = StatementRelation(
                relation_id=(
                    relation_id
                    or f"supersedes.{revision.statement_id}.{old_revision}.{revision.revision}"
                ),
                from_statement_id=revision.statement_id,
                from_revision=old_revision,
                to_statement_id=revision.statement_id,
                to_revision=revision.revision,
                relation_type=RelationType.SUPERSEDES,
                applicable_conditions={},
                reason=reason,
                created_by=revision.created_by,
                evidence_ids=revision.evidence_ids,
            )
            self._insert_relation(conn, relation)
            self._insert_event(
                conn,
                aggregate_kind="RELATION",
                aggregate_id=relation.relation_id,
                event_type="RELATION_CREATED",
                reason=reason,
                created_by=revision.created_by,
                payload={"content_sha256": relation.content_sha256},
            )
            event_id = self._insert_event(
                conn,
                aggregate_kind="REVISION",
                aggregate_id=self._revision_key(revision.statement_id, old_revision),
                event_type="REVISION_SUPERSEDED",
                reason=reason,
                created_by=revision.created_by,
                payload={
                    "superseded_by": self._revision_key(
                        revision.statement_id, revision.revision
                    ),
                    "new_validity": enum_value(revision.validity).upper(),
                    "relation_id": relation.relation_id,
                },
            )
            conn.execute(
                sql.SQL(
                    """
                    UPDATE {table}
                    SET revision = %s, validity = %s,
                        projection_event_id = %s, updated_at = now()
                    WHERE project_id = %s AND statement_id = %s
                    """
                ).format(table=self._table("current_projection")),
                (
                    revision.revision,
                    enum_value(revision.validity).upper(),
                    event_id,
                    self.project_id,
                    revision.statement_id,
                ),
            )
            return LedgerStatementRevision.from_row(
                self._fetch_revision(
                    conn, revision.statement_id, revision.revision
                )
            )

        return self._run_serializable(operation)

    def create_relation(self, relation: StatementRelation) -> LedgerRelation:
        def operation(conn: psycopg.Connection[dict[str, Any]]) -> LedgerRelation:
            self._lock_project_graph(conn)
            self._assert_revisions_exist(
                conn,
                (
                    (relation.from_statement_id, relation.from_revision),
                    (relation.to_statement_id, relation.to_revision),
                ),
            )
            self._assert_evidence_exists(conn, relation.evidence_ids)
            if (
                enum_value(relation.relation_type).upper() in ACYCLIC_RELATIONS
                and self._would_create_cycle(conn, relation)
            ):
                raise ValueError(
                    "relation would create a cycle: "
                    f"{relation.from_statement_id}@{relation.from_revision} -> "
                    f"{relation.to_statement_id}@{relation.to_revision}"
                )
            row = self._insert_relation(conn, relation)
            self._insert_event(
                conn,
                aggregate_kind="RELATION",
                aggregate_id=relation.relation_id,
                event_type="RELATION_CREATED",
                reason=relation.reason,
                created_by=relation.created_by,
                payload={"content_sha256": relation.content_sha256},
            )
            return LedgerRelation.from_row(row)

        return self._run_serializable(operation)

    def set_current_validity(
        self,
        statement_id: str,
        validity: RevisionValidity | str,
        *,
        reason: str,
        created_by: str,
    ) -> LedgerStatementRevision:
        normalized = enum_value(validity).upper()
        event_type = {
            RevisionValidity.ACTIVE.value: "REVISION_REVALIDATED",
            RevisionValidity.STALE.value: "REVISION_MARKED_STALE",
            RevisionValidity.INVALID.value: "REVISION_INVALIDATED",
        }.get(normalized)
        if event_type is None:
            raise ValueError("validity is invalid")
        if not reason.strip() or not created_by.strip():
            raise ValueError("reason and created_by must not be empty")
        with self.connect() as conn:
            with conn.transaction():
                projection = conn.execute(
                    sql.SQL(
                        """
                        SELECT revision
                        FROM {table}
                        WHERE project_id = %s AND statement_id = %s
                        FOR UPDATE
                        """
                    ).format(table=self._table("current_projection")),
                    (self.project_id, statement_id),
                ).fetchone()
                if projection is None:
                    raise KeyError(f"statement not found: {statement_id}")
                revision = int(projection["revision"])
                event_id = self._insert_event(
                    conn,
                    aggregate_kind="REVISION",
                    aggregate_id=self._revision_key(statement_id, revision),
                    event_type=event_type,
                    reason=reason,
                    created_by=created_by,
                    payload={"validity": normalized},
                )
                conn.execute(
                    sql.SQL(
                        """
                        UPDATE {table}
                        SET validity = %s, projection_event_id = %s, updated_at = now()
                        WHERE project_id = %s AND statement_id = %s
                        """
                    ).format(table=self._table("current_projection")),
                    (normalized, event_id, self.project_id, statement_id),
                )
                row = self._fetch_revision(conn, statement_id, revision)
        return LedgerStatementRevision.from_row(row)

    def get_current_revision(self, statement_id: str) -> LedgerStatementRevision:
        with self.connect() as conn:
            row = self._fetch_current_revision(conn, statement_id)
        if row is None:
            raise KeyError(f"statement not found: {statement_id}")
        return LedgerStatementRevision.from_row(row)

    def list_current_revisions(
        self,
        *,
        validities: Sequence[RevisionValidity | str] = (RevisionValidity.ACTIVE,),
        statement_types: Sequence[str] | None = None,
        scope: Mapping[str, Any] | None = None,
        limit: int = 50,
    ) -> list[LedgerStatementRevision]:
        if limit <= 0:
            raise ValueError("limit must be > 0")
        clauses = [
            sql.SQL("projection.project_id = %(project_id)s"),
            sql.SQL("projection.validity = ANY(%(validities)s)"),
        ]
        params: dict[str, Any] = {
            "project_id": self.project_id,
            "validities": [enum_value(value).upper() for value in validities],
            "limit": limit,
        }
        if statement_types:
            clauses.append(sql.SQL("revision.statement_type = ANY(%(statement_types)s)"))
            params["statement_types"] = [str(value).upper() for value in statement_types]
        if scope:
            clauses.append(sql.SQL("revision.scope @> %(scope)s"))
            params["scope"] = Jsonb(dict(scope))
        query = self._revision_select(
            where=sql.SQL(" AND ").join(clauses),
            order=sql.SQL("revision.created_at DESC, revision.statement_id ASC"),
            limit=sql.SQL("LIMIT %(limit)s"),
        )
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [LedgerStatementRevision.from_row(row) for row in rows]

    def lexical_search(
        self,
        query_text: str,
        *,
        limit: int = 20,
        validities: Sequence[RevisionValidity | str] = (
            RevisionValidity.ACTIVE,
            RevisionValidity.STALE,
        ),
        statement_types: Sequence[str] | None = None,
        scope: Mapping[str, Any] | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        permissions: Sequence[str] = (),
    ) -> list[CandidateHit]:
        if not query_text.strip():
            raise ValueError("query_text must not be empty")
        clauses = [
            sql.SQL("projection.project_id = %(project_id)s"),
            sql.SQL("projection.validity = ANY(%(validities)s)"),
            sql.SQL("revision.search_document @@ query.value"),
        ]
        params: dict[str, Any] = {
            "project_id": self.project_id,
            "validities": [enum_value(value).upper() for value in validities],
            "query": query_text,
            "limit": limit,
        }
        self._add_revision_hard_filters(
            clauses,
            params,
            statement_types=statement_types,
            scope=scope,
            created_after=created_after,
            created_before=created_before,
            permissions=permissions,
        )
        base = self._revision_select(
            where=sql.SQL(" AND ").join(clauses),
            order=sql.SQL(
                "ts_rank_cd(revision.search_document, query.value) DESC, "
                "revision.statement_id ASC"
            ),
            limit=sql.SQL("LIMIT %(limit)s"),
            extra_select=sql.SQL(
                ", ts_rank_cd(revision.search_document, query.value) AS lexical_rank"
            ),
            prefix=sql.SQL(
                "WITH query AS (SELECT websearch_to_tsquery('simple', %(query)s) AS value)"
            ),
            extra_from=sql.SQL("CROSS JOIN query"),
        )
        with self.connect() as conn:
            rows = conn.execute(base, params).fetchall()
        return [
            CandidateHit(
                revision=LedgerStatementRevision.from_row(row),
                sources=("LEXICAL",),
                lexical_rank=float(row["lexical_rank"]),
            )
            for row in rows
        ]

    def semantic_search(
        self,
        query_embedding: Sequence[float],
        *,
        profile_id: str,
        limit: int = 20,
        validities: Sequence[RevisionValidity | str] = (
            RevisionValidity.ACTIVE,
            RevisionValidity.STALE,
        ),
        statement_types: Sequence[str] | None = None,
        scope: Mapping[str, Any] | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        permissions: Sequence[str] = (),
    ) -> list[CandidateHit]:
        vector = _vector_literal(query_embedding, self.embedding_dimensions)
        clauses = [
            sql.SQL("projection.project_id = %(project_id)s"),
            sql.SQL("projection.validity = ANY(%(validities)s)"),
            sql.SQL("embedding.profile_id = %(profile_id)s"),
        ]
        params: dict[str, Any] = {
            "project_id": self.project_id,
            "validities": [enum_value(value).upper() for value in validities],
            "profile_id": profile_id,
            "embedding": vector,
            "limit": limit,
        }
        self._add_revision_hard_filters(
            clauses,
            params,
            statement_types=statement_types,
            scope=scope,
            created_after=created_after,
            created_before=created_before,
            permissions=permissions,
        )
        query = self._revision_select(
            where=sql.SQL(" AND ").join(clauses),
            order=sql.SQL(
                "embedding.embedding <=> %(embedding)s::vector ASC, "
                "revision.statement_id ASC"
            ),
            limit=sql.SQL("LIMIT %(limit)s"),
            extra_select=sql.SQL(
                ", embedding.embedding <=> %(embedding)s::vector AS semantic_distance"
            ),
            extra_from=sql.SQL(
                "JOIN {embedding} embedding "
                "ON embedding.project_id = revision.project_id "
                "AND embedding.statement_id = revision.statement_id "
                "AND embedding.revision = revision.revision"
            ).format(embedding=self._table("statement_embedding")),
        )
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            CandidateHit(
                revision=LedgerStatementRevision.from_row(row),
                sources=("SEMANTIC",),
                semantic_distance=float(row["semantic_distance"]),
            )
            for row in rows
        ]

    def get_embedding_input(
        self,
        *,
        statement_id: str,
        revision: int,
        profile_id: str,
    ) -> str:
        with self.connect() as conn:
            authority_revision = LedgerStatementRevision.from_row(
                self._fetch_revision(conn, statement_id, revision)
            )
            profile = conn.execute(
                sql.SQL(
                    """
                    SELECT dimensions, input_template_version
                    FROM {table}
                    WHERE project_id = %s AND profile_id = %s
                    """
                ).format(table=self._table("embedding_profile")),
                (self.project_id, profile_id),
            ).fetchone()
        if profile is None:
            raise KeyError(f"embedding profile not found: {profile_id}")
        if int(profile["dimensions"]) != self.embedding_dimensions:
            raise ValueError("embedding profile dimension mismatch")
        return render_statement_embedding_input(
            authority_revision,
            template_version=str(profile["input_template_version"]),
        )

    def store_embedding(
        self,
        *,
        statement_id: str,
        revision: int,
        profile_id: str,
        embedding: Sequence[float],
        embedded_text_sha256: str,
    ) -> None:
        if len(embedded_text_sha256) != 64 or any(
            value not in "0123456789abcdef" for value in embedded_text_sha256
        ):
            raise ValueError("embedded_text_sha256 is invalid")
        vector = _vector_literal(embedding, self.embedding_dimensions)
        with self.connect() as conn:
            with conn.transaction():
                revision_row = self._fetch_revision(conn, statement_id, revision)
                authority_revision = LedgerStatementRevision.from_row(revision_row)
                profile = conn.execute(
                    sql.SQL(
                        """
                        SELECT dimensions, input_template_version
                        FROM {table}
                        WHERE project_id = %s AND profile_id = %s
                        """
                    ).format(table=self._table("embedding_profile")),
                    (self.project_id, profile_id),
                ).fetchone()
                if profile is None:
                    raise KeyError(f"embedding profile not found: {profile_id}")
                if int(profile["dimensions"]) != self.embedding_dimensions:
                    raise ValueError("embedding profile dimension mismatch")
                expected_text = render_statement_embedding_input(
                    authority_revision,
                    template_version=str(profile["input_template_version"]),
                )
                expected_text_sha256 = hashlib.sha256(
                    expected_text.encode("utf-8")
                ).hexdigest()
                if embedded_text_sha256 != expected_text_sha256:
                    raise ValueError(
                        "embedded text hash differs from the authority input template"
                    )
                conn.execute(
                    sql.SQL(
                        """
                        INSERT INTO {table} (
                          project_id, statement_id, revision, profile_id,
                          embedding, embedded_text_sha256
                        )
                        VALUES (%s, %s, %s, %s, %s::vector, %s)
                        ON CONFLICT (project_id, statement_id, revision, profile_id)
                        DO UPDATE SET
                          embedding = EXCLUDED.embedding,
                          embedded_text_sha256 = EXCLUDED.embedded_text_sha256,
                          created_at = now()
                        """
                    ).format(table=self._table("statement_embedding")),
                    (
                        self.project_id,
                        statement_id,
                        revision,
                        profile_id,
                        vector,
                        embedded_text_sha256,
                    ),
                )
                self._insert_event(
                    conn,
                    aggregate_kind="INDEX",
                    aggregate_id=(
                        f"{statement_id}@{revision}:{profile_id}"
                    ),
                    event_type="EMBEDDING_REBUILT",
                    reason="statement embedding stored or replaced",
                    created_by="reasoning_ledger",
                    payload={
                        "embedded_text_sha256": embedded_text_sha256,
                        "profile_id": profile_id,
                    },
                )

    def hybrid_search(
        self,
        query_text: str,
        *,
        query_embedding: Sequence[float] | None = None,
        profile_id: str | None = None,
        statement_types: Sequence[str] | None = None,
        scope: Mapping[str, Any] | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        permissions: Sequence[str] = (),
        limit: int = 12,
    ) -> list[CandidateHit]:
        lexical = self.lexical_search(
            query_text,
            limit=max(limit * 2, limit),
            statement_types=statement_types,
            scope=scope,
            created_after=created_after,
            created_before=created_before,
            permissions=permissions,
        )
        semantic: list[CandidateHit] = []
        if query_embedding is not None:
            if not profile_id:
                raise ValueError("semantic candidates require profile_id")
            semantic = self.semantic_search(
                query_embedding,
                profile_id=profile_id,
                limit=max(limit * 2, limit),
                statement_types=statement_types,
                scope=scope,
                created_after=created_after,
                created_before=created_before,
                permissions=permissions,
            )
        merged: dict[tuple[str, int], dict[str, Any]] = {}
        for rank, hit in enumerate(lexical, start=1):
            key = (hit.revision.statement_id, hit.revision.revision)
            merged[key] = {
                "revision": hit.revision,
                "sources": {"LEXICAL"},
                "lexical_rank": hit.lexical_rank,
                "semantic_distance": None,
                "rrf": 1.0 / (60 + rank),
            }
        for rank, hit in enumerate(semantic, start=1):
            key = (hit.revision.statement_id, hit.revision.revision)
            entry = merged.setdefault(
                key,
                {
                    "revision": hit.revision,
                    "sources": set(),
                    "lexical_rank": None,
                    "semantic_distance": None,
                    "rrf": 0.0,
                },
            )
            entry["sources"].add("SEMANTIC")
            entry["semantic_distance"] = hit.semantic_distance
            entry["rrf"] += 1.0 / (60 + rank)
        ordered = sorted(
            merged.values(),
            key=lambda value: (
                -float(value["rrf"]),
                value["revision"].statement_id,
                value["revision"].revision,
            ),
        )[:limit]
        return [
            CandidateHit(
                revision=value["revision"],
                sources=tuple(sorted(value["sources"])),
                lexical_rank=value["lexical_rank"],
                semantic_distance=value["semantic_distance"],
            )
            for value in ordered
        ]

    def retrieve_context_pack(
        self,
        *,
        task_id: str,
        agent_role: str,
        query: str,
        query_embedding: Sequence[float] | None = None,
        embedding_profile_id: str | None = None,
        statement_types: Sequence[str] | None = None,
        scope: Mapping[str, Any] | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        permissions: Sequence[str] = (),
        limit: int = 12,
        include_causes: bool = True,
        max_causal_depth: int = 8,
    ) -> AuthorityContextPack:
        candidates = self.hybrid_search(
            query,
            query_embedding=query_embedding,
            profile_id=embedding_profile_id,
            statement_types=statement_types,
            scope=scope,
            created_after=created_after,
            created_before=created_before,
            permissions=permissions,
            limit=limit,
        )
        causal: dict[tuple[str, int], LedgerStatementRevision] = {}
        relations: dict[str, LedgerRelation] = {}
        if include_causes:
            for hit in candidates:
                revisions, edges = self.trace_upstream(
                    hit.revision.statement_id,
                    hit.revision.revision,
                    max_depth=max_causal_depth,
                )
                for revision in revisions:
                    causal[(revision.statement_id, revision.revision)] = revision
                for edge in edges:
                    relations[edge.relation_id] = edge
        selected_keys = {
            (value.revision.statement_id, value.revision.revision)
            for value in candidates
        } | set(causal)
        conflicts = self._conflicts_for(selected_keys)
        conflict_endpoint_keys = {
            key
            for relation in conflicts
            for key in (
                (relation.from_statement_id, relation.from_revision),
                (relation.to_statement_id, relation.to_revision),
            )
        }
        missing_conflict_keys = sorted(conflict_endpoint_keys - selected_keys)
        if missing_conflict_keys:
            with self.connect() as conn:
                for conflict_revision in self._fetch_revisions_by_keys(
                    conn, missing_conflict_keys
                ):
                    causal[
                        (conflict_revision.statement_id, conflict_revision.revision)
                    ] = conflict_revision
            selected_keys.update(missing_conflict_keys)
        evidence_ids = {
            evidence_id
            for value in candidates
            for evidence_id in value.revision.evidence_ids
        }
        evidence_ids.update(
            evidence_id
            for value in causal.values()
            for evidence_id in value.evidence_ids
        )
        evidence_ids.update(
            evidence_id
            for relation in (*relations.values(), *conflicts)
            for evidence_id in relation.evidence_ids
        )
        evidence = self._load_evidence(sorted(evidence_ids))
        self._assert_context_permissions(
            revisions=(
                *(value.revision for value in candidates),
                *causal.values(),
            ),
            relations=(*relations.values(), *conflicts),
            evidence=evidence,
            permissions=permissions,
        )
        warnings: list[str] = []
        for revision in (
            [value.revision for value in candidates] + list(causal.values())
        ):
            if revision.current_validity != RevisionValidity.ACTIVE.value:
                warnings.append(
                    f"{revision.statement_id}@{revision.revision} validity is "
                    f"{revision.current_validity}"
                )
            if revision.statement_type == "HYPOTHESIS":
                warnings.append(
                    f"{revision.statement_id}@{revision.revision} is an unverified hypothesis"
                )
        if conflicts:
            warnings.append("retrieved causal closure contains refuting or preventing relations")
        trace = {
            "hard_filters": {
                "project_id": self.project_id,
                "scope": dict(scope or {}),
                "validities": ["ACTIVE", "STALE"],
                "statement_types": list(statement_types or []),
                "created_after": created_after,
                "created_before": created_before,
                "permissions": sorted(set(permissions)),
            },
            "lexical_candidates": [
                self._revision_key(value.revision.statement_id, value.revision.revision)
                for value in candidates
                if "LEXICAL" in value.sources
            ],
            "semantic_candidates": [
                self._revision_key(value.revision.statement_id, value.revision.revision)
                for value in candidates
                if "SEMANTIC" in value.sources
            ],
            "embedding_profile_id": embedding_profile_id,
            "causal_relations": list(CAUSAL_RELATIONS),
            "max_causal_depth": max_causal_depth,
            "limit": limit,
        }
        return AuthorityContextPack(
            project_id=self.project_id,
            task_id=task_id,
            agent_role=agent_role,
            query=query,
            candidates=candidates,
            causal_revisions=tuple(causal.values()),
            relations=tuple(relations.values()),
            conflicts=tuple(conflicts),
            warnings=tuple(dict.fromkeys(warnings)),
            evidence_descriptors=tuple(evidence),
            retrieval_trace=trace,
        )

    def trace_upstream(
        self,
        statement_id: str,
        revision: int,
        *,
        max_depth: int = 8,
        relation_types: Sequence[RelationType | str] = CAUSAL_RELATIONS,
    ) -> tuple[list[LedgerStatementRevision], list[LedgerRelation]]:
        if max_depth < 1:
            return [], []
        types = [enum_value(value).upper() for value in relation_types]
        query = sql.SQL(
            """
            WITH RECURSIVE walk(statement_id, revision, depth, path) AS (
              SELECT %s::text, %s::integer, 0,
                     ARRAY[%s::text || '@' || %s::text]
              UNION ALL
              SELECT relation.from_statement_id, relation.from_revision,
                     walk.depth + 1,
                     walk.path || (relation.from_statement_id || '@' || relation.from_revision::text)
              FROM walk
              JOIN {relation} relation
                ON relation.project_id = %s
               AND relation.to_statement_id = walk.statement_id
               AND relation.to_revision = walk.revision
               AND relation.relation_type = ANY(%s)
              WHERE walk.depth < %s
                AND NOT (
                  relation.from_statement_id || '@' || relation.from_revision::text
                  = ANY(walk.path)
                )
            )
            SELECT DISTINCT statement_id, revision
            FROM walk
            WHERE depth > 0
            ORDER BY statement_id, revision
            """
        ).format(relation=self._table("relation"))
        with self.connect() as conn:
            keys = conn.execute(
                query,
                (
                    statement_id,
                    revision,
                    statement_id,
                    revision,
                    self.project_id,
                    types,
                    max_depth,
                ),
            ).fetchall()
            revisions = self._fetch_revisions_by_keys(
                conn,
                [(str(row["statement_id"]), int(row["revision"])) for row in keys],
            )
            relations = self._fetch_relations_for_closure(
                conn,
                {(statement_id, revision)}
                | {(value.statement_id, value.revision) for value in revisions},
                types,
            )
        return revisions, relations

    def export_snapshot(
        self, output_path: str | Path | None = None
    ) -> dict[str, Any]:
        with self.connect() as conn:
            with conn.transaction():
                conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                statements = conn.execute(
                    sql.SQL(
                        "SELECT * FROM {table} WHERE project_id = %s ORDER BY statement_id"
                    ).format(table=self._table("statement")),
                    (self.project_id,),
                ).fetchall()
                revision_rows = conn.execute(
                    sql.SQL(
                        """
                        SELECT revision.*,
                               CASE
                                 WHEN projection.revision IS NOT NULL
                                   THEN projection.validity
                                 WHEN EXISTS (
                                   SELECT 1 FROM {relation} superseding
                                   WHERE superseding.project_id = revision.project_id
                                     AND superseding.from_statement_id = revision.statement_id
                                     AND superseding.from_revision = revision.revision
                                     AND superseding.relation_type = 'SUPERSEDES'
                                 ) THEN 'SUPERSEDED'
                                 ELSE revision.validity
                               END AS current_validity,
                               COALESCE(evidence.evidence_ids, ARRAY[]::text[]) AS evidence_ids
                        FROM {revision} revision
                        LEFT JOIN {projection} projection
                          ON projection.project_id = revision.project_id
                         AND projection.statement_id = revision.statement_id
                         AND projection.revision = revision.revision
                        LEFT JOIN LATERAL (
                          SELECT array_agg(link.evidence_id ORDER BY link.ordinal) AS evidence_ids
                          FROM {revision_evidence} link
                          WHERE link.project_id = revision.project_id
                            AND link.statement_id = revision.statement_id
                            AND link.revision = revision.revision
                        ) evidence ON TRUE
                        WHERE revision.project_id = %s
                        ORDER BY revision.statement_id, revision.revision
                        """
                    ).format(
                        revision=self._table("statement_revision"),
                        projection=self._table("current_projection"),
                        relation=self._table("relation"),
                        revision_evidence=self._table("statement_revision_evidence"),
                    ),
                    (self.project_id,),
                ).fetchall()
                evidence_rows = conn.execute(
                    sql.SQL(
                        "SELECT * FROM {table} WHERE project_id = %s ORDER BY evidence_id"
                    ).format(table=self._table("evidence_descriptor")),
                    (self.project_id,),
                ).fetchall()
                relation_rows = self._fetch_all_relations(conn)
                event_rows = conn.execute(
                    sql.SQL(
                        "SELECT * FROM {table} WHERE project_id = %s ORDER BY event_id"
                    ).format(table=self._table("ledger_event")),
                    (self.project_id,),
                ).fetchall()
                projection_rows = conn.execute(
                    sql.SQL(
                        "SELECT * FROM {table} WHERE project_id = %s ORDER BY statement_id"
                    ).format(table=self._table("current_projection")),
                    (self.project_id,),
                ).fetchall()
                profile_rows = conn.execute(
                    sql.SQL(
                        """
                        SELECT project_id, profile_id, provider, model, model_version,
                               dimensions, normalization, input_template_version,
                               content_sha256, created_by, created_at
                        FROM {table}
                        WHERE project_id = %s
                        ORDER BY profile_id
                        """
                    ).format(table=self._table("embedding_profile")),
                    (self.project_id,),
                ).fetchall()
        snapshot: dict[str, Any] = {
            "schema": "aegis.reasoning_ledger.snapshot.v2",
            "project_id": self.project_id,
            "statements": [self._json_row(row) for row in statements],
            "revisions": [
                LedgerStatementRevision.from_row(row).to_dict()
                for row in revision_rows
            ],
            "evidence_descriptors": [
                LedgerEvidence.from_row(row).to_dict() for row in evidence_rows
            ],
            "relations": [row.to_dict() for row in relation_rows],
            "events": [
                LedgerAuthorityEvent.from_row(row).to_dict() for row in event_rows
            ],
            "current_projection": [self._json_row(row) for row in projection_rows],
            "embedding_profiles": [self._json_row(row) for row in profile_rows],
        }
        if output_path is not None:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(snapshot, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return snapshot

    def rebuild_index(self, *, created_by: str = "reasoning_ledger") -> int:
        """Rebuild exact index storage without enabling approximate search."""

        with self.connect() as conn:
            with conn.transaction():
                conn.execute(
                    sql.SQL("REINDEX TABLE {table}").format(
                        table=self._table("statement_embedding")
                    )
                )
                count = int(
                    conn.execute(
                        sql.SQL(
                            "SELECT count(*) AS count FROM {table} WHERE project_id = %s"
                        ).format(table=self._table("statement_embedding")),
                        (self.project_id,),
                    ).fetchone()["count"]
                )
                self._insert_event(
                    conn,
                    aggregate_kind="INDEX",
                    aggregate_id="statement_embedding",
                    event_type="EMBEDDING_REBUILT",
                    reason="exact embedding index storage rebuilt",
                    created_by=created_by,
                    payload={"indexed_revisions": count, "approximate": False},
                )
        return count

    def _add_revision_hard_filters(
        self,
        clauses: list[sql.Composable],
        params: dict[str, Any],
        *,
        statement_types: Sequence[str] | None,
        scope: Mapping[str, Any] | None,
        created_after: str | None,
        created_before: str | None,
        permissions: Sequence[str],
    ) -> None:
        if statement_types:
            clauses.append(
                sql.SQL("revision.statement_type = ANY(%(statement_types)s)")
            )
            params["statement_types"] = [
                str(value).upper() for value in statement_types
            ]
        if scope:
            clauses.append(sql.SQL("revision.scope @> %(scope)s"))
            params["scope"] = Jsonb(dict(scope))
        if created_after is not None:
            if not created_after.endswith("Z"):
                raise ValueError("created_after must be UTC with a Z suffix")
            clauses.append(sql.SQL("revision.created_at >= %(created_after)s"))
            params["created_after"] = created_after
        if created_before is not None:
            if not created_before.endswith("Z"):
                raise ValueError("created_before must be UTC with a Z suffix")
            clauses.append(sql.SQL("revision.created_at <= %(created_before)s"))
            params["created_before"] = created_before
        normalized_permissions = sorted(set(str(value) for value in permissions))
        if any(not value.strip() for value in normalized_permissions):
            raise ValueError("permissions must not contain empty values")
        clauses.append(
            sql.SQL(
                """
                (
                  NOT revision.scope ? 'required_permissions'
                  OR NOT EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements_text(
                      revision.scope->'required_permissions'
                    ) AS required(permission)
                    WHERE NOT required.permission = ANY(%(permissions)s::text[])
                  )
                )
                """
            )
        )
        params["permissions"] = normalized_permissions

    def _assert_context_permissions(
        self,
        *,
        revisions: Sequence[LedgerStatementRevision],
        relations: Sequence[LedgerRelation],
        evidence: Sequence[LedgerEvidence],
        permissions: Sequence[str],
    ) -> None:
        granted = {str(value) for value in permissions}
        if any(not value.strip() for value in granted):
            raise ValueError("permissions must not contain empty values")

        scopes = (
            *(value.scope for value in revisions),
            *(value.applicable_conditions for value in relations),
            *(value.scope for value in evidence),
        )
        for scope in scopes:
            required = scope.get("required_permissions", [])
            if (
                not isinstance(required, list)
                or any(not isinstance(value, str) or not value.strip() for value in required)
                or len(required) != len(set(required))
            ):
                raise RuntimeError(
                    "reasoning authority contains an invalid permission boundary"
                )
            if any(value not in granted for value in required):
                raise PermissionError(
                    "reasoning context closure crosses an ungranted permission boundary"
                )

    def _insert_revision(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        revision: StatementRevision,
    ) -> None:
        conn.execute(
            sql.SQL(
                """
                INSERT INTO {table} (
                  project_id, statement_id, revision, statement_type, content,
                  structured_conditions, validity, scope, confidence,
                  content_sha256, created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
            ).format(table=self._table("statement_revision")),
            (
                self.project_id,
                revision.statement_id,
                revision.revision,
                enum_value(revision.statement_type).upper(),
                revision.content,
                Jsonb(dict(revision.structured_conditions)),
                enum_value(revision.validity).upper(),
                Jsonb(dict(revision.scope)),
                revision.confidence,
                revision.content_sha256,
                revision.created_by,
            ),
        )
        for ordinal, evidence_id in enumerate(revision.evidence_ids):
            conn.execute(
                sql.SQL(
                    """
                    INSERT INTO {table} (
                      project_id, statement_id, revision, evidence_id, ordinal
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """
                ).format(table=self._table("statement_revision_evidence")),
                (
                    self.project_id,
                    revision.statement_id,
                    revision.revision,
                    evidence_id,
                    ordinal,
                ),
            )

    def _insert_relation(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        relation: StatementRelation,
    ) -> Mapping[str, Any]:
        row = conn.execute(
            sql.SQL(
                """
                INSERT INTO {table} (
                  project_id, relation_id, from_statement_id, from_revision,
                  to_statement_id, to_revision, relation_type,
                  applicable_conditions, reason, content_sha256, created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """
            ).format(table=self._table("relation")),
            (
                self.project_id,
                relation.relation_id,
                relation.from_statement_id,
                relation.from_revision,
                relation.to_statement_id,
                relation.to_revision,
                enum_value(relation.relation_type).upper(),
                Jsonb(dict(relation.applicable_conditions)),
                relation.reason,
                relation.content_sha256,
                relation.created_by,
            ),
        ).fetchone()
        assert row is not None
        for ordinal, evidence_id in enumerate(relation.evidence_ids):
            conn.execute(
                sql.SQL(
                    """
                    INSERT INTO {table} (
                      project_id, relation_id, evidence_id, ordinal
                    )
                    VALUES (%s, %s, %s, %s)
                    """
                ).format(table=self._table("relation_evidence")),
                (self.project_id, relation.relation_id, evidence_id, ordinal),
            )
        return {**dict(row), "evidence_ids": list(relation.evidence_ids)}

    def _insert_event(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        *,
        aggregate_kind: str,
        aggregate_id: str,
        event_type: str,
        reason: str,
        created_by: str,
        payload: Mapping[str, Any],
    ) -> int:
        row = conn.execute(
            sql.SQL(
                """
                INSERT INTO {table} (
                  project_id, aggregate_kind, aggregate_id, event_type,
                  reason, payload, created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING event_id
                """
            ).format(table=self._table("ledger_event")),
            (
                self.project_id,
                aggregate_kind,
                aggregate_id,
                event_type,
                reason,
                Jsonb(dict(payload)),
                created_by,
            ),
        ).fetchone()
        assert row is not None
        return int(row["event_id"])

    def _fetch_current_revision(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        statement_id: str,
    ) -> Mapping[str, Any] | None:
        return conn.execute(
            self._revision_select(
                where=sql.SQL(
                    "projection.project_id = %s AND projection.statement_id = %s"
                ),
                order=sql.SQL("revision.revision DESC"),
                limit=sql.SQL("LIMIT 1"),
            ),
            (self.project_id, statement_id),
        ).fetchone()

    def _fetch_revision(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        statement_id: str,
        revision: int,
    ) -> Mapping[str, Any]:
        row = conn.execute(
            sql.SQL(
                """
                SELECT revision.*,
                       CASE
                         WHEN projection.revision IS NOT NULL
                           THEN projection.validity
                         WHEN EXISTS (
                           SELECT 1 FROM {relation} superseding
                           WHERE superseding.project_id = revision.project_id
                             AND superseding.from_statement_id = revision.statement_id
                             AND superseding.from_revision = revision.revision
                             AND superseding.relation_type = 'SUPERSEDES'
                         ) THEN 'SUPERSEDED'
                         ELSE revision.validity
                       END AS current_validity,
                       COALESCE(evidence.evidence_ids, ARRAY[]::text[]) AS evidence_ids
                FROM {revision} revision
                LEFT JOIN {projection} projection
                  ON projection.project_id = revision.project_id
                 AND projection.statement_id = revision.statement_id
                 AND projection.revision = revision.revision
                LEFT JOIN LATERAL (
                  SELECT array_agg(link.evidence_id ORDER BY link.ordinal) AS evidence_ids
                  FROM {revision_evidence} link
                  WHERE link.project_id = revision.project_id
                    AND link.statement_id = revision.statement_id
                    AND link.revision = revision.revision
                ) evidence ON TRUE
                WHERE revision.project_id = %s
                  AND revision.statement_id = %s
                  AND revision.revision = %s
                """
            ).format(
                revision=self._table("statement_revision"),
                projection=self._table("current_projection"),
                relation=self._table("relation"),
                revision_evidence=self._table("statement_revision_evidence"),
            ),
            (self.project_id, statement_id, revision),
        ).fetchone()
        if row is None:
            raise KeyError(f"revision not found: {statement_id}@{revision}")
        return row

    def _revision_select(
        self,
        *,
        where: sql.Composable,
        order: sql.Composable,
        limit: sql.Composable,
        extra_select: sql.Composable | None = None,
        prefix: sql.Composable | None = None,
        extra_from: sql.Composable | None = None,
    ) -> sql.Composed:
        return sql.SQL(
            """
            {prefix}
            SELECT revision.*,
                   projection.validity AS current_validity,
                   COALESCE(evidence.evidence_ids, ARRAY[]::text[]) AS evidence_ids
                   {extra_select}
            FROM {projection} projection
            JOIN {revision} revision
              ON revision.project_id = projection.project_id
             AND revision.statement_id = projection.statement_id
             AND revision.revision = projection.revision
            {extra_from}
            LEFT JOIN LATERAL (
              SELECT array_agg(link.evidence_id ORDER BY link.ordinal) AS evidence_ids
              FROM {revision_evidence} link
              WHERE link.project_id = revision.project_id
                AND link.statement_id = revision.statement_id
                AND link.revision = revision.revision
            ) evidence ON TRUE
            WHERE {where}
            ORDER BY {order}
            {limit}
            """
        ).format(
            prefix=prefix or sql.SQL(""),
            extra_select=extra_select or sql.SQL(""),
            projection=self._table("current_projection"),
            revision=self._table("statement_revision"),
            revision_evidence=self._table("statement_revision_evidence"),
            extra_from=extra_from or sql.SQL(""),
            where=where,
            order=order,
            limit=limit,
        )

    def _fetch_revisions_by_keys(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        keys: Sequence[tuple[str, int]],
    ) -> list[LedgerStatementRevision]:
        if not keys:
            return []
        statement_ids = [key[0] for key in keys]
        revisions = [key[1] for key in keys]
        rows = conn.execute(
            sql.SQL(
                """
                WITH wanted(statement_id, revision) AS (
                  SELECT * FROM unnest(%s::text[], %s::integer[])
                )
                SELECT revision.*,
                       CASE
                         WHEN projection.revision IS NOT NULL
                           THEN projection.validity
                         WHEN EXISTS (
                           SELECT 1 FROM {relation} superseding
                           WHERE superseding.project_id = revision.project_id
                             AND superseding.from_statement_id = revision.statement_id
                             AND superseding.from_revision = revision.revision
                             AND superseding.relation_type = 'SUPERSEDES'
                         ) THEN 'SUPERSEDED'
                         ELSE revision.validity
                       END AS current_validity,
                       COALESCE(evidence.evidence_ids, ARRAY[]::text[]) AS evidence_ids
                FROM wanted
                JOIN {revision} revision
                  ON revision.project_id = %s
                 AND revision.statement_id = wanted.statement_id
                 AND revision.revision = wanted.revision
                LEFT JOIN {projection} projection
                  ON projection.project_id = revision.project_id
                 AND projection.statement_id = revision.statement_id
                 AND projection.revision = revision.revision
                LEFT JOIN LATERAL (
                  SELECT array_agg(link.evidence_id ORDER BY link.ordinal) AS evidence_ids
                  FROM {revision_evidence} link
                  WHERE link.project_id = revision.project_id
                    AND link.statement_id = revision.statement_id
                    AND link.revision = revision.revision
                ) evidence ON TRUE
                ORDER BY revision.statement_id, revision.revision
                """
            ).format(
                relation=self._table("relation"),
                revision=self._table("statement_revision"),
                projection=self._table("current_projection"),
                revision_evidence=self._table("statement_revision_evidence"),
            ),
            (statement_ids, revisions, self.project_id),
        ).fetchall()
        if len(rows) != len(set(keys)):
            found = {
                (str(row["statement_id"]), int(row["revision"])) for row in rows
            }
            missing = sorted(set(keys) - found)
            raise KeyError(
                "missing revision(s): "
                + ", ".join(self._revision_key(*key) for key in missing)
            )
        return [LedgerStatementRevision.from_row(row) for row in rows]

    def _fetch_relations_for_closure(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        keys: set[tuple[str, int]],
        relation_types: Sequence[str],
    ) -> list[LedgerRelation]:
        if not keys:
            return []
        statement_ids = [key[0] for key in sorted(keys)]
        revisions = [key[1] for key in sorted(keys)]
        rows = conn.execute(
            self._relation_select(
                prefix=sql.SQL(
                    "WITH wanted(statement_id, revision) AS ("
                    "SELECT * FROM unnest(%s::text[], %s::integer[]))"
                ),
                where=sql.SQL(
                    "relation.project_id = %s "
                    "AND relation.relation_type = ANY(%s) "
                    "AND EXISTS (SELECT 1 FROM wanted "
                    "WHERE statement_id = relation.from_statement_id "
                    "AND revision = relation.from_revision) "
                    "AND EXISTS (SELECT 1 FROM wanted "
                    "WHERE statement_id = relation.to_statement_id "
                    "AND revision = relation.to_revision)"
                ),
            ),
            (statement_ids, revisions, self.project_id, list(relation_types)),
        ).fetchall()
        return [LedgerRelation.from_row(row) for row in rows]

    def _fetch_all_relations(
        self, conn: psycopg.Connection[dict[str, Any]]
    ) -> list[LedgerRelation]:
        rows = conn.execute(
            self._relation_select(
                prefix=sql.SQL(""),
                where=sql.SQL("relation.project_id = %s"),
            ),
            (self.project_id,),
        ).fetchall()
        return [LedgerRelation.from_row(row) for row in rows]

    def _conflicts_for(
        self, keys: set[tuple[str, int]]
    ) -> list[LedgerRelation]:
        if not keys:
            return []
        ordered = sorted(keys)
        statement_ids = [key[0] for key in ordered]
        revisions = [key[1] for key in ordered]
        with self.connect() as conn:
            rows = conn.execute(
                self._relation_select(
                    prefix=sql.SQL(
                        "WITH wanted(statement_id, revision) AS ("
                        "SELECT * FROM unnest(%s::text[], %s::integer[]))"
                    ),
                    where=sql.SQL(
                        "relation.project_id = %s "
                        "AND relation.relation_type = ANY(%s) "
                        "AND ("
                        "EXISTS (SELECT 1 FROM wanted "
                        "WHERE statement_id = relation.from_statement_id "
                        "AND revision = relation.from_revision) "
                        "OR EXISTS (SELECT 1 FROM wanted "
                        "WHERE statement_id = relation.to_statement_id "
                        "AND revision = relation.to_revision))"
                    ),
                ),
                (
                    statement_ids,
                    revisions,
                    self.project_id,
                    list(CONFLICT_RELATIONS),
                ),
            ).fetchall()
        return [LedgerRelation.from_row(row) for row in rows]

    def _relation_select(
        self,
        *,
        prefix: sql.Composable,
        where: sql.Composable,
    ) -> sql.Composed:
        return sql.SQL(
            """
            {prefix}
            SELECT relation.*,
                   COALESCE(evidence.evidence_ids, ARRAY[]::text[]) AS evidence_ids
            FROM {relation} relation
            LEFT JOIN LATERAL (
              SELECT array_agg(link.evidence_id ORDER BY link.ordinal) AS evidence_ids
              FROM {relation_evidence} link
              WHERE link.project_id = relation.project_id
                AND link.relation_id = relation.relation_id
            ) evidence ON TRUE
            WHERE {where}
            ORDER BY relation.relation_id
            """
        ).format(
            prefix=prefix,
            relation=self._table("relation"),
            relation_evidence=self._table("relation_evidence"),
            where=where,
        )

    def _load_evidence(self, evidence_ids: Sequence[str]) -> list[LedgerEvidence]:
        if not evidence_ids:
            return []
        with self.connect() as conn:
            rows = conn.execute(
                sql.SQL(
                    """
                    SELECT *
                    FROM {table}
                    WHERE project_id = %s AND evidence_id = ANY(%s)
                    ORDER BY evidence_id
                    """
                ).format(table=self._table("evidence_descriptor")),
                (self.project_id, list(evidence_ids)),
            ).fetchall()
        return [LedgerEvidence.from_row(row) for row in rows]

    def _assert_evidence_exists(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        evidence_ids: Sequence[str],
    ) -> None:
        if not evidence_ids:
            raise ValueError("authority content requires evidence descriptors")
        rows = conn.execute(
            sql.SQL(
                """
                SELECT evidence_id
                FROM {table}
                WHERE project_id = %s AND evidence_id = ANY(%s)
                """
            ).format(table=self._table("evidence_descriptor")),
            (self.project_id, list(evidence_ids)),
        ).fetchall()
        found = {str(row["evidence_id"]) for row in rows}
        missing = sorted(set(evidence_ids) - found)
        if missing:
            raise KeyError("missing evidence descriptor(s): " + ", ".join(missing))

    def _assert_revisions_exist(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        keys: Sequence[tuple[str, int]],
    ) -> None:
        missing: list[str] = []
        for statement_id, revision in keys:
            row = conn.execute(
                sql.SQL(
                    """
                    SELECT 1
                    FROM {table}
                    WHERE project_id = %s AND statement_id = %s AND revision = %s
                    """
                ).format(table=self._table("statement_revision")),
                (self.project_id, statement_id, revision),
            ).fetchone()
            if row is None:
                missing.append(self._revision_key(statement_id, revision))
        if missing:
            raise KeyError("missing revision(s): " + ", ".join(missing))

    def _would_create_cycle(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        relation: StatementRelation,
    ) -> bool:
        row = conn.execute(
            sql.SQL(
                """
                WITH RECURSIVE walk(statement_id, revision) AS (
                  SELECT %s::text, %s::integer
                  UNION
                  SELECT edge.to_statement_id, edge.to_revision
                  FROM walk
                  JOIN {table} edge
                    ON edge.project_id = %s
                   AND edge.from_statement_id = walk.statement_id
                   AND edge.from_revision = walk.revision
                   AND edge.relation_type = ANY(%s)
                )
                SELECT EXISTS(
                  SELECT 1 FROM walk
                  WHERE statement_id = %s AND revision = %s
                ) AS cycle
                """
            ).format(table=self._table("relation")),
            (
                relation.to_statement_id,
                relation.to_revision,
                self.project_id,
                list(ACYCLIC_RELATIONS),
                relation.from_statement_id,
                relation.from_revision,
            ),
        ).fetchone()
        assert row is not None
        return bool(row["cycle"])

    def _lock_project_graph(
        self, conn: psycopg.Connection[dict[str, Any]]
    ) -> None:
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (self.project_id,),
        )

    def _run_serializable(
        self,
        operation: Callable[[psycopg.Connection[dict[str, Any]]], T],
    ) -> T:
        last_error: psycopg.Error | None = None
        for attempt in range(self.serialization_retries):
            try:
                with self.connect() as conn:
                    with conn.transaction():
                        conn.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                        return operation(conn)
            except psycopg.Error as error:
                if (
                    error.sqlstate not in SERIALIZATION_FAILURE_SQLSTATES
                    or attempt + 1 >= self.serialization_retries
                ):
                    raise
                last_error = error
        assert last_error is not None
        raise last_error

    @staticmethod
    def _revision_key(statement_id: str, revision: int) -> str:
        return f"{statement_id}@{revision}"

    @staticmethod
    def _version_tuple(value: str) -> tuple[int, ...]:
        try:
            return tuple(int(part) for part in value.split("."))
        except ValueError as error:
            raise RuntimeError(f"invalid database extension version: {value}") from error

    @staticmethod
    def _json_row(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            str(key): json_ready(value)
            for key, value in row.items()
        }

    def _table(self, table_name: str) -> sql.Composed:
        return sql.SQL("{}.{}").format(
            sql.Identifier(self.schema),
            sql.Identifier(table_name),
        )
