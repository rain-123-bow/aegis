# Engineering Input Manifest Contract

Schema: `aegis.engineering_input_manifest.v1`

Master creates the manifest before a new workflow run. Required top-level fields:

- `schema`
- `project_id_hex`
- `created_at_utc`
- `documents`

Each document uses exactly `{kind,path,size,sha256}`. `kind` is `REQUIREMENTS` or `IMPLEMENTATION_PLAN`; at least one document of each kind is required. Paths are absolute, non-symlinked files under the governed project root. Duplicate paths are forbidden.

The Coordinator copies the manifest to `<artifact_path>/ENGINEERING_INPUT_MANIFEST.json`, seals its raw hash and canonical document-set hash, and revalidates every document before and after every A-F node.

A new C-start run must reference a terminal parent run with a completed planning stage. Reuse is allowed only when the canonical document-set hash is identical. The approved test plan, planning review, parent run state, current context pack, and new handoff are copied or indexed under the child run. Any requirements or implementation-plan difference requires a new A-F run from A.
