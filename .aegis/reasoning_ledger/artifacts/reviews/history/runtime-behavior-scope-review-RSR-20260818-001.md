# Aegis Runtime Behavior Scope Review

- Review ID: `RSR-20260818-001`
- Review date: `2026-08-18`
- Reviewer: independent fresh-context Codex/GPT reviewer
- Verdict: `FAIL`
- Blocking findings: `4`
- Cross-model review: skipped by the user's standing model-boundary decision
- Tests: not run; review used file inspection and read-only Git object queries

## Reviewed artifact

- Repository commit: `26983719d3c5ed4945e6f9e79adf4a7880af8489`
- Proposal: `docs/AEGIS_RUNTIME_SCOPE_PROPOSAL.md`
- Proposal SHA-256: `580198d43638a8afa96ce14f86bab57dbc7d6291aeaee83b02594f7efe90d593`
- Architecture contract SHA-256: `42f760fbd0f14473a2b1d7b963535622319954503590856a2b8138f35489711a`
- Runtime scope contract SHA-256: `fc8f94fba120539e366d5b29897870c52f6070da854438f672d2db3b23471ed1`

## P1-1: TraceRelay submodule entries are not bound to their owning commit

Classification: valid and actionable.

Violated invariant: every runtime entry must be proven to belong to the governed Git commit before a v2 Seal is issued.

Evidence:

- `docs/AEGIS_RUNTIME_SCOPE_PROPOSAL.md:12,18-19` selects `submodules/TraceRelay/src`, its `pyproject.toml`, and `.gitmodules`.
- `.gitmodules:1-4` describes the submodule location and remote but does not contain the gitlink object ID.
- The parent commit stores only `160000 commit cb52a01de5d388add796e40887ffb4fd255c2cf7 submodules/TraceRelay`.
- `src/runtime_behavior_scope.py:155-180` materializes files inside the submodule worktree as ordinary runtime entries.
- `src/project_seal_store.py:577-584` reads every entry with parent-repository `git cat-file blob HEAD:<entry.path>`.
- The read-only query for `HEAD:submodules/TraceRelay/src/tracerelay/__init__.py` exits `128`: the file exists in the worktree but not as a blob in the parent commit.

Failure mechanism: the proposed manifest contains entries that the existing commit-membership verifier cannot prove. The v2 Seal cannot be issued. Parent `.gitmodules` content is not a substitute for the gitlink object ID.

Closure condition: add submodule-aware verification that binds the parent gitlink OID, requires the submodule `HEAD` to equal that OID, rejects scoped tracked/untracked/ignored contamination, and reads every selected entry from that submodule commit's object database. The resolved manifest must include the gitlink OID. Vendoring the production source as parent-repository blobs is the alternative, but is not assumed by this review.

## P1-2: Include roots absorb ignored files that have no commit membership

Classification: valid and actionable.

Violated invariant: a resolved runtime manifest must contain only explicitly allowed, commit-provable runtime entries; clean status cannot hide selected files.

Evidence:

- `src/runtime_behavior_scope.py:169-180` recursively selects every file below an include root.
- `src/runtime_behavior_scope.py:501-510` supports exact root/file exclusions, not the proposal's category labels such as “build output”.
- `config/agent_registry.json.bak.20260706145929` exists below selected root `config` and is ignored by `.gitignore:11`.
- `submodules/TraceRelay/src/TraceRelay.egg-info/` exists below the selected TraceRelay source root and is ignored by `submodules/TraceRelay/.gitignore:7`.
- `src/project_seal_store.py:549-565` uses `git ls-files --others --exclude-standard`; ignored files do not enter the dirty set.
- The same ignored files remain selected by the resolver and later fail the commit-blob query at `src/project_seal_store.py:577-584`.

Failure mechanism: a worktree can appear clean while ignored backup/build files enter the manifest. The proposal's migration gate cannot produce a commit-bound Seal from the current tree.

Closure condition: the policy must explicitly exclude the existing backup and `submodules/TraceRelay/src/TraceRelay.egg-info` build-output root. Resolution or Seal verification must also reject every selected entry whose owning repository commit cannot prove membership, regardless of ignore rules.

## P1-3: TraceRelay production packaging inputs and artifact type are undefined

Classification: valid and actionable.

Violated invariant: build descriptions, packaging definitions, and files actually consumed by the production package path must be inside the governed scope; test/demo remain excluded only when the production path does not package them.

Evidence:

- `docs/AEGIS_RUNTIME_SCOPE_PROPOSAL.md:18,24-30` selects TraceRelay `pyproject.toml`, excludes README/test material, and declares no forced inclusions.
- `submodules/TraceRelay/pyproject.toml:1-3` selects the setuptools build backend.
- `submodules/TraceRelay/pyproject.toml:9` reads `README.md` as package metadata.
- `submodules/TraceRelay/pyproject.toml:21-22` defines the production `tracerelay` entry point.
- The generated `submodules/TraceRelay/src/TraceRelay.egg-info/SOURCES.txt:1-3,20-30` includes `LICENSE`, `README.md`, `pyproject.toml`, and tests in the source distribution.

Failure mechanism: the proposal does not state whether production consumes a wheel, source distribution, or editable install. Its current exclusions are correct only under an unstated packaging path. A source distribution would package excluded tests; README/LICENSE can change package output without changing the proposed Seal.

Closure condition: declare one deterministic production package type and command. To preserve the user's test/demo exclusion, production must be wheel-only or use equivalent packaging configuration that proves tests are absent. Include `submodules/TraceRelay/README.md` and `submodules/TraceRelay/LICENSE` when the selected build consumes them, and bind all retained submodule inputs through P1-1.

## P1-4: Approval binding does not prove reviewer PASS for the final policy

Classification: valid and actionable.

Violated invariant: the independent reviewer and user must approve the exact canonical Scope definition executed by the Coordinator.

Evidence:

- `docs/AEGIS_ARCHITECTURE_CONTRACT.md:194` orders the process as policy write, reviewer review, user confirmation, then Coordinator execution.
- `docs/AEGIS_RUNTIME_SCOPE_PROPOSAL.md:52-54` reverses the first stages by obtaining review and confirmation before writing the policy.
- `src/runtime_behavior_scope.py:315-323,423-445` obtains `review.verdict=PASS` from the policy's own fields.
- `src/runtime_behavior_scope.py:348-363,408-420` checks the review report only for non-empty bytes and matching SHA-256; it does not parse the report verdict or reviewed policy identity.
- `src/runtime_behavior_scope.py:385-405` binds policy/report/statement descriptors in the decision, but does not require the report or user statement to bind a policy-definition hash.

Failure mechanism: an unrelated or explicit `FAIL` Markdown report can be hashed into a policy that self-declares `review.verdict=PASS`; a matching `APPROVED` decision passes current validation. Requiring the report to hash the full policy would create a policy-to-report-to-policy hash cycle because the policy contains `report_sha256`.

Closure condition: separate the immutable canonical Scope definition from approval evidence. The structured reviewer result must contain project ID, Scope-definition SHA-256, and parsed `verdict=PASS`. The user confirmation must bind the same definition hash and the reviewer result. The final decision then binds definition, reviewer result, confirmation, and `APPROVED`. Approval evidence may instead live entirely outside the policy, provided the Seal binds both the policy definition and validated decision.

## Final decision

The proposal is not eligible for user confirmation or v2 Seal migration. A revised proposal and matching implementation must close all four findings, then receive a new independent review. This report is evidence of a failed review and must not be represented as `PASS` evidence.
