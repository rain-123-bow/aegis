from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class RealFinalReviewLeaderError(RuntimeError):
    """Raised when Phase 21B real Final Review Leader validation fails."""


VALID_FINAL_REVIEW_DECISIONS = {
    "accept_for_master",
    "accept_for_master_with_scope_limit",
    "reject_to_execution_via_master",
    "request_test_expansion_via_master",
    "request_more_evidence_via_master",
    "governance_blocker_to_master",
    "blocked_resource_policy",
}

ACCEPTANCE_STATUS = "accepted_real_final_review_leader_closure"
PHASE21A_ACCEPTANCE_STATUS = "accepted_final_review_handoff_validation_closure"
PHASE21A_BOUNDARY = "final_review_handoff_validation_not_real_final_review_leader"

FORBIDDEN_TRUE_FIELDS = (
    "final_review_worker_created",
    "production_final_review_lifecycle_closure",
    "production_release_review_closure",
    "remote_push_performed",
    "pr_created",
    "production_merge_performed",
    "release_performed",
    "production_signoff_performed",
    "global_causal_truth_mutation",
)


@dataclass(frozen=True)
class FinalReviewLeaderPolicyProfile:
    role_id: str
    model: str
    reasoning_budget: str
    fallback_allowed: bool
    dynamic_adjustment_allowed: bool

    def assert_strict_extra_high(self) -> None:
        if self.role_id != "final_review_leader":
            raise RealFinalReviewLeaderError(f"final_review_leader profile has wrong role_id: {self.role_id}")
        if self.model != "gpt-5.5":
            raise RealFinalReviewLeaderError(f"final_review_leader model must be gpt-5.5, got {self.model}")
        if self.reasoning_budget != "extra_high":
            raise RealFinalReviewLeaderError(
                f"final_review_leader reasoning_budget must be extra_high, got {self.reasoning_budget}"
            )
        if self.fallback_allowed:
            raise RealFinalReviewLeaderError("final_review_leader fallback must be forbidden")
        if self.dynamic_adjustment_allowed:
            raise RealFinalReviewLeaderError("final_review_leader dynamic adjustment must be forbidden")


@dataclass(frozen=True)
class FinalReviewLeaderCreationRequest:
    agent_id: str
    role_id: str
    display_name: str
    model: str
    reasoning_budget: str
    parent_agent_id: str
    scope: str
    run_id: str
    instructions: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role_id": self.role_id,
            "display_name": self.display_name,
            "model": self.model,
            "reasoning_budget": self.reasoning_budget,
            "parent_agent_id": self.parent_agent_id,
            "scope": self.scope,
            "run_id": self.run_id,
            "instructions": self.instructions,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class FinalReviewLeaderCreationResponse:
    agent_id: str
    role_id: str
    status: str
    resolved_model: str
    resolved_reasoning_budget: str
    raw_response: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "FinalReviewLeaderCreationResponse":
        return cls(
            agent_id=str(value.get("agent_id", "")),
            role_id=str(value.get("role_id", "")),
            status=str(value.get("status", "")),
            resolved_model=str(value.get("resolved_model", value.get("model", ""))),
            resolved_reasoning_budget=str(value.get("resolved_reasoning_budget", value.get("reasoning_budget", ""))),
            raw_response=dict(value),
        )

    def assert_matches(self, request: FinalReviewLeaderCreationRequest) -> None:
        if self.agent_id != request.agent_id:
            raise RealFinalReviewLeaderError(f"agent_id mismatch: {self.agent_id} != {request.agent_id}")
        if self.role_id != request.role_id:
            raise RealFinalReviewLeaderError(f"role_id mismatch: {self.role_id} != {request.role_id}")
        if self.resolved_model != request.model:
            raise RealFinalReviewLeaderError(f"resolved_model mismatch: {self.resolved_model} != {request.model}")
        if self.resolved_reasoning_budget != request.reasoning_budget:
            raise RealFinalReviewLeaderError(
                f"resolved_reasoning_budget mismatch: {self.resolved_reasoning_budget} != {request.reasoning_budget}"
            )
        if self.status not in {"created", "active", "ready"}:
            raise RealFinalReviewLeaderError(f"invalid creation status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role_id": self.role_id,
            "status": self.status,
            "resolved_model": self.resolved_model,
            "resolved_reasoning_budget": self.resolved_reasoning_budget,
            "raw_response": dict(self.raw_response),
        }


