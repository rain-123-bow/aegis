# First Phase Scope

## Goal

Build a minimal Aegis prototype that lets a Codex Master understand top-level organization rules and communicate with generated agents through a local router.

## Included

- Master constitution and governance rules.
- Top-level organization model.
- Placeholder departments.
- A linear topology example: `001 -> 002 -> 003`.
- A local Python router with MCP-style tools.
- Minimal tests for router behavior.

## Excluded

- Full department internals.
- Full causal/knowledge/archive implementations.
- Automatic code submission.
- Automatic branch merging.
- OpenAI Agents SDK dependency.
- Complex multi-agent debate workflows.

## Success criteria

A Master should be able to:

1. Read `aegis-master-kit`.
2. Understand its own constitution and responsibility boundary.
3. Build a top-level department structure.
4. Create or address department leaders.
5. Use the router to register agents and exchange messages under visibility rules.
