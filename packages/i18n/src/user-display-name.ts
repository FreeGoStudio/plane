/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import { i18nInstance } from "./core/instance";

export type UserDisplayIdentity = {
  display_name?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  member__display_name?: string | null;
  member__first_name?: string | null;
  member__last_name?: string | null;
  member__email?: string | null;
};

/** Resolve a UI identity without changing profile fields or exposing data absent from the supplied record. */
export function getUserDisplayName(user: UserDisplayIdentity | null | undefined): string {
  if (!user) return "";
  const displayName = user.display_name?.trim() || user.member__display_name?.trim();
  if (displayName) return displayName;
  const firstName = user.first_name?.trim() || user.member__first_name?.trim();
  const lastName = user.last_name?.trim() || user.member__last_name?.trim();
  const locale = i18nInstance.language || "en";
  const chinese = locale === "zh" || locale.startsWith("zh-");
  const fullName = (chinese ? [lastName, firstName] : [firstName, lastName]).filter(Boolean).join(chinese ? "" : " ");
  return fullName || user.email?.trim() || user.member__email?.trim() || "";
}
