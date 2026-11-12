import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const ts = require("typescript");
let locale = "zh-CN";
const dictionaries = Object.fromEntries(
  ["zh-CN", "en"].map((language) => [
    language,
    JSON.parse(
      readFileSync(
        new URL(`../../../../../../../packages/i18n/src/locales/${language}/common.json`, import.meta.url),
        "utf8"
      )
    ),
  ])
);
const mocks = {
  react: { useState: () => [false, () => {}] },
  "react/jsx-runtime": require("react/jsx-runtime"),
  "mobx-react": { observer: (component) => component },
  "next/navigation": { useParams: () => ({}) },
  "@plane/i18n": {
    useTranslation: () => ({
      t: (key) => key.split(".").reduce((value, part) => value?.[part], dictionaries[locale]) ?? key,
    }),
  },
  "@/hooks/use-issue-layout-store": { useIssueStoreType: () => "PROFILE" },
};
const exports = {};
const code = ts.transpileModule(readFileSync(new URL("./group-by-card.tsx", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
new Function("exports", "require", code)(
  exports,
  (name) => mocks[name] ?? new Proxy({}, { get: (_, key) => String(key) })
);
const props = {
  groupID: "All Issues",
  groupBy: null,
  title: "All work items",
  count: 3,
  canEditProperties: () => false,
  disableIssueCreation: true,
  selectionHelpers: { isGroupSelected: () => "empty" },
  isExpanded: true,
};
function button(node) {
  if (Array.isArray(node)) return node.map(button).find(Boolean);
  if (!node || typeof node !== "object") return undefined;
  return node.type === "button" ? node : button(node.props?.children);
}
test("ungrouped work item heading and accessible name follow language without changing count", () => {
  for (locale of ["zh-CN", "en", "zh-CN"]) {
    const header = button(exports.HeaderGroupByCard(props));
    const expected = dictionaries[locale].space_ui.all_work_items;
    assert.equal(header.props["aria-label"], expected);
    assert.equal(header.props.children[0].props.children, expected);
    assert.equal(header.props.children[1].props.children, 3);
  }
});
test("user-defined groups and epic headings retain their names", () => {
  for (const overrides of [
    { groupID: "custom", groupBy: "state", title: "All work items" },
    { isEpic: true, title: "All Epics" },
  ]) {
    const header = button(exports.HeaderGroupByCard({ ...props, ...overrides }));
    assert.equal(header.props["aria-label"], overrides.title);
  }
});
