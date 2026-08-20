from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg

from path_security import read_regular_file

from .context_pack import write_context_pack
from .embedding import EmbeddingError, resolve_query_embedding
from .models import (
    EmbeddingProfile,
    EvidenceDescriptor,
    QueryEmbeddingReceipt,
    RelationType,
    RevisionValidity,
    StatementRelation,
    StatementRevision,
    StatementType,
    normalize_relative_path,
)
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

    verify_evidence = subparsers.add_parser("verify-evidence")
    add_project_args(verify_evidence)

    evidence = subparsers.add_parser("register-evidence")
    add_project_args(evidence)
    evidence.add_argument("--evidence-id", required=True)
    evidence.add_argument("--path", required=True)
    evidence.add_argument("--source-identity-json", required=True)
    evidence.add_argument("--captured-at")
    evidence.add_argument("--scope-json", default="{}")
    evidence.add_argument("--scope-file")
    evidence.add_argument("--created-by", required=True)

    create = subparsers.add_parser("create-statement")
    add_project_args(create)
    add_statement_args(create, initial=True)

    supersede = subparsers.add_parser("supersede-statement")
    add_project_args(supersede)
    add_statement_args(supersede, initial=False)
    supersede.add_argument("--reason", required=True)
    supersede.add_argument("--relation-id")

    link = subparsers.add_parser(
        "link-revisions",
        description=(
            "Create an evidence-bound edge from an upstream basis or earlier state "
            "to its dependent or successor state."
        ),
    )
    add_project_args(link)
    link.add_argument("--relation-id", required=True)
    link.add_argument("--from-statement-id", required=True)
    link.add_argument("--from-revision", type=int, required=True)
    link.add_argument("--to-statement-id", required=True)
    link.add_argument("--to-revision", type=int, required=True)
    link.add_argument(
        "--relation-type",
        choices=[
            value.value for value in RelationType
            if value is not RelationType.SUPERSEDES
        ],
        required=True,
    )
    link.add_argument("--conditions-json", default="{}")
    link.add_argument("--reason", required=True)
    link.add_argument("--evidence-ids", required=True)
    link.add_argument("--created-by", required=True)

    profile = subparsers.add_parser("register-embedding-profile")
    add_project_args(profile)
    profile.add_argument("--profile-id", required=True)
    profile.add_argument("--provider", required=True)
    profile.add_argument("--model", required=True)
    profile.add_argument("--model-version", required=True)
    profile.add_argument("--normalization", required=True)
    profile.add_argument("--input-template-version", required=True)
    profile.add_argument("--created-by", required=True)

    embedding_input = subparsers.add_parser("embedding-input")
    add_project_args(embedding_input)
    embedding_input.add_argument("--statement-id", required=True)
    embedding_input.add_argument("--revision", type=int, required=True)
    embedding_input.add_argument("--profile-id", required=True)
    embedding_input.add_argument("--output")

    store_embedding = subparsers.add_parser("store-embedding")
    add_project_args(store_embedding)
    store_embedding.add_argument("--statement-id", required=True)
    store_embedding.add_argument("--revision", type=int, required=True)
    store_embedding.add_argument("--profile-id", required=True)
    store_embedding.add_argument("--embedded-text")
    store_embedding.add_argument("--embedded-text-file")
    store_embedding.add_argument("--embedding-command")
    store_embedding.add_argument("--embedding-timeout", type=int, default=60)
    store_embedding.add_argument(
        "--allow-hash-embedding",
        action="store_true",
        help="generate a deterministic development-only embedding",
    )

    search = subparsers.add_parser("semantic-search")
    add_project_args(search)
    search.add_argument("--query")
    search.add_argument("--query-file")
    search.add_argument("--scope-json", default="{}")
    search.add_argument("--scope-file")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--profile-id", required=True)
    search.add_argument("--output")
    add_hard_filter_args(search)
    add_embedding_args(search, hash_help="use offline lexical hash embedding for the search query")

    lexical = subparsers.add_parser("lexical-search")
    add_project_args(lexical)
    lexical.add_argument("--query")
    lexical.add_argument("--query-file")
    lexical.add_argument("--scope-json", default="{}")
    lexical.add_argument("--scope-file")
    lexical.add_argument("--limit", type=int, default=10)
    lexical.add_argument("--output")
    add_hard_filter_args(lexical)

    context = subparsers.add_parser("context-pack")
    add_project_args(context)
    context.add_argument("--artifact-path", help="LangGraph shared artifact directory; default output lives here")
    context.add_argument("--task-id", required=True)
    context.add_argument("--agent-role", required=True)
    context.add_argument("--project-seal", required=True)
    context.add_argument("--engineering-documents-sha256", required=True)
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
    context.add_argument("--embedding-profile-id")
    add_hard_filter_args(context)
    add_embedding_args(context, hash_help="use offline lexical hash embedding for the context-pack query")

    return parser


