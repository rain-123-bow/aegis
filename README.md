# Aegis

Aegis 是面向 Codex/GPT 的工程治理系统。它用职责分离、独立审核、冻结输入、持久证据、项目封印和失败关闭机制约束从需求到终审的全过程。

## 接管入口

按以下顺序阅读：

1. [`docs/PROJECT_HANDOFF.md`](docs/PROJECT_HANDOFF.md)：当前状态、不可丢失的设计语义、云端归档边界和后续门禁。
2. [`docs/AEGIS_ARCHITECTURE_CONTRACT.md`](docs/AEGIS_ARCHITECTURE_CONTRACT.md)：现行最高层架构契约。
3. [`docs/runtime_coordinator.md`](docs/runtime_coordinator.md)：协调器状态、恢复、冻结和证据机制。
4. [`docs/REVIEWER_AND_REASONING_LEDGER_ARCHITECTURE_SPEC.md`](docs/REVIEWER_AND_REASONING_LEDGER_ARCHITECTURE_SPEC.md)：审核者隔离与推理库第一性实现。
5. [`docs/AEGIS_RUNTIME_SCOPE_PROPOSAL.md`](docs/AEGIS_RUNTIME_SCOPE_PROPOSAL.md)：尚待最终批准的生产运行范围。

## 组件边界

- 本仓库：协调器、角色技能、运行契约、推理库、第三方运行快照和历史设计材料。
- AegisSealCore：独立私有源码仓库；本仓库只保存固定的 Windows 二进制和来源证明。
- TraceRelay：独立源码仓库；本仓库保存经过来源验证的第三方运行源码快照，不使用子模块。
- `.aegis/`：只允许保存项目特化推理库实例，不得承载运行状态或临时日志。

## 当前门禁

当前代码不等于生产就绪。`config/reasoning_ledger.json` 中项目锚点仍为空，运行范围仍是提案状态，最新推理库变更只完成静态对抗审核。真实数据库迁移、全量测试、真实外部验收、范围审核、用户结构化确认、项目封印、运行权威和受保护远程见证必须在新的受控环境中完成。
