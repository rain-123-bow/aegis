# Route Envelope and Mailbucket Contract

## 1. Purpose

This contract defines the lightweight top-level communication payload protocol.

The design goal is to prevent the router from carrying long or semantically complex packets.

The router carries only a small envelope. The real message body lives in a local filesystem folder.

## 2. Post-office model

The model is:

```text
router shared communication root = post office / temporary mailbucket
message envelope                  = envelope
README.md                         = letter body
attachments                       = enclosed evidence or artifacts
agent private folder              = private workspace / private archive cabinet
```

The shared communication root is not a vault.

## 3. Agent private folder

Every agent must have a private folder controlled by that agent.

The agent private folder may contain:

- private keys;
- local working notes;
- copied valuable incoming material;
- copied valuable outgoing material;
- role-local route table or role-local prompt material.

The router must not use the shared communication root as a substitute for agent-private storage.

## 4. Key material

Before registering with a router, an agent must create the key material needed for:

1. sender identity authentication;
2. receiver-only path confidentiality.

The concrete algorithms may be selected by implementation. A typical split is:

```text
identity signing key  -> signs envelopes
path encryption key   -> decrypts paths addressed to this agent
```

Public verification and encryption material may be registered with the router or exposed through a governed identity registry.

Private key material must remain inside the agent private folder or another agent-controlled secret location.

## 5. Envelope v1

The logical v1 envelope contains:

```yaml
sender: <sender_agent_id>
receiver: <receiver_agent_id>
path: <encrypted_path_for_receiver>
auth:
  alg: <signature_algorithm>
  key_id: <sender_identity_key_id>
  nonce: <unique_nonce>
  timestamp: <utc_timestamp>
  signature: <signature>
```

The minimal logical fields are:

1. sender;
2. receiver;
3. receiver-encrypted path;
4. authentication field.

The authentication signature must cover at least:

```text
sender | receiver | path | nonce | timestamp
```

This prevents sender spoofing and prevents replacing the receiver or encrypted path without invalidating the signature.

## 6. Router validation

When the router receives an envelope, it must:

1. verify that `sender` is registered and active;
2. verify that `receiver` is registered and active;
3. verify that `sender -> receiver` exists in the authoritative route table;
4. verify `auth` using the sender public identity key;
5. optionally reject stale timestamps or repeated nonces within the configured replay window;
6. store or forward the envelope without decrypting `path`.

The router must not decrypt `path`.

The router must not read the README or attachments referenced by `path`.

## 7. Sender write flow

To send a message, the sender:

1. creates a unique folder under the router-owned shared communication root;
2. writes `README.md` into that folder;
3. writes optional attachments when needed;
4. encrypts the folder path for the receiver;
5. signs the envelope authentication material;
6. sends the envelope to the router.

A recommended folder name is:

```text
<sender>__<receiver>__<utc_timestamp>__<nonce>/
```

The timestamp makes the folder logically one-time-use.

## 8. README rule

Every mailbucket folder must contain `README.md`.

The README must explain:

- what the sender wants to communicate;
- what the receiver should do next, if any;
- how to interpret each attachment;
- whether the message is pure one-time information, evidence feedback, debate material, review material, or causal fork material.

This interpretation is for the receiver. The router must not parse it.

## 9. Receiver read flow

To receive a message, the receiver:

1. receives the envelope from the router;
2. verifies or trusts the router-verified sender identity according to runtime policy;
3. decrypts `path` with its private path key;
4. reads `README.md` and optional attachments in place;
5. uses the information.

If the message is pure one-time information, the receiver may use it directly from the shared mailbucket and copy nothing into its private folder.

## 10. Independent value judgment

The sender and receiver may independently judge that a message has long-term value.

If either side wants to keep the material, that side must copy the material into its own private agent folder.

One side's value judgment is not an effective input for the other side's judgment.

The shared mailbucket folder must not be retained merely because one party thinks it is valuable.

## 11. Cleanup rule

The router periodically scans the shared communication root.

It deletes expired temporary mailbucket folders after a configured grace period.

The grace period exists to give agents time to:

- read the message;
- perform one-time use;
- decide whether to copy valuable material into their own private folder.

Cleanup is based on time and machine-readable folder metadata, not semantic value.

The router must not read README files or attachments to decide whether to retain a folder.

## 12. Boundary to Archive / Knowledge / Causal

Copying material into an agent private folder does not promote it into Archive, Knowledge, or Causal.

Archive, Knowledge, and Causal admission still require their own governance process.

A mailbucket message is evidence that a message was sent. It is not automatically truth.
