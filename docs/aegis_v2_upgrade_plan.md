# Aegis v2 优化升级方案（审核草案）

归档来源：
`C:\Users\playm\AppData\Local\Temp\aegis-v2-plan-review\AEGIS_V2_UPGRADE_PLAN_REVIEWED.md`

归档前来源原始 SHA-256：
`095bce98554f1060dcaccca77ea15c7100b22ab7f75dec8a304c3f56853d6348`

归档语义：本文件是 Phase 0A 仓库内规范输入。来源哈希只证明复制前原像；
冻结时必须对本文件当前 locator bytes 重新计算 `FreezeInput`。状态仍为待独立复审。

状态：`REVISED_PENDING_INDEPENDENT_REVIEW`

复审依据：`PHASE0A_CONTRACT_REVIEW.md` 当前 verdict 为 `FAIL`。本修订不构成
Phase 0A PASS、freeze 或实施授权；schema、evaluation、fixture、hash 全部同步并
再次独立复审前，唯一阶段状态是 `PHASE_0A_PENDING_FREEZE_EVIDENCE`。

适用仓库：`C:\code\aegis-20260727`

基线：Codex CLI `0.145.0`；Codex Desktop `26.721.4979.0`

## 1. 目标

Aegis v2 的唯一质量目标：

1. 禁止用速度、顺滑度、成本、形式完整度交换结论质量。
2. 通过角色价值导向错位，降低同一代理设计、实现、测试、证明自身正确时的主动放水动机。
3. 任何通过结论都必须来自可复验的事实链，不得来自代理自评分、自述完成、形式化文件存在或多数表决。
4. 保留 LangGraph 的确定性路由、持久状态、恢复、重试、事件追踪和系统级门禁。
5. 保留 Codex 用户窗口作为 Master。Master 负责用户交互、子代理生命周期和消息运输，不进入自动测试图的质量裁决。
6. 用户能够观察所有长期子代理和流程进度，但不能把主观意见注入正在执行的测试链。

质量目标不包含“必须通过”。`FAIL_PRODUCT`、`BLOCKED_ENVIRONMENT`、`NEEDS_MASTER_USER_DISCUSSION` 都是合法、高质量结果。

## 2. 威胁模型与边界

### 2.1 防御对象

- 代理因自身评价指标而产生的确认偏误、范围缩减、证据选择、极端场景回避和过早闭环。
- 作者通过修改测试口径、证据描述、门禁字段或旧产物来证明自己正确。
- 审核者只检查形式，未核查证据来源、执行环境、返回码和覆盖关系。
- 进程崩溃、桌面任务中断、重试、并发运行、代码变化导致的状态错配和旧证据复用。
- 用户在活动测试中临时改变标准，导致测试结论承载用户立场。

### 2.2 非目标

- 不把大模型视为拥有系统权限的恶意攻击者。v2 首先防御“有偏且可能尝试协议外捷径”的代理。
- 角色隔离不能只依赖提示词。至少必须满足以下一项：平台强制禁用同级协作与越权写入；或从不受 Master 自述控制的权威事件源检测全部同级通信和越权写入，并立即把 run 置为 `INTERNAL_INTEGRITY_ERROR`。
- 若当前 Codex 既不能阻止也不能可靠检测上述行为，v2 在该版本上不可实施。不得把逻辑约定表述成技术隔离。
- 防御密钥窃取、任意本机进程篡改和 OS 管理员攻击需要独立 OS 身份、容器或外部能力代理，不属于首版威胁模型。
- 不在测试图内修复产品代码。
- 不用 Aegis 替代用户的业务、法律和发布决策。

## 3. 已确认事实与现状缺口

### 3.1 当前 Codex 边界

- V2 子代理由父任务拥有，能显示在 Codex 的 `Subagents Active/Done` 面板。
- 子代理可观察到 thread、session、父任务、角色、创建时间和代次信息；静态
  schema 没有证明独立权威 `agent_id`。物理身份唯一键固定为
  `thread_id + session_id`。
- 当前外部公开调用面没有可依赖的 `spawnAgent/sendInput` 客户端 RPC。
- V2 子代理拒绝外部对其直接执行 `turn/start` 或 `turn/steer`。
- 当前仓库使用 `codex exec resume <child_thread_id>` 直接写入子线程；该方法不能作为 V2 子代理传输层。

结论：不得把“外部 LangGraph 直接驱动 V2 子代理”写成已支持能力。

### 3.2 当前仓库缺口

- `src/main.py` 无 checkpointer，使用一次性 `graph.invoke(state)`。
- A–F 的 `thread_id` 为空时仍可启动，缺少预检和创建流程。
- 节点通过命令行参数传完整 JSON；长上下文会触及 Windows 命令行长度边界。
- 状态以布尔值和自由字典为主，不能区分产品失败、环境阻塞、流程缺陷和内部错误。
- 产物使用固定文件名；缺少运行身份、基线身份、尝试身份和生产者身份。
- 仅凭文件存在、声明和弱哈希即可形成闭环；旧产物、越界路径和错误来源可能被接受。
- 环境变量可降低审核分数阈值；分数仍可能制造“高分覆盖事实缺口”的错觉。
- 重试次数固定。达到预算后结束，但不能表达“仍有真实 blocker”与“系统故障”的区别。
- CLI 在图失败时仍可能返回退出码 0。
- 本地机器路径和代理运行态被写入项目配置，破坏可移植性。
- Reasoning Ledger 与实际节点上下文、运行基线、证据闭环未形成强关联。

## 4. 候选架构

### 4.1 方案 A：修补现有 `codex exec resume`

拒绝。

原因：V2 子代理禁止外部直接输入。继续修补建立在失效前提上。

### 4.2 方案 B：删除 LangGraph，完全使用 Codex 原生多代理

拒绝。

原因：丢失确定性门禁、持久状态、可恢复路由、证据失效传播和程序化审计。模型自行编排又把运输、裁决和执行合并。

### 4.3 方案 C：把 A–F 创建为普通顶层 Codex 任务

拒绝。

原因：外部线程接口更容易驱动，但失去父任务 `Subagents` 面板、父任务所有权和用户指定的可观察结构。它不能作为能力缺失时的替代路径。

### 4.4 方案 D：双平面架构

采用。

```text
用户
  ↕
Codex Master（图外）
  ├─ 前置需求/方案对抗审核
  ├─ 用户确认测试后创建长期 A–F V2 子代理
  ├─ 执行图签发的运输动作
  └─ 向用户提供只读进度和最终讨论
             ↕ 结构化动作/原始回执
LangGraph Durable Kernel
  ├─ 状态、路由、门禁、重试、恢复
  ├─ append-only 事件日志
  ├─ 证据与基线验证
  └─ 最终机器结论
             ↕ 父任务专用发送能力
A 计划作者 ↔ B 计划审核
C 测试执行 ↔ D 证据审核
E 报告作者 ↔ F 最终审核
```

Master 是传输适配器，不是测试事实裁判。图只接受符合协议的回执，Master 不能通过自然语言直接修改门禁字段。

## 5. 不可变规则

1. A、C、E 不能关闭自己产生或被指出的 blocker。
2. B、D、F 不因代码是否通过而获得正向评价；其任务完成标准是发现并准确表达事实。
3. 一个角色不能同时承担相邻的作者与审核者。
4. 代理输出全部视为不可信输入；程序验证 schema、来源、路径、哈希、基线和状态转换。
5. 自评分、满意度分、信心值和“已完成”声明不构成门禁证据。
6. 数值分只可诊断，永不参与机器 verdict。存在未关闭硬 blocker 时，任何分数都不能通过。
7. 兼容读取旧产物时，旧 `review_pass_score` 字段统一规范为 95，拒绝低于 95 的配置；该字段只用于迁移告警，不能改变 v2 gate。新 schema 不再包含分数门禁。
8. 速度只能作为观测指标。超时、预算和重复失败只能触发暂停或升级，不能触发放宽标准。
9. 活动测试不接受用户对范围、预期结果和结论的注入。变更要求必须终止当前 run，并以新 baseline 创建新 run。
10. 用户可以请求取消。图必须先进入取消收敛状态；只有外部作业已静止，或所有仍活动/不可中断作业已被明确登记时，才形成取消终态。取消不能改写为通过或失败。
11. A–F 之间禁止直接通信。所有消息由父 Master 按图签发动作转发。
12. 产品缺陷不自动进入修复。测试尽可能继续，完成报告和终审，再交还 Master 与用户讨论。
13. 用户拥有是否接受风险和是否发布的决策权；用户决策作为追加记录，不能改写 Aegis 的事实结论。

## 6. 生命周期

### 6.1 测试前

1. 用户与当前 Codex Master 定义需求、范围、验收事实和已知限制。
2. Master 创建独立需求/方案审核子代理，完成对抗审核。
3. Master 输出待确认基线。
4. 只有用户明确确认“可以开始测试”，Master 才创建 A–F。
5. Master 捕获每个子代理的权威 `thread_id + session_id`、父任务、角色、创建时间、代次和能力探测结果，写入本地运行注册表。可选 `agent_handle` 必须同时记录观察来源，不能作为身份键。
6. 预检失败时禁止启动图。

### 6.2 子代理寿命

- A–F 是六个长期角色槽位；每个槽位的实例按不可变 baseline 分代。
- 同一 run 绑定同一 `source_generation_id`；正常情况下复用各角色当前 `instance_revision`，故障 replacement 只改变受影响角色的 revision。
- 新 baseline 必须创建全新的 A–F generation。旧实例长期保留为可观察历史，但不再接收新 run 消息。
- 该设计保留长期、可追溯的 A–F 身份，同时用新线程实现跨 run 的物理上下文隔离；提示代理忽略旧对话不作为隔离机制。
- registry 同时保存稳定 `role_slot_id`、`source_generation_id`、`instance_revision` 和每个实例的权威 `thread_id + session_id`。任何消息必须同时匹配 campaign、run、source baseline、source generation、instance revision、thread 和 session。`agent_handle` 只作带来源定位元数据。
- 子代理丢失或不可恢复时，Master 创建 replacement 并增加该 role 的 `instance_revision`。不得沿用旧身份伪装连续性。
- 替代发生在节点提交前：重启该 attempt。
- 替代发生在节点提交后：保留旧回执和来源；后续 attempt 使用新代次。
- 关闭长期子代理需要用户明确确认。

保留合同不是无限容量承诺：

- 用户在首次正式 run 前选择 `max_retained_source_generations = G`、`replacement_reserve = R` 和 `physical_instance_budget = P`，且 `P >= 6 × G + R`。
- 基础认证合同为 `G=2, R=6, P>=18`。任何更高合同必须先按 Phase 0B 相同方法完成实际实例、容量边界、真实重启和侧栏定位认证。
- source generation 以六个角色为原子组，不允许只激活部分角色。单角色故障替换不创建新 source generation；它增加该 role slot 的 `instance_revision`。
- 每次新 baseline 前，preflight 计算当前 retained generation、可用槽位和新增六实例需求。
- 物理容量计数包含：active、retained、provisional、orphan、lost-but-visible、superseded-but-visible 和 replacement；只有取得权威 close receipt 且平台确认不再占用的实例才移出。
- 创建 source generation 前要求剩余物理容量至少 6 且未超过 G；创建 replacement 前要求剩余物理容量至少 1 且未耗尽 R。
- 任一容量不足时，在创建前进入 `CAPACITY_BLOCKED_BY_RETENTION` 或 `CAPACITY_BLOCKED_REPLACEMENT`。
- 用户只能选择：明确关闭列出的某个完整旧 generation；或停止新 run。用户拒绝关闭时，旧代继续保留，新 run 不启动。
- Aegis 禁止自动关闭、自动隐藏、复用旧线程承载新 baseline、创建普通顶层任务或部分降级。

