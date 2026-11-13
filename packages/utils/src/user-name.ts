/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/** Format separate name fields for display, without replacing a user's chosen display name. */
export function formatUserFullName(
  user: { first_name?: string | null; last_name?: string | null } | null | undefined,
  locale: string
): string {
  const isChinese = locale === "zh" || locale.startsWith("zh-");
  const parts = isChinese ? [user?.last_name, user?.first_name] : [user?.first_name, user?.last_name];
  return parts.filter(Boolean).join(isChinese ? "" : " ");
}
