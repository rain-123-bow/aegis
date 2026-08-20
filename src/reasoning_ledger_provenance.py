from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from reasoning_ledger.project import ProjectLedgerConfig
from reasoning_ledger.schema import PGVECTOR_SCHEMA, authority_schema_signature
from reasoning_ledger.store import ReasoningLedger
from reasoning_ledger.models import (
    QUERY_EMBEDDING_SOURCE_KINDS,
    canonical_embedding_sha256,
    validate_embedding,
)


class ReasoningLedgerProvenanceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VerifiedLedgerSnapshot:
    encoded: bytes
    sha256: str
    revision: int


def export_live_reasoning_ledger_snapshot(
    project_root: str | Path,
    *,
    project_id_hex: str,
) -> dict[str, Any]:
    try:
        config = ProjectLedgerConfig.load(project_root)
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ReasoningLedgerProvenanceError(
            f"reasoning ledger project configuration is invalid: {error}"
        ) from error
    if config.project_id != project_id_hex:
        raise ReasoningLedgerProvenanceError(
            "reasoning ledger project identity differs from the project Seal"
        )
    if config.project_anchor_sha256 is None:
        raise ReasoningLedgerProvenanceError(
            "reasoning ledger project configuration has no database authority anchor"
        )
    dsn = os.environ.get(config.dsn_env)
    if not dsn:
        raise ReasoningLedgerProvenanceError(
            f"reasoning ledger DSN environment variable is missing: {config.dsn_env}"
        )
    try:
        ledger = ReasoningLedger(
            dsn,
            project_id=project_id_hex,
            schema=config.schema,
            embedding_dimensions=config.embedding_dimensions,
            minimum_postgresql_major=config.minimum_postgresql_major,
            minimum_pgvector_version=config.minimum_pgvector_version,
            expected_project_anchor_sha256=config.project_anchor_sha256,
        )
        ledger.probe_contract(require_schema=True)
        snapshot = ledger.export_snapshot()
        ledger.verify_snapshot_evidence_files(
            snapshot["evidence_descriptors"],
            project_root=config.project_root,
        )
    except BaseException as error:
        raise ReasoningLedgerProvenanceError(
            f"cannot export the live reasoning ledger snapshot: {error}"
        ) from error
    if not isinstance(snapshot, dict):
        raise ReasoningLedgerProvenanceError("live reasoning ledger export is invalid")
    return snapshot


