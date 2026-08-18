from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from path_security import PathSecurityError, lexical_absolute, read_regular_file


TEST_EVIDENCE_MANIFEST_SCHEMA = "aegis.test_evidence_manifest.v2"
TEST_EVIDENCE_MANIFEST_NAME = "test_evidence_manifest.json"

_HEX_16_PATTERN = re.compile(r"[0-9a-f]{32}")
_HEX_32_PATTERN = re.compile(r"[0-9a-f]{64}")
_TOP_LEVEL_FIELDS = {
    "schema",
    "project_id_hex",
    "workflow_run_id",
    "attempt_id",
    "approved_test_plan",
    "created_at_utc",
    "records",
}
_RECORD_FIELDS = {
    "test_id",
    "requirement_ids",
    "command",
    "executable",
    "execution_policy_sha256",
    "cwd",
    "environment",
    "started_at_utc",
    "finished_at_utc",
    "exit_code",
    "test_inputs",
    "stdout",
    "stderr",
    "raw_results",
    "tracerelay_session_ids",
    "execution_receipt",
}
_DESCRIPTOR_FIELDS = {"path", "size", "sha256"}
_RECEIPT_FIELDS = {
    "schema",
    "trusted_runner",
    "request_sha256",
    "execution_policy_sha256",
    "test_id",
    "command",
    "executable",
    "cwd",
    "environment",
    "started_at_utc",
    "finished_at_utc",
    "exit_code",
    "timed_out",
    "runner_pid",
    "coordinator_pid",
    "test_inputs",
    "stdout",
    "stderr",
}


class TestEvidenceManifestError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ValidatedTestEvidenceManifest:
    path: Path
    sha256: str
    test_ids: tuple[str, ...]
    approved_test_plan_sha256: str
    execution_policy_sha256: str


def validate_test_evidence_manifest(
    manifest_path: str | Path,
    *,
    project_root: str | Path,
    artifact_root: str | Path,
    project_id_hex: str,
    workflow_run_id: str,
    attempt_id: str,
    allowed_tracerelay_session_ids: set[str],
    expected_manifest_path: str | Path | None = None,
) -> ValidatedTestEvidenceManifest:
    project = Path(project_root).resolve()
    artifacts = Path(artifact_root).resolve()
    path = Path(manifest_path).resolve()
    expected_path = (
        Path(expected_manifest_path).resolve()
        if expected_manifest_path is not None
        else artifacts / TEST_EVIDENCE_MANIFEST_NAME
    )
    if path != expected_path:
        raise TestEvidenceManifestError(
            f"test evidence manifest must use the fixed path: {expected_path}"
        )
    raw_bytes, payload = _read_json(path, "test evidence manifest")
    if not isinstance(payload, dict) or set(payload) != _TOP_LEVEL_FIELDS:
        raise TestEvidenceManifestError(
            "test evidence manifest has invalid top-level fields"
        )
    if payload["schema"] != TEST_EVIDENCE_MANIFEST_SCHEMA:
        raise TestEvidenceManifestError(
            "test evidence manifest has an unsupported schema"
        )
    if (
        not isinstance(project_id_hex, str)
        or _HEX_16_PATTERN.fullmatch(project_id_hex) is None
    ):
        raise ValueError("project_id_hex must contain 32 lowercase hex digits")
    if payload["project_id_hex"] != project_id_hex:
        raise TestEvidenceManifestError(
            "test evidence manifest project identity does not match the run"
        )
    if payload["workflow_run_id"] != workflow_run_id:
        raise TestEvidenceManifestError(
            "test evidence manifest workflow run identity does not match"
        )
    if payload["attempt_id"] != attempt_id:
        raise TestEvidenceManifestError(
            "test evidence manifest attempt identity does not match"
        )
    _parse_utc(payload["created_at_utc"], "manifest creation time")
    plan = _validate_descriptor(
        payload["approved_test_plan"],
        description="approved test plan",
        allowed_roots=(artifacts,),
    )
    if plan != (artifacts / "APPROVED_TEST_PLAN.md").resolve():
        raise TestEvidenceManifestError(
            "approved test plan descriptor does not use APPROVED_TEST_PLAN.md"
        )

    records = payload["records"]
    if not isinstance(records, list) or not records:
        raise TestEvidenceManifestError(
            "test evidence manifest must contain at least one record"
        )
    test_ids: list[str] = []
    for index, record in enumerate(records):
        test_ids.append(
            _validate_record(
                record,
                index=index,
                project_root=project,
                artifact_root=artifacts,
                attempt_evidence_root=artifacts / "evidence" / attempt_id,
                allowed_tracerelay_session_ids=allowed_tracerelay_session_ids,
            )
        )
    if len(set(test_ids)) != len(test_ids):
        raise TestEvidenceManifestError(
            "test evidence manifest contains duplicate test IDs"
        )
    policy_hashes = {
        str(record["execution_policy_sha256"])
        for record in records
        if isinstance(record, dict)
    }
    if len(policy_hashes) != 1:
        raise TestEvidenceManifestError(
            "test evidence records do not share one approved execution policy"
        )
    return ValidatedTestEvidenceManifest(
        path=path,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        test_ids=tuple(test_ids),
        approved_test_plan_sha256=str(payload["approved_test_plan"]["sha256"]),
        execution_policy_sha256=next(iter(policy_hashes)),
    )


