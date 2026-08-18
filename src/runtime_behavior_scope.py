from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from path_security import PathSecurityError, lexical_absolute, read_regular_file, require_no_reparse


SCOPE_POLICY_RELATIVE_PATH = Path(
    ".aegis/reasoning_ledger/artifacts/facts/runtime-behavior-scope.json"
)
SCOPE_POLICY_SCHEMA = "aegis.runtime_behavior_scope_definition.v1"
SCOPE_DECISION_RELATIVE_PATH = Path(
    ".aegis/reasoning_ledger/artifacts/facts/runtime-behavior-scope-decision.json"
)
SCOPE_REVIEW_RELATIVE_PATH = Path(
    ".aegis/reasoning_ledger/artifacts/reviews/runtime-behavior-scope-review.md"
)
SCOPE_REVIEW_RESULT_RELATIVE_PATH = Path(
    ".aegis/reasoning_ledger/artifacts/reviews/runtime-behavior-scope-review.json"
)
SCOPE_USER_CONFIRMATION_RELATIVE_PATH = Path(
    ".aegis/reasoning_ledger/artifacts/facts/runtime-behavior-scope-user-confirmation.json"
)
SCOPE_REVIEW_RESULT_SCHEMA = "aegis.runtime_behavior_scope_review.v1"
SCOPE_USER_CONFIRMATION_SCHEMA = "aegis.runtime_behavior_scope_user_confirmation.v1"
SCOPE_DECISION_SCHEMA = "aegis.runtime_behavior_scope_decision.v3"
RESOLVED_MANIFEST_SCHEMA = "aegis.resolved_runtime_behavior_scope.v3"

_HEX_16_PATTERN = re.compile(r"[0-9a-f]{32}")
_HEX_32_PATTERN = re.compile(r"[0-9a-f]{64}")
_TOP_LEVEL_FIELDS = {
    "schema",
    "project_id_hex",
    "version",
    "include_roots",
    "include_files",
    "exclude_roots",
    "exclude_files",
    "force_include_files",
    "external_tools",
    "runtime_authority_id",
}


class RuntimeBehaviorScopeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RuntimeFileEntry:
    path: str
    content: bytes
    sha256: str

    @property
    def size(self) -> int:
        return len(self.content)


@dataclass(frozen=True, slots=True)
class ResolvedRuntimeBehaviorScope:
    project_id_hex: str
    policy_version: int
    policy_path: Path
    policy_sha256: str
    decision_sha256: str | None
    manifest_sha256: str
    git_sha256: str
    git_runtime_sha256: str
    runtime_authority_id: str
    entries: tuple[RuntimeFileEntry, ...]

    def seal_entries(self) -> list[tuple[str, bytes]]:
        if self.decision_sha256 is None:
            raise RuntimeBehaviorScopeError(
                "runtime behavior scope has no approved approval decision"
            )
        entries = [(entry.path, entry.content) for entry in self.entries]
        entries.extend(
            (
                (
                    "aegis-meta/runtime-behavior-scope-policy.sha256",
                    (self.policy_sha256 + "\n").encode("ascii"),
                ),
                (
                    "aegis-meta/runtime-behavior-scope-decision.sha256",
                    (self.decision_sha256 + "\n").encode("ascii"),
                ),
                (
                    "aegis-meta/runtime-behavior-scope-manifest.sha256",
                    (self.manifest_sha256 + "\n").encode("ascii"),
                ),
            )
        )
        return entries

    def manifest_data(self) -> dict[str, object]:
        return {
            "schema": RESOLVED_MANIFEST_SCHEMA,
            "project_id_hex": self.project_id_hex,
            "policy_version": self.policy_version,
            "policy_path": self.policy_path.as_posix(),
            "policy_sha256": self.policy_sha256,
            "approval_decision_sha256": self.decision_sha256,
            "manifest_sha256": self.manifest_sha256,
            "entries": [
                {"path": entry.path, "size": entry.size, "sha256": entry.sha256}
                for entry in self.entries
            ],
        }


def resolve_runtime_behavior_scope(
    project_root: str | Path,
    project_id: bytes,
) -> ResolvedRuntimeBehaviorScope:
    return _resolve_runtime_behavior_scope(
        project_root, project_id, approval_required=True
    )


