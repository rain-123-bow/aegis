from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn

import jsonschema
import rfc8785


SCHEMA_DIRECTORY = Path("schemas/aegis/v2")
BUNDLE_PATH = SCHEMA_DIRECTORY / "schema_bundle.v1.json"
SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
ENTRY_PREIMAGE = "RFC8785_JCS_UTF8"
STATIC_BUNDLE_FIELDS = {
    "schema_version": "SchemaBundle.v1",
    "bundle_id": "AEGIS-V2-SCHEMA-BUNDLE-ROOT",
    "hash_contract": {
        "algorithm": "SHA-256",
        "canonicalization": "RFC8785-JCS",
        "scope": "WHOLE_BUNDLE_WITH_BUNDLE_SHA256_OMITTED",
        "schema_entry_byte_size_preimage": ENTRY_PREIMAGE,
        "schema_entry_sha256_preimage": ENTRY_PREIMAGE,
    },
    "resolution_policy": {
        "all_schema_ids_preloaded_locally": True,
        "network_resolution_allowed": False,
        "unknown_schema_id_action": "REJECT",
    },
    "codex_protocol_contract": {
        "codex_cli_version": "0.145.0",
        "generated_bundle_jcs_sha256": (
            "sha256:"
            "1bc09dedc506075562d4d49b702ecab6d947dd5a8c2a9014a5cde592a0938efb"
        ),
        "raw_bundle_hash_is_compatibility_key": False,
    },
}
BUNDLE_MEMBERS = frozenset(
    (*STATIC_BUNDLE_FIELDS, "schemas", "bundle_sha256")
)


class BundleBuildError(RuntimeError):
    """A deterministic, fail-closed schema-bundle build failure."""


def _fail(message: str) -> NoReturn:
    raise BundleBuildError(message)


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


def _load_strict_json(path: Path) -> Any:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise BundleBuildError(f"cannot read {path}: {error}") from error
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail(f"UTF-8 BOM is forbidden: {path}")
    if b"\r" in raw:
        _fail(f"CR/CRLF is forbidden: {path}")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise BundleBuildError(f"invalid UTF-8 in {path}: {error}") from error
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_members,
            parse_constant=_reject_nonfinite_constant,
        )
    except BundleBuildError:
        raise
    except (json.JSONDecodeError, ValueError) as error:
        raise BundleBuildError(f"invalid JSON in {path}: {error}") from error


def _jcs(value: Any, *, source: str) -> bytes:
    try:
        return rfc8785.dumps(value)
    except (TypeError, ValueError, rfc8785.CanonicalizationError) as error:
        raise BundleBuildError(
            f"RFC 8785 canonicalization failed for {source}: {error}"
        ) from error


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _validate_schema(
    schema: Any,
    *,
    path: Path,
    seen_ids: dict[str, Path],
) -> dict[str, Any]:
    if not isinstance(schema, dict):
        _fail(f"schema root must be an object: {path}")
    if schema.get("$schema") != SCHEMA_DIALECT:
        _fail(f"schema must declare Draft 2020-12: {path}")
    schema_id = schema.get("$id")
    if not isinstance(schema_id, str) or not schema_id:
        _fail(f"schema has no nonempty $id: {path}")
    prior = seen_ids.get(schema_id)
    if prior is not None:
        _fail(f"duplicate schema $id {schema_id!r}: {prior} and {path}")
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except jsonschema.SchemaError as error:
        raise BundleBuildError(
            f"Draft 2020-12 metaschema rejected {path}: {error.message}"
        ) from error
    seen_ids[schema_id] = path
    return schema


