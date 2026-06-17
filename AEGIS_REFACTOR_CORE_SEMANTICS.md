# Aegis 重构核心语义总览

状态：当前文档描述 `v0.1.2-alpha-langgraph-reset` 分支上的 LangGraph 重构语义。

日期：2026-06-17

## 1. 总体定位

Aegis 当前重构不是把旧版多 agent 路由系统简单搬迁到 LangGraph，而是把 Aegis 改造成一个以
`StateGraph` 为运行控制面的本地 git 项目治理运行时。

核心目标是：

- 用 LangGraph 控制长流程、恢复点和 human-in-the-loop。
- 用严格 schema 和显式路由约束替代软 prompt 约束。
- 用项目本地 `archive/`、`knowledge/`、`causal/` 三库保存长期项目候选状态。
- 不使用 LangGraph Store 保存项目事实或长期记忆。
- 先采用 deterministic-first 架构证明运行时边界，再逐步接入真实 LLM 节点。

## 2. 三层语义边界

### 2.1 运行控制面

LangGraph 只负责流程控制、节点状态、interrupt 和 checkpoint。

它保存的是 thread-scoped runtime state，不是项目长期事实源。

默认 checkpoint 位置：

```text
<project-root>/.aegis/runtime/checkpoints.sqlite3
```

每次 graph run 必须绑定 `thread_id`，用于恢复、inspect 和审批继续执行。

### 2.2 项目长期状态

长期项目状态只能通过项目本地三库候选写入：

```text
archive/candidates/
knowledge/candidates/
causal/candidates/
```

当前实现写入的是 candidate，不是最终真值：

- Archive candidate：记录本次 graph run closeout。
- Knowledge candidate：记录静态边界候选。
- Causal candidate：记录因果候选包。

Archive、Knowledge、Causal 的 admission 和 truth merge 不由 LangGraph Store 完成。

### 2.3 工具治理面

所有有副作用的 runtime 工具调用必须经过 `ToolGovernance`。

工具治理顺序语义是：

```text
capability check -> intent assessment -> risk gate -> optional interrupt -> execute -> audit
```

远端 push、PR、merge、release、deploy 等外部责任动作只能产生 developer interrupt，不能自动执行。

## 3. Master 模块语义

Master 不再是单一 skill 或单个 prompt，而是一个独立 runtime module。

当前 Master 模块路径：

```text
src/aegis/modules/master/
```

Master 的职责是项目治理和准入，不是代码执行：

- 做项目连续性检查。
- 与用户澄清需求。
- 形成客观需求文档。
- 等待用户手动确认需求文档。
- 触发独立需求评审。
- 必要时把争议点交给 Debate。
- 等待用户手动确认评审文档。
- 生成 Execution handoff package。

Master 明确禁止：

- 直接写代码。
- 直接运行测试。
- 直接合并全局因果真值。
- 因用户情绪、催促、满意度而降低项目完整性要求。

## 4. Master 需求准入语义

Master PM intake 的核心规则是：

```text
user pressure is not evidence
```

PM 必须把用户请求拆成不同语义层：

- purpose/outcome：用户真正要达成的结果。
- deliverable/output：需要交付的产物。
- technical path request：语言、框架、工具、实现方式等路径请求。
- hard constraint：有证据支撑的硬约束。
- preference：没有足够证据的用户偏好。
- rejected hard-constraint claim：用户要求硬锁定但证据不足的声明。

例如：

```text
我需要使用 C++ 来实现一个数据整理程序，计算平均数和中位数。
```

正确语义拆分是：

- 目的：计算数据平均数和中位数。
- 技术路径请求：C++。
- C++ 是否为硬约束：否，除非提供项目事实、客户书面证据、平台限制、性能测量或第一性必要性。

用户说“必须”“只能”“不要问为什么”不是证据。

## 5. Master 需求文档传递语义

LangGraph 节点之间不传递长文正文。

长文交付物必须落盘成 artifact package，Graph state 只传文件引用、hash 和 approval 记录。

artifact package 的入口文件必须是：

```text
README.md
```

如果 package 中有多个文件，`README.md` 必须说明：

- 每个文件的作用。
- 推荐阅读顺序。
- 哪个文件是机器可读数据。
- 哪个文件是人类可读主文档。

当前 Master artifact 包包括：

- requirement intake package
- requirement document package
- requirement review package
- execution handoff package

## 6. 用户审批语义

Master 有两个硬审批门：

1. 用户确认 objective requirement document。
2. 用户确认 independent requirement review document。

审批绑定 artifact hash。

如果用户没有确认需求文档，不能进入 Review。

如果用户没有确认 Review 文档，不能进入 Execution handoff。

审批是运行时 gate，不是 UI 说明文字。

## 7. Requirement Review 语义

Requirement Review 的核心规则是：

```text
PM output is not truth
```

Review 必须独立检查 PM 输出，不能机械复述。

Review 不能用关键词、正则或技术名列表做判断。词语如“必须”“只能”“C++”“Rust”“React”只能提示存在一个 claim，不能决定 claim 是否成立。

Review 必须基于：

- 需求语义。
- 项目 Knowledge refs。
- 第一性原理。
- 证据引用。
- 项目完整性、简洁性、一致性和可验证性。

Review 决策标签包括：

- `accept`
- `reject_as_hard_constraint`
- `request_more_evidence`
- `route_to_debate`

如果 Review 发现 PM 把无证据技术路径错误升级成硬约束，必须阻断或降级，不允许下发 Execution。

## 8. Debate 语义

Debate 是条件触发，不是固定阶段。

触发条件包括：

