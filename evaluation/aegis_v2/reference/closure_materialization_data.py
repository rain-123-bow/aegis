from __future__ import annotations

import base64
import copy
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .canonical import (
    content_id,
    jcs_bytes,
    sha256_hex,
    sha256_hex_bytes,
    verify_self_hash,
    with_self_hash,
)
from .schema_validation import local_schema_bundle


MATERIALIZER_ID = "MATERIALIZER-BLOCKER-CLOSURE-RUNNER-INPUT-V1"
SUITE_ID = "PROPERTY-BLOCKER-CLOSURE-EXHAUSTIVE-V1"
INPUT_BINDING_ID = "BINDING-BLOCKER-CLOSURE-GATE-1-V1"
CLOSURE_EVENT_SCHEMA_ID = (
    "https://raw.githubusercontent.com/rain-123-bow/aegis/main/"
    "schemas/aegis/v2/blocker_closure_event.v1.schema.json"
)

ROLE_NAMES = {
    "A": "TEST_PLAN_AUTHOR",
    "B": "TEST_PLAN_REVIEWER",
    "C": "TEST_EXECUTOR",
    "D": "TEST_RESULT_REVIEWER",
    "E": "TEST_REPORT_WRITER",
    "F": "FINAL_REVIEWER",
}
ROLE_PHASES = {
    "A": "PLAN_AUTHOR",
    "B": "PLAN_REVIEW",
    "C": "TEST_EXECUTION",
    "D": "RESULT_REVIEW",
    "E": "REPORT_DRAFT",
    "F": "FINAL_REVIEW",
}
STAGE_RANKS = {role: index for index, role in enumerate(ROLE_NAMES, start=1)}
REVIEWER_ROLES = ("B", "D", "F")
ASSIGNMENT_DOMAIN = {
    "origin_role": {"B", "D", "F"},
    "owner_role": set(ROLE_NAMES),
    "reviewer_relation": {"INDEPENDENT", "ORIGIN_OR_OWNER"},
    "owner_evidence": {"PRESENT_VALID", "MISSING_OR_INVALID"},
    "reviewer_evidence": {"PRESENT_VALID", "MISSING_OR_INVALID"},
}

_PROTOCOL_SHA256 = (
    "1bc09dedc506075562d4d49b702ecab6d947dd5a8c2a9014a5cde592a0938efb"
)
_BASE_TIME = datetime(2026, 7, 28, tzinfo=timezone.utc)


class _IdentityFactory:
    """Deterministic UUIDv7/time namespace for one property instance."""

    def __init__(self, envelope: dict[str, Any]):
        self.ordinal = envelope["ordinal"]
        self.instance_id = envelope["instance_id"]
        self.base_time = _BASE_TIME + timedelta(minutes=self.ordinal)

    def uuid(self, sequence: int, label: str) -> str:
        if not 0 <= sequence < 1_000:
            raise ValueError(f"UUIDv7 sequence is outside [0, 1000): {sequence}")
        epoch_ms = int(self.base_time.timestamp() * 1_000) + sequence
        randomness = hashlib.sha256(
            f"{self.instance_id}|{label}|{sequence}".encode("utf-8")
        ).digest()
        rand_a = int.from_bytes(randomness[:2], "big") & 0x0FFF
        rand_b = int.from_bytes(randomness[2:10], "big") & ((1 << 62) - 1)
        high = epoch_ms >> 16
        low = epoch_ms & 0xFFFF
        version_and_rand = 0x7000 | rand_a
        variant_and_rand = (0b10 << 62) | rand_b
        return (
            f"{high:08x}-{low:04x}-{version_and_rand:04x}-"
            f"{variant_and_rand >> 48:04x}-{variant_and_rand & ((1 << 48) - 1):012x}"
        )

    def utc(self, sequence: int) -> str:
        value = self.base_time + timedelta(milliseconds=sequence)
        return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def epoch_ms(self, sequence: int) -> int:
        return int(self.base_time.timestamp() * 1_000) + sequence

    def epoch_seconds(self, sequence: int) -> int:
        return self.epoch_ms(sequence) // 1_000

    def content_id(self, label: str) -> str:
        return content_id(
            {
                "schema_version": "ClosureMaterializationIdentity.v1",
                "instance_id": self.instance_id,
                "label": label,
            }
        )


class _FixtureBuilder:
    def __init__(self, runtime_root: str):
        self.runtime_root = runtime_root.rstrip("\\")
        self.fixtures: list[dict[str, Any]] = []
        self._ids: set[str] = set()
        self._paths: set[str] = set()

    def add_json(
        self, fixture_id: str, run_relative_path: str, value: Any
    ) -> tuple[str, int, str]:
        raw = jcs_bytes(value)
        return self.add_raw(
            fixture_id,
            run_relative_path,
            raw,
            media_type="application/json",
            encoding="UTF-8",
            jcs_sha256=sha256_hex(value),
        )

    def add_raw(
        self,
        fixture_id: str,
        run_relative_path: str,
        raw: bytes,
        *,
        media_type: str,
        encoding: str,
        jcs_sha256: str | None,
    ) -> tuple[str, int, str]:
        logical_path = (
            f"{self.runtime_root}\\{run_relative_path.replace('/', '\\')}"
        )
        if fixture_id in self._ids:
            raise ValueError(f"duplicate fixture_id: {fixture_id}")
        canonical_path = logical_path.replace("\\", "/").lower()
        if canonical_path in self._paths:
            raise ValueError(f"duplicate logical fixture path: {logical_path}")
        self._ids.add(fixture_id)
        self._paths.add(canonical_path)
        raw_sha256 = sha256_hex_bytes(raw)
        self.fixtures.append(
            {
                "fixture_id": fixture_id,
                "logical_runtime_path": logical_path,
                "media_type": media_type,
                "encoding": encoding,
                "byte_domain": "INLINE_BASE64_DECODED_EXACT_BYTES",
                "raw_base64": base64.b64encode(raw).decode("ascii"),
                "byte_size": len(raw),
                "raw_sha256": raw_sha256,
                "jcs_sha256": jcs_sha256,
                "content_id": f"sha256:{raw_sha256}",
                "access_mode": "READ_ONLY",
            }
        )
        return raw_sha256, len(raw), logical_path


