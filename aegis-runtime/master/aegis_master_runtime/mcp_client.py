from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from .models import (
    MasterRuntimeContractError,
    NestedCodexCreateRequest,
    NestedCodexCreateResponse,
)


class NestedCodexClientProtocol:
    def create_agent(self, request: NestedCodexCreateRequest) -> NestedCodexCreateResponse:
        raise NotImplementedError


class NestedCodexMcpClient(NestedCodexClientProtocol):
    """Minimal stdio MCP client for real nested-codex create-agent validation."""

    def __init__(self, command: str, tool_name: str, timeout_seconds: float = 90.0):
        if not command:
            raise MasterRuntimeContractError("mcp command is required")
        if not tool_name:
            raise MasterRuntimeContractError("mcp tool name is required")
        self.command = command
        self.tool_name = tool_name
        self.timeout_seconds = timeout_seconds
        self._next_id = 1
        self._proc: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> "NestedCodexMcpClient":
        args = shlex.split(self.command)
        self._proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "aegis-master-runtime", "version": "0.1.0"},
            },
        )
        self._notify("notifications/initialized", {})
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

    def create_agent(self, request: NestedCodexCreateRequest) -> NestedCodexCreateResponse:
        result = self._request(
            "tools/call",
            {
                "name": self.tool_name,
                "arguments": request.to_dict(),
            },
        )
        payload = self._normalize_tool_result(result)
        response = NestedCodexCreateResponse.from_mapping(payload)
        response.assert_matches(request)
        return response

    def _normalize_tool_result(self, result: dict[str, Any]) -> dict[str, Any]:
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

        if isinstance(result, dict) and {"agent_id", "role_id"} <= set(result):
            return result

        raise MasterRuntimeContractError(f"nested-codex MCP result did not contain structured agent data: {result!r}")

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        proc = self._require_proc()
        msg_id = self._next_id
        self._next_id += 1
        self._write_message({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
        while True:
            msg = self._read_message()
            if msg.get("id") != msg_id:
                # Ignore server notifications during startup/tool call.
                continue
            if "error" in msg:
                raise MasterRuntimeContractError(f"MCP error for {method}: {msg['error']}")
            result = msg.get("result")
            if not isinstance(result, dict):
                raise MasterRuntimeContractError(f"MCP result for {method} must be an object")
            return result

    def _notify(self, method: str, params: dict[str, Any]) -> None:
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
                    try:
                        stderr = proc.stderr.read() or b""
                    except Exception:
                        stderr = b""
                raise MasterRuntimeContractError(f"MCP server closed stdout before response. stderr={stderr!r}")
            headers.extend(byte)
        header_text = headers.decode("ascii", errors="replace")
        length = None
        for line in header_text.split("\r\n"):
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
                break
        if length is None:
            raise MasterRuntimeContractError(f"MCP response missing Content-Length header: {header_text!r}")
        body = proc.stdout.read(length)
        if len(body) != length:
            raise MasterRuntimeContractError("MCP response body ended early")
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise MasterRuntimeContractError("MCP response must be a JSON object")
        return payload

    def _require_proc(self) -> subprocess.Popen[bytes]:
        if self._proc is None:
            raise MasterRuntimeContractError("MCP client is not started")
        return self._proc


class RecordingNestedCodexClient(NestedCodexClientProtocol):
    """In-memory client for unit tests only. Not valid for real validation."""

    def __init__(self):
        self.requests: list[NestedCodexCreateRequest] = []

    def create_agent(self, request: NestedCodexCreateRequest) -> NestedCodexCreateResponse:
        self.requests.append(request)
        response = NestedCodexCreateResponse(
            agent_id=request.agent_id,
            role_id=request.role_id,
            status="created",
            resolved_model=request.model,
            resolved_reasoning_budget=request.reasoning_budget,
            raw_response={"test_only": True},
        )
        response.assert_matches(request)
        return response
