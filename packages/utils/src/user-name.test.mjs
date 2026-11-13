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
const code = ts.transpileModule(readFileSync(new URL("./user-name.ts", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const exports = {};
new Function("exports", code)(exports);
const { formatUserFullName } = exports;
for (const [locale, user, expected] of [
  ["zh-CN", { first_name: "三", last_name: "张" }, "张三"],
  ["zh-TW", { first_name: "明", last_name: "陳" }, "陳明"],
  ["zh-HK", { first_name: "娜娜", last_name: "歐陽" }, "歐陽娜娜"],
  ["en", { first_name: "John", last_name: "Smith" }, "John Smith"],
  ["de", { first_name: "Anna", last_name: "Schmidt" }, "Anna Schmidt"],
  ["zh-CN", { first_name: "小明" }, "小明"],
  ["zh-CN", { last_name: "张" }, "张"],
  ["en", { last_name: "Smith" }, "Smith"],
  ["zh-CN", { first_name: null, last_name: "" }, ""],
  ["en", undefined, ""],
  ["zh-CN", null, ""],
]) {
  test(`formats ${JSON.stringify(user)} in ${locale}`, () => {
    const original = structuredClone(user);
    assert.equal(formatUserFullName(user, locale), expected);
    assert.deepEqual(user, original);
  });
}
