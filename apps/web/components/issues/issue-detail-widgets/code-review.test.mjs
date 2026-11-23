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
const output = {};
const code = ts.transpileModule(readFileSync(new URL("./code-review-report.tsx", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
new Function("exports", "require", code)(output, (name) => {
  if (name === "react/jsx-runtime") return require(name);
  if (name === "@plane/i18n") return { useTranslation: () => ({ t: (key) => key }) };
  throw new Error(name);
});
test("partial coverage exposes missing files and cannot present an acceptance action", () => {
  const html = renderToStaticMarkup(
    React.createElement(output.CodeReviewReport, {
      run: {
        id: "r1",
        status: "partial",
        source_sha: "a",
        target_sha: "b",
        merge_base: "c",
        report: {
          summary: "partial",
          findings: [{ path: "src/a.py", line: 2, severity: "high", message: "<script>bad</script>" }],
          coverage: { diff_files: ["src/a.py", "src/b.py"], missing: ["src/b.py"], excluded: [] },
        },
      },
    })
  );
  assert.match(html, /src\/b.py/);
  assert.match(html, /src\/a.py:2/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
});
