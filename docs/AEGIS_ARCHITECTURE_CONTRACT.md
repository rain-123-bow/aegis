# Aegis 统一架构契约

状态：现行规范
适用平台：Windows 11、PowerShell 7、Python 3.13
优先级：本文件高于旧版 Master/LangGraph 设计文档和静态示例配置。

## 1. 目标与权威

Aegis 通过职责分离、独立审核、语义对抗、持久证据和 fail-closed 控制，形成可恢复、可追责的工程治理系统。

权威从高到低：

1. 用户持久化确认的需求、实现方案、scope 和启动授权。
2. 冻结文档、源码提交、Seal、reasoning ledger 事实及其哈希绑定。
3. Coordinator 生成的机器状态、manifest、checkpoint 和证据索引。
4. 独立 reviewer 与 A-F 的结构化结论。
5. 人类可读报告和 README。
6. 聊天上下文、线程记忆和自然语言转述。

低层材料不能覆盖高层事实。

## 2. Master 模块

Master 是用户意图的长期语义执行者，不是 LangGraph 节点。Master 必须直接完成需求文档、实现方案、代码、代码对应的因果事实、实现自测和 A-F 启动前交接。

Master 不得把最终语义产出委托给 subagent。subagent 只能执行独立审核、研究或取证；Master 必须读取原始产物，不能依赖窗口转述。

同一个独立 reviewer 可以审核需求和实现方案。Reviewer 必须与 Master 保持线程、职责和结论独立；实现方案审核必须同时读取冻结需求文档。

```text
Project Gate
→ Master 编写需求
→ 独立 reviewer 审核
→ 用户确认并冻结需求
→ Master 编写实现方案
→ 独立 reviewer 审核需求与方案
→ 用户确认并冻结实现方案
→ Master 编码并记录因果事实
→ Master 自测
→ provision / preflight
→ 用户持久化授权启动
→ A-F
```

没有 reviewer 时不得降级。质量、预算或证据降级必须获得用户明确授权。模型正确性边界只覆盖 Codex/GPT；非 GPT 模型的理解偏差不属于验收范围。

## 3. A-F 工程审核图

| 节点 | 职责 |
|---|---|
| A | 根据冻结需求和实现方案编写测试方案 |
| B | 独立审核测试方案 |
| C | 把已批准测试方案转换为受控执行请求；Coordinator 在真实目标环境执行 |
| D | 审核执行完整性、原始证据和结论闭合 |
| E | 基于已审核证据编写最终测试报告 |
| F | 审核整个工程：需求、方案、代码、测试、证据、reasoning ledger、Seal 和流程完整性 |

```text
A → B
B FAIL → A
B PASS → C
C FAIL → END
C PASS → D
D FAIL → C
D PASS → E
E FAIL → END
E PASS → F
F PASS → SUCCEEDED
F FAIL → TERMINATED + Master review + user handoff
```

E 失败不得进入 F。F 已执行但审核失败时：

```text
workflow_state = TERMINATED
engineering_verdict = FAIL
delivery_eligible = false
master_review_status = PENDING | CONFIRMED | DISPUTED
```

Master 只能验证 F 结论结构、证据真实性和索引完整性。Master 不得修改、隐藏、降级或覆盖 F 的工程结论。存在分歧时，双方结论与证据一并提交用户。

F 必须写入 `FINAL_REVIEW_VERDICT.json`，明确给出结论、原因和证据索引。Coordinator 必须校验其 verdict 与 F 返回状态一致，并封存文件哈希与证据 ID；缺失或不一致时不得形成 F 终态。

## 4. 运行冻结和恢复

A-F 运行期间，需求、实现方案、代码、runtime behavior scope、相关 reasoning ledger 事实和绑定 Seal 禁止变化。

Coordinator 必须在节点边界复核全部冻结哈希，并在 Windows 上通过递归目录变更日志捕获节点内“修改后还原”。发现变化后：

1. 立即终止当前 workflow run；
2. 保存变化路径、旧新哈希、发现时间和可用进程证据；
3. 标记 `workflow_state=TERMINATED`、`engineering_verdict=INVALIDATED`；
4. Master 要求用户说明变化原因；
5. 原因未记录前禁止重启。

原因通过 `aegis.frozen_input_mutation_reason.v1` 封存，绑定用户确认 ID、原因文件路径、大小和 SHA-256。mutation 终止状态和未解释 marker 在同一 SQLite 事务中持久化；删除或篡改 `RUN_STATE.json` 投影不能解除阻塞。存在任何 `REQUIRES_USER_REASON` 的同项目 run 时，新 run 的 preflight 必须失败；记录原因后只解除启动阻塞，不恢复旧 run，也不改变其失败结论。

Master 修复代码后：

