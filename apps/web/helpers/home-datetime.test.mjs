import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const source = readFileSync(new URL("./home-datetime.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const exports = {};
new Function("exports", "require", compiled)(exports, require);
const { formatHomeDate, getHomeGreetingPeriod } = exports;
const date = new Date("2026-11-12T08:08:00Z");

test("Chinese home date uses localized calendar, weekday and account timezone", () => {
  assert.equal(formatHomeDate(date, "zh-CN", "Asia/Shanghai"), "2026年11月12日 星期四 16:08");
  assert.match(formatHomeDate(date, "en", "Asia/Shanghai"), /November 12, 2026 Thursday 16:08/);
});
test("all explicit date orders preserve the selected language", () => {
  for (const [order, expected] of [
    ["ymd", "2026/11/12"],
    ["mdy", "11/12/2026"],
    ["dmy", "12/11/2026"],
  ]) {
    assert.equal(formatHomeDate(date, "zh-CN", "Asia/Shanghai", order), `${expected} 星期四 16:08`);
  }
});
test("date and greeting respect midnight, noon, evening and timezone boundaries", () => {
  for (const [hour, period] of [
    [0, "morning"],
    [11, "morning"],
    [12, "afternoon"],
    [17, "afternoon"],
    [18, "evening"],
    [23, "evening"],
  ]) {
    assert.equal(getHomeGreetingPeriod(new Date(Date.UTC(2026, 10, 12, hour)), "UTC"), period);
  }
  const midnight = new Date("2026-11-12T16:00:00Z");
  assert.equal(formatHomeDate(midnight, "zh-CN", "Asia/Shanghai"), "2026年11月13日 星期五 00:00");
  assert.equal(getHomeGreetingPeriod(midnight, "Asia/Shanghai"), "morning");
  assert.equal(getHomeGreetingPeriod(midnight, "UTC"), "afternoon");
});

test("date preference loads account value and saves selection through profile service", async () => {
  const React = require("react");
  const updates = [];
  const errors = [];
  let fail = false;
  const profile = { theme: { homeDateOrder: "dmy" } };
  const mocks = {
    "react/jsx-runtime": require("react/jsx-runtime"),
    "mobx-react": { observer: (component) => component },
    "@makeplane/propel/components/select-field": { SelectField: "select" },
    "@plane/i18n": { SUPPORTED_LANGUAGES: [], useTranslation: () => ({ t: (key) => key }) },
    "@plane/blocks/toast": { setToast: (value) => errors.push(value) },
    "@/components/global/timezone-select": { TimezoneSelect: "timezone" },
    "@/components/profile/start-of-week-preference": { StartOfWeekPreference: "week" },
    "@/components/settings/control-item": { SettingsControlItem: "setting" },
    "@/hooks/store/user": {
      useUser: () => ({ userProfile: { data: profile } }),
      useUserProfile: () => ({
        updateUserTheme: async (value) => {
          if (fail) throw new Error("offline");
          updates.push(value);
        },
      }),
    },
  };
  const code = ts.transpileModule(
    readFileSync(
      new URL(
        "../components/settings/profile/content/pages/preferences/language-and-timezone-list.tsx",
        import.meta.url
      ),
      "utf8"
    ),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }
  ).outputText;
  const module = {};
  new Function("exports", "require", code)(module, (name) => {
    assert.ok(name in mocks, `Unmocked import: ${name}`);
    return mocks[name];
  });
  const tree = module.ProfileSettingsLanguageAndTimezonePreferencesList();
  const setting = React.Children.toArray(tree.props.children).find(
    (child) => child.props.title === "home.date_display.title"
  );
  const select = setting.props.control;
  assert.equal(select.props.value, "dmy");
  assert.deepEqual(
    select.props.options.map((option) => option.value),
    ["locale", "ymd", "mdy", "dmy"]
  );
  select.props.onValueChange("ymd");
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(updates, [{ homeDateOrder: "ymd" }]);
  fail = true;
  select.props.onValueChange("mdy");
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(errors[0].type, "error");
});

test("home relative timestamps are Chinese and retain English when selected", () => {
  const hourAgo = new Date(Date.now() - 60 * 60 * 1000);
  const daysAgo = new Date(Date.now() - 10 * 24 * 60 * 60 * 1000);
  assert.equal(exports.formatHomeTimeAgo(hourAgo, "zh-CN"), "大约 1 小时前");
  assert.equal(exports.formatHomeTimeAgo(daysAgo.toISOString(), "zh-CN"), "10 天前");
  assert.equal(exports.formatHomeTimeAgo(hourAgo, "en"), "about 1 hour ago");
  assert.equal(exports.formatHomeTimeAgo(null, "zh-CN"), "");
  assert.equal(exports.formatHomeTimeAgo("invalid", "zh-CN"), "");
});
