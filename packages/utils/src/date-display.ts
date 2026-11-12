/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { formatDistanceToNow, isValid } from "date-fns";
import { enUS, zhCN, zhTW } from "date-fns/locale";
import type { THomeDateOrder } from "@plane/types";

export type DateDisplayPreferences = { locale: string; order?: THomeDateOrder; timeZone?: string };
export type DisplayDateValue = Date | string | number | null | undefined;

/** Pure, per-user formatting. Never use display strings for API values, comparisons or grouping keys. */
export function createDateFormatter({ locale, order = "locale", timeZone }: DateDisplayPreferences) {
  locale = locale === "ua" ? "uk" : locale;
  const dateLocale = locale === "zh-CN" ? zhCN : locale === "zh-TW" ? zhTW : enUS;
  const parse = (value: DisplayDateValue) => {
    if (value === null || value === undefined || value === "") return undefined;
    const date = value instanceof Date ? value : new Date(value);
    return isValid(date) ? date : undefined;
  };
  const renderFormattedTime = (value: DisplayDateValue, timeFormat: "12-hour" | "24-hour" = "24-hour") => {
    const date = parse(value);
    if (!date) return "";
    return new Intl.DateTimeFormat(locale, {
      timeZone,
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: timeFormat === "12-hour" ? "h12" : "h23",
    }).format(date);
  };
  const renderFormattedDate = (value: DisplayDateValue, token?: string): string | undefined => {
    const date = parse(value);
    if (!date) return undefined;
    const zone = typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) ? "UTC" : timeZone;
    // Tokens specify the displayed fields, while preferences determine their order.
    const year = !token || /y/i.test(token);
    const month = !token || /M|L/.test(token);
    const day = !token || /d/.test(token);
    const weekday: Intl.DateTimeFormatOptions["weekday"] =
      token && /E|c/.test(token) ? (/E{4}|c{4}/.test(token) ? "long" : "short") : undefined;
    const hasTime = token && /H|h|m|s/.test(token);
    let result = "";
    if (year || month || day || weekday) {
      const options: Intl.DateTimeFormatOptions = {
        timeZone: zone,
        year: year ? "numeric" : undefined,
        month: month ? "long" : undefined,
        day: day ? "numeric" : undefined,
        weekday,
      };
      if (order === "locale") result = new Intl.DateTimeFormat(locale, options).format(date);
      else if (!year && !month && !day) {
        // With no date fields, Intl would otherwise insert its default full date.
        result = new Intl.DateTimeFormat(locale, { timeZone: zone, weekday }).format(date);
      } else {
        const parts = new Intl.DateTimeFormat("en-US", {
          ...options,
          weekday: undefined,
          month: month ? "2-digit" : undefined,
          day: day ? "2-digit" : undefined,
        }).formatToParts(date);
        const fields =
          order === "dmy"
            ? ["day", "month", "year"]
            : order === "mdy"
              ? ["month", "day", "year"]
              : ["year", "month", "day"];
        result = fields
          .map((field) => parts.find((part) => part.type === field)?.value)
          .filter(Boolean)
          .join("/");
        if (weekday) result += ` ${new Intl.DateTimeFormat(locale, { timeZone: zone, weekday }).format(date)}`;
      }
    }
    if (hasTime)
      result = [result, renderFormattedTime(date, /a/.test(token) ? "12-hour" : "24-hour")].filter(Boolean).join(" ");
    return result;
  };
  const renderFormattedDateWithoutYear = (value: DisplayDateValue) => renderFormattedDate(value, "MMM dd") ?? "";
  const formatDateRange = (from: DisplayDateValue, to: DisplayDateValue) =>
    [
      from instanceof Date ? formatCalendarDate(from) : renderFormattedDate(from),
      to instanceof Date ? formatCalendarDate(to) : renderFormattedDate(to),
    ]
      .filter(Boolean)
      .join(" – ");
  const calculateTimeAgo = (value: DisplayDateValue) => {
    const date = parse(value);
    return date ? formatDistanceToNow(date, { addSuffix: true, locale: dateLocale }) : "";
  };
  const calculateTimeAgoShort = (value: DisplayDateValue) => {
    const date = parse(value);
    if (!date) return "";
    if (locale.startsWith("zh")) return calculateTimeAgo(date);
    const seconds = (Date.now() - date.getTime()) / 1000;
    const units = [
      [60, 1, "s"],
      [3600, 60, "m"],
      [86400, 3600, "h"],
      [2592000, 86400, "d"],
      [31104000, 2592000, "mo"],
      [Infinity, 31104000, "y"],
    ] as const;
    const unit = units.find(([limit]) => seconds < limit)!;
    return `${Math.floor(seconds / unit[1])}${unit[2]}`;
  };
  // Calendar selections are civil dates, not instants in the account timezone.
  const formatCalendarDate = (value: Date | null | undefined, token?: string) =>
    value && isValid(value)
      ? (renderFormattedDate(
          `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`,
          token
        ) ?? "")
      : "";
  return {
    renderFormattedDate,
    renderFormattedDateWithoutYear,
    renderFormattedTime,
    formatDateRange,
    calculateTimeAgo,
    calculateTimeAgoShort,
    formatCalendarDate,
    dateLocale,
    locale,
    order,
    timeZone,
  };
}
export type DateFormatter = ReturnType<typeof createDateFormatter>;
