from __future__ import annotations

from aegis_router.core import Router
from aegis_router.server import AegisRouterMcpServer


def call(server: AegisRouterMcpServer, name: str, arguments: dict):
    return server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}})


def test_mcp_tool_list(tmp_path):
    server = AegisRouterMcpServer(Router(tmp_path / "state.json"))
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert response is not None
    assert "tools" in response["result"]
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert "register_agent" in names
    assert "deactivate_agent" in names
    assert "send_message" in names


def test_mcp_call_create_and_register(tmp_path):
    server = AegisRouterMcpServer(Router(tmp_path / "state.json"))
    response = call(server, "create_domain", {"domain_id": "d"})
    assert response is not None
    assert "error" not in response

    response = call(server, "register_agent", {"agent_id": "a", "domain_id": "d", "role": "master"})
    assert response is not None
    assert "error" not in response


def test_mcp_missing_required_argument_is_invalid_request(tmp_path):
    server = AegisRouterMcpServer(Router(tmp_path / "state.json"))
    response = call(server, "register_agent", {"agent_id": "a", "domain_id": "d"})
    assert response is not None
    assert response["error"]["code"] == -32000
    assert response["error"]["data"]["type"] == "InvalidRequestError"
    assert "missing required argument" in response["error"]["message"]
