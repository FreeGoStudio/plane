# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Evidence requirements for new document reviews, independent of stored legacy reports."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


REVIEW_POLICY = """
以输入中的用户原始需求、后续明确确认及本次交付明确适用的约束为依据；
Agent建议、最佳实践和推断不自动成为要求。只审查本次范围及直接阻止其验收的依赖。
等级与阻断分别判断：P0为有明确成立路径的严重数据破坏、重大安全后果或核心业务严重错误；
P1为已确认要求的遗漏、错误、冲突、不当限制或关键验收缺口，会导致错误实现或错误验收；
P2为已有有效覆盖且不改变业务含义及验收结论的表述、引用或证据说明问题；
P3为结构、措辞、可读性及非必要补充。不能仅凭“安全风险”“核心业务”判P0。
歧义若允许不符合需求的实现为P1；必需证据实际缺失不能按描述问题降为P2。
policy记录等级、证据状态、是否阻断、阻断范围及六项举证。
阻断须同时满足依据有效、范围相关、缺口真实、影响具体、无有效等效覆盖。
阻断仅限受影响验收单元；只有影响整体或整体必要前置条件才阻断整体交付。
六项举证：原始依据及来源、缺口定位、反例证明、影响分析、等效覆盖检查、最小修复方案。
反例至少一种：全部AC通过但原始要求未满足；允许或要求的场景被排除；条款无法同时满足。
具体场景与逻辑推演足够，不要求运行代码。完全遗漏应列出检查过的覆盖位置，不编造位置。
等效覆盖须已确认且适用于当前交付、明确纳入遵循范围、足以推出所需行为、可验证且无冲突；
检查其他AC、业务规则和架构约束。已有效覆盖不得因当前AC没有重复描述而阻断。
证据状态：confirmed为已证实，needs_clarification为待澄清，needs_verification为待验证。
不确定事项只在涉及原定交付必要前置条件时阻断相应验收，写明“验收条件尚未证实”，
列明缺失信息、验证方式或需谁决定，不宣称已证实缺陷，不自行选择新增要求。
confirmed且阻断使用blocking；不确定且阻断使用missing_information；其他均使用suggestion。
P2/P3不阻断。非阻断不确定事项仍保留证据状态，不用missing_information阻断整个结果。
有blocking则changes_requested，否则有missing_information则insufficient_information，否则passed。
最小修复仅消除原始要求缺口；关联问题默认登记，新增业务规则或公共架构调整须另行确认。
阻断不是扩大修改范围的授权。复审只针对原问题及修复直接影响；新问题独立举证，
不得将优化建议升级为旧问题关闭条件。关闭条件区分文档/实现修正、自动验证和最终验收。
允许零问题，不设最低数量。没有阻断时明确说明“未发现满足阻断条件的问题”，建议不影响通过。
policy.original_basis逐字引用原始要求，basis_source_type为basis时basis_source为title或description_html，
为document时basis_source为documents中的路径。非阻断建议没有原始依据时这些字段可为空；
阻断必须引用有效原始依据，不以待评审PRD中的自创规则冒充用户确认。
policy.delivery_prerequisite仅在不确定事项涉及原定必要前置条件时为true，
prerequisite_basis说明为何属于原定前置条件。equivalent_coverage表示是否已有有效覆盖。
reason直接说明问题；suggestion写最小修改动作；policy字段填具体证据，不使用空白占位。
"""


class ReviewPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: Literal["P0", "P1", "P2", "P3"]
    evidence_status: Literal["confirmed", "needs_clarification", "needs_verification"]
    blocks: bool
    blocking_scope: str = Field(max_length=3000)
    basis_source_type: Literal["basis", "document"]
    basis_source: str = Field(max_length=3000)
    original_basis: str = Field(max_length=5000)
    gap: str = Field(max_length=5000)
    counterexample: str = Field(max_length=5000)
    impact: str = Field(max_length=5000)
    coverage_check: str = Field(max_length=5000)
    equivalent_coverage: bool
    minimum_fix: str = Field(max_length=5000)
    delivery_prerequisite: bool
    prerequisite_basis: str = Field(max_length=5000)
    closure_condition: str = Field(min_length=1, max_length=5000)


def validate_policy(policy, severity, snapshot):
    """Reject unsupported blocking assertions without silently turning them into a pass."""
    if policy.original_basis:
        sources = snapshot.get("basis", {}) if policy.basis_source_type == "basis" else snapshot["documents"]
        source = sources.get(policy.basis_source)
        if not isinstance(source, str) or policy.original_basis not in source:
            raise ValueError("invented_original_basis")
    expected = "suggestion"
    if policy.blocks:
        if policy.priority not in ("P0", "P1"):
            raise ValueError("nonblocking_priority")
        if policy.equivalent_coverage:
            raise ValueError("effective_coverage_blocks")
        required = (
            "blocking_scope",
            "basis_source",
            "original_basis",
            "gap",
            "counterexample",
            "impact",
            "coverage_check",
            "minimum_fix",
            "closure_condition",
        )
        if any(not getattr(policy, name).strip() for name in required):
            raise ValueError("incomplete_blocking_evidence")
        if policy.evidence_status == "confirmed":
            expected = "blocking"
        else:
            if not policy.delivery_prerequisite or not policy.prerequisite_basis.strip():
                raise ValueError("unproven_delivery_prerequisite")
            expected = "missing_information"
    if severity != expected:
        raise ValueError("inconsistent_blocking_policy")


def policy_reason(reason, policy):
    """Expose the structured assessment through existing API and UI prose consumers."""
    status = {
        "confirmed": "已证实",
        "needs_clarification": "待澄清",
        "needs_verification": "待验证",
    }[policy.evidence_status]
    fields = [
        ("等级", policy.priority),
        ("证据状态", status),
        ("是否阻断", "是" if policy.blocks else "否"),
        ("阻断范围", policy.blocking_scope),
        (
            "原始依据",
            f"{policy.basis_source_type}:{policy.basis_source}\n{policy.original_basis}"
            if policy.original_basis
            else "无；仅为建议",
        ),
        ("缺口定位", policy.gap),
        ("反例证明", policy.counterexample),
        ("影响分析", policy.impact),
        ("等效覆盖检查", policy.coverage_check),
        ("最小修复方案", policy.minimum_fix),
        ("原定交付前置条件", policy.prerequisite_basis),
        ("关闭条件", policy.closure_condition),
    ]
    if policy.blocks and policy.evidence_status != "confirmed":
        reason = "验收条件尚未证实。\n\n" + reason
    return reason + "\n\n" + "\n\n".join(f"{label}：{value}" for label, value in fields if value)
