from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SemanticDecoyWorkflowContractTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

    def test_master_asks_before_writing_a_requirement_draft(self) -> None:
        skill = self.read("skills/aegis_master_requirement_designer/SKILL.md")

        gate = skill.index("## 代码混淆与语义诱饵预草案门")
        draft = skill.index("### REQUIREMENT_DESIGN_DRAFT.md")
        self.assertLess(gate, draft)
        self.assertIn("是否启用代码混淆与语义诱饵？默认关闭。", skill)
        self.assertIn("未收到用户对此问题的答复前，不得写入需求草案", skill)
        self.assertIn("只有无歧义的明确肯定答复才能设置为 `true`", skill)
        self.assertIn("SEMANTIC_DECOY_DECISION.json", skill)
        self.assertIn("## 17. Code Obfuscation and Semantic Decoy Decision", skill)
        self.assertIn("semantic-decoy-decision-binding", skill)
        self.assertIn("aegis.semantic_decoy_requirement_binding.v1", skill)

    def test_downstream_skills_enforce_the_same_three_class_policy(self) -> None:
        paths = (
            "skills/aegis_master_implementation_plan_designer/SKILL.md",
            "skills/aegis_master_implementation_code_writer/SKILL.md",
            "skills/aegis_test_plan_author/SKILL.md",
            "skills/aegis_test_plan_reviewer/SKILL.md",
            "skills/aegis_final_reviewer/SKILL.md",
        )
        for path in paths:
            with self.subTest(path=path):
                text = self.read(path)
                self.assertIn("DECOY_UNREACHABLE", text)
                self.assertIn("UNKNOWN-STALE", text)
                self.assertIn("默认关闭", text)

        code_writer = self.read(
            "skills/aegis_master_implementation_code_writer/SKILL.md"
        )
        self.assertIn("evaluate_semantic_decoy_files", code_writer)
        self.assertIn("禁止接受调用方自报的摘要", code_writer)
        self.assertIn("内部结构检查只证明结构与绑定合格", code_writer)
        self.assertIn("SEMANTIC_DECOY_IMPLEMENTATION_REVIEW.json", code_writer)
        self.assertIn("SEMANTIC_DECOY_TEST_REVIEW.json", code_writer)

        test_reviewer = self.read("skills/aegis_test_plan_reviewer/SKILL.md")
        self.assertIn("结构校验通过不等于逻辑不可达", test_reviewer)
        self.assertIn("aegis.semantic_decoy_review_receipt.v1", test_reviewer)

    def test_master_flow_places_the_opt_in_gate_before_requirement_drafting(self) -> None:
        zh = self.read("docs/module_designs/master/zh/MASTER_MODULE_DESIGN.md")
        en = self.read("docs/module_designs/master/en/MASTER_MODULE_DESIGN.md")
        graph = self.read("docs/flat_node_graph.md")

        self.assertLess(zh.index("semantic_decoy_opt_in"), zh.index("requirement_doc_draft"))
        self.assertLess(en.index("semantic_decoy_opt_in"), en.index("requirement_doc_draft"))
        self.assertIn("default off", graph)
        self.assertIn("explicit opt-in", graph)


if __name__ == "__main__":
    unittest.main()
