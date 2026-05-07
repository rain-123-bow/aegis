from __future__ import annotations

import base64
import hashlib
import json
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class RealNestedCodexDebateWorkerError(RuntimeError):
    """Raised when strict real nested-Codex Debate Worker validation fails."""


@dataclass(frozen=True)
class DebateWorkerPolicyProfile:
    role_id: str
    model: str
    reasoning_budget: str
    fallback_allowed: bool
    dynamic_adjustment_allowed: bool

    def assert_strict_high(self) -> None:
        if self.role_id != "debate_worker":
            raise RealNestedCodexDebateWorkerError(f"debate_worker profile has wrong role_id: {self.role_id}")
        if self.model != "gpt-5.5":
            raise RealNestedCodexDebateWorkerError(f"debate_worker model must be gpt-5.5, got {self.model}")
        if self.reasoning_budget != "high":
            raise RealNestedCodexDebateWorkerError(
                f"debate_worker reasoning_budget must be high, got {self.reasoning_budget}"
            )
        if self.fallback_allowed:
            raise RealNestedCodexDebateWorkerError("debate_worker fallback must be forbidden")
        if self.dynamic_adjustment_allowed:
            raise RealNestedCodexDebateWorkerError("debate_worker dynamic adjustment must be forbidden")


@dataclass(frozen=True)
class DebateWorkerCreationRequest:
    agent_id: str
    worker_id: str
    role_id: str
    display_name: str
    model: str
    reasoning_budget: str
    parent_agent_id: str
    scope: str
    run_id: str
    stance_id: str
    instructions: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "worker_id": self.worker_id,
            "role_id": self.role_id,
            "display_name": self.display_name,
            "model": self.model,
            "reasoning_budget": self.reasoning_budget,
            "parent_agent_id": self.parent_agent_id,
            "scope": self.scope,
            "run_id": self.run_id,
            "stance_id": self.stance_id,
            "instructions": self.instructions,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class DebateWorkerCreationResponse:
    agent_id: str
    role_id: str
    status: str
    resolved_model: str
    resolved_reasoning_budget: str
    raw_response: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "DebateWorkerCreationResponse":
        return cls(
            agent_id=str(value.get("agent_id", "")),
            role_id=str(value.get("role_id", "")),
            status=str(value.get("status", "")),
            resolved_model=str(value.get("resolved_model", value.get("model", ""))),
            resolved_reasoning_budget=str(value.get("resolved_reasoning_budget", value.get("reasoning_budget", ""))),
            raw_response=dict(value),
        )

    def assert_matches(self, request: DebateWorkerCreationRequest) -> None:
        if self.agent_id != request.agent_id:
            raise RealNestedCodexDebateWorkerError(f"agent_id mismatch: {self.agent_id} != {request.agent_id}")
        if self.role_id != request.role_id:
            raise RealNestedCodexDebateWorkerError(f"role_id mismatch: {self.role_id} != {request.role_id}")
        if self.resolved_model != request.model:
            raise RealNestedCodexDebateWorkerError(
                f"resolved_model mismatch: {self.resolved_model} != {request.model}"
            )
        if self.resolved_reasoning_budget != request.reasoning_budget:
            raise RealNestedCodexDebateWorkerError(
                "resolved_reasoning_budget mismatch: "
                f"{self.resolved_reasoning_budget} != {request.reasoning_budget}"
            )
        if self.status not in {"created", "active", "ready"}:
            raise RealNestedCodexDebateWorkerError(f"invalid creation status: {self.status}")

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
    raise RealNestedCodexDebateWorkerError(f"expected boolean, got {value!r}")


def load_debate_worker_policy(policy_path: str | Path) -> DebateWorkerPolicyProfile:
    text = Path(policy_path).read_text(encoding="utf-8")
    lines = text.splitlines()
    in_profiles = False
    in_debate_worker = False
    fields: dict[str, str] = {}

    for raw in lines:
        if raw.startswith("profiles:"):
            in_profiles = True
            in_debate_worker = False
            continue
        if not in_profiles:
            continue
        if raw.startswith("  ") and not raw.startswith("    ") and raw.strip().endswith(":"):
            in_debate_worker = raw.strip() == "debate_worker:"
            continue
        if in_debate_worker and raw.startswith("    ") and ":" in raw:
            key, value = raw.split(":", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            if key in {"role_id", "model", "reasoning_budget", "fallback_allowed", "dynamic_adjustment_allowed"}:
                fields[key] = value

    required = ["role_id", "model", "reasoning_budget", "fallback_allowed", "dynamic_adjustment_allowed"]
    missing = [key for key in required if key not in fields]
    if missing:
        raise RealNestedCodexDebateWorkerError(f"debate_worker profile missing field(s): {', '.join(missing)}")

    profile = DebateWorkerPolicyProfile(
        role_id=fields["role_id"],
        model=fields["model"],
        reasoning_budget=fields["reasoning_budget"],
        fallback_allowed=_parse_bool(fields["fallback_allowed"]),
        dynamic_adjustment_allowed=_parse_bool(fields["dynamic_adjustment_allowed"]),
    )
    profile.assert_strict_high()
    return profile


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value)


