# Final Review Verdict Contract

Schema: `aegis.final_review_verdict.v1`
Fixed path: `<artifact_path>/FINAL_REVIEW_VERDICT.json`

Required fields:

- `schema`
- `workflow_run_id`
- `verdict`: `PASS` or `FAIL`; must match F's returned `status`
- `conclusion`: non-empty string
- `reasons`: non-empty string array
- `evidence_index`: non-empty array of `{evidence_id,path,size,sha256}`

Before F starts, the Coordinator writes immutable `FINAL_REVIEW_INPUT_MANIFEST.json` using schema `aegis.final_review_input_manifest.v2`. Its `authorities` section binds the Project Seal, remote witness requirement/result, and observed TraceRelay runtime identity. `required_evidence` covers every frozen project-runtime file, Scope control, engineering-input snapshot, reasoning context and ledger snapshot, approved test plan, planning handoff, non-blank test report, every completed A/B planning response and instruction receipt (including C-start reuse snapshots), each completed C request/evidence manifest plus every recursively referenced raw evidence file, and every completed C-E execution response and instruction receipt available to F. The manifest also embeds the frozen runtime identity, planning turns, and all pre-F execution/evidence-session metadata.

Evidence paths must be absolute files under the project or run artifact root. IDs and paths must be unique. F must copy every descriptor in `required_evidence` exactly, then add exact descriptors named `final-review-input-manifest` and `final-review` for the input manifest and a non-blank `FINAL_REVIEW.md`. The Coordinator seals the input-manifest hash and required IDs before the F process starts, then mechanically revalidates every required descriptor, verdict hash, evidence ID, and mandatory non-blank report before terminal completion. A self-authored `FINAL_REVIEW.md` alone can never form a terminal verdict.

An F failure remains `delivery_eligible=false`. Master may confirm or dispute it only through the separate `aegis.master_final_review_confirmation.v1` record. That command loads the SQLite reservation's authoritative state blob unconditionally, holds the reservation transaction while writing confirmation artifacts, and commits with an old-state digest compare-and-swap; `RUN_STATE.json` is only a rebuildable projection and cannot authorize confirmation. Confirmation never changes F's verdict. Later authoritative loads and project audits revalidate the confirmation JSON, Master review, final review, and every indexed descriptor, so deleting or rewriting the sealed audit chain fails closed.
