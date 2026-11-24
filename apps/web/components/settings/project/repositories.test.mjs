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
function load(file, mocks = {}) {
  const source = readFileSync(new URL(file, import.meta.url), "utf8");
  const code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const exports = {};
  new Function("exports", "require", code)(exports, (name) => mocks[name] ?? require(name));
  return exports;
}
const sections = load("./repository-sections.ts");
const rows = [
  { id: "docs", path: "team/project-documentation", purpose: "documentation" },
  { id: "prototype", path: "team/project-prototype", purpose: "prototype" },
  { id: "code", path: "team/backend", purpose: "development" },
  { id: "code-2", path: "team/frontend", purpose: "development" },
  { id: "reference", path: "team/reference", purpose: "reference" },
  { id: "replacement", path: "team/replacement-docs", purpose: "documentation" },
].map((row) =>
  Object.assign(row, {
    enabled: true,
    instance_id: "gitlab",
    instance_name: "Company GitLab",
    provider: "gitlab",
    default_branch: "main",
    credential_id: "mine",
    anonymous: false,
  })
);
const bindings = { revision: 7, documentation_repository_id: "docs", prototype_repository_id: "prototype" };
const info = {
  can_manage: true,
  csrf_token: "test",
  hosts: [{ id: "gitlab", oauth_available: true }],
  credentials: [{ id: "mine", label: "Personal", external_actor_label: "tester", expires_at: "2020-01-01T00:00:00Z" }],
};

for (const section of sections.repositorySections) {
  test(`${section}: only its repositories appear, with no loss of replacement candidates`, () => {
    const filtered = rows.filter((row) => sections.repositorySection(row, bindings) === section);
    assert.deepEqual(
      filtered.map((row) => row.id),
      {
        documentation: ["docs", "replacement"],
        prototype: ["prototype"],
        development: ["code", "code-2"],
        reference: ["reference"],
      }[section]
    );
  });
}
test("legacy and OAuth links resolve the target category; explicit navigation overrides the target", () => {
  assert.equal(sections.selectedRepositorySection(new URLSearchParams(), rows, bindings), "documentation");
  assert.equal(
    sections.selectedRepositorySection(new URLSearchParams("repository=code&connection=connected"), rows, bindings),
    "development"
  );
  assert.equal(
    sections.selectedRepositorySection(new URLSearchParams("repository=prototype&section=reference"), rows, bindings),
    "reference"
  );
  assert.equal(
    sections.selectedRepositorySection(new URLSearchParams("section=unknown&repository=prototype"), rows, bindings),
    "prototype"
  );
});
test("disabled and unknown-purpose repositories remain accessible, and binding takes precedence", () => {
  assert.equal(sections.repositorySection({ id: "new", purpose: "future", enabled: false }, bindings), "reference");
  assert.equal(
    sections.repositorySection({ id: "docs", purpose: "development", enabled: false }, bindings),
    "documentation"
  );
});
const button = ({ label, children, stretch: _stretch, variant: _variant, ...props }) =>
  React.createElement("button", props, label ?? children);