def resolve_runtime_behavior_scope_definition(
    project_root: str | Path,
    project_id: bytes,
) -> ResolvedRuntimeBehaviorScope:
    """Resolve the canonical definition without accepting it for production."""
    return _resolve_runtime_behavior_scope(
        project_root, project_id, approval_required=False
    )


def _resolve_runtime_behavior_scope(
    project_root: str | Path,
    project_id: bytes,
    *,
    approval_required: bool,
) -> ResolvedRuntimeBehaviorScope:
    if not isinstance(project_id, bytes) or len(project_id) != 16:
        raise ValueError("project_id must contain exactly 16 bytes")
    root = lexical_absolute(project_root)
    if not root.is_dir():
        raise RuntimeBehaviorScopeError(f"project root is not a directory: {root}")
    try:
        require_no_reparse(root, root, label="project root")
    except PathSecurityError as error:
        raise RuntimeBehaviorScopeError(str(error)) from error
    policy_path = root / SCOPE_POLICY_RELATIVE_PATH
    if approval_required:
        (
            payload,
            canonical_policy,
            policy_sha256,
            decision_sha256,
        ) = _load_and_validate_policy(root)
    else:
        payload, canonical_policy = _load_policy(
            root, root / SCOPE_POLICY_RELATIVE_PATH
        )
        policy_sha256 = hashlib.sha256(canonical_policy).hexdigest()
        decision_sha256 = None
    project_id_hex = project_id.hex()
    if payload["project_id_hex"] != project_id_hex:
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope project identity does not match the seal chain"
        )
    external_tools = payload["external_tools"]
    if (
        not isinstance(external_tools, dict)
        or set(external_tools) != {"git_sha256", "git_runtime_sha256"}
        or not isinstance(external_tools["git_sha256"], str)
        or _HEX_32_PATTERN.fullmatch(external_tools["git_sha256"]) is None
        or not isinstance(external_tools["git_runtime_sha256"], str)
        or _HEX_32_PATTERN.fullmatch(external_tools["git_runtime_sha256"]) is None
    ):
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope has an invalid Git trust pin"
        )
    runtime_authority_id = payload["runtime_authority_id"]
    if (
        not isinstance(runtime_authority_id, str)
        or _HEX_16_PATTERN.fullmatch(runtime_authority_id) is None
    ):
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope has an invalid runtime authority ID"
        )

    include_roots = _path_list(payload, "include_roots", allow_reasoning=False)
    include_files = _path_list(payload, "include_files", allow_reasoning=False)
    exclude_roots = _path_list(payload, "exclude_roots", allow_reasoning=True)
    exclude_files = _path_list(payload, "exclude_files", allow_reasoning=True)
    force_files = _path_list(
        payload, "force_include_files", allow_reasoning=False
    )
    selected: dict[str, Path] = {}

    for logical_root in include_roots:
        scope_root = root / Path(logical_root)
        if not scope_root.exists():
            raise RuntimeBehaviorScopeError(
                f"runtime behavior scope root is missing: {logical_root}"
            )
        try:
            require_no_reparse(root, scope_root, label="runtime behavior scope root")
        except PathSecurityError as error:
            raise RuntimeBehaviorScopeError(str(error)) from error
        if not scope_root.is_dir():
            raise RuntimeBehaviorScopeError(
                f"runtime behavior scope root is not a real directory: {logical_root}"
            )
        _reject_executable_bytecode_cache(scope_root, root)
        for path in scope_root.rglob("*"):
            logical_path = path.relative_to(root).as_posix()
            if _is_excluded(logical_path, exclude_roots, exclude_files):
                continue
            _add_selected_file(
                selected, root, logical_path, allow_directory=True
            )

    for logical_path in include_files:
        validated_file: dict[str, Path] = {}
        _add_selected_file(
            validated_file, root, logical_path, allow_directory=False
        )
        if not _is_excluded(logical_path, exclude_roots, exclude_files):
            selected.update(validated_file)
    for logical_path in force_files:
        _add_selected_file(
            selected, root, logical_path, allow_directory=False
        )

    if not selected:
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope resolved to an empty file set"
        )

    entries: list[RuntimeFileEntry] = []
    for logical_path in sorted(selected, key=lambda value: value.encode("utf-8")):
        try:
            content, _identity = read_regular_file(
                selected[logical_path],
                allowed_root=root,
                label=f"runtime behavior scope file {logical_path}",
            )
        except PathSecurityError as error:
            raise RuntimeBehaviorScopeError(str(error)) from error
        entries.append(
            RuntimeFileEntry(
                path=logical_path,
                content=content,
                sha256=hashlib.sha256(content).hexdigest(),
            )
        )

    manifest_body = {
        "schema": RESOLVED_MANIFEST_SCHEMA,
        "project_id_hex": project_id_hex,
        "policy_version": payload["version"],
        "policy_sha256": policy_sha256,
        "approval_decision_sha256": decision_sha256,
        "entries": [
            {"path": entry.path, "size": entry.size, "sha256": entry.sha256}
            for entry in entries
        ],
    }
    manifest_sha256 = hashlib.sha256(
        _canonical_json_bytes(manifest_body)
    ).hexdigest()
    return ResolvedRuntimeBehaviorScope(
        project_id_hex=project_id_hex,
        policy_version=int(payload["version"]),
        policy_path=SCOPE_POLICY_RELATIVE_PATH,
        policy_sha256=policy_sha256,
        decision_sha256=decision_sha256,
        manifest_sha256=manifest_sha256,
        git_sha256=str(external_tools["git_sha256"]),
        git_runtime_sha256=str(external_tools["git_runtime_sha256"]),
        runtime_authority_id=runtime_authority_id,
        entries=tuple(entries),
    )


