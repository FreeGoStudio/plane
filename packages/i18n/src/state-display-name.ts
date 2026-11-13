/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TTranslationStore } from "./hooks/use-translation";

const defaultNames: Record<string, string> = {
  backlog: "Backlog",
  unstarted: "Todo",
  started: "In Progress",
  completed: "Done",
  cancelled: "Cancelled",
};

/** Localize unchanged built-in names for Chinese UI without modifying persisted states. */
export function getStateDisplayName(
  state: { name: string; group: string },
  { t, currentLocale }: Pick<TTranslationStore, "t" | "currentLocale">
): string {
  if (
    (currentLocale !== "zh-CN" && currentLocale !== "zh-TW") ||
    !Object.hasOwn(defaultNames, state.group) ||
    defaultNames[state.group] !== state.name
  ) {
    return state.name;
  }
  return t(`workspace_projects.state.${state.group}`);
}