六次原生创建不是事务，必须使用 provisional batch：

1. kernel 先持久化 `provision_batch_id`、六个预期 role slot 和 `PROVISIONING` 状态。
2. 每创建一个实例，立即以 `PROVISIONAL` 状态记录真实 `thread_id + session_id`、父任务、role、generation、时间和创建事件。
3. `PROVISIONAL` 实例禁止接收任何测试 action。
4. 六个实例全部创建且身份、父子关系、面板可见性和能力验证通过后，registry 才在一个本地事务中把整批提交为 `ACTIVE_GENERATION`。
5. 任一步失败，batch 置为 `ABORTED`；已创建实例全部标记 `PROVISIONAL_ORPHAN`，旧 active generation 保持不变，零测试 action 派发。
6. 开始 batch 前，Master 单独请求用户是否预授权“仅清理本 batch 新建 orphan”。有预授权才可自动关闭这些 orphan，并保存 close receipt；无预授权则保留可见 orphan，等待用户逐项决定。
7. orphan 计入容量。重试必须使用新 batch ID，禁止把 orphan 拼入新 generation。

单角色 replacement 合同：

1. registry 身份为 `(source_generation_id, role_slot_id, instance_revision, thread_id, session_id)`。
2. 检测 agent 丢失后暂停新派发，记录旧实例为 `LOST_VISIBLE`；它仍计入 P。
3. preflight 校验一个 replacement 槽位，持久化 `replacement_batch_id`，再创建 `PROVISIONAL_REPLACEMENT`。
4. 新实例身份、父任务、role、面板和能力验证通过后，registry 在一个事务中把 role pointer 从旧 revision 切到 `instance_revision + 1`；旧实例置 `SUPERSEDED_LOST`，新实例置 `ACTIVE`。
5. action 同时绑定 source generation 和 instance revision。切换后，旧实例的晚到回执只进审计日志，禁止驱动 gate。
6. replacement 创建/验证失败时，新实例变成 orphan；旧 pointer 和旧 run 状态不被伪造为可用。无容量或无法恢复时进入 `NEEDS_MASTER_USER_DISCUSSION`。
7. replacement 前后崩溃依靠 batch 状态和单事务 pointer 保证只出现旧 active 或新 active，不出现两个可派发 identity。
8. 已在旧 revision 完整提交并通过 gate 的证据保留原 producer；未完成 attempt 在新 revision 重启。若旧 C 可能留下外部副作用，先按 8.5 进入查询或 `UNKNOWN_SIDE_EFFECT`，不能直接重试。

### 6.3 活动测试

1. 图生成下一条 `dispatch_action`。
2. Master 校验 action schema、run、node、role、generation、nonce 和 payload hash；首版不声称存在密码学签名。
3. Master 使用当前 Codex 父任务的原生子代理工具发送消息。
4. Master 保存原始回执和 Codex 事件元数据。
5. 图验证回执并执行确定性 gate。
6. 图提交 checkpoint 和事件后，才发布下一动作。
7. Master可向用户发送只读进度；用户回复不能进入活动节点上下文。

### 6.4 测试后

- 图返回结构化终态、报告路径、证据索引和未决问题。
- Master 与用户讨论产品缺陷、需求缺陷、风险接受或下一轮实现。
- 任何代码修改产生新 baseline；旧 run 保持不可变。

## 7. 运输层

### 7.1 当前可实现的默认运输

候选实现名为 `CodexNativeMasterRelay`。在 Phase 0B 证明前，它不是已确认能力。

精确协议：

1. `aegis run init --baseline-manifest <path>` 创建 checkpoint，返回 `run_id` 和 `AWAITING_USER_TEST_CONFIRMATION`。
2. 用户确认后，Master 创建当前 baseline 的 A–F generation；`aegis agents register --run-id <id> --registry <path>` 验证父子关系和能力。
3. `aegis run next --run-id <id>` 在单事务内取得 run lease、持久化唯一 action，并返回短 JSON：

```json
{
  "state": "WAITING_MASTER_DISPATCH",
  "run_id": "...",
  "state_seq": 17,
  "action_id": "...",
  "target_thread_id": "...",
  "target_session_id": "...",
  "payload_path": "C:\\...\\action.json",
  "payload_sha256": "..."
}
```

4. Master 只把 `action_id + payload_path + payload_sha256` 发送给目标子代理，不转述正文。
5. 子代理必须先执行 `aegis agent claim --action <path> --observed-thread-id <thread> --observed-session-id <session>`。数据库以 `action_id` 唯一约束原子认领：
   - 首次认领返回 `CLAIMED`。
   - 已完成返回既有 `result_path/result_sha256`，不得重新执行。
   - 正在执行返回 `IN_PROGRESS`，不得启动第二次执行。
   - thread、session、role、generation、revision、baseline 或 registry snapshot 不匹配时返回 `REJECTED`。
6. 子代理把结果直接原子写入自己的 run/role/attempt outbox，并执行 `aegis agent complete --action-id <id> --result <path>`。Master 不转录结果正文。
7. Master 调用 `aegis run ingest --run-id <id> --action-id <id>`；内核读取 outbox 和权威 Codex 事件，验证来源后推进 gate。
8. `aegis run next` 只在上一 action 已唯一消费后产生下一 action。
9. Master 回合中断后，新回合先执行 `aegis run status --run-id <id>`，再调用 `next`。checkpoint 的 `run_id/state_seq/action_id/lease_owner/lease_expiry` 决定恢复位置，不依赖聊天记忆。

暂停状态只有：

- `WAITING_MASTER_DISPATCH`
- `WAITING_AGENT_CLAIM`
- `WAITING_AGENT_RESULT`
- `WAITING_EXTERNAL_QUIESCENCE`
- `NEEDS_MASTER_USER_DISCUSSION`

Master 负责调用父任务原生协作工具和上述短命令。Master 不生成 reviewer 结论、不修改子代理回执、不关闭 blocker。若这套一步协议不能在真实父任务跨回合恢复，Phase 0B 失败。

### 7.2 未来运输

实现可替换 `TransportAdapter`：

```text
provision(role_spec) -> AgentIdentity
dispatch(action) -> DispatchReceipt
wait(receipt) -> RawAgentResult
health(agent) -> CapabilityStatus
close(agent) -> CloseReceipt
```

仅当实时 capability probe 证明 Codex app-server 提供受支持的父级 collab RPC、Desktop 连接方式和权威事件读取时，才启用 `AppServerRelay`。失败时必须 fail closed，不得退回 `codex exec resume`、普通顶层任务或不可追踪实例。

### 7.3 运输封包

每条动作至少包含：

- `protocol_version`
- `campaign_id`
- `run_id`
- `source_baseline_id`
- `registry_snapshot_id`
- `test_plan_revision_id`（A/B 批准前为空）
- `execution_contract_id`（C 开始前为空）
- `node_id`
- `attempt_id`
- `action_id`
- `target_role`
- `target_thread_id`
- `target_session_id`
- `target_generation`
- `target_instance_revision`
- 可选 `target_agent_handle` 与必需的 `target_agent_handle_source`
- `payload_path`
- `payload_sha256`
- `issued_at_utc`
- `expires_at_utc`
- `nonce`
- `graph_transition`
- `state_seq`

大内容只经本地绝对路径传递。命令行和消息只携带短封包、路径与哈希。
dispatch、claim、completion receipt、ingest receipt、evidence origin 和
authority event 必须逐项携带并核对同一
`registry_snapshot_id + thread_id + session_id + source_generation_id + instance_revision`；
handle 不参与身份相等判断。

初版不宣称密码学签名能抵御同一 OS 用户下的恶意代理。初版以 nonce、哈希、append-only 事件、唯一动作消费和权威 Codex 事件绑定防重放；强对抗版本再引入隔离签名服务。任何“签名”措辞只用于具备独立密钥服务的后续版本。

### 7.4 权威来源绑定

内核不得把 Master 提交的自然语言或自述元数据当作来源证明。

Phase 0B 必须证明至少一个不由 Master 改写内容的读取链：

1. 从权威 Codex 历史或事件订阅读取 `senderThreadId`、`receiverThreadIds`、实际 prompt、turn/tool-call ID、agent generation 和状态。
2. 从目标 child thread 的权威 turn 读取结果标识，或把 child 直接写入的已认领 outbox 与该 turn/tool-call 交叉绑定。
3. 图同时校验 `action_id`、payload hash、目标 generation、唯一消费和结果 hash。

Master 提交的伪造、截断、旧代次、错角色、改写 prompt 或遗漏事件必须被拒绝。若当前 Desktop 无法向内核提供这样的独立来源，v2 停止实施。

### 7.5 强制职责边界

首选平台强制：

- A–F 禁用 `spawnAgent/sendInput/resumeAgent` 等同级协作能力。
- 每个角色只可写自己的 run/role/attempt outbox。
- 目标仓库按角色设为只读或限定写范围。

若 0.145.0 不提供上述能力，唯一允许的替代是权威事件检测：

- 审计每个 child thread 的协作工具调用和文件工具调用。
- 检测到 child→child、child 创建后代、跨角色写入或通过共享文件传递未授权消息，立即终止为 `INTERNAL_INTEGRITY_ERROR`。
- 未被审计覆盖的工具通道一律禁用。

Phase 0B 主动攻击测试必须覆盖同级通信、创建后代、跨角色改写和间接文件传话。无法阻止或可靠检测时停止实施。

## 8. 状态与持久化

### 8.1 标识

- `campaign_id`：一次业务目标的跨 run 身份，UUIDv7。
- `run_id`：一个不可变 baseline 上的一次完整测试，UUIDv7。
- `source_baseline_id`：测试前既有需求、方案、代码、依赖、Skill 和策略的规范化哈希。
- `registry_snapshot_id`：当前 agent generation 注册快照哈希。
- `test_plan_revision_id`：B 批准的派生测试方案哈希。
- `execution_contract_id`：C–F 使用的非自引用执行合同哈希。
- `attempt_id`：一次节点尝试，UUIDv7。
- `event_id`：事件身份，UUIDv7。
- 所有事件保存 UTC 时间；本地时区只用于展示。

### 8.2 Baseline

状态身份拆为四层，禁止哈希自引用：

1. `source_baseline_id`：测试开始前已经存在的需求、实现方案、源代码、依赖、Aegis/Codex/Skill 和机器无关策略。
2. `registry_snapshot_id`：当前 A–F role slot、权威 `thread_id + session_id`、generation、revision、父任务和 capability 状态；可以引用 `source_baseline_id`，但 `source_baseline_id` 不包含 registry。
3. `test_plan_revision_id`：B 批准的测试计划、追踪矩阵、case index、A/B attempt 与 `source_baseline_id` 的哈希；A/B 正常迭代只产生新 revision，不改变 source baseline。
4. `execution_contract_id`：对
   `ExecutionContractManifest.v1{schema_version, source_baseline_id, test_plan_revision_id, execution_environment_snapshot_id}`
   的 UTF-8 RFC 8785 JCS 字节取 SHA-256。registry 不进入该 preimage；其任何输入也不得反向包含 `execution_contract_id`。