def build_debate_worker_creation_requests(
    *,
    policy_path: str | Path,
    debate_request: dict[str, Any],
    run_id: str,
    proof_dir: str | Path,
) -> list[DebateWorkerCreationRequest]:
    profile = load_debate_worker_policy(policy_path)
    stances = debate_request.get("candidate_stances")
    if not isinstance(stances, list) or len(stances) < 2:
        raise RealNestedCodexDebateWorkerError("real Debate Worker creation requires at least two candidate stances")

    proof_root = Path(proof_dir)
    requests: list[DebateWorkerCreationRequest] = []
    for index, stance in enumerate(stances):
        if not isinstance(stance, dict):
            raise RealNestedCodexDebateWorkerError("candidate stance entries must be objects")
        stance_id = str(stance.get("stance_id") or f"S{index + 1}")
        worker_id = f"debate_worker__{_safe_id(run_id)}__{_safe_id(stance_id)}"
        proof_path = proof_root / f"{worker_id}_proof.json"
        instructions = _worker_instructions(
            run_id=run_id,
            worker_id=worker_id,
            stance=stance,
            debate_request=debate_request,
            proof_path=proof_path,
        )
        requests.append(
            DebateWorkerCreationRequest(
                agent_id=worker_id,
                worker_id=worker_id,
                role_id="debate_worker",
                display_name=f"Debate Worker {stance_id}",
                model=profile.model,
                reasoning_budget=profile.reasoning_budget,
                parent_agent_id="debate_leader",
                scope="debate_run_local_domain",
                run_id=run_id,
                stance_id=stance_id,
                instructions=instructions,
                metadata={
                    "policy_role_id": profile.role_id,
                    "policy_model": profile.model,
                    "policy_reasoning_budget": profile.reasoning_budget,
                    "fallback_allowed": False,
                    "dynamic_adjustment_allowed": False,
                    "proof_path": str(proof_path),
                    "debate_request_id": debate_request.get("request_id"),
                    "decision_target": debate_request.get("decision_target"),
                },
            )
        )
    return requests


def _worker_instructions(
    *,
    run_id: str,
    worker_id: str,
    stance: dict[str, Any],
    debate_request: dict[str, Any],
    proof_path: Path,
) -> str:
    return (
        "You are a request-scoped Aegis Debate Worker. "
        "You are bound to exactly one stance and must not switch stances. "
        "Argue from first principles, real material conditions, evidence, explicit assumptions, contracts, scope, and risk. "
        "Do not invent evidence. Do not add hidden assumptions. Do not concede without causal defeat. "
        "Do not deadlock debate by rhetorical obstruction. Maintain worker_local_causal_state with route_priority and expand_priority. "
        "Write an auditable proof JSON file before doing any other work.\n\n"
        f"run_id: {run_id}\n"
        f"worker_id: {worker_id}\n"
        f"proof_path: {proof_path}\n"
        f"stance: {json.dumps(stance, ensure_ascii=False)}\n"
        f"debate_request: {json.dumps(debate_request, ensure_ascii=False)}\n\n"
        "The proof JSON must contain: agent_id, worker_id, stance_id, role_id, created_by, creation_mechanism, "
        "requested_model, policy_model, requested_reasoning_effort, policy_reasoning_budget, topology_scope, "
        "run_id, created_at_utc, proof_statement, and worker_local_causal_state."
    )


class StdioMcpClient:
    """Minimal stdio JSON-RPC MCP client for standardized create-agent tools."""

    def __init__(self, command: str, timeout_seconds: float = 90.0):
        if not command:
            raise RealNestedCodexDebateWorkerError("mcp command is required")
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
                "clientInfo": {"name": "aegis-debate-real-worker", "version": "0.1.0"},
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
                raise RealNestedCodexDebateWorkerError(f"MCP error for {method}: {msg['error']}")
            result = msg.get("result")
            if not isinstance(result, dict):
                raise RealNestedCodexDebateWorkerError(f"MCP result for {method} must be an object")
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
                raise RealNestedCodexDebateWorkerError(f"MCP server closed stdout before response. stderr={stderr!r}")
            headers.extend(byte)
        header_text = headers.decode("ascii", errors="replace")
        length = None
        for line in header_text.split("\r\n"):
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
                break
        if length is None:
            raise RealNestedCodexDebateWorkerError(f"MCP response missing Content-Length header: {header_text!r}")
        body = proc.stdout.read(length)
        if len(body) != length:
            raise RealNestedCodexDebateWorkerError("MCP response body ended early")
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise RealNestedCodexDebateWorkerError("MCP response must be a JSON object")
        return payload

    def _require_proc(self) -> subprocess.Popen[bytes]:
        if self._proc is None:
            raise RealNestedCodexDebateWorkerError("MCP client is not started")
        return self._proc


