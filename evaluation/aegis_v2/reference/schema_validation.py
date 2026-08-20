from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource
except ImportError as exc:  # pragma: no cover - exercised by CLI preflight
    raise RuntimeError(
        "The independent reference model requires "
        "jsonschema[format-nongpl]==4.26.0."
    ) from exc

from .canonical import load_json


class LocalSchemaBundle:
    def __init__(self, schema_dir: str | Path):
        self.schema_dir = Path(schema_dir).resolve()
        self.schemas: dict[str, dict[str, Any]] = {}
        registry = Registry()
        for path in sorted(self.schema_dir.glob("*.schema.json")):
            schema = load_json(path)
            if not isinstance(schema, dict) or "$id" not in schema:
                continue
            resource = Resource.from_contents(schema)
            registry = registry.with_resource(schema["$id"], resource)
            self.schemas[path.name] = schema
        self.registry = registry

    def errors(self, instance: Any, schema_name: str) -> list[str]:
        schema = self.schemas.get(schema_name)
        if schema is None:
            return [f"schema not found in local bundle: {schema_name}"]
        validator = Draft202012Validator(
            schema,
            registry=self.registry,
            format_checker=FormatChecker(),
        )
        errors = sorted(
            validator.iter_errors(instance),
            key=lambda error: (
                tuple(str(part) for part in error.absolute_path),
                error.message,
            ),
        )
        rendered: list[str] = []
        for error in errors:
            pointer = "/" + "/".join(
                str(part).replace("~", "~0").replace("/", "~1")
                for part in error.absolute_path
            )
            rendered.append(f"{pointer}: {error.message}")
        return rendered


@lru_cache(maxsize=4)
def local_schema_bundle(schema_dir: str) -> LocalSchemaBundle:
    return LocalSchemaBundle(schema_dir)
