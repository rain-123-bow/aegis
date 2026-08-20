# Aegis v2 需求设计（修订待复审）

归档来源：
`C:\Users\playm\AppData\Local\Temp\aegis-v2-implementation\REQUIREMENT_DESIGN_FINAL.md`

归档前来源原始 SHA-256：
`b14debc6d6c9cb764138365c3a12f6664fe73fac67966a01efbd66d9f0c10b15`

归档语义：本文件是 Phase 0A 仓库内规范输入。来源哈希只证明复制前原像；
冻结时必须对本文件当前 locator bytes 重新计算 `FreezeInput`。状态仍为待独立复审。

状态：`REVISED_PENDING_INDEPENDENT_REVIEW`

原用户确认时间：`2026-07-27T08:03:01Z`

复审状态：`PHASE_0A_CONTRACT_REVIEW=FAIL`。原确认只证明当时的目标和授权，
不覆盖后续发现的合同 blocker；本修订必须重新通过独立复审后才能成为冻结输入。

## 目标与验收需求

| ID | 需求 | 可验证条件 |
|---|---|---|
| R-001 | 质量优先于速度 | 速度、token、重试次数不进入 verdict；不得通过降级覆盖、证据或标准换取完成。 |
| R-002 | 禁止自洽放水 | 方案作者/审核者、测试执行者/证据审核者、报告作者/终审者必须分离；作者不能关闭自己的 blocker。 |
| R-003 | Master 独立于 LangGraph | Master 只负责用户交互、生命周期和受约束传输；事实、门禁、状态和终态由持久内核产生。 |
| R-004 | 用户确认后才创建测试代理 | 未收到逐次“可以开始测试”确认时，不创建正式 A–F；Phase 0B probe 也需单独 capability-test 授权。 |
| R-005 | 子代理长期可见且可追溯 | 每个新 source baseline 使用全新六角色 generation；同一 source baseline 的新 run 可复用仍有效的 generation。registry、dispatch、claim、receipt、evidence、authority event 和 Phase 0B 验收均以 `thread_id + session_id` 为物理身份唯一键；`agent_handle` 仅作带观察来源的可选定位元数据。 |
| R-006 | 禁止测试期间立场注入 | 活动 run 中用户文本不得进入节点 payload；范围、要求或预期变化必须进入与用户取消相同的独立取消收敛协议，当前 run 收敛后再创建新 baseline/run。 |
| R-007 | 禁止同级代理通信 | A–F 只能经父 Master 接收内核 action；同级联系、创建后代、跨角色写入、间接文件传话必须被平台阻止或权威事件检出。 |
| R-008 | 缺陷按事实类型路由 | 测试流程缺陷返回责任节点；Master/需求/方案上游缺陷终止自动图；产品缺陷继续完成 E/F，再交 Master 与用户讨论。 |
| R-009 | 用户保留发布决策权 | reviewer 给事实和意见；用户风险接受作为追加记录，不能改写 Aegis 事实终态。 |
| R-010 | 基线变化与环境漂移分层处理 | 代码、配置、依赖、Skill、策略或声明环境合同变化产生新 source baseline、run 和 generation。活动 run 的观测执行环境 snapshot 漂移终止该 run，并使该 run 旧 execution-contract 证据失效；声明环境合同不变时，新 run 可复用同一 source baseline、仍有效的 generation 和仍适用的 B-approved plan。 |
| R-011 | 极端场景必须现实相关 | 纳入有可证明触发路径且概率/暴露足以影响质量判断的场景；安全、权限、不可恢复损失、法律或系统扩散场景即使低概率也纳入。 |
| R-012 | 本地邮筒与远端证据分离 | `artifact_path` 是 run 内本地 Windows 绝对路径；远端证据可原地保留，但本地索引必须记录身份、命令、返回码、UTC、环境和哈希。 |
| R-013 | 时间维度唯一且可恢复 | campaign/run/attempt/action/event 使用不可复用 ID；状态、事件、动作、回执和证据可跨 Master 回合恢复。恢复结论必须由 crash 前后原像和不中断 reference trace 比较得到，不能由布尔自报或计数摘要得到。 |
| R-014 | 当前 Codex 能力必须实证 | 父子 thread/session 身份、长期保留、侧栏定位、权威事件、跨回合/重启恢复和职责隔离任一缺失即停止；禁止虚构独立 agent ID，禁止降级到旧 CLI、顶层任务或提示词隔离。 |
| R-015 | generation 原子创建 | 六次非事务创建采用 provisional batch；未全部验证前零 action；失败产生可追踪 orphan，旧 active generation 不变。 |
| R-016 | replacement 原子切换 | 单角色替换只增加该 role 的 revision；旧 identity 晚到回执不能驱动 gate；容量不足时创建前阻断。 |
| R-017 | 保留容量显式化 | 基础认证合同 `G=2, R=6, P>=18`；active、retained、provisional、orphan、lost、superseded、replacement 全计入物理容量。 |
| R-018 | E/F 不能省略 | 产品缺陷、环境阻塞和 PASS 候选均须形成报告并经终审；E/F 未批准时不得产生产品/环境/PASS 终态。 |
| R-019 | verdict 可复算 | `VerdictInput.v1 -> GraphDecision.v1` 为无外部读取的确定性纯函数；非法或不闭合组合 fail closed。evaluation 必须冻结输入 schema、SUT 入口、输出 schema、runner、oracle 和 comparator。SUT 只接收 `subject/context_objects/fixture_refs/mutation/observed_state` 五字段，stdout 只输出 `SutDecision.v1`；outer evaluator 形成 `RunnerExecutionRecord.v1` 并嵌入 `EvaluationRunnerOutput.v1`。SUT 不得取得 case ID、expected、runner 元数据或 `oracle.reference_trace_fixture_id`；reference trace 与同 case 的 `input.fixture_refs` 相交时，进程创建前拒绝。五字段 projection 只防接口泄漏，不等于文件系统隔离。 |
| R-020 | 自评分不得成为 gate | 满意度分、质量自评、信心、完成声明、旧 95 分均不得决定 v2 verdict；95 只作 v1 迁移告警下限。 |
| R-021 | 取消独立且最高优先收敛 | cancel/scope-change 请求一经持久接受，立即停止普通 verdict 和新派发。每个 dispatched action 与 external job 必须取得终态，或逐项登记位置、最后状态、可能副作用、owner 和复核方法后，才能形成取消终态；integrity、upstream defect 或 unknown side effect 只能作为取消事实登记，不能抢占取消控制。 |
| R-022 | repo/runtime 边界固定 | repo 只保存 schema、角色规范、机器无关策略、migration 和示例；thread/session ID、可选 sourced handle、Master task ID、绝对本地路径和凭据位于显式 repo 外 runtime root。 |
| R-023 | execution contract 与 registry 解耦 | `execution_contract_id` 只绑定 source baseline、B-approved plan、execution-environment snapshot 和 schema version。registry snapshot、`thread_id + session_id`、generation 与 revision 逐 action/claim/receipt/evidence 绑定。D 已接受的完整证据保留其原 registry snapshot 和 producer；replacement 只使受影响且未完成的 attempt 失效。 |
| R-024 | case 与 supersession 追加不可变 | case、原 expectation、must-detect 分类和 `case_sha256` 永久不可编辑。supersession 使用独立追加事件，绑定原 case hash、用户变更决定和独立 reviewer 记录。发布门禁从完整 parent chain 重放事件，只运行链末最新有效的 `ACTIVE` must-detect 集。 |
| R-025 | Phase 0A 冻结可外部证明 | 冻结记录必须枚举精确文件域；每个 `FreezeInput` 固定 `logical_path/locator/artifact_kind/byte_domain/byte_size/raw_sha256/semantic_jcs_sha256/leaf_sha256`。`byte_size/raw_sha256` 永远绑定 locator 原始 bytes；JSON 另绑定 JCS semantic hash，二者都进入 leaf。文件域包含 `.gitattributes`、`pyproject.toml`、当前平台 lock、全部 generator/oracle/comparator source 及 source manifest；只有 hash 没有可取原像无效。modified/untracked 原像用 `git hash-object -w --no-filters <path>` 存入未 stage/未 commit 的 CAS blob并回读复核，或使用有外部 locator/event 的 frozen snapshot。记录持久化 freeze producer 的 `thread_id/session_id/turn_id`，并绑定完整 code-absence inventory、域外 disposition、独立复审产物及 Codex reviewer final event；独立性不得依赖调用者补传 identity。root 必须写入仓库外、Master 不能改写的追加型权威事件；事件必须绑定候选外预授权 provider/policy、event ID/log position/committed UTC、Codex version/protocol hash、parent spawn/delivery tool-call、reviewer thread/session/turn/final item、`agentMessage/final_answer` 和完整生命周期。caller bool/reader、本地 app-server/history/rollout/hash chain/HMAC/opaque attestation 均不构成 authority。无具体独立 adapter 或可离线复验的外部 proof 时，生产 finalize/verify 与 frozen-record validator 必须 fail closed；pending validator 也返回 `valid=false`、`phase_complete=false` 和非零 exit，仅可单列 `structural_valid=true`。synthetic seam 产物必须被生产 schema 拒绝。首个实现提交必须证明在该锚点之后且基于同一冻结树。 |
| R-026 | JSON 与采集 preimage 唯一 | schema bundle 每个 JSON entry 与 bundle 自哈希均使用 RFC 8785 JCS UTF-8 域。Codex app-server 兼容键只取固定命令生成的 `codex_app_server_protocol.v2.schemas.json`。source diff 使用固定 Git 参数并按 stdout 原始字节哈希；registry state 使用版本化完整对象的 JCS 哈希并绑定数据库 event head。 |
| R-027 | 原始 fixture 与工件原像齐全 | 普通 corpus 的每个 payload、authority record、result 和外部效果必须是仓库相对不可变 raw fixture 或内联精确字节。D snapshot、E report candidate/basis、F review/basis 均有版本化原像；gate 加载原像、重算 ID 并验证 producer、run、state sequence、execution contract 和前置绑定。`evaluation/aegis_v2/reference/` 下 generator/verdict/closure/comparator、辅助模块、CLI、README、`tests/test_reference.py` 和 `source_manifest.v1.json` 的完整原像同样必须可取、可重算；manifest 必须通过 bundle 内 `ReferenceSourceManifest.v1` schema，不能只靠 harness 自验。 |
| R-028 | 协议负例覆盖消费语义 | 每个规范绑定字段均有单字段 mutation；另覆盖 duplicate/out-of-order/omitted/reordered/truncated raw bytes、过期 action、旧 turn 和唯一消费。任一变异 fail closed。 |
| R-029 | 故障与隔离覆盖真实边界 | recovery、side effect、generation、replacement 和 isolation case 必须包含真实前后 trace、journal/query/receipt/event。generation 故障注入需 batch 级 cleanup preauthorization；隔离覆盖 A–F 每个角色乘四类越权通道。 |
| R-030 | defect 与极端场景可审计 | 每个 case 记录 defect class。极端场景记录 trigger、boundary、概率/暴露证据或假设、impact、rationale；排除项进入不可变 risk register 并绑定 freeze root。 |
| R-031 | 依赖与解释器可复现 | 固定 `setuptools==83.0.0`、`jsonschema[format-nongpl]==4.26.0`、`rfc8785==0.1.4`、`langgraph==1.2.9`、`langgraph-checkpoint-sqlite==3.1.0`。v1 的 `SUPPORTED_PLATFORM_SET={windows-cpython313}`，只使用 `pylock.windows-py313.toml`；Linux/其他平台在新增独立 PEP 751 lock、runner-contract revision、environment certification 并重新冻结前 fail closed。每次执行用仓库外新 venv、hash-verified wheel、无 `PYTHONPATH`，argv 固定为绝对 venv Python 加 `-I -X utf8 -m aegis.sut <ENTRYPOINT_ID>`；环境只含 `AEGIS_RUNNER_MODE=FROZEN_EVALUATION`、`LANGGRAPH_STRICT_MSGPACK=true`。必须证明 lock 的传递依赖 `xxhash==3.8.1` 来自隔离 venv 而非仓库 `src/xxhash.py`。 |
| R-032 | evaluator 与 SUT 机制隔离 | runner policy 保持机器无关；每次 run 单独记录实际 Python path/hash/version/ABI、lock、project wheel 和 installed distributions。SUT cwd 是 repo 外 `ISOLATED_EXECUTION_ROOT`。ordinary/conformance case 的 catalog fixture 在 materialization 前必须解析到各自 runner，且每个规范 Windows `logical_runtime_path` 严格位于 `fixture_mount.logical_runtime_root` 下；任何路径逃逸在创建文件前拒绝。release-grade runner 必须由认证 isolation backend 证明：外部 venv 只读/可执行，当前 fixture 只读，本 case outbox 只写/create-new；repo/evaluation/expected/reference/其他路径不可读，network deny。无该能力时 binding=`UNVERIFIED_ISOLATION`、output=`BLOCKED_UNVERIFIED_ISOLATION`，不启动 SUT 且阻断 release。generator/oracle/comparator 不能导入、调用或复用 SUT 决策函数；property domain 必须全量执行。其 AST/import policy 只作冻结源码变更门禁；release-grade reference execution 另需认证 evaluator isolation，禁止 network 和 shell/process creation，隔离 production package/repo，只开放冻结源码与角色声明通道。缺该证明不得形成 release PASS。平台扩展创建新 lock、runner revision、execution-environment evidence 和 freeze，但不能改 case、expected 或其他 corpus bytes。公开 corpus 可预先获知是剩余风险，只能用独立作者、holdout、全量 property 和强隔离降低，不能宣称已消除。 |

## 不可接受替代

- 普通顶层 Codex 任务代替父任务中的长期 subagent。
- `codex exec resume` 代替父级原生协作能力。
- 复用旧线程承载新 source baseline。
- Master 转述或改写节点结果后作为权威来源。
- 只凭文件存在、路径存在、agent 自述或数值分判定通过。
- 因超时、轮次、token 或“已经很接近”而放宽 blocker。

## 本轮授权边界

原用户确认没有被重解释为 Phase 0A PASS。本轮只允许修订、补证、重算和复审。

本轮可执行：

- Phase 0A 合同、schema、evaluation、fixture、冻结记录定义和独立复审。
- Phase 0B 的纯本地模型、runner、oracle、fixture 和无真实 child 的测试。

本轮不可执行：

- 在独立复审 PASS 前写入 Phase 0A 冻结终态或进入 Phase 0B live probe。
- 创建任何正式 A–F。
- 创建 Phase 0B 真实 probe subagent。
- 关闭或重启 Codex Desktop。
- 对真实目标项目运行测试图。

这些行为必须等待用户明确批准 capability test 或正式测试。
