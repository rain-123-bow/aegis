"""Route schema registry and package validation for Top-Level Graph v2."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from aegis.models import StrictModel
from aegis.top_level.manifest import read_manifest, require_under_any_root, sha256_file
from aegis.top_level.models import (
    ModuleName,
    RouteTarget,
    TopLevelHandoffEnvelope,
    RouteValidationResult,
)


class RouteValidationError(ValueError):
    """Raised when a parent-level route or handoff is invalid."""


class RouteSchemaRegistryEntry(StrictModel):
    """Schema binding for one parent-level route edge."""

    source_module: ModuleName
    target_module: RouteTarget
    handoff_kind: str
    expected_envelope_schema: str = "top_level_handoff_v1"
    expected_package_schema: str
    allowed_next_route_values: list[RouteTarget] = Field(default_factory=list)


class RouteSchemaRegistry:
    """Validate route edges, handoff kinds, and package manifests."""

    def __init__(self, entries: list[RouteSchemaRegistryEntry]) -> None:
        self._entries = {
            (entry.source_module, entry.target_module, entry.handoff_kind): entry
            for entry in entries
        }

    def require_entry(
        self,
        source_module: ModuleName,
        target_module: RouteTarget,
        handoff_kind: str,
    ) -> RouteSchemaRegistryEntry:
        try:
            return self._entries[(source_module, target_module, handoff_kind)]
        except KeyError as exc:
            raise RouteValidationError(
                f"handoff_kind not allowed for route {source_module}->{target_module}: {handoff_kind}"
            ) from exc

    def validate_envelope(
        self,
        envelope: TopLevelHandoffEnvelope,
        *,
        project_root: str | Path,
    ) -> RouteValidationResult:
        entry = self.require_entry(
            envelope.source_module,
            envelope.target_module,
            envelope.handoff_kind,
        )
        if envelope.schema_version != entry.expected_envelope_schema:
            raise RouteValidationError("unexpected envelope schema_version")
        if envelope.declared_next_route not in entry.allowed_next_route_values:
            raise RouteValidationError("declared_next_route is not allowed for route")

        root = Path(project_root).resolve()
        allowed_roots = [root / ".aegis" / "artifacts", root / ".aegis" / "runtime"]
        package_path = require_under_any_root(
            envelope.package_path,
            allowed_roots,
            label="package_path",
        )
        manifest_path = require_under_any_root(
            envelope.package_manifest_path,
            allowed_roots,
            label="package_manifest_path",
        )
        if not package_path.exists():
            raise RouteValidationError("package_path does not exist")
        if not manifest_path.exists():
            raise RouteValidationError("package_manifest_path does not exist")
        actual_manifest_sha = sha256_file(manifest_path)
        if actual_manifest_sha != envelope.package_sha256:
            raise RouteValidationError("package_sha256 does not match package_manifest_path")

        manifest = read_manifest(manifest_path)
        if manifest.run_id != envelope.run_id:
            raise RouteValidationError("manifest run_id does not match envelope")
        if manifest.producer_module != envelope.source_module:
            raise RouteValidationError("manifest producer_module does not match envelope")
        if manifest.producer_module_instance_id != envelope.source_module_instance_id:
            raise RouteValidationError(
                "manifest producer_module_instance_id does not match envelope"
            )
        package_root = require_under_any_root(
            manifest.package_root,
            allowed_roots,
            label="manifest.package_root",
        )
        readme = Path(manifest.readme_path).resolve()
        if not readme.exists() or readme.name.lower() != "readme.md":
            raise RouteValidationError("manifest readme_path must point to README.md")
        if not (readme == package_root or readme.is_relative_to(package_root)):
            raise RouteValidationError("manifest readme_path must stay under package_root")
        for file_entry in manifest.files:
            rel = Path(file_entry.rel_path)
            if rel.is_absolute() or ".." in rel.parts:
                raise RouteValidationError("manifest file rel_path must be package-relative")
            file_path = package_root / rel
            if file_entry.required and not file_path.exists():
                raise RouteValidationError("required manifest file is missing")
            if file_path.exists() and sha256_file(file_path) != file_entry.sha256:
                raise RouteValidationError("manifest file sha256 mismatch")

        return RouteValidationResult(
            status="passed",
            source_module=envelope.source_module,
            target_module=envelope.target_module,
            handoff_kind=envelope.handoff_kind,
            envelope_ref=envelope.package_path,
            manifest_ref=envelope.package_manifest_path,
        )


def default_route_schema_registry() -> RouteSchemaRegistry:
    entries = [
        ("master", "debate", "master_requirement_to_debate", "Requirement debate package"),
        ("debate", "master", "debate_requirement_to_master", "Requirement adjudication package"),
        ("master", "execution", "master_to_execution", "Execution handoff package"),
        ("execution", "debate", "execution_route_to_debate", "Implementation route debate package"),
        ("debate", "execution", "debate_route_to_execution", "Implementation adjudication package"),
        ("execution", "test", "execution_to_test", "Execution-to-Test handoff package"),
        ("test", "execution", "test_to_execution_rework", "Test rework package"),
        ("test", "final_review", "test_to_final_review", "Test output package"),
        ("final_review", "master", "final_review_to_master", "Final Review output package"),
        ("master", "closeout", "master_closeout", "Master closeout package"),
    ]
    return RouteSchemaRegistry(
        [
            RouteSchemaRegistryEntry(
                source_module=source,  # type: ignore[arg-type]
                target_module=target,  # type: ignore[arg-type]
                handoff_kind=kind,
                expected_package_schema=schema,
                allowed_next_route_values=[target],  # type: ignore[list-item]
            )
            for source, target, kind, schema in entries
        ]
    )
