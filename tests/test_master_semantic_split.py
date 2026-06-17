from __future__ import annotations

import pytest

from aegis.modules.master import (
    RequirementConstraint,
    RequirementSemanticAnalysis,
    close_requirement_intake,
    draft_requirement_document_from_conversation,
)


TECH_PATH_CASES = [
    ("我需要使用C++来实现一个数据整理程序，计算平均数和中位数", ["C++"], ["data processing program"]),
    ("帮我写个统计程序，用C++写", ["C++"], []),
    ("我要一个计算平均值的工具，必须用C++", ["C++"], []),
    ("用C++做一个CSV数据清洗工具", ["C++"], ["CSV"]),
    ("整个东西拿C++搞", ["C++"], []),
    ("这个小工具最好C++", ["C++"], []),
    ("C++版的数据统计器", ["C++"], []),
    ("写一个本地程序处理数据，语言就C++吧", ["C++"], []),
    ("不要Python，C++实现", ["C++"], []),
    ("我要输出CSV，用C++实现", ["C++"], ["CSV"]),
    ("生成Excel统计表，最好用C++", ["C++"], ["Excel", "table artifact"]),
    ("根据数据画柱状图，用C++", ["C++"], ["chart artifact"]),
    ("输出Markdown表格，C++写", ["C++"], ["Markdown", "table artifact"]),
    ("生成PDF报告，要求C++", ["C++"], ["PDF"]),
    ("C++或Python都可以，能算平均数和中位数就行", ["C++", "Python"], []),
    ("如果方便就用C++，不方便用Python也行", ["C++", "Python"], []),
    ("我倾向C++，但你判断更合适的方案", ["C++"], []),
    ("必须C++，除非你能证明Python更简单", ["C++", "Python"], []),
    ("必须用正则解析所有数据", ["regex-only"], []),
    ("必须用OCR识别表格", ["OCR"], ["table artifact"]),
    ("必须用LLM整理数据", ["LLM"], []),
    ("做成微服务", ["microservice"], []),
    ("做成本地CLI工具", ["CLI"], []),
    ("用C++做个东西", ["C++"], []),
    ("C++实现一下", ["C++"], []),
    ("帮我弄个数据的，C++", ["C++"], []),
    ("做那个统计，还是用C++", ["C++"], []),
    ("按之前说的做，语言C++", ["C++"], []),
    ("不能用Python", ["Python"], []),
    ("不能用第三方库", ["no-third-party-libraries"], []),
    ("不能联网", ["offline-only"], []),
    ("必须离线运行", ["offline-only"], []),
    ("不能保存原始数据", ["no-raw-data-retention"], []),
    ("我有一个CSV，要算平均数、中位数，输出JSON，必须用C++", ["C++"], ["CSV", "JSON"]),
    ("一次性整理Excel数据，生成统计表和柱状图，C++实现", ["C++"], ["Excel", "table artifact", "chart artifact"]),
    ("每天跑一次，读取日志，计算P50/P95，用C++写", ["C++"], []),
    ("在现有C++项目里加平均数和中位数计算", ["C++"], []),
    ("给非技术人员用，双击就能计算CSV平均数和中位数，必须C++", ["C++"], ["CSV"]),
]


@pytest.mark.parametrize(("raw_request", "expected_paths", "expected_deliverables"), TECH_PATH_CASES)
def test_pm_intake_extracts_technical_paths_without_polluting_purpose(
    raw_request: str,
    expected_paths: list[str],
    expected_deliverables: list[str],
):
    conversation = close_requirement_intake(
        raw_request,
        semantic_analysis=RequirementSemanticAnalysis(
            purpose="完成用户指定的数据处理目标",
            technical_path_requests=expected_paths,
            deliverable_requests=expected_deliverables,
        ),
    )

    for expected in expected_paths:
        assert expected in conversation.technical_path_requests
        assert expected not in conversation.purpose
    for expected in expected_deliverables:
        assert expected in conversation.deliverable_requests

    document = draft_requirement_document_from_conversation(conversation)
    for expected in expected_paths:
        assert expected not in document.objective
    technical_path_constraints = [
        item for item in document.constraints if item.text.startswith("Requested implementation path:")
    ]
    assert technical_path_constraints
    assert all(item.hard_constraint is False for item in technical_path_constraints)
    assert all(item.admission == "preference" for item in technical_path_constraints)


NOT_CLOSED_CASES = [
    "我要求C++实现，不接受别的语言",
    "用C++做个东西",
    "C++实现一下",
    "帮我弄个数据的，C++",
    "按之前说的做，语言C++",
    "不要Python，C++实现",
    "不能用Python",
]


@pytest.mark.parametrize("raw_request", NOT_CLOSED_CASES)
def test_pm_intake_does_not_close_when_purpose_is_missing(raw_request: str):
    conversation = close_requirement_intake(
        raw_request,
        semantic_analysis=RequirementSemanticAnalysis(
            purpose="",
            technical_path_requests=["C++"],
            unresolved_questions=["Clarify the concrete objective/outcome."],
            status="clarifying",
        ),
    )

    assert conversation.status == "clarifying"
    assert conversation.unresolved_questions
    assert conversation.technical_path_requests


EVIDENCE_CASES = [
    (
        RequirementConstraint(
            text="Requested implementation path: C++",
            source="customer_written_evidence",
            evidence_refs=["EVID-001"],
        ),
        "hard_constraint",
        True,
    ),
    (
        RequirementConstraint(
            text="Requested implementation path: C++",
            source="customer_written_evidence",
            evidence_refs=[],
        ),
        "rejected",
        False,
    ),
    (
        RequirementConstraint(
            text="Requested implementation path: C++",
            source="user",
            evidence_refs=[],
        ),
        "preference",
        False,
    ),
]


@pytest.mark.parametrize(("constraint", "admission", "hard_constraint"), EVIDENCE_CASES)
def test_requirement_document_admits_technical_paths_only_with_valid_evidence(
    constraint: RequirementConstraint,
    admission: str,
    hard_constraint: bool,
):
    conversation = close_requirement_intake(
        "在现有C++项目里加平均数和中位数计算",
        semantic_analysis=RequirementSemanticAnalysis(
            purpose="给现有项目增加平均数和中位数计算能力",
            technical_path_requests=["C++"],
        ),
    )
    conversation.raw_constraints = [constraint]

    document = draft_requirement_document_from_conversation(conversation)

    assert document.constraints[0].admission == admission
    assert document.constraints[0].hard_constraint is hard_constraint
