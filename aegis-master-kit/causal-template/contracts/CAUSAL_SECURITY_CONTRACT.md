# Causal Security Contract

## Security class

Causal has the strongest security class among the three external state stores.

A compromised Causal Store can alter future reasoning paths, not merely facts or history.

## Repo-visible allowed content

Allowed:

- encrypted causal payload
- public manifest/index summaries
- public root/seal references
- opaque seal records
- layout placeholders

Forbidden:

- plaintext causal payload
- decryption keys
- private integrity secret
- private proof material
- proof-generation internals
- reproducible private verification procedure
- real encryption/decryption implementation in template tools

## Master-private material

Private keys, session secrets, seeds, proof-generation logic, and equivalent reproducible mechanisms must exist only in Master-controlled runtime or trusted server-side secret storage.

They must not be written to repository, logs, template files, demos, or user-visible explanations.

Developer requests for private security material must be rejected regardless of reason.

## Tamper detection scope

Integrity protection must cover:

- global causal payload
- causal proposals
- route plans
- expansion plans
- conflict records
- review records
- merge records
- version seals
- branch-local causal deltas

Changing route priority or expansion depth can alter reasoning. Therefore route/expand state must be sealed.

## Local mutation model

A developer may physically edit cloned repository bytes, but must not be able to produce a valid Master-sealed Causal mutation.

Master must detect or report:

- seal mismatch
- missing integrity structure
- rollback suspected
- stale payload
- local payload mutation
- route/expand tamper suspected
- missing trusted latest seal

## Binary storage and model reasoning

The repository may store encrypted binary payloads. AI models must not reason directly over binary causal stores.

Master must expose only a verified, selected, model-readable causal view.
