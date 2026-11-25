/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import { useTranslation } from "@plane/i18n";
import { ReviewOverview, ReviewChecks, ReviewChanges, ReviewSource, ReviewHandoff } from "./review-report-sections";
import type { ReviewCheck, ReviewComparison } from "./review-report-sections";

export type ReviewRun = {
  id: string;
  link_id: string;
  status: string;
  source_sha: string;
  target_sha: string;
  merge_base: string;
  input_digest: string;
  report_digest: string;
  error: string;
  source_url?: string;
  comparison?: ReviewComparison | null;
  snapshot?: { settings?: { tool_version: string; model: string } };
  report: {
    summary?: string;
    change_summary?: string;
    checks?: ReviewCheck[];
    change_groups?: { name: string; files: string[]; finding_count: number }[];
    findings?: { path: string; line: number; end_line?: number; severity: string; message: string }[];
    coverage?: {
      diff_files?: string[];
      completed?: string[];
      missing?: string[];
      excluded?: { path: string; exclude_reason: string }[];
    };
  };
};

/** Render untrusted report text as text, including uncovered and excluded paths. */
export function CodeReviewReport({ run }: { run: ReviewRun }) {
  const { t } = useTranslation();
  return (
    <div className="text-sm space-y-4">
      <ReviewOverview
        conclusion={t(run.status === "completed" ? "review_report.code_completed" : `code_review.${run.status}`)}
        summary={run.report.change_summary ?? run.report.summary}
        next={t(run.status === "completed" ? "review_report.code_next" : "review_report.wait_next")}
        counts={[
          { label: t("review_report.findings"), value: run.report.findings?.length ?? 0 },
          { label: t("review_report.files"), value: run.report.coverage?.diff_files?.length ?? 0 },
          { label: t("review_report.uncovered"), value: run.report.coverage?.missing?.length ?? 0 },
        ]}
      />
      {run.error && <p role="alert">{run.error}</p>}
      <ReviewChecks checks={run.report.checks} />
      <ReviewChanges comparison={run.comparison} />
      <section className="space-y-2">
        <h4 className="font-medium">{t("review_report.change_groups")}</h4>
        {run.report.change_groups?.map((group) => (
          <details key={group.name} className="rounded border border-subtle p-3">
            <summary className="cursor-pointer break-all">
              {group.name} · {group.files.length} {t("review_report.files")} · {group.finding_count}{" "}
              {t("review_report.findings")}
            </summary>
            <ul className="mt-2 space-y-1">
              {group.files.map((path) => (
                <li key={path}>
                  <ReviewSource base={run.source_url} path={path} />
                </li>
              ))}
            </ul>
          </details>
        ))}
        {!run.report.change_groups && <p className="text-secondary">{t("review_report.legacy_groups")}</p>}
      </section>
      <details className="rounded border border-subtle p-3">
        <summary>{t("review_report.version_details")}</summary>
        <dl className="text-xs break-all text-secondary">
          <dt>{t("code_review.source")}</dt>
          <dd>{run.source_sha}</dd>
          <dt>{t("code_review.target")}</dt>
          <dd>{run.target_sha}</dd>
          <dt>{t("code_review.baseline")}</dt>
          <dd>{run.merge_base}</dd>
          <dt>{t("code_review.tool")}</dt>
          <dd>
            {run.snapshot?.settings?.tool_version} / {run.snapshot?.settings?.model}
          </dd>
        </dl>
      </details>
      <ul className="space-y-2">
        {run.report.findings?.map((finding) => (
          <li
            key={finding.path + ":" + finding.line + ":" + finding.message}
            className="rounded border border-subtle p-2"
          >
            <strong>
              {finding.severity} · {finding.path}:{finding.line}
            </strong>
            <p className="whitespace-pre-wrap">{finding.message}</p>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <ReviewSource base={run.source_url} path={finding.path} line={finding.line} />
              <ReviewHandoff
                text={`${t("review_report.handoff_boundary")}\n${run.source_sha}\n${finding.path}:${finding.line}\n${finding.severity}\n${finding.message}`}
              />
            </div>
          </li>
        ))}
      </ul>
      <details>
        <summary>{t("code_review.coverage")}</summary>
        <p>
          {t("code_review.files")}: {run.report.coverage?.diff_files?.join(", ")}
        </p>
        <p>
          {t("code_review.missing")}: {run.report.coverage?.missing?.join(", ") || "—"}
        </p>
        <ul>
          {run.report.coverage?.excluded?.map((file) => (
            <li key={file.path}>
              {file.path} — {file.exclude_reason}
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
