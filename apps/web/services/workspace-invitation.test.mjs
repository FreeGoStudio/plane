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
function load(path, mocks) {
  const source = readFileSync(new URL(path, import.meta.url), "utf8");
  const code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText;
  const exports = {};
  new Function("require", "exports", code)((id) => {
    if (id in mocks) return mocks[id];
    throw new Error(`Unexpected dependency: ${id}`);
  }, exports);
  return exports;
}
const invitation = "/workspace-invitations/?invitation_id=example&slug=team&token=a.b-c_d#invite";
test("401 login redirect round-trips all invitation parameters and does not loop on login", async () => {
  let rejectResponse;
  const redirects = [];
  const { APIService } = load("./api.service.ts", {
    axios: {
      create: () => ({
        interceptors: {
          request: { use: () => {} },
          response: {
            use: (_success, failure) => {
              rejectResponse = failure;
            },
          },
        },
      }),
    },
    "@plane/services": { normalizeAPIRequestURL: (url) => url },
  });
  const service = new APIService("");
  assert.ok(service);
  const originalWindow = globalThis.window;
  try {
    const url = new URL(invitation, "http://localhost:8088");
    globalThis.window = {
      location: {
        pathname: url.pathname,
        search: url.search,
        hash: url.hash,
        replace: (value) => redirects.push(value),
      },
    };
    const error = { response: { status: 401 } };
    await assert.rejects(rejectResponse(error));
    assert.equal(new URL(redirects[0], url.origin).searchParams.get("next_path"), invitation);
    globalThis.window.location.pathname = "/";
    await assert.rejects(rejectResponse(error));
    assert.equal(redirects.length, 1);
    await assert.rejects(rejectResponse({ response: { status: 403 } }));
    assert.equal(redirects.length, 1);
  } finally {
    globalThis.window = originalWindow;
  }
});
test("incomplete invitations show an actionable error; complete invitations can still be accepted", async () => {
  let params;
  let swrKey;
  let result = {};
  const joined = [];
  const navigated = [];
  const { default: Page } = load("../app/(all)/workspace-invitations/page.tsx", {
    "react/jsx-runtime": require("react/jsx-runtime"),
    "mobx-react": { observer: (component) => component },
    "next/link": { __esModule: true, default: "a" },
    "next/navigation": { useSearchParams: () => params },
    swr: {
      __esModule: true,
      default: (key) => {
        swrKey = key;
        return result;
      },
    },
    "@makeplane/propel/components/anchor-button": { AnchorButton: "a" },
    "@makeplane/propel/components/button": { Button: "button" },
    "@plane/blocks/empty-state": { EmptyStateDetailed: "empty" },
    "@/components/common/logo-spinner": { LogoSpinner: "spinner" },
    "@plane/constants": { WORKSPACE_INVITATION: (id) => id },
    "@/helpers/authentication.helper": { EPageTypes: { PUBLIC: "public" } },
    "@/hooks/store/user": { useUser: () => ({ data: { email: "invitee@example.com" } }) },
    "@/hooks/use-app-router": { useAppRouter: () => ({ push: (path) => navigated.push(path) }) },
    "@/lib/wrappers/authentication-wrapper": { AuthenticationWrapper: "wrapper" },
    "@/services/workspace.service": {
      WorkspaceService: class {
        joinWorkspace(...args) {
          joined.push(args);
          return Promise.resolve();
        }
      },
    },
  });
  for (const missing of ["all", "invitation_id", "slug", "token"]) {
    params = new URL(invitation, "http://localhost").searchParams;
    if (missing === "all") params = new URLSearchParams();
    else params.delete(missing);
    const state = Page().props.children.props.children;
    assert.equal(swrKey, false);
    assert.equal(state.props.title, "This invitation link is incomplete.");
    assert.equal(state.props.customButton.props.render.props.href, "/");
  }
  params = new URL(invitation, "http://localhost").searchParams;
  result = { data: { id: "example", email: "invitee@example.com", workspace: { slug: "team", name: "Team" } } };
  const state = Page().props.children.props.children;
  assert.equal(swrKey, "example");
  state.props.actions[0].onClick();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(joined, [["team", "example", { accepted: true, token: "a.b-c_d" }]]);
  assert.deepEqual(navigated, ["/team"]);
});
