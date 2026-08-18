# Master Module Design

This file follows the current Master model. The authoritative contract is
[`docs/AEGIS_ARCHITECTURE_CONTRACT.md`](../../../AEGIS_ARCHITECTURE_CONTRACT.md).

```mermaid
flowchart TD
  A["Project Gate"] --> B["Master writes requirements"]
  B --> C["Independent reviewer audits requirements"]
  C --> D{"User approves and freezes requirements?"}
  D -- "no" --> B
  D -- "yes" --> E["Master writes implementation plan"]
  E --> F["Same independent reviewer audits requirements and plan"]
  F --> G{"User approves and freezes plan?"}
  G -- "no" --> E
  G -- "yes" --> H["Master writes code and causal facts"]
  H --> I["Master self-tests"]
  I --> J["Provision + Preflight"]
  J --> K{"Durable user start authorization?"}
  K -- "no" --> Z["Wait for authorization"]
  K -- "yes" --> L["A-F engineering review graph"]
```

## Boundary

Master is the single semantic author of requirements, implementation plan, code, and corresponding
causal facts. It must not delegate final semantic authorship to a subagent. An independent reviewer
performs adversarial review. The user freezes requirements, plan, scope, and start authorization.

Master is outside the A-F LangGraph. Frozen inputs must not change during an A-F run.
