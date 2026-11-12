import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
const require = createRequire(import.meta.url);
const ts = require("typescript");
const utils = require("@plane/utils");
const constants = require("@plane/constants");
const types = require("@plane/types");
let formatter = utils.createDateFormatter({ locale: "zh-CN", timeZone: "America/Los_Angeles" });
function load(path, mocks = {}) {
  const code = ts.transpileModule(readFileSync(new URL(path, import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const exports = {};
  new Function("exports", "require", code)(exports, (name) => {
    if (name in mocks) return mocks[name];
    if (name === "@plane/utils") return { ...utils, useDateFormatter: () => formatter };
    if (name === "mobx-react") return { observer: (component) => component };
    return require(name);
  });
  return exports;
}
const chart = load("./utils.ts");
test("weekday-only calendar labels stay compact under every date order", () => {
  const day = new Date(2026, 10, 12);
  for (const order of ["locale", "ymd", "mdy", "dmy"]) {
    for (const [locale, short, long] of [
      ["zh-CN", "周四", "星期四"],
      ["en", "Thu", "Thursday"],
    ]) {
      const calendar = utils.createDateFormatter({ locale, order, timeZone: "America/Los_Angeles" });
      assert.equal(calendar.formatCalendarDate(day, "EEE"), short);
      assert.equal(calendar.formatCalendarDate(day, "EEEE"), long);
    }
  }
});
test("chart date-only buckets keep the same day and month in a negative account timezone", () => {
  const year = new Date().getFullYear();
  const date = `${year}-11-01`;
  const data = { data: [{ key: date, name: date, count: 2 }], schema: { [date]: date } };
  const before = structuredClone(data);
  formatter = utils.createDateFormatter({ locale: "zh-CN", timeZone: "America/Los_Angeles" });
  for (const [group, expected] of [
    ["DAY", "11月1日"],
    ["MONTH", "十一月"],
  ]) {
    const result = chart.parseChartData(
      data,
      types.ChartXAxisProperty.START_DATE,
      types.ChartXAxisProperty.START_DATE,
      constants.ChartXAxisDateGrouping[group],
      formatter
    );
    assert.equal(result.data[0].name, expected);
    assert.equal(result.schema[date], expected);
    assert.equal(result.data[0].key, date);
    assert.equal(result.data[0].count, 2);
    assert.deepEqual(data, before);
  }
});
test("readonly dates follow preferences while preserving civil dates and shifting instants", () => {
  const { ReadonlyDate } = load("../readonly/date.tsx", {
    "@plane/i18n": { useTranslation: () => ({ t: () => "None" }) },
    "@makeplane/propel/icons": { CalendarOutline: "icon" },
  });
  const text = (value) => ReadonlyDate({ value }).props.children[1].props.children;
  formatter = utils.createDateFormatter({ locale: "zh-CN", order: "dmy", timeZone: "America/Los_Angeles" });
  assert.equal(text("2026-11-12"), "12/11/2026");
  assert.equal(text("2026-11-12T01:00:00Z"), "11/11/2026");
  assert.equal(text(null), "None");
  formatter = utils.createDateFormatter({ locale: "en", order: "ymd", timeZone: "Asia/Shanghai" });
  assert.equal(text("2026-11-12T23:00:00Z"), "2026/11/13");
});
test("both gantt resize tooltips show the selected civil date without timezone drift", () => {
  const day = new Date(2026, 10, 12);
  const zone = "Etc/GMT+12";
  formatter = utils.createDateFormatter({ locale: "zh-CN", timeZone: zone });
  for (const side of ["left", "right"]) {
    const module = load(`../gantt-chart/helpers/blockResizables/${side}-resizable.tsx`, {
      react: { useState: () => [true, () => {}] },
      "@/hooks/use-timeline-chart": { useTimeLineChartStore: () => ({ getDateFromPositionOnGantt: () => day }) },
    });
    const Component = module[side === "left" ? "LeftResizable" : "RightResizable"];
    const tree = Component({
      enableBlockLeftResize: true,
      enableBlockRightResize: true,
      position: { marginLeft: 0, width: 10 },
    });
    assert.equal(tree.props.children[0].props.children.props.children, "2026年11月12日");
  }
});
test("user timezone converter uses localized account timezone across midnight", () => {
  formatter = utils.createDateFormatter({ locale: "zh-CN", timeZone: "Asia/Shanghai" });
  const { useTimeZoneConverter } = load("../../hooks/use-timezone-converter.tsx", {
    react: { useCallback: (fn) => fn },
    "@/hooks/store/use-project": { useProject: () => ({ getProjectById: () => ({ timezone: "UTC" }) }) },
    "@/hooks/store/user": { useUser: () => ({ data: { user_timezone: "Asia/Shanghai" } }) },
  });
  assert.equal(
    useTimeZoneConverter("project").renderFormattedDateInUserTimezone("2026-11-12T23:00:00Z", "MMM dd, yyyy HH:mm"),
    "2026年11月13日 07:00"
  );
});