def load_json_object(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RealFinalReviewLeaderError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RealFinalReviewLeaderError(f"invalid JSON file: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RealFinalReviewLeaderError(f"JSON file must contain an object: {path}")
    return payload


def write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_final_review_leader_policy(policy_path: str | Path) -> FinalReviewLeaderPolicyProfile:
    text = Path(policy_path).read_text(encoding="utf-8")
    profile_fields: dict[str, str] = {}
    in_profile = False
    for raw in text.splitlines():
        if raw.startswith("  final_review_leader:"):
            in_profile = True
            continue
        if in_profile and raw.startswith("  ") and not raw.startswith("    ") and raw.strip().endswith(":"):
            break
        if in_profile and raw.startswith("    ") and ":" in raw:
            key, value = raw.split(":", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            if key in {"role_id", "model", "reasoning_budget", "fallback_allowed", "dynamic_adjustment_allowed"}:
                profile_fields[key] = value

    required = ("role_id", "model", "reasoning_budget", "fallback_allowed", "dynamic_adjustment_allowed")
    missing = [key for key in required if key not in profile_fields]
    if missing:
        raise RealFinalReviewLeaderError(f"final_review_leader profile missing field(s): {', '.join(missing)}")

    profile = FinalReviewLeaderPolicyProfile(
        role_id=profile_fields["role_id"],
        model=profile_fields["model"],
        reasoning_budget=profile_fields["reasoning_budget"],
        fallback_allowed=_parse_bool(profile_fields["fallback_allowed"]),
        dynamic_adjustment_allowed=_parse_bool(profile_fields["dynamic_adjustment_allowed"]),
    )
    profile.assert_strict_extra_high()
    if "  - final_review_leader" in text:
        raise RealFinalReviewLeaderError("final_review_leader must not be in deferred_profiles")
    return profile


def build_final_review_leader_creation_request(
    *,
    policy_path: str | Path,
    phase21a_summary: dict[str, Any],
    phase21a_result: dict[str, Any],
    run_id: str,
    proof_dir: str | Path,
    output_dir: str | Path,
) -> FinalReviewLeaderCreationRequest:
    if not run_id:
        raise RealFinalReviewLeaderError("run_id is required")
    profile = load_final_review_leader_policy(policy_path)
    _assert_phase21a_summary(phase21a_summary)
    _assert_phase21a_result(phase21a_result)

    agent_id = f"final_review_leader__{_safe_id(run_id)}"
    proof_path = Path(proof_dir) / f"{agent_id}_proof.json"
    output_path = Path(output_dir) / f"{agent_id}_output.json"
    instructions = _leader_instructions(
        agent_id=agent_id,
        run_id=run_id,
        proof_path=proof_path,
        output_path=output_path,
        phase21a_summary=phase21a_summary,
        phase21a_result=phase21a_result,
    )
    return FinalReviewLeaderCreationRequest(
        agent_id=agent_id,
        role_id="final_review_leader",
        display_name="Final Review Leader Phase 21B",
        model=profile.model,
        reasoning_budget=profile.reasoning_budget,
        parent_agent_id="master",
        scope="top_level_master_domain",
        run_id=run_id,
        instructions=instructions,
        metadata={
            "policy_role_id": profile.role_id,
            "policy_model": profile.model,
            "policy_reasoning_budget": profile.reasoning_budget,
            "fallback_allowed": False,
            "dynamic_adjustment_allowed": False,
            "proof_path": str(proof_path),
            "output_path": str(output_path),
            "phase21a_summary_acceptance_status": phase21a_summary.get("acceptance_status"),
            "phase21a_decision": phase21a_summary.get("decision") or phase21a_result.get("decision"),
            "final_review_workers_forbidden": True,
        },
    )


def expected_final_review_leader_from_creation_request(request: FinalReviewLeaderCreationRequest) -> list[dict[str, Any]]:
    return [
        {
            "agent_id": request.agent_id,
            "role_id": request.role_id,
            "run_id": request.run_id,
            "policy_model": request.model,
            "policy_reasoning_budget": request.reasoning_budget,
            "proof_path": request.metadata["proof_path"],
            "output_path": request.metadata["output_path"],
        }
    ]


def audit_final_review_leader_proof(*, proof_dir: str | Path, expected_leaders: list[dict[str, Any]]) -> dict[str, Any]:
    if len(expected_leaders) != 1:
        raise RealFinalReviewLeaderError("Phase 21B expects exactly one Final Review Leader")
    proof_root = Path(proof_dir).resolve()
    if not proof_root.is_dir():
        raise RealFinalReviewLeaderError(f"proof directory does not exist: {proof_root}")
    expected = expected_leaders[0]
    proof_path = _resolve_expected_path(expected, root=proof_root, key="proof_path", suffix="_proof.json")
    proof = load_json_object(proof_path)
    _assert_leader_proof(proof=proof, expected=expected)
    return {
        "status": "passed",
        "audited_count": 1,
        "leaders": [
            {
                "agent_id": expected["agent_id"],
                "role_id": expected["role_id"],
                "run_id": expected["run_id"],
                "proof_path": str(proof_path),
                "sha256": _sha256_file(proof_path),
            }
        ],
    }


def audit_final_review_leader_output(*, output_dir: str | Path, expected_leaders: list[dict[str, Any]]) -> dict[str, Any]:
    if len(expected_leaders) != 1:
        raise RealFinalReviewLeaderError("Phase 21B expects exactly one Final Review Leader")
    output_root = Path(output_dir).resolve()
    if not output_root.is_dir():
        raise RealFinalReviewLeaderError(f"leader output directory does not exist: {output_root}")
    expected = expected_leaders[0]
    output_path = _resolve_expected_path(expected, root=output_root, key="output_path", suffix="_output.json")
    payload = load_json_object(output_path)
    _assert_leader_output(payload=payload, expected=expected)
    return {
        "status": "passed",
        "audited_count": 1,
        "leaders": [
            {
                "agent_id": expected["agent_id"],
                "role_id": expected["role_id"],
                "run_id": expected["run_id"],
                "output_path": str(output_path),
                "sha256": _sha256_file(output_path),
                "decision": payload.get("final_decision"),
            }
        ],
    }


def create_final_review_leader_via_mcp(
    *,
    request: FinalReviewLeaderCreationRequest,
    mcp_command: str,
    mcp_tool: str,
    timeout_seconds: float = 90.0,
) -> FinalReviewLeaderCreationResponse:
    with StdioMcpClient(mcp_command, timeout_seconds=timeout_seconds) as client:
        result = client.request("tools/call", {"name": mcp_tool, "arguments": request.to_dict()})
        payload = _normalize_tool_result(result)
        response = FinalReviewLeaderCreationResponse.from_mapping(payload)
        response.assert_matches(request)
        return response


def _assert_phase21a_summary(summary: dict[str, Any]) -> None:
    if summary.get("acceptance_status") != PHASE21A_ACCEPTANCE_STATUS:
        raise RealFinalReviewLeaderError("Phase 21A summary must be accepted_final_review_handoff_validation_closure")
    if summary.get("phase_boundary") != PHASE21A_BOUNDARY:
        raise RealFinalReviewLeaderError("Phase 21A phase_boundary is invalid")
    if summary.get("target") != "master":
        raise RealFinalReviewLeaderError("Phase 21A summary target must be master")
    if summary.get("output_route") != "final_review -> master":
        raise RealFinalReviewLeaderError("Phase 21A summary output_route must be final_review -> master")
    if summary.get("real_final_review_leader_created") is not False:
        raise RealFinalReviewLeaderError("Phase 21A must not have created a real Final Review Leader")
    for field_name in FORBIDDEN_TRUE_FIELDS:
        if field_name in summary and summary[field_name] is not False:
            raise RealFinalReviewLeaderError(f"Phase 21A summary field must be false: {field_name}")


def _assert_phase21a_result(result: dict[str, Any]) -> None:
    if result.get("target") != "master":
        raise RealFinalReviewLeaderError("Phase 21A result target must be master")
    if result.get("decision") not in VALID_FINAL_REVIEW_DECISIONS:
        raise RealFinalReviewLeaderError("Phase 21A result decision is invalid")
    if result.get("status") != "final_review_recommendation":
        raise RealFinalReviewLeaderError("Phase 21A result status must be final_review_recommendation")
    boundary = str(result.get("causal_boundary", ""))
    if "not global causal truth" not in boundary:
        raise RealFinalReviewLeaderError("Phase 21A result must preserve causal boundary")
    policy = result.get("resource_policy")
    if not isinstance(policy, dict):
        raise RealFinalReviewLeaderError("Phase 21A result requires resource_policy")
    if policy.get("required_profile") != "final_review_leader":
        raise RealFinalReviewLeaderError("Phase 21A result resource_policy.required_profile must be final_review_leader")
    if policy.get("status") != "satisfied":
        raise RealFinalReviewLeaderError("Phase 21B requires satisfied Final Review resource policy")


def _assert_leader_proof(*, proof: dict[str, Any], expected: dict[str, Any]) -> None:
    required = [
        "agent_id",
        "role_id",
        "created_by",
        "creation_mechanism",
        "requested_model",
        "policy_model",
        "requested_reasoning_effort",
        "policy_reasoning_budget",
        "topology_scope",
        "run_id",
        "proof_statement",
    ]
    missing = [key for key in required if not proof.get(key)]
    if missing:
        raise RealFinalReviewLeaderError(f"leader proof missing required field(s): {', '.join(missing)}")
    if proof["agent_id"] != expected["agent_id"]:
        raise RealFinalReviewLeaderError("leader proof agent_id mismatch")
    if proof["role_id"] != "final_review_leader" or expected["role_id"] != "final_review_leader":
        raise RealFinalReviewLeaderError("leader proof role_id must be final_review_leader")
    if proof["run_id"] != expected["run_id"]:
        raise RealFinalReviewLeaderError("leader proof run_id mismatch")
    if proof["created_by"] != "master":
        raise RealFinalReviewLeaderError("Final Review Leader must be created by Master")
    mechanism = str(proof["creation_mechanism"])
    if "nested-codex" not in mechanism and "mcp__nested_codex__.codex" not in mechanism and "Codex" not in mechanism:
        raise RealFinalReviewLeaderError("leader proof creation_mechanism must record real nested-Codex/Codex creation")
    if proof["requested_model"] != "gpt-5.5" or proof["policy_model"] != "gpt-5.5":
        raise RealFinalReviewLeaderError("leader proof model must be gpt-5.5")
    if proof["requested_reasoning_effort"] != "extra_high" or proof["policy_reasoning_budget"] != "extra_high":
        raise RealFinalReviewLeaderError("leader proof reasoning budget must be extra_high")
    if proof["topology_scope"] != "top_level_master_domain":
        raise RealFinalReviewLeaderError("leader proof topology_scope must be top_level_master_domain")
    timestamp = proof.get("created_at_utc") or proof.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise RealFinalReviewLeaderError("leader proof requires created_at_utc or timestamp")


def _assert_leader_output(*, payload: dict[str, Any], expected: dict[str, Any]) -> None:
    if payload.get("agent_id") != expected["agent_id"]:
        raise RealFinalReviewLeaderError("leader output agent_id mismatch")
    if payload.get("role_id") != "final_review_leader":
        raise RealFinalReviewLeaderError("leader output role_id must be final_review_leader")
    if payload.get("run_id") != expected["run_id"]:
        raise RealFinalReviewLeaderError("leader output run_id mismatch")
    if payload.get("source_phase") != "phase21a_final_review_handoff_validation":
        raise RealFinalReviewLeaderError("leader output source_phase is invalid")
    if payload.get("status") != "final_review_leader_report_candidate":
        raise RealFinalReviewLeaderError("leader output status must be final_review_leader_report_candidate")
    if payload.get("causal_status") != "final_review_recommendation_candidate":
        raise RealFinalReviewLeaderError("leader output causal_status must be final_review_recommendation_candidate")
    if payload.get("real_final_review_leader_created") is not True:
        raise RealFinalReviewLeaderError("leader output must state real_final_review_leader_created=true")
    for field_name in FORBIDDEN_TRUE_FIELDS:
        if payload.get(field_name) is not False:
            raise RealFinalReviewLeaderError(f"leader output field must be false: {field_name}")
    if payload.get("output_route") != "final_review -> master":
        raise RealFinalReviewLeaderError("leader output route must be final_review -> master")

    final_result = payload.get("final_review_result")
    if not isinstance(final_result, dict):
        raise RealFinalReviewLeaderError("leader output requires final_review_result object")
    _assert_phase21a_result(final_result)
    if payload.get("final_decision") != final_result.get("decision"):
        raise RealFinalReviewLeaderError("final_decision must match final_review_result.decision")

    required_list_fields = ("evidence_refs", "recommendation_scope", "known_limits", "blocked_scope")
    for key in required_list_fields:
        if not isinstance(payload.get(key), list):
            raise RealFinalReviewLeaderError(f"leader output {key} must be a list")
    if not payload["evidence_refs"]:
        raise RealFinalReviewLeaderError("leader output evidence_refs must not be empty")
    if not isinstance(payload.get("reviewed_refs"), dict):
        raise RealFinalReviewLeaderError("leader output reviewed_refs must be an object")


def _leader_instructions(
    *,
    agent_id: str,
    run_id: str,
    proof_path: Path,
    output_path: Path,
    phase21a_summary: dict[str, Any],
    phase21a_result: dict[str, Any],
) -> str:
    return (
        "You are the real Aegis Final Review Leader for Phase 21B. "
        "You are created by Master as the only Final Review Leader for this acceptance run. "
        "Do not create Final Review Workers. Do not parallelize review. "
        "Do not modify implementation code, run or replace Test routes, push, open PRs, merge, release, deploy, sign off production, or mutate global causal truth. "
        "Write the proof JSON before substantive review work.\n\n"
        f"agent_id: {agent_id}\n"
        f"run_id: {run_id}\n"
        f"proof_path: {proof_path}\n"
        f"output_path: {output_path}\n\n"
        "Proof JSON required fields: agent_id, role_id, created_by, creation_mechanism, requested_model, policy_model, "
        "requested_reasoning_effort, policy_reasoning_budget, topology_scope, run_id, created_at_utc, proof_statement. "
        "Use role_id=final_review_leader, created_by=master, requested_model=gpt-5.5, policy_model=gpt-5.5, "
        "requested_reasoning_effort=extra_high, policy_reasoning_budget=extra_high, topology_scope=top_level_master_domain.\n\n"
        "Output JSON required fields: agent_id, role_id, run_id, source_phase, phase21a_summary_ref, phase21a_result_ref, "
        "final_review_result, final_decision, output_route, reviewed_refs, evidence_refs, recommendation_scope, known_limits, "
        "blocked_scope, status, causal_status, real_final_review_leader_created, final_review_worker_created, "
        "production_final_review_lifecycle_closure, production_release_review_closure, global_causal_truth_mutation. "
        "Use status=final_review_leader_report_candidate and causal_status=final_review_recommendation_candidate.\n\n"
        f"phase21a_summary: {json.dumps(_compact_phase21a_summary(phase21a_summary), ensure_ascii=False)}\n"
        f"phase21a_result: {json.dumps(_compact_phase21a_result(phase21a_result), ensure_ascii=False)}\n"
    )


def _compact_phase21a_summary(summary: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "acceptance_status",
        "phase_boundary",
        "handoff_kind",
        "source_status",
        "request_id",
        "decision",
        "target",
        "output_route",
        "real_final_review_leader_created",
        "final_review_worker_created",
        "production_final_review_lifecycle_closure",
        "production_release_review_closure",
        "global_causal_truth_mutation",
    )
    return {key: summary.get(key) for key in keys if key in summary}


def _compact_phase21a_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": result.get("request_id"),
        "decision": result.get("decision"),
        "target": result.get("target"),
        "status": result.get("status"),
        "known_limits": result.get("known_limits"),
        "blocked_scope": result.get("blocked_scope"),
        "missing_evidence": result.get("missing_evidence"),
        "causal_boundary": result.get("causal_boundary"),
        "recommended_master_action": result.get("recommended_master_action"),
    }


def _parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    raise RealFinalReviewLeaderError(f"expected boolean, got {value!r}")


def _resolve_expected_path(expected: dict[str, Any], *, root: Path, key: str, suffix: str) -> Path:
    value = expected.get(key)
    if value:
        candidate = Path(str(value))
        if candidate.is_absolute():
            return candidate
        rooted = root / candidate
        if rooted.is_file():
            return rooted.resolve()
        by_name = root / candidate.name
        if by_name.is_file():
            return by_name.resolve()
        return rooted.resolve()
    return (root / f"{expected['agent_id']}{suffix}").resolve()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value)


def _normalize_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result.get("structuredContent"), dict):
        return dict(result["structuredContent"])
    content = result.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("json"), dict):
                    return dict(item["json"])
                text = item.get("text")
                if isinstance(text, str):
                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(parsed, dict):
                        return parsed
    if {"agent_id", "role_id"} <= set(result):
        return result
    raise RealFinalReviewLeaderError(f"MCP result did not contain structured leader data: {result!r}")


