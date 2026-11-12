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
const i18n = require("@plane/i18n");
const activity = { verb: "created", new_value: "https://example.com/new", old_value: "https://example.com/old" };
const mocks = {
  "react/jsx-runtime": require("react/jsx-runtime"),
  "@plane/i18n": i18n,
  "mobx-react": { observer: (component) => component },
  "@makeplane/propel/icons": await import("@makeplane/propel/icons"),
  "@/hooks/store/use-issue-detail": { useIssueDetail: () => ({ activity: { getActivityById: () => activity } }) },
  "./": { IssueActivityBlockComponent: ({ children }) => children, IssueLink: () => "TEST-1" },
};
const exports = {};
const code = ts.transpileModule(readFileSync(new URL("./link.tsx", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
new Function("exports", "require", code)(exports, (name) => {
  assert.ok(name in mocks, name);
  return mocks[name];
});

test("translated activity links retain visible link styling, an external icon and their original destinations", async () => {
  await i18n.initPromise;
  for (const locale of ["zh-CN", "en"]) {
    // The shared translation instance must finish switching before each render.
    // oxlint-disable-next-line no-await-in-loop
    await i18n.setLanguage(locale);
    for (const verb of ["created", "updated", "deleted"]) {
      activity.verb = verb;
      for (const showIssue of [false, true]) {
        const html = renderToStaticMarkup(
          React.createElement(exports.IssueLinkActivity, { activityId: "activity", showIssue })
        );
        const anchor = html.match(/<a\b[^>]*>([\s\S]*?)<\/a>/)?.[0];
        assert.ok(anchor, html);
        assert.ok(anchor.includes(`href="${verb === "created" ? activity.new_value : activity.old_value}"`));
        assert.match(anchor, /target="_blank"/);
        assert.match(anchor, /rel="noopener noreferrer"/);
        const classes = anchor.match(/class="([^"]*)"/)[1].split(" ");
        assert.ok(classes.includes("text-accent-primary"));
        assert.ok(classes.includes("underline"));
        assert.ok(anchor.includes(locale === "zh-CN" ? "链接" : "link"));
        assert.match(anchor, /<svg\b[^>]*aria-hidden="true"/);
        assert.equal((anchor.match(/<svg\b/g) ?? []).length, 1);
      }
    }
  }
});
