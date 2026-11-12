import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { afterEach, test } from "node:test";

// Reuse the repository's DOM test tools without adding a second test runner to web.
const require = createRequire(import.meta.url);
const requireBlocks = createRequire(new URL("../../../../../packages/blocks/package.json", import.meta.url));
const { JSDOM } = requireBlocks("jsdom");
const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost" });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
Object.defineProperty(globalThis, "navigator", { value: dom.window.navigator, configurable: true });
const React = require("react");
const { render, fireEvent, waitFor, cleanup } = requireBlocks("@testing-library/react");
const ts = require("typescript");
const h = React.createElement;
const enums = {
  EAuthModes: { SIGN_IN: "SIGN_IN", SIGN_UP: "SIGN_UP" },
  EAuthSteps: { EMAIL: "EMAIL", PASSWORD: "PASSWORD", UNIQUE_CODE: "UNIQUE_CODE" },
  EErrorAlertType: { BANNER_ALERT: "BANNER_ALERT" },
  EAuthenticationErrorCodes: {},
  E_PASSWORD_STRENGTH: { STRENGTH_VALID: "valid" },
  API_BASE_URL: "",
};
let config;
let checkedEmails;
let codeEmails;
let emailResponse;
const empty = () => null;
function WorkspaceService() {}
const mocks = {
  react: React,
  "react/jsx-runtime": require("react/jsx-runtime"),
  "mobx-react": { observer: (component) => component },
  "next/navigation": { useSearchParams: () => new URLSearchParams("next_path=/workspace") },
  "next/link": { __esModule: true, default: ({ children, ...props }) => h("a", props, children) },
  "@plane/constants": enums,
  "@/helpers/authentication.helper": { ...enums, authErrorHandler: () => undefined },
  "@plane/i18n": { useTranslation: () => ({ t: (key) => key }) },
  "@plane/utils": {
    checkEmailValidity: (email) => /^[^@]+@[^@]+\.[^@]+$/.test(email),
    getPasswordStrength: () => "valid",
  },
  "@/hooks/store/use-instance": { useInstance: () => ({ config }) },
  "@/hooks/use-app-router": { useAppRouter: () => ({ push: empty }) },
  "@/hooks/oauth": { useOAuthConfig: () => ({ isOAuthEnabled: false }) },
  "@/services/auth.service": {
    AuthService: class {
      requestCSRFToken() {
        return Promise.resolve({ csrf_token: "test-token" });
      }
      emailCheck({ email }) {
        checkedEmails.push(email);
        return Promise.resolve(emailResponse);
      }
      generateUniqueCode({ email }) {
        codeEmails.push(email);
        return Promise.resolve({});
      }
    },
  },
  "@makeplane/propel/icons": new Proxy({}, { get: () => empty }),
  "@makeplane/propel/components/banner": { Banner: empty },
  "@makeplane/propel/components/icon": { Icon: empty },
  "@makeplane/propel/components/input-field": {
    InputField: ({ label, orientation, size, endIcon, error, ...props }) =>
      h("label", null, label, h("input", props), endIcon),
  },
  "@makeplane/propel/components/button": {
    Button: ({ label, variant, size, stretch, loading, ...props }) => h("button", props, label),
  },
  "@plane/blocks/auth": { PasswordStrengthIndicator: empty, OAuthOptions: empty },
  "../terms-and-conditions": { TermsAndConditions: empty },
  "./auth-header": { AuthHeader: empty, AuthHeaderBase: empty },
  "./email": { AuthEmailForm: () => h("div", null, "email-step") },
  "./unique-code": { AuthUniqueCodeForm: ({ email }) => h("div", null, `code-step:${email}`) },
};
function loadComponent(name) {
  const source = readFileSync(new URL(`${name}.tsx`, import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  });
  const module = { exports: {} };
  const mockRequire = (id) => {
    if (id in mocks) return mocks[id];
    if (id.startsWith("./")) return loadComponent(id);
    throw new Error(`Unexpected dependency: ${id}`);
  };
  new Function("require", "module", "exports", outputText)(mockRequire, module, module.exports);
  return module.exports;
}
const { AuthRoot } = loadComponent("./auth-root");
afterEach(cleanup);
function setup(mode = "SIGN_IN", overrides = {}) {
  config = { is_email_password_enabled: true, is_magic_login_enabled: true, is_smtp_configured: true, ...overrides };
  checkedEmails = [];
  codeEmails = [];
  emailResponse = { existing: true, status: "CREDENTIAL" };
  return render(h(AuthRoot, { authMode: mode }));
}
function fill(view) {
  fireEvent.change(view.container.querySelector("input[name=email]"), { target: { value: "person@example.com" } });
  fireEvent.change(view.container.querySelector("input[name=password]"), { target: { value: "test-password" } });
}

test("sign-in displays editable credentials together with password-manager metadata", () => {
  const view = setup();
  const email = view.container.querySelector("input[name=email]");
  const password = view.container.querySelector("input[name=password]");
  assert.equal(email.disabled, false);
  assert.equal(email.autocomplete, "username");
  assert.equal(password.autocomplete, "current-password");
  assert.equal(email.form, password.form);
  assert.equal(view.container.querySelectorAll("input[name=email]").length, 1);
});