class StdioMcpClient:
    """Minimal stdio JSON-RPC MCP client for standardized create-agent tools."""

    def __init__(self, command: str, timeout_seconds: float = 90.0):
        if not command:
            raise RealFinalReviewLeaderError("mcp command is required")
        self.command = command
        self.timeout_seconds = timeout_seconds
        self._next_id = 1
        self._proc: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> "StdioMcpClient":
        self._proc = subprocess.Popen(
            shlex.split(self.command, posix=os.name != "nt"),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "aegis-final-review-real-leader", "version": "0.1.0"},
            },
        )
        self.notify("notifications/initialized", {})
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            proc.kill()
        self._proc = None

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        msg_id = self._next_id
        self._next_id += 1
        self._write_message({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
        while True:
            msg = self._read_message()
            if msg.get("id") != msg_id:
                continue
            if "error" in msg:
                raise RealFinalReviewLeaderError(f"MCP error for {method}: {msg['error']}")
            result = msg.get("result")
            if not isinstance(result, dict):
                raise RealFinalReviewLeaderError(f"MCP result for {method} must be an object")
            return result

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._write_message({"jsonrpc": "2.0", "method": method, "params": params})

    def _write_message(self, message: dict[str, Any]) -> None:
        proc = self._require_proc()
        assert proc.stdin is not None
        body = json.dumps(message, separators=(",", ":")).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        proc.stdin.write(header + body)
        proc.stdin.flush()

    def _read_message(self) -> dict[str, Any]:
        proc = self._require_proc()
        assert proc.stdout is not None
        headers = bytearray()
        while b"\r\n\r\n" not in headers:
            byte = proc.stdout.read(1)
            if not byte:
                stderr = b""
                if proc.stderr is not None:
                    stderr = proc.stderr.read() or b""
                raise RealFinalReviewLeaderError(f"MCP server closed stdout before response. stderr={stderr!r}")
            headers.extend(byte)
        header_text = headers.decode("ascii", errors="replace")
        length = None
        for line in header_text.split("\r\n"):
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
                break
        if length is None:
            raise RealFinalReviewLeaderError(f"MCP response missing Content-Length header: {header_text!r}")
        body = proc.stdout.read(length)
        if len(body) != length:
            raise RealFinalReviewLeaderError("MCP response body ended early")
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise RealFinalReviewLeaderError("MCP response must be a JSON object")
        return payload

    def _require_proc(self) -> subprocess.Popen[bytes]:
        if self._proc is None:
            raise RealFinalReviewLeaderError("MCP client is not started")
        return self._proc


__all__ = [
    "ACCEPTANCE_STATUS",
    "FinalReviewLeaderCreationRequest",
    "FinalReviewLeaderCreationResponse",
    "FinalReviewLeaderPolicyProfile",
    "RealFinalReviewLeaderError",
    "audit_final_review_leader_output",
    "audit_final_review_leader_proof",
    "build_final_review_leader_creation_request",
    "create_final_review_leader_via_mcp",
    "expected_final_review_leader_from_creation_request",
    "load_final_review_leader_policy",
]
