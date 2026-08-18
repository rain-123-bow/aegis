# Master 模块设计

本文件采用现行 Master 模型。完整约束见
[`docs/AEGIS_ARCHITECTURE_CONTRACT.md`](../../../AEGIS_ARCHITECTURE_CONTRACT.md)。

```mermaid
flowchart TD
  A["Project Gate"] --> B["Master 编写需求"]
  B --> C["独立 reviewer 审核需求"]
  C --> D{"用户确认并冻结需求？"}
  D -- "否" --> B
  D -- "是" --> E["Master 编写实现方案"]
  E --> F["同一独立 reviewer 审核需求与方案"]
  F --> G{"用户确认并冻结方案？"}
  G -- "否" --> E
  G -- "是" --> H["Master 编码并记录因果事实"]
  H --> I["Master 自测"]
  I --> J["Provision + Preflight"]
  J --> K{"用户持久化授权启动？"}
  K -- "否" --> Z["等待授权"]
  K -- "是" --> L["A-F 工程审核图"]
```

## 边界

Master 是单一语义执行者，直接完成需求、实现方案和代码。Master 不得把最终语义产出委托给
subagent。独立 reviewer 只负责对抗审核。用户负责冻结需求、方案、scope 和启动授权。

Master 不属于 A-F LangGraph。A-F 运行期间所有冻结输入禁止变化。
