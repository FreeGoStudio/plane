# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Read-only report projections; absence of a finding never proves its resolution."""

import hashlib
import json
from collections import defaultdict


def fingerprint(finding):
    """Match exact assertions across runs without depending on changing line numbers."""
    policy = finding.get("policy") or {}
    identity = [
        finding.get("path", ""),
        policy.get("original_basis", ""),
        policy.get("gap") or finding.get("message") or finding.get("reason", ""),
    ]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()[:20]


def compare_findings(current, previous):
    """Return conservative identity matches, retaining the old evidence for absent findings."""
    before = {fingerprint(item): item for item in previous}
    after = {fingerprint(item): item for item in current}
    rows = []
    for key, item in after.items():
        rows.append(
            {
                "fingerprint": key,
                "status": "reobserved" if key in before else "new",
                "path": item.get("path", ""),
                "title": item.get("title") or item.get("message") or item.get("reason", ""),
                "previous_severity": before.get(key, {}).get("severity"),
                "severity": item.get("severity"),
            }
        )
    for key, item in before.items():
        if key not in after:
            rows.append(
                {
                    "fingerprint": key,
                    "status": "not_reobserved",
                    "path": item.get("path", ""),
                    "title": item.get("title") or item.get("message") or item.get("reason", ""),
                    "previous_severity": item.get("severity"),
                    "severity": None,
                }
            )
    return rows


def code_report_details(status, report, raw):
    """Describe observed file coverage and findings without inventing tests or business approval."""
    coverage = report["coverage"]
    groups = defaultdict(list)
    for path in coverage["diff_files"]:
        folder = path.rsplit("/", 1)[0] if "/" in path else "."
        groups[folder].append(path)
    report["change_groups"] = [
        {"name": name, "files": files, "finding_count": sum(f.get("path") in files for f in report["findings"])}
        for name, files in sorted(groups.items())
    ]
    # Preserve a real narrative when the upstream tool supplies one, not a summary of counters.
    upstream = raw.get("summary")
    narrative = upstream if isinstance(upstream, str) else upstream.get("text") if isinstance(upstream, dict) else None
    report["change_summary"] = (
        narrative
        if isinstance(narrative, str) and narrative.strip()
        else (
            f"本次差异涉及 {len(coverage['diff_files'])} 个文件，发现 {len(report['findings'])} 项待判断问题。"
            "文件分组用于定位改动，不代表已完成业务需求符合性验收。"
        )
    )
    report["checks"] = [
        {
            "id": "file_coverage",
            "status": "passed" if status == "completed" else "needs_verification",
            "explanation": (
                f"检查完成 {len(coverage.get('completed', []))} 个文件，"
                f"排除 {len(coverage.get('excluded', []))} 个，未覆盖 {len(coverage.get('missing', []))} 个。"
            ),
        },
        {
            "id": "code_findings",
            "status": "needs_attention"
            if report["findings"]
            else "passed"
            if status == "completed"
            else "needs_verification",
            "explanation": "问题需要逐项判断；执行完成不等于人工确认。"
            if report["findings"]
            else "本轮未发现问题；不证明不存在缺陷。",
        },
        {"id": "runtime_tests", "status": "not_checked", "explanation": "本次静态代码审查未执行项目测试或程序。"},
        {
            "id": "requirement_alignment",
            "status": "not_checked",
            "explanation": "当前代码审查职责不包含需求符合性验收。",
        },
    ]
    report["schema_version"] = "review-report-v2"
