from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from path_security import PathSecurityError, lexical_absolute, read_regular_file

from .models import AuthorityContextPack, json_ready


CONTEXT_PACK_SCHEMA = "aegis.reasoning_context_pack.v2"


def context_pack_to_markdown(
    pack: AuthorityContextPack,
    *,
    retrieval_mode: str = "hybrid_exact",
    embedding_source: str = "none",
    generated_at: datetime | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> str:
    generated = (generated_at or datetime.now(timezone.utc)).isoformat()
    lines = [
        "# Reasoning Ledger Context Pack",
        "",
        "## Metadata",
        f"- project_id: `{pack.project_id}`",
        f"- task_id: `{pack.task_id}`",
        f"- agent_role: `{pack.agent_role}`",
        f"- generated_at: `{generated}`",
        f"- retrieval_mode: `{retrieval_mode}`",
        f"- embedding_source: `{embedding_source}`",
        f"- retrieval_trace: `{_inline_json(pack.retrieval_trace)}`",
        "- query:",
        "",
        "```text",
        pack.query,
        "```",
        "",
    ]
    if metadata:
        lines.extend(["## Runtime Metadata", ""])
        for key, value in sorted(metadata.items()):
            lines.append(f"- {key}: `{_inline_json(value)}`")
        lines.append("")
    lines.extend(["## Candidate Revisions", ""])
    if not pack.candidates:
        lines.extend(["None.", ""])
    for hit in pack.candidates:
        revision = hit.revision
        lines.extend(
            [
                f"### `{revision.statement_id}@{revision.revision}`",
                f"- type: `{revision.statement_type}`",
                f"- validity: `{revision.current_validity}`",
                f"- sources: `{_inline_json(list(hit.sources))}`",
                f"- lexical_rank: `{hit.lexical_rank}`",
                f"- semantic_distance: `{hit.semantic_distance}`",
                f"- evidence_ids: `{_inline_json(list(revision.evidence_ids))}`",
                "- content:",
                "",
                "```text",
                revision.content,
                "```",
                "",
            ]
        )
    lines.extend(_revision_rows("Causal Revisions", pack.causal_revisions))
    lines.extend(_relation_rows("Causal Relations", pack.relations))
    lines.extend(_relation_rows("Conflicts", pack.conflicts))
    lines.extend(_list_rows("Warnings", pack.warnings))
    lines.extend(["## Evidence Descriptors", ""])
    if not pack.evidence_descriptors:
        lines.extend(["None.", ""])
    for evidence in pack.evidence_descriptors:
        lines.extend(
            [
                f"- `{evidence.evidence_id}` -> `{evidence.path}`",
                f"  - size: `{evidence.size}`",
                f"  - sha256: `{evidence.sha256}`",
                f"  - source_identity: `{_inline_json(evidence.source_identity)}`",
            ]
        )
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def context_pack_to_json_data(
    pack: AuthorityContextPack,
    *,
    retrieval_mode: str = "hybrid_exact",
    embedding_source: str = "none",
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
    root = lexical_absolute(project_root)
    evidence_index: list[dict[str, Any]] = []
    for descriptor in pack.evidence_descriptors:
        path = lexical_absolute(root / descriptor.path)
        try:
            content, _identity = read_regular_file(
                path,
                allowed_root=root,
                label=f"reasoning evidence {descriptor.evidence_id}",
                max_bytes=64 * 1024 * 1024,
            )
        except PathSecurityError as error:
            raise ValueError(str(error)) from error
        digest = hashlib.sha256(content).hexdigest()
        if len(content) != descriptor.size or digest != descriptor.sha256:
            raise ValueError(
                f"reasoning evidence bytes differ from descriptor: {descriptor.evidence_id}"
            )
        evidence_index.append(
            {
                "evidence_id": descriptor.evidence_id,
                "path": str(path),
                "size": len(content),
                "sha256": digest,
                "source_identity": json_ready(dict(descriptor.source_identity)),
            }
        )
    payload: dict[str, Any] = {
        "schema": CONTEXT_PACK_SCHEMA,
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
            "trace": json_ready(dict(pack.retrieval_trace)),
        },
        "coverage": json_ready(dict(coverage)),
        "candidates": [value.to_dict() for value in pack.candidates],
        "causal_revisions": [
            value.to_dict() for value in pack.causal_revisions
        ],
        "relations": [value.to_dict() for value in pack.relations],
        "conflicts": [value.to_dict() for value in pack.conflicts],
        "warnings": list(pack.warnings),
        "evidence_descriptors": [
            value.to_dict() for value in pack.evidence_descriptors
        ],
        "evidence_index": evidence_index,
    }
    payload["canonical_payload_sha256"] = hashlib.sha256(
        _canonical_json_bytes(payload)
    ).hexdigest()
    return payload


def write_context_pack(
    pack: AuthorityContextPack,
    output_path: str | Path,
    *,
    json_output_path: str | Path | None = None,
    retrieval_mode: str = "hybrid_exact",
    embedding_source: str = "none",
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
    if json_output_path is not None:
        json_output = Path(json_output_path)
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_bytes(_canonical_json_bytes(json_data) + b"\n")
    return json_data


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        json_ready(dict(value)),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _revision_rows(title: str, values: Any) -> list[str]:
    lines = [f"## {title}", ""]
    rows = list(values)
    if not rows:
        return [*lines, "None.", ""]
    for revision in rows:
        lines.extend(
            [
                f"- `{revision.statement_id}@{revision.revision}` "
                f"[{revision.statement_type}/{revision.current_validity}]",
                f"  - evidence_ids: `{_inline_json(list(revision.evidence_ids))}`",
                f"  - content: {revision.content}",
            ]
        )
    lines.append("")
    return lines


def _relation_rows(title: str, values: Any) -> list[str]:
    lines = [f"## {title}", ""]
    rows = list(values)
    if not rows:
        return [*lines, "None.", ""]
    for relation in rows:
        lines.extend(
            [
                f"- `{relation.from_statement_id}@{relation.from_revision}` "
                f"--{relation.relation_type}--> "
                f"`{relation.to_statement_id}@{relation.to_revision}`",
                f"  - relation_id: `{relation.relation_id}`",
                f"  - reason: {relation.reason}",
                f"  - evidence_ids: `{_inline_json(list(relation.evidence_ids))}`",
            ]
        )
    lines.append("")
    return lines


def _list_rows(title: str, values: Any) -> list[str]:
    lines = [f"## {title}", ""]
    rows = list(values)
    if not rows:
        return [*lines, "None.", ""]
    lines.extend(f"- `{value}`" for value in rows)
    lines.append("")
    return lines


def _inline_json(value: Any) -> str:
    return json.dumps(json_ready(value), ensure_ascii=False, sort_keys=True)
