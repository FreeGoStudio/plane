/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@makeplane/propel/components/button";
import { useTranslation } from "@plane/i18n";
import { repositoryBase, repositoryService } from "@/services/repository.service";
import { RequirementReviewPanel } from "./requirement-review";
import { WbsChanges } from "./wbs-changes";
import { choicesComplete, type ChangeAction, type WbsChange, type WbsChild, type WbsTask } from "./wbs-update";

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
  execution?: { choices?: Record<string, ChangeAction>; replacement_tasks?: Record<string, WbsTask> };
  workflow?: number;
  source?: {
    kind: string;
    commit?: string;
    digest: string;
    documents?: Record<string, string>;
    basis?: { description_html: string };
  };
  source_diff?: string;
  scenario?: string;
  existing_children?: WbsChild[];
  readiness?: { can_apply: boolean; reason: string; body_confirmation_required?: boolean };
  result: {
    summary?: string;
    tasks?: Task[];
    changes?: WbsChange[];
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
  const [choices, setChoices] = useState<Record<string, ChangeAction>>({});
  const [replacements, setReplacements] = useState<Record<string, WbsTask>>({});
  const [bodyConfirmed, setBodyConfirmed] = useState(false);
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
    setChoices(run?.execution?.choices || {});
    setReplacements(run?.execution?.replacement_tasks || {});
    setBodyConfirmed(false);
  }, [run?.id, run?.result_digest, run?.execution?.choices, run?.execution?.replacement_tasks]);
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
          ? {
              decision,
              result_digest: run.result_digest,
              reason,
              ...(run.workflow === 2
                ? {
                    choices: decision === "approve" ? choices : {},
                    source_confirmed: bodyConfirmed,
                    replacement_tasks:
                      decision === "approve"
                        ? Object.fromEntries(
                            Object.entries(replacements).filter(
                              ([id]) =>
                                ["update", "append"].includes(choices[id]) &&
                                run.result.changes?.some((change) => change.id === id && !change.task)
                            )
                          )
                        : {},
                  }
                : {}),
            }
          : {
              expected_updated_at: data.source_version,
              idempotency_key: requestKey.current,
              confirmed: true,
              mode: "update",
            }
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
  if (!data && error) return <p role="alert">{error}</p>;
  if (!data?.can_start) return null;
  return (
    <>
      <RequirementReviewPanel
        workspaceSlug={workspaceSlug}
        projectId={projectId}
        issueId={issueId}
        disabled={disabled}
      />
      <section className="mb-4 space-y-3 rounded-md border border-subtle p-4" aria-label={t("wbs.title")}>
        <h3 className="font-medium">{t("wbs.title")}</h3>
        <p className="text-sm text-secondary">{t("wbs.analyze_hint")}</p>
        {error && (
          <p role="alert" className="text-sm text-danger-primary">
            {error}
          </p>
        )}
        {run && (
          <p role="status">
            {t(run.workflow === 2 && run.status === "completed" ? "wbs.applied" : `wbs.status_${run.status}`)}
          </p>
        )}
        {run?.error && <p role="alert">{run.error}</p>}
        {run?.scenario && <p className="text-sm">{t(`wbs.scenario_${run.scenario}`)}</p>}
        {
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
              label={t("wbs.update_wbs")}
            />
            <Button
              size="sm"
              variant="secondary"
              disabled={busy}
              onClick={() => void refresh()}
              label={t("wbs.refresh")}
              stretch="auto"
            />
          </>
        }
        {run?.result.summary && <p className="text-sm whitespace-pre-wrap">{run.result.summary}</p>}
        {run?.source && (
          <details className="text-sm break-words">
            <summary>PRD · {run.source.commit || run.source.digest}</summary>
            {run.source.documents ? (
              Object.entries(run.source.documents).map(([documentPath, content]) => (
                <div key={documentPath}>
                  <h4>{documentPath}</h4>
                  <pre className="whitespace-pre-wrap">{content}</pre>
                </div>
              ))
            ) : (
              <p>
                {
                  new DOMParser().parseFromString(run.source.basis?.description_html || "", "text/html").body
                    .textContent
                }
              </p>
            )}
          </details>
        )}
        {run?.source_diff && (
          <details>
            <summary>{t("wbs.prd_diff")}</summary>
            <pre className="text-sm break-words whitespace-pre-wrap">{run.source_diff}</pre>
          </details>
        )}
        {run?.readiness && !run.readiness.can_apply && (
          <p role="status" className="text-sm text-warning-primary">
            {run.readiness.reason}
          </p>
        )}
        {run?.result.changes && (
          <WbsChanges
            changes={run.result.changes}
            existingChildren={run.existing_children || []}
            choices={choices}
            replacements={replacements}
            criteria={run.result.coverage?.map((item) => item.criterion_id) || []}
            onReplacement={(id, task) => {
              setReplacements((current) => ({ ...current, [id]: task }));
              setApproved(false);
            }}
            disabled={disabled || busy || run.status !== "ready"}
            onChoose={(id, action) => {
              setChoices((current) => ({ ...current, [id]: action }));
              setApproved(false);
            }}
          />
        )}
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
            {run.readiness?.body_confirmation_required && (
              <label className="text-sm flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={bodyConfirmed}
                  onChange={(event) => setBodyConfirmed(event.target.checked)}
                />
                {t("wbs.confirm_source")}
              </label>
            )}
            <label className="text-sm flex items-center gap-2">
              <input type="checkbox" checked={approved} onChange={(e) => setApproved(e.target.checked)} />
              {t(run.workflow === 2 ? "wbs.apply_changes" : "wbs.confirm_draft")}
            </label>
            <Button
              size="sm"
              stretch="auto"
              variant="primary"
              disabled={
                disabled ||
                busy ||
                !approved ||
                (run.workflow === 2 &&
                  (!run.readiness?.can_apply ||
                    (run.readiness.body_confirmation_required && !bodyConfirmed) ||
                    !choicesComplete(run.result.changes || [], run.existing_children || [], choices, replacements)))
              }
              onClick={() => void submit("approve")}
              label={t(run.workflow === 2 ? "wbs.apply_changes" : "wbs.approve")}
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
        {(data?.results.length || 0) > 1 && (
          <details className="text-sm">
            <summary>{t("wbs.history")}</summary>
            {data?.results.slice(1).map((old) => (
              <details key={old.id} className="my-2 break-words">
                <summary>
                  {old.source?.commit || old.id} ·{" "}
                  {t(old.workflow === 2 && old.status === "completed" ? "wbs.applied" : `wbs.status_${old.status}`)}
                </summary>
                <p className="whitespace-pre-wrap">{old.result.summary}</p>
                {old.result.changes && (
                  <WbsChanges
                    changes={old.result.changes}
                    existingChildren={old.existing_children || []}
                    choices={old.execution?.choices || {}}
                    replacements={old.execution?.replacement_tasks || {}}
                    disabled
                    onChoose={() => undefined}
                  />
                )}
              </details>
            ))}
          </details>
        )}
      </section>
    </>
  );
}
