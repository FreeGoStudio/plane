import assert from "node:assert/strict";
import { test } from "node:test";
import { setLanguage } from "../src/core/set-language";
import { translate } from "../src/core/translate";

test("runtime ICU formats parameters and follows the active language in Node", async () => {
  await setLanguage("zh-CN");
  assert.equal(translate("editor_ui.heading_level", { level: 2 }), "2 级标题");
  assert.equal(translate("editor_ui.file_too_large", { size: 5 }), "文件过大，请选择小于 5 MB 的文件。");
  assert.equal(translate("editor_ui"), "editor_ui");
  await setLanguage("en");
  assert.equal(translate("editor_ui.heading_level", { level: 2 }), "Heading 2");
});

test("home greetings use Chinese sentence order and preserve English greetings", async () => {
  await setLanguage("zh-CN");
  for (const [period, expected] of [
    ["morning", "早上好，Jacky"],
    ["afternoon", "下午好，Jacky"],
    ["evening", "晚上好，Jacky"],
  ]) {
    assert.equal(translate(`home.greetings.${period}`, { name: "Jacky" }), expected);
  }
  await setLanguage("en");
  assert.equal(translate("home.greetings.afternoon", { name: "Jacky" }), "Good afternoon, Jacky");
});
