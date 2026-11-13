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
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
let currentLocale = "zh-CN";
const mocks = {
  "@plane/utils": require("@plane/utils"),
  "react/jsx-runtime": require("react/jsx-runtime"),
  "mobx-react": { observer: (component) => component },
  "@/hooks/store/user": { useUserProfile: () => ({ data: {} }) },
  "@/hooks/use-current-time": { useCurrentTime: () => ({ currentTime: new Date("2026-11-13T00:00:00Z") }) },
  "@/helpers/home-datetime": { getHomeGreetingPeriod: () => "morning", formatHomeDate: () => "2026/11/13" },
  "@plane/i18n": { useTranslation: () => ({ currentLocale, t: (_key, { name }) => `Hello, ${name}` }) },
};
const code = ts.transpileModule(readFileSync(new URL("./user-greetings.tsx", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const exports = {};
new Function("exports", "require", code)(exports, (id) => {
  assert.ok(id in mocks, id);
  return mocks[id];
});

for (const [locale, firstName, lastName, expected] of [
  ["zh-CN", "三", "张", "张三"],
  ["zh-TW", "明", "陳", "陳明"],
  ["zh-CN", "娜娜", "欧阳", "欧阳娜娜"],
  ["en", "John", "Smith", "John Smith"],
  ["zh-CN", "三", "", "三"],
  ["zh-CN", "", "张", "张"],
  ["en", "John", "", "John"],
  ["zh-CN", "", "", ""],
]) {
  test(`home greeting formats ${locale} name ${lastName}/${firstName}`, () => {
    currentLocale = locale;
    const html = renderToStaticMarkup(
      React.createElement(exports.UserGreetingsView, {
        user: { first_name: firstName, last_name: lastName, user_timezone: "Asia/Shanghai" },
      })
    );
    assert.ok(html.includes(`>Hello, ${expected}</h2>`), html);
  });
}
