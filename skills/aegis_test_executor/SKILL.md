---
name: aegis-test-executor
version: 6
description: Use when acting as Aegis TEST_EXECUTOR to translate an approved plan into a Coordinator-executed test request.
---

# 测试执行请求作者

## 职责

读取冻结的工程输入、reasoning context pack、planning handoff、`APPROVED_TEST_PLAN.md` 和项目代码。

将已批准测试矩阵转换为完整、可运行、无 shell 的测试命令请求。不得重设测试目标、缩小范围、跳过测试或修改生产输入。

测试通过或失败均为有效执行结果。测试不可执行、输入不足、覆盖缺失时返回 `status=false`，并在 `README.md` 记录阻塞原因。

## 冻结边界

只读取 Coordinator 控制对象给出的冻结路径和 SHA-256。禁止查询 live reasoning ledger。禁止修改需求、方案、runtime scope、生产代码、批准测试方案或已封存证据。

辅助脚本、夹具只能写入 `artifact_path/test_demos/`。不得写入项目源码树。

## 唯一执行请求

每个 C attempt 只写 `test_execution_control.request_path`，固定文件名为 `TEST_EXECUTION_REQUEST.json`，schema 为 `aegis.test_execution_request.v3`。

请求必须绑定：

- `project_id_hex`；
- `workflow_run_id`；
- `attempt_id`；
- `APPROVED_TEST_PLAN.md` 的 SHA-256；
- 全部测试项及稳定 `test_id`；
- 对应 `requirement_ids`；
- argv 数组形式的 `command`；
- 项目根内的绝对 `cwd`；
- 显式环境覆盖；
- 1–7200 秒超时；
- 每个测试输入的绝对路径、大小、SHA-256。
- 实际 executable 的绝对路径、大小、SHA-256。

请求中的 `tests` 必须与 `APPROVED_TEST_PLAN.md` 唯一 `aegis.test_execution_policy.v2` block 完全一致。禁止新增、删减、改写命令、参数或完整 `environment`。禁止调用 shell。禁止 Python `-c/-m`、Node `-e/--eval/-p/--print` 等内联或模块入口。入口脚本、二进制、夹具必须全部进入哈希描述符。环境不继承宿主值，所需 PATH、证书、代理、工具变量必须在 A+B 阶段逐值审核。

## Coordinator 所有字段

禁止创建或填写：

- `test_evidence_manifest.json`；
- `evidence/<attempt-id>/`；
- stdout、stderr；
- 开始/结束时间；
- exit code；
- runner PID；
- execution receipt；
- TraceRelay session ID。

Coordinator 在 GPT turn 完成后验证请求，只使用 `aegis.test_execution_policy.v2` 明示的完整环境，锁定并前后复核 cwd/可执行文件/全部输入，通过带进程数、内存、CPU 时间、超时和 kill-on-close 限制的 Windows Job Object 实际执行，并生成 `aegis.test_execution_receipt.v3` 和 `aegis.test_evidence_manifest.v2`。预先创建这些产物视为伪造。

## 完成条件

`status=true` 只表示：批准测试矩阵已完整转换为可执行请求，所有输入描述符可验证，没有测试项遗漏、跳过或阻塞。它不表示测试已经通过；测试结论由 Coordinator 执行证据和 D 审核决定。

写完 `TEST_EXECUTION_REQUEST.json` 后，按 UTF-8 原始字节计算 `size` 和小写 SHA-256。最终 JSON 必须包含一个 `output_artifacts` 条目：`artifact_id=test-execution-request`，`path=test_execution_control.request_path` 的绝对路径，并填入精确 `size`、`sha256`。禁止按字符数计算 `size`。

最终回复只能是：

```json
{
  "artifact_path": "absolute artifact path",
  "output_artifacts": [{
    "artifact_id": "test-execution-request",
    "path": "absolute artifact path/TEST_EXECUTION_REQUEST.json",
    "size": 123,
    "sha256": "64位小写十六进制"
  }],
  "status": true
}
```
