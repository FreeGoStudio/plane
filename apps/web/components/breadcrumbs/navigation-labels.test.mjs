import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const root = "../../app/(all)/[workspaceSlug]/(projects)/";
const project = `${root}projects/(detail)/[projectId]/`;
const cases = [
  [`${root}stickies/header.tsx`, "stickies", "便签"],
  ...[
    ["cycles", "周期"],
    ["modules", "模块"],
    ["pages", "页面"],
    ["views", "视图"],
  ].flatMap(([name, label]) => [
    [`${project}${name}/(list)/header.tsx`, name, label],
    [`${project}${name}/(detail)/${name === "views" ? "[viewId]/" : ""}header.tsx`, name, label],
  ]),
];
const dictionaries = Object.fromEntries(
  ["zh-CN", "en"].map((locale) => [
    locale,
    JSON.parse(
      readFileSync(new URL(`../../../../packages/i18n/src/locales/${locale}/navigation.json`, import.meta.url), "utf8")
    ),
  ])
);
for (const [path, key, chinese] of cases) {
  test(`${path}: navigation label supports Chinese and English`, () => {
    const source = ts.createSourceFile(
      path,
      readFileSync(new URL(path, import.meta.url), "utf8"),
      ts.ScriptTarget.Latest,
      true,
      ts.ScriptKind.TSX
    );
    const labels = [];
    function visit(node) {
      if (
        (ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node)) &&
        node.tagName.getText(source) === "BreadcrumbLink"
      ) {
        const label = node.attributes.properties.find((prop) => prop.name?.getText(source) === "label");
        if (label?.initializer && ts.isJsxExpression(label.initializer)) labels.push(label.initializer.expression);
      }
      ts.forEachChild(node, visit);
    }
    visit(source);
    const label = labels.find(
      (expression) => ts.isCallExpression(expression) && expression.arguments[0]?.text === `sidebar.${key}`
    );
    assert.ok(label, "navigation breadcrumb must use the shared translated label");
    const render = new Function("t", `return ${label.getText(source)}`);
    for (const locale of ["zh-CN", "en", "zh-CN"]) {
      const value = render((translationKey) =>
        translationKey.split(".").reduce((object, part) => object[part], dictionaries[locale])
      );
      assert.equal(value, locale === "zh-CN" ? chinese : dictionaries.en.sidebar[key]);
    }
  });
}