- Master 发现多个可辩护立场。
- Review 发现局部方案锁定但理由不足。
- Execution 发现多个 non-dominated implementation routes。

当前第一里程碑中，Debate 是 deterministic black-box node，输出 causal candidate package。

Debate 输出不是全局 Causal truth，不得直接写入全局 causal store。

## 9. Execution 语义

Execution v2 默认是单 Actor。

当前 Execution 不默认创建：

- Execution Group
- Front Agent
- Back Agent

Execution Actor 的核心语义：

- 单项目任务可以执行并产出 implementation artifact。
- 多仓库、跨项目任务必须 block。
- 发现多条非支配有效实现路线时，可以请求 Debate。
- Debate 返回后，Execution 绑定裁决结果继续。
- Execution 只能写执行 artifact 或 candidate refs，不能写三库真值。

## 10. Test 语义

Test 不只是普通节点，而是由结构化 `TestGraphSpec` 编译出的动态测试子图。

当前实现包括：

- atomic route
- parallel super-step
- integration-required flag
- barrier summary

Test 只产生 evidence/result。

Test 不做业务真值裁决，不写 Archive/Knowledge/Causal truth。

如果 parallel super-step 中一个 route 失败，当前 super-step 内其他 route 仍应完成，然后 barrier 后统一回 Execution 或进入 Final Review。

## 11. Final Review 语义

Final Review 是单 Leader node。

它的职责是审查完整链路，而不是重新执行工作。

Final Review 明确禁止：

- 创建 worker。
- 运行测试。
- 修改代码。
- 合并全局 causal truth。

Final Review 输出包括：

- `accept_for_master`
- `accept_with_scope_limit`
- `reject_to_execution`
- `request_more_evidence`
- `governance_blocker`

当前 `FinalReviewResult` 明确记录：

- `workers_created=false`
- `tests_run=false`
- `code_modified=false`
- `global_causal_truth_merge_performed=false`

## 12. Directed Flow 语义

当前合法流程边由 `aegis.graph.routing` 显式声明。

允许边：

```text
Master -> Debate
Master -> Execution
Debate -> Execution
Execution -> Debate
Execution -> Test
Test -> Execution
Test -> Final Review
Final Review -> Master closeout
```

同一 state 中可见某些字段，不代表可以任意跳转。

每条边都有：

- source
- target
- condition
- required state fields
- forbidden side effects

路由函数必须调用 routing policy 检查合法性。

## 13. LLM Node 语义

LLM 行为必须被 `LlmNodeRequest` / `LlmNodeResult` 包裹。

LLM Node 输入包括：

- role
- task
- state refs
- allowed tools
- forbidden actions
- output schema
- evidence requirements

LLM Node 输出包括：

- decision
- state_patch
- tool_requests
- evidence_refs
- self_audit
- schema_valid

默认 adapter 是 deterministic，不调用真实 LLM。

真实 LLM adapter 当前是显式占位，不默认启用。

真实 LLM 输出必须通过 schema validate 和 Tool Governance，不能直接修改三库真值或绕过工具闸门。

## 14. 项目连续性语义

Master 在开始工作前必须进行 continuity preflight。

连续性检查目标不是防御恶意用户，而是识别普通本地 git 项目是否被私自改动。

默认 continuity DB：

```text
%LOCALAPPDATA%/Aegis/continuity/continuity.sqlite3
```

记录内容包括：

- project key
- project root
- remote URL
- baseline commit
- tracked-file fingerprint
- last closeout ref

如果项目有 remote 且发现未授权 dirty 状态，设计语义是隔离当前目录并从远端恢复。

如果项目没有 remote 或无法确认恢复来源，Master 必须 block，不能破坏本地目录。

## 15. 当前验收语义

当前 repo 已有三类 Master 报告：

```text
module_test_reports/master/MASTER_MODULE_IMPLEMENTATION_REPORT.md
module_test_reports/master/MASTER_REAL_AGENT_ACCEPTANCE_REPORT.md
module_test_reports/master/MASTER_PRODUCTION_ACCEPTANCE_REPORT.md
```

最新生产级验收覆盖：

- 真实 Codex CLI PM agent 输出。
- 真实 Codex CLI Review agent 输出。
- Runtime 只有在 Review `handoff_allowed=true` 时才进入 Execution。
- PM blocking 会阻止 requirement approval、Review 和 Execution。
- Review blocking 会阻止 Execution。
- deterministic runtime closure 不能单独作为通过证据。

当前生产验收结果：

```text
4/4 scenarios passed
```

仓库测试结果：

```text
98 passed
ruff check passed
git diff --check passed
```

## 16. 当前非目标

当前重构不声明以下能力已经生产闭环：

- Production Execution implementation quality。
- 真实远端 push / PR / merge / release。
- 真实部署。
- Debate worker-level production orchestration。
- Execution Group / Front / Back 默认创建。
- Test worker-level production orchestration。
- Final Review worker production orchestration。
- Archive / Knowledge / Causal 的最终 truth admission。

这些必须在后续阶段单独实现、单独验收。

## 17. 当前核心判断

当前 Aegis 重构的核心语义是：

```text
Aegis 是一个以 Master 治理为中心、以 LangGraph 为运行控制面、
以文件 artifact 和本地三库候选为状态边界、
以显式审批、显式路由、显式工具治理为安全闸门的
本地 git 项目治理运行时。
```

它当前最重要的设计取向不是“让用户体验更顺滑”，而是：

- 项目完整性。
- 需求闭环。
- 证据准入。
- 简洁性。
- 第一性原理。
- 可恢复。
- 可审计。
- 不把软 prompt 约束当硬执行保证。