def _validate_inputs(
    envelope: dict[str, Any], suite: dict[str, Any]
) -> dict[str, str]:
    if envelope.get("schema_version") != "PropertyInstanceEnvelope.v1":
        raise ValueError("envelope schema_version must be PropertyInstanceEnvelope.v1")
    if envelope.get("suite_id") != SUITE_ID or suite.get("suite_id") != SUITE_ID:
        raise ValueError(f"closure materializer requires suite_id {SUITE_ID}")
    if not verify_self_hash(envelope, "envelope_sha256", prefix=True):
        raise ValueError("envelope_sha256 is invalid")
    ordinal = envelope.get("ordinal")
    if type(ordinal) is not int or ordinal < 1:
        raise ValueError("envelope ordinal must be a positive integer")
    if envelope.get("case_id") != f"{SUITE_ID}-INSTANCE-{ordinal:06d}":
        raise ValueError("envelope case_id does not match suite and ordinal")
    assignment = envelope.get("assignment")
    if not isinstance(assignment, dict):
        raise ValueError("envelope assignment must be an object")
    if set(assignment) != set(ASSIGNMENT_DOMAIN):
        raise ValueError("closure assignment has missing or extra dimensions")
    for dimension, allowed in ASSIGNMENT_DOMAIN.items():
        value = assignment[dimension]
        if value not in allowed:
            raise ValueError(
                f"closure assignment {dimension} is outside its domain: {value!r}"
            )
        suite_domain = suite.get("domain", {}).get(dimension)
        if not isinstance(suite_domain, list) or value not in suite_domain:
            raise ValueError(
                f"closure assignment {dimension} is outside the frozen suite"
            )
    binding = suite.get("input_materializer", {}).get("input_binding_id")
    if binding is not None and binding != INPUT_BINDING_ID:
        raise ValueError(
            f"closure suite input materializer binds unexpected input: {binding}"
        )
    runner_contract_id = suite.get("sut_runner_contract_id")
    if not isinstance(runner_contract_id, str):
        raise ValueError("closure suite has no sut_runner_contract_id")
    return assignment


def _identity(
    role_slot_id: str,
    ids: _IdentityFactory,
    source_generation_id: str,
) -> dict[str, Any]:
    role_offset = list(ROLE_NAMES).index(role_slot_id)
    return {
        "role_slot_id": role_slot_id,
        "role": ROLE_NAMES[role_slot_id],
        "source_generation_id": source_generation_id,
        "instance_revision": 1,
        "agent_handle": f"agent-{role_slot_id.lower()}-rev-1",
        "handle_source": "THREAD_SPAWN_AGENT_PATH",
        "thread_id": ids.uuid(10 + role_offset, f"thread-{role_slot_id}"),
        "session_id": (
            f"session-closure-{ids.ordinal:06d}-{role_slot_id.lower()}"
        ),
    }


def _thread(
    identity: dict[str, Any],
    parent_task_id: str,
    ids: _IdentityFactory,
) -> dict[str, Any]:
    role_slot_id = identity["role_slot_id"]
    role_offset = list(ROLE_NAMES).index(role_slot_id)
    return {
        "id": identity["thread_id"],
        "sessionId": identity["session_id"],
        "parentThreadId": parent_task_id,
        "createdAt": ids.epoch_seconds(10 + role_offset),
        "source": {
            "subAgent": {
                "thread_spawn": {
                    "parent_thread_id": parent_task_id,
                    "depth": 1,
                    "agent_role": "default",
                    "agent_nickname": None,
                    "agent_path": identity["agent_handle"],
                }
            }
        },
    }


def _capability_authority(
    identity: dict[str, Any],
    parent_task_id: str,
    protocol_evidence_record_id: str,
    ids: _IdentityFactory,
    fixtures: _FixtureBuilder,
) -> dict[str, Any]:
    role_slot_id = identity["role_slot_id"]
    role_offset = list(ROLE_NAMES).index(role_slot_id)
    thread = _thread(identity, parent_task_id, ids)
    run_relative_path = (
        f"authority/registry-capability-{role_slot_id.lower()}.json"
    )
    raw_record = {
        "jsonrpc": "2.0",
        "id": f"capability-{ids.ordinal:06d}-{role_slot_id.lower()}",
        "result": {
            "thread": thread,
            "capability": "same-desktop-authority",
        },
    }
    raw_sha256, byte_size, runtime_path = fixtures.add_json(
        f"FIXTURE-REGISTRY-CAPABILITY-{role_slot_id}",
        run_relative_path,
        raw_record,
    )
    return {
        "schema_version": "CodexAuthorityEvent.v1",
        "authority": "CODEX_APP_SERVER",
        "codex_cli_version": "0.145.0",
        "app_server_protocol_canonicalization": "JCS-RFC8785",
        "app_server_protocol_semantic_sha256": _PROTOCOL_SHA256,
        "protocol_bundle_evidence_record_id": protocol_evidence_record_id,
        "authority_event_id": ids.uuid(
            30 + role_offset, f"capability-authority-{role_slot_id}"
        ),
        "event_purpose": "CAPABILITY",
        "thread": thread,
        "collab_agent_tool_call": None,
        "raw_records": [
            {
                "record_kind": "REQUEST_RESPONSE",
                "method": "thread/read",
                "request_id": (
                    f"capability-{ids.ordinal:06d}-{role_slot_id.lower()}"
                ),
                "notification_seq": None,
                "lifecycle_at_ms": None,
                "thread_id": identity["thread_id"],
                "turn_id": None,
                "item_id": None,
                "runtime_path": runtime_path,
                "run_relative_path": run_relative_path,
                "canonical_casefold_key": runtime_path.replace(
                    "\\", "/"
                ).lower(),
                "byte_size": byte_size,
                "raw_sha256": raw_sha256,
            }
        ],
        "child_result_binding": None,
        "observed_at_utc": ids.utc(30 + role_offset),
    }


