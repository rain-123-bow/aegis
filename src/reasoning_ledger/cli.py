from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from .context_pack import write_context_pack
from .embedding import EmbeddingError, resolve_query_embedding
from .models import CreateItem, ItemStatus
from .project import ProjectLedgerConfig, bootstrap_project_ledger
from .store import ReasoningLedger


DEFAULT_CONTEXT_PACK_NAME = "REASONING_LEDGER_CONTEXT_PACK.md"
DEFAULT_CONTEXT_PACK_JSON_NAME = "REASONING_LEDGER_CONTEXT_PACK.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reasoning-ledger")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap")
    bootstrap.add_argument("--project-root", default=".")
    bootstrap.add_argument("--project-id", required=True)
    bootstrap.add_argument("--schema", default="reasoning_ledger")
    bootstrap.add_argument("--dsn-env", default="AEGIS_LEDGER_DSN")
    bootstrap.add_argument("--embedding-dimensions", type=int, default=1536)

    migrate = subparsers.add_parser("migrate")
    add_project_args(migrate)

    probe = subparsers.add_parser("probe")
    add_project_args(probe)

    export = subparsers.add_parser("export")
    add_project_args(export)
    export.add_argument("--output", required=True)

    add_item = subparsers.add_parser("add-item")
    add_project_args(add_item)
    add_item.add_argument("--id", required=True)
    add_item.add_argument("--type", required=True, choices=("input", "fact", "rule", "claim"))
    add_item.add_argument("--status", default="active", choices=("active", "stale", "invalid", "superseded"))
    add_item.add_argument("--scope-json", default="{}")
    add_item.add_argument("--scope-file")
    add_item.add_argument("--content")
    add_item.add_argument("--content-file")
    add_item.add_argument("--created-by", required=True)
    add_item.add_argument("--artifact-path")
    add_item.add_argument("--source")
    add_item.add_argument("--evidence-path")
    add_item.add_argument("--confidence", type=float)
    add_item.add_argument("--level", type=int, default=0)
    add_item.add_argument("--version", type=int, default=1)
    add_item.add_argument("--metadata-json", default="{}")
    add_item.add_argument("--metadata-file")
    add_embedding_args(add_item, hash_help="generate an offline lexical hash embedding for item content")
    add_item.add_argument("--no-embedding", action="store_true")

    search = subparsers.add_parser("semantic-search")
    add_project_args(search)
    search.add_argument("--query")
    search.add_argument("--query-file")
    search.add_argument("--scope-json", default="{}")
    search.add_argument("--scope-file")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--statuses", default="active")
    search.add_argument("--item-types")
    search.add_argument("--output")
    add_embedding_args(search, hash_help="use offline lexical hash embedding for the search query")

    context = subparsers.add_parser("context-pack")
    add_project_args(context)
    context.add_argument("--artifact-path", help="LangGraph shared artifact directory; default output lives here")
    context.add_argument("--task-id", required=True)
    context.add_argument("--agent-role", required=True)
    context.add_argument("--query")
    context.add_argument("--query-file")
    context.add_argument("--scope-json", default="{}")
    context.add_argument("--scope-file")
    context.add_argument("--limit", type=int, default=12)
    context.add_argument("--include-causes", dest="include_causes", action="store_true", default=True)
    context.add_argument("--no-include-causes", dest="include_causes", action="store_false")
    context.add_argument("--output")
    context.add_argument("--json-output")
    context.add_argument("--require-semantic", action="store_true")
    add_embedding_args(context, hash_help="use offline lexical hash embedding for the context-pack query")

    return parser


def add_project_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--dsn")


