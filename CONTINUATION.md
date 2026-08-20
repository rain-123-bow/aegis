# Aegis Recorder continuation

## 最新检查点：Round 11 两项 P1 闭合后暂停

记录时间：`2026-07-29T09:59:57.8238067+08:00`

状态：`ROUND_11_TWO_P1_CHECKPOINT_COMPLETED_AND_PAUSED`

- 计划状态仍为
  `ROUND_11_CONTRACT_AND_SNAPSHOT_RECONCILIATION_IN_PROGRESS`。
- 未设置 `READY_FOR_FINAL_REVIEW`。
- 未启动下一轮 reviewer、最终方案审核或 R11A 实现。
- 未暂存、未提交、未推送。

### 本原子阶段完成

1. 跨记录 UTC 顺序合同：
   - dispatch、START、reviewer-final、END、user-decision、failure 之间不做
     UTC 大小关系验证。
   - 跨进程时钟回拨合法。
   - UTC 只验证语法、同一捕获内的局部关系和重复字段相等。
   - 真实顺序由 content-ID predecessor 链和持久化状态机证明。
2. native 顶层调用输入绑定：
   - 增加精确 `NativeInvocationDeclaration.v1`。
   - native evidence 从五前像升级为六前像。
   - 聚合器签名直接接收 invocation declaration 原始字节。
   - trace、expectation、result-schema-derived entrypoint、lifecycle 必须一致。
   - BUILD 的 source locator、artifact locator、request 原始字节必须绑定实际
     `DIRECTORY_OPEN`、manifest/result/port 关系。
   - PUBLISH_TRANSITION 的 binding、record 原始字节必须绑定实际
     open/write/verify/publication/result 关系。
   - receipt 增加 `invocation_declaration_sha256`。
   - mutation 矩阵加入 A→B 输入替换、locator swap、declaration/trace
     mismatch、binding/record 脱离实际调用。
   - `THREAT_MODEL.md` 同步为六前像威胁闭合。

本阶段落盘文件：

```text
docs/recorder/IMPLEMENTATION_PLAN_FINAL.md
docs/recorder/THREAT_MODEL.md
CONTINUATION.md
```

### reviewer 搜索方式确认

已向两个现有 reviewer 询问；未创建新 subagent。

- 两者都采用增量反例搜索。
- 两者都没有把“找到至少一个 P1”作为主动停止条件。
- reviewer 会分段继续扫描，但发现 P1 后立即上报。
- 主 agent 收到首个 finding 后立即修改文件，导致被审 SHA 失效并中断
  未完成范围。
- 每次修订又引入新合同，使后续跨合同反例只能在下一 SHA 暴露。
- “每轮一个新问题”主要来自移动目标和即时修订，不是 reviewer 故意
  挤牙膏。

后续必须改为批量收敛：

1. 冻结一个不可修改 SHA。
2. 审查期间作者不得修改目标字节。
3. reviewer 在固定矩阵内累计 findings，不触发即时修订。
4. 每个范围完成正常、失败、崩溃、重放、并发、边界值反例搜索。
5. 所有 reviewer 完成后一次性合并、去重 P0/P1。
6. 一次性修订整批问题。
7. 冻结新 SHA，从头执行完整矩阵；零 P0/P1 才进入最终独立审核。

### 验证证据

冻结 snapshot 代码和测试在本轮较早时已执行：

```text
Windows:
python -m unittest evaluation.aegis_v2.tests.test_review_snapshot
Ran 62 tests in 268.031s
OK (skipped=2)

WSL:
python -m unittest evaluation.aegis_v2.tests.test_review_snapshot
Ran 62 tests in 11.652s
OK
```

WSL 使用临时安装的 `rfc8785==0.1.4`；临时目录已清理。第一次 WSL
调用因 PowerShell CR 被传入模块名而在测试前失败，属于调用器错误；
修正后的 exact-byte 运行结果如上。

本原子阶段修改的是文档合同。冻结代码与测试哈希未变，因此未重复执行
62 项 suite；改为执行直接相关的一致性检查：

```text
Windows strict UTF-8: PASS
UTF-8 BOM: 0
CR bytes: 0
reviewed trailing whitespace: 0
Markdown fences: even
plan READY status count: 0
five-preimage stale native references: 0
UTC cross-record inequality requirement: 0
git diff --check: PASS
git diff --cached --check: PASS

WSL git diff --check: PASS
WSL CR scan: PASS
WSL /tmp/aegis-r11-* directories: 0
Windows/WSL relevant-file SHA-256: identical
```

