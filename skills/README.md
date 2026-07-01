# Aegis Test Skills

本包包含 6 个 LangGraph 测试链路 skill。

全部 skill 已统一为共享 `artifact_path` 语义：`artifact_path` 是整个 LangGraph 当前任务共享产物目录，不是 agent 专属目录。

每个节点写入 `README.md` 前必须清空旧内容，但不得删除其他历史产物文件。

链路：

1. `aegis_test_plan_author`
2. `aegis_test_plan_reviewer`
3. `aegis_test_executor`
4. `aegis_test_result_reviewer`
5. `aegis_test_report_writer`
6. `aegis_final_reviewer`
