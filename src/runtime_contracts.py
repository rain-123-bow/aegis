from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


RUN_STATE_SCHEMA = "aegis.run_state.v14"
FINAL_REVIEW_INPUT_MANIFEST_SCHEMA = "aegis.final_review_input_manifest.v2"

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_MANIFEST_FIELDS = {
    "schema",
    "workflow_run_id",
    "final_attempt",
    "frozen_runtime_manifest",
    "engineering_input_manifest",
    "reasoning_context_pack",
    "authorities",
    "planning",
    "execution",
    "required_evidence",
}
_AUTHORITY_FIELDS = {
    "schema",
    "workflow_run_id",
    "project_seal",
    "project_seal_record",
    "remote_witness_required",
    "remote_witness",
    "tracerelay_observed_identity_required",
    "tracerelay_runtime",
}
_DESCRIPTOR_FIELDS = {"path", "size", "sha256"}


class RuntimeContractError(RuntimeError):
    pass


def validate_final_review_input_manifest_payload(
    payload: object,
    *,
    workflow_run_id: str,
    final_attempt: Mapping[str, object],
) -> list[dict[str, object]]:
    if not isinstance(payload, dict) or set(payload) != _MANIFEST_FIELDS:
        raise RuntimeContractError(
            "final-review input manifest has invalid top-level fields"
        )
    if payload.get("schema") != FINAL_REVIEW_INPUT_MANIFEST_SCHEMA:
        raise RuntimeContractError(
            "final-review input manifest has an unsupported schema"
        )
    if payload.get("workflow_run_id") != workflow_run_id:
        raise RuntimeContractError(
            "final-review input manifest changed workflow identity"
        )
    expected_attempt = {
        "attempt_id": final_attempt.get("attempt_id"),
        "job_id": final_attempt.get("job_id"),
        "input_sha256": final_attempt.get("input_sha256"),
    }
    if payload.get("final_attempt") != expected_attempt:
        raise RuntimeContractError(
            "final-review input manifest changed attempt identity"
        )
    for field in (
        "frozen_runtime_manifest",
        "engineering_input_manifest",
        "reasoning_context_pack",
    ):
        if not isinstance(payload.get(field), dict):
            raise RuntimeContractError(
                f"final-review input manifest has invalid {field}"
            )
    authorities = payload.get("authorities")
    if not isinstance(authorities, dict) or set(authorities) != _AUTHORITY_FIELDS:
        raise RuntimeContractError(
            "final-review input manifest has invalid authorities"
        )
    if (
        authorities.get("schema") != "aegis.run_authority_evidence.v1"
        or authorities.get("workflow_run_id") != workflow_run_id
        or not isinstance(authorities.get("project_seal"), dict)
        or not isinstance(authorities.get("remote_witness_required"), bool)
        or not isinstance(
            authorities.get("tracerelay_observed_identity_required"), bool
        )
        or not isinstance(authorities.get("tracerelay_runtime"), dict)
    ):
        raise RuntimeContractError(
            "final-review input manifest authority identity is invalid"
        )
    _validate_descriptor(
        authorities.get("project_seal_record"),
        "project_seal_record",
    )
    if authorities["remote_witness_required"] and not isinstance(
        authorities.get("remote_witness"), dict
    ):
        raise RuntimeContractError(
            "final-review input manifest lacks the required remote witness"
        )
    tracerelay_runtime = authorities["tracerelay_runtime"]
    if (
        authorities["tracerelay_observed_identity_required"]
        and tracerelay_runtime.get("observed_identity") is None
    ):
        raise RuntimeContractError(
            "final-review input manifest lacks observed TraceRelay identity"
        )
    planning = payload.get("planning")
    if (
        not isinstance(planning, dict)
        or set(planning) != {"rounds", "reuse", "turns"}
        or not isinstance(planning.get("rounds"), list)
        or planning.get("reuse") is not None
        and not isinstance(planning.get("reuse"), dict)
        or not isinstance(planning.get("turns"), list)
    ):
        raise RuntimeContractError(
            "final-review input manifest has invalid planning records"
        )
    execution = payload.get("execution")
    if (
        not isinstance(execution, dict)
        or set(execution) != {"attempts", "turns", "evidence_sessions"}
        or not all(
            isinstance(execution.get(field), list)
            for field in ("attempts", "turns", "evidence_sessions")
        )
    ):
        raise RuntimeContractError(
            "final-review input manifest has invalid execution records"
        )
    required = payload.get("required_evidence")
    if not isinstance(required, list) or not required:
        raise RuntimeContractError(
            "final-review input manifest has no required evidence"
        )
    normalized: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for index, item in enumerate(required):
        if not isinstance(item, dict) or set(item) != {
            "evidence_id",
            *_DESCRIPTOR_FIELDS,
        }:
            raise RuntimeContractError(
                f"required final-review evidence {index} has invalid fields"
            )
        evidence_id = item.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id:
            raise RuntimeContractError(
                f"required final-review evidence {index} has an invalid ID"
            )
        if evidence_id in seen_ids:
            raise RuntimeContractError(
                "required final-review evidence IDs are not unique"
            )
        _validate_descriptor(item, f"required_evidence[{index}]")
        path = str(item["path"]).casefold()
        if path in seen_paths:
            raise RuntimeContractError(
                "required final-review evidence paths are not unique"
            )
        seen_ids.add(evidence_id)
        seen_paths.add(path)
        normalized.append(dict(item))
    return normalized


def _validate_descriptor(value: object, label: str) -> None:
    if not isinstance(value, Mapping) or not _DESCRIPTOR_FIELDS.issubset(value):
        raise RuntimeContractError(f"{label} is not a file descriptor")
    path = value.get("path")
    size = value.get("size")
    sha256 = value.get("sha256")
    if not isinstance(path, str) or not path:
        raise RuntimeContractError(f"{label} has an invalid path")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise RuntimeContractError(f"{label} has an invalid size")
    if not isinstance(sha256, str) or _SHA256_PATTERN.fullmatch(sha256) is None:
        raise RuntimeContractError(f"{label} has an invalid SHA-256")
