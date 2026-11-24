// Copyright (c) 2023-present Plane Software, Inc. and contributors
// SPDX-License-Identifier: AGPL-3.0-only
// See the LICENSE file for details.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { runInNewContext } from "node:vm";
import { setImmediate } from "node:timers/promises";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const source = readFileSync(
  new URL("../components/issues/issue-detail-widgets/sub-issues/wbs.tsx", import.meta.url),
  "utf8"
);
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
});

function find(node) {
  if (node?.props?.label === "wbs.update_wbs") return node;
  return [node?.props?.children].flat(Infinity).filter(Boolean).map(find).find(Boolean);
}

// Exercise the component's submit callback with isolated hooks and service boundaries.
async function clickUpdate(previous, returned, failure) {
  const toasts = [];
  const states = [];
  const data = { results: previous ? [previous] : [], source_version: "v1", csrf_token: "csrf", can_start: true };
  let index = 0;
  const dependencies = {
    react: {
      useState: (initial) => {
        const slot = index++;
        states[slot] = slot === 0 ? data : initial;
        return [
          states[slot],
          (value) => {
            states[slot] = value;
          },
        ];
      },
      useRef: (value) => ({ current: value }),
      useCallback: (value) => value,
      useEffect: () => undefined,
    },
    "react/jsx-runtime": { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
    "@makeplane/propel/components/button": { Button: "Button" },
    "@plane/i18n": { useTranslation: () => ({ t: (key) => key }) },
    "@plane/blocks/toast": { setToast: (toast) => toasts.push(toast) },
    "@/services/repository.service": {
      repositoryBase: () => "/api/",
      repositoryService: {
        write: async () => {
          if (failure === "write") throw Error("Offline");
          return returned;
        },
        read: async () => {
          if (failure === "refresh") throw Error("Offline");
          return data;
        },
      },
    },
    "./requirement-review": {},
    "./wbs-changes": {},
    "./wbs-update": { choicesComplete: () => false, readinessMessageKey: () => undefined },
  };
  const exports = {};
  runInNewContext(outputText, { exports, require: (name) => dependencies[name], crypto });
  const tree = exports.WbsPanel({ workspaceSlug: "test", projectId: "project", issueId: "issue", disabled: false });
  find(tree).props.onClick();
  await setImmediate();
  return { toasts, error: states[1] };
}

for (const status of ["queued", "running", "ready"]) {
  test(`repeated update visibly acknowledges the existing ${status} analysis`, async () => {
    const run = { id: "existing", status, result: {} };
    const { toasts } = await clickUpdate(run, run);
    assert.equal(toasts.length, 1);
    assert.equal(toasts[0].title, `wbs.status_${status}`);
    assert.equal(toasts[0].message, "wbs.update_reused");
  });
}
test("new analysis reports submission without claiming the draft is ready", async () => {
  const { toasts } = await clickUpdate(undefined, { id: "new", status: "queued" });
  assert.equal(toasts[0].message, "wbs.update_submitted");
});
for (const failure of ["write", "refresh"]) {
  test(`${failure} failure retains an error without a success notice`, async () => {
    const { toasts, error } = await clickUpdate(undefined, { id: "new", status: "queued" }, failure);
    assert.equal(toasts.length, 0);
    assert.ok(error);
  });
}
