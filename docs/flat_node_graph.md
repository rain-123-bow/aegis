# Current Master and A-F Graph

The authoritative contract is `AEGIS_ARCHITECTURE_CONTRACT.md`.

Master is the user's long-lived semantic executor. Master directly writes requirements, the implementation plan, code, causal reasoning facts, and self-test results. Independent subagents may review or collect evidence; they do not author these final semantic artifacts through an intermediary handoff.

Master is outside LangGraph. The flat LangGraph contains only A-F:

1. A / `TEST_PLAN_AUTHOR` writes a test plan from the frozen engineering-input manifest and reasoning context pack.
2. B / `TEST_PLAN_REVIEWER` independently reviews the exact frozen plan. Rejection returns to A through a new immutable round.
3. C / `TEST_EXECUTOR` writes only a bound `aegis.test_execution_request.v3`; it must exactly reproduce the reviewer-approved `aegis.test_execution_policy.v2` including the complete effective environment.
4. The Coordinator validates the request, executes it without a shell through a Windows Job Object, and exclusively writes execution receipts and `aegis.test_evidence_manifest.v2`.
5. D / `TEST_RESULT_REVIEWER` audits plan completeness and evidence closure. D failure blocks E.
6. E / `TEST_REPORT_WRITER` writes the report only from approved plans and reviewed evidence. E failure blocks F.
7. F / `FINAL_REVIEWER` audits the whole engineering result: requirements, implementation plan, code, tests, evidence, reasoning ledger, Seal, and governance integrity.
8. F failure terminates the run. Master verifies the verdict structure and indexed evidence, then submits both F's conclusion and any documented disagreement to the user. Master cannot overwrite F's engineering verdict.

## State and message boundaries

Graph state carries control metadata and artifact paths, not long prose. Coordinator-owned state, immutable snapshots, TraceRelay evidence, GPT instruction receipts, and dynamic role registry records are authoritative.

A/B share one traced App Server process while retaining separate persistent role threads. C-F retain one persistent thread per role, but every node turn uses a new App Server process and TraceRelay session. No role thread directly messages another role thread.

Every role reads the Coordinator-bound engineering inputs and reasoning context snapshot. Hidden Master conversation context is not an A-F input.

## Mechanical gates

- A/B approval requires `score >= 95`, `error_count == 0`, `verdict == PASS`, and exact plan-hash binding.
- Rejected semantic issues are tracked by normalized logical identity and explicit predecessor mappings; renaming or paraphrasing is not repair.
- C cannot create evidence, timestamps, exit codes, runner identity, or execution receipts.
- D cannot start without valid Coordinator-generated test evidence.
- E failure cannot route to F.
- Frozen requirements, implementation plan, runtime behavior, context pack, approved plan, and governance controls cannot change during A-F.
- Any frozen-input mutation terminates the run and requires a user-confirmed accountability reason before another project run.
- One project lease permits only one active run. Terminal state releases the lease; a saved run may resume.
- Codex/GPT is the supported model boundary. Non-GPT interpretation compatibility is outside acceptance.