- 需求和实现方案哈希均未变化：保留已批准测试方案，新 `workflow_run_id` 从 C 开始；
- 需求或实现方案任一变化：新 run 从 A 开始；
- 旧 run、测试方案、结论和证据不可覆盖。

角色线程是项目级长期资源。故障线程可关闭并重建；旧线程必须标记 `retired`，新线程只能从冻结 artifact、role skill 和 reasoning ledger 恢复。

## 5. 语义问题与重复拒绝

审核问题的基础单元为：

```text
前提集合 + 推理关系 + 结论 + 必需证据 + 未排除替代解释
```

Reviewer 输出 `semantic_issue_id`、受质疑前提和结论、缺失证据、未排除替代解释、闭合条件，以及与历史问题的 `predecessor_issue_ids` 映射。对每个历史问题还必须输出 GPT 语义裁决回执：`REPEATED_UNRESOLVED|RESOLVED|SUPERSEDED`、关联当前问题、理由和证据。Coordinator fail closed 校验覆盖和双向映射，不以文本哈希代替语义。改 ID、调顺序或改写措辞不能自动视为修复。

相同推理缺口被再次提交，且没有补证、收窄结论、修正推理或排除替代解释，视为重复拒绝修复。改写措辞、重复解释和更换 blocker ID 不构成修复。

## 6. 身份模型

- `project_id`：项目永久身份；
- `seal_chain_id`：一条 Seal 链的永久身份；
- `workflow_run_id`：一次 A-F 审核运行；
- `thread_id`：项目内某角色的长期 Codex 线程；
- `attempt_id`：节点的一次执行或恢复尝试；
- `semantic_issue_id`：一个稳定的基础语义问题。

不得使用同一个 `run_id` 同时表达 Seal 链、LangGraph checkpoint 和一次业务运行。

## 7. 存储边界

项目目录中的 `.aegis/`只允许承载 reasoning ledger 实例，用于高效检索项目因果结构和客观现实条件。

`.aegis/`禁止存放 LangGraph checkpoint、RUN_STATE、agent registry、Codex 原始响应、TraceRelay journal、临时文件和普通运行缓存。

```text
<local-runtime-root>/<project-id>/
  project_state/
    runtime-authority.json
    dynamic_agent_registry.json
    dynamic_agent_registry.sqlite3
    checkpoints.sqlite3
    instruction_receipts/
  runs/<workflow-run-id>/
    RUN_STATE.json
    manifest.json
    artifacts/
      master/
      reviewers/<stage>/
      graph/A/
      graph/B/
      graph/C/
      graph/D/
      graph/E/
      graph/F/
      evidence/
    responses/
    tracerelay/
    instruction-receipts/
```

所有 artifact 必须是本地 Windows 路径。大段内容通过文件传递；消息只传路径、哈希、身份和最小控制字段。

`runtime-authority.json`、SQLite authority row、runtime-scope policy、受保护远程 witness 绑定同一永久 `runtime_authority_id`。生产运行不允许隐式初始化；anchor 或 SQLite 任一缺失即视为权威状态删除并终止。

## 8. 动态 Agent Registry

版本库中的 `config/agent_registry.json`只保存 schema、角色模板和默认模型策略，不得保存真实 thread ID 或特定项目路径。

动态 registry 以 SQLite 事务状态为权威，JSON 只作可读投影。它记录 project ID、role key、thread ID、lifecycle、model、reasoning effort、role skill 名称/版本/SHA-256、创建/更新时间、退役原因和替代线程关系；revision 更新使用 CAS。

线程不得跨项目复用。同一项目只允许一个 active A-F Coordinator 实例。Lease 绑定 run ID、实例 UUID、PID、进程创建时间和 heartbeat；同一 run ID 也不得双持。只有确认旧进程身份已死亡后才允许 CAS takeover；权限或探测错误属于 `UNKNOWN`，必须 fail-closed。一次运行中不得改变模型或 reasoning effort。Ultra 禁止。

## 9. Skill 契约

每个角色必须加载共享质量/value skill和角色专属 skill。Coordinator 必须绑定并持久化 skill 名称、版本、内容 SHA-256、角色映射和注入回执。Developer instruction 内含仅由该层提供的 challenge；GPT 必须在每个 turn 前写入精确 `aegis.gpt_instruction_receipt.v1`，Coordinator 再封存。缺失或不匹配即失败。仅在 prompt 中声称“已加载”不构成证据。

## 10. Reasoning Ledger 与 Context Pack

`.aegis/`中的 reasoning ledger 是项目因果检索实例。Master 在 A-F 启动前按当前工程任务导出完整相关 context pack；“完整”指覆盖需求、实现方案、runtime scope、代码因果、已知反证、环境事实和待决 warning。

