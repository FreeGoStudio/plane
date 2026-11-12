/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createDateFormatter, DateDisplayProvider, useDateFormatter, renderFormattedPayloadDate } from "@plane/utils";
import { DateSelect } from "./date-select";
import { DateRangeSelect } from "./date-range-select";

const instant = "2026-11-12T08:08:00Z";
function DateText() {
  const formatter = useDateFormatter();
  return (
    <span>
      {formatter.renderFormattedDate(instant)} {formatter.renderFormattedTime(instant)}
    </span>
  );
}

describe("shared date display", () => {
  it("formats every date order, localized partial dates, ranges and timestamp time", () => {
    for (const [order, expected] of [
      ["locale", "2026年11月12日"],
      ["ymd", "2026/11/12"],
      ["mdy", "11/12/2026"],
      ["dmy", "12/11/2026"],
    ] as const) {
      const formatter = createDateFormatter({ locale: "zh-CN", order, timeZone: "Asia/Shanghai" });
      expect(formatter.renderFormattedDate(instant)).toBe(expected);
      expect(formatter.renderFormattedDate(instant, "MMM d, yyyy HH:mm")).toBe(`${expected} 16:08`);
      expect(formatter.formatDateRange(instant, instant)).toBe(`${expected} – ${expected}`);
    }
    const formatter = createDateFormatter({ locale: "zh-CN", timeZone: "Asia/Shanghai" });
    expect(formatter.renderFormattedDate(instant, "MMMM yyyy")).toBe("2026年11月");
    expect(formatter.renderFormattedDate(instant, "EEEE")).toBe("星期四");
    expect(formatter.renderFormattedDateWithoutYear(instant)).toBe("11月12日");
    expect(formatter.calculateTimeAgo(new Date(Date.now() - 3600000))).toBe("大约 1 小时前");
    expect(formatter.renderFormattedDate(null)).toBeUndefined();
    expect(formatter.renderFormattedDate("invalid")).toBeUndefined();
  });
  it("keeps civil dates and API payloads stable while timestamp dates honor the account timezone", () => {
    const formatter = createDateFormatter({ locale: "zh-CN", timeZone: "America/Los_Angeles", order: "dmy" });
    expect(formatter.renderFormattedDate("2026-11-12")).toBe("12/11/2026");
    expect(formatter.renderFormattedDate("2026-11-12T01:00:00Z")).toBe("11/11/2026");
    const day = new Date(2026, 10, 12);
    expect(formatter.formatCalendarDate(day)).toBe("12/11/2026");
    expect(renderFormattedPayloadDate(day)).toBe("2026-11-12");
  });
  it("updates mounted consumers and selectors when preferences or language change without sharing user state", () => {
    const onChange = vi.fn();
    const view = (locale: string, order: "locale" | "dmy") => (
      <>
        <DateDisplayProvider locale={locale} order={order} timeZone="Asia/Shanghai">
          <DateText />
          <DateSelect value={new Date(2026, 10, 12)} onChange={onChange} variant="select-md" />
          <DateRangeSelect
            value={{ from: new Date(2026, 10, 12), to: new Date(2026, 11, 3) }}
            onChange={onChange}
            variant="select-md"
            mergeDates
          />
        </DateDisplayProvider>
        <DateDisplayProvider locale="en-US" order="ymd" timeZone="UTC">
          <DateText />
        </DateDisplayProvider>
      </>
    );
    const { rerender } = render(view("zh-CN", "locale"));
    expect(screen.getByText("2026年11月12日 16:08")).toBeTruthy();
    expect(screen.getByRole("button", { name: "2026年11月12日" })).toBeTruthy();
    expect(screen.getByText("2026/11/12 08:08")).toBeTruthy();
    rerender(view("zh-CN", "dmy"));
    expect(screen.getByText("12/11/2026 16:08")).toBeTruthy();
    expect(screen.getByRole("button", { name: "12/11/2026" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /12\/11\/2026 - 03\/12\/2026/ })).toBeTruthy();
    rerender(view("en-US", "locale"));
    expect(screen.getByText("November 12, 2026 16:08")).toBeTruthy();
    expect(onChange).not.toHaveBeenCalled();
  });
});
