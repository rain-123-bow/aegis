# Knowledge Authority Contract

## 1. Who may propose Knowledge

The following actors may submit Knowledge proposals:

- developer
- Master
- department lead
- ordinary task agent
- reviewer agent
- verification agent
- external input adapter

## 2. Who may write Knowledge

Only Master may write, update, invalidate, supersede, seal, or expose Knowledge entries.

Contributors submit proposals; they do not mutate the Knowledge Base directly.

```text
Contributor may propose.
Master may admit.
Master may seal.
```

## 3. Developer input rule

Developer-provided information may be used as a source, but it is not automatically an active fact.

Master must classify it as one of:

- verified_fact
- reported_fact
- tentative_fact
- accepted_external_requirement
- rejected_claim

External customer requirements may be accepted as constraints when source identity and scope are sufficient, even if they are not empirically verified.

## 4. Agent observation rule

Agent observations may become Knowledge only after Master reviews:

- source
- evidence
- scope
- version_context
- applicability
- confidence
- conflict risk

## 5. Direct mutation rule

Any direct modification to encrypted payload, public manifest, indexes, integrity files, or entry records outside Master governance is an unauthorized mutation.

Master must not trust such state until validated against trusted seal continuity.
