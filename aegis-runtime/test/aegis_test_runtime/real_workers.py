from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class RealTestWorkerError(RuntimeError):
    """Raised when Phase 20B real Test Worker validation fails."""


@dataclass(frozen=True)
class TestWorkerPolicyProfile:
    role_id: str
    model: str
    reasoning_budget: str
    fallback_allowed: bool
    dynamic_adjustment_allowed: bool

    def assert_strict_high(self) -> None:
        if self.role_id != "test_worker":
            raise RealTestWorkerError(f"test_worker profile has wrong role_id: {self.role_id}")
        if self.model != "gpt-5.5":
            raise RealTestWorkerError(f"test_worker model must be gpt-5.5, got {self.model}")
        if self.reasoning_budget != "high":
            raise RealTestWorkerError(f"test_worker reasoning_budget must be high, got {self.reasoning_budget}")
        if self.fallback_allowed:
            raise RealTestWorkerError("test_worker fallback must be forbidden")
        if self.dynamic_adjustment_allowed:
            raise RealTestWorkerError("test_worker dynamic adjustment must be forbidden")


@dataclass(frozen=True)
class TestWorkerCreationRequest:
    agent_id: str
    role_id: str
    display_name: str
    model: str
    reasoning_budget: str
    parent_agent_id: str
    scope: str
    run_id: str
    route_id: str
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
            "route_id": self.route_id,
            "instructions": self.instructions,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class TestWorkerCreationResponse:
    agent_id: str
    role_id: str
    status: str
    resolved_model: str
    resolved_reasoning_budget: str
    raw_response: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "TestWorkerCreationResponse":
        return cls(
            agent_id=str(value.get("agent_id", "")),
            role_id=str(value.get("role_id", "")),
            status=str(value.get("status", "")),
            resolved_model=str(value.get("resolved_model", value.get("model", ""))),
            resolved_reasoning_budget=str(value.get("resolved_reasoning_budget", value.get("reasoning_budget", ""))),
            raw_response=dict(value),
        )

    def assert_matches(self, request: TestWorkerCreationRequest) -> None:
        if self.agent_id != request.agent_id:
            raise RealTestWorkerError(f"agent_id mismatch: {self.agent_id} != {request.agent_id}")
        if self.role_id != request.role_id:
            raise RealTestWorkerError(f"role_id mismatch: {self.role_id} != {request.role_id}")
        if self.resolved_model != request.model:
            raise RealTestWorkerError(f"resolved_model mismatch: {self.resolved_model} != {request.model}")
        if self.resolved_reasoning_budget != request.reasoning_budget:
            raise RealTestWorkerError(
                f"resolved_reasoning_budget mismatch: {self.resolved_reasoning_budget} != {request.reasoning_budget}"
            )
        if self.status not in {"created", "active", "ready"}:
            raise RealTestWorkerError(f"invalid creation status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role_id": self.role_id,
            "status": self.status,
            "resolved_model": self.resolved_model,
            "resolved_reasoning_budget": self.resolved_reasoning_budget,
            "raw_response": dict(self.raw_response),
        }


def load_test_worker_policy(policy_path: str | Path) -> TestWorkerPolicyProfile:
    text = Path(policy_path).read_text(encoding="utf-8")
    profile_fields: dict[str, str] = {}
    in_profile = False
    for raw in text.splitlines():
        if raw.startswith("  test_worker:"):
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

    missing = [
        key
        for key in ("role_id", "model", "reasoning_budget", "fallback_allowed", "dynamic_adjustment_allowed")
        if key not in profile_fields
    ]
    if missing:
        raise RealTestWorkerError(f"test_worker profile missing field(s): {', '.join(missing)}")
    profile = TestWorkerPolicyProfile(
        role_id=profile_fields["role_id"],
        model=profile_fields["model"],
        reasoning_budget=profile_fields["reasoning_budget"],
        fallback_allowed=_parse_bool(profile_fields["fallback_allowed"]),
        dynamic_adjustment_allowed=_parse_bool(profile_fields["dynamic_adjustment_allowed"]),
    )
    profile.assert_strict_high()
    if "  - test_worker" in text:
        raise RealTestWorkerError("test_worker must not remain in deferred_profiles")
    return profile


