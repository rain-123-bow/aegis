# Windows 部署与迁移

当前完整运行器支持 Windows x64。本轮只处理 Windows 机器之间的迁移；macOS、Linux 适配不在支持范围，AegisSealCore 保持仓库中的配套版本。

源码可放在当前用户有权限访问的普通目录中。Python 环境、运行目录和凭据由当前部署提供。克隆仓库后仍须完成依赖安装、项目配置、授权与封印检查，不能直接继承开发者机器的运行资格。

## 环境前提

| 项目 | 要求 |
| --- | --- |
| Windows | 当前验证基线为 Windows 11 x64、PowerShell 7；保留正常的 `LOCALAPPDATA`、`SystemRoot` 环境；运行器使用 Windows Job Object、进程身份和文件共享锁 |
| Python | 当前验证基线为 CPython 3.13 x64；在仓库外新建虚拟环境，不复制其他机器的 venv；依赖版本见 [`requirements-runtime.txt`](../requirements-runtime.txt) |
| Git | Git for Windows，包含 `mingw64`、`usr/bin/ssh.exe` 等完整安装布局；执行文件与运行时摘要须符合本项目批准的配置 |
| Codex | 当前运行时识别 Windows npm 安装布局，启动器旁有 `node_modules/@openai/codex*`，并能找到 Node.js；单独下载的原生 exe 不满足现有完整运行时校验 |
| TraceRelay | 与 Aegis 使用同一个 Python，安装与[固定 SDK 快照](../third_party/TraceRelay/README.md)一致的已批准 wheel |
| 推理库数据库 | PostgreSQL 16 或以上、pgvector 0.8.0 或以上；连接信息由环境变量提供，数据库身份须与项目配置及 anchor 相符 |
| Agent skills | 按 [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) 的安装说明准备 Master 所需技能；本仓库内保留 Aegis 专用角色技能 |
| AegisSealCore | 使用仓库配套的 Windows x64 组件；本指南不修改、重编译或绕过该组件 |

版本约束和字节检查同时生效。升级工具、替换依赖或改动运行配置后，需重新审核受影响的固定输入。`LOCALAPPDATA` 在启动隔离阶段即被使用，显式设置 `--runtime-root` 也不能替代它。

## 准备 Python 环境

以下命令在仓库根目录执行，前提是已经安装上述 Python 和 Git。虚拟环境路径可换成当前用户有权限访问的仓库外目录；应选择尚未使用的目录。

```powershell
$aegisProject = (Get-Location).Path
$aegisVenv = Join-Path $env:LOCALAPPDATA 'Aegis\python'
if (Test-Path -LiteralPath $aegisVenv) { throw '请选择新的虚拟环境目录' }
py -3.13 -m venv $aegisVenv
if ($LASTEXITCODE -ne 0) { throw '创建虚拟环境失败' }
$aegisPython = Join-Path $aegisVenv 'Scripts\python.exe'
& $aegisPython -m pip install --no-compile -r (Join-Path $aegisProject 'requirements-runtime.txt')
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，停止部署' }
```

随后按照 [TraceRelay 集成说明](../third_party/TraceRelay/README.md)，将已批准 wheel 以 `--no-compile --no-deps` 安装到同一个 `$aegisPython`。本仓库的 TraceRelay 目录是校验用源码快照，不是可直接安装的构建目录；本仓库也未附带该 wheel。拿不到匹配 wheel 时，完整流程保持未就绪，不使用上游最新版本替代。

依赖准备完成后，可先检查命令入口：

```powershell
& $aegisPython -B src/main.py --help
& $aegisPython -B src/main.py ledger --help
```

帮助输出只证明命令入口可加载，不代表运行预检、数据库或远端见证已经通过。

## 配置当前机器的见证身份

`config/seal_witness.json` 的 v4 格式把私钥的文件位置改为环境变量引用：

```json
"ssh_identity": {
  "path_env": "AEGIS_WITNESS_IDENTITY_FILE",
  "sha256": "<已批准私钥文件的64位小写SHA-256>"
}
```

启动 Aegis 的同一个 PowerShell 进程中，设置当前机器的绝对路径：

```powershell
$env:AEGIS_WITNESS_IDENTITY_FILE = Read-Host '当前部署已批准 SSH 私钥的绝对路径'
```

变量值必须是非空绝对路径；运行器不会自动展开 `~` 或路径字符串中的环境变量。路径指向的文件仍须通过原有身份摘要、普通文件检查和 Windows 文件锁校验；只改变路径不会改变受信任身份。整个 Git 传输期间会锁住实际选用的身份文件。

v3 中显式 `path` 的配置仍可读取。新部署应使用 v4，避免把个人目录提交进仓库。仓库内的身份摘要、远端 URL 和受保护 ref 是已有项目的配置；接入自己的项目时，需要提供自己的凭据和远端，并审核、封印变更。不要复制他人的私钥或仅为通过校验而修改摘要。

