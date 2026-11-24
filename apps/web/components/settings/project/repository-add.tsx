/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import { useRef, useState } from "react";
import { isAxiosError } from "axios";
import { Button } from "@makeplane/propel/components/button";
import { Input, InputGroup } from "@makeplane/propel/components/input";
import { useTranslation } from "@plane/i18n";
import { repositoryService as api, type RepositoryRegistration } from "@/services/repository.service";

/** Project registration never reads or creates personal credentials. */
export function RepositoryAdd({
  base,
  csrf,
  section,
  busy,
  registrations = [],
  onAdded,
}: {
  base: string;
  csrf: string;
  section: string;
  busy: boolean;
  registrations?: RepositoryRegistration[];
  onAdded: (section: string) => void | Promise<void>;
}) {
  const { t } = useTranslation();
  const [url, setUrl] = useState("");
  const [pending, setPending] = useState(false);
  const submitting = useRef(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const [submittedId, setSubmittedId] = useState<string | null>(null);
  const currentRegistration = registrations.find((row) => row.id === submittedId);
  async function register(address: string) {
    if (submitting.current) return;
    submitting.current = true;
    setPending(true);
    setSubmittedId(null);
    setFailed(false);
    setMessage(t("submitting"));
    try {
      const result = await api.write<RepositoryRegistration>(base + "repository-add/", "POST", csrf, {
        url: address,
        purpose: section,
        method: "register",
      });
      setMessage(t(`repository_ui.registration.${result.status}`));
      setSubmittedId(result.id);
      setUrl("");
      try {
        await onAdded(result.purpose);
      } catch {
        setFailed(true);
        setMessage(`${t(`repository_ui.registration.${result.status}`)} · ${t("repository_ui.load_failed")}`);
      }
    } catch (error) {
      const code = isAxiosError(error) ? error.response?.data?.error : undefined;
      const key = `repository_ui.results.${code}`;
      const translated = code ? t(key) : "";
      setFailed(true);
      setMessage(translated && translated !== key ? translated : t("repository_ui.failed"));
    } finally {
      setPending(false);
      submitting.current = false;
    }
  }
  return (
    <section id="repository-add" className="mt-6 rounded-lg border border-subtle p-5">
      <h3 className="text-body-md-medium">{t("repository_ui.add")}</h3>
      <p className="mt-2 text-body-sm-regular text-secondary">{t("repository_ui.registration.hint")}</p>
      <form
        className="mt-4 flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          void register(url);
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
            disabled={busy || pending}
            placeholder="https://gitlab.com/group/repository"
            onChange={(event) => setUrl(event.target.value)}
          />
        </InputGroup>
        <Button
          type="submit"
          disabled={busy || pending}
          label={t(pending ? "submitting" : "repository_ui.add")}
          size="md"
          variant="primary"
          stretch="auto"
        />
      </form>
      {message && (
        <p className="mt-3 text-body-sm-regular" role={failed ? "alert" : "status"} aria-live="polite">
          {!failed && !pending && currentRegistration
            ? t(`repository_ui.registration.${currentRegistration.status}`)
            : message}
        </p>
      )}
      <div className="mt-4 space-y-3">
        {registrations
          .filter((row) => row.purpose === section)
          .map((row) => (
            <div key={row.id} className="rounded-md border border-subtle p-3">
              <p className="break-all">{row.path}</p>
              <p role="status">{t(`repository_ui.registration.${row.status}`)}</p>
              {row.error_code && (
                <p className="text-body-sm-regular text-secondary">
                  {t(
                    row.status === "waiting_access"
                      ? "repository_ui.registration.access_hint"
                      : "repository_ui.registration.sync_hint"
                  )}
                  {` (${row.error_code})`}
                </p>
              )}
              {row.repository_id && (
                <a className="text-accent-primary" href={`#${row.repository_id}`}>
                  {t("repository_ui.details")}
                </a>
              )}
              {["waiting_access", "sync_error"].includes(row.status) && (
                <Button
                  type="button"
                  disabled={busy || pending}
                  label={t("repository_ui.registration.retry")}
                  size="md"
                  variant="secondary"
                  stretch="auto"
                  onClick={() => void register(row.url)}
                />
              )}
            </div>
          ))}
      </div>
    </section>
  );
}