def _registry(
    identities: dict[str, dict[str, Any]],
    parent_task_id: str,
    source_baseline_id: str,
    source_generation_id: str,
    registry_snapshot_id: str,
    protocol_evidence_record_id: str,
    ids: _IdentityFactory,
    fixtures: _FixtureBuilder,
) -> dict[str, Any]:
    agents: list[dict[str, Any]] = []
    for role_slot_id in ROLE_NAMES:
        identity = identities[role_slot_id]
        authority_event = _capability_authority(
            identity,
            parent_task_id,
            protocol_evidence_record_id,
            ids,
            fixtures,
        )
        agents.append(
            {
                "schema_version": "AgentIdentity.v1",
                "identity": copy.deepcopy(identity),
                "parent_task_id": parent_task_id,
                "thread": _thread(identity, parent_task_id, ids),
                "lifecycle_state": "ACTIVE",
                "capability_state": "VERIFIED",
                "observed_at_utc": ids.utc(
                    30 + list(ROLE_NAMES).index(role_slot_id)
                ),
                "authority_event": authority_event,
            }
        )
    committed_state_sha256 = ids.content_id(
        "registry-committed-state"
    ).removeprefix("sha256:")
    return {
        "schema_version": "AgentRegistry.v1",
        "registry_id": ids.uuid(8, "registry"),
        "registry_cas": {
            "revision": 0,
            "previous_state_preimage_id": None,
            "previous_state_sha256": None,
            "committed_state_preimage_id": (
                f"sha256:{committed_state_sha256}"
            ),
            "committed_state_sha256": committed_state_sha256,
        },
        "parent_task_id": parent_task_id,
        "capacity_contract": {
            "max_retained_source_generations": 2,
            "replacement_reserve": 6,
            "physical_instance_budget": 18,
            "capacity_certification_id": ids.content_id(
                "capacity-certification"
            ),
        },
        "current_source_baseline_id": source_baseline_id,
        "current_source_generation_id": source_generation_id,
        "current_registry_snapshot_id": registry_snapshot_id,
        "active_role_pointers": [
            copy.deepcopy(identities[role]) for role in ROLE_NAMES
        ],
        "identities": agents,
        "provision_batch_ids": [],
        "replacement_batch_ids": [],
        "platform_close_receipt_ids": [],
        "last_event_id": ids.uuid(36, "registry-last-event"),
        "updated_at_utc": ids.utc(36),
    }


def _dispatch_action(
    *,
    channel: str,
    identity: dict[str, Any],
    blocker: dict[str, Any],
    source_blocker_content_id: str,
    campaign_id: str,
    run_id: str,
    registry_snapshot_id: str,
    ids: _IdentityFactory,
    fixtures: _FixtureBuilder,
    attempt_sequence: int,
    action_sequence: int,
    state_seq: int,
) -> dict[str, Any]:
    action_id = ids.uuid(action_sequence, f"{channel}-action")
    payload = {
        "schema_version": "ClosureDispatchPayload.v1",
        "blocker_id": blocker["blocker_id"],
        "source_blocker_content_id": source_blocker_content_id,
        "action_id": action_id,
        "target_identity": identity,
    }
    run_relative_path = f"inbox/{channel}-closure-dispatch.json"
    payload_sha256, _, payload_path = fixtures.add_json(
        f"FIXTURE-{channel.upper()}-DISPATCH-PAYLOAD",
        run_relative_path,
        payload,
    )
    role_slot_id = identity["role_slot_id"]
    issued = ids.base_time + timedelta(milliseconds=action_sequence)
    return {
        "schema_version": "DispatchAction.v1",
        "protocol_version": "aegis.native-master-relay.v1",
        "action_kind": "NODE_WORK",
        "campaign_id": campaign_id,
        "run_id": run_id,
        "source_baseline_id": blocker["source_baseline_id"],
        "registry_snapshot_id": registry_snapshot_id,
        "test_plan_revision_id": blocker["test_plan_revision_id"],
        "execution_contract_id": blocker["execution_contract_id"],
        "node_id": role_slot_id,
        "attempt_id": ids.uuid(
            attempt_sequence, f"{channel}-attempt"
        ),
        "action_id": action_id,
        "target_role_slot_id": role_slot_id,
        "target_role": identity["role"],
        "target_agent_handle": identity["agent_handle"],
        "target_thread_id": identity["thread_id"],
        "target_session_id": identity["session_id"],
        "target_generation": identity["source_generation_id"],
        "target_instance_revision": identity["instance_revision"],
        "payload_path": payload_path,
        "payload_sha256": payload_sha256,
        "issued_at_utc": issued.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        ),
        "expires_at_utc": (
            issued + timedelta(hours=1)
        ).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "nonce": (
            f"nonce_{channel}_{ids.ordinal:06d}_abcdefghijklmnopqrstuv"
        ),
        "side_effect_policy": {
            "operation_class": "PURE_READ",
            "operation_id": None,
            "journal_ref": None,
            "result_query_method": None,
            "user_approval_event_id": None,
        },
        "graph_transition": {
            "workflow_phase": ROLE_PHASES[role_slot_id],
            "current_node": role_slot_id,
        },
        "state_seq": state_seq,
    }


