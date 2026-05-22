"""Phase 19B historical strict real Front/Back proof-audit path.

This module intentionally preserves the older Phase 19B strict model policy checks:
gpt-5.5 / high, fallback forbidden, and dynamic adjustment forbidden.

Phase 26A role-bound Execution skill enforcement lives in ``operational_skill.py`` and
follows the root ``MODEL_REASONING_BUDGET_POLICY.yaml`` authority, including explicit
gpt-5.5 -> gpt-5.4 fallback with evidence when the root policy allows it.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class RealExecutionAgentError(RuntimeError):
    """Raised when Phase 19B real Execution Front/Back agent validation fails."""


@dataclass(frozen=True)
class ExecutionAgentPolicyProfile:
    role_id: str
    model: str
    reasoning_budget: str
    fallback_allowed: bool
    dynamic_adjustment_allowed: bool

    def assert_strict_high(self, expected_role: str) -> None:
        if self.role_id != expected_role:
            raise RealExecutionAgentError(f"{expected_role} profile has wrong role_id: {self.role_id}")
        if self.model != "gpt-5.5":
            raise RealExecutionAgentError(f"{expected_role} model must be gpt-5.5, got {self.model}")
        if self.reasoning_budget != "high":
            raise RealExecutionAgentError(f"{expected_role} reasoning_budget must be high, got {self.reasoning_budget}")
        if self.fallback_allowed:
            raise RealExecutionAgentError(f"{expected_role} fallback must be forbidden")
        if self.dynamic_adjustment_allowed:
            raise RealExecutionAgentError(f"{expected_role} dynamic adjustment must be forbidden")


@dataclass(frozen=True)
class ExecutionAgentCreationRequest:
    agent_id: str
    role_id: str
    display_name: str
    model: str
    reasoning_budget: str
    parent_agent_id: str
    scope: str
    run_id: str
    group_id: str
    subtask_id: str
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
            "group_id": self.group_id,
            "subtask_id": self.subtask_id,
            "instructions": self.instructions,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ExecutionAgentCreationResponse:
    agent_id: str
    role_id: str
    status: str
    resolved_model: str
    resolved_reasoning_budget: str
    raw_response: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ExecutionAgentCreationResponse":
        return cls(
            agent_id=str(value.get("agent_id", "")),
            role_id=str(value.get("role_id", "")),
            status=str(value.get("status", "")),
            resolved_model=str(value.get("resolved_model", value.get("model", ""))),
            resolved_reasoning_budget=str(value.get("resolved_reasoning_budget", value.get("reasoning_budget", ""))),
            raw_response=dict(value),
        )

    def assert_matches(self, request: ExecutionAgentCreationRequest) -> None:
        if self.agent_id != request.agent_id:
            raise RealExecutionAgentError(f"agent_id mismatch: {self.agent_id} != {request.agent_id}")
        if self.role_id != request.role_id:
            raise RealExecutionAgentError(f"role_id mismatch: {self.role_id} != {request.role_id}")
        if self.resolved_model != request.model:
            raise RealExecutionAgentError(f"resolved_model mismatch: {self.resolved_model} != {request.model}")
        if self.resolved_reasoning_budget != request.reasoning_budget:
            raise RealExecutionAgentError(
                f"resolved_reasoning_budget mismatch: {self.resolved_reasoning_budget} != {request.reasoning_budget}"
            )
        if self.status not in {"created", "active", "ready"}:
            raise RealExecutionAgentError(f"invalid creation status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role_id": self.role_id,
            "status": self.status,
            "resolved_model": self.resolved_model,
            "resolved_reasoning_budget": self.resolved_reasoning_budget,
            "raw_response": dict(self.raw_response),
        }


def _parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    raise RealExecutionAgentError(f"expected boolean, got {value!r}")


def load_execution_agent_policies(policy_path: str | Path) -> dict[str, ExecutionAgentPolicyProfile]:
    text = Path(policy_path).read_text(encoding="utf-8")
    profiles: dict[str, dict[str, str]] = {}
    in_profiles = False
    current_profile: str | None = None

    for raw in text.splitlines():
        if raw.startswith("profiles:"):
            in_profiles = True
            current_profile = None
            continue
        if not in_profiles:
            continue
        if raw and not raw.startswith(" "):
            current_profile = None
            continue
        if raw.startswith("  ") and not raw.startswith("    ") and raw.strip().endswith(":"):
            current_profile = raw.strip()[:-1]
            profiles.setdefault(current_profile, {})
            continue
        if current_profile in {"execution_front_agent", "execution_back_agent"} and raw.startswith("    ") and ":" in raw:
            key, value = raw.split(":", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            if key in {"role_id", "model", "reasoning_budget", "fallback_allowed", "dynamic_adjustment_allowed"}:
                profiles[current_profile][key] = value

    result: dict[str, ExecutionAgentPolicyProfile] = {}
    for role in ("execution_front_agent", "execution_back_agent"):
        fields = profiles.get(role, {})
        missing = [
            key
            for key in ("role_id", "model", "reasoning_budget", "fallback_allowed", "dynamic_adjustment_allowed")
            if key not in fields
        ]
        if missing:
            raise RealExecutionAgentError(f"{role} profile missing field(s): {', '.join(missing)}")
        profile = ExecutionAgentPolicyProfile(
            role_id=fields["role_id"],
            model=fields["model"],
            reasoning_budget=fields["reasoning_budget"],
            fallback_allowed=_parse_bool(fields["fallback_allowed"]),
            dynamic_adjustment_allowed=_parse_bool(fields["dynamic_adjustment_allowed"]),
        )
        profile.assert_strict_high(role)
        result[role] = profile
    return result


def build_execution_agent_creation_requests(
    *,
    policy_path: str | Path,
    execution_package: dict[str, Any],
    run_id: str,
    proof_dir: str | Path,
    output_dir: str | Path,
) -> list[ExecutionAgentCreationRequest]:
    policies = load_execution_agent_policies(policy_path)
    groups = _extract_group_records(execution_package)
    proof_root = Path(proof_dir)
    output_root = Path(output_dir)
    requests: list[ExecutionAgentCreationRequest] = []

    for group in groups:
        group_id = str(group["group_id"])
        subtask_id = str(group.get("subtask_id", group_id))
        for role_id in ("execution_front_agent", "execution_back_agent"):
            profile = policies[role_id]
            agent_kind = "front" if role_id == "execution_front_agent" else "back"
            agent_id = f"execution_{agent_kind}__{_safe_id(run_id)}__{_safe_id(group_id)}"
            proof_path = proof_root / f"{agent_id}_proof.json"
            agent_output_path = output_root / f"{agent_id}_output.json"
            instructions = _agent_instructions(
                role_id=role_id,
                run_id=run_id,
                group=group,
                proof_path=proof_path,
                output_path=agent_output_path,
                execution_package=execution_package,
            )
            requests.append(
                ExecutionAgentCreationRequest(
                    agent_id=agent_id,
                    role_id=role_id,
                    display_name=f"Execution {agent_kind.title()} Agent {group_id}",
                    model=profile.model,
                    reasoning_budget=profile.reasoning_budget,
                    parent_agent_id="execution_leader",
                    scope="execution_group_local_domain",
                    run_id=run_id,
                    group_id=group_id,
                    subtask_id=subtask_id,
                    instructions=instructions,
                    metadata={
                        "policy_role_id": profile.role_id,
                        "policy_model": profile.model,
                        "policy_reasoning_budget": profile.reasoning_budget,
                        "fallback_allowed": False,
                        "dynamic_adjustment_allowed": False,
                        "proof_path": str(proof_path),
                        "output_path": str(agent_output_path),
                        "group_id": group_id,
                        "subtask_id": subtask_id,
                    },
                )
            )
    return requests


def expected_agents_from_creation_requests(requests: list[ExecutionAgentCreationRequest]) -> list[dict[str, Any]]:
    return [
        {
            "agent_id": request.agent_id,
            "role_id": request.role_id,
            "group_id": request.group_id,
            "subtask_id": request.subtask_id,
            "policy_model": request.model,
            "policy_reasoning_budget": request.reasoning_budget,
            "proof_path": request.metadata["proof_path"],
            "output_path": request.metadata["output_path"],
        }
        for request in requests
    ]


def audit_execution_agent_proofs(*, proof_dir: str | Path, expected_agents: list[dict[str, Any]]) -> dict[str, Any]:
    proof_root = Path(proof_dir).resolve()
    if not proof_root.is_dir():
        raise RealExecutionAgentError(f"proof directory does not exist: {proof_root}")
    if not expected_agents:
        raise RealExecutionAgentError("expected_agents must not be empty")

    audited: list[dict[str, Any]] = []
    for expected in expected_agents:
        proof_path = _resolve_expected_path(expected, root=proof_root, key="proof_path", suffix="_proof.json")
        proof = _read_json(proof_path)
        _assert_proof(proof=proof, expected=expected)
        audited.append(
            {
                "agent_id": expected["agent_id"],
                "role_id": expected["role_id"],
                "group_id": expected["group_id"],
                "proof_path": str(proof_path),
                "sha256": _sha256_file(proof_path),
            }
        )
    return {"status": "passed", "audited_count": len(audited), "agents": audited}


def audit_execution_agent_outputs(*, output_dir: str | Path, expected_agents: list[dict[str, Any]]) -> dict[str, Any]:
    output_root = Path(output_dir).resolve()
    if not output_root.is_dir():
        raise RealExecutionAgentError(f"output directory does not exist: {output_root}")
    if not expected_agents:
        raise RealExecutionAgentError("expected_agents must not be empty")

    audited: list[dict[str, Any]] = []
    for expected in expected_agents:
        output_path = _resolve_expected_path(expected, root=output_root, key="output_path", suffix="_output.json")
        payload = _read_json(output_path)
        _assert_agent_output(payload=payload, expected=expected)
        audited.append(
            {
                "agent_id": expected["agent_id"],
                "role_id": expected["role_id"],
                "group_id": expected["group_id"],
                "output_path": str(output_path),
                "sha256": _sha256_file(output_path),
            }
        )
    return {"status": "passed", "audited_count": len(audited), "agents": audited}


def _extract_group_records(execution_package: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(execution_package.get("group_records"), list):
        return [dict(item) for item in execution_package["group_records"]]
    package = execution_package.get("test_handoff_package")
    if isinstance(package, dict) and isinstance(package.get("group_mapping"), list):
        return [dict(item) for item in package["group_mapping"]]
    if isinstance(execution_package.get("group_mapping"), list):
        return [dict(item) for item in execution_package["group_mapping"]]
    raise RealExecutionAgentError("execution package requires group_records or group_mapping")


def _agent_instructions(
    *,
    role_id: str,
    run_id: str,
    group: dict[str, Any],
    proof_path: Path,
    output_path: Path,
    execution_package: dict[str, Any],
) -> str:
    group_id = str(group.get("group_id", "unknown_group"))
    subtask_id = str(group.get("subtask_id", group_id))
    common = (
        "You are a request-scoped Aegis Execution Department internal agent. "
        "You were created by the Execution Leader, not by Master. "
        "You are bound to exactly one Execution Group. "
        "Do not push, open PRs, merge remote branches, release, deploy, or claim global causal truth. "
        "Write your proof JSON file before doing substantive work.\n\n"
        f"run_id: {run_id}\n"
        f"group_id: {group_id}\n"
        f"subtask_id: {subtask_id}\n"
        f"proof_path: {proof_path}\n"
        f"output_path: {output_path}\n"
        f"group_record: {json.dumps(group, ensure_ascii=False)}\n"
        f"execution_package_summary: {json.dumps(_package_summary(execution_package), ensure_ascii=False)}\n\n"
    )
    proof_rule = (
        "The proof JSON must contain: agent_id, role_id, created_by, creation_mechanism, requested_model, "
        "policy_model, requested_reasoning_effort, policy_reasoning_budget, topology_scope, run_id, group_id, "
        "subtask_id, created_at_utc, and proof_statement.\n\n"
    )
    if role_id == "execution_front_agent":
        return common + proof_rule + (
            "As Front Agent, inspect your group scope and produce front_output JSON at output_path. "
            "The output must include: agent_id, role_id, group_id, subtask_id, implementation_summary, touched_files, "
            "local_test_evidence, group_causal_fork, known_limits, and status. "
            "group_causal_fork.status must be causal_candidate."
        )
    return common + proof_rule + (
        "As Back Agent, independently review the Front output and group branch evidence when available. "
        "Produce back_review JSON at output_path. The output must include: agent_id, role_id, group_id, subtask_id, "
        "reviewed_front_agent_id, review_decision, review_summary, blocking_objections, evidence_checked, risk_notes, "
        "and status. Do not accept without evidence."
    )


def _package_summary(package: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": package.get("run_id"),
        "status": package.get("status"),
        "target_repo": package.get("target_repo"),
        "integration_branch": package.get("integration_branch"),
        "integration_commit": package.get("integration_commit"),
    }


def _assert_proof(*, proof: dict[str, Any], expected: dict[str, Any]) -> None:
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
        "group_id",
        "subtask_id",
        "proof_statement",
    ]
    missing = [key for key in required if not proof.get(key)]
    if missing:
        raise RealExecutionAgentError(f"proof missing required field(s): {', '.join(missing)}")

    if proof["agent_id"] != expected["agent_id"]:
        raise RealExecutionAgentError("proof agent_id mismatch")
    if proof["role_id"] != expected["role_id"]:
        raise RealExecutionAgentError("proof role_id mismatch")
    if proof["group_id"] != expected["group_id"]:
        raise RealExecutionAgentError("proof group_id mismatch")
    if proof["subtask_id"] != expected["subtask_id"]:
        raise RealExecutionAgentError("proof subtask_id mismatch")
    if proof["created_by"] != "execution_leader":
        raise RealExecutionAgentError("proof created_by must be execution_leader")
    mechanism = str(proof["creation_mechanism"])
    if "nested-codex" not in mechanism and "mcp__nested_codex__.codex" not in mechanism and "Codex" not in mechanism:
        raise RealExecutionAgentError("proof creation_mechanism must record real nested-Codex/Codex creation")
    if proof["requested_model"] != "gpt-5.5" or proof["policy_model"] != "gpt-5.5":
        raise RealExecutionAgentError("proof model must be gpt-5.5")
    if proof["requested_reasoning_effort"] != "high" or proof["policy_reasoning_budget"] != "high":
        raise RealExecutionAgentError("proof reasoning budget must be high")
    if proof["topology_scope"] != "execution_group_local_domain":
        raise RealExecutionAgentError("proof topology_scope must be execution_group_local_domain")
    timestamp = proof.get("created_at_utc") or proof.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise RealExecutionAgentError("proof requires created_at_utc or timestamp")


def _assert_agent_output(*, payload: dict[str, Any], expected: dict[str, Any]) -> None:
    for key in ("agent_id", "role_id", "group_id", "subtask_id"):
        if payload.get(key) != expected[key]:
            raise RealExecutionAgentError(f"output {key} mismatch")

    if expected["role_id"] == "execution_front_agent":
        required = ["implementation_summary", "touched_files", "local_test_evidence", "group_causal_fork", "known_limits", "status"]
        missing = [key for key in required if key not in payload]
        if missing:
            raise RealExecutionAgentError(f"front output missing field(s): {', '.join(missing)}")
        if not isinstance(payload["local_test_evidence"], list):
            raise RealExecutionAgentError("front output local_test_evidence must be a list")
        fork = payload["group_causal_fork"]
        if not isinstance(fork, dict) or fork.get("status") != "causal_candidate":
            raise RealExecutionAgentError("front output group_causal_fork must remain causal_candidate")
        if payload["status"] != "front_output_candidate":
            raise RealExecutionAgentError("front output status must be front_output_candidate")
        return

    required = ["reviewed_front_agent_id", "review_decision", "review_summary", "blocking_objections", "evidence_checked", "risk_notes", "status"]
    missing = [key for key in required if key not in payload]
    if missing:
        raise RealExecutionAgentError(f"back review missing field(s): {', '.join(missing)}")
    if payload["review_decision"] not in {
        "accept",
        "reject",
        "request_changes",
        "request_more_evidence",
        "scope_violation",
        "contract_violation",
    }:
        raise RealExecutionAgentError("back review_decision is invalid")
    if not isinstance(payload["blocking_objections"], list):
        raise RealExecutionAgentError("back blocking_objections must be a list")
    if payload["status"] != "review_candidate":
        raise RealExecutionAgentError("back review status must be review_candidate")


def _resolve_expected_path(expected: dict[str, Any], *, root: Path, key: str, suffix: str) -> Path:
    value = expected.get(key)
    if value:
        candidate = Path(str(value))
        if candidate.is_absolute():
            return candidate
        if candidate.is_file():
            return candidate.resolve()
        rooted = root / candidate.name if str(candidate).startswith(str(root)) else root / candidate
        if rooted.is_file():
            return rooted.resolve()
        return rooted.resolve()
    return (root / f"{expected['agent_id']}{suffix}").resolve()


def create_agents_via_mcp(
    *,
    requests: list[ExecutionAgentCreationRequest],
    mcp_command: str,
    mcp_tool: str,
    timeout_seconds: float = 90.0,
) -> list[ExecutionAgentCreationResponse]:
    responses: list[ExecutionAgentCreationResponse] = []
    with StdioMcpClient(mcp_command, timeout_seconds=timeout_seconds) as client:
        for request in requests:
            result = client.request("tools/call", {"name": mcp_tool, "arguments": request.to_dict()})
            payload = _normalize_tool_result(result)
            response = ExecutionAgentCreationResponse.from_mapping(payload)
            response.assert_matches(request)
            responses.append(response)
    return responses


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
    raise RealExecutionAgentError(f"MCP result did not contain structured agent data: {result!r}")


class StdioMcpClient:
    """Minimal stdio JSON-RPC MCP client for standardized create-agent tools."""

    def __init__(self, command: str, timeout_seconds: float = 90.0):
        if not command:
            raise RealExecutionAgentError("mcp command is required")
        self.command = command
        self.timeout_seconds = timeout_seconds
        self._next_id = 1
        self._proc: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> "StdioMcpClient":
        self._proc = subprocess.Popen(
            shlex.split(self.command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "aegis-execution-real-agents", "version": "0.1.0"},
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
        proc = self._require_proc()
        msg_id = self._next_id
        self._next_id += 1
        self._write_message({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
        while True:
            msg = self._read_message()
            if msg.get("id") != msg_id:
                continue
            if "error" in msg:
                raise RealExecutionAgentError(f"MCP error for {method}: {msg['error']}")
            result = msg.get("result")
            if not isinstance(result, dict):
                raise RealExecutionAgentError(f"MCP result for {method} must be an object")
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
                raise RealExecutionAgentError(f"MCP server closed stdout before response. stderr={stderr!r}")
            headers.extend(byte)
        header_text = headers.decode("ascii", errors="replace")
        length = None
        for line in header_text.split("\r\n"):
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
                break
        if length is None:
            raise RealExecutionAgentError(f"MCP response missing Content-Length header: {header_text!r}")
        body = proc.stdout.read(length)
        if len(body) != length:
            raise RealExecutionAgentError("MCP response body ended early")
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise RealExecutionAgentError("MCP response must be a JSON object")
        return payload

    def _require_proc(self) -> subprocess.Popen[bytes]:
        if self._proc is None:
            raise RealExecutionAgentError("MCP client is not started")
        return self._proc


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RealExecutionAgentError(f"required JSON file does not exist: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RealExecutionAgentError(f"required JSON file is malformed: {path}") from exc


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
