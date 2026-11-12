import assert from "node:assert/strict";
import { test } from "node:test";
import { createInstance } from "i18next";
import { createRequire } from "node:module";
import type ICUPlugin from "i18next-icu";
import en from "../src/locales/en/common.json";
import zh from "../src/locales/zh-CN/common.json";
import { translateValidationMessage } from "../src/validation";

const ICU = createRequire(import.meta.url)("i18next-icu").default as typeof ICUPlugin;
test("validation localization preserves success and unknown content", async () => {
  const instance = createInstance().use(ICU);
  await instance.init({
    lng: "zh-CN",
    fallbackLng: false,
    resources: { "zh-CN": { translation: zh }, en: { translation: en } },
  });
  const t = (key: string) => instance.t(key);
  assert.equal(translateValidationMessage(true, t), true);
  assert.equal(translateValidationMessage(false, t), false);
  assert.equal(translateValidationMessage(undefined, t), undefined);
  assert.equal(translateValidationMessage("用户原文", t), "用户原文");
  assert.equal(translateValidationMessage("Workspace name is required", t), "请填写工作空间名称。");
  assert.equal(translateValidationMessage("Slug must be 48 characters or less", t), "地址标识不能超过 48 个字符。");
  assert.equal(
    instance.t("validation.workspace_name_special"),
    `工作空间名称不能包含以下特殊字符：< > ' " { } [ ] * ^ ! # %`
  );
  await instance.changeLanguage("en");
  assert.equal(translateValidationMessage("Workspace name is required", t), "Workspace name is required");
  assert.equal(
    instance.t("validation.workspace_name_special"),
    `Workspace name cannot contain special characters like < > ' " { } [ ] * ^ ! # %`
  );
});