def _child_result_authority(
    *,
    channel: str,
    action: dict[str, Any],
    identity: dict[str, Any],
    result_raw: bytes,
    parent_task_id: str,
    protocol_evidence_record_id: str,
    ids: _IdentityFactory,
    fixtures: _FixtureBuilder,
    authority_sequence: int,
    turn_sequence: int,
) -> dict[str, Any]:
    result_sha256 = sha256_hex_bytes(result_raw)
    result_relative_path = f"outbox/{channel}-closure-evidence.json"
    result_path = (
        f"{fixtures.runtime_root}\\"
        f"{result_relative_path.replace('/', '\\')}"
    )
    fixtures.add_raw(
        (
            "FIXTURE-OWNER-CORRECTION-PREIMAGE"
            if channel == "owner"
            else "FIXTURE-INDEPENDENT-REVIEW-PREIMAGE"
        ),
        result_relative_path,
        result_raw,
        media_type="application/json",
        encoding="UTF-8",
        jcs_sha256=result_sha256,
    )
    thread = _thread(identity, parent_task_id, ids)
    turn_id = ids.uuid(turn_sequence, f"{channel}-turn")
    item_id = f"message-{channel}-{ids.ordinal:06d}"
    tool_call_id = f"tool-{channel}-{ids.ordinal:06d}"
    message_text = f"result_sha256={result_sha256}"
    agent_message = {
        "id": item_id,
        "text": message_text,
        "type": "agentMessage",
    }
    completed_at_ms = ids.epoch_ms(authority_sequence)
    item_raw = {
        "jsonrpc": "2.0",
        "method": "item/completed",
        "params": {
            "threadId": identity["thread_id"],
            "turnId": turn_id,
            "completedAtMs": completed_at_ms,
            "item": agent_message,
        },
    }
    turn_raw = {
        "jsonrpc": "2.0",
        "method": "turn/completed",
        "params": {
            "threadId": identity["thread_id"],
            "turn": {
                "id": turn_id,
                "items": [agent_message],
                "status": "completed",
                "startedAt": completed_at_ms // 1_000 - 1,
                "completedAt": completed_at_ms // 1_000,
                "durationMs": 1_000,
                "error": None,
                "itemsView": "full",
            },
        },
    }
    item_relative_path = f"authority/{channel}-item-completed.json"
    turn_relative_path = f"authority/{channel}-turn-completed.json"
    item_sha256, item_size, item_path = fixtures.add_json(
        f"FIXTURE-{channel.upper()}-ITEM-COMPLETED",
        item_relative_path,
        item_raw,
    )
    turn_sha256, turn_size, turn_path = fixtures.add_json(
        f"FIXTURE-{channel.upper()}-TURN-COMPLETED",
        turn_relative_path,
        turn_raw,
    )
    return {
        "schema_version": "CodexAuthorityEvent.v1",
        "authority": "CODEX_APP_SERVER",
        "codex_cli_version": "0.145.0",
        "app_server_protocol_canonicalization": "JCS-RFC8785",
        "app_server_protocol_semantic_sha256": _PROTOCOL_SHA256,
        "protocol_bundle_evidence_record_id": protocol_evidence_record_id,
        "authority_event_id": ids.uuid(
            authority_sequence, f"{channel}-authority"
        ),
        "event_purpose": "CHILD_RESULT",
        "thread": thread,
        "collab_agent_tool_call": {
            "type": "collabAgentToolCall",
            "id": tool_call_id,
            "tool": "sendInput",
            "senderThreadId": parent_task_id,
            "receiverThreadIds": [identity["thread_id"]],
            "status": "completed",
            "agentsStates": {
                identity["agent_handle"]: {
                    "status": "completed",
                    "message": None,
                }
            },
            "prompt": (
                f"action_id={action['action_id']} "
                f"payload_path={action['payload_path']} "
                f"payload_sha256={action['payload_sha256']}"
            ),
            "model": None,
            "reasoningEffort": None,
        },
        "raw_records": [
            {
                "record_kind": "ITEM_COMPLETED",
                "method": "item/completed",
                "request_id": None,
                "notification_seq": 1,
                "lifecycle_at_ms": completed_at_ms,
                "thread_id": identity["thread_id"],
                "turn_id": turn_id,
                "item_id": item_id,
                "runtime_path": item_path,
                "run_relative_path": item_relative_path,
                "canonical_casefold_key": item_path.replace(
                    "\\", "/"
                ).lower(),
                "byte_size": item_size,
                "raw_sha256": item_sha256,
            },
            {
                "record_kind": "TURN_COMPLETED",
                "method": "turn/completed",
                "request_id": None,
                "notification_seq": 2,
                "lifecycle_at_ms": completed_at_ms,
                "thread_id": identity["thread_id"],
                "turn_id": turn_id,
                "item_id": None,
                "runtime_path": turn_path,
                "run_relative_path": turn_relative_path,
                "canonical_casefold_key": turn_path.replace(
                    "\\", "/"
                ).lower(),
                "byte_size": turn_size,
                "raw_sha256": turn_sha256,
            },
        ],
        "child_result_binding": {
            "parent_tool_call_id": tool_call_id,
            "child_thread_id": identity["thread_id"],
            "child_turn_id": turn_id,
            "child_item_id": item_id,
            "agent_message": agent_message,
            "agent_message_text_sha256": hashlib.sha256(
                message_text.encode("utf-8")
            ).hexdigest(),
            "outbox_result_path": result_path,
            "outbox_result_run_relative_path": result_relative_path,
            "outbox_result_canonical_casefold_key": result_path.replace(
                "\\", "/"
            ).lower(),
            "outbox_result_sha256": result_sha256,
            "item_completed_raw_sha256": item_sha256,
            "turn_completed_raw_sha256": turn_sha256,
        },
        "observed_at_utc": ids.utc(authority_sequence),
    }


def _receipt(
    *,
    receipt_kind: str,
    receipt_status: str,
    receipt_id: str,
    recorded_event_id: str,
    recorded_at_utc: str,
    action: dict[str, Any],
    identity: dict[str, Any],
    authority_event: dict[str, Any],
) -> dict[str, Any]:
    child_binding = authority_event["child_result_binding"]
    return {
        "schema_version": "AgentReceipt.v1",
        "receipt_id": receipt_id,
        "receipt_kind": receipt_kind,
        "receipt_status": receipt_status,
        "action": copy.deepcopy(action),
        "campaign_id": action["campaign_id"],
        "run_id": action["run_id"],
        "action_id": action["action_id"],
        "state_seq": action["state_seq"],
        "source_baseline_id": action["source_baseline_id"],
        "registry_snapshot_id": action["registry_snapshot_id"],
        "test_plan_revision_id": action["test_plan_revision_id"],
        "execution_contract_id": action["execution_contract_id"],
        "observed_identity": copy.deepcopy(identity),
        "payload_sha256": action["payload_sha256"],
        "result": {
            "result_path": child_binding["outbox_result_path"],
            "result_sha256": child_binding["outbox_result_sha256"],
        },
        "rejection_reason_id": None,
        "failure_reason": None,
        "authority_event": copy.deepcopy(authority_event),
        "recorded_event_id": recorded_event_id,
        "recorded_at_utc": recorded_at_utc,
    }


