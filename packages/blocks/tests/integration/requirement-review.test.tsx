/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RequirementReviewPanel } from "../../../../apps/web/components/issues/issue-detail-widgets/sub-issues/requirement-review";
import { RequirementReviewFinding } from "../../../../apps/web/components/issues/issue-detail-widgets/sub-issues/requirement-review-finding";
import {
  ReviewChecks,
  ReviewChanges,
  ReviewSource,
  ReviewHandoff,
  ReviewCoverage,
} from "../../../../apps/web/components/issues/issue-detail-widgets/review-report-sections";
import { CodeReviewReport } from "../../../../apps/web/components/issues/issue-detail-widgets/code-review-report";

const service = vi.hoisted(() => ({ read: vi.fn(), write: vi.fn() }));
vi.mock("@/services/repository.service", () => ({ repositoryBase: () => "/test/", repositoryService: service }));
vi.mock("@plane/i18n", () => {
  const labels: Record<string, string> = {
    "document_review.adopt": "采用此版本",
    "document_review.adopting": "采用中",
    "document_review.adoption_completed": "已采用",
    "document_review.override": "人工确认采用",
    "document_review.finding_problem": "问题与影响",
    "document_review.finding_action": "建议修改",
    "document_review.finding_evidence": "查看引用原文",
    "document_review.policy_details": "查看判定依据",
    "document_review.policy_closure": "关闭条件",
  };
  const t = (key: string) => labels[key] ?? key;
  return { useTranslation: () => ({ t }) };
});

describe("readable document findings", () => {
  const finding = {
    id: "F1",
    severity: "blocking",
    path: "requirements/SING-19/prd.md",
    line: 33,
    reason: "缺少固定版本 PRD 的审查与采用检查。仅核对提交，无法证明采用完成。",
    suggestion: "在 AC-004 增加：\n\n- 记录固定版本。\n- 核对采用结果。",
    evidence: "| AC-004 | 冻结候选 | 未经人工批准不得发布 |",
  };
  it("gives legacy findings a readable heading and keeps exact evidence separately collapsed", () => {
    const { container } = render(<RequirementReviewFinding finding={finding} />);
    expect(container.querySelector("summary")?.textContent).toContain("缺少固定版本 PRD 的审查与采用检查。");
    expect(screen.getByRole("heading", { name: "问题与影响", hidden: true })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "建议修改", hidden: true })).toBeTruthy();
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.querySelector("pre")?.textContent).toBe(finding.evidence);
    expect(container.querySelector("details details")?.hasAttribute("open")).toBe(false);
  });
  it("prefers the concise generated title without truncating the full explanation", () => {
    const { container } = render(<RequirementReviewFinding finding={{ ...finding, title: "缺少 PRD 采用检查" }} />);
    expect(container.querySelector("summary")?.textContent).toContain("缺少 PRD 采用检查");
    expect(container.textContent).toContain(finding.reason);
  });
  it("renders markdown escapes and line breaks without enabling injected HTML or media", () => {
    const { container } = render(
      <RequirementReviewFinding
        finding={{
          ...finding,
          reason: "核对 A\\|B。\\\n保留原始约束。<script>alert(1)</script>",
          suggestion: "![remote](https://example.com/track.png)\n[unsafe](javascript:alert(1))",
          evidence: "<img src=x onerror=alert(1)>",
        }}
      />
    );
    expect(container.textContent).toContain("核对 A|B。");
    expect(container.querySelectorAll("script, img, iframe, a")).toHaveLength(0);
    expect(container.querySelector("pre")?.textContent).toBe("<img src=x onerror=alert(1)>");
  });
  it("does not invent a line number or empty source section for missing information", () => {
    const { container } = render(<RequirementReviewFinding finding={{ ...finding, line: 0, evidence: "" }} />);
    expect(container.querySelector("summary")?.textContent).not.toContain(":0");
    expect(screen.queryByText("查看引用原文")).toBeNull();
  });
  it("shows structured findings without duplicating the flattened legacy explanation", () => {
    const policy = {
      priority: "P1",
      evidence_status: "confirmed",
      blocking_scope: "固定版本采用",
      gap: "缺少固定版本采用核对。",
      impact: "可能错误验收。",
      minimum_fix: "核对采用记录及对应版本。",
      original_basis: "必须采用固定版本。",
      counterexample: "所有AC通过但采用未完成。",
      coverage_check: "版本冻结不能证明已采用。",
      closure_condition: "补齐核对并保留证据。",
      delivery_prerequisite: false,
      prerequisite_basis: "不适用的前置条件说明",
    };
    const { container } = render(
      <RequirementReviewFinding finding={{ ...finding, policy, reason: "不应重复显示的拼接长文" }} />
    );
    expect(container.querySelector("summary")?.textContent).toContain("P1");
    expect(container.textContent).not.toContain("不应重复显示的拼接长文");
    expect(container.textContent).not.toContain(policy.prerequisite_basis);
    expect(container.textContent?.split(policy.minimum_fix)).toHaveLength(2);
    const evidence = screen.getByText("查看判定依据").closest("details")!;
    expect(evidence.open).toBe(false);
    fireEvent.click(container.querySelector("summary")!);
    fireEvent.click(screen.getByText("查看判定依据"));
    expect(evidence.open).toBe(true);
    expect(evidence.querySelectorAll("dt")).toHaveLength(3);
    expect(evidence.textContent).toContain(policy.counterexample);
    expect(container.textContent).toContain(policy.closure_condition);
  });
});

