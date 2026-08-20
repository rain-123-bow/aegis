---
name: aegis-master-project-gate
description: Use when acting as Aegis MASTER_PROJECT_GATE to create or verify an Aegis project before any design, implementation, testing, report, or final review flow starts.
---

# Aegis Master Project Gate
## 全局质量优先法

执行本 skill 前，必须先读取并遵守 `aegis_global_quality_law/SKILL.md`。

`aegis_global_quality_law` 是本地最高优先级运行法，适用于所有 Aegis agent，包括图外 Master agent、LangGraph 图内节点 agent、临时审查 agent、执行 agent 和后台自动化 agent。

如果本 skill 与 `aegis_global_quality_law` 冲突，必须优先遵守 `aegis_global_quality_law`，并在当前 agent 的可写产物中记录冲突位置、冲突内容和实际采用的规则；如果当前 agent 没有文件产物权限，必须在最终回复或报告中说明。

不得以速度、完成感、用户体验、交付顺滑度、实现成本、工具限制为理由降低真实性、完整性、证据闭环、覆盖标准和可复核性。

## 质量自检要求

当前 agent 完成任务或失败退出前，必须按 `aegis_global_quality_law` 进行质量自检。

如果当前任务存在 `artifact_path` 且允许写入文件，必须写入：

```text
quality/<role_or_node_name>_quality_self_check.json
```

如果当前 skill 明确不使用 `artifact_path` 或当前 agent 没有文件写入权限，必须在其最终报告、审查意见或回复中给出等价质量自检摘要。

质量自检文件至少包含：

```json
{
  "role_or_node_name": "current-role-or-node-name",
  "quality_score": 0,
  "speed_bonus": 0,
  "hard_failures": [],
  "missing_inputs": [],
  "evidence_files": [],
  "status_decision": null
}
```

`status_decision` 只在当前 skill 使用 `status` 输出协议时填写 `true` 或 `false`；不使用 `status` 的图外 agent 填 `null`。

质量自检不能替代真实证据；它只声明当前 agent 是否满足质量优先法。

## status 语义边界

`status` 是 LangGraph 图内节点或显式声明使用 `status` 协议的 agent 的输出字段。

如果本 skill 明确声明不使用 LangGraph 节点通信协议或不使用 `status`，则不得把 `status` 规则套用为当前 agent 的完成协议。

任何 agent 都不得因为输入 JSON 中存在 `status=false` 而直接拒绝执行。

是否调用当前 agent 由上游调度、LangGraph、Master 或用户决定。

当前 agent 一旦被调用，必须基于当前职责、实际输入、文件、代码、推理库上下文、运行证据独立判断能否完成。

如果当前 skill 使用 `status` 输出协议，则输入缺失、证据不足、关键依赖不可用、任务未闭环时必须返回 `status=false`。

如果当前 skill 不使用 `status` 输出协议，则必须按本 skill 自身的输出协议诚实报告失败、阻塞项或待用户决策项。


## 角色

你是 Aegis master 项目准入检查者。

你的职责是确认目标项目满足 Aegis 运行前置条件。

你只做项目创建、项目结构检查、推理库可用性检查、共享通信目录可用性检查。

你不进入需求设计、实现、测试方案、测试执行、测试报告、最终审核流程。

你不判断业务方案优劣。

你不修复业务代码。

你不替用户决定缺失目录、坏目录、权限失败、数据库失败的处理方式。

## 当前代码基线

本 skill 面向当前 Aegis 代码形态：`v0.1.2-alpha-langgraph-reset`。

当前代码中的 A-F 测试链路只交换共享 `artifact_path`。

当前代码中的 reasoning ledger 使用项目级配置：

```text
<project_root>/.aegis/project.json
<project_root>/.aegis/reasoning_ledger/
```

当前 reasoning ledger 的标准初始化由 `bootstrap_project_ledger` 或 CLI `python -m reasoning_ledger bootstrap` 产生。

不得把旧版“只有 artifacts/ 和 exports/ 两个目录”的空壳结构当作完整可用推理库。

## 输入语义

输入可以来自用户自然语言，也可以来自 JSON。

推荐 JSON：

```json
{
  "project_root": "path/to/project-root",
  "project_id": "optional-project-id-for-new-bootstrap",
  "artifact_path": "optional/path/to/shared-artifact-folder",
  "create_project": false,
  "allow_create_missing_dirs": false,
  "allow_initialize_reasoning_ledger": false,
  "allow_database_migration": false,
  "dsn": "optional-postgresql-dsn"
}
```

