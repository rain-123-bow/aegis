# Aegis 对抗审核报告

日期：2026-08-17

结论：REQUEST_CHANGES

## 审核基线

- 公共仓库：C:\Users\playm\Documents\self-git\aegis
- 分支：agent/aegis-seal-core-integration
- HEAD：a8598437c0f7ca0b2d1c1baf5610cdc647ded282
- 私有仓库：C:\Users\playm\Documents\self-git\AegisSealCore
- 分支：main
- HEAD：90281bce2fe48f2c30ab9158e28f43f96aaded8c
- 审核方式：一个 fresh-context subagent，只读；先测试、后实现、再契约。
- 未运行测试、构建、可执行文件、网络或外部服务。
- 未读取 C:\Users\playm\Documents\self-git\aegis\.aegis\runs\。

## 真实缺陷

### P1-01 C-start 可复用伪造或篡改的父 run

位置：src/aegis_runtime.py:1020、1104、3159。

父 RUN_STATE.json 只经过 schema、run ID、reservation token 格式校验。复用路径不校验父 reservation 数据、项目根、project ID、Seal、remote witness、planning turn/evidence/checkpoint；父状态还能指定任意绝对 artifact 路径。伪造 terminal/completed 状态与匹配哈希后可直接进入 C。

修复：执行完整父 run 只读恢复校验；固定父 artifact 路径；验证 reservation、项目/Seal/witness、approved round、TraceRelay evidence、checkpoint；child handoff 绑定不可变父终态摘要。

### P1-02 Context pack 只做文件哈希

位置：src/aegis_runtime.py:1062、1211、1494。

任意文件，包括空 JSON 或其他项目的 pack，都可成为 A-F reasoning context。没有 schema、project/task/role、Seal、engineering manifest、ledger revision、查询范围、证据索引校验。

修复：定义并机械校验 context-pack schema；复制到 run-owned 固定路径；绑定项目、任务、run、Seal、工程输入、ledger revision、查询范围和证据描述符。

### P1-03 冻结输入仍从 live 工作树读取

位置：src/aegis_runtime.py:498、637、940、977、1780。

Coordinator 只快照 engineering manifest，不快照需求和方案文件；execution control 暴露 live project_root。节点执行期间改动、读取改后内容、返回前恢复原字节，可绕过节点边界哈希。

修复：生成完整不可变输入快照；agent 只访问快照；代码使用隔离只读 worktree。若必须访问 live tree，增加文件身份锁定和文件系统变更日志，不能只比较前后哈希。

### P1-04 mutation 终止记录缺少追责证据

位置：src/aegis_runtime.py:1783、3102。

Seal 错误被压成统一字符串；RUN_STATE 仅保存异常类型、消息和责任节点，没有变化路径、旧新哈希、发现时间、文件身份或可用进程证据。

修复：持久化结构化 mutation event，包含 path、expected/actual size/hash/file ID、observed_at、node、process/session。

### P1-05 Test Evidence Manifest 可由 C 自证

位置：src/test_evidence_manifest.py:145、179、235；src/aegis_runtime.py:1876。

C 可自填 command、cwd、environment、时间、exit_code、stdout/stderr/raw result。Coordinator 只校验类型、路径、哈希并插入 App Server turn 的 TraceRelay session；该 session 不证明真实测试进程执行过对应命令。

修复：由 Coordinator 或受控 runner 启动测试并签发不可由 C 编辑的 execution receipt；manifest 只引用 receipt ID/hash，并逐条绑定进程、命令、cwd、环境、时间、退出码和输出。

### P1-06 remote witness 未证明 Seal 对应其声明的 Git commit

位置：src/project_seal_store.py:120、157；src/remote_seal_witness.py:123。

record_project_seal 接受调用者传入 git_head_before_record；未读取真实 HEAD、拒绝 dirty scoped tree或从 commit tree 构造 manifest。工作树改动可进入 Seal，同时 witness 仍声明当前 HEAD。

修复：记录时读取真实 HEAD；拒绝 dirty scoped tree；从目标 commit tree 构造并比对 manifest；要求 witness.git_commit、seal.git_head_before_record、HEAD 三者一致。

### P1-07 Master 确认 F 失败时未重验 verdict 证据

位置：src/final_review_confirmation.py:57、69、80、103。

F 失败后可修改 FINAL_REVIEW.md 并保留原 verdict。confirmation 重新散列新 review，只核对 verdict 文件哈希，没有调用完整 verdict validator，也没有重验 verdict 内旧 evidence descriptors。

