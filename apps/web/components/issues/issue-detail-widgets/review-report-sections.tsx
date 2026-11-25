/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import { useState } from "react";
import { useTranslation } from "@plane/i18n";

export type ReviewCheck = { id: string; status: string; explanation: string };
export type ReviewComparison = {
  previous_run_id: string;
  previous_source_sha: string;
  same_source: boolean;
  findings: {
    fingerprint: string;
    status: string;
    path: string;
    title: string;
    previous_severity?: string | null;
    severity?: string | null;
  }[];
};
export type RequirementCoverage = {
  requirement_id: string;
  status: string;
  explanation: string;
  finding_ids: string[];
  references: { path: string; line: number; quote: string }[];
};

/** Link only to the server-provided fixed revision, encoding untrusted file paths. */
export function ReviewSource({ base, path, line }: { base?: string; path: string; line?: number }) {
  const url =
    base && /^https?:\/\//.test(base)
      ? `${base}/${path.split("/").map(encodeURIComponent).join("/")}${line ? `#L${line}` : ""}`
      : undefined;
  const label = `${path}${line ? `:${line}` : ""}`;
  return url ? (
    <a href={url} target="_blank" rel="noopener noreferrer" className="break-all underline">
      {label}
    </a>
  ) : (
    <span className="break-all">{label}</span>
  );
}

/** Lead with the decision and actionable next step; execution metadata belongs in details. */
export function ReviewOverview({
  conclusion,
  summary,
  next,
  counts,
}: {
  conclusion: string;
  summary?: string;
  next: string;
  counts: { label: string; value: number }[];
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3 rounded-md border border-subtle bg-surface-1 p-4">
      <h4 className="text-body-md-medium" role="status">
        {conclusion}
      </h4>
      <div className="flex flex-wrap gap-3 text-body-sm-regular">
        {counts.map((c) => (
          <span key={c.label}>
            {c.label} <strong>{c.value}</strong>
          </span>
        ))}
      </div>
      {summary && <p className="max-w-4xl leading-6 whitespace-pre-wrap">{summary}</p>}
      <p className="max-w-4xl leading-6">
        <strong>{t("review_report.next_action")}：</strong>
        {next}
      </p>
    </div>
  );
}

/** Display explicit outcomes; a missing historical check is never synthesized as passed. */
export function ReviewChecks({ checks }: { checks?: ReviewCheck[] }) {
  const { t } = useTranslation();
  return (
    <section className="space-y-2">
      <h4 className="font-medium">{t("review_report.checks")}</h4>
      {!checks?.length ? (
        <p className="text-secondary">{t("review_report.legacy_checks")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-body-sm-regular">
            <thead>
              <tr>
                {["check", "status", "explanation"].map((k) => (
                  <th key={k} className="border-b border-subtle p-2">
                    {t(`review_report.${k}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {checks.map((check) => (
                <tr key={check.id}>
                  <td className="border-b border-subtle p-2 align-top">{t(`review_report.${check.id}`)}</td>
                  <td className="border-b border-subtle p-2 align-top">{t(`review_report.${check.status}`)}</td>
                  <td className="border-b border-subtle p-2 align-top leading-6">
                    {check.explanation.length <= 160 ? (
                      check.explanation
                    ) : (
                      <details>
                        <summary className="cursor-pointer">{check.explanation.slice(0, 160)}…</summary>
                        <p className="mt-2 whitespace-pre-wrap">{check.explanation}</p>
                      </details>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/** Make requirement coverage visible without equating documentation with implementation. */
export function ReviewCoverage({
  rows,
  inventory,
  sourceUrl,
}: {
  rows?: RequirementCoverage[];
  inventory?: { id: string; text: string }[];
  sourceUrl?: string;
}) {
  const { t } = useTranslation();
  return (
    <section className="space-y-2">
      <h4 className="font-medium">{t("review_report.requirement_coverage")}</h4>
      <p className="text-caption-sm-regular text-secondary">{t("review_report.coverage_boundary")}</p>
      {!rows?.length ? (
        <p>{t("review_report.legacy_coverage")}</p>
      ) : (
        rows.map((row) => (
          <details key={row.requirement_id} className="rounded border border-subtle p-3">
            <summary className="cursor-pointer leading-6">
              {t(`review_report.${row.status}`)} ·{" "}
              {inventory?.find((r) => r.id === row.requirement_id)?.text ?? row.requirement_id}
            </summary>
            <div className="mt-3 space-y-3 leading-6">
              <p>{row.explanation}</p>
              {row.finding_ids.length > 0 && (
                <p>
                  {t("review_report.related_findings")}：{row.finding_ids.join(", ")}
                </p>
              )}
              {row.references.map((ref) => (
                <div key={`${ref.path}:${ref.line}:${ref.quote}`} className="space-y-1">
                  <ReviewSource base={sourceUrl} path={ref.path} line={ref.line} />
                  <blockquote className="border-l-2 border-subtle pl-3 whitespace-pre-wrap text-secondary">
                    {ref.quote}
                  </blockquote>
                </div>
              ))}
            </div>
          </details>
        ))
      )}
    </section>
  );
}

/** Compare exact assertions conservatively: disappearance is not verified remediation. */
export function ReviewChanges({ comparison }: { comparison?: ReviewComparison | null }) {
  const { t } = useTranslation();
  if (!comparison) return null;
  return (
    <details className="rounded border border-subtle p-3">
      <summary className="cursor-pointer font-medium">
        {t("review_report.review_changes")} · {comparison.previous_source_sha.slice(0, 12)}
      </summary>
      <p className="my-3 text-secondary">{t("review_report.comparison_boundary")}</p>
      {comparison.same_source && <p className="mb-3">{t("review_report.same_source")}</p>}
      <ul className="space-y-3">
        {comparison.findings.map((f) => (
          <li key={f.fingerprint} className="space-y-1">
            <strong>{t(`review_report.${f.status}`)}</strong>
            <p className="break-all text-secondary">
              {f.path} · {f.previous_severity ?? "—"} → {f.severity ?? "—"}
            </p>
            <p className="leading-6 whitespace-pre-wrap">{f.title}</p>
          </li>
        ))}
      </ul>
    </details>
  );
}

/** Copy a bounded handoff for an agent; copying never submits or authorizes a fix. */
export function ReviewHandoff({ text }: { text: string }) {
  const { t } = useTranslation();
  const [state, setState] = useState("copy_handoff");
  return (
    <button
      type="button"
      className="rounded border border-subtle px-3 py-1 text-body-sm-regular"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setState("copied");
        } catch {
          setState("copy_failed");
        }
      }}
    >
      {t(`review_report.${state}`)}
    </button>
  );
}