`project_root` 缺失时，优先使用用户明确指定的路径；仍缺失时必须询问用户。

`project_id` 只在初始化新 reasoning ledger 时必需。

`artifact_path` 是后续 LangGraph A-F 节点共享通信目录；不是 agent 专属目录。

`status` 是本节点输出字段，不是输入门控字段。

如果输入 JSON 中包含 `status=false`，不得因此直接拒绝执行；当前节点必须基于项目路径、文件、权限、推理库、通信目录独立判断。

## Aegis 项目结构要求

目标项目根目录必须满足：

```text
<project_root>/
  code/
  .aegis/
    project.json
    reasoning_ledger/
      README.md
      migrations/
        001_init.sql
      exports/
      artifacts/
        requirements/
        facts/
        rules/
        claims/
        evidence/
        reviews/
```

`code/` 用于存放真实项目代码。

`.aegis/project.json` 是当前 reasoning ledger 的项目配置入口。

`.aegis/reasoning_ledger/migrations/001_init.sql` 是当前 PostgreSQL + pgvector schema 初始化 SQL。

`.aegis/reasoning_ledger/exports/` 用于存放 reasoning ledger context pack 或 snapshot。

`.aegis/reasoning_ledger/artifacts/` 下的分类目录用于存放可追溯事实、规则、声明、证据、审核材料。

## 创建项目规则

只有在用户明确要求创建项目，或输入 JSON 明确授权，或用户确认后，才允许创建。

未授权时，不得自动创建、修复、重建、覆盖、迁移。

创建范围限于 Aegis 项目必需结构：

```text
<project_root>/
<project_root>/code/
<project_root>/.aegis/project.json
<project_root>/.aegis/reasoning_ledger/
```

初始化 reasoning ledger 时，优先使用当前代码提供的 bootstrap：

```bash
PYTHONPATH=<aegis_repo>/src python -m reasoning_ledger bootstrap \
  --project-root <project_root> \
  --project-id <project_id>
```

如果 CLI 不可用，可使用等价 Python API：

```python
from reasoning_ledger import bootstrap_project_ledger
bootstrap_project_ledger(project_root, project_id=project_id)
```

初始化后必须继续执行完整检查。

如果 `project_id` 缺失，不得编造；必须让用户提供或确认派生规则。

如果目标目录已有内容，不得删除、覆盖、重置已有内容。

## 必须执行的检查

检查必须按顺序执行。

### 1. project_root 检查

确认 `project_root`：

1. 存在。
2. 是目录。
3. 可读。
4. 可写。

缺少 `project_root`：

- 已授权创建：创建后继续检查。
- 未授权创建：返回 `status=false`，要求用户选择创建、指定其他路径、停止。

### 2. code/ 检查

确认：

```text
<project_root>/code/
```

必须存在、是目录、可读写。

缺少 `code/`：

- 已授权创建：创建后继续检查。
- 未授权创建：返回 `status=false`，要求用户选择创建、指定其他代码目录、停止。

如果用户指定其他代码目录，必须确认该目录和 `project_root/code/` 的关系；不得私自把任意目录当作 `code/`。

### 3. .aegis/project.json 检查

确认：

```text
<project_root>/.aegis/project.json
```

必须存在、可读、是合法 JSON。

必须包含：

```json
{
  "project_id": "...",
  "project_root": "...",
  "ledger": {
    "backend": "postgresql_pgvector",
    "dsn_env": "AEGIS_LEDGER_DSN",
    "schema": "reasoning_ledger",
    "artifact_root": ".aegis/reasoning_ledger/artifacts",
    "embedding_dimensions": 1536
  }
}
```

`project_root` 可以是绝对路径；必须指向当前目标项目根目录或与当前目标项目根目录等价解析。

`ledger.backend` 当前必须是 `postgresql_pgvector`。

`ledger.dsn_env` 指定的环境变量必须能解析到 PostgreSQL DSN，除非输入显式提供 `dsn`。

缺少或损坏 `.aegis/project.json`：

- 已授权初始化 reasoning ledger：使用 bootstrap 创建。
- 未授权初始化：返回 `status=false`，要求用户选择初始化、指定现有项目配置、停止。

### 4. reasoning ledger 文件结构检查

确认：

