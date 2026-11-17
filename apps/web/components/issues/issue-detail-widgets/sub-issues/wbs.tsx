/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@makeplane/propel/components/button";
import { useTranslation } from "@plane/i18n";
import { repositoryBase, repositoryService } from "@/services/repository.service";

type Task = {
  id: string;
  title: string;
  scope: string;
  deliverable: string;
  acceptance: string;
  dependencies: string[];
  criteria: string[];
  role: string;
};
type Run = {
  id: string;
  status: string;
  result_digest: string;
  error: string;
  children: Record<string, string>;
  result: {
    summary?: string;
    tasks?: Task[];
    questions?: string[];
    coverage?: { criterion_id: string; disposition: string; basis: string; task_ids: string[] }[];
  };
};
type Data = { results: Run[]; source_version: string; csrf_token: string; can_start: boolean };

/** Page commands use the same persisted workflow and review endpoints as MCP. */
export function WbsPanel({
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
  const path = repositoryBase(workspaceSlug, projectId) + `work-items/${issueId}/wbs/`;
  const [data, setData] = useState<Data>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [approved, setApproved] = useState(false);
  const [reason, setReason] = useState("");
  const requestKey = useRef(crypto.randomUUID());
  const refresh = useCallback(async () => {
    try {
      setData(await repositoryService.read<Data>(path));
    } catch {
      setError(t("wbs.load_error"));
    }
  }, [path, t]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  const run = data?.results[0];
  useEffect(() => {
    if (!run || !["queued", "running"].includes(run.status)) return;
    const timer = setInterval(() => void refresh(), 4000);
    return () => clearInterval(timer);
  }, [run, refresh]);
  useEffect(() => {
    setApproved(false);
  }, [run?.id, run?.result_digest]);
  /** Preserve a submission key on transport failure and show server conflicts. */
  const submit = async (decision?: "approve" | "reject") => {
    if (!data) return;
    setBusy(true);
    setError("");
    try {
      await repositoryService.write(
        path + (decision && run ? `${run.id}/` : ""),
        "POST",
        data.csrf_token,
        decision && run
          ? { decision, result_digest: run.result_digest, reason }
          : { expected_updated_at: data.source_version, idempotency_key: requestKey.current, confirmed: true }
      );
      requestKey.current = crypto.randomUUID();
      setConfirmed(false);
      setApproved(false);
      await refresh();
      if (decision === "approve") window.location.reload();
    } catch (failure) {
      const details = (failure as { response?: { data?: unknown } }).response?.data;
      setError(details ? JSON.stringify(details) : t("wbs.action_error"));
    } finally {
      setBusy(false);
    }
  };
  if (!data?.can_start) return null;
  return (
    <section className="mb-4 space-y-3 rounded-md border border-subtle p-4" aria-label={t("wbs.title")}>
      <h3 className="font-medium">{t("wbs.title")}</h3>
      <p className="text-sm text-secondary">{t("wbs.description")}</p>
      {error && (
        <p role="alert" className="text-sm text-danger-primary">
          {error}
        </p>
      )}
      {run && <p role="status">{t(`wbs.status_${run.status}`)}</p>}
      {run?.error && <p role="alert">{run.error}</p>}
      {(!run || ["completed", "rejected", "failed"].includes(run.status)) && (
        <>
          <label className="text-sm flex items-center gap-2">
            <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
            {t("wbs.confirm_source")}
          </label>
          <Button
            size="sm"
            stretch="auto"
            variant="primary"
            disabled={disabled || busy || !confirmed}
            onClick={() => void submit()}
            label={t("wbs.start")}
          />
        </>
      )}
      {run?.result.summary && <p className="text-sm whitespace-pre-wrap">{run.result.summary}</p>}
      {run?.result.coverage?.map((c) => (
        <p key={c.criterion_id} className="text-sm">
          {c.criterion_id} · {c.task_ids.join(", ")} — {c.basis}
        </p>
      ))}
      {run?.result.tasks?.map((task) => (
        <article key={task.id} className="text-sm space-y-2 rounded-md border border-subtle p-3">
          <h4 className="font-medium">
            {task.id} · {task.title}
          </h4>
          <p>
            {task.role} · {task.criteria.join(", ")}
          </p>
          <p className="whitespace-pre-wrap">{task.scope}</p>
          <p className="whitespace-pre-wrap">
            {t("wbs.deliverable")}: {task.deliverable}
          </p>
          <p className="whitespace-pre-wrap">
            {t("wbs.acceptance")}: {task.acceptance}
          </p>
          <p>
            {t("wbs.dependencies")}: {task.dependencies.join(", ") || "—"}
          </p>
        </article>
      ))}
      {run?.result.questions?.map((q) => (
        <p key={q} className="text-sm">
          {q}
        </p>
      ))}
      {run?.status === "ready" && (
        <>
          <label className="text-sm flex items-center gap-2">
            <input type="checkbox" checked={approved} onChange={(e) => setApproved(e.target.checked)} />
            {t("wbs.confirm_draft")}
          </label>
          <Button
            size="sm"
            stretch="auto"
            variant="primary"
            disabled={disabled || busy || !approved}
            onClick={() => void submit("approve")}
            label={t("wbs.approve")}
          />
          <textarea
            aria-label={t("wbs.reason")}
            placeholder={t("wbs.reason")}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="block w-full rounded border border-subtle bg-transparent p-2"
          />
          <Button
            size="sm"
            stretch="auto"
            variant="secondary"
            disabled={disabled || busy || !reason.trim()}
            onClick={() => void submit("reject")}
            label={t("wbs.reject")}
          />
        </>
      )}
    </section>
  );
}