function data(status: string | null = null, verdict = "passed") {
  return {
    config: { draft_branch: "draft/REQ-1", adopted_branch: "REQ-1", adopted_sha: "merge-sha", error: "" },
    results: [
      { id: "review", source_sha: "source-sha", status: "completed", result: { verdict }, adoption_status: status },
    ],
    // The authoritative status must work even if history is on another page.
    adoptions: [],
    target_sha: "merge-sha",
    csrf_token: "test",
    next_offset: null,
  };
}
function panel() {
  return render(<RequirementReviewPanel workspaceSlug="test" projectId="project" issueId="issue" disabled={false} />);
}
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe("document version adoption", () => {
  it("keeps a superseded pass readable but prevents adoption", async () => {
    const value = data();
    service.read.mockResolvedValue({ ...value, results: [{ ...value.results[0], superseded: true }] });
    panel();
    expect(((await screen.findByRole("button", { name: "采用此版本" })) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("review_report.superseded")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "review_report.rereview" })).toBeNull();
  });
  it("requests a new fixed-version assessment and selects the new run", async () => {
    const value = data();
    service.read.mockResolvedValueOnce(value).mockResolvedValue({
      ...value,
      results: [{ ...value.results[0], id: "new-review", status: "queued", result: {} }, ...value.results],
    });
    service.write.mockResolvedValue({ id: "new-review" });
    panel();
    fireEvent.click(await screen.findByRole("button", { name: "review_report.rereview" }));
    await waitFor(() => expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("new-review"));
    expect(service.write).toHaveBeenCalledWith(expect.stringContaining("review/rereview/"), "POST", "test", {
      idempotency_key: expect.any(String),
    });
    expect(screen.queryByRole("button", { name: "采用此版本" })).toBeNull();
  });
  it.each(["pending", "running"])("disables a %s version after loading", async (status) => {
    service.read.mockResolvedValue(data(status));
    panel();
    const button = await screen.findByRole("button", { name: "采用中" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(button);
    expect(service.write).not.toHaveBeenCalled();
  });
  it.each(["passed", "changes_requested"])(
    "shows completed adoption for %s, including human overrides",
    async (verdict) => {
      service.read.mockResolvedValue(data("completed", verdict));
      panel();
      expect(((await screen.findByRole("button", { name: "已采用" })) as HTMLButtonElement).disabled).toBe(true);
      expect(screen.queryByRole("button", { name: "人工确认采用" })).toBeNull();
    }
  );
  it("blocks repeated clicks while submitting and remains pending when refresh fails", async () => {
    service.read.mockResolvedValueOnce(data()).mockRejectedValue(new Error("offline"));
    let resolve!: (value: unknown) => void;
    service.write.mockReturnValue(
      new Promise((done) => {
        resolve = done;
      })
    );
    panel();
    const button = await screen.findByRole("button", { name: "采用此版本" });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(service.write).toHaveBeenCalledTimes(1);
    expect(((await screen.findByRole("button", { name: "采用中" })) as HTMLButtonElement).disabled).toBe(true);
    resolve({ status: "pending", source_sha: "source-sha" });
    await waitFor(() => expect(service.read).toHaveBeenCalledTimes(2));
    expect(((await screen.findByRole("button", { name: "采用中" })) as HTMLButtonElement).disabled).toBe(true);
  });
  it("keeps an unadopted or previously failed version available", async () => {
    service.read.mockResolvedValue(data());
    panel();
    expect(((await screen.findByRole("button", { name: "采用此版本" })) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("review report evidence boundaries", () => {
  it("does not turn missing historical checks into success", () => {
    render(<ReviewChecks />);
    expect(screen.getByText("review_report.legacy_checks")).toBeTruthy();
    expect(screen.queryByText("review_report.passed")).toBeNull();
  });
  it("labels disappearance on the same revision as unverified", () => {
    const { container } = render(
      <ReviewChanges
        comparison={{
          previous_run_id: "old",
          previous_source_sha: "sha",
          same_source: true,
          findings: [
            { fingerprint: "f", status: "not_reobserved", path: "prd.md", title: "Missing acceptance criterion" },
          ],
        }}
      />
    );
    expect(container.textContent).toContain("review_report.not_reobserved");
    expect(container.textContent).toContain("review_report.same_source");
    expect(container.querySelector("details")?.open).toBe(false);
  });
  it("links evidence to a fixed revision and refuses executable URL schemes", () => {
    const { container, rerender } = render(
      <ReviewSource base="https://git.example/repo/-/blob/abc123" path="docs/a b.md" line={8} />
    );
    expect(container.querySelector("a")?.getAttribute("href")).toBe(
      "https://git.example/repo/-/blob/abc123/docs/a%20b.md#L8"
    );
    rerender(<ReviewSource base="javascript:alert(1)" path="prd.md" />);
    expect(container.querySelector("a")).toBeNull();
  });
  it("shows original requirements with collapsed source evidence", () => {
    const { container } = render(
      <ReviewCoverage
        inventory={[{ id: "R1", text: "Keep an audit trail" }]}
        rows={[
          {
            requirement_id: "R1",
            status: "covered",
            explanation: "AC-1 covers it",
            references: [{ path: "prd.md", line: 2, quote: "AC-1: record the actor" }],
            finding_ids: [],
          },
        ]}
      />
    );
    expect(container.querySelector("summary")?.textContent).toContain("Keep an audit trail");
    expect(container.querySelector("details")?.open).toBe(false);
    expect(container.querySelector("blockquote")?.textContent).toBe("AC-1: record the actor");
  });
  it("copies the bounded handoff without submitting a repair", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    render(<ReviewHandoff text="Verify original scope; repair only AC-1" />);
    fireEvent.click(screen.getByRole("button"));
    await screen.findByText("review_report.copied");
    expect(writeText).toHaveBeenCalledWith("Verify original scope; repair only AC-1");
    expect(service.write).not.toHaveBeenCalled();
  });
  it("keeps code execution completion distinct from human acceptance and runtime tests", () => {
    render(
      <CodeReviewReport
        run={{
          id: "r",
          link_id: "l",
          status: "completed",
          source_sha: "head",
          target_sha: "target",
          merge_base: "base",
          input_digest: "i",
          report_digest: "d",
          error: "",
          report: {
            change_summary: "Payment callback changes",
            checks: [{ id: "runtime_tests", status: "not_checked", explanation: "Static review only" }],
            change_groups: [{ name: "src", files: ["src/pay.py"], finding_count: 0 }],
            findings: [],
            coverage: { diff_files: ["src/pay.py"], missing: [] },
          },
        }}
      />
    );
    expect(screen.getByRole("status").textContent).toBe("review_report.code_completed");
    expect(screen.getByText("review_report.not_checked")).toBeTruthy();
    expect(screen.getByText("Payment callback changes")).toBeTruthy();
    expect(screen.getByText("src/pay.py", { selector: "span" })).toBeTruthy();
  });
});
