/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// local imports
import { useTranslation } from "@plane/i18n";
import { coreSidebarMenuLinks, type TCoreSidebarMenuKey } from "./core";
import type { TSidebarMenuItem } from "./types";

export function useSidebarMenu(): TSidebarMenuItem[] {
  const { t } = useTranslation();
  const keys: TCoreSidebarMenuKey[] = ["general", "email", "authentication", "workspace", "ai", "image"];
  return keys.map((key) => ({
    Icon: coreSidebarMenuLinks[key].Icon,
    href: coreSidebarMenuLinks[key].href,
    name: t(`admin_ui.nav.${key}`),
    description: t(`admin_ui.nav_description.${key}`),
  }));
}
