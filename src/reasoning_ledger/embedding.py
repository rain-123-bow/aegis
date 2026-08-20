from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

from frozen_input_watcher import FrozenInputWatcher, FrozenInputWatcherError
from .models import validate_embedding
from path_security import read_regular_file


class EmbeddingError(RuntimeError):
    """Raised when an embedding cannot be produced or parsed."""


_WORD_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def parse_embedding_payload(payload: str | bytes | Sequence[float] | dict[str, Any]) -> list[float]:
    """Parse an embedding from JSON or a numeric sequence.

    Accepted payloads:
    - JSON array: [0.1, 0.2, ...]
    - JSON object: {"embedding": [...]} or {"data": [{"embedding": [...]}]}
    - comma/space separated numbers
    - Python sequence of floats
    """
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, dict):
        return _embedding_from_object(payload)
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            raise EmbeddingError("embedding payload is empty")
        try:
            value = json.loads(text)
            if isinstance(value, dict):
                return _embedding_from_object(value)
            if isinstance(value, list):
                return validate_embedding(value) or []
        except json.JSONDecodeError:
            pass
        try:
            return validate_embedding([float(part) for part in re.split(r"[\s,]+", text) if part]) or []
        except ValueError as exc:
            raise EmbeddingError("embedding payload is not valid JSON or numeric text") from exc
    return validate_embedding(payload) or []


def _embedding_from_object(value: dict[str, Any]) -> list[float]:
    if "embedding" in value:
        return validate_embedding(value["embedding"]) or []
    data = value.get("data")
    if isinstance(data, list) and data and isinstance(data[0], dict) and "embedding" in data[0]:
        return validate_embedding(data[0]["embedding"]) or []
    raise EmbeddingError("JSON object must contain 'embedding' or 'data[0].embedding'")


def load_embedding_file(path: str | Path) -> list[float]:
    return parse_embedding_payload(Path(path).read_text(encoding="utf-8"))


def run_embedding_command(command: str, text: str, *, timeout_seconds: int = 60) -> list[float]:
    """Run an external embedding command.

    The command receives the text on stdin and must print an embedding payload to stdout.
    No shell is used; pass a normal command string such as:

        python scripts/embed.py

    stdout can be a JSON array, {"embedding": [...]}, or OpenAI-style
    {"data": [{"embedding": [...]}]}.
    """
    args = shlex.split(command)
    if not args:
        raise EmbeddingError("embedding command is empty")
    return _run_embedding_args(args, text, timeout_seconds=timeout_seconds)


