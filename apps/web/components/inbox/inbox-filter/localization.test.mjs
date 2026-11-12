import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const constants = require("@plane/constants");
let locale = "zh-CN";
let filters = {};
const updates = [];
const dictionaries = Object.fromEntries(
  ["zh-CN", "en"].map((language) => [
    language,
    JSON.parse(
      readFileSync(new URL(`../../../../../packages/i18n/src/locales/${language}/common.json`, import.meta.url), "utf8")
    ),
  ])
);
const translate = (key) => key.split(".").reduce((value, part) => value?.[part], dictionaries[locale]) ?? key;
const mocks = {
  "@plane/utils": { useDateFormatter: () => ({ renderFormattedDate: (value) => value }) },
  "react/jsx-runtime": require("react/jsx-runtime"),
  "mobx-react": { observer: (component) => component },
  "@plane/constants": constants,
  "@plane/i18n": { useTranslation: () => ({ t: translate }) },
  "@/hooks/store/use-project-inbox": {
    useProjectInbox: () => ({
      currentTab: "open",
      inboxFilters: filters,
      handleInboxIssueFilters: (...args) => updates.push(args),
    }),
  },
  "@/hooks/use-window-size": { __esModule: true, default: () => [1400, 900] },
  "@/hooks/store/use-member": { useMember: () => ({ project: { projectMemberIds: [] } }) },
  "@/hooks/store/use-label": { useLabel: () => ({ projectLabels: [] }) },
};
function load(path) {
  const exports = {};
  const code = ts.transpileModule(readFileSync(new URL(path, import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  new Function("exports", "require", code)(
    exports,
    (name) => mocks[name] ?? new Proxy({}, { get: (_, key) => String(key) })
  );
  return exports;
}
function flatten(node) {
  if (Array.isArray(node)) return node.flatMap(flatten);
  if (node && typeof node === "object")
    return [node, ...flatten(node.props?.children), ...flatten(node.props?.menuButton)];
  return [node];
}
const { FiltersRoot } = load("./root.tsx");
const { FilterPriority } = load("./filters/priority.tsx");
const { FilterStatus } = load("./filters/status.tsx");
const { InboxIssueFilterSelection } = load("./filters/filter-selection.tsx");
const { InboxIssueAppliedFiltersPriority } = load("./applied-filters/priority.tsx");
const { FilterDate } = load("./filters/date.tsx");
const { InboxIssueAppliedFiltersDate } = load("./applied-filters/date.tsx");

test("date presets and selected chips translate without changing date filter values", () => {
  const values = ["today", "yesterday", "last_7_days", "last_30_days"];
  for (locale of ["zh-CN", "en", "zh-CN"]) {
    filters = { created_at: ["yesterday"] };
    const menu = FilterDate({ filterKey: "created_at" });
    assert.equal(menu.props.label, translate("common.date_filter.created_date"));
    assert.deepEqual(
      menu.props.options.map((option) => option.value),
      values
    );
    const labels = menu.props.options.map((option) => translate(option.i18n_name));
    assert.deepEqual(
      labels,
      locale === "zh-CN"
        ? ["今天", "昨天", "最近 7 天", "最近 30 天"]
        : ["Today", "Yesterday", "Last 7 days", "Last 30 days"]
    );
    menu.props.onToggleOption("last_7_days");
    assert.deepEqual(updates.pop(), ["created_at", ["last_7_days"]]);
    menu.props.onToggleOption("yesterday");
    assert.deepEqual(updates.pop(), ["created_at", []]);
    filters = { created_at: values };
    const chips = flatten(InboxIssueAppliedFiltersDate({ filterKey: "created_at", label: "date" })).filter(
      (node) => node?.type === "RemovableChip"
    );
    assert.deepEqual(
      chips.map((chip) => chip.props.label),
      labels
    );
    chips[1].props.onRemove();
    assert.deepEqual(updates.pop(), ["created_at", ["today", "last_7_days", "last_30_days"]]);
  }
});
test("filter button, categories and priority options follow language changes", () => {
  for (locale of ["zh-CN", "en", "zh-CN"]) {
    assert.ok(flatten(FiltersRoot()).includes(translate("common.filters")));
    const selection = flatten(InboxIssueFilterSelection());
    assert.equal(
      selection.find((n) => n?.props?.filterKey === "created_by").props.label,
      translate("common.created_by")
    );
    assert.equal(
      selection.find((n) => n?.props?.filterKey === "updated_at").props.label,
      translate("common.sort.updated_on")
    );
    assert.equal(FilterStatus().props.label, translate("common.state"));
    const priority = FilterPriority();
    assert.deepEqual(
      priority.props.options.map((o) => o.label),
      constants.ISSUE_PRIORITIES.map((p) => translate(p.key))
    );
    assert.deepEqual(
      priority.props.options.map((o) => o.value),
      constants.ISSUE_PRIORITIES.map((p) => p.key)
    );
  }
});
test("translated selections keep filter values and removal behavior", () => {
  filters = { priority: [] };
  FilterPriority().props.onToggle("high");
  assert.deepEqual(updates.pop(), ["priority", ["high"]]);
  filters = { priority: ["high"] };
  const chip = flatten(InboxIssueAppliedFiltersPriority()).find((n) => n?.type === "RemovableChip");
  assert.equal(chip.props.label, translate("high"));
  chip.props.onRemove();
  assert.deepEqual(updates.pop(), ["priority", []]);
});
