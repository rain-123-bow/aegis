# Phase 25A Debate Role Operational Skills Acceptance Report

## Verdict

accepted_phase25a_debate_role_operational_skill_enforcement

Phase 25A was applied to the local target branch and validated in the real repository.

## Repository State Tested

```text
repository: C:\Users\playm\Documents\self-git\aegis
branch: v0.1.1-alpha-skill
python: C:\Users\playm\Documents\self-git\aegis\.venv-debate-skill-phase25a\Scripts\python.exe
```

## Scope

Phase 25A converts Debate Leader and Debate Worker role behavior from superseded role-contract documents into explicit role-bound operational skills.

It does not claim production Debate closure, remote push, PR creation, remote merge, release, deployment, external sign-off, production store writes, or global causal truth merge.

## Files Added Or Modified

```text
README.md

aegis-master-kit/organization/departments/debate/README.md
aegis-master-kit/organization/departments/debate/MANIFEST.yaml
aegis-master-kit/organization/departments/debate/DEBATE_LEADER_OPERATIONAL_SKILL.md
aegis-master-kit/organization/departments/debate/DEBATE_WORKER_OPERATIONAL_SKILL.md
aegis-master-kit/organization/departments/debate/DEBATE_LEADER_WORKER_SKILL_ENFORCEMENT_CONTRACT.md

aegis-runtime/debate/pyproject.toml
aegis-runtime/debate/aegis_debate_runtime/__init__.py
aegis-runtime/debate/aegis_debate_runtime/operational_skill.py
aegis-runtime/debate/tests/test_debate_policy_real_worker_contract.py
aegis-runtime/debate/tests/test_phase25a_debate_role_operational_skills.py

runtime_test_reports/PHASE_25A_DEBATE_ROLE_OPERATIONAL_SKILLS_PATCH_PLAN.md
runtime_test_reports/PHASE_25A_DEBATE_ROLE_OPERATIONAL_SKILLS_ACCEPTANCE_REPORT.md
```

## Files Removed

```text
aegis-master-kit/organization/departments/debate/DEBATE_LEADER_CONTRACT.md
aegis-master-kit/organization/departments/debate/DEBATE_WORKER_CONTRACT.md
aegis-master-kit/organization/departments/debate/DEBATE_WORKER_CAUSAL_STATE_CONTRACT.md
aegis-master-kit/organization/departments/debate/DEBATE_ADJUDICATOR_CAUSAL_STATE_CONTRACT.md
aegis-master-kit/organization/departments/debate/ADJUDICATION_AND_CAUSAL_OUTPUT_RULES.md
```

## Local Adaptation

One existing Debate runtime test still referenced the removed `DEBATE_WORKER_CONTRACT.md`.

The test was updated to read `DEBATE_WORKER_OPERATIONAL_SKILL.md` and preserve the same semantic check:

- `worker_local_causal_state` is required;
- `route_priority` is required;
- `expand_priority` is required;
- local causal state remains the compact authoritative stance representation for later turns.

## Commands Run

```powershell
py -3.13 .\apply_phase25a_patch.py --repo-root C:\Users\playm\Documents\self-git\aegis

cd C:\Users\playm\Documents\self-git\aegis
py -3.13 -m venv .venv-debate-skill-phase25a
.\.venv-debate-skill-phase25a\Scripts\python.exe -m pip install -U pip
.\.venv-debate-skill-phase25a\Scripts\python.exe -m pip install -e ".\aegis-runtime\debate[dev]"
.\.venv-debate-skill-phase25a\Scripts\python.exe -m compileall .\aegis-runtime\debate\aegis_debate_runtime
.\.venv-debate-skill-phase25a\Scripts\python.exe -m pytest .\aegis-runtime\debate\tests\test_phase25a_debate_role_operational_skills.py -vv
.\.venv-debate-skill-phase25a\Scripts\python.exe -m pip install -e ".\aegis-router[dev]"
.\.venv-debate-skill-phase25a\Scripts\python.exe -m pytest .\aegis-runtime\debate -vv
git diff --check
git status --short
```

## Test Results

### Compile

```text
compileall: passed
```

### Targeted Phase 25A Test

```text
20 passed in 0.15s
```

### Full Debate Runtime Suite

```text
43 passed in 0.25s
```

### Hygiene

```text
git diff --check: passed
generated pycache/pytest cache cleanup: completed
repo-local venv: .venv-debate-skill-phase25a, ignored by git
```

## Boundary Checks

- Leader skill requires Worker skill installation.
- Worker output must prove Worker skill receipt/application.
- Worker local causal state is mandatory.
- Route priority and expand priority are mandatory.
- Worker final adjudication attempt is rejected.
- Worker global truth claim is rejected.
- Equipoise/developer decision is preserved.
- `final_report.causal_chain` is required in addition to `final_report.causal_result`.
- Complete causal package is required.
- Superseded role contracts are removed.
- No router or top-level topology change was introduced by Phase 25A.
- No production store write, remote push, PR, merge, release, deployment, or global causal truth merge was performed.

## Notes

The first full Debate runtime attempt failed during collection because the Phase 25A venv initially did not include `aegis_router`, which is required by the existing router-integrated Debate closure test. Installing the local router package into the same venv resolved that environment issue.

After applying Phase 25A, one existing test still referenced the removed Worker contract file. The test was updated to validate the equivalent Worker operational skill file.