每个 workflow run 生成不可覆盖的基础 context pack，包含 project/task/role 身份、查询、active 项、原因项、边、stale/invalid 警告、证据路径、ledger revision、生成时间和 SHA-256。Coordinator 以只读 repeatable-read 事务直接导出 live ledger snapshot，逐项核对 pack item/edge，并封存 snapshot bytes；agent 自报 revision、coverage 或 hash 不能构成来源证明。

角色可以获得基础 pack 的角色视图，但不得因此失去直接读取冻结事实和原始证据的能力。A-F 期间所有角色只能读取 Coordinator 绑定并校验哈希的冻结 pack，禁止查询在线 ledger。pack 范围不足时必须失败，不能动态补查。相关事实变化后生成新版本，不覆盖旧 pack，并从 A 启动新 run。

## 11. Runtime Behavior Scope

凡可能改变生产运行时编译结果、启动方式、执行路径、输入解释或外部行为的文件，均属于 `runtime_behavior_scope`。

包括生产源码、构建描述、依赖锁、代码生成输入、生产入口、运行配置、插件清单、迁移、运行资源、打包与部署定义。

排除 demo、test、example、benchmark、文档、日志、缓存和构建产物。若生产路径实际导入、加载或打包这些目录中的文件，则该文件不能排除。

Scope 采用 `Master 提案并写入 → reviewer 审核 → 用户确认 → Coordinator 解析并执行`。固定 decision manifest 必须绑定 canonical policy SHA-256、project ID、review report、用户确认 statement、confirmation ID 和 `APPROVED` 决定；hash 形状的占位字符串无效。

Seal 必须绑定 scope policy 哈希、精确 resolved manifest 哈希、project ID、seal chain ID、sequence 和 previous seal。Scope 变更必须产生新版本和新 Seal，历史不可覆盖。

## 12. Test Evidence Manifest

Test/demo 不进入 runtime behavior Seal。C 只提交 `aegis.test_execution_request.v3`，且必须逐值匹配审核通过方案中的 `aegis.test_execution_policy.v2`。Policy 明示完整有效环境；Coordinator 不继承宿主环境，拒绝 shell、内联代码和未绑定入口，锁定并前后复核 cwd、可执行文件、全部输入，通过带进程数、内存、CPU 时间、超时和关闭即终止约束的 Windows Job Object 执行，并生成不可由 C 编辑的 `aegis.test_execution_receipt.v3` 和 `aegis.test_evidence_manifest.v2`。

测试结论不能脱离该 manifest 单独成立。

## 13. Seal 最新状态见证

项目使用远端 Git 受保护引用保存最新 project ID、seal chain ID、sequence、Seal 和对应提交。Seal 记录时必须读取真实 HEAD、拒绝 scoped dirty/untracked 路径，并确认全部 runtime entry 属于该 commit。Preflight 必须 fetch 并验证 `witness.git_commit == seal.git_head_before_record == HEAD`。远端不可访问、引用缺失或本地状态落后时 fail closed。禁止静默离线降级。

所有 Git 调用必须位于同一个已验证 Git 运行时锁会话内。会话按 scope policy 固定 launcher SHA-256 与完整 Git 依赖闭包 SHA-256；Windows 文件与祖先目录共享锁从校验前持续到最后一次本地或远端 Git 调用返回，禁止校验后替换可执行文件、DLL 或子命令。

`config/seal_witness.json` 使用 `aegis.remote_seal_witness_config.v3`，直接封存 canonical SSH repository URL、protected ref、SSH identity 绝对路径与 SHA-256；禁止 remote alias。SSH 强制使用锁定 Git 发行版内的 `usr/bin/ssh.exe`、锁定 identity、`config/git_ssh_known_hosts`、Ed25519 host key、空 HOME、无代理配置。默认 identity、agent、PKCS#11 与 security-key provider 全部禁用。远程读取在一次性 bare repository 中执行，不读取项目 `.git/config`。引用指向的提交必须包含仓库根文件 `aegis-seal-witness.json`；该文件使用 `aegis.remote_seal_witness.v2`，绑定 project ID、seal chain ID、sequence、Seal、scope policy SHA-256、resolved manifest SHA-256、runtime authority ID 和受治理分支提交。Witness分支提交与受治理分支提交是两个不同对象；前者携带见证文件，后者由其中的 `git_commit` 指向。

## 14. 命令、边界与成功标准

本地无外部费用测试：

```powershell
python -B -m unittest discover -s test -p "test_*.py"
```

真实 Codex、App Server、TraceRelay、远端推送和任何可能产生费用的操作必须另行获得用户授权。

实现成功要求：E 失败机械阻止 F；F verdict、workflow state、Master review 分离；运行状态迁出 `.aegis/`；registry 动态化；skill 有哈希绑定；冻结输入变化立即终止；未变需求/方案可复用测试方案从 C 开始；runtime scope 不再硬编码为 `src/include`；测试结论绑定 evidence manifest；本地测试通过；真实外部验收边界明确。
