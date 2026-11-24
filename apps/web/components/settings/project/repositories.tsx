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
import { repositorySection, selectedRepositorySection, type RepositoryBindings } from "./repository-sections";
import { RepositoryAdd } from "./repository-add";
import { RepositoryInitialization, RepositoryMemberPermissions } from "./repository-management";
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

const field = "rounded-md border border-subtle bg-surface-1 px-3 py-2 text-body-sm-regular text-primary";
type BindingRole = "documentation" | "prototype";
const bindingRoles: BindingRole[] = ["documentation", "prototype"];

/** Keeps bindings read-only until an administrator explicitly chooses to edit a single role. */
function RepositoryBindingEditor({
  role,
  bindings,
  rows,
  busy,
  action,
  save,
}: {
  role: BindingRole;
  bindings: RepositoryBindings;
  rows: Repository[];
  busy: boolean;
  action: (fn: () => Promise<void>) => Promise<void>;
  save: (role: BindingRole, repositoryId: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const current = bindings[`${role}_repository_id`] || "";
  const [selected, setSelected] = useState(current);
  if (!editing)
    return (
      <Button
        disabled={busy}
        onClick={() => {
          setSelected(current);
          setEditing(true);
        }}
      >
        {t(current ? "repository_ui.change_binding" : "repository_ui.select_binding")}
      </Button>
    );
  return (
    <form
      className="mt-3 w-full rounded-md bg-surface-2 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        void action(async () => {
          await save(role, selected);
          setEditing(false);
        });
      }}
    >
      <label className="flex min-w-0 flex-col gap-2 text-body-sm-regular">
        {t(`repository_ui.${role}`)}
        <select
          name={role}
          className={`${field} w-full min-w-0`}
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          disabled={busy}
          required
        >
          <option value="" disabled>
            {t("repository_ui.unbound")}
          </option>
          {rows
            .filter((row) => row.purpose === role)
            .map((row) => (
              <option key={row.id} value={row.id} disabled={!row.enabled}>
                {row.instance_name} / {row.path}
                {!row.enabled ? ` (${t("repository_ui.disabled")})` : ""}
              </option>
            ))}
        </select>
      </label>
      <p className="my-3 text-body-xs-regular text-tertiary">{t("repository_ui.migration_hint")}</p>
      <div className="flex justify-end gap-2">
        <Button disabled={busy} onClick={() => setEditing(false)}>
          {t("repository_ui.cancel_edit")}
        </Button>
        <Button type="submit" disabled={busy || !selected || selected === current}>
          {t("repository_ui.save")}
        </Button>
      </div>
    </form>
  );
}