def build_test_worker_creation_requests(
    *,
    policy_path: str | Path,
    validation_package: dict[str, Any],
    run_id: str,
    proof_dir: str | Path,
    output_dir: str | Path,
) -> list[TestWorkerCreationRequest]:
    profile = load_test_worker_policy(policy_path)
    routes = _extract_routes(validation_package)
    proof_root = Path(proof_dir)
    output_root = Path(output_dir)
    requests: list[TestWorkerCreationRequest] = []
    for route in routes:
        route_id = str(route["route_id"])
        agent_id = f"test_worker__{_safe_id(run_id)}__{_safe_id(route_id)}"
        proof_path = proof_root / f"{agent_id}_proof.json"
        output_path = output_root / f"{agent_id}_output.json"
        instructions = _worker_instructions(
            agent_id=agent_id,
            run_id=run_id,
            route=route,
            proof_path=proof_path,
            output_path=output_path,
            validation_package=validation_package,
        )
        requests.append(
            TestWorkerCreationRequest(
                agent_id=agent_id,
                role_id="test_worker",
                display_name=f"Test Worker {route_id}",
                model=profile.model,
                reasoning_budget=profile.reasoning_budget,
                parent_agent_id="test_leader",
                scope="test_route_local_domain",
                run_id=run_id,
                route_id=route_id,
                instructions=instructions,
                metadata={
                    "policy_role_id": profile.role_id,
                    "policy_model": profile.model,
                    "policy_reasoning_budget": profile.reasoning_budget,
                    "fallback_allowed": False,
                    "dynamic_adjustment_allowed": False,
                    "proof_path": str(proof_path),
                    "output_path": str(output_path),
                    "route_id": route_id,
                },
            )
        )
    return requests


def expected_workers_from_creation_requests(requests: list[TestWorkerCreationRequest]) -> list[dict[str, Any]]:
    return [
        {
            "agent_id": request.agent_id,
            "role_id": request.role_id,
            "route_id": request.route_id,
            "policy_model": request.model,
            "policy_reasoning_budget": request.reasoning_budget,
            "proof_path": request.metadata["proof_path"],
            "output_path": request.metadata["output_path"],
        }
        for request in requests
    ]


def audit_test_worker_proofs(*, proof_dir: str | Path, expected_workers: list[dict[str, Any]]) -> dict[str, Any]:
    proof_root = Path(proof_dir).resolve()
    if not proof_root.is_dir():
        raise RealTestWorkerError(f"proof directory does not exist: {proof_root}")
    if not expected_workers:
        raise RealTestWorkerError("expected_workers must not be empty")
    audited: list[dict[str, Any]] = []
    for expected in expected_workers:
        proof_path = _resolve_expected_path(expected, root=proof_root, key="proof_path", suffix="_proof.json")
        proof = _read_json_object(proof_path)
        _assert_worker_proof(proof=proof, expected=expected)
        audited.append({
            "agent_id": expected["agent_id"],
            "role_id": expected["role_id"],
            "route_id": expected["route_id"],
            "proof_path": str(proof_path),
            "sha256": _sha256_file(proof_path),
        })
    return {"status": "passed", "audited_count": len(audited), "workers": audited}


def audit_test_worker_outputs(*, output_dir: str | Path, expected_workers: list[dict[str, Any]]) -> dict[str, Any]:
    output_root = Path(output_dir).resolve()
    if not output_root.is_dir():
        raise RealTestWorkerError(f"output directory does not exist: {output_root}")
    if not expected_workers:
        raise RealTestWorkerError("expected_workers must not be empty")
    audited: list[dict[str, Any]] = []
    for expected in expected_workers:
        output_path = _resolve_expected_path(expected, root=output_root, key="output_path", suffix="_output.json")
        payload = _read_json_object(output_path)
        _assert_worker_output(payload=payload, expected=expected)
        audited.append({
            "agent_id": expected["agent_id"],
            "role_id": expected["role_id"],
            "route_id": expected["route_id"],
            "output_path": str(output_path),
            "sha256": _sha256_file(output_path),
        })
    return {"status": "passed", "audited_count": len(audited), "workers": audited}