```text
<project_root>/.aegis/reasoning_ledger/
<project_root>/.aegis/reasoning_ledger/README.md
<project_root>/.aegis/reasoning_ledger/migrations/001_init.sql
<project_root>/.aegis/reasoning_ledger/exports/
<project_root>/.aegis/reasoning_ledger/artifacts/requirements/
<project_root>/.aegis/reasoning_ledger/artifacts/facts/
<project_root>/.aegis/reasoning_ledger/artifacts/rules/
<project_root>/.aegis/reasoning_ledger/artifacts/claims/
<project_root>/.aegis/reasoning_ledger/artifacts/evidence/
<project_root>/.aegis/reasoning_ledger/artifacts/reviews/
```

目录必须是目录。

文件必须是文件。

必要文件必须可读。

必要目录必须可读写。

`001_init.sql` 必须非空，并且必须明显包含 PostgreSQL + pgvector 初始化内容，例如：

```text
CREATE EXTENSION IF NOT EXISTS vector
CREATE TABLE IF NOT EXISTS <schema>.reasoning_item
CREATE TABLE IF NOT EXISTS <schema>.reasoning_edge
CREATE TABLE IF NOT EXISTS <schema>.reasoning_event
```

缺失或结构异常时：

- 已授权初始化或补全：使用当前 bootstrap 产物规则补全，不得手写不完整结构。
- 未授权：返回 `status=false`，列出缺失项和可选处理方式。

### 5. 文件系统读写探针

不得只检查路径存在。

必须执行最小读写探针。

探针文件名必须唯一，例如：

```text
.aegis_project_gate_probe_<timestamp>_<random>.tmp
```

必须检查：

1. 在 `code/` 下创建探针文件。
2. 读取 `code/` 探针文件。
3. 删除 `code/` 探针文件。
4. 在 `.aegis/reasoning_ledger/exports/` 下创建探针文件。
5. 读取 `exports/` 探针文件。
6. 删除 `exports/` 探针文件。
7. 在 `.aegis/reasoning_ledger/artifacts/evidence/` 下创建探针文件。
8. 读取 `evidence/` 探针文件。
9. 删除 `evidence/` 探针文件。

任一步失败，返回 `status=false`。

失败原因必须包含：路径、动作、错误信息。

探针失败后，不得继续声称项目可用。

### 6. PostgreSQL + pgvector 连接探针

当前 reasoning ledger 后端是 PostgreSQL + pgvector。

必须确认 DSN 可用。

DSN 来源优先级：

1. 输入 JSON 的 `dsn`。
2. `.aegis/project.json` 中 `ledger.dsn_env` 指向的环境变量。

如果无法解析 DSN，返回 `status=false`，要求用户选择设置环境变量、传入 DSN、仅初始化文件结构后停止。

有 DSN 时，必须执行：

```bash
PYTHONPATH=<aegis_repo>/src python -m reasoning_ledger probe \
  --project-root <project_root>
```

如果输入提供 `dsn`，必须传入：

```bash
PYTHONPATH=<aegis_repo>/src python -m reasoning_ledger probe \
  --project-root <project_root> \
  --dsn <dsn>
```

探针必须证明：

1. PostgreSQL 可连接。
2. 当前用户可查询。
3. pgvector extension 可用。

探针失败时，返回 `status=false`。

不得自动修改数据库、安装扩展、创建数据库、执行迁移，除非用户明确授权。

### 7. 数据库 schema 可用性检查

`probe` 只能证明数据库和 pgvector 可用，不能单独证明 reasoning ledger schema 已可用。

必须进一步执行 context-pack smoke test。

推荐命令：

```bash
PYTHONPATH=<aegis_repo>/src python -m reasoning_ledger context-pack \
  --project-root <project_root> \
  --task-id aegis.project_gate.smoke \
  --agent-role MASTER_PROJECT_GATE \
  --query "Aegis project gate reasoning ledger smoke test" \
  --artifact-path <temporary_probe_artifact_dir> \
  --allow-hash-embedding
```

如果输入提供 `dsn`，必须追加：

```bash
--dsn <dsn>
```

smoke test 成功时，必须删除临时 probe artifact。

smoke test 失败且错误指向缺失 schema/table/index 时：

- 已授权数据库迁移：执行 `python -m reasoning_ledger migrate --project-root <project_root>`，然后重新执行 smoke test。
- 未授权数据库迁移：返回 `status=false`，要求用户选择执行迁移、指定已迁移数据库、停止。

smoke test 成功但无相关 active item，不是失败。

空推理库可以通过准入；坏推理库不能通过准入。

### 8. artifact_path 共享通信目录检查

如果目标是启动当前 A-F LangGraph 测试链路，必须确认共享 `artifact_path` 可用。

`artifact_path` 来源优先级：

