/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import { useState, type ComponentProps } from "react";
import { useSearchParams } from "react-router";
import useSWR from "swr";
import { isAxiosError } from "axios";
import { Button as PropelButton } from "@makeplane/propel/components/button";
import { Input } from "@makeplane/propel/components/input";
import { useTranslation } from "@plane/i18n";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { SettingsHeading } from "@/components/settings/heading";
import {
  repositoryService as api,
  repositoryBase,
  type Repository,
  type ConnectionInfo,
  type RepositoryContent,
} from "@/services/repository.service";

function Button({
  children,
  ...props
}: Omit<ComponentProps<typeof PropelButton>, "label" | "size" | "variant" | "stretch"> & {
  children: string | string[];
}) {
  return (
    <PropelButton
      {...props}
      size="md"
      variant="secondary"
      stretch="auto"
      label={Array.isArray(children) ? children.join("") : children}
    />
  );
}

const field = "rounded-md border border-subtle bg-surface-1 px-3 py-2 text-sm text-primary";
export function ProjectRepositoriesSettings({
  workspaceSlug,
  projectId,
}: {
  workspaceSlug: string;
  projectId: string;
}) {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const base = repositoryBase(workspaceSlug, projectId);
  const {
    data: rows,
    error,
    mutate,
  } = useSWR<Repository[]>(base + "repositories/", (url: string) => api.read<Repository[]>(url));
  const { data: info, mutate: refreshInfo } = useSWR<ConnectionInfo>(base + "repository-connections/", (url: string) =>
    api.read<ConnectionInfo>(url)
  );
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [preview, setPreview] = useState<{ repository: Repository; value: RepositoryContent } | null>(null);
  const text = (key: string) => t(`repository_ui.${key}`);
  const feedback = (code: string) => {
    const key = `repository_ui.results.${code}`;
    const translated = t(key);
    return translated === key ? text("failed") : translated;
  };
  async function action(fn: () => Promise<void>) {
    setBusy(true);
    setStatus("");
    try {
      await fn();
    } catch (e) {
      setStatus(feedback(isAxiosError(e) ? (e.response?.data?.error ?? "failed") : "failed"));
    } finally {
      setBusy(false);
    }
  }
  async function write(path: string, data?: unknown, method: "POST" | "DELETE" | "PATCH" = "POST") {
    if (!info) return;
    await api.write(base + path, method, info.csrf_token, data);
    await Promise.all([mutate(), refreshInfo()]);
    setStatus(text("saved"));
  }
  async function browse(
    repository: Repository,
    path = "",
    operation = "tree",
    ref = repository.default_branch,
    page = 1
  ) {
    const query = new URLSearchParams({ path, ref, page: String(page) });
    const value = await api.read<RepositoryContent>(base + `repositories/${repository.id}/${operation}/?${query}`);
    setPreview({ repository, value });
  }
  const result = status || (params.get("connection") ? feedback(params.get("connection")!) : "");
  return (
    <SettingsContentWrapper>
      <SettingsHeading title={text("title")} description={text("description")} />
      <p className="text-sm my-4 text-secondary" role="status" aria-live="polite">
        {result}
      </p>
      {error ? (
        <p role="alert">{text("load_failed")}</p>
      ) : !rows || !info ? (
        <p>{text("loading")}</p>
      ) : (
        <>
          {!rows.length && <p className="py-6 text-secondary">{text("empty")}</p>}
          <div className="space-y-5">
            {rows.map((row) => {
              const credential = info.credentials.find((c) => c.id === row.credential_id);
              const host = info.hosts.find((h) => h.id === row.instance_id);
              return (
                <section
                  key={row.id}
                  id={row.id}
                  className={`rounded-lg border p-5 ${params.get("repository") === row.id ? "border-accent-strong" : "border-subtle"}`}
                >
                  <h4 className="font-medium text-primary">
                    {row.instance_name} / {row.path}
                  </h4>
                  <p className="text-sm my-2 text-secondary">
                    {row.enabled
                      ? credential
                        ? `${text("account")}: ${credential.external_actor_label || credential.label}${credential.expires_at ? ` · ${text("expires")}: ${new Date(credential.expires_at).toLocaleString()}` : ""}`
                        : row.anonymous
                          ? text("anonymous")
                          : text("not_connected")
                      : text("disabled")}
                  </p>
                  {row.enabled && (
                    <>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          disabled={busy || !host?.oauth_available}
                          onClick={() =>
                            void action(async () => {
                              const authorization = await api.write<{ authorization_url: string }>(
                                base + `repositories/${row.id}/connection/`,
                                "POST",
                                info.csrf_token,
                                { method: "oauth" }
                              );
                              window.location.assign(authorization.authorization_url);
                            })
                          }
                        >
                          {text("connect")} {row.provider === "github" ? "GitHub" : "GitLab"}
                        </Button>
                        <Button disabled={busy} onClick={() => void action(() => browse(row))}>
                          {text("browse")}
                        </Button>
                        {(row.credential_id || row.anonymous) && (
                          <Button
                            disabled={busy}
                            onClick={() =>
                              void action(() => write(`repositories/${row.id}/connection/`, undefined, "DELETE"))
                            }
                          >
                            {text("disconnect")}
                          </Button>
                        )}
                      </div>
                      <p className="text-xs my-2 text-tertiary">
                        {host?.oauth_available
                          ? text(row.provider === "github" ? "github_scope" : "scope")
                          : text("oauth_unavailable")}
                      </p>
                      <details className="text-sm mt-4">
                        <summary className="cursor-pointer">{text("manual")}</summary>
                        <form
                          className="my-3 flex flex-wrap gap-2"
                          onSubmit={(e) => {
                            e.preventDefault();
                            const form = e.currentTarget;
                            const data = new FormData(form);
                            void action(() =>
                              write(
                                `repositories/${row.id}/access/`,
                                data.get("credential") === "anonymous"
                                  ? { anonymous: true }
                                  : { credential_id: data.get("credential") }
                              )
                            );
                          }}
                        >
                          <select
                            className={field}
                            name="credential"
                            required
                            aria-label={text("choose")}
                            defaultValue={row.anonymous ? "anonymous" : row.credential_id || ""}
                          >
                            <option value="" disabled>
                              {text("choose")}
                            </option>
                            {info.credentials
                              .filter(
                                (c) =>
                                  c.instance_id === row.instance_id &&
                                  (!c.expires_at || Date.parse(c.expires_at) > Date.now())
                              )
                              .map((c) => (
                                <option value={c.id} key={c.id}>
                                  {c.label} · {c.external_actor_label}
                                </option>
                              ))}
                            <option value="anonymous">{text("anonymous")}</option>
                          </select>
                          <Button type="submit" disabled={busy}>
                            {text("use_connection")}
                          </Button>
                        </form>
                        <form
                          className="flex flex-wrap gap-2"
                          onSubmit={(e) => {
                            e.preventDefault();
                            const form = e.currentTarget;
                            const data = new FormData(form);
                            const token = String(data.get("token"));
                            form.reset();
                            void action(() => write(`repositories/${row.id}/connection/`, { label: row.path, token }));
                          }}
                        >
                          <Input
                            size="md"
                            name="token"
                            type="password"
                            required
                            autoComplete="new-password"
                            placeholder={text("token_placeholder")}
                            aria-label={text("token_placeholder")}
                          />
                          <Button type="submit" disabled={busy}>
                            {text("verify_save")}
                          </Button>
                        </form>
                      </details>
                    </>
                  )}
                  {info.can_manage && (
                    <details className="text-sm mt-4">
                      <summary className="cursor-pointer">{text("manage")}</summary>
                      <form
                        className="my-3 flex flex-wrap gap-2"
                        onSubmit={(e) => {
                          e.preventDefault();
                          const data = new FormData(e.currentTarget);
                          void action(() =>
                            write(
                              `repositories/${row.id}/`,
                              { default_branch: data.get("branch"), purpose: data.get("purpose") },
                              "PATCH"
                            )
                          );
                        }}
                      >
                        <Input size="md" name="branch" defaultValue={row.default_branch} aria-label={text("branch")} />
                        <select
                          className={field}
                          name="purpose"
                          defaultValue={row.purpose}
                          aria-label={text("purpose")}
                        >
                          {["development", "reference", "documentation"].map((p) => (
                            <option key={p} value={p}>
                              {text(p)}
                            </option>
                          ))}
                        </select>
                        <Button type="submit" disabled={busy}>
                          {text("save")}
                        </Button>
                        <Button
                          disabled={busy}
                          onClick={() =>
                            void action(() => write(`repositories/${row.id}/`, { enabled: !row.enabled }, "PATCH"))
                          }
                        >
                          {text(row.enabled ? "disable" : "enable")}
                        </Button>
                      </form>
                    </details>
                  )}
                </section>
              );
            })}
          </div>
          {info.can_manage && (
            <details className="mt-6 rounded-lg border border-subtle p-5">
              <summary className="cursor-pointer">{text("add")}</summary>
              <form
                className="mt-4 flex flex-col gap-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  const data = new FormData(e.currentTarget);
                  void action(() =>
                    write("repositories/", {
                      instance_id: data.get("host"),
                      path: data.get("path"),
                      purpose: data.get("purpose"),
                      ...(data.get("credential") === "anonymous"
                        ? { anonymous: true }
                        : { credential_id: data.get("credential") }),
                    })
                  );
                }}
              >
                <select className={field} name="host" aria-label={text("host")}>
                  {info.hosts.map((h) => (
                    <option key={h.id} value={h.id}>
                      {h.name}
                    </option>
                  ))}
                </select>
                <Input size="md" name="path" required placeholder={text("path")} aria-label={text("path")} />
                <select className={field} name="purpose" aria-label={text("purpose")}>
                  {["development", "reference", "documentation"].map((p) => (
                    <option key={p} value={p}>
                      {text(p)}
                    </option>
                  ))}
                </select>
                <select className={field} name="credential" required aria-label={text("choose")}>
                  <option value="anonymous">{text("anonymous")}</option>
                  {info.credentials.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.label}
                    </option>
                  ))}
                </select>
                <Button type="submit" disabled={busy}>
                  {text("add")}
                </Button>
              </form>
            </details>
          )}
        </>
      )}
      {preview && (
        <section className="mt-6 rounded-lg border border-subtle p-5">
          <h4 className="font-medium">
            {preview.repository.path} / {preview.value.path}
          </h4>
          <p className="text-xs my-2 break-all text-tertiary">{preview.value.commit_sha}</p>
          <a className="text-accent-primary" href={preview.value.source_url} target="_blank" rel="noopener noreferrer">
            {text("source")}
          </a>
          <form
            className="my-3 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              const data = new FormData(e.currentTarget);
              void action(() => browse(preview.repository, "", "tree", String(data.get("ref"))));
            }}
          >
            <Input size="md" name="ref" defaultValue={preview.value.commit_sha} aria-label={text("branch")} />
            <Button type="submit" disabled={busy}>
              {text("browse")}
            </Button>
          </form>
          <Button
            disabled={busy}
            onClick={() => void action(() => browse(preview.repository, "", "tree", preview.value.commit_sha))}
          >
            {text("root")}
          </Button>
          <div className="my-3 flex flex-col items-start gap-1">
            {preview.value.entries?.map((entry) => (
              <Button
                key={entry.path}
                disabled={busy || !["tree", "blob"].includes(entry.type)}
                onClick={() =>
                  void action(() =>
                    browse(
                      preview.repository,
                      entry.path,
                      entry.type === "tree" ? "tree" : "file",
                      preview.value.commit_sha
                    )
                  )
                }
              >
                {entry.type === "tree" ? "▸ " : ""}
                {entry.name}
              </Button>
            ))}
          </div>
          {preview.value.next_page && (
            <Button
              disabled={busy}
              onClick={() =>
                void action(() =>
                  browse(
                    preview.repository,
                    preview.value.path,
                    "tree",
                    preview.value.commit_sha,
                    preview.value.next_page!
                  )
                )
              }
            >
              {text("next")}
            </Button>
          )}
          {preview.value.content !== undefined && (
            <pre className="text-sm mt-4 max-h-96 overflow-auto rounded bg-surface-2 p-4 break-words whitespace-pre-wrap">
              {preview.value.content}
            </pre>
          )}
        </section>
      )}
    </SettingsContentWrapper>
  );
}
