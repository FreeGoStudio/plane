/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import { RepositoryOAuthSetup } from "./repository-oauth-setup";
import { useState } from "react";
import { Button } from "@makeplane/propel/components/button";
import { Input, InputGroup } from "@makeplane/propel/components/input";
import { useTranslation } from "@plane/i18n";
import { repositoryService as api } from "@/services/repository.service";

type Host = {
  instance_id?: string | null;
  unregistered?: boolean;
  name: string;
  provider: string;
  path: string;
  oauth_available: boolean;
  credentials: { id: string; label: string }[];
};
/** Resolve a URL, then verify consent or an existing credential before registration. */
export function RepositoryAdd({
  base,
  csrf,
  section,
  busy,
  action,
  onAdded,
  canConfigureOAuth = false,
}: {
  base: string;
  csrf: string;
  canConfigureOAuth?: boolean;
  section: string;
  busy: boolean;
  action: (fn: () => Promise<void>) => Promise<void>;
  onAdded: (section: string) => void | Promise<void>;
}) {
  const { t } = useTranslation();
  const [url, setUrl] = useState("");
  const [host, setHost] = useState<Host | null>(null);
  const [credential, setCredential] = useState("");
  const [token, setToken] = useState("");
  const inspect = async () => {
    const result = await api.write<Host>(base + "repository-add/", "POST", csrf, {
      url,
      purpose: section,
      method: "inspect",
    });
    setHost(result);
    setCredential(result.credentials[0]?.id || "");
  };
  const add = (method: string) =>
    void action(async () => {
      const result = await api.write<{ authorization_url?: string; purpose: string }>(
        base + "repository-add/",
        "POST",
        csrf,
        {
          url,
          purpose: section,
          method,
          ...(method === "existing" ? { credential_id: credential } : {}),
          ...(method === "token" ? { token } : {}),
        }
      );
      if (result.authorization_url) {
        window.location.assign(result.authorization_url);
        return;
      }
      setToken("");
      setUrl("");
      setHost(null);
      await onAdded(result.purpose);
    });
  return (
    <section className="mt-6 rounded-lg border border-subtle p-5">
      <h3 className="text-body-md-medium">{t("repository_ui.add")}</h3>
      <form
        className="mt-4 flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          void action(inspect);
        }}
      >
        <label htmlFor="repository-url">{t("repository_ui.repository_url")}</label>
        <InputGroup size="xl">
          <Input
            id="repository-url"
            name="url"
            type="url"
            required
            size="md"
            value={url}
            disabled={busy}
            placeholder="https://gitlab.com/group/repository"
            onChange={(e) => {
              setUrl(e.target.value);
              setHost(null);
              setToken("");
            }}
          />
        </InputGroup>
        <Button
          type="submit"
          disabled={busy}
          label={t("repository_ui.continue_add")}
          size="md"
          variant="secondary"
          stretch="auto"
        />
      </form>
      {host && (
        <div className="mt-4 space-y-3">
          <p className="break-all">
            {host.name} · {host.path}
          </p>
          {!!host.credentials.length && (
            <div className="flex flex-wrap gap-3">
              <select
                aria-label={t("repository_ui.choose")}
                className="rounded-md border border-subtle bg-surface-1 px-3 py-2"
                value={credential}
                disabled={busy}
                onChange={(e) => setCredential(e.target.value)}
              >
                {host.credentials.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
              <Button
                disabled={busy}
                onClick={() => add("existing")}
                label={t("repository_ui.add")}
                size="md"
                variant="secondary"
                stretch="auto"
              />
            </div>
          )}
          {host.oauth_available ? (
            <>
              <p className="text-body-sm-regular text-secondary">{t("repository_ui.scope")}</p>
              <Button
                disabled={busy}
                onClick={() => add("oauth")}
                label={`${t("repository_ui.connect")} GitLab`}
                size="md"
                variant="primary"
                stretch="auto"
              />
            </>
          ) : (
            <p className="text-body-sm-regular text-secondary">{t("repository_ui.oauth_unavailable")}</p>
          )}
          {canConfigureOAuth && (
            <RepositoryOAuthSetup
              key={host.instance_id || url}
              instanceId={host.instance_id}
              repositoryUrl={url}
              csrf={csrf}
              busy={busy}
              action={action}
              onConfigured={inspect}
            />
          )}
          {!host.unregistered && (
            <details>
              <summary className="cursor-pointer">{t("repository_ui.connection_options")}</summary>
              <div className="mt-3 space-y-3">
                <Button
                  disabled={busy}
                  onClick={() => add("anonymous")}
                  label={t("repository_ui.anonymous")}
                  size="md"
                  variant="secondary"
                  stretch="auto"
                />
                <form
                  className="flex flex-col gap-3"
                  onSubmit={(e) => {
                    e.preventDefault();
                    add("token");
                  }}
                >
                  <InputGroup size="xl">
                    <Input
                      name="token"
                      type="password"
                      autoComplete="off"
                      required
                      size="md"
                      aria-label={t("repository_ui.token_placeholder")}
                      placeholder={t("repository_ui.token_placeholder")}
                      value={token}
                      disabled={busy}
                      onChange={(e) => setToken(e.target.value)}
                    />
                  </InputGroup>
                  <Button
                    type="submit"
                    disabled={busy}
                    label={t("repository_ui.verify_save")}
                    size="md"
                    variant="secondary"
                    stretch="auto"
                  />
                </form>
              </div>
            </details>
          )}
        </div>
      )}
    </section>
  );
}
