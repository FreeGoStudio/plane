import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const { STATE_GROUPS } = require("@plane/constants");
let locale = "zh-CN";
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
const mocks = {
  "react/jsx-runtime": require("react/jsx-runtime"),
  "@plane/constants": { STATE_GROUPS },
  "@plane/blocks/card": { Card: "card" },
  "@plane/i18n": {
    useTranslation: () => ({
      t: (key) => key.split(".").reduce((value, part) => value?.[part], dictionaries[locale]) ?? key,
    }),
  },
};
const exports = {};
const code = ts.transpileModule(readFileSync(new URL("./workload.tsx", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
new Function("exports", "require", code)(exports, (name) => {
  assert.ok(name in mocks, name);
  return mocks[name];
});
function nodes(node) {
  if (Array.isArray(node)) return node.flatMap(nodes);
  if (!node || typeof node !== "object") return [];
  return [node, ...nodes(node.props?.children)];
}
test("workload translates all five states on language changes without changing counts or colors", () => {
  const groups = ["backlog", "unstarted", "started", "completed", "cancelled"];
  const distribution = groups.map((state_group, index) => ({ state_group, state_count: index + 1 }));
  const original = structuredClone(distribution);
  for (locale of ["zh-CN", "en", "zh-CN"]) {
    const tree = nodes(exports.ProfileWorkload({ stateDistribution: distribution }));
    assert.deepEqual(
      tree.filter((node) => node.type === "span").map((node) => node.props.children),
      groups.map((group) => dictionaries[locale].workspace_projects.state[group])
    );
    assert.deepEqual(
      tree.filter((node) => node.type === "p").map((node) => node.props.children),
      [1, 2, 3, 4, 5]
    );
    assert.deepEqual(
      tree.filter((node) => node.props.style?.backgroundColor).map((node) => node.props.style.backgroundColor),
      groups.map((group) => STATE_GROUPS[group].color)
    );
  }
  assert.deepEqual(distribution, original);
});
