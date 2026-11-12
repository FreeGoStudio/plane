import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const ts = require("typescript");
let locale = "zh-CN";
let cached = true;
let state = { id: "state-id", name: "Triage", group: "triage", color: "#4E5355" };
const dictionaries = Object.fromEntries(
  ["zh-CN", "en"].map((language) => [
    language,
    JSON.parse(
      readFileSync(new URL(`../../../../../packages/i18n/src/locales/${language}/inbox.json`, import.meta.url), "utf8")
    ),
  ])
);
const mocks = {
  react: { useCallback: (callback) => callback },
  "react/jsx-runtime": require("react/jsx-runtime"),
  "mobx-react": { observer: (component) => component },
  "@plane/blocks/property-select": { IntakeStateSelect: "select" },
  "@plane/i18n": {
    useTranslation: () => {
      const language = locale;
      return {
        currentLocale: language,
        t: (key) => key.split(".").reduce((value, part) => value?.[part], dictionaries[language]) ?? key,
      };
    },
  },
  "@/hooks/store/use-project-state": {
    useProjectState: () => ({
      getIntakeStateById: () => (cached ? state : undefined),
      getProjectIntakeState: () => (cached ? state : undefined),
      fetchProjectIntakeState: async () => state,
    }),
  },
};
const exports = {};
const code = ts.transpileModule(readFileSync(new URL("./intake-state-select.tsx", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
new Function("exports", "require", code)(exports, (name) => {
  assert.ok(name in mocks, name);
  return mocks[name];
});
const props = { workspaceSlug: "workspace", projectId: "project", value: "state-id", onChange: () => {} };
test("selected triage and dropdown options switch languages without modifying state identity or data", async () => {
  const original = structuredClone(state);
  const optionChecks = [];
  for (locale of ["zh-CN", "en", "zh-CN"]) {
    const select = exports.IntakeStateSelect(props);
    assert.equal(select.key, locale, "language changes must invalidate cached dropdown options");
    const expected = { ...original, name: locale === "zh-CN" ? "待分流" : "Triage" };
    assert.deepEqual(select.props.value, expected);
    optionChecks.push(select.props.getValues({}).then((response) => assert.deepEqual(response.results, [expected])));
    assert.equal(select.props.onChange, props.onChange);
  }
  await Promise.all(optionChecks);
  assert.deepEqual(state, original);
});
test("uncached intake states translate after loading and ordinary states keep user names", async () => {
  cached = false;
  const select = exports.IntakeStateSelect(props);
  assert.equal(select.props.value, null);
  assert.equal((await select.props.getValues({})).results[0].name, "待分流");
  cached = true;
  state = { ...state, group: "backlog", name: "Triage" };
  assert.equal(exports.IntakeStateSelect(props).props.value.name, "Triage");
  state = { ...state, name: "团队自定义状态" };
  assert.equal((await exports.IntakeStateSelect(props).props.getValues({})).results[0].name, state.name);
});
