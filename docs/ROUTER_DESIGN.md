# Aegis Router Design

## Definition

`aegis-router` is a lightweight local message router. It can be exposed as an MCP-style stdio server.

It is closer to a local post office than to a general network protocol stack.

## Responsibilities

- Create routing domains.
- Register agents.
- Maintain identity registry.
- Maintain an authoritative directed route table.
- Reject messages whose `sender -> receiver` edge is not allowed by the route table.
- Send envelopes by target identity.
- Maintain inbox/outbox state.
- Support ack and heartbeat.
- Provide domain snapshots for the owning hub.
- Own a shared local communication root for temporary mailbucket folders.
- Periodically clean expired temporary mailbucket folders.

## Non-responsibilities

- It does not judge whether a task is reasonable.
- It does not evaluate causal truth.
- It does not write business libraries.
- It does not understand payload semantics.
- It does not decide organization structure.
- It does not decrypt message payload paths.
- It does not store long-lived agent knowledge, evidence, or private working material.
- It does not act as a vault.

## Phase-1 policy

Only same-domain communication is allowed by default. Cross-domain communication must be mediated by a higher-level hub in future versions.

Visibility is not permission. A visible agent may still be unreachable unless a directed edge exists in the authoritative route table.

## Directed route table

The router-side route table is the runtime authority for communication topology.

A message envelope is accepted only when all of the following hold:

1. `sender` is a registered active agent.
2. `receiver` is a registered active agent.
3. `sender -> receiver` exists in the router route table.
4. The envelope authentication field verifies against the sender public identity key.
5. The envelope has not violated the router replay window when nonce or timestamp checks are enabled.

The router must reject any message whose directed edge is missing, even if both agents are in the same domain.

## Role-local route table

Every role also carries a local route table in its own role contract or prompt package.

The role-local route table tells the agent:

- which roles it may send to;
- which roles may send to it;
- which edges are single-direction edges;
- which pairs form a protocol-level bidirectional loop through two directed edges.

The router table provides mechanism-level enforcement. The role-local table provides semantic self-limitation. The two tables must describe the same directed graph.

## Envelope v1

The v1 envelope is intentionally small:

```yaml
sender: <sender_agent_id>
receiver: <receiver_agent_id>
path: <receiver-key-encrypted mailbucket path>
auth:
  alg: <signature_algorithm>
  key_id: <sender_identity_key_id>
  nonce: <unique_nonce>
  timestamp: <utc_timestamp>
  signature: <signature over sender|receiver|path|nonce|timestamp>
```

`path` is encrypted for the receiver. The router cannot decrypt it and must not try to interpret it.

`auth` proves that the envelope was produced by the sender identity key and that the visible routing fields and encrypted path were not replaced in transit.

The concrete cryptographic implementation is allowed to use separate key material for identity signatures and path encryption. The contract requirement is simple:

```text
sender authentication + receiver-only path confidentiality
```

## Mailbucket payload model

Large or semantically rich payloads must not be placed inside the router envelope.

The sender writes the real message into a unique folder under the router-owned shared communication root, then sends only the encrypted path to that folder.

A mailbucket folder must contain at least:

```text
README.md
```

The README is the letter body. It explains what the sender wants to say and how the receiver should interpret any attached files.

Optional attachments may include logs, test evidence, patches, reports, screenshots, or other artifacts.

The receiver decrypts `path`, reads the folder in place, and uses the information. If the information is one-time-use, the receiver does not need to copy it anywhere.

If the sender or receiver independently judges that the material has long-term value, that agent must copy it into its own private agent folder. The shared mailbucket is temporary public infrastructure and must not be used as long-term storage.

## Cleanup policy

The router periodically scans the shared communication root and deletes expired temporary mailbucket folders.

Cleanup is based on folder age and configured grace period, not on payload meaning.

The grace period exists only to give agents enough time to:

- read the message;
- use one-time information;
- decide whether to copy valuable material into their own private folder.

The router must not retain a shared mailbucket folder merely because an agent considers it valuable. Long-term retention belongs to agent-private folders or to the governed Archive / Knowledge / Causal admission process.

## Contract references

Top-level topology and payload contracts are defined in:

- `aegis-master-kit/organization/topologies/master_top_level_v1.yaml`
- `aegis-master-kit/organization/contracts/TOP_LEVEL_ROUTE_TOPOLOGY_CONTRACT.md`
- `aegis-master-kit/organization/contracts/ROUTE_ENVELOPE_AND_MAILBUCKET_CONTRACT.md`
