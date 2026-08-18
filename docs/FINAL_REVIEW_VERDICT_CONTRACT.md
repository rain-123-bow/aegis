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

Evidence paths must be absolute files under the project or run artifact root. IDs and paths must be unique. `FINAL_REVIEW.md` must be indexed. The Coordinator seals the verdict hash and evidence IDs into the completed F attempt, then revalidates them before terminal completion.

An F failure remains `delivery_eligible=false`. Master may confirm or dispute it only through the separate `aegis.master_final_review_confirmation.v1` record; this never changes F's verdict.
