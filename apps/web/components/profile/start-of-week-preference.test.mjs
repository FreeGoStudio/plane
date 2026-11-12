import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const ts = require("typescript");
let locale = "zh-CN";
const updates = [];
const mocks = {
  "react/jsx-runtime": require("react/jsx-runtime"),
  "mobx-react": { observer: (component) => component },
  "@makeplane/propel/components/select-field": { SelectField: "select" },
  "@plane/i18n": { useTranslation: () => ({ currentLocale: locale }) },
  "@plane/constants": {
    START_OF_THE_WEEK_OPTIONS: Array.from({ length: 7 }, (_, value) => ({ value, label: "English" })),
  },
  "@plane/blocks/toast": { setToast: () => undefined },
  "@/components/settings/control-item": { SettingsControlItem: "setting" },
  "@/hooks/store/user": {
    useUserProfile: () => ({ data: { start_of_the_week: 1 }, updateUserProfile: async (value) => updates.push(value) }),
  },
};
const source = readFileSync(new URL("./start-of-week-preference.tsx", import.meta.url), "utf8");
const code = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const exports = {};
new Function("exports", "require", code)(exports, (name) => {
  assert.ok(name in mocks, name);
  return mocks[name];
});

test("weekly preference displays Chinese copy and weekdays, preserving stored values", async () => {
  const settings = JSON.parse(
    readFileSync(new URL("../../../../packages/i18n/src/locales/zh-CN/settings.json", import.meta.url), "utf8")
  );
  const option = settings.account_settings.start_of_week;
  const tree = exports.StartOfWeekPreference({ option });
  assert.equal(tree.props.title, "每周首日");
  assert.equal(tree.props.description, "设置应用中所有日历一周从星期几开始。");
  const select = tree.props.control;
  assert.deepEqual(
    select.props.options.map((item) => item.label),
    ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"]
  );
  assert.deepEqual(
    select.props.options.map((item) => item.value),
    [0, 1, 2, 3, 4, 5, 6]
  );
  assert.equal(select.props.value, 1);
  select.props.onValueChange(0);
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(updates, [{ start_of_the_week: 0 }]);
  locale = "en";
  const english = exports.StartOfWeekPreference({ option }).props.control;
  assert.equal(english.props.options[0].label, "Sunday");
  assert.equal(english.props.options[6].label, "Saturday");
});
