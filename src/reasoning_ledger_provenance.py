from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from reasoning_ledger.project import ProjectLedgerConfig
from reasoning_ledger.store import ReasoningLedger


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
        )
        snapshot = ledger.export_snapshot()
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
        "statements",
        "revisions",
        "evidence_descriptors",
        "relations",
        "events",
        "current_projection",
        "embedding_profiles",
    }
    if set(snapshot) != required_sections or snapshot.get("schema") != "aegis.reasoning_ledger.snapshot.v2" or not all(
        isinstance(snapshot[field], list)
        for field in required_sections - {"schema", "project_id"}
    ):
        raise ReasoningLedgerProvenanceError(
            "live reasoning ledger snapshot has invalid sections"
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
        (item.get("statement_id"), item.get("revision")): item
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
        edge.get("relation_id"): edge
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
        descriptor.get("evidence_id"): descriptor
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
    return VerifiedLedgerSnapshot(
        encoded=canonical_snapshot,
        sha256=digest,
        revision=revision,
    )