修复：确认前重验 FAIL verdict、全部 evidence descriptors 与 F attempt 封存的 evidence ID/hash；Master review 绑定精确 evidence set。

### P1-08 跨 run 共享 registry/thread 无并发租约

位置：src/agent_registry.py:181、205；src/aegis_runtime.py:2083。

两个 run 可读取同一 revision、同时 resume 同一 role thread；并发 persist 最后写入覆盖。revision 没有 CAS；active record 没有 run/turn lease；reservation 只约束相同 run ID。

修复：使用事务存储；revision CAS；role-thread 唯一 active run/turn lease；同项目并发 run 排队或 fail closed。

### P1-09 F verdict 固定路径检查可被 symlink 绕过

位置：src/final_review_verdict.py:47、49；src/aegis_runtime.py:1999。

supplied path 与 expected path 都先 resolve。固定文件若是指向外部的 symlink，两者解析为同一外部目标，路径检查通过。

修复：先校验 lexical fixed path；逐组件拒绝 symlink、junction、reparse point；使用 no-follow handle 读取并核对最终 file ID。

### P1-10 Windows 大小写和 reparse point 可绕过 runtime scope

位置：src/runtime_behavior_scope.py:253、264、317。

include_roots 中 .AEGIS 在 NTFS 上可指向 .aegis，但文本检查只拒绝小写；代码只检查 is_symlink，未拒绝 directory junction 等 reparse point。

修复：使用 Windows canonical case/normcase；拒绝全部 reparse points；通过 handle 核对 final path、volume serial 和 file ID。

### P2-01 重复语义问题依赖 agent ID 与整对象文本相等

位置：src/aegis_runtime.py:1377、1384。

相同问题更换 semantic_issue_id、列表顺序或措辞即可避开 repeated_unresolved_issue_ids。

修复：持久化稳定语义 identity；由独立 reviewer 输出 predecessor/closure 映射；Coordinator 验证 closure evidence。不得添加尚未获用户确认的终局政策。

### P2-02 Seal chain 并发 append 可丢记录

位置：src/project_seal_store.py:131、182、320。

两个进程同时读取 sequence N，可各自生成 N+1；后一次 os.replace 覆盖前一次，链历史丢失。

修复：独占锁或事务存储；提交前 CAS 检查末端 sequence/seal；冲突失败并重算。

### P2-03 Skill 只有本地意图哈希，没有注入回执

位置：src/aegis_runtime.py:688、2134；docs/AEGIS_ARCHITECTURE_CONTRACT.md:171。

App Server 忽略、截断或错误应用 developer instructions 时，RUN_STATE 仍只记录本地计算的哈希。无法证明实际注入成功。

修复：要求 App Server 返回可验证 instruction receipt；接口不支持时将边界标记为未验证并 fail closed。

## 契约缺口

### P2-04 Scope reviewer/user confirmation 是不可验证占位字段

位置：src/runtime_behavior_scope.py:213、227；docs/RUNTIME_BEHAVIOR_SCOPE_CONTRACT.md:9。

任意 64 位十六进制哈希和非空 confirmation ID 即被视为用户确认。契约未定义报告、用户决定的固定路径、身份、授权域、签名或权威回执。

修复：定义独立 decision manifest，绑定 scope hash、project ID、reviewer identity、user authorization identity、时间和签名/外部权威回执。

### P2-05 mutation 终局枚举矛盾

位置：docs/AEGIS_ARCHITECTURE_CONTRACT.md:89、93；docs/runtime_coordinator.md:83；src/aegis_runtime.py:3102。

架构契约要求 engineering_verdict=INVALIDATED；运行文档和代码写 UNDETERMINED。

修复：由用户确认唯一枚举及语义，再统一 schema、代码、测试和文档。

## 外部门禁

- docs/AEGIS_RUNTIME_SCOPE_PROPOSAL.md 仍为 PROPOSED；没有 reviewer PASS 与用户确认时，生产 preflight 应拒绝。
- 私有 AegisSealCore 源码仍是 modified-uncommitted；vendored binary 不是 release-ready。
- 未验证 binary 确由当前私有源码 diff 构建。
- 未验证真实 protected ref、远端保护策略、Codex/App Server、TraceRelay、Postgres/pgvector。
- 以上属于当前 fail-closed 边界；实现若绕过才构成新增缺陷。

## 覆盖边界

- 检查公共仓库全部相关 tracked diff、列明的新增实现/测试/契约/skills。
- 检查私有核心全部 tracked diff和公共 provenance。
- 未逐字检查长 skill 的未变正文。
- 未读取 .aegis/runs。
- 未运行测试、构建、动态 symlink/junction PoC或外部服务。
