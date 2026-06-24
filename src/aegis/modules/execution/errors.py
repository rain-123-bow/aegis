"""Execution Subgraph v2 errors."""

from __future__ import annotations

from enum import Enum
from typing import Any


class ExecutionErrorCode(str, Enum):
    """Machine-readable ExecutionSubgraph error codes."""

    PATH_POLICY_VIOLATION = "PATH_POLICY_VIOLATION"
    PROJECT_STORE_NOT_FOUND = "PROJECT_STORE_NOT_FOUND"
    INPUT_VALIDATION_FAILED = "INPUT_VALIDATION_FAILED"
    SCORECARD_INVALID = "SCORECARD_INVALID"
    IMPLEMENTATION_BLOCKED = "IMPLEMENTATION_BLOCKED"
    COMMAND_BLOCKED = "COMMAND_BLOCKED"
    STATE_SIZE_EXCEEDED = "STATE_SIZE_EXCEEDED"


class ExecutionRuntimeError(RuntimeError):
    """Runtime error with structured context."""

    def __init__(
        self,
        code: ExecutionErrorCode,
        message: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = context or {}
