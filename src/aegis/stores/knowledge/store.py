from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from aegis.models import utc_now
from aegis.stores.knowledge.models import (
    AdmissionRequest,
    AdmissionResult,
    ApplicabilityProfile,
    ConflictRecord,
    EvidenceRef,
    InvalidationRequest,
    InvalidationResult,
    InvalidationRule,
    KnowledgeFact,
    KnowledgeFactDraft,
    KnowledgeQueryContext,
    KnowledgeQueryResult,
    KnowledgeStoreError,
    KnowledgeStoreWarning,
    MissingKnowledgeNeed,
    NeedRule,
    QueueRevalidationRequest,
    RejectedFact,
    RejectionRequest,
    RejectionResult,
    ResolveRevalidationRequest,
    RevalidationQueueResult,
    SupersessionRequest,
    SupersessionResult,
)


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
SCHEMA_VERSION = 1
AUTHORIZED_ADMISSION_MODULES = {"master", "knowledge_review", "store_import"}
GLOBAL_SCOPE_VALUES = {"*", "all", "any", "global", "project-wide", "all-projects"}
ACTIVE_QUERY_MODE = "active"


@dataclass(frozen=True)
class QueryVisibility:
    visible: bool
    reason: str | None = None


class KnowledgeStore:
    """SQLite-backed project-local verified fact store."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def put_candidate(self, fact: KnowledgeFactDraft) -> int:
        now = utc_now()
        strict_hash = _strict_content_hash(fact)
        identity_hash = _fact_identity_hash(fact)
        fingerprint = _semantic_fingerprint(fact)

        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                duplicate = conn.execute(
                    """
                    SELECT knowledge_id
                    FROM knowledge_facts
                    WHERE fact_identity_hash = ? AND status IN ('candidate', 'admitted')
                    """,
                    (identity_hash,),
                ).fetchone()
                if duplicate:
                    raise KnowledgeStoreError(
                        "DUPLICATE_FACT",
                        f"knowledge fact duplicates existing fact {duplicate['knowledge_id']}",
                    )
                cursor = conn.execute(
                    """
                    INSERT INTO knowledge_facts (
                      knowledge_uuid, created_at_utc, updated_at_utc, status, fact_kind,
                      subject_kind, subject_id, subject_attributes_json, predicate,
                      object_kind, object_json, unit, qualifiers_json,
                      fact_validity_scope_json, validity_window_json, semantic_summary,
                      source_module, source_run_id, source_artifact_ref,
                      fact_identity_hash, strict_content_hash, semantic_fingerprint,
                      no_known_invalidation
                    )
                    VALUES (
                      ?, ?, ?, 'candidate', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        str(uuid4()),
                        now,
                        now,
                        fact.fact_kind,
                        fact.subject_kind,
                        fact.subject_id,
                        _canonical_json(fact.subject_attributes),
                        fact.predicate,
                        fact.object_kind,
                        _canonical_json(fact.object),
                        fact.unit,
                        _canonical_json(fact.qualifiers),
                        _canonical_json(fact.fact_validity_scope),
                        _json_or_none(fact.validity_window),
                        fact.semantic_summary,
                        fact.source_module,
                        fact.source_run_id,
                        fact.source_artifact_ref,
                        identity_hash,
                        strict_hash,
                        fingerprint,
                        1 if fact.no_known_invalidation else 0,
                    ),
                )
                knowledge_id = int(cursor.lastrowid)
                self._write_semantic_keys(conn, knowledge_id, fact.semantic_keys)
                self._write_evidence_refs(conn, knowledge_id, fact.evidence_refs)
                self._write_applicability(conn, knowledge_id, fact.applicability_profile)
                self._write_invalidation_rules(conn, knowledge_id, fact.invalidation_rules)
                self._upsert_semantic_tokens(conn, knowledge_id)
                self._upsert_fts(conn, knowledge_id)
                return knowledge_id
        except sqlite3.Error as exc:
            raise _sqlite_error("put_candidate", exc) from exc

    def get_fact(self, knowledge_id: int) -> KnowledgeFact:
        with self._connect() as conn:
            return self._load_fact(conn, knowledge_id)

    def register_need_rule(self, rule: NeedRule) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO knowledge_need_rules (
                      rule_id, required_dimension, trigger_terms_json,
                      trigger_task_intents_json, trigger_operations_json,
                      trigger_qualities_json, required_subject_kinds_json,
                      acceptable_sources_json, default_blocking_level, rationale
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rule.rule_id,
                        rule.required_dimension,
                        _canonical_json(rule.trigger_terms),
                        _canonical_json(rule.trigger_task_intents),
                        _canonical_json(rule.trigger_operations),
                        _canonical_json(rule.trigger_qualities),
                        _canonical_json(rule.required_subject_kinds),
                        _canonical_json(rule.acceptable_sources),
                        rule.default_blocking_level,
                        rule.rationale,
                    ),
                )
        except sqlite3.Error as exc:
            raise _sqlite_error("register_need_rule", exc) from exc

    def admit_fact(self, request: AdmissionRequest) -> AdmissionResult:
        if request.admitted_by_module not in AUTHORIZED_ADMISSION_MODULES:
            raise KnowledgeStoreError(
                "UNAUTHORIZED_ADMISSION_MODULE",
                f"{request.admitted_by_module} cannot admit Knowledge facts",
            )

        admitted_at = utc_now()
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                fact = self._load_fact(conn, request.knowledge_id)
                if fact.status == "admitted":
                    raise KnowledgeStoreError("ALREADY_ADMITTED", "fact is already admitted")
                if fact.status != "candidate":
                    raise KnowledgeStoreError(
                        "INVALID_ADMISSION_STATUS",
                        f"cannot admit fact in status {fact.status}",
                    )
                for ref in request.evidence_refs:
                    if not self._evidence_ref_exists(conn, request.knowledge_id, ref.ref_type, ref.ref_id):
                        raise KnowledgeStoreError(
                            "ADMISSION_EVIDENCE_NOT_REGISTERED",
                            "admission evidence ref is not registered for this fact",
                            context={"ref_type": ref.ref_type, "ref_id": ref.ref_id},
                        )

                conn.execute(
                    """
                    UPDATE knowledge_facts
                    SET status = 'admitted', updated_at_utc = ?
                    WHERE knowledge_id = ?
                    """,
                    (admitted_at, request.knowledge_id),
                )
                conn.execute(
                    """
                    INSERT INTO knowledge_admission_records (
                      knowledge_id, admitted_at_utc, admitted_by_module,
                      admission_run_id, admission_method, rationale
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request.knowledge_id,
                        admitted_at,
                        request.admitted_by_module,
                        request.admission_run_id,
                        request.admission_method,
                        request.rationale,
                    ),
                )
                for ref in request.evidence_refs:
                    conn.execute(
                        """
                        INSERT INTO knowledge_admission_evidence_refs (
                          knowledge_id, ref_type, ref_id
                        )
                        VALUES (?, ?, ?)
                        """,
                        (request.knowledge_id, ref.ref_type, ref.ref_id),
                    )
                self._detect_conflicts_for_fact(conn, request.knowledge_id)
                return AdmissionResult(knowledge_id=request.knowledge_id, admitted_at_utc=admitted_at)
        except sqlite3.Error as exc:
            raise _sqlite_error("admit_fact", exc) from exc

    def reject_candidate(self, request: RejectionRequest) -> RejectionResult:
        rejected_at = utc_now()
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                fact = self._load_fact(conn, request.knowledge_id)
                if fact.status != "candidate":
                    raise KnowledgeStoreError(
                        "INVALID_REJECTION_STATUS",
                        f"cannot reject fact in status {fact.status}",
                    )
                conn.execute(
                    """
                    UPDATE knowledge_facts
                    SET status = 'rejected', updated_at_utc = ?
                    WHERE knowledge_id = ?
                    """,
                    (rejected_at, request.knowledge_id),
                )
                conn.execute(
                    """
                    INSERT INTO knowledge_rejection_records (
                      knowledge_id, rejected_at_utc, rejected_by_module,
                      rejection_run_id, reason, missing_fields_json, evidence_review_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request.knowledge_id,
                        rejected_at,
                        request.rejected_by_module,
                        request.rejection_run_id,
                        request.reason,
                        _canonical_json(request.missing_fields),
                        _canonical_json(request.evidence_review),
                    ),
                )
                return RejectionResult(knowledge_id=request.knowledge_id, rejected_at_utc=rejected_at)
        except sqlite3.Error as exc:
            raise _sqlite_error("reject_candidate", exc) from exc

    def invalidate_fact(self, request: InvalidationRequest) -> InvalidationResult:
        invalidated_at = utc_now()
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                fact = self._load_fact(conn, request.knowledge_id)
                if fact.status not in {"candidate", "admitted", "deprecated"}:
                    raise KnowledgeStoreError(
                        "INVALID_INVALIDATION_STATUS",
                        f"cannot invalidate fact in status {fact.status}",
                    )
                if request.evidence_ref and not self._evidence_ref_exists(
                    conn,
                    request.knowledge_id,
                    request.evidence_ref.ref_type,
                    request.evidence_ref.ref_id,
                ):
                    raise KnowledgeStoreError(
                        "INVALIDATION_EVIDENCE_NOT_REGISTERED",
                        "invalidation evidence ref is not registered for this fact",
                    )
                if request.triggered_rule_id and not self._invalidation_rule_belongs_to_fact(
                    conn,
                    request.knowledge_id,
                    request.triggered_rule_id,
                ):
                    raise KnowledgeStoreError(
                        "INVALIDATION_RULE_NOT_OWNED_BY_FACT",
                        "triggered invalidation rule does not belong to this knowledge fact",
                        context={
                            "knowledge_id": request.knowledge_id,
                            "triggered_rule_id": request.triggered_rule_id,
                        },
                    )
                conn.execute(
                    """
                    UPDATE knowledge_facts
                    SET status = 'invalidated', updated_at_utc = ?
                    WHERE knowledge_id = ?
                    """,
                    (invalidated_at, request.knowledge_id),
                )
                conn.execute(
                    """
                    INSERT INTO knowledge_invalidation_records (
                      knowledge_id, invalidated_at_utc, invalidated_by_module,
                      invalidation_run_id, reason, triggered_rule_id,
                      evidence_ref_type, evidence_ref_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request.knowledge_id,
                        invalidated_at,
                        request.invalidated_by_module,
                        request.invalidation_run_id,
                        request.reason,
                        request.triggered_rule_id,
                        request.evidence_ref.ref_type if request.evidence_ref else None,
                        request.evidence_ref.ref_id if request.evidence_ref else None,
                    ),
                )
                return InvalidationResult(
                    knowledge_id=request.knowledge_id,
                    invalidated_at_utc=invalidated_at,
                )
        except sqlite3.Error as exc:
            raise _sqlite_error("invalidate_fact", exc) from exc

    def supersede_fact(self, request: SupersessionRequest) -> SupersessionResult:
        superseded_at = utc_now()
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                self._validate_supersession(conn, request)
                conn.execute(
                    """
                    UPDATE knowledge_facts
                    SET status = 'superseded', updated_at_utc = ?
                    WHERE knowledge_id = ?
                    """,
                    (superseded_at, request.old_knowledge_id),
                )
                conn.execute(
                    """
                    INSERT INTO knowledge_supersession_records (
                      old_knowledge_id, new_knowledge_id, superseded_at_utc,
                      superseded_by_module, supersession_run_id, reason
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request.old_knowledge_id,
                        request.new_knowledge_id,
                        superseded_at,
                        request.superseded_by_module,
                        request.supersession_run_id,
                        request.reason,
                    ),
                )
                return SupersessionResult(
                    old_knowledge_id=request.old_knowledge_id,
                    new_knowledge_id=request.new_knowledge_id,
                    superseded_at_utc=superseded_at,
                )
        except sqlite3.Error as exc:
            raise _sqlite_error("supersede_fact", exc) from exc

    def query(self, context: KnowledgeQueryContext) -> KnowledgeQueryResult:
        with self._connect() as conn:
            rejected: dict[int, str] = {}
            query_plan: dict[str, object] = {
                "applicability_index_used": True,
                "fts_used": False,
                "fts_failed": False,
                "fallback_token_lookup_used": False,
                "embedding_used": False,
                "degraded_recall": False,
                "full_scan_used": False,
                "missing_need_rules_checked": True,
                "historical_mode": context.mode != ACTIVE_QUERY_MODE,
            }
            mandatory_ids = self._mandatory_fact_ids(conn, context, rejected)
            supplemental_ids, warnings, supplemental_plan = self._supplemental_fact_ids(conn, context)
            query_plan.update(supplemental_plan)
            active_supplemental = []
            for fact_id in supplemental_ids:
                if fact_id in mandatory_ids:
                    continue
                visibility = self._query_visibility(conn, fact_id, context)
                if visibility.visible:
                    active_supplemental.append(fact_id)
                elif visibility.reason:
                    if (
                        visibility.reason == "fact_validity_scope_mismatch"
                        and _any_exact_overlap(
                            self._load_profile(conn, fact_id).exclude_when,
                            _context_terms(context),
                        )
                    ):
                        rejected[fact_id] = "excluded_by_applicability_profile"
                    else:
                        rejected[fact_id] = visibility.reason
            missing = self._missing_knowledge_needs(conn, context)
            query_plan["degraded_recall"] = bool(warnings)

            return KnowledgeQueryResult(
                mandatory_facts=[self._load_fact(conn, fact_id) for fact_id in mandatory_ids],
                supplemental_facts=[self._load_fact(conn, fact_id) for fact_id in active_supplemental],
                rejected_facts=[
                    RejectedFact(knowledge_id=fact_id, reason=reason)
                    for fact_id, reason in sorted(rejected.items())
                ],
                missing_knowledge_needs=missing,
                degraded_recall_warnings=warnings,
                query_plan=query_plan,
            )

    def list_conflicts(self, status: str = "open") -> list[ConflictRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT conflict_id, left_knowledge_id, right_knowledge_id,
                       detected_at_utc, conflict_reason, status
                FROM knowledge_conflict_records
                WHERE status = ?
                ORDER BY detected_at_utc, conflict_id
                """,
                (status,),
            ).fetchall()
        return [ConflictRecord(**dict(row)) for row in rows]

    def queue_revalidation(self, request: QueueRevalidationRequest) -> RevalidationQueueResult:
        queued_at = utc_now()
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                self._load_fact(conn, request.knowledge_id)
                existing = conn.execute(
                    """
                    SELECT queue_id, status
                    FROM knowledge_revalidation_queue
                    WHERE knowledge_id = ?
                      AND trigger_type = ?
                      AND COALESCE(triggered_by_ref, '') = COALESCE(?, '')
                      AND status IN ('pending', 'in_progress')
                    ORDER BY queued_at_utc
                    LIMIT 1
                    """,
                    (
                        request.knowledge_id,
                        request.trigger_type,
                        request.triggered_by_ref,
                    ),
                ).fetchone()
                if existing:
                    return RevalidationQueueResult(
                        queue_id=existing["queue_id"],
                        knowledge_id=request.knowledge_id,
                        status=existing["status"],
                        created=False,
                    )
                queue_id = f"revalidation-{uuid4().hex[:12]}"
                conn.execute(
                    """
                    INSERT INTO knowledge_revalidation_queue (
                      queue_id, knowledge_id, trigger_type, triggered_by_ref,
                      queued_at_utc, reason, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 'pending')
                    """,
                    (
                        queue_id,
                        request.knowledge_id,
                        request.trigger_type,
                        request.triggered_by_ref,
                        queued_at,
                        request.reason,
                    ),
                )
                return RevalidationQueueResult(
                    queue_id=queue_id,
                    knowledge_id=request.knowledge_id,
                    status="pending",
                    created=True,
                )
        except sqlite3.Error as exc:
            raise _sqlite_error("queue_revalidation", exc) from exc

    def resolve_revalidation(
        self,
        request: ResolveRevalidationRequest,
    ) -> RevalidationQueueResult:
        return self._set_revalidation_status(
            request.queue_id,
            "resolved",
            request.resolution_rationale,
        )

    def cancel_revalidation(
        self,
        request: ResolveRevalidationRequest,
    ) -> RevalidationQueueResult:
        return self._set_revalidation_status(
            request.queue_id,
            "cancelled",
            request.resolution_rationale,
        )

    def fail_revalidation(
        self,
        request: ResolveRevalidationRequest,
    ) -> RevalidationQueueResult:
        return self._set_revalidation_status(
            request.queue_id,
            "failed",
            request.resolution_rationale,
        )

    def backup_to(self, backup_path: str | Path) -> None:
        backup = Path(backup_path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._connect() as source:
                with sqlite3.connect(backup) as target:
                    source.backup(target)
        except sqlite3.Error as exc:
            raise _sqlite_error("backup_to", exc) from exc

    def integrity_check(self) -> dict[str, object]:
        with self._connect() as conn:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_keys = [tuple(row) for row in conn.execute("PRAGMA foreign_key_check").fetchall()]
        return {"integrity_check": integrity, "foreign_key_violations": foreign_keys}

    def rebuild_indexes(self) -> int:
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                self._ensure_fts(conn)
                conn.execute("DELETE FROM knowledge_facts_fts")
                ids = [
                    int(row["knowledge_id"])
                    for row in conn.execute("SELECT knowledge_id FROM knowledge_facts")
                ]
                for knowledge_id in ids:
                    self._upsert_semantic_tokens(conn, knowledge_id)
                    self._upsert_fts(conn, knowledge_id)
                return len(ids)
        except sqlite3.Error as exc:
            raise _sqlite_error("rebuild_indexes", exc) from exc

    def _initialize(self) -> None:
        try:
            with self._connect() as conn:
                self._reject_unsupported_schema_version(conn)
                conn.execute("BEGIN IMMEDIATE")
                conn.executescript(_SCHEMA_SQL)
                self._ensure_schema_columns(conn)
                self._ensure_fts(conn)
                self._backfill_missing_semantic_tokens(conn)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO schema_migrations(version, name, applied_at_utc)
                    VALUES (?, 'knowledge_store_v1', ?)
                    """,
                    (SCHEMA_VERSION, utc_now()),
                )
        except sqlite3.Error as exc:
            raise _sqlite_error("initialize", exc) from exc

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _ensure_schema_columns(self, conn: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(knowledge_facts)").fetchall()
        }
        if "no_known_invalidation" not in columns:
            conn.execute(
                """
                ALTER TABLE knowledge_facts
                ADD COLUMN no_known_invalidation INTEGER NOT NULL DEFAULT 0
                """
            )

    def _reject_unsupported_schema_version(self, conn: sqlite3.Connection) -> None:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
        if not exists:
            return
        row = conn.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
        version = row["version"] if row else None
        if version and int(version) > SCHEMA_VERSION:
            raise KnowledgeStoreError(
                "UNSUPPORTED_SCHEMA_VERSION",
                f"database schema version {version} is newer than supported {SCHEMA_VERSION}",
            )

    def _ensure_fts(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_facts_fts USING fts5(
              knowledge_id UNINDEXED,
              semantic_summary,
              semantic_keys,
              subject_terms,
              predicate_terms,
              object_terms,
              applicability_terms,
              scope_terms,
              condition_terms,
              invalidation_terms
            )
            """
        )

    def _write_semantic_keys(
        self,
        conn: sqlite3.Connection,
        knowledge_id: int,
        semantic_keys: list[str],
    ) -> None:
        for key in sorted(set(semantic_keys)):
            if key.strip():
                conn.execute(
                    "INSERT INTO knowledge_semantic_keys(knowledge_id, semantic_key) VALUES (?, ?)",
                    (knowledge_id, key),
                )

    def _upsert_semantic_tokens(self, conn: sqlite3.Connection, knowledge_id: int) -> None:
        fact = conn.execute(
            """
            SELECT semantic_summary, subject_kind, subject_id, predicate, object_json
            FROM knowledge_facts
            WHERE knowledge_id = ?
            """,
            (knowledge_id,),
        ).fetchone()
        if not fact:
            raise KnowledgeStoreError("FACT_NOT_FOUND", f"knowledge fact {knowledge_id} does not exist")

        semantic_key_tokens: set[str] = set()
        for row in conn.execute(
            "SELECT semantic_key FROM knowledge_semantic_keys WHERE knowledge_id = ?",
            (knowledge_id,),
        ):
            semantic_key_tokens.update(_tokenize(row["semantic_key"]))

        applicability_tokens = {
            row["term"]
            for row in conn.execute(
                """
                SELECT term
                FROM knowledge_applicability_terms
                WHERE knowledge_id = ?
                  AND term_kind IN (
                    'entity',
                    'operation',
                    'quality',
                    'condition',
                    'risk_class',
                    'task_intent',
                    'lifecycle_phase',
                    'must_consider'
                  )
                """,
                (knowledge_id,),
            )
        }

        token_groups = {
            "summary": _tokenize(fact["semantic_summary"]),
            "semantic_key": semantic_key_tokens,
            "subject": _tokenize(f"{fact['subject_kind']} {fact['subject_id']}"),
            "predicate": _tokenize(fact["predicate"]),
            "object": _tokenize(fact["object_json"]),
            "applicability": applicability_tokens,
        }
        conn.execute("DELETE FROM knowledge_semantic_tokens WHERE knowledge_id = ?", (knowledge_id,))
        for source, tokens in token_groups.items():
            for token in sorted(tokens):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO knowledge_semantic_tokens (
                      knowledge_id, token, source
                    )
                    VALUES (?, ?, ?)
                    """,
                    (knowledge_id, token, source),
                )

    def _backfill_missing_semantic_tokens(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT knowledge_id
            FROM knowledge_facts AS facts
            WHERE NOT EXISTS (
              SELECT 1
              FROM knowledge_semantic_tokens AS tokens
              WHERE tokens.knowledge_id = facts.knowledge_id
            )
            ORDER BY knowledge_id
            """
        ).fetchall()
        for row in rows:
            self._upsert_semantic_tokens(conn, int(row["knowledge_id"]))

    def _write_evidence_refs(
        self,
        conn: sqlite3.Connection,
        knowledge_id: int,
        evidence_refs: list[EvidenceRef],
    ) -> None:
        for ref in evidence_refs:
            conn.execute(
                """
                INSERT INTO knowledge_evidence_refs (
                  knowledge_id, ref_type, ref_id, verifier,
                  verified_at_utc, verification_method
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    knowledge_id,
                    ref.ref_type,
                    ref.ref_id,
                    ref.verifier,
                    ref.verified_at_utc,
                    ref.verification_method,
                ),
            )

    def _write_applicability(
        self,
        conn: sqlite3.Connection,
        knowledge_id: int,
        profile: ApplicabilityProfile,
    ) -> None:
        conn.execute(
            """
            INSERT INTO knowledge_applicability_profiles (
              profile_id, knowledge_id, applicability_scope_json,
              affected_entities_json, affected_operations_json, affected_qualities_json,
              required_conditions_json, risk_classes_json, task_intents_json,
              lifecycle_phases_json, must_consider_when_json, exclude_when_json, priority
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile.profile_id,
                knowledge_id,
                _canonical_json(profile.applicability_scope),
                _canonical_json(profile.affected_entities),
                _canonical_json(profile.affected_operations),
                _canonical_json(profile.affected_qualities),
                _canonical_json(profile.required_conditions),
                _canonical_json(profile.risk_classes),
                _canonical_json(profile.task_intents),
                _canonical_json(profile.lifecycle_phases),
                _canonical_json(profile.must_consider_when),
                _canonical_json(profile.exclude_when),
                profile.priority,
            ),
        )
        term_groups = {
            "scope": _terms_from_obj(profile.applicability_scope),
            "entity": profile.affected_entities,
            "operation": profile.affected_operations,
            "quality": profile.affected_qualities,
            "condition": profile.required_conditions,
            "risk_class": profile.risk_classes,
            "task_intent": profile.task_intents,
            "lifecycle_phase": profile.lifecycle_phases,
            "must_consider": profile.must_consider_when,
            "exclude": profile.exclude_when,
        }
        for kind, terms in term_groups.items():
            for term in _expanded_terms(terms):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO knowledge_applicability_terms (
                      knowledge_id, term_kind, term, weight
                    )
                    VALUES (?, ?, ?, 1.0)
                    """,
                    (knowledge_id, kind, term),
                )

    def _write_invalidation_rules(
        self,
        conn: sqlite3.Connection,
        knowledge_id: int,
        rules: list[InvalidationRule],
    ) -> None:
        for rule in rules:
            conn.execute(
                """
                INSERT INTO knowledge_invalidation_rules (
                  rule_id, knowledge_id, invalidation_condition,
                  affected_scope_json, revalidation_required
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    rule.rule_id,
                    knowledge_id,
                    rule.invalidation_condition,
                    _canonical_json(rule.affected_scope),
                    1 if rule.revalidation_required else 0,
                ),
            )

    def _upsert_fts(self, conn: sqlite3.Connection, knowledge_id: int) -> None:
        row = conn.execute(
            """
            SELECT semantic_summary, subject_kind, subject_id, predicate, object_json,
                   fact_validity_scope_json
            FROM knowledge_facts
            WHERE knowledge_id = ?
            """,
            (knowledge_id,),
        ).fetchone()
        semantic_keys = [
            row["semantic_key"]
            for row in conn.execute(
                "SELECT semantic_key FROM knowledge_semantic_keys WHERE knowledge_id = ?",
                (knowledge_id,),
            )
        ]
        applicability_terms = [
            row["term"]
            for row in conn.execute(
                "SELECT term FROM knowledge_applicability_terms WHERE knowledge_id = ?",
                (knowledge_id,),
            )
        ]
        invalidation_terms = [
            row["invalidation_condition"]
            for row in conn.execute(
                "SELECT invalidation_condition FROM knowledge_invalidation_rules WHERE knowledge_id = ?",
                (knowledge_id,),
            )
        ]
        conn.execute("DELETE FROM knowledge_facts_fts WHERE knowledge_id = ?", (knowledge_id,))
        conn.execute(
            """
            INSERT INTO knowledge_facts_fts (
              knowledge_id, semantic_summary, semantic_keys, subject_terms, predicate_terms,
              object_terms, applicability_terms, scope_terms, condition_terms, invalidation_terms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                knowledge_id,
                row["semantic_summary"],
                " ".join(semantic_keys),
                f"{row['subject_kind']} {row['subject_id']}",
                row["predicate"],
                row["object_json"],
                " ".join(applicability_terms),
                row["fact_validity_scope_json"],
                " ".join(applicability_terms),
                " ".join(invalidation_terms),
            ),
        )

    def _load_fact(self, conn: sqlite3.Connection, knowledge_id: int) -> KnowledgeFact:
        row = conn.execute(
            """
            SELECT *
            FROM knowledge_facts
            WHERE knowledge_id = ?
            """,
            (knowledge_id,),
        ).fetchone()
        if not row:
            raise KnowledgeStoreError("FACT_NOT_FOUND", f"knowledge fact {knowledge_id} does not exist")

        semantic_keys = [
            item["semantic_key"]
            for item in conn.execute(
                "SELECT semantic_key FROM knowledge_semantic_keys WHERE knowledge_id = ?",
                (knowledge_id,),
            )
        ]
        evidence_refs = [
            EvidenceRef(
                ref_type=item["ref_type"],
                ref_id=item["ref_id"],
                verifier=item["verifier"],
                verified_at_utc=item["verified_at_utc"],
                verification_method=item["verification_method"],
            )
            for item in conn.execute(
                """
                SELECT ref_type, ref_id, verifier, verified_at_utc, verification_method
                FROM knowledge_evidence_refs
                WHERE knowledge_id = ?
                ORDER BY ref_type, ref_id
                """,
                (knowledge_id,),
            )
        ]
        profile = self._load_profile(conn, knowledge_id)
        invalidation_rules = [
            InvalidationRule(
                rule_id=item["rule_id"],
                invalidation_condition=item["invalidation_condition"],
                affected_scope=_loads(item["affected_scope_json"]),
                revalidation_required=bool(item["revalidation_required"]),
            )
            for item in conn.execute(
                """
                SELECT rule_id, invalidation_condition, affected_scope_json, revalidation_required
                FROM knowledge_invalidation_rules
                WHERE knowledge_id = ?
                ORDER BY rule_id
                """,
                (knowledge_id,),
            )
        ]
        return KnowledgeFact(
            knowledge_id=knowledge_id,
            knowledge_uuid=row["knowledge_uuid"],
            created_at_utc=row["created_at_utc"],
            updated_at_utc=row["updated_at_utc"],
            status=row["status"],
            fact_kind=row["fact_kind"],
            subject_kind=row["subject_kind"],
            subject_id=row["subject_id"],
            subject_attributes=_loads(row["subject_attributes_json"]),
            predicate=row["predicate"],
            object_kind=row["object_kind"],
            object=_loads(row["object_json"]),
            unit=row["unit"],
            qualifiers=_loads(row["qualifiers_json"]),
            fact_validity_scope=_loads(row["fact_validity_scope_json"]),
            validity_window=_loads(row["validity_window_json"]) if row["validity_window_json"] else None,
            semantic_summary=row["semantic_summary"],
            semantic_keys=semantic_keys,
            source_module=row["source_module"],
            source_run_id=row["source_run_id"],
            source_artifact_ref=row["source_artifact_ref"],
            fact_identity_hash=row["fact_identity_hash"],
            strict_content_hash=row["strict_content_hash"],
            semantic_fingerprint=row["semantic_fingerprint"],
            no_known_invalidation=bool(row["no_known_invalidation"]),
            evidence_refs=evidence_refs,
            applicability_profile=profile,
            invalidation_rules=invalidation_rules,
        )

    def _load_profile(self, conn: sqlite3.Connection, knowledge_id: int) -> ApplicabilityProfile:
        row = conn.execute(
            """
            SELECT *
            FROM knowledge_applicability_profiles
            WHERE knowledge_id = ?
            """,
            (knowledge_id,),
        ).fetchone()
        if not row:
            raise KnowledgeStoreError("PROFILE_NOT_FOUND", "applicability profile is missing")
        return ApplicabilityProfile(
            profile_id=row["profile_id"],
            applicability_scope=_loads(row["applicability_scope_json"]),
            affected_entities=_loads(row["affected_entities_json"]),
            affected_operations=_loads(row["affected_operations_json"]),
            affected_qualities=_loads(row["affected_qualities_json"]),
            required_conditions=_loads(row["required_conditions_json"]),
            risk_classes=_loads(row["risk_classes_json"]),
            task_intents=_loads(row["task_intents_json"]),
            lifecycle_phases=_loads(row["lifecycle_phases_json"]),
            must_consider_when=_loads(row["must_consider_when_json"]),
            exclude_when=_loads(row["exclude_when_json"]),
            priority=row["priority"],
        )

    def _evidence_ref_exists(
        self,
        conn: sqlite3.Connection,
        knowledge_id: int,
        ref_type: str,
        ref_id: str,
    ) -> bool:
        return (
            conn.execute(
                """
                SELECT 1
                FROM knowledge_evidence_refs
                WHERE knowledge_id = ? AND ref_type = ? AND ref_id = ?
                """,
                (knowledge_id, ref_type, ref_id),
            ).fetchone()
            is not None
        )

    def _invalidation_rule_belongs_to_fact(
        self,
        conn: sqlite3.Connection,
        knowledge_id: int,
        rule_id: str,
    ) -> bool:
        return (
            conn.execute(
                """
                SELECT 1
                FROM knowledge_invalidation_rules
                WHERE knowledge_id = ? AND rule_id = ?
                """,
                (knowledge_id, rule_id),
            ).fetchone()
            is not None
        )

    def _query_visibility(
        self,
        conn: sqlite3.Connection,
        knowledge_id: int,
        context: KnowledgeQueryContext,
        *,
        require_active: bool = False,
    ) -> QueryVisibility:
        row = conn.execute(
            """
            SELECT status, fact_validity_scope_json
            FROM knowledge_facts
            WHERE knowledge_id = ?
            """,
            (knowledge_id,),
        ).fetchone()
        if not row:
            return QueryVisibility(False, "fact_not_found")

        pending = self._has_pending_revalidation(conn, knowledge_id)
        if pending and context.mode == ACTIVE_QUERY_MODE:
            return QueryVisibility(False, "pending_revalidation")

        status = row["status"]
        status_visible = _status_visible_in_mode(status, context.mode)
        if require_active and status != "admitted":
            return QueryVisibility(False, _status_rejection_reason(status))
        if not status_visible:
            return QueryVisibility(False, _status_rejection_reason(status))

        if status == "admitted" and not _fact_validity_scope_matches(
            _loads(row["fact_validity_scope_json"]),
            context,
        ):
            return QueryVisibility(False, "fact_validity_scope_mismatch")
        return QueryVisibility(True)

    def _has_pending_revalidation(self, conn: sqlite3.Connection, knowledge_id: int) -> bool:
        return (
            conn.execute(
                """
                SELECT 1
                FROM knowledge_revalidation_queue
                WHERE knowledge_id = ? AND status IN ('pending', 'in_progress')
                """,
                (knowledge_id,),
            ).fetchone()
            is not None
        )

    def _set_revalidation_status(
        self,
        queue_id: str,
        status: str,
        rationale: str,
    ) -> RevalidationQueueResult:
        resolved_at = utc_now()
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    """
                    SELECT queue_id, knowledge_id
                    FROM knowledge_revalidation_queue
                    WHERE queue_id = ?
                    """,
                    (queue_id,),
                ).fetchone()
                if not row:
                    raise KnowledgeStoreError(
                        "REVALIDATION_QUEUE_NOT_FOUND",
                        f"revalidation queue item {queue_id} does not exist",
                    )
                conn.execute(
                    """
                    UPDATE knowledge_revalidation_queue
                    SET status = ?, resolved_at_utc = ?, resolution_rationale = ?
                    WHERE queue_id = ?
                    """,
                    (status, resolved_at, rationale, queue_id),
                )
                return RevalidationQueueResult(
                    queue_id=queue_id,
                    knowledge_id=int(row["knowledge_id"]),
                    status=status,
                    created=False,
                )
        except sqlite3.Error as exc:
            raise _sqlite_error("set_revalidation_status", exc) from exc

    def _mandatory_fact_ids(
        self,
        conn: sqlite3.Connection,
        context: KnowledgeQueryContext,
        rejected: dict[int, str],
    ) -> list[int]:
        context_terms = _context_terms(context)
        candidate_rows = conn.execute(
            """
            SELECT DISTINCT knowledge_id
            FROM knowledge_applicability_terms
            WHERE term IN ({})
            ORDER BY knowledge_id
            """.format(",".join("?" for _ in context_terms) or "''"),
            tuple(context_terms),
        ).fetchall()
        ids: list[int] = []
        for row in candidate_rows:
            knowledge_id = int(row["knowledge_id"])
            profile = self._load_profile(conn, knowledge_id)
            visibility = self._query_visibility(conn, knowledge_id, context, require_active=True)
            if not visibility.visible:
                if visibility.reason:
                    if (
                        visibility.reason == "fact_validity_scope_mismatch"
                        and _any_exact_overlap(profile.exclude_when, context_terms)
                    ):
                        rejected[knowledge_id] = "excluded_by_applicability_profile"
                    else:
                        rejected[knowledge_id] = visibility.reason
                continue
            if _any_exact_overlap(profile.exclude_when, context_terms):
                rejected[knowledge_id] = "excluded_by_applicability_profile"
                continue
            if not _applicability_scope_matches(profile.applicability_scope, context):
                rejected[knowledge_id] = "scope_mismatch"
                continue
            if not set(_normalize_many(profile.required_conditions)).issubset(context_terms):
                rejected[knowledge_id] = "missing_required_conditions"
                continue
            if _is_mandatory_match(profile, context, context_terms):
                ids.append(knowledge_id)
        return ids

    def _supplemental_fact_ids(
        self,
        conn: sqlite3.Connection,
        context: KnowledgeQueryContext,
    ) -> tuple[list[int], list[KnowledgeStoreWarning], dict[str, object]]:
        tokens = _tokenize(" ".join(context.query_terms))
        plan = {
            "fts_used": False,
            "fts_failed": False,
            "fallback_token_lookup_used": False,
        }
        if not tokens:
            return [], [], plan
        warnings: list[KnowledgeStoreWarning] = []
        scored: dict[int, float] = {}
        try:
            for token in tokens:
                rows = conn.execute(
                    """
                    SELECT knowledge_id
                    FROM knowledge_facts_fts
                    WHERE knowledge_facts_fts MATCH ?
                    LIMIT 50
                    """,
                    (_fts_token(token),),
                ).fetchall()
                plan["fts_used"] = True
                for row in rows:
                    scored[int(row["knowledge_id"])] = scored.get(int(row["knowledge_id"]), 0.0) + 2.0
        except sqlite3.OperationalError:
            plan["fts_failed"] = True
            warnings.append(
                KnowledgeStoreWarning(
                    code="FTS_INDEX_UNAVAILABLE",
                    message="knowledge_facts_fts is unavailable; using deterministic fallback recall",
                )
            )
        placeholders = ",".join("?" for _ in tokens)
        plan["fallback_token_lookup_used"] = True
        fallback_rows = conn.execute(
            f"""
            SELECT knowledge_id, COUNT(*) AS token_hits
            FROM knowledge_semantic_tokens
            WHERE token IN ({placeholders})
            GROUP BY knowledge_id
            ORDER BY token_hits DESC, knowledge_id
            LIMIT 100
            """,
            tuple(tokens),
        ).fetchall()
        for row in fallback_rows:
            scored[int(row["knowledge_id"])] = (
                scored.get(int(row["knowledge_id"]), 0.0) + float(row["token_hits"])
            )
        ordered = [
            knowledge_id
            for knowledge_id, _score in sorted(scored.items(), key=lambda item: (-item[1], item[0]))
        ]
        return ordered, warnings, plan

    def _missing_knowledge_needs(
        self,
        conn: sqlite3.Connection,
        context: KnowledgeQueryContext,
    ) -> list[MissingKnowledgeNeed]:
        context_terms = _context_terms(context).union(_tokenize(" ".join(context.query_terms)))
        rows = conn.execute(
            """
            SELECT *
            FROM knowledge_need_rules
            ORDER BY rule_id
            """
        ).fetchall()
        needs: list[MissingKnowledgeNeed] = []
        for row in rows:
            rule_terms = set(_normalize_many(_loads(row["trigger_terms_json"])))
            rule_intents = set(_normalize_many(_loads(row["trigger_task_intents_json"])))
            rule_operations = set(_normalize_many(_loads(row["trigger_operations_json"])))
            rule_qualities = set(_normalize_many(_loads(row["trigger_qualities_json"])))
            if not (
                rule_terms.intersection(context_terms)
                or rule_intents.intersection(_normalize_many(context.task_intents))
                or rule_operations.intersection(_normalize_many(context.operations))
                or rule_qualities.intersection(_normalize_many(context.qualities))
            ):
                continue
            subject_kinds = _loads(row["required_subject_kinds_json"])
            if self._need_rule_satisfied(conn, row, context, subject_kinds):
                continue
            needs.append(
                MissingKnowledgeNeed(
                    need_id=f"need-{uuid4().hex[:12]}",
                    rule_id=row["rule_id"],
                    required_dimension=row["required_dimension"],
                    subject_kind=subject_kinds[0] if subject_kinds else "other",
                    why_needed=row["rationale"],
                    blocking_level=row["default_blocking_level"],
                    acceptable_sources=_loads(row["acceptable_sources_json"]),
                )
            )
        return needs

    def _need_rule_satisfied(
        self,
        conn: sqlite3.Connection,
        rule_row: sqlite3.Row,
        context: KnowledgeQueryContext,
        subject_kinds: list[str],
    ) -> bool:
        params: list[object] = []
        subject_filter = ""
        if subject_kinds:
            placeholders = ",".join("?" for _ in subject_kinds)
            subject_filter = f"AND subject_kind IN ({placeholders})"
            params.extend(subject_kinds)
        rows = conn.execute(
            f"""
            SELECT knowledge_id, subject_kind, subject_id
            FROM knowledge_facts
            WHERE status = 'admitted'
            {subject_filter}
            ORDER BY knowledge_id
            """,
            tuple(params),
        ).fetchall()
        for row in rows:
            knowledge_id = int(row["knowledge_id"])
            if not _subject_matches_context(
                row["subject_kind"],
                row["subject_id"],
                context,
            ):
                continue
            if not self._query_visibility(conn, knowledge_id, context, require_active=True).visible:
                continue
            if self._fact_satisfies_required_dimension(
                conn,
                knowledge_id,
                str(rule_row["required_dimension"]),
            ):
                return True
        return False

    def _fact_satisfies_required_dimension(
        self,
        conn: sqlite3.Connection,
        knowledge_id: int,
        required_dimension: str,
    ) -> bool:
        dimension_tokens = _dimension_tokens(required_dimension)
        if not dimension_tokens:
            return False

        row = conn.execute(
            """
            SELECT subject_kind, subject_id, predicate, object_kind, object_json, semantic_summary
            FROM knowledge_facts
            WHERE knowledge_id = ?
            """,
            (knowledge_id,),
        ).fetchone()
        if not row:
            return False

        fact_tokens = set().union(
            _tokenize(row["subject_kind"]),
            _tokenize(row["subject_id"]),
            _tokenize(row["predicate"]),
            _tokenize(row["object_kind"]),
            _tokenize(row["object_json"]),
            _tokenize(row["semantic_summary"]),
        )
        for token_row in conn.execute(
            """
            SELECT token
            FROM knowledge_semantic_tokens
            WHERE knowledge_id = ?
            """,
            (knowledge_id,),
        ):
            fact_tokens.add(token_row["token"])

        return dimension_tokens.issubset(fact_tokens)

    def _validate_supersession(self, conn: sqlite3.Connection, request: SupersessionRequest) -> None:
        if request.old_knowledge_id == request.new_knowledge_id:
            raise KnowledgeStoreError(
                "SELF_SUPERSESSION_FORBIDDEN",
                "a knowledge fact cannot supersede itself",
            )
        old = self._load_fact(conn, request.old_knowledge_id)
        new = self._load_fact(conn, request.new_knowledge_id)
        if old.status not in {"admitted", "deprecated"}:
            raise KnowledgeStoreError(
                "INVALID_SUPERSEDED_STATUS",
                f"old fact status {old.status} cannot be superseded",
            )
        if new.status != "admitted":
            raise KnowledgeStoreError(
                "SUPERSESSION_REPLACEMENT_NOT_ADMITTED",
                f"replacement fact status {new.status} is not admitted",
            )

    def _detect_conflicts_for_fact(self, conn: sqlite3.Connection, knowledge_id: int) -> None:
        current = conn.execute(
            """
            SELECT knowledge_id, subject_kind, subject_id, predicate, object_json, fact_validity_scope_json
            FROM knowledge_facts
            WHERE knowledge_id = ? AND status = 'admitted'
            """,
            (knowledge_id,),
        ).fetchone()
        if not current:
            return
        rows = conn.execute(
            """
            SELECT knowledge_id
            FROM knowledge_facts
            WHERE status = 'admitted'
              AND knowledge_id != ?
              AND subject_kind = ?
              AND subject_id = ?
              AND predicate = ?
              AND fact_validity_scope_json = ?
              AND object_json != ?
            ORDER BY knowledge_id
            """,
            (
                knowledge_id,
                current["subject_kind"],
                current["subject_id"],
                current["predicate"],
                current["fact_validity_scope_json"],
                current["object_json"],
            ),
        ).fetchall()
        for row in rows:
            left, right = sorted([knowledge_id, int(row["knowledge_id"])])
            conflict_id = _hash_text(f"{left}:{right}:exact-scope-conflict")
            conn.execute(
                """
                INSERT OR IGNORE INTO knowledge_conflict_records (
                  conflict_id, left_knowledge_id, right_knowledge_id,
                  detected_at_utc, conflict_reason, status
                )
                VALUES (?, ?, ?, ?, ?, 'open')
                """,
                (
                    conflict_id,
                    left,
                    right,
                    utc_now(),
                    "same subject/predicate/validity scope with different canonical object",
                ),
            )