def _validate_static_bundle_contract(template: Mapping[str, Any]) -> None:
    members = set(template)
    if members != BUNDLE_MEMBERS:
        missing = sorted(BUNDLE_MEMBERS - members)
        extra = sorted(repr(member) for member in members - BUNDLE_MEMBERS)
        _fail(
            "schema bundle top-level members mismatch: "
            f"missing={missing}; extra={extra}"
        )
    for field, expected in STATIC_BUNDLE_FIELDS.items():
        if _jcs(
            template[field],
            source=f"schema bundle static field {field}",
        ) != _jcs(
            expected,
            source=f"authoritative schema bundle static field {field}",
        ):
            _fail(f"schema bundle static field mismatch: {field}")
    if not isinstance(template["schemas"], list):
        _fail("schema bundle schemas must be an array")
    bundle_sha256 = template["bundle_sha256"]
    if (
        not isinstance(bundle_sha256, str)
        or not bundle_sha256.startswith("sha256:")
        or len(bundle_sha256) != len("sha256:") + 64
        or any(
            character not in "0123456789abcdef"
            for character in bundle_sha256[len("sha256:") :]
        )
    ):
        _fail("schema bundle bundle_sha256 is malformed")


def render_schema_bundle(
    *,
    repository_root: Path | str,
    template: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the complete deterministic bundle without writing files."""

    root = Path(repository_root).resolve(strict=True)
    schema_directory = root / SCHEMA_DIRECTORY
    if not schema_directory.is_dir():
        _fail(f"schema directory missing: {schema_directory}")
    if not isinstance(template, Mapping):
        _fail("schema bundle template must be an object")
    _validate_static_bundle_contract(template)

    paths = sorted(
        schema_directory.glob("*.schema.json"),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    if not paths:
        _fail(f"no versioned schemas found in {schema_directory}")

    seen_ids: dict[str, Path] = {}
    entries: list[dict[str, Any]] = []
    for path in paths:
        schema = _validate_schema(
            _load_strict_json(path),
            path=path,
            seen_ids=seen_ids,
        )
        canonical = _jcs(
            schema,
            source=path.relative_to(root).as_posix(),
        )
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "byte_size": len(canonical),
                "sha256": f"sha256:{_sha256(canonical)}",
            }
        )

    result = copy.deepcopy(STATIC_BUNDLE_FIELDS)
    result["schemas"] = entries
    result["bundle_sha256"] = (
        "sha256:"
        + _sha256(_jcs(result, source="schema bundle self-hash preimage"))
    )
    return result


def bundle_matches_expected(
    *,
    observed: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> bool:
    """Compare the complete semantic values, including the self-hash."""

    return _jcs(observed, source="observed bundle") == _jcs(
        expected,
        source="expected bundle",
    )


def _write_atomic(path: Path, value: Mapping[str, Any]) -> None:
    if path.is_symlink():
        _fail(f"refusing to replace symlink: {path}")
    raw = _jcs(value, source=str(path)) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        finally:
            raise


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministically rebuild or check the complete Aegis v2 "
            "schema bundle."
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
    root = arguments.repo_root.resolve(strict=True)
    path = root / BUNDLE_PATH
    try:
        observed = _load_strict_json(path)
        if not isinstance(observed, dict):
            _fail("schema bundle root must be an object")
        expected = render_schema_bundle(
            repository_root=root,
            template=observed,
        )
        if arguments.write:
            _write_atomic(path, expected)
            state = "WRITTEN"
            exit_code = 0
        elif bundle_matches_expected(
            observed=observed,
            expected=expected,
        ):
            state = "CURRENT"
            exit_code = 0
        else:
            state = "STALE"
            exit_code = 1
        report = {
            "schema_version": "SchemaBundleBuildReport.v1",
            "state": state,
            "schema_count": len(expected["schemas"]),
            "bundle_sha256": expected["bundle_sha256"],
        }
    except BundleBuildError as error:
        report = {
            "schema_version": "SchemaBundleBuildReport.v1",
            "state": "INVALID",
            "errors": [str(error)],
        }
        exit_code = 1
    sys.stdout.buffer.write(_jcs(report, source="build report") + b"\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
