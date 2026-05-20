# Phase 25A Debate Role Operational Skills Patch Plan

## Goal

Convert Debate Leader and Debate Worker role behavior from scattered role contracts into two explicit role-bound operational skills:

```text
DEBATE_LEADER_OPERATIONAL_SKILL.md
DEBATE_WORKER_OPERATIONAL_SKILL.md
```

Add a local demo validator that enforces the skill relationship:

```text
Leader creates Worker -> Leader must install Worker skill -> Worker output must prove skill receipt/application -> Leader validates Worker skill compliance before adjudication.
```

## Scope

In scope:

- add Debate Leader operational skill;
- add Debate Worker operational skill;
- add Debate Leader/Worker skill enforcement contract;
- remove old superseded role-contract documents;
- update Debate department README and MANIFEST;
- add `aegis_debate_runtime.operational_skill` validator;
- add targeted Phase 25A tests;
- add `aegis-debate-skill` console script.

Out of scope:

- production Debate lifecycle closure;
- production nested-Codex supervision;
- remote push, PR, merge, release, deployment;
- global causal truth merge;
- Archive / Knowledge / Causal store writes;
- changing router or top-level topology.

## Superseded files removed

```text
aegis-master-kit/organization/departments/debate/DEBATE_LEADER_CONTRACT.md
aegis-master-kit/organization/departments/debate/DEBATE_WORKER_CONTRACT.md
aegis-master-kit/organization/departments/debate/DEBATE_WORKER_CAUSAL_STATE_CONTRACT.md
aegis-master-kit/organization/departments/debate/DEBATE_ADJUDICATOR_CAUSAL_STATE_CONTRACT.md
aegis-master-kit/organization/departments/debate/ADJUDICATION_AND_CAUSAL_OUTPUT_RULES.md
```

## Validation

Expected targeted validation:

```powershell
py -3.13 -m venv .venv-debate-skill-phase25a
.\.venv-debate-skill-phase25a\Scripts\python.exe -m pip install -U pip
.\.venv-debate-skill-phase25a\Scripts\python.exe -m pip install -e ".\aegis-runtime\debate[dev]"
.\.venv-debate-skill-phase25a\Scripts\python.exe -m compileall .\aegis-runtime\debate\aegis_debate_runtime
.\.venv-debate-skill-phase25a\Scripts\python.exe -m pytest .\aegis-runtime\debate\tests\test_phase25a_debate_role_operational_skills.py -vv
```

Expected targeted result:

```text
20 passed
```

## Acceptance label

```text
accepted_phase25a_debate_role_operational_skill_enforcement
```


## v0.2 update

- Validator, skill, and tests now require `final_report.causal_chain` in addition to `final_report.causal_result`.
- Apply script writes README updates with LF newlines to avoid CRLF drift under Windows.

## v0.3 update

Fix the validator missing-value helper and preserve final_report.causal_chain enforcement.
