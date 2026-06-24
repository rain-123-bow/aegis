"""Debate runtime error types."""

from __future__ import annotations

from enum import Enum
from typing import Any


class DebateErrorCode(str, Enum):
    """Machine-readable DebateSubgraph error codes."""

    PROJECT_STORE_NOT_FOUND = "PROJECT_STORE_NOT_FOUND"
    PATH_POLICY_VIOLATION = "PATH_POLICY_VIOLATION"
    INVALID_INPUT_PACKAGE = "INVALID_INPUT_PACKAGE"
    MISSING_REQUIRED_CONTEXT = "MISSING_REQUIRED_CONTEXT"
    MISSING_TEST_MEASUREMENT = "MISSING_TEST_MEASUREMENT"
    DEGRADED_CONTEXT_RECALL = "DEGRADED_CONTEXT_RECALL"
    UNSUPPORTED_HARD_CONSTRAINT = "UNSUPPORTED_HARD_CONSTRAINT"
    INSUFFICIENT_DEFENSIBLE_STANCES = "INSUFFICIENT_DEFENSIBLE_STANCES"
    INSUFFICIENT_CONTESTED_STANCES = "INSUFFICIENT_CONTESTED_STANCES"
    WORKER_PROTOCOL_VIOLATION = "WORKER_PROTOCOL_VIOLATION"
    LEADER_DECISION_INVALID = "LEADER_DECISION_INVALID"
    DEBATE_NON_CONVERGENT = "DEBATE_NON_CONVERGENT"
    CAUSAL_CANDIDATE_WRITE_FAILED = "CAUSAL_CANDIDATE_WRITE_FAILED"


class DebateRuntimeError(RuntimeError):
    """Exception with stable error code and diagnostic context."""

    def __init__(
        self,
        code: DebateErrorCode,
        message: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = context or {}

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-safe error record."""

        return {
            "code": self.code.value,
            "message": self.message,
            "context": self.context,
        }