def runtime_behavior_path_is_selected(
    project_root: str | Path,
    project_id: bytes,
    logical_path: str,
) -> bool:
    """Return whether a file path belongs to the confirmed runtime scope.

    This predicate is also used for deleted Git paths, which cannot be found by
    live-tree enumeration.
    """
    if not isinstance(project_id, bytes) or len(project_id) != 16:
        raise ValueError("project_id must contain exactly 16 bytes")
    normalized = _normalize_logical_path(logical_path, "git path")
    root = lexical_absolute(project_root)
    payload, _canonical, _digest, _decision_digest = _load_and_validate_policy(root)
    if payload["project_id_hex"] != project_id.hex():
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope project identity does not match the seal chain"
        )
    include_roots = _path_list(payload, "include_roots", allow_reasoning=False)
    include_files = _path_list(payload, "include_files", allow_reasoning=False)
    exclude_roots = _path_list(payload, "exclude_roots", allow_reasoning=True)
    exclude_files = _path_list(payload, "exclude_files", allow_reasoning=True)
    force_files = _path_list(payload, "force_include_files", allow_reasoning=False)
    if normalized in force_files:
        return True
    selected = normalized in include_files or any(
        normalized == candidate or normalized.startswith(candidate + "/")
        for candidate in include_roots
    )
    return selected and not _is_excluded(
        normalized, exclude_roots, exclude_files
    )


def _reject_executable_bytecode_cache(scope_root: Path, project_root: Path) -> None:
    offenders = [
        path.relative_to(project_root).as_posix()
        for path in scope_root.rglob("*")
        if path.name.casefold() == "__pycache__"
        or (path.is_file() and path.suffix.casefold() in {".pyc", ".pyo"})
    ]
    if offenders:
        raise RuntimeBehaviorScopeError(
            "runtime behavior roots contain executable Python bytecode cache: "
            + ", ".join(sorted(offenders)[:20])
        )


def _load_policy(root: Path, path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        encoded, _identity = read_regular_file(
            path,
            allowed_root=root,
            label="runtime behavior scope policy",
            max_bytes=1024 * 1024,
        )
        payload = json.loads(encoded.decode("utf-8", errors="strict"))
    except PathSecurityError as error:
        raise RuntimeBehaviorScopeError(str(error)) from error
    except (UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeBehaviorScopeError(
            f"runtime behavior scope policy cannot be read: {path}: {error}"
        ) from error
    if not isinstance(payload, dict) or set(payload) != _TOP_LEVEL_FIELDS:
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope policy has invalid top-level fields"
        )
    if payload["schema"] != SCOPE_POLICY_SCHEMA:
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope policy has an unsupported schema"
        )
    try:
        canonical = _canonical_json_bytes(payload)
    except (TypeError, ValueError) as error:
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope definition is not canonical JSON"
        ) from error
    if encoded != canonical:
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope definition is not canonical JSON"
        )
    if (
        not isinstance(payload["project_id_hex"], str)
        or _HEX_16_PATTERN.fullmatch(payload["project_id_hex"]) is None
    ):
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope policy has an invalid project ID"
        )
    version = payload["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope policy has an invalid version"
        )
    return payload, canonical