function renderPage(section, overrides = {}, repositoryRows = rows) {
  const currentInfo = { ...info, ...overrides };
  const mocks = {
    swr: {
      default: (url) => ({
        data: url.endsWith("repository-bindings/")
          ? bindings
          : url.endsWith("repository-connections/")
            ? currentInfo
            : repositoryRows,
      }),
    },
    "react-router": { useSearchParams: () => [new URLSearchParams(`section=${section}`)] },
    "@makeplane/propel/components/button": { Button: button },
    "@makeplane/propel/components/input": { Input: "input" },
    "@plane/i18n": { useTranslation: () => ({ t: (key) => key }) },
    "@/components/settings/content-wrapper": {
      SettingsContentWrapper: ({ children }) => React.createElement("main", null, children),
    },
    "@/components/settings/heading": { SettingsHeading: ({ title }) => React.createElement("h1", null, title) },
    "./repository-management": {
      RepositoryInitialization: () => null,
      RepositoryMemberPermissions: () => React.createElement("span", null, "member-permissions"),
    },
    "./repository-add": {
      RepositoryAdd: ({ section: addSection }) =>
        React.createElement("span", { "data-add-section": addSection }, "repository_ui.add"),
    },
    "./repository-sections": sections,
    "@/services/repository.service": { repositoryBase: () => "/test/", repositoryService: {} },
  };
  const { ProjectRepositoriesSettings } = load("./repositories.tsx", mocks);
  return renderToStaticMarkup(
    React.createElement(ProjectRepositoriesSettings, { workspaceSlug: "test", projectId: "test" })
  );
}
test("code list renders both names, expired connection status and collapsed details", () => {
  const html = renderPage("development");
  assert.match(html, /backend/);
  assert.match(html, /frontend/);
  assert.doesNotMatch(html, /project-documentation|project-prototype/);
  assert.match(html, /repository_ui.expired/);
  assert.match(html, /id="repository-details-code" hidden=""/);
  assert.match(html, /aria-expanded="false"/);
  for (const action of [
    "connect",
    "disconnect",
    "connection_options",
    "verify_save",
    "manage",
    "disable",
    "browse",
    "add",
  ])
    assert.match(html, new RegExp(`repository_ui.${action}`));
  assert.match(html, /member-permissions/);
});
test("default document binding retains change-binding control and candidates", () => {
  const html = renderPage("documentation");
  assert.match(html, /repository_ui.change_binding/);
  assert.match(html, /replacement-docs/);
});
test("non-admin keeps personal access and browsing but has no binding/member/configuration controls", () => {
  const html = renderPage("documentation", { can_manage: false });
  assert.match(html, /repository_ui.browse/);
  assert.match(html, /repository_ui.verify_save/);
  assert.doesNotMatch(html, /repository_ui.change_binding|member-permissions|repository_ui.manage|repository_ui.add/);
});
test("add repository defaults to the current category", () => {
  for (const section of sections.repositorySections)
    assert.match(renderPage(section), new RegExp(`data-add-section="${section}"`));
});
test("GitHub offers selected installation and only the matching App connection, without PAT entry", () => {
  const githubRows = [{ ...rows[2], provider: "github", instance_id: "github", external_id: "123" }];
  const html = renderPage(
    "development",
    {
      hosts: [{ id: "github", oauth_available: true, install_url: "https://github.com/apps/reader/installations/new" }],
      credentials: [
        {
          id: "app",
          instance_id: "github",
          kind: "github_app",
          github_repository_id: "123",
          label: "matching-app",
          expires_at: "2020-01-01T00:00:00Z",
        },
        {
          id: "other",
          instance_id: "github",
          kind: "github_app",
          github_repository_id: "456",
          label: "other-repository",
        },
        { id: "pat", instance_id: "github", kind: "https_token", label: "legacy-pat" },
      ],
    },
    githubRows
  );
  assert.match(html, /https:\/\/github.com\/apps\/reader\/installations\/new/);
  assert.match(html, /matching-app/);
  assert.doesNotMatch(html, /other-repository|legacy-pat|name="token"|repository_ui.verify_save/);
  assert.match(html, /repository_ui.anonymous/);
});

