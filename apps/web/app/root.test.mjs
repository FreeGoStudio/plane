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
const requireBlocks = createRequire(new URL("../../../packages/blocks/package.json", import.meta.url));
const { JSDOM } = requireBlocks("jsdom");
const React = require("react");
const { renderToString } = require("react-dom/server");
const { hydrateRoot } = require("react-dom/client");
const ts = require("typescript");
const source = readFileSync(new URL("./root.tsx", import.meta.url), "utf8");
const ast = ts.createSourceFile("root.tsx", source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const fallback = ast.statements.find((node) => ts.isFunctionDeclaration(node) && node.name?.text === "HydrateFallback");
assert.ok(fallback);
const { outputText } = ts.transpileModule(fallback.getText(ast), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
});
let theme;
const exports = {};
new Function("exports", "require", "useState", "useEffect", "useTheme", "LogoSpinner", outputText)(
  exports,
  require,
  React.useState,
  React.useEffect,
  () => ({ resolvedTheme: theme }),
  () => React.createElement("img", { alt: "logo", src: theme === "dark" ? "/dark.gif" : "/light.gif" })
);

for (const initialTheme of ["light", "dark", undefined]) {
  test(`hydrates the prerendered fallback when browser theme is ${initialTheme}`, async () => {
    theme = undefined;
    const html = renderToString(React.createElement(exports.HydrateFallback));
    assert.equal(html, "<div></div>");
    const dom = new JSDOM(`<div id="root">${html}</div>`, { url: "http://localhost" });
    globalThis.window = dom.window;
    globalThis.document = dom.window.document;
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    theme = initialTheme;
    const errors = [];
    let root;
    try {
      await React.act(async () => {
        root = hydrateRoot(
          document.getElementById("root"),
          React.createElement(React.StrictMode, null, React.createElement(exports.HydrateFallback)),
          { onRecoverableError: (error) => errors.push(error.message) }
        );
      });
      assert.deepEqual(errors, [], "server and first client markup must agree");
      if (initialTheme === undefined) {
        assert.equal(document.querySelector("img"), null);
        theme = "dark";
        await React.act(() =>
          root.render(React.createElement(React.StrictMode, null, React.createElement(exports.HydrateFallback)))
        );
      }
      assert.equal(document.querySelector("img")?.getAttribute("src"), theme === "dark" ? "/dark.gif" : "/light.gif");
    } finally {
      if (root) await React.act(() => root.unmount());
      dom.window.close();
      delete globalThis.window;
      delete globalThis.document;
      delete globalThis.IS_REACT_ACT_ENVIRONMENT;
    }
  });
}
