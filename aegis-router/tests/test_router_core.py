from __future__ import annotations

import pytest

from aegis_router import Router
from aegis_router.errors import ConflictError, NotFoundError, PermissionDeniedError


def test_register_send_receive_ack(tmp_path):
    router = Router(tmp_path / "state.json")
    router.create_domain("master_domain", owner_agent_id="master")
    router.register_agent("master", "master_domain", "master")
    router.register_agent("dept_001", "master_domain", "department_leader", parent_id="master")
    router.register_agent("dept_002", "master_domain", "department_leader", parent_id="master")

    visible = router.list_visible_agents("dept_001")
    assert {a["agent_id"] for a in visible} == {"master", "dept_001", "dept_002"}

    msg = router.send_message(
        from_id="dept_001",
        to_id="dept_002",
        message_type="request",
        payload={"hello": "world"},
        task_id="T0001",
    )
    assert msg["status"] == "pending"

    messages = router.receive_messages("dept_002")
    assert len(messages) == 1
    assert messages[0]["payload"] == {"hello": "world"}

    acked = router.ack_message("dept_002", msg["message_id"])
    assert acked["status"] == "acked"


def test_duplicate_agent_rejected(tmp_path):
    router = Router(tmp_path / "state.json")
    router.create_domain("d")
    router.register_agent("a", "d", "role")
    with pytest.raises(ConflictError):
        router.register_agent("a", "d", "role")


def test_cross_domain_message_rejected(tmp_path):
    router = Router(tmp_path / "state.json")
    router.create_domain("d1")
    router.create_domain("d2")
    router.register_agent("a1", "d1", "role")
    router.register_agent("a2", "d2", "role")
    with pytest.raises(PermissionDeniedError):
        router.send_message("a1", "a2", "request", {"x": 1})


def test_only_target_can_ack(tmp_path):
    router = Router(tmp_path / "state.json")
    router.create_domain("d")
    router.register_agent("a1", "d", "role")
    router.register_agent("a2", "d", "role")
    msg = router.send_message("a1", "a2", "request", {})
    with pytest.raises(PermissionDeniedError):
        router.ack_message("a1", msg["message_id"])


def test_cross_domain_parent_rejected(tmp_path):
    router = Router(tmp_path / "state.json")
    router.create_domain("d1")
    router.create_domain("d2")
    router.register_agent("parent", "d1", "role")
    with pytest.raises(PermissionDeniedError):
        router.register_agent("child", "d2", "role", parent_id="parent")


def test_no_ack_message_completes_on_receive(tmp_path):
    router = Router(tmp_path / "state.json")
    router.create_domain("d")
    router.register_agent("a1", "d", "role")
    router.register_agent("a2", "d", "role")
    msg = router.send_message("a1", "a2", "notify", {}, requires_ack=False)
    assert msg["status"] == "pending"

    messages = router.receive_messages("a2")
    assert len(messages) == 1
    assert messages[0]["status"] == "completed"
    assert router.receive_messages("a2") == []
    assert router.receive_messages("a2", include_delivered=True) == []


def test_deactivate_and_unregister_contract(tmp_path):
    router = Router(tmp_path / "state.json")
    router.create_domain("d")
    router.register_agent("a1", "d", "role")
    router.register_agent("a2", "d", "role")

    deactivated = router.deactivate_agent("a1")
    assert deactivated["status"] == "inactive"
    with pytest.raises(PermissionDeniedError):
        router.send_message("a1", "a2", "request", {})
    with pytest.raises(PermissionDeniedError):
        router.heartbeat("a1")

    unregistered = router.unregister_agent("a1")
    assert unregistered["status"] == "unregistered"
    with pytest.raises(NotFoundError):
        router.heartbeat("a1")