def _validate_record(
    value: Any,
    *,
    index: int,
    project_root: Path,
    artifact_root: Path,
    attempt_evidence_root: Path,
    allowed_tracerelay_session_ids: set[str],
) -> str:
    if not isinstance(value, dict) or set(value) != _RECORD_FIELDS:
        raise TestEvidenceManifestError(
            f"test evidence record {index} has invalid fields"
        )
    test_id = _nonempty_string(value["test_id"], f"record {index} test ID")
    _nonempty_unique_strings(
        value["requirement_ids"], f"record {index} requirement IDs"
    )
    _nonempty_unique_strings(value["command"], f"record {index} command")
    _validate_descriptor(
        value["executable"],
        description=f"record {index} executable",
        allowed_roots=(_external_descriptor_root(value["executable"]),),
    )
    if (
        not isinstance(value["execution_policy_sha256"], str)
        or _HEX_32_PATTERN.fullmatch(value["execution_policy_sha256"]) is None
    ):
        raise TestEvidenceManifestError(
            f"test evidence record {index} has an invalid execution policy hash"
        )
    _nonempty_string(value["cwd"], f"record {index} working directory")
    environment = value["environment"]
    if (
        not isinstance(environment, dict)
        or not environment
        or not all(
            isinstance(key, str)
            and bool(key)
            and isinstance(item, str)
            and bool(item)
            for key, item in environment.items()
        )
    ):
        raise TestEvidenceManifestError(
            f"test evidence record {index} has an invalid environment fingerprint"
        )
    started = _parse_utc(value["started_at_utc"], f"record {index} start time")
    finished = _parse_utc(value["finished_at_utc"], f"record {index} finish time")
    if finished < started:
        raise TestEvidenceManifestError(
            f"test evidence record {index} finishes before it starts"
        )
    exit_code = value["exit_code"]
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise TestEvidenceManifestError(
            f"test evidence record {index} has an invalid exit code"
        )
    inputs = value["test_inputs"]
    if not isinstance(inputs, list) or not inputs:
        raise TestEvidenceManifestError(
            f"test evidence record {index} has no test inputs"
        )
    for descriptor in inputs:
        _validate_descriptor(
            descriptor,
            description=f"record {index} test input",
            allowed_roots=(project_root, artifact_root),
        )
    _validate_descriptor(
        value["stdout"],
        description=f"record {index} stdout",
        allowed_roots=(attempt_evidence_root,),
    )
    _validate_descriptor(
        value["stderr"],
        description=f"record {index} stderr",
        allowed_roots=(attempt_evidence_root,),
    )
    raw_results = value["raw_results"]
    if not isinstance(raw_results, list) or not raw_results:
        raise TestEvidenceManifestError(
            f"test evidence record {index} has no raw result artifacts"
        )
    for descriptor in raw_results:
        _validate_descriptor(
            descriptor,
            description=f"record {index} raw result",
            allowed_roots=(attempt_evidence_root,),
        )
    receipt_path = _validate_descriptor(
        value["execution_receipt"],
        description=f"record {index} execution receipt",
        allowed_roots=(attempt_evidence_root,),
    )
    if not any(
        isinstance(descriptor, dict)
        and descriptor.get("path") == str(receipt_path)
        and descriptor.get("sha256") == value["execution_receipt"].get("sha256")
        for descriptor in raw_results
    ):
        raise TestEvidenceManifestError(
            f"test evidence record {index} raw results omit its execution receipt"
        )
    _validate_execution_receipt(
        receipt_path,
        record=value,
        index=index,
        attempt_evidence_root=attempt_evidence_root,
    )
    session_ids = _nonempty_unique_strings(
        value["tracerelay_session_ids"],
        f"record {index} TraceRelay session IDs",
    )
    unknown = set(session_ids) - allowed_tracerelay_session_ids
    if unknown:
        raise TestEvidenceManifestError(
            f"test evidence record {index} references unknown TraceRelay sessions: "
            + ", ".join(sorted(unknown))
        )
    return test_id


