import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const ts = require("typescript");
let language = "zh-CN";
const calls = [];
const dictionaries = Object.fromEntries(
  ["zh-CN", "en"].map((locale) => [
    locale,
    JSON.parse(
      readFileSync(new URL(`../../../../packages/i18n/src/locales/${locale}/stickies.json`, import.meta.url), "utf8")
    ),
  ])
);
const mocks = {
  "react/jsx-runtime": require("react/jsx-runtime"),
  "mobx-react": { observer: (component) => component },
  "next/navigation": { useParams: () => ({ workspaceSlug: "workspace" }) },
  "@plane/i18n": {
    useTranslation: () => ({
      t: (key) => key.split(".").reduce((value, part) => value?.[part], dictionaries[language]) ?? key,
    }),
  },
  "@/hooks/use-stickies": {
    useSticky: () => ({ creatingSticky: true, toggleShowNewSticky: (value) => calls.push(value) }),
  },
  "@/components/stickies/sticky/use-operations": {
    useStickyOperations: () => ({ stickyOperations: { create: () => calls.push("create") } }),
  },
};
const component = new Proxy(() => null, { get: (_, key) => String(key) });
const exports = {};
const source = readFileSync(
  new URL("../../app/(all)/[workspaceSlug]/(projects)/stickies/header.tsx", import.meta.url),
  "utf8"
);
const code = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
new Function("exports", "require", code)(exports, (name) => mocks[name] ?? new Proxy({}, { get: () => component }));
function nodes(node) {
  if (Array.isArray(node)) return node.flatMap(nodes);
  if (!node || typeof node !== "object") return [];
  return [node, ...nodes(node.props?.children)];
}
test("add sticky button follows language and retains creation and loading behavior", () => {
  for (language of ["zh-CN", "en", "zh-CN"]) {
    const button = nodes(exports.WorkspaceStickyHeader()).find((node) => node.props.onClick);
    assert.equal(button.props.label, language === "zh-CN" ? "添加便签" : "Add sticky");
    assert.equal(button.props.loading, true);
    button.props.onClick();
    assert.deepEqual(calls.splice(0), [true, "create"]);
  }
});
