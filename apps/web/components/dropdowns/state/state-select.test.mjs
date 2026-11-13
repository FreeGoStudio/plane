/* eslint-disable no-await-in-loop -- Language-switch tests must exercise shared locale state sequentially. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const ts = require("typescript");
let locale = "zh-CN";
let cached = true;
let state = { id: "state-id", name: "In Progress", group: "started", color: "#4E5355" };
const dictionaries = Object.fromEntries(
  ["zh-CN", "en"].map((language) => [
    language,
    JSON.parse(
      readFileSync(
        new URL(`../../../../../packages/i18n/src/locales/${language}/workspace.json`, import.meta.url),
        "utf8"
      )
    ),
  ])
);
const displayNameExports = {};
new Function(
  "exports",
  ts.transpileModule(
    readFileSync(new URL("../../../../../packages/i18n/src/state-display-name.ts", import.meta.url), "utf8"),
    { compilerOptions: { module: ts.ModuleKind.CommonJS } }
  ).outputText
)(displayNameExports);
const mocks = {
  react: { useCallback: (callback) => callback, useMemo: (callback) => callback() },
  "next/navigation": { useParams: () => ({ workspaceSlug: "workspace" }) },
  "react/jsx-runtime": require("react/jsx-runtime"),
  "mobx-react": { observer: (component) => component },
  "@plane/blocks/property-select": { StateSelect: "select" },
  "@plane/i18n": {
    getStateDisplayName: displayNameExports.getStateDisplayName,
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
      getStateById: () => state,
      getProjectStateIds: () => (cached ? [state.id] : undefined),
      fetchProjectStates: async () => {
        cached = true;
      },
    }),
  },
};
const exports = {};
const code = ts.transpileModule(readFileSync(new URL("./state-select.tsx", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
new Function("exports", "require", code)(exports, (name) => {
  assert.ok(name in mocks, name);
  return mocks[name];
});
const props = { workspaceSlug: "workspace", projectId: "project", value: "state-id", onChange: () => {} };
test("state options, selection and search follow UI language without changing stored names", async () => {
  const original = structuredClone(state);
  for (locale of ["zh-CN", "en", "zh-CN"]) {
    const select = exports.StateSelect(props);
    const expectedName = locale === "zh-CN" ? "进行中" : "In Progress";
    assert.equal(select.key, locale);
    assert.equal(select.props.value.name, expectedName);
    assert.equal(select.props.value.id, original.id);
    assert.equal(select.props.onChange, props.onChange);
    assert.equal((await select.props.getValues({ search: expectedName })).results[0].name, expectedName);
    assert.equal((await select.props.getValues({ search: "In Progress" })).results.length, 1);
    assert.equal((await select.props.getValues({ search: "missing" })).results.length, 0);
  }
  assert.deepEqual(state, original);
  cached = false;
  assert.equal((await exports.StateSelect(props).props.getValues({})).results[0].name, "进行中");
  state = { ...state, name: "团队评审" };
  const select = exports.StateSelect(props);
  assert.equal(select.props.value.name, "团队评审");
  assert.equal((await select.props.getValues({ search: "评审" })).results[0].name, "团队评审");
});
