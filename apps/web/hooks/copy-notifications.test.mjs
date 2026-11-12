/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Locale cases run sequentially because identifier tests replace the global clipboard.
/* oxlint-disable no-await-in-loop */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const root = new URL("../../../", import.meta.url);
const dictionaries = Object.fromEntries(
  ["en", "zh-cn"].map((locale) => [
    locale,
    Object.assign(
      {},
      ...["common", "power-k", "wiki", "accessibility"].map((namespace) =>
        JSON.parse(readFileSync(new URL(`packages/i18n/src/locales/${locale}/${namespace}.json`, root), "utf8"))
      )
    ),
  ])
);

function harness(locale) {
  const toasts = [];
  const copies = [];
  let fail = false;
  let menuActions;
  const t = (key, params = {}) => {
    const value = key.split(".").reduce((node, part) => node?.[part], dictionaries[locale]);
    assert.equal(typeof value, "string", `Missing ${locale} translation: ${key}`);
    return value.replace(/\{(\w+)\}/g, (_, name) => params[name]);
  };
  const mocks = {
    "mobx-react": { observer: (component) => component },
    "@/components/common/quick-actions-helper": {
      useLayoutMenuItems: (props) => {
        menuActions = props;
        return [];
      },
      useViewMenuItems: (props) => {
        menuActions = props;
        return [];
      },
    },
    "@plane/blocks/context-menu": { getRenderableItems: () => [] },
    "@plane/constants": { EUserPermissions: {}, EUserPermissionsLevel: {} },
    "@/hooks/store/user": { useUser: () => ({}), useUserPermissions: () => ({ allowPermissions: () => false }) },
    "@/components/views/publish": { useViewPublish: () => ({}) },
    react: { useCallback: (fn) => fn, useMemo: (fn) => fn(), useState: (value) => [value, () => {}] },
    "react/jsx-runtime": require("react/jsx-runtime"),
    "@plane/i18n": { useTranslation: () => ({ t }) },
    "@plane/blocks/toast": { setToast: (toast) => toasts.push(toast) },
    "@plane/utils": {
      cn: () => "",
      copyUrlToClipboard: async (value) => {
        if (fail) throw new Error("Clipboard unavailable");
        copies.push(value);
      },
    },
    "@/hooks/use-collaborative-page-actions": { useCollaborativePageActions: () => ({}) },
    "./use-local-storage": { default: () => ({}) },
  };
  const load = (path) => {
    const code = ts.transpileModule(readFileSync(new URL(`apps/web/${path}`, root), "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
    }).outputText;
    const exports = {};
    new Function("exports", "require", code)(
      exports,
      (name) => mocks[name] ?? new Proxy({}, { get: (_, key) => String(key) })
    );
    return exports;
  };
  return {
    t,
    toasts,
    copies,
    load,
    copyMenuLink: () => menuActions.handleCopyLink(),
    failCopy: () => {
      fail = true;
    },
  };
}

test("identifier tooltip and successful copy use the selected language and preserve the ID", async () => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  try {
    for (const locale of ["zh-cn", "en", "zh-cn"]) {
      const h = harness(locale);
      Object.defineProperty(globalThis, "navigator", {
        configurable: true,
        value: {
          clipboard: {
            writeText: async (value) => h.copies.push(value),
          },
        },
      });
      const { IdentifierText } = h.load("components/issues/issue-detail/identifier-text.tsx");
      const node = IdentifierText({ identifier: "DEMO-42", enableClickToCopyIdentifier: true });
      assert.equal(node.props.label, h.t("common.tooltip.copy_to_clipboard"));
      node.props.children.props.onClick();
      await new Promise((resolve) => setImmediate(resolve));
      assert.deepEqual(h.copies, ["DEMO-42"]);
      assert.equal(h.toasts[0].title, h.t("power_k.contextual_actions.work_item.copy_id_toast_success"));
      assert.equal(IdentifierText({ identifier: "DEMO-42" }).type, "span");
    }
  } finally {
    if (original) Object.defineProperty(globalThis, "navigator", original);
    else delete globalThis.navigator;
  }
});

test("project and page copy notifications follow language and preserve target URLs", async () => {
  for (const locale of ["zh-cn", "en"]) {
    const h = harness(locale);
    const { useProjectActions } = h.load("components/navigation/use-project-actions.ts");
    const actions = useProjectActions({
      workspaceSlug: "team",
      projectId: "project",
      activeItem: { href: "/custom/view" },
    });
    await actions.handleCopyText();
    assert.equal(h.copies[0], "/custom/view");
    assert.equal(h.toasts[0].title, h.t("common.link_copied"));
    assert.equal(h.toasts[0].message, h.t("project_link_copied_to_clipboard"));
    const { usePageOperations } = h.load("hooks/use-page-operations.ts");
    await usePageOperations({ page: { getRedirectionLink: () => "/page/42" } }).pageOperations.copyLink();
    assert.equal(h.copies[1], "/page/42");
    assert.equal(h.toasts[1].message, h.t("wiki_collections.list.page_link_copied"));
    h.failCopy();
    await actions.handleCopyText();
    assert.equal(h.toasts[2].type, "error");
    assert.equal(h.toasts[2].title, h.t("common.clipboard_copy_failed"));
    assert.equal(h.toasts[2].message, h.t("something_went_wrong_please_try_again"));
  }
});

test("view and work item list copy messages localize the entity and keep the correct route", async () => {
  for (const locale of ["zh-cn", "en"]) {
    const h = harness(locale);
    const { LayoutQuickActions } = h.load("components/issues/layout-quick-actions.tsx");
    for (const storeType of ["PROJECT", "EPIC"]) {
      LayoutQuickActions({ workspaceSlug: "team", projectId: "project", storeType });
      await h.copyMenuLink();
      assert.equal(h.copies.at(-1), `team/projects/project/${storeType === "EPIC" ? "epics" : "issues"}`);
      assert.equal(
        h.toasts.at(-1).message,
        h.t("entity.link_copied_to_clipboard", {
          entity: h.t(storeType === "EPIC" ? "common.epics" : "common.work_items"),
        })
      );
    }
    const { ViewQuickActions } = h.load("components/views/quick-actions.tsx");
    ViewQuickActions({ workspaceSlug: "team", projectId: "project", view: { id: "view42" } });
    await h.copyMenuLink();
    assert.equal(h.copies.at(-1), "team/projects/project/views/view42");
    assert.equal(h.toasts.at(-1).title, h.t("common.link_copied"));
    assert.equal(h.toasts.at(-1).message, h.t("view_link_copied_to_clipboard"));
  }
});
