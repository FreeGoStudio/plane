/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import ts from "typescript";
import { setLanguage } from "../src/core/set-language";
import { translate } from "../src/core/translate";

const require = createRequire(import.meta.url);

// Exercise the actual application functions with their browser/store boundaries stubbed.
function loadApplicationModule(relativePath: string, imports: Record<string, unknown>) {
  const filename = new URL(`../../../apps/web/${relativePath}`, import.meta.url);
  const { outputText } = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
  });
  const module = { exports: {} as Record<string, any> };
  new Function("require", "exports", "module", outputText)(
    (name: string) => (name in imports ? imports[name] : require(name)),
    module.exports,
    module
  );
  return module.exports;
}

test("filter names are searchable in Chinese without translating user-defined labels", async () => {
  const { getFilterPropertyLabel } = loadApplicationModule("components/rich-filters/property-label.ts", {});
  await setLanguage("zh-CN");
  assert.equal(getFilterPropertyLabel("priority", "Priority", translate), "优先级");
  assert.equal(getFilterPropertyLabel("customer_field", "Customer status", translate), "Customer status");
  const fields = ["start_date", "target_date", "priority"];
  assert.deepEqual(
    fields.filter((field) => getFilterPropertyLabel(field, "", translate).includes("日期")),
    ["start_date", "target_date"]
  );
  await setLanguage("en");
  assert.equal(getFilterPropertyLabel("priority", "Priority", translate), "Priority");
});

test("analytics duration options resolve in both languages", async () => {
  const checkLabels = (locale: string) => {
    for (const duration of ["yesterday", "last_7_days", "last_30_days", "last_3_months"]) {
      const key = `workspace_analytics.chart.${duration}`;
      const label = translate(key);
      assert.notEqual(label, key);
      if (locale === "zh-CN") assert.match(label, /[\u4e00-\u9fff]/);
    }
  };
  await setLanguage("zh-CN");
  checkLabels("zh-CN");
  await setLanguage("en");
  checkLabels("en");
});

test("authentication errors follow language changes without changing codes or the public call signature", async () => {
  const { authErrorHandler, EAuthenticationErrorCodes: codes } = loadApplicationModule(
    "helpers/authentication.helper.tsx",
    {
      "@plane/i18n": { translate },
      "@plane/constants": { SUPPORT_EMAIL: "support@example.test" },
      "next/link": { __esModule: true, default: "a" },
    }
  );
  await setLanguage("zh-CN");
  const chinese = authErrorHandler(codes.INVALID_EMAIL);
  assert.equal(chinese.code, codes.INVALID_EMAIL);
  assert.match(chinese.title, /[\u4e00-\u9fff]/);
  assert.match(chinese.message, /[\u4e00-\u9fff]/);
  assert.equal(authErrorHandler("unknown"), undefined);
  assert.equal(authErrorHandler(codes.PASSWORD_TOO_SHORT).code, codes.PASSWORD_TOO_SHORT);
  await setLanguage("en");
  const english = authErrorHandler(codes.INVALID_EMAIL);
  assert.equal(english.code, chinese.code);
  assert.equal(english.type, chinese.type);
  assert.equal(english.title, "Invalid email");
  assert.notEqual(english.message, chinese.message);
});

test("localized page operations retain collaboration commands, success and failure behavior", async () => {
  const toasts: Array<{ type: string; title: string; message: string }> = [];
  const commands: unknown[] = [];
  let failDuplicate = false;
  let duplicates = 0;
  const { usePageOperations } = loadApplicationModule("hooks/use-page-operations.ts", {
    "@plane/i18n": { useTranslation: () => ({ t: translate }) },
    react: { useMemo: (factory: () => unknown) => factory() },
    "@plane/constants": { IS_FAVORITE_MENU_OPEN: "favorite-menu-open" },
    "@plane/blocks/toast": { setToast: (toast: (typeof toasts)[number]) => toasts.push(toast) },
    "@plane/types": { EPageAccess: { PUBLIC: 0, PRIVATE: 1 } },
    "@plane/utils": { copyUrlToClipboard: async () => {} },
    "@/hooks/use-collaborative-page-actions": {
      useCollaborativePageActions: () => ({
        executeCollaborativeAction: async (command: unknown) => {
          commands.push(command);
        },
      }),
    },
    "./use-local-storage": { __esModule: true, default: () => ({ setValue: () => {}, storedValue: true }) },
  });
  const page = {
    access: 0,
    archived_at: null,
    is_favorite: false,
    is_locked: false,
    getRedirectionLink: () => "/workspace/projects/project/pages/page",
    addToFavorites: async () => {},
    removePageFromFavorites: async () => {},
    duplicate: async () => {
      duplicates++;
      if (failDuplicate) throw new Error("fixture failure");
    },
  };
  await setLanguage("zh-CN");
  const chinese = usePageOperations({ page }).pageOperations;
  await chinese.duplicate();
  assert.equal(duplicates, 1);
  assert.equal(toasts.at(-1)?.type, "success");
  assert.match(toasts.at(-1)!.message, /[\u4e00-\u9fff]/);
  await chinese.toggleAccess();
  await chinese.toggleArchive();
  await chinese.toggleLock();
  assert.deepEqual(
    commands,
    ["make-private", "archive", "lock"].map((message) => ({ type: "sendMessageToServer", message }))
  );
  failDuplicate = true;
  await chinese.duplicate();
  assert.equal(toasts.at(-1)?.type, "error");
  assert.match(toasts.at(-1)!.message, /[\u4e00-\u9fff]/);
  await setLanguage("en");
  failDuplicate = false;
  await usePageOperations({ page }).pageOperations.duplicate();
  assert.equal(toasts.at(-1)?.message, "Page duplicated successfully.");
});