def add_statement_args(parser: argparse.ArgumentParser, *, initial: bool) -> None:
    parser.add_argument("--statement-id", required=True)
    parser.add_argument("--revision", type=int, default=1 if initial else None, required=not initial)
    parser.add_argument("--statement-type", choices=[value.value for value in StatementType], required=True)
    parser.add_argument("--content")
    parser.add_argument("--content-file")
    parser.add_argument("--conditions-json", default="{}")
    parser.add_argument("--validity", choices=[value.value for value in RevisionValidity], default="ACTIVE")
    parser.add_argument("--scope-json", default="{}")
    parser.add_argument("--scope-file")
    parser.add_argument("--confidence", type=float)
    parser.add_argument("--evidence-ids", required=True)
    parser.add_argument("--created-by", required=True)


def add_hard_filter_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--statement-types")
    parser.add_argument("--created-after")
    parser.add_argument("--created-before")


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
    except (
        EmbeddingError,
        ValueError,
        KeyError,
        PermissionError,
        RuntimeError,
        psycopg.Error,
    ) as exc:
        print(json.dumps({"status": False, "error": str(exc)}, ensure_ascii=False))
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

    config = (
        ProjectLedgerConfig.load_for_migration(args.project_root)
        if args.command == "migrate"
        else ProjectLedgerConfig.load(args.project_root)
    )
    dsn = args.dsn or os.environ.get(config.dsn_env)
    ledger = ReasoningLedger(
        dsn,
        project_id=config.project_id,
        schema=config.schema,
        embedding_dimensions=config.embedding_dimensions,
        minimum_postgresql_major=config.minimum_postgresql_major,
        minimum_pgvector_version=config.minimum_pgvector_version,
        expected_project_anchor_sha256=config.project_anchor_sha256,
    )

    if args.command == "migrate":
        project_anchor = ledger.migrate()
        bind_configuration = config.project_anchor_sha256 is None
        if config.project_anchor_sha256 is None:
            if ProjectLedgerConfig.load_for_migration(args.project_root) != config:
                raise RuntimeError(
                    "reasoning-ledger project configuration changed during migration"
                )
            config = replace(
                config,
                project_anchor_sha256=str(project_anchor["anchor_sha256"]),
            )
        config.ensure_migration_artifact()
        if bind_configuration:
            config.save()
        print(
            json.dumps(
                {
                    "status": True,
                    "migrated": True,
                    "schema": config.schema,
                    "project_anchor": project_anchor,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "probe":
        print(json.dumps(ledger.probe_contract(require_schema=True), ensure_ascii=False))
        return 0

    if args.command == "export":
        snapshot = ledger.export_snapshot(Path(args.output))
        print(
            json.dumps(
                {
                    "statements": len(snapshot["statements"]),
                    "relations": len(snapshot["relations"]),
                    "events": len(snapshot["events"]),
                    "output": args.output,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "verify-evidence":
        result = ledger.verify_evidence_files(project_root=config.project_root)
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "register-evidence":
        relative_path = normalize_relative_path(args.path)
        if relative_path is None:
            raise ValueError("evidence path must not be empty")
        evidence_path = config.project_root / relative_path
        content, _identity = read_regular_file(
            evidence_path,
            allowed_root=config.project_root,
            label="reasoning evidence",
            max_bytes=64 * 1024 * 1024,
        )
        descriptor = ledger.register_evidence(
            EvidenceDescriptor(
                evidence_id=args.evidence_id,
                path=relative_path,
                size=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                source_identity=_json_object(args.source_identity_json, "source identity"),
                captured_at=args.captured_at
                or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                scope=_read_json_arg(args.scope_json, args.scope_file, argument_name="scope"),
                created_by=args.created_by,
            ),
            project_root=config.project_root,
        )
        print(json.dumps({"evidence": descriptor.to_dict()}, ensure_ascii=False))
        return 0

    if args.command in {"create-statement", "supersede-statement"}:
        revision = _statement_revision(args)
        if args.command == "create-statement":
            result = ledger.create_statement(revision)
        else:
            result = ledger.supersede_statement(
                revision,
                reason=args.reason,
                relation_id=args.relation_id,
            )
        print(json.dumps({"revision": result.to_dict()}, ensure_ascii=False))
        return 0

    if args.command == "link-revisions":
        relation = ledger.create_relation(
            StatementRelation(
                relation_id=args.relation_id,
                from_statement_id=args.from_statement_id,
                from_revision=args.from_revision,
                to_statement_id=args.to_statement_id,
                to_revision=args.to_revision,
                relation_type=args.relation_type,
                applicable_conditions=_json_object(args.conditions_json, "conditions"),
                reason=args.reason,
                created_by=args.created_by,
                evidence_ids=_csv(args.evidence_ids) or [],
            )
        )
        print(json.dumps({"relation": relation.to_dict()}, ensure_ascii=False))
        return 0

    if args.command == "register-embedding-profile":
        profile = ledger.register_embedding_profile(
            EmbeddingProfile(
                profile_id=args.profile_id,
                provider=args.provider,
                model=args.model,
                model_version=args.model_version,
                dimensions=config.embedding_dimensions,
                normalization=args.normalization,
                input_template_version=args.input_template_version,
                created_by=args.created_by,
            )
        )
        print(
            json.dumps(
                {"profile_id": profile.profile_id, "content_sha256": profile.content_sha256},
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "embedding-input":
        embedded_text = ledger.get_embedding_input(
            statement_id=args.statement_id,
            revision=args.revision,
            profile_id=args.profile_id,
        )
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(embedded_text, encoding="utf-8")
        print(
            json.dumps(
                {
                    "statement_id": args.statement_id,
                    "revision": args.revision,
                    "profile_id": args.profile_id,
                    "embedded_text": embedded_text,
                    "embedded_text_sha256": hashlib.sha256(
                        embedded_text.encode("utf-8")
                    ).hexdigest(),
                    "output": args.output,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "store-embedding":
        embedded_text = _read_text_arg(
            args.embedded_text,
            args.embedded_text_file,
            argument_name="embedded-text",
        )
        embedding_source = ledger.generate_and_store_embedding(
            statement_id=args.statement_id,
            revision=args.revision,
            profile_id=args.profile_id,
            embedded_text=embedded_text,
            embedding_command=args.embedding_command,
            allow_hash_embedding=args.allow_hash_embedding,
            command_timeout_seconds=args.embedding_timeout,
        )
        print(
            json.dumps(
                {
                    "stored": True,
                    "statement_id": args.statement_id,
                    "revision": args.revision,
                    "profile_id": args.profile_id,
                    "embedding_source": embedding_source,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "semantic-search":
        return _semantic_search(args, ledger, config)

    if args.command == "lexical-search":
        return _lexical_search(args, ledger, config)

    if args.command == "context-pack":
        return _context_pack(args, ledger, config)

    raise AssertionError(args.command)


def _statement_revision(args: argparse.Namespace) -> StatementRevision:
    return StatementRevision(
        statement_id=args.statement_id,
        revision=args.revision,
        statement_type=args.statement_type,
        content=_read_text_arg(args.content, args.content_file, argument_name="content"),
        structured_conditions=_json_object(args.conditions_json, "conditions"),
        validity=args.validity,
        scope=_read_json_arg(args.scope_json, args.scope_file, argument_name="scope"),
        confidence=args.confidence,
        created_by=args.created_by,
        evidence_ids=_csv(args.evidence_ids) or [],
    )


def _semantic_search(args: argparse.Namespace, ledger: ReasoningLedger, config: ProjectLedgerConfig) -> int:
    query = _read_text_arg(args.query, args.query_file, argument_name="query")
    scope = _read_json_arg(args.scope_json, args.scope_file, argument_name="scope")
    embedding, embedding_source, generator_identity = resolve_query_embedding(
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
    if generator_identity is None:
        raise EmbeddingError("semantic-search has no query generator identity")
    query_receipt = QueryEmbeddingReceipt(
        profile_id=args.profile_id,
        source=embedding_source,
        embedding=embedding,
        generator_identity=generator_identity,
    )
    results = ledger.semantic_search(
        query_receipt,
        limit=args.limit,
        statement_types=_csv(args.statement_types),
        scope=scope,
        created_after=args.created_after,
        created_before=args.created_before,
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


def _lexical_search(
    args: argparse.Namespace,
    ledger: ReasoningLedger,
    config: ProjectLedgerConfig,
) -> int:
    query = _read_text_arg(args.query, args.query_file, argument_name="query")
    scope = _read_json_arg(args.scope_json, args.scope_file, argument_name="scope")
    results = ledger.lexical_search(
        query,
        limit=args.limit,
        statement_types=_csv(args.statement_types),
        scope=scope,
        created_after=args.created_after,
        created_before=args.created_before,
    )
    data = {
        "project_id": config.project_id,
        "query": query,
        "results": [result.to_dict() for result in results],
    }
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(data, ensure_ascii=False))
    return 0


def _context_pack(args: argparse.Namespace, ledger: ReasoningLedger, config: ProjectLedgerConfig) -> int:
    query = _read_text_arg(args.query, args.query_file, argument_name="query")
    scope = _read_json_arg(args.scope_json, args.scope_file, argument_name="scope")
    embedding, embedding_source, generator_identity = resolve_query_embedding(
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
    if embedding is not None and not args.embedding_profile_id:
        raise ValueError("semantic context retrieval requires --embedding-profile-id")
    query_receipt = None
    if embedding is not None:
        if generator_identity is None:
            raise EmbeddingError("context-pack has no query generator identity")
        query_receipt = QueryEmbeddingReceipt(
            profile_id=args.embedding_profile_id,
            source=embedding_source,
            embedding=embedding,
            generator_identity=generator_identity,
        )
    retrieval_mode = "hybrid_exact" if embedding is not None else "lexical_exact"
    snapshot_before = ledger.export_snapshot()
    snapshot_before_bytes = json.dumps(
        snapshot_before,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    pack = ledger.retrieve_context_pack(
        task_id=args.task_id,
        agent_role=args.agent_role,
        query=query,
        query_embedding=query_receipt,
        statement_types=_csv(args.statement_types),
        scope=scope,
        created_after=args.created_after,
        created_before=args.created_before,
        limit=args.limit,
        include_causes=args.include_causes,
    )
    snapshot_after = ledger.export_snapshot()
    snapshot_after_bytes = json.dumps(
        snapshot_after,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if snapshot_after_bytes != snapshot_before_bytes:
        raise RuntimeError(
            "reasoning ledger changed while generating the context pack"
        )
    event_ids = [
        event.get("event_id")
        for event in snapshot_after["events"]
        if isinstance(event.get("event_id"), int)
    ]
    ledger_revision = max(event_ids, default=0)
    ledger_snapshot_sha256 = hashlib.sha256(snapshot_after_bytes).hexdigest()
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
        project_seal=args.project_seal,
        engineering_documents_sha256=args.engineering_documents_sha256,
        ledger_revision=ledger_revision,
        ledger_snapshot_sha256=ledger_snapshot_sha256,
        retrieval_scope=scope,
        limit=args.limit,
        include_causes=args.include_causes,
        project_root=config.project_root,
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
                "candidates": len(pack.candidates),
                "causal_revisions": len(pack.causal_revisions),
                "relations": len(pack.relations),
                "conflicts": len(pack.conflicts),
                "warnings": len(pack.warnings),
                "evidence_descriptors": len(pack.evidence_descriptors),
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


def _json_object(value: str, argument_name: str) -> dict[str, Any]:
    parsed = json.loads(value)
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
