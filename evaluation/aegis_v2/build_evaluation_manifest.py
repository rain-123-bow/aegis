"""Deterministically render or check the Aegis v2 evaluation manifest.

The renderer has no write side effects.  It consumes already loaded values
and their exact preimage bytes, validates every bound source and fixture, and
returns a new candidate.  The CLI defaults to check mode.  Filesystem
replacement is intentionally disabled until a reparse-safe atomic commit
backend is available; callers can obtain exact bytes from
``render_evaluation_manifest_bytes``.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import ntpath
import os
import re
import stat
import sys
import urllib.parse
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

import jsonschema
import rfc8785
from referencing import Registry, Resource


EVALUATION_DIRECTORY = Path("evaluation/aegis_v2")
MANIFEST_PATH = EVALUATION_DIRECTORY / "evaluation_manifest.v1.json"
SOURCE_MANIFEST_PATH = (
    EVALUATION_DIRECTORY / "reference/source_manifest.v1.json"
)
FIXTURE_CATALOG_PATH = EVALUATION_DIRECTORY / "fixture_catalog.v1.json"
RISK_REGISTER_PATH = EVALUATION_DIRECTORY / "risk_register.v1.json"
EVALUATION_SCHEMA_PATH = Path(
    "schemas/aegis/v2/evaluation_manifest.v1.schema.json"
)
RUNNER_SCHEMA_PATH = Path(
    "schemas/aegis/v2/evaluation_runner_contract.v1.schema.json"
)
SOURCE_MANIFEST_SCHEMA_PATH = Path(
    "schemas/aegis/v2/reference_source_manifest.v1.schema.json"
)
COMMON_SCHEMA_PATH = Path("schemas/aegis/v2/common.v1.schema.json")
SCHEMA_BUNDLE_PATH = Path("schemas/aegis/v2/schema_bundle.v1.json")

SCHEMA_BASE = (
    "https://raw.githubusercontent.com/rain-123-bow/"
    "aegis/main/schemas/aegis/v2/"
)
RUNNER_INPUT_SCHEMA_ID = f"{SCHEMA_BASE}evaluation_runner_input.v1.schema.json"
SUT_DECISION_SCHEMA_ID = f"{SCHEMA_BASE}sut_decision.v1.schema.json"
RUNNER_OUTPUT_SCHEMA_ID = (
    f"{SCHEMA_BASE}evaluation_runner_output.v1.schema.json"
)
RUNNER_EXECUTION_RECORD_SCHEMA_ID = (
    f"{SCHEMA_BASE}runner_execution_record.v1.schema.json"
)
RUNNER_CONTRACT_SCHEMA_ID = (
    f"{SCHEMA_BASE}evaluation_runner_contract.v1.schema.json"
)
ISOLATION_BINDING_SCHEMA_ID = (
    f"{SCHEMA_BASE}evaluation_isolation_binding.v1.schema.json"
)
PYTHON_BINDING_SCHEMA_ID = (
    f"{SCHEMA_BASE}python_executable_binding.v1.schema.json"
)
PROPERTY_ENVELOPE_SCHEMA_ID = (
    f"{SCHEMA_BASE}property_instance_envelope.v1.schema.json"
)
PROPERTY_BUNDLE_SCHEMA_ID = (
    f"{SCHEMA_BASE}property_materialization_bundle.v1.schema.json"
)
PROPERTY_EXPECTED_SCHEMA_ID = (
    f"{SCHEMA_BASE}property_expected_record.v1.schema.json"
)
RUNNER_CONFORMANCE_RESULT_SCHEMA_ID = (
    f"{SCHEMA_BASE}runner_conformance_result.v1.schema.json"
)
SOURCE_MANIFEST_SCHEMA_ID = (
    f"{SCHEMA_BASE}reference_source_manifest.v1.schema.json"
)
FIXTURE_CATALOG_SCHEMA_ID = (
    f"{SCHEMA_BASE}evaluation_fixture_catalog.v1.schema.json"
)

# Phase 0A corpus identity anchors.  Counts prevent deletion; JCS hashes of
# sorted stable IDs prevent same-count substitution.
ORDINARY_CASE_BASELINE = (
    406,
    "cef7d228a5fb7d4f16ef24738fd85196b9f38dcba073c4aacc581deb7538d611",
)
RENDERED_CASES_BASELINE_SHA256 = (
    "133e9b281767546eb4b24057f996eda64302d18872edbb7ea6b5e60c780de803"
)
RENDERED_RUNNERS_BASELINE_SHA256 = (
    "6531eaf862ccad1b47ea6a0a4da1bcfddbcff3bddfbef745faf170995bb4b238"
)
RENDERED_PROPERTY_SUITES_BASELINE_SHA256 = (
    "fee0d69588bb146a9763542965d2148e0898ec9ad3fa1c2225915db99cf69a3c"
)
RENDERED_DENOMINATORS_BASELINE_SHA256 = (
    "86683c5c0dd07dce1940ed51a9bc453a13497ac1bc84465859214b80ec07b929"
)
RENDERED_CONFORMANCE_BASELINE_SHA256 = (
    "bc1b8df04c13de5a66cdcb2254ad91a2e14749c2590b61c79e091f4a3376e561"
)
STATIC_RUNNER_BASELINE = (
    16,
    26,
    "6a6c72a303f23f3361685d03ab5b8bd6350969f1456ab805d81d98839a85165b",
)
DENOMINATOR_BASELINE = (
    19,
    "321e3414b83e05d1c44a3593a9e1236b35d4bacd83fcb6b4112b75f600d66de4",
)
FIXTURE_BASELINE = (
    96,
    "4acd2fa6139d081b9335f94225036878c31d6a30df938a514280aa1a2dbd21fa",
)
SOURCE_MANIFEST_BASELINE_SHA256 = (
    "8b214722aef6963927fd476687ba43a327f4c9850e50da74b06afa166aa01ac6"
)
FIXTURE_CATALOG_BASELINE_SHA256 = (
    "bfacb90b65f4eac1b066e2c0cf94589f10f3b70295e58f57979aff67832eb86c"
)
RISK_REGISTER_BASELINE_SHA256 = (
    "sha256:a516b6990c43be69146f7b6f9769cb7501fd7ff8bec97b33b0e0e8f1a1d1c921"
)

# This allowlist is intentionally independent of the candidate source
# manifest.  A source-manifest update therefore cannot authorize a new
# standard-library capability by changing its own declarations.
SOURCE_ENTRY_STDLIB_ALLOWLIST = {
    "COMPARATOR-REFERENCE-TRACE-AUDITABLE-V1": frozenset(
        "__future__ copy datetime functools hashlib json pathlib re typing".split()
    ),
    "COMPARATOR-SUT-DECISION-EXACT-JCS-V1": frozenset(
        "__future__ copy datetime functools hashlib json pathlib re typing".split()
    ),
    "GENERATOR-BLOCKER-CLOSURE-CARTESIAN-V1": frozenset(
        (
            "__future__ collections.abc copy functools hashlib itertools "
            "json math pathlib typing"
        ).split()
    ),
    "GENERATOR-VERDICT-CARTESIAN-V1": frozenset(
        (
            "__future__ collections.abc copy functools hashlib itertools "
            "json math pathlib typing"
        ).split()
    ),
    "MATERIALIZER-BLOCKER-CLOSURE-RUNNER-INPUT-V1": frozenset(
        (
            "__future__ base64 binascii collections.abc copy datetime "
            "functools hashlib itertools json math pathlib typing"
        ).split()
    ),
    "MATERIALIZER-VERDICT-RUNNER-INPUT-V1": frozenset(
        (
            "__future__ base64 binascii collections.abc copy functools "
            "hashlib itertools json math pathlib re typing"
        ).split()
    ),
    "ORACLE-BLOCKER-CLOSURE-INDEPENDENCE-V1": frozenset(
        (
            "__future__ base64 binascii copy functools hashlib json "
            "pathlib re typing"
        ).split()
    ),
    "ORACLE-VERDICT-PRIORITY-TABLE-V1": frozenset(
        "__future__ copy hashlib json pathlib re typing".split()
    ),
    "REFERENCE-CLI-JSONL-V1": frozenset(
        (
            "__future__ argparse base64 binascii collections.abc copy "
            "datetime functools hashlib itertools json math pathlib re "
            "sys typing"
        ).split()
    ),
}
SOURCE_POLICY_ASSURANCE_BOUNDARIES = {
    "source_ast_policy": "FROZEN_SOURCE_CHANGE_REVIEW_GATE_ONLY",
    "network_filesystem_shell_runtime": "OS_ISOLATION_REQUIRED",
}

CONFORMANCE_INPUT_BINDING_ID = "BINDING-ISOLATION-GATE-1-V1"
CONFORMANCE_EXECUTION_ID = "019fa1ff-8282-7f00-8abc-000000000900"
PROPERTY_MATERIALIZERS = {
    "PROPERTY-BLOCKER-CLOSURE-EXHAUSTIVE-V1": {
        "algorithm_id": "MATERIALIZER-BLOCKER-CLOSURE-RUNNER-INPUT-V1",
        "input_binding_id": "BINDING-BLOCKER-CLOSURE-GATE-1-V1",
    },
    "PROPERTY-VERDICT-EXHAUSTIVE-V1": {
        "algorithm_id": "MATERIALIZER-VERDICT-RUNNER-INPUT-V1",
        "input_binding_id": "BINDING-VERDICT-FUNCTION-1-V1",
    },
}
PROPERTY_DOMAIN_ORDER = {
    "PROPERTY-BLOCKER-CLOSURE-EXHAUSTIVE-V1": [
        "origin_role",
        "owner_role",
        "reviewer_relation",
        "owner_evidence",
        "reviewer_evidence",
    ],
    "PROPERTY-VERDICT-EXHAUSTIVE-V1": [
        "cancel_state",
        "workflow_integrity",
        "evidence_state",
        "coverage_state",
        "report_state",
        "workflow_phase",
        "fact_mask",
    ],
}
ISOLATION_FIXTURE_IDS = {
    "certificate": "AEGIS-FIXTURE-V1-EVALUATOR-ISOLATION-CERTIFICATE",
    "deny": {
        "REPOSITORY_ROOT": (
            "AEGIS-FIXTURE-V1-EVALUATOR-ISOLATION-DENY-REPOSITORY-ROOT"
        ),
        "EVALUATION_CORPUS": (
            "AEGIS-FIXTURE-V1-EVALUATOR-ISOLATION-DENY-EVALUATION-CORPUS"
        ),
        "EXPECTED_DATA": (
            "AEGIS-FIXTURE-V1-EVALUATOR-ISOLATION-DENY-EXPECTED-DATA"
        ),
        "REFERENCE_SOURCES": (
            "AEGIS-FIXTURE-V1-EVALUATOR-ISOLATION-DENY-REFERENCE-SOURCES"
        ),
    },
    "network": "AEGIS-FIXTURE-V1-EVALUATOR-ISOLATION-NETWORK-PROBE",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ManifestBuildError(RuntimeError):
    """A deterministic, fail-closed manifest build failure."""


def _fail(message: str) -> NoReturn:
    raise ManifestBuildError(message)


def _reject_duplicate_members(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON member: {key!r}")
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> NoReturn:
    _fail(f"non-finite JSON number is forbidden: {value}")


def _parse_strict_json(raw: bytes, *, source: str) -> Any:
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail(f"UTF-8 BOM is forbidden: {source}")
    if b"\r" in raw:
        _fail(f"CR/CRLF is forbidden: {source}")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ManifestBuildError(
            f"invalid UTF-8 in {source}: {error}"
        ) from error
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_members,
            parse_constant=_reject_nonfinite_constant,
        )
    except ManifestBuildError:
        raise
    except (json.JSONDecodeError, ValueError) as error:
        raise ManifestBuildError(
            f"invalid JSON in {source}: {error}"
        ) from error


def _load_strict_json(path: Path) -> tuple[Any, bytes]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ManifestBuildError(f"cannot read {path}: {error}") from error
    return _parse_strict_json(raw, source=str(path)), raw


def _jcs(value: Any, *, source: str) -> bytes:
    try:
        return rfc8785.dumps(value)
    except (TypeError, ValueError, rfc8785.CanonicalizationError) as error:
        raise ManifestBuildError(
            f"RFC 8785 canonicalization failed for {source}: {error}"
        ) from error


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _value_sha256(value: Any, *, source: str) -> str:
    return _sha256(_jcs(value, source=source))


def _self_hash(
    value: Mapping[str, Any],
    field: str,
    *,
    prefixed: bool = True,
    source: str,
) -> str:
    preimage = copy.deepcopy(dict(value))
    preimage.pop(field, None)
    digest = _value_sha256(preimage, source=f"{source} preimage")
    return f"sha256:{digest}" if prefixed else digest


def _set_self_hash(
    value: dict[str, Any],
    field: str,
    *,
    prefixed: bool = True,
    source: str,
) -> None:
    value[field] = _self_hash(
        value,
        field,
        prefixed=prefixed,
        source=source,
    )


def _validate_identifier_baseline(
    identifiers: Sequence[Any],
    *,
    expected_count: int,
    expected_sha256: str,
    source: str,
) -> None:
    if len(identifiers) != expected_count:
        _fail(
            f"{source} baseline count mismatch: "
            f"expected={expected_count}, observed={len(identifiers)}"
        )
    if not all(
        isinstance(identifier, str) and identifier
        for identifier in identifiers
    ):
        _fail(f"{source} baseline contains an invalid identifier")
    if len(set(identifiers)) != len(identifiers):
        _fail(f"{source} baseline contains duplicate identifiers")
    observed_sha256 = _value_sha256(
        sorted(identifiers),
        source=f"{source} sorted identifier baseline",
    )
    if observed_sha256 != expected_sha256:
        _fail(
            f"{source} baseline identity mismatch: "
            f"expected={expected_sha256}, observed={observed_sha256}"
        )


def _validate_collection_baseline(
    values: Sequence[Any],
    *,
    expected_sha256: str,
    source: str,
) -> None:
    observed_sha256 = _value_sha256(values, source=source)
    if observed_sha256 != expected_sha256:
        _fail(
            f"{source} baseline mismatch: "
            f"expected={expected_sha256}, observed={observed_sha256}"
        )


def _require_object(value: Any, *, source: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{source} must be an object")
    return copy.deepcopy(dict(value))


def _require_list(value: Any, *, source: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(f"{source} must be an array")
    return value


def _unique_map(
    values: Sequence[Mapping[str, Any]],
    key: str,
    *,
    source: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for value in values:
        identifier = value.get(key)
        if not isinstance(identifier, str) or not identifier:
            _fail(f"{source} has invalid {key}")
        if identifier in result:
            _fail(f"duplicate {source} {key}: {identifier}")
        result[identifier] = copy.deepcopy(dict(value))
    return result


def _frozen_value(
    definition: Mapping[str, Any],
    *,
    schema: Mapping[str, Any],
    source: str,
) -> Any:
    if "const" in definition:
        return copy.deepcopy(definition["const"])
    if definition.get("type") == "null":
        return None
    reference = definition.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        name = reference.removeprefix("#/$defs/")
        target = schema.get("$defs", {}).get(name)
        if not isinstance(target, Mapping):
            _fail(f"{source} has unresolved local reference: {reference}")
        return _frozen_object(target, schema=schema, source=name)
    _fail(f"{source} is not frozen by a schema const")


def _frozen_object(
    definition: Mapping[str, Any],
    *,
    schema: Mapping[str, Any],
    source: str,
) -> dict[str, Any]:
    required = definition.get("required")
    properties = definition.get("properties")
    if not isinstance(required, list) or not isinstance(properties, Mapping):
        _fail(f"{source} is not a frozen object definition")
    result: dict[str, Any] = {}
    for key in required:
        property_schema = properties.get(key)
        if not isinstance(property_schema, Mapping):
            _fail(f"{source}.{key} schema is missing")
        result[key] = _frozen_value(
            property_schema,
            schema=schema,
            source=f"{source}.{key}",
        )
    return result


def _schema_definition(
    schema: Mapping[str, Any],
    name: str,
) -> Mapping[str, Any]:
    definition = schema.get("$defs", {}).get(name)
    if not isinstance(definition, Mapping):
        _fail(f"schema definition missing: {name}")
    return definition


def _validate_bound_json(
    value: Mapping[str, Any],
    raw: bytes,
    *,
    source: str,
) -> None:
    parsed = _parse_strict_json(raw, source=source)
    if parsed != value:
        _fail(f"{source} value does not match supplied raw bytes")


def _network_schema_resolution_forbidden(uri: str) -> NoReturn:
    _fail(f"network schema resolution is forbidden: {uri}")


def _walk_schema_references(value: Any) -> Sequence[str]:
    references: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in {"$ref", "$dynamicRef"}:
                if not isinstance(child, str):
                    _fail(f"schema {key} must be a string")
                references.append(child)
            else:
                references.extend(_walk_schema_references(child))
    elif isinstance(value, list):
        for child in value:
            references.extend(_walk_schema_references(child))
    return references


def _build_offline_schema_registry(
    schema_documents: Mapping[str, Mapping[str, Any]],
) -> tuple[Registry, dict[str, dict[str, Any]]]:
    if not schema_documents:
        _fail("offline schema bundle is empty")
    resources: list[tuple[str, Resource[Any]]] = []
    schemas_by_id: dict[str, dict[str, Any]] = {}
    source_for_id: dict[str, str] = {}
    for source, supplied_schema in sorted(schema_documents.items()):
        schema = _require_object(
            supplied_schema,
            source=f"schema document {source}",
        )
        schema_id = schema.get("$id")
        if not isinstance(schema_id, str) or not schema_id:
            _fail(f"schema document {source} has no nonempty $id")
        if schema_id in schemas_by_id:
            _fail(
                f"duplicate schema $id {schema_id}: "
                f"{source_for_id[schema_id]}, {source}"
            )
        if (
            schema.get("$schema")
            != "https://json-schema.org/draft/2020-12/schema"
        ):
            _fail(f"schema document {source} is not Draft 2020-12")
        try:
            jsonschema.Draft202012Validator.check_schema(schema)
            resources.append(
                (schema_id, Resource.from_contents(schema))
            )
        except (jsonschema.SchemaError, ValueError) as error:
            raise ManifestBuildError(
                f"schema document {source} is invalid: {error}"
            ) from error
        schemas_by_id[schema_id] = schema
        source_for_id[schema_id] = source

    for schema_id, schema in schemas_by_id.items():
        for reference in _walk_schema_references(schema):
            absolute = urllib.parse.urljoin(schema_id, reference)
            target_id, _ = urllib.parse.urldefrag(absolute)
            if target_id.startswith("https://json-schema.org/"):
                continue
            if target_id not in schemas_by_id:
                _fail(
                    "offline schema closure failure: "
                    f"{reference!r} from {source_for_id[schema_id]}"
                )

    registry = Registry(
        retrieve=_network_schema_resolution_forbidden
    ).with_resources(resources)
    return registry, schemas_by_id


def _validate_schema_bundle_inputs(
    schema_bundle: Mapping[str, Any],
    schema_bundle_raw: bytes,
    *,
    schema_documents: Mapping[str, Mapping[str, Any]],
    schema_raw_documents: Mapping[str, bytes],
) -> None:
    _validate_bound_json(
        schema_bundle,
        schema_bundle_raw,
        source="offline schema bundle",
    )
    if schema_bundle.get("bundle_sha256") != _self_hash(
        schema_bundle,
        "bundle_sha256",
        source="offline schema bundle",
    ):
        _fail("offline schema bundle self-hash mismatch")
    if schema_bundle.get("schema_version") != "SchemaBundle.v1":
        _fail("offline schema bundle version mismatch")
    resolution_policy = _require_object(
        schema_bundle.get("resolution_policy"),
        source="offline schema resolution policy",
    )
    if resolution_policy != {
        "all_schema_ids_preloaded_locally": True,
        "network_resolution_allowed": False,
        "unknown_schema_id_action": "REJECT",
    }:
        _fail("offline schema resolution policy mismatch")
    entries = _unique_map(
        _require_list(
            schema_bundle.get("schemas"),
            source="offline schema entries",
        ),
        "path",
        source="offline schema entry",
    )
    if list(entries) != sorted(entries):
        _fail("offline schema entries are not sorted")
    if set(entries) != set(schema_documents):
        _fail(
            "offline schema bundle membership mismatch: "
            f"declared={sorted(entries)}; "
            f"loaded={sorted(schema_documents)}"
        )
    if set(schema_raw_documents) != set(schema_documents):
        _fail("offline schema raw-document membership mismatch")
    for repository_path, entry in entries.items():
        _canonical_repository_path(
            repository_path,
            source="offline schema entry path",
        )
        raw = schema_raw_documents[repository_path]
        _validate_bound_json(
            schema_documents[repository_path],
            raw,
            source=f"offline schema document {repository_path}",
        )
        canonical = _jcs(
            schema_documents[repository_path],
            source=f"offline schema document {repository_path}",
        )
        if entry.get("byte_size") != len(canonical):
            _fail(
                f"offline schema JCS byte-size mismatch: {repository_path}"
            )
        if entry.get("sha256") != f"sha256:{_sha256(canonical)}":
            _fail(f"offline schema JCS hash mismatch: {repository_path}")


def _validate_schema_instance(
    instance: Any,
    *,
    schema: Mapping[str, Any],
    registry: Registry,
    source: str,
) -> None:
    try:
        validator = jsonschema.Draft202012Validator(
            dict(schema),
            registry=registry,
            format_checker=jsonschema.FormatChecker(),
        )
        errors = sorted(
            validator.iter_errors(instance),
            key=lambda error: (
                tuple(str(part) for part in error.absolute_path),
                error.message,
            ),
        )
    except ManifestBuildError:
        raise
    except Exception as error:
        raise ManifestBuildError(
            f"{source} schema evaluation failed: {error}"
        ) from error
    if errors:
        first = errors[0]
        location = "/".join(str(part) for part in first.absolute_path)
        _fail(
            f"{source} schema validation failed"
            f"{' at /' + location if location else ''}: {first.message}"
        )


def _validate_schema_fragment(
    instance: Any,
    *,
    schema_id: str,
    fragment: str,
    registry: Registry,
    source: str,
) -> None:
    wrapper = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": (
            "urn:aegis:builder-fragment:"
            + hashlib.sha256(source.encode("utf-8")).hexdigest()
        ),
        "$ref": f"{schema_id}#{fragment}",
    }
    _validate_schema_instance(
        instance,
        schema=wrapper,
        registry=registry,
        source=source,
    )


def _require_sorted_unique_strings(
    values: Any,
    *,
    source: str,
) -> list[str]:
    result = _require_list(values, source=source)
    if not all(isinstance(value, str) and value for value in result):
        _fail(f"{source} must contain nonempty strings")
    if len(result) != len(set(result)):
        _fail(f"{source} contains duplicates")
    if result != sorted(result):
        _fail(f"{source} is not sorted")
    return result


def _verify_bound_file(
    record: Mapping[str, Any],
    source_blobs: Mapping[str, bytes],
    *,
    source: str,
) -> str:
    repository_path = record.get("repository_path")
    _canonical_repository_path(repository_path, source=f"{source} path")
    raw = source_blobs.get(repository_path)
    if raw is None:
        _fail(f"{source} bytes missing: {repository_path}")
    if record.get("byte_size") != len(raw):
        _fail(f"{source} byte-size mismatch: {repository_path}")
    if record.get("raw_sha256") != _sha256(raw):
        _fail(f"{source} raw hash mismatch: {repository_path}")
    return repository_path


def _verify_source_entrypoint(
    entry: Mapping[str, Any],
    source_blobs: Mapping[str, bytes],
) -> None:
    direct_files = entry.get("direct_source_files")
    entrypoints = entry.get("entrypoints")
    if (
        not isinstance(direct_files, list)
        or not direct_files
        or not isinstance(entrypoints, list)
        or not entrypoints
    ):
        _fail(f"materializer entry is not executable: {entry.get('entry_id')}")
    parsed_files: dict[str, set[str]] = {}
    for repository_path in direct_files:
        raw = source_blobs.get(repository_path)
        if raw is None:
            _fail(
                "materializer direct source bytes missing: "
                f"{repository_path}"
            )
        try:
            tree = ast.parse(raw, filename=repository_path)
        except (SyntaxError, ValueError) as error:
            raise ManifestBuildError(
                f"materializer source is invalid: {repository_path}: {error}"
            ) from error
        parsed_files[repository_path] = {
            node.name
            for node in tree.body
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            )
        }
    for entrypoint in entrypoints:
        if not isinstance(entrypoint, str) or "." not in entrypoint:
            _fail(f"invalid materializer entrypoint: {entrypoint!r}")
        module, symbol = entrypoint.rsplit(".", 1)
        expected_path = module.replace(".", "/") + ".py"
        if expected_path not in parsed_files:
            _fail(
                f"materializer entrypoint is outside direct source: "
                f"{entrypoint}"
            )
        if symbol not in parsed_files[expected_path]:
            _fail(f"materializer entrypoint symbol missing: {entrypoint}")


def _local_source_dependencies(
    repository_path: str,
    *,
    raw: bytes,
    source_paths: set[str],
) -> set[str]:
    try:
        tree = ast.parse(raw, filename=repository_path)
    except (SyntaxError, ValueError) as error:
        raise ManifestBuildError(
            f"reference source is invalid: {repository_path}: {error}"
        ) from error
    package_parts = list(PurePosixPath(repository_path).with_suffix("").parts)
    if package_parts[-1] == "__init__":
        package_parts = package_parts[:-1]
    else:
        package_parts = package_parts[:-1]
    local_prefix = "evaluation/aegis_v2/reference/"
    dependencies = {f"{local_prefix}__init__.py"}

    def add_module(module_parts: Sequence[str], *, local: bool) -> None:
        module_path = "/".join(module_parts)
        candidates = (
            f"{module_path}.py",
            f"{module_path}/__init__.py",
        )
        matched = False
        for candidate in candidates:
            if candidate in source_paths:
                dependencies.add(candidate)
                matched = True
        if local and not matched:
            _fail(
                "reference source imports an undeclared local module: "
                f"{repository_path} -> {module_path}"
            )

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                keep = len(package_parts) - (node.level - 1)
                if keep < 0:
                    _fail(
                        "reference source relative import escapes package: "
                        f"{repository_path}"
                    )
                module_parts = package_parts[:keep]
                if node.module:
                    module_parts.extend(node.module.split("."))
                    add_module(module_parts, local=True)
                else:
                    for alias in node.names:
                        add_module(
                            [*module_parts, alias.name],
                            local=True,
                        )
            elif (
                isinstance(node.module, str)
                and node.module.startswith(
                    "evaluation.aegis_v2.reference"
                )
            ):
                add_module(node.module.split("."), local=True)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(
                    "evaluation.aegis_v2.reference"
                ):
                    add_module(alias.name.split("."), local=True)
    return dependencies


def _attribute_name(node: ast.AST) -> str | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def _verify_source_import_policy(
    entry: Mapping[str, Any],
    *,
    source_blobs: Mapping[str, bytes],
) -> None:
    entry_id = entry.get("entry_id")
    if not isinstance(entry_id, str):
        _fail("algorithm entry has invalid entry_id")
    allowed_stdlib_modules = SOURCE_ENTRY_STDLIB_ALLOWLIST.get(entry_id)
    if allowed_stdlib_modules is None:
        _fail(f"algorithm {entry_id} has no frozen standard-library allowlist")
    import_policy = _require_object(
        entry.get("import_policy"),
        source=f"import policy for {entry_id}",
    )
    dependency_policy = _require_object(
        entry.get("dependency_policy"),
        source=f"dependency policy for {entry_id}",
    )
    allowed_local_prefix = import_policy.get("allowed_local_prefix")
    production_roots = set(
        _require_sorted_unique_strings(
            import_policy.get("production_package_roots"),
            source=f"production package roots for {entry_id}",
        )
    )
    distributions = _require_list(
        dependency_policy.get("third_party_distributions"),
        source=f"third-party distributions for {entry_id}",
    )
    allowed_third_party = {
        str(distribution.get("name")).replace("-", "_")
        for distribution in distributions
        if isinstance(distribution, Mapping)
    }
    forbidden_dynamic_calls = {
        "__import__",
        "eval",
        "exec",
        "compile",
        "importlib.import_module",
        "importlib.util.module_from_spec",
        "importlib.util.spec_from_file_location",
    }
    forbidden_dynamic_suffixes = {
        ".exec_module",
        ".load_module",
        ".SourceFileLoader",
        ".ExtensionFileLoader",
    }
    forbidden_dynamic_terminals = {
        "__import__",
        "eval",
        "exec",
        "exec_module",
        "import_module",
        "load_module",
        "module_from_spec",
        "spec_from_file_location",
    }
    forbidden_dynamic_primitives = {
        "__builtins__",
        "__import__",
        "compile",
        "eval",
        "exec",
        "getattr",
        "globals",
        "locals",
        "setattr",
        "vars",
    }
    allowed_sys_members = {"stderr", "stdin", "stdout"}
    forbidden_runtime_import_registry_attributes = {
        "meta_path",
        "modules",
        "path",
        "path_hooks",
        "path_importer_cache",
    }
    forbidden_reflection_attributes = {
        "__bases__",
        "__class__",
        "__dict__",
        "__getattribute__",
        "__globals__",
        "__mro__",
        "__subclasses__",
    }
    forbidden_network_roots = {
        "asyncio",
        "ftplib",
        "http",
        "imaplib",
        "poplib",
        "smtplib",
        "socket",
        "telnetlib",
        "urllib",
        "xmlrpc",
    }
    forbidden_shell_roots = {
        "multiprocessing",
        "pty",
        "subprocess",
    }
    forbidden_dynamic_roots = {
        "ctypes",
        "importlib",
        "pkgutil",
        "runpy",
    }
    forbidden_os_members = {
        "fork",
        "forkpty",
        "popen",
        "startfile",
        "system",
    }

    def verify_import(module_name: str, repository_path: str) -> None:
        root = module_name.split(".", 1)[0]
        if (
            dependency_policy.get("network_access") == "DENIED"
            and root in forbidden_network_roots
        ):
            _fail(
                f"algorithm {entry_id} imports network-capable module "
                f"{root}: {repository_path}"
            )
        if (
            dependency_policy.get("shell_execution") == "FORBIDDEN"
            and root in forbidden_shell_roots
        ):
            _fail(
                f"algorithm {entry_id} imports shell-capable module "
                f"{root}: {repository_path}"
            )
        if (
            import_policy.get("dynamic_sut_loading") == "FORBIDDEN"
            and root in forbidden_dynamic_roots
        ):
            _fail(
                f"algorithm {entry_id} imports dynamic loader module "
                f"{root}: {repository_path}"
            )
        if root in production_roots:
            _fail(
                f"algorithm {entry_id} imports forbidden production "
                f"package {root}: {repository_path}"
            )
        if root == "evaluation":
            if (
                not isinstance(allowed_local_prefix, str)
                or not (
                    module_name == allowed_local_prefix
                    or module_name.startswith(
                        f"{allowed_local_prefix}."
                    )
                )
            ):
                _fail(
                    f"algorithm {entry_id} imports outside its local "
                    f"prefix: {module_name}"
                )
            return
        if root in sys.stdlib_module_names:
            if module_name not in allowed_stdlib_modules:
                _fail(
                    f"algorithm {entry_id} imports undeclared "
                    f"standard-library module {module_name}: "
                    f"{repository_path}"
                )
            return
        normalized_root = root.replace("-", "_")
        if normalized_root not in allowed_third_party:
            _fail(
                f"algorithm {entry_id} imports unlisted third-party "
                f"module {root}: {repository_path}"
            )

    owned_files = _require_list(
        entry.get("owned_source_files"),
        source=f"owned source files for {entry_id}",
    )
    for binding in owned_files:
        if not isinstance(binding, Mapping):
            _fail(f"algorithm {entry_id} has invalid owned source binding")
        repository_path = binding.get("repository_path")
        raw = source_blobs.get(repository_path)
        if raw is None:
            _fail(
                f"algorithm {entry_id} source bytes missing: "
                f"{repository_path}"
            )
        try:
            tree = ast.parse(raw, filename=repository_path)
        except (SyntaxError, ValueError) as error:
            raise ManifestBuildError(
                f"reference source is invalid: {repository_path}: {error}"
            ) from error
        sys_aliases = {
            alias.asname or "sys"
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
            if alias.name == "sys"
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    verify_import(alias.name, str(repository_path))
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module is not None:
                    verify_import(node.module, str(repository_path))
                    if node.module == "sys":
                        for alias in node.names:
                            if alias.name not in allowed_sys_members:
                                _fail(
                                    f"algorithm {entry_id} imports "
                                    f"forbidden sys member {alias.name}: "
                                    f"{repository_path}"
                                )
                    if (
                        node.module == "os"
                        and dependency_policy.get("shell_execution")
                        == "FORBIDDEN"
                    ):
                        for alias in node.names:
                            if (
                                alias.name in forbidden_os_members
                                or alias.name.startswith("exec")
                                or alias.name.startswith("spawn")
                            ):
                                _fail(
                                    f"algorithm {entry_id} imports "
                                    "forbidden OS execution member "
                                    f"{alias.name}: {repository_path}"
                                )
            elif isinstance(node, ast.Call):
                call_name = _attribute_name(node.func)
                if call_name is None:
                    continue
                if (
                    call_name in forbidden_dynamic_calls
                    or call_name.rsplit(".", 1)[-1]
                    in forbidden_dynamic_terminals
                    or any(
                        call_name.endswith(suffix)
                        for suffix in forbidden_dynamic_suffixes
                    )
                ):
                    _fail(
                        f"algorithm {entry_id} uses forbidden dynamic "
                        f"loading call {call_name}: {repository_path}"
                    )
                if (
                    dependency_policy.get("shell_execution")
                    == "FORBIDDEN"
                    and (
                        call_name.startswith("subprocess.")
                        or call_name in {"os.system", "os.popen"}
                        or call_name.startswith("os.spawn")
                        or call_name.startswith("os.exec")
                    )
                ):
                    _fail(
                        f"algorithm {entry_id} uses forbidden shell "
                        f"call {call_name}: {repository_path}"
                    )
            elif isinstance(node, ast.Attribute):
                if (
                    node.attr
                    in forbidden_runtime_import_registry_attributes
                ):
                    _fail(
                        f"algorithm {entry_id} accesses forbidden runtime "
                        f"import registry member {node.attr}: "
                        f"{repository_path}"
                    )
                if node.attr in forbidden_reflection_attributes:
                    _fail(
                        f"algorithm {entry_id} accesses forbidden "
                        f"reflection member {node.attr}: {repository_path}"
                    )
                attribute_name = _attribute_name(node)
                if attribute_name is not None:
                    parts = attribute_name.split(".")
                    if (
                        len(parts) > 1
                        and parts[0] in sys_aliases
                        and parts[1] not in allowed_sys_members
                    ):
                        _fail(
                            f"algorithm {entry_id} accesses forbidden "
                            f"sys member {parts[1]}: {repository_path}"
                        )
            elif (
                isinstance(node, ast.Name)
                and node.id in forbidden_dynamic_primitives
            ):
                _fail(
                    f"algorithm {entry_id} references forbidden dynamic "
                    f"primitive {node.id}: {repository_path}"
                )
            elif isinstance(node, ast.Attribute):
                attribute_name = _attribute_name(node)
                if attribute_name is None:
                    continue
                if (
                    attribute_name in {"os.system", "os.popen", "os.startfile"}
                    or attribute_name.startswith("os.exec")
                    or attribute_name.startswith("os.spawn")
                ):
                    _fail(
                        f"algorithm {entry_id} references forbidden OS "
                        f"execution member {attribute_name}: "
                        f"{repository_path}"
                    )


def _verify_owned_source_closure(
    entry: Mapping[str, Any],
    *,
    sources: Mapping[str, Mapping[str, Any]],
    source_blobs: Mapping[str, bytes],
) -> None:
    entry_id = entry.get("entry_id")
    direct_files = _require_list(
        entry.get("direct_source_files"),
        source=f"direct source files for {entry_id}",
    )
    owned_bindings = _require_list(
        entry.get("owned_source_files"),
        source=f"owned source files for {entry_id}",
    )
    owned_paths = [
        binding.get("repository_path")
        if isinstance(binding, Mapping)
        else None
        for binding in owned_bindings
    ]
    if not all(isinstance(path, str) and path for path in owned_paths):
        _fail(f"algorithm {entry_id} has invalid owned source path")
    if len(owned_paths) != len(set(owned_paths)):
        _fail(f"algorithm {entry_id} has duplicate owned source path")
    source_paths = set(sources)
    for repository_path in direct_files:
        if repository_path not in source_paths:
            _fail(
                f"algorithm {entry_id} has undeclared direct source: "
                f"{repository_path}"
            )

    closure: set[str] = set()
    pending = list(direct_files)
    while pending:
        repository_path = pending.pop()
        if repository_path in closure:
            continue
        raw = source_blobs.get(repository_path)
        if raw is None:
            _fail(
                f"algorithm {entry_id} source bytes missing: "
                f"{repository_path}"
            )
        closure.add(repository_path)
        pending.extend(
            _local_source_dependencies(
                repository_path,
                raw=raw,
                source_paths=source_paths,
            )
            - closure
        )
    if set(owned_paths) != closure:
        _fail(
            f"algorithm {entry_id} owned source closure mismatch: "
            f"declared={sorted(owned_paths)}; required={sorted(closure)}"
        )


def _validate_source_manifest(
    source_manifest: Mapping[str, Any],
    source_manifest_raw: bytes,
    source_blobs: Mapping[str, bytes],
    *,
    source_manifest_schema: Mapping[str, Any],
    schema_registry: Registry,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    _validate_bound_json(
        source_manifest,
        source_manifest_raw,
        source="reference source manifest",
    )
    _validate_schema_instance(
        source_manifest,
        schema=source_manifest_schema,
        registry=schema_registry,
        source="reference source manifest",
    )
    if source_manifest.get("manifest_sha256") != _self_hash(
        source_manifest,
        "manifest_sha256",
        prefixed=False,
        source="reference source manifest",
    ):
        _fail("reference source manifest self-hash mismatch")
    sources = _unique_map(
        _require_list(
            source_manifest.get("source_files"),
            source="reference source files",
        ),
        "repository_path",
        source="reference source",
    )
    if list(sources) != sorted(sources):
        _fail("reference source_files are not sorted")
    bound_paths: dict[str, str] = {}

    def remember_path(repository_path: str, binding: str) -> None:
        folded = repository_path.casefold()
        previous = bound_paths.get(folded)
        if previous is not None:
            _fail(
                "duplicate reference source bound path: "
                f"{repository_path} ({previous}, {binding})"
            )
        bound_paths[folded] = binding

    for repository_path, record in sources.items():
        verified_path = _verify_bound_file(
            record,
            source_blobs,
            source="reference source",
        )
        remember_path(verified_path, "source_files")

    assurance_files = _unique_map(
        _require_list(
            source_manifest.get("assurance_files"),
            source="reference assurance files",
        ),
        "repository_path",
        source="reference assurance file",
    )
    if list(assurance_files) != sorted(assurance_files):
        _fail("reference assurance_files are not sorted")
    for record in assurance_files.values():
        verified_path = _verify_bound_file(
            record,
            source_blobs,
            source="reference assurance file",
        )
        remember_path(verified_path, "assurance_files")

    runtime_binding = _require_object(
        source_manifest.get("runtime_binding"),
        source="reference runtime binding",
    )
    for binding_name in ("pyproject", "lock", "schema_bundle"):
        binding = _require_object(
            runtime_binding.get(binding_name),
            source=f"reference runtime {binding_name} binding",
        )
        verified_path = _verify_bound_file(
            binding,
            source_blobs,
            source=f"reference runtime {binding_name}",
        )
        remember_path(verified_path, f"runtime_binding.{binding_name}")

    entries = _unique_map(
        _require_list(
            source_manifest.get("algorithm_entries"),
            source="reference algorithm entries",
        ),
        "entry_id",
        source="reference algorithm entry",
    )
    if list(entries) != sorted(entries):
        _fail("reference algorithm_entries are not sorted")
    for entry_id, entry in entries.items():
        if entry.get("entry_sha256") != _self_hash(
            entry,
            "entry_sha256",
            prefixed=False,
            source=f"reference algorithm entry {entry_id}",
        ):
            _fail(f"reference algorithm entry self-hash mismatch: {entry_id}")
        _require_sorted_unique_strings(
            entry.get("entrypoints"),
            source=f"entrypoints for {entry_id}",
        )
        _require_sorted_unique_strings(
            entry.get("direct_source_files"),
            source=f"direct source files for {entry_id}",
        )
        owned_source_files = _require_list(
            entry.get("owned_source_files"),
            source=f"owned source files for {entry_id}",
        )
        owned_paths = [
            owned.get("repository_path")
            if isinstance(owned, Mapping)
            else None
            for owned in owned_source_files
        ]
        _require_sorted_unique_strings(
            owned_paths,
            source=f"owned source paths for {entry_id}",
        )
        for owned in _require_list(
            entry.get("owned_source_files"),
            source=f"owned source files for {entry_id}",
        ):
            repository_path = owned.get("repository_path")
            source_record = sources.get(repository_path)
            if source_record is None:
                _fail(
                    f"algorithm {entry_id} owns undeclared source: "
                    f"{repository_path}"
                )
            for field in ("byte_size", "raw_sha256"):
                if owned.get(field) != source_record.get(field):
                    _fail(
                        f"algorithm {entry_id} source binding mismatch: "
                        f"{repository_path}"
                    )
        _verify_owned_source_closure(
            entry,
            sources=sources,
            source_blobs=source_blobs,
        )
        _verify_source_entrypoint(entry, source_blobs)
        _verify_source_import_policy(
            entry,
            source_blobs=source_blobs,
        )

    specs = _unique_map(
        _require_list(
            source_manifest.get("comparator_specs"),
            source="reference comparator specs",
        ),
        "comparator_id",
        source="reference comparator spec",
    )
    if list(specs) != sorted(specs):
        _fail("reference comparator_specs are not sorted")
    for comparator_id, spec in specs.items():
        if spec.get("spec_sha256") != _self_hash(
            spec,
            "spec_sha256",
            prefixed=False,
            source=f"reference comparator spec {comparator_id}",
        ):
            _fail(
                "reference comparator spec self-hash mismatch: "
                f"{comparator_id}"
            )
        algorithm_entry_id = spec.get("algorithm_entry_id")
        algorithm_entry = entries.get(algorithm_entry_id)
        if algorithm_entry is None:
            _fail(
                f"comparator {comparator_id} algorithm entry missing: "
                f"{algorithm_entry_id}"
            )
        if spec.get("algorithm_entry_sha256") != algorithm_entry.get(
            "entry_sha256"
        ):
            _fail(
                f"comparator {comparator_id} algorithm entry hash mismatch"
            )
        trace_entry_id = spec.get("trace_algorithm_entry_id")
        trace_entry_hash = spec.get("trace_algorithm_entry_sha256")
        if trace_entry_id is None:
            if trace_entry_hash is not None:
                _fail(
                    f"comparator {comparator_id} has orphan trace entry hash"
                )
        else:
            trace_entry = entries.get(trace_entry_id)
            if trace_entry is None:
                _fail(
                    f"comparator {comparator_id} trace entry missing: "
                    f"{trace_entry_id}"
                )
            if trace_entry_hash != trace_entry.get("entry_sha256"):
                _fail(
                    f"comparator {comparator_id} trace entry hash mismatch"
                )
    for materializer in PROPERTY_MATERIALIZERS.values():
        entry = entries.get(materializer["algorithm_id"])
        if entry is None:
            _fail(
                "property materializer source missing: "
                f"{materializer['algorithm_id']}"
            )
        expected_separation = _frozen_object(
            _schema_definition(
                source_manifest_schema,
                "materializerSeparationPolicy",
            ),
            schema=source_manifest_schema,
            source="materializerSeparationPolicy",
        )
        if entry.get("separation_policy") != expected_separation:
            _fail(
                "property materializer separation policy mismatch: "
                f"{materializer['algorithm_id']}"
            )
    if (
        source_manifest.get("manifest_sha256")
        != SOURCE_MANIFEST_BASELINE_SHA256
    ):
        _fail("reference source manifest baseline mismatch")
    return entries, specs


def _normalise_static_runner_contracts(
    template: Mapping[str, Any],
    *,
    runner_schema: Mapping[str, Any],
    fixture_catalog: Mapping[str, Any],
    comparator_specs: Mapping[str, Mapping[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    executable_policy = _frozen_object(
        _schema_definition(runner_schema, "executableBindingPolicy"),
        schema=runner_schema,
        source="executableBindingPolicy",
    )
    isolation_policy = _frozen_object(
        _schema_definition(runner_schema, "isolationPolicy"),
        schema=runner_schema,
        source="isolationPolicy",
    )
    sut_definition = _schema_definition(runner_schema, "sut")
    contracts = _require_list(
        template.get("runner_contracts"),
        source="runner contracts",
    )
    static_inputs = [
        contract
        for contract in contracts
        if contract.get("fixture_mount", {}).get("source")
        != "PROPERTY_INSTANCE_MATERIALIZATION"
    ]
    static_binding_ids = [
        binding.get("input_binding_id")
        for contract in static_inputs
        for binding in _require_list(
            contract.get("input_bindings"),
            source="static runner input bindings",
        )
        if isinstance(binding, Mapping)
    ]
    expected_runner_count, expected_binding_count, binding_sha256 = (
        STATIC_RUNNER_BASELINE
    )
    if len(static_inputs) != expected_runner_count:
        _fail(
            "static runner baseline count mismatch: "
            f"expected={expected_runner_count}, "
            f"observed={len(static_inputs)}"
        )
    _validate_identifier_baseline(
        static_binding_ids,
        expected_count=expected_binding_count,
        expected_sha256=binding_sha256,
        source="static runner input binding",
    )
    if not static_inputs:
        _fail("no static runner contracts")

    result: list[dict[str, Any]] = []
    aliases: dict[str, dict[str, Any]] = {}
    seen_old_ids: set[str] = set()
    for original in static_inputs:
        contract = _require_object(original, source="runner contract")
        old_id = contract.get("runner_contract_id")
        if not isinstance(old_id, str) or old_id in seen_old_ids:
            _fail(f"duplicate or invalid runner contract ID: {old_id!r}")
        seen_old_ids.add(old_id)
        contract["runner_input_schema_id"] = RUNNER_INPUT_SCHEMA_ID
        contract["sut_output_schema_id"] = SUT_DECISION_SCHEMA_ID
        contract["runner_output_schema_id"] = RUNNER_OUTPUT_SCHEMA_ID
        contract["runner_execution_record_schema_id"] = (
            RUNNER_EXECUTION_RECORD_SCHEMA_ID
        )
        contract["executable_binding_policy"] = copy.deepcopy(
            executable_policy
        )
        contract["isolation_policy"] = copy.deepcopy(isolation_policy)
        mount = _require_object(
            contract.get("fixture_mount"),
            source=f"runner {old_id} fixture mount",
        )
        mount["source"] = "STATIC_CATALOG"
        mount["catalog_id"] = (
            f"sha256:{fixture_catalog['catalog_sha256']}"
        )
        mount["catalog_sha256"] = fixture_catalog["catalog_sha256"]
        contract["fixture_mount"] = mount
        bindings = _require_list(
            contract.get("input_bindings"),
            source=f"runner {old_id} input bindings",
        )
        binding_ids: set[str] = set()
        normalised_bindings: list[dict[str, Any]] = []
        for original_binding in bindings:
            binding = _require_object(
                original_binding,
                source=f"runner {old_id} input binding",
            )
            binding_id = binding.get("input_binding_id")
            if (
                not isinstance(binding_id, str)
                or binding_id in binding_ids
            ):
                _fail(
                    f"duplicate or invalid input binding in runner {old_id}: "
                    f"{binding_id!r}"
                )
            binding_ids.add(binding_id)
            sut = _require_object(
                binding.get("sut"),
                source=f"input binding {binding_id} SUT",
            )
            sut.pop("executable_binding_policy", None)
            for field in sut_definition.get("required", []):
                property_schema = sut_definition.get(
                    "properties", {}
                ).get(field)
                if (
                    isinstance(property_schema, Mapping)
                    and "const" in property_schema
                ):
                    sut[field] = copy.deepcopy(property_schema["const"])
            binding["sut"] = sut
            binding.pop("output_schema", None)
            binding["sut_output_schema"] = {
                "schema_id": SUT_DECISION_SCHEMA_ID,
                "json_pointer": "",
            }
            binding["runner_output_schema"] = {
                "schema_id": RUNNER_OUTPUT_SCHEMA_ID,
                "json_pointer": "",
            }
            old_comparator = _require_object(
                binding.get("comparator"),
                source=f"input binding {binding_id} comparator",
            )
            comparator_id = old_comparator.get("comparator_id")
            comparator_spec = comparator_specs.get(str(comparator_id))
            if comparator_spec is None:
                _fail(
                    f"input binding comparator source missing: "
                    f"{comparator_id}"
                )
            binding["comparator"] = {
                "comparator_id": comparator_id,
                "kind": "SUT_DECISION_SHA256_EXACT",
                "spec_sha256": comparator_spec["spec_sha256"],
                "observed_source": (
                    "EVALUATION_RUNNER_OUTPUT.SUT_DECISION"
                ),
                "expected_source": "EVALUATION_CASE.EXPECTED",
                "hash_member": "sut_decision_sha256",
                "required_runner_state": "SUT_DECISION_READY",
                "exact_array_order": old_comparator[
                    "exact_array_order"
                ],
                "exact_reason_order": old_comparator[
                    "exact_reason_order"
                ],
            }
            oracle = _require_object(
                binding.get("oracle"),
                source=f"input binding {binding_id} oracle",
            )
            oracle["expected_source"] = "OUTER_CASE_EXPECTED_ONLY"
            binding["oracle"] = oracle
            normalised_bindings.append(binding)
        contract["input_bindings"] = sorted(
            normalised_bindings,
            key=lambda item: item["input_binding_id"],
        )
        _set_self_hash(
            contract,
            "runner_contract_id",
            source=f"runner contract {old_id}",
        )
        new_id = contract["runner_contract_id"]
        aliases[old_id] = contract
        aliases[new_id] = contract
        result.append(contract)
    if len({item["runner_contract_id"] for item in result}) != len(result):
        _fail("normalised static runner contract IDs are not unique")
    return result, aliases


def _resolve_static_binding(
    static_contracts: Sequence[Mapping[str, Any]],
    input_binding_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for contract in static_contracts:
        for binding in contract["input_bindings"]:
            if binding["input_binding_id"] == input_binding_id:
                matches.append(
                    (
                        copy.deepcopy(dict(contract)),
                        copy.deepcopy(dict(binding)),
                    )
                )
    if len(matches) != 1:
        _fail(
            f"expected exactly one static runner input binding "
            f"{input_binding_id}; found {len(matches)}"
        )
    return matches[0]


def _build_property_contracts_and_suites(
    suites: Sequence[Mapping[str, Any]],
    *,
    static_contracts: Sequence[Mapping[str, Any]],
    source_entries: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(suites) != 2:
        _fail(f"expected exactly two property suites; found {len(suites)}")
    property_contracts: list[dict[str, Any]] = []
    rendered_suites: list[dict[str, Any]] = []
    for original_suite in suites:
        suite = _require_object(original_suite, source="property suite")
        suite_id = suite.get("suite_id")
        materializer = PROPERTY_MATERIALIZERS.get(str(suite_id))
        if materializer is None:
            _fail(f"unknown property suite: {suite_id}")
        generator = _require_object(
            suite.get("generator"),
            source=f"property suite {suite_id} generator",
        )
        oracle = _require_object(
            suite.get("reference_oracle"),
            source=f"property suite {suite_id} oracle",
        )
        generator_entry = source_entries.get(
            str(generator.get("algorithm_id"))
        )
        oracle_entry = source_entries.get(
            str(oracle.get("algorithm_id"))
        )
        materializer_entry = source_entries.get(
            materializer["algorithm_id"]
        )
        if generator_entry is None or oracle_entry is None:
            _fail(f"property source missing: {suite_id}")
        if materializer_entry is None:
            _fail(f"property materializer source missing: {suite_id}")

        base_contract, selected_binding = _resolve_static_binding(
            static_contracts,
            materializer["input_binding_id"],
        )
        property_contract = copy.deepcopy(base_contract)
        property_contract["fixture_mount"] = {
            "source": "PROPERTY_INSTANCE_MATERIALIZATION",
            "materialization_bundle_schema_id": (
                PROPERTY_BUNDLE_SCHEMA_ID
            ),
            "materializer_algorithm_id": materializer_entry["entry_id"],
            "materializer_source_manifest_entry_sha256": (
                materializer_entry["entry_sha256"]
            ),
            "bundle_self_hash_member": "bundle_sha256",
            "bundle_self_hash_rule": (
                "sha256:JCS(PropertyMaterializationBundle object with "
                "bundle_sha256 omitted; every other member retained)"
            ),
            "bundle_fixture_array_pointer": "/sut_materialized_fixtures",
            "bundle_fixture_set_hash_member": (
                "sut_materialized_fixtures_jcs_sha256"
            ),
            "logical_runtime_root": base_contract["fixture_mount"][
                "logical_runtime_root"
            ],
            "materialization": (
                "DECODE_VERIFY_AND_COPY_BUNDLE_FIXTURES_ONLY"
            ),
            "access_mode": "READ_ONLY",
            "envelope_mount": "FORBIDDEN",
            "expected_store_mount": "FORBIDDEN",
        }
        selected_binding["comparator"]["expected_source"] = (
            "PROPERTY_EXPECTED_RECORD.EXPECTED"
        )
        selected_binding["oracle"]["expected_source"] = (
            "PROPERTY_EXPECTED_RECORD_ONLY"
        )
        property_contract["input_bindings"] = [selected_binding]
        _set_self_hash(
            property_contract,
            "runner_contract_id",
            source=f"property runner {suite_id}",
        )
        property_contracts.append(property_contract)

        domain = suite.get("domain")
        if not isinstance(domain, Mapping) or not domain:
            _fail(f"property suite domain invalid: {suite_id}")
        derived_domain_order = PROPERTY_DOMAIN_ORDER[suite_id]
        if set(domain) != set(derived_domain_order):
            _fail(f"property suite domain fields mismatch: {suite_id}")
        if "domain_order" in suite and (
            suite["domain_order"] != derived_domain_order
        ):
            _fail(f"property suite domain_order mismatch: {suite_id}")
        expected_count = 1
        for name, values in domain.items():
            if not isinstance(values, list) or not values:
                _fail(f"property suite domain is empty: {suite_id}.{name}")
            encoded = [_jcs(value, source=f"{suite_id}.{name}") for value in values]
            if len(encoded) != len(set(encoded)):
                _fail(
                    f"property suite domain has JCS duplicates: "
                    f"{suite_id}.{name}"
                )
            expected_count *= len(values)
        if suite.get("expected_instance_count") != expected_count:
            _fail(f"property suite instance count mismatch: {suite_id}")

        suite["sut_runner_contract_id"] = property_contract[
            "runner_contract_id"
        ]
        suite["domain_order"] = derived_domain_order
        generator.pop("source_sha256", None)
        generator["source_manifest_entry_sha256"] = generator_entry[
            "entry_sha256"
        ]
        generator["output_schema_ref"] = PROPERTY_ENVELOPE_SCHEMA_ID
        generator["output_visibility"] = (
            "EVALUATOR_ONLY_NEVER_SUT_READABLE"
        )
        suite["generator"] = generator
        suite["input_materializer"] = {
            "algorithm_id": materializer_entry["entry_id"],
            "algorithm_version": "1.0.0",
            "source_manifest_entry_sha256": materializer_entry[
                "entry_sha256"
            ],
            "input_binding_id": materializer["input_binding_id"],
            "input_schema_ref": PROPERTY_ENVELOPE_SCHEMA_ID,
            "output_schema_ref": PROPERTY_BUNDLE_SCHEMA_ID,
            "case_id_algorithm": (
                "concat(suite_id,'-INSTANCE-',"
                "one_based_ordinal_zero_padded_6)"
            ),
            "identity_validation_policy": (
                "INSTANCE_ID_AND_CASE_ID_RECOMPUTED_BEFORE_MATERIALIZATION"
            ),
            "validation_policy": (
                "FULL_BUNDLE_RUNNER_INPUT_BOUND_SUBJECT_AND_FIXTURE_BYTES_"
                "BEFORE_SUT"
            ),
            "sut_entrypoint_policy": (
                "RESOLVE_ONLY_FROM_SUITE_RUNNER_CONTRACT_INPUT_BINDING"
            ),
        }
        oracle.pop("source_sha256", None)
        oracle.pop("output_schema_ref", None)
        oracle.pop("sut_output_schema_ref", None)
        oracle["source_manifest_entry_sha256"] = oracle_entry[
            "entry_sha256"
        ]
        oracle["oracle_output_schema_ref"] = SUT_DECISION_SCHEMA_ID
        oracle["input_source"] = (
            "PROPERTY_INSTANCE_ENVELOPE_READ_ONLY_COPY"
        )
        oracle["materialized_input_access"] = "FORBIDDEN"
        oracle["sut_output_artifact_access"] = "FORBIDDEN"
        suite["reference_oracle"] = oracle
        suite["instance_validation_policy"] = (
            "VALIDATE_PROPERTY_INSTANCE_ENVELOPE_AND_EXACT_DOMAIN_"
            "MEMBERSHIP_BEFORE_MATERIALIZATION"
        )
        suite["runner_fixture_source"] = (
            "PROPERTY_INSTANCE_MATERIALIZATION"
        )
        suite["expected_record_schema_ref"] = (
            PROPERTY_EXPECTED_SCHEMA_ID
        )
        suite["expected_record_assembly_policy"] = (
            "FREEZE_SUT_OUTPUT_ARTIFACT_THEN_INVOKE_ORACLE_WITH_"
            "ENVELOPE_ONLY"
        )
        suite["store_separation_policy"] = (
            "MATERIALIZATION_BUNDLE_AND_EXPECTED_RECORD_PHYSICALLY_SEPARATE"
        )
        suite["sut_mount_policy"] = (
            "ONLY_BUNDLE_SUT_MATERIALIZED_FIXTURES"
        )
        suite["isolation_mount_binding_policy"] = (
            "CURRENT_CASE_DECLARED_FIXTURES_MANIFEST_EQUALS_BUNDLE_"
            "FIXTURE_SET_HASH"
        )
        _set_self_hash(
            suite,
            "suite_sha256",
            source=f"property suite {suite_id}",
        )
        rendered_suites.append(suite)
    property_ids = {
        contract["runner_contract_id"] for contract in property_contracts
    }
    if len(property_ids) != 2:
        _fail("derived property runner IDs are not unique")
    return (
        sorted(
            property_contracts,
            key=lambda item: item["runner_contract_id"],
        ),
        sorted(rendered_suites, key=lambda item: item["suite_id"]),
    )


def _normalise_cases(
    cases: Sequence[Mapping[str, Any]],
    *,
    runner_aliases: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    _validate_identifier_baseline(
        [
            case.get("case_id")
            if isinstance(case, Mapping)
            else None
            for case in cases
        ],
        expected_count=ORDINARY_CASE_BASELINE[0],
        expected_sha256=ORDINARY_CASE_BASELINE[1],
        source="ordinary evaluation case",
    )
    rendered: list[dict[str, Any]] = []
    case_ids: set[str] = set()
    for original_case in cases:
        case = _require_object(original_case, source="evaluation case")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or case_id in case_ids:
            _fail(f"duplicate or invalid evaluation case ID: {case_id!r}")
        case_ids.add(case_id)
        contract = runner_aliases.get(str(case.get("runner_contract_id")))
        if contract is None:
            _fail(f"case runner missing: {case_id}")
        runner_id = contract["runner_contract_id"]
        case["runner_contract_id"] = runner_id
        runner_input = _require_object(
            case.get("input"),
            source=f"case {case_id} runner input",
        )
        runner_input["runner_contract_id"] = runner_id
        binding_id = runner_input.get("input_binding_id")
        if not any(
            binding["input_binding_id"] == binding_id
            for binding in contract["input_bindings"]
        ):
            _fail(f"case input binding missing: {case_id}: {binding_id}")
        subject = runner_input.get("subject")
        if (
            isinstance(subject, Mapping)
            and subject.get("schema_version")
            == "EvaluationRunnerContract.v1"
        ):
            subject_contract = runner_aliases.get(
                str(subject.get("runner_contract_id"))
            )
            if subject_contract is None:
                _fail(f"case history subject runner missing: {case_id}")
            runner_input["subject"] = copy.deepcopy(subject_contract)
        case["input"] = runner_input
        case.pop("output_schema_ref", None)
        case["sut_output_schema_ref"] = SUT_DECISION_SCHEMA_ID
        prior_expected = _require_object(
            case.get("expected"),
            source=f"case {case_id} expected decision",
        )
        expected = {
            "schema_version": "SutDecision.v1",
            "outcome": prior_expected.get("outcome"),
            "decision": prior_expected.get("decision"),
            "reason_ids": copy.deepcopy(prior_expected.get("reason_ids")),
            "assertion_ids": copy.deepcopy(
                prior_expected.get("assertion_ids")
            ),
        }
        _set_self_hash(
            expected,
            "sut_decision_sha256",
            prefixed=False,
            source=f"case {case_id} expected decision",
        )
        case["expected"] = expected
        oracle = _require_object(
            case.get("oracle"),
            source=f"case {case_id} oracle",
        )
        mode_aliases = {
            "EXACT_OUTPUT": "EXACT_SUT_DECISION",
            "EXACT_OUTPUT_AND_REFERENCE_TRACE": (
                "EXACT_SUT_DECISION_AND_REFERENCE_TRACE"
            ),
        }
        oracle["mode"] = mode_aliases.get(
            str(oracle.get("mode")),
            oracle.get("mode"),
        )
        oracle.pop("expected_output_sha256", None)
        oracle["expected_sut_decision_sha256"] = expected[
            "sut_decision_sha256"
        ]
        reference_trace_fixture_id = oracle.get(
            "reference_trace_fixture_id"
        )
        if reference_trace_fixture_id is not None:
            fixture_refs = _require_list(
                runner_input.get("fixture_refs"),
                source=f"case {case_id} fixture refs",
            )
            runner_input["fixture_refs"] = [
                fixture_id
                for fixture_id in fixture_refs
                if fixture_id != reference_trace_fixture_id
            ]
        case["oracle"] = oracle
        _set_self_hash(
            case,
            "case_sha256",
            source=f"evaluation case {case_id}",
        )
        rendered.append(case)
    return sorted(rendered, key=lambda item: item["case_id"])


def _fixture_by_id(
    fixtures: Mapping[str, Mapping[str, Any]],
    fixture_id: str,
) -> dict[str, Any]:
    fixture = fixtures.get(fixture_id)
    if fixture is None:
        _fail(f"fixture missing: {fixture_id}")
    return copy.deepcopy(dict(fixture))


def _fixture_json(
    fixture: Mapping[str, Any],
    fixture_blobs: Mapping[str, bytes],
) -> dict[str, Any]:
    repository_path = fixture.get("repository_path")
    raw = fixture_blobs.get(str(repository_path))
    if raw is None:
        _fail(f"fixture bytes missing: {repository_path}")
    value = _parse_strict_json(
        raw,
        source=f"fixture {fixture.get('fixture_id')}",
    )
    return _require_object(
        value,
        source=f"fixture {fixture.get('fixture_id')}",
    )


def _finalize_isolation_binding(
    binding: Mapping[str, Any],
) -> dict[str, Any]:
    result = copy.deepcopy(dict(binding))
    _set_self_hash(
        result,
        "binding_id",
        source="conformance isolation binding",
    )
    return result


def _unverified_isolation_binding(
    *,
    runner_contract_id: str,
    isolation_policy_sha256: str,
    failure_reasons: Sequence[str],
) -> dict[str, Any]:
    return _finalize_isolation_binding(
        {
            "schema_version": "EvaluationIsolationBinding.v1",
            "binding_id": "",
            "evaluation_execution_id": CONFORMANCE_EXECUTION_ID,
            "runner_contract_id": runner_contract_id,
            "isolation_policy_sha256": isolation_policy_sha256,
            "state": "UNVERIFIED_ISOLATION",
            "execution_authorized": False,
            "backend": None,
            "certification": None,
            "mounts": [],
            "deny_evidence": [],
            "network_evidence": None,
            "failure_reasons": list(failure_reasons),
            "checked_at_utc": "2026-07-27T12:00:00Z",
        }
    )


def _verified_isolation_attempt(
    *,
    runner_contract_id: str,
    isolation_policy_sha256: str,
    fixtures: Mapping[str, Mapping[str, Any]],
    fixture_blobs: Mapping[str, bytes],
) -> dict[str, Any]:
    certificate_fixture = _fixture_by_id(
        fixtures,
        ISOLATION_FIXTURE_IDS["certificate"],
    )
    certificate = _fixture_json(certificate_fixture, fixture_blobs)
    signed = certificate["signed_payload"]["preimage"]
    mount_paths = [
        (
            r"C:\aegis-runtime\isolated-venv",
            r"C:\sandbox\venv",
        ),
        (
            r"C:\aegis-runtime\runs\run-101\fixtures",
            r"C:\sandbox\fixtures",
        ),
        (
            r"C:\aegis-runtime\runs\run-101\outbox",
            r"C:\sandbox\outbox",
        ),
    ]
    mounts = []
    for mount, paths in zip(
        signed["mounts"],
        mount_paths,
        strict=True,
    ):
        mounts.append(
            {
                "resource": mount["resource"],
                "host_realpath": paths[0],
                "sandbox_path": paths[1],
                "access": mount["access"],
                "content_manifest_sha256": mount[
                    "content_manifest_sha256"
                ],
            }
        )
    deny_evidence = []
    for resource, fixture_id in ISOLATION_FIXTURE_IDS["deny"].items():
        fixture = _fixture_by_id(fixtures, fixture_id)
        record = _fixture_json(fixture, fixture_blobs)
        deny_evidence.append(
            {
                "resource": resource,
                "probe_operation": record["probe_operation"],
                "target_identity_sha256": record[
                    "target_identity_sha256"
                ],
                "blocked": record["blocked"],
                "observed_error_code": record["observed_error_code"],
                "evidence_raw_sha256": fixture["raw_sha256"],
            }
        )
    network_fixture = _fixture_by_id(
        fixtures,
        ISOLATION_FIXTURE_IDS["network"],
    )
    network_record = _fixture_json(network_fixture, fixture_blobs)
    backend_id = "SYNTHETIC-OFFLINE-ISOLATION-BACKEND-V1"
    return _finalize_isolation_binding(
        {
            "schema_version": "EvaluationIsolationBinding.v1",
            "binding_id": "",
            "evaluation_execution_id": CONFORMANCE_EXECUTION_ID,
            "runner_contract_id": runner_contract_id,
            "isolation_policy_sha256": isolation_policy_sha256,
            "state": "VERIFIED_RELEASE_GRADE",
            "execution_authorized": True,
            "backend": {
                "backend_id": backend_id,
                "backend_version": signed["backend_version"],
                "enforcement_kind": "OS_SANDBOX",
                "binary_realpath": (
                    r"C:\aegis-runtime\isolation"
                    r"\synthetic-offline-backend.exe"
                ),
                "binary_byte_size": certificate["backend_binary"][
                    "raw_byte_size"
                ],
                "binary_raw_sha256": certificate["backend_binary"][
                    "raw_sha256"
                ],
                "default_filesystem_access": "DENIED",
                "network_enforcement": "DENIED_AT_BACKEND",
                "same_user_bypass_resistance": "CERTIFIED",
            },
            "certification": {
                "certification_id": (
                    f"sha256:{certificate_fixture['raw_sha256']}"
                ),
                "issuer_id": "SYNTHETIC-OFFLINE-FIXTURE-ISSUER-V1",
                "trust_root_id": (
                    "sha256:"
                    + certificate["trust_root_public_key"]["raw_sha256"]
                ),
                "backend_id": backend_id,
                "backend_version": signed["backend_version"],
                "isolation_policy_sha256": isolation_policy_sha256,
                "platform_descriptor_id": signed[
                    "platform_descriptor_id"
                ],
                "validation_suite_sha256": signed[
                    "validation_suite_sha256"
                ],
                "valid_from_utc": signed["valid_from_utc"],
                "valid_until_utc": signed["valid_until_utc"],
                "certificate_path": certificate_fixture[
                    "logical_runtime_paths"
                ][0],
                "certificate_byte_size": certificate_fixture["byte_size"],
                "certificate_raw_sha256": certificate_fixture[
                    "raw_sha256"
                ],
                "signed_payload_jcs_sha256": certificate[
                    "signed_payload"
                ]["jcs_sha256"],
                "signature_algorithm": "ED25519",
                "signature_base64": certificate["certificate"][
                    "signature_base64"
                ],
                "trust_result": (
                    "VALID_TRUSTED_UNEXPIRED_EXACT_PLATFORM"
                ),
            },
            "mounts": mounts,
            "deny_evidence": deny_evidence,
            "network_evidence": {
                "probe_set_id": (
                    "SYNTHETIC-OFFLINE-NETWORK-DENIAL-PROBE-V1"
                ),
                "address_families": network_record["address_families"],
                "operations": network_record["operations"],
                "all_blocked": network_record["all_blocked"],
                "evidence_raw_sha256": network_fixture["raw_sha256"],
            },
            "failure_reasons": [],
            "checked_at_utc": "2026-07-27T12:00:00Z",
        }
    )


def _mutation(
    operation: str,
    target_pointer: str,
    value: Any,
) -> dict[str, Any]:
    return {
        "operation": operation,
        "target_pointer": target_pointer,
        "value_or_sequence": copy.deepcopy(value),
    }


def _conformance_scenario(
    case_id: str,
    title: str,
) -> dict[str, Any]:
    return {
        "trigger": {
            "mechanism": f"{case_id}: {title}",
            "observable_preconditions": [
                (
                    "The outer evaluator resolves every referenced "
                    "authority preimage before process creation."
                ),
                (
                    "A blocked runner state is ineligible for comparison "
                    "or PASS credit."
                ),
            ],
        },
        "runtime_boundary": (
            "Aegis v2 frozen outer-runner trust gate before SUT process "
            "creation."
        ),
        "probability_or_exposure": {
            "basis_kind": "DIRECT_CONTRACT_PATH",
            "statement": (
                "The candidate reaches a mandatory fail-closed runner "
                "boundary before SUT spawn."
            ),
            "evidence_refs": [
                "CONTRACT-SECTION-14.2",
                "CONTRACT-SECTION-16.1",
            ],
        },
        "impact": {
            "domains": [
                "AUTHORITY",
                "INTEGRITY",
                "RELEASE_DECISION",
                "SAFETY",
            ],
            "consequence": (
                "Failure to block permits unisolated code execution or "
                "false PASS credit."
            ),
        },
        "inclusion_rationale": (
            "Included because the runner trust gate must reject this exact "
            "pre-spawn condition without consulting SUT output."
        ),
        "risk_register_entry_id": None,
    }


def _make_conformance_case(
    specification: Mapping[str, Any],
    *,
    runner_contract_id: str,
    fixtures: Mapping[str, Mapping[str, Any]],
    forbidden_result_members: Sequence[str],
) -> dict[str, Any]:
    case_id = specification["case_id"]
    fixture_refs = sorted(specification.get("fixture_refs", []))
    candidate = copy.deepcopy(specification["candidate"])
    candidate_sha256 = _value_sha256(
        candidate,
        source=f"conformance candidate {case_id}",
    )
    evidence_ids = sorted(
        {
            f"sha256:{candidate_sha256}",
            *(
                f"sha256:{_fixture_by_id(fixtures, fixture_id)['raw_sha256']}"
                for fixture_id in fixture_refs
            ),
        }
    )
    input_variant = {
        "schema_version": "RunnerConformanceInputVariant.v1",
        "variant_kind": specification["variant_kind"],
        "target_schema_ref": specification["target_schema_ref"],
        "fixture_refs": fixture_refs,
        "mutation": copy.deepcopy(specification.get("mutation")),
        "candidate": candidate,
        "candidate_sha256": candidate_sha256,
    }
    invocation = {
        "schema_version": "RunnerConformanceInvocation.v1",
        "case_id": case_id,
        "runner_contract_id": runner_contract_id,
        "input_binding_id": CONFORMANCE_INPUT_BINDING_ID,
        "input_variant": input_variant,
    }
    _set_self_hash(
        invocation,
        "invocation_jcs_sha256",
        prefixed=False,
        source=f"conformance invocation {case_id}",
    )
    expected_runner_state = specification["expected_runner_state"]
    result = {
        "case_id": case_id,
        "title": specification["title"],
        "category": "EVALUATOR-ISOLATION-CONFORMANCE",
        "defect_class": specification["defect_class"],
        "severity": "P0",
        "must_detect": True,
        "denominator_group_ids": ["DENOM-EVALUATOR-ISOLATION"],
        "source_contract_refs": [
            "CONTRACT-SECTION-14.2",
            "CONTRACT-SECTION-16.1",
        ],
        "scenario_basis": _conformance_scenario(
            case_id,
            specification["title"],
        ),
        "invocation": invocation,
        "expected": {
            "schema_version": "RunnerConformanceExpected.v1",
            "result_schema_ref": RUNNER_CONFORMANCE_RESULT_SCHEMA_ID,
            "result_validation_policy": (
                "VALIDATE_FULL_RESULT_SCHEMA_AND_SELF_HASH_BEFORE_"
                "EXPECTED_TEMPLATE"
            ),
            "expected_runner_state": expected_runner_state,
            "required_isolation_binding_state": (
                "UNVERIFIED_ISOLATION"
                if expected_runner_state == "BLOCKED_UNVERIFIED_ISOLATION"
                else "NOT_APPLICABLE"
            ),
            "pre_spawn_expectation": {
                "spawn_attempted": False,
                "comparison_performed": False,
                "pass_eligible": False,
                "output_artifact_raw_sha256": None,
            },
            "expected_reason_ids": list(specification["reason_ids"]),
            "reason_match_policy": "EXACT_ARRAY_ORDER",
            "required_evidence_ids": evidence_ids,
            "evidence_match_policy": (
                "REQUIRED_SUBSET_ALLOW_RUNTIME_ADDITIONS"
            ),
            "forbidden_result_members": list(
                forbidden_result_members
            ),
            "assertion_ids": [
                specification["assertion_id"],
                "ASSERT-BLOCKED-STATE-CANNOT-PASS",
                "ASSERT-SUT-NOT-SPAWNED",
            ],
        },
    }
    _set_self_hash(
        result,
        "case_sha256",
        source=f"runner conformance case {case_id}",
    )
    return result


def _build_conformance_cases(
    *,
    static_contracts: Sequence[Mapping[str, Any]],
    runner_schema: Mapping[str, Any],
    evaluation_schema: Mapping[str, Any],
    fixtures: Mapping[str, Mapping[str, Any]],
    fixture_blobs: Mapping[str, bytes],
) -> list[dict[str, Any]]:
    conformance_contract, _ = _resolve_static_binding(
        static_contracts,
        CONFORMANCE_INPUT_BINDING_ID,
    )
    runner_contract_id = conformance_contract["runner_contract_id"]
    isolation_policy = _frozen_object(
        _schema_definition(runner_schema, "isolationPolicy"),
        schema=runner_schema,
        source="isolationPolicy",
    )
    isolation_policy_sha256 = _value_sha256(
        isolation_policy,
        source="runner isolation policy",
    )
    certificate_fixture = _fixture_by_id(
        fixtures,
        ISOLATION_FIXTURE_IDS["certificate"],
    )
    certificate = _fixture_json(certificate_fixture, fixture_blobs)
    if (
        certificate.get("isolation_policy", {}).get("jcs_sha256")
        != isolation_policy_sha256
    ):
        _fail("certificate fixture isolation policy drift")
    baseline = _verified_isolation_attempt(
        runner_contract_id=runner_contract_id,
        isolation_policy_sha256=isolation_policy_sha256,
        fixtures=fixtures,
        fixture_blobs=fixture_blobs,
    )
    all_isolation_fixtures = sorted(
        [
            ISOLATION_FIXTURE_IDS["certificate"],
            *ISOLATION_FIXTURE_IDS["deny"].values(),
            ISOLATION_FIXTURE_IDS["network"],
        ]
    )
    expected_definition = _schema_definition(
        evaluation_schema,
        "runnerConformanceExpected",
    )
    forbidden_result_members = expected_definition["properties"][
        "forbidden_result_members"
    ]["const"]
    specifications: list[dict[str, Any]] = []

    no_backend = _unverified_isolation_binding(
        runner_contract_id=runner_contract_id,
        isolation_policy_sha256=isolation_policy_sha256,
        failure_reasons=["NO_CERTIFIED_BACKEND"],
    )
    specifications.append(
        {
            "case_id": "EV-RUNNER-ISOLATION-NO-CERTIFIED-BACKEND",
            "title": (
                "Missing certified isolation backend blocks before SUT spawn"
            ),
            "defect_class": "DEFECT-UNCERTIFIED-ISOLATION-BACKEND",
            "variant_kind": "ISOLATION_BINDING",
            "target_schema_ref": ISOLATION_BINDING_SCHEMA_ID,
            "candidate": no_backend,
            "expected_runner_state": "BLOCKED_UNVERIFIED_ISOLATION",
            "reason_ids": ["REASON-NO-CERTIFIED-ISOLATION-BACKEND"],
            "assertion_id": "ASSERT-UNCERTIFIED-BACKEND-BLOCKS",
        }
    )
    unauthorized = copy.deepcopy(no_backend)
    unauthorized["execution_authorized"] = True
    _set_self_hash(
        unauthorized,
        "binding_id",
        source="unauthorized unverified isolation binding",
    )
    specifications.append(
        {
            "case_id": "EV-RUNNER-ISOLATION-UNVERIFIED-AUTHORIZED",
            "title": "UNVERIFIED isolation cannot authorize process execution",
            "defect_class": "DEFECT-UNVERIFIED-EXECUTION-AUTHORIZED",
            "variant_kind": "ISOLATION_BINDING",
            "target_schema_ref": ISOLATION_BINDING_SCHEMA_ID,
            "mutation": _mutation(
                "REPLACE",
                "/execution_authorized",
                True,
            ),
            "candidate": unauthorized,
            "expected_runner_state": "BLOCKED_INVALID_RUNNER_INPUT",
            "reason_ids": [
                "REASON-UNVERIFIED-ISOLATION-AUTHORIZATION-INVALID"
            ],
            "assertion_id": (
                "ASSERT-UNVERIFIED-BINDING-NEVER-AUTHORIZES"
            ),
        }
    )

    invalid_certificate = copy.deepcopy(baseline)
    signature = invalid_certificate["certification"]["signature_base64"]
    invalid_certificate["certification"]["signature_base64"] = (
        f"B{signature[1:]}"
    )
    _set_self_hash(
        invalid_certificate,
        "binding_id",
        source="invalid certificate isolation binding",
    )
    specifications.append(
        {
            "case_id": "EV-RUNNER-ISOLATION-CERTIFICATION-INVALID",
            "title": (
                "Invalid isolation certification signature blocks execution"
            ),
            "defect_class": "DEFECT-ISOLATION-CERTIFICATION-INVALID",
            "variant_kind": "CERTIFICATION_EVIDENCE",
            "target_schema_ref": ISOLATION_BINDING_SCHEMA_ID,
            "fixture_refs": [ISOLATION_FIXTURE_IDS["certificate"]],
            "mutation": _mutation(
                "REPLACE",
                "/certification/signature_base64",
                invalid_certificate["certification"]["signature_base64"],
            ),
            "candidate": invalid_certificate,
            "expected_runner_state": "BLOCKED_UNVERIFIED_ISOLATION",
            "reason_ids": ["REASON-ISOLATION-CERTIFICATION-INVALID"],
            "assertion_id": "ASSERT-CERTIFICATION-SIGNATURE-VERIFIED",
        }
    )
    expired = copy.deepcopy(baseline)
    expired["certification"]["valid_until_utc"] = (
        "2026-07-26T23:59:59Z"
    )
    _set_self_hash(
        expired,
        "binding_id",
        source="expired certificate isolation binding",
    )
    specifications.append(
        {
            "case_id": "EV-RUNNER-ISOLATION-CERTIFICATION-EXPIRED",
            "title": "Expired isolation certification blocks execution",
            "defect_class": "DEFECT-ISOLATION-CERTIFICATION-EXPIRED",
            "variant_kind": "CERTIFICATION_EVIDENCE",
            "target_schema_ref": ISOLATION_BINDING_SCHEMA_ID,
            "fixture_refs": [ISOLATION_FIXTURE_IDS["certificate"]],
            "mutation": _mutation(
                "REPLACE",
                "/certification/valid_until_utc",
                "2026-07-26T23:59:59Z",
            ),
            "candidate": expired,
            "expected_runner_state": "BLOCKED_UNVERIFIED_ISOLATION",
            "reason_ids": ["REASON-ISOLATION-CERTIFICATION-EXPIRED"],
            "assertion_id": (
                "ASSERT-CERTIFICATION-VALIDITY-WINDOW-ENFORCED"
            ),
        }
    )
    mismatched = copy.deepcopy(baseline)
    mismatched["certification"]["backend_id"] = (
        "SYNTHETIC-OFFLINE-DIFFERENT-BACKEND-V1"
    )
    _set_self_hash(
        mismatched,
        "binding_id",
        source="mismatched certificate isolation binding",
    )
    specifications.append(
        {
            "case_id": (
                "EV-RUNNER-ISOLATION-CERTIFICATION-BACKEND-MISMATCH"
            ),
            "title": (
                "Certification bound to a different backend blocks execution"
            ),
            "defect_class": (
                "DEFECT-ISOLATION-CERTIFICATION-BACKEND-MISMATCH"
            ),
            "variant_kind": "CERTIFICATION_EVIDENCE",
            "target_schema_ref": ISOLATION_BINDING_SCHEMA_ID,
            "fixture_refs": [ISOLATION_FIXTURE_IDS["certificate"]],
            "mutation": _mutation(
                "REPLACE",
                "/certification/backend_id",
                "SYNTHETIC-OFFLINE-DIFFERENT-BACKEND-V1",
            ),
            "candidate": mismatched,
            "expected_runner_state": "BLOCKED_UNVERIFIED_ISOLATION",
            "reason_ids": [
                "REASON-ISOLATION-BACKEND-IDENTITY-MISMATCH"
            ],
            "assertion_id": (
                "ASSERT-CERTIFICATION-BACKEND-BINDING-EXACT"
            ),
        }
    )

    for index, resource in enumerate(ISOLATION_FIXTURE_IDS["deny"]):
        token = resource.replace("_", "-")
        missing = copy.deepcopy(baseline)
        missing["deny_evidence"].pop(index)
        _set_self_hash(
            missing,
            "binding_id",
            source=f"missing deny evidence {resource}",
        )
        specifications.append(
            {
                "case_id": (
                    f"EV-RUNNER-ISOLATION-DENY-{token}-MISSING"
                ),
                "title": f"{resource} read-denial probe is mandatory",
                "defect_class": (
                    "DEFECT-FILESYSTEM-DENIAL-EVIDENCE-MISSING"
                ),
                "variant_kind": "ISOLATION_BINDING",
                "target_schema_ref": ISOLATION_BINDING_SCHEMA_ID,
                "fixture_refs": all_isolation_fixtures,
                "mutation": _mutation(
                    "REMOVE",
                    f"/deny_evidence/{index}",
                    None,
                ),
                "candidate": missing,
                "expected_runner_state": (
                    "BLOCKED_UNVERIFIED_ISOLATION"
                ),
                "reason_ids": [
                    "REASON-CERTIFICATION-SYNTHETIC-NOT-AUTHORIZED",
                    "REASON-FILESYSTEM-DENIAL-NOT-PROVEN",
                ],
                "assertion_id": (
                    f"ASSERT-DENY-PROBE-{token}-REQUIRED"
                ),
            }
        )
        false_probe = copy.deepcopy(baseline)
        false_probe["deny_evidence"][index]["blocked"] = False
        _set_self_hash(
            false_probe,
            "binding_id",
            source=f"false deny evidence {resource}",
        )
        specifications.append(
            {
                "case_id": f"EV-RUNNER-ISOLATION-DENY-{token}-FALSE",
                "title": (
                    f"{resource} read-denial probe must report blocked=true"
                ),
                "defect_class": (
                    "DEFECT-FILESYSTEM-DENIAL-EVIDENCE-FALSE"
                ),
                "variant_kind": "ISOLATION_BINDING",
                "target_schema_ref": ISOLATION_BINDING_SCHEMA_ID,
                "fixture_refs": all_isolation_fixtures,
                "mutation": _mutation(
                    "REPLACE",
                    f"/deny_evidence/{index}/blocked",
                    False,
                ),
                "candidate": false_probe,
                "expected_runner_state": (
                    "BLOCKED_UNVERIFIED_ISOLATION"
                ),
                "reason_ids": [
                    "REASON-CERTIFICATION-SYNTHETIC-NOT-AUTHORIZED",
                    "REASON-FILESYSTEM-DENIAL-NOT-PROVEN",
                ],
                "assertion_id": (
                    f"ASSERT-DENY-PROBE-{token}-BLOCKED"
                ),
            }
        )

    expanded_mount = copy.deepcopy(baseline)
    expanded_mount["mounts"][1]["access"] = "READ_EXECUTE"
    _set_self_hash(
        expanded_mount,
        "binding_id",
        source="expanded isolation mount",
    )
    specifications.append(
        {
            "case_id": (
                "EV-RUNNER-ISOLATION-MOUNT-PERMISSION-EXPANDED"
            ),
            "title": "Expanded fixture mount permission blocks execution",
            "defect_class": (
                "DEFECT-ISOLATION-MOUNT-PERMISSION-EXPANDED"
            ),
            "variant_kind": "ISOLATION_BINDING",
            "target_schema_ref": ISOLATION_BINDING_SCHEMA_ID,
            "fixture_refs": all_isolation_fixtures,
            "mutation": _mutation(
                "REPLACE",
                "/mounts/1/access",
                "READ_EXECUTE",
            ),
            "candidate": expanded_mount,
            "expected_runner_state": "BLOCKED_UNVERIFIED_ISOLATION",
            "reason_ids": [
                "REASON-CERTIFICATION-SYNTHETIC-NOT-AUTHORIZED",
                "REASON-ISOLATION-MOUNT-POLICY-MISMATCH",
            ],
            "assertion_id": "ASSERT-MOUNT-PERMISSIONS-EXACT",
        }
    )
    extra_mount = copy.deepcopy(baseline)
    extra_mount["mounts"].append(
        {
            "resource": "REPOSITORY_ROOT",
            "host_realpath": r"C:\code\aegis-20260727",
            "sandbox_path": r"C:\sandbox\repository",
            "access": "READ_ONLY",
            "content_manifest_sha256": "f" * 64,
        }
    )
    _set_self_hash(
        extra_mount,
        "binding_id",
        source="extra isolation mount",
    )
    specifications.append(
        {
            "case_id": "EV-RUNNER-ISOLATION-EXTRA-MOUNT",
            "title": "Undeclared fourth mount blocks execution",
            "defect_class": "DEFECT-ISOLATION-EXTRA-MOUNT",
            "variant_kind": "ISOLATION_BINDING",
            "target_schema_ref": ISOLATION_BINDING_SCHEMA_ID,
            "fixture_refs": all_isolation_fixtures,
            "mutation": _mutation(
                "INSERT",
                "/mounts/3",
                extra_mount["mounts"][3],
            ),
            "candidate": extra_mount,
            "expected_runner_state": "BLOCKED_UNVERIFIED_ISOLATION",
            "reason_ids": [
                "REASON-CERTIFICATION-SYNTHETIC-NOT-AUTHORIZED",
                "REASON-ISOLATION-MOUNT-POLICY-MISMATCH",
            ],
            "assertion_id": "ASSERT-MOUNT-ALLOWLIST-EXACT",
        }
    )
    missing_network = copy.deepcopy(baseline)
    missing_network["network_evidence"] = None
    _set_self_hash(
        missing_network,
        "binding_id",
        source="missing network evidence",
    )
    specifications.append(
        {
            "case_id": (
                "EV-RUNNER-ISOLATION-NETWORK-EVIDENCE-MISSING"
            ),
            "title": "Missing network-denial evidence blocks execution",
            "defect_class": (
                "DEFECT-NETWORK-DENIAL-EVIDENCE-MISSING"
            ),
            "variant_kind": "ISOLATION_BINDING",
            "target_schema_ref": ISOLATION_BINDING_SCHEMA_ID,
            "fixture_refs": all_isolation_fixtures,
            "mutation": _mutation(
                "REPLACE",
                "/network_evidence",
                None,
            ),
            "candidate": missing_network,
            "expected_runner_state": "BLOCKED_UNVERIFIED_ISOLATION",
            "reason_ids": [
                "REASON-CERTIFICATION-SYNTHETIC-NOT-AUTHORIZED",
                "REASON-NETWORK-DENIAL-NOT-PROVEN",
            ],
            "assertion_id": (
                "ASSERT-NETWORK-DENIAL-EVIDENCE-REQUIRED"
            ),
        }
    )
    false_network = copy.deepcopy(baseline)
    false_network["network_evidence"]["all_blocked"] = False
    _set_self_hash(
        false_network,
        "binding_id",
        source="false network evidence",
    )
    specifications.append(
        {
            "case_id": "EV-RUNNER-ISOLATION-NETWORK-EVIDENCE-FALSE",
            "title": (
                "Network probe with all_blocked=false blocks execution"
            ),
            "defect_class": "DEFECT-NETWORK-DENIAL-EVIDENCE-FALSE",
            "variant_kind": "ISOLATION_BINDING",
            "target_schema_ref": ISOLATION_BINDING_SCHEMA_ID,
            "fixture_refs": all_isolation_fixtures,
            "mutation": _mutation(
                "REPLACE",
                "/network_evidence/all_blocked",
                False,
            ),
            "candidate": false_network,
            "expected_runner_state": "BLOCKED_UNVERIFIED_ISOLATION",
            "reason_ids": [
                "REASON-CERTIFICATION-SYNTHETIC-NOT-AUTHORIZED",
                "REASON-NETWORK-DENIAL-NOT-PROVEN",
            ],
            "assertion_id": "ASSERT-NETWORK-PROBES-ALL-BLOCKED",
        }
    )

    legacy_contracts = [
        {
            "case_id": "EV-RUNNER-CONTRACT-HOST-ENV-INHERITANCE",
            "title": "Host environment inheritance is forbidden",
            "defect_class": "DEFECT-RUNNER-HOST-ENVIRONMENT-INHERITED",
            "pointer": "/input_bindings/0/sut/environment_inheritance",
            "value": "HOST",
            "reason": "REASON-RUNNER-HOST-ENVIRONMENT-FORBIDDEN",
            "assertion": "ASSERT-ENVIRONMENT-INHERITANCE-NONE",
        },
        {
            "case_id": "EV-RUNNER-CONTRACT-PYTHONPATH-FORBIDDEN",
            "title": "PYTHONPATH injection in the SUT environment is forbidden",
            "defect_class": "DEFECT-RUNNER-PYTHONPATH-INJECTION",
            "pointer": "/input_bindings/0/sut/environment/2",
            "value": {"name": "PYTHONPATH", "value": "src"},
            "operation": "INSERT",
            "reason": "REASON-RUNNER-PYTHONPATH-FORBIDDEN",
            "assertion": "ASSERT-SUT-ENVIRONMENT-EXACT",
        },
        {
            "case_id": (
                "EV-RUNNER-CONTRACT-REPOSITORY-WORKING-DIRECTORY"
            ),
            "title": "Repository-root SUT working directory is forbidden",
            "defect_class": (
                "DEFECT-RUNNER-REPOSITORY-WORKING-DIRECTORY"
            ),
            "pointer": "/input_bindings/0/sut/working_directory",
            "value": "REPOSITORY_ROOT",
            "reason": (
                "REASON-RUNNER-REPOSITORY-WORKING-DIRECTORY-FORBIDDEN"
            ),
            "assertion": "ASSERT-ISOLATED-WORKING-DIRECTORY",
        },
        {
            "case_id": "EV-RUNNER-CONTRACT-LEGACY-FOUR-ARG-ARGV",
            "title": (
                "Legacy four-argument SUT argv without isolated mode is "
                "forbidden"
            ),
            "defect_class": "DEFECT-RUNNER-LEGACY-ARGV",
            "pointer": "/input_bindings/0/sut/argv_template",
            "value": [
                "{PYTHON_EXECUTABLE}",
                "-m",
                "aegis.sut",
                "{ENTRYPOINT_ID}",
            ],
            "reason": "REASON-RUNNER-LEGACY-ARGV-FORBIDDEN",
            "assertion": "ASSERT-SUT-ARGV-ISOLATED-SEVEN-MEMBERS",
        },
    ]
    for legacy in legacy_contracts:
        candidate = copy.deepcopy(conformance_contract)
        sut = candidate["input_bindings"][0]["sut"]
        if legacy["case_id"].endswith("HOST-ENV-INHERITANCE"):
            sut["environment_inheritance"] = legacy["value"]
        elif legacy["case_id"].endswith("PYTHONPATH-FORBIDDEN"):
            sut["environment"].append(legacy["value"])
        elif legacy["case_id"].endswith(
            "REPOSITORY-WORKING-DIRECTORY"
        ):
            sut["working_directory"] = legacy["value"]
        else:
            sut["argv_template"] = legacy["value"]
        specifications.append(
            {
                "case_id": legacy["case_id"],
                "title": legacy["title"],
                "defect_class": legacy["defect_class"],
                "variant_kind": "RUNNER_CONTRACT",
                "target_schema_ref": RUNNER_CONTRACT_SCHEMA_ID,
                "mutation": _mutation(
                    legacy.get("operation", "REPLACE"),
                    legacy["pointer"],
                    legacy["value"],
                ),
                "candidate": candidate,
                "expected_runner_state": (
                    "BLOCKED_INVALID_RUNNER_CONTRACT"
                ),
                "reason_ids": [legacy["reason"]],
                "assertion_id": legacy["assertion"],
            }
        )

    specifications.extend(
        [
            {
                "case_id": (
                    "EV-RUNNER-PYTHON-REPOSITORY-IMPORT-ORIGIN"
                ),
                "title": (
                    "Production aegis module resolved from repository "
                    "source blocks spawn"
                ),
                "defect_class": (
                    "DEFECT-RUNNER-REPOSITORY-IMPORT-ORIGIN"
                ),
                "variant_kind": "PYTHON_IMPORT_ORIGIN",
                "target_schema_ref": PYTHON_BINDING_SCHEMA_ID,
                "candidate": {
                    "schema_version": "PythonImportOriginObservation.v1",
                    "module_name": "aegis.sut",
                    "resolved_origin": (
                        r"C:\code\aegis-20260727\src"
                        r"\aegis\sut\__init__.py"
                    ),
                    "repository_origin": True,
                    "isolated_environment_origin": False,
                },
                "expected_runner_state": (
                    "BLOCKED_INVALID_PYTHON_BINDING"
                ),
                "reason_ids": [
                    "REASON-PRODUCTION-MODULE-ORIGIN-NOT-ISOLATED"
                ],
                "assertion_id": (
                    "ASSERT-PRODUCTION-IMPORT-ORIGIN-OUTSIDE-REPOSITORY"
                ),
            },
            {
                "case_id": "EV-RUNNER-UNSUPPORTED-PLATFORM",
                "title": (
                    "Non-Windows platform profile blocks before "
                    "environment creation"
                ),
                "defect_class": "DEFECT-RUNNER-UNSUPPORTED-PLATFORM",
                "variant_kind": "PYTHON_IMPORT_ORIGIN",
                "target_schema_ref": PYTHON_BINDING_SCHEMA_ID,
                "candidate": {
                    "schema_version": "PlatformProfileObservation.v1",
                    "operating_system": "Linux",
                    "sys_platform": "linux",
                    "machine": "x86_64",
                    "python_implementation": "CPython",
                    "python_major_minor": "3.13",
                    "wheel_platform_tag": "manylinux_2_28_x86_64",
                },
                "expected_runner_state": "BLOCKED_UNSUPPORTED_PLATFORM",
                "reason_ids": [
                    "REASON-UNSUPPORTED-RUNNER-PLATFORM"
                ],
                "assertion_id": "ASSERT-SUPPORTED-PLATFORM-EXACT",
            },
            {
                "case_id": (
                    "EV-RUNNER-ISOLATION-SELF-REPORTED-BOOLEAN"
                ),
                "title": (
                    "Self-reported isolation boolean cannot replace "
                    "binding evidence"
                ),
                "defect_class": "DEFECT-ISOLATION-SELF-REPORT",
                "variant_kind": "SELF_REPORT",
                "target_schema_ref": ISOLATION_BINDING_SCHEMA_ID,
                "candidate": {"isolation_verified": True},
                "expected_runner_state": "BLOCKED_INVALID_RUNNER_INPUT",
                "reason_ids": [
                    "REASON-ISOLATION-SELF-REPORT-NOT-EVIDENCE"
                ],
                "assertion_id": (
                    "ASSERT-FULL-ISOLATION-BINDING-REQUIRED"
                ),
            },
        ]
    )

    blocked_output = {
        "schema_version": "EvaluationRunnerOutput.v1",
        "evaluation_execution_id": CONFORMANCE_EXECUTION_ID,
        "runner_contract_id": runner_contract_id,
        "case_id": "EV-RUNNER-OUTPUT-CONFORMANCE-CANDIDATE",
        "input_binding_id": CONFORMANCE_INPUT_BINDING_ID,
        "runner_input_jcs_sha256": "0" * 64,
        "runner_state": "BLOCKED_UNVERIFIED_ISOLATION",
        "isolation_binding": no_backend,
        "pre_spawn_block": {
            "spawn_attempted": False,
            "comparison_performed": False,
            "pass_eligible": False,
            "reason_ids": [
                "REASON-NO-CERTIFIED-ISOLATION-BACKEND"
            ],
            "evidence_ids": [f"sha256:{'1' * 64}"],
        },
        "runner_output_sha256": "2" * 64,
    }
    blocked_with_decision = copy.deepcopy(blocked_output)
    blocked_with_decision["sut_decision"] = {
        "schema_version": "SutDecision.v1",
        "outcome": "ACCEPT",
        "decision": None,
        "reason_ids": ["REASON-FORBIDDEN-BLOCKED-DECISION"],
        "assertion_ids": ["ASSERT-FORBIDDEN-BLOCKED-DECISION"],
        "sut_decision_sha256": "3" * 64,
    }
    blocked_with_record = copy.deepcopy(blocked_output)
    blocked_with_record["execution_record"] = {
        "schema_version": "ForbiddenSyntheticExecutionRecord.v1"
    }
    ready_without_isolation = {
        "schema_version": "EvaluationRunnerOutput.v1",
        "evaluation_execution_id": CONFORMANCE_EXECUTION_ID,
        "runner_contract_id": runner_contract_id,
        "case_id": "EV-RUNNER-OUTPUT-CONFORMANCE-CANDIDATE",
        "input_binding_id": CONFORMANCE_INPUT_BINDING_ID,
        "runner_input_jcs_sha256": "0" * 64,
        "runner_state": "SUT_DECISION_READY",
        "execution_record": {"isolation_binding": no_backend},
        "runner_output_sha256": "4" * 64,
    }
    specifications.extend(
        [
            {
                "case_id": (
                    "EV-RUNNER-OUTPUT-BLOCKED-CONTAINS-SUT-DECISION"
                ),
                "title": "Blocked runner output cannot contain a SutDecision",
                "defect_class": (
                    "DEFECT-BLOCKED-OUTPUT-CONTAINS-DECISION"
                ),
                "variant_kind": "RUNNER_OUTPUT",
                "target_schema_ref": RUNNER_OUTPUT_SCHEMA_ID,
                "mutation": _mutation(
                    "INSERT",
                    "/sut_decision",
                    blocked_with_decision["sut_decision"],
                ),
                "candidate": blocked_with_decision,
                "expected_runner_state": (
                    "BLOCKED_INVALID_RUNNER_INPUT"
                ),
                "reason_ids": [
                    "REASON-BLOCKED-OUTPUT-CONTAINS-SUT-DECISION"
                ],
                "assertion_id": (
                    "ASSERT-BLOCKED-OUTPUT-HAS-NO-DECISION"
                ),
            },
            {
                "case_id": (
                    "EV-RUNNER-OUTPUT-BLOCKED-CONTAINS-EXECUTION-RECORD"
                ),
                "title": (
                    "Blocked runner output cannot contain an execution record"
                ),
                "defect_class": (
                    "DEFECT-BLOCKED-OUTPUT-CONTAINS-EXECUTION-RECORD"
                ),
                "variant_kind": "RUNNER_OUTPUT",
                "target_schema_ref": RUNNER_OUTPUT_SCHEMA_ID,
                "mutation": _mutation(
                    "INSERT",
                    "/execution_record",
                    blocked_with_record["execution_record"],
                ),
                "candidate": blocked_with_record,
                "expected_runner_state": (
                    "BLOCKED_INVALID_RUNNER_INPUT"
                ),
                "reason_ids": [
                    "REASON-BLOCKED-OUTPUT-CONTAINS-EXECUTION-RECORD"
                ],
                "assertion_id": (
                    "ASSERT-BLOCKED-OUTPUT-HAS-NO-PROCESS-RECORD"
                ),
            },
            {
                "case_id": (
                    "EV-RUNNER-OUTPUT-READY-WITHOUT-VERIFIED-ISOLATION"
                ),
                "title": (
                    "SUT_DECISION_READY without verified isolation is "
                    "forbidden"
                ),
                "defect_class": (
                    "DEFECT-READY-OUTPUT-WITHOUT-VERIFIED-ISOLATION"
                ),
                "variant_kind": "RUNNER_OUTPUT",
                "target_schema_ref": RUNNER_OUTPUT_SCHEMA_ID,
                "candidate": ready_without_isolation,
                "expected_runner_state": (
                    "BLOCKED_UNVERIFIED_ISOLATION"
                ),
                "reason_ids": [
                    "REASON-READY-OUTPUT-LACKS-VERIFIED-ISOLATION"
                ],
                "assertion_id": (
                    "ASSERT-READY-STATE-REQUIRES-VERIFIED-ISOLATION"
                ),
            },
        ]
    )
    if len(specifications) != 27:
        _fail(
            f"runner conformance specification count mismatch: "
            f"{len(specifications)}"
        )
    cases = [
        _make_conformance_case(
            specification,
            runner_contract_id=runner_contract_id,
            fixtures=fixtures,
            forbidden_result_members=forbidden_result_members,
        )
        for specification in specifications
    ]
    case_ids = [case["case_id"] for case in cases]
    if len(case_ids) != len(set(case_ids)):
        _fail("duplicate runner conformance case ID")
    return sorted(cases, key=lambda item: item["case_id"])


def _validate_risk_register(
    risk_register: Mapping[str, Any],
    risk_register_raw: bytes,
) -> None:
    _validate_bound_json(
        risk_register,
        risk_register_raw,
        source="evaluation risk register",
    )
    entries = _require_list(
        risk_register.get("entries"),
        source="evaluation risk entries",
    )
    _unique_map(
        entries,
        "risk_id",
        source="evaluation risk entry",
    )
    for entry in entries:
        risk_id = entry.get("risk_id")
        if entry.get("risk_sha256") != _self_hash(
            entry,
            "risk_sha256",
            source=f"risk entry {risk_id}",
        ):
            _fail(f"risk entry self-hash mismatch: {risk_id}")
    if risk_register.get("register_sha256") != _self_hash(
        risk_register,
        "register_sha256",
        source="evaluation risk register",
    ):
        _fail("evaluation risk register self-hash mismatch")


def _canonical_repository_path(
    repository_path: Any,
    *,
    source: str,
) -> PurePosixPath:
    if (
        not isinstance(repository_path, str)
        or not repository_path
        or "\\" in repository_path
        or ":" in repository_path
    ):
        _fail(f"{source} is not a canonical POSIX repository path")
    path = PurePosixPath(repository_path)
    if (
        path.is_absolute()
        or str(path) != repository_path
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        _fail(f"{source} is not a canonical POSIX repository path")
    return path


def _collect_fixture_case_references(
    cases: Sequence[Mapping[str, Any]],
    conformance_cases: Sequence[Mapping[str, Any]],
) -> dict[str, set[str]]:
    references: dict[str, set[str]] = {}

    def add(fixture_id: Any, case_id: str) -> None:
        if not isinstance(fixture_id, str) or not fixture_id:
            _fail(f"case {case_id} has invalid fixture reference")
        references.setdefault(fixture_id, set()).add(case_id)

    for case in cases:
        case_id = str(case["case_id"])
        runner_input = _require_object(
            case.get("input"),
            source=f"case {case_id} runner input",
        )
        for fixture_id in _require_list(
            runner_input.get("fixture_refs"),
            source=f"case {case_id} fixture refs",
        ):
            add(fixture_id, case_id)
        oracle = _require_object(
            case.get("oracle"),
            source=f"case {case_id} oracle",
        )
        trace_fixture_id = oracle.get("reference_trace_fixture_id")
        if trace_fixture_id is not None:
            add(trace_fixture_id, case_id)
    for case in conformance_cases:
        case_id = str(case["case_id"])
        fixture_refs = case["invocation"]["input_variant"]["fixture_refs"]
        for fixture_id in fixture_refs:
            add(fixture_id, case_id)
    return references


def _validate_case_fixture_containment(
    cases: Sequence[Mapping[str, Any]],
    *,
    conformance_cases: Sequence[Mapping[str, Any]],
    runner_contracts: Sequence[Mapping[str, Any]],
    fixtures: Mapping[str, Mapping[str, Any]],
) -> None:
    contracts = _unique_map(
        runner_contracts,
        "runner_contract_id",
        source="rendered runner contract",
    )
    def validate_references(
        *,
        case_id: Any,
        runner_contract_id: Any,
        fixture_refs: Any,
    ) -> None:
        contract = contracts.get(runner_contract_id)
        if contract is None:
            _fail(f"case runner missing for fixture containment: {case_id}")
        fixture_mount = _require_object(
            contract.get("fixture_mount"),
            source=f"case {case_id} fixture mount",
        )
        runtime_root = fixture_mount.get("logical_runtime_root")
        normalized_root = _normalize_windows_runtime_path(
            runtime_root,
            source=f"case {case_id} logical runtime root",
        )
        for fixture_id in _require_list(
            fixture_refs,
            source=f"case {case_id} fixture refs",
        ):
            fixture = fixtures.get(fixture_id)
            if fixture is None:
                _fail(
                    f"case {case_id} references unknown fixture: "
                    f"{fixture_id}"
                )
            logical_paths = _require_list(
                fixture.get("logical_runtime_paths"),
                source=f"fixture {fixture_id} logical runtime paths",
            )
            for logical_path in logical_paths:
                normalized_path = _normalize_windows_runtime_path(
                    logical_path,
                    source=f"fixture {fixture_id} logical path",
                )
                try:
                    common = ntpath.commonpath(
                        [normalized_root, normalized_path]
                    )
                except ValueError:
                    common = ""
                if (
                    common != normalized_root
                    or normalized_path == normalized_root
                ):
                    _fail(
                        "case fixture logical path escapes runner root: "
                        f"case={case_id}; fixture={fixture_id}; "
                        f"root={runtime_root}; path={logical_path}"
                    )

    for case in cases:
        case_id = case.get("case_id")
        runner_input = _require_object(
            case.get("input"),
            source=f"case {case_id} runner input",
        )
        validate_references(
            case_id=case_id,
            runner_contract_id=case.get("runner_contract_id"),
            fixture_refs=runner_input.get("fixture_refs"),
        )
    for case in conformance_cases:
        case_id = case.get("case_id")
        invocation = _require_object(
            case.get("invocation"),
            source=f"conformance case {case_id} invocation",
        )
        input_variant = _require_object(
            invocation.get("input_variant"),
            source=f"conformance case {case_id} input variant",
        )
        validate_references(
            case_id=case_id,
            runner_contract_id=invocation.get("runner_contract_id"),
            fixture_refs=input_variant.get("fixture_refs"),
        )


def _normalize_windows_runtime_path(
    value: Any,
    *,
    source: str,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "/" in value
        or not ntpath.isabs(value)
    ):
        _fail(f"{source} is not an absolute Windows path")
    _, tail = ntpath.splitdrive(value)
    segments = tail.split("\\")
    if any(segment in {".", ".."} for segment in segments):
        _fail(f"{source} contains a dot traversal segment")
    if ":" in tail:
        _fail(f"{source} contains an NTFS alternate data stream")
    if any(
        segment.endswith((" ", "."))
        for segment in segments
        if segment
    ):
        _fail(f"{source} contains a Windows-aliased path segment")
    return ntpath.normcase(ntpath.normpath(value))


def _validate_fixture_catalog(
    fixture_catalog: Mapping[str, Any],
    fixture_catalog_raw: bytes,
    fixture_blobs: Mapping[str, bytes],
    *,
    cases: Sequence[Mapping[str, Any]],
    conformance_cases: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    _validate_bound_json(
        fixture_catalog,
        fixture_catalog_raw,
        source="evaluation fixture catalog",
    )
    if fixture_catalog.get("catalog_sha256") != _self_hash(
        fixture_catalog,
        "catalog_sha256",
        prefixed=False,
        source="evaluation fixture catalog",
    ):
        _fail("evaluation fixture catalog self-hash mismatch")
    fixtures = _require_list(
        fixture_catalog.get("fixtures"),
        source="evaluation fixtures",
    )
    fixture_ids = [
        fixture.get("fixture_id")
        if isinstance(fixture, Mapping)
        else None
        for fixture in fixtures
    ]
    _validate_identifier_baseline(
        fixture_ids,
        expected_count=FIXTURE_BASELINE[0],
        expected_sha256=FIXTURE_BASELINE[1],
        source="evaluation fixture",
    )
    if not all(
        isinstance(fixture_id, str) and fixture_id
        for fixture_id in fixture_ids
    ):
        _fail("fixture catalog contains an invalid fixture ID")
    if fixture_ids != sorted(fixture_ids):
        _fail("fixture catalog fixtures are not sorted by fixture_id")
    fixtures_by_id = _unique_map(
        fixtures,
        "fixture_id",
        source="evaluation fixture",
    )
    references = _collect_fixture_case_references(
        cases,
        conformance_cases,
    )
    repository_paths: set[str] = set()
    repository_casefold_paths: set[str] = set()
    logical_paths: set[str] = set()
    logical_casefold_paths: set[str] = set()
    for fixture_id, fixture in fixtures_by_id.items():
        repository_path = fixture.get("repository_path")
        path = _canonical_repository_path(
            repository_path,
            source=f"fixture {fixture_id} repository path",
        )
        if repository_path in repository_paths:
            _fail(f"duplicate fixture repository path: {repository_path}")
        repository_paths.add(repository_path)
        path_casefold = repository_path.casefold()
        if path_casefold in repository_casefold_paths:
            _fail(
                "case-insensitive fixture repository path collision: "
                f"{repository_path}"
            )
        repository_casefold_paths.add(path_casefold)
        parts = path.parts
        if (
            len(parts) < 5
            or parts[:3] != ("evaluation", "aegis_v2", "fixtures")
            or not _SHA256_RE.fullmatch(parts[3])
        ):
            _fail(f"fixture outside content-addressed root: {fixture_id}")
        raw_sha256 = fixture.get("raw_sha256")
        if parts[3] != raw_sha256:
            _fail(f"fixture CAS path mismatch: {fixture_id}")

        runtime_paths = _require_list(
            fixture.get("logical_runtime_paths"),
            source=f"fixture {fixture_id} logical runtime paths",
        )
        if not runtime_paths:
            _fail(f"fixture has no logical runtime path: {fixture_id}")
        local_paths: set[str] = set()
        for logical_path in runtime_paths:
            if not isinstance(logical_path, str) or not logical_path:
                _fail(f"fixture has invalid logical path: {fixture_id}")
            if logical_path in local_paths:
                _fail(
                    f"duplicate logical path within fixture: {fixture_id}"
                )
            local_paths.add(logical_path)
            if logical_path in logical_paths:
                _fail(f"duplicate fixture logical path: {logical_path}")
            logical_paths.add(logical_path)
            casefold_path = logical_path.casefold()
            if casefold_path in logical_casefold_paths:
                _fail(
                    "case-insensitive fixture logical path collision: "
                    f"{logical_path}"
                )
            logical_casefold_paths.add(casefold_path)
        if runtime_paths != sorted(runtime_paths):
            _fail(
                "fixture logical_runtime_paths are not sorted: "
                f"{fixture_id}"
            )

        raw = fixture_blobs.get(repository_path)
        if raw is None:
            _fail(f"fixture bytes missing: {fixture_id}")
        try:
            raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise ManifestBuildError(
                f"fixture is not strict UTF-8: {fixture_id}: {error}"
            ) from error
        if raw.startswith(b"\xef\xbb\xbf"):
            _fail(f"fixture has forbidden UTF-8 BOM: {fixture_id}")
        if b"\r" in raw:
            _fail(f"fixture has forbidden CR/CRLF: {fixture_id}")
        if fixture.get("byte_size") != len(raw):
            _fail(f"fixture byte-size mismatch: {fixture_id}")
        if raw_sha256 != _sha256(raw):
            _fail(f"fixture raw hash mismatch: {fixture_id}")
        jcs_sha256 = fixture.get("jcs_sha256")
        if jcs_sha256 is not None:
            value = _parse_strict_json(
                raw,
                source=f"fixture {fixture_id}",
            )
            if jcs_sha256 != _value_sha256(
                value,
                source=f"fixture {fixture_id}",
            ):
                _fail(f"fixture JCS hash mismatch: {fixture_id}")

        declared_case_ids = _require_list(
            fixture.get("case_ids"),
            source=f"fixture {fixture_id} reverse case IDs",
        )
        if not all(
            isinstance(case_id, str) and case_id
            for case_id in declared_case_ids
        ):
            _fail(f"invalid fixture reverse case ID: {fixture_id}")
        if declared_case_ids != sorted(declared_case_ids):
            _fail(f"fixture case_ids are not sorted: {fixture_id}")
        if len(declared_case_ids) != len(set(declared_case_ids)):
            _fail(f"duplicate fixture reverse case ID: {fixture_id}")
        declared = set(declared_case_ids)
        observed = references.get(fixture_id, set())
        if declared != observed:
            _fail(
                f"fixture reverse closure mismatch: {fixture_id}; "
                f"declared={sorted(declared)}; referenced={sorted(observed)}"
            )
    unknown = sorted(set(references) - set(fixtures_by_id))
    if unknown:
        _fail(f"cases reference unknown fixtures: {unknown}")
    if (
        fixture_catalog.get("catalog_sha256")
        != FIXTURE_CATALOG_BASELINE_SHA256
    ):
        _fail("evaluation fixture catalog baseline mismatch")
    return fixtures_by_id


def _build_denominator_groups(
    existing: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    groups = [
        _require_object(group, source="denominator group")
        for group in existing
        if group.get("group_id") != "DENOM-EVALUATOR-ISOLATION"
    ]
    _validate_identifier_baseline(
        [
            group.get("group_id")
            if isinstance(group, Mapping)
            else None
            for group in groups
        ],
        expected_count=DENOMINATOR_BASELINE[0],
        expected_sha256=DENOMINATOR_BASELINE[1],
        source="evaluation denominator group",
    )
    groups.append(
        {
            "group_id": "DENOM-EVALUATOR-ISOLATION",
            "description": (
                "Every frozen outer-runner isolation conformance case must "
                "block before SUT process creation and receive no PASS "
                "credit."
            ),
            "release_requirement": (
                "ALL_RUNNER_CONFORMANCE_CASES_MUST_BLOCK_WITHOUT_SPAWN"
            ),
            "group_sha256": "",
        }
    )
    by_id = _unique_map(
        groups,
        "group_id",
        source="denominator group",
    )
    rendered = []
    for group_id in sorted(by_id):
        group = by_id[group_id]
        _set_self_hash(
            group,
            "group_sha256",
            source=f"denominator group {group_id}",
        )
        rendered.append(group)
    return rendered


def _artifact_binding(
    current: Mapping[str, Any],
    *,
    artifact_kind: str,
    repository_path: str,
    declared_content_hash: str,
    raw: bytes,
    schema_ref: str | None = None,
) -> dict[str, Any]:
    result = copy.deepcopy(dict(current))
    result["artifact_kind"] = artifact_kind
    if schema_ref is not None:
        result["schema_ref"] = schema_ref
    result["repository_path"] = repository_path
    result["declared_content_hash"] = declared_content_hash
    result["raw_sha256"] = _sha256(raw)
    result["byte_size"] = len(raw)
    result["byte_domain"] = "EXACT_GIT_BLOB_BYTES_UTF8_LF_NO_BOM"
    return result


def render_evaluation_manifest(
    *,
    template: Mapping[str, Any],
    evaluation_schema: Mapping[str, Any],
    runner_schema: Mapping[str, Any],
    source_manifest_schema: Mapping[str, Any],
    common_schema: Mapping[str, Any],
    schema_documents: Mapping[str, Mapping[str, Any]],
    schema_raw_documents: Mapping[str, bytes],
    schema_bundle: Mapping[str, Any],
    schema_bundle_raw: bytes,
    source_manifest: Mapping[str, Any],
    source_manifest_raw: bytes,
    source_blobs: Mapping[str, bytes],
    fixture_catalog: Mapping[str, Any],
    fixture_catalog_raw: bytes,
    fixture_blobs: Mapping[str, bytes],
    risk_register: Mapping[str, Any],
    risk_register_raw: bytes,
) -> dict[str, Any]:
    """Return a complete deterministic candidate without writing files."""

    result = _require_object(template, source="evaluation manifest template")
    _validate_schema_bundle_inputs(
        schema_bundle,
        schema_bundle_raw,
        schema_documents=schema_documents,
        schema_raw_documents=schema_raw_documents,
    )
    schema_registry, schemas_by_id = _build_offline_schema_registry(
        schema_documents
    )
    for label, schema in (
        ("evaluation manifest", evaluation_schema),
        ("runner contract", runner_schema),
        ("reference source manifest", source_manifest_schema),
        ("common", common_schema),
    ):
        schema_id = schema.get("$id")
        if (
            not isinstance(schema_id, str)
            or schemas_by_id.get(schema_id) != schema
        ):
            _fail(
                f"{label} schema does not match the offline schema bundle"
            )
    source_entries, comparator_specs = _validate_source_manifest(
        source_manifest,
        source_manifest_raw,
        source_blobs,
        source_manifest_schema=source_manifest_schema,
        schema_registry=schema_registry,
    )
    runtime_schema_bundle = _require_object(
        _require_object(
            source_manifest.get("runtime_binding"),
            source="reference runtime binding",
        ).get("schema_bundle"),
        source="reference runtime schema bundle binding",
    )
    if (
        runtime_schema_bundle.get("bundle_id")
        != schema_bundle.get("bundle_id")
        or runtime_schema_bundle.get("bundle_sha256")
        != schema_bundle.get("bundle_sha256")
    ):
        _fail("reference runtime schema bundle identity mismatch")
    _validate_risk_register(risk_register, risk_register_raw)
    evaluation_schema_id = evaluation_schema.get("$id")
    if not isinstance(evaluation_schema_id, str):
        _fail("evaluation manifest schema has no $id")
    _validate_schema_fragment(
        risk_register,
        schema_id=evaluation_schema_id,
        fragment="/$defs/riskRegister",
        registry=schema_registry,
        source="evaluation risk register",
    )
    if (
        risk_register.get("register_sha256")
        != RISK_REGISTER_BASELINE_SHA256
    ):
        _fail("evaluation risk register baseline mismatch")
    fixture_catalog_schema = schemas_by_id.get(
        FIXTURE_CATALOG_SCHEMA_ID
    )
    if fixture_catalog_schema is None:
        _fail("evaluation fixture catalog schema is not bundled")
    _validate_schema_instance(
        fixture_catalog,
        schema=fixture_catalog_schema,
        registry=schema_registry,
        source="evaluation fixture catalog",
    )
    if fixture_catalog.get("catalog_sha256") != _self_hash(
        fixture_catalog,
        "catalog_sha256",
        prefixed=False,
        source="evaluation fixture catalog",
    ):
        _fail("evaluation fixture catalog self-hash mismatch")

    static_contracts, runner_aliases = (
        _normalise_static_runner_contracts(
            result,
            runner_schema=runner_schema,
            fixture_catalog=fixture_catalog,
            comparator_specs=comparator_specs,
        )
    )
    property_contracts, property_suites = (
        _build_property_contracts_and_suites(
            _require_list(
                result.get("property_suites"),
                source="property suites",
            ),
            static_contracts=static_contracts,
            source_entries=source_entries,
        )
    )
    cases = _normalise_cases(
        _require_list(result.get("cases"), source="evaluation cases"),
        runner_aliases=runner_aliases,
    )
    fixture_index = _unique_map(
        _require_list(
            fixture_catalog.get("fixtures"),
            source="evaluation fixtures",
        ),
        "fixture_id",
        source="evaluation fixture",
    )
    _validate_identifier_baseline(
        list(fixture_index),
        expected_count=FIXTURE_BASELINE[0],
        expected_sha256=FIXTURE_BASELINE[1],
        source="evaluation fixture",
    )
    conformance_cases = _build_conformance_cases(
        static_contracts=static_contracts,
        runner_schema=runner_schema,
        evaluation_schema=evaluation_schema,
        fixtures=fixture_index,
        fixture_blobs=fixture_blobs,
    )
    _validate_case_fixture_containment(
        cases,
        conformance_cases=conformance_cases,
        runner_contracts=static_contracts,
        fixtures=fixture_index,
    )
    ordinary_ids = {case["case_id"] for case in cases}
    conformance_ids = {
        case["case_id"] for case in conformance_cases
    }
    overlap = sorted(ordinary_ids & conformance_ids)
    if overlap:
        _fail(f"ordinary and conformance case IDs overlap: {overlap}")
    _validate_fixture_catalog(
        fixture_catalog,
        fixture_catalog_raw,
        fixture_blobs,
        cases=cases,
        conformance_cases=conformance_cases,
    )
    _validate_collection_baseline(
        conformance_cases,
        expected_sha256=RENDERED_CONFORMANCE_BASELINE_SHA256,
        source="rendered runner conformance corpus",
    )
    _validate_collection_baseline(
        cases,
        expected_sha256=RENDERED_CASES_BASELINE_SHA256,
        source="rendered ordinary case corpus",
    )

    root_properties = evaluation_schema.get("properties", {})
    for key in ("schema_version", "manifest_kind", "canonicalization"):
        definition = root_properties.get(key)
        if not isinstance(definition, Mapping):
            _fail(f"evaluation schema root property missing: {key}")
        result[key] = _frozen_value(
            definition,
            schema=evaluation_schema,
            source=f"evaluation manifest {key}",
        )
    result["freeze"] = _frozen_object(
        _schema_definition(evaluation_schema, "pendingFreeze"),
        schema=evaluation_schema,
        source="pendingFreeze",
    )
    result["hash_contract"] = _frozen_object(
        _schema_definition(evaluation_schema, "hashContract"),
        schema=evaluation_schema,
        source="hashContract",
    )
    result["history_policy"] = _frozen_object(
        _schema_definition(evaluation_schema, "historyPolicy"),
        schema=evaluation_schema,
        source="historyPolicy",
    )
    result["release_policy"] = _frozen_object(
        _schema_definition(evaluation_schema, "releasePolicy"),
        schema=evaluation_schema,
        source="releasePolicy",
    )
    result["capability_claim_policy"] = _frozen_object(
        _schema_definition(evaluation_schema, "capabilityClaimPolicy"),
        schema=evaluation_schema,
        source="capabilityClaimPolicy",
    )
    all_contracts = sorted(
        [*static_contracts, *property_contracts],
        key=lambda item: item["runner_contract_id"],
    )
    if len(all_contracts) != len(static_contracts) + 2:
        _fail("derived property runner count mismatch")
    if len(
        {contract["runner_contract_id"] for contract in all_contracts}
    ) != len(all_contracts):
        _fail("runner contract IDs are not unique")
    result["runner_contracts"] = all_contracts
    _validate_collection_baseline(
        all_contracts,
        expected_sha256=RENDERED_RUNNERS_BASELINE_SHA256,
        source="rendered runner contract corpus",
    )
    result["property_suites"] = property_suites
    _validate_collection_baseline(
        property_suites,
        expected_sha256=RENDERED_PROPERTY_SUITES_BASELINE_SHA256,
        source="rendered property suite corpus",
    )
    result["cases"] = cases
    result["runner_conformance_cases"] = conformance_cases
    result["denominator_groups"] = _build_denominator_groups(
        _require_list(
            result.get("denominator_groups"),
            source="denominator groups",
        )
    )
    _validate_collection_baseline(
        result["denominator_groups"],
        expected_sha256=RENDERED_DENOMINATORS_BASELINE_SHA256,
        source="rendered denominator corpus",
    )
    result["fixture_catalog_binding"] = _artifact_binding(
        _require_object(
            result.get("fixture_catalog_binding"),
            source="fixture catalog binding",
        ),
        artifact_kind="EVALUATION_FIXTURE_CATALOG",
        repository_path=FIXTURE_CATALOG_PATH.as_posix(),
        declared_content_hash=(
            f"sha256:{fixture_catalog['catalog_sha256']}"
        ),
        raw=fixture_catalog_raw,
    )
    result["risk_register_binding"] = _artifact_binding(
        _require_object(
            result.get("risk_register_binding"),
            source="risk register binding",
        ),
        artifact_kind="EVALUATION_RISK_REGISTER",
        repository_path=RISK_REGISTER_PATH.as_posix(),
        declared_content_hash=risk_register["register_sha256"],
        raw=risk_register_raw,
    )
    result["reference_source_manifest_binding"] = _artifact_binding(
        {},
        artifact_kind="REFERENCE_SOURCE_MANIFEST",
        repository_path=SOURCE_MANIFEST_PATH.as_posix(),
        declared_content_hash=(
            f"sha256:{source_manifest['manifest_sha256']}"
        ),
        raw=source_manifest_raw,
        schema_ref=SOURCE_MANIFEST_SCHEMA_ID,
    )
    _set_self_hash(
        result,
        "manifest_sha256",
        source="evaluation manifest",
    )
    _validate_schema_instance(
        result,
        schema=evaluation_schema,
        registry=schema_registry,
        source="rendered evaluation manifest",
    )
    return result


def manifest_matches_expected(
    *,
    observed: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> bool:
    return _jcs(
        observed,
        source="observed evaluation manifest",
    ) == _jcs(
        expected,
        source="expected evaluation manifest",
    )


def render_evaluation_manifest_bytes(
    value: Mapping[str, Any],
) -> bytes:
    """Return the exact candidate bytes without writing a pathname."""

    return _jcs(value, source="rendered evaluation manifest") + b"\n"


def _assert_no_reparse_components(
    root: Path,
    relative: PurePosixPath,
) -> Path:
    current = root
    for part in relative.parts:
        current = current / part
        try:
            metadata = os.lstat(current)
        except OSError as error:
            raise ManifestBuildError(
                f"repository blob missing: {relative.as_posix()}: {error}"
            ) from error
        file_attributes = getattr(
            metadata,
            "st_file_attributes",
            0,
        )
        if (
            stat.S_ISLNK(metadata.st_mode)
            or bool(
                file_attributes
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            )
            or (
                hasattr(os.path, "isjunction")
                and os.path.isjunction(current)
            )
        ):
            _fail(
                "repository blob path traverses a reparse point: "
                f"{relative.as_posix()}"
            )
    return current


def _windows_final_path_from_handle(handle: int) -> Path:
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    function = kernel32.GetFinalPathNameByHandleW
    function.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
    ]
    function.restype = ctypes.c_uint32
    capacity = 32768
    buffer = ctypes.create_unicode_buffer(capacity)
    length = function(handle, buffer, capacity, 0)
    if length == 0 or length >= capacity:
        error_code = ctypes.get_last_error()
        raise ManifestBuildError(
            "cannot resolve opened repository file handle: "
            f"winerror={error_code}"
        )
    value = buffer.value
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return Path(value)


def _windows_final_path(file_descriptor: int) -> Path:
    import msvcrt

    return _windows_final_path_from_handle(
        msvcrt.get_osfhandle(file_descriptor)
    )


def _open_windows_directory_guard(directory: Path) -> int:
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p
    handle = create_file(
        str(directory),
        0x0001 | 0x0080,  # FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES
        0x0001,  # FILE_SHARE_READ; deny write/delete sharing
        None,
        3,  # OPEN_EXISTING
        0x02000000 | 0x00200000,  # BACKUP_SEMANTICS | OPEN_REPARSE_POINT
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle in (None, invalid_handle):
        error_code = ctypes.get_last_error()
        raise ManifestBuildError(
            "cannot lock schema directory for enumeration: "
            f"winerror={error_code}"
        )
    try:
        if _windows_handle_is_reparse(handle):
            _fail("opened schema directory handle is a reparse point")
        final_path = _windows_final_path_from_handle(handle)
        if os.path.normcase(
            os.path.abspath(final_path)
        ) != os.path.normcase(os.path.abspath(directory)):
            _fail("opened schema directory identity mismatch")
    except BaseException:
        _close_windows_handle(handle)
        raise
    return handle


def _windows_handle_is_reparse(handle: int) -> bool:
    import ctypes

    class FileAttributeTagInfo(ctypes.Structure):
        _fields_ = [
            ("FileAttributes", ctypes.c_uint32),
            ("ReparseTag", ctypes.c_uint32),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_information = kernel32.GetFileInformationByHandleEx
    get_information.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    get_information.restype = ctypes.c_int
    information = FileAttributeTagInfo()
    if not get_information(
        handle,
        9,  # FileAttributeTagInfo
        ctypes.byref(information),
        ctypes.sizeof(information),
    ):
        error_code = ctypes.get_last_error()
        raise ManifestBuildError(
            "cannot inspect schema directory handle attributes: "
            f"winerror={error_code}"
        )
    return bool(
        information.FileAttributes
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _close_windows_handle(handle: int) -> None:
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int
    if not close_handle(handle):
        error_code = ctypes.get_last_error()
        raise ManifestBuildError(
            f"cannot close schema directory guard: winerror={error_code}"
        )


def _verify_opened_repository_file(
    stream: Any,
    *,
    expected_path: Path,
    repository_path: str,
) -> None:
    if os.name == "nt":
        final_path = _windows_final_path(stream.fileno())
        if os.path.normcase(os.path.abspath(final_path)) != os.path.normcase(
            os.path.abspath(expected_path)
        ):
            _fail(
                "opened repository file identity mismatch: "
                f"{repository_path}"
            )
        return
    opened = os.fstat(stream.fileno())
    expected = os.stat(expected_path, follow_symlinks=False)
    if (opened.st_dev, opened.st_ino) != (
        expected.st_dev,
        expected.st_ino,
    ):
        _fail(
            f"opened repository file identity mismatch: {repository_path}"
        )


def _read_repository_blob(
    root: Path,
    repository_path: str,
    *,
    snapshot: dict[str, bytes] | None = None,
) -> bytes:
    relative = _canonical_repository_path(
        repository_path,
        source="repository blob path",
    )
    current = _assert_no_reparse_components(root, relative)
    try:
        with current.open("rb") as stream:
            _assert_no_reparse_components(root, relative)
            _verify_opened_repository_file(
                stream,
                expected_path=current,
                repository_path=repository_path,
            )
            raw = stream.read()
    except OSError as error:
        raise ManifestBuildError(
            f"cannot read repository blob {repository_path}: {error}"
        ) from error
    if snapshot is not None:
        if (
            repository_path in snapshot
            and snapshot[repository_path] != raw
        ):
            _fail(
                "repository input changed during snapshot acquisition: "
                f"{repository_path}"
            )
        snapshot.setdefault(repository_path, raw)
    return raw


def _load_repository_json(
    root: Path,
    repository_path: str,
    *,
    snapshot: dict[str, bytes],
) -> tuple[Any, bytes]:
    raw = _read_repository_blob(
        root,
        repository_path,
        snapshot=snapshot,
    )
    return (
        _parse_strict_json(raw, source=repository_path),
        raw,
    )


def _verify_repository_snapshot(
    root: Path,
    snapshot: Mapping[str, bytes],
) -> None:
    for repository_path, expected in sorted(snapshot.items()):
        observed = _read_repository_blob(root, repository_path)
        if observed != expected:
            _fail(
                "repository input changed before snapshot commit: "
                f"{repository_path}"
            )


def _schema_directory_membership(root: Path) -> set[str]:
    relative = PurePosixPath("schemas/aegis/v2")
    directory = _assert_no_reparse_components(root, relative)
    if not directory.is_dir():
        _fail(f"schema directory is not a directory: {directory}")
    directory_guard = (
        _open_windows_directory_guard(directory)
        if os.name == "nt"
        else None
    )
    try:
        with os.scandir(directory) as entries:
            names = []
            for entry in entries:
                if not entry.name.endswith(".schema.json"):
                    continue
                metadata = entry.stat(follow_symlinks=False)
                file_attributes = getattr(
                    metadata,
                    "st_file_attributes",
                    0,
                )
                if (
                    entry.is_symlink()
                    or not entry.is_file(follow_symlinks=False)
                    or bool(
                        file_attributes
                        & getattr(
                            stat,
                            "FILE_ATTRIBUTE_REPARSE_POINT",
                            0,
                        )
                    )
                ):
                    _fail(
                        "schema directory contains a non-regular or "
                        f"reparse schema entry: {entry.name}"
                    )
                names.append(entry.name)
    except OSError as error:
        raise ManifestBuildError(
            f"cannot enumerate schema directory: {error}"
        ) from error
    finally:
        if directory_guard is not None:
            _close_windows_handle(directory_guard)
    _assert_no_reparse_components(root, relative)
    return {
        f"schemas/aegis/v2/{name}"
        for name in names
    }


def _validate_schema_directory_membership(
    root: Path,
    declared_paths: set[str],
) -> None:
    observed_paths = _schema_directory_membership(root)
    if observed_paths != declared_paths:
        _fail(
            "schema directory membership mismatch: "
            f"declared={sorted(declared_paths)}; "
            f"observed={sorted(observed_paths)}"
        )


def _render_from_repository(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot: dict[str, bytes] = {}
    template, _ = _load_repository_json(
        root,
        MANIFEST_PATH.as_posix(),
        snapshot=snapshot,
    )
    schema_bundle, schema_bundle_raw = _load_repository_json(
        root,
        SCHEMA_BUNDLE_PATH.as_posix(),
        snapshot=snapshot,
    )
    schema_entries = _require_list(
        _require_object(
            schema_bundle,
            source="offline schema bundle",
        ).get("schemas"),
        source="offline schema entries",
    )
    declared_schema_paths = {
        entry.get("path")
        for entry in schema_entries
        if isinstance(entry, Mapping)
        and isinstance(entry.get("path"), str)
    }
    if len(declared_schema_paths) != len(schema_entries):
        _fail("offline schema bundle has invalid or duplicate paths")
    _validate_schema_directory_membership(
        root,
        declared_schema_paths,
    )
    schema_documents: dict[str, Mapping[str, Any]] = {}
    schema_raw_documents: dict[str, bytes] = {}
    for entry in schema_entries:
        if not isinstance(entry, Mapping):
            _fail("offline schema entry must be an object")
        repository_path = entry.get("path")
        canonical_path = _canonical_repository_path(
            repository_path,
            source="offline schema entry path",
        )
        if (
            canonical_path.parent
            != PurePosixPath("schemas/aegis/v2")
            or not canonical_path.name.endswith(".schema.json")
        ):
            _fail(
                f"offline schema entry path is out of scope: "
                f"{repository_path}"
            )
        schema, raw = _load_repository_json(
            root,
            repository_path,
            snapshot=snapshot,
        )
        if not isinstance(schema, Mapping):
            _fail(f"schema root must be an object: {repository_path}")
        if repository_path in schema_documents:
            _fail(f"duplicate offline schema path: {repository_path}")
        schema_documents[repository_path] = schema
        schema_raw_documents[repository_path] = raw
    required_schemas = {}
    for schema_path in (
        EVALUATION_SCHEMA_PATH,
        RUNNER_SCHEMA_PATH,
        SOURCE_MANIFEST_SCHEMA_PATH,
        COMMON_SCHEMA_PATH,
    ):
        schema = schema_documents.get(schema_path.as_posix())
        if schema is None:
            _fail(f"required schema is missing: {schema_path.as_posix()}")
        required_schemas[schema_path.as_posix()] = schema
    evaluation_schema = required_schemas[
        EVALUATION_SCHEMA_PATH.as_posix()
    ]
    runner_schema = required_schemas[RUNNER_SCHEMA_PATH.as_posix()]
    source_manifest_schema = required_schemas[
        SOURCE_MANIFEST_SCHEMA_PATH.as_posix()
    ]
    common_schema = required_schemas[COMMON_SCHEMA_PATH.as_posix()]
    source_manifest, source_raw = _load_repository_json(
        root,
        SOURCE_MANIFEST_PATH.as_posix(),
        snapshot=snapshot,
    )
    fixture_catalog, fixture_raw = _load_repository_json(
        root,
        FIXTURE_CATALOG_PATH.as_posix(),
        snapshot=snapshot,
    )
    risk_register, risk_raw = _load_repository_json(
        root,
        RISK_REGISTER_PATH.as_posix(),
        snapshot=snapshot,
    )
    for label, value in (
        ("evaluation manifest", template),
        ("evaluation schema", evaluation_schema),
        ("runner schema", runner_schema),
        ("source manifest schema", source_manifest_schema),
        ("common schema", common_schema),
        ("source manifest", source_manifest),
        ("fixture catalog", fixture_catalog),
        ("risk register", risk_register),
    ):
        if not isinstance(value, Mapping):
            _fail(f"{label} root must be an object")
    source_paths: set[str] = set()
    for collection_name in ("source_files", "assurance_files"):
        for item in _require_list(
            source_manifest.get(collection_name),
            source=f"reference {collection_name}",
        ):
            if not isinstance(item, Mapping):
                _fail(
                    f"reference {collection_name} entry must be an object"
                )
            repository_path = item.get("repository_path")
            _canonical_repository_path(
                repository_path,
                source=f"reference {collection_name} path",
            )
            source_paths.add(repository_path)
    runtime_binding = _require_object(
        source_manifest.get("runtime_binding"),
        source="reference runtime binding",
    )
    for binding_name in ("pyproject", "lock", "schema_bundle"):
        binding = _require_object(
            runtime_binding.get(binding_name),
            source=f"reference runtime {binding_name} binding",
        )
        repository_path = binding.get("repository_path")
        _canonical_repository_path(
            repository_path,
            source=f"reference runtime {binding_name} path",
        )
        source_paths.add(repository_path)
    source_blobs = {
        path: _read_repository_blob(
            root,
            path,
            snapshot=snapshot,
        )
        for path in sorted(source_paths)
    }
    fixture_blobs: dict[str, bytes] = {}
    for fixture in _require_list(
        fixture_catalog.get("fixtures"),
        source="evaluation fixtures",
    ):
        if not isinstance(fixture, Mapping):
            _fail("evaluation fixture entry must be an object")
        repository_path = fixture.get("repository_path")
        _canonical_repository_path(
            repository_path,
            source="evaluation fixture repository path",
        )
        fixture_blobs[repository_path] = _read_repository_blob(
            root,
            repository_path,
            snapshot=snapshot,
        )
    rendered = render_evaluation_manifest(
        template=template,
        evaluation_schema=evaluation_schema,
        runner_schema=runner_schema,
        source_manifest_schema=source_manifest_schema,
        common_schema=common_schema,
        schema_documents=schema_documents,
        schema_raw_documents=schema_raw_documents,
        schema_bundle=schema_bundle,
        schema_bundle_raw=schema_bundle_raw,
        source_manifest=source_manifest,
        source_manifest_raw=source_raw,
        source_blobs=source_blobs,
        fixture_catalog=fixture_catalog,
        fixture_catalog_raw=fixture_raw,
        fixture_blobs=fixture_blobs,
        risk_register=risk_register,
        risk_register_raw=risk_raw,
    )
    _verify_repository_snapshot(root, snapshot)
    _validate_schema_directory_membership(
        root,
        declared_schema_paths,
    )
    return _require_object(template, source="evaluation manifest"), rendered


def _write_atomic(path: Path, value: Mapping[str, Any]) -> None:
    del path, value
    _fail(
        "filesystem manifest replacement is disabled: no verified "
        "reparse-safe atomic commit primitive is available; use "
        "render_evaluation_manifest_bytes() and an independently "
        "authorized safe writer"
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministically rebuild or check the Aegis v2 evaluation "
            "manifest."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_args(argv)
    try:
        root = arguments.repo_root.resolve(strict=True)
        observed, expected = _render_from_repository(root)
        if arguments.write:
            _write_atomic(root / MANIFEST_PATH, expected)
            state = "WRITTEN"
            exit_code = 0
        elif manifest_matches_expected(
            observed=observed,
            expected=expected,
        ):
            state = "CURRENT"
            exit_code = 0
        else:
            state = "STALE"
            exit_code = 1
        report = {
            "schema_version": "EvaluationManifestBuildReport.v1",
            "state": state,
            "ordinary_case_count": len(expected["cases"]),
            "runner_contract_count": len(expected["runner_contracts"]),
            "property_suite_count": len(expected["property_suites"]),
            "runner_conformance_case_count": len(
                expected["runner_conformance_cases"]
            ),
            "manifest_sha256": expected["manifest_sha256"],
            "assurance_boundaries": dict(
                SOURCE_POLICY_ASSURANCE_BOUNDARIES
            ),
        }
    except Exception as error:
        report = {
            "schema_version": "EvaluationManifestBuildReport.v1",
            "state": "INVALID",
            "error_type": type(error).__name__,
            "errors": [str(error)],
            "assurance_boundaries": dict(
                SOURCE_POLICY_ASSURANCE_BOUNDARIES
            ),
        }
        exit_code = 1
    sys.stdout.buffer.write(
        _jcs(report, source="evaluation manifest build report") + b"\n"
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
