/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import { useTranslation } from "@plane/i18n";

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
  snapshot?: { settings?: { tool_version: string; model: string } };
  report: {
    summary?: string;
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
    <div className="text-sm space-y-2">
      <p>
        {t("code_review.status")}: {t(`code_review.${run.status}`)}
      </p>
      <p role={run.error ? "alert" : undefined}>{run.error || run.report.summary}</p>
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
