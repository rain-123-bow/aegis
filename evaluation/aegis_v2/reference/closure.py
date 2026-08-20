from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import re
from pathlib import Path
from typing import Any

from .canonical import (
    content_id,
    jcs_bytes,
    loads_json,
    sha256_hex,
    sha256_hex_bytes,
    verify_self_hash,
    with_self_hash,
)
from .schema_validation import local_schema_bundle


VALID_ASSERTIONS = sorted(
    [
        "ASSERT-APPEND-ONLY-CLOSURE-EVENT",
        "ASSERT-OWNER-AND-REVIEWER-EVIDENCE-LOADED",
        "ASSERT-REVIEWER-NEITHER-ORIGIN-NOR-OWNER",
    ]
)
REJECT_ASSERTIONS = sorted(
    [
        "ASSERT-BLOCKER-REMAINS-OPEN",
        "ASSERT-INDEPENDENT-CLOSURE-GATE",
        "ASSERT-NO-IN-PLACE-BLOCKER-OVERWRITE",
    ]
)


def evaluate_closure_assignment(assignment: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if assignment["reviewer_relation"] != "INDEPENDENT":
        reasons.append("REASON-REVIEWER-NOT-INDEPENDENT")
    if assignment["owner_evidence"] != "PRESENT_VALID":
        reasons.append("REASON-OWNER-EVIDENCE-INVALID")
    if assignment["reviewer_evidence"] != "PRESENT_VALID":
        reasons.append("REASON-REVIEWER-EVIDENCE-INVALID")
    if reasons:
        return {
            "algorithm_id": "ORACLE-BLOCKER-CLOSURE-INDEPENDENCE-V1",
            "outcome": "REJECT",
            "decision": None,
            "reason_ids": sorted(reasons),
            "assertion_ids": REJECT_ASSERTIONS,
        }
    return {
        "algorithm_id": "ORACLE-BLOCKER-CLOSURE-INDEPENDENCE-V1",
        "outcome": "ACCEPT",
        "decision": None,
        "reason_ids": ["REASON-BLOCKER-CLOSURE-VALID"],
        "assertion_ids": VALID_ASSERTIONS,
    }


def _physical_identity(identity: dict[str, Any]) -> tuple[Any, Any]:
    return identity.get("thread_id"), identity.get("session_id")


def _schema_reasons(
    value: Any,
    schema_name: str,
    reason_prefix: str,
    schema_dir: Path,
) -> list[str]:
    bundle = local_schema_bundle(str(schema_dir.resolve()))
    return [
        f"{reason_prefix}:{index:04d}"
        for index, _ in enumerate(bundle.errors(value, schema_name), start=1)
    ]


def _validate_evidence_set(
    label: str,
    refs: list[str],
    expected_identity: dict[str, Any],
    blocker: dict[str, Any],
    records: dict[str, dict[str, Any]],
    raw_evidence: dict[str, bytes],
    schema_dir: Path,
) -> list[str]:
    reasons: list[str] = []
    prefix = f"REASON-{label}-EVIDENCE"
    if not refs:
        return [f"{prefix}-MISSING"]
    for evidence_id in refs:
        record = records.get(evidence_id)
        if record is None:
            reasons.append(f"{prefix}-RECORD-MISSING")
            continue
        reasons.extend(
            _schema_reasons(
                record,
                "evidence_record.v1.schema.json",
                f"{prefix}-SCHEMA-INVALID",
                schema_dir,
            )
        )
        if record.get("evidence_id") != evidence_id:
            reasons.append(f"{prefix}-ID-MISMATCH")
        producer = record.get("producer_identity", {})
        if producer.get("kind") != "AGENT" or producer.get(
            "identity"
        ) != expected_identity:
            reasons.append(f"{prefix}-PRODUCER-IDENTITY-MISMATCH")
        if record.get("validity", {}).get("state") != "ACTIVE":
            reasons.append(f"{prefix}-NOT-ACTIVE")
        for field, suffix in (
            ("source_baseline_id", "SOURCE-BASELINE-MISMATCH"),
            ("test_plan_revision_id", "TEST-PLAN-MISMATCH"),
            ("execution_contract_id", "EXECUTION-CONTRACT-MISMATCH"),
        ):
            if record.get(field) != blocker.get(field):
                reasons.append(f"{prefix}-{suffix}")
        raw = raw_evidence.get(evidence_id)
        if raw is None:
            reasons.append(f"{prefix}-RAW-BYTES-MISSING")
            continue
        content = record.get("content", {})
        if content.get("mode") != "SHA256":
            reasons.append(f"{prefix}-RAW-HASH-CONTRACT-MISSING")
            continue
        if content.get("byte_size") != len(raw):
            reasons.append(f"{prefix}-BYTE-SIZE-MISMATCH")
        if content.get("sha256") != hashlib.sha256(raw).hexdigest():
            reasons.append(f"{prefix}-CONTENT-HASH-MISMATCH")
    return reasons


def evaluate_closure(
    blocker: dict[str, Any],
    closure_event: dict[str, Any],
    evidence_records: dict[str, dict[str, Any]],
    evidence_bytes: dict[str, bytes],
    dependency_propagation: dict[str, Any],
    *,
    schema_dir: str | Path,
) -> dict[str, Any]:
    """Validate one append-only closure without reading or importing the SUT."""

    schema_path = Path(schema_dir)
    reasons: list[str] = []
    reasons.extend(
        _schema_reasons(
            blocker,
            "blocker_record.v1.schema.json",
            "REASON-BLOCKER-SCHEMA-INVALID",
            schema_path,
        )
    )
    reasons.extend(
        _schema_reasons(
            closure_event,
            "blocker_closure_event.v1.schema.json",
            "REASON-CLOSURE-EVENT-SCHEMA-INVALID",
            schema_path,
        )
    )
    if blocker.get("status") != "OPEN":
        reasons.append("REASON-SOURCE-BLOCKER-NOT-OPEN")
    if any(
        event.get("closure_result") == "CLOSED"
        for event in blocker.get("closure_events", [])
    ):
        reasons.append("REASON-SOURCE-BLOCKER-ALREADY-CLOSED")
    if closure_event.get("closure_result") != "CLOSED":
        reasons.append("REASON-CLOSURE-RESULT-NOT-CLOSED")
    if closure_event.get("blocker_id") != blocker.get("blocker_id"):
        reasons.append("REASON-BLOCKER-ID-MISMATCH")
    source_blocker_id = content_id(blocker)
    if closure_event.get("source_blocker_content_id") != source_blocker_id:
        reasons.append("REASON-SOURCE-BLOCKER-HASH-MISMATCH")
    if not verify_self_hash(
        closure_event, "closure_event_content_id", prefix=True
    ):
        reasons.append("REASON-CLOSURE-EVENT-SELF-HASH-MISMATCH")

    for field, reason in (
        ("origin_role", "REASON-ORIGIN-ROLE-MISMATCH"),
        ("owner_role", "REASON-OWNER-ROLE-MISMATCH"),
        ("source_baseline_id", "REASON-SOURCE-BASELINE-MISMATCH"),
        ("test_plan_revision_id", "REASON-TEST-PLAN-MISMATCH"),
        ("execution_contract_id", "REASON-EXECUTION-CONTRACT-MISMATCH"),
    ):
        if closure_event.get(field) != blocker.get(field):
            reasons.append(reason)

    owner = closure_event.get("owner_identity", {})
    reviewer = closure_event.get("reviewer_identity", {})
    if owner.get("role_slot_id") != blocker.get("owner_role"):
        reasons.append("REASON-OWNER-IDENTITY-ROLE-MISMATCH")
    reviewer_role = reviewer.get("role_slot_id")
    if reviewer_role in {
        blocker.get("origin_role"),
        blocker.get("owner_role"),
    }:
        reasons.append("REASON-REVIEWER-NOT-INDEPENDENT")
    if _physical_identity(owner) == _physical_identity(reviewer):
        reasons.append("REASON-REVIEWER-PHYSICAL-IDENTITY-REUSED")

    owner_refs = closure_event.get("owner_evidence_refs", [])
    reviewer_refs = closure_event.get("reviewer_evidence_refs", [])
    if set(owner_refs) & set(reviewer_refs):
        reasons.append("REASON-OWNER-REVIEWER-EVIDENCE-NOT-DISJOINT")
    reasons.extend(
        _validate_evidence_set(
            "OWNER",
            owner_refs,
            owner,
            blocker,
            evidence_records,
            evidence_bytes,
            schema_path,
        )
    )
    reasons.extend(
        _validate_evidence_set(
            "REVIEWER",
            reviewer_refs,
            reviewer,
            blocker,
            evidence_records,
            evidence_bytes,
            schema_path,
        )
    )

    if dependency_propagation.get(
        "source_blocker_content_id"
    ) != source_blocker_id:
        reasons.append("REASON-DEPENDENCY-SOURCE-BLOCKER-MISMATCH")
    if dependency_propagation.get("severity") != blocker.get("severity"):
        reasons.append("REASON-DEPENDENCY-SEVERITY-MISMATCH")
    expected_artifacts = sorted(
        artifact["artifact_id"] for artifact in blocker.get("affected_artifacts", [])
    )
    if dependency_propagation.get("invalidated_artifact_ids") != expected_artifacts:
        reasons.append("REASON-DEPENDENCY-ARTIFACT-PROPAGATION-MISMATCH")
    expected_cases = sorted(blocker.get("affected_case_ids", []))
    if dependency_propagation.get("invalidated_case_ids") != expected_cases:
        reasons.append("REASON-DEPENDENCY-CASE-PROPAGATION-MISMATCH")
    prohibited_used = dependency_propagation.get(
        "prohibited_substitutes_used", []
    )
    if prohibited_used:
        reasons.append("REASON-PROHIBITED-SUBSTITUTE-USED")

    reason_ids = sorted(set(reasons))
    return {
        "algorithm_id": "ORACLE-BLOCKER-CLOSURE-INDEPENDENCE-V1",
        "accepted": not reason_ids,
        "closure_result": "CLOSED" if not reason_ids else "REJECTED",
        "reason_ids": reason_ids,
        "source_blocker_content_id": source_blocker_id,
    }


def closure_sut_decision(assignment: dict[str, Any]) -> dict[str, Any]:
    """Return only the context-free SUT decision expected on stdout."""

    reference = evaluate_closure_assignment(assignment)
    return with_self_hash(
        {
            "schema_version": "SutDecision.v1",
            "outcome": reference["outcome"],
            "decision": None,
            "reason_ids": reference["reason_ids"],
            "assertion_ids": reference["assertion_ids"],
        },
        "sut_decision_sha256",
    )


def expected_closure_record(
    envelope: dict[str, Any],
    *,
    sut_output_artifact_raw_sha256: str,
    oracle_source_manifest_entry_sha256: str,
) -> dict[str, Any]:
    """Assemble the evaluator-only record after output-byte freeze."""

    if not verify_self_hash(
        envelope, "envelope_sha256", prefix=True
    ):
        raise ValueError("property envelope self-hash mismatch")
    for label, digest in (
        (
            "sut_output_artifact_raw_sha256",
            sut_output_artifact_raw_sha256,
        ),
        (
            "oracle_source_manifest_entry_sha256",
            oracle_source_manifest_entry_sha256,
        ),
    ):
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError(f"{label} must be lowercase SHA-256")
    record = {
        "schema_version": "PropertyExpectedRecord.v1",
        "suite_id": envelope["suite_id"],
        "ordinal": envelope["ordinal"],
        "instance_id": envelope["instance_id"],
        "case_id": envelope["case_id"],
        "envelope_sha256": envelope["envelope_sha256"],
        "oracle_algorithm_id": (
            "ORACLE-BLOCKER-CLOSURE-INDEPENDENCE-V1"
        ),
        "oracle_source_manifest_entry_sha256": (
            oracle_source_manifest_entry_sha256
        ),
        "generated_after_sut_output_freeze": True,
        "sut_output_artifact_raw_sha256": (
            sut_output_artifact_raw_sha256
        ),
        "expected": closure_sut_decision(
            copy.deepcopy(envelope["assignment"])
        ),
    }
    return with_self_hash(record, "record_sha256", prefix=True)


_CONTEXT_SCHEMAS = {
    "AGENT-REGISTRY": "agent_registry.v1.schema.json",
    "OWNER-DISPATCH": "dispatch_action.v1.schema.json",
    "OWNER-AUTHORITY": "codex_authority_event.v1.schema.json",
    "OWNER-COMPLETE-RECEIPT": "agent_receipt.v1.schema.json",
    "OWNER-INGEST-RECEIPT": "agent_receipt.v1.schema.json",
    "OWNER-EVIDENCE-REVISION-1": "evidence_record.v1.schema.json",
    "OWNER-EVIDENCE-REVISION-2": "evidence_record.v1.schema.json",
    "REVIEWER-DISPATCH": "dispatch_action.v1.schema.json",
    "REVIEWER-AUTHORITY": "codex_authority_event.v1.schema.json",
    "REVIEWER-COMPLETE-RECEIPT": "agent_receipt.v1.schema.json",
    "REVIEWER-INGEST-RECEIPT": "agent_receipt.v1.schema.json",
    "REVIEWER-EVIDENCE-REVISION-1": "evidence_record.v1.schema.json",
    "REVIEWER-EVIDENCE-REVISION-2": "evidence_record.v1.schema.json",
}
_OWNER_PREIMAGE_FIELDS = {
    "schema_version",
    "blocker_id",
    "source_blocker_content_id",
    "addressed_requirement_id",
    "owner_action_id",
    "owner_completion_receipt_id",
    "owner_ingest_receipt_id",
    "owner_identity",
    "source_baseline_id",
    "test_plan_revision_id",
    "execution_contract_id",
    "corrected_artifacts",
    "dependency_propagation",
}
_REVIEWER_PREIMAGE_FIELDS = {
    "schema_version",
    "blocker_id",
    "source_blocker_content_id",
    "reviewed_owner_evidence_id",
    "reviewed_owner_record_id",
    "reviewed_owner_preimage_sha256",
    "owner_identity",
    "reviewer_action_id",
    "reviewer_completion_receipt_id",
    "reviewer_ingest_receipt_id",
    "reviewer_identity",
    "source_baseline_id",
    "test_plan_revision_id",
    "execution_contract_id",
    "verified_requirement_id",
    "verification_result",
}


def _reasoned_schema_errors(
    validator: Any,
    value: Any,
    schema_name: str,
    prefix: str,
) -> list[str]:
    return [
        f"{prefix}-SCHEMA-{index:04d}"
        for index, _ in enumerate(
            validator.errors(value, schema_name), start=1
        )
    ]


def _decode_fixtures(
    fixtures: Any,
) -> tuple[dict[str, tuple[dict[str, Any], bytes]], list[str]]:
    indexed: dict[str, tuple[dict[str, Any], bytes]] = {}
    reasons: list[str] = []
    if not isinstance(fixtures, list):
        return indexed, ["REASON-FIXTURE-SET-NOT-ARRAY"]
    paths: set[str] = set()
    for fixture in fixtures:
        if not isinstance(fixture, dict):
            reasons.append("REASON-FIXTURE-NOT-OBJECT")
            continue
        fixture_id = fixture.get("fixture_id")
        path = fixture.get("logical_runtime_path")
        if not isinstance(fixture_id, str) or fixture_id in indexed:
            reasons.append("REASON-FIXTURE-ID-NOT-UNIQUE")
            continue
        if not isinstance(path, str) or path.casefold() in paths:
            reasons.append("REASON-FIXTURE-PATH-NOT-UNIQUE")
        elif isinstance(path, str):
            paths.add(path.casefold())
        try:
            raw = base64.b64decode(
                fixture.get("raw_base64", ""), validate=True
            )
        except (binascii.Error, ValueError):
            reasons.append(f"REASON-FIXTURE-BASE64-INVALID:{fixture_id}")
            continue
        raw_sha256 = sha256_hex_bytes(raw)
        if fixture.get("byte_size") != len(raw):
            reasons.append(f"REASON-FIXTURE-SIZE-MISMATCH:{fixture_id}")
        if fixture.get("raw_sha256") != raw_sha256:
            reasons.append(f"REASON-FIXTURE-HASH-MISMATCH:{fixture_id}")
        if fixture.get("content_id") != f"sha256:{raw_sha256}":
            reasons.append(
                f"REASON-FIXTURE-CONTENT-ID-MISMATCH:{fixture_id}"
            )
        if fixture.get("media_type") == "application/json":
            try:
                value = loads_json(raw, source=fixture_id)
            except ValueError:
                reasons.append(
                    f"REASON-FIXTURE-JSON-INVALID:{fixture_id}"
                )
            else:
                if raw != jcs_bytes(value):
                    reasons.append(
                        f"REASON-FIXTURE-JSON-NOT-JCS:{fixture_id}"
                    )
                if fixture.get("jcs_sha256") != sha256_hex(value):
                    reasons.append(
                        f"REASON-FIXTURE-JCS-HASH-MISMATCH:{fixture_id}"
                    )
        indexed[fixture_id] = (fixture, raw)
    return indexed, reasons


def _context_index(
    runner_input: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    grouped: dict[str, list[Any]] = {}
    reasons: list[str] = []
    for item in runner_input.get("context_objects", []):
        if not isinstance(item, dict):
            reasons.append("REASON-CONTEXT-OBJECT-MALFORMED")
            continue
        grouped.setdefault(str(item.get("object_role")), []).append(
            item.get("value")
        )
    required = set(_CONTEXT_SCHEMAS) | {"CLOSURE-EVENT"}
    if set(grouped) != required:
        for role in sorted(required - set(grouped)):
            reasons.append(f"REASON-CONTEXT-ROLE-MISSING:{role}")
        for role in sorted(set(grouped) - required):
            reasons.append(f"REASON-CONTEXT-ROLE-EXTRA:{role}")
    indexed: dict[str, dict[str, Any]] = {}
    for role in sorted(required):
        values = grouped.get(role, [])
        if len(values) != 1:
            reasons.append(
                f"REASON-CONTEXT-ROLE-CARDINALITY:{role}:{len(values)}"
            )
        elif isinstance(values[0], dict):
            indexed[role] = values[0]
        else:
            reasons.append(f"REASON-CONTEXT-VALUE-MALFORMED:{role}")
    return indexed, reasons


def _identity_from_registry(
    registry: dict[str, Any], role_slot_id: Any
) -> dict[str, Any] | None:
    matches = [
        pointer
        for pointer in registry.get("active_role_pointers", [])
        if isinstance(pointer, dict)
        and pointer.get("role_slot_id") == role_slot_id
    ]
    if len(matches) != 1:
        return None
    identity = matches[0]
    records = [
        record
        for record in registry.get("identities", [])
        if isinstance(record, dict)
        and record.get("identity") == identity
        and record.get("lifecycle_state") == "ACTIVE"
        and record.get("capability_state") == "VERIFIED"
    ]
    return identity if len(records) == 1 else None


def _fixture_at_path(
    fixtures: dict[str, tuple[dict[str, Any], bytes]],
    logical_runtime_path: Any,
) -> tuple[dict[str, Any], bytes] | None:
    matches = [
        fixture
        for fixture in fixtures.values()
        if fixture[0].get("logical_runtime_path") == logical_runtime_path
    ]
    return matches[0] if len(matches) == 1 else None


def _check_channel(
    label: str,
    context: dict[str, dict[str, Any]],
    registry: dict[str, Any],
    fixtures: dict[str, tuple[dict[str, Any], bytes]],
) -> tuple[dict[str, Any] | None, list[str]]:
    prefix = label.upper()
    reasons: list[str] = []
    try:
        action = context[f"{prefix}-DISPATCH"]
        authority = context[f"{prefix}-AUTHORITY"]
        complete = context[f"{prefix}-COMPLETE-RECEIPT"]
        ingest = context[f"{prefix}-INGEST-RECEIPT"]
        revision_1 = context[f"{prefix}-EVIDENCE-REVISION-1"]
        revision_2 = context[f"{prefix}-EVIDENCE-REVISION-2"]
    except KeyError:
        return None, [f"REASON-{prefix}-CHAIN-INCOMPLETE"]

    identity = _identity_from_registry(
        registry, action.get("target_role_slot_id")
    )
    target_projection = {
        "role_slot_id": action.get("target_role_slot_id"),
        "role": action.get("target_role"),
        "source_generation_id": action.get("target_generation"),
        "instance_revision": action.get("target_instance_revision"),
        "agent_handle": action.get("target_agent_handle"),
        "handle_source": (
            identity.get("handle_source")
            if isinstance(identity, dict)
            else None
        ),
        "thread_id": action.get("target_thread_id"),
        "session_id": action.get("target_session_id"),
    }
    if identity is None or target_projection != identity:
        reasons.append(f"REASON-{prefix}-REGISTRY-IDENTITY-MISMATCH")
    if (
        action.get("source_baseline_id")
        != registry.get("current_source_baseline_id")
        or action.get("registry_snapshot_id")
        != registry.get("current_registry_snapshot_id")
    ):
        reasons.append(f"REASON-{prefix}-DISPATCH-REGISTRY-MISMATCH")
    payload_fixture = _fixture_at_path(
        fixtures, action.get("payload_path")
    )
    if (
        payload_fixture is None
        or sha256_hex_bytes(payload_fixture[1])
        != action.get("payload_sha256")
    ):
        reasons.append(f"REASON-{prefix}-DISPATCH-PAYLOAD-MISMATCH")

    child = authority.get("child_result_binding", {})
    if (
        authority.get("event_purpose") != "CHILD_RESULT"
        or authority.get("thread", {}).get("id")
        != action.get("target_thread_id")
        or child.get("child_thread_id") != action.get("target_thread_id")
    ):
        reasons.append(f"REASON-{prefix}-AUTHORITY-IDENTITY-MISMATCH")
    raw_by_kind: dict[str, dict[str, Any]] = {}
    for raw_record in authority.get("raw_records", []):
        if not isinstance(raw_record, dict):
            reasons.append(f"REASON-{prefix}-AUTHORITY-RAW-MALFORMED")
            continue
        kind = raw_record.get("record_kind")
        if kind in raw_by_kind:
            reasons.append(f"REASON-{prefix}-AUTHORITY-RAW-DUPLICATE")
        raw_by_kind[str(kind)] = raw_record
        raw_fixture = _fixture_at_path(
            fixtures, raw_record.get("runtime_path")
        )
        if (
            raw_fixture is None
            or len(raw_fixture[1]) != raw_record.get("byte_size")
            or sha256_hex_bytes(raw_fixture[1])
            != raw_record.get("raw_sha256")
        ):
            reasons.append(
                f"REASON-{prefix}-AUTHORITY-RAW-BYTES-MISMATCH"
            )
    if set(raw_by_kind) != {"ITEM_COMPLETED", "TURN_COMPLETED"}:
        reasons.append(f"REASON-{prefix}-AUTHORITY-RAW-SET-MISMATCH")
    else:
        if (
            child.get("item_completed_raw_sha256")
            != raw_by_kind["ITEM_COMPLETED"].get("raw_sha256")
            or child.get("turn_completed_raw_sha256")
            != raw_by_kind["TURN_COMPLETED"].get("raw_sha256")
            or child.get("child_turn_id")
            != raw_by_kind["ITEM_COMPLETED"].get("turn_id")
            or child.get("child_turn_id")
            != raw_by_kind["TURN_COMPLETED"].get("turn_id")
            or child.get("child_item_id")
            != raw_by_kind["ITEM_COMPLETED"].get("item_id")
        ):
            reasons.append(
                f"REASON-{prefix}-AUTHORITY-CHILD-RESULT-MISMATCH"
            )

    expected_receipt = (
        ("COMPLETE", "COMPLETED", complete),
        ("INGEST", "ACCEPTED", ingest),
    )
    for kind, status, receipt in expected_receipt:
        if (
            receipt.get("receipt_kind") != kind
            or receipt.get("receipt_status") != status
            or receipt.get("action") != action
            or receipt.get("action_id") != action.get("action_id")
            or receipt.get("payload_sha256")
            != action.get("payload_sha256")
            or receipt.get("observed_identity") != identity
            or receipt.get("authority_event") != authority
        ):
            reasons.append(
                f"REASON-{prefix}-{kind}-RECEIPT-LINK-MISMATCH"
            )
    if complete.get("receipt_id") == ingest.get("receipt_id"):
        reasons.append(f"REASON-{prefix}-RECEIPT-ID-REUSED")

    evidence_id = (
        "EVIDENCE-OWNER-CORRECTION"
        if prefix == "OWNER"
        else "EVIDENCE-INDEPENDENT-REVIEW"
    )
    for revision, number in ((revision_1, 1), (revision_2, 2)):
        origin = revision.get("origin", {})
        producer = revision.get("producer_identity", {})
        if (
            revision.get("evidence_id") != evidence_id
            or revision.get("record_revision") != number
            or revision.get("attempt_id") != action.get("attempt_id")
            or origin.get("action_id") != action.get("action_id")
            or origin.get("completion_receipt_id")
            != complete.get("receipt_id")
            or origin.get("ingest_receipt_id") != ingest.get("receipt_id")
            or origin.get("authority_event_ids")
            != [authority.get("authority_event_id")]
            or producer.get("kind") != "AGENT"
            or producer.get("identity") != identity
            or revision.get("registry_snapshot_id")
            != registry.get("current_registry_snapshot_id")
            or origin.get("registry_snapshot_id")
            != registry.get("current_registry_snapshot_id")
        ):
            reasons.append(
                f"REASON-{prefix}-EVIDENCE-REVISION-{number}-LINK-MISMATCH"
            )
    if (
        revision_1.get("supersedes_record_id") is not None
        or revision_2.get("supersedes_record_id")
        != revision_1.get("record_id")
        or revision_1.get("validity", {}).get("state") != "STALE"
    ):
        reasons.append(f"REASON-{prefix}-EVIDENCE-REVISION-CHAIN-INVALID")

    fixture_id = (
        "FIXTURE-OWNER-CORRECTION-PREIMAGE"
        if prefix == "OWNER"
        else "FIXTURE-INDEPENDENT-REVIEW-PREIMAGE"
    )
    fixture = fixtures.get(fixture_id)
    if fixture is None:
        reasons.append(f"REASON-{prefix}-PREIMAGE-MISSING")
        return None, reasons
    fixture_record, raw = fixture
    raw_sha256 = sha256_hex_bytes(raw)
    result = complete.get("result") or {}
    evidence_content = revision_2.get("content") or {}
    if (
        child.get("outbox_result_sha256") != raw_sha256
        or child.get("outbox_result_path")
        != fixture_record.get("logical_runtime_path")
        or result.get("result_sha256") != raw_sha256
        or result.get("result_path")
        != fixture_record.get("logical_runtime_path")
        or evidence_content.get("sha256") != raw_sha256
        or evidence_content.get("byte_size") != len(raw)
        or revision_1.get("content") != evidence_content
    ):
        reasons.append(f"REASON-{prefix}-PREIMAGE-PROVENANCE-MISMATCH")
    try:
        preimage = loads_json(raw, source=fixture_id)
    except ValueError:
        reasons.append(f"REASON-{prefix}-PREIMAGE-JSON-INVALID")
        return None, reasons
    if not isinstance(preimage, dict):
        reasons.append(f"REASON-{prefix}-PREIMAGE-NOT-OBJECT")
        return None, reasons
    return preimage, reasons


def _check_owner_preimage(
    preimage: dict[str, Any],
    blocker: dict[str, Any],
    source_blocker_id: str,
    context: dict[str, dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if "prohibited_substitutes_used" in preimage:
        reasons.append(
            "REASON-PROHIBITED-SUBSTITUTE-SELF-REPORT-FORBIDDEN"
        )
    if set(preimage) != _OWNER_PREIMAGE_FIELDS:
        reasons.append("REASON-OWNER-OBLIGATION-FIELDS-INVALID")
    action = context.get("OWNER-DISPATCH", {})
    complete = context.get("OWNER-COMPLETE-RECEIPT", {})
    ingest = context.get("OWNER-INGEST-RECEIPT", {})
    identity = _identity_from_registry(
        context.get("AGENT-REGISTRY", {}),
        action.get("target_role_slot_id"),
    )
    required = {
        "schema_version": "OwnerCorrectionEvidence.v1",
        "blocker_id": blocker.get("blocker_id"),
        "source_blocker_content_id": source_blocker_id,
        "addressed_requirement_id": blocker.get("violated_requirement"),
        "owner_action_id": action.get("action_id"),
        "owner_completion_receipt_id": complete.get("receipt_id"),
        "owner_ingest_receipt_id": ingest.get("receipt_id"),
        "owner_identity": identity,
        "source_baseline_id": blocker.get("source_baseline_id"),
        "test_plan_revision_id": blocker.get("test_plan_revision_id"),
        "execution_contract_id": blocker.get("execution_contract_id"),
    }
    if any(preimage.get(key) != value for key, value in required.items()):
        reasons.append("REASON-OWNER-OBLIGATION-BINDING-MISMATCH")
    dependency = preimage.get("dependency_propagation")
    expected_dependency = {
        "invalidated_artifact_ids": sorted(
            artifact.get("artifact_id")
            for artifact in blocker.get("affected_artifacts", [])
        ),
        "invalidated_case_ids": sorted(
            blocker.get("affected_case_ids", [])
        ),
        "severity": blocker.get("severity"),
    }
    if dependency != expected_dependency:
        reasons.append("REASON-OWNER-OBLIGATION-PROPAGATION-MISMATCH")
    corrected = preimage.get("corrected_artifacts")
    expected_artifacts = {
        (
            artifact.get("artifact_id"),
            artifact.get("run_relative_path"),
        )
        for artifact in blocker.get("affected_artifacts", [])
    }
    actual_artifacts = {
        (artifact.get("artifact_id"), artifact.get("run_relative_path"))
        for artifact in corrected
        if isinstance(artifact, dict)
    } if isinstance(corrected, list) else set()
    if (
        actual_artifacts != expected_artifacts
        or not isinstance(corrected, list)
        or any(
            not isinstance(artifact, dict)
            or set(artifact)
            != {"artifact_id", "run_relative_path", "sha256"}
            for artifact in corrected
        )
        or any(
            re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"]) is None
            for artifact in corrected
            if isinstance(artifact, dict)
        )
    ):
        reasons.append("REASON-OWNER-OBLIGATION-CORRECTION-MISMATCH")
    return reasons


def _check_reviewer_preimage(
    preimage: dict[str, Any],
    owner_preimage: dict[str, Any] | None,
    owner_preimage_sha256: str | None,
    blocker: dict[str, Any],
    source_blocker_id: str,
    context: dict[str, dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if set(preimage) != _REVIEWER_PREIMAGE_FIELDS:
        reasons.append("REASON-REVIEWER-OBLIGATION-FIELDS-INVALID")
    owner_action = context.get("OWNER-DISPATCH", {})
    reviewer_action = context.get("REVIEWER-DISPATCH", {})
    reviewer_complete = context.get("REVIEWER-COMPLETE-RECEIPT", {})
    reviewer_ingest = context.get("REVIEWER-INGEST-RECEIPT", {})
    registry = context.get("AGENT-REGISTRY", {})
    owner_identity = _identity_from_registry(
        registry, owner_action.get("target_role_slot_id")
    )
    reviewer_identity = _identity_from_registry(
        registry, reviewer_action.get("target_role_slot_id")
    )
    owner_revision = context.get("OWNER-EVIDENCE-REVISION-2", {})
    required = {
        "schema_version": "IndependentReviewEvidence.v1",
        "blocker_id": blocker.get("blocker_id"),
        "source_blocker_content_id": source_blocker_id,
        "reviewed_owner_evidence_id": owner_revision.get("evidence_id"),
        "reviewed_owner_record_id": owner_revision.get("record_id"),
        "reviewed_owner_preimage_sha256": owner_preimage_sha256,
        "owner_identity": owner_identity,
        "reviewer_action_id": reviewer_action.get("action_id"),
        "reviewer_completion_receipt_id": reviewer_complete.get(
            "receipt_id"
        ),
        "reviewer_ingest_receipt_id": reviewer_ingest.get("receipt_id"),
        "reviewer_identity": reviewer_identity,
        "source_baseline_id": blocker.get("source_baseline_id"),
        "test_plan_revision_id": blocker.get("test_plan_revision_id"),
        "execution_contract_id": blocker.get("execution_contract_id"),
        "verified_requirement_id": blocker.get("violated_requirement"),
        "verification_result": "VERIFIED",
    }
    if any(preimage.get(key) != value for key, value in required.items()):
        reasons.append("REASON-REVIEWER-OBLIGATION-BINDING-MISMATCH")
    if owner_preimage is None:
        reasons.append("REASON-REVIEWER-OWNER-PREIMAGE-UNAVAILABLE")
    return reasons


def evaluate_materialized_closure(
    bundle: dict[str, Any],
    *,
    schema_dir: str | Path,
) -> dict[str, Any]:
    """Audit the complete materialized provenance chain independently."""

    validator = local_schema_bundle(str(Path(schema_dir).resolve()))
    reasons = _reasoned_schema_errors(
        validator,
        bundle,
        "property_materialization_bundle.v1.schema.json",
        "REASON-MATERIALIZATION-BUNDLE",
    )
    if not isinstance(bundle, dict):
        reasons.append("REASON-MATERIALIZATION-BUNDLE-NOT-OBJECT")
        return _materialized_closure_result(None, reasons)
    if not verify_self_hash(bundle, "bundle_sha256", prefix=True):
        reasons.append("REASON-MATERIALIZATION-BUNDLE-SELF-HASH-MISMATCH")
    fixtures_raw = bundle.get("sut_materialized_fixtures", [])
    if (
        sha256_hex(fixtures_raw)
        != bundle.get("sut_materialized_fixtures_jcs_sha256")
    ):
        reasons.append("REASON-FIXTURE-SET-HASH-MISMATCH")
    fixtures, fixture_reasons = _decode_fixtures(fixtures_raw)
    reasons.extend(fixture_reasons)
    runner_input = bundle.get("runner_input")
    if not isinstance(runner_input, dict):
        reasons.append("REASON-RUNNER-INPUT-NOT-OBJECT")
        return _materialized_closure_result(None, reasons)
    reasons.extend(
        _reasoned_schema_errors(
            validator,
            runner_input,
            "evaluation_runner_input.v1.schema.json",
            "REASON-RUNNER-INPUT",
        )
    )
    if runner_input.get("fixture_refs") != [
        fixture.get("fixture_id")
        for fixture in fixtures_raw
        if isinstance(fixture, dict)
    ]:
        reasons.append("REASON-RUNNER-FIXTURE-REFS-MISMATCH")
    blocker = runner_input.get("subject")
    if not isinstance(blocker, dict):
        reasons.append("REASON-BLOCKER-NOT-OBJECT")
        return _materialized_closure_result(None, reasons)
    reasons.extend(
        _reasoned_schema_errors(
            validator,
            blocker,
            "blocker_record.v1.schema.json",
            "REASON-BLOCKER",
        )
    )
    source_blocker_id = content_id(blocker)
    context, context_reasons = _context_index(runner_input)
    reasons.extend(context_reasons)
    if set(_CONTEXT_SCHEMAS) <= set(context):
        for role, schema_name in _CONTEXT_SCHEMAS.items():
            reasons.extend(
                _reasoned_schema_errors(
                    validator,
                    context[role],
                    schema_name,
                    f"REASON-{role}",
                )
            )
    registry = context.get("AGENT-REGISTRY", {})
    pointers = registry.get("active_role_pointers", [])
    if (
        len(pointers) != 6
        or len(
            {
                pointer.get("role_slot_id")
                for pointer in pointers
                if isinstance(pointer, dict)
            }
        )
        != 6
    ):
        reasons.append("REASON-AGENT-REGISTRY-ACTIVE-SET-INVALID")
    for identity_record in registry.get("identities", []):
        if not isinstance(identity_record, dict):
            reasons.append("REASON-AGENT-REGISTRY-IDENTITY-MALFORMED")
            continue
        authority = identity_record.get("authority_event", {})
        raw_records = authority.get("raw_records", [])
        if (
            authority.get("event_purpose") != "CAPABILITY"
            or len(raw_records) != 1
            or not isinstance(raw_records[0], dict)
        ):
            reasons.append(
                "REASON-AGENT-REGISTRY-CAPABILITY-AUTHORITY-INVALID"
            )
            continue
        raw_record = raw_records[0]
        raw_fixture = _fixture_at_path(
            fixtures, raw_record.get("runtime_path")
        )
        if (
            raw_fixture is None
            or len(raw_fixture[1]) != raw_record.get("byte_size")
            or sha256_hex_bytes(raw_fixture[1])
            != raw_record.get("raw_sha256")
        ):
            reasons.append(
                "REASON-AGENT-REGISTRY-CAPABILITY-BYTES-MISMATCH"
            )
    owner_preimage, owner_reasons = _check_channel(
        "owner", context, registry, fixtures
    )
    reviewer_preimage, reviewer_reasons = _check_channel(
        "reviewer", context, registry, fixtures
    )
    reasons.extend(owner_reasons)
    reasons.extend(reviewer_reasons)
    if owner_preimage is not None:
        reasons.extend(
            _check_owner_preimage(
                owner_preimage, blocker, source_blocker_id, context
            )
        )
    owner_fixture = fixtures.get("FIXTURE-OWNER-CORRECTION-PREIMAGE")
    owner_sha256 = (
        sha256_hex_bytes(owner_fixture[1])
        if owner_fixture is not None
        else None
    )
    if reviewer_preimage is not None:
        reasons.extend(
            _check_reviewer_preimage(
                reviewer_preimage,
                owner_preimage,
                owner_sha256,
                blocker,
                source_blocker_id,
                context,
            )
        )

    closure_value = context.get("CLOSURE-EVENT")
    closure_event: dict[str, Any] | None = None
    if isinstance(closure_value, dict) and closure_value.get(
        "schema_version"
    ) == "UnvalidatedCandidate.v1":
        reasons.extend(
            _reasoned_schema_errors(
                validator,
                closure_value,
                "unvalidated_candidate.v1.schema.json",
                "REASON-CLOSURE-CANDIDATE",
            )
        )
        candidate = closure_value.get("candidate")
        if (
            isinstance(candidate, dict)
            and closure_value.get("candidate_sha256")
            == sha256_hex(candidate)
        ):
            closure_event = candidate
        else:
            reasons.append("REASON-CLOSURE-CANDIDATE-HASH-MISMATCH")
        reasons.append("REASON-REVIEWER-NOT-INDEPENDENT")
    elif isinstance(closure_value, dict):
        closure_event = closure_value
        reasons.extend(
            _reasoned_schema_errors(
                validator,
                closure_event,
                "blocker_closure_event.v1.schema.json",
                "REASON-CLOSURE-EVENT",
            )
        )
    else:
        reasons.append("REASON-CLOSURE-EVENT-MISSING")

    if closure_event is not None:
        if not verify_self_hash(
            closure_event, "closure_event_content_id", prefix=True
        ):
            reasons.append("REASON-CLOSURE-EVENT-SELF-HASH-MISMATCH")
        owner_identity = _identity_from_registry(
            registry, blocker.get("owner_role")
        )
        reviewer_identity = closure_event.get("reviewer_identity", {})
        if (
            closure_event.get("blocker_id") != blocker.get("blocker_id")
            or closure_event.get("source_blocker_content_id")
            != source_blocker_id
            or closure_event.get("origin_role")
            != blocker.get("origin_role")
            or closure_event.get("owner_role") != blocker.get("owner_role")
            or closure_event.get("owner_identity") != owner_identity
            or closure_event.get("owner_evidence_refs")
            != ["EVIDENCE-OWNER-CORRECTION"]
            or closure_event.get("reviewer_evidence_refs")
            != ["EVIDENCE-INDEPENDENT-REVIEW"]
            or closure_event.get("source_baseline_id")
            != blocker.get("source_baseline_id")
            or closure_event.get("test_plan_revision_id")
            != blocker.get("test_plan_revision_id")
            or closure_event.get("execution_contract_id")
            != blocker.get("execution_contract_id")
            or closure_event.get("closure_result") != "CLOSED"
        ):
            reasons.append("REASON-CLOSURE-EVENT-BINDING-MISMATCH")
        if (
            reviewer_identity.get("role_slot_id")
            in {blocker.get("origin_role"), blocker.get("owner_role")}
            or _physical_identity(reviewer_identity)
            == _physical_identity(owner_identity or {})
        ):
            reasons.append("REASON-REVIEWER-NOT-INDEPENDENT")
        prior_event_ids = [
            registry.get("last_event_id"),
            *[
                context.get(role, {}).get("recorded_event_id")
                for role in (
                    "OWNER-COMPLETE-RECEIPT",
                    "OWNER-INGEST-RECEIPT",
                    "REVIEWER-COMPLETE-RECEIPT",
                    "REVIEWER-INGEST-RECEIPT",
                )
            ],
            *[
                context.get(role, {}).get("created_event_id")
                for role in (
                    "OWNER-EVIDENCE-REVISION-1",
                    "OWNER-EVIDENCE-REVISION-2",
                    "REVIEWER-EVIDENCE-REVISION-1",
                    "REVIEWER-EVIDENCE-REVISION-2",
                )
            ],
        ]
        recorded_event_id = closure_event.get("recorded_event_id")
        if (
            not isinstance(recorded_event_id, str)
            or any(
                isinstance(event_id, str)
                and recorded_event_id <= event_id
                for event_id in prior_event_ids
            )
        ):
            reasons.append(
                "REASON-CLOSURE-EVENT-ORDER-NOT-APPEND-ONLY"
            )
    for prefix in ("OWNER", "REVIEWER"):
        revision_2 = context.get(f"{prefix}-EVIDENCE-REVISION-2", {})
        if revision_2.get("validity", {}).get("state") != "ACTIVE":
            reasons.append(f"REASON-{prefix}-EVIDENCE-NOT-ACTIVE")
    return _materialized_closure_result(source_blocker_id, reasons)


def _materialized_closure_result(
    source_blocker_content_id: str | None,
    reasons: list[str],
) -> dict[str, Any]:
    reason_ids = sorted(set(reasons))
    accepted = not reason_ids
    return {
        "algorithm_id": "ORACLE-BLOCKER-CLOSURE-INDEPENDENCE-V1",
        "accepted": accepted,
        "closure_result": "CLOSED" if accepted else "REJECTED",
        "reason_ids": reason_ids,
        "source_blocker_content_id": source_blocker_content_id,
    }