for (const provider of ["github", "gitlab"]) {
  test(`${provider}: setup submits the correct application fields and clears the secret`, async () => {
    const guide = {
      instance_id: "host",
      provider,
      web_url: "https://github.com",
      api_url: "https://api.github.com",
      create_url: "https://github.com/settings/apps/new",
      homepage_url: "https://plane.test",
      callback_url: "https://plane.test/auth/singularity/repository-callback/",
      scope: provider === "github" ? "Contents: read; Metadata: read" : "read_api",
      github_app_slug: "reader",
      configured: false,
    };
    const state = [true, guide, guide.web_url, provider, "", "", "client", "secret", "reader", ""];
    let cursor = 0;
    let pending;
    let submitted;
    let configured = false;
    const { RepositoryOAuthSetup } = load("./repository-oauth-setup.tsx", {
      react: {
        ...React,
        useState: () => {
          const index = cursor++;
          return [
            state[index],
            (value) => {
              state[index] = value;
            },
          ];
        },
      },
      "@makeplane/propel/components/button": { Button: button },
      "@makeplane/propel/components/input": { Input: "input", InputGroup: "div" },
      "@plane/i18n": { useTranslation: () => ({ t: (key) => key }) },
      "@/services/repository.service": {
        repositoryService: {
          write: async (...args) => {
            submitted = args;
          },
        },
      },
    });
    const tree = RepositoryOAuthSetup({
      instanceId: "host",
      repositoryUrl: "https://github.com/team/repo",
      csrf: "csrf",
      busy: false,
      action: (fn) => {
        pending = fn();
        return pending;
      },
      onConfigured: async () => {
        configured = true;
      },
    });
    const elements = [];
    function walk(node) {
      if (!node || typeof node !== "object") return;
      if (Array.isArray(node)) return node.forEach(walk);
      elements.push(node);
      walk(node.props?.children);
    }
    walk(tree);
    assert.equal(
      elements.some((node) => node.props?.id === "repository-github-app-slug"),
      provider === "github"
    );
    assert.ok(elements.some((node) => node.props?.value === guide.callback_url && node.props.readOnly));
    elements.find((node) => node.type === "form").props.onSubmit({ preventDefault() {} });
    await pending;
    assert.equal(submitted[0], "/api/singularity/v1/repository-oauth-setup/");
    assert.deepEqual(submitted[3], {
      instance_id: "host",
      client_id: "client",
      client_secret: "secret",
      ...(provider === "github" ? { github_app_slug: "reader" } : {}),
    });
    assert.equal(state[7], "");
    assert.equal(configured, true);
  });
}
test("ready initialization is hidden only when both active bindings exist; errors remain visible", () => {
  function render(status, allBound, error = undefined) {
    const { RepositoryInitialization } = load("./repository-management.tsx", {
      swr: { default: () => ({ data: { enabled: true, status, error_code: "" }, error }) },
      "@makeplane/propel/components/button": { Button: button },
      "@plane/i18n": { useTranslation: () => ({ t: (key) => key }) },
      "@/services/repository.service": { repositoryService: {} },
    });
    return renderToStaticMarkup(
      React.createElement(RepositoryInitialization, {
        base: "/test/",
        canManage: true,
        busy: false,
        allBound,
        write: async () => ({}),
        onReady: () => {},
      })
    );
  }
  assert.equal(render("ready", true), "");
  assert.equal(render("syncing", true), "");
  assert.match(render("sync_error", true), /initialization.sync_error/);
  assert.doesNotMatch(render("sync_error", true), /repository_ui.initialize/);
  assert.match(render("ready", false), /repository_ui.initialize/);
  assert.match(render("processing", true), /repository_ui.initialization.processing/);
  assert.match(render("ready", true, new Error("offline")), /status_unavailable/);
});
test("new repository labels are translated in every locale with matching keys", () => {
  const en = JSON.parse(
    readFileSync(new URL("../../../../../packages/i18n/src/locales/en/repositories.json", import.meta.url), "utf8")
  ).repository_ui;
  for (const locale of [
    "bg",
    "cs",
    "de",
    "es",
    "fr",
    "id",
    "it",
    "ja",
    "ka-ge",
    "ko",
    "nl",
    "pl",
    "pt-BR",
    "ro",
    "ru",
    "sk",
    "tr-TR",
    "ua",
    "vi-VN",
    "zh-CN",
    "zh-TW",
  ]) {
    const local = JSON.parse(
      readFileSync(
        new URL(`../../../../../packages/i18n/src/locales/${locale}/repositories.json`, import.meta.url),
        "utf8"
      )
    ).repository_ui;
    assert.deepEqual(Object.keys(local.sections), Object.keys(en.sections));
    assert.notEqual(local.sections.documentation, en.sections.documentation);
    for (const key of ["connected", "expired", "details"]) assert.ok(local[key]);
  }
});
