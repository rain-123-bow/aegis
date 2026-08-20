from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from path_security import PathSecurityError, read_regular_file

from .schema import build_init_sql, validate_identifier


DEFAULT_ARTIFACT_ROOT = ".aegis/reasoning_ledger/artifacts"
PROJECT_LEDGER_CONFIG_RELATIVE_PATH = Path("config/reasoning_ledger.json")
SUPPORTED_BACKEND = "postgresql_pgvector"
SUPPORTED_AUTHORITY_SCHEMA_VERSION = 2
MINIMUM_SUPPORTED_POSTGRESQL_MAJOR = 16
MINIMUM_SUPPORTED_PGVECTOR_VERSION = (0, 8, 0)
_CONFIG_FIELDS = {"project_id", "ledger"}
_LEDGER_CONFIG_FIELDS = {
    "backend",
    "dsn_env",
    "schema",
    "artifact_root",
    "embedding_dimensions",
    "authority_schema_version",
    "approximate_vector_index",
    "minimum_postgresql_major",
    "minimum_pgvector_version",
}


def _parse_version(value: str, *, field_name: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
    if match is None:
        raise ValueError(f"{field_name} must use MAJOR.MINOR.PATCH")
    return tuple(int(part) for part in match.groups())


@dataclass(frozen=True)
class ProjectLedgerConfig:
    project_id: str
    project_root: Path
    backend: str = "postgresql_pgvector"
    dsn_env: str = "AEGIS_LEDGER_DSN"
    schema: str = "reasoning_ledger"
    artifact_root: str = DEFAULT_ARTIFACT_ROOT
    embedding_dimensions: int = 1536
    authority_schema_version: int = 2
    approximate_vector_index: bool = False
    minimum_postgresql_major: int = 16
    minimum_pgvector_version: str = "0.8.0"

    def __post_init__(self) -> None:
        if not self.project_id.strip():
            raise ValueError("project_id must not be empty")
        if self.backend != SUPPORTED_BACKEND:
            raise ValueError(f"unsupported reasoning ledger backend: {self.backend}")
        validate_identifier(self.schema)
        if not self.dsn_env.strip():
            raise ValueError("dsn_env must not be empty")
        if not self.artifact_root.strip():
            raise ValueError("artifact_root must not be empty")
        artifact_root = Path(self.artifact_root)
        if artifact_root.is_absolute() or ".." in artifact_root.parts:
            raise ValueError("artifact_root must be a project-relative path")
        if (
            isinstance(self.embedding_dimensions, bool)
            or not isinstance(self.embedding_dimensions, int)
            or self.embedding_dimensions <= 0
        ):
            raise ValueError("embedding_dimensions must be positive")
        if (
            isinstance(self.authority_schema_version, bool)
            or not isinstance(self.authority_schema_version, int)
            or self.authority_schema_version != SUPPORTED_AUTHORITY_SCHEMA_VERSION
        ):
            raise ValueError(
                "unsupported reasoning ledger authority schema version: "
                f"{self.authority_schema_version}"
            )
        if not isinstance(self.approximate_vector_index, bool):
            raise ValueError("approximate_vector_index must be boolean")
        if self.approximate_vector_index:
            raise ValueError(
                "approximate vector indexing is unsupported until a measured profile is approved"
            )
        if (
            isinstance(self.minimum_postgresql_major, bool)
            or not isinstance(self.minimum_postgresql_major, int)
            or self.minimum_postgresql_major < MINIMUM_SUPPORTED_POSTGRESQL_MAJOR
        ):
            raise ValueError(
                "minimum_postgresql_major cannot weaken the supported baseline"
            )
        if not isinstance(self.minimum_pgvector_version, str):
            raise ValueError("minimum_pgvector_version must be a string")
        pgvector_version = _parse_version(
            self.minimum_pgvector_version,
            field_name="minimum_pgvector_version",
        )
        if pgvector_version < MINIMUM_SUPPORTED_PGVECTOR_VERSION:
            raise ValueError(
                "minimum_pgvector_version cannot weaken the supported baseline"
            )

    @property
    def config_path(self) -> Path:
        return self.project_root / PROJECT_LEDGER_CONFIG_RELATIVE_PATH

    @property
    def migration_path(self) -> Path:
        return (
            self.project_root
            / ".aegis"
            / "reasoning_ledger"
            / "migrations"
            / "002_immutable_authority.sql"
        )

    def to_json_data(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "ledger": {
                "backend": self.backend,
                "dsn_env": self.dsn_env,
                "schema": self.schema,
                "artifact_root": self.artifact_root,
                "embedding_dimensions": self.embedding_dimensions,
                "authority_schema_version": self.authority_schema_version,
                "approximate_vector_index": self.approximate_vector_index,
                "minimum_postgresql_major": self.minimum_postgresql_major,
                "minimum_pgvector_version": self.minimum_pgvector_version,
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
        config_path = root / PROJECT_LEDGER_CONFIG_RELATIVE_PATH
        try:
            raw, _identity = read_regular_file(
                config_path,
                allowed_root=root,
                label="reasoning ledger project configuration",
                max_bytes=1024 * 1024,
            )
            data = json.loads(raw.decode("utf-8", errors="strict"))
        except (PathSecurityError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(
                f"reasoning ledger project configuration is unreadable: {error}"
            ) from error
        if not isinstance(data, dict) or set(data) != _CONFIG_FIELDS:
            raise ValueError("reasoning ledger project configuration fields are invalid")
        ledger = data["ledger"]
        if not isinstance(ledger, dict) or set(ledger) != _LEDGER_CONFIG_FIELDS:
            raise ValueError("reasoning ledger backend configuration fields are invalid")
        if not isinstance(ledger["approximate_vector_index"], bool):
            raise ValueError("approximate_vector_index must be boolean")
        for integer_field in (
            "embedding_dimensions",
            "authority_schema_version",
            "minimum_postgresql_major",
        ):
            value = ledger[integer_field]
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{integer_field} must be an integer")
        return cls(
            project_id=str(data["project_id"]),
            project_root=root,
            backend=str(ledger["backend"]),
            dsn_env=str(ledger["dsn_env"]),
            schema=str(ledger["schema"]),
            artifact_root=str(ledger["artifact_root"]),
            embedding_dimensions=ledger["embedding_dimensions"],
            authority_schema_version=ledger["authority_schema_version"],
            approximate_vector_index=ledger["approximate_vector_index"],
            minimum_postgresql_major=ledger["minimum_postgresql_major"],
            minimum_pgvector_version=ledger["minimum_pgvector_version"],
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
                "- PostgreSQL stores immutable statement revisions, evidence, relations, and events.",
                "- Current validity is an event-derived projection.",
                "- pgvector stores rebuildable semantic candidates bound to an embedding profile.",
                "- Exact vector search is the default; approximate indexing requires measured approval.",
                "- Evidence paths are project-relative and byte-bound by size and SHA-256.",
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
