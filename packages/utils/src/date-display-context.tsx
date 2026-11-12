/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { createContext, useContext, useMemo } from "react";
import type { ReactNode } from "react";
import { createDateFormatter } from "./date-display";
import type { DateDisplayPreferences, DateFormatter } from "./date-display";

const DateDisplayContext = createContext<DateFormatter | null>(null);
const fallback = createDateFormatter({ locale: "en-US" });

export function DateDisplayProvider({
  children,
  locale,
  order,
  timeZone,
}: DateDisplayPreferences & { children: ReactNode }) {
  const formatter = useMemo(() => createDateFormatter({ locale, order, timeZone }), [locale, order, timeZone]);
  return <DateDisplayContext.Provider value={formatter}>{children}</DateDisplayContext.Provider>;
}
export const useDateDisplayContext = () => useContext(DateDisplayContext);
export const useDateFormatter = () => useDateDisplayContext() ?? fallback;

export function DateDisplay({
  value,
  formatToken,
}: {
  value: import("./date-display").DisplayDateValue;
  formatToken?: string;
}) {
  return useDateFormatter().renderFormattedDate(value, formatToken) ?? null;
}