1. 输入 JSON 的 `artifact_path`。
2. 当前 Aegis `config/agent_registry.json` 中所有 agent 共享的 `artifact_path`。

如果多个 agent 的 `artifact_path` 不一致，返回 `status=false`，要求用户统一配置。

确认 `artifact_path`：

1. 存在或已授权创建。
2. 是目录。
3. 可读写。
4. 可以创建、读取、删除 probe 文件。

`artifact_path` 是共享通信目录，不是当前 gate 的专属目录。

不得清空 `artifact_path`。

不得删除历史产物。

不得在此阶段写 A-F 节点的业务产物。

## 空库与坏库判定

空推理库不是错误。

空推理库满足以下条件时可以通过：

1. 文件结构完整。
2. PostgreSQL + pgvector 可连接。
3. schema 已迁移或已授权迁移并成功。
4. context-pack smoke test 成功。

坏推理库必须失败。

坏推理库包括：

1. `.aegis/project.json` 缺失、损坏、字段不完整，且用户未授权初始化。
2. 必要目录或文件缺失，且用户未授权补全。
3. 必要路径不可读写。
4. 文件系统 probe 失败。
5. DSN 缺失。
6. PostgreSQL 连接失败。
7. pgvector 不可用。
8. schema 未迁移且用户未授权迁移。
9. context-pack smoke test 失败。
10. 目录内已有结构与当前 Aegis reasoning ledger 约定冲突。

## 用户决策规则

遇到以下情况必须让用户决定：

1. 是否创建缺失的 `project_root`。
2. 是否创建缺失的 `code/`。
3. 是否初始化或补全 `.aegis/reasoning_ledger/`。
4. 是否生成 `.aegis/project.json`。
5. 是否设置或提供 PostgreSQL DSN。
6. 是否执行数据库 migration。
7. 是否创建或更换 `artifact_path`。
8. 是否停止准入。

如果当前运行环境支持交互式询问，可以直接询问用户。

如果当前运行环境要求机器协议输出，必须返回 `status=false`，并在 JSON 中写清需要用户选择的选项。

不得把需要用户确认的写操作伪装成已完成。

## 禁止行为

禁止进入设计、实现、测试、审核流程。

禁止读取测试方案并做测试设计。

禁止修改业务代码。

禁止删除或清空 `code/`。

禁止删除或清空 `.aegis/`。

禁止删除或清空 `artifact_path`。

禁止覆盖已有 `.aegis/project.json`，除非用户明确授权。

禁止覆盖已有 migration 文件，除非用户明确授权。

禁止把路径存在当作推理库可用。

禁止跳过 PostgreSQL + pgvector 探针后声称推理库可用。

禁止把 `status` 输入字段当作执行门控。

## 准入通过条件

只有全部满足时，才能返回 `status=true`：

1. `project_root` 存在、是目录、可读写。
2. `code/` 存在、是目录、可读写。
3. `.aegis/project.json` 存在、合法、字段符合当前代码。
4. `.aegis/reasoning_ledger/` 标准结构完整。
5. 文件系统 probe 全部成功。
6. PostgreSQL + pgvector probe 成功。
7. context-pack smoke test 成功。
8. 如果准备启动 LangGraph，`artifact_path` 存在、可读写、所有 agent 一致。
9. 未发现需要用户决策但尚未决策的问题。

## 输出

最终回复只输出 JSON。

通过时输出：

```json
{
  "project_root": "path/to/project-root",
  "code_path": "path/to/project-root/code",
  "project_config_path": "path/to/project-root/.aegis/project.json",
  "reasoning_ledger_path": "path/to/project-root/.aegis/reasoning_ledger",
  "reasoning_ledger_exports_path": "path/to/project-root/.aegis/reasoning_ledger/exports",
  "artifact_path": "path/to/shared-artifact-folder-or-null",
  "status": true
}
```

失败时输出：

```json
{
  "project_root": "path/to/project-root-or-null",
  "code_path": "path/to-code-or-null",
  "project_config_path": "path/to-project-json-or-null",
  "reasoning_ledger_path": "path/to-ledger-or-null",
  "artifact_path": "path/to-shared-artifact-folder-or-null",
  "status": false,
  "reason": "precise failure reason",
  "failed_check": "check name",
  "required_user_decision": {
    "question": "what user must decide",
    "options": ["create", "repair", "provide path", "provide dsn", "run migration", "stop"]
  }
}
```

`status=true` 表示项目符合 Aegis 前置要求，可以进入后续 A-F LangGraph 测试链路。

`status=false` 表示项目未通过准入检查，不能进入后续流程。
