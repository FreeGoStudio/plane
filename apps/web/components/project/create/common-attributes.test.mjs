/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const mocks = {
  "react/jsx-runtime": require("react/jsx-runtime"),
  "pinyin-pro": require("pinyin-pro"),
  "react-hook-form": { Controller: "Controller", useFormContext: () => ({ formState: { errors: {} }, control: {} }) },
  "@plane/constants": { ETabIndices: { PROJECT_CREATE: 0 } },
  "@plane/i18n": { useTranslation: () => ({ t: (key) => key }) },
  "@plane/utils": require("@plane/utils"),
};
const code = ts.transpileModule(readFileSync(new URL("./common-attributes.tsx", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const exports = {};
new Function("exports", "require", code)(exports, (id) => {
  if (id.startsWith("@makeplane/propel/")) return new Proxy({}, { get: (_target, key) => key });
  assert.ok(id in mocks, id);
  return mocks[id];
});

function form() {
  const values = { name: "", identifier: "" };
  let autoSync = true;
  const change = (field, value) => {
    const tree = exports.default({
      setValue: (key, next) => {
        values[key] = next;
      },
      isMobile: false,
      shouldAutoSyncIdentifier: autoSync,
      setShouldAutoSyncIdentifier: (next) => {
        autoSync = next;
      },
    });
    const controller = tree.props.children[field === "name" ? 0 : 1].props.children;
    const input = controller.props.render({
      field: {
        value: values[field],
        onChange: (next) => {
          values[field] = typeof next === "string" ? next : next.target.value;
        },
      },
    });
    input.props.onChange({ target: { value } });
  };
  return { values, change };
}

for (const [name, expected] of [
  ["项目管理", "XMGL"],
  ["重庆银行", "CQYH"],
  ["中文API平台2026", "ZWAPIPT202"],
  ["项目-管理！", "XMGL"],
  ["一二三四五六七八九十百", "YESSWLQBJS"],
  ["API 2026", "API2026"],
]) {
  test(`project name ${name} generates ${expected}`, () => {
    const { values, change } = form();
    change("name", name);
    assert.equal(values.name, name);
    assert.equal(values.identifier, expected);
  });
}

test("identifier follows incremental typing, replacement, deletion and clearing", () => {
  const { values, change } = form();
  for (const [name, expected] of [
    ["项", "X"],
    ["项目", "XM"],
    ["研发", "YF"],
    ["研", "Y"],
    ["", ""],
  ]) {
    change("name", name);
    assert.equal(values.identifier, expected);
  }
});

test("manual identifier edits stop automatic synchronization", () => {
  const { values, change } = form();
  change("name", "项目");
  change("identifier", "CUSTOM-1");
  change("name", "项目管理");
  assert.equal(values.name, "项目管理");
  assert.equal(values.identifier, "CUSTOM1");
});