冻结哈希：

```text
d203b6af117ae03dca57d223b7fa30384a3f622af44c85d506735ef5b8963116  docs/recorder/IMPLEMENTATION_PLAN_FINAL.md
0e8c22ad02746c19911fe0ce56d698f5f06bf51db9d84db52cfd9703845fc025  docs/recorder/THREAT_MODEL.md
078c2fb82b13a25994f5b19dd5a1c9532c0c97a7883d0d87d173cd5f35908e3a  docs/recorder/PLAN_REVIEW_REPORT.md
07faf9d415d0e1e5285c0f275050a65c31059549e1f6df35c3a2c1ccf8d21d05  evaluation/aegis_v2/review_snapshot.py
c5a9c1dba3c9bc56960389a4d2917304e5b08ebb01e886da6ebfe08567f88d93  evaluation/aegis_v2/tests/test_review_snapshot.py
```

### 尚未解决

只记录已知项；本阶段未继续扫描或修复。

1. required absence 缺少 no-follow 的“任意对象类型已存在”探针。
   当前 `OBJECT_OPEN` 必须预先指定 DIRECTORY 或 REGULAR_FILE，无法在不
   猜类型时证明目录、链接或特殊对象占位。
2. port outcome 与 `BoundObjectFacts.v1` 无法表达特殊对象类型和
   `UNSUPPORTED_OBJECT_TYPE`，无法唯一映射 symlink、FIFO、device 到
   `UNSUPPORTED_FILE_TYPE`。
3. 当前最新字节尚未在单一稳定 SHA 上完成端到端 specialty rereview。
4. 当前 `PLAN_REVIEW_REPORT.md` 仍是 FAIL/revision-in-progress；没有针对
   最新稳定字节的独立最终审核。
5. R11A 实现与 RED 测试尚未开始。

### Git 现场

```text
branch = v0.1.2-alpha-langgraph-reset
HEAD   = 1933fab4fd042f9bb884274c87443d1cb618a859
staged = 0
tracked modified = 11
untracked files = 212
tracked diff = 11 files changed, 82 insertions(+), 77 deletions(-)
```

`git status --short --branch`：

```text
## v0.1.2-alpha-langgraph-reset...origin/v0.1.2-alpha-langgraph-reset
 M .aegis/master/subagents/MASTER_SUBAGENTS_MANIFEST.json
 M config/agent_registry.json
 M config/node_message_schema.json
 M docs/flat_node_graph.md
 M docs/langgraph_json_contract.md
 M skills/aegis_test_plan_reviewer/SKILL.md
 M skills/aegis_test_result_reviewer/SKILL.md
 M src/langgraph_contract.py
 M src/main.py
 M test/test.py
 M test/test_langgraph_contract.py
?? .gitattributes
?? .gitignore
?? CONTINUATION.md
?? docs/aegis_v2_codex_static_evidence.md
?? docs/aegis_v2_phase0_contract.md
?? docs/aegis_v2_requirements.md
?? docs/aegis_v2_upgrade_plan.md
?? docs/decisions/
?? docs/recorder/
?? evaluation/
?? pylock.windows-py313.toml
?? pyproject.toml
?? schemas/
```

`git diff --stat` 只覆盖 tracked 文件。Recorder 文档、evaluation、schema
和本检查点均为 untracked；必须结合
`git ls-files --others --exclude-standard` 查看。当前 tracked diff 仍完整
保存在工作树；本阶段未回退既有修改。

### 下一步原计划

仅在用户明确继续后：

1. 先闭合已知的 port 特殊对象表达能力问题。
2. 冻结新的计划 SHA。
3. 按固定审查矩阵启动批量 specialty review；审查期间禁止修改文件。
4. 收齐完整 finding 批次后统一修订。
5. 新 SHA 从头回归。
6. specialty review 达到 P0=0/P1=0 后，才启动全新最终方案 reviewer。
7. 最终方案审核通过后，才进入 R11A。

恢复命令：