def create_test_workers_via_mcp(
    *,
    requests: list[TestWorkerCreationRequest],
    mcp_command: str,
    mcp_tool: str,
    timeout_seconds: float = 90.0,
) -> list[TestWorkerCreationResponse]:
    responses: list[TestWorkerCreationResponse] = []
    with StdioMcpClient(mcp_command, timeout_seconds=timeout_seconds) as client:
        for request in requests:
            result = client.request("tools/call", {"name": mcp_tool, "arguments": request.to_dict()})
            payload = _normalize_tool_result(result)
            response = TestWorkerCreationResponse.from_mapping(payload)
            response.assert_matches(request)
            responses.append(response)
    return responses


def _extract_routes(validation_package: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(validation_package.get("test_routes"), list):
        routes = [dict(item) for item in validation_package["test_routes"]]
    elif isinstance(validation_package.get("routes"), list):
        routes = [dict(item) for item in validation_package["routes"]]
    else:
        changed_files = validation_package.get("changed_files") or validation_package.get("expected_changed_files") or []
        if not isinstance(changed_files, list) or not changed_files:
            raise RealTestWorkerError("validation package requires test_routes, routes, or changed_files")
        routes = [
            {
                "route_id": "route.sandbox_pytest",
                "route_type": "command",
                "mandatory": True,
                "scope": list(changed_files),
                "method": "local_pytest",
                "commands": ["pytest"],
                "expected_result": "passed",
            }
        ]
    for route in routes:
        if not isinstance(route.get("route_id"), str) or not route["route_id"]:
            raise RealTestWorkerError("each route requires route_id")
    return routes


def _worker_instructions(
    *,
    agent_id: str,
    run_id: str,
    route: dict[str, Any],
    proof_path: Path,
    output_path: Path,
    validation_package: dict[str, Any],
) -> str:
    return (
        "You are a request-scoped Aegis Test Department internal Test Worker. "
        "You were created by the Test Leader, not by Master. "
        "You are bound to exactly one validation route. "
        "Do not modify implementation code, push, open PRs, merge remote branches, release, deploy, or claim global causal truth. "
        "Write your proof JSON before substantive work.\n\n"
        f"agent_id: {agent_id}\n"
        f"run_id: {run_id}\n"
        f"route_id: {route['route_id']}\n"
        f"proof_path: {proof_path}\n"
        f"output_path: {output_path}\n"
        f"route: {json.dumps(route, ensure_ascii=False)}\n"
        f"validation_package_summary: {json.dumps(_package_summary(validation_package), ensure_ascii=False)}\n\n"
        "The proof JSON must include: agent_id, role_id, created_by, creation_mechanism, requested_model, policy_model, "
        "requested_reasoning_effort, policy_reasoning_budget, topology_scope, run_id, route_id, created_at_utc, proof_statement.\n\n"
        "The output JSON must include: agent_id, role_id, run_id, route_id, route_result, command_evidence, observations, "
        "evidence_refs, test_data_refs, covered_scope, uncovered_scope, owner_hint, status, and causal_status. "
        "status must be test_worker_report_candidate; causal_status must be scoped_evidence_candidate."
    )


def _assert_worker_proof(*, proof: dict[str, Any], expected: dict[str, Any]) -> None:
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
        "route_id",
        "proof_statement",
    ]
    missing = [key for key in required if not proof.get(key)]
    if missing:
        raise RealTestWorkerError(f"proof missing required field(s): {', '.join(missing)}")
    if proof["agent_id"] != expected["agent_id"]:
        raise RealTestWorkerError("proof agent_id mismatch")
    if proof["role_id"] != "test_worker" or expected["role_id"] != "test_worker":
        raise RealTestWorkerError("proof role_id must be test_worker")
    if proof["route_id"] != expected["route_id"]:
        raise RealTestWorkerError("proof route_id mismatch")
    if proof["created_by"] != "test_leader":
        raise RealTestWorkerError("proof created_by must be test_leader")
    mechanism = str(proof["creation_mechanism"])
    if "nested-codex" not in mechanism and "mcp__nested_codex__.codex" not in mechanism and "Codex" not in mechanism:
        raise RealTestWorkerError("proof creation_mechanism must record real nested-Codex/Codex creation")
    if proof["requested_model"] != "gpt-5.5" or proof["policy_model"] != "gpt-5.5":
        raise RealTestWorkerError("proof model must be gpt-5.5")
    if proof["requested_reasoning_effort"] != "high" or proof["policy_reasoning_budget"] != "high":
        raise RealTestWorkerError("proof reasoning budget must be high")
    if proof["topology_scope"] != "test_route_local_domain":
        raise RealTestWorkerError("proof topology_scope must be test_route_local_domain")
    timestamp = proof.get("created_at_utc") or proof.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise RealTestWorkerError("proof requires created_at_utc or timestamp")