def _fact_validity_scope_matches(scope: dict[str, object], context: KnowledgeQueryContext) -> bool:
    if not scope:
        return True
    context_scope = _hard_scope_values(context)
    for dimension, raw_value in scope.items():
        scope_options = _scope_value_options(raw_value)
        if not scope_options or any(option.intersection(GLOBAL_SCOPE_VALUES) for option in scope_options):
            continue
        context_values = context_scope.get(str(dimension).lower(), set())
        if not context_values:
            return False
        if not any(_scope_option_matches(option, context_values) for option in scope_options):
            return False
    return True


def _applicability_scope_matches(scope: dict[str, object], context: KnowledgeQueryContext) -> bool:
    if not scope:
        return True
    context_scope = _context_scope_values(context)
    for dimension, raw_value in scope.items():
        scope_options = _scope_value_options(raw_value)
        if not scope_options or any(option.intersection(GLOBAL_SCOPE_VALUES) for option in scope_options):
            continue
        context_values = context_scope.get(str(dimension).lower(), set())
        context_values = set(context_values).union(_context_terms(context))
        if not context_values:
            return False
        if not any(_scope_option_matches(option, context_values) for option in scope_options):
            return False
    return True


def _is_mandatory_match(
    profile: ApplicabilityProfile,
    context: KnowledgeQueryContext,
    context_terms: set[str],
) -> bool:
    trigger_pairs = (
        (profile.must_consider_when, context_terms),
        (profile.task_intents, _normalize_many(context.task_intents)),
        (profile.affected_operations, _normalize_many(context.operations)),
        (profile.affected_qualities, _normalize_many(context.qualities)),
        (profile.risk_classes, _normalize_many(context.risk_classes)),
        (profile.affected_entities, _normalize_many(context.affected_entities)),
        (profile.lifecycle_phases, _normalize_many([context.lifecycle_phase])),
    )
    return any(_any_overlap(profile_terms, context_values) for profile_terms, context_values in trigger_pairs)


