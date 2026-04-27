# Aegis Router Design

## Definition

`aegis-router` is a lightweight local message router. It can be exposed as an MCP-style stdio server.

## Responsibilities

- Create routing domains.
- Register agents.
- Maintain identity registry.
- Enforce same-domain visibility in Phase 1.
- Send messages by target identity.
- Maintain inbox/outbox state.
- Support ack and heartbeat.
- Provide domain snapshots for the owning hub.

## Non-responsibilities

- It does not judge whether a task is reasonable.
- It does not evaluate causal truth.
- It does not write business libraries.
- It does not understand payload semantics.
- It does not decide organization structure.

## Phase-1 policy

Only same-domain communication is allowed by default. Cross-domain communication must be mediated by a higher-level hub in future versions.
