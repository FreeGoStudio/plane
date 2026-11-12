import assert from "node:assert/strict";
import { test } from "node:test";
import { loadLocale } from "../src/load-locale";
import { SUPPORTED_LANGUAGES } from "../src/constants/language";
import { NAMESPACES } from "../src/constants/namespaces";

test("all supported locales load without a filesystem symlink", async () => {
  await Promise.all(
    SUPPORTED_LANGUAGES.flatMap(({ value }) =>
      NAMESPACES.map(async (namespace) => {
        const resource = await loadLocale(value, namespace);
        assert.ok(resource.default && typeof resource.default === "object", `${value}/${namespace}`);
      })
    )
  );
});

test("unsupported resource paths are rejected", async () => {
  await assert.rejects(loadLocale("../../en", "common"), /Unsupported locale resource/);
});
