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

function find(node, label = "wbs.update_wbs") {
  if (node?.props?.label === label) return node;
  return [node?.props?.children]
    .flat(Infinity)
    .filter(Boolean)
    .map((child) => find(child, label))
    .find(Boolean);
}

// Exercise the component's submit callback with isolated hooks and service boundaries.
async function clickUpdate(previous, returned, failure, mode = "update", options = {}) {
  const writes = [];
  const toasts = [];
  const states = [];
  const data = { results: previous ? [previous] : [], source_version: "v1", csrf_token: "csrf", can_start: true };
  let index = 0;
  const dependencies = {
    react: {
      useState: (initial) => {
        const slot = index++;
        states[slot] = slot === 0 ? data : slot === 4 ? (options.confirmed ?? true) : initial;
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
        write: async (...args) => {
          writes.push(args);
          if (failure === "write") throw Error("Offline");
          if (failure && typeof failure === "object") throw Object.assign(Error("Request failed"), failure);
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
    "./wbs-update": { choicesComplete: () => false },
    "./wbs-messages": require("../components/issues/issue-detail-widgets/sub-issues/wbs-messages.ts"),
  };
  const exports = {};
  runInNewContext(outputText, { exports, require: (name) => dependencies[name], crypto });
  const tree = exports.WbsPanel({
    workspaceSlug: "test",
    projectId: "project",
    issueId: "issue",
    disabled: options.disabled ?? false,
  });
  const button = find(tree, mode === "regenerate" ? "wbs.regenerate" : "wbs.update_wbs");
  if (button && !button.props.disabled) button.props.onClick();
  await setImmediate();
  await (options.moreClicks || []).reduce(async (previousClick, label) => {
    await previousClick;
    find(tree, label).props.onClick();
    await setImmediate();
  }, Promise.resolve());
  return { toasts, error: states[1], errorDetails: states[2], tree, writes };
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

test("server conflicts are localized instead of displaying raw JSON", async () => {
  const { error, toasts } = await clickUpdate(undefined, undefined, {
    response: { data: { detail: "PRD changed; update WBS again" } },
  });
  assert.equal(error, "wbs.server_prd_changed_update_wbs_again");
  assert.equal(toasts.length, 0);
});
test("worker and readiness diagnostics both render through translation keys", async () => {
  const run = {
    id: "run",
    status: "ready",
    result: {},
    error: "ReadTimeout",
    readiness: { can_apply: false, reason: "Child tasks changed; update WBS again" },
  };
  const { tree } = await clickUpdate(run, run);
  const rendered = JSON.stringify(tree);
  assert.ok(rendered.includes("wbs.server_readtimeout"));
  assert.ok(rendered.includes("wbs.server_child_tasks_changed_update_wbs_again"));
  assert.ok(!rendered.includes("ReadTimeout"));
});
test("unrecognized errors retain diagnostics alongside the localized fallback", async () => {
  const details = { fields: ["New server reason"] };
  const { error, errorDetails } = await clickUpdate(undefined, undefined, { response: { data: details } });
  assert.equal(error, "wbs.server_error_unknown");
  assert.equal(errorDetails, JSON.stringify(details));
});

test("regenerate submits explicit mode and reports fresh analysis", async () => {
  const { writes, toasts } = await clickUpdate(
    { id: "old", status: "ready", result: {} },
    { id: "new", status: "queued" },
    undefined,
    "regenerate"
  );
  assert.equal(writes.length, 1);
  assert.equal(writes[0][3].mode, "regenerate");
  assert.equal(writes[0][3].confirmed, true);
  assert.equal(toasts[0].message, "wbs.update_submitted");
});
for (const status of ["queued", "running"]) {
  test(`regenerate disabled during ${status}`, async () => {
    const { writes, tree } = await clickUpdate({ id: "old", status, result: {} }, undefined, undefined, "regenerate");
    assert.equal(find(tree, "wbs.regenerate").props.disabled, true);
    assert.equal(writes.length, 0);
  });
}
for (const options of [{ confirmed: false }, { disabled: true }]) {
  test(`regenerate respects confirmation and permissions: ${JSON.stringify(options)}`, async () => {
    const { writes } = await clickUpdate(
      { id: "old", status: "ready", result: {} },
      undefined,
      undefined,
      "regenerate",
      options
    );
    assert.equal(writes.length, 0);
  });
}
test("regenerate is hidden before first analysis", async () => {
  const { tree, writes } = await clickUpdate(undefined, undefined, undefined, "regenerate");
  assert.equal(find(tree, "wbs.regenerate"), undefined);
  assert.equal(writes.length, 0);
});
test("regenerate conflict is localized", async () => {
  const { error, toasts } = await clickUpdate(
    { id: "old", status: "ready", result: {} },
    undefined,
    { response: { data: { detail: "WBS analysis is in progress; wait before regenerating" } } },
    "regenerate"
  );
  assert.equal(error, "wbs.regenerate_in_progress");
  assert.equal(toasts.length, 0);
});

test("uncertain regeneration retries its key while update uses a separate key", async () => {
  const { writes, toasts } = await clickUpdate(
    { id: "old", status: "ready", result: {} },
    undefined,
    "write",
    "regenerate",
    { moreClicks: ["wbs.update_wbs", "wbs.regenerate"] }
  );
  assert.equal(writes.length, 3);
  assert.equal(writes[0][3].idempotency_key, writes[2][3].idempotency_key);
  assert.notEqual(writes[0][3].idempotency_key, writes[1][3].idempotency_key);
  assert.equal(toasts.length, 0);
});
