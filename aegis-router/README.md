# aegis-router

`aegis-router` is a lightweight local message router for Aegis agent communication domains.

It can run as a simple MCP-style stdio server. The implementation intentionally avoids external dependencies in Phase 1.

Supported Python:

```text
>=3.11
recommended: 3.13
```

v0.1.2 does not change router behavior. It only standardizes installation, CI, and verification.

## What it does

- Create routing domains.
- Register agents.
- Route messages by `target_id`.
- Enforce same-domain visibility in Phase 1.
- Maintain inbox/outbox message state.
- Support ack, heartbeat, temporary deactivation, and final unregistration.
- Provide domain snapshots.

## What it does not do

- It does not reason about task truth.
- It does not judge payload content.
- It does not write the archive, causal, or knowledge libraries.
- It does not decide organization topology.

## Run as MCP-style stdio server

```bash
cd aegis-router
python -m aegis_router.server --store .aegis-router/state.json
```

The server supports JSON-RPC methods:

- `initialize`
- `tools/list`
- `tools/call`

## Agent lifecycle contract

Registered agents are active by default.

- `deactivate_agent(agent_id)` marks an agent `inactive`. Inactive agents cannot send, receive, ack, list visibility, or heartbeat.
- `unregister_agent(agent_id)` permanently removes an agent from the registry. A later heartbeat for that agent returns not found.
- `heartbeat(agent_id)` only updates an already active agent. It does not reactivate inactive or unregistered agents.

## Message lifecycle contract

- `requires_ack=True`: `pending -> delivered -> acked`.
- `requires_ack=False`: `pending -> completed` on first successful receive. `completed` is terminal and is not returned by later receives.

## Direct demo

```bash
cd aegis-router
python examples/demo_router_flow.py
```

## Local install

Runtime install:

```bash
cd aegis-router
python -m pip install --upgrade pip
pip install -e .
```

Development install:

```bash
cd aegis-router
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

## Tests

```bash
cd aegis-router
python -m pytest
python scripts/acceptance_router_contract.py
```
