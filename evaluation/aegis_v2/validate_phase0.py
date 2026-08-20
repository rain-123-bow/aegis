from __future__ import annotations

import argparse
import ast
import base64
import copy
import hashlib
import itertools
import json
import math
import os
import re
import stat
import sys
import tomllib
import unicodedata
import urllib.parse
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

import jsonschema
import rfc8785
from referencing import Registry, Resource


SCHEMA_DIRECTORY = Path("schemas/aegis/v2")
EVALUATION_DIRECTORY = Path("evaluation/aegis_v2")
MANIFEST_PATH = EVALUATION_DIRECTORY / "evaluation_manifest.v1.json"
FIXTURE_CATALOG_PATH = EVALUATION_DIRECTORY / "fixture_catalog.v1.json"
RISK_REGISTER_PATH = EVALUATION_DIRECTORY / "risk_register.v1.json"
REFERENCE_MANIFEST_PATH = (
    EVALUATION_DIRECTORY / "reference/source_manifest.v1.json"
)
SCHEMA_BUNDLE_PATH = SCHEMA_DIRECTORY / "schema_bundle.v1.json"
LOCK_PATH = Path("pylock.windows-py313.toml")
PYPROJECT_PATH = Path("pyproject.toml")

_FIXED_PHASE0A_REPOSITORY_INPUTS = {
    "docs/aegis_v2_requirements.md": (
        "REQUIREMENT_DESIGN",
        "UTF8_LF_NO_BOM",
    ),
    "docs/aegis_v2_upgrade_plan.md": (
        "REVIEWED_IMPLEMENTATION_PLAN",
        "UTF8_LF_NO_BOM",
    ),
    "docs/aegis_v2_codex_static_evidence.md": (
        "STATIC_CAPABILITY_EVIDENCE",
        "UTF8_LF_NO_BOM",
    ),
    "docs/aegis_v2_phase0_contract.md": (
        "NORMATIVE_CONTRACT",
        "UTF8_LF_NO_BOM",
    ),
    "docs/decisions/0001-aegis-v2-dual-plane.md": (
        "ARCHITECTURE_DECISION",
        "UTF8_LF_NO_BOM",
    ),
    ".gitattributes": ("ATTRIBUTE_POLICY", "GIT_BLOB_BYTES"),
    "pyproject.toml": ("PROJECT_METADATA", "GIT_BLOB_BYTES"),
    "pylock.windows-py313.toml": (
        "PLATFORM_DEPENDENCY_LOCK",
        "GIT_BLOB_BYTES",
    ),
    "schemas/aegis/v2/schema_bundle.v1.json": (
        "VERSIONED_SCHEMA",
        "JCS_RFC8785",
    ),
    "evaluation/aegis_v2/evaluation_manifest.v1.json": (
        "EVALUATION_MANIFEST",
        "JCS_RFC8785",
    ),
    "evaluation/aegis_v2/fixture_catalog.v1.json": (
        "FIXTURE_CATALOG",
        "JCS_RFC8785",
    ),
    "evaluation/aegis_v2/risk_register.v1.json": (
        "EXCLUSION_RISK_REGISTER",
        "JCS_RFC8785",
    ),
    "evaluation/aegis_v2/reference/source_manifest.v1.json": (
        "EVALUATION_REFERENCE_SOURCE_MANIFEST",
        "JCS_RFC8785",
    ),
}
_REQUIRED_REFERENCE_SOURCE_PATHS = frozenset(
    {
        "evaluation/aegis_v2/reference/__init__.py",
        "evaluation/aegis_v2/reference/__main__.py",
        "evaluation/aegis_v2/reference/canonical.py",
        "evaluation/aegis_v2/reference/cli.py",
        "evaluation/aegis_v2/reference/closure.py",
        "evaluation/aegis_v2/reference/closure_materialization_data.py",
        "evaluation/aegis_v2/reference/comparator.py",
        "evaluation/aegis_v2/reference/coverage.py",
        "evaluation/aegis_v2/reference/generator.py",
        "evaluation/aegis_v2/reference/manifest.py",
        "evaluation/aegis_v2/reference/materialization.py",
        "evaluation/aegis_v2/reference/materialize_closure.py",
        "evaluation/aegis_v2/reference/materialize_verdict.py",
        "evaluation/aegis_v2/reference/schema_validation.py",
        "evaluation/aegis_v2/reference/verdict.py",
        "evaluation/aegis_v2/reference/verdict_facts.py",
    }
)
_REQUIRED_REFERENCE_ASSURANCE_PATHS = frozenset(
    {
        "evaluation/aegis_v2/reference/README.md",
        "evaluation/aegis_v2/reference/tests/test_audit_remediation.py",
        "evaluation/aegis_v2/reference/tests/test_reference.py",
    }
)

CRITICAL_LOCK_VERSIONS = {
    "jsonschema": "4.26.0",
    "langgraph": "1.2.9",
    "langgraph-checkpoint-sqlite": "3.1.0",
    "pytest": "9.1.1",
    "referencing": "0.37.0",
    "rfc8785": "0.1.4",
    "xxhash": "3.8.1",
}
REFERENCE_RUNTIME_DISTRIBUTIONS = frozenset(
    {
        "arrow",
        "attrs",
        "fqdn",
        "idna",
        "isoduration",
        "jsonpointer",
        "jsonschema",
        "jsonschema-specifications",
        "lark",
        "python-dateutil",
        "referencing",
        "rfc3339-validator",
        "rfc3986-validator",
        "rfc3987-syntax",
        "rfc8785",
        "rpds-py",
        "six",
        "tzdata",
        "uri-template",
        "webcolors",
    }
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CONTENT_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")
_DIRECT_PIN_RE = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]+\])?==([^;\s]+)$"
)


class ValidationError(RuntimeError):
    """A deterministic fail-closed Phase 0A validation failure."""


def _fail(message: str) -> NoReturn:
    raise ValidationError(message)


def _reject_duplicate_members(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON member: {key!r}")
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> NoReturn:
    raise ValidationError(f"non-finite JSON number is forbidden: {value}")


def _read_utf8_lf_no_bom(path: Path) -> bytes:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ValidationError(f"cannot read {path}: {error}") from error
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail(f"BOM is forbidden: {path}")
    if b"\r" in raw:
        _fail(f"CR/CRLF is forbidden: {path}")
    try:
        raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValidationError(f"invalid UTF-8 in {path}: {error}") from error
    return raw


def _parse_json_bytes(raw: bytes, *, source: str) -> Any:
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail(f"BOM is forbidden: {source}")
    if b"\r" in raw:
        _fail(f"CR/CRLF is forbidden: {source}")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValidationError(f"invalid UTF-8 in {source}: {error}") from error
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_members,
            parse_constant=_reject_nonfinite_constant,
        )
    except ValidationError:
        raise
    except (json.JSONDecodeError, ValueError) as error:
        raise ValidationError(f"invalid JSON in {source}: {error}") from error


def load_strict_json(path: Path) -> Any:
    """Load JSON without accepting duplicate keys, BOM, CRLF, or NaN."""

    return _parse_json_bytes(path.read_bytes(), source=str(path))


def _jcs(value: Any, *, source: str) -> bytes:
    try:
        return rfc8785.dumps(value)
    except (TypeError, ValueError, rfc8785.CanonicalizationError) as error:
        raise ValidationError(f"JCS canonicalization failed for {source}: {error}") from error


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _jcs_sha256(value: Any, *, source: str) -> str:
    return _sha256(_jcs(value, source=source))


def _without_member(value: Mapping[str, Any], member: str) -> dict[str, Any]:
    if member not in value:
        _fail(f"required self-hash member {member!r} is absent")
    result = dict(value)
    del result[member]
    return result


def _expect_hash(
    actual: Any,
    expected_hex: str,
    *,
    source: str,
    prefixed: bool,
) -> None:
    expected = f"sha256:{expected_hex}" if prefixed else expected_hex
    if actual != expected:
        _fail(f"{source} mismatch: expected {expected}, got {actual!r}")


def _verify_self_hash(
    value: Mapping[str, Any],
    field: str,
    *,
    source: str,
    prefixed: bool,
) -> str:
    digest = _jcs_sha256(
        _without_member(value, field),
        source=f"{source} preimage",
    )
    _expect_hash(
        value[field],
        digest,
        source=f"{source}.{field}",
        prefixed=prefixed,
    )
    return digest


def _unique(
    values: Iterable[Any],
    *,
    source: str,
    key=lambda value: value,
) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for value in values:
        identity = key(value)
        if identity in result:
            _fail(f"duplicate {source}: {identity!r}")
        result[identity] = value
    return result


def _repository_path(root: Path, relative: Any, *, source: str) -> Path:
    if not isinstance(relative, str) or not relative:
        _fail(f"{source} must be a nonempty repository-relative path")
    if (
        relative.startswith(("/", "\\"))
        or "\\" in relative
        or _DRIVE_PATH_RE.match(relative)
        or ":" in PurePosixPath(relative).parts[0]
    ):
        _fail(f"absolute or non-portable repository path in {source}: {relative!r}")
    pure = PurePosixPath(relative)
    if (
        pure.as_posix() != relative
        or any(part in ("", ".", "..") for part in pure.parts)
    ):
        _fail(f"non-canonical repository path in {source}: {relative!r}")
    candidate = root
    for part in pure.parts:
        candidate = candidate / part
        try:
            metadata = os.lstat(candidate)
        except OSError as error:
            raise ValidationError(
                f"repository path is unavailable in {source}: {relative!r}: "
                f"{error}"
            ) from error
        file_attributes = getattr(metadata, "st_file_attributes", 0)
        if (
            stat.S_ISLNK(metadata.st_mode)
            or bool(
                file_attributes
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            )
            or (
                hasattr(os.path, "isjunction")
                and os.path.isjunction(candidate)
            )
        ):
            _fail(
                f"repository path traverses a symlink, junction, or reparse "
                f"point in {source}: {relative!r}"
            )
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise ValidationError(
            f"repository path escapes root in {source}: {relative!r}"
        ) from error
    return candidate


def _read_repository_bytes(
    root: Path,
    relative: Any,
    *,
    source: str,
) -> bytes:
    path = _repository_path(root, relative, source=source)
    if not path.is_file():
        _fail(f"repository path is not a regular file in {source}: {relative!r}")
    try:
        return path.read_bytes()
    except OSError as error:
        raise ValidationError(
            f"cannot read repository file in {source}: {relative!r}: {error}"
        ) from error


def _read_repository_utf8_lf_no_bom(
    root: Path,
    relative: Any,
    *,
    source: str,
) -> bytes:
    raw = _read_repository_bytes(root, relative, source=source)
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail(f"BOM is forbidden: {source}")
    if b"\r" in raw:
        _fail(f"CR/CRLF is forbidden: {source}")
    try:
        raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValidationError(f"invalid UTF-8 in {source}: {error}") from error
    return raw


