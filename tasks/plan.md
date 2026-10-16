# Aegis 可迁移性审查与修复计划

状态：本轮 Windows 本机解绑与当前环境验证已完成，结果见 [validation.md](validation.md)。另一台 Windows 的完整部署验收未执行；不实施其他平台适配。

## 目标与边界

消除对开发者个人目录、隐含工具安装位置和本机测试材料的依赖，保证另一台机器能够根据交付说明完成配置、验证与受控运行。

- AegisSealCore 源码、二进制及其适配器保持不变；不实施该组件的跨平台移植或编译。
- README 已明确给出处理办法的依赖事项不重复实现；缺少可执行步骤的安装环节仍记录为缺口。
- 不放宽封印、Git/SSH 身份、运行时固定输入和证据检查。
- 不复制个人密钥、Codex 登录信息、运行授权或旧运行的检查点充当新环境授权。
- 不重写 Git 历史，不更改第三方许可证。审查阶段不推送；2026-10-16 用户随后授权将当前改动提交、推送到现有分支。
- 保留本轮之前已有的 README、交接文档和验收准备代码变更。

平台边界已确认：完整运行器保留 Windows 限制。Windows 标准环境目录与经验证的 Git-for-Windows、Codex 安装布局作为部署前提写清；不改造平台安全后端。

## 已核对的问题

| 编号 | 证据 | 影响与处置边界 |
| --- | --- | --- |
| P01 | `config/seal_witness.json`；`src/remote_seal_witness.py::_load_witness_config`；`src/project_seal_store.py::_sealed_ssh_identity_spec` | 仓库提交了个人 SSH 私钥路径及身份摘要。需要分离路径定位与受审批身份描述，保留摘要验证与文件锁；私钥内容不进入仓库。修改当前版本不会清除历史中的路径。 |
| P02 | `src/reasoning_ledger/project.py::bootstrap_project_ledger` | 重复初始化先覆盖配置，再检查迁移 SQL；会重置已有 anchor，冲突失败也可能留下已修改的配置。必须先验证并复用已有身份，冲突时不写。 |
| P03 | `src/main.py::_relaunch_isolated_if_needed` | 在参数解析前依赖 `LOCALAPPDATA`，即使提供运行目录也无法绕过。按已确认的 Windows 范围保留，并作为部署环境前提明确说明。 |
| P04 | `src/runtime_identity.py` | Git 运行时枚举、SSH 和 Codex 依赖发现采用 Windows 安装布局。其他布局必须有明确、完整且经验证的运行时描述，不能只删除校验。 |
| P05 | `src/windows_job_runner.py`；`src/tracerelay_client.py`；`src/path_security.py`；`src/frozen_input_watcher.py` | 受管进程树、进程创建身份和不可变文件锁依赖 Windows；现有 POSIX 分支仅用于测试夹具。完整 macOS/Linux 运行需要新的安全后端及实机验证。 |
| P06 | `third_party/TraceRelay/README.md`；`requirements-runtime.txt` | 文档要求安装匹配的 wheel，但没有交付 wheel 或完整构建入口。固定源码快照与版本要求已有说明，本轮不改第三方源码；补齐可复现获取步骤需要单独核对。 |
| P07 | `test/runtime_codex_acceptance.py`；`src/main.py::main` | 旧验收入口仍从 F 开始，缺少当前必需的工程输入清单；普通摘要测试未覆盖入口失效。应明确退出使用该入口，或按现行协议重建验收；不能放宽运行器准入。 |
| P08 | `test/acceptance_preparation.py`；`test/runtime_codex_acceptance.py` | 默认产物位置写死为特定盘符目录。应改为显式参数或用户可写的隔离目录，保留现有显式配置。 |
| P09 | `test/test_reasoning_ledger.py` | DB 集成测试默认连接本机固定 DSN，并对固定测试 schema 执行清理。迁移验收必须显式提供隔离测试数据库，不能使用业务库连接串。 |
| P10 | `test/test.py` | 早期 CLI 示例写死了个人会话 ID 和 prompt。保留示例用途，改为显式必填参数，无参数时不接触 Codex。 |
| P11 | `test/test_final_review_verdict.py`、`test/test_final_review_confirmation.py`、`test/test_mutation_accountability.py` | 单独执行依赖其他模块预先加入 `src` 路径；已补上基于本文件位置的路径初始化，保留原测试逻辑与断言。 |

历史交接文档中的证据路径与运行时硬编码分开处理：历史证据不伪造为已迁移，也不作为安装依赖。配置中的项目 ID、authority ID、Git 摘要和数据库 anchor 属于证据与授权绑定，不能为了迁移直接删除。

## 修复顺序

1. 配置与身份：新增 v4 见证配置，用 `ssh_identity.path_env` 引用部署环境的绝对路径；保留 v3 绝对路径配置。身份 SHA-256、仓库 URL 与受保护 ref 继续由受审批配置绑定。共享解析函数用于读取与锁定，缺失配置及摘要不符仍拒绝。运行时继续固定整个环境的值摘要。
2. 初始化安全：补重复初始化、参数冲突和迁移材料冲突的失败测试；最小修改避免覆盖已有项目。
3. 路径与测试入口：清理未说明的目录默认值，补入口契约检查；完整运行器的平台限制显式保留。
4. 交付说明与隔离验证：列出已支持环境、所需用户配置和未验证项；从新目录、无旧环境变量的进程执行测试。
5. 独立复核：真实独立 subagent 检查改动和负向测试。推理预算不超过 high，不跨模型。

上述任务的文件范围和验收条件见 [todo.md](todo.md)。P03–P05 中的平台移植工作排除；仅说明 Windows 的安装前提。P06 按用户要求保留已说明的外部依赖处理方式，不改造 TraceRelay 构建或源码。

## 验证标准

- 新增逻辑先有失败测试，再实施修复；使用本仓库 `unittest`，不引入测试框架。
- 换目录运行不访问原 checkout、个人私钥目录或固定测试产物目录。
- 错误身份摘要、篡改配置、缺失授权、未支持平台仍明确失败。
- 已有项目重复初始化保持文件字节、数据库 anchor 与项目身份不变；冲突参数在写入前拒绝。
- 已存在的用户工作区变更保留，不归入本轮验证结论。
- 同机换目录只证明已覆盖的路径行为独立；另一台 Windows 的完整运行仍需要真实环境证据。macOS、Linux 不在当前支持范围。

## 本轮已有验证

2026-10-16 在当前 Windows 环境执行：

```text
python -I -B -X utf8 -m unittest discover -s test -p test_main_runtime.py
python -I -B -X utf8 -m unittest discover -s test -p test_reviewer_contract.py
python -I -B -X utf8 -m unittest discover -s test -p test_reviewer_integration_contract.py
```

结果分别为 14、11、10 项通过。这些是入口与角色契约测试，不包含真实 Codex A–F 全流程、远端见证或跨平台验收。两名独立只读审查 agent 分别核对了运行时与安装/初始化链路。