def _assert_worker_output(*, payload: dict[str, Any], expected: dict[str, Any]) -> None:
    for key in ("agent_id", "role_id", "route_id"):
        if payload.get(key) != expected[key]:
            raise RealTestWorkerError(f"output {key} mismatch")
    required = [
        "run_id",
        "route_result",
        "command_evidence",
        "observations",
        "evidence_refs",
        "test_data_refs",
        "covered_scope",
        "uncovered_scope",
        "owner_hint",
        "status",
        "causal_status",
    ]
    missing = [key for key in required if key not in payload]
    if missing:
        raise RealTestWorkerError(f"test worker output missing field(s): {', '.join(missing)}")
    if payload["route_result"] not in {"passed", "failed", "inconclusive", "blocked"}:
        raise RealTestWorkerError("route_result is invalid")
    if payload["status"] != "test_worker_report_candidate":
        raise RealTestWorkerError("test worker output status must be test_worker_report_candidate")
    if payload["causal_status"] != "scoped_evidence_candidate":
        raise RealTestWorkerError("test worker causal_status must be scoped_evidence_candidate")
    for key in ("command_evidence", "observations", "evidence_refs", "test_data_refs", "covered_scope", "uncovered_scope"):
        if not isinstance(payload[key], list):
            raise RealTestWorkerError(f"{key} must be a list")
    if not isinstance(payload["owner_hint"], dict) or payload["owner_hint"].get("owner_type") not in {"group", "integration", "ambiguous", "none"}:
        raise RealTestWorkerError("owner_hint.owner_type is invalid")


def _parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    raise RealTestWorkerError(f"expected boolean, got {value!r}")


def _package_summary(package: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": package.get("run_id"),
        "status": package.get("status"),
        "test_result": package.get("test_result"),
        "target_repo": package.get("target_repo"),
        "integration_branch": package.get("integration_branch"),
        "integration_commit": package.get("integration_commit"),
    }


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


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RealTestWorkerError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RealTestWorkerError(f"invalid JSON file: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RealTestWorkerError(f"JSON file must contain an object: {path}")
    return payload


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
    raise RealTestWorkerError(f"MCP result did not contain structured worker data: {result!r}")


class StdioMcpClient:
    """Minimal stdio JSON-RPC MCP client for standardized create-agent tools."""

    def __init__(self, command: str, timeout_seconds: float = 90.0):
        if not command:
            raise RealTestWorkerError("mcp command is required")
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
                "clientInfo": {"name": "aegis-test-real-workers", "version": "0.1.0"},
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
                raise RealTestWorkerError(f"MCP error for {method}: {msg['error']}")
            result = msg.get("result")
            if not isinstance(result, dict):
                raise RealTestWorkerError(f"MCP result for {method} must be an object")
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
                raise RealTestWorkerError(f"MCP server closed stdout before response. stderr={stderr!r}")
            headers.extend(byte)
        header_text = headers.decode("ascii", errors="replace")
        length = None
        for line in header_text.split("\r\n"):
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
                break
        if length is None:
            raise RealTestWorkerError(f"MCP response missing Content-Length header: {header_text!r}")
        body = proc.stdout.read(length)
        if len(body) != length:
            raise RealTestWorkerError("MCP response body ended early")
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise RealTestWorkerError("MCP response must be a JSON object")
        return payload

    def _require_proc(self) -> subprocess.Popen[bytes]:
        if self._proc is None:
            raise RealTestWorkerError("MCP client is not started")
        return self._proc
