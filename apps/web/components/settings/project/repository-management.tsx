/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import { useRef, useState } from "react";
import useSWR from "swr";
import { Button } from "@makeplane/propel/components/button";
import { useTranslation } from "@plane/i18n";
import { repositoryService as api } from "@/services/repository.service";

type Management = { enabled: boolean; status: string; error_code: string };
type Member = {
  user_id: string;
  display_name: string;
  plane_role: number | null;
  external_user_id: string | null;
  access_override: number | null;
  default_access: number;
  applied_access: number | null;
  effective_access: number | null;
  direct_access: number | null;
  managed: boolean;
  status: string;
  error_code: string;
  revision: number;
};

const field = "rounded-md border border-subtle bg-surface-1 px-3 py-2 text-sm text-primary";

function useStatusLabel() {
  const { t } = useTranslation();
  return (status: string) => {
    if (["ready", "synced", "removed"].includes(status)) return t("common.completed");
    if (["unmanaged", "inherited"].includes(status)) return t("repository_ui.external_permissions");
    if (status === "waiting_identity") return t("repository_ui.identity_required");
    if (["blocked", "error", "conflict"].includes(status)) return t("error");
    if (status === "not_started") return t("repository_ui.unbound");
    return t(status === "processing" ? "common.processing" : "common.pending");
  };
}

/** Tracks asynchronous repository initialization and prevents duplicate requests until it settles. */
export function RepositoryInitialization({
  base,
  canManage,
  write,
  busy,
  onReady,
}: {
  base: string;
  canManage: boolean;
  write: () => Promise<{ status: string }>;
  busy: boolean;
  onReady: () => void;
}) {
  const { t } = useTranslation();
  const submittingRef = useRef(false);
  const [submitting, setSubmitting] = useState(false);
  const [submissionFailed, setSubmissionFailed] = useState(false);
  const { data, error, mutate } = useSWR<Management>(
    base + "repository-management/",
    (url: string) => api.read<Management>(url),
    {
      refreshInterval: 5000,
      onSuccess: (value) => {
        if (value.status === "ready") onReady();
      },
    }
  );
  const running = submitting || ["pending", "processing", "retry"].includes(data?.status ?? "");
  /** Publish the accepted state through SWR so older polling responses cannot overwrite it. */
  async function initialize() {
    if (submittingRef.current || busy || running) return;
    submittingRef.current = true;
    setSubmitting(true);
    setSubmissionFailed(false);
    try {
      await mutate(async () => ({ ...data!, error_code: "", ...(await write()) }), { revalidate: false });
    } catch {
      setSubmissionFailed(true);
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
      void mutate();
    }
  }
  const progress = submitting ? "submitting" : (data?.status ?? "not_started");
  if (!data) return error ? <p role="alert">{t("repository_ui.load_failed")}</p> : null;
  if (!data.enabled) return null;
  return (
    <section className="mt-6 rounded-lg border border-subtle p-5">
      <p>{t("repository_ui.management_hint")}</p>
      <p className="my-3" role="status" aria-live="polite">
        {t(`repository_ui.initialization.${progress}`)}
      </p>
      {error && <p role="alert">{t("repository_ui.initialization.status_unavailable")}</p>}
      {submissionFailed && <p role="alert">{t("repository_ui.failed")}</p>}
      {data.error_code && (
        <details className="text-sm mb-3">
          <summary>{t("error")}</summary>
          <code>{data.error_code}</code>
        </details>
      )}
      {canManage && (
        <Button
          label={t("repository_ui.initialize")}
          size="md"
          variant="secondary"
          stretch="auto"
          disabled={busy || running}
          onClick={() => void initialize()}
        />
      )}
    </section>
  );
}

export function RepositoryMemberPermissions({
  base,
  repositoryId,
  csrf,
  busy,
  action,
}: {
  base: string;
  repositoryId: string;
  csrf: string;
  busy: boolean;
  action: (fn: () => Promise<void>) => Promise<void>;
}) {
  const { t } = useTranslation();
  const label = useStatusLabel();
  const [open, setOpen] = useState(false);
  const url = base + `repositories/${repositoryId}/members/`;
  const { data, error, mutate } = useSWR<{ results: Member[] }>(
    open ? url : null,
    (path: string) => api.read<{ results: Member[] }>(path),
    { refreshInterval: 5000 }
  );
  return (
    <details className="text-sm mt-4" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="cursor-pointer">{t("members")}</summary>
      <p className="my-3 text-secondary">{t("repository_ui.permission_hint")}</p>
      {error && <p role="alert">{t("repository_ui.load_failed")}</p>}
      {data?.results.map((member) => (
        <form
          key={`${member.user_id}:${member.revision}`}
          className="my-3 flex flex-wrap items-center gap-3 rounded-md border border-subtle p-3"
          onSubmit={(e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            const adopting = (e.nativeEvent as SubmitEvent).submitter?.getAttribute("name") === "adopt";
            void action(async () => {
              try {
                await api.write(url + member.user_id + "/", "PATCH", csrf, {
                  expected_revision: member.revision,
                  access_override: form.get("access") === "default" ? null : Number(form.get("access")),
                  ...(adopting ? { adopt_existing: true, expected_direct_access: member.direct_access } : {}),
                });
              } finally {
                await mutate();
              }
            });
          }}
        >
          <div className="min-w-0 grow">
            <strong>{member.display_name}</strong>
            <p>
              {label(member.status)} · {t("repository_ui.effective_access")}: {member.effective_access ?? "—"}
            </p>
            {!member.external_user_id && <p>{t("repository_ui.identity_required")}</p>}
            {member.error_code && (
              <details>
                <summary>{t("common.status")}</summary>
                <code>{member.error_code}</code>
              </details>
            )}
          </div>
          <select
            name="access"
            className={field}
            aria-label={`${member.display_name} ${t("role")}`}
            defaultValue={member.access_override ?? "default"}
            disabled={busy}
          >
            <option value="default">
              {t("common.default")} ({member.default_access})
            </option>
            <option value="0">{t("remove")}</option>
            {([20, 30, 40] as const).map((level) => (
              <option key={level} value={level}>
                {{ 20: "Reporter", 30: "Developer", 40: "Maintainer" }[level]} ({level})
              </option>
            ))}
          </select>
          {member.direct_access !== null && ["unmanaged", "conflict"].includes(member.status) ? (
            <Button
              type="submit"
              name="adopt"
              label={t("repository_ui.adopt_existing")}
              size="md"
              variant="secondary"
              stretch="auto"
              disabled={busy}
            />
          ) : (
            <Button
              type="submit"
              label={t("repository_ui.save")}
              size="md"
              variant="secondary"
              stretch="auto"
              disabled={busy}
            />
          )}
        </form>
      ))}
    </details>
  );
}
