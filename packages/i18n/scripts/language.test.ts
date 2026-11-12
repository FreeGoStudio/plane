import assert from "node:assert/strict";
import { test } from "node:test";
import { DEFAULT_LANGUAGE, FALLBACK_LANGUAGE, SUPPORTED_LANGUAGES, resolveLanguage } from "../src/constants/language";

test("new and invalid preferences select Simplified Chinese", () => {
  for (const value of [undefined, null, "", "invalid", "../../en"]) {
    assert.equal(resolveLanguage(value), "zh-CN");
  }
  assert.equal(DEFAULT_LANGUAGE, "zh-CN");
  assert.equal(FALLBACK_LANGUAGE, "en");
});

test("every existing supported preference is preserved", () => {
  for (const { value } of SUPPORTED_LANGUAGES) assert.equal(resolveLanguage(value), value);
});
