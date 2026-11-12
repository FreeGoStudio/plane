/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { formatDistanceToNow, isValid } from "date-fns";
import { zhCN, zhTW } from "date-fns/locale";
import type { THomeDateOrder } from "@plane/types";

export function formatHomeDate(date: Date, locale: string, timeZone: string, order: THomeDateOrder = "locale") {
  const weekday = new Intl.DateTimeFormat(locale, { weekday: "long", timeZone }).format(date);
  const time = new Intl.DateTimeFormat(locale, {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone,
  }).format(date);
  return `${formatPreferredDate(date, locale, timeZone, order)} ${weekday} ${time}`;
}

/** Shared date preference; date-only values retain their calendar day in every timezone. */
export function formatPreferredDate(
  value: Date | string | null | undefined,
  locale: string,
  timeZone?: string,
  order: THomeDateOrder = "locale"
) {
  if (!value) return "";
  const date = value instanceof Date ? value : new Date(value);
  if (!isValid(date)) return "";
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) timeZone = "UTC";
  let calendarDate: string;
  if (order === "locale") {
    calendarDate = new Intl.DateTimeFormat(locale, { year: "numeric", month: "long", day: "numeric", timeZone }).format(
      date
    );
  } else {
    const parts = new Intl.DateTimeFormat("en-US", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      timeZone,
    }).formatToParts(date);
    const part = (type: string) => parts.find((datePart) => datePart.type === type)?.value ?? "";
    const fields =
      order === "mdy"
        ? ["month", "day", "year"]
        : order === "dmy"
          ? ["day", "month", "year"]
          : ["year", "month", "day"];
    calendarDate = fields.map(part).join("/");
  }
  return calendarDate;
}

export function getHomeGreetingPeriod(date: Date, timeZone: string) {
  const hour = Number(new Intl.DateTimeFormat("en-US", { hour: "numeric", hourCycle: "h23", timeZone }).format(date));
  return hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
}

export function formatHomeTimeAgo(value: Date | string | null | undefined, locale: string) {
  if (!value) return "";
  const date = value instanceof Date ? value : new Date(value);
  if (!isValid(date)) return "";
  return formatDistanceToNow(date, {
    addSuffix: true,
    locale: locale === "zh-CN" ? zhCN : locale === "zh-TW" ? zhTW : undefined,
  });
}
