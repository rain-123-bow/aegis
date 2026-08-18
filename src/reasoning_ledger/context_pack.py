from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .models import ContextPack, LedgerEdge, LedgerItem, json_ready


def context_pack_to_markdown(
    pack: ContextPack,
    *,
    retrieval_mode: str = "unknown",
    embedding_source: str = "unknown",
    generated_at: datetime | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> str:
    generated = (generated_at or datetime.now(timezone.utc)).isoformat()
    meta = dict(metadata or {})
    lines: list[str] = [
        "# Reasoning Ledger Context Pack",
        "",
        "## Metadata",
        f"- project_id: `{pack.project_id}`",
        f"- task_id: `{pack.task_id}`",
        f"- agent_role: `{pack.agent_role}`",
        f"- generated_at: `{generated}`",
        f"- retrieval_mode: `{retrieval_mode}`",
        f"- embedding_source: `{embedding_source}`",
        "- query:",
        "",
        "```text",
        pack.query,
        "```",
        "",
    ]
    if meta:
        lines.extend(["## Runtime Metadata", ""])
        for key, value in sorted(meta.items()):
            lines.append(f"- {key}: `{_inline_json(value)}`")
        lines.append("")

    lines.extend(_items_section("Retrieved Items", pack.items))
    lines.extend(_items_section("Cause Items", pack.cause_items))
    lines.extend(_edges_section("Edges", pack.edges))
    lines.extend(_list_section("Warnings", pack.warnings))
    lines.extend(_list_section("Required Artifact Paths", pack.artifact_paths))
    lines.extend(
        [
            "## Status Semantics",
            "",
            "- `active`: valid project knowledge; may be used as evidence.",
            "- `stale`: risk signal only; must not be used as final evidence without revalidation.",
            "- `invalid`: not valid evidence.",
            "- `superseded`: replaced by newer knowledge; not valid evidence unless used for history tracing.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def context_pack_to_json_data(
    pack: ContextPack,
    *,
    retrieval_mode: str = "unknown",
    embedding_source: str = "unknown",
    generated_at: datetime | None = None,
    project_seal: str,
    engineering_documents_sha256: str,
    ledger_revision: int,
    ledger_snapshot_sha256: str,
    retrieval_scope: Mapping[str, Any],
    limit: int,
    include_causes: bool,
    coverage: Mapping[str, bool],
    project_root: str | Path,
) -> dict[str, Any]:
    generated = (generated_at or datetime.now(timezone.utc)).isoformat().replace(
        "+00:00", "Z"
    )
    root = Path(project_root).resolve()
    required_paths = list(
        dict.fromkeys(
            path
            for item in (*pack.items, *pack.cause_items)
            for path in (item.artifact_path, item.evidence_path)
            if path
        )
    )
    evidence_index: list[dict[str, object]] = []
    for relative_path in required_paths:
        path = (root / relative_path).resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise ValueError(
                f"context-pack artifact escapes the project root: {relative_path}"
            ) from error
        if not path.is_file():
            raise ValueError(
                f"context-pack artifact is missing: {relative_path}"
            )
        content = path.read_bytes()
        evidence_index.append(
            {
                "path": str(path),
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return {
        "schema": "aegis.reasoning_context_pack.v1",
        "project_id_hex": pack.project_id,
        "task_id": pack.task_id,
        "agent_role": pack.agent_role,
        "query": pack.query,
        "generated_at_utc": generated,
        "bindings": {
            "project_seal": project_seal,
            "engineering_documents_sha256": engineering_documents_sha256,
        },
        "ledger": {
            "revision": ledger_revision,
            "snapshot_sha256": ledger_snapshot_sha256,
        },
        "retrieval": {
            "mode": retrieval_mode,
            "embedding_source": embedding_source,
            "scope": json_ready(dict(retrieval_scope)),
            "limit": limit,
            "include_causes": include_causes,
        },
        "coverage": json_ready(dict(coverage)),
        "items": [item.to_dict() for item in pack.items],
        "cause_items": [item.to_dict() for item in pack.cause_items],
        "edges": [edge.to_dict() for edge in pack.edges],
        "warnings": list(pack.warnings),
        "required_artifact_paths": required_paths,
        "evidence_index": evidence_index,
    }


def write_context_pack(
    pack: ContextPack,
    output_path: str | Path,
    *,
    json_output_path: str | Path | None = None,
    retrieval_mode: str = "unknown",
    embedding_source: str = "unknown",
    metadata: Mapping[str, Any] | None = None,
    project_seal: str,
    engineering_documents_sha256: str,
    ledger_revision: int,
    ledger_snapshot_sha256: str,
    retrieval_scope: Mapping[str, Any],
    limit: int,
    include_causes: bool,
    coverage: Mapping[str, bool],
    project_root: str | Path,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        context_pack_to_markdown(
            pack,
            retrieval_mode=retrieval_mode,
            embedding_source=embedding_source,
            generated_at=generated_at,
            metadata=metadata,
        ),
        encoding="utf-8",
    )
    json_data = context_pack_to_json_data(
        pack,
        retrieval_mode=retrieval_mode,
        embedding_source=embedding_source,
        generated_at=generated_at,
        project_seal=project_seal,
        engineering_documents_sha256=engineering_documents_sha256,
        ledger_revision=ledger_revision,
        ledger_snapshot_sha256=ledger_snapshot_sha256,
        retrieval_scope=retrieval_scope,
        limit=limit,
        include_causes=include_causes,
        coverage=coverage,
        project_root=project_root,
    )
    if json_output_path is not None:
        json_output = Path(json_output_path)
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(json.dumps(json_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return json_data


def _items_section(title: str, items: list[LedgerItem] | tuple[LedgerItem, ...] | Any) -> list[str]:
    rows = list(items)
    lines = [f"## {title}", ""]
    if not rows:
        lines.extend(["None.", ""])
        return lines
    for index, item in enumerate(rows, start=1):
        lines.extend(
            [
                f"### {index}. `{item.id}`",
                f"- type: `{item.type}`",
                f"- status: `{item.status}`",
                f"- level: `{item.level}`",
                f"- confidence: `{item.confidence}`",
                f"- source: `{item.source}`",
                f"- artifact_path: `{item.artifact_path}`",
                f"- evidence_path: `{item.evidence_path}`",
                f"- created_by: `{item.created_by}`",
                f"- created_at: `{item.created_at}`",
                f"- updated_at: `{item.updated_at}`",
                f"- scope: `{_inline_json(item.scope)}`",
                f"- metadata: `{_inline_json(item.metadata)}`",
                "- content:",
                "",
                "```text",
                item.content,
                "```",
                "",
            ]
        )
    return lines


def _edges_section(title: str, edges: list[LedgerEdge] | tuple[LedgerEdge, ...] | Any) -> list[str]:
    rows = list(edges)
    lines = [f"## {title}", ""]
    if not rows:
        lines.extend(["None.", ""])
        return lines
    for edge in rows:
        lines.extend(
            [
                f"- `{edge.from_id}` --{edge.relation}--> `{edge.to_id}`",
                f"  - edge_id: `{edge.id}`",
                f"  - status: `{edge.status}`",
                f"  - confidence: `{edge.confidence}`",
                f"  - reason: {edge.reason}",
                f"  - metadata: `{_inline_json(edge.metadata)}`",
            ]
        )
    lines.append("")
    return lines


def _list_section(title: str, values: Any) -> list[str]:
    rows = list(values)
    lines = [f"## {title}", ""]
    if not rows:
        lines.extend(["None.", ""])
        return lines
    for value in rows:
        lines.append(f"- `{value}`")
    lines.append("")
    return lines


def _inline_json(value: Any) -> str:
    return json.dumps(json_ready(value), ensure_ascii=False, sort_keys=True)
