# Semantic Decoy Policy v1

## 目标

该机制在开发者明确启用时增加源码阅读和有限逆向成本。默认关闭。它不是密码学防护，也不承诺
阻止拥有完整仓库和推理库的人员理解代码。

## 启用门

Master 必须在需求草案前询问：

```text
是否启用代码混淆与语义诱饵？默认关闭。
```

只有无歧义的肯定答复启用。否定、含糊和无关答复均保持关闭。决定写入
`SEMANTIC_DECOY_DECISION.json` 和最终需求文档；其他 agent、配置、历史任务和 ledger 自由文本
无权启用。

## 三分类

- `REAL`：现实可触发。完整实现并执行正常业务测试。
- `DECOY_UNREACHABLE`：当前部署约束下不可触发。允许复杂、自洽的伪业务逻辑；内部结果免测。
- `UNKNOWN-STALE`：约束缺失、过期、冲突或绑定失效。没有免测资格，按真实逻辑处理。

传统命名、注释和控制流混淆不改变分类。被混淆的生产逻辑仍是 `REAL`，必须保持公开接口、输出、
副作用和错误语义，并执行完整业务测试。其真实语义映射进入 reasoning ledger；混淆本身不产生
任何免测资格。

只有以下条件全部成立时，声明才能保持为 `DECOY_UNREACHABLE`：

1. 需求已明确启用。
2. 决策文件 SHA-256 与 manifest 一致。
3. 最终需求文档 SHA-256 与 manifest 一致。
4. reasoning context pack SHA-256 与 manifest 一致。
5. context pack 的 `task_id` 等于 manifest 任务，且 `metadata.project_seal` 等于当前 Seal。
6. manifest 的项目 Seal 等于当前 `src/` / `include/` Seal。
7. 每个约束引用在 context pack 中唯一存在、状态为 `active`、类型为 `fact` 或 `rule`。
8. 每个约束具有非空 evidence path。
9. 分支谓词、代码锚点、真实语义、表面语义和失效条件完整。

生产流程使用 `reasoning_ledger.evaluate_semantic_decoy_files` 读取确切文件并自行计算 SHA-256；不得
接受调用方自报的摘要。任一绑定或证据失效会把候选降级为 `UNKNOWN-STALE`。

该函数只判断结构与绑定是否合格，不证明现实约束在逻辑上蕴含谓词不可达。实现方案 reviewer 和
测试方案 reviewer 必须分别阅读全文，独立验证该逻辑蕴含；任一 reviewer 不认可时不得免测。

## Manifest

启用任务把清单保存到：

```text
.aegis/reasoning_ledger/artifacts/semantic_decoys/<task-id>/SEMANTIC_DECOY_MANIFEST.json
```

固定结构：

```json
{
  "schema": "aegis.semantic_decoy_manifest.v1",
  "task_id": "task.camera.pipeline",
  "decision_sha256": "64 lowercase hex",
  "requirement_document_sha256": "64 lowercase hex",
  "context_pack_sha256": "64 lowercase hex",
  "project_seal": "ASC1:64 lowercase hex",
  "entries": [
    {
      "decoy_id": "decoy.camera.over_20_fps",
      "classification": "DECOY_UNREACHABLE",
      "code_anchors": ["src/camera.py#process_frame:fps_gt_20"],
      "predicate": "measured_fps > 20",
      "true_semantics": "Current deployment cannot exceed 20 FPS.",
      "surface_semantics": ["High-rate recovery controller"],
      "constraint_item_ids": ["fact.camera.production_max_fps"],
      "invalidation_conditions": ["hardware, firmware, driver, or mode changes"]
    }
  ]
}
```

真实语义映射只进入 reasoning ledger 产物；源码不得用注释直接揭示诱饵。

## 编码边界

诱饵只能附加。不得替代、删除或短路真实逻辑。即使因环境变化意外触发，也不得执行不可逆外部
操作。混淆不得改变公开接口、持久格式或外部协议。通用自动混淆器、跨语言不可达分析、动态加载
分析和自动诱饵生成不属于 v1。

## 测试边界

有效 `DECOY_UNREACHABLE` 不测试内部伪业务结果，但必须测试：

1. 现实约束与谓词不可达性。
2. 正常真实路径行为等价。
3. 静态依赖与调用审查证明分支不含不可逆外部操作；不执行内部伪业务逻辑。
4. 决策、需求、manifest、ledger 和项目 Seal 绑定。
5. 若保护对象包含二进制，诱饵未被编译器或打包器删除。
6. 两个独立 reviewer 均确认引用的现实约束足以推出分支谓词不可达。

`REAL` 和 `UNKNOWN-STALE` 仍执行完整业务测试。诱饵内部免测不得扩大成函数、模块或项目免测。