def verify_context_pack_against_live_snapshot(
    pack: Mapping[str, Any], snapshot: Mapping[str, Any]
) -> VerifiedLedgerSnapshot:
    required_sections = {
        "schema",
        "project_id",
        "database_contract",
        "statements",
        "revisions",
        "evidence_descriptors",
        "relations",
        "events",
        "current_projection",
        "embedding_profiles",
        "embedding_index",
    }
    if set(snapshot) != required_sections or snapshot.get("schema") != "aegis.reasoning_ledger.snapshot.v5" or not all(
        isinstance(snapshot[field], list)
        for field in required_sections - {"schema", "project_id", "database_contract"}
    ):
        raise ReasoningLedgerProvenanceError(
            "live reasoning ledger snapshot has invalid sections"
        )
    database_contract = snapshot["database_contract"]
    expected_database_fields = {
        "database",
        "user",
        "postgresql_major",
        "postgresql_version_num",
        "pgvector_version",
        "pgvector_schema",
        "schema",
        "schema_version",
        "embedding_dimensions",
        "schema_contract_signature",
        "catalog_signature",
        "project_anchor",
    }
    if (
        not isinstance(database_contract, Mapping)
        or set(database_contract) != expected_database_fields
        or not isinstance(database_contract.get("postgresql_major"), int)
        or database_contract["postgresql_major"] < 16
        or not isinstance(database_contract.get("postgresql_version_num"), int)
        or database_contract["postgresql_version_num"] // 10000
        != database_contract["postgresql_major"]
        or not isinstance(database_contract.get("database"), str)
        or not database_contract["database"]
        or not isinstance(database_contract.get("user"), str)
        or not database_contract["user"]
        or not isinstance(database_contract.get("pgvector_version"), str)
        or _version_tuple(database_contract["pgvector_version"]) < (0, 8, 0)
        or not isinstance(database_contract.get("pgvector_schema"), str)
        or database_contract["pgvector_schema"] != PGVECTOR_SCHEMA
        or database_contract.get("schema_version") != 3
        or not isinstance(database_contract.get("schema"), str)
        or not database_contract["schema"]
        or not isinstance(database_contract.get("embedding_dimensions"), int)
        or database_contract["embedding_dimensions"] <= 0
        or not isinstance(database_contract.get("schema_contract_signature"), str)
        or len(database_contract["schema_contract_signature"]) != 64
        or any(
            character not in "0123456789abcdef"
            for character in database_contract["schema_contract_signature"]
        )
        or database_contract["schema_contract_signature"]
        != authority_schema_signature(
            schema=database_contract["schema"],
            embedding_dimensions=database_contract["embedding_dimensions"],
        )
        or not isinstance(database_contract.get("catalog_signature"), str)
        or len(database_contract["catalog_signature"]) != 64
        or any(
            character not in "0123456789abcdef"
            for character in database_contract["catalog_signature"]
        )
    ):
        raise ReasoningLedgerProvenanceError(
            "live reasoning ledger database contract is invalid"
        )
    project_anchor = database_contract["project_anchor"]
    expected_anchor_fields = {
        "schema",
        "project_id",
        "cluster_system_identifier",
        "database_oid",
        "database_name",
        "schema_name",
        "anchor_sha256",
        "created_at",
    }
    if (
        not isinstance(project_anchor, Mapping)
        or set(project_anchor) != expected_anchor_fields
        or project_anchor.get("schema")
        != "aegis.reasoning_ledger.project_anchor.v1"
        or project_anchor.get("project_id") != snapshot.get("project_id")
        or not isinstance(project_anchor.get("cluster_system_identifier"), str)
        or not project_anchor["cluster_system_identifier"].isdigit()
        or not isinstance(project_anchor.get("database_oid"), int)
        or project_anchor["database_oid"] <= 0
        or project_anchor.get("database_name") != database_contract.get("database")
        or project_anchor.get("schema_name") != database_contract.get("schema")
        or not isinstance(project_anchor.get("anchor_sha256"), str)
        or len(project_anchor["anchor_sha256"]) != 64
        or any(
            character not in "0123456789abcdef"
            for character in project_anchor["anchor_sha256"]
        )
        or not isinstance(project_anchor.get("created_at"), str)
    ):
        raise ReasoningLedgerProvenanceError(
            "live reasoning ledger project anchor is invalid"
        )
    anchor_body = {
        key: project_anchor[key]
        for key in (
            "schema",
            "project_id",
            "cluster_system_identifier",
            "database_oid",
            "database_name",
            "schema_name",
        )
    }
    anchor_sha256 = hashlib.sha256(
        json.dumps(
            anchor_body,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if anchor_sha256 != project_anchor["anchor_sha256"]:
        raise ReasoningLedgerProvenanceError(
            "live reasoning ledger project anchor hash is invalid"
        )
    canonical_snapshot = json.dumps(
        snapshot,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(canonical_snapshot).hexdigest()
    ledger_binding = pack.get("ledger")
    if not isinstance(ledger_binding, Mapping):
        raise ReasoningLedgerProvenanceError("context pack has no ledger binding")
    if ledger_binding.get("snapshot_sha256") != digest:
        raise ReasoningLedgerProvenanceError(
            "context pack ledger hash differs from the Coordinator export"
        )
    event_ids = [
        event.get("event_id")
        for event in snapshot["events"]
        if isinstance(event, Mapping) and isinstance(event.get("event_id"), int)
    ]
    revision = max(event_ids, default=0)
    if ledger_binding.get("revision") != revision:
        raise ReasoningLedgerProvenanceError(
            "context pack ledger revision differs from the Coordinator export"
        )
    live_revisions = {
        (item.get("statement_id"), item.get("revision")): _agent_projection(item)
        for item in snapshot["revisions"]
        if isinstance(item, dict)
        and isinstance(item.get("statement_id"), str)
        and isinstance(item.get("revision"), int)
    }
    candidate_revisions = [
        item.get("revision")
        for item in pack.get("candidates", [])
        if isinstance(item, Mapping)
    ]
    for item in [*candidate_revisions, *pack.get("causal_revisions", [])]:
        key = (
            item.get("statement_id") if isinstance(item, Mapping) else None,
            item.get("revision") if isinstance(item, Mapping) else None,
        )
        if not isinstance(item, dict) or live_revisions.get(key) != item:
            raise ReasoningLedgerProvenanceError(
                "context pack revision is absent or differs from the live ledger: "
                + (
                    f"{key[0]}@{key[1]}"
                    if isinstance(item, dict)
                    else "<invalid>"
                )
            )
    live_relations = {
        edge.get("relation_id"): _agent_projection(edge)
        for edge in snapshot["relations"]
        if isinstance(edge, dict) and isinstance(edge.get("relation_id"), str)
    }
    for edge in [*pack.get("relations", []), *pack.get("conflicts", [])]:
        if not isinstance(edge, dict) or live_relations.get(edge.get("relation_id")) != edge:
            raise ReasoningLedgerProvenanceError(
                "context pack relation is absent or differs from the live ledger: "
                + (
                    str(edge.get("relation_id"))
                    if isinstance(edge, dict)
                    else "<invalid>"
                )
            )
    live_evidence = {
        descriptor.get("evidence_id"): _agent_projection(descriptor)
        for descriptor in snapshot["evidence_descriptors"]
        if isinstance(descriptor, dict)
        and isinstance(descriptor.get("evidence_id"), str)
    }
    for descriptor in pack.get("evidence_descriptors", []):
        if (
            not isinstance(descriptor, dict)
            or live_evidence.get(descriptor.get("evidence_id")) != descriptor
        ):
            raise ReasoningLedgerProvenanceError(
                "context pack evidence is absent or differs from the live ledger: "
                + (
                    str(descriptor.get("evidence_id"))
                    if isinstance(descriptor, dict)
                    else "<invalid>"
                )
            )
    _verify_embedding_provenance(pack, snapshot)
    _verify_retrieval_closure(
        pack,
        live_revisions=live_revisions,
        live_relations=live_relations,
        live_evidence=live_evidence,
    )
    return VerifiedLedgerSnapshot(
        encoded=canonical_snapshot,
        sha256=digest,
        revision=revision,
    )


def _agent_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    hidden_fields = {"created_by"}
    if "evidence_id" in value:
        hidden_fields.add("source_identity")
    return {
        str(key): item
        for key, item in value.items()
        if key not in hidden_fields
    }


def _version_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError as error:
        raise ReasoningLedgerProvenanceError(
            "live reasoning ledger pgvector version is invalid"
        ) from error


def _verify_embedding_provenance(
    pack: Mapping[str, Any], snapshot: Mapping[str, Any]
) -> None:
    profiles = {
        row.get("profile_id"): row
        for row in snapshot["embedding_profiles"]
        if isinstance(row, Mapping) and isinstance(row.get("profile_id"), str)
    }
    expected_index_fields = {
        "project_id",
        "statement_id",
        "revision",
        "profile_id",
        "embedding",
        "embedded_text_sha256",
        "embedding_sha256",
        "generator_identity",
        "generation_receipt",
        "generation_receipt_sha256",
        "created_at",
    }
    index: dict[tuple[str, int, str], Mapping[str, Any]] = {}
    for row in snapshot["embedding_index"]:
        if not isinstance(row, Mapping) or set(row) != expected_index_fields:
            raise ReasoningLedgerProvenanceError(
                "reasoning ledger embedding index metadata is invalid"
            )
        if (
            not isinstance(row.get("statement_id"), str)
            or isinstance(row.get("revision"), bool)
            or not isinstance(row.get("revision"), int)
            or not isinstance(row.get("profile_id"), str)
        ):
            raise ReasoningLedgerProvenanceError(
                "reasoning ledger embedding index key is invalid"
            )
        key = (
            row["statement_id"],
            row["revision"],
            row["profile_id"],
        )
        if key in index or key[2] not in profiles:
            raise ReasoningLedgerProvenanceError(
                "reasoning ledger embedding identity is invalid"
            )
        receipt = row.get("generation_receipt")
        generator = row.get("generator_identity")
        if not isinstance(receipt, Mapping) or not isinstance(generator, Mapping):
            raise ReasoningLedgerProvenanceError(
                "reasoning ledger embedding generation receipt is invalid"
            )
        expected_receipt_fields = {
            "schema",
            "project_id",
            "statement_id",
            "revision",
            "profile_id",
            "profile_content_sha256",
            "provider",
            "model",
            "model_version",
            "embedded_text_sha256",
            "embedding_sha256",
            "embedding_encoding",
            "generator_identity",
        }
        if set(receipt) != expected_receipt_fields:
            raise ReasoningLedgerProvenanceError(
                "reasoning ledger embedding generation receipt fields are invalid"
            )
        receipt_hash = hashlib.sha256(
            json.dumps(
                dict(receipt),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        profile = profiles[key[2]]
        try:
            raw_embedding = json.loads(row["embedding"])
            dimensions = profile.get("dimensions")
            if isinstance(dimensions, bool) or not isinstance(dimensions, int):
                raise ValueError("embedding profile dimensions are invalid")
            values = validate_embedding(raw_embedding, dimensions=dimensions)
            assert values is not None
            actual_embedding_sha256 = canonical_embedding_sha256(
                values,
                dimensions=dimensions,
            )
        except (AssertionError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ReasoningLedgerProvenanceError(
                "reasoning ledger stored embedding is invalid"
            ) from error
        if (
            receipt_hash != row.get("generation_receipt_sha256")
            or receipt.get("schema") != "aegis.embedding_generation_receipt.v1"
            or receipt.get("project_id") != row.get("project_id")
            or receipt.get("statement_id") != key[0]
            or receipt.get("revision") != key[1]
            or receipt.get("profile_id") != key[2]
            or receipt.get("profile_content_sha256")
            != profile.get("content_sha256")
            or receipt.get("provider") != profile.get("provider")
            or receipt.get("model") != profile.get("model")
            or receipt.get("model_version") != profile.get("model_version")
            or receipt.get("embedded_text_sha256")
            != row.get("embedded_text_sha256")
            or receipt.get("embedding_sha256") != row.get("embedding_sha256")
            or receipt.get("embedding_encoding")
            != "ieee754-binary32-big-endian-zero-normalized-v1"
            or actual_embedding_sha256 != row.get("embedding_sha256")
            or receipt.get("generator_identity") != generator
        ):
            raise ReasoningLedgerProvenanceError(
                "reasoning ledger embedding generation receipt differs from its index row"
            )
        index[key] = row
    retrieval = pack.get("retrieval")
    trace = retrieval.get("trace") if isinstance(retrieval, Mapping) else None
    if not isinstance(trace, Mapping):
        return
    profile_id = trace.get("embedding_profile_id")
    semantic_candidates = trace.get("semantic_candidates")
    query_receipt = trace.get("embedding_query_receipt")
    if not isinstance(semantic_candidates, list):
        raise ReasoningLedgerProvenanceError(
            "reasoning context pack semantic trace is invalid"
        )
    if query_receipt is None:
        if (
            profile_id is not None
            or semantic_candidates
            or retrieval.get("mode") != "lexical_exact"
            or retrieval.get("embedding_source") != "none"
        ):
            raise ReasoningLedgerProvenanceError(
                "lexical retrieval identity differs from its absent query receipt"
            )
        return
    expected_query_fields = {
        "schema",
        "profile_id",
        "source",
        "embedding_sha256",
        "generator_identity",
    }
    source = query_receipt.get("source") if isinstance(query_receipt, Mapping) else None
    generator = (
        query_receipt.get("generator_identity")
        if isinstance(query_receipt, Mapping)
        else None
    )
    profile = profiles.get(profile_id)
    if (
        not isinstance(query_receipt, Mapping)
        or set(query_receipt) != expected_query_fields
        or query_receipt.get("schema") != "aegis.query_embedding_receipt.v1"
        or not isinstance(profile_id, str)
        or query_receipt.get("profile_id") != profile_id
        or profile is None
        or not isinstance(source, str)
        or source not in QUERY_EMBEDDING_SOURCE_KINDS
        or retrieval.get("mode") != "hybrid_exact"
        or retrieval.get("embedding_source") != source
        or not isinstance(generator, Mapping)
        or generator.get("kind") != QUERY_EMBEDDING_SOURCE_KINDS[source]
        or not isinstance(query_receipt.get("embedding_sha256"), str)
        or len(query_receipt["embedding_sha256"]) != 64
        or any(
            character not in "0123456789abcdef"
            for character in query_receipt["embedding_sha256"]
        )
    ):
        raise ReasoningLedgerProvenanceError(
            "reasoning query embedding receipt is invalid"
        )
    development_profile = (
        profile.get("provider") == "aegis-development"
        and profile.get("model") == "hashed-text-v1"
    )
    if development_profile != (source == "hash-fallback"):
        raise ReasoningLedgerProvenanceError(
            "reasoning query embedding source differs from its profile"
        )
    for value in semantic_candidates:
        if not isinstance(value, str) or "@" not in value:
            raise ReasoningLedgerProvenanceError(
                "semantic candidate identity is invalid"
            )
        statement_id, raw_revision = value.rsplit("@", 1)
        try:
            key = statement_id, int(raw_revision), str(profile_id)
        except ValueError as error:
            raise ReasoningLedgerProvenanceError(
                "semantic candidate revision is invalid"
            ) from error
        if key not in index:
            raise ReasoningLedgerProvenanceError(
                "semantic candidate has no bound embedding generation receipt: "
                + value
            )


def _revision_key(value: Mapping[str, Any]) -> tuple[str, int]:
    statement_id = value.get("statement_id")
    revision = value.get("revision")
    if not isinstance(statement_id, str) or not isinstance(revision, int):
        raise ReasoningLedgerProvenanceError(
            "reasoning context pack contains an invalid revision identity"
        )
    return statement_id, revision


def _verify_retrieval_closure(
    pack: Mapping[str, Any],
    *,
    live_revisions: Mapping[tuple[object, object], Mapping[str, Any]],
    live_relations: Mapping[object, Mapping[str, Any]],
    live_evidence: Mapping[object, Mapping[str, Any]],
) -> None:
    retrieval = pack.get("retrieval")
    if not isinstance(retrieval, Mapping):
        raise ReasoningLedgerProvenanceError(
            "context pack has no retrieval proof"
        )
    trace = retrieval.get("trace")
    if not isinstance(trace, Mapping):
        raise ReasoningLedgerProvenanceError(
            "context pack has no retrieval trace"
        )
    include_causes = retrieval.get("include_causes")
    if not isinstance(include_causes, bool):
        raise ReasoningLedgerProvenanceError(
            "context pack cause-expansion setting is invalid"
        )
    candidate_rows = pack.get("candidates")
    if not isinstance(candidate_rows, list):
        raise ReasoningLedgerProvenanceError("context pack candidates are invalid")
    candidate_keys = {
        _revision_key(row["revision"])
        for row in candidate_rows
        if isinstance(row, Mapping) and isinstance(row.get("revision"), Mapping)
    }
    if len(candidate_keys) != len(candidate_rows):
        raise ReasoningLedgerProvenanceError(
            "context pack candidate identities are incomplete"
        )
    causal_types = trace.get("causal_relations")
    max_depth = trace.get("max_causal_depth")
    if (
        not isinstance(causal_types, list)
        or any(not isinstance(value, str) for value in causal_types)
        or isinstance(max_depth, bool)
        or not isinstance(max_depth, int)
        or max_depth < 0
    ):
        raise ReasoningLedgerProvenanceError(
            "context pack causal retrieval trace is invalid"
        )
    graph_relations = [
        relation
        for relation in live_relations.values()
        if include_causes and relation.get("relation_type") in causal_types
    ]
    reached = set(candidate_keys)
    frontier = set(candidate_keys)
    for _depth in range(max_depth):
        upstream = {
            (
                str(relation.get("from_statement_id")),
                int(relation.get("from_revision")),
            )
            for relation in graph_relations
            if (
                relation.get("to_statement_id"),
                relation.get("to_revision"),
            ) in frontier
        }
        frontier = upstream - reached
        reached.update(frontier)
        if not frontier:
            break
    closure_relation_ids = {
        str(relation.get("relation_id"))
        for relation in graph_relations
        if (
            relation.get("from_statement_id"),
            relation.get("from_revision"),
        ) in reached
        and (
            relation.get("to_statement_id"),
            relation.get("to_revision"),
        ) in reached
    }
    conflict_relations = [
        relation
        for relation in live_relations.values()
        if relation.get("relation_type") in {"REFUTES", "PREVENTS"}
        and (
            (
                relation.get("from_statement_id"),
                relation.get("from_revision"),
            ) in reached
            or (
                relation.get("to_statement_id"),
                relation.get("to_revision"),
            ) in reached
        )
    ]
    conflict_relation_ids = {
        str(relation.get("relation_id")) for relation in conflict_relations
    }
    conflict_endpoints = {
        key
        for relation in conflict_relations
        for key in (
            (
                str(relation.get("from_statement_id")),
                int(relation.get("from_revision")),
            ),
            (
                str(relation.get("to_statement_id")),
                int(relation.get("to_revision")),
            ),
        )
    }
    expected_causal_keys = (reached | conflict_endpoints) - candidate_keys
    observed_causal_keys = {
        _revision_key(row)
        for row in pack.get("causal_revisions", [])
        if isinstance(row, Mapping)
    }
    observed_relation_ids = {
        str(row.get("relation_id"))
        for row in pack.get("relations", [])
        if isinstance(row, Mapping)
    }
    observed_conflict_ids = {
        str(row.get("relation_id"))
        for row in pack.get("conflicts", [])
        if isinstance(row, Mapping)
    }
    if (
        observed_causal_keys != expected_causal_keys
        or observed_relation_ids != closure_relation_ids
        or observed_conflict_ids != conflict_relation_ids
    ):
        raise ReasoningLedgerProvenanceError(
            "context pack omits or invents causal or conflict closure rows"
        )
    referenced_evidence = {
        str(evidence_id)
        for key in candidate_keys | expected_causal_keys
        for evidence_id in live_revisions[key].get("evidence_ids", [])
    }
    referenced_evidence.update(
        str(evidence_id)
        for relation_id in closure_relation_ids | conflict_relation_ids
        for evidence_id in live_relations[relation_id].get("evidence_ids", [])
    )
    if set(pack_evidence := [
        str(row.get("evidence_id"))
        for row in pack.get("evidence_descriptors", [])
        if isinstance(row, Mapping)
    ]) != referenced_evidence or len(pack_evidence) != len(referenced_evidence):
        raise ReasoningLedgerProvenanceError(
            "context pack evidence set differs from deterministic retrieval closure"
        )
    if any(evidence_id not in live_evidence for evidence_id in referenced_evidence):
        raise ReasoningLedgerProvenanceError(
            "context pack retrieval closure references missing evidence"
        )