def _evidence_revisions(
    *,
    channel: str,
    evidence_id: str,
    action: dict[str, Any],
    identity: dict[str, Any],
    authority_event: dict[str, Any],
    complete_receipt: dict[str, Any],
    ingest_receipt: dict[str, Any],
    result_raw: bytes,
    execution_environment_snapshot_id: str,
    case_id: str,
    final_valid: bool,
    ids: _IdentityFactory,
    first_record_sequence: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    child_binding = authority_event["child_result_binding"]
    first_record_id = ids.uuid(
        first_record_sequence, f"{channel}-evidence-record-1"
    )
    second_record_id = ids.uuid(
        first_record_sequence + 3, f"{channel}-evidence-record-2"
    )
    base = {
        "schema_version": "EvidenceRecord.v1",
        "evidence_id": evidence_id,
        "evidence_kind": "LOCAL_FILE",
        "campaign_id": action["campaign_id"],
        "run_id": action["run_id"],
        "case_ids": [case_id],
        "source_baseline_id": action["source_baseline_id"],
        "registry_snapshot_id": action["registry_snapshot_id"],
        "test_plan_revision_id": action["test_plan_revision_id"],
        "execution_environment_snapshot_id": (
            execution_environment_snapshot_id
        ),
        "execution_contract_id": action["execution_contract_id"],
        "attempt_id": action["attempt_id"],
        "origin": {
            "kind": "ACTION_RESULT",
            "registry_snapshot_id": action["registry_snapshot_id"],
            "action_id": action["action_id"],
            "completion_receipt_id": complete_receipt["receipt_id"],
            "ingest_receipt_id": ingest_receipt["receipt_id"],
            "authority_event_ids": [authority_event["authority_event_id"]],
        },
        "producer_identity": {
            "kind": "AGENT",
            "identity": copy.deepcopy(identity),
        },
        "collector_identity": {
            "kind": "AGENT",
            "identity": copy.deepcopy(identity),
        },
        "acquisition": {
            "kind": "COMMAND",
            "complete_invocation": (
                f"aegis-evaluation-fixture --closure-role {channel}"
            ),
            "return_code": 0,
            "started_at_utc": action["issued_at_utc"],
            "ended_at_utc": authority_event["observed_at_utc"],
            "environment_fingerprint": ids.content_id(
                "execution-environment-fingerprint"
            ),
        },
        "locator": {
            "kind": "LOCAL",
            "absolute_path": child_binding["outbox_result_path"],
            "run_relative_path": child_binding[
                "outbox_result_run_relative_path"
            ],
            "canonical_casefold_key": child_binding[
                "outbox_result_canonical_casefold_key"
            ],
        },
        "content": {
            "mode": "SHA256",
            "byte_size": len(result_raw),
            "sha256": sha256_hex_bytes(result_raw),
        },
        "retention": {
            "retention_class": "CAMPAIGN_LIFETIME",
            "expires_at_utc": None,
            "access_method": "Load exact materialized fixture bytes.",
            "responsible_party": "Aegis evaluation runner",
        },
    }
    first = copy.deepcopy(base)
    first.update(
        {
            "record_id": first_record_id,
            "record_revision": 1,
            "supersedes_record_id": None,
            "validity": {
                "state": "STALE",
                "invalidated_event_id": ids.uuid(
                    first_record_sequence + 2,
                    f"{channel}-evidence-revision-1-invalidated",
                ),
                "reason": (
                    "Superseded by provenance-revalidated active revision."
                ),
            },
            "created_event_id": ids.uuid(
                first_record_sequence + 1,
                f"{channel}-evidence-revision-1-created",
            ),
            "created_at_utc": ids.utc(first_record_sequence + 1),
        }
    )
    if final_valid:
        second_validity = {
            "state": "ACTIVE",
            "invalidated_event_id": None,
            "reason": None,
        }
    else:
        second_validity = {
            "state": "INVALID",
            "invalidated_event_id": ids.uuid(
                first_record_sequence + 5,
                f"{channel}-evidence-revision-2-invalidated",
            ),
            "reason": "Property assignment requires invalid closure evidence.",
        }
    second = copy.deepcopy(base)
    second.update(
        {
            "record_id": second_record_id,
            "record_revision": 2,
            "supersedes_record_id": first_record_id,
            "validity": second_validity,
            "created_event_id": ids.uuid(
                first_record_sequence + 4,
                f"{channel}-evidence-revision-2-created",
            ),
            "created_at_utc": ids.utc(first_record_sequence + 4),
        }
    )
    return first, second


def _reviewer_role(assignment: dict[str, str]) -> str:
    origin_role = assignment["origin_role"]
    owner_role = assignment["owner_role"]
    if assignment["reviewer_relation"] == "INDEPENDENT":
        return next(
            role
            for role in REVIEWER_ROLES
            if role not in {origin_role, owner_role}
        )
    if owner_role in REVIEWER_ROLES:
        return owner_role
    return origin_role


def _validate_production_object(
    value: Any,
    schema_name: str,
    schema_dir: Path,
    label: str,
) -> None:
    errors = local_schema_bundle(str(schema_dir.resolve())).errors(
        value, schema_name
    )
    if errors:
        raise ValueError(f"{label} failed {schema_name}: {errors}")


def build_closure_materialization(
    envelope: dict[str, Any],
    suite: dict[str, Any],
    schema_dir: str | Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build a complete SUT input without importing or consulting an oracle."""

    assignment = _validate_inputs(envelope, suite)
    schema_path = Path(schema_dir)
    ids = _IdentityFactory(envelope)
    runtime_root = (
        f"C:\\aegis-runtime\\runs\\closure-{ids.ordinal:06d}"
    )
    fixtures = _FixtureBuilder(runtime_root)

    parent_task_id = ids.uuid(1, "parent-task")
    campaign_id = ids.uuid(2, "campaign")
    run_id = ids.uuid(3, "run")
    source_generation_id = ids.uuid(4, "source-generation")
    protocol_evidence_record_id = ids.uuid(
        5, "protocol-bundle-evidence-record"
    )
    source_baseline_id = ids.content_id("source-baseline")
    registry_snapshot_id = ids.content_id("registry-snapshot")
    test_plan_revision_id = ids.content_id("test-plan-revision")
    execution_contract_id = ids.content_id("execution-contract")
    execution_environment_snapshot_id = ids.content_id(
        "execution-environment-snapshot"
    )
    identities = {
        role: _identity(role, ids, source_generation_id)
        for role in ROLE_NAMES
    }
    registry = _registry(
        identities,
        parent_task_id,
        source_baseline_id,
        source_generation_id,
        registry_snapshot_id,
        protocol_evidence_record_id,
        ids,
        fixtures,
    )

    blocker_id = f"BLOCKER-CLOSURE-{ids.ordinal:06d}"
    closure_case_id = f"CASE-CLOSURE-{ids.ordinal:06d}"
    affected_artifact = {
        "artifact_id": "ARTIFACT-TEST-PLAN",
        "run_relative_path": "artifacts/a/plan.json",
        "sha256": ids.content_id("affected-artifact").removeprefix(
            "sha256:"
        ),
    }
    blocker = {
        "schema_version": "BlockerRecord.v1",
        "blocker_id": blocker_id,
        "fact_type": "PROCESS_BLOCKER",
        "blocker_kind": "WORKFLOW_PROCESS",
        "origin_role": assignment["origin_role"],
        "owner_role": assignment["owner_role"],
        "severity": "P1",
        "claim": "The workflow omits a required executable boundary.",
        "violated_requirement": "REQUIREMENT-R-002",
        "evidence_refs": ["EVIDENCE-BLOCKER-OPEN"],
        "required_closure_evidence": [
            "Corrected artifact bytes.",
            "Independent reviewer verification bytes.",
        ],
        "prohibited_substitutes": [
            "Author self-assertion.",
            "Numeric score or confidence.",
        ],
        "affected_artifacts": [affected_artifact],
        "affected_case_ids": [closure_case_id],
        "source_baseline_id": source_baseline_id,
        "test_plan_revision_id": test_plan_revision_id,
        "execution_contract_id": execution_contract_id,
        "opened_attempt_id": ids.uuid(40, "blocker-open-attempt"),
        "opened_event_id": ids.uuid(41, "blocker-opened-event"),
        "stage_rank": STAGE_RANKS[assignment["owner_role"]],
        "gate_effect": "BLOCKING",
        "status": "OPEN",
        "source_report_defect": None,
        "closure_events": [],
    }
    source_blocker_content_id = content_id(blocker)
    owner_identity = identities[assignment["owner_role"]]
    reviewer_identity = identities[_reviewer_role(assignment)]

    owner_action = _dispatch_action(
        channel="owner",
        identity=owner_identity,
        blocker=blocker,
        source_blocker_content_id=source_blocker_content_id,
        campaign_id=campaign_id,
        run_id=run_id,
        registry_snapshot_id=registry_snapshot_id,
        ids=ids,
        fixtures=fixtures,
        attempt_sequence=50,
        action_sequence=51,
        state_seq=ids.ordinal * 10 + 1,
    )
    owner_complete_receipt_id = ids.uuid(54, "owner-complete-receipt")
    owner_ingest_receipt_id = ids.uuid(56, "owner-ingest-receipt")
    owner_record_2_id = ids.uuid(61, "owner-evidence-record-2")
    corrected_artifact = {
        **affected_artifact,
        "sha256": ids.content_id("corrected-artifact").removeprefix(
            "sha256:"
        ),
    }
    owner_preimage = {
        "schema_version": "OwnerCorrectionEvidence.v1",
        "blocker_id": blocker_id,
        "source_blocker_content_id": source_blocker_content_id,
        "source_baseline_id": source_baseline_id,
        "test_plan_revision_id": test_plan_revision_id,
        "execution_contract_id": execution_contract_id,
        "owner_identity": owner_identity,
        "owner_action_id": owner_action["action_id"],
        "owner_completion_receipt_id": owner_complete_receipt_id,
        "owner_ingest_receipt_id": owner_ingest_receipt_id,
        "addressed_requirement_id": blocker["violated_requirement"],
        "corrected_artifacts": [corrected_artifact],
        "dependency_propagation": {
            "severity": blocker["severity"],
            "invalidated_artifact_ids": [
                artifact["artifact_id"]
                for artifact in blocker["affected_artifacts"]
            ],
            "invalidated_case_ids": sorted(blocker["affected_case_ids"]),
        },
    }
    owner_raw = jcs_bytes(owner_preimage)
    owner_authority = _child_result_authority(
        channel="owner",
        action=owner_action,
        identity=owner_identity,
        result_raw=owner_raw,
        parent_task_id=parent_task_id,
        protocol_evidence_record_id=protocol_evidence_record_id,
        ids=ids,
        fixtures=fixtures,
        authority_sequence=52,
        turn_sequence=53,
    )
    owner_complete_receipt = _receipt(
        receipt_kind="COMPLETE",
        receipt_status="COMPLETED",
        receipt_id=owner_complete_receipt_id,
        recorded_event_id=ids.uuid(55, "owner-complete-recorded"),
        recorded_at_utc=ids.utc(55),
        action=owner_action,
        identity=owner_identity,
        authority_event=owner_authority,
    )
    owner_ingest_receipt = _receipt(
        receipt_kind="INGEST",
        receipt_status="ACCEPTED",
        receipt_id=owner_ingest_receipt_id,
        recorded_event_id=ids.uuid(57, "owner-ingest-recorded"),
        recorded_at_utc=ids.utc(57),
        action=owner_action,
        identity=owner_identity,
        authority_event=owner_authority,
    )
    owner_evidence_1, owner_evidence_2 = _evidence_revisions(
        channel="owner",
        evidence_id="EVIDENCE-OWNER-CORRECTION",
        action=owner_action,
        identity=owner_identity,
        authority_event=owner_authority,
        complete_receipt=owner_complete_receipt,
        ingest_receipt=owner_ingest_receipt,
        result_raw=owner_raw,
        execution_environment_snapshot_id=execution_environment_snapshot_id,
        case_id=closure_case_id,
        final_valid=assignment["owner_evidence"] == "PRESENT_VALID",
        ids=ids,
        first_record_sequence=58,
    )
    if owner_evidence_2["record_id"] != owner_record_2_id:
        raise AssertionError("owner evidence revision ID schedule drifted")

    reviewer_action = _dispatch_action(
        channel="reviewer",
        identity=reviewer_identity,
        blocker=blocker,
        source_blocker_content_id=source_blocker_content_id,
        campaign_id=campaign_id,
        run_id=run_id,
        registry_snapshot_id=registry_snapshot_id,
        ids=ids,
        fixtures=fixtures,
        attempt_sequence=70,
        action_sequence=71,
        state_seq=ids.ordinal * 10 + 2,
    )
    reviewer_complete_receipt_id = ids.uuid(
        74, "reviewer-complete-receipt"
    )
    reviewer_ingest_receipt_id = ids.uuid(
        76, "reviewer-ingest-receipt"
    )
    reviewer_preimage = {
        "schema_version": "IndependentReviewEvidence.v1",
        "blocker_id": blocker_id,
        "source_blocker_content_id": source_blocker_content_id,
        "source_baseline_id": source_baseline_id,
        "test_plan_revision_id": test_plan_revision_id,
        "execution_contract_id": execution_contract_id,
        "owner_identity": owner_identity,
        "reviewer_identity": reviewer_identity,
        "reviewer_action_id": reviewer_action["action_id"],
        "reviewer_completion_receipt_id": reviewer_complete_receipt_id,
        "reviewer_ingest_receipt_id": reviewer_ingest_receipt_id,
        "reviewed_owner_evidence_id": "EVIDENCE-OWNER-CORRECTION",
        "reviewed_owner_record_id": owner_record_2_id,
        "reviewed_owner_preimage_sha256": sha256_hex_bytes(owner_raw),
        "verification_result": "VERIFIED",
        "verified_requirement_id": blocker["violated_requirement"],
    }
    reviewer_raw = jcs_bytes(reviewer_preimage)
    reviewer_authority = _child_result_authority(
        channel="reviewer",
        action=reviewer_action,
        identity=reviewer_identity,
        result_raw=reviewer_raw,
        parent_task_id=parent_task_id,
        protocol_evidence_record_id=protocol_evidence_record_id,
        ids=ids,
        fixtures=fixtures,
        authority_sequence=72,
        turn_sequence=73,
    )
    reviewer_complete_receipt = _receipt(
        receipt_kind="COMPLETE",
        receipt_status="COMPLETED",
        receipt_id=reviewer_complete_receipt_id,
        recorded_event_id=ids.uuid(75, "reviewer-complete-recorded"),
        recorded_at_utc=ids.utc(75),
        action=reviewer_action,
        identity=reviewer_identity,
        authority_event=reviewer_authority,
    )
    reviewer_ingest_receipt = _receipt(
        receipt_kind="INGEST",
        receipt_status="ACCEPTED",
        receipt_id=reviewer_ingest_receipt_id,
        recorded_event_id=ids.uuid(77, "reviewer-ingest-recorded"),
        recorded_at_utc=ids.utc(77),
        action=reviewer_action,
        identity=reviewer_identity,
        authority_event=reviewer_authority,
    )
    reviewer_evidence_1, reviewer_evidence_2 = _evidence_revisions(
        channel="reviewer",
        evidence_id="EVIDENCE-INDEPENDENT-REVIEW",
        action=reviewer_action,
        identity=reviewer_identity,
        authority_event=reviewer_authority,
        complete_receipt=reviewer_complete_receipt,
        ingest_receipt=reviewer_ingest_receipt,
        result_raw=reviewer_raw,
        execution_environment_snapshot_id=execution_environment_snapshot_id,
        case_id=closure_case_id,
        final_valid=assignment["reviewer_evidence"] == "PRESENT_VALID",
        ids=ids,
        first_record_sequence=78,
    )

    closure_event = {
        "schema_version": "BlockerClosureEvent.v1",
        "closure_event_content_id": ids.content_id(
            "closure-event-placeholder"
        ),
        "closure_event_id": ids.uuid(90, "closure-event"),
        "blocker_id": blocker_id,
        "source_blocker_content_id": source_blocker_content_id,
        "closure_result": "CLOSED",
        "origin_role": assignment["origin_role"],
        "owner_role": assignment["owner_role"],
        "owner_identity": owner_identity,
        "owner_evidence_refs": ["EVIDENCE-OWNER-CORRECTION"],
        "reviewer_identity": reviewer_identity,
        "reviewer_evidence_refs": ["EVIDENCE-INDEPENDENT-REVIEW"],
        "source_baseline_id": source_baseline_id,
        "test_plan_revision_id": test_plan_revision_id,
        "execution_contract_id": execution_contract_id,
        "recorded_event_id": ids.uuid(91, "closure-recorded-event"),
        "occurred_at_utc": ids.utc(91),
    }
    closure_event = with_self_hash(
        closure_event, "closure_event_content_id", prefix=True
    )
    if assignment["reviewer_relation"] == "INDEPENDENT":
        closure_context_value: dict[str, Any] = closure_event
    else:
        closure_context_value = {
            "schema_version": "UnvalidatedCandidate.v1",
            "intended_schema_id": CLOSURE_EVENT_SCHEMA_ID,
            "declared_candidate_schema_version": "BlockerClosureEvent.v1",
            "candidate": closure_event,
            "candidate_sha256": sha256_hex(closure_event),
            "expected_rejection_ids": [
                "REJECTION-CLOSURE-REVIEWER-NOT-INDEPENDENT"
            ],
        }

    context_objects = [
        {"object_role": "AGENT-REGISTRY", "value": registry},
        {"object_role": "OWNER-DISPATCH", "value": owner_action},
        {"object_role": "OWNER-AUTHORITY", "value": owner_authority},
        {
            "object_role": "OWNER-COMPLETE-RECEIPT",
            "value": owner_complete_receipt,
        },
        {
            "object_role": "OWNER-INGEST-RECEIPT",
            "value": owner_ingest_receipt,
        },
        {
            "object_role": "OWNER-EVIDENCE-REVISION-1",
            "value": owner_evidence_1,
        },
        {
            "object_role": "OWNER-EVIDENCE-REVISION-2",
            "value": owner_evidence_2,
        },
        {"object_role": "REVIEWER-DISPATCH", "value": reviewer_action},
        {"object_role": "REVIEWER-AUTHORITY", "value": reviewer_authority},
        {
            "object_role": "REVIEWER-COMPLETE-RECEIPT",
            "value": reviewer_complete_receipt,
        },
        {
            "object_role": "REVIEWER-INGEST-RECEIPT",
            "value": reviewer_ingest_receipt,
        },
        {
            "object_role": "REVIEWER-EVIDENCE-REVISION-1",
            "value": reviewer_evidence_1,
        },
        {
            "object_role": "REVIEWER-EVIDENCE-REVISION-2",
            "value": reviewer_evidence_2,
        },
        {"object_role": "CLOSURE-EVENT", "value": closure_context_value},
    ]
    fixture_values = sorted(
        fixtures.fixtures, key=lambda item: item["fixture_id"]
    )
    runner_input = {
        "schema_version": "EvaluationRunnerInput.v1",
        "runner_contract_id": suite["sut_runner_contract_id"],
        "input_binding_id": INPUT_BINDING_ID,
        "case_id": envelope["case_id"],
        "subject": blocker,
        "context_objects": context_objects,
        "fixture_refs": [
            fixture["fixture_id"] for fixture in fixture_values
        ],
        "mutation": None,
        "observed_state": None,
    }

    direct_objects = [
        ("blocker", blocker, "blocker_record.v1.schema.json"),
        ("registry", registry, "agent_registry.v1.schema.json"),
        ("owner dispatch", owner_action, "dispatch_action.v1.schema.json"),
        (
            "reviewer dispatch",
            reviewer_action,
            "dispatch_action.v1.schema.json",
        ),
        (
            "owner authority",
            owner_authority,
            "codex_authority_event.v1.schema.json",
        ),
        (
            "reviewer authority",
            reviewer_authority,
            "codex_authority_event.v1.schema.json",
        ),
        (
            "owner complete receipt",
            owner_complete_receipt,
            "agent_receipt.v1.schema.json",
        ),
        (
            "owner ingest receipt",
            owner_ingest_receipt,
            "agent_receipt.v1.schema.json",
        ),
        (
            "reviewer complete receipt",
            reviewer_complete_receipt,
            "agent_receipt.v1.schema.json",
        ),
        (
            "reviewer ingest receipt",
            reviewer_ingest_receipt,
            "agent_receipt.v1.schema.json",
        ),
        (
            "owner evidence revision 1",
            owner_evidence_1,
            "evidence_record.v1.schema.json",
        ),
        (
            "owner evidence revision 2",
            owner_evidence_2,
            "evidence_record.v1.schema.json",
        ),
        (
            "reviewer evidence revision 1",
            reviewer_evidence_1,
            "evidence_record.v1.schema.json",
        ),
        (
            "reviewer evidence revision 2",
            reviewer_evidence_2,
            "evidence_record.v1.schema.json",
        ),
    ]
    for label, value, schema_name in direct_objects:
        _validate_production_object(value, schema_name, schema_path, label)
    if assignment["reviewer_relation"] == "INDEPENDENT":
        _validate_production_object(
            closure_event,
            "blocker_closure_event.v1.schema.json",
            schema_path,
            "closure event",
        )
    else:
        closure_errors = local_schema_bundle(
            str(schema_path.resolve())
        ).errors(closure_event, "blocker_closure_event.v1.schema.json")
        if not closure_errors:
            raise ValueError(
                "ORIGIN_OR_OWNER closure unexpectedly passed production schema"
            )
        _validate_production_object(
            closure_context_value,
            "unvalidated_candidate.v1.schema.json",
            schema_path,
            "closure candidate",
        )
    _validate_production_object(
        runner_input,
        "evaluation_runner_input.v1.schema.json",
        schema_path,
        "runner input",
    )

    validation_bundle = with_self_hash(
        {
            "schema_version": "PropertyMaterializationBundle.v1",
            "suite_id": envelope["suite_id"],
            "ordinal": envelope["ordinal"],
            "instance_id": envelope["instance_id"],
            "case_id": envelope["case_id"],
            "envelope_sha256": envelope["envelope_sha256"],
            "runner_input": runner_input,
            "sut_materialized_fixtures": fixture_values,
            "sut_materialized_fixtures_jcs_sha256": sha256_hex(
                fixture_values
            ),
        },
        "bundle_sha256",
        prefix=True,
    )
    _validate_production_object(
        validation_bundle,
        "property_materialization_bundle.v1.schema.json",
        schema_path,
        "materialization bundle projection",
    )
    return copy.deepcopy(runner_input), copy.deepcopy(fixture_values)


__all__ = [
    "INPUT_BINDING_ID",
    "MATERIALIZER_ID",
    "build_closure_materialization",
]