上述 JSON manifest 的语义 ID 使用 RFC 8785 JCS UTF-8。文件证据的
`byte_size/raw_sha256` 始终绑定 locator 原始 bytes；任何 LF 规则都是原始 bytes
的验证约束，不是哈希前转换。路径保存 Windows 规范绝对路径、仓库相对路径和大小写规范键。

registry 是逐工作单元的身份 segment，不是全 run execution contract。每个
dispatch/claim/receipt/evidence 都绑定当时的 `registry_snapshot_id`、role revision
和 `thread_id + session_id`。D acceptance 追加保存该 segment 和 producer；终态
可引用多个已验证 segment。replacement 后，已由 D 完整接受的证据保持原
segment；只有受影响且尚未完成或尚未被 D 接受的 attempt 失效。

`source_baseline_manifest.v1` 至少记录：

- 仓库绝对路径和仓库身份。
- Git commit。
- 工作区 clean/dirty。
- staged/unstaged diff 原始字节哈希。
- 所有未忽略 untracked 文件的路径、大小、哈希；不能只由执行者自行判断“与范围相关”。
- 需求文档、实现方案的路径和哈希。
- Aegis 版本、Codex 版本、模型、reasoning effort、角色 Skill 哈希。
- 本地与远端的静态环境契约：OS/架构要求、依赖锁、构建产物、硬件/固件要求、相关服务配置要求。
- 明确的排除字段及理由。时间戳、临时文件等非物质字段只有经过 schema 固定才可排除。

冻结时点：

1. 用户确认待测输入后冻结 `source_baseline_id`；此时尚未加入 A/B 产物和 agent registry。
2. A–F generation 注册完成后独立冻结 `registry_snapshot_id`。
3. A/B 可在同一 source baseline 内多轮迭代；只有 B 通过的 revision 生成 `test_plan_revision_id`。
4. C 开始前采集真实执行环境，冻结 `execution_environment_snapshot_id` 和非自引用的 `execution_contract_id`。
5. 每次 dispatch 前、receipt ingest 前、gate 前和最终提交前分别重算其对应层的可变输入。
6. source、Skill、策略、配置、依赖或**声明环境合同**变化：当前 run 进入 `SOURCE_BASELINE_DRIFT`，停止并创建新 source baseline、new run、new A–F generation；依赖旧声明的证据按传播 gate 失效。
7. registry 变化：只使该 role/revision 下尚未完成的 action/attempt 失效；记录新 `registry_snapshot_id`，从受影响 attempt 重启。其他 role 和 D 已接受证据不失效，不伪造身份连续性。
8. B 批准后测试计划发生变化：原 `test_plan_revision_id` 失效，返回 A/B，C 及之后证据失效。
9. **观测 execution-environment snapshot 漂移**：立即终止当前 run 为
   `EXECUTION_ENVIRONMENT_DRIFT`，旧 execution contract 和该 run 的 C–F
   evidence 全部失效，不得现场续跑。若声明环境合同未变，新 run 保持同一
   `source_baseline_id`，可复用仍 VERIFIED 的 generation；B-approved plan 仅在
   execution prerequisites 仍成立时复用，并冻结新 environment snapshot 和
   execution contract。若声明合同需变更，适用第 6 条。

影响分析只发生在新 run 创建前。A 生成版本化依赖/影响证明，B 独立审核，程序 gate 应用保守传播规则；证明失败时全部相关证据失效。

### 8.2.1 Canonical preimage 合同

JSON hash 域统一为：拒绝重复对象键后解析 JSON，序列化为 RFC 8785 JCS，
编码为 UTF-8 无 BOM，再取字节数和 SHA-256。`schema_bundle.v1` 中每个 schema
entry 的 `byte_size/sha256` 指该 schema 的 JCS 字节；entry 按 `path` 码点升序。
`bundle_sha256` 对省略自身字段后的完整 bundle JCS 字节计算。仓库
`.gitattributes` 固定 schemas/evaluation/docs 为 LF、fixtures 为 `-text`；
checkout EOL 不替代上述 JCS 规则。

Codex app-server 静态兼容键只允许以下采集：

```text
codex app-server generate-json-schema --experimental --out <new-empty-directory>
```

- executable 版本必须是记录的 `codex-cli 0.145.0`，并保存 executable SHA-256、
  argv、cwd、feature config、return code 和 UTC；
- 输出目录开始时必须存在且为空；
- 只解析 `<new-empty-directory>/codex_app_server_protocol.v2.schemas.json`；
- 兼容键是该单一 JSON value 的 RFC 8785 JCS SHA-256；legacy aggregate、目录中
  全部 `{path,json}` 包装或原始文件字节均不得作为兼容键；
- 原始 v2 文件的绝对路径、size、raw SHA-256 只作 acquisition evidence。

source baseline 的 staged/unstaged diff 分别对以下**参数向量产生的 stdout 原始
字节**取 SHA-256；stderr 单独保留，return code 必须为 0，禁止经 PowerShell
文本重定向或换行转换：

```text
git --no-pager -c color.ui=false -c core.autocrlf=false -c core.safecrlf=false -c core.quotepath=true -c diff.external= -c diff.renames=false -c diff.algorithm=myers diff --cached --no-ext-diff --no-textconv --binary --full-index --abbrev=40 --src-prefix=a/ --dst-prefix=b/ --
git --no-pager -c color.ui=false -c core.autocrlf=false -c core.safecrlf=false -c core.quotepath=true -c diff.external= -c diff.renames=false -c diff.algorithm=myers diff --no-ext-diff --no-textconv --binary --full-index --abbrev=40 --src-prefix=a/ --dst-prefix=b/ --
```

采集记录还绑定 Git executable SHA-256、`git --version`、当前 commit、
`.gitattributes` raw bytes/size/SHA-256、cwd 的 canonical path 和完整 argv。

`registry_state_sha256` 的唯一 preimage 是 read transaction 在一个
`registry_event_head_seq + registry_event_head_hash` 上导出的
`RegistryStatePreimage.v1`：schema/version、source baseline、parent task
thread/session、capacity contract、按 role 排序的 role pointers、按物理身份排序的
全部 active/retained/provisional/orphan/lost/superseded/replacement instances、
provision/replacement batch、capability state 和 event head。preimage 不含
`registry_state_sha256`、`registry_snapshot_id`、导出路径或采集时间。数据库
snapshot locator、transaction ID、导出时间位于 hash 外；gate 必须在同一 event
head 重导出并比较 JCS 字节。

### 8.3 持久层

- LangGraph checkpointer 保存可恢复的类型化状态。
- append-only event store 保存每个状态转换、动作、回执、gate 和人工决定。
- artifact store 保存大文件；checkpoint 只保存路径、哈希和元数据。
- SQLite 作为单机默认；PostgreSQL 作为并发或远端协调后端。
- 所有状态迁移带 schema version 和 migration。
- 写入顺序采用 outbox/inbox：先持久化动作，再发送；回执按 `action_id` 幂等提交。

### 8.4 恢复

- 进程在发送前崩溃：恢复未发送动作。
- 发送后、记录 dispatch 前崩溃：Master 可重发同一 `action_id`；child inbox 的唯一认领使第二个 turn 只能返回现有状态，不能再次执行。
- child 认领后、开始副作用前崩溃：恢复认领记录；按操作类别决定恢复或阻塞。
- 副作用后、结果提交前崩溃：不得假设未执行，也不得自动重放；按 8.5 的外部作业日志查询，无法确定时进入 `UNKNOWN_SIDE_EFFECT`。
- 节点超时：状态为 `WAITING_AGENT`；不把超时当失败结论。
- 状态或证据不一致：`INTERNAL_INTEGRITY_ERROR`，停止图并交给 Master。

每个故障实验必须生成 `RecoveryRecord.v1`，绑定 run/state sequence、lease、
checkpoint/action/claim/dispatch/result/receipt/event IDs、crash boundary、effect
class、journal/query evidence、crash 前后 state hash、恢复 decision 和 terminal
trace hash。runner 用同一 fixture/seed/action IDs 先运行不中断 reference，再运行
单点 crash；oracle 比较 schema 定义的 observable trace：有序 transition/action/
receipt/event kind、唯一消费次数、terminal state、result hash 和 observable effect
count。时间、lease owner 等允许差异字段必须由 schema 明列，不能由 comparator
临时忽略。`NON_IDEMPOTENT_UNJOURNALED` 在副作用后、receipt 前的未知窗口只能
得到 `UNKNOWN_SIDE_EFFECT`，自动 replay 次数必须为 0。

### 8.5 副作用与幂等

任一 C 节点测试动作在批准计划中预先分类：

- `PURE_READ`：可按同一 action 重试。
- `IDEMPOTENT_QUERYABLE`：必须向目标系统传递 `operation_id=action_id`，并能查询既有结果。
- `NON_IDEMPOTENT`：必须通过目标端 durable job wrapper 执行。wrapper 先持久认领 `operation_id`，再执行一次；重复请求只查询，不重放。
- `NON_IDEMPOTENT_UNJOURNALED`：禁止自动执行。若现实环境无法提供 job journal，只能由用户在测试前明确批准单次执行窗口；一旦结果不确定，run 进入 `UNKNOWN_SIDE_EFFECT`，后续由 Master/用户处理。

本地 claim 与远端副作用无法形成通用原子事务，因此 v2 不宣称任意外部操作“恰好一次”。它提供：

- 有 durable wrapper 时：副作用最多一次，结果可查询。
- 无 wrapper 时：未知窗口绝不自动重放，宁可阻塞。

故障注入必须用非幂等计数器、文件追加和可中断设备替身覆盖发送后所有崩溃窗口，证明不会发生第二次副作用。
side-effect must-detect case 必须实际提交 duplicate/replay 请求：
`IDEMPOTENT_QUERYABLE` 从 target query 返回既有结果，`NON_IDEMPOTENT` 从
durable journal 返回既有结果，unjournaled uncertainty 拒绝 replay；oracle 读取
原始 journal/query 和 effect counter fixture，不能接受
`automatic_replay_requested=false` 或“零重放”自报作为证明。

## 9. 图状态和路由

禁止单一 `status: bool`。终态聚合器只接收完整序列化 `VerdictInput.v1`：

