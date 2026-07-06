# Aegis Skills

本目录存放 Aegis 本地 agent skills。

## 全局最高优先级

所有 Aegis agent 执行任何角色 skill 前，必须先读取并遵守：

```text
aegis_global_quality_law/SKILL.md
```

该 skill 是本地最高优先级运行法，适用于所有 agent：图外 Master、LangGraph 图内节点、临时审查者、执行者、报告者、最终审核者、preflight、provisioner、project gate。

如果任一角色 skill 与 `aegis_global_quality_law` 冲突，必须优先遵守质量优先原则，并在当前 agent 的可写产物、报告或回复中记录冲突。

质量排序固定为：

```text
真实性 > 完整性 > 证据闭环 > 可复核 > 可维护 > 速度 > 顺滑体验 > 完成感
```

速度只在质量门槛满足后才有价值。

## 通用运行约束

- 不得用“看起来完成”替代真实完成。
- 不得用假设补齐缺失输入。
- 不得把未执行、未验证、未覆盖的内容写成已完成。
- 不得为了通过、速度、用户体验、交付顺滑度降低证据和质量标准。
- 不得默认一次性创建全链路 subagent；资源必须按需懒加载。
- `status` 只属于显式使用该协议的流程，不是所有 agent 的通用完成协议。
- 任何 agent 都不得因为输入 JSON 中存在 `status=false` 而自动拒绝执行。
- `artifact_path` 的语义由当前 role skill 或 workflow 契约决定，不得把 LangGraph 共享目录语义强行套用到图外 Master skill。
- 所有关键结论必须有证据闭环。
- 每个 agent 必须进行质量自检；有 `artifact_path` 且可写时输出 `quality/<role_or_node_name>_quality_self_check.json`，否则在报告或回复中给出等价质量自检摘要。

## 目录结构

```text
skills/
├── README.md
├── aegis_global_quality_law/
│   └── SKILL.md
├── aegis_final_reviewer/
│   └── SKILL.md
├── aegis_master_implementation_code_writer/
│   └── SKILL.md
├── aegis_master_implementation_plan_designer/
│   └── SKILL.md
├── aegis_master_project_gate/
│   └── SKILL.md
├── aegis_master_requirement_designer/
│   └── SKILL.md
├── aegis_master_subagent_provisioner/
│   └── SKILL.md
├── aegis_master_test_workflow_preflight/
│   └── SKILL.md
├── aegis_test_executor/
│   └── SKILL.md
├── aegis_test_plan_author/
│   └── SKILL.md
├── aegis_test_plan_reviewer/
│   └── SKILL.md
├── aegis_test_report_writer/
│   └── SKILL.md
├── aegis_test_result_reviewer/
│   └── SKILL.md
```
