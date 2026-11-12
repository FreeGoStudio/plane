import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const ts = require("typescript");
function AnalyticsService() {}
function load(path, mocks = {}) {
  const code = ts.transpileModule(readFileSync(new URL(path, import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const exports = {};
  new Function("exports", "require", code)(exports, (name) => {
    assert.ok(name in mocks, `Missing mock: ${name}`);
    return mocks[name];
  });
  return exports;
}
const types = load("../../../../../packages/types/src/analytics.ts");
const { localizeWorkItemChart } = load("./utils.ts", { "@plane/types": types });
function translator(locale) {
  const dictionary = Object.assign(
    {},
    ...["common", "workspace"].map((namespace) =>
      JSON.parse(
        readFileSync(
          new URL(`../../../../../packages/i18n/src/locales/${locale}/${namespace}.json`, import.meta.url),
          "utf8"
        )
      )
    )
  );
  return (key) => {
    const value = key.split(".").reduce((object, part) => object?.[part], dictionary);
    assert.equal(typeof value, "string", `Missing translation: ${key}`);
    return value;
  };
}
const zh = translator("zh-CN");
const en = translator("en");
test("priority and state group labels translate without changing counts, identities or input", () => {
  const data = {
    data: [{ key: "urgent", name: "Urgent", count: 3, started: 2, backlog: 1 }],
    schema: { started: "Started", backlog: "Backlog" },
  };
  const before = structuredClone(data);
  const result = localizeWorkItemChart(
    data,
    types.ChartXAxisProperty.PRIORITY,
    types.ChartXAxisProperty.STATE_GROUPS,
    zh
  );
  assert.deepEqual(result, {
    data: [{ key: "urgent", name: "紧急", count: 3, started: 2, backlog: 1 }],
    schema: { started: "进行中", backlog: "待办" },
  });
  assert.deepEqual(data, before);
  assert.deepEqual(
    localizeWorkItemChart(data, types.ChartXAxisProperty.PRIORITY, types.ChartXAxisProperty.STATE_GROUPS, en),
    data
  );
});
test("user names are preserved, missing assignees and categories translate by their sentinel key", () => {
  const data = {
    data: [
      { key: "id-1", name: "None", count: 2 },
      { key: "none", name: "None", count: 1 },
    ],
    schema: { "id-2": "Urgent", none: "None" },
  };
  const result = localizeWorkItemChart(data, types.ChartXAxisProperty.ASSIGNEES, types.ChartXAxisProperty.LABELS, zh);
  assert.deepEqual(
    result.data.map((row) => row.name),
    ["None", "未分配"]
  );
  assert.deepEqual(result.schema, { "id-2": "Urgent", none: "无" });
});
test("all selectable analytics axes and metrics have Chinese labels", () => {
  const constants = load("../../../../../packages/constants/src/analytics/common.ts", { "@plane/types": types });
  for (const option of [...constants.ANALYTICS_X_AXIS_VALUES, ...constants.ANALYTICS_Y_AXIS_VALUES]) {
    assert.match(zh(`workspace_analytics.work_item_charts.axes.${option.value}`), /[\u4e00-\u9fff]/);
  }
});
test("created/resolved legend responds to language while preserving series keys", () => {
  let t = zh;
  const component = load("./created-vs-resolved.tsx", {
    react: { useMemo: (factory) => factory() },
    "react/jsx-runtime": require("react/jsx-runtime"),
    "mobx-react": { observer: (render) => render },
    "next/navigation": { useParams: () => ({ workspaceSlug: "test" }) },
    swr: { __esModule: true, default: () => ({ data: { data: [{ key: "2026-11-12", count: 2 }] } }) },
    "@plane/i18n": { useTranslation: () => ({ t }) },
    "@plane/blocks/charts/area-chart": { AreaChart: "chart" },
    "@plane/blocks/empty-state": { EmptyStateCompact: "empty" },
    "@plane/utils": {
      cn: () => "",
      useDateFormatter: () => ({ renderFormattedDate: (value) => value }),
      renderFormattedDate: (value) => value,
    },
    "@/hooks/store/use-analytics": { useAnalytics: () => ({}) },
    "@/services/analytics.service": { AnalyticsService },
    "../analytics-section-wrapper": { __esModule: true, default: "section" },
    "../constants": { ANALYTICS_CHART_HEIGHT_CLASSNAME: "chart" },
    "../loaders": { ChartLoader: "loader" },
  }).default;
  const areas = component().props.children.props.areas;
  assert.deepEqual(
    areas.map(({ key }) => key),
    ["completed_issues", "created_issues"]
  );
  assert.deepEqual(
    areas.map(({ label }) => label),
    [zh("common.resolved"), zh("created")]
  );
  t = en;
  assert.deepEqual(
    component().props.children.props.areas.map(({ label }) => label),
    ["Resolved", "Created"]
  );
});