```powershell
Set-Location C:\code\aegis-20260727
git branch --show-current
git rev-parse HEAD
git status --short --branch
git diff --check
git diff --cached --check
git diff --stat
git diff --numstat
git diff
git ls-files --others --exclude-standard
Get-FileHash -Algorithm SHA256 -LiteralPath `
  docs/recorder/IMPLEMENTATION_PLAN_FINAL.md,`
  docs/recorder/THREAT_MODEL.md,`
  docs/recorder/PLAN_REVIEW_REPORT.md,`
  evaluation/aegis_v2/review_snapshot.py,`
  evaluation/aegis_v2/tests/test_review_snapshot.py
```

WSL：

```bash
cd /mnt/c/code/aegis-20260727
sha256sum \
  docs/recorder/IMPLEMENTATION_PLAN_FINAL.md \
  docs/recorder/THREAT_MODEL.md \
  docs/recorder/PLAN_REVIEW_REPORT.md \
  evaluation/aegis_v2/review_snapshot.py \
  evaluation/aegis_v2/tests/test_review_snapshot.py
git diff --check
```

### 暂停完整性

- 所有本阶段修改、reviewer 方法答复、验证结果和恢复入口已落盘。
- 无关键结果仅存在于终端、临时目录或 agent 内存。
- 两个 reviewer 已完成。
- 两个旧 `pending_init` Phase 0 agent 已再次 interrupt，未进入执行。
- 未提交、未推送。
- 到此暂停。

---

以下内容是 `2026-07-28` 历史检查点，仅供追溯，不是当前恢复入口。

记录时间：`2026-07-28T23:47:04.8509162+08:00`

## 当前状态

- 当前原子阶段：`CPython 3.12.3 getpath 合同闭合`。
- 阶段状态：`COMPLETED_AND_PAUSED`。
- 下一阶段尚未启动。
- 生产 Recorder 代码与 RED 测试尚未开始。
- schema bundle 未重建。
- 未暂存、未提交、未推送。
- 上一个 Phase 0A authority 快照已完整保存在
  `docs/recorder/CONTINUATION_PHASE0A_AUTHORITY_SNAPSHOT.md`。

## 本阶段完成

### 全项目 LF

- 新增 `.gitattributes`，默认文本固定 `LF`。
- Recorder artifact 与 evaluation fixture 明确 `-text -eol`。
- Windows 与 WSL 对同一工作树独立扫描：
  - 工作区文件：`305`
  - 严格 UTF-8 文本：`257`
  - 非 UTF-8 二进制：`48`，实际为 `47` 个 `.pyc` 和 `1` 个 `.png`
  - UTF-8 文本含 CR：`0`
  - UTF-8 BOM：`0`
- 二进制内偶然出现的 `0d0a` 字节序列未改写；它们不是文本换行。
- Markdown 奇数 fence：`0`。
- Markdown 行尾空白：`0`。

### getpath 缺口

独立只读审计针对旧 POSIX 快照返回：

```text
P0=0
P1=2
P2=0
```

缺口：

1. 旧合同只在 bootstrap 后检查三项 `sys.path`；CPython 已可能从环境编译
   prefix 加载未批准的 `encodings`。
2. RED 没有覆盖首语句前的 venv、`._pth`、build marker、ZIP/stdlib
   landmark 和 stderr 行为。

选定闭合：

```text
P/python3.12
P/python3.12._pth       exact bytes: lib/python3.12\n
P/lib/python3.12/
P/lib/python3.12/lib-dynload/
```

- V1 固定 exact CPython `3.12.3`、解释器 SHA-256、`PLATLIBDIR=lib`、
  `VPATH=..`。
- `python3.12._pth` 固定 15 bytes，SHA-256：
  `489d6a4a7ff6f07d321bda6f61470f964de6fa753ee3e86078ea1b56ded7647a`。
- 初始 `sys.path` 仅为 `[stdlib_root]`。
- `sys.executable`、prefix/base-prefix、exec-prefix/base-exec-prefix、
  `_stdlib_dir`、`platlibdir` 全部固定。
- launcher 在 `execveat` 前认证 getpath 文件、闭合根成员，并拒绝
  `pyvenv.cfg`、build marker 和 competing `._pth`。
- bootstrap 首语句后 no-follow 重开、验证并留存 getpath FD。
- CPython 的早期 pathname 读取仍明确属于 root/operator 外部信任边界；
  事后复核不伪装成 held-FD 读取。
- stdlib manifest 禁止 `os` 行；`os` 只能来自批准的 frozen finder。
- RED 矩阵已加入 getpath 字节、身份、权限、override、patch/build/layout
  漂移和验证后替换。

同步文件：

```text
.gitattributes
docs/recorder/POSIX_ADAPTER_CONTRACT.md
docs/recorder/REQUIREMENT_ADDENDUM.md
docs/recorder/THREAT_MODEL.md
docs/recorder/CODEBASE_FACTS.md
docs/recorder/IMPLEMENTATION_PLAN_FINAL.md
docs/recorder/PLAN_REVIEW_REPORT.md
docs/decisions/0003-recorder-protected-runtime-deployment.md
```

### WSL 实证

- 复制 exact `/usr/bin/python3.12` 到临时 ext4 `P/bin`。
- 存在 `P/lib/python3.12/os.py` 时，默认 getpath 选择 `P` 三路径。
- 删除 `os.py` 后，stdlib/prefix 回退 `/usr`，dynload/exec-prefix 留在
  `P`；旧合同因此不可实现为批准来源闭包。
- direct-`P` 单行 `._pth` 在 pathname launch 与 held-FD
  `os.execve(fd, ...)` 下均得到：
  - `sys.path == [P/lib/python3.12]`
  - prefix/exec-prefix/base-prefix/base-exec-prefix `== P`
  - `_stdlib_dir == P/lib/python3.12`
  - filesystem-backed entry modules恰为三个 `encodings`
  - `os` 未加载且 `_imp.is_frozen("os") == true`
- 所有 `/tmp/aegis-*` probe root 已由脚本 trap 删除。
- 关键结果已写入 `CODEBASE_FACTS.md` 与 `PLAN_REVIEW_REPORT.md`。

## 验证

### 聚焦测试

```powershell
python -m unittest `
  evaluation.aegis_v2.tests.test_build_schema_bundle `
  evaluation.aegis_v2.reference.tests.test_reference `
  evaluation.aegis_v2.reference.tests.test_audit_remediation
```