def _load_repository_json(
    root: Path,
    relative: Any,
    *,
    source: str,
) -> Any:
    raw = _read_repository_bytes(root, relative, source=source)
    return _parse_json_bytes(raw, source=source)


def _repository_tree_files(
    root: Path,
    relative_directory: str,
    *,
    source: str,
    optional: bool = False,
) -> Iterator[Path]:
    """Enumerate without following an unchecked directory or member."""

    try:
        directory = _repository_path(
            root,
            relative_directory,
            source=f"{source} directory",
        )
    except ValidationError as error:
        if optional and isinstance(error.__cause__, FileNotFoundError):
            return
        raise
    if not directory.is_dir():
        _fail(f"{source} directory is not a directory: {relative_directory}")
    pending = [relative_directory]
    while pending:
        current_relative = pending.pop()
        current = _repository_path(
            root,
            current_relative,
            source=f"{source} directory member",
        )
        if not current.is_dir():
            _fail(f"{source} traversal member is not a directory: {current_relative}")
        try:
            with os.scandir(current) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError as error:
            raise ValidationError(
                f"cannot enumerate {source} directory {current_relative}: {error}"
            ) from error
        for entry in entries:
            relative = (
                PurePosixPath(current_relative) / entry.name
            ).as_posix()
            checked = _repository_path(
                root,
                relative,
                source=f"{source} enumerated member",
            )
            if checked.is_dir():
                if entry.name != "__pycache__":
                    pending.append(relative)
            elif checked.is_file():
                yield checked
            else:
                _fail(f"{source} contains a non-regular member: {relative}")


def _add_required_phase0a_input(
    root: Path,
    required: dict[str, tuple[str, str]],
    path: Any,
    artifact_kind: str,
    byte_domain: str,
    *,
    source: str,
) -> str:
    if (
        not isinstance(path, str)
        or not path
        or "\\" in path
        or PurePosixPath(path).as_posix() != path
    ):
        _fail(f"{source} must be a repository-relative path")
    checked = _repository_path(root, path, source=source)
    if not checked.is_file():
        _fail(f"{source} must identify a regular repository file: {path}")
    if path in required:
        _fail(f"duplicate normative Phase 0A repository path: {path}")
    required[path] = (artifact_kind, byte_domain)
    return path


def _phase0a_paths_from_rows(
    root: Path,
    value: Mapping[str, Any],
    member: str,
    *,
    source: str,
) -> list[str]:
    rows = value.get(member)
    if not isinstance(rows, list) or not rows:
        _fail(f"{source}.{member} must be a nonempty array")
    paths: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            _fail(f"{source}.{member}[{index}] must be an object")
        path = row.get("repository_path")
        if not isinstance(path, str):
            _fail(f"{source}.{member}[{index}].repository_path must be a string")
        checked = _repository_path(
            root,
            path,
            source=f"{source}.{member}[{index}].repository_path",
        )
        if not checked.is_file():
            _fail(
                f"{source}.{member}[{index}].repository_path is not a file"
            )
        paths.append(path)
    if len(paths) != len(set(paths)):
        _fail(f"{source}.{member} contains duplicate repository paths")
    return paths


def _derive_required_phase0a_repository_inputs(
    root: Path,
) -> dict[str, tuple[str, str]]:
    """Independently derive the repository portion of the normative freeze root."""

    required: dict[str, tuple[str, str]] = {}
    for path, (artifact_kind, byte_domain) in (
        _FIXED_PHASE0A_REPOSITORY_INPUTS.items()
    ):
        _add_required_phase0a_input(
            root,
            required,
            path,
            artifact_kind,
            byte_domain,
            source=f"fixed normative Phase 0A input {path}",
        )

    schema_bundle = _load_repository_json(
        root,
        SCHEMA_BUNDLE_PATH.as_posix(),
        source="normative schema bundle",
    )
    if not isinstance(schema_bundle, Mapping):
        _fail("normative schema bundle root must be an object")
    schema_rows = schema_bundle.get("schemas")
    if not isinstance(schema_rows, list) or not schema_rows:
        _fail("normative schema bundle.schemas must be a nonempty array")
    schema_paths: list[str] = []
    for index, row in enumerate(schema_rows):
        if not isinstance(row, Mapping) or not isinstance(row.get("path"), str):
            _fail(f"normative schema bundle.schemas[{index}].path is invalid")
        schema_paths.append(row["path"])
    if len(schema_paths) != len(set(schema_paths)):
        _fail("normative schema bundle contains duplicate schema paths")
    actual_schema_paths = {
        path.relative_to(root).as_posix()
        for path in _repository_tree_files(
            root,
            SCHEMA_DIRECTORY.as_posix(),
            source="versioned schema closure",
        )
        if path.name.endswith(".schema.json")
    }
    if set(schema_paths) != actual_schema_paths:
        _fail(
            "normative schema closure membership mismatch; "
            f"missing_from_bundle={sorted(actual_schema_paths - set(schema_paths))}, "
            f"missing_from_directory={sorted(set(schema_paths) - actual_schema_paths)}"
        )
    for path in schema_paths:
        _add_required_phase0a_input(
            root,
            required,
            path,
            "VERSIONED_SCHEMA",
            "JCS_RFC8785",
            source=f"normative schema {path}",
        )

    manifest_path = MANIFEST_PATH.as_posix()
    manifest = _load_repository_json(
        root,
        manifest_path,
        source="normative evaluation manifest",
    )
    if not isinstance(manifest, Mapping):
        _fail("normative evaluation manifest root must be an object")
    seen_manifest_paths = {manifest_path}
    while True:
        parent_hash = manifest.get("parent_manifest_hash")
        parent_locator = manifest.get("parent_manifest_locator")
        if parent_hash is None:
            if parent_locator is not None:
                _fail("normative root manifest has an orphan parent locator")
            break
        if (
            not isinstance(parent_hash, str)
            or _CONTENT_ID_RE.fullmatch(parent_hash) is None
        ):
            _fail("normative parent manifest hash is invalid")
        if not isinstance(parent_locator, Mapping):
            _fail("normative parent manifest locator must be an object")
        if parent_locator.get("declared_manifest_sha256") != parent_hash:
            _fail("normative parent manifest locator/hash mismatch")
        parent_path = parent_locator.get("repository_path")
        if not isinstance(parent_path, str):
            _fail("normative parent manifest repository_path is invalid")
        if parent_path in seen_manifest_paths:
            _fail(f"normative evaluation manifest parent cycle: {parent_path}")
        seen_manifest_paths.add(parent_path)
        _add_required_phase0a_input(
            root,
            required,
            parent_path,
            "EVALUATION_MANIFEST",
            "JCS_RFC8785",
            source=f"normative parent manifest {parent_path}",
        )
        manifest = _load_repository_json(
            root,
            parent_path,
            source=f"normative parent manifest {parent_path}",
        )
        if not isinstance(manifest, Mapping):
            _fail(f"normative parent manifest root is invalid: {parent_path}")
    parent_paths = seen_manifest_paths - {manifest_path}
    actual_parent_paths = {
        path.relative_to(root).as_posix()
        for path in _repository_tree_files(
            root,
            (EVALUATION_DIRECTORY / "manifests/sha256").as_posix(),
            source="parent manifest CAS closure",
            optional=True,
        )
    }
    if parent_paths != actual_parent_paths:
        _fail(
            "normative parent manifest closure membership mismatch; "
            f"unreachable_cas={sorted(actual_parent_paths - parent_paths)}, "
            f"missing_cas={sorted(parent_paths - actual_parent_paths)}"
        )

    catalog = _load_repository_json(
        root,
        FIXTURE_CATALOG_PATH.as_posix(),
        source="normative fixture catalog",
    )
    if not isinstance(catalog, Mapping):
        _fail("normative fixture catalog root must be an object")
    fixture_paths = _phase0a_paths_from_rows(
        root,
        catalog,
        "fixtures",
        source="normative fixture catalog",
    )
    actual_fixture_paths = {
        path.relative_to(root).as_posix()
        for path in _repository_tree_files(
            root,
            (EVALUATION_DIRECTORY / "fixtures").as_posix(),
            source="fixture preimage closure",
        )
    }
    if set(fixture_paths) != actual_fixture_paths:
        _fail(
            "normative fixture closure membership mismatch; "
            f"missing_from_catalog={sorted(actual_fixture_paths - set(fixture_paths))}, "
            f"missing_from_directory={sorted(set(fixture_paths) - actual_fixture_paths)}"
        )
    for path in fixture_paths:
        _add_required_phase0a_input(
            root,
            required,
            path,
            "EVALUATION_FIXTURE",
            "GIT_BLOB_BYTES",
            source=f"normative fixture {path}",
        )

    source_manifest = _load_repository_json(
        root,
        REFERENCE_MANIFEST_PATH.as_posix(),
        source="normative reference source manifest",
    )
    if not isinstance(source_manifest, Mapping):
        _fail("normative reference source manifest root must be an object")
    source_paths = _phase0a_paths_from_rows(
        root,
        source_manifest,
        "source_files",
        source="normative reference source manifest",
    )
    assurance_paths = _phase0a_paths_from_rows(
        root,
        source_manifest,
        "assurance_files",
        source="normative reference source manifest",
    )
    if set(source_paths) != _REQUIRED_REFERENCE_SOURCE_PATHS:
        _fail(
            "normative reference source closure mismatch; "
            f"missing={sorted(_REQUIRED_REFERENCE_SOURCE_PATHS - set(source_paths))}, "
            f"extra={sorted(set(source_paths) - _REQUIRED_REFERENCE_SOURCE_PATHS)}"
        )
    if set(assurance_paths) != _REQUIRED_REFERENCE_ASSURANCE_PATHS:
        _fail(
            "normative reference assurance closure mismatch; "
            f"missing={sorted(_REQUIRED_REFERENCE_ASSURANCE_PATHS - set(assurance_paths))}, "
            f"extra={sorted(set(assurance_paths) - _REQUIRED_REFERENCE_ASSURANCE_PATHS)}"
        )
    for path in source_paths:
        _add_required_phase0a_input(
            root,
            required,
            path,
            "EVALUATION_REFERENCE_SOURCE",
            "GIT_BLOB_BYTES",
            source=f"normative reference source {path}",
        )
    for path in assurance_paths:
        _add_required_phase0a_input(
            root,
            required,
            path,
            "EVALUATION_HARNESS",
            "GIT_BLOB_BYTES",
            source=f"normative reference assurance {path}",
        )
    by_casefold: dict[str, str] = {}
    for path in required:
        prior = by_casefold.get(path.casefold())
        if prior is not None and prior != path:
            _fail(
                "normative Phase 0A repository domain has a case-fold "
                f"collision: {prior!r}, {path!r}"
            )
        by_casefold[path.casefold()] = path
    return dict(sorted(required.items()))