`.env`、`*.local.json` 和常见私钥文件名已加入忽略规则。这些文件不会被运行器自动加载，也不能覆盖受封印配置或充当授权。确认 `git status` 中没有凭据后再提交；忽略规则不会移除已经进入历史的文件或文本。

## 推理库与运行状态

迁移已有项目时，保留 `code/`、`.aegis/reasoning_ledger/`、`config/reasoning_ledger.json` 和对应数据库，按项目的备份恢复流程处理。配置中的项目 ID、schema、anchor 和迁移 SQL 必须保持一致。数据库连接串放入配置所指定的 `dsn_env` 环境变量，不提交到仓库，不使用命令行参数传递秘密。

在数据库连接配置完成后，可以运行只读可用性检查：

```powershell
& $aegisPython -B src/main.py ledger probe --project-root $aegisProject
```

`ledger bootstrap` 用于经授权的项目文件初始化；重复执行相同参数会保留已有配置字节、anchor 与自定义 README，参数或已有 SQL 冲突会在写入前拒绝。它不会迁移数据库，也不能作为重置项目身份的手段。`ledger migrate` 会修改数据库，应在备份、授权和目标核对之后执行。

默认运行目录为 `%LOCALAPPDATA%/Aegis/runtime/<project-id>/`，也可显式指定项目外的运行目录。旧运行中的路径、进程身份、依赖摘要和授权记录绑定原环境；直接复制检查点到新机器不构成恢复授权。保留旧证据，在新部署上按[运行范围与迁移门槛](AEGIS_RUNTIME_SCOPE_PROPOSAL.md#migration-gate)核对配置、封印、运行授权与受保护远端见证，再启动新运行。该文档中的历史测量和审批状态不替代当前部署的确认。

## 验证入口

### 不调用真实 agent 的回归

在当前 PowerShell 会话中取消外部验收开关，再运行单元与契约测试：

```powershell
Remove-Item Env:RUN_TRACERELAY_REAL_ACCEPTANCE -ErrorAction SilentlyContinue
Remove-Item Env:AEGIS_TEST_LEDGER_DSN -ErrorAction SilentlyContinue
& $aegisPython -I -B -X utf8 -m unittest discover -s test -p 'test_*.py'
```

这些测试会在临时目录创建夹具、运行本地子进程并验证 Windows 锁与进程管理。不调用真实 Codex agent；数据库集成和真实 TraceRelay/App Server 用例会跳过。跳过项不计为已验证。

数据库集成测试只读取 `AEGIS_TEST_LEDGER_DSN`，不会自动使用业务库的 `AEGIS_LEDGER_DSN`。仅在专用、可丢弃的测试数据库上启用；测试会创建随机 schema 并清理测试数据。显式配置但连接失败或版本不符合要求时，测试报告失败。

### 真实集成验收

当前入口为 [`test/test_traced_app_server_real_integration.py`](../test/test_traced_app_server_real_integration.py)；真实 TraceRelay SDK 测试为 [`test/test_tracerelay_real_integration.py`](../test/test_tracerelay_real_integration.py)。它们由 `RUN_TRACERELAY_REAL_ACCEPTANCE=1` 显式启用，会启动受管进程；App Server 测试会调用真实 Codex agent，需具备账号、网络和任务授权。

运行前按测试前置条件准备环境，核对当前实际的本机代理端口并显式设置 `TRACERELAY_UPSTREAM_PORT`。不要把测试中的默认端口当作其他机器的网络配置。

未准备固定材料的验收默认在当前用户临时目录的 `aegis-acceptance/` 下创建隔离夹具。使用准备清单时，必须同时显式设置 `AEGIS_APP_SERVER_ACCEPTANCE_ROOT`、`AEGIS_APP_SERVER_PREPARED_MANIFEST` 和 `AEGIS_APP_SERVER_PREPARED_SHA256`，根目录和清单摘要必须匹配；不从旧机器路径猜测目标。

`test/runtime_codex_acceptance.py` 的旧 F-start 执行入口已经停用，调用会直接报错；历史报告处理代码保留。`test/test.py` 仅为早期 CLI 转发示例，必须显式提供两个已有会话 ID 和 prompt，不作为 Aegis 验收入口。

## 迁移结果如何认定

同一机器换目录测试只能证明已覆盖的路径与文件行为不依赖原 checkout。另一台 Windows 机器仍需分别验证依赖安装、数据库、凭据、授权、远端见证及真实 agent 全流程；源码可加载、单测通过或旧项目曾通过受控验收，都不能替代这一步。

历史文档中的个人路径只用于解释原验证记录，不参与运行时路径发现。本轮修改当前版本，不重写已有 Git 历史。
