# Aegis Router Nested Codex Test Report

## Conclusion

`aegis_router` can complete the intended Phase-1 route loop when the Master owns the router state, agents are registered first, and registered identities are used for routing.

The tested positive path is closed:

```text
Master initializes router state
-> Master registers agents
-> nested agent_alpha sends to nested agent_beta
-> nested agent_beta receives and acknowledges
-> Master verifies final persisted state
```

The router correctly rejects cross-domain send, unregistered send/receive, inactive send, and non-target ack. The remaining code-level gaps are:

- `register_agent()` allows a child agent in one domain to use a parent from another domain.
- `requires_ack=False` messages stop at `delivered` and have no terminal lifecycle state.
- MCP wrapper malformed calls can return internal `KeyError` instead of controlled `InvalidRequestError`.
- `heartbeat()` reactivates inactive agents; this may be valid, but the contract should state it explicitly.

## Test Scope

Test target:

```text
C:\Users\playm\Documents\self-git\patch\aegis-implemented-v0.1\aegis\aegis-router
```

Router state file:

```text
C:\Users\playm\AppData\Local\Temp\aegis_router_gpt54_full_test_state.json
```

Nested agent runtime:

```text
nested-codex model: gpt-5.4
```

Python executable:

```text
C:\Users\playm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
```

This test intentionally focused on router code behavior and route mechanics. It did not depend on `pytest`.

## Initial State

The Master session created a clean state file and initialized two domains:

```text
master_domain
isolated_domain
```

Registered agents:

```text
master_domain:
  master
  agent_alpha
  agent_beta
  agent_gamma

isolated_domain:
  isolated_agent
```

Initial verification:

```text
master_agents = ['agent_alpha', 'agent_beta', 'agent_gamma', 'master']
master_messages = 0
isolated_agents = ['isolated_agent']
```

## Positive Route Flow

### Step 1: agent_alpha sends a message

Execution context:

```text
nested-codex / gpt-5.4 / agent_alpha
```

Action:

```text
from_id = agent_alpha
to_id = agent_beta
message_type = handoff
task_id = FULL-T001
priority = high
requires_ack = True
```

Result:

```text
ok = true
message_id = msg_9eb9e544537a4e8d
status = pending
from_id = agent_alpha
to_id = agent_beta
task_id = FULL-T001
priority = high
requires_ack = true
```

Interpretation:

The router accepted a message from a registered sender to a registered target in the same domain and persisted it as `pending`.

### Step 2: agent_beta receives and acknowledges

Execution context:

```text
nested-codex / gpt-5.4 / agent_beta
```

Action:

```text
receive_messages('agent_beta', include_delivered=True)
ack_message('agent_beta', 'msg_9eb9e544537a4e8d')
```

Result:

```text
ok = true
received_count = 1
message_id = msg_9eb9e544537a4e8d
status_before_ack = delivered
ack_status = acked
from_id = agent_alpha
to_id = agent_beta
task_id = FULL-T001
payload = {
  "content": "phase-1 positive route",
  "sender": "agent_alpha",
  "sequence": 1
}
```

Interpretation:

The router moved the message from `pending` to `delivered` on receive, then to `acked` when the target agent acknowledged it.

## Boundary Tests

### Same-domain visibility

Execution context:

```text
nested-codex / gpt-5.4 / agent_gamma
```

Action:

```text
list_visible_agents('agent_gamma')
```

Result:

```text
visible_agents = ['agent_alpha', 'agent_beta', 'agent_gamma', 'master']
isolated_visible_to_gamma = false
```

Interpretation:

Same-domain visibility works for active agents. `isolated_agent` was not visible to `agent_gamma`.

### Cross-domain send rejection

Action:

```text
send_message('agent_alpha', 'isolated_agent', ...)
```

Result:

```text
cross_domain_rejected = true
cross_domain_error = cross-domain message is not allowed in phase 1: master_domain -> isolated_domain
```

Interpretation:

The Phase-1 same-domain routing boundary is enforced for sends.

### Unregistered send rejection

Action:

```text
send_message('ghost_agent', 'agent_beta', ...)
```

Result:

```text
unregistered_send_rejected = true
unregistered_send_error = agent not found: ghost_agent
```

Interpretation:

An unregistered sender cannot use the router's send capability.

### Unregistered receive rejection

Action:

```text
receive_messages('ghost_agent')
```

Result:

```text
unregistered_receive_rejected = true
unregistered_receive_error = agent not found: ghost_agent
```

Interpretation:

An unregistered receiver cannot use mailbox access.

### Non-target ack rejection

Setup:

```text
agent_alpha -> agent_beta
task_id = FULL-T002
message_id = msg_1630830d5bde4c40
```

Action:

