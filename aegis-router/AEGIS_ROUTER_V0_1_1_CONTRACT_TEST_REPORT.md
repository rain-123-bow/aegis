# Aegis Router v0.1.1 Contract Closure Test Report

## Conclusion

The v0.1.1 contract closure is complete.

All requested contract gaps were fixed and all acceptance tests passed in the local no-dependency acceptance suite:

```text
passed = 11
failed = 0
```

`pytest` was also attempted, but the bundled local Python environment does not have `pytest` installed:

```text
No module named pytest
```

This report therefore uses the direct acceptance script result as the verification source.

## Changed Contract

### Parent Domain Contract

`register_agent(parent_id=...)` now rejects parent/child relationships that cross routing domains.

Accepted:

```text
parent.domain_id == child.domain_id
```

Rejected:

```text
parent.domain_id != child.domain_id
```

### No-Ack Message Lifecycle

`requires_ack=False` messages now enter a terminal state after first successful receive.

Lifecycle:

```text
pending -> completed
```

`completed` messages are terminal:

- not returned by later default receives
- not returned by `include_delivered=True`
- cannot be acknowledged later

### MCP Malformed Call Contract

MCP `tools/call` now validates required arguments before handler dispatch.

Malformed calls return controlled router errors:

```text
code = -32000
type = InvalidRequestError
```

They no longer fall through as internal `KeyError`.

### Agent Lifecycle Contract

The lifecycle contract is now explicit:

```text
register_agent()    -> active registered agent
deactivate_agent()  -> temporary inactive agent
unregister_agent()  -> final removal from registry
heartbeat()         -> only updates active registered agents
```

Heartbeat does not reactivate inactive agents and does not recreate unregistered agents.

## Files Changed

```text
aegis_router/core.py
aegis_router/server.py
tests/test_router_core.py
tests/test_mcp_server.py
README.md
AEGIS_ROUTER_V0_1_1_CONTRACT_TEST_REPORT.md
```

## Acceptance Test Environment

Working directory:

```text
C:\Users\playm\Documents\self-git\patch\aegis-implemented-v0.1\aegis\aegis-router
```

Python executable:

```text
C:\Users\playm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
```

Test method:

```text
Direct no-dependency Python acceptance script
```

Reason:

```text
pytest is not installed in the current bundled Python environment.
```

## Acceptance Results

### 1. Positive route: registered same-domain sender -> target receive -> ack -> persisted acked

Result:

```text
passed = true
message_id = msg_a45c14a3492546f5
persisted_status = acked
```

Closure:

```text
agent_alpha sends to agent_beta
-> router stores pending message
-> agent_beta receives message as delivered
-> agent_beta ack succeeds
-> persisted state is acked
```

### 2. Cross-domain send rejected

Result:

```text
passed = true
error = cross-domain message is not allowed in phase 1: master_domain -> isolated_domain
```

Closure:

```text
agent_alpha in master_domain
isolated_agent in isolated_domain
-> send rejected
```

### 3. Unregistered send rejected

Result:

```text
passed = true
error = agent not found: ghost
```

Closure:

```text
ghost is not registered
-> send rejected before routing
```

### 4. Unregistered receive rejected

Result:

```text
passed = true
error = agent not found: ghost
```

Closure:

```text
ghost is not registered
-> mailbox access rejected
```

### 5. Inactive send rejected

Result:

```text
passed = true
error = agent is not active: agent_gamma
```

Closure:

```text
deactivate_agent(agent_gamma)
-> agent_gamma.status = inactive
-> send rejected
```

### 6. Non-target ack rejected

Result:

```text
passed = true
error = only the target agent may ack a message
```

Closure:

```text
message target = agent_beta
agent_alpha attempts ack
-> ack rejected
```

### 7. Cross-domain parent registration rejected

Result:

```text
passed = true
error = parent agent must be in the same domain: isolated_domain -> master_domain
```

Closure:

```text
parent = isolated_agent in isolated_domain
child target domain = master_domain
-> registration rejected
```

### 8. No-ack message reaches terminal lifecycle state

Result:

```text
passed = true
message_id = msg_63d8ea54a282413f
received_status = completed
persisted_status = completed
ack_error = message does not require ack
```

Closure:

```text
requires_ack=False
-> first receive succeeds
-> status becomes completed
-> completed is persisted
-> later receive returns nothing
-> later ack is rejected
```

### 9. Heartbeat does not reactivate inactive agent

Result:

```text
passed = true
error = agent is not active: agent_gamma
```

Closure:

```text
agent_gamma is inactive
-> heartbeat rejected
-> heartbeat does not silently reactivate
```

### 10. Heartbeat rejects unregistered agent

Result:

```text
passed = true
unregister_status = unregistered
heartbeat_error = agent not found: agent_gamma
```

Closure:

```text
unregister_agent(agent_gamma)
-> agent removed from registry
-> heartbeat rejected as not found
```

### 11. Malformed MCP call returns controlled request error

Result:

```text
passed = true
code = -32000
type = InvalidRequestError
message = missing required argument(s) for register_agent: role
```

Closure:

```text
tools/call register_agent without role
-> required argument validation runs before handler indexing
-> InvalidRequestError returned
-> no internal KeyError leak
```

## Final Verification Judgment

The four requested contract gaps are closed:

```text
1. cross-domain parent registration rejected
2. no-ack messages reach terminal completed state
3. malformed MCP calls return InvalidRequestError
4. inactive/unregister/heartbeat semantics are explicit and enforced
```

No prohibited scope was added:

```text
no cross-domain routing
no complex topology DSL
no department automation
no new framework dependency
no unrelated refactor
```
