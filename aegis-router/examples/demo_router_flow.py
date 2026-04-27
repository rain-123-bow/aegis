from __future__ import annotations

import json
import tempfile
from pathlib import Path

from aegis_router import Router


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        router = Router(Path(tmp) / "state.json")
        router.create_domain("master_domain", owner_agent_id="master")
        router.register_agent("master", "master_domain", "master")
        router.register_agent("dept_001_leader", "master_domain", "department_leader", parent_id="master")
        router.register_agent("dept_002_leader", "master_domain", "department_leader", parent_id="master")
        msg = router.send_message(
            from_id="dept_001_leader",
            to_id="dept_002_leader",
            message_type="handoff",
            task_id="T0001",
            payload={"summary": "request admitted", "next": "plan task"},
        )
        received = router.receive_messages("dept_002_leader")
        router.ack_message("dept_002_leader", msg["message_id"])
        print(json.dumps({"sent": msg, "received": received}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