def _load_and_validate_policy(
    root: Path,
) -> tuple[dict[str, Any], bytes, str, str]:
    payload, canonical = _load_policy(root, root / SCOPE_POLICY_RELATIVE_PATH)
    digest = hashlib.sha256(canonical).hexdigest()
    decision_digest = _validate_scope_decision(root, payload, canonical, digest)
    return payload, canonical, digest, decision_digest


def _validate_scope_decision(
    root: Path,
    policy: dict[str, Any],
    policy_bytes: bytes,
    policy_sha256: str,
) -> str:
    review_report = _read_scope_evidence(
        root, SCOPE_REVIEW_RELATIVE_PATH, "runtime scope review"
    )
    review_result_bytes = _read_scope_evidence(
        root, SCOPE_REVIEW_RESULT_RELATIVE_PATH, "runtime scope review result"
    )
    review_result = _load_canonical_evidence_json(
        review_result_bytes, "runtime scope review result"
    )
    expected_review_fields = {
        "schema",
        "review_id",
        "project_id_hex",
        "scope_definition_sha256",
        "verdict",
        "report",
    }
    if set(review_result) != expected_review_fields:
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope review result has invalid fields"
        )
    review_id = review_result.get("review_id")
    if not isinstance(review_id, str) or not review_id.strip():
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope review result has no review ID"
        )
    if (
        review_result.get("schema") != SCOPE_REVIEW_RESULT_SCHEMA
        or review_result.get("project_id_hex") != policy["project_id_hex"]
        or review_result.get("scope_definition_sha256") != policy_sha256
    ):
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope review result does not bind the definition"
        )
    if review_result.get("verdict") != "PASS":
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope review did not pass"
        )
    if review_result.get("report") != _evidence_descriptor(
        SCOPE_REVIEW_RELATIVE_PATH, review_report
    ):
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope review result does not bind its report"
        )

    confirmation_bytes = _read_scope_evidence(
        root,
        SCOPE_USER_CONFIRMATION_RELATIVE_PATH,
        "runtime scope user confirmation",
    )
    confirmation = _load_canonical_evidence_json(
        confirmation_bytes, "runtime scope user confirmation"
    )
    expected_confirmation_fields = {
        "schema",
        "confirmation_id",
        "project_id_hex",
        "scope_definition_sha256",
        "review_result",
        "decision",
        "statement",
    }
    if set(confirmation) != expected_confirmation_fields:
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope user confirmation has invalid fields"
        )
    confirmation_id = confirmation.get("confirmation_id")
    statement = confirmation.get("statement")
    if not isinstance(confirmation_id, str) or not confirmation_id.strip():
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope user confirmation has no confirmation ID"
        )
    if not isinstance(statement, str) or not statement.strip():
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope user confirmation has no statement"
        )
    review_result_descriptor = _evidence_descriptor(
        SCOPE_REVIEW_RESULT_RELATIVE_PATH, review_result_bytes
    )
    if (
        confirmation.get("schema") != SCOPE_USER_CONFIRMATION_SCHEMA
        or confirmation.get("project_id_hex") != policy["project_id_hex"]
        or confirmation.get("scope_definition_sha256") != policy_sha256
        or confirmation.get("review_result") != review_result_descriptor
    ):
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope user confirmation does not bind the approved review"
        )
    if confirmation.get("decision") != "CONFIRMED":
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope user confirmation is not CONFIRMED"
        )

    decision_bytes = _read_scope_evidence(
        root, SCOPE_DECISION_RELATIVE_PATH, "runtime scope decision manifest"
    )
    decision = _load_canonical_evidence_json(
        decision_bytes, "runtime scope decision manifest"
    )
    expected_fields = {
        "schema",
        "project_id_hex",
        "decision",
        "scope_definition",
        "review_result",
        "user_confirmation",
    }
    if not isinstance(decision, dict) or set(decision) != expected_fields:
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope decision manifest has invalid fields"
        )
    expected = {
        "schema": SCOPE_DECISION_SCHEMA,
        "project_id_hex": policy["project_id_hex"],
        "decision": "APPROVED",
        "scope_definition": _evidence_descriptor(
            SCOPE_POLICY_RELATIVE_PATH, policy_bytes
        ),
        "review_result": review_result_descriptor,
        "user_confirmation": {
            **_evidence_descriptor(
                SCOPE_USER_CONFIRMATION_RELATIVE_PATH, confirmation_bytes
            ),
            "confirmation_id": confirmation_id,
        },
    }
    if decision != expected:
        raise RuntimeBehaviorScopeError(
            "runtime behavior scope decision manifest does not bind the approved policy"
        )
    return hashlib.sha256(decision_bytes).hexdigest()


