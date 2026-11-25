/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import ReactMarkdown from "react-markdown";
import { useTranslation } from "@plane/i18n";

export type DocumentFinding = {
  id: string;
  title?: string | null;
  severity: string;
  path: string;
  line: number;
  evidence: string;
  reason: string;
  suggestion: string;
};

/** Summarize legacy reports without generating or changing their review conclusions. */
function findingTitle(finding: DocumentFinding) {
  if (finding.title?.trim()) return finding.title.trim();
  const firstSentence = finding.reason.trim().split(/\r?\n|(?<=[。！？])\s*/u)[0];
  return firstSentence.length > 64 ? `${firstSentence.slice(0, 64)}…` : firstSentence;
}

/** Render model prose as text, paragraphs and lists, without HTML or embedded media. */
function FindingProse({ children }: { children: string }) {
  return (
    <div className="min-w-0 space-y-2 text-body-sm-regular leading-6 break-words [&_li]:pl-1 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:whitespace-pre-line [&_ul]:list-disc [&_ul]:pl-5">
      <ReactMarkdown
        skipHtml
        allowedElements={["p", "ul", "ol", "li", "strong", "em", "code", "pre", "br"]}
        unwrapDisallowed
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}

/** Keep the actionable explanation separate from the exact, unchanged source evidence. */
export function RequirementReviewFinding({ finding }: { finding: DocumentFinding }) {
  const { t } = useTranslation();
  return (
    <details className="min-w-0 rounded-md border border-subtle p-3">
      <summary className="cursor-pointer space-y-1">
        <span className="mr-2 text-caption-sm-regular font-medium text-secondary">
          {finding.id} · {t(`document_review.${finding.severity}`)}
        </span>
        <span className="text-body-sm-medium break-words">{findingTitle(finding)}</span>
        <span className="block text-caption-sm-regular break-all text-secondary">
          {finding.path}
          {finding.line ? `:${finding.line}` : ""}
        </span>
      </summary>
      <div className="mt-4 space-y-4 border-t border-subtle pt-3">
        <div className="space-y-1">
          <h4 className="text-body-sm-medium">{t("document_review.finding_problem")}</h4>
          <FindingProse>{finding.reason}</FindingProse>
        </div>
        <div className="space-y-1">
          <h4 className="text-body-sm-medium">{t("document_review.finding_action")}</h4>
          <FindingProse>{finding.suggestion}</FindingProse>
        </div>
        {finding.evidence && (
          <details className="rounded border border-subtle bg-surface-1 p-2">
            <summary className="cursor-pointer text-caption-sm-regular text-secondary">
              {t("document_review.finding_evidence")}
            </summary>
            <pre className="mt-2 max-h-60 overflow-auto text-caption-sm-regular leading-5 break-words whitespace-pre-wrap">
              {finding.evidence}
            </pre>
          </details>
        )}
      </div>
    </details>
  );
}
