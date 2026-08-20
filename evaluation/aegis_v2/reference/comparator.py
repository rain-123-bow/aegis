from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .canonical import jcs_bytes, sha256_hex, verify_self_hash
from .schema_validation import local_schema_bundle


TRACE_NORMALIZATION_NONE = "NONE"
TRACE_NORMALIZATION_DROP_OBSERVATION_TIME = (
    "DROP_OBSERVATION_TIME_ONLY_KEEP_ORDER_AND_IDENTITIES"
)
TRACE_SCHEMA_VERSION = "ReferenceExecutionTrace.v1"
TRACE_TIME_POINTERS = (
    re.compile(r"^/observed_at_utc$"),
    re.compile(r"^/effects/\d+/observation_time_utc$"),
    re.compile(r"^/events/\d+/observation_time_utc$"),
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
)
_OPERATION_CLASSES = {
    "PURE_READ",
    "IDEMPOTENT_QUERYABLE",
    "NON_IDEMPOTENT_JOURNALED",
    "NON_IDEMPOTENT_UNJOURNALED",
}
_EVENT_KINDS = {
    "ACTION_DISPATCHED",
    "EFFECT_COMMITTED",
    "RECEIPT_COMMITTED",
    "RECOVERY_STARTED",
    "RECOVERY_COMPLETED",
    "REPLAY_SUPPRESSED",
}


def _schema_mismatches(
    value: dict[str, Any], schema_dir: Path, label: str
) -> list[str]:
    errors = local_schema_bundle(str(schema_dir.resolve())).errors(
        value, "sut_decision.v1.schema.json"
    )
    return [
        f"{label}-SUT-DECISION-SCHEMA-INVALID:{index:04d}"
        for index, _ in enumerate(errors, 1)
    ]


def compare_outputs(
    expected: dict[str, Any],
    actual: dict[str, Any],
    schema_dir: str | Path,
) -> dict[str, Any]:
    """Compare a context-free SUT decision to an external expected decision."""

    path = Path(schema_dir)
    mismatches: list[str] = []
    mismatches.extend(_schema_mismatches(expected, path, "EXPECTED"))
    mismatches.extend(_schema_mismatches(actual, path, "ACTUAL"))
    if not verify_self_hash(expected, "sut_decision_sha256"):
        mismatches.append("EXPECTED-SUT-DECISION-SELF-HASH-MISMATCH")
    if not verify_self_hash(actual, "sut_decision_sha256"):
        mismatches.append("SUT-DECISION-SELF-HASH-MISMATCH")
    if actual.get("reason_ids") != expected.get("reason_ids"):
        mismatches.append("REASON-ORDER-OR-VALUE-MISMATCH")
    if actual.get("assertion_ids") != expected.get("assertion_ids"):
        mismatches.append("ASSERTION-ORDER-OR-VALUE-MISMATCH")
    expected_bytes = jcs_bytes(expected)
    actual_bytes = jcs_bytes(actual)
    if actual_bytes != expected_bytes:
        mismatches.append("SUT-DECISION-JCS-MISMATCH")
    mismatch_ids = sorted(set(mismatches))
    return {
        "algorithm_id": "COMPARATOR-SUT-DECISION-EXACT-JCS-V1",
        "equal": not mismatch_ids,
        "mismatch_ids": mismatch_ids,
        "expected_jcs_sha256": sha256_hex(expected),
        "actual_jcs_sha256": sha256_hex(actual),
    }


def _escape_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _time_pointer_is_whitelisted(pointer: str) -> bool:
    return any(pattern.fullmatch(pointer) for pattern in TRACE_TIME_POINTERS)


