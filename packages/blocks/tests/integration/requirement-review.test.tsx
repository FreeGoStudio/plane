/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RequirementReviewPanel } from "../../../../apps/web/components/issues/issue-detail-widgets/sub-issues/requirement-review";

const service = vi.hoisted(() => ({ read: vi.fn(), write: vi.fn() }));
vi.mock("@/services/repository.service", () => ({ repositoryBase: () => "/test/", repositoryService: service }));
vi.mock("@plane/i18n", () => {
  const labels: Record<string, string> = {
    "document_review.adopt": "采用此版本",
    "document_review.adopting": "采用中",
    "document_review.adoption_completed": "已采用",
    "document_review.override": "人工确认采用",
  };
  const t = (key: string) => labels[key] ?? key;
  return { useTranslation: () => ({ t }) };
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
