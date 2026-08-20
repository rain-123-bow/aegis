"""Fail-closed Phase 0A freeze candidate and structural-record construction.

This module is evaluation infrastructure, not an Aegis v2 product
implementation.  It deliberately cannot create or externally verify a reviewer
PASS event.  Public finalization and verification remain unavailable until a
concrete independently verifiable authority provider is implemented.  The
private reader seam exists only to test structural record logic and establishes
no production provenance.
"""

from __future__ import annotations

import ast
import base64
import copy
import datetime as _datetime
import hashlib
import hmac
import json
import os
import re
import stat
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Sequence

import rfc8785


class FreezeError(ValueError):
    """The requested freeze cannot be proved from the supplied evidence."""


class ProhibitedImplementationError(FreezeError):
    """Executable Aegis v2 implementation content exists before the freeze."""


ExternalAcquisitionVerifier = Callable[[Mapping[str, Any], bytes], bool]
AuthorityEventReader = Callable[[Mapping[str, Any]], bytes]


_TEST_ONLY_FREEZE_STATE = "TEST_ONLY_STRUCTURAL_RECORD"
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CONTENT_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_OBJECT_ID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_UUID_V7_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_UTC_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z$"
)
_OPAQUE_ID_RE = re.compile(r"^[A-Za-z0-9_./:@-]{1,256}$")
_REPOSITORY_PATH_RE = re.compile(
    r"^(?![A-Za-z]:)(?!/)(?!.*(?:^|/)\.{1,2}(?:/|$))"
    r"(?!.*//)[^\\:\r\n]+$"
)
_LOGICAL_PATH_RE = re.compile(r"^(?:repo|external):/[^\r\n]+$")
_WINDOWS_DRIVE_ABSOLUTE_RE = re.compile(
    r'^[A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]+$'
)
_WINDOWS_UNC_ABSOLUTE_RE = re.compile(
    r'^\\\\[^\\/:*?"<>|\r\n]+\\[^\\/:*?"<>|\r\n]+'
    r'(?:\\[^\\/:*?"<>|\r\n]+)*$'
)
_GLOB_CHARACTERS = frozenset("*?[]{}")

_ARTIFACT_KINDS = frozenset(
    {
        "NORMATIVE_CONTRACT",
        "ARCHITECTURE_DECISION",
        "REQUIREMENT_DESIGN",
        "REVIEWED_IMPLEMENTATION_PLAN",
        "STATIC_CAPABILITY_EVIDENCE",
        "VERSIONED_SCHEMA",
        "EVALUATION_MANIFEST",
        "FIXTURE_CATALOG",
        "EVALUATION_FIXTURE",
        "EXCLUSION_RISK_REGISTER",
        "ATTRIBUTE_POLICY",
        "PROJECT_METADATA",
        "PLATFORM_DEPENDENCY_LOCK",
        "EVALUATION_HARNESS",
        "EVALUATION_REFERENCE_SOURCE",
        "EVALUATION_REFERENCE_SOURCE_MANIFEST",
        "COMPARATOR_SPEC",
    }
)
_BYTE_DOMAINS = frozenset(
    {"GIT_BLOB_BYTES", "UTF8_LF_NO_BOM", "JCS_RFC8785"}
)
_JCS_ARTIFACT_KINDS = frozenset(
    {
        "VERSIONED_SCHEMA",
        "EVALUATION_MANIFEST",
        "FIXTURE_CATALOG",
        "EXCLUSION_RISK_REGISTER",
        "EVALUATION_REFERENCE_SOURCE_MANIFEST",
        "COMPARATOR_SPEC",
    }
)
_UTF8_ARTIFACT_KINDS = frozenset(
    {
        "NORMATIVE_CONTRACT",
        "ARCHITECTURE_DECISION",
        "REQUIREMENT_DESIGN",
        "REVIEWED_IMPLEMENTATION_PLAN",
        "STATIC_CAPABILITY_EVIDENCE",
    }
)
_EXACT_TEXT_ARTIFACT_KINDS = frozenset(
    {
        "ATTRIBUTE_POLICY",
        "PROJECT_METADATA",
        "PLATFORM_DEPENDENCY_LOCK",
        "EVALUATION_HARNESS",
        "EVALUATION_REFERENCE_SOURCE",
    }
)
_GIT_BLOB_ARTIFACT_KINDS = frozenset(
    {
        "EVALUATION_FIXTURE",
        *_EXACT_TEXT_ARTIFACT_KINDS,
    }
)
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
_PROHIBITED_CLASSIFIERS = [
    "AEGIS_V2_KERNEL",
    "RELAY_EXECUTOR",
    "LIVE_CAPABILITY_PROBE",
    "EQUIVALENT_EXECUTABLE_IMPLEMENTATION",
]
_EXECUTABLE_SUFFIXES = frozenset(
    {
        ".py",
        ".pyw",
        ".js",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".sh",
        ".bash",
        ".ps1",
        ".go",
        ".rs",
        ".java",
        ".c",
        ".cc",
        ".cpp",
        ".h",
        ".hpp",
    }
)

_FREEZE_INPUT_SPEC_KEYS = {
    "logical_path",
    "locator",
    "artifact_kind",
    "byte_domain",
}
_FREEZE_INPUT_KEYS = _FREEZE_INPUT_SPEC_KEYS | {
    "byte_size",
    "raw_sha256",
    "semantic_jcs_sha256",
    "leaf_sha256",
}
_PRODUCER_IDENTITY_KEYS = {"thread_id", "session_id", "turn_id"}
_DISPOSITION_SPEC_KEYS = {
    "disposition",
    "executable_v2_classification",
    "rationale",
    "reviewer_thread_id",
    "reviewer_session_id",
    "reviewer_turn_id",
    "disposition_artifact_locator",
}
_OUTSIDE_DOMAIN_KEYS = {
    "repository_relative_path",
    "inventory_entry_id",
    *_DISPOSITION_SPEC_KEYS,
    "disposition_artifact_byte_size",
    "disposition_artifact_sha256",
}
_FROZEN_BYTES_KEYS = {
    "source_kind",
    "byte_size",
    "raw_sha256",
    "git_blob_id",
    "snapshot_locator",
    "acquisition_event_id",
}
_INVENTORY_ENTRY_KEYS = {
    "inventory_entry_id",
    "repository_relative_path",
    "entry_kind",
    "base_bytes",
    "worktree_bytes",
}
_TRACKED_CAPTURE_KEYS = {
    "argv",
    "working_directory",
    "stdout_encoding",
    "raw_stdout_base64",
    "stdout_byte_size",
    "stdout_sha256",
    "required_exit_code",
    "stderr_byte_size",
    "stderr_sha256",
}
_CODE_ABSENCE_KEYS = {
    "schema_version",
    "code_absence_proof_id",
    "canonicalization",
    "freeze_base_commit",
    "tracked_tree_capture",
    "worktree_inventory_id",
    "worktree_inventory",
    "tracked_entry_count",
    "nonignored_untracked_entry_count",
    "allowed_phase0a_file_domain",
    "outside_domain_entries",
    "prohibited_implementation_classifiers",
    "base_tree_prohibited_matches",
    "worktree_prohibited_matches",
    "proof_event_id",
    "proven_at_utc",
}
_CANDIDATE_KEYS = {
    "schema_version",
    "candidate_id",
    "freeze_state",
    "canonicalization",
    "freeze_base_commit",
    "freeze_base_tree",
    "freeze_time_utc",
    "freeze_inputs",
    "freeze_root_id",
    "code_absence_proof",
    "freeze_producer_identity",
}
_AUTHORITY_LOCATOR_KEYS = {
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
}
_REVIEW_ARTIFACT_KEYS = {
    "logical_path",
    "locator",
    "byte_size",
    "raw_sha256",
}
_FINAL_EVENT_KEYS = {
    "schema_version",
    "authority_locator",
    "freeze_root_id",
    "code_absence_proof_id",
    "review_artifact",
    "verdict",
    "open_blocker_ids",
    "reviewed_at_utc",
}
_REVIEW_ANCHOR_KEYS = {
    "review_outcome",
    "open_blocker_ids",
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
    "review_artifact",
    "reviewed_freeze_root_id",
    "reviewed_code_absence_proof_id",
    "reviewed_at_utc",
}
_AUTHORITY_ANCHOR_KEYS = {
    "authority",
    "authority_locator",
    "anchor_event_encoding",
    "anchor_event_preimage",
    "anchor_event_raw_base64",
    "anchor_event_byte_size",
    "anchor_event_raw_sha256",
    "recorded_at_utc",
}
_IMPLEMENTATION_ORDER = {
    "policy": "FIRST_IMPLEMENTATION_COMMIT_AFTER_ANCHOR",
    "required_ancestry": (
        "FIRST_IMPLEMENTATION_COMMIT_DESCENDS_FROM_FREEZE_BASE_COMMIT"
    ),
    "required_freeze_root_preservation": True,
}
_FREEZE_RECORD_KEYS = {
    "schema_version",
    "freeze_record_id",
    "freeze_state",
    "canonicalization",
    "freeze_base_commit",
    "freeze_base_tree",
    "freeze_time_utc",
    "freeze_inputs",
    "freeze_root_id",
    "code_absence_proof",
    "freeze_producer_identity",
    "review_anchor",
    "authority_anchor",
    "implementation_order_constraint",
}


def _fail(message: str) -> None:
    raise FreezeError(message)


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    context: str,
) -> None:
    if not isinstance(value, Mapping):
        _fail(f"{context} must be an object")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        _fail(f"{context} keys mismatch; missing={missing}, extra={extra}")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _jcs(value: Any, context: str) -> bytes:
    try:
        return rfc8785.dumps(value)
    except Exception as error:
        raise FreezeError(f"{context} is not RFC 8785 canonicalizable: {error}") from error


def _content_id(value: Any, context: str) -> str:
    return "sha256:" + _sha256(_jcs(value, context))


def _self_omission_content_id(
    value: Mapping[str, Any],
    identity_field: str,
    context: str,
) -> str:
    preimage = dict(value)
    preimage.pop(identity_field, None)
    return _content_id(preimage, context)