- `execution_contract_id`
- `test_plan_revision_id`
- `workflow_phase`: `PLAN_AUTHOR | PLAN_REVIEW | TEST_EXECUTION | RESULT_REVIEW | REPORT_DRAFT | FINAL_REVIEW | TERMINAL_EVALUATION | CANCEL_CONTROL`
- `current_node`: `A | B | C | D | E | F | KERNEL_CANCEL_COORDINATOR | null`
- `d_review_snapshot_id`
- `report_candidate_id`
- `report_candidate_basis_id`
- `final_review_id`
- `final_review_basis_id`
- `final_review_completed`
- `approved_case_ids[]`
- `required_case_ids[]`
- `optional_case_ids[]`
- `d_accepted_required_case_ids[]`
- `d_accepted_optional_case_ids[]`
- `missing_required_case_ids[]`
- `open_required_environment_gap_case_ids[]`
- `required_process_blocked_case_ids[]`
- `open_optional_environment_gap_case_ids[]`
- `optional_process_issue_case_ids[]`
- `safety_stopped_case_ids[]`
- `cancelled_case_ids[]`
- `unclassified_missing_case_ids[]`
- `workflow_integrity`: `VALID | INVALID | UNKNOWN`
- `evidence_state`: `COMPLETE | PARTIAL | INVALID | STALE`
- `coverage_state`: `COMPLETE | PARTIAL_SAFETY_POLICY | INCOMPLETE`
- `report_state`: `NOT_READY | REWORK | APPROVED`
- `cancel_state`: `NOT_REQUESTED | REQUESTED | QUIESCING | QUIESCENT | TERMINATED_WITH_ACTIVE_WORK`
- `dispatched_action_states[]`，每项含 action identity、原 registry segment、terminal receipt，或 non-terminal registration 的位置、最后状态、可能副作用、owner 和复核方法
- `active_external_jobs[]`
- `unknown_side_effects[]`
- `open_process_blockers[]`，每项含 stable ID、`blocker_kind`、由 kernel 计算的 `gate_effect: BLOCKING | DIAGNOSTIC`、owner role、stage rank、opened event 和 `affected_case_ids[]`
- `open_upstream_defect_ids[]`
- `stagnation_state`: `NONE | CONFIRMED`
- `product_findings[]`，每项含 `verification_state: PROPOSED | CONFIRMED | REJECTED`
- `environment_gaps[]`，每项含受影响的批准 `case_id` 和 `resolution: OPEN | RESOLVED`

事实类型分离：

- `PRODUCT_FINDING`：产品行为与已批准要求不符；不由实现者在图内关闭。
- `PROCESS_BLOCKER`：A–F 工作产物或步骤不合格；返回 owner 修正。
- `ENVIRONMENT_GAP`：环境使证据无法取得或复验；`RESOLVED` 只由新 D-accepted evidence 产生，不能用解释性文字消除。
- `UPSTREAM_DEFECT`：需求、实现方案、Master 前置输入或 baseline 有问题；终止自动图。
- `REPORT_DEFECT`：报告与已审核事实不一致；返回 E。

五类 terminal-basis 原像必须是版本化、可加载 JSON，不得只保存 content ID：

1. `DReviewSnapshot.v1`：D 的权威 `thread_id + session_id`、run/state sequence、
   execution contract、D 接受的 evidence/finding/gap/job/blocker/coverage 完整排序集，
   各 evidence 的原 registry segment 和 producer。
2. `ReportCandidate.v1`：E 身份、run、attempt、当前 D snapshot、报告 raw bytes
   locator/hash 和报告中的完整 normalized fact IDs。
3. `ReportCandidateBasis.v1`：kernel 从 D snapshot 与 E candidate 重算的 expected/actual
   fact sets、差集、report hash 和生成 event。
4. `FinalReview.v1`：F 身份、run、attempt、当前 E candidate/basis、review decision、
   report-defect IDs 和 raw review artifact。
5. `FinalReviewBasis.v1`：kernel 重算的 D/E/F 完整 binding、normalized facts、
   execution contract、state sequence 和 final-review event。

每个 ID 等于对应完整对象的 UTF-8 JCS SHA-256。gate 必须从 content-addressed
store 加载对象、过 schema、重算 ID，再验证 role、thread/session、run、attempt、
state sequence、execution contract 和所有前置 ID；不存在或全零 ID fail closed。

字段唯一生产规则：

1. A 定义 case；B 批准 `required` 标志和可触发 `PARTIAL_SAFETY_POLICY` 的客观停止条件。
2. C 只能提交原始 execution、finding、gap 和 external job 记录。
3. `approved_case_ids[]`、`required_case_ids[]`、`optional_case_ids[]`、安全停止策略及其哈希来自 `test_plan_revision_id`，在构造 `VerdictInput` 时完整内联；required 与 optional 互斥且并集等于 approved。聚合器禁止再读取测试计划文件或数据库。
4. D gate 在一个事务中产生 `d_accepted_required_case_ids[]`、`d_accepted_optional_case_ids[]`、required/optional 的 environment/process 分类、对应 `CASE_PROCESS` blocker/gap 记录、finding verification、gap resolution 和 `evidence_state`。D 的结构化回执必须先通过程序证据校验；C 无权把执行遗漏标成环境问题。
5. kernel 计算 `missing_required_case_ids = required_case_ids - d_accepted_required_case_ids`。
6. D 依据批准计划和真实证据，把每个 missing required case 分类为 required environment gap、required execution blocker 或已验证 safety stop；kernel 依据取消事件产生 `cancelled_case_ids[]`。
7. 四个 required 分类集合必须互斥并完整覆盖 `missing_required_case_ids[]`。差集由 kernel 写入 `unclassified_missing_case_ids[]`。
8. optional case 的 OPEN gap、process issue、finding 和 evidence 原记录继续保留在 `VerdictInput` 与报告；它们不进入 required coverage 集合。optional test 产生的已确认产品 finding 仍可证明产品缺陷。
9. `coverage_state` 由 kernel 计算：missing 为空是 `COMPLETE`；missing 非空且全部属于 safety stop 是 `PARTIAL_SAFETY_POLICY`；其余是 `INCOMPLETE`。
10. kernel 是 `workflow_phase`、`current_node`、`workflow_integrity`、required/optional case 集、门禁分类集合、`missing_required_case_ids[]`、`unclassified_missing_case_ids[]`、`coverage_state`、`gate_effect` 和 `cancel_state` 的唯一生产者。
11. D gate 完成后，kernel 对已审核 evidence/finding/gap/job/blocker/coverage 生成 `d_review_snapshot_id`，并把 phase 置为 `REPORT_DRAFT`；产品 finding、环境 gap 和 PASS candidate 都不能在此处终结。
12. E 只能提交 report candidate。kernel 校验其完整覆盖 `d_review_snapshot_id` 后生成 `report_candidate_id/report_candidate_basis_id`，把 phase 置为 `FINAL_REVIEW`。
13. F gate 是 `report_state`、`final_review_id`、`final_review_basis_id` 和 `final_review_completed` 的唯一生产者。F 驳回时产生对应 blocker 并路由 E/D/A；F 通过且 basis 与当前事实完全一致时，kernel 才把 phase 置为 `TERMINAL_EVALUATION`。
14. `cancel_state=QUIESCENT` 只在全部已派发 action 有终态回执、全部 job 状态属于 terminal 且没有活动登记时由 kernel 产生。
15. `cancel_state=TERMINATED_WITH_ACTIVE_WORK` 只在停止新派发后，把每个 non-terminal/unverifiable action 和 job 的稳定 ID、位置、最后状态、可能副作用、owner 与复核方法逐项登记时由 kernel 产生。
16. B、D、F 可以提出 `PROCESS_BLOCKER`；只有独立 reviewer closure 和程序 gate 能移出 `open_process_blockers[]`。
17. 上游 defect 经对应 reviewer 验证后进入 `open_upstream_defect_ids[]`；活动 run 内不能关闭。

phase/node 映射固定为：

| workflow_phase | current_node |
|---|---|
| `PLAN_AUTHOR` | `A` |
| `PLAN_REVIEW` | `B` |
| `TEST_EXECUTION` | `C` |
| `RESULT_REVIEW` | `D` |
| `REPORT_DRAFT` | `E` |
| `FINAL_REVIEW` | `F` |
| `CANCEL_CONTROL` | `KERNEL_CANCEL_COORDINATOR` |
| `TERMINAL_EVALUATION` | `null` |

聚合前必须通过跨字段一致性校验：

- `execution_contract_id` 必须绑定同一个 source baseline、`test_plan_revision_id` 和 execution-environment snapshot；它不绑定 registry。
- 每个 action/receipt/evidence 必须验证自身记录的 registry snapshot、thread/session、generation 和 revision。terminal fact set 可包含多个已验证历史 registry segment；不得把 replacement 后 snapshot 强加给已由 D 接受的旧 segment evidence。
- `workflow_phase/current_node` 只能是预定义映射；任何跳阶段组合非法。
- `required_case_ids ∩ optional_case_ids = ∅`，且两者并集严格等于 `approved_case_ids`。
- `d_accepted_required_case_ids`、`safety_stopped_case_ids` 必须是 `required_case_ids` 的子集且互斥。
- `d_accepted_optional_case_ids` 必须是 `optional_case_ids` 的子集。
- `missing_required_case_ids` 必须严格等于 `required_case_ids - d_accepted_required_case_ids`。
- `open_required_environment_gap_case_ids`、`required_process_blocked_case_ids`、`safety_stopped_case_ids`、`cancelled_case_ids` 必须都是 missing 的子集、两两互斥，且并集严格等于 missing。
- `unclassified_missing_case_ids` 必须等于 missing 减去上述四类并集；非空时输入非法。
- `required_process_blocked_case_ids` 必须严格等于所有 open `blocker_kind=CASE_PROCESS` 记录的 `affected_case_ids` 并集与 `missing_required_case_ids` 的交集。
- `open_required_environment_gap_case_ids` 必须严格等于所有 `environment_gaps.resolution=OPEN` case ID 与 `missing_required_case_ids` 的交集。
- `optional_process_issue_case_ids` 和 `open_optional_environment_gap_case_ids` 必须分别严格等于对应 OPEN 记录与 `optional_case_ids` 的交集。
- CASE_PROCESS 记录必须有 owner。只影响 optional case 的记录由 kernel 标为 `DIAGNOSTIC`；影响 required missing case，或不属于 case coverage 的计划/证据/报告 blocker 标为 `BLOCKING`。缺记录、多余记录、错 gate effect 或无 owner 均非法。
- 每个 `CONFIRMED` finding 的 case/evidence 必须属于 `d_accepted_required_case_ids ∪ d_accepted_optional_case_ids` 的 D-accepted 记录。
- 每个 `RESOLVED` gap 必须引用后续 D-accepted evidence；open required gap 的 case 不能位于 accepted 集合。
- `coverage_state` 必须等于三组 case ID 按上述算法的重算结果。
- `evidence_state=COMPLETE` 要求每个 accepted required case 的 evidence schema、hash、producer、environment 和 execution contract 全部有效。
- `report_state=APPROVED` 要求 F gate 验证报告哈希及其 finding/gap/job/blocker 集合与本输入完全一致。
- `report_candidate_basis_id` 必须绑定当前 `d_review_snapshot_id` 和全部规范化事实集合；事实变化使 candidate 立即失效并返回 E。
- `final_review_basis_id` 必须绑定当前 `report_candidate_id`、candidate basis 和事实集合。
- `workflow_phase=TERMINAL_EVALUATION` 要求 `report_state=APPROVED`、`final_review_completed=true`、非空 final review ID 且 basis 全部匹配；其他组合非法。
- `report_state in {NOT_READY, REWORK}` 或 `final_review_completed=false` 时，`PASS/FAIL_PRODUCT/BLOCKED_ENVIRONMENT` 均非法。
- `cancel_state=QUIESCENT` 与任何非终态 action/job 非法；`TERMINATED_WITH_ACTIVE_WORK` 时，每个非终态 action/job 必须有完整登记，漏项或多余项非法。

