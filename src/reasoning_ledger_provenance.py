from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from path_security import PathSecurityError, read_regular_file
from reasoning_ledger.project import PROJECT_LEDGER_CONFIG_RELATIVE_PATH
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
    root = Path(project_root).resolve()
    config_path = root / PROJECT_LEDGER_CONFIG_RELATIVE_PATH
    try:
        raw, _identity = read_regular_file(
            config_path,
            allowed_root=root,
            label="reasoning ledger project configuration",
            max_bytes=1024 * 1024,
        )
        config_data = json.loads(raw.decode("utf-8", errors="strict"))
    except (PathSecurityError, UnicodeError, json.JSONDecodeError) as error:
        raise ReasoningLedgerProvenanceError(
            f"cannot load reasoning ledger project configuration: {error}"
        ) from error
    try:
        ledger_data = config_data["ledger"]
        configured_id = str(config_data["project_id"])
        dsn_env = str(ledger_data["dsn_env"])
        schema = str(ledger_data["schema"])
        dimensions = int(ledger_data["embedding_dimensions"])
    except (KeyError, TypeError, ValueError) as error:
        raise ReasoningLedgerProvenanceError(
            "reasoning ledger project configuration is invalid"
        ) from error
    if configured_id != project_id_hex:
        raise ReasoningLedgerProvenanceError(
            "reasoning ledger project identity differs from the project Seal"
        )
    dsn = os.environ.get(dsn_env)
    if not dsn:
        raise ReasoningLedgerProvenanceError(
            f"reasoning ledger DSN environment variable is missing: {dsn_env}"
        )
    try:
        ledger = ReasoningLedger(
            dsn,
            project_id=project_id_hex,
            schema=schema,
            embedding_dimensions=dimensions,
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
    if set(snapshot) != {"items", "edges", "events"} or not all(
        isinstance(snapshot[field], list) for field in ("items", "edges", "events")
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
        event.get("id")
        for event in snapshot["events"]
        if isinstance(event, Mapping) and isinstance(event.get("id"), int)
    ]
    revision = max(event_ids, default=0)
    if ledger_binding.get("revision") != revision:
        raise ReasoningLedgerProvenanceError(
            "context pack ledger revision differs from the Coordinator export"
        )
    live_items = {
        item.get("id"): item
        for item in snapshot["items"]
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    for item in [*pack.get("items", []), *pack.get("cause_items", [])]:
        if not isinstance(item, dict) or live_items.get(item.get("id")) != item:
            raise ReasoningLedgerProvenanceError(
                f"context pack item is absent or differs from the live ledger: {item.get('id') if isinstance(item, dict) else '<invalid>'}"
            )
    live_edges = {
        edge.get("id"): edge
        for edge in snapshot["edges"]
        if isinstance(edge, dict) and isinstance(edge.get("id"), int)
    }
    for edge in pack.get("edges", []):
        if not isinstance(edge, dict) or live_edges.get(edge.get("id")) != edge:
            raise ReasoningLedgerProvenanceError(
                f"context pack edge is absent or differs from the live ledger: {edge.get('id') if isinstance(edge, dict) else '<invalid>'}"
            )
    return VerifiedLedgerSnapshot(
        encoded=canonical_snapshot,
        sha256=digest,
        revision=revision,
    )
