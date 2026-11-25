# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Source-grounded requirement inventory and coverage assessment contract."""

import hashlib
from html.parser import HTMLParser
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

POLICY_VERSION = "documents-report-v2"
COVERAGE_INSTRUCTIONS = """
为输入requirement_inventory中的每一项原始陈述输出一条coverage，不能遗漏或自行改写编号。
陈述包含业务要求、范围及非业务背景；非要求背景可以not_applicable，但必须具体说明。
covered仅表示文档覆盖，必须给出documents内逐字引用和准确行号，不表示程序已实现或业务验收完成。
gap必须关联本报告finding_ids；needs_verification表示需要外部证据；not_checked明确本轮未检查及原因。
references中的path、quote、line必须来自固定输入，禁止编造外部约束已经读取。
输出change_summary概括这份需求的交付内容与范围，不编造相对历史版本的变化。
输出next_action明确接下来处理什么；零问题时仍说明哪些条件需实际执行或人工确认。
summary用一至两句概括结论，next_action只写最优先的下一步；不要重复问题详情或完整举证。
输出checks，固定四项scope、rule_consistency、acceptance_testability、equivalent_coverage：
每项状态为passed、needs_attention、needs_verification或not_checked，并给出具体说明。
每项explanation优先用一至两句说明结果；完整论证放在对应finding的结构化字段中。
这些是文档审查结论，不是已运行的自动测试。无法判断时不得标passed。
"""


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Reference(Contract):
    path: str
    line: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=3000)


class Coverage(Contract):
    requirement_id: str
    status: Literal["covered", "gap", "needs_verification", "not_checked", "not_applicable"]
    explanation: str = Field(min_length=1, max_length=3000)
    references: list[Reference] = Field(max_length=20)
    finding_ids: list[str] = Field(max_length=80)


class Check(Contract):
    id: Literal["scope", "rule_consistency", "acceptance_testability", "equivalent_coverage"]
    status: Literal["passed", "needs_attention", "needs_verification", "not_checked"]
    explanation: str = Field(min_length=1, max_length=3000)


def requirement_inventory(basis):
    """Extract all source paragraphs, preserving text rather than guessing which are requirements."""

    class Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []

        def handle_data(self, data):
            self.parts.append(data)

        def handle_endtag(self, tag):
            if tag in ("p", "li", "div", "h1", "h2", "h3", "tr"):
                self.parts.append("\n")

        def handle_starttag(self, tag, attrs):
            if tag == "br":
                self.parts.append("\n")

    parser = Parser()
    parser.feed(basis.get("description_html") or "")
    statements = list(dict.fromkeys(x.strip() for x in "".join(parser.parts).splitlines() if x.strip()))
    if not statements and basis.get("title"):
        statements = [basis["title"]]
    return [{"id": "R-" + hashlib.sha256(text.encode()).hexdigest()[:16], "text": text} for text in statements]


def validate_coverage(coverage, checks, inventory, documents, finding_ids):
    """Require complete inventory accounting and real source references without weakening findings."""
    ids = [row.requirement_id for row in coverage]
    if len(ids) != len(set(ids)) or set(ids) != {row["id"] for row in inventory}:
        raise ValueError("incomplete_requirement_inventory")
    for row in coverage:
        if not row.explanation.strip() or not set(row.finding_ids) <= finding_ids:
            raise ValueError("invalid_coverage_finding")
        if row.status == "covered" and not row.references:
            raise ValueError("coverage_requires_evidence")
        if row.status == "gap" and not row.finding_ids:
            raise ValueError("gap_requires_finding")
        for ref in row.references:
            source = documents.get(ref.path, "")
            lines = source.splitlines()
            if ref.quote not in source or ref.line > len(lines) or ref.quote.splitlines()[0] not in lines[ref.line - 1]:
                raise ValueError("invented_coverage_reference")
    expected = {"scope", "rule_consistency", "acceptance_testability", "equivalent_coverage"}
    if len(checks) != 4 or {check.id for check in checks} != expected:
        raise ValueError("incomplete_review_checks")
