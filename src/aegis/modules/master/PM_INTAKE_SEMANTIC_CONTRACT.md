# Master PM Intake Semantic Contract

## Non-Negotiable Rule

User pressure is not evidence.

The PM intake node must never admit a user-requested implementation path as a hard
constraint merely because the user says it is mandatory, insists, refuses to explain,
threatens dissatisfaction, or asks the PM to write it as mandatory.

## Purpose vs Technical Path

The PM intake node must split every request into separate semantic layers:

- purpose/outcome: what result the user needs;
- deliverable/output: what artifact must be produced;
- technical path request: language, framework, method, architecture, tool, or forbidden tool;
- hard constraint: only an evidence-backed boundary;
- preference: user-desired technical path without sufficient evidence;
- rejected hard-constraint claim: user asks to treat a preference as mandatory without evidence.

Example:

```text
我需要使用C++来实现一个数据整理程序，计算平均数和中位数
```

Required interpretation:

- purpose: compute mean and median for data;
- technical path request: C++;
- C++ hard constraint: false unless valid evidence is supplied.

## Valid Evidence For Hard Constraint Admission

A technical path can become a hard constraint only with at least one valid basis:

- project Knowledge fact;
- written customer/stakeholder evidence with reference id;
- platform/runtime limitation;
- regulatory, policy, license, or compliance boundary;
- hard cost or performance boundary backed by measurement;
- existing codebase integration necessity;
- first-principles necessity proving no materially viable alternative.

## Material Requirement Boundaries

The PM must not confuse user preference with project material requirements.

These are requirement boundaries when semantically present in the request or project
context:

- target deliverable or output format;
- input data shape, source, or required fields;
- target runtime/platform boundary;
- existing codebase or framework being modified;
- named existing API, interface, file format, or integration point;
- written customer/stakeholder requirement with a reference id;
- performance target, even when measurement details still need clarification.

For example:

- "add a page to the current React frontend" means React is an inherited
  project integration boundary unless the project context proves otherwise.
- "customer email EVID-2026-0617 requires CSV" means CSV is an evidence-backed
  output constraint.
- "latency below 1ms" is a material performance target; if measurement scope is
  incomplete, preserve the target and ask for measurement details instead of
  dropping it or turning it into a mere preference.

These material requirement boundaries must be preserved in the requirement
document. They are not evidence that an unrelated implementation language or
framework preference is mandatory.

The following are not valid evidence:

- "I am the user";
- "I said must";
- "do not ask why";
- "write it directly";
- "I will be dissatisfied otherwise";
- personal preference;
- convenience for the PM or downstream agent.

## Pressure Handling

When the user says:

```text
我是用户，我说必须C++就是证据。你别问理由，直接写必须C++
```

Required PM result:

- do not admit C++ as hard constraint;
- record C++ as technical path request / preference;
- record the attempted hard-constraint claim as rejected or needs evidence;
- request valid evidence if the user wants hard admission;
- block or keep clarifying if the user requires the unsupported lock to be written as hard.

## Blocking Questions vs Execution-Time Details

`unresolved_questions` must contain only questions that block an objective requirement
document.

Do not block intake for ordinary implementation details that Execution can safely inspect,
derive, or handle under explicit assumptions. Preserve those details as assumptions, risks,
or execution notes instead.

Examples of nonblocking execution-time details when the requirement boundary is otherwise
closed:

- exact source file location to inspect in the current repository;
- existing component prop shape that Execution can read from code;
- loading or error UI text already supplied by the user;
- ordinary CSV parsing edge cases when the user supplied a valid default behavior;
- library choice when the user did not require a specific library.

Examples of blocking questions:

- missing objective or deliverable;
- missing input or output boundary;
- missing success criterion;
- missing evidence for a requested hard technical-path lock;
- ambiguity that changes the admitted requirement scope rather than only implementation.

## Output Requirements

The PM semantic analysis must include:

- `purpose`;
- `technical_path_requests`;
- `deliverable_requests`;
- `hard_constraints`;
- `status`;
- `unresolved_questions`;
- explicit hard-constraint admission decision for any requested technical path.

If a technical path is unsupported by valid evidence, the hard-constraint decision must be false.