任一非法组合由 kernel 把 `workflow_integrity` 置为 `INVALID`。聚合器只接收规范化 `VerdictInput.v1` 字节，不允许外部查询。

cancel/scope-change 使用独立 control ingress。合法 control 一经 durable append，
kernel 在构造普通 verdict 前原子停止新派发并进入 `CANCEL_CONTROL`；后续
integrity/upstream/unknown-side-effect 只作为取消登记事实，不得恢复或抢占普通
路由。决策器是 `VerdictInput.v1 -> GraphDecision.v1` 的纯函数。输出只能是
`{kind: ROUTE, target_node, reason_ids}` 或 `{kind: TERMINAL, verdict}`。按以下固定
优先级计算；finding、gap、job 和 blocker 原记录全部保留：

| 条件 | 主 verdict |
|---|---|
| `cancel_state in {REQUESTED, QUIESCING}` | `ROUTE: KERNEL_CANCEL_COORDINATOR` |
| `cancel_state=TERMINATED_WITH_ACTIVE_WORK` | `CANCELLED_WITH_ACTIVE_EXTERNAL_WORK` |
| `cancel_state=QUIESCENT` | `CANCELLED_BY_USER` |
| `workflow_integrity=INVALID/UNKNOWN` | `INTERNAL_INTEGRITY_ERROR` |
| `unknown_side_effects` 非空 | `NEEDS_MASTER_USER_DISCUSSION` |
| `open_upstream_defect_ids` 非空 | `NEEDS_MASTER_USER_DISCUSSION` |
| 存在 `gate_effect=BLOCKING` process blocker 且 `stagnation_state=CONFIRMED` | `TERMINAL: NEEDS_MASTER_USER_DISCUSSION` |
| 存在 `gate_effect=BLOCKING` process blocker 且未 stagnate | `ROUTE` 到最小 stage rank 的 blocker owner；同 rank 按 opened event 排序 |
| `evidence_state in {INVALID, STALE}` | `INTERNAL_INTEGRITY_ERROR` |
| `unclassified_missing_case_ids` 非空 | `INTERNAL_INTEGRITY_ERROR` |
| `workflow_phase=PLAN_AUTHOR/PLAN_REVIEW/TEST_EXECUTION/RESULT_REVIEW/REPORT_DRAFT/FINAL_REVIEW` | 分别 `ROUTE: A/B/C/D/E/F` |
| `workflow_phase=TERMINAL_EVALUATION` 且 `report_state!=APPROVED` 或 F basis 不匹配 | `INTERNAL_INTEGRITY_ERROR` |
| phase=`TERMINAL_EVALUATION`、F 已批准，且 `open_required_environment_gap_case_ids` 非空并与 safety/cancel 覆盖全部非流程 missing required case | `BLOCKED_ENVIRONMENT` |
| phase=`TERMINAL_EVALUATION`、F 已批准，至少一项 CONFIRMED finding 且 coverage in `{COMPLETE, PARTIAL_SAFETY_POLICY}` | `FAIL_PRODUCT` |
| phase=`TERMINAL_EVALUATION`、F 已批准，无 CONFIRMED finding、evidence=`COMPLETE`、coverage=`COMPLETE`、所有 required gap=`RESOLVED` | `PASS` |
| 其他组合 | `NEEDS_MASTER_USER_DISCUSSION` |

“required gap”只由同一输入内的 `environment_gap.case_id ∈ required_case_ids` 计算，不接受 reviewer 自由标注。相同规范化 `VerdictInput.v1` 字节必须产生相同 `GraphDecision.v1`。决策器对状态字段与 case/finding/gap/job/blocker 集合的笛卡尔积做穷举属性测试，禁止未覆盖分支。

三个同构缺失 case 必须产生不同结果：

- D 以远端环境不可达证据确认 environment gap：`BLOCKED_ENVIRONMENT`。
- D 确认 C 漏执行或证据采集错误：路由 C，不得形成 `BLOCKED_ENVIRONMENT`。
- D 未分类或分类集合不闭合：`INTERNAL_INTEGRITY_ERROR`。

### 9.1 A/B：测试方案

- A 写测试计划、追踪矩阵、风险覆盖和执行前提。
- B 独立审查需求覆盖、可执行性、合理边界、伪阳性/伪阴性和不可证明断言。
- B 的计划 blocker 返回 A。
- 固定重试上限删除。只要有新的实质变化，可以继续。
- 连续多次输出哈希不变、只改措辞或重复同一未解决 blocker，触发 `STAGNATION`，终止到 `NEEDS_MASTER_USER_DISCUSSION`；绝不强制通过。

### 9.2 C/D：执行与证据

- C 只执行 B 批准的计划并采集原始证据；不得改预期结果。
- 产品缺陷被发现后，默认继续其余独立测试，避免只报告第一个失败。
- 继续执行会破坏数据、设备、安全或后续证据有效性时停止相关分支，并明确记录未执行原因。
- D 审核命令、输入、环境、返回码、时间、原始输出、覆盖矩阵和结论推导。
- 执行缺陷返回 C。
- 计划覆盖缺陷返回 A，再经过 B。
- 确认的产品缺陷继续 E，不回到实现。
- 环境无法提供有效证据时进入 E/F 形成 `BLOCKED_ENVIRONMENT` 报告。

### 9.3 E/F：报告与终审

- E 只能从 D 接受的证据生成报告。
- F 审核报告与原始证据一致性、未执行项、证据寿命、结论边界和遗留 blocker。
- 报告表达问题返回 E。
- 证据问题返回 D；D 决定是否回 C。
- 计划覆盖问题返回 A/B。
- 需求、实现方案或 Master 前置决策有问题：立即停止自动图，形成 `NEEDS_MASTER_USER_DISCUSSION`。
- F 不修改产品代码，也不接受用户在活动 run 中改写通过标准。

### 9.4 取消收敛

1. 用户取消或活动 run 的 scope/requirement/expectation 变更写入独立
   `CancelControl`，durable append 后原子设置 `cancel_state=REQUESTED`，立即停止
   普通 verdict、普通路由和新 action。
2. 对未发送 action 作废；对已发送 action 发送同一 `action_id` 的 cancel control。
3. kernel 枚举 event store 中每个 dispatched action；C 同时记录本地进程、远端 job、设备操作和不可中断动作的稳定 job ID。
4. 图把 `cancel_state` 写为 `QUIESCING`，查询每个 action/job 的停止、完成或不可验证状态。
5. 晚到回执进入事件日志和报告，但不能恢复普通路由。
6. 全部 dispatched action 有 terminal receipt 且全部 job 静止后形成 `CANCELLED_BY_USER`。
7. 无法停止或无法确认的 action/job 必须逐项记录主机/设备或 authority locator、稳定 ID、最后状态、可能副作用、责任人和后续检查方法；零漏项时才形成 `CANCELLED_WITH_ACTIVE_EXTERNAL_WORK`，不得声称系统已静止。
8. integrity defect、upstream defect 和 unknown side effect 在取消期间只增加上述登记和报告事实；取消收敛结束前不得产生普通终态。scope change 收敛后才可建立新 baseline/run。

取消验收覆盖执行前、执行中、回执落库前和不可中断操作四个窗口。

## 10. Blocker 合同

每个 blocker 至少包含：

- 稳定 `blocker_id`
- `origin_role`
- `owner_role`
- `severity`
- `claim`
- `violated_requirement`
- `evidence_refs`
- `required_closure_evidence`
- `prohibited_substitutes`
- `affected_artifacts`
- `source_baseline_id`
- `test_plan_revision_id`
- `execution_contract_id`
- `opened_attempt_id`
- `status`

关闭条件：

1. owner 提供修正和证据。
2. 独立 reviewer 核验。
3. 程序 gate 校验 reviewer 身份、baseline、证据哈希和依赖传播。
4. blocker 追加 `closure_event`；原记录不覆盖。

严重性不由作者降级。争议进入 Master/用户讨论，但原 reviewer 意见保留。

`PROCESS_BLOCKER` 才使用关闭协议。`PRODUCT_FINDING` 不在图内关闭；`ENVIRONMENT_GAP` 只能由新证据消除；`UPSTREAM_DEFECT` 终止 run；`REPORT_DEFECT` 由 E 修改、F 复核。

## 11. 极端场景选择

禁止“能想象到”即纳入，也禁止“概率低”即排除。

一个场景满足任一条件时纳入：

1. 在声明运行边界内存在可证明的触发路径，且概率或暴露频次足以改变真实质量判断。
2. 即使概率低，后果涉及安全、权限突破、不可恢复数据损失、法律责任或系统性扩散。

每个极端场景必须记录：

- 稳定 `scenario_id` 与 `defect_class`。
- 触发机制。
- 适用运行边界。
- 概率或暴露依据；无数据时明确为假设。
- 影响范围。
- 纳入或排除理由。

纯粹理论、无触发路径、影响有限且概率无依据的场景可以排除；排除决定以
`ExtremeScenarioDecision.v1` 追加到不可变 `ExclusionRiskRegister.v1`。每项绑定
scenario 原像、决定者、独立 reviewer、来源 evidence、decision event 和前一条
register hash。register head 进入 evaluation manifest 与 Phase 0A freeze root；
禁止删除、覆盖或把“无数据”改写成低概率事实。

## 12. 证据系统

### 12.1 本地邮筒

每个 run 使用独立目录：

```text
<runtime_root>/
  campaigns/<campaign_id>/
    runs/<run_id>/
      baseline/
      inbox/
      outbox/
      artifacts/
      evidence/
      reports/
      events/
```

- `artifact_path` 必须是本地 Windows 绝对路径。
- 所有路径必须位于本 run 根目录；拒绝 `..`、符号链接、junction 和大小写绕过。
- 文件采用临时名写完后原子重命名。
- 固定旧文件名不再作为“当前版本”依据；manifest 指向具体 attempt 产物。

### 12.2 远端证据

远端证据可以留在服务器。本地证据索引必须记录：

- 主机身份，不只记录可漂移别名。
- 绝对路径或对象标识。
- 产生证据的完整命令/调用。
- 返回码。
- 开始/结束 UTC 时间。
- 环境指纹。
- 内容哈希或可验证摘要。
- 采集者、run、attempt。
- 保留期和访问方式。

远端证据无法再访问且本地没有足够原始材料时，不能继续支撑可复验结论；报告必须降级为证据失效。

### 12.3 代码变化与证据失效

- 代码、配置、依赖、Skill、策略或**声明环境合同**变化产生新 source baseline、
  new run 和 new generation；旧证据按保守依赖传播失效。
- **观测 execution-environment snapshot** 在活动 run 中漂移时终止该 run，
  旧 execution contract 和该 run 的 C–F evidence 全部失效。声明合同未变时，
  新 run 可复用同一 source baseline、仍有效的 generation，以及 prerequisites
  仍成立的 B-approved plan；必须采集新 snapshot 和 execution contract。