def add_embedding_args(parser: argparse.ArgumentParser, *, hash_help: str) -> None:
    parser.add_argument("--embedding-json", help="embedding JSON array or object")
    parser.add_argument("--embedding-file", help="file containing embedding JSON or numeric text")
    parser.add_argument(
        "--embedding-command",
        help=(
            "external command that reads text from stdin and prints embedding JSON; "
            "defaults to AEGIS_LEDGER_EMBEDDING_COMMAND when set"
        ),
    )
    parser.add_argument("--embedding-timeout", type=int, default=60)
    parser.add_argument("--allow-hash-embedding", action="store_true", help=hash_help)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        return _main(args)
    except (EmbeddingError, ValueError, KeyError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


def _main(args: argparse.Namespace) -> int:
    if args.command == "bootstrap":
        result = bootstrap_project_ledger(
            args.project_root,
            project_id=args.project_id,
            schema=args.schema,
            dsn_env=args.dsn_env,
            embedding_dimensions=args.embedding_dimensions,
        )
        print(json.dumps({"config": str(result.config.config_path)}, ensure_ascii=False))
        return 0

    config = ProjectLedgerConfig.load(args.project_root)
    dsn = args.dsn or os.environ.get(config.dsn_env)
    ledger = ReasoningLedger(
        dsn,
        project_id=config.project_id,
        schema=config.schema,
        embedding_dimensions=config.embedding_dimensions,
    )

    if args.command == "migrate":
        ledger.migrate()
        print(json.dumps({"migrated": True, "schema": config.schema}, ensure_ascii=False))
        return 0

    if args.command == "probe":
        with ledger.connect() as conn:
            row = conn.execute("SELECT current_database() AS database, current_user AS user").fetchone()
            vector = conn.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            ).fetchone()
        print(
            json.dumps(
                {
                    "database": row["database"],
                    "user": row["user"],
                    "vector": vector["extversion"] if vector else None,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "export":
        snapshot = ledger.export_snapshot(Path(args.output))
        print(
            json.dumps(
                {
                    "items": len(snapshot["items"]),
                    "edges": len(snapshot["edges"]),
                    "events": len(snapshot["events"]),
                    "output": args.output,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "add-item":
        return _add_item(args, ledger, config)

    if args.command == "semantic-search":
        return _semantic_search(args, ledger, config)

    if args.command == "context-pack":
        return _context_pack(args, ledger, config)

    raise AssertionError(args.command)


def _add_item(args: argparse.Namespace, ledger: ReasoningLedger, config: ProjectLedgerConfig) -> int:
    content = _read_text_arg(args.content, args.content_file, argument_name="content")
    scope = _read_json_arg(args.scope_json, args.scope_file, argument_name="scope")
    metadata = _read_json_arg(args.metadata_json, args.metadata_file, argument_name="metadata")
    embedding = None
    embedding_source = "none"
    if not args.no_embedding:
        embedding, embedding_source = resolve_query_embedding(
            text=content,
            dimensions=config.embedding_dimensions,
            embedding_json=args.embedding_json,
            embedding_file=args.embedding_file,
            embedding_command=args.embedding_command,
            allow_hash_embedding=args.allow_hash_embedding,
            command_timeout_seconds=args.embedding_timeout,
        )
    item = ledger.add_item(
        CreateItem(
            id=args.id,
            type=args.type,
            status=args.status,
            scope=scope,
            content=content,
            created_by=args.created_by,
            artifact_path=args.artifact_path,
            source=args.source,
            evidence_path=args.evidence_path,
            confidence=args.confidence,
            level=args.level,
            version=args.version,
            embedding=embedding,
            metadata=metadata,
        )
    )
    print(json.dumps({"item": item.to_dict(), "embedding_source": embedding_source}, ensure_ascii=False))
    return 0


def _semantic_search(args: argparse.Namespace, ledger: ReasoningLedger, config: ProjectLedgerConfig) -> int:
    query = _read_text_arg(args.query, args.query_file, argument_name="query")
    scope = _read_json_arg(args.scope_json, args.scope_file, argument_name="scope")
    embedding, embedding_source = resolve_query_embedding(
        text=query,
        dimensions=config.embedding_dimensions,
        embedding_json=args.embedding_json,
        embedding_file=args.embedding_file,
        embedding_command=args.embedding_command,
        allow_hash_embedding=args.allow_hash_embedding,
        command_timeout_seconds=args.embedding_timeout,
    )
    if embedding is None:
        raise EmbeddingError(
            "semantic-search requires an embedding source: --embedding-json, --embedding-file, "
            "--embedding-command, AEGIS_LEDGER_EMBEDDING_COMMAND, or --allow-hash-embedding"
        )
    results = ledger.semantic_search(
        embedding,
        limit=args.limit,
        statuses=_csv(args.statuses) or [ItemStatus.ACTIVE.value],
        item_types=_csv(args.item_types),
        scope=scope,
    )
    data = {
        "project_id": config.project_id,
        "query": query,
        "embedding_source": embedding_source,
        "results": [result.to_dict() for result in results],
    }
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False))
    return 0


def _context_pack(args: argparse.Namespace, ledger: ReasoningLedger, config: ProjectLedgerConfig) -> int:
    query = _read_text_arg(args.query, args.query_file, argument_name="query")
    scope = _read_json_arg(args.scope_json, args.scope_file, argument_name="scope")
    embedding, embedding_source = resolve_query_embedding(
        text=query,
        dimensions=config.embedding_dimensions,
        embedding_json=args.embedding_json,
        embedding_file=args.embedding_file,
        embedding_command=args.embedding_command,
        allow_hash_embedding=args.allow_hash_embedding,
        command_timeout_seconds=args.embedding_timeout,
    )
    if embedding is None and args.require_semantic:
        raise EmbeddingError(
            "context-pack --require-semantic needs an embedding source: --embedding-json, "
            "--embedding-file, --embedding-command, AEGIS_LEDGER_EMBEDDING_COMMAND, or --allow-hash-embedding"
        )
    retrieval_mode = "semantic_search" if embedding is not None else "list_items_fallback"
    pack = ledger.retrieve_context_pack(
        task_id=args.task_id,
        agent_role=args.agent_role,
        query=query,
        query_embedding=embedding,
        scope=scope,
        limit=args.limit,
        include_causes=args.include_causes,
    )
    artifact_path = Path(args.artifact_path) if args.artifact_path else None
    output = Path(args.output) if args.output else (artifact_path / DEFAULT_CONTEXT_PACK_NAME if artifact_path else Path(DEFAULT_CONTEXT_PACK_NAME))
    json_output = (
        Path(args.json_output)
        if args.json_output
        else (artifact_path / DEFAULT_CONTEXT_PACK_JSON_NAME if artifact_path else None)
    )
    json_data = write_context_pack(
        pack,
        output,
        json_output_path=json_output,
        retrieval_mode=retrieval_mode,
        embedding_source=embedding_source,
        metadata={
            "project_root": str(config.project_root),
            "schema": config.schema,
            "embedding_dimensions": config.embedding_dimensions,
            "scope": scope,
            "limit": args.limit,
            "include_causes": args.include_causes,
        },
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "json_output": str(json_output) if json_output else None,
                "project_id": pack.project_id,
                "task_id": pack.task_id,
                "agent_role": pack.agent_role,
                "retrieval_mode": retrieval_mode,
                "embedding_source": embedding_source,
                "items": len(pack.items),
                "cause_items": len(pack.cause_items),
                "edges": len(pack.edges),
                "warnings": len(pack.warnings),
                "required_artifact_paths": json_data.get("required_artifact_paths", []),
            },
            ensure_ascii=False,
        )
    )
    return 0


def _read_text_arg(value: str | None, file_path: str | None, *, argument_name: str) -> str:
    if value and file_path:
        raise ValueError(f"pass either --{argument_name} or --{argument_name}-file, not both")
    if file_path:
        return Path(file_path).read_text(encoding="utf-8")
    if value is not None:
        return value
    raise ValueError(f"missing --{argument_name} or --{argument_name}-file")


def _read_json_arg(value: str | None, file_path: str | None, *, argument_name: str) -> dict[str, Any]:
    if file_path and value not in (None, "{}"): 
        raise ValueError(f"pass either --{argument_name}-json or --{argument_name}-file, not both")
    raw = Path(file_path).read_text(encoding="utf-8") if file_path else (value or "{}")
    parsed = json.loads(raw)
    if not isinstance(parsed, Mapping):
        raise ValueError(f"{argument_name} must be a JSON object")
    return dict(parsed)


def _csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    rows = [part.strip() for part in value.split(",") if part.strip()]
    return rows or None


if __name__ == "__main__":
    raise SystemExit(main())
