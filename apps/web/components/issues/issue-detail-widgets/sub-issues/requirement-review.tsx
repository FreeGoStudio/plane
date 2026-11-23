/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@makeplane/propel/components/button";
import { useTranslation } from "@plane/i18n";
import { useDateFormatter } from "@plane/utils";
import { repositoryBase, repositoryService } from "@/services/repository.service";

type Finding = {
  id: string;
  severity: string;
  path: string;
  line: number;
  evidence: string;
  reason: string;
  suggestion: string;
};
type Run = {
  id: string;
  source_sha: string;
  status: string;
  error: string;
  created_at: string;
  result: { verdict?: string; summary?: string; findings?: Finding[] };
  adoption_status?: "pending" | "running" | "completed" | null;
};
type Adoption = {
  id: string;
  source_sha: string;
  target_sha: string;
  kind: string;
  reason: string;
  actor_id: string;
  status: string;
  error: string;
  created_at: string;
};
type Data = {
  config: { draft_branch: string; adopted_branch: string; adopted_sha: string; error: string } | null;
  results: Run[];
  adoptions: Adoption[];
  csrf_token: string;
  target_sha: string;
  target_error: string;
  next_offset: number | null;
};

/** Display fixed-version findings and require a human explanation before an override. */
export function RequirementReviewPanel({
  workspaceSlug,
  projectId,
  issueId,
  disabled,
}: {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled: boolean;
}) {
  const { t } = useTranslation();
  const { locale, timeZone, renderFormattedDate } = useDateFormatter();
  const formatTimestamp = (value: string) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    const time = new Intl.DateTimeFormat(locale, {
      timeZone,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    }).format(date);
    return `${renderFormattedDate(value)} ${time}`;
  };
  const path = repositoryBase(workspaceSlug, projectId) + `work-items/${issueId}/requirement-review/`;
  const [data, setData] = useState<Data>();
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("");
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [submittingSource, setSubmittingSource] = useState<string>();
  const inFlight = useRef(false);
  const [error, setError] = useState("");
  const requestKey = useRef(crypto.randomUUID());
  const epoch = useRef(0);
  const refresh = useCallback(async () => {
    const version = ++epoch.current;
    try {
      const value = await repositoryService.read<Data>(path + `?offset=${offset}`);
      if (version === epoch.current) setData(value);
    } catch {
      if (version === epoch.current) setError(t("document_review.load_error"));
    }
  }, [path, offset, t]);
  useEffect(() => {
    const requestEpoch = epoch;
    setData(undefined);
    setSelected("");
    setReason("");
    setConfirmed(false);
    void refresh();
    const timer = setInterval(() => void refresh(), 10000);
    return () => {
      clearInterval(timer);
      requestEpoch.current++;
    };
  }, [refresh]);
  const run = data?.results.find((r) => r.id === selected) ?? data?.results[0];
  const adopted = run?.adoption_status === "completed";
  const adopting =
    !!run && (submittingSource === run.source_sha || ["pending", "running"].includes(run.adoption_status ?? ""));
  const adoptionLocked = adopted || adopting;
  useEffect(() => {
    setConfirmed(false);
    setReason("");
    requestKey.current = crypto.randomUUID();
  }, [run?.id, data?.target_sha]);
  /** Reuse operation keys on transport failure; the server owns all permission checks. */
  const submit = async (action: "retry" | "adopt", override = false) => {
    if (!data || !run || disabled || inFlight.current || (action === "adopt" && adoptionLocked)) return;
    inFlight.current = true;
    if (action === "adopt") setSubmittingSource(run.source_sha);
    setBusy(true);
    setError("");
    try {
      const response = await repositoryService.write<Adoption>(
        path + `${run.id}/${action}/`,
        "POST",
        data.csrf_token,
        action === "retry"
          ? { idempotency_key: requestKey.current }
          : {
              idempotency_key: requestKey.current,
              target_sha: data.target_sha,
              ...(override ? { override: true, confirmed, reason } : {}),
            }
      );
      // Retain the accepted operation even when the following refresh is offline.
      if (action === "adopt") {
        setData(
          (current) =>
            current && {
              ...current,
              results: current.results.map((item) =>
                item.source_sha === run.source_sha
                  ? { ...item, adoption_status: response.status as Run["adoption_status"] }
                  : item
              ),
            }
        );
      }
      requestKey.current = crypto.randomUUID();
      setConfirmed(false);
      setReason("");
      await refresh();
    } catch (failure) {
      const details = (failure as { response?: { data?: unknown } }).response?.data;
      setError(details ? JSON.stringify(details) : t("document_review.action_error"));
    } finally {
      inFlight.current = false;
      setSubmittingSource(undefined);
      setBusy(false);
    }
  };
  return (
    <section className="mb-4 space-y-3 rounded-md border border-subtle p-4" aria-label={t("document_review.title")}>
      <h3 className="font-medium">{t("document_review.title")}</h3>
      <p className="text-sm text-secondary">{t("document_review.description")}</p>
      {error && <p role="alert">{error}</p>}
      {data && !data.config && <p>{t("document_review.not_configured")}</p>}
      {data?.config && (
        <>
          <p className="break-all">
            {data.config.draft_branch} → {data.config.adopted_branch}
          </p>
          <p className="break-all">
            {t("document_review.adopted")}: {data.config.adopted_sha || "—"}
          </p>
          {(data.config.error || data.target_error) && <p role="alert">{data.config.error || data.target_error}</p>}
          <label className="block">
            {t("document_review.history")}
            <select
              value={run?.id ?? ""}
              onChange={(e) => setSelected(e.target.value)}
              className="block w-full rounded border border-subtle bg-surface-1 p-2"
            >
              {data.results.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.source_sha.slice(0, 12)} · {formatTimestamp(r.created_at)}
                </option>
              ))}
            </select>
          </label>
          {run && (
            <>
              <p role="status">
                {t(`document_review.${run.status}`)}{" "}
                {run.result.verdict && `· ${t(`document_review.${run.result.verdict}`)}`}
              </p>
              <p className="break-all">{run.source_sha}</p>
              {run.error && <p role="alert">{run.error}</p>}
              <p>{run.result.summary}</p>
              {run.result.findings?.map((f) => (
                <details key={f.id} className="rounded border border-subtle p-2">
                  <summary>
                    {f.id} · {t(`document_review.${f.severity}`)} · {f.path}
                    {f.line ? `:${f.line}` : ""}
                  </summary>
                  {f.evidence && <blockquote className="whitespace-pre-wrap">{f.evidence}</blockquote>}
                  <p>{f.reason}</p>
                  <p>{f.suggestion}</p>
                </details>
              ))}
              {run.status === "failed" && (
                <Button
                  size="sm"
                  stretch="auto"
                  variant="secondary"
                  disabled={disabled || busy}
                  onClick={() => void submit("retry")}
                  label={t("document_review.retry")}
                />
              )}
              {(run.result.verdict === "passed" || adoptionLocked) && (
                <Button
                  size="sm"
                  stretch="auto"
                  variant="primary"
                  disabled={disabled || busy || adoptionLocked || !data.target_sha}
                  onClick={() => void submit("adopt")}
                  label={t(
                    adopted
                      ? "document_review.adoption_completed"
                      : adopting
                        ? "document_review.adopting"
                        : "document_review.adopt"
                  )}
                />
              )}
              {!adoptionLocked && ["completed", "failed"].includes(run.status) && run.result.verdict !== "passed" && (
                <>
                  <label className="block">
                    {t("document_review.reason")}
                    <textarea
                      value={reason}
                      maxLength={5000}
                      onChange={(e) => setReason(e.target.value)}
                      className="block w-full rounded border border-subtle bg-transparent p-2"
                    />
                  </label>
                  <label className="flex gap-2">
                    <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
                    {t("document_review.confirm_override")}
                  </label>
                  <Button
                    size="sm"
                    stretch="auto"
                    variant="secondary"
                    disabled={disabled || busy || !confirmed || !reason.trim() || !data.target_sha}
                    onClick={() => void submit("adopt", true)}
                    label={t("document_review.override")}
                  />
                </>
              )}
            </>
          )}
          <div className="flex gap-2">
            <Button
              size="sm"
              stretch="auto"
              variant="secondary"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 20))}
              label={t("document_review.previous")}
            />
            <Button
              size="sm"
              stretch="auto"
              variant="secondary"
              disabled={data.next_offset === null}
              onClick={() => setOffset(data.next_offset ?? offset)}
              label={t("document_review.next")}
            />
          </div>
          {data.adoptions.map((a) => (
            <details key={a.id} className="rounded border border-subtle p-2">
              <summary>
                {t(`document_review.${a.kind === "override" ? "override_record" : a.kind}`)} ·{" "}
                {t(`document_review.${a.status}`)} · {a.source_sha.slice(0, 12)}
              </summary>
              <p>{a.reason}</p>
              <p>
                {a.actor_id} · {formatTimestamp(a.created_at)}
              </p>
              <p role="status">{a.error}</p>
            </details>
          ))}
        </>
      )}
    </section>
  );
}