def _context_terms(context: KnowledgeQueryContext) -> set[str]:
    terms: set[str] = set()
    fields = [
        [context.project_id],
        context.task_intents,
        [context.lifecycle_phase],
        context.affected_entities,
        context.operations,
        context.qualities,
        context.conditions,
        context.risk_classes,
        context.query_terms,
    ]
    for values in fields:
        terms.update(_expanded_terms(values))
    for subject in context.subject_refs:
        terms.update(_expanded_terms(_terms_from_obj(subject)))
    return terms


def _any_overlap(left: list[str], right: set[str]) -> bool:
    return bool(_expanded_terms(left).intersection(right))


def _any_exact_overlap(left: list[str], right: set[str]) -> bool:
    return bool(_normalize_many(left).intersection(right))


def _canonical_json(value: object) -> str:
    normalized = _normalize_json_value(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _json_or_none(value: object | None) -> str | None:
    return None if value is None else _canonical_json(value)


def _loads(value: str) -> object:
    return json.loads(value)


def _strict_content_hash(fact: KnowledgeFactDraft) -> str:
    return _hash_obj(
        {
            "subject_kind": fact.subject_kind,
            "subject_id": fact.subject_id,
            "subject_attributes": fact.subject_attributes,
            "predicate": fact.predicate,
            "object_kind": fact.object_kind,
            "object": fact.object,
            "unit": fact.unit,
        }
    )


def _fact_identity_hash(fact: KnowledgeFactDraft) -> str:
    return _hash_obj(
        {
            "subject_kind": fact.subject_kind,
            "subject_id": fact.subject_id,
            "subject_attributes": fact.subject_attributes,
            "predicate": fact.predicate,
            "object_kind": fact.object_kind,
            "object": fact.object,
            "unit": fact.unit,
            "qualifiers": fact.qualifiers,
            "fact_validity_scope": fact.fact_validity_scope,
        }
    )


def _semantic_fingerprint(fact: KnowledgeFactDraft) -> str:
    return _hash_text(_normalize_text(" ".join([fact.semantic_summary, *fact.semantic_keys]).lower()))


def _hash_obj(value: object) -> str:
    return _hash_text(_canonical_json(value))


def _hash_text(value: str) -> str:
    return hashlib.sha256(_normalize_text(value).encode("utf-8")).hexdigest()


def _tokenize(text: str) -> set[str]:
    normalized = _normalize_text(text)
    tokens: set[str] = set()
    for match in TOKEN_RE.finditer(normalized):
        token = match.group(0).lower()
        tokens.add(token)
        tokens.update(part for part in token.split("_") if part)
    for match in CJK_RE.finditer(normalized):
        segment = match.group(0).lower()
        tokens.add(segment)
        tokens.update(_ngrams(segment, 2))
        tokens.update(_ngrams(segment, 3))
        if len(segment) <= 2:
            tokens.update(segment)
    return tokens


def _normalize_many(values: list[str]) -> set[str]:
    return {_normalize_text(str(value)).strip().lower() for value in values if str(value).strip()}


def _expanded_terms(values: list[str]) -> set[str]:
    terms = _normalize_many(values)
    for value in values:
        tokens = _tokenize(str(value))
        if len(tokens) > 1:
            tokens = {_token_is_decision_worthy(token) for token in tokens}
            tokens = {token for token in tokens if token}
        terms.update(tokens)
    return terms


def _token_is_decision_worthy(token: str) -> str:
    """Drop punctuation-derived one-letter fragments from compound identifiers."""
    if len(token) == 1 and token.isascii() and token.isalnum():
        return ""
    return token


def _dimension_tokens(required_dimension: str) -> set[str]:
    tokens = _tokenize(required_dimension.replace("_", " "))
    return {token for token in tokens if token not in {"target", "current", "required"}}


def _normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _normalize_json_value(value: object) -> object:
    if isinstance(value, str):
        return _normalize_text(value)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("knowledge facts cannot contain NaN or Infinity")
        return value
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {
            _normalize_text(str(key)): _normalize_json_value(item)
            for key, item in value.items()
        }
    return value


def _ngrams(value: str, size: int) -> set[str]:
    if len(value) < size:
        return set()
    return {value[index : index + size] for index in range(len(value) - size + 1)}


def _terms_from_obj(value: object) -> list[str]:
    if isinstance(value, dict):
        terms: list[str] = []
        for key, item in value.items():
            terms.append(str(key))
            terms.extend(_terms_from_obj(item))
        return terms
    if isinstance(value, list):
        terms = []
        for item in value:
            terms.extend(_terms_from_obj(item))
        return terms
    if value is None:
        return []
    return [str(value)]


HARD_SCOPE_IDENTITY_DIMENSIONS = {
    "host",
    "device",
    "component",
    "runtime",
    "platform",
    "dependency",
    "customer",
    "service",
    "module",
    "file",
    "function",
    "class",
    "api",
    "schema",
    "entity",
}


def _hard_scope_values(context: KnowledgeQueryContext) -> dict[str, set[str]]:
    scope: dict[str, set[str]] = {"project": _expanded_terms([context.project_id])}
    structured_identity_terms: set[str] = set()

    for subject in context.subject_refs:
        normalized = {str(key).lower(): value for key, value in subject.items()}
        subject_kind = normalized.get("subject_kind")
        subject_id = normalized.get("subject_id")
        if subject_kind and subject_id:
            kind = str(subject_kind).strip().lower()
            subject_id_terms = _expanded_terms(_terms_from_obj(subject_id))
            scope.setdefault(kind, set()).update(subject_id_terms)
            structured_identity_terms.update(subject_id_terms)
        for key, value in normalized.items():
            scope.setdefault(str(key).strip().lower(), set()).update(
                _expanded_terms(_terms_from_obj(value))
            )

    entity_terms = _expanded_terms(context.affected_entities)
    structured_identity_terms.update(entity_terms)
    scope.setdefault("entity", set()).update(entity_terms)
    for dimension in HARD_SCOPE_IDENTITY_DIMENSIONS:
        scope.setdefault(dimension, set()).update(structured_identity_terms)

    scope.setdefault("operation", set()).update(_expanded_terms(context.operations))
    scope.setdefault("quality", set()).update(_expanded_terms(context.qualities))
    scope.setdefault("condition", set()).update(_expanded_terms(context.conditions))
    scope.setdefault("risk_class", set()).update(_expanded_terms(context.risk_classes))
    scope.setdefault("task_intent", set()).update(_expanded_terms(context.task_intents))
    scope.setdefault("lifecycle_phase", set()).update(_expanded_terms([context.lifecycle_phase]))
    return scope


def _context_scope_values(context: KnowledgeQueryContext) -> dict[str, set[str]]:
    scope: dict[str, set[str]] = {"project": {context.project_id.strip().lower()}}
    for subject in context.subject_refs:
        normalized = {str(key).lower(): value for key, value in subject.items()}
        subject_kind = normalized.get("subject_kind")
        subject_id = normalized.get("subject_id")
        if subject_kind and subject_id:
            scope.setdefault(str(subject_kind).strip().lower(), set()).update(
                _expanded_terms(_terms_from_obj(subject_id))
            )
        for key, value in normalized.items():
            scope.setdefault(str(key).strip().lower(), set()).update(
                _expanded_terms(_terms_from_obj(value))
            )
    scope.setdefault("entity", set()).update(_expanded_terms(context.affected_entities))
    scope.setdefault("condition", set()).update(_expanded_terms(context.conditions))
    return scope


def _scope_value_options(value: object) -> list[set[str]]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_expanded_terms(_terms_from_obj(item)) for item in value]
    if isinstance(value, dict):
        return [_expanded_terms(_terms_from_obj(value))]
    return [_expanded_terms(_terms_from_obj(value))]


