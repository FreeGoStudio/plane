# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Document review blocking decisions and compatibility with historical reports."""

import json
from unittest.mock import Mock, patch

import pytest

from plane.singularity.requirement_review_generation import generate, validate_result
from plane.singularity.requirement_review_policy import ReviewPolicy, validate_policy

pytestmark = pytest.mark.unit


@pytest.fixture
def snapshot():
    return {
        "basis": {"title": "订单", "description_html": "已支付订单不得重复扣款。"},
        "documents": {"prd.md": "AC01：支付成功显示结果。"},
    }


@pytest.fixture
def policy():
    return ReviewPolicy(
        priority="P1",
        evidence_status="confirmed",
        blocks=True,
        blocking_scope="支付幂等验收",
        basis_source_type="basis",
        basis_source="description_html",
        original_basis="已支付订单不得重复扣款。",
        gap="AC01仅检查成功显示，未限制重复扣款。",
        counterexample="重复回调扣款两次且显示成功，AC01通过，原始要求未满足。",
        impact="重复扣款导致错误实现和错误验收。",
        coverage_check="检查全部AC，无其他幂等规则。",
        equivalent_coverage=False,
        minimum_fix="补充重复回调只扣款一次的验收条件。",
        delivery_prerequisite=False,
        prerequisite_basis="",
        closure_condition="文档明确幂等规则；实现及重复回调测试、最终验收分别记录。",
    )


def report(policy=None, severity="blocking", verdict="changes_requested"):
    finding = {
        "id": "F1",
        "title": "重复扣款未受约束",
        "severity": severity,
        "path": "prd.md",
        "line": 1,
        "evidence": "AC01：支付成功显示结果。",
        "reason": "当前验收条件允许重复扣款。",
        "suggestion": "补充幂等验收。",
    }
    if policy is not None:
        finding["policy"] = policy.model_dump()
    return {"verdict": verdict, "summary": "审查结果", "findings": [finding]}


@pytest.mark.parametrize("priority", ["P0", "P1"])
def test_supported_blockers(priority, policy, snapshot):
    policy.priority = priority
    assert validate_result(report(policy), snapshot)["verdict"] == "changes_requested"


@pytest.mark.parametrize("priority", ["P2", "P3"])
def test_low_priority_never_blocks(priority, policy, snapshot):
    policy.priority = priority
    with pytest.raises(ValueError, match="nonblocking_priority"):
        validate_result(report(policy), snapshot)
    policy.blocks = False
    assert validate_result(report(policy, "suggestion", "passed"), snapshot)["verdict"] == "passed"


@pytest.mark.parametrize(
    "field",
    [
        "blocking_scope",
        "basis_source",
        "original_basis",
        "gap",
        "counterexample",
        "impact",
        "coverage_check",
        "minimum_fix",
        "closure_condition",
    ],
)
def test_blockers_require_complete_evidence(field, policy, snapshot):
    setattr(policy, field, " ")
    with pytest.raises(ValueError):
        validate_policy(policy, "blocking", snapshot)


def test_equivalent_coverage_prevents_blocking(policy, snapshot):
    policy.equivalent_coverage = True
    with pytest.raises(ValueError, match="effective_coverage_blocks"):
        validate_result(report(policy), snapshot)
    policy.blocks = False
    validate_result(report(policy, "suggestion", "passed"), snapshot)


@pytest.mark.parametrize("status", ["needs_clarification", "needs_verification"])
def test_uncertainty_only_blocks_original_prerequisites(status, policy, snapshot):
    policy.evidence_status = status
    with pytest.raises(ValueError, match="unproven_delivery_prerequisite"):
        validate_result(report(policy, "missing_information", "insufficient_information"), snapshot)
    policy.blocks = False
    validate_result(report(policy, "suggestion", "passed"), snapshot)
    policy.blocks = True
    policy.delivery_prerequisite = True
    policy.prerequisite_basis = "原定支付验收需要确认重复回调不重复扣款，目前尚无该证据。"
    validate_result(report(policy, "missing_information", "insufficient_information"), snapshot)
    with pytest.raises(ValueError, match="inconsistent_blocking_policy"):
        validate_result(report(policy), snapshot)


def test_original_basis_must_exist_in_snapshot(policy, snapshot):
    policy.original_basis = "审查者新增的要求"
    with pytest.raises(ValueError, match="invented_original_basis"):
        validate_result(report(policy), snapshot)
    policy.basis_source_type = "document"
    policy.basis_source = "original.md"
    policy.original_basis = "已支付订单不得重复扣款。"
    snapshot["documents"]["original.md"] = "用户确认：已支付订单不得重复扣款。"
    validate_result(report(policy), snapshot)


def test_legacy_reports_remain_unchanged(snapshot):
    value = report()
    del value["findings"][0]["title"]
    assert validate_result(value, snapshot) == value


def test_empty_review_can_pass(snapshot):
    value = {"verdict": "passed", "summary": "未发现满足阻断条件的问题。", "findings": []}
    assert validate_result(value, snapshot) == value


def test_verdict_and_source_checks_remain_enforced(policy, snapshot):
    with pytest.raises(ValueError, match="inconsistent_verdict"):
        validate_result(report(policy, verdict="passed"), snapshot)
    value = report(policy)
    value["findings"][0]["evidence"] = "不存在的原文"
    with pytest.raises(ValueError, match="invented_evidence"):
        validate_result(value, snapshot)


def test_generation_requires_policy_and_exposes_it_to_existing_consumers(policy, snapshot, tmp_path, monkeypatch):
    key = tmp_path / "model.key"
    key.write_text("test-key")
    monkeypatch.setenv("DOCUMENT_REVIEW_MODEL_KEY_FILE", str(key))
    response = Mock()

    def set_response(value):
        from plane.singularity.requirement_review_coverage import requirement_inventory

        value.update(
            change_summary="支付幂等要求",
            next_action="补充验收条件",
            coverage=[
                {
                    "requirement_id": requirement_inventory(snapshot["basis"])[0]["id"],
                    "status": "gap",
                    "explanation": "缺少幂等验收",
                    "references": [],
                    "finding_ids": ["F1"],
                }
            ],
            checks=[
                {"id": key, "status": "needs_attention", "explanation": "存在待处理缺口"}
                for key in ("scope", "rule_consistency", "acceptance_testability", "equivalent_coverage")
            ],
        )
        response.json.return_value = {
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(value)}]}],
        }

    with patch("plane.singularity.requirement_review_generation.requests.post", return_value=response):
        set_response(report())
        with pytest.raises(ValueError):
            generate(snapshot)
        set_response(report(policy))
        result = generate(snapshot)
        reason = result["findings"][0]["reason"]
        assert "等级：P1" in reason
        assert policy.counterexample in reason
        assert policy.minimum_fix in reason
        assert policy.closure_condition in reason
        assert validate_result(result, snapshot) == result
        policy.evidence_status = "needs_verification"
        policy.delivery_prerequisite = True
        policy.prerequisite_basis = "原定支付验收的前置条件"
        set_response(report(policy, "missing_information", "insufficient_information"))
        assert "验收条件尚未证实" in generate(snapshot)["findings"][0]["reason"]