def _load_canonical_evidence_json(content: bytes, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(content.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeBehaviorScopeError(f"{label} is invalid JSON") from error
    if not isinstance(payload, dict):
        raise RuntimeBehaviorScopeError(f"{label} must be a JSON object")
    try:
        canonical = _canonical_json_bytes(payload)
    except (TypeError, ValueError) as error:
        raise RuntimeBehaviorScopeError(f"{label} is not canonical JSON") from error
    if content != canonical:
        raise RuntimeBehaviorScopeError(f"{label} is not canonical JSON")
    return payload


def _evidence_descriptor(relative_path: Path, content: bytes) -> dict[str, object]:
    return {
        "path": relative_path.as_posix(),
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _read_scope_evidence(root: Path, relative_path: Path, label: str) -> bytes:
    try:
        content, _identity = read_regular_file(
            root / relative_path,
            allowed_root=root,
            label=label,
            max_bytes=16 * 1024 * 1024,
        )
    except PathSecurityError as error:
        raise RuntimeBehaviorScopeError(str(error)) from error
    if not content:
        raise RuntimeBehaviorScopeError(f"{label} is empty")
    return content


def _path_list(
    payload: dict[str, Any], field: str, *, allow_reasoning: bool
) -> tuple[str, ...]:
    value = payload[field]
    if not isinstance(value, list):
        raise RuntimeBehaviorScopeError(
            f"runtime behavior scope policy {field} must be a list"
        )
    normalized: list[str] = []
    for item in value:
        logical_path = _normalize_logical_path(item, field)
        folded_path = logical_path.casefold()
        if not allow_reasoning and (
            folded_path == ".aegis" or folded_path.startswith(".aegis/")
        ):
            raise RuntimeBehaviorScopeError(
                "reasoning ledger cannot be selected as runtime behavior code"
            )
        normalized.append(logical_path)
    if len(set(normalized)) != len(normalized):
        raise RuntimeBehaviorScopeError(
            f"runtime behavior scope policy {field} contains duplicates"
        )
    return tuple(normalized)


def _normalize_logical_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeBehaviorScopeError(
            f"runtime behavior scope policy {field} contains an invalid path"
        )
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise RuntimeBehaviorScopeError(
            f"runtime behavior scope policy {field} path is not UTF-8"
        ) from error
    path = PurePosixPath(value)
    if (
        value.startswith("/")
        or value.endswith("/")
        or "\\" in value
        or ":" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or path.as_posix() != value
    ):
        raise RuntimeBehaviorScopeError(
            f"runtime behavior scope policy {field} path is not normalized: {value}"
        )
    return value


def _is_excluded(
    logical_path: str,
    exclude_roots: Iterable[str],
    exclude_files: Iterable[str],
) -> bool:
    if logical_path in exclude_files:
        return True
    return any(
        logical_path == root or logical_path.startswith(root + "/")
        for root in exclude_roots
    )


def _add_selected_file(
    selected: dict[str, Path],
    root: Path,
    logical_path: str,
    *,
    allow_directory: bool,
) -> None:
    path = root / Path(logical_path)
    if not path.exists():
        raise RuntimeBehaviorScopeError(
            f"runtime behavior scope file is missing: {logical_path}"
        )
    try:
        require_no_reparse(root, path, label=f"runtime behavior scope file {logical_path}")
    except PathSecurityError as error:
        raise RuntimeBehaviorScopeError(str(error)) from error
    if path.is_dir():
        if allow_directory:
            return
        raise RuntimeBehaviorScopeError(
            f"runtime behavior scope explicit file is a directory: {logical_path}"
        )
    if not path.is_file():
        raise RuntimeBehaviorScopeError(
            f"runtime behavior scope contains an unsupported file: {logical_path}"
        )
    selected[logical_path] = path


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