def _walk_json(value: Any) -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _json_pointer(document: Any, fragment: str, *, source: str) -> Any:
    if not fragment:
        return document
    if not fragment.startswith("/"):
        _fail(f"unsupported non-pointer JSON Schema fragment in {source}: #{fragment}")
    current = document
    for encoded in fragment[1:].split("/"):
        token = urllib.parse.unquote(encoded).replace("~1", "/").replace("~0", "~")
        try:
            if isinstance(current, list):
                current = current[int(token)]
            else:
                current = current[token]
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ValidationError(
                f"unresolved JSON Schema fragment in {source}: #{fragment}"
            ) from error
    return current


class _OfflineSchemas:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.directory = _repository_path(
            root,
            SCHEMA_DIRECTORY.as_posix(),
            source="schema directory",
        )
        if not self.directory.is_dir():
            _fail(f"schema directory missing: {self.directory}")
        self.by_path: dict[str, dict[str, Any]] = {}
        self.by_id: dict[str, dict[str, Any]] = {}
        self.path_for_id: dict[str, Path] = {}
        try:
            with os.scandir(self.directory) as iterator:
                members = sorted(
                    iterator,
                    key=lambda entry: entry.name,
                )
        except OSError as error:
            raise ValidationError(
                f"cannot enumerate schema directory: {error}"
            ) from error
        for member in members:
            relative = (SCHEMA_DIRECTORY / member.name).as_posix()
            path = _repository_path(
                root,
                relative,
                source=f"schema directory member {relative}",
            )
            if not member.name.endswith(".schema.json"):
                continue
            if not path.is_file():
                _fail(f"versioned schema is not a regular file: {relative}")
            schema = _load_repository_json(
                root,
                relative,
                source=relative,
            )
            if not isinstance(schema, dict):
                _fail(f"schema root must be an object: {path}")
            schema_id = schema.get("$id")
            if not isinstance(schema_id, str) or not schema_id:
                _fail(f"schema has no nonempty $id: {path}")
            if schema_id in self.by_id:
                _fail(
                    f"duplicate schema $id {schema_id!r}: "
                    f"{self.path_for_id[schema_id]} and {path}"
                )
            self.by_path[relative] = schema
            self.by_id[schema_id] = schema
            self.path_for_id[schema_id] = path

        if not self.by_path:
            _fail("no versioned Phase 0A schemas found")
        self.registry = Registry(retrieve=self._network_forbidden).with_resources(
            (
                schema_id,
                Resource.from_contents(schema),
            )
            for schema_id, schema in self.by_id.items()
        )
        self._check_metaschemas_and_refs()

    def _check_metaschemas_and_refs(self) -> None:
        for schema_id, schema in self.by_id.items():
            if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                _fail(
                    f"{self.path_for_id[schema_id]} does not declare Draft 2020-12"
                )
            try:
                jsonschema.Draft202012Validator.check_schema(schema)
            except jsonschema.SchemaError as error:
                raise ValidationError(
                    f"Draft 2020-12 metaschema rejection for "
                    f"{self.path_for_id[schema_id]}: {error.message}"
                ) from error

            for keyword, reference in _walk_json(schema):
                if keyword not in {"$ref", "$dynamicRef"}:
                    continue
                if not isinstance(reference, str):
                    _fail(
                        f"non-string {keyword} in {self.path_for_id[schema_id]}"
                    )
                absolute = urllib.parse.urljoin(schema_id, reference)
                target_id, fragment = urllib.parse.urldefrag(absolute)
                if target_id.startswith("https://json-schema.org/draft/2020-12/"):
                    continue
                target = self.by_id.get(target_id)
                if target is None:
                    _fail(
                        f"offline schema closure failure: {reference!r} from "
                        f"{self.path_for_id[schema_id]} is not bundled"
                    )
                _json_pointer(
                    target,
                    fragment,
                    source=f"{self.path_for_id[schema_id]} -> {reference}",
                )

    @staticmethod
    def _network_forbidden(uri: str) -> NoReturn:
        _fail(f"network schema resolution is forbidden: {uri}")

    def validate(
        self,
        instance: Any,
        *,
        schema_path: str | None = None,
        schema_id: str | None = None,
        schema_fragment: str = "",
        source: str,
    ) -> None:
        if (schema_path is None) == (schema_id is None):
            _fail("exactly one schema locator must be supplied")
        if schema_path is not None:
            schema = self.by_path.get(schema_path)
            if schema is None:
                _fail(f"required schema is not bundled: {schema_path}")
            schema_id = schema["$id"]
        else:
            assert schema_id is not None
            schema = self.by_id.get(schema_id)
            if schema is None:
                _fail(f"required schema ID is not bundled: {schema_id}")

        if schema_fragment:
            wrapper = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": f"urn:aegis:validation-wrapper:{hashlib.sha256(source.encode()).hexdigest()}",
                "$ref": f"{schema_id}#{schema_fragment}",
            }
            selected = wrapper
        else:
            selected = schema

        validator = jsonschema.Draft202012Validator(
            selected,
            registry=self.registry,
            format_checker=jsonschema.FormatChecker(),
        )
        errors = sorted(
            validator.iter_errors(instance),
            key=lambda error: (
                tuple(str(part) for part in error.absolute_path),
                error.message,
            ),
        )
        if errors:
            first = errors[0]
            location = "/".join(str(part) for part in first.absolute_path)
            _fail(
                f"schema validation failed for {source}"
                f"{' at /' + location if location else ''}: {first.message}"
            )


def _validate_schema_bundle(
    root: Path,
    schemas: _OfflineSchemas,
) -> dict[str, Any]:
    bundle = _load_repository_json(
        root,
        SCHEMA_BUNDLE_PATH.as_posix(),
        source=SCHEMA_BUNDLE_PATH.as_posix(),
    )
    if not isinstance(bundle, dict):
        _fail("schema bundle root must be an object")
    entries = bundle.get("schemas")
    if not isinstance(entries, list):
        _fail("schema bundle schemas must be an array")
    by_path = _unique(
        entries,
        source="schema bundle path",
        key=lambda entry: entry.get("path") if isinstance(entry, dict) else None,
    )
    expected_paths = set(schemas.by_path)
    actual_paths = set(by_path)
    missing = sorted(expected_paths - actual_paths)
    extra = sorted(actual_paths - expected_paths)
    if missing or extra:
        _fail(
            f"schema bundle membership mismatch; missing={missing}, extra={extra}"
        )

    hash_contract = bundle.get("hash_contract")
    if not isinstance(hash_contract, dict):
        _fail("schema bundle hash_contract must be an object")
    entry_preimage = (
        hash_contract.get("schema_entry_sha256_preimage")
        or hash_contract.get("entry_sha256_preimage")
        or hash_contract.get("schema_sha256_preimage")
    )
    if entry_preimage != "RFC8785_JCS_UTF8":
        _fail(
            "schema bundle does not freeze schema-entry sha256 as RFC8785 JCS UTF-8"
        )
    size_preimage = (
        hash_contract.get("schema_entry_byte_size_preimage")
        or hash_contract.get("entry_byte_size_preimage")
        or hash_contract.get("schema_byte_size_preimage")
    )
    if size_preimage != "RFC8785_JCS_UTF8":
        _fail(
            "schema bundle does not freeze schema-entry byte_size as "
            "RFC8785 JCS UTF-8"
        )

    for relative, schema in schemas.by_path.items():
        entry = by_path[relative]
        if not isinstance(entry, dict):
            _fail(f"invalid schema bundle entry for {relative}")
        _read_repository_utf8_lf_no_bom(
            root,
            relative,
            source=relative,
        )
        canonical = _jcs(schema, source=relative)
        if entry.get("byte_size") != len(canonical):
            _fail(f"schema bundle byte_size mismatch for {relative}")
        digest = _sha256(canonical)
        _expect_hash(
            entry.get("sha256"),
            digest,
            source=f"schema bundle sha256 for {relative}",
            prefixed=True,
        )

    _verify_self_hash(
        bundle,
        "bundle_sha256",
        source="schema bundle",
        prefixed=True,
    )
    return bundle


def _artifact_binding(
    root: Path,
    binding: Mapping[str, Any],
    *,
    expected_path: Path,
    declared_hex: str,
    source: str,
) -> None:
    relative = binding.get("repository_path")
    if relative != expected_path.as_posix():
        _fail(
            f"{source}.repository_path mismatch: "
            f"expected {expected_path.as_posix()!r}, got {relative!r}"
        )
    raw = _read_repository_utf8_lf_no_bom(
        root,
        relative,
        source=f"{source}.repository_path",
    )
    if binding.get("byte_size") != len(raw):
        _fail(f"{source}.byte_size mismatch")
    if binding.get("raw_sha256") != _sha256(raw):
        _fail(f"{source}.raw_sha256 mismatch")
    if binding.get("declared_content_hash") != f"sha256:{declared_hex}":
        _fail(f"{source}.declared_content_hash mismatch")


def _collect_fixture_references(case: Mapping[str, Any]) -> set[str]:
    references: set[str] = set()
    for key, value in _walk_json(case):
        if key == "fixture_refs":
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                _fail(f"invalid fixture_refs in case {case.get('case_id')!r}")
            references.update(value)
        elif key == "reference_trace_fixture_id" and value is not None:
            if not isinstance(value, str):
                _fail(
                    f"invalid reference_trace_fixture_id in case "
                    f"{case.get('case_id')!r}"
                )
            references.add(value)
    return references


def _verify_fixture_preimage(
    root: Path,
    fixture_id: str,
    fixture: Mapping[str, Any],
) -> None:
    relative = fixture["repository_path"]
    raw = _read_repository_bytes(
        root,
        relative,
        source=f"fixture {fixture_id}.repository_path",
    )
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail(f"fixture BOM is forbidden: {relative}")
    if b"\r" in raw:
        _fail(f"fixture CR/CRLF is forbidden: {relative}")
    try:
        raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValidationError(f"invalid UTF-8 fixture {relative}: {error}") from error
    if fixture["byte_size"] != len(raw):
        _fail(f"fixture {fixture_id} size mismatch")
    digest = _sha256(raw)
    if fixture["raw_sha256"] != digest:
        _fail(f"fixture {fixture_id} raw_sha256 mismatch")
    parts = PurePosixPath(relative).parts
    try:
        fixture_root_index = parts.index("fixtures")
        cas_component = parts[fixture_root_index + 1]
    except (ValueError, IndexError) as error:
        raise ValidationError(
            f"fixture {fixture_id} path is outside the fixture CAS: {relative}"
        ) from error
    if cas_component != digest:
        _fail(f"fixture {fixture_id} path CAS does not match raw_sha256")

    if (
        fixture["media_type"] == "application/json"
        and fixture["jcs_sha256"] is not None
    ):
        parsed = _parse_json_bytes(raw, source=relative)
        jcs_digest = _jcs_sha256(parsed, source=relative)
        if fixture["jcs_sha256"] != jcs_digest:
            _fail(f"fixture {fixture_id} jcs_sha256 mismatch")
    elif (
        fixture["media_type"] != "application/json"
        and fixture["jcs_sha256"] is not None
    ):
        _fail(f"text fixture {fixture_id} must have null jcs_sha256")