def _run_embedding_args(
    args: Sequence[str],
    text: str,
    *,
    timeout_seconds: int,
) -> list[float]:
    try:
        result = subprocess.run(
            list(args),
            input=text,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EmbeddingError(f"embedding command failed to run: {exc}") from exc
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise EmbeddingError(f"embedding command exited with {result.returncode}: {stderr}")
    return parse_embedding_payload(result.stdout)


def _run_bound_persistent_embedding_command(
    command: str,
    text: str,
    *,
    dimensions: int,
    timeout_seconds: int,
) -> tuple[list[float], dict[str, Any]]:
    if sys.platform != "win32":
        raise EmbeddingError(
            "persistent external embedding commands require Windows file-object locks"
        )
    command_args = shlex.split(command)
    if not command_args:
        raise EmbeddingError("embedding command is empty")
    executable = shutil.which(command_args[0])
    if executable is None:
        raise EmbeddingError("embedding command executable cannot be resolved")
    executable_path = Path(executable).resolve()
    executed_args = [str(executable_path), *command_args[1:]]
    input_paths: list[tuple[int | None, Path]] = [(None, executable_path)]
    for index, argument in enumerate(command_args[1:], start=1):
        candidate = Path(argument)
        if not candidate.is_file():
            continue
        resolved = candidate.resolve()
        executed_args[index] = str(resolved)
        input_paths.append((index, resolved))
    paths_by_parent: dict[Path, list[Path]] = {}
    for _index, path in input_paths:
        paths_by_parent.setdefault(path.parent, []).append(path)
    watchers: list[FrozenInputWatcher] = []
    descriptors: dict[Path, dict[str, Any]] = {}
    try:
        for parent, paths in paths_by_parent.items():
            watcher = FrozenInputWatcher(parent)
            watcher.start()
            watcher.lock_files(paths)
            watchers.append(watcher)
        for _index, path in input_paths:
            content, _identity = read_regular_file(
                path,
                allowed_root=Path(path.anchor),
                label="embedding generator locked input",
                max_bytes=128 * 1024 * 1024,
            )
            descriptors[path] = {
                "path": str(path),
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        embedding = validate_embedding(
            _run_embedding_args(
                executed_args,
                text,
                timeout_seconds=timeout_seconds,
            ),
            dimensions=dimensions,
        )
        assert embedding is not None
        for path, descriptor in descriptors.items():
            content, _identity = read_regular_file(
                path,
                allowed_root=Path(path.anchor),
                label="embedding generator locked input recheck",
                max_bytes=128 * 1024 * 1024,
            )
            if (
                len(content) != descriptor["size"]
                or hashlib.sha256(content).hexdigest() != descriptor["sha256"]
            ):
                raise EmbeddingError(
                    "embedding generator input changed during execution"
                )
        bound_paths = set(descriptors)
        for watcher in watchers:
            events = watcher.drain()
            if any(event.path in bound_paths for event in events):
                raise EmbeddingError(
                    "embedding generator input emitted a filesystem mutation event"
                )
        executable_descriptor = descriptors[executable_path]
        file_inputs = [
            descriptors[path]
            for index, path in input_paths
            if index is not None
        ]
        return embedding, {
            "kind": "external-command",
            "command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
            "executed_arguments_sha256": hashlib.sha256(
                json.dumps(
                    executed_args,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
            "executable": executable_descriptor,
            "file_inputs": file_inputs,
            "binding": "windows-deny-write-delete-file-object-lock-v1",
        }
    except (FrozenInputWatcherError, OSError) as error:
        raise EmbeddingError(
            f"embedding generator identity could not be frozen: {error}"
        ) from error
    finally:
        close_errors: list[BaseException] = []
        for watcher in reversed(watchers):
            try:
                watcher.close()
            except BaseException as error:
                close_errors.append(error)
        if close_errors and sys.exc_info()[0] is None:
            raise EmbeddingError(
                f"embedding generator file locks failed to close: {close_errors[0]}"
            ) from close_errors[0]


def hashed_text_embedding(text: str, *, dimensions: int = 1536) -> list[float]:
    """Deterministic local fallback embedding.

    This is useful for offline development and CI. It is not a replacement for a
    real semantic embedding model, but it preserves enough lexical signal to make
    vector plumbing testable without external services.
    """
    if dimensions <= 0:
        raise ValueError("dimensions must be > 0")
    vector = [0.0] * dimensions
    tokens = _tokens(text)
    if not tokens:
        tokens = [text.strip() or "<empty>"]
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:8], "big") % dimensions
        sign = -1.0 if digest[8] & 1 else 1.0
        # Slightly upweight longer lexical units while keeping values bounded.
        weight = 1.0 + min(len(token), 16) / 32.0
        vector[index] += sign * weight
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _tokens(text: str) -> list[str]:
    base = [match.group(0).lower() for match in _WORD_RE.finditer(text)]
    cjk_chars = [token for token in base if len(token) == 1 and "\u4e00" <= token <= "\u9fff"]
    cjk_bigrams = ["".join(pair) for pair in zip(cjk_chars, cjk_chars[1:])]
    ascii_bigrams: list[str] = []
    for token in base:
        if len(token) > 3 and not (len(token) == 1 and "\u4e00" <= token <= "\u9fff"):
            ascii_bigrams.extend(token[i : i + 3] for i in range(len(token) - 2))
    return base + cjk_bigrams + ascii_bigrams


def resolve_query_embedding(
    *,
    text: str,
    dimensions: int,
    embedding_json: str | None = None,
    embedding_file: str | Path | None = None,
    embedding_command: str | None = None,
    allow_hash_embedding: bool = False,
    command_timeout_seconds: int = 60,
) -> tuple[list[float] | None, str, dict[str, Any] | None]:
    """Resolve an embedding for query text.

    Returns embedding bytes, source classification, and a byte-bound generator
    identity. If no source is available, all authority fields are absent.
    """
    if embedding_json:
        encoded = embedding_json.encode("utf-8")
        return (
            validate_embedding(
                parse_embedding_payload(encoded),
                dimensions=dimensions,
            ),
            "json",
            {
                "kind": "provided-json",
                "size": len(encoded),
                "sha256": hashlib.sha256(encoded).hexdigest(),
            },
        )
    if embedding_file:
        path = Path(embedding_file).resolve()
        encoded = path.read_bytes()
        return (
            validate_embedding(
                parse_embedding_payload(encoded),
                dimensions=dimensions,
            ),
            "file",
            {
                "kind": "provided-file",
                "path": str(path),
                "size": len(encoded),
                "sha256": hashlib.sha256(encoded).hexdigest(),
            },
        )
    command = embedding_command or os.environ.get("AEGIS_LEDGER_EMBEDDING_COMMAND")
    if command:
        embedding, identity = _run_bound_persistent_embedding_command(
            command,
            text,
            dimensions=dimensions,
            timeout_seconds=command_timeout_seconds,
        )
        return embedding, "command", identity
    if allow_hash_embedding:
        return (
            hashed_text_embedding(text, dimensions=dimensions),
            "hash-fallback",
            {
                "kind": "aegis-development-hash-embedding",
                "implementation": "reasoning_ledger.embedding.hashed_text_embedding",
            },
        )
    return None, "none", None


def resolve_persistent_embedding(
    *,
    text: str,
    dimensions: int,
    embedding_command: str | None = None,
    allow_hash_embedding: bool = False,
    command_timeout_seconds: int = 60,
) -> tuple[list[float], str, dict[str, Any]]:
    command = embedding_command or os.environ.get(
        "AEGIS_LEDGER_EMBEDDING_COMMAND"
    )
    if command:
        embedding, identity = _run_bound_persistent_embedding_command(
            command,
            text,
            dimensions=dimensions,
            timeout_seconds=command_timeout_seconds,
        )
        return embedding, "command", identity
    if allow_hash_embedding:
        return hashed_text_embedding(text, dimensions=dimensions), "hash-fallback", {
            "kind": "aegis-development-hash-embedding",
            "implementation": "reasoning_ledger.embedding.hashed_text_embedding",
        }
    else:
        raise EmbeddingError(
            "persistent embeddings require an executable generator or the "
            "dedicated development hash profile"
        )