def _scope_option_matches(option: set[str], context_values: set[str]) -> bool:
    if not option:
        return True
    if option.intersection(GLOBAL_SCOPE_VALUES):
        return True
    return option.issubset(context_values)


def _subject_matches_context(
    subject_kind: str,
    subject_id: str,
    context: KnowledgeQueryContext,
) -> bool:
    matching_refs = [
        ref
        for ref in context.subject_refs
        if str(ref.get("subject_kind", "")).strip().lower() == subject_kind.strip().lower()
    ]
    if not matching_refs:
        return True
    subject_tokens = _expanded_terms([subject_id])
    for ref in matching_refs:
        ref_id = ref.get("subject_id")
        if ref_id is None:
            continue
        ref_tokens = _expanded_terms(_terms_from_obj(ref_id))
        if subject_tokens.issubset(ref_tokens) or ref_tokens.issubset(subject_tokens):
            return True
    return False


def _status_visible_in_mode(status: str, mode: str) -> bool:
    if mode == "active":
        return status == "admitted"
    if mode in {"historical", "review"}:
        return status in {
            "candidate",
            "admitted",
            "rejected",
            "invalidated",
            "deprecated",
            "superseded",
        }
    if mode == "include_rejected":
        return status == "rejected"
    if mode == "include_invalidated":
        return status == "invalidated"
    if mode == "include_superseded":
        return status == "superseded"
    return False