def _object_pairs_without_duplicates(
    pairs: Iterable[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FreezeError(f"duplicate JSON member rejected: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise FreezeError(f"non-finite JSON number rejected: {value}")


def parse_json_no_duplicates(raw: bytes, *, context: str) -> Any:
    """Parse strict UTF-8 JSON while rejecting BOM, CR, duplicates and NaN."""

    _require_utf8_lf_no_bom(raw, context)
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_object_pairs_without_duplicates,
            parse_constant=_reject_json_constant,
        )
    except FreezeError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FreezeError(f"{context} is not strict duplicate-free JSON: {error}") from error


def _require_utf8_lf_no_bom(raw: bytes, context: str) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail(f"{context} has a forbidden UTF-8 BOM")
    if b"\r" in raw:
        _fail(f"{context} is not LF-only")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FreezeError(f"{context} is not UTF-8: {error}") from error


def _validate_sha256(value: Any, context: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(f"{context} must be a lowercase SHA-256 digest")
    return value


def _validate_content_id(value: Any, context: str) -> str:
    if not isinstance(value, str) or _CONTENT_ID_RE.fullmatch(value) is None:
        _fail(f"{context} must be a sha256: content ID")
    return value


def _validate_git_object_id(value: Any, context: str) -> str:
    if not isinstance(value, str) or _GIT_OBJECT_ID_RE.fullmatch(value) is None:
        _fail(f"{context} must be a Git object ID")
    return value


def _validate_uuid_v7(value: Any, context: str) -> str:
    if not isinstance(value, str) or _UUID_V7_RE.fullmatch(value) is None:
        _fail(f"{context} must be a canonical lowercase UUIDv7")
    return value


def _parse_utc(value: Any, context: str) -> _datetime.datetime:
    if not isinstance(value, str) or _UTC_RE.fullmatch(value) is None:
        _fail(f"{context} must be an RFC 3339 UTC timestamp ending in Z")
    try:
        parsed = _datetime.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise FreezeError(f"{context} is not a valid UTC timestamp") from error
    if parsed.tzinfo != _datetime.timezone.utc:
        _fail(f"{context} must use UTC")
    return parsed


def _validate_opaque_id(value: Any, context: str) -> str:
    if not isinstance(value, str) or _OPAQUE_ID_RE.fullmatch(value) is None:
        _fail(f"{context} is not a valid opaque platform ID")
    return value


def _validate_repository_path(value: Any, context: str) -> str:
    if not isinstance(value, str) or _REPOSITORY_PATH_RE.fullmatch(value) is None:
        _fail(f"{context} is not a schema-valid repository-relative path")
    parts = PurePosixPath(value).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        _fail(f"{context} is not a normalized repository-relative path")
    if parts[0].casefold() == ".git":
        _fail(f"{context} may not address Git administrative data")
    return value


def _validate_explicit_repository_path(value: Any, context: str) -> str:
    path = _validate_repository_path(value, context)
    if any(character in path for character in _GLOB_CHARACTERS):
        _fail(f"{context} contains a forbidden glob metacharacter")
    return path


def _validate_logical_path(value: Any, context: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 4096
        or _LOGICAL_PATH_RE.fullmatch(value) is None
    ):
        _fail(f"{context} is not a valid freeze logical path")
    return value


def _validate_no_casefold_collisions(values: Sequence[str], context: str) -> None:
    seen: dict[str, str] = {}
    for value in values:
        key = value.casefold()
        prior = seen.get(key)
        if prior is not None and prior != value:
            _fail(f"{context} has a case-fold collision: {prior!r}, {value!r}")
        seen[key] = value


def _validate_producer_identity(value: Mapping[str, Any]) -> dict[str, str]:
    _require_exact_keys(value, _PRODUCER_IDENTITY_KEYS, "freeze producer identity")
    return {
        key: _validate_opaque_id(value[key], f"freeze producer {key}")
        for key in ("thread_id", "session_id", "turn_id")
    }


def _reviewer_agent_identity(value: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(value["reviewer_thread_id"]),
        str(value["reviewer_session_id"]),
    )


def _producer_agent_identity(value: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(value["thread_id"]),
        str(value["session_id"]),
    )


def _require_independent_reviewer(
    reviewer: Mapping[str, Any],
    producer: Mapping[str, Any],
    context: str,
) -> None:
    # A Codex agent identity is thread_id + session_id.  turn_id locates a
    # delivery within that same agent and cannot manufacture independence.  A
    # reviewer reusing the producer thread is also rejected even if a new
    # session exists: role separation requires a separately visible subagent.
    if (
        _reviewer_agent_identity(reviewer) == _producer_agent_identity(producer)
        or str(reviewer["reviewer_thread_id"]) == str(producer["thread_id"])
    ):
        _fail(f"{context} must be independent from the freeze producer")


def _run_git(
    repo_root: Path,
    arguments: Sequence[str],
    context: str,
    *,
    accepted_exit_codes: frozenset[int] = frozenset({0}),
) -> subprocess.CompletedProcess[bytes]:
    argv = ["git", *arguments]
    try:
        result = subprocess.run(
            argv,
            cwd=repo_root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            check=False,
        )
    except OSError as error:
        raise FreezeError(f"{context} could not execute direct argv {argv!r}: {error}") from error
    if result.returncode not in accepted_exit_codes:
        stderr = result.stderr.decode("utf-8", "replace")
        _fail(
            f"{context} direct argv failed with exit {result.returncode}: "
            f"{stderr!r}"
        )
    return result


def _require_repository_root(repo_root: Path | str) -> Path:
    root = Path(repo_root).resolve(strict=True)
    if not root.is_dir():
        _fail("repo_root must be a directory")
    result = _run_git(root, ["rev-parse", "--show-toplevel"], "repository root")
    if result.stderr:
        _fail("git rev-parse --show-toplevel emitted stderr")
    try:
        discovered = Path(result.stdout.decode("utf-8").strip()).resolve(strict=True)
    except (UnicodeDecodeError, OSError) as error:
        raise FreezeError(f"could not resolve Git repository root: {error}") from error
    try:
        same = root.samefile(discovered)
    except OSError as error:
        raise FreezeError(f"could not compare repository roots: {error}") from error
    if not same:
        _fail(f"repo_root must be the Git top-level directory, got {root}")
    return root


def _path_has_link_or_junction(root: Path, relative_path: str) -> bool:
    current = root
    for part in PurePosixPath(relative_path).parts:
        current = current / part
        try:
            metadata = os.lstat(current)
            if (
                stat.S_ISLNK(metadata.st_mode)
                or bool(
                    getattr(metadata, "st_file_attributes", 0)
                    & getattr(
                        stat,
                        "FILE_ATTRIBUTE_REPARSE_POINT",
                        0x400,
                    )
                )
                or (
                    hasattr(os.path, "isjunction")
                    and os.path.isjunction(current)
                )
            ):
                return True
        except OSError as error:
            raise FreezeError(f"cannot inspect path boundary {current}: {error}") from error
    return False


def _absolute_path_has_link_or_junction(path: Path) -> bool:
    parts = path.parts
    if not parts:
        return False
    current = Path(parts[0])
    for part in parts[1:]:
        current = current / part
        try:
            metadata = os.lstat(current)
            if (
                stat.S_ISLNK(metadata.st_mode)
                or bool(
                    getattr(metadata, "st_file_attributes", 0)
                    & getattr(
                        stat,
                        "FILE_ATTRIBUTE_REPARSE_POINT",
                        0x400,
                    )
                )
                or (
                    hasattr(os.path, "isjunction")
                    and os.path.isjunction(current)
                )
            ):
                return True
        except OSError as error:
            raise FreezeError(f"cannot inspect external path boundary {current}: {error}") from error
    return False


def _repository_entry_path(
    root: Path,
    relative_path: str,
    context: str,
    *,
    allow_missing: bool = False,
) -> Path | None:
    normalized = _validate_repository_path(relative_path, context)
    current = root
    for part in PurePosixPath(normalized).parts:
        current = current / part
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            if allow_missing:
                return None
            raise FreezeError(f"{context} is not retrievable: {current}")
        except OSError as error:
            raise FreezeError(
                f"cannot inspect path boundary {current}: {error}"
            ) from error
        if (
            stat.S_ISLNK(metadata.st_mode)
            or bool(
                getattr(metadata, "st_file_attributes", 0)
                & getattr(
                    stat,
                    "FILE_ATTRIBUTE_REPARSE_POINT",
                    0x400,
                )
            )
            or (
                hasattr(os.path, "isjunction")
                and os.path.isjunction(current)
            )
        ):
            _fail(f"{context} traverses a symlink, junction, or reparse point")
    try:
        resolved = current.resolve(strict=True)
    except OSError as error:
        raise FreezeError(f"{context} is not retrievable: {error}") from error
    if not resolved.is_relative_to(root):
        _fail(f"{context} escapes the repository root")
    return resolved


def _repository_file_path(
    root: Path,
    relative_path: str,
    context: str,
) -> Path:
    resolved = _repository_entry_path(root, relative_path, context)
    assert resolved is not None
    if not resolved.is_file():
        _fail(f"{context} is not a regular file")
    return resolved


def _read_repository_file(root: Path, relative_path: str, context: str) -> bytes:
    path = _repository_file_path(root, relative_path, context)
    try:
        return path.read_bytes()
    except OSError as error:
        raise FreezeError(f"{context} cannot be read: {error}") from error


def _load_repository_json_object(
    root: Path,
    relative_path: str,
    context: str,
) -> dict[str, Any]:
    raw = _read_repository_file(root, relative_path, context)
    value = parse_json_no_duplicates(raw, context=context)
    if not isinstance(value, dict):
        _fail(f"{context} root must be an object")
    return value


def _enumerate_repository_files(
    root: Path,
    relative_directory: str,
    *,
    context: str,
    optional: bool = False,
) -> list[str]:
    directory = _repository_entry_path(
        root,
        relative_directory,
        f"{context} directory",
        allow_missing=optional,
    )
    if directory is None:
        return []
    if not directory.is_dir():
        _fail(f"{context} is not a directory: {relative_directory}")
    pending = [relative_directory]
    files: list[str] = []
    while pending:
        current_relative = pending.pop()
        current = _repository_entry_path(
            root,
            current_relative,
            f"{context} traversal",
        )
        assert current is not None
        if not current.is_dir():
            _fail(f"{context} traversal member is not a directory")
        try:
            with os.scandir(current) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError as error:
            raise FreezeError(
                f"cannot enumerate {context} at {current_relative}: {error}"
            ) from error
        for entry in entries:
            relative = (
                PurePosixPath(current_relative) / entry.name
            ).as_posix()
            checked = _repository_entry_path(
                root,
                relative,
                f"{context} member {relative}",
            )
            assert checked is not None
            if checked.is_dir():
                pending.append(relative)
            elif checked.is_file():
                files.append(relative)
            else:
                _fail(f"{context} contains a non-regular member: {relative}")
    return sorted(files)


def _add_required_repository_input(
    required: dict[str, tuple[str, str]],
    path: Any,
    artifact_kind: str,
    byte_domain: str,
    *,
    context: str,
) -> str:
    normalized = _validate_explicit_repository_path(path, context)
    _validate_artifact_domain(artifact_kind, byte_domain)
    expected = (artifact_kind, byte_domain)
    prior = required.get(normalized)
    if prior is not None:
        _fail(f"duplicate normative Phase 0A repository path: {normalized}")
    required[normalized] = expected
    return normalized


def _repository_paths_from_rows(
    value: Mapping[str, Any],
    member: str,
    *,
    context: str,
) -> list[str]:
    rows = value.get(member)
    if not isinstance(rows, list) or not rows:
        _fail(f"{context}.{member} must be a nonempty array")
    paths: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            _fail(f"{context}.{member}[{index}] must be an object")
        paths.append(
            _validate_explicit_repository_path(
                row.get("repository_path"),
                f"{context}.{member}[{index}].repository_path",
            )
        )
    if len(paths) != len(set(paths)):
        _fail(f"{context}.{member} contains duplicate repository paths")
    _validate_no_casefold_collisions(paths, f"{context}.{member}")
    return paths


def _derive_required_phase0a_repository_inputs(
    root: Path,
) -> dict[str, tuple[str, str]]:
    """Derive the contract-owned repository root independently of caller input."""

    required = dict(_FIXED_PHASE0A_REPOSITORY_INPUTS)

    schema_bundle_path = "schemas/aegis/v2/schema_bundle.v1.json"
    schema_bundle = _load_repository_json_object(
        root,
        schema_bundle_path,
        "normative schema bundle",
    )
    schema_rows = schema_bundle.get("schemas")
    if not isinstance(schema_rows, list) or not schema_rows:
        _fail("normative schema bundle.schemas must be a nonempty array")
    schema_paths: list[str] = []
    for index, row in enumerate(schema_rows):
        if not isinstance(row, Mapping):
            _fail(f"normative schema bundle.schemas[{index}] must be an object")
        schema_paths.append(
            _validate_explicit_repository_path(
                row.get("path"),
                f"normative schema bundle.schemas[{index}].path",
            )
        )
    if len(schema_paths) != len(set(schema_paths)):
        _fail("normative schema bundle contains duplicate schema paths")
    _validate_no_casefold_collisions(
        schema_paths,
        "normative schema bundle paths",
    )
    actual_schema_paths = {
        path
        for path in _enumerate_repository_files(
            root,
            "schemas/aegis/v2",
            context="versioned schema closure",
        )
        if path.endswith(".schema.json")
    }
    if set(schema_paths) != actual_schema_paths:
        _fail(
            "normative schema closure membership mismatch; "
            f"missing_from_bundle={sorted(actual_schema_paths - set(schema_paths))}, "
            f"missing_from_directory={sorted(set(schema_paths) - actual_schema_paths)}"
        )
    for path in schema_paths:
        _add_required_repository_input(
            required,
            path,
            "VERSIONED_SCHEMA",
            "JCS_RFC8785",
            context="normative schema path",
        )

    manifest_path = "evaluation/aegis_v2/evaluation_manifest.v1.json"
    manifest = _load_repository_json_object(
        root,
        manifest_path,
        "normative evaluation manifest",
    )
    seen_manifest_paths = {manifest_path}
    while True:
        parent_hash = manifest.get("parent_manifest_hash")
        parent_locator = manifest.get("parent_manifest_locator")
        if parent_hash is None:
            if parent_locator is not None:
                _fail("normative root manifest has an orphan parent locator")
            break
        _validate_content_id(parent_hash, "normative parent manifest hash")
        if not isinstance(parent_locator, Mapping):
            _fail("normative parent manifest locator must be an object")
        if parent_locator.get("declared_manifest_sha256") != parent_hash:
            _fail("normative parent manifest locator/hash mismatch")
        parent_path = _validate_explicit_repository_path(
            parent_locator.get("repository_path"),
            "normative parent manifest repository_path",
        )
        if parent_path in seen_manifest_paths:
            _fail(f"normative evaluation manifest parent cycle: {parent_path}")
        seen_manifest_paths.add(parent_path)
        _add_required_repository_input(
            required,
            parent_path,
            "EVALUATION_MANIFEST",
            "JCS_RFC8785",
            context="normative parent manifest path",
        )
        manifest = _load_repository_json_object(
            root,
            parent_path,
            f"normative parent manifest {parent_path}",
        )
    parent_paths = seen_manifest_paths - {manifest_path}
    actual_parent_paths = set(
        _enumerate_repository_files(
            root,
            "evaluation/aegis_v2/manifests/sha256",
            context="parent manifest CAS closure",
            optional=True,
        )
    )
    if parent_paths != actual_parent_paths:
        _fail(
            "normative parent manifest closure membership mismatch; "
            f"unreachable_cas={sorted(actual_parent_paths - parent_paths)}, "
            f"missing_cas={sorted(parent_paths - actual_parent_paths)}"
        )

    catalog = _load_repository_json_object(
        root,
        "evaluation/aegis_v2/fixture_catalog.v1.json",
        "normative fixture catalog",
    )
    fixture_paths = _repository_paths_from_rows(
        catalog,
        "fixtures",
        context="normative fixture catalog",
    )
    actual_fixture_paths = set(
        _enumerate_repository_files(
            root,
            "evaluation/aegis_v2/fixtures",
            context="fixture preimage closure",
        )
    )
    if set(fixture_paths) != actual_fixture_paths:
        _fail(
            "normative fixture closure membership mismatch; "
            f"missing_from_catalog={sorted(actual_fixture_paths - set(fixture_paths))}, "
            f"missing_from_directory={sorted(set(fixture_paths) - actual_fixture_paths)}"
        )
    for path in fixture_paths:
        _add_required_repository_input(
            required,
            path,
            "EVALUATION_FIXTURE",
            "GIT_BLOB_BYTES",
            context="normative fixture path",
        )

    source_manifest = _load_repository_json_object(
        root,
        "evaluation/aegis_v2/reference/source_manifest.v1.json",
        "normative reference source manifest",
    )
    source_paths = _repository_paths_from_rows(
        source_manifest,
        "source_files",
        context="normative reference source manifest",
    )
    assurance_paths = _repository_paths_from_rows(
        source_manifest,
        "assurance_files",
        context="normative reference source manifest",
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
        _add_required_repository_input(
            required,
            path,
            "EVALUATION_REFERENCE_SOURCE",
            "GIT_BLOB_BYTES",
            context="normative reference source path",
        )
    for path in assurance_paths:
        _add_required_repository_input(
            required,
            path,
            "EVALUATION_HARNESS",
            "GIT_BLOB_BYTES",
            context="normative reference assurance path",
        )

    ordered = dict(sorted(required.items()))
    _validate_no_casefold_collisions(
        list(ordered),
        "normative Phase 0A repository domain",
    )
    return ordered


def _validate_locator(locator: Mapping[str, Any], context: str) -> None:
    if not isinstance(locator, Mapping):
        _fail(f"{context} must be an object")
    kind = locator.get("kind")
    if kind == "REPOSITORY":
        _require_exact_keys(
            locator,
            {"kind", "repository_path"},
            context,
        )
        _validate_repository_path(locator["repository_path"], f"{context}.repository_path")
        return
    if kind == "EXTERNAL_ACQUISITION":
        _require_exact_keys(
            locator,
            {
                "kind",
                "absolute_path",
                "acquisition_evidence_id",
                "acquisition_event_id",
            },
            context,
        )
        absolute_path = locator["absolute_path"]
        if (
            not isinstance(absolute_path, str)
            or (
                _WINDOWS_DRIVE_ABSOLUTE_RE.fullmatch(absolute_path) is None
                and _WINDOWS_UNC_ABSOLUTE_RE.fullmatch(absolute_path) is None
            )
            or any(part in {".", ".."} for part in Path(absolute_path).parts)
        ):
            _fail(f"{context}.absolute_path must be a schema-valid Windows path")
        _validate_content_id(
            locator["acquisition_evidence_id"],
            f"{context}.acquisition_evidence_id",
        )
        _validate_uuid_v7(
            locator["acquisition_event_id"],
            f"{context}.acquisition_event_id",
        )
        return
    _fail(f"{context}.kind must be REPOSITORY or EXTERNAL_ACQUISITION")


def _read_locator(
    repo_root: Path,
    locator: Mapping[str, Any],
    context: str,
    external_acquisition_verifier: ExternalAcquisitionVerifier | None,
) -> bytes:
    _validate_locator(locator, context)
    if locator["kind"] == "REPOSITORY":
        return _read_repository_file(
            repo_root,
            locator["repository_path"],
            context,
        )
    if external_acquisition_verifier is None:
        _fail(f"{context} requires an external acquisition verifier")
    path = Path(locator["absolute_path"])
    if _absolute_path_has_link_or_junction(path):
        _fail(f"{context} external path traverses a symlink or junction")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise FreezeError(f"{context} external acquisition is unavailable: {error}") from error
    if not resolved.is_file() or resolved.is_symlink():
        _fail(f"{context} external acquisition must be a regular non-link file")
    try:
        raw = resolved.read_bytes()
    except OSError as error:
        raise FreezeError(f"{context} external acquisition cannot be read: {error}") from error
    try:
        verified = external_acquisition_verifier(copy.deepcopy(dict(locator)), raw)
    except Exception as error:
        raise FreezeError(f"{context} external acquisition verification failed: {error}") from error
    if verified is not True:
        _fail(f"{context} external acquisition evidence was not verified")
    return raw


def _decode_single_line(
    raw: bytes,
    context: str,
    pattern: re.Pattern[str],
) -> str:
    try:
        text = raw.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise FreezeError(f"{context} did not return ASCII: {error}") from error
    if pattern.fullmatch(text) is None:
        _fail(f"{context} returned an invalid identifier: {text!r}")
    return text


def _git_cat_blob(repo_root: Path, object_id: str, context: str) -> bytes:
    _validate_git_object_id(object_id, f"{context} object ID")
    result = _run_git(repo_root, ["cat-file", "blob", object_id], context)
    if result.stderr:
        _fail(f"{context} emitted stderr")
    return result.stdout


def _frozen_git_blob(raw: bytes, object_id: str) -> dict[str, Any]:
    return {
        "source_kind": "GIT_BLOB",
        "byte_size": len(raw),
        "raw_sha256": _sha256(raw),
        "git_blob_id": object_id,
        "snapshot_locator": None,
        "acquisition_event_id": None,
    }


def _write_worktree_bytes_to_git_cas(
    repo_root: Path,
    relative_path: str,
    raw: bytes,
) -> dict[str, Any]:
    # A leading '-' would be parsed as an option by the contract's exact
    # five-element argv.  Reject it instead of silently changing the argv.
    if relative_path.startswith("-"):
        _fail(
            f"worktree path {relative_path!r} cannot be captured by the "
            "contract's exact hash-object argv"
        )
    result = _run_git(
        repo_root,
        ["hash-object", "-w", "--no-filters", relative_path],
        f"CAS capture for {relative_path}",
    )
    if result.stderr:
        _fail(f"CAS capture for {relative_path} emitted stderr")
    object_id = _decode_single_line(
        result.stdout,
        f"CAS capture for {relative_path}",
        _GIT_OBJECT_ID_RE,
    )
    stored = _git_cat_blob(
        repo_root,
        object_id,
        f"CAS verification for {relative_path}",
    )
    if stored != raw:
        _fail(f"CAS capture for {relative_path} changed the exact worktree bytes")
    return _frozen_git_blob(raw, object_id)


def _parse_nul_paths(raw: bytes, context: str) -> list[str]:
    if raw and not raw.endswith(b"\0"):
        _fail(f"{context} is truncated: missing terminal NUL")
    records = raw.split(b"\0")
    if records and records[-1] == b"":
        records.pop()
    paths: list[str] = []
    for record in records:
        try:
            path = record.decode("utf-8")
        except UnicodeDecodeError as error:
            raise FreezeError(f"{context} has a non-UTF-8 path: {error}") from error
        paths.append(_validate_repository_path(path, f"{context} path"))
    if len(paths) != len(set(paths)):
        _fail(f"{context} contains duplicate paths")
    _validate_no_casefold_collisions(paths, context)
    return paths


def _parse_ls_tree(
    raw: bytes,
) -> dict[str, tuple[str, str, str]]:
    if raw and not raw.endswith(b"\0"):
        _fail("git ls-tree output is truncated: missing terminal NUL")
    records = raw.split(b"\0")
    if records and records[-1] == b"":
        records.pop()
    result: dict[str, tuple[str, str, str]] = {}
    for record in records:
        try:
            metadata, path_raw = record.split(b"\t", 1)
            mode_raw, object_type_raw, object_id_raw = metadata.split(b" ", 2)
            mode = mode_raw.decode("ascii")
            object_type = object_type_raw.decode("ascii")
            object_id = object_id_raw.decode("ascii")
            path = path_raw.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            raise FreezeError(f"malformed git ls-tree record: {record!r}") from error
        path = _validate_repository_path(path, "git ls-tree path")
        _validate_git_object_id(object_id, f"git ls-tree object for {path}")
        if object_type != "blob" or mode not in {"100644", "100755"}:
            _fail(
                f"unsupported tracked entry {path!r}: mode={mode}, "
                f"type={object_type}; symlinks and submodules fail closed"
            )
        if path in result:
            _fail(f"git ls-tree contains duplicate path {path!r}")
        result[path] = (mode, object_type, object_id)
    _validate_no_casefold_collisions(list(result), "git ls-tree")
    return result


def _resolve_base(repo_root: Path, freeze_base_ref: str) -> tuple[str, str]:
    if not isinstance(freeze_base_ref, str) or not freeze_base_ref:
        _fail("freeze_base_ref must be a non-empty Git revision")
    commit_result = _run_git(
        repo_root,
        ["rev-parse", "--verify", f"{freeze_base_ref}^{{commit}}"],
        "freeze base commit resolution",
    )
    if commit_result.stderr:
        _fail("freeze base commit resolution emitted stderr")
    commit = _decode_single_line(
        commit_result.stdout,
        "freeze base commit resolution",
        _GIT_OBJECT_ID_RE,
    )
    tree_result = _run_git(
        repo_root,
        ["rev-parse", "--verify", f"{commit}^{{tree}}"],
        "freeze base tree resolution",
    )
    if tree_result.stderr:
        _fail("freeze base tree resolution emitted stderr")
    tree = _decode_single_line(
        tree_result.stdout,
        "freeze base tree resolution",
        _GIT_OBJECT_ID_RE,
    )
    return commit, tree


def _require_clean_index_against_base(repo_root: Path, commit: str) -> None:
    result = _run_git(
        repo_root,
        ["diff", "--cached", "--quiet", commit, "--"],
        "index/base comparison",
        accepted_exit_codes=frozenset({0, 1}),
    )
    if result.returncode == 1:
        _fail(
            "the Git index differs from freeze_base_commit; staged state is "
            "outside the Phase 0A inventory contract"
        )
    if result.stdout or result.stderr:
        _fail("git diff --cached --quiet produced unexpected output")


def _capture_inventory(
    repo_root: Path,
    freeze_base_commit: str,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, bytes],
    dict[str, bytes],
    int,
    int,
]:
    _require_clean_index_against_base(repo_root, freeze_base_commit)

    tree_arguments = [
        "ls-tree",
        "-rz",
        "--full-tree",
        freeze_base_commit,
    ]
    tree_result = _run_git(repo_root, tree_arguments, "tracked tree capture")
    if tree_result.stderr:
        _fail("tracked tree capture emitted stderr")
    tracked = _parse_ls_tree(tree_result.stdout)
    tracked_capture = {
        "argv": ["git", *tree_arguments],
        "working_directory": "REPOSITORY_ROOT",
        "stdout_encoding": "RAW_BYTES_BASE64",
        "raw_stdout_base64": base64.b64encode(tree_result.stdout).decode("ascii"),
        "stdout_byte_size": len(tree_result.stdout),
        "stdout_sha256": _sha256(tree_result.stdout),
        "required_exit_code": 0,
        "stderr_byte_size": len(tree_result.stderr),
        "stderr_sha256": _sha256(tree_result.stderr),
    }

    untracked_result = _run_git(
        repo_root,
        ["ls-files", "--others", "--exclude-standard", "-z"],
        "non-ignored untracked capture",
    )
    if untracked_result.stderr:
        _fail("non-ignored untracked capture emitted stderr")
    untracked_paths = _parse_nul_paths(
        untracked_result.stdout,
        "non-ignored untracked capture",
    )
    overlap = set(tracked) & set(untracked_paths)
    if overlap:
        _fail(f"tracked/untracked path overlap: {sorted(overlap)}")

    all_paths = sorted([*tracked, *untracked_paths])
    _validate_no_casefold_collisions(all_paths, "worktree inventory")
    base_raw: dict[str, bytes] = {}
    worktree_raw: dict[str, bytes] = {}
    inventory: list[dict[str, Any]] = []

    for relative_path in all_paths:
        if relative_path in tracked:
            _, _, base_object_id = tracked[relative_path]
            raw_base = _git_cat_blob(
                repo_root,
                base_object_id,
                f"base blob for {relative_path}",
            )
            base_raw[relative_path] = raw_base
            base_bytes = _frozen_git_blob(raw_base, base_object_id)
        else:
            base_bytes = None

        candidate_path = repo_root.joinpath(*PurePosixPath(relative_path).parts)
        if candidate_path.exists() or candidate_path.is_symlink():
            raw_worktree = _read_repository_file(
                repo_root,
                relative_path,
                f"worktree inventory file {relative_path}",
            )
            worktree_raw[relative_path] = raw_worktree
            worktree_bytes = _write_worktree_bytes_to_git_cas(
                repo_root,
                relative_path,
                raw_worktree,
            )
        else:
            worktree_bytes = None

        if relative_path not in tracked:
            entry_kind = "UNTRACKED_NONIGNORED"
            if worktree_bytes is None:
                _fail(f"untracked inventory path disappeared: {relative_path}")
        elif worktree_bytes is None:
            entry_kind = "TRACKED_DELETED"
        elif base_raw[relative_path] == worktree_raw[relative_path]:
            entry_kind = "TRACKED_UNCHANGED"
        else:
            entry_kind = "TRACKED_MODIFIED"

        entry: dict[str, Any] = {
            "repository_relative_path": relative_path,
            "entry_kind": entry_kind,
            "base_bytes": base_bytes,
            "worktree_bytes": worktree_bytes,
        }
        entry["inventory_entry_id"] = _self_omission_content_id(
            entry,
            "inventory_entry_id",
            f"inventory entry {relative_path}",
        )
        inventory.append(entry)

    return (
        tracked_capture,
        inventory,
        base_raw,
        worktree_raw,
        len(tracked),
        len(untracked_paths),
    )


def _validate_artifact_domain(artifact_kind: str, byte_domain: str) -> None:
    if artifact_kind not in _ARTIFACT_KINDS:
        _fail(f"unsupported artifact_kind: {artifact_kind!r}")
    if byte_domain not in _BYTE_DOMAINS:
        _fail(f"unsupported byte_domain: {byte_domain!r}")
    if artifact_kind in _JCS_ARTIFACT_KINDS and byte_domain != "JCS_RFC8785":
        _fail(f"{artifact_kind} must use JCS_RFC8785")
    if artifact_kind in _UTF8_ARTIFACT_KINDS and byte_domain != "UTF8_LF_NO_BOM":
        _fail(f"{artifact_kind} must use UTF8_LF_NO_BOM")
    if artifact_kind in _GIT_BLOB_ARTIFACT_KINDS and byte_domain != "GIT_BLOB_BYTES":
        _fail(f"{artifact_kind} must use GIT_BLOB_BYTES")


def _build_freeze_input(
    repo_root: Path,
    spec: Mapping[str, Any],
    external_acquisition_verifier: ExternalAcquisitionVerifier | None,
) -> dict[str, Any]:
    _require_exact_keys(spec, _FREEZE_INPUT_SPEC_KEYS, "freeze input spec")
    logical_path = _validate_logical_path(spec["logical_path"], "freeze input logical_path")
    if not isinstance(spec["locator"], Mapping):
        _fail(f"freeze input {logical_path} locator must be an object")
    locator = copy.deepcopy(dict(spec["locator"]))
    _validate_locator(locator, f"freeze input {logical_path} locator")
    artifact_kind = spec["artifact_kind"]
    byte_domain = spec["byte_domain"]
    if not isinstance(artifact_kind, str) or not isinstance(byte_domain, str):
        _fail(f"freeze input {logical_path} kind/domain must be strings")
    _validate_artifact_domain(artifact_kind, byte_domain)

    if locator["kind"] == "REPOSITORY":
        expected_logical_path = f"repo:/{locator['repository_path']}"
        if logical_path != expected_logical_path:
            _fail(
                f"freeze input logical/locator mismatch: {logical_path!r} != "
                f"{expected_logical_path!r}"
            )
    elif not logical_path.startswith("external:/"):
        _fail("external acquisition locator requires an external:/ logical path")

    raw = _read_locator(
        repo_root,
        locator,
        f"freeze input {logical_path}",
        external_acquisition_verifier,
    )
    semantic_jcs_sha256: str | None = None
    if byte_domain == "JCS_RFC8785":
        parsed = parse_json_no_duplicates(raw, context=f"freeze input {logical_path}")
        semantic_jcs_sha256 = _sha256(
            _jcs(parsed, f"freeze input {logical_path} semantic JSON")
        )
    elif byte_domain == "UTF8_LF_NO_BOM":
        _require_utf8_lf_no_bom(raw, f"freeze input {logical_path}")
    elif artifact_kind in _EXACT_TEXT_ARTIFACT_KINDS:
        _require_utf8_lf_no_bom(raw, f"freeze input {logical_path}")

    leaf: dict[str, Any] = {
        "logical_path": logical_path,
        "locator": locator,
        "artifact_kind": artifact_kind,
        "byte_domain": byte_domain,
        "byte_size": len(raw),
        "raw_sha256": _sha256(raw),
        "semantic_jcs_sha256": semantic_jcs_sha256,
    }
    leaf["leaf_sha256"] = _sha256(
        _jcs(leaf, f"freeze input {logical_path} leaf preimage")
    )
    return leaf


def _validate_freeze_input(
    repo_root: Path,
    leaf: Mapping[str, Any],
    external_acquisition_verifier: ExternalAcquisitionVerifier | None,
) -> None:
    _require_exact_keys(leaf, _FREEZE_INPUT_KEYS, "freeze input")
    spec = {key: copy.deepcopy(leaf[key]) for key in _FREEZE_INPUT_SPEC_KEYS}
    expected = _build_freeze_input(
        repo_root,
        spec,
        external_acquisition_verifier,
    )
    if dict(leaf) != expected:
        _fail(f"freeze input {leaf.get('logical_path')!r} changed or hash mismatch")


def _python_identifiers(tree: ast.AST) -> tuple[set[str], bool]:
    identifiers: set[str] = set()
    executable_shape = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            identifiers.add(node.name.casefold())
            executable_shape = True
        elif isinstance(node, ast.Name):
            identifiers.add(node.id.casefold())
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr.casefold())
        elif isinstance(node, ast.alias):
            identifiers.update(part.casefold() for part in node.name.split("."))
        elif isinstance(node, (ast.Call, ast.Await)):
            executable_shape = True
    return identifiers, executable_shape


def _generic_identifiers(text: str) -> tuple[set[str], bool]:
    identifiers = {
        token.casefold()
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text)
    }
    executable_shape = bool(
        re.search(
            r"\b(?:class|def|function|func|fn)\s+[A-Za-z_]"
            r"|\b(?:subprocess|exec|spawn|compile)\s*\(",
            text,
        )
    )
    return identifiers, executable_shape


def _classify_executable_content(
    repository_relative_path: str,
    raw: bytes,
) -> list[tuple[str, list[str]]]:
    suffix = PurePosixPath(repository_relative_path).suffix.casefold()
    if b"\0" in raw:
        return []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        if suffix not in _EXECUTABLE_SUFFIXES:
            return []
        raise FreezeError(
            f"cannot classify non-UTF-8 executable source "
            f"{repository_relative_path}: {error}"
        ) from error

    has_shebang = text.startswith("#!")
    strong_python_shape = bool(
        re.search(
            r"(?m)^\s*(?:from\s+langgraph(?:\.|\s)|import\s+langgraph\b|"
            r"class\s+(?:AegisV2Kernel|AegisQualityKernel)\b|"
            r"def\s+(?:live_capability_probe|codex_capability_probe|"
            r"relay_executor|native_action_executor)\b)",
            text,
        )
    )
    strong_generic_shape = bool(
        re.search(
            r"(?im)^\s*(?:class|def|function|func|fn)\s+"
            r"(?:aegis_?v2_?kernel|aegis_?quality_?kernel|"
            r"live_?capability_?probe|codex_?capability_?probe|"
            r"relay_?executor|native_?action_?executor)\b",
            text,
        )
    )
    if (
        suffix not in _EXECUTABLE_SUFFIXES
        and not has_shebang
        and not strong_python_shape
        and not strong_generic_shape
    ):
        return []

    python_syntax = suffix in {".py", ".pyw"} or strong_python_shape or (
        has_shebang and "python" in text.splitlines()[0].casefold()
    )
    if python_syntax:
        try:
            tree = ast.parse(text, filename=repository_relative_path)
        except SyntaxError as error:
            raise FreezeError(
                f"cannot classify syntactically invalid Python source "
                f"{repository_relative_path}: {error}"
            ) from error
        identifiers, executable_shape = _python_identifiers(tree)
    else:
        identifiers, executable_shape = _generic_identifiers(text)
    if not executable_shape:
        return []

    compact_identifiers = {identifier.replace("_", "") for identifier in identifiers}
    classifications: list[tuple[str, list[str]]] = []

    kernel_names = {
        "aegisv2kernel",
        "aegisqualitykernel",
        "v2qualitykernel",
        "qualitykernelv2",
    }
    kernel_hits = sorted(kernel_names & compact_identifiers)
    if kernel_hits:
        classifications.append(("AEGIS_V2_KERNEL", kernel_hits))

    graph_hits = sorted(
        {
            "stategraph",
            "sqlitesaver",
            "checkpoint",
            "compile",
        }
        & compact_identifiers
    )
    v2_hits = sorted(
        {
            identifier
            for identifier in compact_identifiers
            if "aegisv2" in identifier
            or identifier
            in {
                "verdictinput",
                "graphdecision",
                "evidencerecord",
                "runnerexecutionrecord",
            }
        }
    )
    if len(graph_hits) >= 2 and v2_hits:
        classifications.append(
            (
                "EQUIVALENT_EXECUTABLE_IMPLEMENTATION",
                [*graph_hits, *v2_hits],
            )
        )

    relay_name_hits = sorted(
        {
            identifier
            for identifier in compact_identifiers
            if "relay" in identifier or "nativeactionexecutor" in identifier
        }
    )
    relay_api_hits = sorted(
        {
            "sendmessage",
            "sendmessagetothread",
            "spawnagent",
            "createthread",
            "resumethread",
            "subprocess",
        }
        & compact_identifiers
    )
    if relay_name_hits and relay_api_hits:
        classifications.append(
            ("RELAY_EXECUTOR", [*relay_name_hits, *relay_api_hits])
        )

    probe_name_hits = sorted(
        {
            identifier
            for identifier in compact_identifiers
            if "livecapabilityprobe" in identifier
            or "codexcapabilityprobe" in identifier
        }
    )
    probe_api_hits = sorted(
        {
            "sendmessage",
            "sendmessagetothread",
            "spawnagent",
            "createthread",
            "subprocess",
        }
        & compact_identifiers
    )
    if probe_name_hits and probe_api_hits:
        classifications.append(
            ("LIVE_CAPABILITY_PROBE", [*probe_name_hits, *probe_api_hits])
        )
    return classifications


def scan_prohibited_implementations(
    files: Mapping[str, bytes],
) -> list[dict[str, str]]:
    """Classify executable content; filenames alone never produce a match."""

    matches: list[dict[str, str]] = []
    for repository_relative_path in sorted(files):
        _validate_repository_path(
            repository_relative_path,
            "prohibited implementation scan path",
        )
        raw = files[repository_relative_path]
        if not isinstance(raw, bytes):
            _fail("prohibited implementation scan values must be bytes")
        for classifier, signals in _classify_executable_content(
            repository_relative_path,
            raw,
        ):
            evidence = {
                "repository_relative_path": repository_relative_path,
                "classifier": classifier,
                "raw_sha256": _sha256(raw),
                "signals": sorted(set(signals)),
            }
            matches.append(
                {
                    "repository_relative_path": repository_relative_path,
                    "classifier": classifier,
                    "evidence_sha256": _sha256(
                        _jcs(evidence, "prohibited implementation evidence")
                    ),
                }
            )
    return matches


def _build_outside_domain_entries(
    repo_root: Path,
    inventory: Sequence[Mapping[str, Any]],
    allowed_domain: Sequence[str],
    dispositions: Mapping[str, Mapping[str, Any]],
    producer_identity: Mapping[str, Any],
    external_acquisition_verifier: ExternalAcquisitionVerifier | None,
) -> list[dict[str, Any]]:
    by_path = {entry["repository_relative_path"]: entry for entry in inventory}
    complement = sorted(set(by_path) - set(allowed_domain))
    if not isinstance(dispositions, Mapping):
        _fail("outside_domain_dispositions must be a path-to-disposition object")
    disposition_paths = sorted(dispositions)
    if disposition_paths != complement:
        _fail(
            "outside-domain dispositions must equal the exact inventory "
            f"complement; expected={complement}, actual={disposition_paths}"
        )
    result: list[dict[str, Any]] = []
    for path in complement:
        spec = dispositions[path]
        _require_exact_keys(
            spec,
            _DISPOSITION_SPEC_KEYS,
            f"outside-domain disposition {path}",
        )
        disposition = spec["disposition"]
        if disposition not in {"BASE_EQUAL", "PREEXISTING_NON_V2"}:
            _fail(f"outside-domain disposition {path} has invalid disposition")
        entry = by_path[path]
        if disposition == "BASE_EQUAL" and entry["entry_kind"] != "TRACKED_UNCHANGED":
            _fail(
                f"outside-domain disposition {path} may use BASE_EQUAL only "
                "for TRACKED_UNCHANGED bytes"
            )
        if spec["executable_v2_classification"] != "NOT_V2_IMPLEMENTATION":
            _fail(f"outside-domain disposition {path} must classify NOT_V2_IMPLEMENTATION")
        rationale = spec["rationale"]
        if not isinstance(rationale, str) or not rationale or len(rationale) > 32768:
            _fail(f"outside-domain disposition {path} requires a rationale")
        reviewer = {
            key: _validate_opaque_id(spec[key], f"outside-domain {path} {key}")
            for key in (
                "reviewer_thread_id",
                "reviewer_session_id",
                "reviewer_turn_id",
            )
        }
        _require_independent_reviewer(
            reviewer,
            producer_identity,
            f"outside-domain disposition reviewer for {path}",
        )
        if not isinstance(spec["disposition_artifact_locator"], Mapping):
            _fail(f"outside-domain disposition artifact locator for {path} must be an object")
        artifact_locator = copy.deepcopy(dict(spec["disposition_artifact_locator"]))
        artifact_raw = _read_locator(
            repo_root,
            artifact_locator,
            f"outside-domain disposition artifact for {path}",
            external_acquisition_verifier,
        )
        if not artifact_raw:
            _fail(f"outside-domain disposition artifact for {path} is empty")
        result.append(
            {
                "repository_relative_path": path,
                "inventory_entry_id": entry["inventory_entry_id"],
                "disposition": disposition,
                "executable_v2_classification": "NOT_V2_IMPLEMENTATION",
                "rationale": rationale,
                **reviewer,
                "disposition_artifact_locator": artifact_locator,
                "disposition_artifact_byte_size": len(artifact_raw),
                "disposition_artifact_sha256": _sha256(artifact_raw),
            }
        )
    return result


def _validate_allowed_domain_and_inputs(
    repo_root: Path,
    allowed_phase0a_file_domain: Sequence[str],
    leaves: Sequence[Mapping[str, Any]],
) -> list[str]:
    if isinstance(allowed_phase0a_file_domain, (str, bytes)) or not isinstance(
        allowed_phase0a_file_domain,
        Sequence,
    ):
        _fail("allowed_phase0a_file_domain must be an explicit path list")
    allowed = [
        _validate_explicit_repository_path(path, "allowed Phase 0A file-domain path")
        for path in allowed_phase0a_file_domain
    ]
    if not allowed:
        _fail("allowed_phase0a_file_domain must not be empty")
    if allowed != sorted(allowed) or len(allowed) != len(set(allowed)):
        _fail("allowed_phase0a_file_domain must be unique and sorted")
    _validate_no_casefold_collisions(allowed, "allowed_phase0a_file_domain")
    repository_leaf_paths = sorted(
        leaf["locator"]["repository_path"]
        for leaf in leaves
        if leaf["locator"]["kind"] == "REPOSITORY"
    )
    required = _derive_required_phase0a_repository_inputs(repo_root)
    required_paths = list(required)
    observed = {
        leaf["locator"]["repository_path"]: (
            leaf["artifact_kind"],
            leaf["byte_domain"],
        )
        for leaf in leaves
        if leaf["locator"]["kind"] == "REPOSITORY"
    }
    missing = sorted(set(required) - set(observed))
    extra = sorted(set(observed) - set(required))
    mismatched = sorted(
        path
        for path in set(required) & set(observed)
        if observed[path] != required[path]
    )
    if missing or extra or mismatched:
        _fail(
            "normative Phase 0A repository domain mismatch; "
            f"missing={missing}, extra={extra}, kind_or_domain={mismatched}"
        )
    if allowed != required_paths:
        _fail(
            "normative Phase 0A repository domain must equal the explicit "
            f"allowed domain; required={required_paths}, allowed={allowed}"
        )
    if repository_leaf_paths != allowed:
        _fail(
            "the explicit allowed Phase 0A domain must equal the repository "
            f"freeze input set; domain={allowed}, freeze inputs={repository_leaf_paths}"
        )
    return allowed


def build_freeze_candidate(
    *,
    repo_root: Path | str,
    freeze_input_specs: Sequence[Mapping[str, Any]],
    allowed_phase0a_file_domain: Sequence[str],
    outside_domain_dispositions: Mapping[str, Mapping[str, Any]],
    freeze_producer_identity: Mapping[str, Any],
    freeze_time_utc: str,
    proof_event_id: str,
    proven_at_utc: str,
    freeze_base_ref: str = "HEAD",
    external_acquisition_verifier: ExternalAcquisitionVerifier | None = None,
) -> dict[str, Any]:
    """Build a review candidate without manufacturing a PASS or final anchor."""

    root = _require_repository_root(repo_root)
    producer = _validate_producer_identity(freeze_producer_identity)
    freeze_time = _parse_utc(freeze_time_utc, "freeze_time_utc")
    proven_time = _parse_utc(proven_at_utc, "proven_at_utc")
    if proven_time < freeze_time:
        _fail("proven_at_utc cannot be before freeze_time_utc")
    _validate_uuid_v7(proof_event_id, "proof_event_id")
    freeze_base_commit, freeze_base_tree = _resolve_base(root, freeze_base_ref)

    if isinstance(freeze_input_specs, (str, bytes)) or not isinstance(
        freeze_input_specs,
        Sequence,
    ):
        _fail("freeze_input_specs must be an explicit list")
    leaves = [
        _build_freeze_input(root, spec, external_acquisition_verifier)
        for spec in freeze_input_specs
    ]
    if not leaves:
        _fail("freeze_input_specs must not be empty")
    leaves.sort(key=lambda leaf: leaf["logical_path"])
    logical_paths = [leaf["logical_path"] for leaf in leaves]
    if len(logical_paths) != len(set(logical_paths)):
        _fail("freeze input logical paths must be unique")
    _validate_no_casefold_collisions(logical_paths, "freeze input logical paths")
    allowed = _validate_allowed_domain_and_inputs(
        root,
        allowed_phase0a_file_domain,
        leaves,
    )

    (
        tracked_capture,
        inventory,
        base_raw,
        worktree_raw,
        tracked_count,
        untracked_count,
    ) = _capture_inventory(root, freeze_base_commit)
    inventory_paths = {entry["repository_relative_path"] for entry in inventory}
    missing_allowed = sorted(set(allowed) - inventory_paths)
    if missing_allowed:
        _fail(f"allowed Phase 0A paths are missing from the inventory: {missing_allowed}")

    outside_entries = _build_outside_domain_entries(
        root,
        inventory,
        allowed,
        outside_domain_dispositions,
        producer,
        external_acquisition_verifier,
    )
    base_matches = scan_prohibited_implementations(base_raw)
    worktree_matches = scan_prohibited_implementations(worktree_raw)
    if base_matches or worktree_matches:
        raise ProhibitedImplementationError(
            "prohibited implementation content detected: "
            f"base={base_matches}, worktree={worktree_matches}"
        )

    proof: dict[str, Any] = {
        "schema_version": "CodeAbsenceProof.v1",
        "canonicalization": "JCS-RFC8785",
        "freeze_base_commit": freeze_base_commit,
        "tracked_tree_capture": tracked_capture,
        "worktree_inventory_id": _content_id(
            inventory,
            "worktree inventory",
        ),
        "worktree_inventory": inventory,
        "tracked_entry_count": tracked_count,
        "nonignored_untracked_entry_count": untracked_count,
        "allowed_phase0a_file_domain": allowed,
        "outside_domain_entries": outside_entries,
        "prohibited_implementation_classifiers": list(_PROHIBITED_CLASSIFIERS),
        "base_tree_prohibited_matches": [],
        "worktree_prohibited_matches": [],
        "proof_event_id": proof_event_id,
        "proven_at_utc": proven_at_utc,
    }
    proof["code_absence_proof_id"] = _self_omission_content_id(
        proof,
        "code_absence_proof_id",
        "code absence proof",
    )
    root_preimage = [
        {
            "logical_path": leaf["logical_path"],
            "leaf_sha256": leaf["leaf_sha256"],
        }
        for leaf in leaves
    ]
    candidate: dict[str, Any] = {
        "schema_version": "Phase0FreezeCandidate.v1",
        "freeze_state": "CANDIDATE_AWAITING_INDEPENDENT_REVIEW",
        "canonicalization": "JCS-RFC8785",
        "freeze_base_commit": freeze_base_commit,
        "freeze_base_tree": freeze_base_tree,
        "freeze_time_utc": freeze_time_utc,
        "freeze_inputs": leaves,
        "freeze_root_id": _content_id(root_preimage, "freeze root"),
        "code_absence_proof": proof,
        "freeze_producer_identity": producer,
    }
    candidate["candidate_id"] = _self_omission_content_id(
        candidate,
        "candidate_id",
        "freeze candidate",
    )
    verify_freeze_candidate(
        candidate,
        repo_root=root,
        external_acquisition_verifier=external_acquisition_verifier,
    )
    return candidate


def _validate_frozen_bytes(
    repo_root: Path,
    value: Mapping[str, Any],
    context: str,
) -> bytes:
    _require_exact_keys(value, _FROZEN_BYTES_KEYS, context)
    if value["source_kind"] != "GIT_BLOB":
        _fail(f"{context} must use a repository Git blob CAS")
    object_id = _validate_git_object_id(value["git_blob_id"], f"{context}.git_blob_id")
    if value["snapshot_locator"] is not None or value["acquisition_event_id"] is not None:
        _fail(f"{context} Git blob must not carry snapshot acquisition fields")
    raw = _git_cat_blob(repo_root, object_id, context)
    if value["byte_size"] != len(raw):
        _fail(f"{context} byte_size mismatch")
    if value["raw_sha256"] != _sha256(raw):
        _fail(f"{context} raw_sha256 mismatch")
    return raw


def _verify_inventory(
    repo_root: Path,
    proof: Mapping[str, Any],
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    capture = proof["tracked_tree_capture"]
    _require_exact_keys(capture, _TRACKED_CAPTURE_KEYS, "tracked tree capture")
    expected_argv = [
        "git",
        "ls-tree",
        "-rz",
        "--full-tree",
        proof["freeze_base_commit"],
    ]
    if capture["argv"] != expected_argv:
        _fail("tracked tree capture argv mismatch")
    if capture["working_directory"] != "REPOSITORY_ROOT":
        _fail("tracked tree capture working_directory mismatch")
    if capture["stdout_encoding"] != "RAW_BYTES_BASE64":
        _fail("tracked tree capture encoding mismatch")
    if capture["required_exit_code"] != 0:
        _fail("tracked tree capture must require exit code zero")
    if capture["stderr_byte_size"] != 0 or capture["stderr_sha256"] != _EMPTY_SHA256:
        _fail("tracked tree capture must bind empty stderr")
    try:
        captured_raw = base64.b64decode(
            capture["raw_stdout_base64"],
            validate=True,
        )
    except (ValueError, TypeError) as error:
        raise FreezeError("tracked tree capture base64 is invalid") from error
    if len(captured_raw) != capture["stdout_byte_size"]:
        _fail("tracked tree capture stdout_byte_size mismatch")
    if _sha256(captured_raw) != capture["stdout_sha256"]:
        _fail("tracked tree capture stdout_sha256 mismatch")
    tracked = _parse_ls_tree(captured_raw)

    actual_tree = _run_git(
        repo_root,
        ["ls-tree", "-rz", "--full-tree", proof["freeze_base_commit"]],
        "tracked tree recapture",
    )
    if actual_tree.stderr or actual_tree.stdout != captured_raw:
        _fail("tracked tree capture no longer matches the frozen base commit")

    actual_untracked = _run_git(
        repo_root,
        ["ls-files", "--others", "--exclude-standard", "-z"],
        "non-ignored untracked recapture",
    )
    if actual_untracked.stderr:
        _fail("non-ignored untracked recapture emitted stderr")
    untracked_paths = _parse_nul_paths(
        actual_untracked.stdout,
        "non-ignored untracked recapture",
    )
    _require_clean_index_against_base(repo_root, proof["freeze_base_commit"])
    expected_paths = sorted([*tracked, *untracked_paths])

    inventory = proof["worktree_inventory"]
    if not isinstance(inventory, list) or not inventory:
        _fail("worktree_inventory must be a non-empty list")
    paths = [entry.get("repository_relative_path") for entry in inventory]
    if paths != expected_paths:
        _fail(
            "worktree inventory is incomplete or unsorted; "
            f"expected={expected_paths}, actual={paths}"
        )
    if proof["worktree_inventory_id"] != _content_id(
        inventory,
        "worktree inventory verification",
    ):
        _fail("worktree_inventory_id mismatch")
    if proof["tracked_entry_count"] != len(tracked):
        _fail("tracked_entry_count mismatch")
    if proof["nonignored_untracked_entry_count"] != len(untracked_paths):
        _fail("nonignored_untracked_entry_count mismatch")

    base_raw: dict[str, bytes] = {}
    worktree_raw: dict[str, bytes] = {}
    for entry in inventory:
        _require_exact_keys(entry, _INVENTORY_ENTRY_KEYS, "worktree inventory entry")
        path = _validate_repository_path(
            entry["repository_relative_path"],
            "worktree inventory entry path",
        )
        if entry["inventory_entry_id"] != _self_omission_content_id(
            entry,
            "inventory_entry_id",
            f"inventory entry verification {path}",
        ):
            _fail(f"inventory_entry_id mismatch for {path}")

        if path in tracked:
            if entry["base_bytes"] is None:
                _fail(f"tracked inventory entry {path} lacks base_bytes")
            raw_base = _validate_frozen_bytes(
                repo_root,
                entry["base_bytes"],
                f"base bytes {path}",
            )
            if entry["base_bytes"]["git_blob_id"] != tracked[path][2]:
                _fail(f"base Git object mismatch for {path}")
            base_raw[path] = raw_base
        elif entry["base_bytes"] is not None:
            _fail(f"untracked inventory entry {path} unexpectedly has base_bytes")

        candidate_path = repo_root.joinpath(*PurePosixPath(path).parts)
        exists = candidate_path.exists() or candidate_path.is_symlink()
        if exists:
            if entry["worktree_bytes"] is None:
                _fail(f"worktree inventory entry {path} lacks worktree_bytes")
            raw_cas = _validate_frozen_bytes(
                repo_root,
                entry["worktree_bytes"],
                f"worktree bytes {path}",
            )
            raw_current = _read_repository_file(
                repo_root,
                path,
                f"current worktree bytes {path}",
            )
            if raw_current != raw_cas:
                _fail(f"current worktree bytes changed for {path}")
            worktree_raw[path] = raw_current
        elif entry["worktree_bytes"] is not None:
            _fail(f"deleted worktree inventory entry {path} has worktree_bytes")

        if path not in tracked:
            expected_kind = "UNTRACKED_NONIGNORED"
        elif not exists:
            expected_kind = "TRACKED_DELETED"
        elif base_raw[path] == worktree_raw[path]:
            expected_kind = "TRACKED_UNCHANGED"
        else:
            expected_kind = "TRACKED_MODIFIED"
        if entry["entry_kind"] != expected_kind:
            _fail(
                f"inventory entry_kind mismatch for {path}: "
                f"expected {expected_kind}, got {entry['entry_kind']}"
            )
    return base_raw, worktree_raw


def _verify_outside_domain_entries(
    repo_root: Path,
    proof: Mapping[str, Any],
    producer: Mapping[str, Any],
    external_acquisition_verifier: ExternalAcquisitionVerifier | None,
) -> None:
    inventory_by_path = {
        entry["repository_relative_path"]: entry
        for entry in proof["worktree_inventory"]
    }
    allowed = proof["allowed_phase0a_file_domain"]
    expected_paths = sorted(set(inventory_by_path) - set(allowed))
    outside = proof["outside_domain_entries"]
    if not isinstance(outside, list):
        _fail("outside_domain_entries must be a list")
    actual_paths = [item.get("repository_relative_path") for item in outside]
    if actual_paths != expected_paths:
        _fail(
            "outside_domain_entries must equal the sorted inventory complement"
        )
    for item in outside:
        _require_exact_keys(item, _OUTSIDE_DOMAIN_KEYS, "outside-domain entry")
        path = item["repository_relative_path"]
        inventory_entry = inventory_by_path[path]
        if item["inventory_entry_id"] != inventory_entry["inventory_entry_id"]:
            _fail(f"outside-domain inventory binding mismatch for {path}")
        if item["disposition"] == "BASE_EQUAL":
            if inventory_entry["entry_kind"] != "TRACKED_UNCHANGED":
                _fail(f"outside-domain BASE_EQUAL is invalid for {path}")
        elif item["disposition"] != "PREEXISTING_NON_V2":
            _fail(f"outside-domain disposition is invalid for {path}")
        if item["executable_v2_classification"] != "NOT_V2_IMPLEMENTATION":
            _fail(f"outside-domain classification is invalid for {path}")
        if (
            not isinstance(item["rationale"], str)
            or not item["rationale"]
            or len(item["rationale"]) > 32768
        ):
            _fail(f"outside-domain rationale is invalid for {path}")
        reviewer = {
            key: _validate_opaque_id(item[key], f"outside-domain {path} {key}")
            for key in (
                "reviewer_thread_id",
                "reviewer_session_id",
                "reviewer_turn_id",
            )
        }
        _require_independent_reviewer(
            reviewer,
            producer,
            f"outside-domain disposition reviewer for {path}",
        )
        artifact = _read_locator(
            repo_root,
            item["disposition_artifact_locator"],
            f"outside-domain disposition artifact for {path}",
            external_acquisition_verifier,
        )
        if not artifact:
            _fail(f"outside-domain disposition artifact for {path} is empty")
        if item["disposition_artifact_byte_size"] != len(artifact):
            _fail(f"outside-domain disposition artifact byte size mismatch for {path}")
        if item["disposition_artifact_sha256"] != _sha256(artifact):
            _fail(f"outside-domain disposition artifact hash mismatch for {path}")


def _verify_candidate_core(
    candidate: Mapping[str, Any],
    repo_root: Path,
    external_acquisition_verifier: ExternalAcquisitionVerifier | None,
) -> None:
    if candidate["schema_version"] != "Phase0FreezeCandidate.v1":
        _fail("candidate schema_version mismatch")
    if candidate["freeze_state"] != "CANDIDATE_AWAITING_INDEPENDENT_REVIEW":
        _fail("candidate freeze_state mismatch")
    if candidate["canonicalization"] != "JCS-RFC8785":
        _fail("candidate canonicalization mismatch")
    _validate_git_object_id(candidate["freeze_base_commit"], "candidate base commit")
    _validate_git_object_id(candidate["freeze_base_tree"], "candidate base tree")
    freeze_time = _parse_utc(candidate["freeze_time_utc"], "candidate freeze_time_utc")
    producer = _validate_producer_identity(candidate["freeze_producer_identity"])

    resolved_commit, resolved_tree = _resolve_base(
        repo_root,
        candidate["freeze_base_commit"],
    )
    if resolved_commit != candidate["freeze_base_commit"]:
        _fail("candidate freeze_base_commit no longer resolves exactly")
    if resolved_tree != candidate["freeze_base_tree"]:
        _fail("candidate freeze_base_tree mismatch")

    leaves = candidate["freeze_inputs"]
    if not isinstance(leaves, list) or not leaves:
        _fail("candidate freeze_inputs must be non-empty")
    logical_paths = [leaf.get("logical_path") for leaf in leaves]
    if logical_paths != sorted(logical_paths) or len(logical_paths) != len(
        set(logical_paths)
    ):
        _fail("candidate freeze_inputs must have unique sorted logical paths")
    _validate_no_casefold_collisions(logical_paths, "candidate freeze input paths")
    for leaf in leaves:
        _validate_freeze_input(
            repo_root,
            leaf,
            external_acquisition_verifier,
        )
    root_preimage = [
        {
            "logical_path": leaf["logical_path"],
            "leaf_sha256": leaf["leaf_sha256"],
        }
        for leaf in leaves
    ]
    if candidate["freeze_root_id"] != _content_id(
        root_preimage,
        "candidate freeze root verification",
    ):
        _fail("candidate freeze_root_id mismatch")

    proof = candidate["code_absence_proof"]
    _require_exact_keys(proof, _CODE_ABSENCE_KEYS, "code absence proof")
    if proof["schema_version"] != "CodeAbsenceProof.v1":
        _fail("code absence proof schema_version mismatch")
    if proof["canonicalization"] != "JCS-RFC8785":
        _fail("code absence proof canonicalization mismatch")
    if proof["freeze_base_commit"] != candidate["freeze_base_commit"]:
        _fail("code absence proof/base commit mismatch")
    if proof["code_absence_proof_id"] != _self_omission_content_id(
        proof,
        "code_absence_proof_id",
        "code absence proof verification",
    ):
        _fail("code_absence_proof_id mismatch")
    _validate_uuid_v7(proof["proof_event_id"], "code absence proof event")
    proven_time = _parse_utc(proof["proven_at_utc"], "code absence proof UTC")
    if proven_time < freeze_time:
        _fail("code absence proof UTC is before freeze_time_utc")
    if proof["prohibited_implementation_classifiers"] != _PROHIBITED_CLASSIFIERS:
        _fail("prohibited implementation classifier set mismatch")
    if proof["base_tree_prohibited_matches"] != []:
        _fail("base tree has prohibited implementation matches")
    if proof["worktree_prohibited_matches"] != []:
        _fail("worktree has prohibited implementation matches")

    allowed = proof["allowed_phase0a_file_domain"]
    if not isinstance(allowed, list):
        _fail("allowed_phase0a_file_domain must be a list")
    normalized_allowed = [
        _validate_explicit_repository_path(path, "allowed Phase 0A path")
        for path in allowed
    ]
    if normalized_allowed != sorted(normalized_allowed) or len(
        normalized_allowed
    ) != len(set(normalized_allowed)):
        _fail("allowed_phase0a_file_domain must be unique and sorted")
    _validate_no_casefold_collisions(allowed, "allowed_phase0a_file_domain")
    repository_leaf_paths = sorted(
        leaf["locator"]["repository_path"]
        for leaf in leaves
        if leaf["locator"]["kind"] == "REPOSITORY"
    )
    required = _derive_required_phase0a_repository_inputs(repo_root)
    observed = {
        leaf["locator"]["repository_path"]: (
            leaf["artifact_kind"],
            leaf["byte_domain"],
        )
        for leaf in leaves
        if leaf["locator"]["kind"] == "REPOSITORY"
    }
    missing = sorted(set(required) - set(observed))
    extra = sorted(set(observed) - set(required))
    mismatched = sorted(
        path
        for path in set(required) & set(observed)
        if observed[path] != required[path]
    )
    if missing or extra or mismatched:
        _fail(
            "normative Phase 0A repository domain mismatch during verification; "
            f"missing={missing}, extra={extra}, kind_or_domain={mismatched}"
        )
    if allowed != list(required):
        _fail(
            "allowed Phase 0A domain does not equal the independently "
            "derived normative repository domain"
        )
    if repository_leaf_paths != allowed:
        _fail("allowed Phase 0A domain/freeze input mismatch")

    base_raw, worktree_raw = _verify_inventory(repo_root, proof)
    if set(allowed) - set(worktree_raw):
        _fail("allowed Phase 0A domain contains deleted or missing worktree files")
    _verify_outside_domain_entries(
        repo_root,
        proof,
        producer,
        external_acquisition_verifier,
    )
    base_matches = scan_prohibited_implementations(base_raw)
    worktree_matches = scan_prohibited_implementations(worktree_raw)
    if base_matches or worktree_matches:
        raise ProhibitedImplementationError(
            "prohibited implementation content detected during verification: "
            f"base={base_matches}, worktree={worktree_matches}"
        )


def verify_freeze_candidate(
    candidate: Mapping[str, Any],
    *,
    repo_root: Path | str,
    external_acquisition_verifier: ExternalAcquisitionVerifier | None = None,
) -> None:
    """Recompute every candidate binding against Git and current locators."""

    _require_exact_keys(candidate, _CANDIDATE_KEYS, "freeze candidate")
    if candidate["candidate_id"] != _self_omission_content_id(
        candidate,
        "candidate_id",
        "freeze candidate verification",
    ):
        _fail("candidate_id mismatch")
    root = _require_repository_root(repo_root)
    _verify_candidate_core(candidate, root, external_acquisition_verifier)


def _validate_authority_locator(
    locator: Mapping[str, Any],
    context: str,
) -> dict[str, Any]:
    _require_exact_keys(locator, _AUTHORITY_LOCATOR_KEYS, context)
    if (
        locator["capture_source"]
        != "PREAUTHORIZED_APPEND_ONLY_CODEX_EVENT_SOURCE"
    ):
        _fail(f"{context}.capture_source mismatch")
    for key in (
        "authority_source_id",
        "authority_policy_id",
        "authority_event_id",
        "reviewer_task_path",
        "parent_thread_id",
        "parent_spawn_tool_call_id",
        "parent_delivery_tool_call_id",
        "reviewer_thread_id",
        "reviewer_session_id",
        "reviewer_turn_id",
        "reviewer_item_id",
    ):
        _validate_opaque_id(locator[key], f"{context}.{key}")
    timestamp_keys = (
        "reviewer_turn_started_at_unix_seconds",
        "reviewer_turn_completed_at_unix_seconds",
        "reviewer_item_started_at_unix_ms",
        "reviewer_item_completed_at_unix_ms",
    )
    for key in timestamp_keys:
        if (
            not isinstance(locator[key], int)
            or isinstance(locator[key], bool)
            or locator[key] < 0
            ):
            _fail(f"{context}.{key} must be a nonnegative integer")
    if (
        not isinstance(locator["authority_event_sequence"], int)
        or isinstance(locator["authority_event_sequence"], bool)
        or locator["authority_event_sequence"] < 0
    ):
        _fail(f"{context}.authority_event_sequence must be a nonnegative integer")
    _parse_utc(
        locator["authority_committed_at_utc"],
        f"{context}.authority_committed_at_utc",
    )
    if (
        not isinstance(locator["codex_cli_version"], str)
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", locator["codex_cli_version"])
        is None
    ):
        _fail(f"{context}.codex_cli_version must be an exact stable version")
    _validate_content_id(
        locator["codex_app_server_protocol_semantic_sha256"],
        f"{context}.codex_app_server_protocol_semantic_sha256",
    )
    if (
        locator["reviewer_turn_completed_at_unix_seconds"]
        < locator["reviewer_turn_started_at_unix_seconds"]
    ):
        _fail(f"{context} reviewer turn completion predates its start")
    if (
        locator["reviewer_item_started_at_unix_ms"]
        < locator["reviewer_turn_started_at_unix_seconds"] * 1000
    ):
        _fail(f"{context} reviewer item predates its turn")
    if (
        locator["reviewer_item_completed_at_unix_ms"]
        < locator["reviewer_item_started_at_unix_ms"]
    ):
        _fail(f"{context} reviewer item completion predates its start")
    if (
        locator["reviewer_item_completed_at_unix_ms"]
        >= (locator["reviewer_turn_completed_at_unix_seconds"] + 1) * 1000
    ):
        _fail(f"{context} reviewer item completes after its turn")
    if locator["reviewer_turn_status"] != "completed":
        _fail(f"{context}.reviewer_turn_status mismatch")
    if locator["reviewer_item_type"] != "agentMessage":
        _fail(f"{context}.reviewer_item_type mismatch")
    if locator["reviewer_item_phase"] != "final_answer":
        _fail(f"{context}.reviewer_item_phase mismatch")
    if locator["delivery_kind"] != "AGENT_MESSAGE_FINAL_ANSWER":
        _fail(f"{context}.delivery_kind mismatch")
    return copy.deepcopy(dict(locator))


def _require_authoritative_event(
    locator: Mapping[str, Any],
    raw: bytes,
    reader: AuthorityEventReader | None,
) -> None:
    if reader is None:
        _fail(
            "authority_event_reader is required; a local PASS file, local "
            "app-server response, rollout JSONL, opaque attestation token, "
            "or caller verdict is not an append-only Codex authority"
        )
    try:
        authoritative_raw = reader(copy.deepcopy(dict(locator)))
    except Exception as error:
        raise FreezeError(f"authority event read failed: {error}") from error
    if type(authoritative_raw) is not bytes:
        _fail(
            "authority_event_reader must return exact authoritative event "
            "bytes; boolean or narrative verification is forbidden"
        )
    if not hmac.compare_digest(authoritative_raw, raw):
        _fail(
            "reviewer final event bytes do not match the exact event read "
            "from the preauthorized append-only authority"
        )


def _validate_review_artifact_binding(
    binding: Mapping[str, Any],
    *,
    repo_root: Path,
    external_acquisition_verifier: ExternalAcquisitionVerifier | None,
) -> dict[str, Any]:
    _require_exact_keys(binding, _REVIEW_ARTIFACT_KEYS, "review artifact binding")
    logical_path = _validate_logical_path(
        binding["logical_path"],
        "review artifact logical_path",
    )
    if not isinstance(binding["locator"], Mapping):
        _fail("review artifact locator must be an object")
    locator = copy.deepcopy(dict(binding["locator"]))
    _validate_locator(locator, "review artifact locator")
    if locator["kind"] == "REPOSITORY":
        if logical_path != f"repo:/{locator['repository_path']}":
            _fail("review artifact logical/locator mismatch")
    elif not logical_path.startswith("external:/"):
        _fail("external review artifact must use an external:/ logical path")
    raw = _read_locator(
        repo_root,
        locator,
        "review artifact",
        external_acquisition_verifier,
    )
    if not raw:
        _fail("review artifact is empty")
    if binding["byte_size"] != len(raw):
        _fail("review artifact byte_size mismatch")
    if binding["raw_sha256"] != _sha256(raw):
        _fail("review artifact raw_sha256 mismatch")
    return copy.deepcopy(dict(binding))


def _parse_and_validate_final_event(
    raw: bytes,
    *,
    candidate: Mapping[str, Any],
    repo_root: Path,
    external_acquisition_verifier: ExternalAcquisitionVerifier | None,
    authority_event_reader: AuthorityEventReader | None,
) -> dict[str, Any]:
    event = parse_json_no_duplicates(raw, context="reviewer final event")
    if not isinstance(event, Mapping):
        _fail("reviewer final event must be a JSON object")
    canonical = _jcs(event, "reviewer final event")
    if canonical != raw:
        _fail("reviewer final event bytes are not exact RFC 8785 canonical JCS")
    _require_exact_keys(event, _FINAL_EVENT_KEYS, "reviewer final event")
    if event["schema_version"] != "Phase0ReviewFinalEvent.v1":
        _fail("reviewer final event schema_version mismatch")
    locator = _validate_authority_locator(
        event["authority_locator"],
        "reviewer final event authority_locator",
    )
    _require_authoritative_event(locator, raw, authority_event_reader)
    if (
        locator["parent_thread_id"]
        != candidate["freeze_producer_identity"]["thread_id"]
    ):
        _fail("reviewer final event parent thread does not bind the freeze producer")
    if locator["reviewer_thread_id"] == locator["parent_thread_id"]:
        _fail("reviewer final event must come from a thread independent of its parent")
    if event["freeze_root_id"] != candidate["freeze_root_id"]:
        _fail("reviewer final event freeze root mismatch")
    if (
        event["code_absence_proof_id"]
        != candidate["code_absence_proof"]["code_absence_proof_id"]
    ):
        _fail("reviewer final event code absence proof mismatch")
    _validate_review_artifact_binding(
        event["review_artifact"],
        repo_root=repo_root,
        external_acquisition_verifier=external_acquisition_verifier,
    )
    if event["verdict"] != "PASS":
        _fail("reviewer final event verdict must be PASS")
    if event["open_blocker_ids"] != []:
        _fail("reviewer final event must have zero open blockers")
    reviewed_at = _parse_utc(
        event["reviewed_at_utc"],
        "reviewer final event reviewed_at_utc",
    )
    freeze_time = _parse_utc(candidate["freeze_time_utc"], "freeze_time_utc")
    item_started_at = _datetime.datetime.fromtimestamp(
        locator["reviewer_item_started_at_unix_ms"] / 1000,
        tz=_datetime.timezone.utc,
    )
    item_completed_at = _datetime.datetime.fromtimestamp(
        locator["reviewer_item_completed_at_unix_ms"] / 1000,
        tz=_datetime.timezone.utc,
    )
    authority_committed_at = _parse_utc(
        locator["authority_committed_at_utc"],
        "authority_committed_at_utc",
    )
    if reviewed_at < freeze_time:
        _fail("reviewer final event predates the freeze candidate")
    if item_started_at < freeze_time:
        _fail("reviewer final item predates the freeze candidate")
    if reviewed_at > item_completed_at:
        _fail("reviewed_at_utc is later than authoritative item completion")
    if authority_committed_at < item_completed_at:
        _fail("authority commit predates authoritative item completion")
    reviewer = {
        "reviewer_thread_id": locator["reviewer_thread_id"],
        "reviewer_session_id": locator["reviewer_session_id"],
        "reviewer_turn_id": locator["reviewer_turn_id"],
    }
    _require_independent_reviewer(
        reviewer,
        candidate["freeze_producer_identity"],
        "final reviewer",
    )
    return copy.deepcopy(dict(event))


def finalize_freeze_record(
    candidate: Mapping[str, Any],
    *,
    repo_root: Path | str,
    reviewer_final_event_path: Path | str,
    recorded_at_utc: str,
    external_acquisition_verifier: ExternalAcquisitionVerifier | None = None,
) -> dict[str, Any]:
    """Fail closed until a concrete independent authority adapter exists.

    A caller-supplied boolean verifier, exact-byte reader, environment flag, or
    local Codex history reader would let the caller echo forged bytes.  None is
    an authority boundary.  A later production implementation must hard-bind a
    concrete independently operated source, or verify a self-contained external
    proof, before this public entry point may construct a record.
    """

    del (
        candidate,
        repo_root,
        reviewer_final_event_path,
        recorded_at_utc,
        external_acquisition_verifier,
    )
    _fail(
        "AUTHORITY_UNVERIFIED: production authority adapter is unavailable; "
        "Phase 0A freeze must remain PENDING and caller-supplied authority "
        "verification is forbidden"
    )


def _finalize_freeze_record_with_test_authority_reader(
    candidate: Mapping[str, Any],
    *,
    repo_root: Path | str,
    reviewer_final_event_path: Path | str,
    recorded_at_utc: str,
    external_acquisition_verifier: ExternalAcquisitionVerifier | None = None,
    authority_event_reader: AuthorityEventReader | None = None,
) -> dict[str, Any]:
    """Exercise record construction with a synthetic authority in unit tests.

    This is not a production authority adapter and MUST NOT be called by
    product, release, validator, migration, or operator code.  The returned
    object is deliberately marked with a state rejected by the production
    Phase0FreezeRecord.v1 schema, so this seam cannot emit a production-shaped
    frozen record.
    """

    root = _require_repository_root(repo_root)
    verify_freeze_candidate(
        candidate,
        repo_root=root,
        external_acquisition_verifier=external_acquisition_verifier,
    )
    event_path = Path(reviewer_final_event_path)
    if not event_path.is_absolute():
        _fail("reviewer_final_event_path must be absolute")
    if _absolute_path_has_link_or_junction(event_path):
        _fail(
            "reviewer final event path traverses a symlink, junction, "
            "or reparse point"
        )
    try:
        resolved_event_path = event_path.resolve(strict=True)
    except OSError as error:
        raise FreezeError(f"reviewer final event is unavailable: {error}") from error
    if not resolved_event_path.is_file() or resolved_event_path.is_symlink():
        _fail("reviewer final event must be a regular non-link file")
    try:
        event_raw = resolved_event_path.read_bytes()
    except OSError as error:
        raise FreezeError(f"reviewer final event cannot be read: {error}") from error
    event = _parse_and_validate_final_event(
        event_raw,
        candidate=candidate,
        repo_root=root,
        external_acquisition_verifier=external_acquisition_verifier,
        authority_event_reader=authority_event_reader,
    )
    recorded_at = _parse_utc(recorded_at_utc, "authority recorded_at_utc")
    reviewed_at = _parse_utc(event["reviewed_at_utc"], "reviewed_at_utc")
    if recorded_at < reviewed_at:
        _fail("authority recorded_at_utc cannot predate reviewer reviewed_at_utc")
    locator = event["authority_locator"]
    item_completed_at = _datetime.datetime.fromtimestamp(
        locator["reviewer_item_completed_at_unix_ms"] / 1000,
        tz=_datetime.timezone.utc,
    )
    if recorded_at < item_completed_at:
        _fail("authority recorded_at_utc cannot predate item completion")
    authority_committed_at = _parse_utc(
        locator["authority_committed_at_utc"],
        "authority_committed_at_utc",
    )
    if recorded_at < authority_committed_at:
        _fail("authority recorded_at_utc cannot predate authority commit")
    review_anchor = {
        "review_outcome": "PASS",
        "open_blocker_ids": [],
        "capture_source": locator["capture_source"],
        "authority_source_id": locator["authority_source_id"],
        "authority_policy_id": locator["authority_policy_id"],
        "authority_event_id": locator["authority_event_id"],
        "authority_event_sequence": locator["authority_event_sequence"],
        "authority_committed_at_utc": locator["authority_committed_at_utc"],
        "codex_cli_version": locator["codex_cli_version"],
        "codex_app_server_protocol_semantic_sha256": locator[
            "codex_app_server_protocol_semantic_sha256"
        ],
        "reviewer_task_path": locator["reviewer_task_path"],
        "parent_thread_id": locator["parent_thread_id"],
        "parent_spawn_tool_call_id": locator["parent_spawn_tool_call_id"],
        "parent_delivery_tool_call_id": locator[
            "parent_delivery_tool_call_id"
        ],
        "reviewer_thread_id": locator["reviewer_thread_id"],
        "reviewer_session_id": locator["reviewer_session_id"],
        "reviewer_turn_id": locator["reviewer_turn_id"],
        "reviewer_item_id": locator["reviewer_item_id"],
        "reviewer_turn_started_at_unix_seconds": locator[
            "reviewer_turn_started_at_unix_seconds"
        ],
        "reviewer_turn_completed_at_unix_seconds": locator[
            "reviewer_turn_completed_at_unix_seconds"
        ],
        "reviewer_item_started_at_unix_ms": locator[
            "reviewer_item_started_at_unix_ms"
        ],
        "reviewer_item_completed_at_unix_ms": locator[
            "reviewer_item_completed_at_unix_ms"
        ],
        "reviewer_turn_status": "completed",
        "reviewer_item_type": "agentMessage",
        "reviewer_item_phase": "final_answer",
        "delivery_kind": "AGENT_MESSAGE_FINAL_ANSWER",
        "review_artifact": copy.deepcopy(event["review_artifact"]),
        "reviewed_freeze_root_id": candidate["freeze_root_id"],
        "reviewed_code_absence_proof_id": event["code_absence_proof_id"],
        "reviewed_at_utc": event["reviewed_at_utc"],
    }
    authority_anchor = {
        "authority": "PREAUTHORIZED_APPEND_ONLY_CODEX_EVENT_SOURCE",
        "authority_locator": copy.deepcopy(locator),
        "anchor_event_encoding": "UTF8_JCS_RFC8785",
        "anchor_event_preimage": copy.deepcopy(event),
        "anchor_event_raw_base64": base64.b64encode(event_raw).decode("ascii"),
        "anchor_event_byte_size": len(event_raw),
        "anchor_event_raw_sha256": _sha256(event_raw),
        "recorded_at_utc": recorded_at_utc,
    }
    record: dict[str, Any] = {
        "schema_version": "Phase0FreezeRecord.v1",
        "freeze_state": "FROZEN_REVIEWED_ANCHORED",
        "canonicalization": "JCS-RFC8785",
        "freeze_base_commit": candidate["freeze_base_commit"],
        "freeze_base_tree": candidate["freeze_base_tree"],
        "freeze_time_utc": candidate["freeze_time_utc"],
        "freeze_inputs": copy.deepcopy(candidate["freeze_inputs"]),
        "freeze_root_id": candidate["freeze_root_id"],
        "code_absence_proof": copy.deepcopy(candidate["code_absence_proof"]),
        "freeze_producer_identity": copy.deepcopy(
            candidate["freeze_producer_identity"]
        ),
        "review_anchor": review_anchor,
        "authority_anchor": authority_anchor,
        "implementation_order_constraint": copy.deepcopy(_IMPLEMENTATION_ORDER),
    }
    record["freeze_record_id"] = _self_omission_content_id(
        record,
        "freeze_record_id",
        "Phase 0A freeze record",
    )
    _verify_freeze_record_with_test_authority_reader(
        record,
        repo_root=root,
        freeze_producer_identity=candidate["freeze_producer_identity"],
        external_acquisition_verifier=external_acquisition_verifier,
        authority_event_reader=authority_event_reader,
    )
    record["freeze_state"] = _TEST_ONLY_FREEZE_STATE
    record["freeze_record_id"] = _self_omission_content_id(
        record,
        "freeze_record_id",
        "test-only Phase 0A structural record",
    )
    return record


def verify_freeze_record(
    record: Mapping[str, Any],
    *,
    repo_root: Path | str,
    freeze_producer_identity: Mapping[str, Any] | None = None,
    external_acquisition_verifier: ExternalAcquisitionVerifier | None = None,
) -> None:
    """Fail closed until external authority proof verification is concrete."""

    del (
        record,
        repo_root,
        freeze_producer_identity,
        external_acquisition_verifier,
    )
    _fail(
        "AUTHORITY_UNVERIFIED: production authority adapter is unavailable; "
        "a frozen record cannot be verified from local bytes or "
        "caller-supplied authority assertions"
    )


def _verify_freeze_record_with_test_authority_reader(
    record: Mapping[str, Any],
    *,
    repo_root: Path | str,
    freeze_producer_identity: Mapping[str, Any] | None = None,
    external_acquisition_verifier: ExternalAcquisitionVerifier | None = None,
    authority_event_reader: AuthorityEventReader | None = None,
) -> None:
    """Exercise record verification with a synthetic authority in unit tests.

    This private seam validates structural and byte bindings but establishes no
    production provenance.  It accepts the schema-invalid test-only state
    returned by the synthetic constructor solely to support negative tests.
    """

    _require_exact_keys(record, _FREEZE_RECORD_KEYS, "Phase 0A freeze record")
    if record["freeze_record_id"] != _self_omission_content_id(
        record,
        "freeze_record_id",
        "Phase 0A freeze record verification",
    ):
        _fail("freeze_record_id mismatch")
    if record["schema_version"] != "Phase0FreezeRecord.v1":
        _fail("freeze record schema_version mismatch")
    if record["freeze_state"] not in {
        "FROZEN_REVIEWED_ANCHORED",
        _TEST_ONLY_FREEZE_STATE,
    }:
        _fail("freeze record state mismatch")
    if record["canonicalization"] != "JCS-RFC8785":
        _fail("freeze record canonicalization mismatch")
    if record["implementation_order_constraint"] != _IMPLEMENTATION_ORDER:
        _fail("implementation_order_constraint mismatch")

    producer = _validate_producer_identity(record["freeze_producer_identity"])
    if freeze_producer_identity is not None:
        external_producer = _validate_producer_identity(
            freeze_producer_identity
        )
        if external_producer != producer:
            _fail(
                "external freeze_producer_identity does not match the "
                "persisted record identity"
            )
    candidate_core = {
        "schema_version": "Phase0FreezeCandidate.v1",
        "freeze_state": "CANDIDATE_AWAITING_INDEPENDENT_REVIEW",
        "canonicalization": record["canonicalization"],
        "freeze_base_commit": record["freeze_base_commit"],
        "freeze_base_tree": record["freeze_base_tree"],
        "freeze_time_utc": record["freeze_time_utc"],
        "freeze_inputs": copy.deepcopy(record["freeze_inputs"]),
        "freeze_root_id": record["freeze_root_id"],
        "code_absence_proof": copy.deepcopy(record["code_absence_proof"]),
        "freeze_producer_identity": producer,
    }
    _verify_candidate_core(
        candidate_core,
        _require_repository_root(repo_root),
        external_acquisition_verifier,
    )

    review_anchor = record["review_anchor"]
    authority_anchor = record["authority_anchor"]
    _require_exact_keys(review_anchor, _REVIEW_ANCHOR_KEYS, "review anchor")
    _require_exact_keys(authority_anchor, _AUTHORITY_ANCHOR_KEYS, "authority anchor")
    if review_anchor["review_outcome"] != "PASS":
        _fail("review anchor outcome mismatch")
    if review_anchor["open_blocker_ids"] != []:
        _fail("review anchor contains blockers")
    if review_anchor["delivery_kind"] != "AGENT_MESSAGE_FINAL_ANSWER":
        _fail("review anchor delivery kind mismatch")
    if review_anchor["reviewed_freeze_root_id"] != record["freeze_root_id"]:
        _fail("review anchor freeze root mismatch")
    if (
        review_anchor["reviewed_code_absence_proof_id"]
        != record["code_absence_proof"]["code_absence_proof_id"]
    ):
        _fail("review anchor code absence proof mismatch")

    if (
        authority_anchor["authority"]
        != "PREAUTHORIZED_APPEND_ONLY_CODEX_EVENT_SOURCE"
    ):
        _fail("authority anchor authority mismatch")
    if authority_anchor["anchor_event_encoding"] != "UTF8_JCS_RFC8785":
        _fail("authority anchor encoding mismatch")
    locator = _validate_authority_locator(
        authority_anchor["authority_locator"],
        "authority anchor locator",
    )
    try:
        event_raw = base64.b64decode(
            authority_anchor["anchor_event_raw_base64"],
            validate=True,
        )
    except (TypeError, ValueError) as error:
        raise FreezeError("authority anchor event base64 is invalid") from error
    if authority_anchor["anchor_event_byte_size"] != len(event_raw):
        _fail("authority anchor event byte_size mismatch")
    if authority_anchor["anchor_event_raw_sha256"] != _sha256(event_raw):
        _fail("authority anchor event raw_sha256 mismatch")
    event = parse_json_no_duplicates(event_raw, context="embedded reviewer final event")
    if _jcs(event, "embedded reviewer final event") != event_raw:
        _fail("embedded reviewer final event is not exact canonical JCS")
    if event != authority_anchor["anchor_event_preimage"]:
        _fail("authority anchor event preimage/raw mismatch")

    root = _require_repository_root(repo_root)
    candidate_with_identity = dict(candidate_core)
    candidate_with_identity["candidate_id"] = _self_omission_content_id(
        candidate_with_identity,
        "candidate_id",
        "derived candidate",
    )
    validated_event = _parse_and_validate_final_event(
        event_raw,
        candidate=candidate_with_identity,
        repo_root=root,
        external_acquisition_verifier=external_acquisition_verifier,
        authority_event_reader=authority_event_reader,
    )
    if validated_event != event:
        _fail("authority anchor final event changed during validation")
    if locator != event["authority_locator"]:
        _fail("authority locator/final event mismatch")

    review_locator_projection = {
        "capture_source": review_anchor["capture_source"],
        "authority_source_id": review_anchor["authority_source_id"],
        "authority_policy_id": review_anchor["authority_policy_id"],
        "authority_event_id": review_anchor["authority_event_id"],
        "authority_event_sequence": review_anchor["authority_event_sequence"],
        "authority_committed_at_utc": review_anchor[
            "authority_committed_at_utc"
        ],
        "codex_cli_version": review_anchor["codex_cli_version"],
        "codex_app_server_protocol_semantic_sha256": review_anchor[
            "codex_app_server_protocol_semantic_sha256"
        ],
        "reviewer_task_path": review_anchor["reviewer_task_path"],
        "parent_thread_id": review_anchor["parent_thread_id"],
        "parent_spawn_tool_call_id": review_anchor[
            "parent_spawn_tool_call_id"
        ],
        "parent_delivery_tool_call_id": review_anchor[
            "parent_delivery_tool_call_id"
        ],
        "reviewer_thread_id": review_anchor["reviewer_thread_id"],
        "reviewer_session_id": review_anchor["reviewer_session_id"],
        "reviewer_turn_id": review_anchor["reviewer_turn_id"],
        "reviewer_item_id": review_anchor["reviewer_item_id"],
        "reviewer_turn_started_at_unix_seconds": review_anchor[
            "reviewer_turn_started_at_unix_seconds"
        ],
        "reviewer_turn_completed_at_unix_seconds": review_anchor[
            "reviewer_turn_completed_at_unix_seconds"
        ],
        "reviewer_item_started_at_unix_ms": review_anchor[
            "reviewer_item_started_at_unix_ms"
        ],
        "reviewer_item_completed_at_unix_ms": review_anchor[
            "reviewer_item_completed_at_unix_ms"
        ],
        "reviewer_turn_status": review_anchor["reviewer_turn_status"],
        "reviewer_item_type": review_anchor["reviewer_item_type"],
        "reviewer_item_phase": review_anchor["reviewer_item_phase"],
        "delivery_kind": review_anchor["delivery_kind"],
    }
    authority_locator_projection = {
        key: locator[key] for key in review_locator_projection
    }
    if review_locator_projection != authority_locator_projection:
        _fail("review anchor/authority locator identity mismatch")
    if review_anchor["review_artifact"] != event["review_artifact"]:
        _fail("review anchor/final event artifact mismatch")
    if review_anchor["reviewed_at_utc"] != event["reviewed_at_utc"]:
        _fail("review anchor/final event UTC mismatch")
    freeze_time = _parse_utc(record["freeze_time_utc"], "freeze_time_utc")
    reviewed_at = _parse_utc(review_anchor["reviewed_at_utc"], "reviewed_at_utc")
    recorded_at = _parse_utc(
        authority_anchor["recorded_at_utc"],
        "authority recorded_at_utc",
    )
    if reviewed_at < freeze_time or recorded_at < reviewed_at:
        _fail("freeze/review/recorded UTC ordering mismatch")
