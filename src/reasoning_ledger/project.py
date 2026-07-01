from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .schema import build_init_sql, validate_identifier


DEFAULT_ARTIFACT_ROOT = ".aegis/reasoning_ledger/artifacts"


@dataclass(frozen=True)
class ProjectLedgerConfig:
    project_id: str
    project_root: Path
    backend: str = "postgresql_pgvector"
    dsn_env: str = "AEGIS_LEDGER_DSN"
    schema: str = "reasoning_ledger"
    artifact_root: str = DEFAULT_ARTIFACT_ROOT
    embedding_dimensions: int = 1536

    @property
    def config_path(self) -> Path:
        return self.project_root / ".aegis" / "project.json"

    @property
    def migration_path(self) -> Path:
        return self.project_root / ".aegis" / "reasoning_ledger" / "migrations" / "001_init.sql"

    def to_json_data(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "project_root": self.project_root.as_posix(),
            "ledger": {
                "backend": self.backend,
                "dsn_env": self.dsn_env,
                "schema": self.schema,
                "artifact_root": self.artifact_root,
                "embedding_dimensions": self.embedding_dimensions,
            },
        }

    def save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(self.to_json_data(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, project_root: str | Path) -> "ProjectLedgerConfig":
        root = Path(project_root).resolve()
        data = json.loads((root / ".aegis" / "project.json").read_text(encoding="utf-8"))
        ledger = data["ledger"]
        return cls(
            project_id=str(data["project_id"]),
            project_root=root,
            backend=str(ledger["backend"]),
            dsn_env=str(ledger["dsn_env"]),
            schema=str(ledger["schema"]),
            artifact_root=str(ledger["artifact_root"]),
            embedding_dimensions=int(ledger["embedding_dimensions"]),
        )


@dataclass(frozen=True)
class BootstrapResult:
    config: ProjectLedgerConfig
    migration_sql: str
    created_paths: tuple[Path, ...]


def bootstrap_project_ledger(
    project_root: str | Path,
    *,
    project_id: str,
    dsn_env: str = "AEGIS_LEDGER_DSN",
    schema: str = "reasoning_ledger",
    embedding_dimensions: int = 1536,
) -> BootstrapResult:
    root = Path(project_root).resolve()
    validate_identifier(schema)
    if not project_id:
        raise ValueError("project_id must not be empty")

    config = ProjectLedgerConfig(
        project_id=project_id,
        project_root=root,
        dsn_env=dsn_env,
        schema=schema,
        embedding_dimensions=embedding_dimensions,
    )
    ledger_root = root / ".aegis" / "reasoning_ledger"
    directories = [
        root / ".aegis",
        ledger_root,
        ledger_root / "migrations",
        ledger_root / "exports",
        ledger_root / "artifacts" / "requirements",
        ledger_root / "artifacts" / "facts",
        ledger_root / "artifacts" / "rules",
        ledger_root / "artifacts" / "claims",
        ledger_root / "artifacts" / "evidence",
        ledger_root / "artifacts" / "reviews",
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

    migration_sql = build_init_sql(schema=schema, embedding_dimensions=embedding_dimensions)
    config.save()
    config.migration_path.write_text(migration_sql + "\n", encoding="utf-8")
    readme_path = ledger_root / "README.md"
    readme_path.write_text(
        "\n".join(
            [
                "# Reasoning Ledger",
                "",
                "Project-owned reasoning ledger assets.",
                "",
                "- PostgreSQL stores item, edge, and event rows.",
                "- pgvector stores semantic embeddings.",
                "- Artifact paths are project-relative.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return BootstrapResult(
        config=config,
        migration_sql=migration_sql,
        created_paths=tuple(directories + [config.config_path, config.migration_path, readme_path]),
    )
