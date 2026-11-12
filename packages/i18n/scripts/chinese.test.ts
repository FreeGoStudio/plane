import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { createRequire } from "node:module";
import { createInstance } from "i18next";
import type ICUPlugin from "i18next-icu";

// The plugin's ESM entry assumes bundler default-import interop; Node uses its CJS entry.
const ICU = createRequire(import.meta.url)("i18next-icu").default as typeof ICUPlugin;

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
      const params = Object.fromEntries(
        [...zh[key].matchAll(/\{([A-Za-z_]\w*)\s*[,}]/g)].map((match) => [match[1], 2])
      );
      assert.equal(typeof instance.t(key, params), "string", `${file}: invalid ${key}`);
    }
  });
}
