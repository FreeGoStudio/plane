import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const names = ["Work Items", "Cycles", "Modules", "Intake", "Members", "Pages", "Views"];
const data = names.map((name, index) => ({ key: `metric-${index}`, name, count: index + 1 }));
let language = "zh-CN";
const dictionaries = Object.fromEntries(
  ["en", "zh-CN"].map((locale) => [
    locale,
    JSON.parse(
      readFileSync(new URL(`../../../../../packages/i18n/src/locales/${locale}/common.json`, import.meta.url), "utf8")
    ),
  ])
);
const mocks = {
  react: { lazy: () => "radar-chart", Suspense: "suspense" },
  "react/jsx-runtime": require("react/jsx-runtime"),
  "mobx-react": { observer: (component) => component },
  "next/navigation": { useParams: () => ({ workspaceSlug: "workspace" }) },
  swr: { __esModule: true, default: () => ({ data, isLoading: false }) },
  "@plane/i18n": { useTranslation: () => ({ t: (key) => dictionaries[language][key] ?? key }) },
  "@plane/blocks/empty-state": { EmptyStateCompact: "empty" },
  "@plane/utils": { cn: (...classes) => classes.join(" ") },
  "@/hooks/store/use-analytics": { useAnalytics: () => ({}) },
  "@/services/analytics.service": {
    AnalyticsService: class {
      getAdvanceAnalyticsCharts() {
        return Promise.resolve(data);
      }
    },
  },
  "../analytics-section-wrapper": { __esModule: true, default: "section" },
  "../constants": { ANALYTICS_CHART_HEIGHT_CLASSNAME: "chart" },
  "../loaders": { ProjectInsightsLoader: "loader" },
};
const source = readFileSync(new URL("./project-insights.tsx", import.meta.url), "utf8");
const code = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const exports = {};
new Function("exports", "require", code)(exports, (name) => {
  assert.ok(name in mocks, name);
  return mocks[name];
});
function collect(node, nodes = [], text = []) {
  if (Array.isArray(node)) node.forEach((child) => collect(child, nodes, text));
  else if (node && typeof node === "object") {
    nodes.push(node);
    collect(node.props?.children, nodes, text);
  } else if (typeof node === "string") text.push(node);
  return { nodes, text };
}

test("project insight chart and summary use Chinese labels without changing metric keys or counts", () => {
  const before = structuredClone(data);
  const { nodes, text } = collect(exports.default());
  const expected = ["工作项", "周期", "模块", "收集", "成员", "页面", "视图"];
  const chart = nodes.find((node) => node.type === "radar-chart");
  assert.deepEqual(
    chart.props.data.map((item) => item.name),
    expected
  );
  expected.forEach((label) => assert.ok(text.includes(label)));
  assert.deepEqual(
    chart.props.data.map(({ key, count }) => ({ key, count })),
    data.map(({ key, count }) => ({ key, count }))
  );
  assert.deepEqual(data, before);
  language = "en";
  const english = collect(exports.default()).nodes.find((node) => node.type === "radar-chart");
  assert.equal(english.props.data[1].name, "Cycles");
  assert.equal(english.props.data[4].name, "Members");
});