test("one submit sends both credentials, CSRF and redirect to the existing endpoint", async () => {
  const view = setup();
  fill(view);
  const form = view.container.querySelector("form");
  let submitted;
  form.submit = () => {
    submitted = new dom.window.FormData(form);
  };
  fireEvent.submit(form);
  await waitFor(() => assert.ok(submitted));
  assert.deepEqual(checkedEmails, ["person@example.com"]);
  assert.equal(form.getAttribute("action"), "/auth/sign-in/");
  assert.equal(submitted.get("email"), "person@example.com");
  assert.equal(submitted.get("password"), "test-password");
  assert.equal(submitted.get("csrfmiddlewaretoken"), "test-token");
  assert.equal(submitted.get("next_path"), "/workspace");
});

test("edited email is used for password reset and switching to code sign-in", async () => {
  const view = setup();
  fill(view);
  assert.ok(view.container.querySelector("a").href.endsWith("email=person%40example.com"));
  fireEvent.click(view.getByText("auth.common.sign_in_with_unique_code"));
  await waitFor(() => assert.ok(view.getByText("code-step:person@example.com")));
  assert.deepEqual(codeEmails, ["person@example.com"]);
});

test("registration and magic-only instances still start with email verification", () => {
  const signup = setup("SIGN_UP");
  assert.ok(signup.getByText("email-step"));
  signup.unmount();
  const magic = setup("SIGN_IN", { is_email_password_enabled: false });
  assert.ok(magic.getByText("email-step"));
  assert.equal(magic.container.querySelector("input[name=password]"), null);
});

test("an unregistered email still follows the registration flow", async () => {
  const view = setup();
  emailResponse = { existing: false, status: "CREDENTIAL" };
  fill(view);
  fireEvent.submit(view.container.querySelector("form"));
  await waitFor(() => assert.ok(view.container.querySelector("input[name=confirm_password]")));
  assert.equal(view.container.querySelector("form").getAttribute("action"), "/auth/sign-up/");
});

test("accounts requiring a magic code retain their authentication route", async () => {
  const view = setup();
  emailResponse = { existing: true, status: "MAGIC_CODE" };
  fill(view);
  fireEvent.submit(view.container.querySelector("form"));
  await waitFor(() => assert.ok(view.getByText("code-step:person@example.com")));
  assert.deepEqual(codeEmails, ["person@example.com"]);
});

test("Chinese sign-in and sign-up render localized headings, navigation and legal links", () => {
  const locales = ["auth", "common"].map((name) =>
    JSON.parse(
      readFileSync(new URL(`../../../../../packages/i18n/src/locales/zh-CN/${name}.json`, import.meta.url), "utf8")
    )
  );
  const originalTranslation = mocks["@plane/i18n"];
  mocks["@plane/i18n"] = {
    useTranslation: () => ({
      t: (key, values = {}) => {
        const value = locales
          .map((locale) => key.split(".").reduce((node, part) => node?.[part], locale))
          .find((candidate) => typeof candidate === "string");
        assert.ok(value, `Missing Chinese translation: ${key}`);
        return value.replace("{count, number}", new Intl.NumberFormat("zh-CN").format(values.count));
      },
    }),
  };
  mocks.swr = { __esModule: true, default: () => ({ data: undefined, isLoading: false }) };
  mocks["@makeplane/propel/components/workspace-avatar"] = { WorkspaceAvatar: empty };
  mocks["@/components/common/logo-spinner"] = { LogoSpinner: empty };
  mocks["@/services/workspace.service"] = { WorkspaceService };
  mocks["@plane/blocks/icons"] = new Proxy({}, { get: () => empty });
  mocks["@/components/core/page-title"] = {
    PageHead: ({ title }) => h("span", { "data-testid": "page-title" }, title),
  };
  try {
    config = { enable_signup: true };
    const { AuthHeader: Heading } = loadComponent("./auth-header");
    const { AuthHeader: Navigation } = loadComponent("../../auth-screens/header");
    const { AuthFooter } = loadComponent("../../auth-screens/footer");
    const { TermsAndConditions } = loadComponent("../terms-and-conditions");
    for (const mode of ["SIGN_IN", "SIGN_UP"]) {
      for (const step of ["EMAIL", "PASSWORD", "UNIQUE_CODE"]) {
        const view = render(
          h(
            React.Fragment,
            null,
            h(Navigation, { type: mode }),
            h(Heading, { authMode: mode, currentAuthStep: step }),
            h(TermsAndConditions, { authType: mode }),
            h(AuthFooter)
          )
        );
        assert.ok(view.getByText("全方位协作，让工作有序推进。"));
        assert.ok(view.getByText(mode === "SIGN_IN" ? "欢迎回到 Plane。" : "创建您的 Plane 账号。"));
        assert.equal(view.getByTestId("page-title").textContent, mode === "SIGN_IN" ? "登录 - Plane" : "注册 - Plane");
        assert.equal(
          view.getByText(mode === "SIGN_IN" ? "注册" : "登录").getAttribute("href"),
          mode === "SIGN_IN" ? "/sign-up" : "/sign-in"
        );
        assert.equal(view.getByText("服务条款").closest("a").href, "https://plane.so/legals/terms-and-conditions");
        assert.equal(view.getByText("隐私政策").closest("a").href, "https://plane.so/legals/privacy-policy");
        assert.ok(view.getByText("与超过 10,000 个团队一起使用 Plane 共创成果"));
        assert.doesNotMatch(view.container.textContent, /Sign up|Sign in|Welcome back|Terms of Service|Privacy Policy/);
        view.unmount();
      }
    }
  } finally {
    mocks["@plane/i18n"] = originalTranslation;
  }
});