def _windows_path_key(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("\\", "/")).casefold()


def _validate_fixture_path_namespace(
    fixtures: Mapping[str, Mapping[str, Any]],
) -> None:
    fixture_ids = list(fixtures)
    if fixture_ids != sorted(fixture_ids):
        _fail("fixture catalog must be Unicode-code-point sorted by fixture_id")

    repository_keys: dict[str, str] = {}
    logical_keys: dict[str, tuple[str, str]] = {}
    for fixture_id, fixture in fixtures.items():
        repository_path = fixture["repository_path"]
        repository_key = unicodedata.normalize(
            "NFC",
            repository_path,
        ).casefold()
        prior_repository = repository_keys.get(repository_key)
        if prior_repository is not None:
            _fail(
                "case-insensitive fixture repository path collision: "
                f"{prior_repository!r} and {repository_path!r}"
            )
        repository_keys[repository_key] = repository_path

        logical_paths = fixture["logical_runtime_paths"]
        if logical_paths != sorted(logical_paths):
            _fail(
                f"fixture {fixture_id} logical_runtime_paths must be "
                "Unicode-code-point sorted"
            )
        case_ids = fixture["case_ids"]
        if case_ids != sorted(case_ids):
            _fail(
                f"fixture {fixture_id} case_ids must be "
                "Unicode-code-point sorted"
            )
        for logical_path in logical_paths:
            logical_key = _windows_path_key(logical_path)
            prior_logical = logical_keys.get(logical_key)
            if prior_logical is not None:
                prior_path, prior_fixture_id = prior_logical
                _fail(
                    "case-insensitive logical runtime path collision: "
                    f"{prior_fixture_id}:{prior_path!r} and "
                    f"{fixture_id}:{logical_path!r}"
                )
            logical_keys[logical_key] = (logical_path, fixture_id)


def _validate_fixture_visibility(
    regular_cases: Sequence[Mapping[str, Any]],
    _conformance_cases: Sequence[Mapping[str, Any]],
    fixtures: Mapping[str, Mapping[str, Any]],
) -> None:
    for case in regular_cases:
        case_id = case["case_id"]
        input_fixture_ids = set(case["input"]["fixture_refs"])
        trace_fixture_id = case["oracle"]["reference_trace_fixture_id"]
        if trace_fixture_id is None:
            continue
        trace_fixture = fixtures.get(trace_fixture_id)
        if trace_fixture is None:
            _fail(
                f"case {case_id} references unknown trace fixture "
                f"{trace_fixture_id}"
            )
        if trace_fixture["artifact_kind"] != "REFERENCE_TRACE":
            _fail(
                f"case {case_id} oracle trace fixture has wrong artifact kind: "
                f"{trace_fixture_id}"
            )
        if trace_fixture_id in input_fixture_ids:
            _fail(
                f"case {case_id} oracle-only fixture enters the SUT mount: "
                f"{trace_fixture_id}"
            )


def _validate_fixture_catalog(
    root: Path,
    schemas: _OfflineSchemas,
    manifest: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    catalog = _load_repository_json(
        root,
        FIXTURE_CATALOG_PATH.as_posix(),
        source=FIXTURE_CATALOG_PATH.as_posix(),
    )
    schemas.validate(
        catalog,
        schema_path=(
            "schemas/aegis/v2/evaluation_fixture_catalog.v1.schema.json"
        ),
        source=FIXTURE_CATALOG_PATH.as_posix(),
    )
    catalog_digest = _verify_self_hash(
        catalog,
        "catalog_sha256",
        source="fixture catalog",
        prefixed=False,
    )
    _artifact_binding(
        root,
        manifest["fixture_catalog_binding"],
        expected_path=FIXTURE_CATALOG_PATH,
        declared_hex=catalog_digest,
        source="manifest.fixture_catalog_binding",
    )

    fixtures = _unique(
        catalog["fixtures"],
        source="fixture_id",
        key=lambda fixture: fixture["fixture_id"],
    )
    _unique(
        catalog["fixtures"],
        source="fixture repository_path",
        key=lambda fixture: fixture["repository_path"],
    )
    _validate_fixture_path_namespace(fixtures)
    expected_case_ids: dict[str, set[str]] = defaultdict(set)
    all_cases = [
        *manifest.get("cases", []),
        *manifest.get("runner_conformance_cases", []),
    ]
    _validate_fixture_visibility(
        manifest.get("cases", []),
        manifest.get("runner_conformance_cases", []),
        fixtures,
    )
    for case in all_cases:
        case_id = case["case_id"]
        for fixture_id in _collect_fixture_references(case):
            if fixture_id not in fixtures:
                _fail(f"case {case_id} references unknown fixture {fixture_id}")
            expected_case_ids[fixture_id].add(case_id)

    for fixture_id, fixture in fixtures.items():
        _verify_fixture_preimage(root, fixture_id, fixture)

        declared_case_ids = set(fixture["case_ids"])
        expected = expected_case_ids.get(fixture_id, set())
        if declared_case_ids != expected:
            _fail(
                f"fixture {fixture_id} case_ids reverse binding mismatch; "
                f"expected={sorted(expected)}, got={sorted(declared_case_ids)}"
            )

    unreferenced = sorted(set(fixtures) - set(expected_case_ids))
    if unreferenced:
        _fail(f"fixture catalog contains unreferenced fixtures: {unreferenced}")
    return catalog, fixtures


def _validate_risk_register(
    root: Path,
    schemas: _OfflineSchemas,
    manifest: Mapping[str, Any],
    case_ids: set[str],
) -> dict[str, Any]:
    risk = _load_repository_json(
        root,
        RISK_REGISTER_PATH.as_posix(),
        source=RISK_REGISTER_PATH.as_posix(),
    )
    manifest_schema_id = schemas.by_path[
        "schemas/aegis/v2/evaluation_manifest.v1.schema.json"
    ]["$id"]
    schemas.validate(
        risk,
        schema_id=manifest_schema_id,
        schema_fragment="/$defs/riskRegister",
        source=RISK_REGISTER_PATH.as_posix(),
    )
    entries = _unique(
        risk["entries"],
        source="risk_id",
        key=lambda entry: entry["risk_id"],
    )
    for risk_id, entry in entries.items():
        _verify_self_hash(
            entry,
            "risk_sha256",
            source=f"risk entry {risk_id}",
            prefixed=True,
        )
        unknown = sorted(set(entry["linked_case_ids"]) - case_ids)
        if unknown:
            _fail(f"risk entry {risk_id} links unknown cases: {unknown}")
    digest = _verify_self_hash(
        risk,
        "register_sha256",
        source="risk register",
        prefixed=True,
    )
    _artifact_binding(
        root,
        manifest["risk_register_binding"],
        expected_path=RISK_REGISTER_PATH,
        declared_hex=digest,
        source="manifest.risk_register_binding",
    )
    return risk


def _source_imports(path: Path) -> tuple[set[str], set[str], bool]:
    raw = _read_utf8_lf_no_bom(path)
    try:
        tree = ast.parse(raw.decode("utf-8"), filename=str(path))
    except SyntaxError as error:
        raise ValidationError(f"invalid Python source {path}: {error}") from error
    absolute_roots: set[str] = set()
    local_modules: set[str] = set()
    dynamic = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                absolute_roots.add(root)
                if alias.name.startswith("evaluation.aegis_v2.reference."):
                    local_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                prefix = "." * node.level
                if node.module:
                    local_modules.add(prefix + node.module)
                else:
                    for alias in node.names:
                        if alias.name == "*":
                            dynamic = True
                        else:
                            local_modules.add(prefix + alias.name)
            elif node.module:
                absolute_roots.add(node.module.split(".", 1)[0])
                if node.module.startswith("evaluation.aegis_v2.reference."):
                    local_modules.add(node.module)
        elif isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Name) and target.id == "__import__":
                dynamic = True
            elif (
                isinstance(target, ast.Attribute)
                and target.attr == "import_module"
                and isinstance(target.value, ast.Name)
                and target.value.id == "importlib"
            ):
                dynamic = True
    return absolute_roots, local_modules, dynamic


def _resolve_local_import(source: str, module: str) -> str:
    source_parts = PurePosixPath(source).parts
    package_parts = list(source_parts[:-1])
    if source_parts[-1] == "__init__.py":
        package_parts = list(source_parts[:-1])
    if module.startswith("."):
        level = len(module) - len(module.lstrip("."))
        suffix = module[level:]
        if level > len(package_parts):
            _fail(f"relative import escapes reference package: {source} -> {module}")
        base = package_parts[: len(package_parts) - level + 1]
        module_parts = suffix.split(".") if suffix else []
        target_parts = [*base, *module_parts]
    else:
        target_parts = module.split(".")
    return PurePosixPath(*target_parts).as_posix()


def _resolve_module_source(
    source: str,
    module: str,
    *,
    source_paths: set[str],
) -> str:
    module_path = _resolve_local_import(source, module)
    candidates = [
        f"{module_path}.py",
        f"{module_path}/__init__.py",
    ]
    matches = [candidate for candidate in candidates if candidate in source_paths]
    if len(matches) != 1:
        _fail(
            f"reference import closure is unresolved or ambiguous: "
            f"{source} -> {module}"
        )
    return matches[0]


def _entrypoint_source(
    entrypoint: str,
    *,
    source_paths: set[str],
) -> str:
    candidates: list[tuple[int, str]] = []
    for source_path in source_paths:
        if not source_path.endswith(".py"):
            continue
        module_path = source_path[:-3]
        if module_path.endswith("/__init__"):
            module_path = module_path[: -len("/__init__")]
        module = module_path.replace("/", ".")
        if entrypoint.startswith(module + "."):
            candidates.append((len(module), source_path))
    if not candidates:
        _fail(f"reference entrypoint source is unresolved: {entrypoint}")
    candidates.sort(reverse=True)
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        _fail(f"reference entrypoint source is ambiguous: {entrypoint}")
    return candidates[0][1]


def _validate_algorithm_source_closure(
    entry_id: str,
    entry: Mapping[str, Any],
    *,
    owned_paths: set[str],
    source_paths: set[str],
    imported_by_source: Mapping[
        str,
        tuple[set[str], set[str], bool],
    ],
) -> None:
    direct_paths = set(entry["direct_source_files"])
    if not direct_paths <= owned_paths:
        _fail(
            f"reference algorithm {entry_id} direct sources are not all owned: "
            f"{sorted(direct_paths - owned_paths)}"
        )
    for entrypoint in entry["entrypoints"]:
        source = _entrypoint_source(entrypoint, source_paths=source_paths)
        if source not in direct_paths:
            _fail(
                f"reference algorithm {entry_id} entrypoint source is not "
                f"direct: {entrypoint} -> {source}"
            )
    for relative in owned_paths:
        _, local_modules, _ = imported_by_source.get(
            relative,
            (set(), set(), False),
        )
        for module in local_modules:
            imported_source = _resolve_module_source(
                relative,
                module,
                source_paths=source_paths,
            )
            if imported_source not in owned_paths:
                _fail(
                    f"reference algorithm {entry_id} transitive source closure "
                    f"escapes ownership: {relative} -> {imported_source}"
                )


