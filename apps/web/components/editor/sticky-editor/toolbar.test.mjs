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
      ...["common", "editor"].map((namespace) =>
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
const items = ["bold", "italic", "to-do-list"].map((itemKey) => ({ itemKey, renderKey: itemKey }));
const t = (key) => key.split(".").reduce((value, part) => value?.[part], dictionaries[locale]) ?? key;
const mocks = {
  react: { useState: (value) => [value, () => {}], useEffect: () => {}, useCallback: (callback) => callback },
  "react/jsx-runtime": require("react/jsx-runtime"),
  "@plane/i18n": { useTranslation: () => ({ t }) },
  "@plane/editor": { TOOLBAR_ITEMS: { sticky: { basic: items } } },
};
function load(path) {
  const exports = {};
  const code = ts.transpileModule(readFileSync(new URL(path, import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
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
  return [node, ...nodes(node.props?.children), ...nodes(node.props?.render)];
}
const { StickyEditorToolbar } = load("./toolbar.tsx");
const { ColorPalette, STICKY_COLORS_LIST } = load("./color-palette.tsx");
test("sticky toolbar tooltips and accessible labels follow language while retaining commands", () => {
  const commands = [];
  for (locale of ["zh-CN", "en", "zh-CN"]) {
    const tree = nodes(StickyEditorToolbar({ executeCommand: (item) => commands.push(item), editorRef: null }));
    assert.deepEqual(
      tree.filter((n) => n.type === "Tooltip").map((n) => n.props.label),
      ["background_color", "bold", "italic", "todo_list"].map((key) => t(`editor_ui.${key}`))
    );
    const buttons = tree.filter((n) => n.type === "ToolbarToggle");
    assert.deepEqual(
      buttons.map((n) => n.props["aria-label"]),
      ["bold", "italic", "todo_list"].map((key) => t(`editor_ui.${key}`))
    );
    buttons.forEach((button) => button.props.onPressedChange());
    assert.deepEqual(commands.splice(0), items);
    assert.equal(tree.find((n) => n.type === "IconButton").props["aria-label"], t("editor_controls.delete"));
    const colors = nodes(ColorPalette({ handleUpdate: (value) => commands.push(value) })).filter(
      (n) => n.type === "button"
    );
    assert.deepEqual(
      colors.map((n) => n.props["aria-label"]),
      STICKY_COLORS_LIST.map((color) => t(`editor_controls.colors.${color.key}`))
    );
    colors.forEach((button) => button.props.onClick());
    assert.deepEqual(
      commands.splice(0),
      STICKY_COLORS_LIST.map((color) => ({ background_color: color.key }))
    );
  }
});
