from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from aegis_router import Router
from aegis_router.errors import InvalidRequestError, NotFoundError, PermissionDeniedError
from aegis_router.server import AegisRouterMcpServer


def record(results: list[dict[str, Any]], name: str, passed: bool, detail: Any) -> None:
    results.append({"name": name, "passed": passed, "detail": detail})


def run_acceptance() -> dict[str, Any]:
    results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state.json"
        router = Router(state_path)
        router.create_domain("master_domain", owner_agent_id="master")
        router.create_domain("isolated_domain", owner_agent_id="isolated_master")
        router.register_agent("master", "master_domain", "master")
        router.register_agent("agent_alpha", "master_domain", "worker", parent_id="master")
        router.register_agent("agent_beta", "master_domain", "worker", parent_id="master")
        router.register_agent("agent_gamma", "master_domain", "worker", parent_id="master")
        router.register_agent("isolated_agent", "isolated_domain", "worker")

        msg = router.send_message(
            "agent_alpha",
            "agent_beta",
            "handoff",
            {"content": "positive"},
            task_id="ACCEPT-POS",
        )
        received = router.receive_messages("agent_beta")
        acked = router.ack_message("agent_beta", msg["message_id"])
        persisted = next(
            m for m in router.domain_snapshot("master_domain")["messages"] if m["message_id"] == msg["message_id"]
        )
        record(
            results,
            "positive same-domain route with ack",
            persisted["status"] == "acked" and received[0]["status"] == "delivered" and acked["status"] == "acked",
            {"message_id": msg["message_id"], "persisted_status": persisted["status"]},
        )

        try:
            router.send_message("agent_alpha", "isolated_agent", "probe", {}, task_id="ACCEPT-XDOMAIN")
            record(results, "cross-domain send rejected", False, "send unexpectedly succeeded")
        except PermissionDeniedError as exc:
            record(results, "cross-domain send rejected", True, str(exc))

        try:
            router.send_message("ghost", "agent_beta", "probe", {}, task_id="ACCEPT-GHOST-SEND")
            record(results, "unregistered send rejected", False, "send unexpectedly succeeded")
        except NotFoundError as exc:
            record(results, "unregistered send rejected", True, str(exc))

        try:
            router.receive_messages("ghost")
            record(results, "unregistered receive rejected", False, "receive unexpectedly succeeded")
        except NotFoundError as exc:
            record(results, "unregistered receive rejected", True, str(exc))

        router.deactivate_agent("agent_gamma")
        try:
            router.send_message("agent_gamma", "agent_alpha", "probe", {}, task_id="ACCEPT-INACTIVE")
            record(results, "inactive send rejected", False, "send unexpectedly succeeded")
        except PermissionDeniedError as exc:
            record(results, "inactive send rejected", True, str(exc))

        wrong_ack_msg = router.send_message("agent_alpha", "agent_beta", "probe", {}, task_id="ACCEPT-WRONG-ACK")
        try:
            router.ack_message("agent_alpha", wrong_ack_msg["message_id"])
            record(results, "non-target ack rejected", False, "ack unexpectedly succeeded")
        except PermissionDeniedError as exc:
            record(results, "non-target ack rejected", True, str(exc))
        router.ack_message("agent_beta", wrong_ack_msg["message_id"])

        try:
            router.register_agent("cross_parent_child", "master_domain", "worker", parent_id="isolated_agent")
            record(results, "cross-domain parent registration rejected", False, "registration unexpectedly succeeded")
        except PermissionDeniedError as exc:
            record(results, "cross-domain parent registration rejected", True, str(exc))

        no_ack = router.send_message(
            "agent_alpha",
            "agent_beta",
            "notify",
            {"content": "no ack"},
            task_id="ACCEPT-NOACK",
            requires_ack=False,
        )
        no_ack_received = router.receive_messages("agent_beta")
        no_ack_persisted = next(
            m for m in router.domain_snapshot("master_domain")["messages"] if m["message_id"] == no_ack["message_id"]
        )
        second_default = router.receive_messages("agent_beta")
        second_delivered = router.receive_messages("agent_beta", include_delivered=True)
        try:
            router.ack_message("agent_beta", no_ack["message_id"])
            no_ack_ack_rejected = False
            no_ack_ack_error = "ack unexpectedly succeeded"
        except InvalidRequestError as exc:
            no_ack_ack_rejected = True
            no_ack_ack_error = str(exc)
        record(
            results,
            "no-ack message reaches terminal completed state",
            no_ack_received[0]["status"] == "completed"
            and no_ack_persisted["status"] == "completed"
            and second_default == []
            and second_delivered == []
            and no_ack_ack_rejected,
            {
                "message_id": no_ack["message_id"],
                "received_status": no_ack_received[0]["status"],
                "persisted_status": no_ack_persisted["status"],
                "ack_error": no_ack_ack_error,
            },
        )

        try:
            router.heartbeat("agent_gamma")
            record(results, "heartbeat does not reactivate inactive agent", False, "heartbeat unexpectedly succeeded")
        except PermissionDeniedError as exc:
            record(results, "heartbeat does not reactivate inactive agent", True, str(exc))

        unregistered = router.unregister_agent("agent_gamma")
        try:
            router.heartbeat("agent_gamma")
            record(results, "heartbeat rejects unregistered agent", False, "heartbeat unexpectedly succeeded")
        except NotFoundError as exc:
            record(
                results,
                "heartbeat rejects unregistered agent",
                True,
                {"unregister_status": unregistered["status"], "heartbeat_error": str(exc)},
            )

        server = AegisRouterMcpServer(Router(Path(tmp) / "mcp_state.json"))
        bad_resp = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "register_agent", "arguments": {"agent_id": "a", "domain_id": "d"}},
            }
        )
        error = bad_resp.get("error", {}) if bad_resp else {}
        record(
            results,
            "malformed MCP call returns controlled InvalidRequestError",
            error.get("code") == -32000 and error.get("data", {}).get("type") == "InvalidRequestError",
            error,
        )

    failed = [item for item in results if not item["passed"]]
    return {"passed": len(results) - len(failed), "failed": len(failed), "results": results}


def main() -> None:
    summary = run_acceptance()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    if summary["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
