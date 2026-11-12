import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
const require = createRequire(import.meta.url);
const ts = require("typescript");
function load(path, mocks) {
  const code = ts.transpileModule(readFileSync(new URL(path, import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const exports = {};
  new Function("exports", "require", code)(exports, (name) => mocks[name] ?? require(name));
  return exports;
}
const utils = require("@plane/utils");
const chart = load("./utils.ts", { "@plane/utils": utils });
test("chart completion preserves input, existing counts and missing series", () => {
  const data = { data: [{ key: "a", name: "Alpha", present: 3 }], schema: { present: "Present", missing: "Missing" } };
  const before = structuredClone(data);
  const result = chart.parseChartData(data, null, null, null);
  assert.deepEqual(result.data, [{ key: "a", name: "Alpha", present: 3, missing: 0 }]);
  assert.deepEqual(data, before);
  assert.notEqual(result.data[0], data.data[0]);
});
test("extending colors preserves the caller palette and requested count", () => {
  const palette = ["#6172E8", "#29A383"];
  const before = [...palette];
  assert.deepEqual(chart.generateExtendedColors(palette, 1), [palette[0]]);
  const result = chart.generateExtendedColors(palette, 6);
  assert.equal(result.length, 6);
  assert.deepEqual(result.slice(0, 2), palette);
  assert.deepEqual(palette, before);
});
test("module gantt navigation is a native link with unchanged destination and drag behavior", () => {
  const module = load("../modules/gantt-chart/blocks.tsx", {
    "mobx-react": { observer: (component) => component },
    "next/link": { __esModule: true, default: "a" },
    "next/navigation": { useParams: () => ({ workspaceSlug: "workspace" }) },
    "@plane/utils": { ...utils, useDateFormatter: () => utils.createDateFormatter({ locale: "en" }) },
    "@plane/blocks/icons": { ModuleStatusIcon: "icon" },
    "@makeplane/propel/components/tooltip": { Tooltip: "tooltip" },
    "@/components/gantt-chart/constants": { SIDEBAR_WIDTH: 100 },
    "@/components/issues/issue-layouts/utils": { getBlockViewDetails: () => ({ blockStyle: {} }) },
    "@/hooks/store/use-module": {
      useModule: () => ({ getModuleById: () => ({ id: "module", project_id: "project", name: "Module" }) }),
    },
    "@/hooks/use-platform-os": { usePlatformOS: () => ({ isMobile: false }) },
  });
  const link = module.ModuleGanttBlock({ moduleId: "module" }).props.children;
  assert.equal(link.type, "a");
  assert.equal(link.props.href, "/workspace/projects/project/modules/module");
  assert.equal(link.props.draggable, false);
});