def _normalize_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _validate_reference_runtime_binding(
    root: Path,
    source_manifest: Mapping[str, Any],
    *,
    schema_bundle: Mapping[str, Any],
    lock: Mapping[str, Any],
    imported_by_source: Mapping[
        str,
        tuple[set[str], set[str], bool],
    ],
) -> None:
    runtime = source_manifest["runtime_binding"]
    file_bindings = (
        ("pyproject", PYPROJECT_PATH),
        ("lock", LOCK_PATH),
        ("schema_bundle", SCHEMA_BUNDLE_PATH),
    )
    for binding_name, expected_path in file_bindings:
        binding = runtime[binding_name]
        if binding["repository_path"] != expected_path.as_posix():
            _fail(f"reference runtime {binding_name} path mismatch")
        raw = _read_repository_utf8_lf_no_bom(
            root,
            binding["repository_path"],
            source=f"reference runtime {binding_name}",
        )
        if binding["byte_size"] != len(raw):
            _fail(f"reference runtime {binding_name} byte_size mismatch")
        if binding["raw_sha256"] != _sha256(raw):
            _fail(f"reference runtime {binding_name} raw_sha256 mismatch")
    bundle_binding = runtime["schema_bundle"]
    if (
        bundle_binding["bundle_id"] != schema_bundle["bundle_id"]
        or bundle_binding["bundle_sha256"] != schema_bundle["bundle_sha256"]
    ):
        _fail("reference runtime schema bundle semantic binding mismatch")

    locked_packages = _unique(
        lock["packages"],
        source="reference runtime locked package",
        key=lambda package: package["name"],
    )
    distributions = runtime["resolved_distributions"]
    names = [distribution["name"] for distribution in distributions]
    if names != sorted(names) or len(names) != len(set(names)):
        _fail(
            "reference runtime distributions must have unique "
            "Unicode-code-point sorted names"
        )
    if set(names) != REFERENCE_RUNTIME_DISTRIBUTIONS:
        _fail(
            "reference runtime distribution closure mismatch; "
            f"missing={sorted(REFERENCE_RUNTIME_DISTRIBUTIONS - set(names))}, "
            f"extra={sorted(set(names) - REFERENCE_RUNTIME_DISTRIBUTIONS)}"
        )

    import_sources: dict[str, set[str]] = defaultdict(set)
    for relative, imported in imported_by_source.items():
        absolute_roots, _, _ = imported
        for root_name in absolute_roots:
            if (
                root_name in sys.stdlib_module_names
                or root_name == "evaluation"
            ):
                continue
            import_sources[_normalize_distribution_name(root_name)].add(
                PurePosixPath(relative).name
            )
    direct_names = set(import_sources)
    resolved_names = set(names)
    if not direct_names <= resolved_names:
        _fail(
            "reference source imports unresolved runtime distributions: "
            f"{sorted(direct_names - resolved_names)}"
        )

    for distribution in distributions:
        name = distribution["name"]
        locked = locked_packages.get(name)
        if locked is None or locked.get("version") != distribution["version"]:
            _fail(
                f"reference runtime lock version mismatch for {name}: "
                f"{distribution['version']!r}"
            )
        via = distribution["via"]
        if via != sorted(via) or len(via) != len(set(via)) or not via:
            _fail(f"reference runtime {name} via must be nonempty and sorted")
        if name in direct_names:
            if distribution["relationship"] != "DIRECT_IMPORT":
                _fail(
                    f"reference runtime {name} must be DIRECT_IMPORT"
                )
            expected_via = sorted(import_sources[name])
            if via != expected_via:
                _fail(
                    f"reference runtime {name} direct import provenance "
                    f"mismatch; expected={expected_via}, got={via}"
                )
        elif distribution["relationship"] != "TRANSITIVE_RUNTIME":
            _fail(
                f"reference runtime {name} must be TRANSITIVE_RUNTIME"
            )
        else:
            for parent in via:
                normalized_parent = _normalize_distribution_name(
                    parent.split("[", 1)[0],
                )
                if normalized_parent not in resolved_names:
                    _fail(
                        f"reference runtime {name} has unresolved via "
                        f"distribution: {parent}"
                    )


def _same_file_binding(
    binding: Mapping[str, Any],
    source: Mapping[str, Any],
) -> bool:
    return all(
        binding.get(field) == source.get(field)
        for field in ("repository_path", "byte_size", "raw_sha256")
    )


