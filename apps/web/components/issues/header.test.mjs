import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const ts = require("typescript");
let language = "zh-CN";
const dictionaries = Object.fromEntries(
  ["zh-CN", "en"].map((locale) => [
    locale,
    JSON.parse(
      readFileSync(new URL(`../../../../packages/i18n/src/locales/${locale}/navigation.json`, import.meta.url), "utf8")
    ),
  ])
);
const component = new Proxy(() => null, { get: (_, key) => String(key) });
const mocks = {
  "react/jsx-runtime": require("react/jsx-runtime"),
  "mobx-react": { observer: (value) => value },
  "next/navigation": { useParams: () => ({ workspaceSlug: "workspace", projectId: "project", workItem: "TEST-1" }) },
  "@plane/i18n": {
    useTranslation: () => ({
      t: (key) => key.split(".").reduce((value, part) => value?.[part], dictionaries[language]) ?? key,
    }),
  },
  "@plane/constants": { EUserPermissions: {}, EUserPermissionsLevel: {}, SPACE_BASE_URL: "", SPACE_BASE_PATH: "" },
  "@plane/types": { EIssuesStoreType: {} },
  "@/hooks/store/use-issues": { useIssues: () => ({ issues: { getGroupIssueCount: () => 0 } }) },
  "@/hooks/store/use-project": { useProject: () => ({ getProjectById: () => ({ identifier: "TEST" }) }) },
  "@/hooks/store/use-issue-detail": {
    useIssueDetail: () => ({
      issue: { getIssueIdByIdentifier: () => "issue", getIssueById: () => ({ project_id: "project", sequence_id: 1 }) },
    }),
  },
  "@/hooks/store/use-command-palette": { useCommandPalette: () => ({}) },
  "@/hooks/store/user": { useUserPermissions: () => ({ allowPermissions: () => false }) },
  "@/hooks/use-platform-os": { usePlatformOS: () => ({ isMobile: false }) },
  "@/components/breadcrumbs/use-project-crumb-props": { useProjectCrumbProps: () => ({}) },
};
function load(path) {
  const code = ts.transpileModule(readFileSync(new URL(path, import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const exports = {};
  new Function("exports", "require", code)(exports, (name) => mocks[name] ?? new Proxy({}, { get: () => component }));
  return exports;
}
function links(node) {
  if (Array.isArray(node)) return node.flatMap(links);
  if (!node || typeof node !== "object") return [];
  return [node.props, ...links(node.props?.children), ...links(node.props?.component)].filter(Boolean);
}
const headers = [
  load("./header.tsx").IssuesHeader,
  load("../../app/(all)/[workspaceSlug]/(projects)/browse/[workItem]/work-item-header.tsx").WorkItemDetailsHeader,
];
test("list and detail breadcrumbs follow language changes and retain the project destination", () => {
  for (language of ["zh-CN", "en", "zh-CN"]) {
    for (const Header of headers) {
      const link = links(Header()).find((props) => props.href === "/workspace/projects/project/issues/");
      assert.ok(link);
      assert.equal(link.label, language === "zh-CN" ? "工作项" : dictionaries.en.sidebar.work_items);
    }
  }
});
