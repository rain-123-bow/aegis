from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from aegis_seal_core import SealContext, compute_project_seal, verify_project_seal


SEAL_RECORD_RELATIVE_PATH = Path(
    ".aegis/reasoning_ledger/artifacts/facts/project-seal.json"
)
SEAL_CHAIN_SCHEMA = "aegis.project_seal_chain.v1"

_HEX_16_PATTERN = re.compile(r"[0-9a-f]{32}")
_HEX_32_PATTERN = re.compile(r"[0-9a-f]{64}")
_GIT_HEAD_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_SEAL_PATTERN = re.compile(r"ASC1:[0-9a-f]{64}")
_RECORD_FIELDS = {
    "project_id_hex",
    "run_id_hex",
    "sequence",
    "previous_seal_hex",
    "expected_seal",
    "created_at_utc",
    "git_head_before_record",
}


class ProjectSealStoreError(RuntimeError):
    pass


class ProjectSealMismatchError(ProjectSealStoreError):
    pass


@dataclass(frozen=True, slots=True)
class StoredProjectSeal:
    project_id: bytes
    run_id: bytes
    sequence: int
    previous_seal: bytes
    expected_seal: str
    created_at_utc: str
    git_head_before_record: str

    @property
    def context(self) -> SealContext:
        return SealContext(
            project_id=self.project_id,
            run_id=self.run_id,
            sequence=self.sequence,
            previous_seal=self.previous_seal,
        )

    def as_json_data(self) -> dict[str, object]:
        return {
            "project_id_hex": self.project_id.hex(),
            "run_id_hex": self.run_id.hex(),
            "sequence": self.sequence,
            "previous_seal_hex": self.previous_seal.hex(),
            "expected_seal": self.expected_seal,
            "created_at_utc": self.created_at_utc,
            "git_head_before_record": self.git_head_before_record,
        }


@dataclass(frozen=True, slots=True)
class ProjectSealChain:
    records: tuple[StoredProjectSeal, ...]


def seal_record_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / SEAL_RECORD_RELATIVE_PATH


