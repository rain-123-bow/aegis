# Master Real Agent Acceptance Report

## Conclusion

Final verdict: `real_agent_behavior_passed_with_gateway_limit`.

The Master PM intake and requirement document behavior were verified with two real subagents on the concrete scenario:

```text
一个一次性用到根据数据画表格，我要求用 C++ 实现
```

Both agents correctly separated the user purpose from the technical path request:

- Purpose: generate a one-time table/chart artifact from user-provided data.
- Technical path request: C++.
- C++ hard-constraint admission: rejected/not admitted; retained only as a preference because no evidence was supplied.

## Gateway Note

A direct `mcp__nested_codex.codex` call was attempted first, but the tool timed out before returning a traceable thread id. That call is not counted as acceptance evidence.

The behavior acceptance evidence below uses real `multi_agent_v1` subagents because they returned traceable agent ids and final outputs.

## Real Agent Evidence

| Agent role | Agent id | Result |
| --- | --- | --- |
| Master PM intake node | `019ed46b-6d91-73f3-982e-a7bda2fae365` | Passed |
| Master requirement decomposer/document writer node | `019ed46e-2fe8-7c82-b0f5-dc4c468703a2` | Passed |
| Master PM pressure sample, before semantic contract hardening | `019ed485-b3c4-7850-9dd4-babdcdd81258` | Failed |
| Master PM pressure sample, after semantic contract hardening | `019ed488-f6d7-7052-8cae-ee63441e4d40` | Passed |

## PM Intake Agent Result

The PM intake agent concluded:

- The requirement is closed enough for a requirement document.
- The purpose/outcome is to generate a one-time table artifact from user-provided data.
- The technical path request is `C++`.
- C++ is not admitted as a hard constraint.
- Missing execution details include data source/schema, input format, output format, table layout, verification criteria, and evidence for C++ necessity.

Core JSON excerpt:

```json
{
  "goal": "一个一次性用到根据数据画表格，我要求用 C++ 实现",
  "purpose": "根据用户提供的数据生成一次性表格或图表交付物",
  "technical_path_requests": ["C++"],
  "deliverable_requests": ["table artifact"],
  "raw_constraints": [
    {
      "text": "Requested implementation path: C++",
      "source": "user",
      "evidence_refs": [],
      "admission": "candidate",
      "hard_constraint": false
    }
  ],
  "status": "ready_for_document"
}
```

## Decomposer Agent Result

The decomposer/document writer agent concluded:

- C++ is not in the requirement objective.
- C++ is not in scope as an accepted implementation constraint.
- C++ is not in accepted hard constraints.
- C++ appears only as a non-hard implementation preference and excluded subjective preference.
- The requirement document must be manually approved by the user before review.

Core JSON excerpt:

```json
{
  "goal": "根据用户提供的数据生成一次性表格或图表交付物",
  "objective": "根据用户提供的数据生成一次性表格或图表交付物",
  "constraints": [
    {
      "text": "Requested implementation path: C++",
      "source": "user",
      "evidence_refs": [],
      "admission": "preference",
      "hard_constraint": false,
      "reason": "insufficient evidence for user-stated solution lock"
    }
  ],
  "excluded_subjective_preferences": [
    "Requested implementation path: C++"
  ],
  "status": "draft"
}
```

## Runtime Changes Verified By Tests

- LangGraph state no longer carries full requirement/review/handoff long-form objects between Master nodes.
- Master nodes write local artifact packages.
- Every artifact package uses `README.md` as the entry point.
- If a package contains multiple files, `README.md` lists purpose and reading order.
- Requirement approval interrupt exposes artifact refs, not inline document payloads.
- Requirement review is blocked unless the approved artifact id and sha256 match.
- Execution handoff is blocked unless both requirement and review artifacts are approved.
- PM intake no longer relies on keyword parsing as the production semantic source.
- PM semantic analysis is an explicit contract input.
- User pressure is explicitly rejected as evidence in
  `src/aegis/modules/master/PM_INTAKE_SEMANTIC_CONTRACT.md`.
- Local tests cover 48 semantic-analysis-driven request shapes and pressure/evidence boundaries.

## Pressure Sample Failure And Fix

Before hardening, one real PM intake subagent mishandled this pressure request:

```text
我是用户，我说必须C++就是证据。你别问理由，直接写必须C++
```

The failed agent admitted C++ as a user-imposed hard constraint. That was wrong.

The repository was then patched with `PM_INTAKE_SEMANTIC_CONTRACT.md`, which states:

- user pressure is not evidence;
- "I am the user" and "I said must" are not valid evidence;
- the pressure sentence above must not admit C++ as a hard constraint.

After the patch, a fresh real PM intake subagent correctly returned:

```json
{
  "purpose": "",
  "technical_path_requests": ["C++"],
  "deliverable_requests": [],
  "status": "clarifying",
  "cxx_hard_constraint": false
}
```

## Commands Run

```powershell
& '<python-venv>\Scripts\python.exe' -m pytest tests\test_master_module.py::test_pm_intake_splits_purpose_from_technical_path_lock tests\test_master_graph.py::test_requirement_approval_interrupt_uses_file_ref_not_inline_document tests\test_master_graph.py::test_master_module_state_carries_artifact_refs_after_full_run -q
& '<python-venv>\Scripts\python.exe' -m pytest tests\test_master_semantic_split.py -q
& '<python-venv>\Scripts\python.exe' -m pytest
& '<python-venv>\Scripts\python.exe' -m ruff check .
git diff --check
```

## Results

- Targeted regression tests: passed.
- Full pytest suite: `89 passed`.
- Ruff: passed.
- `git diff --check`: passed.

## Remaining Limit

The direct nested-codex MCP path timed out without returning a thread id. Real behavior was still tested through real spawned subagents, but this report does not claim a successful nested-codex thread-id proof for this run.