结果：`42/42 PASS`，`7.071s`。

### schema 派生物检查

```powershell
python -m evaluation.aegis_v2.build_schema_bundle --check
```

预期结果：exit `1`，不得当作测试失败：

```json
{"bundle_sha256":"sha256:c9357671354214a3513cfd00195ff81990d268ccd94a20e55d08650734641061","schema_count":53,"schema_version":"SchemaBundleBuildReport.v1","state":"STALE"}
```

未运行 `--write`。只有独立最终计划审核 `P0=0/P1=0` 后才允许重建。

### 文档与换行

```powershell
git diff --check
git check-attr -a -- `
  evaluation/aegis_v2/fixtures/reference/pass/audit_tail.bin `
  docs/recorder/POSIX_ADAPTER_CONTRACT.md
```

- `git diff --check`：PASS。
- fixture：`text/eol unset`。
- POSIX 合同：`text set`、`eol lf`。
- Windows/WSL LF 扫描：PASS。
- getpath 固定版本、解释器摘要、getpath 摘要、单项路径和旧三项路径清除
  的机械断言：PASS。

## 当前审核边界

- getpath 修改后的稳定快照尚未接受定向复审。
- 旧 POSIX 审核不能授权新字节。
- 旧 Windows 审核曾返回 `P0=0/P1=0/P2=0`，但 plan、requirement、
  threat、ADR 已变化；最终稳定快照仍需重新确认。
- schema/JCS 定向审核曾返回 `P0=0/P1=0/P2=0`；schema 本阶段未改。
- 独立 `implementation_plan_reviewer` 尚未审核 Round 10。
- 不得把 42 项测试通过解释为方案审核通过或生产实现通过。

## 下一步入口

1. 重新计算最终审核输入文件的逐文件 SHA-256 与聚合 manifest。
2. 对 exact stable snapshot 运行 POSIX/getpath 定向只读复审。
3. 对同一 stable snapshot 重新确认 Windows 定向合同。
4. 将复审结果写入 `PLAN_REVIEW_REPORT.md`；任何 P0/P1 继续闭合。
5. 取得定向 `P0=0/P1=0` 后，创建全新
   `implementation_plan_reviewer`，只给精确 manifest，不给历史辩解。
6. 最终 reviewer 返回 `P0=0/P1=0` 后，处理 ADR 状态并再次核对最终字节。
7. 然后才运行 schema bundle `--write`、53-schema closure、完整 Phase 0。
8. Phase 0 通过后，按 TDD 先写 Recorder RED，再写生产实现。