- 复用旧证据只在新 run 的预处理子图执行：A 作为独立影响分析作者，提交依赖图、接口边界、变更集和不扩散证明；B 审核。实现代码作者和 Master 都不能批准复用。
- B 通过且程序传播 gate 通过后，只复用严格独立的未受影响测试单元。
- 公共模块、共享状态、构建系统、接口契约或声明环境合同变化默认传播到所有依赖方。
- 复用决定和被复用证据的原始 run 必须可追溯。
- 活动 run 发现 source baseline 或 execution-environment snapshot 漂移时不得现场复用；必须终止并建立新 run。只有 source baseline 不变时才允许复用同一 generation。

## 13. Context 与 Skill

- 全局质量法只注入一次，保持短且不可被角色 Skill 降级。
- 每个角色只有一个角色合同：目标、非目标、可写产物、禁止行为、输入/输出 schema。
- 节点只获取本次所需上下文；不复制全仓库历史。
- Reasoning Ledger 只使用当前实现支持的 `active`、`stale`、`invalid`、`superseded`；不引入未实现的 `disputed`。
- 本次审计未找到项目 ledger 配置或 context pack，因此使用显式 `NOT_CONFIGURED + empty items`，不宣称 ledger 一致性。审计记录：`C:\Users\playm\AppData\Local\Temp\aegis-v2-plan-review\LEDGER_CONTEXT_AUDIT.md`。
- 实施前若提供外部 ledger 配置，必须生成包含 query、项目 ID、四类状态、生成时间、源版本和内容哈希的 context pack，并把其哈希纳入 baseline。
- 历史信息只作为检索材料，不自动成为当前事实。
- Skill 版本和哈希进入 baseline。
- 删除“通过自评分证明质量”的 gate。Skill 的自检只能产出待 reviewer 验证的风险列表。
- 项目内模板与用户本机安装的 Codex Skill 分离：仓库保存可发布源，安装器生成本机运行副本。

## 14. 用户可见性与中途回复

- Codex `Subagents` 面板展示 A–F 的 Active/Done 状态。
- Master 周期性读取 checkpoint，向用户输出：当前节点、attempt、已确认 blocker、等待原因、已耗时、证据位置。
- 进度消息只读，不把用户回复写入活动 run。
- 用户提出变更时，Master提供两个动作：继续原 run；取消并创建新 baseline/run。
- 用户可查看原始事件和证据索引。
- Aegis 终态与用户风险接受分开显示。

## 15. 配置与可移植性

仓库内只保存：

- JSON Schema。
- 角色规范。
- 默认非机器相关策略。
- migration。
- 示例配置。

本机 runtime 目录保存：

- 权威 thread/session IDs 与可选 sourced handles。
- Master task ID。
- 绝对 `artifact_path`。
- checkpointer 数据库。
- 事件、回执和证据索引。
- 本机 Codex capability probe。

`config/agent_registry.json` 改为模板；实际注册表放入 runtime 目录并从 CLI 参数或环境变量显式指定。不得提交旧 ID 和用户机器绝对路径。

## 16. 观测指标

Phase 0A 固定 `evaluation_manifest.v1`。它保存 corpus 版本、每个 case 的输入、预期路由/终态、缺陷类别、严重性、分母和哈希，之后只能通过带父哈希的新版本累积，不能为通过而改写。

生产发布硬指标：

- 关键不变量 corpus：所有 must-detect case 100% 被拒绝；零 false PASS。
- clean reference corpus：所有已证明满足合同的 case 得到预期 PASS；零 false blocker。
- stale/baseline corpus：100% 拒绝旧证据、漂移证据、错 producer 和错 generation。
- blocker corpus：零作者自关闭；零未满足关闭证据的 closure。
- recovery corpus：每个可恢复崩溃窗口的最终 state/event 等价；零跳节点。
- side-effect corpus：有 journal 的非幂等动作副作用最多一次；无 journal 的不确定动作零自动重放。
- isolation corpus：所有同级通信、创建后代、跨角色写入、间接文件传话尝试均被阻止或由权威事件检测并终止 run；零漏检。
- user-interference corpus：活动 run 的用户文本零进入节点 payload。
- report corpus：报告结论与已审核原始证据逐项一致。

探索性 mutation recall 单独报告，不设一个可掩盖关键漏检的总平均分。新 mutation 若表达既有硬不变量，立即加入 must-detect corpus。

速度、token、重试次数和 wall-clock 只用于容量规划，不进入通过计算。

用历史“审核连续 13 次打回”的真实记录建立回归语料。评估目标是保持合理 blocker，拒绝为减少轮次而放行。

## 17. 代码结构建议

逐步把当前两个大文件拆为以下边界：

```text
src/aegis/
  domain/          # typed IDs, state, verdict, blocker, baseline
  graph/           # topology, routes, node adapters
  gates/           # deterministic validation and closure
  transport/       # CodexNativeMasterRelay, future AppServerRelay
  persistence/     # checkpointer, event store, inbox/outbox
  evidence/        # manifest, hashing, path containment, invalidation
  runtime/         # preflight, registry, lifecycle, capability probe
  observability/   # progress and final handoff
  cli.py
schemas/
roles/
migrations/
tests/
```

不做一次性全量重写。先建立 v2 kernel 和兼容读取器，再迁移节点。

## 18. 实施阶段与硬验收

### Phase 0A：先冻结可证伪合同

工作：

- 在编写任何 v2 kernel、relay 或 capability probe 实现前，固化终态纯函数、blocker/finding、四层状态身份、evidence、dispatch/receipt、取消和 `evaluation_manifest.v1`。
- evaluation case 使用永久 stable ID；case 原像、expected、must-detect membership
  和 `case_sha256` 永久不可编辑。supersession 只能追加独立
  `CaseSupersessionEvent.v1`，绑定目标 case ID/hash、用户 requirement-change
  decision、独立 review、replacement case 和 event hash。
- manifest 的 `manifest_sha256` 是省略自身字段后完整 manifest 的 UTF-8 JCS
  SHA-256；非根 `parent_manifest_hash` 必须严格等于父 artifact 声明的
  `manifest_sha256`。父 artifact 存入 `manifests/sha256/<digest>.json` 或等价
  content-addressed store。root 引入初始 case；child manifest 只追加新 case 和
  event，不复制旧 case。跨版本 gate 验证 parent 可取、case ID 仅引入一次、旧
  case bytes/hash 不变、supersession target 存在。
- 独立测试合同 reviewer 先审核 case 输入、预期结果、分母和 must-detect 分类；通过后冻结 root hash，之后实施者无权改写。
- 发布门禁从根到最新 manifest 重放完整父链和全部有效 supersession 事件，计算
  链末最新有效 `ACTIVE` case 集；只运行该集合中的 must-detect case。无效、缺父、
  分叉未裁决或越权 supersession 使发布 fail closed。被 supersede 的旧 case、
  expectation、用户决定和 review 永久保留，但不再以冲突 expectation 阻止发布。

`Phase0FreezeRecord.v1` 的 normative file domain 必须精确枚举：

- 仓库规范输入 `docs/aegis_v2_requirements.md`、
  `docs/aegis_v2_upgrade_plan.md` 和
  `docs/aegis_v2_codex_static_evidence.md`；temp 来源只作 provenance，不替代
  repository locator；
- `docs/aegis_v2_phase0_contract.md` 与
  `docs/decisions/0001-aegis-v2-dual-plane.md`；
- `.gitattributes`、`pyproject.toml` 和当前 Windows CPython 3.13 平台 lock
  `pylock.windows-py313.toml`；
- `schema_bundle.v1.json` 及其列出的全部 versioned schema；
- 最新 evaluation manifest、完整 parent chain、raw fixtures、runner/oracle contract
  和 exclusion risk register；
- 全部 reference generator、oracle、comparator 的可执行 source，以及把 stable ID
  映射到 source 原像、依赖/import policy、byte size/hash 的完整 source manifest。
  精确集合为 `evaluation/aegis_v2/reference/` 下 `__init__.py`、
  `__main__.py`、`canonical.py`、`cli.py`、`closure.py`、
  `closure_materialization_data.py`、`comparator.py`、`coverage.py`、
  `generator.py`、`manifest.py`、`materialization.py`、
  `materialize_closure.py`、`materialize_verdict.py`、
  `schema_validation.py`、`verdict.py`、`verdict_facts.py`、`README.md`、
  `tests/test_audit_remediation.py`、`tests/test_reference.py`，以及
  `source_manifest.v1.json`；
- `source_manifest.v1.json` 必须通过 bundle 内
  `schemas/aegis/v2/reference_source_manifest.v1.schema.json`
  (`ReferenceSourceManifest.v1`)；harness 自验不能替代独立闭合 schema；
- 最终独立 review artifact 作为 review binding，不进入被其审查的 normative root。

每个 `FreezeInput` leaf 严格为
`{logical_path,locator,artifact_kind,byte_domain,byte_size,raw_sha256,
semantic_jcs_sha256,leaf_sha256}`；`locator` 明确区分 repository path 与外部
acquisition locator。JSON 使用 `JCS_RFC8785`，同时保留采集 raw size/hash 和
semantic JCS hash；其 raw bytes 必须为 UTF-8、无 BOM、LF-only、无重复 key。
Markdown 使用 `UTF8_LF_NO_BOM`，要求 locator 原像本身已满足 UTF-8、无 BOM、
LF-only，不做 CRLF 转换；fixture、lock、source 和其他 exact-byte 输入使用
`GIT_BLOB_BYTES`。非 JSON 的 `semantic_jcs_sha256=null`。
`byte_size/raw_sha256` 永远绑定 locator 原始 bytes，`byte_domain` 不改变该哈希域；
JSON raw 和 semantic hash 同时进入 leaf，因此仅格式变化也改变 root。只有
hash/source-manifest row、没有可取 locator 和完整原像的项目无效。
`leaf_sha256` 对省略自身后的 leaf JCS 计算。按
`logical_path` 码点升序的
`[{logical_path,leaf_sha256}, ...]` JCS SHA-256 是 `freeze_root_id`。

`CodeAbsenceProof.v1` 绑定 `freeze_base_commit` 和直接调用的精确五元素 argv
`["git","ls-tree","-rz","--full-tree","<freeze_base_commit>"]`；最后一项必须等于
该 commit。保留 repository-root cwd、exit code 0、空 stderr、包含 NUL 的 stdout
原始 bytes/base64、size/hash。inventory 是 base tree 全部 tracked path 和全部
non-ignored untracked path 的排序并集，包含 tracked deletion；每项绑定
entry kind、base/worktree 原始 bytes、blob ID 或外部 frozen-snapshot
locator/event、自省略 content ID。证明还绑定 inventory ID、重算 counts、精确
allowed domain，以及域外精确补集的逐项独立 disposition 原像。`BASE_EQUAL` 只适用
于 base/worktree bytes 相等；其他项必须是 `PREEXISTING_NON_V2`，并绑定
`NOT_V2_IMPLEMENTATION`、rationale、reviewer thread/session/turn 与 disposition
artifact locator/size/hash。任何 v2 kernel/relay/live capability-probe
implementation、未分类项、缺失项或 count 不符都使证明失败。

