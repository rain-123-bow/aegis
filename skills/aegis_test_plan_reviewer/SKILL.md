---
name: aegis-test-plan-reviewer
version: 6
description: Review a frozen test plan against frozen requirements, implementation design, reasoning facts, and project evidence.
---

# 测试方案审核

## 唯一职责

审核测试方案是否完整、严谨、可执行、可复现，并能产生足以判断需求成立性的证据。

被审核材料通过或拒绝不影响审核工作的质量要求。审核必须覆盖全部必要输入，并把每个结论绑定到证据。

## 输入

从控制输入读取：

1. 冻结测试方案路径和 SHA-256。
2. 冻结需求文档描述符。
3. 冻结实现方案描述符。
4. 冻结推理上下文路径和 SHA-256。
5. 审核报告唯一写入路径。
6. 历史未关闭语义问题及其证据。

不得根据文件名猜测多个候选输入。必要输入无法唯一定位时，结论为 `UNDETERMINED`，问题类别为 `REQUIRED_INPUT_MISSING`。

## 只读边界

只能写入控制输入指定的审核报告路径。

禁止修改、删除、重命名、移动或覆盖测试方案、需求文档、实现方案、推理上下文、历史审核报告和共享入口文件。

禁止创建批准版测试方案。批准版和交接索引不属于本任务产物。

## 审核内容

逐项检查：

1. 每项需求是否有测试和唯一需求标识。
2. 每项实现机制、失败路径、边界条件和降级行为是否被覆盖。
3. 测试前置条件、命令、工作目录、环境、输入、超时和通过条件是否确定。
4. 测试能否区分真实实现、伪实现、空实现、硬编码和遗漏路径。
5. 描述性矩阵与机器执行策略是否逐项一致。
6. 测试是否绑定可执行文件、入口文件、输入文件和有效环境。
7. 原始输出、退出码、时间、运行身份和数据文件能否形成完整证据。
8. 推理上下文中的冲突、失效项、假设和警告是否被处理。
9. 历史问题是否被真实修复，或仍是同一个未关闭逻辑单元。

## 事实类别

- `REQUIREMENT_DEFECT`：需求自身矛盾、缺失或不可判定。
- `IMPLEMENTATION_PLAN_DEFECT`：实现方案自身矛盾、缺失机制或无法支撑测试设计。
- `TEST_PLAN_DEFECT`：测试覆盖、执行定义或证据要求存在缺陷。
- `EVIDENCE_MISSING`：测试方案的关键判断缺少现有依据。
- `LOGIC_GAP`：前提不能推出结论。
- `REQUIRED_INPUT_MISSING`：必要冻结输入不存在或不可验证。

不得输出接收者、流程方向、继续、回退、终止或任何处理对象。

## 结论

`PASS`：分数至少 95、阻断错误为 0、没有阻断问题。

`FAIL`：至少一个有证据索引的问题。测试方案缺陷必须包含 `TEST_PLAN_DEFECT`。

`UNDETERMINED`：现有冻结输入无法支持确定判断，必须列出缺失项和已检查范围。

## 审核报告

审核报告必须包含：输入描述符、检查矩阵、结论、问题、推理链、替代解释、关闭条件、证据索引、历史问题处置和未确定边界。

写完后按 UTF-8 原始字节计算大小和小写 SHA-256。

## 机器输出

返回字段：

```text
artifact_path
reasoning_ledger_context_pack
review_conclusion
findings
review_output_artifacts
reviewed_plan_sha256
score
error_count
warning_count
semantic_issues
prior_issue_assessments
```

协调器从 `findings[*].category` 确定性派生 `finding_categories`；机器输出不得返回该冗余字段。

`review_output_artifacts` 必须且只能描述控制输入指定的审核报告，标识为 `test-plan-review`。

`semantic_issues` 只记录阻断问题。每项必须包含唯一标识、前提、推理、结论、缺失证据、替代解释、关闭条件和历史问题标识。

`prior_issue_assessments` 必须覆盖全部历史问题。只有新增证据、收窄结论、修正推理或排除替代解释才构成修复。
