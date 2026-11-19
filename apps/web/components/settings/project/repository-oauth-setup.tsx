/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import { useState } from "react";
import { Button } from "@makeplane/propel/components/button";
import { Input, InputGroup } from "@makeplane/propel/components/input";
import { useTranslation } from "@plane/i18n";
import { repositoryService as api } from "@/services/repository.service";

type Guide = {
  instance_id: string | null;
  provider: string;
  web_url: string;
  api_url: string;
  create_url: string;
  homepage_url: string;
  callback_url: string;
  scope: string;
  client_id: string;
  configured: boolean;
};
const endpoint = "/api/singularity/v1/repository-oauth-setup/";
/** Administrator-only setup; opening provider registration never sends a client secret. */
export function RepositoryOAuthSetup({
  instanceId,
  repositoryUrl,
  csrf,
  busy,
  action,
  onConfigured,
}: {
  instanceId?: string | null;
  repositoryUrl: string;
  csrf: string;
  busy: boolean;
  action: (fn: () => Promise<void>) => Promise<void>;
  onConfigured: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [guide, setGuide] = useState<Guide | null>(null);
  const [site, setSite] = useState(() => new URL(repositoryUrl).origin);
  const [provider, setProvider] = useState("gitlab");
  const [apiUrl, setApiUrl] = useState("");
  const [networks, setNetworks] = useState("");
  const [clientId, setClientId] = useState("");
  const [secret, setSecret] = useState("");
  const [copied, setCopied] = useState("");
  const inspect = async () => {
    const params = new URLSearchParams(
      instanceId ? { instance_id: instanceId } : { web_url: site, provider, ...(apiUrl ? { api_url: apiUrl } : {}) }
    );
    const result = await api.read<Guide>(`${endpoint}?${params}`);
    setGuide(result);
    setClientId(result.client_id);
    setSecret("");
  };
  const copy = (value: string) =>
    void action(async () => {
      await navigator.clipboard.writeText(value);
      setCopied(value);
    });
  return (
    <div className="rounded-md border border-subtle p-4">
      <Button
        disabled={busy}
        label={t("repository_ui.oauth_setup.title")}
        size="md"
        variant="secondary"
        stretch="auto"
        onClick={() => {
          if (open) {
            setOpen(false);
            setSecret("");
            return;
          }
          setOpen(true);
          if (instanceId) void action(inspect);
        }}
      />
      {open && (
        <div className="mt-4 space-y-4">
          {!instanceId && !guide && (
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                void action(inspect);
              }}
            >
              <label className="block">
                {t("repository_ui.host")}
                <InputGroup size="xl">
                  <Input
                    size="xl"
                    type="url"
                    value={site}
                    required
                    disabled={busy}
                    onChange={(e) => setSite(e.target.value)}
                  />
                </InputGroup>
              </label>
              <select
                aria-label={t("repository_ui.host")}
                className="rounded-md border border-subtle bg-surface-1 px-3 py-2"
                value={provider}
                disabled={busy}
                onChange={(e) => setProvider(e.target.value)}
              >
                <option value="gitlab">GitLab</option>
                <option value="github">GitHub</option>
              </select>
              <label className="block" htmlFor="repository-oauth-api">
                API URL
                <InputGroup size="xl">
                  <Input
                    size="xl"
                    type="url"
                    id="repository-oauth-api"
                    value={apiUrl}
                    placeholder={site.replace(/\/$/, "") + (provider === "gitlab" ? "/api/v4" : "/api/v3")}
                    disabled={busy}
                    onChange={(e) => setApiUrl(e.target.value)}
                  />
                </InputGroup>
              </label>
              <Button
                type="submit"
                disabled={busy}
                label={t("repository_ui.continue_add")}
                size="md"
                variant="secondary"
                stretch="auto"
              />
            </form>
          )}
          {guide && (
            <>
              <a
                className="text-accent-primary underline"
                href={guide.create_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {t("repository_ui.oauth_setup.create")} · {guide.provider === "github" ? "GitHub" : "GitLab"}
              </a>
              <p className="text-body-sm-regular text-secondary">
                {t(`repository_ui.oauth_setup.${guide.provider}_steps`)}
              </p>
              {[
                ["Homepage URL", guide.homepage_url],
                ["Authorization callback URL / Redirect URI", guide.callback_url],
              ].map(([label, value]) => (
                <div key={label} className="space-y-2">
                  <p className="text-body-sm-regular">{label}</p>
                  <div className="flex items-center gap-2">
                    <InputGroup size="xl">
                      <Input size="xl" aria-label={label} value={value} readOnly />
                    </InputGroup>
                    <Button
                      label={t(copied === value ? "common.copied" : "common.tooltip.copy_to_clipboard")}
                      size="md"
                      variant="secondary"
                      stretch="auto"
                      onClick={() => copy(value)}
                    />
                  </div>
                </div>
              ))}
              <p className="text-body-sm-regular">
                OAuth scope: <code>{guide.scope}</code>
              </p>
              {guide.provider === "github" && (
                <p className="text-body-sm-regular text-secondary">{t("repository_ui.github_scope")}</p>
              )}
              <form
                className="space-y-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  void action(async () => {
                    await api.write(endpoint, "POST", csrf, {
                      ...(guide.instance_id
                        ? { instance_id: guide.instance_id }
                        : {
                            provider: guide.provider,
                            web_url: guide.web_url,
                            api_url: guide.api_url,
                            allowed_networks: networks.split(/[,\s]+/).filter(Boolean),
                          }),
                      client_id: clientId,
                      client_secret: secret,
                    });
                    setSecret("");
                    setOpen(false);
                    await onConfigured();
                  });
                }}
              >
                <label className="block" htmlFor="repository-oauth-client-id">
                  Client ID / Application ID
                  <InputGroup size="xl">
                    <Input
                      size="xl"
                      id="repository-oauth-client-id"
                      name="client_id"
                      value={clientId}
                      required
                      autoComplete="off"
                      disabled={busy}
                      onChange={(e) => setClientId(e.target.value)}
                    />
                  </InputGroup>
                </label>
                <label className="block" htmlFor="repository-oauth-secret">
                  Client Secret / Secret
                  <InputGroup size="xl">
                    <Input
                      size="xl"
                      id="repository-oauth-secret"
                      name="client_secret"
                      type="password"
                      value={secret}
                      required
                      autoComplete="new-password"
                      disabled={busy}
                      onChange={(e) => setSecret(e.target.value)}
                    />
                  </InputGroup>
                </label>
                {!guide.instance_id && (
                  <label className="block">
                    {t("repository_ui.oauth_setup.private_networks")}
                    <InputGroup size="xl">
                      <Input
                        size="xl"
                        value={networks}
                        placeholder="192.168.3.56/32, 10.0.0.0/24"
                        disabled={busy}
                        onChange={(e) => setNetworks(e.target.value)}
                      />
                    </InputGroup>
                  </label>
                )}
                <div className="flex gap-2">
                  <Button
                    type="submit"
                    disabled={busy}
                    label={t("repository_ui.save")}
                    size="md"
                    variant="primary"
                    stretch="auto"
                  />
                  {!guide.instance_id && (
                    <Button
                      disabled={busy}
                      label={t("repository_ui.cancel_edit")}
                      size="md"
                      variant="secondary"
                      stretch="auto"
                      onClick={() => {
                        setGuide(null);
                        setSecret("");
                      }}
                    />
                  )}
                </div>
              </form>
            </>
          )}
        </div>
      )}
    </div>
  );
}
