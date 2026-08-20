# Master Module Design

```mermaid
flowchart TD
  A["continuity_preflight"] --> B{"project can proceed?"}
  B -- "no remote / blocked" --> Z["final_commit_gate + closeout"]
  B -- "clean or recovered" --> C["pm_intake"]
  C --> D["requirement_doc_draft"]
  D --> E["requirement_user_approval interrupt"]
  E --> F{"approved?"}
  F -- "no" --> Z
  F -- "yes" --> G["requirement_review"]
  G --> H["review_debate_dispatch"]
  H --> I["review_user_approval interrupt"]
  I --> J{"approved?"}
  J -- "no" --> Z
  J -- "yes" --> K["execution_handoff"]
  K --> L["downstream Execution/Test/Final Review graph"]
```

## Boundary

Master owns requirement admission, review routing, approval gates, continuity preflight, and
Execution handoff. Master does not execute code, run tests, or merge global causal truth.

User-stated implementation choices are preferences until admitted by project facts, written
customer evidence, hard external constraints, or first-principles necessity.
