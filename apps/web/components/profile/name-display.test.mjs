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
const { renderToStaticMarkup } = require("react-dom/server");
const ts = require("typescript");
const h = React.createElement;
const empty = () => null;
const box = ({ children, render, label }) => h(React.Fragment, null, render, children, label);
const components = new Proxy({}, { get: (_target, key) => (key === "__esModule" ? false : box) });
let locale = "zh-CN";
let user;
const mocks = {
  react: React,
  "react/jsx-runtime": require("react/jsx-runtime"),
  "mobx-react": { observer: (component) => component },
  "next/link": { __esModule: true, default: ({ children, href }) => h("a", { href }, children) },
  "next/navigation": {
    useParams: () => ({ workspaceSlug: "team" }),
    useRouter: () => ({}),
    usePathname: () => "/spaces/team",
    useSearchParams: () => new URLSearchParams(),
  },
  "react-router": { Link: ({ children, to }) => h("a", { href: to }, children) },
  "react-hook-form": {},
  "@plane/constants": require("@plane/constants"),
  "@plane/types": require("@plane/types"),
  "@plane/utils": require("@plane/utils"),
  "@plane/services": {
    AuthService: class {
      requestCSRFToken() {
        return Promise.resolve({ csrf_token: "test" });
      }
    },
  },
  "@/hooks/store/use-user": { useUser: () => ({ data: user }) },
  "@/helpers/query-param-generator": { queryParamGenerator: () => ({ queryParam: "" }) },
  "@plane/i18n": { useTranslation: () => ({ currentLocale: locale, t: (key) => key }) },
  "@/hooks/store/user": { useUser: () => ({ data: user }) },
  "@/hooks/store/use-member": { useMember: () => ({ getUserDetails: () => user, project: {} }) },
  "@/hooks/store/use-instance": { useInstance: () => ({ config: { is_self_managed: true } }) },
  "@/hooks/store/use-app-theme": { useAppTheme: () => ({}) },
  "@/hooks/store/use-command-palette": { useCommandPalette: () => ({}) },
  "./switch-account-modal": { SwitchAccountModal: empty },
  "./switch-account-dropdown": { SwitchAccountDropdown: ({ fullName }) => fullName },
  "@/components/common/cover-image": { CoverImage: empty },
};
function load(path) {
  const code = ts.transpileModule(readFileSync(new URL(path, import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText;
  const exports = {};
  new Function("exports", "require", code)(exports, (id) => {
    if (id in mocks) return mocks[id];
    if (id.startsWith("@makeplane/propel/") || id.startsWith("@plane/blocks/")) return components;
    throw new Error(id);
  });
  return exports;
}
const SpaceUserAvatar = load("../../../space/components/issues/navbar/user-avatar.tsx").UserAvatar;
const OnboardingHeader = load("../onboarding/header.tsx").OnboardingHeader;
const surfaces = [
  ["public space account", SpaceUserAvatar, () => ({})],
  ["onboarding header", OnboardingHeader, () => ({ currentStep: "ROLE_SETUP", hasInvitations: false })],
  ["settings header", load("../settings/profile/sidebar/header.tsx").ProfileSettingsSidebarHeader, () => ({})],
  [
    "project members",
    load("../project/settings/member-columns.tsx").NameColumn,
    () => ({ rowData: { member: user }, workspaceSlug: "team", isAdmin: false }),
  ],
  [
    "workspace members",
    load("../workspace/settings/member-columns.tsx").NameColumn,
    () => ({ rowData: { member: user, is_active: true }, workspaceSlug: "team", isAdmin: false }),
  ],
  ["editor user card", load("../editor/embeds/mentions/user.tsx").EditorUserMention, () => ({ id: user.id })],
  ["switch account", load("../onboarding/switch-account-dropdown.tsx").SwitchAccountDropdown, () => ({})],
  ["workspace menu", load("../workspace/sidebar/user-menu-root.tsx").UserMenuRoot, () => ({})],
];
for (const [name, Component, props] of surfaces) {
  test(`${name} follows language changes without changing profile links or stored fields`, () => {
    for (const [language, first, last, expected] of [
      ["zh-CN", "三", "张", "张三"],
      ["zh-TW", "明", "陳", "陳明"],
      ["en", "John", "Smith", "John Smith"],
      ["zh-CN", "", "张", "张"],
    ]) {
      locale = language;
      user = {
        id: "person",
        first_name: first,
        last_name: last,
        email: "person@example.com",
        display_name: name === "public space account" || name === "onboarding header" ? "" : "nickname",
      };
      const original = structuredClone(user);
      const html = renderToStaticMarkup(h(Component, props()));
      assert.ok(html.includes(expected), `${name}/${locale}: ${html}`);
      if (name.includes("members") || name.includes("editor")) assert.ok(html.includes('href="/team/profile/person"'));
      assert.deepEqual(user, original);
    }
  });
}

test("account headers preserve a chosen nickname and fall back to email when name fields are absent", () => {
  locale = "zh-CN";
  for (const Component of [SpaceUserAvatar, OnboardingHeader]) {
    for (const displayName of ["chosen nickname", ""]) {
      user = { id: "person", first_name: "", last_name: "", display_name: displayName, email: "person@example.com" };
      const html = renderToStaticMarkup(h(Component, { currentStep: "ROLE_SETUP", hasInvitations: false }));
      assert.ok(html.includes(displayName || user.email), html);
      assert.ok(!html.includes("undefined"), html);
    }
  }
});
