/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@makeplane/propel/components/button";
import { useTranslation } from "@plane/i18n";
import { repositoryBase, repositoryService } from "@/services/repository.service";
import type { Repository } from "@/services/repository.service";
import { CodeReviewReport } from "./code-review-report";
import type { ReviewRun } from "./code-review-report";

type Link = {
  id: string;
  repository_id: string;
  mr_iid: number;
  active: boolean;
  accepted: boolean;
  current_run_id: string | null;
  error: string;
  version: { web_url?: string; draft?: boolean; state?: string };
};
type Decision = { id: string; run_id: string; kind: string; reason: string; actor_id: string; revision: number };
type Data = {
  revision: number;
  csrf_token: string;
  can_edit: boolean;
  evidence_inconsistent: boolean;
  links: Link[];
  current_runs: ReviewRun[];
  runs: ReviewRun[];
  decisions: Decision[];
  next_offset: number | null;
  events: { id: string; kind: string; payload: { reason?: string }; created_at: string }[];
};
type MR = { iid: number; title: string; state: string; draft: boolean };

/** Task-scoped review workflow; server owns version, permission and completion checks. */
export function CodeReviewPanel({
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
  const base = repositoryBase(workspaceSlug, projectId);
  const path = base + `work-items/${issueId}/code-review/`;
  const [data, setData] = useState<Data>();
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [repository, setRepository] = useState("");
  const [mrs, setMrs] = useState<MR[]>([]);
  const [mr, setMr] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState("");
  const [history, setHistory] = useState<ReviewRun>();
  const [historyDecisions, setHistoryDecisions] = useState<Decision[]>([]);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [offset, setOffset] = useState(0);
  const epoch = useRef(0);
  const operation = useRef({ signature: "", key: "" });
  const refresh = useCallback(async () => {
    const version = ++epoch.current;
    try {
      const result = await repositoryService.read<Data>(path + `?offset=${offset}`);
      if (version === epoch.current) {
        setData(result);
        setError("");
      }
    } catch {
      if (version === epoch.current) setError(t("code_review.load_error"));
    }
  }, [path, offset, t]);
  useEffect(() => {
    const requestEpoch = epoch;
    setData(undefined);
    setHistory(undefined);
    setSelected("");
    setReason("");
    void refresh();
    const timer = setInterval(() => void refresh(), 10000);
    return () => {
      clearInterval(timer);
      requestEpoch.current++;
    };
  }, [refresh]);
  useEffect(() => {
    let active = true;
    setRepositories([]);
    setRepository("");
    setMrs([]);
    setMr("");
    setPage(1);
    void repositoryService
      .read<Repository[]>(base + "repositories/")
      .then((rows) => {
        if (active)
          setRepositories(rows.filter((r) => r.enabled && r.provider === "gitlab" && r.purpose === "development"));
        return undefined;
      })
      .catch(() => {
        if (active) setError(t("code_review.load_error"));
      });
    return () => {
      active = false;
    };
  }, [base, t]);
  useEffect(() => {
    let active = true;
    setMrs([]);
    setMr("");
    if (repository)
      void repositoryService
        .read<{ results: MR[] }>(path + `merge-requests/?repository_id=${repository}&page=${page}`)
        .then((value) => {
          if (active) setMrs(value.results);
          return undefined;
        })
        .catch(() => {
          if (active) setError(t("code_review.load_error"));
        });
    return () => {
      active = false;
    };
  }, [repository, page, path, t]);
  const link = data?.links.find((l) => l.id === selected && l.active) ?? data?.links.find((l) => l.active);
  const run = history ?? data?.current_runs.find((r) => r.id === link?.current_run_id);
  const decisions = history ? historyDecisions : (data?.decisions.filter((d) => d.run_id === run?.id) ?? []);
  const latest = decisions.at(-1);
  const editable = !disabled && !!data?.can_edit && !busy;
  const current = !!run && run.id === link?.current_run_id && !history;
  useEffect(() => {
    setReason("");
  }, [run?.id]);

  /** Keep an operation key across transport retries; changing intent creates a new key. */
  const mutate = async (action: string, body: Record<string, unknown>) => {
    if (!data) return;
    setBusy(true);
    setError("");
    const signature = JSON.stringify([action, body]);
    if (operation.current.signature !== signature) operation.current = { signature, key: crypto.randomUUID() };
    try {
      await repositoryService.write(path + action, "POST", data.csrf_token, {
        ...body,
        idempotency_key: operation.current.key,
      });
      operation.current = { signature: "", key: "" };
      setHistory(undefined);
      setReason("");
      await refresh();
    } catch (failure) {
      const details = (failure as { response?: { data?: unknown } }).response?.data;
      setError(details ? JSON.stringify(details) : t("code_review.action_error"));
    } finally {
      setBusy(false);
    }
  };
  const showHistory = async (row: ReviewRun) => {
    try {
      const value = await repositoryService.read<ReviewRun & { decisions: Decision[] }>(path + `runs/${row.id}/`);
      setHistory(value);
      setHistoryDecisions(value.decisions);
    } catch {
      setError(t("code_review.load_error"));
    }
  };
  const decide = (decision: string) => {
    if (!run) return;
    void mutate(`runs/${run.id}/decisions/`, {
      decision,
      reason,
      report_digest: run.report_digest,
      input_digest: run.input_digest,
      expected_decision_revision: latest?.revision ?? 0,
    });
  };
  return (
    <section className="mb-4 space-y-3 rounded-md border border-subtle p-4" aria-label={t("code_review.title")}>
      <h3 className="font-medium">{t("code_review.title")}</h3>
      {error && (
        <p role="alert" className="text-danger-primary">
          {error}
        </p>
      )}
      {data?.evidence_inconsistent && (
        <p role="status" className="text-danger-primary">
          {t("code_review.inconsistent")}
        </p>
      )}
      <p className="text-sm text-secondary">{t("code_review.hint")}</p>
      <div className="flex flex-wrap gap-2">
        <select
          aria-label={t("code_review.repository")}
          value={repository}
          disabled={!editable}
          onChange={(e) => {
            setRepository(e.target.value);
            setPage(1);
          }}
          className="rounded border border-subtle bg-surface-1 p-2"
        >
          <option value="">{t("code_review.repository")}</option>
          {repositories.map((repo) => (
            <option key={repo.id} value={repo.id}>
              {repo.path}
            </option>
          ))}
        </select>
        <select
          aria-label={t("code_review.mr")}
          value={mr}
          disabled={!editable}
          onChange={(e) => setMr(e.target.value)}
          className="max-w-full rounded border border-subtle bg-surface-1 p-2"
        >
          <option value="">{t("code_review.mr")}</option>
          {mrs.map((row) => (
            <option key={row.iid} value={row.iid}>
              !{row.iid} {row.title} ({row.state})
            </option>
          ))}
        </select>
        <Button
          size="sm"
          stretch="auto"
          variant="secondary"
          disabled={!editable || !mr}
          onClick={() =>
            void mutate("links/", {
              repository_id: repository,
              mr_iid: Number(mr),
              expected_revision: data?.revision,
            })
          }
          label={t("code_review.link")}
        />
        {repository && (
          <>
            <Button
              size="sm"
              stretch="auto"
              variant="secondary"
              disabled={page === 1}
              onClick={() => setPage(page - 1)}
              label={t("code_review.previous")}
            />
            <Button
              size="sm"
              stretch="auto"
              variant="secondary"
              disabled={mrs.length < 20}
              onClick={() => setPage(page + 1)}
              label={t("code_review.next")}
            />
          </>
        )}
      </div>
      <ul className="space-y-1">
        {data?.links
          .filter((l) => l.active)
          .map((item) => (
            <li key={item.id} className="flex gap-2">
              <button
                type="button"
                className="text-accent-primary underline"
                onClick={() => {
                  setSelected(item.id);
                  setHistory(undefined);
                }}
              >
                !{item.mr_iid}
              </button>
              <span>{item.version.draft ? t("code_review.draft") : item.version.state}</span>
              <span>{item.accepted ? t("code_review.accepted") : t("code_review.pending")}</span>
              <span>{item.error}</span>
            </li>
          ))}
      </ul>
      {!link && <p>{t("code_review.no_links")}</p>}
      {run && <CodeReviewReport run={run} />}
      {latest && (
        <p>
          {t(`code_review.${latest.kind}`)} · {latest.actor_id} · {latest.reason}
        </p>
      )}
      {link && (
        <div className="space-y-2">
          <textarea
            aria-label={t("code_review.reason")}
            placeholder={t("code_review.reason")}
            value={reason}
            maxLength={5000}
            disabled={!editable}
            onChange={(e) => setReason(e.target.value)}
            className="w-full rounded border border-subtle bg-surface-1 p-2"
          />
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              stretch="auto"
              variant="secondary"
              disabled={
                !editable ||
                !current ||
                run?.status !== "completed" ||
                (!!run.report.findings?.length && !reason.trim())
              }
              onClick={() => decide("accepted")}
              label={t("code_review.accept")}
            />
            <Button
              size="sm"
              stretch="auto"
              variant="secondary"
              disabled={!editable || !current}
              onClick={() => decide("returned")}
              label={t("code_review.return")}
            />
            <Button
              size="sm"
              stretch="auto"
              variant="secondary"
              disabled={!editable}
              onClick={() =>
                void mutate(`links/${link.id}/rerun/`, {
                  expected_revision: data?.revision,
                })
              }
              label={t("code_review.rerun")}
            />
            <Button
              size="sm"
              stretch="auto"
              variant="secondary"
              disabled={!editable || !reason.trim()}
              onClick={() =>
                void mutate(`links/${link.id}/remove/`, {
                  reason,
                  expected_revision: data?.revision,
                })
              }
              label={t("code_review.remove")}
            />
          </div>
        </div>
      )}
      <details>
        <summary>{t("code_review.history")}</summary>
        <ul>
          {data?.events.map((event) => (
            <li key={event.id}>
              {event.created_at} · {event.kind} · {event.payload.reason}
            </li>
          ))}
        </ul>
        <ul>
          {data?.runs.map((row) => (
            <li key={row.id}>
              <button type="button" className="text-accent-primary underline" onClick={() => void showHistory(row)}>
                {row.source_sha.slice(0, 12)} · {t(`code_review.${row.status}`)}
              </button>
            </li>
          ))}
        </ul>
        <Button
          size="sm"
          stretch="auto"
          variant="secondary"
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 20))}
          label={t("code_review.previous")}
        />
        <Button
          size="sm"
          stretch="auto"
          variant="secondary"
          disabled={data?.next_offset == null}
          onClick={() => setOffset(data?.next_offset ?? 0)}
          label={t("code_review.next")}
        />
      </details>
    </section>
  );
}