def _normalize_trace_value(value: Any, pointer: str) -> Any:
    if isinstance(value, list):
        return [
            _normalize_trace_value(item, f"{pointer}/{index}")
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            child_pointer = f"{pointer}/{_escape_pointer(key)}"
            if key in {"observed_at_utc", "observation_time_utc"}:
                if not _time_pointer_is_whitelisted(child_pointer):
                    raise ValueError(
                        f"observation time pointer not whitelisted: "
                        f"{child_pointer}"
                    )
                continue
            normalized[key] = _normalize_trace_value(
                item, child_pointer
            )
        return normalized
    return copy.deepcopy(value)


def normalize_reference_trace(value: Any, mode: str) -> Any:
    if mode == TRACE_NORMALIZATION_NONE:
        return copy.deepcopy(value)
    if mode != TRACE_NORMALIZATION_DROP_OBSERVATION_TIME:
        raise ValueError(f"unsupported trace normalization: {mode}")
    return _normalize_trace_value(value, "")


def _require_exact_keys(
    value: Any,
    required: set[str],
    pointer: str,
    errors: list[str],
) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{pointer or '/'}: must be an object")
        return False
    actual = set(value)
    missing = sorted(required - actual)
    extra = sorted(actual - required)
    for key in missing:
        errors.append(f"{pointer}/{key}: required property missing")
    for key in extra:
        errors.append(f"{pointer}/{key}: additional property forbidden")
    return not missing


def _require_string(
    value: Any, pointer: str, errors: list[str]
) -> bool:
    if not isinstance(value, str) or not value:
        errors.append(f"{pointer}: must be a non-empty string")
        return False
    return True


def _require_sha256(
    value: Any, pointer: str, errors: list[str]
) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        errors.append(f"{pointer}: must be lowercase SHA-256")


def _require_utc(
    value: Any, pointer: str, errors: list[str]
) -> None:
    if not isinstance(value, str) or _UTC_RE.fullmatch(value) is None:
        errors.append(f"{pointer}: must be a UTC date-time ending in Z")
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{pointer}: invalid calendar date-time")
        return
    if parsed.tzinfo != timezone.utc:
        errors.append(f"{pointer}: date-time is not UTC")


def _require_nonnegative_integer(
    value: Any, pointer: str, errors: list[str]
) -> None:
    if isinstance(value, bool):
        errors.append(f"{pointer}: boolean is not an integer")
    elif type(value) is not int or value < 0:
        errors.append(f"{pointer}: must be a non-negative integer")


def _validate_trace(value: Any, category: str) -> list[str]:
    errors: list[str] = []
    top_keys = {
        "schema_version",
        "trace_kind",
        "action_id",
        "operation_id",
        "operation_class",
        "observed_at_utc",
        "state",
        "effects",
        "events",
        "recovery",
    }
    if not _require_exact_keys(value, top_keys, "", errors):
        return errors
    if value.get("schema_version") != TRACE_SCHEMA_VERSION:
        errors.append(
            "/schema_version: must equal ReferenceExecutionTrace.v1"
        )
    if value.get("trace_kind") not in {"RECOVERY", "SIDE_EFFECT"}:
        errors.append("/trace_kind: unsupported trace kind")
    if category not in {"RECOVERY", "SIDE_EFFECT"}:
        errors.append("/: unsupported comparator category")
    elif value.get("trace_kind") != category:
        errors.append("/trace_kind: does not match comparator category")
    for field in ("action_id", "operation_id", "operation_class"):
        _require_string(value.get(field), f"/{field}", errors)
    if value.get("operation_class") not in _OPERATION_CLASSES:
        errors.append("/operation_class: unsupported operation class")
    _require_utc(value.get("observed_at_utc"), "/observed_at_utc", errors)

    state = value.get("state")
    state_keys = {"before_sha256", "after_sha256"}
    if _require_exact_keys(state, state_keys, "/state", errors):
        _require_sha256(
            state.get("before_sha256"), "/state/before_sha256", errors
        )
        _require_sha256(
            state.get("after_sha256"), "/state/after_sha256", errors
        )

    root_action = value.get("action_id")
    root_operation = value.get("operation_id")
    effects = value.get("effects")
    if not isinstance(effects, list):
        errors.append("/effects: must be an array")
        effects = []
    effect_ids: set[str] = set()
    effect_sequences: list[int] = []
    effect_keys = {
        "effect_id",
        "action_id",
        "operation_id",
        "sequence",
        "payload_sha256",
        "observation_time_utc",
    }
    for index, effect in enumerate(effects):
        pointer = f"/effects/{index}"
        if not _require_exact_keys(
            effect, effect_keys, pointer, errors
        ):
            continue
        effect_id = effect.get("effect_id")
        if _require_string(
            effect_id, f"{pointer}/effect_id", errors
        ):
            if effect_id in effect_ids:
                errors.append(f"{pointer}/effect_id: duplicate identity")
            effect_ids.add(effect_id)
        if effect.get("action_id") != root_action:
            errors.append(
                f"{pointer}/action_id: does not match root action_id"
            )
        if effect.get("operation_id") != root_operation:
            errors.append(
                f"{pointer}/operation_id: does not match root operation_id"
            )
        sequence = effect.get("sequence")
        _require_nonnegative_integer(
            sequence, f"{pointer}/sequence", errors
        )
        if type(sequence) is int and not isinstance(sequence, bool):
            if sequence < 1:
                errors.append(f"{pointer}/sequence: must be at least 1")
            effect_sequences.append(sequence)
        _require_sha256(
            effect.get("payload_sha256"),
            f"{pointer}/payload_sha256",
            errors,
        )
        _require_utc(
            effect.get("observation_time_utc"),
            f"{pointer}/observation_time_utc",
            errors,
        )
    if effect_sequences != list(range(1, len(effects) + 1)):
        errors.append("/effects: sequence must be contiguous array order")

    events = value.get("events")
    if not isinstance(events, list):
        errors.append("/events: must be an array")
        events = []
    event_ids: set[str] = set()
    event_sequences: list[int] = []
    event_keys = {
        "event_id",
        "action_id",
        "operation_id",
        "sequence",
        "event_kind",
        "observation_time_utc",
    }
    for index, event in enumerate(events):
        pointer = f"/events/{index}"
        if not _require_exact_keys(
            event, event_keys, pointer, errors
        ):
            continue
        event_id = event.get("event_id")
        if _require_string(event_id, f"{pointer}/event_id", errors):
            if event_id in event_ids:
                errors.append(f"{pointer}/event_id: duplicate identity")
            event_ids.add(event_id)
        if event.get("action_id") != root_action:
            errors.append(
                f"{pointer}/action_id: does not match root action_id"
            )
        if event.get("operation_id") != root_operation:
            errors.append(
                f"{pointer}/operation_id: does not match root operation_id"
            )
        sequence = event.get("sequence")
        _require_nonnegative_integer(
            sequence, f"{pointer}/sequence", errors
        )
        if type(sequence) is int and not isinstance(sequence, bool):
            if sequence < 1:
                errors.append(f"{pointer}/sequence: must be at least 1")
            event_sequences.append(sequence)
        _require_string(
            event.get("event_kind"), f"{pointer}/event_kind", errors
        )
        if event.get("event_kind") not in _EVENT_KINDS:
            errors.append(f"{pointer}/event_kind: unsupported event kind")
        _require_utc(
            event.get("observation_time_utc"),
            f"{pointer}/observation_time_utc",
            errors,
        )
    if event_sequences != list(range(1, len(events) + 1)):
        errors.append("/events: sequence must be contiguous array order")

    recovery = value.get("recovery")
    recovery_keys = {
        "observed_effect_count_before_crash",
        "observed_effect_count_after_recovery",
        "automatic_replay_performed",
    }
    if _require_exact_keys(
        recovery, recovery_keys, "/recovery", errors
    ):
        before = recovery.get("observed_effect_count_before_crash")
        after = recovery.get("observed_effect_count_after_recovery")
        _require_nonnegative_integer(
            before,
            "/recovery/observed_effect_count_before_crash",
            errors,
        )
        _require_nonnegative_integer(
            after,
            "/recovery/observed_effect_count_after_recovery",
            errors,
        )
        if (
            type(before) is int
            and not isinstance(before, bool)
            and type(after) is int
            and not isinstance(after, bool)
            and after < before
        ):
            errors.append(
                "/recovery: effect count regressed after recovery"
            )
        if (
            type(after) is int
            and not isinstance(after, bool)
            and after != len(effects)
        ):
            errors.append(
                "/recovery/observed_effect_count_after_recovery: "
                "must equal effect array length"
            )
        if type(recovery.get("automatic_replay_performed")) is not bool:
            errors.append(
                "/recovery/automatic_replay_performed: must be boolean"
            )
    return errors


def _trace_audit_issues(trace: Any, category: str) -> list[str]:
    if not isinstance(trace, dict):
        return ["TRACE-NOT-OBJECT"]
    issues: list[str] = []
    recovery = trace.get("recovery", {})
    before = recovery.get("observed_effect_count_before_crash")
    after = recovery.get("observed_effect_count_after_recovery")
    operation_class = str(trace.get("operation_class", ""))
    if (
        category in {"RECOVERY", "SIDE_EFFECT"}
        and "NONIDEMPOTENT" in operation_class.replace("_", "")
        and type(after) is int
        and not isinstance(after, bool)
        and after > 1
    ):
        issues.append("SIDE-EFFECT-NONIDEMPOTENT-MULTIPLE-EFFECTS")
    if (
        "UNJOURNALED" in operation_class
        and recovery.get("automatic_replay_performed") is True
    ):
        issues.append("SIDE-EFFECT-UNJOURNALED-AUTOMATIC-REPLAY")
    return sorted(set(issues))


def compare_reference_traces(
    expected: Any,
    actual: Any,
    normalization: str,
    category: str,
) -> dict[str, Any]:
    """Normalize only observation time; retain event order and identity fields."""

    expected_validation_errors = _validate_trace(expected, category)
    actual_validation_errors = _validate_trace(actual, category)
    if expected_validation_errors or actual_validation_errors:
        return {
            "algorithm_id": "COMPARATOR-REFERENCE-TRACE-AUDITABLE-V1",
            "normalization": normalization,
            "category": category,
            "equal": False,
            "expected_validation_errors": expected_validation_errors,
            "actual_validation_errors": actual_validation_errors,
            "state_equal": False,
            "effect_equal": False,
            "event_equal": False,
            "recovery_equal": False,
            "expected_normalized_sha256": None,
            "actual_normalized_sha256": None,
            "audit_issue_ids": [],
        }
    normalized_expected = normalize_reference_trace(
        expected, normalization
    )
    normalized_actual = normalize_reference_trace(actual, normalization)
    audit_issues = _trace_audit_issues(actual, category)
    expected_bytes = jcs_bytes(normalized_expected)
    actual_bytes = jcs_bytes(normalized_actual)
    state_equal = (
        jcs_bytes(normalized_expected["state"])
        == jcs_bytes(normalized_actual["state"])
    )
    effect_equal = (
        jcs_bytes(normalized_expected["effects"])
        == jcs_bytes(normalized_actual["effects"])
    )
    event_equal = (
        jcs_bytes(normalized_expected["events"])
        == jcs_bytes(normalized_actual["events"])
    )
    recovery_equal = (
        jcs_bytes(normalized_expected["recovery"])
        == jcs_bytes(normalized_actual["recovery"])
    )
    return {
        "algorithm_id": "COMPARATOR-REFERENCE-TRACE-AUDITABLE-V1",
        "normalization": normalization,
        "category": category,
        "equal": expected_bytes == actual_bytes and not audit_issues,
        "expected_validation_errors": [],
        "actual_validation_errors": [],
        "state_equal": state_equal,
        "effect_equal": effect_equal,
        "event_equal": event_equal,
        "recovery_equal": recovery_equal,
        "expected_normalized_sha256": sha256_hex(normalized_expected),
        "actual_normalized_sha256": sha256_hex(normalized_actual),
        "audit_issue_ids": audit_issues,
    }
