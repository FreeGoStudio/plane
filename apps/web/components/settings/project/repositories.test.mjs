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
function renderPage(section, overrides = {}, repositoryRows = rows, callback = "") {
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
    "react-router": { useSearchParams: () => [new URLSearchParams(`section=${section}${callback}`)] },
    "@makeplane/propel/components/button": { Button: button },
    "@makeplane/propel/components/input": { Input: "input" },
    "@plane/i18n": {
      useTranslation: () => ({ t: (key) => (key.startsWith("repository_ui.results.") ? `translated:${key}` : key) }),
    },
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
    "./repository-oauth-setup": { RepositoryOAuthSetup: () => null },
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

for (const outcome of ["connected", "upstream_resource_invisible", "cancelled"]) {
  test(`personal OAuth return ${outcome} expands the target repository with local feedback`, () => {
    const html = renderPage("development", {}, rows, `&repository=code&connection=${outcome}`);
    assert.match(html, /id="repository-details-code">/);
    assert.doesNotMatch(html, /id="repository-details-code" hidden/);
    assert.match(html, new RegExp(`repository-details-code[\\s\\S]*translated:repository_ui.results.${outcome}`));
  });
}
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
test("GitLab retains OAuth, token and anonymous options", () => {
  const html = renderPage("development", { hosts: [{ id: rows[2].instance_id, oauth_available: true }] });
  assert.match(html, /GitLab/);
  assert.match(html, /name="token"/);
  assert.match(html, /repository_ui.anonymous/);
  assert.doesNotMatch(html, /GitHub|github_install/);
});

for (const provider of ["gitlab"]) {
  test(`${provider}: setup submits the correct application fields and clears the secret`, async () => {
    const guide = {
      instance_id: "host",
      provider,
      web_url: "https://gitlab.com",
      api_url: "https://gitlab.com/api/v4",
      create_url: "https://gitlab.com/-/user_settings/applications",
      homepage_url: "https://plane.test",
      callback_url: "https://plane.test/auth/singularity/repository-callback/",
      scope: "read_api",
      configured: false,
    };
    const state = [true, guide, guide.web_url, "", "", "client", "secret", ""];
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
      repositoryUrl: "https://gitlab.com/team/repo",
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
      false
    );
    assert.ok(elements.some((node) => node.props?.value === guide.callback_url && node.props.readOnly));
    elements.find((node) => node.type === "form").props.onSubmit({ preventDefault() {} });
    await pending;
    assert.equal(submitted[0], "/api/singularity/v1/repository-oauth-setup/");
    assert.deepEqual(submitted[3], {
      instance_id: "host",
      client_id: "client",
      client_secret: "secret",
    });
    assert.equal(state[6], "");
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

test("repository address example uses GitLab", () => {
  const { RepositoryAdd } = load("./repository-add.tsx", {
    "./repository-oauth-setup": { RepositoryOAuthSetup: () => null },
    "@makeplane/propel/components/button": { Button: button },
    "@makeplane/propel/components/input": {
      Input: (props) => React.createElement("input", props),
      InputGroup: ({ children }) => React.createElement("div", null, children),
    },
    "@plane/i18n": { useTranslation: () => ({ t: (key) => key }) },
    "@/services/repository.service": { repositoryService: {} },
  });
  const html = renderToStaticMarkup(
    React.createElement(RepositoryAdd, {
      base: "/test/",
      csrf: "csrf",
      section: "development",
      busy: false,
      action: async (fn) => fn(),
      onAdded: async () => {},
    })
  );
  assert.match(html, /placeholder="https:\/\/gitlab.com\/group\/repository"/);
  assert.doesNotMatch(html, /github.com/);
});

for (const outcome of ["success", "failure"]) {
  test(`registration ${outcome}: local feedback, no credential request, double submit suppressed`, async () => {
    const state = ["https://gitlab.com/team/repo", false, "", false];
    let cursor = 0;
    const ref = { current: false };
    let resolveWrite;
    let rejectWrite;
    let calls = 0;
    let payload;
    const request = new Promise((resolve, reject) => {
      resolveWrite = resolve;
      rejectWrite = reject;
    });
    const { RepositoryAdd } = load("./repository-add.tsx", {
      react: {
        ...React,
        useRef: () => ref,
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
      "@plane/i18n": { useTranslation: () => ({ t: (key) => `translated:${key}` }) },
      "@/services/repository.service": {
        repositoryService: {
          write: (...args) => {
            calls++;
            payload = args[3];
            return request;
          },
        },
      },
    });
    function render() {
      cursor = 0;
      return RepositoryAdd({
        base: "/test/",
        csrf: "csrf",
        section: "development",
        busy: false,
        onAdded: async () => {},
      });
    }
    const tree = render();
    const form = tree.props.children.find((child) => child?.type === "form");
    form.props.onSubmit({ preventDefault() {} });
    form.props.onSubmit({ preventDefault() {} });
    assert.equal(calls, 1);
    assert.deepEqual(payload, { url: state[0], purpose: "development", method: "register" });
    assert.equal(state[1], true);
    if (outcome === "success") resolveWrite({ status: "pending", purpose: "development" });
    else rejectWrite({ isAxiosError: true, response: { data: { error: "invalid_repository_url" } } });
    await new Promise((resolve) => setImmediate(resolve));
    const html = renderToStaticMarkup(render());
    assert.equal(state[1], false);
    assert.match(html, new RegExp(outcome === "success" ? 'role="status"' : 'role="alert"'));
    assert.match(html, new RegExp(outcome === "success" ? "registration.pending" : "invalid_repository_url"));
    assert.equal(state[0], outcome === "success" ? "" : "https://gitlab.com/team/repo");
    assert.doesNotMatch(html, /name="token"|oauth_setup|connection_options/);
  });
}

test("registration status survives reload and shows retry next to the affected address", () => {
  const { RepositoryAdd } = load("./repository-add.tsx", {
    "@makeplane/propel/components/button": { Button: button },
    "@makeplane/propel/components/input": { Input: "input", InputGroup: "div" },
    "@plane/i18n": { useTranslation: () => ({ t: (key) => `translated:${key}` }) },
    "@/services/repository.service": { repositoryService: {} },
  });
  const html = renderToStaticMarkup(
    React.createElement(RepositoryAdd, {
      base: "/test/",
      csrf: "csrf",
      section: "development",
      busy: false,
      onAdded: async () => {},
      registrations: [
        {
          id: "pending",
          path: "team/repo",
          purpose: "development",
          status: "waiting_access",
          error_code: "upstream_resource_invisible",
          url: "https://gitlab.com/team/repo",
        },
      ],
    })
  );
  assert.match(html, /team\/repo/);
  assert.match(html, /registration.waiting_access/);
  assert.match(html, /registration.retry/);
  assert.match(html, /registration.access_hint/);
});

for (const address of ["git@gitlab.com:team/repo.git", "ssh://git@gitlab.com:2424/team/repo.git"]) {
  test(`SSH clone input is accepted and can select its registered instance: ${address}`, async () => {
    const state = [address, false, "", false, null, "host"];
    let cursor = 0;
    let submitted;
    const { RepositoryAdd } = load("./repository-add.tsx", {
      react: {
        ...React,
        useRef: () => ({ current: false }),
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
            submitted = args[3];
            return { id: "registration", status: "pending", purpose: "development" };
          },
        },
      },
    });
    const tree = RepositoryAdd({
      base: "/test/",
      csrf: "csrf",
      section: "development",
      busy: false,
      hosts: [{ id: "host", name: "Company", web_url: "https://gitlab.com:8446" }],
      onAdded: async () => {},
    });
    const html = renderToStaticMarkup(tree);
    assert.match(html, /type="text"/);
    assert.doesNotMatch(html, /type="url"/);
    assert.match(html, /Company/);
    tree.props.children.find((child) => child?.type === "form").props.onSubmit({ preventDefault() {} });
    await new Promise((resolve) => setImmediate(resolve));
    assert.deepEqual(submitted, { url: address, purpose: "development", method: "register", instance_id: "host" });
  });
}
