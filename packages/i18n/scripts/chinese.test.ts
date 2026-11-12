import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { createRequire } from "node:module";
import { createInstance } from "i18next";
import type ICUPlugin from "i18next-icu";

// The plugin's ESM entry assumes bundler default-import interop; Node uses its CJS entry.
const ICU = createRequire(import.meta.url)("i18next-icu").default as typeof ICUPlugin;

// Use the same ICU parser as the installed runtime plugin, including quoted literals.
type MessageNode = {
  type: number;
  value?: string;
  options?: Record<string, { value: MessageNode[] }>;
  children?: MessageNode[];
};
const require = createRequire(import.meta.url);
const { IntlMessageFormat } = createRequire(require.resolve("i18next-icu"))("intl-messageformat") as {
  IntlMessageFormat: new (
    message: string,
    locale: string,
    formats?: unknown,
    options?: { ignoreTag: boolean }
  ) => { getAst(): MessageNode[] };
};
const allowlist = JSON.parse(fs.readFileSync(new URL("./chinese-allowlist.json", import.meta.url), "utf8")) as Record<
  string,
  { value: string; reason: string }
>;
function argumentsOf(message: string): string[] {
  const args = new Set<string>();
  function walk(nodes: MessageNode[]) {
    for (const node of nodes) {
      if ([1, 2, 3, 4, 5, 6, 8].includes(node.type) && node.value) args.add(node.value);
      for (const option of Object.values(node.options ?? {})) walk(option.value);
      if (node.children) walk(node.children);
    }
  }
  walk(new IntlMessageFormat(message, "en", undefined, { ignoreTag: true }).getAst());
  return [...args].toSorted();
}

const root = path.resolve(import.meta.dirname, "../src/locales");

test("test-email confirmation preserves the recipient in Chinese and English", async () => {
  const instance = createInstance().use(ICU);
  const resources = Object.fromEntries(
    ["en", "zh-CN"].map((language) => [
      language,
      {
        translation: JSON.parse(fs.readFileSync(path.join(root, language, "common.json"), "utf8")),
      },
    ])
  );
  await instance.init({ lng: "zh-CN", fallbackLng: false, resources });
  const email = "person+test@example.com";
  assert.equal(
    instance.t("admin_email.sent_message", { email }),
    `测试邮件已发送至 ${email}。如果未收到，请检查垃圾邮件文件夹。`
  );
  await instance.changeLanguage("en");
  assert.equal(
    instance.t("admin_email.sent_message", { email }),
    `We have sent the test email to ${email}. Please check your spam folder if you cannot find it.`
  );
});

// Provider names, field identifiers and state must survive localization and switching.
test("OAuth help and status preserve technical values in both languages", async () => {
  const instance = createInstance().use(ICU);
  const resources = Object.fromEntries(
    ["en", "zh-CN"].map((language) => [
      language,
      {
        translation: JSON.parse(fs.readFileSync(path.join(root, language, "common.json"), "utf8")),
      },
    ])
  );
  await instance.init({ lng: "zh-CN", fallbackLng: false, resources });
  assert.equal(
    instance.t("admin_settings.auth_state", { provider: "GitHub", enabled: "yes" }),
    "GitHub 认证现已启用。"
  );
  assert.equal(instance.t("admin_settings.auth_state", { provider: "GitHub", enabled: "no" }), "GitHub 认证现已禁用。");
  assert.equal(instance.t("admin_settings.required", { label: "客户端 ID" }), "请填写客户端 ID。");
  assert.equal(
    instance.t("admin_settings.auto_url", { provider: "Google", field: "Authorized Redirect URI" }),
    "此地址由系统自动生成，请将其粘贴到 Google OAuth 应用设置的 Authorized Redirect URI 字段中。"
  );
  await instance.changeLanguage("en");
  assert.equal(
    instance.t("admin_settings.auth_state", { provider: "GitHub", enabled: "yes" }),
    "GitHub authentication is now active."
  );
  assert.equal(
    instance.t("admin_settings.auth_state", { provider: "GitHub", enabled: "no" }),
    "GitHub authentication is now disabled."
  );
});

function flatten(data: Record<string, unknown>, prefix = ""): Record<string, string> {
  return Object.fromEntries(
    Object.entries(data).flatMap(([key, value]) => {
      const name = prefix ? `${prefix}.${key}` : key;
      return typeof value === "object" && value !== null
        ? Object.entries(flatten(value as Record<string, unknown>, name))
        : [[name, String(value)]];
    })
  );
}

for (const file of fs.readdirSync(path.join(root, "en"))) {
  if (!file.endsWith(".json")) continue;
  test(`${file}: Chinese covers English messages and ICU expressions render`, async () => {
    const en = flatten(JSON.parse(fs.readFileSync(path.join(root, "en", file), "utf8")));
    const zh = flatten(JSON.parse(fs.readFileSync(path.join(root, "zh-CN", file), "utf8")));
    const instance = createInstance().use(ICU);
    await instance.init({
      lng: "zh-CN",
      fallbackLng: false,
      keySeparator: false,
      resources: { "zh-CN": { translation: zh } },
      i18nFormat: {
        parseErrorHandler: (error: Error) => {
          throw error;
        },
      },
    });
    for (const [key, value] of Object.entries(en)) {
      assert.ok(Object.hasOwn(zh, key), `${file}: missing ${key}`);
      if (value) assert.ok(zh[key].trim(), `${file}: empty ${key}`);
      const args = argumentsOf(value);
      assert.deepEqual(argumentsOf(zh[key]), args, `${file}: interpolation mismatch at ${key}`);
      if (value === zh[key] && /[A-Za-z]/.test(value)) {
        const allowed = allowlist[`${file}:${key}`];
        assert.equal(allowed?.value, value, `${file}: unreviewed English at ${key}`);
        assert.ok(allowed.reason);
      }
      assert.ok(!zh[key].includes("工作区"), `${file}: inconsistent workspace terminology at ${key}`);
      const params = Object.fromEntries(args.map((name) => [name, 2]));
      assert.equal(typeof instance.t(key, params), "string", `${file}: invalid ${key}`);
    }
  });
}
