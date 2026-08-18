"""Append-only TraceRelay evidence journal writer."""

from __future__ import annotations

import hashlib
import os
import struct
import threading
import time
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import BinaryIO

from .config import FORMAT_VERSION, JOURNAL_LIMIT_BYTES, READ_CHUNK_SIZE


JOURNAL_MAGIC = b"TRR1"
HASH_SIZE = hashlib.sha256().digest_size
ZERO_HASH = bytes(HASH_SIZE)

# v1: magic, version, type, direction, sequence, UTC ns, monotonic ns,
# related DATA sequence, direction offset, payload length, result code, prev hash.
JOURNAL_HEADER_V1 = struct.Struct("<4sHBBQQQQQIi32s")

# v2 adds connection_id before sequence. Every record is therefore bound to one
# application connection while the global sequence and hash chain stay singular.
JOURNAL_HEADER = struct.Struct("<4sHBBQQQQQQIi32s")
JOURNAL_RECORD_OVERHEAD = JOURNAL_HEADER.size + HASH_SIZE
SEND_RESULT_RECORD_SIZE = JOURNAL_RECORD_OVERHEAD


class JournalLimitExceeded(RuntimeError):
    """Raised before a DATA record would exceed the session journal limit."""


class RecordType(IntEnum):
    DATA = 1
    SEND_OK = 2
    SEND_ERROR = 3


class Direction(IntEnum):
    CLIENT_TO_UPSTREAM = 1
    UPSTREAM_TO_CLIENT = 2

    @property
    def label(self) -> str:
        if self is Direction.CLIENT_TO_UPSTREAM:
            return "client_to_upstream"
        return "upstream_to_client"


@dataclass(frozen=True, slots=True)
class DataReference:
    sequence: int
    connection_id: int
    direction: Direction
    stream_offset: int
    length: int


@dataclass(frozen=True, slots=True)
class JournalSummary:
    final_sequence: int
    final_hash: str
    observed_bytes: dict[str, int]
    sent_success_bytes: dict[str, int]
    pending_results: int