tracked-modified 与 non-ignored untracked 原像在复审前用直接 argv
`["git","hash-object","-w","--no-filters","<path>"]` 写入 Git object database；
`<path>` 必须先证明位于 repo 内，禁止 shell/filters。该操作不 stage、不 commit。
collector 要求 exit 0、单一 object ID，再以 `git cat-file blob <id>` 取 raw bytes，
复核 size/SHA-256 后把 `source_kind=GIT_BLOB` 与 `git_blob_id` 写入 inventory。对象
缺失、被 GC、路径逃逸或 bytes 不匹配使 freeze 失效。替代的
`FROZEN_SNAPSHOT` 必须绑定 schema 定义的外部 locator 与 acquisition event。

独立 reviewer 的最终 Codex event 必须来自 Master 不能改写的 append-only event
源，并包含候选外预授权 provider/policy、provider event ID、单调 log position、
authority committed UTC、Codex version/protocol semantic hash、reviewer
`thread_id + session_id`、parent identity、parent spawn/delivery tool-call、
reviewer turn/final item、`agentMessage/final_answer`、item/turn lifecycle、
`freeze_root_id`、code-absence proof content ID、完整 review artifact hash、
`verdict=PASS` 和空 blocker 集。authority proof 保存 parent spawn、
item-completed、turn-completed 原始 records 的 bytes/size/hash；final item text 必须
精确等于保存的 canonical review payload。freeze record 保存 payload 的 event
locator/bytes/hash。
review anchor 与 authority anchor 必须引用同一个 reviewer-final delivery event；
freeze record 还必须持久化 producer 的 `thread_id + session_id + turn_id`；验证器从
record 自身判定 reviewer 与 producer 独立，不能依赖调用者补传 identity。
`freeze_record_id` 对包含 root、code proof、review artifact 和 event raw hash 的
完整 freeze record 省略自身后取 JCS SHA-256。首个 v2 implementation commit 必须
证明其 parent ancestry 包含 `freeze_base_commit`，且其 parent tree/delta 与记录的
repository snapshot 一致；任何规范叶变化要求新 review/event/root。

生产 API 不接受 caller `Callable`、boolean verdict 或 exact-byte reader。reader
可闭包回显伪造 bytes，仍是自证。固定 provider adapter 必须从 candidate 外
preauthorized policy 取得 trust root，并使第二个独立消费者可复验 proof。本地
app-server/history、rollout JSONL、SQLite/CAS/hash chain/HMAC 和 opaque
attestation 只可作为 non-authoritative observation。当前没有具体 adapter/proof，
所以 public finalize/verify 永久 fail closed；offline validator 遇到任何 frozen
record 返回 `AUTHORITY_UNVERIFIED`。pending 也必须返回 `valid=false`、
`phase_complete=false` 和非零 exit；静态结构通过只能单列
`structural_valid=true`，不能被消费者当作 Phase 0A gate 通过。synthetic seam
只能生成 production schema 明确拒绝的 test-only record。

通过条件：

- 冻结动作发生在首个 v2 实现提交之前，并有 commit/time/hash 证据。
- 修改/删除 case、原 expectation 或 must-detect 分类必须失败；合法 requirement
  change 只能追加 supersession event。换 manifest 版本不能绕过链末最新有效
  `ACTIVE` must-detect case。
- 当前修订必须先同步 schema、evaluation、fixture、所有 JCS/hash，并获得新的
  独立 reviewer PASS event；在此之前不得写 freeze PASS。

### Phase 0B：真实 Codex 可行性探针

工作：

- Phase 0A 通过且用户批准 capability test 后，在同一真实 Codex 父任务创建六个非正式 probe role slot；它们不是正式产品测试 A–F。
- 创建 synthetic source baseline 1 的六个 generation，完成各自发送、等待和父 Master 回合中断恢复。
- 保留 generation 1；创建 synthetic source baseline 2 的六个新 generation，并只向 generation 2 发送新 baseline action。
- 以认证合同 `G=2, R=6, P>=18` 记录平台的同时活动上限、累计保留上限、侧栏保留/折叠规则和可稳定定位边界。
- 在已保留 12 个实例时尝试创建第三代；preflight 必须在创建任何实例前返回 `CAPACITY_BLOCKED_BY_RETENTION`。用户拒绝关闭时，12 个实例保持不变且新 run 不启动。
- 先验证 cleanup preauthorization=false 会在第一条 create 前拒绝实验。用户对命名 batch 单独预授权后，分别在 native create、create-event/provisional persist、thread/session/role identity、parent binding、panel/capability validation、pre-activation registry commit 六个边界注入单点失败；每轮核查 aborted batch、完整 provisional registry、orphan 可见性、零 action 派发、旧 active generation 不变和 authoritative close receipt。
- 对 A–F 每个 role 依次注入 agent 丢失并创建一个 replacement，验证 `instance_revision` 单调增加、旧 identity 禁止收件、新 identity 独占派发、物理容量从 12 增至 18。随后尝试第 7 个 replacement，必须在创建前返回 `CAPACITY_BLOCKED_REPLACEMENT`。
- 在每个 role 的 replacement 创建前、创建后、验证后、registry pointer 提交前后注入崩溃，验证恢复后至多一个 active identity、所有 orphan/lost/superseded 实例可追踪、旧代和其他 role 不变。
- 真实关闭并重启 Codex Desktop，验证同一父任务、十八个 retained child instance、两 source generation、六条 replacement 关系、旧 identity 可观察、新 identity 可发送和侧栏定位。
- 实测可取得稳定且成对绑定的 `thread_id + session_id`、父子关系、实际 prompt、turn/tool-call ID、sender/receiver 和 child 结果来源；handle 仅验证为带来源定位元数据。
- 用第 7.1 节的 CLI 证明 `CodexNativeMasterRelay` 完整一步闭环。
- 主动尝试同级通信、创建后代、跨角色改写和间接文件传话。
- 将 app-server 直连标为 capability-gated，不作成功假设。

通过条件：

- 上述每项都有真实事件、ID、路径、哈希、时间和返回码证据。
- 用户未确认正式产品测试前，不创建正式 A–F。
- 六角色、两 source generation、六个单角色 replacement、旧实例长期保留、新 identity 发送、父子身份、`Subagents` 面板可见性、跨 Master 回合复用、真实 Desktop 重启恢复、稳定定位、权威来源绑定、职责越权阻止/检测全部通过。
- 用户在未确认关闭旧实例前，能够在原父任务中持续观察并定位全部旧代/lost/superseded identity；实测平台容量满足 `6 × G + R = 18`。
- 第三代容量不足路径整批 fail closed；六次创建中途失败时允许出现已登记 `PROVISIONAL_ORPHAN`，但零部分 generation 激活、零 action 派发、零未授权关闭、零旧代复用、零顶层任务降级。
- replacement 有容量时只原子切换一个 role revision；无容量时零创建并停止，用户拒绝关闭旧实例则 run 保持阻塞。
- 任一硬能力缺失，结论为“当前 Codex 版本不能实现用户目标”，停止 Phase 1–5。无普通顶层任务、`codex exec resume`、不可恢复实例或提示词隔离降级。

### Phase 1：持久内核

工作：

- 类型化 state/verdict/IDs。
- SQLite checkpointer、append-only event store、inbox/outbox。
- 每 run 目录、原子写、幂等 action。
- 正确退出码。

通过条件：

- 在发送前、发送后、claim 前后、远端副作用前后、回执前后、gate 前后注入崩溃；恢复后无跳节点。
- 有 durable journal 的副作用最多一次；无 journal 的未知窗口进入 `UNKNOWN_SIDE_EFFECT` 且绝不自动重放。
- 并发 run 不共享产物或状态。

### Phase 2：证据与基线

工作：

- baseline 采集和 hashing。
- 本地路径 containment。
- remote evidence locator。
- evidence invalidation/impact analysis。
- versioned JSON Schema。

通过条件：

- 旧 run 产物、路径越界、软链接/junction、错误 baseline、错误 producer、篡改哈希全部 fail closed。
- 两个独立子模块的有限复用案例可由机器验证追踪。

### Phase 3：A–F 图迁移

工作：

- 迁移 A/B、C/D、E/F。
- 实现跨环节问题回路和终态分类。
- 移除固定重试强制结束；加入 stagnation 检测。
- 产品缺陷继续报告，不进入代码修复。

通过条件：

- 计划缺陷、执行缺陷、证据缺陷、报告缺陷、产品缺陷、环境阻塞、Master 前置缺陷分别走到唯一正确路径。
- 作者不能关闭自身 blocker。
- 分数 100 不能覆盖一个硬 blocker。

### Phase 4：Codex 生命周期和只读进度

工作：

- 用户确认后的 A–F provision。
- runtime registry。
- 长期代理健康检查和 generation replacement。
- Master 进度输出和最终 handoff。

通过条件：

- 用户能在 `Subagents` 面板观察 A–F。
- 活动 run 中的用户文本不能进入节点 payload。
- 代理替代可追溯且不伪造身份连续性。
- 同一 baseline 多轮审核保持同代；新 baseline 必须启用新 generation，旧冲突指令和旧证据均被 gate 拒绝。

### Phase 5：Context、Skill 与评估

工作：

- 重写 low/global/role Skills，移除自评分门禁。
- Reasoning Ledger baseline 绑定和状态分类。
- 历史 13 轮案例、mutation tests、fault injection。
- 文档、安装、迁移和回滚说明。

通过条件：

- 第 16 节全部生产发布硬指标通过。
- reviewer 未因轮次、耗时或 token 压力放宽 blocker。
- 新安装不需要修改仓库中的机器特定配置。

### 全阶段发布门禁

Phase 0A、0B、1–5 未全部通过前，v2 只能运行专用 probe、fixture、替身和已知 corpus；禁止对真实目标项目启动正式测试 run。通过后，正式 A–F 仍只在用户逐次确认测试时创建。

## 19. 测试矩阵

至少覆盖：

- 空/错 `thread_id`、空/错 `session_id`、thread/session 交叉拼接、父任务不匹配、旧 generation。
- 每个 role replacement 的有容量、无容量、创建前后崩溃、旧 identity 晚到回执。
- 子代理试图创建或联系其他代理、跨角色改写、通过共享文件间接传话。
- Master 伪造、截断、遗漏、错配、改写 prompt 或提交旧 turn 回执。
- 父 Master 回合中断后从 checkpoint 恢复。
- Codex Desktop 真实重启后同一父子身份恢复。
- 用户尝试中途改预期结果。
- 重放 action、重复回执、乱序回执、过期 action。
- 非幂等计数器、文件追加、远端 job 在每个崩溃窗口最多一次或进入未知副作用状态。
- Windows 长命令行。
- 路径穿越、盘符大小写、UNC、junction、symlink。
- 旧固定文件名污染新 run。
- dirty worktree、untracked 代码、依赖变化、Skill 变化。
- 远端返回码非零但文本像成功。
- 远端证据路径存在但内容已变。
- checkpoint 崩溃恢复和并发 run。
- A 后、B 后、C 后、D 后、E 后及 F 提交前发生 baseline 漂移。
- reviewer 高分但存在 blocker。
- 连续 13 次合理打回。
- 无实质变化的无限循环。
- 产品缺陷后其余独立测试继续。
- 继续测试会破坏设备/数据时正确停止。
- 产品缺陷、环境 gap、安全停止、报告缺陷、上游缺陷的全部两两组合和三类组合。
- process/environment missing case 的单类、混合、缺 blocker/gap 记录、多余记录和无 owner 记录。
- required/optional 的 environment gap、process issue、confirmed finding 及混合组合；optional 事实必须保留但不得伪装 required coverage blocker。
- required/optional confirmed finding、environment block、PASS candidate 在 E 报告缺失、F 驳回、F basis 过期、F 通过四种状态；前三者不得形成产品/环境/PASS 终态。
- 执行前、执行中、回执前、不可中断动作的取消收敛。
- 新 baseline 使用新 generation；旧 run 冲突指令和旧证据不能污染。
- 用户风险接受不改写图终态。

