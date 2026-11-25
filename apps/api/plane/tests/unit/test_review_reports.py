# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Evidence accounting, conservative comparisons and distinct review/test outcomes."""

import pytest
from plane.singularity.requirement_review_coverage import Coverage, Check, requirement_inventory, validate_coverage
from plane.singularity.requirement_review_generation import GeneratedReviewResult
from plane.singularity.review_report import compare_findings, code_report_details


def test_inventory_preserves_inline_text_and_all_source_statements():
    rows = requirement_inventory(
        {"description_html": "<h2>范围</h2><p>必须<b>保留</b>记录。</p><ul><li><p>不得重复扣款。</p></li></ul>"}
    )
    assert [r["text"] for r in rows] == ["范围", "必须保留记录。", "不得重复扣款。"]
    assert rows == requirement_inventory({"description_html": "范围\n必须保留记录。\n不得重复扣款。"})


def test_coverage_requires_every_requirement_and_real_source_evidence():
    inventory = requirement_inventory({"description_html": "必须保留记录。"})
    row = Coverage(
        requirement_id=inventory[0]["id"], status="covered", explanation="AC1覆盖", references=[], finding_ids=[]
    )
    checks = [
        Check(id=k, status="passed", explanation="已核对")
        for k in ("scope", "rule_consistency", "acceptance_testability", "equivalent_coverage")
    ]
    with pytest.raises(ValueError, match="incomplete_requirement_inventory"):
        validate_coverage([], checks, inventory, {}, set())
    with pytest.raises(ValueError, match="coverage_requires_evidence"):
        validate_coverage([row], checks, inventory, {}, set())
    row = Coverage.model_validate(
        {**row.model_dump(), "references": [{"path": "prd.md", "line": 1, "quote": "AC1：保留记录"}]}
    )
    validate_coverage([row], checks, inventory, {"prd.md": "AC1：保留记录"}, set())
    with pytest.raises(ValueError, match="invented_coverage_reference"):
        validate_coverage([row], checks, inventory, {"prd.md": "其他内容"}, set())
    row.status = "gap"
    with pytest.raises(ValueError, match="gap_requires_finding"):
        validate_coverage([row], checks, inventory, {}, set())


def test_disappearing_findings_are_not_declared_fixed():
    old = [{"path": "a.py", "line": 3, "message": "division by zero", "severity": "high"}]
    moved = [{**old[0], "line": 20, "severity": "low"}]
    rows = compare_findings(moved, old)
    assert rows[0]["status"] == "reobserved"
    assert rows[0]["previous_severity"] == "high"
    assert compare_findings([], old)[0]["status"] == "not_reobserved"
    assert compare_findings(old, [])[0]["status"] == "new"


def test_code_details_never_claim_runtime_or_requirement_validation():
    report = {
        "findings": [{"path": "src/a.py"}],
        "coverage": {
            "diff_files": ["src/a.py", "tests/a.py"],
            "completed": ["src/a.py", "tests/a.py"],
            "missing": [],
            "excluded": [],
        },
    }
    code_report_details("completed", report, {"summary": {"text": "修改了支付回调与对应测试"}})
    assert report["change_summary"] == "修改了支付回调与对应测试"
    assert len(report["change_groups"]) == 2
    statuses = {c["id"]: c["status"] for c in report["checks"]}
    assert statuses == {
        "file_coverage": "passed",
        "code_findings": "needs_attention",
        "runtime_tests": "not_checked",
        "requirement_alignment": "not_checked",
    }


def test_generated_schema_has_only_required_properties_at_every_object():
    def check(value):
        if isinstance(value, dict):
            if value.get("type") == "object":
                assert set(value.get("properties", {})) == set(value.get("required", []))
                assert value.get("additionalProperties") is False
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(GeneratedReviewResult.model_json_schema())
