// Copyright (c) 2023-present Plane Software, Inc. and contributors
// SPDX-License-Identifier: AGPL-3.0-only
// See the LICENSE file for details.

import { useTranslation } from "@plane/i18n";
import {
  actionOptions,
  needsChoice,
  type ChangeAction,
  type WbsChange,
  type WbsChild,
  type WbsTask,
} from "./wbs-update";

export function WbsChanges({
  changes,
  existingChildren,
  choices,
  disabled,
  onChoose,
  replacements = {},
  criteria = [],
  onReplacement,
}: {
  changes: WbsChange[];
  existingChildren: WbsChild[];
  choices: Record<string, ChangeAction>;
  disabled: boolean;
  onChoose: (id: string, action: ChangeAction) => void;
  replacements?: Record<string, WbsTask>;
  criteria?: string[];
  onReplacement?: (id: string, task: WbsTask) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3">
      {changes.every((change) => change.action === "keep") && <p>{t("wbs.no_changes")}</p>}
      {changes.map((change) => {
        const child = existingChildren.find((item) => item.id === change.target_id);
        const replacement = replacements[change.id] || {
          id: change.id,
          title: child?.name || "",
          role: "",
          criteria: [],
          scope: "",
          deliverable: "",
          acceptance: "",
          dependencies: [],
        };
        const before = child
          ? new DOMParser().parseFromString(child.description_html || "", "text/html").body.textContent
          : "";
        return (
          <article key={change.id} className="text-sm space-y-2 rounded-md border border-subtle p-3 break-words">
            <h4 className="font-medium">
              {change.id} · {change.task?.title || child?.name} · {t(`wbs.action_${change.action}`)}
            </h4>
            <p className="whitespace-pre-wrap">{change.basis}</p>
            <p className="whitespace-pre-wrap">{change.impact}</p>
            {child && (
              <details>
                <summary>
                  {t("wbs.before")} · {child.name}
                </summary>
                <p className="whitespace-pre-wrap">{before}</p>
              </details>
            )}
            {change.task && (
              <div className="space-y-1">
                <p className="font-medium">{t("wbs.after")}</p>
                <p>
                  {change.task.role} · {change.task.criteria.join(", ")}
                </p>
                <p className="whitespace-pre-wrap">{change.task.scope}</p>
                <p className="whitespace-pre-wrap">
                  {t("wbs.deliverable")}: {change.task.deliverable}
                </p>
                <p className="whitespace-pre-wrap">
                  {t("wbs.acceptance")}: {change.task.acceptance}
                </p>
                <p>
                  {t("wbs.dependencies")}: {change.task.dependencies.join(", ") || "—"}
                </p>
              </div>
            )}
            {needsChoice(change, child) && (
              <label className="flex flex-wrap items-center gap-2">
                {t("wbs.choose_action")}
                <select
                  aria-label={`${change.id} ${t("wbs.choose_action")}`}
                  disabled={disabled}
                  className="max-w-full rounded border border-subtle bg-surface-1 p-2"
                  value={choices[change.id] || ""}
                  onChange={(event) => onChoose(change.id, event.target.value as ChangeAction)}
                >
                  <option value="" disabled>
                    {t("wbs.choose_action")}
                  </option>
                  {actionOptions(change, child).map((action) => (
                    <option key={action} value={action}>
                      {t(`wbs.action_${action}`)}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {!change.task && ["update", "append"].includes(choices[change.id]) && (
              <fieldset className="space-y-2" disabled={disabled}>
                <legend>{t("wbs.after")}</legend>
                {(
                  [
                    ["title", "title"],
                    ["role", "role"],
                    ["scope", "description"],
                    ["deliverable", "wbs.deliverable"],
                    ["acceptance", "wbs.acceptance"],
                  ] as const
                ).map(([field, label]) => (
                  <label className="block" key={field}>
                    {t(label)}
                    <textarea
                      className="block w-full rounded border border-subtle bg-transparent p-2"
                      required
                      aria-label={`${change.id} ${t(label)}`}
                      value={replacement[field]}
                      onChange={(event) => onReplacement?.(change.id, { ...replacement, [field]: event.target.value })}
                    />
                  </label>
                ))}
                <label className="block">
                  {t("wbs.acceptance")} · AC
                  <select
                    multiple
                    aria-label={`${change.id} AC`}
                    className="block w-full rounded border border-subtle p-2"
                    value={replacement.criteria}
                    onChange={(event) =>
                      onReplacement?.(change.id, {
                        ...replacement,
                        criteria: Array.from(event.target.selectedOptions, (option) => option.value),
                      })
                    }
                  >
                    {(disabled ? replacement.criteria : criteria).map((id) => (
                      <option key={id} value={id}>
                        {id}
                      </option>
                    ))}
                  </select>
                </label>
              </fieldset>
            )}
          </article>
        );
      })}
    </div>
  );
}