def load_project_seal_chain(project_root: str | Path) -> ProjectSealChain:
    path = seal_record_path(project_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ProjectSealStoreError(f"project seal record is missing: {path}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProjectSealStoreError(
            f"project seal record cannot be read: {path}: {error}"
        ) from error

    if not isinstance(payload, dict) or set(payload) != {"schema", "records"}:
        raise ProjectSealStoreError("project seal record has invalid top-level fields")
    if payload["schema"] != SEAL_CHAIN_SCHEMA:
        raise ProjectSealStoreError("project seal record has an unsupported schema")
    raw_records = payload["records"]
    if not isinstance(raw_records, list) or not raw_records:
        raise ProjectSealStoreError("project seal chain must contain at least one record")

    records = tuple(
        _parse_record(raw_record, index)
        for index, raw_record in enumerate(raw_records)
    )
    _validate_chain(records)
    return ProjectSealChain(records)


def record_project_seal(
    project_root: str | Path,
    *,
    git_head_before_record: str,
    project_id: bytes | None = None,
    run_id: bytes | None = None,
) -> StoredProjectSeal:
    root = Path(project_root).resolve()
    if _GIT_HEAD_PATTERN.fullmatch(git_head_before_record) is None:
        raise ValueError("git_head_before_record must be a lowercase SHA-1 or SHA-256")

    path = seal_record_path(root)
    if path.exists():
        chain = load_project_seal_chain(root)
        last = chain.records[-1]
        if project_id is not None and project_id != last.project_id:
            raise ValueError("project_id cannot change within a seal chain")
        if run_id is not None and run_id != last.run_id:
            raise ValueError("run_id cannot change within a seal chain")
        context = SealContext(
            project_id=last.project_id,
            run_id=last.run_id,
            sequence=last.sequence + 1,
            previous_seal=bytes.fromhex(last.expected_seal.removeprefix("ASC1:")),
        )
        previous_records = chain.records
    else:
        context = SealContext(
            project_id=project_id if project_id is not None else uuid4().bytes,
            run_id=run_id if run_id is not None else uuid4().bytes,
        )
        previous_records = ()

    expected_seal = compute_project_seal(root, context)
    record = StoredProjectSeal(
        project_id=context.project_id,
        run_id=context.run_id,
        sequence=context.sequence,
        previous_seal=context.previous_seal,
        expected_seal=expected_seal,
        created_at_utc=_utc_now_text(),
        git_head_before_record=git_head_before_record,
    )
    _atomic_write_chain(path, (*previous_records, record))
    return record


def verify_expected_project_seal(
    project_root: str | Path,
) -> StoredProjectSeal:
    root = Path(project_root).resolve()
    record = load_project_seal_chain(root).records[-1]
    if not verify_project_seal(root, record.context, record.expected_seal):
        raise ProjectSealMismatchError(
            f"project source does not match the recorded seal: {root}"
        )
    return record


def _parse_record(value: Any, index: int) -> StoredProjectSeal:
    if not isinstance(value, dict) or set(value) != _RECORD_FIELDS:
        raise ProjectSealStoreError(f"seal record {index} has invalid fields")

    project_id_hex = _require_pattern(
        value["project_id_hex"], _HEX_16_PATTERN, "project_id_hex", index
    )
    run_id_hex = _require_pattern(
        value["run_id_hex"], _HEX_16_PATTERN, "run_id_hex", index
    )
    previous_seal_hex = _require_pattern(
        value["previous_seal_hex"], _HEX_32_PATTERN, "previous_seal_hex", index
    )
    expected_seal = _require_pattern(
        value["expected_seal"], _SEAL_PATTERN, "expected_seal", index
    )
    git_head = _require_pattern(
        value["git_head_before_record"],
        _GIT_HEAD_PATTERN,
        "git_head_before_record",
        index,
    )
    sequence = value["sequence"]
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise ProjectSealStoreError(f"seal record {index} has an invalid sequence")
    created_at_utc = value["created_at_utc"]
    if not isinstance(created_at_utc, str) or not created_at_utc.endswith("Z"):
        raise ProjectSealStoreError(
            f"seal record {index} has an invalid created_at_utc"
        )
    try:
        datetime.fromisoformat(created_at_utc.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise ProjectSealStoreError(
            f"seal record {index} has an invalid created_at_utc"
        ) from error

    try:
        return StoredProjectSeal(
            project_id=bytes.fromhex(project_id_hex),
            run_id=bytes.fromhex(run_id_hex),
            sequence=sequence,
            previous_seal=bytes.fromhex(previous_seal_hex),
            expected_seal=expected_seal,
            created_at_utc=created_at_utc,
            git_head_before_record=git_head,
        )
    except ValueError as error:
        raise ProjectSealStoreError(f"seal record {index} is invalid: {error}") from error


def _require_pattern(
    value: Any, pattern: re.Pattern[str], field: str, index: int
) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ProjectSealStoreError(f"seal record {index} has an invalid {field}")
    return value


def _validate_chain(records: tuple[StoredProjectSeal, ...]) -> None:
    first = records[0]
    if first.sequence != 0 or first.previous_seal != bytes(32):
        raise ProjectSealStoreError(
            "first seal record must use sequence zero and a zero previous seal"
        )
    for index, record in enumerate(records):
        if record.sequence != index:
            raise ProjectSealStoreError("seal sequence must be contiguous from zero")
        if record.project_id != first.project_id or record.run_id != first.run_id:
            raise ProjectSealStoreError("project_id and run_id must remain fixed")
        if index == 0:
            continue
        expected_previous = bytes.fromhex(records[index - 1].expected_seal[5:])
        if record.previous_seal != expected_previous:
            raise ProjectSealStoreError(
                f"seal record {index} previous seal does not match record {index - 1}"
            )


def _atomic_write_chain(
    path: Path, records: tuple[StoredProjectSeal, ...]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(
            {
                "schema": SEAL_CHAIN_SCHEMA,
                "records": [record.as_json_data() for record in records],
            },
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _utc_now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