```text
ack_message('agent_gamma', 'msg_1630830d5bde4c40')
```

Result:

```text
wrong_ack_rejected = true
wrong_ack_error = only the target agent may ack a message
```

Interpretation:

The router enforces that only the target agent can acknowledge a message.

## Lifecycle Tests

### Normal ack lifecycle

Message:

```text
FULL-T002
agent_alpha -> agent_beta
requires_ack = True
```

Result after `agent_beta` receive and ack:

```text
status = acked
```

Interpretation:

The standard acknowledged message lifecycle is closed.

### No-ack lifecycle

Message:

```text
FULL-T003
agent_alpha -> agent_beta
requires_ack = False
```

Result after `agent_beta` receive:

```text
first receive:
  status = delivered
  requires_ack = false

second default receive:
  count = 0

receive with include_delivered=True:
  status = delivered
```

Interpretation:

The message is delivered and hidden from default receives, but it has no terminal state such as `completed`, `closed`, or `no_ack_delivered`. This is a contract gap if no-ack messages are meant to be terminal after delivery.

### Inactive agent behavior

Action:

```text
unregister_agent('agent_gamma')
send_message('agent_gamma', 'agent_alpha', ...)
```

Result:

```text
unregister_status = inactive
inactive_send_rejected = true
inactive_send_error = agent is not active: agent_gamma
```

Interpretation:

Inactive agents cannot send messages.

### Heartbeat reactivation

Action:

```text
heartbeat('agent_gamma')
send_message('agent_gamma', 'agent_alpha', ...)
```

Result:

```text
heartbeat_status = active
reactivated_send:
  message_id = msg_96b41f6f7b874d94
  status = pending
  task_id = FULL-T004
```

Then `agent_alpha` received and acknowledged:

```text
ack_status = acked
status_before_ack = delivered
task_id = FULL-T004
```

Interpretation:

`heartbeat()` reactivates an inactive agent. This behavior works, but the intended contract should clarify whether unregister means temporary inactive state or final deregistration.

## Contract Gap Tests

### Cross-domain parent accepted

Action:

```text
register_agent(
  agent_id='cross_parent_child',
  domain_id='master_domain',
  role='worker',
  parent_id='isolated_agent'
)
```

Result:

```text
cross_domain_parent_accepted = true
cross_domain_parent_agent = cross_parent_child
```

Final state includes:

```text
agent_id = cross_parent_child
domain_id = master_domain
parent_id = isolated_agent
status = active
```

Interpretation:

This is a code-level contract defect. `register_agent()` checks that the parent exists, but it does not check that parent and child are in the same domain. That allows a topology that violates the domain boundary model.

### MCP malformed call handling

Action:

```text
tools/call register_agent with missing role
```

Result:

```text
bad_call_error:
  code = -32603
  type = KeyError
  message = 'role'
```

Interpretation:

The MCP wrapper exposes an input schema, but does not validate required fields before indexing the argument dictionary. Missing required fields can escape as internal errors instead of controlled `InvalidRequestError`.

## Final Persisted State

Final messages in `master_domain`:

```text
FULL-T001: agent_alpha -> agent_beta, requires_ack=True,  status=acked
FULL-T002: agent_alpha -> agent_beta, requires_ack=True,  status=acked
FULL-T003: agent_alpha -> agent_beta, requires_ack=False, status=delivered
FULL-T004: agent_gamma -> agent_alpha, requires_ack=True,  status=acked
```

Final agents in `master_domain`:

```text
agent_alpha: active, parent=master
agent_beta: active, parent=master
agent_gamma: active, parent=master
cross_parent_child: active, parent=isolated_agent
master: active, parent=None
```

Final agents in `isolated_domain`:

```text
isolated_agent: active, parent=None
```

## Logical Closure

The main route contract is closed:

```text
registered sender
-> same-domain target
-> persisted pending message
-> target receive
-> delivered state
-> target ack
-> acked state
-> Master verifies persisted state
```

The rejection contract is closed for:

```text
cross-domain send
unregistered send
unregistered receive
inactive send
non-target ack
```

The unresolved contract points are:

```text
cross-domain parent relationship is accepted
no-ack messages have no terminal state
MCP required-argument validation is not enforced before handler indexing
heartbeat reactivation semantics are not documented as temporary inactive vs final unregister
```

## Recommended Fix Order

1. Add same-domain validation for `parent_id` in `register_agent()`.
2. Define `requires_ack=False` lifecycle semantics and implement a terminal state.
3. Add MCP argument validation so malformed calls return `InvalidRequestError`.
4. Document or split inactive behavior:
   - `unregister_agent()` for final deregistration, or
   - `deactivate_agent()` for temporary inactive state that heartbeat may restore.
