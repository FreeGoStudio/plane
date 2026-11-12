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
const React = require("react");
const ts = require("typescript");
const { renderToStaticMarkup } = require("react-dom/server");
const i18n = require("@plane/i18n");
const passthrough = ({ children }) => children;
const mocks = {
  react: React,
  "react/jsx-runtime": require("react/jsx-runtime"),
  "@plane/i18n": i18n,
  "mobx-react": { observer: (component) => component },
  "next/navigation": { useParams: () => ({ workspaceSlug: "workspace", userId: "other" }) },
  "@makeplane/propel/icons": await import("@makeplane/propel/icons"),
  "@plane/blocks/icons": { BlockedIcon: () => null, BlockerIcon: () => null },
  "@makeplane/propel/components/tooltip": {
    Tooltip: ({ label, children }) => React.createElement("span", { title: label }, children),
  },
  "@plane/utils": {
    generateWorkItemLink: () => "/workspace/browse/TEST-1/",
    DateDisplay: () => null,
    capitalizeFirstLetter: (value) => value,
    cn: (...values) => values.join(" "),
    getFileURL: (value) => value,
    useDateFormatter: () => ({ renderFormattedDate: () => "2026年11月12日" }),
  },
  "@/hooks/store/use-label": {
    useLabel: () => ({ workspaceLabels: [{ id: "label", color: "#123456" }], fetchWorkspaceLabels: () => {} }),
  },
  "@/hooks/use-platform-os": { usePlatformOS: () => ({ isMobile: false }) },
  "@plane/hooks": { useOutsideClickDetector: () => {} },
  "@plane/blocks/emoji-icon-picker": { Logo: () => null },
  "@makeplane/propel/components/collapsible": {
    Collapsible: ({ trigger, trailing, children }) => React.createElement("section", null, trigger, trailing, children),
  },
  "@makeplane/propel/components/avatar": { Avatar: () => null },
  "@makeplane/propel/components/badge": { Badge: ({ label }) => label },
  "@makeplane/propel/components/icon-button": { IconButton: () => null },
  "@makeplane/propel/components/icon": { Icon: () => null },
  "@makeplane/propel/components/scroll-area": { ScrollArea: passthrough },
  "@plane/blocks/skeleton": { Loader: passthrough },
  "@/components/common/cover-image": { CoverImage: () => null },
  "@/hooks/store/use-app-theme": { useAppTheme: () => ({ profileSidebarCollapsed: false }) },
  "@/hooks/store/use-command-palette": { useCommandPalette: () => ({}) },
  "@/hooks/store/use-project": { useProject: () => ({ getProjectById: () => ({ name: "Original project" }) }) },
  "@/hooks/store/user": { useUser: () => ({ data: { id: "self" } }) },
  "./time": { ProfileSidebarTime: () => "UTC" },
};
function load(path) {
  const exports = {};
  const code = ts.transpileModule(readFileSync(new URL(path, import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  new Function("exports", "require", code)(exports, (name) => {
    assert.ok(name in mocks, name);
    return mocks[name];
  });
  return exports;
}
const { ActivityMessage } = load("../core/activity.tsx");
const { ProfileSidebar } = load("./sidebar.tsx");
const base = {
  issue: "issue",
  project: "project",
  project_detail: { identifier: "TEST" },
  issue_detail: { sequence_id: 1, name: "Original <title>" },
  new_identifier: "label",
  old_identifier: "label",
  old_value: "",
  new_value: "Label <text>",
};

test("profile screenshot activity branches translate without changing values or link destinations", async () => {
  await i18n.initPromise;
  for (const language of ["zh-CN", "en", "zh-CN"]) {
    // Language is shared state, so each render must follow its completed switch.
    // oxlint-disable-next-line no-await-in-loop
    await i18n.setLanguage(language);
    const chinese = language === "zh-CN";
    for (const [field, verb, oldValue, newValue, word] of [
      ["issue", "created", "", "", chinese ? "创建了" : "created"],
      ["issue", "deleted", "", "", chinese ? "删除了" : "deleted"],
      ["issue", "converted", "", "", chinese ? "史诗" : "epic"],
      ["labels", "updated", "", "Label <text>", chinese ? "添加了" : "added"],
      ["labels", "updated", "Label <text>", "", chinese ? "移除了" : "removed"],
      ["link", "created", "", "https://example.com/new", chinese ? "添加了" : "added"],
      ["link", "updated", "https://example.com/old", "https://example.com/new", chinese ? "更新了" : "updated"],
      ["link", "deleted", "https://example.com/old", "", chinese ? "移除了" : "removed"],
    ]) {
      const activity = { ...base, field, verb, old_value: oldValue, new_value: newValue };
      const original = structuredClone(activity);
      const html = renderToStaticMarkup(React.createElement(ActivityMessage, { activity, showIssue: true }));
      assert.ok(html.includes(word), html);
      assert.ok(html.includes("Original &lt;title&gt;"), html);
      assert.ok(html.includes('href="/workspace/browse/TEST-1/"'), html);
      if (field === "labels") {
        assert.ok(html.includes("Label &lt;text&gt;"), html);
        assert.ok(html.includes("#123456"), html);
      }
      if (field === "link") {
        assert.ok(html.includes(`href="${verb === "created" ? newValue : oldValue}"`), html);
        assert.ok(html.includes(chinese ? "链接" : "link"), html);
        assert.ok(html.includes('rel="noopener noreferrer"'), html);
      }
      assert.deepEqual(activity, original);
    }
    const deleted = renderToStaticMarkup(
      React.createElement(ActivityMessage, {
        activity: { ...base, field: "issue", verb: "deleted", issue: null, issue_detail: null },
        showIssue: true,
      })
    );
    assert.ok(deleted.includes(chinese ? "此工作项已删除" : "This work item has been deleted"), deleted);
  }
});

test("profile project statistics and completion tooltip translate while preserving counts and names", async () => {
  for (const language of ["zh-CN", "en"]) {
    // oxlint-disable-next-line no-await-in-loop
    await i18n.setLanguage(language);
    for (const count of [0, 1, 2]) {
      const html = renderToStaticMarkup(
        React.createElement(ProfileSidebar, {
          userProjectsData: {
            user_data: { display_name: "Original user" },
            project_data: [
              {
                id: "project",
                created_issues: count,
                assigned_issues: count,
                pending_issues: count,
                completed_issues: count,
              },
            ],
          },
        })
      );
      for (const label of language === "zh-CN"
        ? ["已创建", "已分配", "待完成", "已完成"]
        : ["Created", "Assigned", "Due", "Completed"]) {
        assert.ok(html.includes(label), html);
      }
      if (count > 0) assert.ok(html.includes(language === "zh-CN" ? "完成率" : "Completion percentage"), html);
      assert.ok(html.includes("Original project") && html.includes("Original user"), html);
      assert.equal((html.match(new RegExp(`>${count} `, "g")) ?? []).length, 4, html);
    }
  }
});