def normalize_mcp_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result.get("structuredContent"), dict):
        return dict(result["structuredContent"])
    content = result.get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
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
    raise RealNestedCodexDebateWorkerError(f"MCP tool result did not contain structured agent data: {result!r}")


def create_workers_via_mcp(
    *,
    requests: list[DebateWorkerCreationRequest],
    mcp_command: str,
    mcp_tool: str,
    timeout_seconds: float = 90.0,
) -> list[DebateWorkerCreationResponse]:
    responses: list[DebateWorkerCreationResponse] = []
    with StdioMcpClient(mcp_command, timeout_seconds=timeout_seconds) as client:
        for request in requests:
            result = client.request("tools/call", {"name": mcp_tool, "arguments": request.to_dict()})
            payload = normalize_mcp_tool_result(result)
            response = DebateWorkerCreationResponse.from_mapping(payload)
            response.assert_matches(request)
            responses.append(response)
    return responses


def audit_debate_worker_proofs(
    *,
    proof_dir: str | Path,
    expected_workers: list[dict[str, Any]],
) -> dict[str, Any]:
    root = Path(proof_dir)
    if not root.is_dir():
        raise RealNestedCodexDebateWorkerError(f"proof directory does not exist: {root}")
    audited: list[dict[str, Any]] = []
    for expected in expected_workers:
        worker_id = str(expected["worker_id"])
        stance_id = str(expected["stance_id"])
        proof_path = _resolve_expected_proof_path(root, expected, worker_id)
        if not proof_path.is_file():
            raise RealNestedCodexDebateWorkerError(f"missing real Debate Worker proof: {proof_path}")
        file_bytes = proof_path.read_bytes()
        proof = json.loads(file_bytes.decode("utf-8"))
        _assert_proof(proof=proof, worker_id=worker_id, stance_id=stance_id)
        audited.append(
            {
                "worker_id": worker_id,
                "stance_id": stance_id,
                "proof_path": str(proof_path),
                "sha256": hashlib.sha256(file_bytes).hexdigest(),
            }
        )
    return {"status": "passed", "audited_count": len(audited), "workers": audited}


def _resolve_expected_proof_path(root: Path, expected: dict[str, Any], worker_id: str) -> Path:
    raw = expected.get("proof_path")
    if not raw:
        return root / f"{worker_id}_proof.json"

    candidate = Path(str(raw))
    if candidate.is_absolute():
        return candidate

    root_resolved = root.resolve()
    candidate_resolved = candidate.resolve()
    try:
        if candidate_resolved.is_relative_to(root_resolved):
            return candidate
    except AttributeError:
        if str(candidate_resolved).startswith(str(root_resolved)):
            return candidate

    return root / candidate


def _assert_proof(*, proof: dict[str, Any], worker_id: str, stance_id: str) -> None:
    expected_pairs = {
        "worker_id": worker_id,
        "agent_id": worker_id,
        "stance_id": stance_id,
        "role_id": "debate_worker",
        "created_by": "debate_leader",
        "requested_model": "gpt-5.5",
        "policy_model": "gpt-5.5",
        "requested_reasoning_effort": "high",
        "policy_reasoning_budget": "high",
        "topology_scope": "debate_run_local_domain",
    }
    for key, expected in expected_pairs.items():
        if proof.get(key) != expected:
            raise RealNestedCodexDebateWorkerError(f"proof {key} mismatch: {proof.get(key)!r} != {expected!r}")
    mechanism = str(proof.get("creation_mechanism", ""))
    if "nested-codex" not in mechanism and "mcp" not in mechanism.lower() and "codex" not in mechanism.lower():
        raise RealNestedCodexDebateWorkerError("proof does not record real nested-Codex creation mechanism")
    if not isinstance(proof.get("proof_statement"), str) or not proof["proof_statement"].strip():
        raise RealNestedCodexDebateWorkerError("proof_statement is required")
    if not isinstance(proof.get("created_at_utc"), str) or not proof["created_at_utc"].strip():
        raise RealNestedCodexDebateWorkerError("created_at_utc is required")
    state = proof.get("worker_local_causal_state")
    if not isinstance(state, dict):
        raise RealNestedCodexDebateWorkerError("worker_local_causal_state is required in proof")
    if state.get("stance_id") != stance_id:
        raise RealNestedCodexDebateWorkerError("worker_local_causal_state.stance_id mismatch")
    if not state.get("route_priority") or not state.get("expand_priority"):
        raise RealNestedCodexDebateWorkerError("worker_local_causal_state must include route_priority and expand_priority")


def expected_workers_from_creation_requests(requests: list[DebateWorkerCreationRequest]) -> list[dict[str, Any]]:
    result = []
    for request in requests:
        result.append(
            {
                "worker_id": request.worker_id,
                "agent_id": request.agent_id,
                "stance_id": request.stance_id,
                "role_id": request.role_id,
                "model": request.model,
                "reasoning_budget": request.reasoning_budget,
                "proof_path": request.metadata.get("proof_path"),
            }
        )
    return result