def _validate_reference_sources(
    root: Path,
    schemas: _OfflineSchemas,
    manifest: Mapping[str, Any],
    *,
    schema_bundle: Mapping[str, Any],
    lock: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_manifest = _load_repository_json(
        root,
        REFERENCE_MANIFEST_PATH.as_posix(),
        source=REFERENCE_MANIFEST_PATH.as_posix(),
    )
    schemas.validate(
        source_manifest,
        schema_path="schemas/aegis/v2/reference_source_manifest.v1.schema.json",
        source=REFERENCE_MANIFEST_PATH.as_posix(),
    )
    manifest_digest = _verify_self_hash(
        source_manifest,
        "manifest_sha256",
        source="reference source manifest",
        prefixed=False,
    )
    _artifact_binding(
        root,
        manifest["reference_source_manifest_binding"],
        expected_path=REFERENCE_MANIFEST_PATH,
        declared_hex=manifest_digest,
        source="manifest.reference_source_manifest_binding",
    )

    source_files = _unique(
        source_manifest["source_files"],
        source="reference source path",
        key=lambda binding: binding["repository_path"],
    )
    assurance_files = _unique(
        source_manifest["assurance_files"],
        source="reference assurance path",
        key=lambda binding: binding["repository_path"],
    )
    overlap = sorted(set(source_files) & set(assurance_files))
    if overlap:
        _fail(f"reference source/assurance overlap: {overlap}")

    declared_files = {**source_files, **assurance_files}
    for relative, binding in declared_files.items():
        raw = _read_repository_utf8_lf_no_bom(
            root,
            relative,
            source=f"reference file binding {relative}",
        )
        if binding["byte_size"] != len(raw):
            _fail(f"reference file byte_size mismatch: {relative}")
        if binding["raw_sha256"] != _sha256(raw):
            _fail(f"reference file raw_sha256 mismatch: {relative}")

    actual_normative_files = {
        item.relative_to(root).as_posix()
        for item in _repository_tree_files(
            root,
            (EVALUATION_DIRECTORY / "reference").as_posix(),
            source="reference source closure",
        )
        if item.is_file()
        and "__pycache__" not in item.parts
        and item.suffix in {".py", ".md"}
    }
    if set(declared_files) != actual_normative_files:
        _fail(
            "reference source/assurance file closure mismatch; "
            f"missing={sorted(actual_normative_files - set(declared_files))}, "
            f"extra={sorted(set(declared_files) - actual_normative_files)}"
        )

    imported_by_source: dict[str, tuple[set[str], set[str], bool]] = {}
    for relative in declared_files:
        if not relative.endswith(".py"):
            continue
        imported = _source_imports(
            _repository_path(
                root,
                relative,
                source=f"reference import source {relative}",
            )
        )
        imported_by_source[relative] = imported
        absolute_roots, _, dynamic = imported
        if "aegis" in absolute_roots:
            _fail(f"reference source imports production aegis package: {relative}")
        if dynamic:
            _fail(f"dynamic import is forbidden in reference source: {relative}")
    _validate_reference_runtime_binding(
        root,
        source_manifest,
        schema_bundle=schema_bundle,
        lock=lock,
        imported_by_source=imported_by_source,
    )

    algorithms = _unique(
        source_manifest["algorithm_entries"],
        source="reference algorithm entry_id",
        key=lambda entry: entry["entry_id"],
    )
    owned_union: set[str] = set()
    for entry_id, entry in algorithms.items():
        _verify_self_hash(
            entry,
            "entry_sha256",
            source=f"reference algorithm {entry_id}",
            prefixed=False,
        )
        owned = _unique(
            entry["owned_source_files"],
            source=f"{entry_id} owned source path",
            key=lambda binding: binding["repository_path"],
        )
        owned_union.update(owned)
        for relative, binding in owned.items():
            top = source_files.get(relative)
            if top is None or not _same_file_binding(binding, top):
                _fail(
                    f"reference algorithm {entry_id} source binding does not "
                    f"match top-level source_files: {relative}"
                )
        _validate_algorithm_source_closure(
            entry_id,
            entry,
            owned_paths=set(owned),
            source_paths=set(source_files),
            imported_by_source=imported_by_source,
        )

        declared_distributions = {
            re.sub(r"[-.]+", "_", distribution["name"]).lower()
            for distribution in entry["dependency_policy"][
                "third_party_distributions"
            ]
        }
        for relative in owned:
            absolute_roots, local_modules, _ = imported_by_source.get(
                relative,
                (set(), set(), False),
            )
            third_party = {
                root_name
                for root_name in absolute_roots
                if root_name not in sys.stdlib_module_names
                and root_name not in {"evaluation"}
            }
            normalized_imports = {
                re.sub(r"[-.]+", "_", name).lower() for name in third_party
            }
            undeclared = sorted(normalized_imports - declared_distributions)
            if undeclared:
                _fail(
                    f"reference algorithm {entry_id} has unlisted third-party "
                    f"imports in {relative}: {undeclared}"
                )
            for module in local_modules:
                _resolve_module_source(
                    relative,
                    module,
                    source_paths=set(source_files),
                )

    if owned_union != set(source_files):
        _fail(
            "reference algorithm owned-source closure mismatch; "
            f"unowned={sorted(set(source_files) - owned_union)}, "
            f"unknown={sorted(owned_union - set(source_files))}"
        )

    comparator_specs = _unique(
        source_manifest["comparator_specs"],
        source="comparator_id",
        key=lambda spec: spec["comparator_id"],
    )
    for comparator_id, spec in comparator_specs.items():
        _verify_self_hash(
            spec,
            "spec_sha256",
            source=f"comparator spec {comparator_id}",
            prefixed=False,
        )
        algorithm = algorithms.get(spec["algorithm_entry_id"])
        if algorithm is None:
            _fail(
                f"comparator {comparator_id} references unknown algorithm "
                f"{spec['algorithm_entry_id']}"
            )
        if spec["algorithm_entry_sha256"] != algorithm["entry_sha256"]:
            _fail(f"comparator {comparator_id} algorithm hash mismatch")
        trace_id = spec["trace_algorithm_entry_id"]
        trace_hash = spec["trace_algorithm_entry_sha256"]
        if trace_id is None:
            if trace_hash is not None:
                _fail(f"comparator {comparator_id} has orphan trace hash")
        else:
            trace = algorithms.get(trace_id)
            if trace is None or trace_hash != trace["entry_sha256"]:
                _fail(f"comparator {comparator_id} trace algorithm mismatch")

    return source_manifest, algorithms, comparator_specs


def _validate_lock(root: Path) -> dict[str, Any]:
    raw = _read_repository_utf8_lf_no_bom(
        root,
        LOCK_PATH.as_posix(),
        source=LOCK_PATH.as_posix(),
    )
    try:
        lock = tomllib.loads(raw.decode("utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ValidationError(f"invalid dependency lock: {error}") from error
    if lock.get("lock-version") != "1.0":
        _fail("dependency lock must use PEP 751 lock-version 1.0")
    packages = _unique(
        lock.get("packages", []),
        source="locked package",
        key=lambda package: package.get("name"),
    )
    for name, expected in CRITICAL_LOCK_VERSIONS.items():
        package = packages.get(name)
        if package is None or package.get("version") != expected:
            _fail(
                f"critical dependency pin mismatch for {name}: "
                f"expected {expected}, got "
                f"{None if package is None else package.get('version')}"
            )

    for name, package in packages.items():
        if "directory" in package:
            if name != "aegis-quality-kernel":
                _fail(f"unexpected local directory package in lock: {name}")
            continue
        if "sdist" in package:
            _fail(f"source distribution is forbidden in Windows lock: {name}")
        wheels = package.get("wheels")
        if not isinstance(wheels, list) or not wheels:
            _fail(f"locked package has no wheel: {name}")
        for wheel in wheels:
            wheel_name = wheel.get("name", "")
            compatible = (
                wheel_name.endswith("-py3-none-any.whl")
                or wheel_name.endswith("-py2.py3-none-any.whl")
                or (
                    "cp313" in wheel_name
                    and wheel_name.endswith("-win_amd64.whl")
                )
                or wheel_name.endswith("-py3-none-win_amd64.whl")
            )
            if not compatible:
                _fail(
                    f"wheel is not compatible with Windows CPython 3.13: "
                    f"{wheel_name}"
                )
            if not str(wheel.get("url", "")).startswith(
                "https://files.pythonhosted.org/"
            ):
                _fail(f"non-PyPI or non-HTTPS wheel URL for {name}")
            digest = wheel.get("hashes", {}).get("sha256")
            if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
                _fail(f"invalid wheel SHA-256 for {wheel_name}")

    pyproject_raw = _read_repository_utf8_lf_no_bom(
        root,
        PYPROJECT_PATH.as_posix(),
        source=PYPROJECT_PATH.as_posix(),
    )
    try:
        pyproject = tomllib.loads(pyproject_raw.decode("utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ValidationError(f"invalid pyproject.toml: {error}") from error
    project = pyproject.get("project", {})
    declared = [
        *project.get("dependencies", []),
        *project.get("optional-dependencies", {}).get("test", []),
    ]
    for requirement in declared:
        match = _DIRECT_PIN_RE.fullmatch(requirement)
        if match is None:
            _fail(f"direct dependency is not exactly pinned: {requirement!r}")
        name = re.sub(r"[-_.]+", "-", match.group(1)).lower()
        version = match.group(2)
        package = packages.get(name)
        if package is None or package.get("version") != version:
            _fail(f"pyproject/lock version mismatch for {name}=={version}")
    return lock


def _validate_property_suites(
    manifest: Mapping[str, Any],
    runners: Mapping[str, Mapping[str, Any]],
    algorithms: Mapping[str, Mapping[str, Any]],
) -> int:
    total = 0
    suite_ids: set[str] = set()
    for suite in manifest["property_suites"]:
        suite_id = suite["suite_id"]
        if suite_id in suite_ids:
            _fail(f"duplicate property suite_id: {suite_id}")
        suite_ids.add(suite_id)
        _verify_self_hash(
            suite,
            "suite_sha256",
            source=f"property suite {suite_id}",
            prefixed=True,
        )
        runner = runners.get(suite["sut_runner_contract_id"])
        if runner is None:
            _fail(f"property suite {suite_id} references unknown runner")
        domain = suite["domain"]
        domain_order = suite.get("domain_order")
        if (
            not isinstance(domain_order, list)
            or not domain_order
            or not all(
                isinstance(name, str) and name
                for name in domain_order
            )
        ):
            _fail(
                f"property suite {suite_id} domain_order must be a "
                "non-empty array of field names"
            )
        if len(domain_order) != len(set(domain_order)):
            _fail(
                f"property suite {suite_id} domain_order contains duplicates"
            )
        if set(domain_order) != set(domain):
            missing = sorted(set(domain) - set(domain_order))
            extra = sorted(set(domain_order) - set(domain))
            _fail(
                f"property suite {suite_id} domain_order must contain each "
                f"domain field exactly once; missing={missing}, extra={extra}"
            )
        for name in domain_order:
            values = domain[name]
            encoded = [_jcs(value, source=f"{suite_id}.{name}") for value in values]
            if len(set(encoded)) != len(encoded):
                _fail(f"property suite {suite_id} domain {name} has duplicates")
        count = math.prod(len(domain[name]) for name in domain_order)
        if suite["expected_instance_count"] != count:
            _fail(
                f"property suite {suite_id} count mismatch: "
                f"declared {suite['expected_instance_count']}, product {count}"
            )

        for binding_name in ("generator", "input_materializer", "reference_oracle"):
            binding = suite[binding_name]
            algorithm = algorithms.get(binding["algorithm_id"])
            if algorithm is None:
                _fail(
                    f"property suite {suite_id} {binding_name} references "
                    f"unknown algorithm {binding['algorithm_id']}"
                )
            if (
                binding["source_manifest_entry_sha256"]
                != algorithm["entry_sha256"]
            ):
                _fail(
                    f"property suite {suite_id} {binding_name} source hash mismatch"
                )
        input_binding_id = suite["input_materializer"]["input_binding_id"]
        runner_bindings = {
            binding["input_binding_id"]
            for binding in runner["input_bindings"]
        }
        if input_binding_id not in runner_bindings:
            _fail(
                f"property suite {suite_id} input binding is absent from runner"
            )

        names = tuple(domain_order)
        value_arrays = tuple(domain[name] for name in names)
        instance_ids: set[str] = set()
        observed = 0
        for values in itertools.product(*value_arrays):
            assignment = dict(zip(names, values, strict=True))
            digest = _jcs_sha256(
                {"suite_id": suite_id, "assignment": assignment},
                source=f"{suite_id} instance {observed}",
            )
            instance_id = f"sha256:{digest}"
            if instance_id in instance_ids:
                _fail(f"property suite {suite_id} has duplicate instance_id")
            instance_ids.add(instance_id)
            observed += 1
        if observed != count:
            _fail(f"property suite {suite_id} enumeration count mismatch")
        total += observed
    return total


def _load_manifest_chain(
    root: Path,
    schemas: _OfflineSchemas,
    head: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    reverse_chain: list[Mapping[str, Any]] = []
    seen_hashes: set[str] = set()
    current = head
    while True:
        schemas.validate(
            current,
            schema_path="schemas/aegis/v2/evaluation_manifest.v1.schema.json",
            source=(
                MANIFEST_PATH.as_posix()
                if not reverse_chain
                else "parent evaluation manifest"
            ),
        )
        digest = _verify_self_hash(
            current,
            "manifest_sha256",
            source=(
                "evaluation manifest"
                if not reverse_chain
                else "parent evaluation manifest"
            ),
            prefixed=True,
        )
        manifest_hash = f"sha256:{digest}"
        if manifest_hash in seen_hashes:
            _fail(f"evaluation manifest parent cycle: {manifest_hash}")
        seen_hashes.add(manifest_hash)
        reverse_chain.append(current)

        parent_hash = current["parent_manifest_hash"]
        locator = current["parent_manifest_locator"]
        if parent_hash is None:
            if locator is not None:
                _fail("root manifest has an orphan parent locator")
            break
        if locator is None:
            _fail(f"manifest {manifest_hash} has no parent locator")
        if (
            locator["declared_manifest_sha256"] != parent_hash
            or locator["content_addressed_store_key"] != parent_hash
        ):
            _fail(f"manifest {manifest_hash} parent locator hash mismatch")
        parent_digest = parent_hash.removeprefix("sha256:")
        expected_relative = (
            EVALUATION_DIRECTORY
            / "manifests"
            / "sha256"
            / f"{parent_digest}.json"
        ).as_posix()
        if locator["repository_path"] != expected_relative:
            _fail(
                f"manifest {manifest_hash} parent locator is not the frozen "
                f"content-addressed path: {locator['repository_path']!r}"
            )
        raw = _read_repository_utf8_lf_no_bom(
            root,
            locator["repository_path"],
            source=f"manifest {manifest_hash} parent locator",
        )
        if len(raw) != locator["byte_size"]:
            _fail(f"parent manifest byte_size mismatch for {parent_hash}")
        if _sha256(raw) != locator["raw_sha256"]:
            _fail(f"parent manifest raw_sha256 mismatch for {parent_hash}")
        parent = _parse_json_bytes(
            raw,
            source=locator["repository_path"],
        )
        if not isinstance(parent, dict):
            _fail(f"parent manifest root is not an object: {parent_hash}")
        if parent.get("manifest_sha256") != parent_hash:
            _fail(f"parent manifest declared hash mismatch for {parent_hash}")
        current = parent

    chain = list(reversed(reverse_chain))
    _replay_manifest_history(chain)
    return chain


def _replay_manifest_history(
    chain: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], set[str]]:
    if not chain:
        _fail("evaluation manifest history is empty")
    all_cases: dict[str, Mapping[str, Any]] = {}
    active_case_ids: set[str] = set()
    event_ids: set[str] = set()
    previous_hash: str | None = None
    for index, manifest in enumerate(chain):
        manifest_hash = manifest["manifest_sha256"]
        parent_hash = manifest["parent_manifest_hash"]
        if index == 0:
            if parent_hash is not None:
                _fail("manifest history root has a parent")
            if manifest.get("supersession_events"):
                _fail("manifest history root cannot contain supersession events")
        elif parent_hash != previous_hash:
            _fail(
                f"manifest history parent hash mismatch at {manifest_hash}: "
                f"expected {previous_hash}, got {parent_hash}"
            )

        introduced_cases = [
            *manifest.get("cases", []),
            *manifest.get("runner_conformance_cases", []),
        ]
        for case in introduced_cases:
            case_id = case["case_id"]
            if case_id in all_cases:
                _fail(f"duplicate historical case_id: {case_id}")
            all_cases[case_id] = case
            active_case_ids.add(case_id)

        for event in manifest.get("supersession_events", []):
            event_id = event["event_id"]
            if event_id in event_ids:
                _fail(f"duplicate historical supersession event_id: {event_id}")
            event_ids.add(event_id)
            if event["parent_manifest_hash"] != parent_hash:
                _fail(
                    f"supersession event {event_id} parent manifest hash "
                    "mismatch"
                )
            target_id = event["target_case_id"]
            target = all_cases.get(target_id)
            if target is None:
                _fail(
                    f"supersession event {event_id} targets unknown historical "
                    f"case: {target_id}"
                )
            if event["target_case_sha256"] != target["case_sha256"]:
                _fail(
                    f"supersession event {event_id} target case hash mismatch"
                )
            if target_id not in active_case_ids:
                _fail(
                    f"supersession event {event_id} targets an already "
                    f"superseded case: {target_id}"
                )
            replacement_ids = event["replacement_case_ids"]
            if target_id in replacement_ids:
                _fail(
                    f"supersession event {event_id} cannot replace a case "
                    "with itself"
                )
            unknown_replacements = sorted(
                set(replacement_ids) - set(all_cases),
            )
            if unknown_replacements:
                _fail(
                    f"supersession event {event_id} references unknown "
                    f"replacement cases: {unknown_replacements}"
                )
            active_case_ids.remove(target_id)
        previous_hash = manifest_hash
    return all_cases, active_case_ids


def _validate_manifest_relations(
    manifest: Mapping[str, Any],
    *,
    catalog_digest: str,
    algorithms: Mapping[str, Mapping[str, Any]],
    comparator_specs: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], set[str], int]:
    runners = _unique(
        manifest["runner_contracts"],
        source="runner_contract_id",
        key=lambda runner: runner["runner_contract_id"],
    )
    bindings_by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
    for runner_id, runner in runners.items():
        digest = _verify_self_hash(
            runner,
            "runner_contract_id",
            source=f"runner contract {runner_id}",
            prefixed=True,
        )
        if runner_id != f"sha256:{digest}":
            _fail(f"runner contract identity mismatch: {runner_id}")
        mount = runner["fixture_mount"]
        mount_source = mount.get("source")
        if mount_source == "STATIC_CATALOG":
            if (
                mount["catalog_id"] != f"sha256:{catalog_digest}"
                or mount["catalog_sha256"] != catalog_digest
            ):
                _fail(
                    f"runner contract {runner_id} fixture catalog binding "
                    "mismatch"
                )
        elif mount_source == "PROPERTY_INSTANCE_MATERIALIZATION":
            materializer_id = mount["materializer_algorithm_id"]
            materializer = algorithms.get(materializer_id)
            if materializer is None:
                _fail(
                    f"runner contract {runner_id} references unknown "
                    f"materializer {materializer_id}"
                )
            if (
                mount["materializer_source_manifest_entry_sha256"]
                != materializer["entry_sha256"]
            ):
                _fail(
                    f"runner contract {runner_id} materializer source hash "
                    "mismatch"
                )
        else:
            _fail(
                f"runner contract {runner_id} has unknown fixture mount source"
            )
        local_bindings: set[str] = set()
        for binding in runner["input_bindings"]:
            binding_id = binding["input_binding_id"]
            if binding_id in local_bindings:
                _fail(f"duplicate input binding {binding_id} in runner {runner_id}")
            local_bindings.add(binding_id)
            binding_key = (runner_id, binding_id)
            if binding_key in bindings_by_key:
                _fail(
                    f"duplicate runner input binding identity: {binding_key}"
                )
            bindings_by_key[binding_key] = binding
            comparator = comparator_specs.get(binding["comparator"]["comparator_id"])
            if comparator is None:
                _fail(
                    f"runner {runner_id} binding {binding_id} references unknown "
                    "comparator"
                )
            if binding["comparator"]["spec_sha256"] != comparator["spec_sha256"]:
                _fail(
                    f"runner {runner_id} binding {binding_id} comparator "
                    "spec_sha256 mismatch"
                )

    groups = _unique(
        manifest["denominator_groups"],
        source="denominator group_id",
        key=lambda group: group["group_id"],
    )
    for group_id, group in groups.items():
        _verify_self_hash(
            group,
            "group_sha256",
            source=f"denominator group {group_id}",
            prefixed=True,
        )

    regular_cases = manifest["cases"]
    conformance_cases = manifest.get("runner_conformance_cases", [])
    all_cases = [*regular_cases, *conformance_cases]
    case_map = _unique(
        all_cases,
        source="evaluation case_id",
        key=lambda case: case["case_id"],
    )
    for case in regular_cases:
        case_id = case["case_id"]
        _verify_self_hash(
            case,
            "case_sha256",
            source=f"evaluation case {case_id}",
            prefixed=True,
        )
        _verify_self_hash(
            case["expected"],
            "sut_decision_sha256",
            source=f"evaluation case {case_id} expected",
            prefixed=False,
        )
        runner_id = case["runner_contract_id"]
        runner = runners.get(runner_id)
        if runner is None:
            _fail(f"case {case_id} references unknown runner {runner_id}")
        input_value = case["input"]
        if input_value["runner_contract_id"] != runner_id:
            _fail(f"case {case_id} input runner_contract_id mismatch")
        if input_value["case_id"] != case_id:
            _fail(f"case {case_id} input case_id mismatch")
        binding_key = (runner_id, input_value["input_binding_id"])
        resolved_binding = bindings_by_key.get(binding_key)
        if resolved_binding is None:
            _fail(f"case {case_id} references unknown runner input binding")
        comparator = comparator_specs.get(case["oracle"]["comparator_id"])
        if comparator is None:
            _fail(f"case {case_id} references unknown comparator")
        if (
            case["oracle"]["comparator_id"]
            != resolved_binding["comparator"]["comparator_id"]
        ):
            _fail(f"case comparator mismatch for {case_id}")
        if (
            case["oracle"]["trace_normalization"]
            != comparator["trace_normalization"]
        ):
            _fail(f"case trace normalization mismatch for {case_id}")
        expected_mode = (
            "EXACT_SUT_DECISION"
            if comparator["trace_algorithm_entry_id"] is None
            else "EXACT_SUT_DECISION_AND_REFERENCE_TRACE"
        )
        if case["oracle"]["mode"] != expected_mode:
            _fail(f"case comparator mode mismatch for {case_id}")
        if (
            case["oracle"]["expected_sut_decision_sha256"]
            != case["expected"]["sut_decision_sha256"]
        ):
            _fail(f"case {case_id} oracle expected hash mismatch")
        unknown_groups = sorted(set(case["denominator_group_ids"]) - set(groups))
        if unknown_groups:
            _fail(f"case {case_id} references unknown groups: {unknown_groups}")

    for case in conformance_cases:
        case_id = case["case_id"]
        _verify_self_hash(
            case,
            "case_sha256",
            source=f"runner conformance case {case_id}",
            prefixed=True,
        )
        invocation = case["invocation"]
        _verify_self_hash(
            invocation,
            "invocation_jcs_sha256",
            source=f"runner conformance invocation {case_id}",
            prefixed=False,
        )
        if invocation["case_id"] != case_id:
            _fail(
                f"conformance invocation case_id mismatch for {case_id}"
            )
        runner_id = invocation["runner_contract_id"]
        runner = runners.get(runner_id)
        if runner is None:
            _fail(
                f"runner conformance case {case_id} references unknown runner"
            )
        if runner["fixture_mount"].get("source") != "STATIC_CATALOG":
            _fail(
                f"runner conformance case {case_id} must bind a static runner"
            )
        binding_key = (runner_id, invocation["input_binding_id"])
        if binding_key not in bindings_by_key:
            _fail(
                f"runner conformance case {case_id} references unknown "
                "runner input binding"
            )
        variant = invocation["input_variant"]
        _expect_hash(
            variant["candidate_sha256"],
            _jcs_sha256(
                variant["candidate"],
                source=f"runner conformance candidate {case_id}",
            ),
            source=f"runner conformance candidate hash {case_id}",
            prefixed=False,
        )
        unknown_groups = sorted(set(case["denominator_group_ids"]) - set(groups))
        if unknown_groups:
            _fail(
                f"runner conformance case {case_id} references unknown groups: "
                f"{unknown_groups}"
            )

    event_ids: set[str] = set()
    for event in manifest["supersession_events"]:
        event_id = event["event_id"]
        if event_id in event_ids:
            _fail(f"duplicate supersession event_id: {event_id}")
        event_ids.add(event_id)
        _verify_self_hash(
            event,
            "event_sha256",
            source=f"supersession event {event_id}",
            prefixed=True,
        )

    property_count = _validate_property_suites(manifest, runners, algorithms)
    _verify_self_hash(
        manifest,
        "manifest_sha256",
        source="evaluation manifest",
        prefixed=True,
    )
    return runners, set(case_map), property_count


def _validate_freeze_identity_bindings(
    record: Mapping[str, Any],
) -> None:
    producer = record["freeze_producer_identity"]
    review = record["review_anchor"]
    authority_locator = record["authority_anchor"]["authority_locator"]
    event = record["authority_anchor"]["anchor_event_preimage"]
    locator_fields = (
        "capture_source",
        "authority_source_id",
        "authority_policy_id",
        "authority_event_id",
        "authority_event_sequence",
        "authority_committed_at_utc",
        "codex_cli_version",
        "codex_app_server_protocol_semantic_sha256",
        "reviewer_task_path",
        "parent_thread_id",
        "parent_spawn_tool_call_id",
        "parent_delivery_tool_call_id",
        "reviewer_thread_id",
        "reviewer_session_id",
        "reviewer_turn_id",
        "reviewer_item_id",
        "reviewer_turn_started_at_unix_seconds",
        "reviewer_turn_completed_at_unix_seconds",
        "reviewer_item_started_at_unix_ms",
        "reviewer_item_completed_at_unix_ms",
        "reviewer_turn_status",
        "reviewer_item_type",
        "reviewer_item_phase",
        "delivery_kind",
    )
    review_locator = {field: review[field] for field in locator_fields}
    authority_projection = {
        field: authority_locator[field] for field in locator_fields
    }
    if review_locator != authority_projection:
        _fail("freeze review/authority locator identity mismatch")
    if event["authority_locator"] != authority_locator:
        _fail("freeze authority/final event locator mismatch")
    if review["parent_thread_id"] != producer["thread_id"]:
        _fail("freeze reviewer is not a child of the persisted producer")
    if (
        review["reviewer_thread_id"] == producer["thread_id"]
        or (
            review["reviewer_thread_id"],
            review["reviewer_session_id"],
        )
        == (
            producer["thread_id"],
            producer["session_id"],
        )
    ):
        _fail("freeze reviewer is not independent from the persisted producer")

    expected_event_bindings = {
        "freeze_root_id": record["freeze_root_id"],
        "code_absence_proof_id": record["code_absence_proof"][
            "code_absence_proof_id"
        ],
        "review_artifact": review["review_artifact"],
        "verdict": review["review_outcome"],
        "open_blocker_ids": review["open_blocker_ids"],
        "reviewed_at_utc": review["reviewed_at_utc"],
    }
    observed_event_bindings = {
        field: event[field] for field in expected_event_bindings
    }
    if observed_event_bindings != expected_event_bindings:
        _fail("freeze final event binding mismatch")
    if (
        review["reviewed_freeze_root_id"] != record["freeze_root_id"]
        or review["reviewed_code_absence_proof_id"]
        != record["code_absence_proof"]["code_absence_proof_id"]
    ):
        _fail("freeze review anchor binding mismatch")

    for entry in record["code_absence_proof"]["outside_domain_entries"]:
        if (
            entry["reviewer_thread_id"] == producer["thread_id"]
            or (
                entry["reviewer_thread_id"],
                entry["reviewer_session_id"],
            )
            == (
                producer["thread_id"],
                producer["session_id"],
            )
        ):
            _fail(
                "outside-domain disposition reviewer is not independent "
                f"for {entry['repository_relative_path']}"
            )


def _validate_freeze_repository_domain(
    root: Path,
    record: Mapping[str, Any],
) -> None:
    required = _derive_required_phase0a_repository_inputs(root)
    leaves = record.get("freeze_inputs")
    if not isinstance(leaves, list):
        _fail("freeze inputs must be a list")
    repository_rows: list[tuple[str, tuple[Any, Any]]] = []
    for leaf in leaves:
        if not isinstance(leaf, Mapping):
            _fail("freeze input must be an object")
        locator = leaf.get("locator")
        if not isinstance(locator, Mapping):
            _fail("freeze input locator must be an object")
        if locator.get("kind") != "REPOSITORY":
            continue
        path = locator.get("repository_path")
        if not isinstance(path, str):
            _fail("repository freeze input path must be a string")
        repository_rows.append(
            (
                path,
                (leaf.get("artifact_kind"), leaf.get("byte_domain")),
            )
        )
    paths = [path for path, _ in repository_rows]
    if len(paths) != len(set(paths)):
        _fail("repository freeze inputs contain duplicate paths")
    observed = dict(repository_rows)
    missing = sorted(set(required) - set(observed))
    extra = sorted(set(observed) - set(required))
    mismatched = sorted(
        path
        for path in set(required) & set(observed)
        if observed[path] != required[path]
    )
    if missing or extra or mismatched:
        _fail(
            "normative Phase 0A repository domain mismatch in freeze record; "
            f"missing={missing}, extra={extra}, kind_or_domain={mismatched}"
        )
    proof = record.get("code_absence_proof")
    if not isinstance(proof, Mapping):
        _fail("freeze code_absence_proof must be an object")
    allowed = proof.get("allowed_phase0a_file_domain")
    if allowed != list(required):
        _fail(
            "freeze allowed Phase 0A domain does not equal the independently "
            "derived normative repository domain"
        )


def _validate_freeze_record_relations(
    root: Path,
    schemas: _OfflineSchemas,
    record: Mapping[str, Any],
) -> None:
    schemas.validate(
        record,
        schema_path="schemas/aegis/v2/phase0_freeze_record.v1.schema.json",
        source="Phase0FreezeRecord.v1",
    )
    _validate_freeze_repository_domain(root, record)
    _validate_freeze_identity_bindings(record)
    leaves = record["freeze_inputs"]
    logical_paths = [leaf["logical_path"] for leaf in leaves]
    if logical_paths != sorted(logical_paths) or len(set(logical_paths)) != len(
        logical_paths
    ):
        _fail("freeze inputs must have unique Unicode-code-point sorted paths")
    for leaf in leaves:
        _verify_self_hash(
            leaf,
            "leaf_sha256",
            source=f"freeze leaf {leaf['logical_path']}",
            prefixed=False,
        )
        locator = leaf["locator"]
        if locator["kind"] == "REPOSITORY":
            raw = _read_repository_bytes(
                root,
                locator["repository_path"],
                source=f"freeze leaf {leaf['logical_path']} locator",
            )
            if len(raw) != leaf["byte_size"]:
                _fail(f"freeze leaf byte_size mismatch: {leaf['logical_path']}")
            if _sha256(raw) != leaf["raw_sha256"]:
                _fail(f"freeze leaf raw_sha256 mismatch: {leaf['logical_path']}")
            if leaf["byte_domain"] in {"JCS_RFC8785", "UTF8_LF_NO_BOM"}:
                _read_repository_utf8_lf_no_bom(
                    root,
                    locator["repository_path"],
                    source=f"freeze leaf {leaf['logical_path']} text",
                )
            if leaf["byte_domain"] == "JCS_RFC8785":
                parsed = _load_repository_json(
                    root,
                    locator["repository_path"],
                    source=f"freeze leaf {leaf['logical_path']} JSON",
                )
                if (
                    leaf["semantic_jcs_sha256"]
                    != _jcs_sha256(parsed, source=leaf["logical_path"])
                ):
                    _fail(
                        f"freeze leaf semantic hash mismatch: "
                        f"{leaf['logical_path']}"
                    )
            elif leaf["semantic_jcs_sha256"] is not None:
                _fail(
                    f"non-JSON freeze leaf has semantic hash: "
                    f"{leaf['logical_path']}"
                )
    root_preimage = [
        {
            "logical_path": leaf["logical_path"],
            "leaf_sha256": leaf["leaf_sha256"],
        }
        for leaf in leaves
    ]
    _expect_hash(
        record["freeze_root_id"],
        _jcs_sha256(root_preimage, source="freeze root"),
        source="freeze_root_id",
        prefixed=True,
    )
    proof = record["code_absence_proof"]
    for entry in proof["worktree_inventory"]:
        _verify_self_hash(
            entry,
            "inventory_entry_id",
            source=f"worktree inventory {entry['repository_relative_path']}",
            prefixed=True,
        )
    _expect_hash(
        proof["worktree_inventory_id"],
        _jcs_sha256(
            proof["worktree_inventory"],
            source="worktree inventory",
        ),
        source="worktree_inventory_id",
        prefixed=True,
    )
    _verify_self_hash(
        proof,
        "code_absence_proof_id",
        source="code absence proof",
        prefixed=True,
    )
    if (
        record["review_anchor"]["reviewed_freeze_root_id"]
        != record["freeze_root_id"]
        or record["review_anchor"]["reviewed_code_absence_proof_id"]
        != proof["code_absence_proof_id"]
    ):
        _fail("freeze review anchor does not bind root and code-absence proof")
    authority = record["authority_anchor"]
    try:
        raw_event = base64.b64decode(
            authority["anchor_event_raw_base64"],
            validate=True,
        )
    except (ValueError, TypeError) as error:
        raise ValidationError("invalid freeze authority event base64") from error
    if len(raw_event) != authority["anchor_event_byte_size"]:
        _fail("freeze authority event byte_size mismatch")
    if _sha256(raw_event) != authority["anchor_event_raw_sha256"]:
        _fail("freeze authority event raw_sha256 mismatch")
    event = _parse_json_bytes(raw_event, source="freeze authority event")
    if _jcs(event, source="freeze authority event") != raw_event:
        _fail("freeze authority event must be exact JCS bytes")
    _verify_self_hash(
        record,
        "freeze_record_id",
        source="Phase0 freeze record",
        prefixed=True,
    )


def validate_repository(root: Path | str) -> dict[str, Any]:
    """Validate the frozen Phase 0A corpus without executing the SUT."""

    repository_root = Path(root).resolve(strict=True)
    schemas = _OfflineSchemas(repository_root)
    schema_bundle = _validate_schema_bundle(repository_root, schemas)
    lock = _validate_lock(repository_root)

    manifest = _load_repository_json(
        repository_root,
        MANIFEST_PATH.as_posix(),
        source=MANIFEST_PATH.as_posix(),
    )
    schemas.validate(
        manifest,
        schema_path="schemas/aegis/v2/evaluation_manifest.v1.schema.json",
        source=MANIFEST_PATH.as_posix(),
    )
    manifest_chain = _load_manifest_chain(
        repository_root,
        schemas,
        manifest,
    )
    historical_cases, active_case_ids = _replay_manifest_history(
        manifest_chain,
    )
    source_manifest, algorithms, comparator_specs = _validate_reference_sources(
        repository_root,
        schemas,
        manifest,
        schema_bundle=schema_bundle,
        lock=lock,
    )
    catalog, fixtures = _validate_fixture_catalog(
        repository_root,
        schemas,
        manifest,
    )
    runners, case_ids, property_count = _validate_manifest_relations(
        manifest,
        catalog_digest=catalog["catalog_sha256"],
        algorithms=algorithms,
        comparator_specs=comparator_specs,
    )
    risk = _validate_risk_register(
        repository_root,
        schemas,
        manifest,
        set(historical_cases),
    )

    freeze = manifest["freeze"]
    if freeze.get("schema_version") == "Phase0FreezeRecord.v1":
        _validate_freeze_record_relations(
            repository_root,
            schemas,
            freeze,
        )
        _fail(
            "AUTHORITY_UNVERIFIED: the offline validator has no concrete "
            "independent provider adapter or self-contained verifiable "
            "external proof; a structurally self-consistent FROZEN record "
            "cannot produce valid=true"
        )

    return {
        "valid": False,
        "structural_valid": True,
        "phase_complete": False,
        "validation_scope": (
            "PHASE_0A_STATIC_STRUCTURE_AND_FREEZE_AUTHORITY"
        ),
        "blockers": [
            "AUTHORITY_UNVERIFIED",
            "PHASE_0A_PENDING_FREEZE_EVIDENCE",
        ],
        "errors": [],
        "checks": {
            "schema_count": len(schemas.by_path),
            "runner_count": len(runners),
            "case_count": len(historical_cases),
            "head_delta_case_count": len(case_ids),
            "effective_active_case_count": len(active_case_ids),
            "manifest_chain_length": len(manifest_chain),
            "fixture_count": len(fixtures),
            "risk_count": len(risk["entries"]),
            "reference_algorithm_count": len(algorithms),
            "comparator_spec_count": len(comparator_specs),
            "property_instance_count": property_count,
            "freeze_state": freeze.get(
                "freeze_state",
                freeze.get("state", "UNKNOWN"),
            ),
            "authority_event_verified": False,
            "phase_gate_state": "BLOCKED_PENDING_FREEZE_EVIDENCE",
            "sut_executed": False,
            "network_used": False,
        },
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only, offline Aegis v2 Phase 0A validator.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root. Defaults to the root containing this validator.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_args(argv)
    try:
        report = validate_repository(arguments.repo_root)
    except ValidationError as error:
        authority_unverified = str(error).startswith(
            "AUTHORITY_UNVERIFIED:"
        )
        report = {
            "valid": False,
            "structural_valid": authority_unverified,
            "phase_complete": False,
            "validation_scope": (
                "PHASE_0A_STATIC_STRUCTURE_AND_FREEZE_AUTHORITY"
            ),
            "blockers": (
                ["AUTHORITY_UNVERIFIED"]
                if authority_unverified
                else []
            ),
            "errors": [str(error)],
            "checks": {
                "authority_event_verified": False,
                "sut_executed": False,
                "network_used": False,
            },
        }
        sys.stdout.buffer.write(_jcs(report, source="validation failure report") + b"\n")
        return 1
    sys.stdout.buffer.write(_jcs(report, source="validation report") + b"\n")
    return 0 if report.get("valid") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
