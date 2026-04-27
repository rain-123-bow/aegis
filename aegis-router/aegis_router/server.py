from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

from .core import Router
from .errors import ConflictError, InvalidRequestError, NotFoundError, PermissionDeniedError, RouterError

ToolHandler = Callable[[dict[str, Any]], Any]


def _tool_schema(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": True,
        },
    }


class AegisRouterMcpServer:
    """A very small JSON-RPC/MCP-style stdio server.

    It implements the methods needed by common MCP clients:
    - initialize
    - tools/list
    - tools/call

    Messages are newline-delimited JSON-RPC objects.
    """

    def __init__(self, router: Router):
        self.router = router
        self.handlers: dict[str, ToolHandler] = {
            "create_domain": self._create_domain,
            "register_agent": self._register_agent,
            "deactivate_agent": self._deactivate_agent,
            "unregister_agent": self._unregister_agent,
            "heartbeat": self._heartbeat,
            "list_visible_agents": self._list_visible_agents,
            "send_message": self._send_message,
            "receive_messages": self._receive_messages,
            "ack_message": self._ack_message,
            "domain_snapshot": self._domain_snapshot,
        }

    def tools(self) -> list[dict[str, Any]]:
        return [
            _tool_schema(
                "create_domain",
                "Create a local routing domain owned by a hub.",
                {
                    "domain_id": {"type": "string"},
                    "owner_agent_id": {"type": "string"},
                    "parent_domain_id": {"type": "string"},
                    "metadata": {"type": "object"},
                },
                ["domain_id"],
            ),
            _tool_schema(
                "register_agent",
                "Register an agent into a routing domain.",
                {
                    "agent_id": {"type": "string"},
                    "domain_id": {"type": "string"},
                    "role": {"type": "string"},
                    "parent_id": {"type": "string"},
                    "capabilities": {"type": "array", "items": {"type": "string"}},
                    "metadata": {"type": "object"},
                },
                ["agent_id", "domain_id", "role"],
            ),
            _tool_schema(
                "deactivate_agent",
                "Temporarily mark an agent inactive. Heartbeat does not reactivate inactive agents.",
                {"agent_id": {"type": "string"}},
                ["agent_id"],
            ),
            _tool_schema(
                "unregister_agent",
                "Permanently remove an agent from the registry.",
                {"agent_id": {"type": "string"}},
                ["agent_id"],
            ),
            _tool_schema(
                "heartbeat",
                "Update agent heartbeat timestamp.",
                {"agent_id": {"type": "string"}},
                ["agent_id"],
            ),
            _tool_schema(
                "list_visible_agents",
                "List agents visible to an agent under router policy.",
                {"agent_id": {"type": "string"}},
                ["agent_id"],
            ),
            _tool_schema(
                "send_message",
                "Send a message to a target agent in the same routing domain.",
                {
                    "from_id": {"type": "string"},
                    "to_id": {"type": "string"},
                    "message_type": {"type": "string"},
                    "payload": {"type": "object"},
                    "task_id": {"type": "string"},
                    "priority": {"type": "string"},
                    "requires_ack": {"type": "boolean"},
                },
                ["from_id", "to_id", "message_type", "payload"],
            ),
            _tool_schema(
                "receive_messages",
                "Receive pending messages for an agent.",
                {
                    "agent_id": {"type": "string"},
                    "include_delivered": {"type": "boolean"},
                },
                ["agent_id"],
            ),
            _tool_schema(
                "ack_message",
                "Acknowledge a delivered message.",
                {"agent_id": {"type": "string"}, "message_id": {"type": "string"}},
                ["agent_id", "message_id"],
            ),
            _tool_schema(
                "domain_snapshot",
                "Return a domain snapshot for its owner or diagnostics.",
                {"domain_id": {"type": "string"}},
                ["domain_id"],
            ),
        ]

    def _create_domain(self, args: dict[str, Any]) -> Any:
        return self.router.create_domain(
            domain_id=args["domain_id"],
            owner_agent_id=args.get("owner_agent_id"),
            parent_domain_id=args.get("parent_domain_id"),
            metadata=args.get("metadata") or {},
        )

    def _register_agent(self, args: dict[str, Any]) -> Any:
        return self.router.register_agent(
            agent_id=args["agent_id"],
            domain_id=args["domain_id"],
            role=args["role"],
            parent_id=args.get("parent_id"),
            capabilities=args.get("capabilities") or [],
            metadata=args.get("metadata") or {},
        )

    def _deactivate_agent(self, args: dict[str, Any]) -> Any:
        return self.router.deactivate_agent(args["agent_id"])

    def _unregister_agent(self, args: dict[str, Any]) -> Any:
        return self.router.unregister_agent(args["agent_id"])

    def _heartbeat(self, args: dict[str, Any]) -> Any:
        return self.router.heartbeat(args["agent_id"])

    def _list_visible_agents(self, args: dict[str, Any]) -> Any:
        return self.router.list_visible_agents(args["agent_id"])

    def _send_message(self, args: dict[str, Any]) -> Any:
        return self.router.send_message(
            from_id=args["from_id"],
            to_id=args["to_id"],
            message_type=args["message_type"],
            payload=args["payload"],
            task_id=args.get("task_id"),
            priority=args.get("priority", "normal"),
            requires_ack=bool(args.get("requires_ack", True)),
        )

    def _receive_messages(self, args: dict[str, Any]) -> Any:
        return self.router.receive_messages(
            agent_id=args["agent_id"],
            include_delivered=bool(args.get("include_delivered", False)),
        )

    def _ack_message(self, args: dict[str, Any]) -> Any:
        return self.router.ack_message(args["agent_id"], args["message_id"])

    def _domain_snapshot(self, args: dict[str, Any]) -> Any:
        return self.router.domain_snapshot(args["domain_id"])

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params") or {}

        # notifications do not need responses
        if method == "notifications/initialized":
            return None

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                    "serverInfo": {"name": "aegis-router", "version": "0.1.0"},
                    "capabilities": {"tools": {}},
                }
                return {"jsonrpc": "2.0", "id": msg_id, "result": result}

            if method == "tools/list":
                return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": self.tools()}}

            if method == "tools/call":
                name = params.get("name")
                args = params.get("arguments") or {}
                if name not in self.handlers:
                    raise InvalidRequestError(f"unknown tool: {name}")
                self._validate_tool_arguments(name, args)
                value = self.handlers[name](args)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
                            }
                        ]
                    },
                }

            raise InvalidRequestError(f"unknown method: {method}")

        except (InvalidRequestError, NotFoundError, ConflictError, PermissionDeniedError) as exc:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32000, "message": str(exc), "data": {"type": exc.__class__.__name__}},
            }
        except RouterError as exc:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32001, "message": str(exc), "data": {"type": exc.__class__.__name__}},
            }
        except Exception as exc:  # defensive server boundary
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32603, "message": str(exc), "data": {"type": exc.__class__.__name__}},
            }

    def serve_stdio(self) -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
                print(json.dumps(response, ensure_ascii=False), flush=True)
                continue
            response = self.handle(message)
            if response is not None:
                print(json.dumps(response, ensure_ascii=False), flush=True)

    def _validate_tool_arguments(self, name: str, args: Any) -> None:
        if not isinstance(args, dict):
            raise InvalidRequestError("tool arguments must be an object")
        required_by_tool = {tool["name"]: tool["inputSchema"].get("required", []) for tool in self.tools()}
        missing = [key for key in required_by_tool.get(name, []) if key not in args]
        if missing:
            joined = ", ".join(missing)
            raise InvalidRequestError(f"missing required argument(s) for {name}: {joined}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Aegis Router MCP-style stdio server.")
    parser.add_argument("--store", default=".aegis-router/state.json", help="Path to JSON router state store.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    server = AegisRouterMcpServer(Router(Path(args.store)))
    server.serve_stdio()


if __name__ == "__main__":
    main()
