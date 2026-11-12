import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const i18n = require("@plane/i18n");
const mocks = {
  "react/jsx-runtime": require("react/jsx-runtime"),
  "@plane/i18n": i18n,
  "@plane/utils": { cn: (...values) => values.join(" ") },
  "@/components/editor/lite-text": {},
  "../../notification-card/content": {},
};
const exports = {};
const code = ts.transpileModule(readFileSync(new URL("./content.tsx", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
new Function("exports", "require", code)(exports, (name) => {
  assert.ok(name in mocks, name);
  return mocks[name];
});
test("label notifications translate both actions while preserving actor and label text", async () => {
  await i18n.initPromise;
  const check = async (locale, added, removed) => {
    await i18n.setLanguage(locale);
    for (const adding of [true, false]) {
      const notification = {
        triggered_by_details: { display_name: "Original actor" },
        data: {
          issue_activity: {
            field: "labels",
            verb: "updated",
            new_value: adding ? "UI <label> 中文" : "",
            old_value: adding ? "" : "UI <label> 中文",
          },
        },
      };
      const original = structuredClone(notification);
      const html = renderToStaticMarkup(
        React.createElement(exports.NotificationContent, {
          notification,
          workspaceId: "workspace",
          workspaceSlug: "workspace",
          projectId: "project",
          isUnread: true,
        })
      );
      assert.ok(html.includes(adding ? added : removed), html);
      assert.ok(html.includes("Original actor"));
      assert.ok(html.includes("UI &lt;label&gt; 中文"));
      assert.ok(html.includes("font-semibold"));
      assert.deepEqual(notification, original);
    }
  };
  await check("zh-CN", "添加了标签", "移除了标签");
  await check("en", "added the label", "removed the label");
  await check("zh-CN", "添加了标签", "移除了标签");
});
