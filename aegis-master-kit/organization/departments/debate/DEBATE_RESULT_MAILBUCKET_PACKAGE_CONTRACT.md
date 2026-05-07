# Debate Result Mailbucket Package Contract

## 1. Purpose

This contract defines how the Debate Leader delivers a completed Debate causal package to Master through the existing router mailbucket model.

The router remains a post office. It does not read, judge, summarize, or promote the package into truth.

---

## 2. Package layout

A completed Debate package must be stored in one mailbucket folder:

```text
<mailbucket-message-folder>/
  README.md
  final_report.json
  adjudicator_causal_state.json
  worker_states/
    <worker_id>.json
  worker_proofs/
    <worker_id>_proof.json
  transcript_digest.json
  evidence_manifest.json
```

---

## 3. README requirements

`README.md` must explain:

- debate run id;
- sender and receiver;
- decision target;
- final decision label;
- whether developer decision is required;
- how to interpret each attachment;
- whether the package is ready for Master causal admission, Test request, or developer direction.

---

## 4. Required JSON files

### final_report.json

The Leader's final causal report.

It must not be a bare conclusion.

### adjudicator_causal_state.json

The Leader's causal state including route priority and expand priority.

### worker_states/*.json

Each Debate Worker's local causal state.

### worker_proofs/*.json

Each real nested-Codex Debate Worker's creation proof.

### transcript_digest.json

Digest of worker turns sufficient to understand attacks, answers, concessions, and scope narrowing without raw chat history.

### evidence_manifest.json

Evidence references used by the run and their source categories.

---

## 5. Strict proof rule

For real acceptance, every worker state must have a matching worker proof.

Missing proof is a failure, not a skip.

---

## 6. Master handoff

Master reads the package from the mailbucket and decides the next action.

If `developer_decision_required` is true, Master must not collapse the result into a fake unique conclusion. It must ask the developer to choose.

---

## 7. Boundary to Archive / Knowledge / Causal

A mailbucket package is not automatic global causal truth.

It may later be promoted into Archive, Knowledge, or Causal only through the configured governance process.
