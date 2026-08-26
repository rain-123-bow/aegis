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
from path_security import PathSecurityError, read_regular_file

from .models import (
    AuthorityContextPack,
    CandidateHit,
    EmbeddingProfile,
    EvidenceDescriptor,
    LedgerAuthorityEvent,
    LedgerEvidence,
    LedgerRelation,
    LedgerStatementRevision,
    QueryEmbeddingReceipt,
    RelationType,
    RevisionValidity,
    StatementRelation,
    StatementRevision,
    SUPPORTED_EMBEDDING_INPUT_TEMPLATE_VERSION,
    canonical_embedding_sha256,
    enum_value,
    json_ready,
    render_statement_embedding_input,
    validate_embedding,
)
from .embedding import resolve_persistent_embedding
from .project import (
    MINIMUM_SUPPORTED_PGVECTOR_VERSION,
    MINIMUM_SUPPORTED_POSTGRESQL_MAJOR,
    _parse_version,
)
from .schema import (
    AUTHORITY_TABLE_COLUMNS,
    PGVECTOR_SCHEMA,
    REQUIRED_INDEX_NAMES,
    REQUIRED_TRIGGER_NAMES,
    V2_AUTHORITY_TABLE_COLUMNS,
    V2_REQUIRED_TRIGGER_NAMES,
    authority_schema_signature,
    build_forbidden_authority_key_function_sql,
    build_init_sql,
    build_v2_projection_validation_function_sql,
    build_v2_reference_sql,
    validate_identifier,
)


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
DEVELOPMENT_HASH_PROFILE_PROVIDER = "aegis-development"
DEVELOPMENT_HASH_PROFILE_MODEL = "hashed-text-v1"


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
        expected_project_anchor_sha256: str | None = None,
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
        if expected_project_anchor_sha256 is not None and (
            not isinstance(expected_project_anchor_sha256, str)
            or len(expected_project_anchor_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in expected_project_anchor_sha256
            )
        ):
            raise ValueError("expected_project_anchor_sha256 is invalid")
        self.expected_project_anchor_sha256 = expected_project_anchor_sha256

    def _connect_unbound(self) -> psycopg.Connection[dict[str, Any]]:
        conn = psycopg.connect(self.dsn, row_factory=dict_row)
        conn.execute("SET search_path TO pg_catalog")
        return conn

    def connect(self) -> psycopg.Connection[dict[str, Any]]:
        conn = psycopg.connect(self.dsn, row_factory=dict_row)
        try:
            conn.execute("SET search_path TO pg_catalog")
            self._probe_server_contract(conn, create_extension=False)
            self._validate_schema_contract(conn)
            self._validate_project_anchor(conn, require_expected=True)
            conn.commit()
        except BaseException:
            conn.close()
            raise
        return conn

    def migrate(self) -> dict[str, Any]:
        anchor: dict[str, Any] | None = None
        with self._connect_unbound() as conn:
            server_contract = self._probe_server_contract(
                conn,
                create_extension=True,
                tolerate_legacy_namespace=True,
            )
            existing_tables = self._schema_table_columns(conn)
            if existing_tables:
                version = self._schema_metadata_version(conn)
                if version == 2:
                    self._validate_v2_upgrade_source(
                        conn,
                        existing_tables,
                        vector_schema=str(server_contract["pgvector_schema"]),
                    )
                    if server_contract["pgvector_schema"] != PGVECTOR_SCHEMA:
                        self._probe_server_contract(
                            conn,
                            create_extension=False,
                            relocate_legacy_namespace=True,
                        )
                    self._migrate_v2_to_v3(conn)
                elif version == 3:
                    if server_contract["pgvector_schema"] != PGVECTOR_SCHEMA:
                        raise RuntimeError(
                            "version 3 reasoning-ledger pgvector namespace differs "
                            "from the authority contract"
                        )
                    self._validate_schema_contract(
                        conn,
                        require_catalog_signature=False,
                    )
                else:
                    raise RuntimeError(
                        "unsupported reasoning-ledger database schema version: "
                        + str(version)
                    )
            elif server_contract["pgvector_schema"] != PGVECTOR_SCHEMA:
                raise RuntimeError(
                    "refusing to relocate a database-wide pgvector extension "
                    "for a new reasoning-ledger schema"
                )
            conn.execute(
                build_init_sql(
                    schema=self.schema,
                    embedding_dimensions=self.embedding_dimensions,
                )
            )
            anchor = self._ensure_project_anchor(conn)
            self._stamp_schema_catalog_signature(conn)
            self._validate_schema_contract(conn)
        assert anchor is not None
        self.expected_project_anchor_sha256 = str(anchor["anchor_sha256"])
        return anchor

    def probe_contract(self, *, require_schema: bool = True) -> dict[str, Any]:
        with self.connect() as conn:
            result = self._probe_server_contract(conn, create_extension=False)
            if require_schema:
                catalog_signature = self._validate_schema_contract(conn)
                project_anchor = self._validate_project_anchor(
                    conn, require_expected=True
                )
                result.update(
                    {
                        "schema": self.schema,
                        "schema_version": 3,
                        "embedding_dimensions": self.embedding_dimensions,
                        "schema_contract_signature": authority_schema_signature(
                            schema=self.schema,
                            embedding_dimensions=self.embedding_dimensions,
                        ),
                        "catalog_signature": catalog_signature,
                        "project_anchor": project_anchor,
                    }
                )
            result["status"] = True
            return result

    def register_evidence(
        self,
        descriptor: EvidenceDescriptor,
        *,
        project_root: str | Path,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> LedgerEvidence:
        root = Path(project_root).resolve()
        evidence_path = root / descriptor.path
        try:
            content, _identity = read_regular_file(
                evidence_path,
                allowed_root=root,
                label=f"reasoning evidence {descriptor.evidence_id}",
                max_bytes=max_bytes,
            )
        except PathSecurityError as error:
            raise ValueError(str(error)) from error
        digest = hashlib.sha256(content).hexdigest()
        if len(content) != descriptor.size or digest != descriptor.sha256:
            raise ValueError(
                "reasoning evidence bytes differ from the authority descriptor"
            )
        return self._register_evidence_descriptor(descriptor)

    def _register_evidence_descriptor(
        self, descriptor: EvidenceDescriptor
    ) -> LedgerEvidence:
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

    def verify_evidence_files(
        self,
        *,
        project_root: str | Path,
        max_bytes_per_file: int = 64 * 1024 * 1024,
    ) -> dict[str, Any]:
        snapshot = self.export_snapshot()
        return self.verify_snapshot_evidence_files(
            snapshot["evidence_descriptors"],
            project_root=project_root,
            max_bytes_per_file=max_bytes_per_file,
        )

    def verify_snapshot_evidence_files(
        self,
        evidence_descriptors: Sequence[Mapping[str, Any]],
        *,
        project_root: str | Path,
        max_bytes_per_file: int = 64 * 1024 * 1024,
    ) -> dict[str, Any]:
        root = Path(project_root).resolve()
        verified: list[dict[str, Any]] = []
        for row in evidence_descriptors:
            descriptor = LedgerEvidence.from_row(row)
            if descriptor.project_id != self.project_id:
                raise ValueError(
                    "reasoning evidence snapshot contains another project"
                )
            try:
                content, _identity = read_regular_file(
                    root / descriptor.path,
                    allowed_root=root,
                    label=f"reasoning evidence {descriptor.evidence_id}",
                    max_bytes=max_bytes_per_file,
                )
            except PathSecurityError as error:
                raise ValueError(str(error)) from error
            digest = hashlib.sha256(content).hexdigest()
            if len(content) != descriptor.size or digest != descriptor.sha256:
                raise ValueError(
                    "reasoning evidence bytes differ from descriptor: "
                    + descriptor.evidence_id
                )
            verified.append(
                {
                    "evidence_id": descriptor.evidence_id,
                    "path": descriptor.path,
                    "size": len(content),
                    "sha256": digest,
                }
            )
        canonical = json.dumps(
            verified,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return {
            "status": True,
            "project_id": self.project_id,
            "verified_evidence": len(verified),
            "evidence_manifest_sha256": hashlib.sha256(canonical).hexdigest(),
        }

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
        if enum_value(relation.relation_type).upper() == RelationType.SUPERSEDES.value:
            raise ValueError(
                "SUPERSEDES relations can only be created by supersede_statement"
            )

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
        query_embedding: QueryEmbeddingReceipt,
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
    ) -> list[CandidateHit]:
        if not isinstance(query_embedding, QueryEmbeddingReceipt):
            raise TypeError("semantic search requires a query embedding receipt")
        self.assert_embedding_source_compatible(
            profile_id=query_embedding.profile_id,
            embedding_source=query_embedding.source,
        )
        vector = _vector_literal(
            query_embedding.embedding,
            self.embedding_dimensions,
        )
        clauses = [
            sql.SQL("projection.project_id = %(project_id)s"),
            sql.SQL("projection.validity = ANY(%(validities)s)"),
            sql.SQL("embedding.profile_id = %(profile_id)s"),
        ]
        params: dict[str, Any] = {
            "project_id": self.project_id,
            "validities": [enum_value(value).upper() for value in validities],
            "profile_id": query_embedding.profile_id,
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
        )
        query = self._revision_select(
            where=sql.SQL(" AND ").join(clauses),
            order=sql.SQL(
                f"embedding.embedding <=> %(embedding)s::{PGVECTOR_SCHEMA}.vector ASC, "
                "revision.statement_id ASC"
            ),
            limit=sql.SQL("LIMIT %(limit)s"),
            extra_select=sql.SQL(
                f", embedding.embedding <=> %(embedding)s::{PGVECTOR_SCHEMA}.vector AS semantic_distance"
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

    def generate_and_store_embedding(
        self,
        *,
        statement_id: str,
        revision: int,
        profile_id: str,
        embedded_text: str,
        embedding_command: str | None = None,
        allow_hash_embedding: bool = False,
        command_timeout_seconds: int = 60,
    ) -> str:
        embedding, source, generator_identity = resolve_persistent_embedding(
            text=embedded_text,
            dimensions=self.embedding_dimensions,
            embedding_command=embedding_command,
            allow_hash_embedding=allow_hash_embedding,
            command_timeout_seconds=command_timeout_seconds,
        )
        self._store_embedding(
            statement_id=statement_id,
            revision=revision,
            profile_id=profile_id,
            embedding=embedding,
            embedded_text_sha256=hashlib.sha256(
                embedded_text.encode("utf-8")
            ).hexdigest(),
            generator_identity=generator_identity,
        )
        return source

    def _store_embedding(
        self,
        *,
        statement_id: str,
        revision: int,
        profile_id: str,
        embedding: Sequence[float],
        embedded_text_sha256: str,
        generator_identity: Mapping[str, Any],
    ) -> None:
        if len(embedded_text_sha256) != 64 or any(
            value not in "0123456789abcdef" for value in embedded_text_sha256
        ):
            raise ValueError("embedded_text_sha256 is invalid")
        values = validate_embedding(
            embedding,
            dimensions=self.embedding_dimensions,
        )
        assert values is not None
        vector = _vector_literal(values, self.embedding_dimensions)
        if not isinstance(generator_identity, Mapping) or not generator_identity:
            raise ValueError("embedding generator identity must be a non-empty mapping")
        generator = json_ready(dict(generator_identity))
        embedding_sha256 = canonical_embedding_sha256(
            values,
            dimensions=self.embedding_dimensions,
        )
        with self.connect() as conn:
            with conn.transaction():
                revision_row = self._fetch_revision(conn, statement_id, revision)
                authority_revision = LedgerStatementRevision.from_row(revision_row)
                profile = conn.execute(
                    sql.SQL(
                        """
                        SELECT dimensions, input_template_version, content_sha256,
                               provider, model, model_version
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
                development_profile = (
                    profile["provider"] == DEVELOPMENT_HASH_PROFILE_PROVIDER
                    and profile["model"] == DEVELOPMENT_HASH_PROFILE_MODEL
                )
                hash_generator = (
                    generator.get("kind") == "aegis-development-hash-embedding"
                )
                if development_profile != hash_generator:
                    raise ValueError(
                        "the development hash profile and hash generator must be "
                        "used together and cannot share another vector space"
                    )
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
                generation_receipt = {
                    "schema": "aegis.embedding_generation_receipt.v1",
                    "project_id": self.project_id,
                    "statement_id": statement_id,
                    "revision": revision,
                    "profile_id": profile_id,
                    "profile_content_sha256": str(profile["content_sha256"]),
                    "provider": str(profile["provider"]),
                    "model": str(profile["model"]),
                    "model_version": str(profile["model_version"]),
                    "embedded_text_sha256": embedded_text_sha256,
                    "embedding_sha256": embedding_sha256,
                    "embedding_encoding": "ieee754-binary32-big-endian-zero-normalized-v1",
                    "generator_identity": generator,
                }
                generation_receipt_sha256 = hashlib.sha256(
                    json.dumps(
                        generation_receipt,
                        ensure_ascii=False,
                        allow_nan=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
                conn.execute(
                    sql.SQL(
                        """
                        INSERT INTO {table} (
                          project_id, statement_id, revision, profile_id,
                          embedding, embedded_text_sha256, embedding_sha256,
                          generator_identity, generation_receipt,
                          generation_receipt_sha256
                        )
                        VALUES (%s, %s, %s, %s, %s::public.vector, %s, %s, %s, %s, %s)
                        ON CONFLICT (project_id, statement_id, revision, profile_id)
                        DO UPDATE SET
                          embedding = EXCLUDED.embedding,
                          embedded_text_sha256 = EXCLUDED.embedded_text_sha256,
                          embedding_sha256 = EXCLUDED.embedding_sha256,
                          generator_identity = EXCLUDED.generator_identity,
                          generation_receipt = EXCLUDED.generation_receipt,
                          generation_receipt_sha256 = EXCLUDED.generation_receipt_sha256,
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
                        embedding_sha256,
                        Jsonb(generator),
                        Jsonb(generation_receipt),
                        generation_receipt_sha256,
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
                        "embedding_sha256": embedding_sha256,
                        "generation_receipt_sha256": generation_receipt_sha256,
                    },
                )

    def assert_embedding_source_compatible(
        self, *, profile_id: str, embedding_source: str
    ) -> None:
        with self.connect() as conn:
            profile = conn.execute(
                sql.SQL(
                    "SELECT provider, model FROM {table} "
                    "WHERE project_id = %s AND profile_id = %s"
                ).format(table=self._table("embedding_profile")),
                (self.project_id, profile_id),
            ).fetchone()
        if profile is None:
            raise KeyError(f"embedding profile not found: {profile_id}")
        development_profile = (
            profile["provider"] == DEVELOPMENT_HASH_PROFILE_PROVIDER
            and profile["model"] == DEVELOPMENT_HASH_PROFILE_MODEL
        )
        if development_profile != (embedding_source == "hash-fallback"):
            raise ValueError(
                "the development hash profile and hash query source must be used "
                "together and cannot share another vector space"
            )
    def hybrid_search(
        self,
        query_text: str,
        *,
        query_embedding: QueryEmbeddingReceipt | None = None,
        statement_types: Sequence[str] | None = None,
        scope: Mapping[str, Any] | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        limit: int = 12,
    ) -> list[CandidateHit]:
        lexical = self.lexical_search(
            query_text,
            limit=max(limit * 2, limit),
            statement_types=statement_types,
            scope=scope,
            created_after=created_after,
            created_before=created_before,
        )
        semantic: list[CandidateHit] = []
        if query_embedding is not None:
            semantic = self.semantic_search(
                query_embedding,
                limit=max(limit * 2, limit),
                statement_types=statement_types,
                scope=scope,
                created_after=created_after,
                created_before=created_before,
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
        query_embedding: QueryEmbeddingReceipt | None = None,
        statement_types: Sequence[str] | None = None,
        scope: Mapping[str, Any] | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        limit: int = 12,
        include_causes: bool = True,
        max_causal_depth: int = 8,
    ) -> AuthorityContextPack:
        candidates = self.hybrid_search(
            query,
            query_embedding=query_embedding,
            statement_types=statement_types,
            scope=scope,
            created_after=created_after,
            created_before=created_before,
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
            "embedding_profile_id": (
                query_embedding.profile_id if query_embedding is not None else None
            ),
            "embedding_query_receipt": (
                query_embedding.to_trace_dict()
                if query_embedding is not None
                else None
            ),
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
                database_contract = self._probe_server_contract(
                    conn, create_extension=False
                )
                catalog_signature = self._validate_schema_contract(conn)
                project_anchor = self._validate_project_anchor(
                    conn, require_expected=True
                )
                database_contract.update(
                    {
                        "schema": self.schema,
                        "schema_version": 3,
                        "embedding_dimensions": self.embedding_dimensions,
                        "schema_contract_signature": authority_schema_signature(
                            schema=self.schema,
                            embedding_dimensions=self.embedding_dimensions,
                        ),
                        "catalog_signature": catalog_signature,
                        "project_anchor": project_anchor,
                    }
                )
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
                embedding_rows = conn.execute(
                    sql.SQL(
                        """
                         SELECT project_id, statement_id, revision, profile_id,
                                embedding::text AS embedding,
                                embedded_text_sha256, embedding_sha256,
                               generator_identity, generation_receipt,
                               generation_receipt_sha256, created_at
                        FROM {table}
                        WHERE project_id = %s
                        ORDER BY statement_id, revision, profile_id
                        """
                    ).format(table=self._table("statement_embedding")),
                    (self.project_id,),
                ).fetchall()
        snapshot: dict[str, Any] = {
            "schema": "aegis.reasoning_ledger.snapshot.v5",
            "project_id": self.project_id,
            "database_contract": database_contract,
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
            "embedding_index": [self._json_row(row) for row in embedding_rows],
        }
        if output_path is not None:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(snapshot, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return snapshot

    def reindex_storage(self, *, created_by: str = "reasoning_ledger") -> int:
        """Rebuild PostgreSQL index storage; this does not regenerate vectors."""

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
                    event_type="INDEX_STORAGE_REINDEXED",
                    reason="PostgreSQL index storage reindexed; vectors unchanged",
                    created_by=created_by,
                    payload={
                        "stored_vectors": count,
                        "approximate": False,
                        "vectors_regenerated": False,
                    },
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
            "SELECT pg_catalog.pg_advisory_xact_lock("
            "pg_catalog.hashtextextended(%s, 0))",
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

    def _schema_metadata_value(
        self, conn: psycopg.Connection[dict[str, Any]]
    ) -> dict[str, Any] | None:
        row = conn.execute(
            sql.SQL(
                "SELECT value FROM {table} WHERE key = 'schema_version'"
            ).format(table=self._table("schema_metadata"))
        ).fetchone()
        return dict(row["value"] or {}) if row is not None else None

    def _schema_metadata_version(
        self, conn: psycopg.Connection[dict[str, Any]]
    ) -> int | None:
        value = self._schema_metadata_value(conn)
        version = value.get("version") if value is not None else None
        return version if isinstance(version, int) and not isinstance(version, bool) else None

    def _database_identity(
        self, conn: psycopg.Connection[dict[str, Any]]
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT control.system_identifier::text AS cluster_system_identifier,
                   database.oid::text AS database_oid,
                   pg_catalog.current_database()::text AS database_name
            FROM pg_catalog.pg_control_system() control
            JOIN pg_catalog.pg_database database
              ON database.datname = pg_catalog.current_database()
            """
        ).fetchone()
        if row is None:
            raise RuntimeError("cannot resolve PostgreSQL cluster/database identity")
        identity = {
            "cluster_system_identifier": str(row["cluster_system_identifier"]),
            "database_oid": int(str(row["database_oid"])),
            "database_name": str(row["database_name"]),
            "schema_name": self.schema,
        }
        if (
            not identity["cluster_system_identifier"].isdigit()
            or identity["database_oid"] <= 0
            or not identity["database_name"]
        ):
            raise RuntimeError("PostgreSQL cluster/database identity is invalid")
        return identity

    def _project_anchor_descriptor(
        self, identity: Mapping[str, Any]
    ) -> dict[str, Any]:
        descriptor = {
            "schema": "aegis.reasoning_ledger.project_anchor.v1",
            "project_id": self.project_id,
            "cluster_system_identifier": str(
                identity["cluster_system_identifier"]
            ),
            "database_oid": int(identity["database_oid"]),
            "database_name": str(identity["database_name"]),
            "schema_name": str(identity["schema_name"]),
        }
        encoded = json.dumps(
            descriptor,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return {
            **descriptor,
            "anchor_sha256": hashlib.sha256(encoded).hexdigest(),
        }

    def _ensure_project_anchor(
        self, conn: psycopg.Connection[dict[str, Any]]
    ) -> dict[str, Any]:
        row = conn.execute(
            sql.SQL(
                "SELECT project_id FROM {table} WHERE project_id = %s"
            ).format(table=self._table("project_anchor")),
            (self.project_id,),
        ).fetchone()
        if row is None:
            if self.expected_project_anchor_sha256 is not None:
                raise RuntimeError(
                    "configured project anchor is absent from the selected database"
                )
            descriptor = self._project_anchor_descriptor(
                self._database_identity(conn)
            )
            conn.execute(
                sql.SQL(
                    """
                    INSERT INTO {table} (
                      project_id, cluster_system_identifier, database_oid,
                      database_name, schema_name, anchor_sha256
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """
                ).format(table=self._table("project_anchor")),
                (
                    self.project_id,
                    descriptor["cluster_system_identifier"],
                    descriptor["database_oid"],
                    descriptor["database_name"],
                    descriptor["schema_name"],
                    descriptor["anchor_sha256"],
                ),
            )
        return self._validate_project_anchor(
            conn,
            require_expected=self.expected_project_anchor_sha256 is not None,
        )

    def _validate_project_anchor(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        *,
        require_expected: bool,
    ) -> dict[str, Any]:
        row = conn.execute(
            sql.SQL(
                """
                SELECT project_id, cluster_system_identifier,
                       database_oid::text AS database_oid, database_name,
                       schema_name, anchor_sha256, created_at
                FROM {table}
                WHERE project_id = %s
                """
            ).format(table=self._table("project_anchor")),
            (self.project_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError(
                "reasoning-ledger project anchor is missing from the selected database"
            )
        identity = self._database_identity(conn)
        descriptor = self._project_anchor_descriptor(identity)
        stored_descriptor = {
            "schema": descriptor["schema"],
            "project_id": str(row["project_id"]),
            "cluster_system_identifier": str(row["cluster_system_identifier"]),
            "database_oid": int(str(row["database_oid"])),
            "database_name": str(row["database_name"]),
            "schema_name": str(row["schema_name"]),
            "anchor_sha256": str(row["anchor_sha256"]),
        }
        if stored_descriptor != descriptor:
            raise RuntimeError(
                "reasoning-ledger project anchor differs from the live "
                "PostgreSQL cluster/database identity"
            )
        expected = self.expected_project_anchor_sha256
        if require_expected and expected is None:
            raise RuntimeError(
                "project configuration has not bound the reasoning-ledger anchor"
            )
        if expected is not None and descriptor["anchor_sha256"] != expected:
            raise RuntimeError(
                "reasoning-ledger project anchor differs from project configuration"
            )
        return {
            **descriptor,
            "created_at": json_ready(row["created_at"]),
        }

    def _validate_v2_upgrade_source(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        columns: Mapping[str, tuple[str, ...]],
        *,
        vector_schema: str,
    ) -> None:
        if dict(columns) != V2_AUTHORITY_TABLE_COLUMNS:
            raise RuntimeError(
                "version-2 reasoning ledger differs from the supported upgrade source"
            )
        self._validate_v2_column_definitions(
            conn,
            vector_schema=vector_schema,
        )
        expected_metadata = {
            "name": "reasoning_ledger",
            "version": 2,
            "embedding_dimensions": self.embedding_dimensions,
            "authority_model": "immutable_revision_event_projection",
        }
        if self._schema_metadata_value(conn) != expected_metadata:
            raise RuntimeError(
                "version-2 reasoning-ledger metadata differs from the supported upgrade source"
            )
        forbidden = conn.execute(
            sql.SQL(
                """
                SELECT
                  EXISTS(
                    SELECT 1 FROM {evidence}
                    WHERE jsonb_path_exists(
                      scope,
                      '$.** ? (@.type() == "object").keyvalue() ? (@.key == "required_permissions")'
                    )
                  )
                  OR EXISTS(
                    SELECT 1 FROM {revision}
                    WHERE jsonb_path_exists(
                            scope,
                            '$.** ? (@.type() == "object").keyvalue() ? (@.key == "required_permissions")'
                          )
                       OR jsonb_path_exists(
                            structured_conditions,
                            '$.** ? (@.type() == "object").keyvalue() ? (@.key == "required_permissions")'
                          )
                  )
                  OR EXISTS(
                    SELECT 1 FROM {relation}
                    WHERE jsonb_path_exists(
                      applicable_conditions,
                      '$.** ? (@.type() == "object").keyvalue() ? (@.key == "required_permissions")'
                    )
                  ) AS present
                """
            ).format(
                evidence=self._table("evidence_descriptor"),
                revision=self._table("statement_revision"),
                relation=self._table("relation"),
            )
        ).fetchone()
        if forbidden is None or bool(forbidden["present"]):
            raise RuntimeError(
                "version-2 reasoning ledger contains self-declared permission fields; "
                "supersede or rebuild those authority rows before migration"
            )
        invalid_supersedes = conn.execute(
            sql.SQL(
                """
                WITH revision_chain AS (
                  SELECT project_id, statement_id,
                         min(revision) AS first_revision,
                         max(revision) AS last_revision,
                         count(*) AS revision_count
                  FROM {revision}
                  GROUP BY project_id, statement_id
                ), relation_chain AS (
                  SELECT project_id, from_statement_id AS statement_id,
                         count(*) AS relation_count
                  FROM {relation}
                  WHERE relation_type = 'SUPERSEDES'
                  GROUP BY project_id, from_statement_id
                )
                SELECT
                  EXISTS (
                    SELECT 1
                    FROM {statement} statement
                    LEFT JOIN revision_chain chain
                      ON chain.project_id = statement.project_id
                     AND chain.statement_id = statement.statement_id
                    LEFT JOIN {projection} projection
                      ON projection.project_id = statement.project_id
                     AND projection.statement_id = statement.statement_id
                    LEFT JOIN relation_chain relations
                      ON relations.project_id = statement.project_id
                     AND relations.statement_id = statement.statement_id
                    WHERE chain.statement_id IS NULL
                       OR chain.first_revision <> 1
                       OR chain.revision_count <> chain.last_revision
                       OR projection.revision IS DISTINCT FROM chain.last_revision
                       OR projection.validity = 'SUPERSEDED'
                       OR coalesce(relations.relation_count, 0)
                          <> chain.last_revision - 1
                  )
                  OR EXISTS (
                    SELECT 1
                    FROM {relation} relation
                    WHERE relation.relation_type = 'SUPERSEDES'
                      AND (
                        relation.from_statement_id <> relation.to_statement_id
                        OR relation.to_revision <> relation.from_revision + 1
                        OR (
                          SELECT count(*)
                          FROM {event} event
                          WHERE event.project_id = relation.project_id
                            AND event.aggregate_kind = 'REVISION'
                            AND event.event_type = 'REVISION_SUPERSEDED'
                            AND event.aggregate_id = relation.from_statement_id
                                || '@' || relation.from_revision::text
                            AND event.payload->>'superseded_by'
                                = relation.to_statement_id
                                  || '@' || relation.to_revision::text
                            AND event.payload->>'relation_id' = relation.relation_id
                            AND event.payload->>'new_validity' = (
                              SELECT target.validity
                              FROM {revision} target
                              WHERE target.project_id = relation.project_id
                                AND target.statement_id = relation.to_statement_id
                                AND target.revision = relation.to_revision
                            )
                        ) <> 1
                      )
                  )
                  OR EXISTS (
                    SELECT 1
                    FROM {revision} revision
                    WHERE (revision.revision = 1 AND revision.validity = 'SUPERSEDED')
                       OR (revision.revision > 1 AND revision.validity <> 'ACTIVE')
                  )
                  OR EXISTS (
                    SELECT 1
                    FROM {revision} revision
                    WHERE revision.revision > 1
                      AND (
                        SELECT count(*)
                        FROM {relation} relation
                        WHERE relation.project_id = revision.project_id
                          AND relation.relation_type = 'SUPERSEDES'
                          AND relation.to_statement_id = revision.statement_id
                          AND relation.to_revision = revision.revision
                      ) <> 1
                  )
                  OR EXISTS (
                    SELECT 1
                    FROM {event} event
                    WHERE event.event_type = 'REVISION_SUPERSEDED'
                      AND (
                        event.aggregate_kind <> 'REVISION'
                        OR NOT EXISTS (
                        SELECT 1
                        FROM {relation} relation
                        JOIN {revision} target
                          ON target.project_id = relation.project_id
                         AND target.statement_id = relation.to_statement_id
                         AND target.revision = relation.to_revision
                        WHERE relation.project_id = event.project_id
                          AND relation.relation_type = 'SUPERSEDES'
                          AND relation.relation_id = event.payload->>'relation_id'
                          AND relation.from_statement_id || '@'
                              || relation.from_revision::text = event.aggregate_id
                          AND relation.to_statement_id || '@'
                              || relation.to_revision::text
                              = event.payload->>'superseded_by'
                          AND event.payload->>'new_validity' = target.validity
                        )
                      )
                  ) AS present
                """
            ).format(
                statement=self._table("statement"),
                revision=self._table("statement_revision"),
                relation=self._table("relation"),
                projection=self._table("current_projection"),
                event=self._table("ledger_event"),
            )
        ).fetchone()
        if invalid_supersedes is None or bool(invalid_supersedes["present"]):
            raise RuntimeError(
                "version-2 reasoning ledger revision/SUPERSEDES/event/projection "
                "history is not one complete consecutive chain"
            )
        trigger_rows = conn.execute(
            """
            SELECT trigger.tgname AS name,
                   pg_catalog.pg_get_triggerdef(trigger.oid, true) AS definition,
                   trigger.tgenabled AS enabled
            FROM pg_catalog.pg_trigger trigger
            JOIN pg_catalog.pg_class relation ON relation.oid = trigger.tgrelid
            JOIN pg_catalog.pg_namespace namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = %s AND NOT trigger.tgisinternal
            """,
            (self.schema,),
        ).fetchall()
        expected_triggers = V2_REQUIRED_TRIGGER_NAMES
        observed = {str(row["name"]): str(row["definition"]) for row in trigger_rows}
        if set(observed) != expected_triggers or any(
            str(row["enabled"]) != "O" for row in trigger_rows
        ):
            raise RuntimeError(
                "version-2 reasoning-ledger trigger contract differs from the upgrade source"
            )
        for name, definition in observed.items():
            expected_function = (
                "validate_current_projection_event"
                if name == "current_projection_event_bound"
                else "reject_authority_mutation"
            )
            if expected_function not in definition:
                raise RuntimeError(
                    "version-2 reasoning-ledger trigger binding differs: " + name
                )

    def _schema_column_definitions(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        *,
        schema: str,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT table_name, column_name, data_type, udt_name, is_nullable,
                   column_default, generation_expression
            FROM information_schema.columns
            WHERE table_schema = %s
            ORDER BY table_name, ordinal_position
            """,
            (schema,),
        ).fetchall()

        def normalize(value: Any) -> Any:
            if not isinstance(value, str):
                return json_ready(value)
            return value.replace(f'"{schema}".', '<schema>.').replace(
                f"{schema}.", "<schema>."
            )

        return {
            (str(row["table_name"]), str(row["column_name"])): {
                str(key): normalize(value)
                for key, value in row.items()
                if key not in {"table_name", "column_name"}
            }
            for row in rows
        }

    def _validate_v2_column_definitions(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        *,
        vector_schema: str,
    ) -> None:
        conn.execute(
            sql.SQL("SET search_path TO pg_catalog, {}").format(
                sql.Identifier(vector_schema)
            )
        )
        v2_functions = (
            "reject_authority_mutation",
            "validate_current_projection_event",
        )
        v2_triggers = V2_REQUIRED_TRIGGER_NAMES

        def function_contract(schema: str) -> dict[str, dict[str, Any]]:
            rows = conn.execute(
                """
                SELECT procedure.proname, procedure.prosrc,
                       procedure.provolatile, procedure.prosecdef,
                       procedure.proleakproof, procedure.proconfig
                FROM pg_catalog.pg_proc procedure
                JOIN pg_catalog.pg_namespace namespace ON namespace.oid = procedure.pronamespace
                WHERE namespace.nspname = %s
                  AND procedure.proname::text = ANY(%s::text[])
                ORDER BY procedure.proname
                """,
                (schema, list(v2_functions)),
            ).fetchall()
            return {
                str(row["proname"]): {
                    str(key): (
                        value.replace(f'"{schema}".', '<schema>.').replace(
                            f"{schema}.", "<schema>."
                        )
                        if isinstance(value, str)
                        else json_ready(value)
                    )
                    for key, value in row.items()
                    if key != "proname"
                }
                for row in rows
            }

        def trigger_contract(schema: str) -> dict[str, dict[str, Any]]:
            rows = conn.execute(
                """
                SELECT trigger.tgname, relation.relname AS table_name,
                       trigger.tgenabled,
                       pg_catalog.pg_get_triggerdef(trigger.oid, true) AS definition
                FROM pg_catalog.pg_trigger trigger
                JOIN pg_catalog.pg_class relation ON relation.oid = trigger.tgrelid
                JOIN pg_catalog.pg_namespace namespace ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = %s
                  AND NOT trigger.tgisinternal
                  AND trigger.tgname::text = ANY(%s::text[])
                ORDER BY relation.relname, trigger.tgname
                """,
                (schema, sorted(v2_triggers)),
            ).fetchall()
            return {
                str(row["tgname"]): {
                    str(key): (
                        value.replace(f'"{schema}".', '<schema>.').replace(
                            f"{schema}.", "<schema>."
                        )
                        if isinstance(value, str)
                        else json_ready(value)
                    )
                    for key, value in row.items()
                    if key != "tgname"
                }
                for row in rows
            }

        reference_schema = validate_identifier(
            "aegis_v3_reference_" + hashlib.sha256(os.urandom(32)).hexdigest()[:12]
        )
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(reference_schema)))
        try:
            conn.execute(
                build_v2_reference_sql(
                    schema=reference_schema,
                    embedding_dimensions=self.embedding_dimensions,
                )
            )
            conn.execute(
                build_v2_projection_validation_function_sql(
                    schema=reference_schema,
                )
            )
            reference = self._schema_column_definitions(
                conn,
                schema=reference_schema,
            )
            reference_functions = function_contract(reference_schema)
            reference_triggers = trigger_contract(reference_schema)
        finally:
            conn.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(
                    sql.Identifier(reference_schema)
                )
            )
        observed = self._schema_column_definitions(conn, schema=self.schema)
        for table, column_names in V2_AUTHORITY_TABLE_COLUMNS.items():
            for column_name in column_names:
                key = (table, column_name)
                if observed.get(key) != reference.get(key):
                    raise RuntimeError(
                        "version-2 reasoning-ledger column definition differs: "
                        f"{table}.{column_name}"
                    )
        if function_contract(self.schema) != reference_functions:
            raise RuntimeError(
                "version-2 reasoning-ledger trigger function bodies differ from "
                "the supported upgrade source"
            )
        if trigger_contract(self.schema) != reference_triggers:
            raise RuntimeError(
                "version-2 reasoning-ledger trigger definitions differ from "
                "the supported upgrade source"
            )

    def _migrate_v2_to_v3(
        self, conn: psycopg.Connection[dict[str, Any]]
    ) -> None:
        conn.execute(
            build_forbidden_authority_key_function_sql(schema=self.schema)
        )
        conn.execute(
            sql.SQL("DELETE FROM {table}").format(
                table=self._table("statement_embedding")
            )
        )
        conn.execute(
            sql.SQL(
                """
                ALTER TABLE {embedding}
                  ADD COLUMN embedding_sha256 text NOT NULL
                    CHECK (embedding_sha256 ~ '^[0-9a-f]{{64}}$'),
                  ADD COLUMN generator_identity jsonb NOT NULL,
                  ADD COLUMN generation_receipt jsonb NOT NULL,
                  ADD COLUMN generation_receipt_sha256 text NOT NULL
                    CHECK (generation_receipt_sha256 ~ '^[0-9a-f]{{64}}$');

                ALTER TABLE {evidence}
                  DROP CONSTRAINT evidence_descriptor_scope_check,
                  ADD CONSTRAINT evidence_descriptor_scope_check
                    CHECK (NOT {forbidden}(scope));

                ALTER TABLE {revision}
                  DROP CONSTRAINT statement_revision_scope_check,
                  ADD CONSTRAINT statement_revision_scope_check
                    CHECK (NOT {forbidden}(scope)),
                  ADD CONSTRAINT statement_revision_structured_conditions_check
                    CHECK (NOT {forbidden}(structured_conditions));

                ALTER TABLE {relation}
                  ADD CONSTRAINT relation_applicable_conditions_check
                    CHECK (NOT {forbidden}(applicable_conditions));

                ALTER TABLE {event}
                  DROP CONSTRAINT ledger_event_event_type_check,
                  ADD CONSTRAINT ledger_event_event_type_check CHECK (
                    event_type IN (
                      'STATEMENT_CREATED', 'REVISION_CREATED',
                      'REVISION_INVALIDATED', 'REVISION_MARKED_STALE',
                      'REVISION_REVALIDATED', 'REVISION_SUPERSEDED',
                      'RELATION_CREATED', 'EVIDENCE_REGISTERED',
                      'EMBEDDING_PROFILE_REGISTERED', 'EMBEDDING_REBUILT',
                      'INDEX_STORAGE_REINDEXED'
                    )
                  );
                """
            ).format(
                embedding=self._table("statement_embedding"),
                evidence=self._table("evidence_descriptor"),
                revision=self._table("statement_revision"),
                relation=self._table("relation"),
                event=self._table("ledger_event"),
                forbidden=sql.SQL("{}.contains_forbidden_authority_key").format(
                    sql.Identifier(self.schema)
                ),
            )
        )
        metadata = {
            "name": "reasoning_ledger",
            "version": 3,
            "embedding_dimensions": self.embedding_dimensions,
            "authority_model": "immutable_revision_event_projection",
            "contract_signature": authority_schema_signature(
                schema=self.schema,
                embedding_dimensions=self.embedding_dimensions,
            ),
            "catalog_signature": None,
        }
        conn.execute(
            sql.SQL(
                "UPDATE {table} SET value = %s, updated_at = now() "
                "WHERE key = 'schema_version'"
            ).format(table=self._table("schema_metadata")),
            (Jsonb(metadata),),
        )

    def _catalog_signature(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        *,
        schema: str | None = None,
    ) -> str:
        target_schema = self.schema if schema is None else validate_identifier(schema)
        columns = conn.execute(
            """
            SELECT table_name, column_name, ordinal_position, data_type, udt_name,
                   is_nullable, column_default, generation_expression,
                   character_maximum_length, numeric_precision, numeric_scale,
                   datetime_precision, collation_schema, collation_name,
                   is_identity, identity_generation, identity_start,
                   identity_increment, is_generated
            FROM information_schema.columns
            WHERE table_schema = %s
            ORDER BY table_name, ordinal_position
            """,
            (target_schema,),
        ).fetchall()
        relations = conn.execute(
            """
            SELECT relation.relname AS table_name, relation.relkind,
                   relation.relpersistence, relation.relrowsecurity,
                   relation.relforcerowsecurity, relation.relreplident,
                   relation.relispartition
            FROM pg_catalog.pg_class relation
            JOIN pg_catalog.pg_namespace namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = %s
              AND relation.relkind IN ('r', 'p')
            ORDER BY relation.relname
            """,
            (target_schema,),
        ).fetchall()
        constraints = conn.execute(
            """
            SELECT relation.relname AS table_name, catalog_constraint.contype,
                   catalog_constraint.condeferrable, catalog_constraint.condeferred,
                   catalog_constraint.convalidated,
                   pg_catalog.pg_get_constraintdef(catalog_constraint.oid, true) AS definition
            FROM pg_catalog.pg_constraint catalog_constraint
            JOIN pg_catalog.pg_class relation ON relation.oid = catalog_constraint.conrelid
            JOIN pg_catalog.pg_namespace namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = %s
            ORDER BY relation.relname, catalog_constraint.contype,
                     catalog_constraint.conname
            """,
            (target_schema,),
        ).fetchall()
        triggers = conn.execute(
            """
            SELECT relation.relname AS table_name, trigger.tgname,
                   trigger.tgenabled,
                   pg_catalog.pg_get_triggerdef(trigger.oid, true) AS definition
            FROM pg_catalog.pg_trigger trigger
            JOIN pg_catalog.pg_class relation ON relation.oid = trigger.tgrelid
            JOIN pg_catalog.pg_namespace namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = %s AND NOT trigger.tgisinternal
            ORDER BY relation.relname, trigger.tgname
            """,
            (target_schema,),
        ).fetchall()
        functions = conn.execute(
            """
            SELECT procedure.proname,
                   pg_catalog.pg_get_functiondef(procedure.oid) AS definition
            FROM pg_catalog.pg_proc procedure
            JOIN pg_catalog.pg_namespace namespace ON namespace.oid = procedure.pronamespace
            WHERE namespace.nspname = %s
              AND procedure.proname::text = ANY(%s::text[])
            ORDER BY procedure.proname
            """,
            (
                target_schema,
                [
                    "reject_authority_mutation",
                    "validate_current_projection_event",
                    "validate_supersedes_transaction",
                    "validate_supersedes_event_transaction",
                    "validate_revision_transaction",
                    "contains_forbidden_authority_key",
                    "freeze_schema_metadata",
                ],
            ),
        ).fetchall()
        indexes = conn.execute(
            """
            SELECT indexes.tablename, indexes.indexname, indexes.indexdef,
                   catalog.indisvalid, catalog.indisready
            FROM pg_catalog.pg_indexes indexes
            JOIN pg_catalog.pg_class index_relation ON index_relation.relname = indexes.indexname
            JOIN pg_catalog.pg_namespace namespace
              ON namespace.oid = index_relation.relnamespace
             AND namespace.nspname = indexes.schemaname
            JOIN pg_catalog.pg_index catalog ON catalog.indexrelid = index_relation.oid
            WHERE indexes.schemaname = %s
            ORDER BY indexes.tablename, indexes.indexname
            """,
            (target_schema,),
        ).fetchall()
        policies = conn.execute(
            """
            SELECT tablename, policyname, permissive, roles, cmd,
                   qual, with_check
            FROM pg_catalog.pg_policies
            WHERE schemaname = %s
            ORDER BY tablename, policyname
            """,
            (target_schema,),
        ).fetchall()
        sequences = conn.execute(
            """
            SELECT sequences.sequencename, sequences.sequenceowner,
                   sequences.data_type, sequences.start_value,
                   sequences.min_value, sequences.max_value,
                   sequences.increment_by, sequences.cycle,
                   sequences.cache_size,
                   owned_table.relname AS owned_table,
                   owned_column.attname AS owned_column,
                   dependency.deptype AS ownership_dependency
            FROM pg_catalog.pg_sequences sequences
            JOIN pg_catalog.pg_namespace namespace
              ON namespace.nspname = sequences.schemaname
            JOIN pg_catalog.pg_class sequence_relation
              ON sequence_relation.relnamespace = namespace.oid
             AND sequence_relation.relname = sequences.sequencename
             AND sequence_relation.relkind = 'S'
            LEFT JOIN pg_catalog.pg_depend dependency
              ON dependency.classid = 'pg_catalog.pg_class'::pg_catalog.regclass
             AND dependency.objid = sequence_relation.oid
             AND dependency.deptype IN ('a', 'i')
            LEFT JOIN pg_catalog.pg_class owned_table
              ON owned_table.oid = dependency.refobjid
            LEFT JOIN pg_catalog.pg_attribute owned_column
              ON owned_column.attrelid = dependency.refobjid
             AND owned_column.attnum = dependency.refobjsubid
            WHERE sequences.schemaname = %s
            ORDER BY sequences.sequencename
            """,
            (target_schema,),
        ).fetchall()
        extensions = conn.execute(
            """
            SELECT extension.extname, extension.extversion,
                   extension.extrelocatable,
                   namespace.nspname AS extension_schema
            FROM pg_catalog.pg_extension extension
            JOIN pg_catalog.pg_namespace namespace
              ON namespace.oid = extension.extnamespace
            WHERE extension.extname = 'vector'
            ORDER BY extension.extname
            """
        ).fetchall()

        def normalize(value: Any) -> Any:
            if not isinstance(value, str):
                return json_ready(value)
            return value.replace(f'"{target_schema}".', '<schema>.').replace(
                f"{target_schema}.", "<schema>."
            )

        payload = {
            "relations": [
                {str(key): normalize(value) for key, value in row.items()}
                for row in relations
            ],
            "columns": [
                {str(key): normalize(value) for key, value in row.items()}
                for row in columns
            ],
            "constraints": [
                {str(key): normalize(value) for key, value in row.items()}
                for row in constraints
            ],
            "triggers": [
                {str(key): normalize(value) for key, value in row.items()}
                for row in triggers
            ],
            "functions": [
                {str(key): normalize(value) for key, value in row.items()}
                for row in functions
            ],
            "indexes": [
                {str(key): normalize(value) for key, value in row.items()}
                for row in indexes
            ],
            "policies": [
                {str(key): normalize(value) for key, value in row.items()}
                for row in policies
            ],
            "sequences": [
                {str(key): normalize(value) for key, value in row.items()}
                for row in sequences
            ],
            "extensions": [
                {str(key): normalize(value) for key, value in row.items()}
                for row in extensions
            ],
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _expected_catalog_signature(
        self, conn: psycopg.Connection[dict[str, Any]]
    ) -> str:
        reference_schema = validate_identifier(
            "aegis_v3_catalog_" + hashlib.sha256(os.urandom(32)).hexdigest()[:12]
        )
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(reference_schema)))
        try:
            conn.execute(
                build_init_sql(
                    schema=reference_schema,
                    embedding_dimensions=self.embedding_dimensions,
                )
            )
            return self._catalog_signature(conn, schema=reference_schema)
        finally:
            conn.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(
                    sql.Identifier(reference_schema)
                )
            )

    def _stamp_schema_catalog_signature(
        self, conn: psycopg.Connection[dict[str, Any]]
    ) -> None:
        metadata = self._schema_metadata_value(conn)
        if metadata is None:
            raise RuntimeError("reasoning-ledger schema metadata is missing")
        actual = self._catalog_signature(conn)
        stored = metadata.get("catalog_signature")
        if stored is None:
            expected = self._expected_catalog_signature(conn)
            if actual != expected:
                raise RuntimeError(
                    "reasoning-ledger actual catalog differs from the generated "
                    "version-3 authority schema"
                )
            updated = {**metadata, "catalog_signature": actual}
            conn.execute(
                sql.SQL(
                    "UPDATE {table} SET value = %s, updated_at = now() "
                    "WHERE key = 'schema_version'"
                ).format(table=self._table("schema_metadata")),
                (Jsonb(updated),),
            )
        elif stored != actual:
            raise RuntimeError(
                "reasoning-ledger actual catalog differs from its frozen signature"
            )

    def _probe_server_contract(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        *,
        create_extension: bool,
        tolerate_legacy_namespace: bool = False,
        relocate_legacy_namespace: bool = False,
    ) -> dict[str, Any]:
        if tolerate_legacy_namespace and relocate_legacy_namespace:
            raise ValueError(
                "legacy pgvector namespace cannot be tolerated and relocated together"
            )
        row = conn.execute(
            """
            SELECT pg_catalog.current_database() AS database,
                   current_user AS user,
                   pg_catalog.current_setting('server_version_num')::integer
                     AS server_version_num
            """
        ).fetchone()
        assert row is not None
        server_version = int(row["server_version_num"])
        server_major = server_version // 10000
        if server_major < self.minimum_postgresql_major:
            raise RuntimeError(
                "PostgreSQL major version is below the reasoning-ledger baseline: "
                f"{server_major} < {self.minimum_postgresql_major}"
            )
        vector = conn.execute(
            """
            SELECT extension.extversion,
                   extension.extrelocatable,
                   namespace.nspname AS extension_schema
            FROM pg_catalog.pg_extension extension
            JOIN pg_catalog.pg_namespace namespace
              ON namespace.oid = extension.extnamespace
            WHERE extension.extname = 'vector'
            """
        ).fetchone()
        if vector is None and create_extension:
            conn.execute(
                sql.SQL("CREATE EXTENSION vector WITH SCHEMA {}").format(
                    sql.Identifier(PGVECTOR_SCHEMA)
                )
            )
            vector = conn.execute(
                """
                SELECT extension.extversion,
                       extension.extrelocatable,
                       namespace.nspname AS extension_schema
                FROM pg_catalog.pg_extension extension
                JOIN pg_catalog.pg_namespace namespace
                  ON namespace.oid = extension.extnamespace
                WHERE extension.extname = 'vector'
                """
            ).fetchone()
        if vector is None:
            raise RuntimeError("pgvector extension is not installed")
        vector_version = str(vector["extversion"])
        if self._version_tuple(vector_version) < self._version_tuple(
            self.minimum_pgvector_version
        ):
            raise RuntimeError(
                "pgvector version is below the reasoning-ledger baseline: "
                f"{vector_version} < {self.minimum_pgvector_version}"
            )
        vector_schema = str(vector["extension_schema"])
        if vector_schema != PGVECTOR_SCHEMA and relocate_legacy_namespace:
            if not bool(vector["extrelocatable"]):
                raise RuntimeError(
                    "pgvector extension cannot be relocated to the authority namespace"
                )
            conn.execute(
                sql.SQL("ALTER EXTENSION vector SET SCHEMA {}").format(
                    sql.Identifier(PGVECTOR_SCHEMA)
                )
            )
            vector = conn.execute(
                """
                SELECT extension.extversion,
                       extension.extrelocatable,
                       namespace.nspname AS extension_schema
                FROM pg_catalog.pg_extension extension
                JOIN pg_catalog.pg_namespace namespace
                  ON namespace.oid = extension.extnamespace
                WHERE extension.extname = 'vector'
                """
            ).fetchone()
            if vector is None:
                raise RuntimeError("pgvector extension disappeared during relocation")
            vector_schema = str(vector["extension_schema"])
        if vector_schema != PGVECTOR_SCHEMA and not tolerate_legacy_namespace:
            raise RuntimeError(
                "pgvector extension namespace differs from the authority contract: "
                f"{vector_schema} != {PGVECTOR_SCHEMA}"
            )
        conn.execute(
            sql.SQL("SET search_path TO pg_catalog, {}").format(
                sql.Identifier(vector_schema)
            )
        )
        return {
            "database": str(row["database"]),
            "user": str(row["user"]),
            "postgresql_major": server_major,
            "postgresql_version_num": server_version,
            "pgvector_version": vector_version,
            "pgvector_schema": vector_schema,
        }

    def _schema_table_columns(
        self, conn: psycopg.Connection[dict[str, Any]]
    ) -> dict[str, tuple[str, ...]]:
        rows = conn.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = %s
            ORDER BY table_name, ordinal_position
            """,
            (self.schema,),
        ).fetchall()
        result: dict[str, list[str]] = {}
        for row in rows:
            result.setdefault(str(row["table_name"]), []).append(
                str(row["column_name"])
            )
        return {key: tuple(value) for key, value in result.items()}

    def _validate_event_sequence(
        self, conn: psycopg.Connection[dict[str, Any]]
    ) -> None:
        rows = conn.execute(
            """
            SELECT sequences.sequencename, sequences.data_type,
                   sequences.start_value, sequences.min_value,
                   sequences.max_value, sequences.increment_by,
                   sequences.cycle, sequences.cache_size,
                   owned_table.relname AS owned_table,
                   owned_column.attname AS owned_column,
                   dependency.deptype AS ownership_dependency
            FROM pg_catalog.pg_sequences sequences
            JOIN pg_catalog.pg_namespace namespace
              ON namespace.nspname = sequences.schemaname
            JOIN pg_catalog.pg_class sequence_relation
              ON sequence_relation.relnamespace = namespace.oid
             AND sequence_relation.relname = sequences.sequencename
             AND sequence_relation.relkind = 'S'
            LEFT JOIN pg_catalog.pg_depend dependency
              ON dependency.classid = 'pg_catalog.pg_class'::pg_catalog.regclass
             AND dependency.objid = sequence_relation.oid
             AND dependency.deptype IN ('a', 'i')
            LEFT JOIN pg_catalog.pg_class owned_table
              ON owned_table.oid = dependency.refobjid
            LEFT JOIN pg_catalog.pg_attribute owned_column
              ON owned_column.attrelid = dependency.refobjid
             AND owned_column.attnum = dependency.refobjsubid
            WHERE sequences.schemaname = %s
            """,
            (self.schema,),
        ).fetchall()
        expected = {
            "sequencename": "ledger_event_event_id_seq",
            "data_type": "bigint",
            "start_value": 1,
            "min_value": 1,
            "max_value": 9223372036854775807,
            "increment_by": 1,
            "cycle": False,
            "cache_size": 1,
            "owned_table": "ledger_event",
            "owned_column": "event_id",
            "ownership_dependency": "a",
        }
        observed = [
            {str(key): json_ready(value) for key, value in row.items()}
            for row in rows
        ]
        if observed != [expected]:
            raise RuntimeError(
                "reasoning-ledger event sequence contract differs from the authority schema"
            )
        state = conn.execute(
            sql.SQL("SELECT last_value, is_called FROM {}.{}").format(
                sql.Identifier(self.schema),
                sql.Identifier("ledger_event_event_id_seq"),
            )
        ).fetchone()
        maximum = conn.execute(
            sql.SQL("SELECT coalesce(max(event_id), 0) AS maximum FROM {}").format(
                self._table("ledger_event")
            )
        ).fetchone()
        if state is None or maximum is None:
            raise RuntimeError("reasoning-ledger event sequence state is unreadable")
        next_value = int(state["last_value"]) + (1 if bool(state["is_called"]) else 0)
        if next_value <= int(maximum["maximum"]):
            raise RuntimeError(
                "reasoning-ledger event sequence cannot allocate above existing events"
            )
        if next_value > int(expected["max_value"]):
            raise RuntimeError(
                "reasoning-ledger event sequence has exhausted its allocatable range"
            )

    def _validate_schema_contract(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        *,
        require_catalog_signature: bool = True,
    ) -> str:
        columns = self._schema_table_columns(conn)
        if columns != AUTHORITY_TABLE_COLUMNS:
            raise RuntimeError(
                "reasoning-ledger database tables or columns differ from the "
                "configured authority contract"
            )
        vector = conn.execute(
            """
            SELECT format_type(attribute.atttypid, attribute.atttypmod) AS vector_type
            FROM pg_catalog.pg_attribute attribute
            JOIN pg_catalog.pg_class relation ON relation.oid = attribute.attrelid
            JOIN pg_catalog.pg_namespace namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = %s
              AND relation.relname = 'statement_embedding'
              AND attribute.attname = 'embedding'
              AND NOT attribute.attisdropped
            """,
            (self.schema,),
        ).fetchone()
        if vector is None or str(vector["vector_type"]) != (
            f"vector({self.embedding_dimensions})"
        ):
            raise RuntimeError(
                "reasoning-ledger vector dimension differs from the configured contract"
            )
        self._validate_event_sequence(conn)
        trigger_rows = conn.execute(
            """
            SELECT trigger.tgname AS trigger_name,
                   pg_catalog.pg_get_triggerdef(trigger.oid, true) AS definition,
                   trigger.tgenabled AS enabled
            FROM pg_catalog.pg_trigger trigger
            JOIN pg_catalog.pg_class relation ON relation.oid = trigger.tgrelid
            JOIN pg_catalog.pg_namespace namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = %s AND NOT trigger.tgisinternal
            """,
            (self.schema,),
        ).fetchall()
        trigger_definitions = {
            str(row["trigger_name"]): str(row["definition"])
            for row in trigger_rows
        }
        trigger_names = set(trigger_definitions)
        if any(str(row["enabled"]) != "O" for row in trigger_rows):
            raise RuntimeError(
                "reasoning-ledger authority trigger is disabled or replica-only"
            )
        if trigger_names != REQUIRED_TRIGGER_NAMES:
            raise RuntimeError(
                "reasoning-ledger authority triggers are missing or renamed"
            )
        for trigger_name in REQUIRED_TRIGGER_NAMES:
            definition = trigger_definitions[trigger_name]
            expected_function = (
                "validate_current_projection_event"
                if trigger_name == "current_projection_event_bound"
                else "validate_supersedes_transaction"
                if trigger_name == "supersedes_transaction_bound"
                else "validate_supersedes_event_transaction"
                if trigger_name == "supersedes_event_transaction_bound"
                else "validate_revision_transaction"
                if trigger_name == "revision_transaction_bound"
                else "freeze_schema_metadata"
                if trigger_name == "schema_metadata_immutable"
                else "reject_authority_mutation"
            )
            if expected_function not in definition:
                raise RuntimeError(
                    "reasoning-ledger trigger function binding differs: "
                    + trigger_name
                )
        for trigger_name in (
            "supersedes_transaction_bound",
            "supersedes_event_transaction_bound",
        ):
            if not all(
                token in trigger_definitions[trigger_name].upper()
                for token in ("CONSTRAINT TRIGGER", "DEFERRABLE INITIALLY DEFERRED")
            ):
                raise RuntimeError(
                    "reasoning-ledger supersedes trigger is not deferred to commit"
                )
        function_rows = conn.execute(
            """
            SELECT procedure.proname AS function_name,
                   pg_catalog.pg_get_functiondef(procedure.oid) AS definition
            FROM pg_catalog.pg_proc procedure
            JOIN pg_catalog.pg_namespace namespace ON namespace.oid = procedure.pronamespace
            WHERE namespace.nspname = %s
              AND procedure.proname::text = ANY(%s::text[])
            """,
            (
                self.schema,
                [
                    "reject_authority_mutation",
                    "validate_current_projection_event",
                    "validate_supersedes_transaction",
                    "validate_supersedes_event_transaction",
                    "validate_revision_transaction",
                    "contains_forbidden_authority_key",
                    "freeze_schema_metadata",
                ],
            ),
        ).fetchall()
        function_definitions = {
            str(row["function_name"]): str(row["definition"])
            for row in function_rows
        }
        required_function_fragments = {
            "reject_authority_mutation": (
                "authority rows are immutable",
            ),
            "validate_current_projection_event": (
                "projection identity or event order is invalid",
                "projection has no revision event",
                "projection event type is invalid",
                "projection validity differs from its event",
            ),
            "validate_supersedes_transaction": (
                "consecutive version transition",
                "bound to the current projection",
                "no atomic authority event",
            ),
            "validate_supersedes_event_transaction": (
                "one atomic revision/relation/projection transaction",
                "pg_current_xact_id",
            ),
            "validate_revision_transaction": (
                "initial revision is not bound",
                "successor revision is not bound",
                "pg_current_xact_id",
            ),
            "contains_forbidden_authority_key": (
                "required_permissions",
                "jsonb_path_exists",
            ),
            "freeze_schema_metadata": (
                "schema metadata is immutable",
                "catalog_signature",
            ),
        }
        if set(function_definitions) != set(required_function_fragments):
            raise RuntimeError("reasoning-ledger trigger functions differ")
        for function_name, fragments in required_function_fragments.items():
            if any(
                fragment not in function_definitions[function_name]
                for fragment in fragments
            ):
                raise RuntimeError(
                    "reasoning-ledger trigger function body differs: "
                    + function_name
                )
        index_rows = conn.execute(
            """
            SELECT indexes.indexname, indexes.indexdef,
                   catalog.indisvalid AS valid,
                   catalog.indisready AS ready
            FROM pg_catalog.pg_indexes indexes
            JOIN pg_catalog.pg_class index_relation
              ON index_relation.relname = indexes.indexname
            JOIN pg_catalog.pg_namespace namespace
              ON namespace.oid = index_relation.relnamespace
             AND namespace.nspname = indexes.schemaname
            JOIN pg_catalog.pg_index catalog ON catalog.indexrelid = index_relation.oid
            WHERE indexes.schemaname = %s
            """,
            (self.schema,),
        ).fetchall()
        if any(
            not bool(row["valid"]) or not bool(row["ready"])
            for row in index_rows
        ):
            raise RuntimeError("reasoning-ledger contains an invalid index")
        index_names = {str(row["indexname"]) for row in index_rows}
        if not REQUIRED_INDEX_NAMES.issubset(index_names):
            raise RuntimeError("reasoning-ledger required indexes are missing")
        index_definitions = {
            str(row["indexname"]): str(row["indexdef"]).lower()
            for row in index_rows
        }
        expected_index_fragments = {
            "statement_revision_project_type_idx": "(project_id, statement_type, created_at desc)",
            "statement_revision_scope_gin_idx": "using gin (scope)",
            "statement_revision_search_gin_idx": "using gin (search_document)",
            "relation_from_idx": "(project_id, from_statement_id, from_revision, relation_type)",
            "relation_to_idx": "(project_id, to_statement_id, to_revision, relation_type)",
            "ledger_event_aggregate_idx": "(project_id, aggregate_kind, aggregate_id, event_id)",
            "current_projection_validity_idx": "(project_id, validity, statement_id)",
        }
        for index_name, fragment in expected_index_fragments.items():
            if fragment not in index_definitions[index_name]:
                raise RuntimeError(
                    "reasoning-ledger index definition differs: " + index_name
                )
        if any(
            token in str(row["indexdef"]).lower()
            for row in index_rows
            for token in ("using hnsw", "using ivfflat")
        ):
            raise RuntimeError(
                "reasoning-ledger approximate vector index is not approved"
            )
        constraints = conn.execute(
            """
            SELECT relation.relname AS table_name,
                   catalog_constraint.contype AS constraint_type,
                   pg_catalog.pg_get_constraintdef(catalog_constraint.oid, true) AS definition,
                   catalog_constraint.convalidated AS validated
            FROM pg_catalog.pg_constraint catalog_constraint
            JOIN pg_catalog.pg_class relation ON relation.oid = catalog_constraint.conrelid
            JOIN pg_catalog.pg_namespace namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = %s
            """,
            (self.schema,),
        ).fetchall()
        if any(not bool(row["validated"]) for row in constraints):
            raise RuntimeError(
                "reasoning-ledger contains an unvalidated authority constraint"
            )
        primary_tables = {
            str(row["table_name"])
            for row in constraints
            if row["constraint_type"] == "p"
        }
        if primary_tables != set(AUTHORITY_TABLE_COLUMNS):
            raise RuntimeError(
                "reasoning-ledger primary-key contract differs from the authority schema"
            )
        expected_primary_keys = {
            "project_anchor": "PRIMARY KEY (project_id)",
            "statement": "PRIMARY KEY (project_id, statement_id)",
            "evidence_descriptor": "PRIMARY KEY (project_id, evidence_id)",
            "statement_revision": "PRIMARY KEY (project_id, statement_id, revision)",
            "statement_revision_evidence": "PRIMARY KEY (project_id, statement_id, revision, evidence_id)",
            "relation": "PRIMARY KEY (project_id, relation_id)",
            "relation_evidence": "PRIMARY KEY (project_id, relation_id, evidence_id)",
            "ledger_event": "PRIMARY KEY (project_id, event_id)",
            "current_projection": "PRIMARY KEY (project_id, statement_id)",
            "embedding_profile": "PRIMARY KEY (project_id, profile_id)",
            "statement_embedding": "PRIMARY KEY (project_id, statement_id, revision, profile_id)",
            "schema_metadata": "PRIMARY KEY (key)",
        }
        observed_primary_keys = {
            str(row["table_name"]): str(row["definition"])
            for row in constraints
            if row["constraint_type"] == "p"
        }
        if observed_primary_keys != expected_primary_keys:
            raise RuntimeError(
                "reasoning-ledger primary-key columns differ from the authority schema"
            )
        foreign_keys = [
            str(row["definition"])
            for row in constraints
            if row["constraint_type"] == "f"
        ]
        if len(foreign_keys) != 11 or any(
            "project_id" not in definition for definition in foreign_keys
        ):
            raise RuntimeError(
                "reasoning-ledger project-scoped foreign-key contract differs"
            )
        required_foreign_key_fragments = {
            "FOREIGN KEY (project_id, statement_id) REFERENCES",
            "FOREIGN KEY (project_id, statement_id, revision) REFERENCES",
            "FOREIGN KEY (project_id, evidence_id) REFERENCES",
            "FOREIGN KEY (project_id, relation_id) REFERENCES",
            "FOREIGN KEY (project_id, projection_event_id) REFERENCES",
            "FOREIGN KEY (project_id, profile_id) REFERENCES",
        }
        foreign_key_text = "\n".join(foreign_keys)
        if any(
            fragment not in foreign_key_text
            for fragment in required_foreign_key_fragments
        ) or any(
            "ON UPDATE RESTRICT ON DELETE RESTRICT" not in definition
            for definition in foreign_keys
        ):
            raise RuntimeError(
                "reasoning-ledger foreign-key definitions differ from the authority schema"
            )
        unique_constraints = {
            (str(row["table_name"]), str(row["definition"]))
            for row in constraints
            if row["constraint_type"] == "u"
        }
        expected_unique_constraints = {
            ("evidence_descriptor", "UNIQUE (project_id, content_sha256)"),
            (
                "statement_revision",
                "UNIQUE (project_id, statement_id, content_sha256)",
            ),
            (
                "statement_revision_evidence",
                "UNIQUE (project_id, statement_id, revision, ordinal)",
            ),
            (
                "relation",
                "UNIQUE (project_id, from_statement_id, from_revision, "
                "to_statement_id, to_revision, relation_type, content_sha256)",
            ),
            ("relation_evidence", "UNIQUE (project_id, relation_id, ordinal)"),
            ("embedding_profile", "UNIQUE (project_id, content_sha256)"),
        }
        if unique_constraints != expected_unique_constraints:
            raise RuntimeError(
                "reasoning-ledger unique constraints differ from the authority schema"
            )
        check_definitions = "\n".join(
            str(row["definition"])
            for row in constraints
            if row["constraint_type"] == "c"
        )
        for required in (
            "contains_forbidden_authority_key",
            "SUPERSEDES",
            "INDEX_STORAGE_REINDEXED",
            "content_sha256",
        ):
            if required not in check_definitions:
                raise RuntimeError(
                    "reasoning-ledger check-constraint contract differs: " + required
                )
        expected_check_counts = {
            "project_anchor": 5,
            "evidence_descriptor": 4,
            "statement_revision": 8,
            "statement_revision_evidence": 1,
            "relation": 5,
            "relation_evidence": 1,
            "ledger_event": 3,
            "current_projection": 1,
            "embedding_profile": 2,
            "statement_embedding": 3,
        }
        observed_check_counts: dict[str, int] = {}
        for row in constraints:
            if row["constraint_type"] == "c":
                table = str(row["table_name"])
                observed_check_counts[table] = observed_check_counts.get(table, 0) + 1
        if observed_check_counts != expected_check_counts:
            raise RuntimeError(
                "reasoning-ledger check-constraint count differs from the authority schema"
            )
        metadata = conn.execute(
            sql.SQL(
                "SELECT value FROM {table} WHERE key = 'schema_version'"
            ).format(table=self._table("schema_metadata"))
        ).fetchone()
        expected_metadata = {
            "name": "reasoning_ledger",
            "version": 3,
            "embedding_dimensions": self.embedding_dimensions,
            "authority_model": "immutable_revision_event_projection",
            "contract_signature": authority_schema_signature(
                schema=self.schema,
                embedding_dimensions=self.embedding_dimensions,
            ),
        }
        value = dict(metadata["value"] or {}) if metadata is not None else {}
        catalog_signature = value.pop("catalog_signature", None)
        if value != expected_metadata:
            raise RuntimeError(
                "reasoning-ledger schema metadata differs from the authority contract"
            )
        actual_catalog_signature = self._catalog_signature(conn)
        if catalog_signature is None:
            expected_catalog_signature = self._expected_catalog_signature(conn)
            if actual_catalog_signature != expected_catalog_signature:
                raise RuntimeError(
                    "reasoning-ledger unsigned catalog differs from the generated "
                    "version-3 authority schema"
                )
            if require_catalog_signature:
                raise RuntimeError(
                    "reasoning-ledger catalog signature has not been frozen"
                )
        elif (
            not isinstance(catalog_signature, str)
            or len(catalog_signature) != 64
            or any(
                character not in "0123456789abcdef"
                for character in catalog_signature
            )
            or catalog_signature != actual_catalog_signature
        ):
            raise RuntimeError(
                "reasoning-ledger actual catalog differs from its frozen signature"
            )
        return actual_catalog_signature

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
