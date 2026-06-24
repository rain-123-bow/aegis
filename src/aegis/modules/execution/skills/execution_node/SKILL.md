# Execution Node Operational Skill

Use this skill when acting as Aegis Execution Node inside Execution Subgraph v2.

## Core Rule

Plan first, submit the plan for Review, implement only after receiving an approved review artifact.

## Must Do

1. Read the Master handoff artifact through its `README.md`.
2. Preserve purpose, hard constraints, rejected constraints, known limits, and evidence refs.
3. Produce an implementation plan artifact before writing code.
4. Include `expected_file_changes.json` in the plan artifact.
5. Wait for the Review Node approval artifact.
6. Implement only within approved `code_root` and expected change ids.
7. Run simple local sanity checks and record structured evidence.
8. Output an execution causal candidate as candidate only.

## Must Not Do

1. Do not write code before approval.
2. Do not treat unsupported technical preference as a hard constraint.
3. Do not create default Execution Group, Front Agent, or Back Agent.
4. Do not write Archive, Knowledge, or Causal admitted truth.
5. Do not push, merge, release, deploy, or create PR automatically.