### 19.1 Phase 0A 可执行 corpus 合同

`EvaluationRunnerContract.v1` 固定每个 `input_schema_id` 到生产 schema 的确切
`$id + JSON Pointer`、`sut_entrypoint_id`、直接进程 argv、精确
SUT-decision/outer-output schema、fixture mount、comparator 和 oracle version。
`EvaluationRunnerInput.v1` 是 outer envelope；SUT stdin 只含重新投影出的五字段
`subject/context_objects/fixture_refs/mutation/observed_state`。SUT 不得到 runner
contract ID、input-binding ID、case ID、expected、manifest path、runner metadata
或 comparator/oracle 配置，也无权读取 expected/case store。
`oracle.reference_trace_fixture_id` 仅供 outer evaluator 使用；它若出现在同 case
的 `input.fixture_refs`，runner 必须在创建 SUT 进程前拒绝。要求 SUT 回传、识别或
依赖未知 case ID 的行为按 lookup-table 泄漏失败。SUT stdout 只能是一个
schema-valid `SutDecision.v1` JCS，闭合字段为
`schema_version/outcome/decision/reason_ids/assertion_ids/
sut_decision_sha256`。outer evaluator 冻结 runner/case/input identity、
runner-input/SUT-stdin hash、exact argv/cwd/env、process/times/return code、
stdout/stderr exact bytes、Python binding 与 per-invocation revalidation 为
基础，再加入 isolation binding 与 invocation-time isolation revalidation，形成
`RunnerExecutionRecord.v1`，再把 decision 和该 record 嵌入
`EvaluationRunnerOutput.v1`；之后隔离 comparator 才能读取 expected。

ordinary case 与 runner-conformance case 在 materialization 前，必须用各自绑定的
runner contract 解析 fixture。每个 `logical_runtime_path` 必须是严格位于
`fixture_mount.logical_runtime_root` 下的规范 Windows 绝对路径；点段、ADS、
尾随空格/点别名、跨盘、UNC 逃逸和等于根目录均在创建任何文件前拒绝。SUT 负例不能
授权 outer runner 向 run 根外写入。

五字段 projection 只防接口直接泄漏。它不证明同 OS 用户进程不能读取 repo 或公开
corpus。release-grade runner 必须使用认证 isolation backend，并由 SUT 外部权威
证据证明：cwd 为 repo 外 `ISOLATED_EXECUTION_ROOT`；外部 venv 只读/可执行，
当前 case fixture 只读，本 invocation outbox 只写/create-new；repo、
`evaluation/`、expected store、reference source、其他 case 和未声明路径不可读；
network deny。当前 Windows 若无该 backend，isolation
binding=`UNVERIFIED_ISOLATION`，outer
output=`BLOCKED_UNVERIFIED_ISOLATION`，不启动 SUT、不产生 decision/process
record，release blocked；禁止用 best-effort ACL、prompt、projection 或进程自报
升级为 PASS。公开 corpus 的预先可见性保留为风险，通过独立 expected/reference
作者、未公开 holdout、全量 property domain 和认证隔离降低；不得宣称 corpus 对
实现不可知。

- 纯函数：output 先过 exact production schema，再比较 RFC 8785 JCS bytes；
  decision/reason/assertion 的值与顺序都必须完全相同。
- 状态/副作用：比较 `RecoveryTrace.v1` 或对应 domain trace；禁止只比较最终 label、
  自报布尔值或计数摘要。
- unknown input/output schema、额外 stdout framing、非零 return code、缺 fixture、
  hash 不符或 comparator 未注册均 fail closed。
- runner 自身、SUT build 和 comparator 分别 content-addressed；SUT build hash 进入
  result，避免 case lookup 替身冒充真实入口。
- reference generator、oracle、comparator 在 SUT 环境外运行；其 source、source
  manifest 和 import/dependency policy 全部冻结。它们禁止导入、调用、复制或复用
  SUT 决策函数/implementation module。property domain 全量运行；禁止采样、early
  pass 或缩小分母。
- AST/import policy 只承担 frozen-source change-review gate，不构成 Python
  sandbox。release-grade reference execution 必须由独立 evaluator isolation
  backend 证明 network 与 shell/process creation 禁止、production package 与 repo
  路径不可见，且仅开放冻结 source 和角色声明的输入/输出通道；缺该证明不得形成
  release PASS。

机器无关 runner policy 固定 build/runtime 栈：
`setuptools==83.0.0`、`jsonschema[format-nongpl]==4.26.0`、
`rfc8785==0.1.4`、`langgraph==1.2.9`、
`langgraph-checkpoint-sqlite==3.1.0`；`psycopg` 只属于 legacy optional。
v1 固定 `SUPPORTED_PLATFORM_SET={windows-cpython313}`，只使用
`pylock.windows-py313.toml`。Linux/其他平台在新增独立 PEP 751 lock、
runner-contract revision、execution-environment certification 并重新冻结前 fail
closed；扩展不能改写既有 case/expected/generator/corpus bytes。每个 evaluation
execution 在 repo 外新建隔离 venv，按 lock hash
验证并安装 project wheel/全部 wheels，禁止 editable install、`PYTHONPATH`、user
site、PATH interpreter lookup 和 shell。直接 argv 固定为
`[<absolute-venv-python>,"-I","-X","utf8","-m","aegis.sut",
"<ENTRYPOINT_ID>"]`。SUT 环境不继承父环境，只含
`AEGIS_RUNNER_MODE=FROZEN_EVALUATION` 和
`LANGGRAPH_STRICT_MSGPACK=true`。run evidence 记录并逐次复核真实 Python
path/realpath/bytes hash/version/ABI、lock bytes/hash、project wheel 和完整
installed distributions。传递依赖 `xxhash==3.8.1` 必须证明来自 lock 中的真实
distribution；解析到仓库 `src/xxhash.py` 或其他 checkout source 立即 fail
closed。

raw fixture 只能是 `evaluation/aegis_v2/fixtures/<sha256>/...` 下仓库相对 exact
bytes，或 manifest 内 base64/UTF-8 明确编码的 exact bytes。每项记录 encoding、
BOM/EOL policy、byte size、SHA-256 和只读 mount path。绝对临时路径只能出现在
acquisition record，不能作为冻结 locator；生成器必须确定性且其 source/hash 同时
冻结。Phase 0B capability PASS 仍必须绑定真实 child/event/version/restart，synthetic
fixture 只能验证协议拒绝/接受逻辑。

generation fault corpus 包含：

1. cleanup preauthorization=false：在第一条 native create 前拒绝实验，零实例、零
   batch mutation；
2. preauthorization=true：分别在 native create、create-event/provisional persist、
   thread/session/role identity、parent binding、panel/capability validation、
   pre-activation registry transaction 六个边界单点失败；
3. 每例验证新 batch=`ABORTED`、所有已创建实例=`PROVISIONAL_ORPHAN`、旧
   generation 不变、零 dispatch；只有授权 batch 可有 authoritative close receipts，
   未授权 orphan 必须保留可见并计入容量。

isolation corpus 是 A–F 六个 actor 乘四种攻击：direct sibling contact、descendant
creation、cross-role outbox write、shared-file message。输入必须是平台 deny raw
result或不可改写 authority event，含 sender/receiver/path/turn/tool-call/raw bytes；
`platform_prevented=true`、`detected=true` 等结论布尔值不能作为 oracle 输入。

protocol mutation 对以下每个 binding 做单字段变异且其余原始字节不变：
protocol、campaign、run、source baseline、registry snapshot、plan、execution
contract、node、attempt、action、target role、thread、session、generation、
revision、payload path/hash、issued/expiry UTC、nonce、transition、state sequence、
result hash、claim/receipt authority IDs。另覆盖 duplicate consumption、expired
action、old turn、event omit/insert/reorder、duplicate/out-of-order receipt、forged
或 truncated raw bytes。每例必须得到 exact fail-closed decision。

冻结前必须增加以下 raw/preimage case：Windows traversal/drive-case/UNC/junction/
symlink；旧固定文件名污染；dirty/untracked/dependency/Skill drift；非零 return code
配“成功”文本；远端 locator 未变而 bytes 改变；A/B/C/D/E/F 六个 drift window；
A 自批、相邻角色复用同一 thread/session、C 改 expected、C 把 omission 伪装
environment gap、D 忽略非零 return code。每类都有 clean 对照、must-detect 和
denominator。

verdict oracle 在 cancel 独立优先级固定后，枚举 schema-valid/invalid closure：
每一对优先条件同时成立、所有三类关键碰撞、required/optional fact set 的有限
笛卡尔积、缺/多 blocker-gap-job registration。独立 reference model 比较 exact
decision bytes 和 ordered reason IDs；样例 case 不能替代该属性测试。

每个 case 的 `defect_class` 必填。extreme scenario 使用第 11 节五类依据；所有
exclude decision 进入 hash-chained risk register，register head 同时绑定 manifest
和 Phase 0A root。

## 20. 迁移与回滚

- v1 数据只读导入；必须标记 `legacy_untrusted`，不能直接支撑 v2 通过。
- 不做 v1/v2 双写，避免两个真相源。
- v2 使用新 runtime 根目录和 schema version。
- 每阶段单独可运行、可回滚；回滚只切换启动入口，不删除 v2 事件和证据。
- 当前 dirty worktree 先由用户确认归属，再实施迁移；不得覆盖既有修改。

## 21. 开工门禁

以下条件全部满足才进入实现：

1. 用户确认本方案的目标、边界和双平面选择。
2. 第一性原理 reviewer 无未关闭 blocker。
3. Phase 0A 的评估合同与 Phase 0B 的 capability probe 分别被明确批准。
4. 正式 A–F 仍只在用户确认测试时创建。
5. 运行目录、目标仓库和证据保留策略明确。

## 22. 当前不确定项

1. Codex Desktop 重启后，V2 子代理身份和父任务工具能否稳定恢复。
2. 当前父任务原生工具能暴露 subagent thread ID；同一 thread tree 的
   `sessionId`、parent、turn/item/tool-call 完整绑定仍需 Phase 0B 实测。
3. 本地 Desktop/app-server/history 已确认可 rollback/delete/inject，不能作为
   freeze authority。是否存在覆盖 subagent final raw event 的独立 Compliance
   provider 或受认证 recorder，及其可复验证明合同，仍未证明。
4. 未来 app-server 是否提供受支持的父级 collab RPC 与 Desktop attach。
5. Windows 下 per-agent 工具/文件能力能否被硬性限制；若不能，权威事件是否覆盖全部协作和文件写通道。
6. 每个新 baseline 创建六个新 generation 后，Codex 的实例上限和侧栏可观察性是否仍满足长期追溯。

这些问题由 Phase 0B 实验回答。1、3、5、6 任一失败都使当前方案在当前 Codex 版本上不可实施；不得静默降级。