def _status_rejection_reason(status: str) -> str:
    return {
        "candidate": "status_candidate",
        "rejected": "rejected",
        "invalidated": "invalidated",
        "deprecated": "deprecated",
        "superseded": "superseded",
    }.get(status, "status_not_admitted")


def _fts_token(token: str) -> str:
    escaped = token.replace('"', '""')
    return f'"{escaped}"'


def _sqlite_error(operation: str, exc: sqlite3.Error) -> KnowledgeStoreError:
    if isinstance(exc, sqlite3.IntegrityError):
        message = str(exc)
        if "idx_knowledge_fact_identity_active" in message or "fact_identity_hash" in message:
            return KnowledgeStoreError(
                "DUPLICATE_FACT",
                "knowledge fact identity already exists for an active fact",
                cause=exc,
            )
        return KnowledgeStoreError(
            "SQLITE_INTEGRITY_ERROR",
            f"{operation} violated SQLite integrity constraints: {exc}",
            cause=exc,
        )
    return KnowledgeStoreError("SQLITE_ERROR", f"{operation} failed: {exc}", cause=exc)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_facts (
  knowledge_id INTEGER PRIMARY KEY,
  knowledge_uuid TEXT NOT NULL UNIQUE,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  status TEXT NOT NULL,
  fact_kind TEXT NOT NULL,
  subject_kind TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  subject_attributes_json TEXT NOT NULL,
  predicate TEXT NOT NULL,
  object_kind TEXT NOT NULL,
  object_json TEXT NOT NULL,
  unit TEXT,
  qualifiers_json TEXT NOT NULL,
  fact_validity_scope_json TEXT NOT NULL,
  validity_window_json TEXT,
  semantic_summary TEXT NOT NULL,
  source_module TEXT NOT NULL,
  source_run_id TEXT,
  source_artifact_ref TEXT,
  fact_identity_hash TEXT NOT NULL,
  strict_content_hash TEXT NOT NULL,
  semantic_fingerprint TEXT,
  no_known_invalidation INTEGER NOT NULL DEFAULT 0,
  CHECK (no_known_invalidation IN (0, 1)),
  CHECK (status IN (
    'candidate',
    'admitted',
    'rejected',
    'invalidated',
    'deprecated',
    'superseded'
  )),
  CHECK (fact_kind IN (
    'environment',
    'dependency',
    'platform',
    'customer_constraint',
    'repository_source',
    'test_result',
    'policy',
    'interface',
    'configuration',
    'business_rule',
    'other'
  )),
  CHECK (subject_kind IN (
    'project',
    'module',
    'file',
    'function',
    'class',
    'dependency',
    'runtime',
    'platform',
    'customer',
    'device',
    'host',
    'service',
    'api',
    'schema',
    'other'
  )),
  CHECK (object_kind IN (
    'scalar',
    'range',
    'set',
    'object',
    'version',
    'path',
    'url',
    'identifier',
    'boolean',
    'other'
  )),
  CHECK (source_module IN (
    'master',
    'debate',
    'execution',
    'test',
    'final_review',
    'knowledge_review',
    'store_import'
  ))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_fact_identity_active
ON knowledge_facts(fact_identity_hash)
WHERE status IN ('candidate', 'admitted');

CREATE INDEX IF NOT EXISTS idx_knowledge_status
ON knowledge_facts(status);

CREATE INDEX IF NOT EXISTS idx_knowledge_subject
ON knowledge_facts(subject_kind, subject_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_predicate
ON knowledge_facts(predicate);

CREATE TABLE IF NOT EXISTS knowledge_semantic_keys (
  knowledge_id INTEGER NOT NULL,
  semantic_key TEXT NOT NULL,
  PRIMARY KEY (knowledge_id, semantic_key),
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);

CREATE TABLE IF NOT EXISTS knowledge_semantic_tokens (
  knowledge_id INTEGER NOT NULL,
  token TEXT NOT NULL,
  source TEXT NOT NULL,
  PRIMARY KEY (knowledge_id, token, source),
  CHECK (source IN (
    'summary',
    'semantic_key',
    'subject',
    'predicate',
    'object',
    'applicability'
  )),
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_semantic_token
ON knowledge_semantic_tokens(token, knowledge_id);

CREATE TABLE IF NOT EXISTS knowledge_applicability_profiles (
  profile_id TEXT PRIMARY KEY,
  knowledge_id INTEGER NOT NULL,
  applicability_scope_json TEXT NOT NULL,
  affected_entities_json TEXT NOT NULL,
  affected_operations_json TEXT NOT NULL,
  affected_qualities_json TEXT NOT NULL,
  required_conditions_json TEXT NOT NULL,
  risk_classes_json TEXT NOT NULL,
  task_intents_json TEXT NOT NULL,
  lifecycle_phases_json TEXT NOT NULL,
  must_consider_when_json TEXT NOT NULL,
  exclude_when_json TEXT NOT NULL,
  priority TEXT NOT NULL,
  CHECK (priority IN ('low', 'normal', 'high', 'critical')),
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);

CREATE TABLE IF NOT EXISTS knowledge_applicability_terms (
  knowledge_id INTEGER NOT NULL,
  term_kind TEXT NOT NULL,
  term TEXT NOT NULL,
  weight REAL NOT NULL,
  PRIMARY KEY (knowledge_id, term_kind, term),
  CHECK (term_kind IN (
    'scope',
    'entity',
    'operation',
    'quality',
    'condition',
    'risk_class',
    'task_intent',
    'lifecycle_phase',
    'must_consider',
    'exclude'
  )),
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_applicability_term
ON knowledge_applicability_terms(term_kind, term, knowledge_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_applicability_term_value
ON knowledge_applicability_terms(term, knowledge_id);

CREATE TABLE IF NOT EXISTS knowledge_evidence_refs (
  knowledge_id INTEGER NOT NULL,
  ref_type TEXT NOT NULL,
  ref_id TEXT NOT NULL,
  verifier TEXT NOT NULL,
  verified_at_utc TEXT NOT NULL,
  verification_method TEXT NOT NULL,
  PRIMARY KEY (knowledge_id, ref_type, ref_id),
  CHECK (ref_type IN (
    'test',
    'external',
    'artifact',
    'customer_written',
    'platform_doc',
    'repository_source'
  )),
  CHECK (verifier IN (
    'master',
    'debate',
    'execution',
    'test',
    'final_review',
    'knowledge_review'
  )),
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_evidence_ref
ON knowledge_evidence_refs(ref_type, ref_id);

CREATE TABLE IF NOT EXISTS knowledge_admission_records (
  knowledge_id INTEGER NOT NULL,
  admitted_at_utc TEXT NOT NULL,
  admitted_by_module TEXT NOT NULL,
  admission_run_id TEXT,
  admission_method TEXT NOT NULL,
  rationale TEXT NOT NULL,
  CHECK (admitted_by_module IN ('master', 'knowledge_review', 'store_import')),
  CHECK (admission_method IN (
    'master_manual_review',
    'knowledge_review',
    'test_verified',
    'repository_inspected',
    'external_authority_verified'
  )),
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);

CREATE TABLE IF NOT EXISTS knowledge_admission_evidence_refs (
  knowledge_id INTEGER NOT NULL,
  ref_type TEXT NOT NULL,
  ref_id TEXT NOT NULL,
  PRIMARY KEY (knowledge_id, ref_type, ref_id),
  CHECK (ref_type IN (
    'test',
    'external',
    'artifact',
    'customer_written',
    'platform_doc',
    'repository_source'
  )),
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id),
  FOREIGN KEY (knowledge_id, ref_type, ref_id)
    REFERENCES knowledge_evidence_refs(knowledge_id, ref_type, ref_id)
);

CREATE TABLE IF NOT EXISTS knowledge_rejection_records (
  knowledge_id INTEGER NOT NULL,
  rejected_at_utc TEXT NOT NULL,
  rejected_by_module TEXT NOT NULL,
  rejection_run_id TEXT,
  reason TEXT NOT NULL,
  missing_fields_json TEXT NOT NULL,
  evidence_review_json TEXT NOT NULL,
  CHECK (rejected_by_module IN (
    'master',
    'debate',
    'execution',
    'test',
    'final_review',
    'knowledge_review'
  )),
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);

CREATE TABLE IF NOT EXISTS knowledge_invalidation_rules (
  rule_id TEXT PRIMARY KEY,
  knowledge_id INTEGER NOT NULL,
  invalidation_condition TEXT NOT NULL,
  affected_scope_json TEXT NOT NULL,
  revalidation_required INTEGER NOT NULL,
  CHECK (revalidation_required IN (0, 1)),
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);

CREATE TABLE IF NOT EXISTS knowledge_invalidation_records (
  knowledge_id INTEGER NOT NULL,
  invalidated_at_utc TEXT NOT NULL,
  invalidated_by_module TEXT NOT NULL,
  invalidation_run_id TEXT,
  reason TEXT NOT NULL,
  triggered_rule_id TEXT,
  evidence_ref_type TEXT,
  evidence_ref_id TEXT,
  CHECK (
    evidence_ref_type IS NULL OR evidence_ref_type IN (
      'test',
      'external',
      'artifact',
      'customer_written',
      'platform_doc',
      'repository_source'
    )
  ),
  CHECK (
    (evidence_ref_type IS NULL AND evidence_ref_id IS NULL)
    OR
    (evidence_ref_type IS NOT NULL AND evidence_ref_id IS NOT NULL)
  ),
  CHECK (invalidated_by_module IN (
    'master',
    'debate',
    'execution',
    'test',
    'final_review',
    'knowledge_review'
  )),
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id),
  FOREIGN KEY (triggered_rule_id) REFERENCES knowledge_invalidation_rules(rule_id)
);

CREATE TABLE IF NOT EXISTS knowledge_supersession_records (
  old_knowledge_id INTEGER NOT NULL,
  new_knowledge_id INTEGER NOT NULL,
  superseded_at_utc TEXT NOT NULL,
  superseded_by_module TEXT NOT NULL,
  supersession_run_id TEXT,
  reason TEXT NOT NULL,
  CHECK (old_knowledge_id != new_knowledge_id),
  CHECK (superseded_by_module IN ('master', 'knowledge_review', 'store_import')),
  FOREIGN KEY (old_knowledge_id) REFERENCES knowledge_facts(knowledge_id),
  FOREIGN KEY (new_knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);

CREATE TABLE IF NOT EXISTS knowledge_revalidation_queue (
  queue_id TEXT PRIMARY KEY,
  knowledge_id INTEGER NOT NULL,
  trigger_type TEXT NOT NULL,
  triggered_by_ref TEXT,
  queued_at_utc TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL,
  resolved_at_utc TEXT,
  resolution_rationale TEXT,
  CHECK (status IN ('pending', 'in_progress', 'resolved', 'cancelled', 'failed')),
  FOREIGN KEY (knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_revalidation_status
ON knowledge_revalidation_queue(status, knowledge_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_revalidation_active_key
ON knowledge_revalidation_queue(knowledge_id, trigger_type, triggered_by_ref, status);

CREATE TABLE IF NOT EXISTS knowledge_need_rules (
  rule_id TEXT PRIMARY KEY,
  required_dimension TEXT NOT NULL,
  trigger_terms_json TEXT NOT NULL,
  trigger_task_intents_json TEXT NOT NULL,
  trigger_operations_json TEXT NOT NULL,
  trigger_qualities_json TEXT NOT NULL,
  required_subject_kinds_json TEXT NOT NULL,
  acceptable_sources_json TEXT NOT NULL,
  default_blocking_level TEXT NOT NULL,
  rationale TEXT NOT NULL,
  CHECK (default_blocking_level IN (
    'hard_block',
    'needs_user_clarification',
    'request_test_measurement',
    'request_evidence_artifact_lookup'
  ))
);

CREATE TABLE IF NOT EXISTS knowledge_conflict_records (
  conflict_id TEXT PRIMARY KEY,
  left_knowledge_id INTEGER NOT NULL,
  right_knowledge_id INTEGER NOT NULL,
  detected_at_utc TEXT NOT NULL,
  conflict_reason TEXT NOT NULL,
  status TEXT NOT NULL,
  CHECK (status IN ('open', 'resolved', 'accepted_with_scope_split', 'dismissed')),
  FOREIGN KEY (left_knowledge_id) REFERENCES knowledge_facts(knowledge_id),
  FOREIGN KEY (right_knowledge_id) REFERENCES knowledge_facts(knowledge_id)
);
"""
