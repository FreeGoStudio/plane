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
    Object.assign(
      {},
      ...["common", "editor", "work-item"].map((namespace) =>
        JSON.parse(
          readFileSync(
            new URL(`../../../../../packages/i18n/src/locales/${language}/${namespace}.json`, import.meta.url),
            "utf8"
          )
        )
      )
    ),
  ])
);
const t = (key) => {
  const value = key.split(".").reduce((node, part) => node?.[part], dictionaries[locale]);
  assert.equal(typeof value, "string", `Missing translation: ${key}`);
  return value;
};
const mocks = {
  react: { useState: (value) => [value, () => {}], useEffect: () => {}, useCallback: (callback) => callback },
  "react/jsx-runtime": require("react/jsx-runtime"),
  "mobx-react": { observer: (component) => component },
  "@plane/i18n": { getUserDisplayName: require("@plane/i18n").getUserDisplayName, useTranslation: () => ({ t }) },
  "@plane/constants": { EIssueCommentAccessSpecifier: { INTERNAL: "INTERNAL", EXTERNAL: "EXTERNAL" } },
  "@plane/types": { EIssueCommentAccessSpecifier: { INTERNAL: "INTERNAL", EXTERNAL: "EXTERNAL" } },
  "@plane/hooks": { useHashScroll: () => ({ isHashMatch: false }) },
  "next/navigation": { usePathname: () => "/work-item" },
  "@/hooks/store/use-member": { useMember: () => ({ getUserDetails: () => ({ display_name: "Alice" }) }) },
  "@plane/utils": {
    getFileURL: (url) => url,
    useDateFormatter: () => ({
      renderFormattedDate: () => "2026-11-12",
      renderFormattedTime: () => "10:30",
      calculateTimeAgo: () => "now",
    }),
  },
};
function load(path) {
  const exports = {};
  const code = ts.transpileModule(readFileSync(new URL(path, import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText;
  new Function("exports", "require", code)(
    exports,
    (name) => mocks[name] ?? new Proxy({}, { get: (_, key) => String(key) })
  );
  return exports;
}
function nodes(node) {
  if (Array.isArray(node)) return node.flatMap(nodes);
  if (!node || typeof node !== "object") return [];
  return [node, ...nodes(node.props?.children), ...nodes(node.props?.header)];
}
const { TOOLBAR_ITEMS } = load("../../../../../packages/editor/src/constants/common.ts");
mocks["@plane/editor"] = { TOOLBAR_ITEMS };
const { IssueCommentToolbar } = load("./toolbar.tsx");
const { CommentCardDisplay } = load("../../comments/card/display.tsx");

test("comment toolbar translates every tooltip and accessible label without changing commands or shortcuts", () => {
  const expectedKeys = [
    "bold",
    "italic",
    "underline",
    "strikethrough",
    "align_left",
    "align_center",
    "align_right",
    "bulleted_list",
    "numbered_list",
    "todo_list",
    "quote",
    "code",
    "image",
  ];
  const items = Object.values(TOOLBAR_ITEMS.lite).flat();
  for (locale of ["zh-CN", "en", "zh-CN"]) {
    const commands = [];
    const tree = nodes(
      IssueCommentToolbar({
        executeCommand: (item) => commands.push(item),
        editorRef: null,
        showAccessSpecifier: true,
        accessSpecifier: "INTERNAL",
      })
    );
    const labels = [t("private"), t("public"), ...expectedKeys.map((key) => t(`editor_ui.${key}`))];
    const tooltips = tree.filter((node) => node.type === "Tooltip");
    assert.deepEqual(
      tooltips.map((node) => node.props.label),
      labels
    );
    const buttons = tree.filter((node) => ["ToolbarToggle", "ToolbarButton"].includes(node.type));
    assert.deepEqual(
      buttons.map((node) => node.props["aria-label"]),
      labels
    );
    buttons.slice(2).forEach((button) => (button.props.onPressedChange ?? button.props.onClick)());
    assert.deepEqual(commands, items);
    assert.deepEqual(
      tooltips.slice(2).map((node) => node.props.shortcut),
      items.map((item) => item.shortcut?.join(" + "))
    );
  }
});

test("comment headers localize action and edited marker while retaining author and content", () => {
  for (locale of ["zh-CN", "en"]) {
    const tree = nodes(
      CommentCardDisplay({
        comment: {
          id: "comment",
          actor: "author",
          comment_html: "<p>Hello</p>",
          created_at: "2026-11-12",
          edited_at: "2026-11-12",
        },
        disabled: true,
        readOnlyEditorRef: { current: null },
        activityOperations: { userReactions: () => [], reactionIds: () => ({}) },
      })
    );
    const header = tree.find((node) => node.type === "ActivityCommentHeader");
    assert.equal(header.props.action, t("issue.comments.commented"));
    assert.equal(header.props.author, "Alice");
    assert.equal(header.props.timestamp.props.tooltip, "2026-11-12 10:30");
    assert.ok(header.props.timestamp.props.children.includes(` (${t("edited")})`));
    assert.equal(tree.find((node) => node.type === "LiteTextEditor").props.initialValue, "<p>Hello</p>");
  }
});