class JournalWriter:
    """Serialize and durably flush every evidence record before returning."""

    def __init__(self, path: Path, *, max_bytes: int = JOURNAL_LIMIT_BYTES) -> None:
        if (
            type(max_bytes) is not int
            or not 1 <= max_bytes <= JOURNAL_LIMIT_BYTES
        ):
            raise ValueError(
                f"max_bytes must be an integer between 1 and {JOURNAL_LIMIT_BYTES}"
            )
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream: BinaryIO = self.path.open("xb")
        self._lock = threading.Lock()
        self._sequence = 0
        self._previous_hash = ZERO_HASH
        self._offsets: dict[tuple[int, Direction], int] = {}
        self._observed = {direction: 0 for direction in Direction}
        self._sent_success = {direction: 0 for direction in Direction}
        self._pending: dict[int, DataReference] = {}
        self._bytes_written = 0
        self._reserved_result_bytes = 0
        self._closed = False

    def append_data(
        self,
        direction: Direction,
        payload: bytes,
        *,
        connection_id: int = 1,
    ) -> DataReference:
        if not isinstance(direction, Direction):
            raise TypeError("direction must be a Direction")
        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")
        if not payload or len(payload) > READ_CHUNK_SIZE:
            raise ValueError("payload length must be between 1 and READ_CHUNK_SIZE")
        _validate_connection_id(connection_id)

        with self._lock:
            required_bytes = (
                JOURNAL_RECORD_OVERHEAD + len(payload) + SEND_RESULT_RECORD_SIZE
            )
            projected_bytes = (
                self._bytes_written
                + self._reserved_result_bytes
                + required_bytes
            )
            if projected_bytes > self.max_bytes:
                raise JournalLimitExceeded(
                    f"journal limit of {self.max_bytes} bytes would be exceeded"
                )
            stream_key = (connection_id, direction)
            stream_offset = self._offsets.get(stream_key, 0)
            sequence = self._write_record_locked(
                record_type=RecordType.DATA,
                connection_id=connection_id,
                direction=direction,
                related_sequence=0,
                stream_offset=stream_offset,
                payload=payload,
                result_code=0,
            )
            reference = DataReference(
                sequence,
                connection_id,
                direction,
                stream_offset,
                len(payload),
            )
            self._offsets[stream_key] = stream_offset + len(payload)
            self._observed[direction] += len(payload)
            self._pending[sequence] = reference
            self._reserved_result_bytes += SEND_RESULT_RECORD_SIZE
            return reference

    def append_send_ok(self, reference: DataReference) -> None:
        with self._lock:
            pending = self._require_pending_locked(reference)
            self._write_record_locked(
                record_type=RecordType.SEND_OK,
                connection_id=pending.connection_id,
                direction=pending.direction,
                related_sequence=pending.sequence,
                stream_offset=pending.stream_offset,
                payload=b"",
                result_code=0,
            )
            self._sent_success[pending.direction] += pending.length
            self._reserved_result_bytes -= SEND_RESULT_RECORD_SIZE
            del self._pending[pending.sequence]

    def append_send_error(self, reference: DataReference, error_code: int) -> None:
        if isinstance(error_code, bool) or not isinstance(error_code, int):
            raise TypeError("error_code must be an integer")
        if error_code == 0 or not -(2**31) <= error_code < 2**31:
            raise ValueError("error_code must be a non-zero signed 32-bit integer")

        with self._lock:
            pending = self._require_pending_locked(reference)
            self._write_record_locked(
                record_type=RecordType.SEND_ERROR,
                connection_id=pending.connection_id,
                direction=pending.direction,
                related_sequence=pending.sequence,
                stream_offset=pending.stream_offset,
                payload=b"",
                result_code=error_code,
            )
            self._reserved_result_bytes -= SEND_RESULT_RECORD_SIZE
            del self._pending[pending.sequence]

    def summary(self) -> JournalSummary:
        with self._lock:
            return JournalSummary(
                final_sequence=self._sequence,
                final_hash=self._previous_hash.hex(),
                observed_bytes={key.label: value for key, value in self._observed.items()},
                sent_success_bytes={
                    key.label: value for key, value in self._sent_success.items()
                },
                pending_results=len(self._pending),
            )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._stream.flush()
            os.fsync(self._stream.fileno())
            self._stream.close()
            self._closed = True

    def __enter__(self) -> JournalWriter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _require_pending_locked(self, reference: DataReference) -> DataReference:
        pending = self._pending.get(reference.sequence)
        if pending != reference:
            raise ValueError("DATA reference is not pending or does not match")
        return pending

    def _write_record_locked(
        self,
        *,
        record_type: RecordType,
        connection_id: int,
        direction: Direction,
        related_sequence: int,
        stream_offset: int,
        payload: bytes,
        result_code: int,
    ) -> int:
        if self._closed:
            raise ValueError("journal is closed")
        sequence = self._sequence + 1
        header = JOURNAL_HEADER.pack(
            JOURNAL_MAGIC,
            FORMAT_VERSION,
            int(record_type),
            int(direction),
            connection_id,
            sequence,
            time.time_ns(),
            time.monotonic_ns(),
            related_sequence,
            stream_offset,
            len(payload),
            result_code,
            self._previous_hash,
        )
        current_hash = hashlib.sha256(header + payload).digest()
        self._stream.write(header)
        self._stream.write(payload)
        self._stream.write(current_hash)
        self._stream.flush()
        os.fsync(self._stream.fileno())
        self._bytes_written += len(header) + len(payload) + len(current_hash)
        self._sequence = sequence
        self._previous_hash = current_hash
        return sequence


def _validate_connection_id(connection_id: int) -> None:
    if (
        type(connection_id) is not int
        or not 1 <= connection_id <= 2**64 - 1
    ):
        raise ValueError("connection_id must be a positive unsigned 64-bit integer")
