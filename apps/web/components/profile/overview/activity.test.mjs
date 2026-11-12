import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const ts = require("typescript");
let locale = "zh-CN";
const dictionaries = Object.fromEntries(
  ["zh-CN", "en"].map((language) => [
    language,
    JSON.parse(
      readFileSync(new URL(`../../../../../packages/i18n/src/locales/${language}/common.json`, import.meta.url), "utf8")
    ),
  ])
);
const activities = ["self", "other"].map((id) => ({
  id,
  actor_detail: { id, display_name: "Original name" },
  issue_detail: { name: "SMS login prototype" },
}));
const mocks = {
  "react/jsx-runtime": require("react/jsx-runtime"),
  "mobx-react": { observer: (component) => component },
  "next/navigation": { useParams: () => ({ workspaceSlug: "workspace", userId: "self" }) },
  swr: { __esModule: true, default: () => ({ data: { results: activities } }) },
  "@plane/i18n": { useTranslation: () => ({ t: (key) => dictionaries[locale][key] ?? key }) },
  "@plane/utils": { getFileURL: () => "", useDateFormatter: () => ({ calculateTimeAgo: () => "time" }) },
  "@plane/constants": { USER_PROFILE_ACTIVITY: () => "activity" },
  "@/hooks/store/user": { useUser: () => ({ data: { id: "self" } }) },
  "@/services/user.service": {
    UserService: function UserService() {
      return {};
    },
  },
};
const exports = {};
const code = ts.transpileModule(readFileSync(new URL("./activity.tsx", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
new Function("exports", "require", code)(
  exports,
  (name) => mocks[name] ?? new Proxy({}, { get: (_, key) => String(key) })
);
function flatten(node) {
  if (Array.isArray(node)) return node.flatMap(flatten);
  if (node && typeof node === "object") return [node, ...flatten(node.props?.children)];
  return [node];
}
test("recent creation activity follows language while preserving other actors and linked work item data", () => {
  const original = structuredClone(activities);
  for (locale of ["zh-CN", "en", "zh-CN"]) {
    const tree = flatten(exports.ProfileActivity());
    assert.ok(tree.includes(dictionaries[locale].you));
    assert.equal(tree.filter((value) => value === dictionaries[locale].created).length, 2);
    assert.ok(tree.includes("Original name"));
    const links = tree.filter((node) => node?.type === "IssueLink");
    assert.deepEqual(
      links.map((node) => node.props.activity),
      activities
    );
  }
  assert.deepEqual(activities, original);
});
