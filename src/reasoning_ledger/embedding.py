from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Sequence

from .models import validate_embedding


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
    try:
        result = subprocess.run(
            args,
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
) -> tuple[list[float] | None, str]:
    """Resolve an embedding for query text.

    Returns (embedding, source). If no embedding source is available, returns
    (None, "none").
    """
    if embedding_json:
        return validate_embedding(parse_embedding_payload(embedding_json), dimensions=dimensions), "json"
    if embedding_file:
        return validate_embedding(load_embedding_file(embedding_file), dimensions=dimensions), "file"
    command = embedding_command or os.environ.get("AEGIS_LEDGER_EMBEDDING_COMMAND")
    if command:
        return (
            validate_embedding(
                run_embedding_command(command, text, timeout_seconds=command_timeout_seconds),
                dimensions=dimensions,
            ),
            "command",
        )
    if allow_hash_embedding:
        return hashed_text_embedding(text, dimensions=dimensions), "hash-fallback"
    return None, "none"