/** Renders repository configuration and refreshes bindings when background initialization completes. */
export function ProjectRepositoriesSettings({
  workspaceSlug,
  projectId,
}: {
  workspaceSlug: string;
  projectId: string;
}) {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const base = repositoryBase(workspaceSlug, projectId);
  const {
    data: rows,
    error,
    mutate,
  } = useSWR<Repository[]>(base + "repositories/", (url: string) => api.read<Repository[]>(url));
  const { data: info, mutate: refreshInfo } = useSWR<ConnectionInfo>(base + "repository-connections/", (url: string) =>
    api.read<ConnectionInfo>(url)
  );
  const {
    data: bindings,
    error: bindingError,
    mutate: refreshBindings,
  } = useSWR<RepositoryBindings>(base + "repository-bindings/", (url: string) => api.read<RepositoryBindings>(url));
  const section = selectedRepositorySection(params, rows, bindings);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [preview, setPreview] = useState<{ repository: Repository; value: RepositoryContent } | null>(null);
  const text = (key: string) => t(`repository_ui.${key}`);
  const feedback = (code: string) => {
    if (
      [
        "repository_binding_revision_conflict",
        "invalid_repository_binding",
        "bound_repository_purpose_locked",
      ].includes(code)
    )
      return text("results.configuration_conflict");
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
    await Promise.all([mutate(), refreshInfo(), refreshBindings()]);
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
  /** Updates one binding with its observed revision and preserves the other dedicated role. */
  function bindingEditor(role: BindingRole) {
    if (!bindings || !rows) return null;
    return (
      <RepositoryBindingEditor
        key={`${role}:${bindings.revision}`}
        role={role}
        bindings={bindings}
        rows={rows}
        busy={busy}
        action={action}
        save={async (targetRole, repositoryId) => {
          try {
            await write(
              "repository-bindings/",
              { expected_revision: bindings.revision, [`${targetRole}_repository_id`]: repositoryId },
              "PATCH"
            );
            setStatus(text("binding_saved"));
          } finally {
            await refreshBindings();
          }
        }}
      />
    );
  }
  const orderedRows = [
    ...bindingRoles.flatMap((role) => rows?.filter((row) => row.id === bindings?.[`${role}_repository_id`]) ?? []),
    ...(rows?.filter((row) => !bindingRoles.some((role) => row.id === bindings?.[`${role}_repository_id`])) ?? []),
  ].filter((row) => repositorySection(row, bindings) === section);
  const result = status || (params.get("connection") ? feedback(params.get("connection")!) : "");
  return (
    <SettingsContentWrapper>
      <SettingsHeading title={text(`sections.${section}`)} description={text("description")} />
      {info && (
        <RepositoryInitialization
          base={base}
          canManage={info.can_manage}
          busy={busy}
          allBound={bindingRoles.every((role) =>
            rows?.some((row) => row.enabled && row.id === bindings?.[`${role}_repository_id`])
          )}
          write={async () => {
            setStatus("");
            return api.write<{ status: string }>(base + "repository-management/", "POST", info.csrf_token, {});
          }}
          onReady={() => {
            void mutate();
            void refreshBindings();
          }}
        />
      )}
      {bindingError && <p role="alert">{text("load_failed")}</p>}
      {result && (
        <p className="my-4 text-body-sm-regular text-secondary" role="status" aria-live="polite">
          {result}
        </p>
      )}
      {error ? (
        <p role="alert">{text("load_failed")}</p>
      ) : !rows || !info ? (
        <p>{text("loading")}</p>
      ) : (
        <>
          <div
            className={`mt-5 ${bindingRoles.includes(section as BindingRole) ? "space-y-4" : "overflow-hidden rounded-lg border border-subtle"}`}
          >
            {bindings &&
              bindingRoles
                .filter((role) => role === section && !rows.some((row) => row.id === bindings[`${role}_repository_id`]))
                .map((role) => (
                  <section key={role} className="rounded-lg border border-subtle p-5">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <h3 className="text-h6-medium text-primary">{text(role)}</h3>
                      <span className="rounded bg-surface-2 px-2 py-1 text-body-xs-regular text-secondary">
                        {text("unbound")}
                      </span>
                    </div>
                    <p className="my-3 text-body-sm-regular text-secondary">{text("binding_hint")}</p>
                    {info.can_manage && bindingEditor(role)}
                  </section>
                ))}
            {orderedRows.length === 0 && !bindingRoles.includes(section as BindingRole) && (
              <p className="rounded-lg border border-dashed border-subtle p-6 text-body-sm-regular text-secondary">
                {text("empty")}
              </p>
            )}
            {orderedRows.map((row) => {
              const boundRole = bindingRoles.find((role) => bindings?.[`${role}_repository_id`] === row.id);
              const credential = info.credentials.find((c) => c.id === row.credential_id);
              const host = info.hosts.find((h) => h.id === row.instance_id);
              const access = credential
                ? text(
                    credential.expires_at && Date.parse(credential.expires_at) <= Date.now() ? "expired" : "connected"
                  )
                : text(row.anonymous ? "anonymous" : "personal_not_connected");
              const isExpanded = expanded === row.id;
              return (
                <section
                  key={row.id}
                  id={row.id}
                  className={`${bindingRoles.includes(section as BindingRole) ? "rounded-lg border p-5" : "border-b px-4 py-3 last:border-b-0"} ${params.get("repository") === row.id ? "border-accent-strong bg-surface-2" : "border-subtle"}`}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <h3 className="truncate text-h6-medium text-primary" title={row.path}>
                        {boundRole ? text(`sections.${boundRole}`) : row.path.split("/").pop()}
                      </h3>
                      {boundRole && <p className="mt-1 text-body-xs-regular text-tertiary">{row.instance_name}</p>}
                      <p className="mt-1 truncate text-body-sm-regular text-secondary" title={row.path}>
                        {row.path}
                      </p>
                    </div>
                    <span className="shrink-0 rounded bg-surface-2 px-2 py-1 text-body-xs-regular text-secondary">
                      {text(
                        !row.enabled ? "disabled" : boundRole ? "bound" : `sections.${repositorySection(row, bindings)}`
                      )}
                    </span>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                    <p className="text-body-xs-regular text-secondary">
                      {text("personal_access")} · {access}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {row.enabled && (
                        <Button disabled={busy} onClick={() => void action(() => browse(row))}>
                          {text("browse")}
                        </Button>
                      )}
                      <Button
                        aria-expanded={isExpanded}
                        aria-controls={`repository-details-${row.id}`}
                        onClick={() => setExpanded(isExpanded ? null : row.id)}
                      >
                        {text("details")}
                      </Button>
                    </div>
                  </div>
                  <div id={`repository-details-${row.id}`} hidden={!isExpanded}>
                    <p className="mt-4 text-body-sm-regular break-all text-secondary">
                      {row.instance_name} / {row.path}
                    </p>
                    <div className="mt-4 border-t border-subtle pt-4">
                      <p className="text-body-xs-regular font-medium text-tertiary">{text("personal_access")}</p>
                      <p className="mt-1 text-body-sm-regular break-words text-secondary">
                        {credential
                          ? `${text("account")}: ${credential.external_actor_label || credential.label}${credential.expires_at ? ` · ${text("expires")}: ${new Date(credential.expires_at).toLocaleString()}` : ""}`
                          : row.anonymous
                            ? text("anonymous")
                            : text("personal_not_connected")}
                      </p>
                    </div>
                    {row.enabled && (
                      <>
                        <div className="mt-3 flex flex-wrap gap-2">
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
                            {text("connect")} GitLab
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
                        <details className="mt-4 text-body-sm-regular">
                          <summary className="cursor-pointer text-secondary">{text("connection_options")}</summary>
                          <p className="my-3 text-body-xs-regular text-tertiary">
                            {host?.oauth_available ? text("scope") : text("oauth_unavailable")}
                          </p>
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
                                .filter(
                                  (c, index, choices) =>
                                    c.kind !== "oauth" ||
                                    !c.external_actor_id ||
                                    choices.findIndex(
                                      (other) =>
                                        other.kind === "oauth" && other.external_actor_id === c.external_actor_id
                                    ) === index
                                )
                                .map((c) => (
                                  <option value={c.id} key={c.id}>
                                    {c.label}
                                    {c.kind && c.kind !== "oauth" ? ` · Token ${c.id.slice(0, 8)}` : ""}
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
                              void action(() =>
                                write(`repositories/${row.id}/connection/`, { label: row.path, token })
                              );
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
                      <details className="mt-4 border-t border-subtle pt-3 text-body-sm-regular">
                        <summary className="cursor-pointer">{text("manage")}</summary>
                        {boundRole && <div className="mt-3">{bindingEditor(boundRole)}</div>}
                        <form
                          className="my-3 flex flex-wrap gap-2"
                          onSubmit={(e) => {
                            e.preventDefault();
                            const data = new FormData(e.currentTarget);
                            void action(() =>
                              write(
                                `repositories/${row.id}/`,
                                {
                                  default_branch: data.get("branch"),
                                  purpose: data.get("purpose"),
                                  path: data.get("path"),
                                },
                                "PATCH"
                              )
                            );
                          }}
                        >
                          <Input
                            size="md"
                            name="branch"
                            defaultValue={row.default_branch}
                            aria-label={text("branch")}
                          />
                          <Input size="md" name="path" defaultValue={row.path} aria-label={text("path")} required />
                          <select
                            className={field}
                            name="purpose"
                            defaultValue={row.purpose}
                            aria-label={text("purpose")}
                          >
                            {["development", "reference", "documentation", "prototype"].map((p) => (
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
                        {row.purpose !== "reference" && (
                          <RepositoryMemberPermissions
                            base={base}
                            repositoryId={row.id}
                            csrf={info.csrf_token}
                            busy={busy}
                            action={action}
                          />
                        )}
                      </details>
                    )}
                  </div>
                </section>
              );
            })}
          </div>
          {info.can_manage && (
            <RepositoryAdd
              key={section}
              base={base}
              csrf={info.csrf_token}
              canConfigureOAuth={info.can_configure_oauth}
              section={section}
              busy={busy}
              action={action}
              onAdded={async (purpose) => {
                await Promise.all([mutate(), refreshInfo(), refreshBindings()]);
                setParams({ section: purpose });
              }}
            />
          )}
        </>
      )}
      {preview && repositorySection(preview.repository, bindings) === section && (
        <section className="mt-6 rounded-lg border border-subtle p-5">
          <h4 className="font-medium">
            {preview.repository.path} / {preview.value.path}
          </h4>
          <p className="my-2 text-body-xs-regular break-all text-tertiary">{preview.value.commit_sha}</p>
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
            <pre className="mt-4 max-h-96 overflow-auto rounded bg-surface-2 p-4 text-body-sm-regular break-words whitespace-pre-wrap">
              {preview.value.content}
            </pre>
          )}
        </section>
      )}
    </SettingsContentWrapper>
  );
}