def _validate_execution_receipt(
    path: Path,
    *,
    record: dict[str, Any],
    index: int,
    attempt_evidence_root: Path,
) -> None:
    _raw, receipt = _read_json(path, f"record {index} execution receipt")
    if not isinstance(receipt, dict) or set(receipt) != _RECEIPT_FIELDS:
        raise TestEvidenceManifestError(
            f"test evidence record {index} execution receipt has invalid fields"
        )
    if (
        receipt["schema"] != "aegis.test_execution_receipt.v3"
        or receipt["trusted_runner"] != "aegis.coordinator.windows_job.v1"
        or not isinstance(receipt["request_sha256"], str)
        or _HEX_32_PATTERN.fullmatch(receipt["request_sha256"]) is None
    ):
        raise TestEvidenceManifestError(
            f"test evidence record {index} execution receipt is not trusted"
        )
    for field in (
        "test_id",
        "command",
        "executable",
        "execution_policy_sha256",
        "cwd",
        "environment",
        "started_at_utc",
        "finished_at_utc",
        "exit_code",
        "test_inputs",
        "stdout",
        "stderr",
    ):
        if receipt[field] != record[field]:
            raise TestEvidenceManifestError(
                f"test evidence record {index} differs from its execution receipt: {field}"
            )
    if not isinstance(receipt["timed_out"], bool):
        raise TestEvidenceManifestError(
            f"test evidence record {index} receipt timeout flag is invalid"
        )
    for field in ("runner_pid", "coordinator_pid"):
        if (
            isinstance(receipt[field], bool)
            or not isinstance(receipt[field], int)
            or receipt[field] <= 0
        ):
            raise TestEvidenceManifestError(
                f"test evidence record {index} receipt {field} is invalid"
            )
    expected_parent = attempt_evidence_root / f"test-{index + 1:04d}"
    if path.parent != expected_parent or path.name != "execution_receipt.json":
        raise TestEvidenceManifestError(
            f"test evidence record {index} receipt path is not coordinator-owned"
        )


def _validate_descriptor(
    value: Any,
    *,
    description: str,
    allowed_roots: tuple[Path, ...],
) -> Path:
    if not isinstance(value, dict) or set(value) != _DESCRIPTOR_FIELDS:
        raise TestEvidenceManifestError(f"{description} has invalid fields")
    raw_path = value["path"]
    if not isinstance(raw_path, str) or not raw_path:
        raise TestEvidenceManifestError(f"{description} has an invalid path")
    path = lexical_absolute(raw_path)
    if not path.is_absolute():
        raise TestEvidenceManifestError(f"{description} path is not absolute")
    containing_root = _containing_root(path, allowed_roots)
    if containing_root is None:
        raise TestEvidenceManifestError(
            f"{description} path is outside its allowed artifact root"
        )
    try:
        content, _identity = read_regular_file(
            path,
            allowed_root=containing_root,
            label=description,
            max_bytes=512 * 1024 * 1024,
        )
    except PathSecurityError as error:
        raise TestEvidenceManifestError(str(error)) from error
    expected_size = value["size"]
    if (
        isinstance(expected_size, bool)
        or not isinstance(expected_size, int)
        or expected_size < 0
        or len(content) != expected_size
    ):
        raise TestEvidenceManifestError(f"{description} size mismatch")
    expected_sha256 = value["sha256"]
    if (
        not isinstance(expected_sha256, str)
        or _HEX_32_PATTERN.fullmatch(expected_sha256) is None
    ):
        raise TestEvidenceManifestError(f"{description} has an invalid SHA-256")
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if actual_sha256 != expected_sha256:
        raise TestEvidenceManifestError(f"{description} hash mismatch")
    return path


def _containing_root(path: Path, roots: Iterable[Path]) -> Path | None:
    for root in roots:
        try:
            path.relative_to(root)
        except ValueError:
            continue
        return root
    return None


def _external_descriptor_root(value: Any) -> Path:
    if not isinstance(value, dict):
        raise TestEvidenceManifestError("executable descriptor is invalid")
    raw_path = value.get("path")
    if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
        raise TestEvidenceManifestError("executable descriptor path is invalid")
    return Path(Path(raw_path).anchor)


def _nonempty_string(value: Any, description: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TestEvidenceManifestError(f"{description} must not be empty")
    return value


def _nonempty_unique_strings(value: Any, description: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and bool(item.strip()) for item in value)
        or len(set(value)) != len(value)
    ):
        raise TestEvidenceManifestError(
            f"{description} must contain unique non-empty strings"
        )
    return tuple(value)


def _parse_utc(value: Any, description: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise TestEvidenceManifestError(f"{description} is not canonical UTC")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise TestEvidenceManifestError(
            f"{description} is not a valid timestamp"
        ) from error
    return parsed


def _read_json(path: Path, description: str) -> tuple[bytes, Any]:
    try:
        raw = path.read_bytes()
        return raw, json.loads(raw.decode("utf-8", errors="strict"))
    except FileNotFoundError as error:
        raise TestEvidenceManifestError(f"{description} is missing: {path}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise TestEvidenceManifestError(
            f"{description} cannot be read: {path}: {error}"
        ) from error