禁止跨过第 2–6 步直接编码。

## 建议复验命令

```powershell
python -m unittest `
  evaluation.aegis_v2.tests.test_build_schema_bundle `
  evaluation.aegis_v2.reference.tests.test_reference `
  evaluation.aegis_v2.reference.tests.test_audit_remediation

python -m evaluation.aegis_v2.build_schema_bundle --check
git diff --check
git diff --cached --check
git branch --show-current
git rev-parse HEAD
git status --short
git diff --stat
git diff --numstat
git diff
git ls-files --others --exclude-standard
```

WSL 工作树路径：

```text
/mnt/c/code/aegis-20260727
```

## 冻结文件哈希

```text
6a64a14483606789af5d39bc9eb18bfa46b017aca7074738f2286d5ab6dfe3ab  docs/recorder/POSIX_ADAPTER_CONTRACT.md
1310a8ba2e262ef7df7ddc3e77258efbc0ccb100e177fbd1eff54c623b634d26  docs/recorder/SUPERVISOR_CONTRACT.md
20a1f14e033efacbd1e59b08f3a419809c556d539d75f3174b796aba599ffc28  docs/recorder/IMPLEMENTATION_PLAN_FINAL.md
a3ccb2bbe7568e10369c03121b69194e8d0579c17ac8e700b8fec23cd051c105  docs/recorder/REQUIREMENT_ADDENDUM.md
874834887714b62b87f39a2f911fcdc303e7dd23c9c524ed19db1596b3889479  docs/recorder/THREAT_MODEL.md
30fd85374f1c1cbea658b907398c9767d1bffd1490981068cd0deaee1c89098e  docs/recorder/CODEBASE_FACTS.md
48f032271cfb053e3073e6a5ff41132215ef95b151a8f044169d9c0a21b325f5  docs/recorder/PLAN_REVIEW_REPORT.md
ced5cdf7f77f4aabd9e80a94e26909f140265e1439b141357485034096ba34bb  docs/decisions/0003-recorder-protected-runtime-deployment.md
56c3d794434c7230c7ac57626f19bdd4f577fd71f7b462ddda8d8586bce9681f  .gitattributes
```

这些哈希是暂停前的阶段快照。修改任一文件后全部复审授权失效。

## Git 现场

```text
branch = v0.1.2-alpha-langgraph-reset
HEAD   = 1933fab4fd042f9bb884274c87443d1cb618a859
staged = 0
tracked modified = 11
tracked diff = 11 files changed, 82 insertions(+), 77 deletions(-)
```

`git status --short`：

```text
 M .aegis/master/subagents/MASTER_SUBAGENTS_MANIFEST.json
 M config/agent_registry.json
 M config/node_message_schema.json
 M docs/flat_node_graph.md
 M docs/langgraph_json_contract.md
 M skills/aegis_test_plan_reviewer/SKILL.md
 M skills/aegis_test_result_reviewer/SKILL.md
 M src/langgraph_contract.py
 M src/main.py
 M test/test.py
 M test/test_langgraph_contract.py
?? .gitattributes
?? .gitignore
?? CONTINUATION.md
?? docs/aegis_v2_codex_static_evidence.md
?? docs/aegis_v2_phase0_contract.md
?? docs/aegis_v2_requirements.md
?? docs/aegis_v2_upgrade_plan.md
?? docs/decisions/
?? docs/recorder/
?? evaluation/
?? pylock.windows-py313.toml
?? pyproject.toml
?? schemas/
```

`git diff --stat` 只覆盖 11 个 tracked 文件；Recorder 文档、schema、
evaluation 和本文件当前均为 untracked，必须同时用
`git ls-files --others --exclude-standard` 查看。

11 个 tracked 修改在本 Recorder 原子阶段开始前已经存在；本阶段没有
回退它们。

## 暂停检查

- 代码、文档、配置修改全部落盘。
- 审计发现、官方源码结论、WSL 实证、测试结果均已持久化。
- 临时 WSL probe root 已删除；无关键结果只存在于 `/tmp`。
- 无关键结果只存在于终端输出或 agent 内存。
- 无正在执行的子任务；两个旧 Phase 0 agent 记录仍显示
  `pending_init`，已调用 interrupt，未进入执行。
- staged：`0`。
- commit：未执行。
- push：未执行。
- 到此暂停。
