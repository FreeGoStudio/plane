import assert from "node:assert/strict";
import { test } from "node:test";
import { localizeGroupColumns } from "../helpers/localization";

test("public-board localization preserves identifiers, payloads and user names", () => {
  const payload = { state_id: "user-state" };
  const groups = [
    { id: "user-state", name: "None", payload },
    { id: "None", name: "None", payload: {} },
    { id: "All Issues", name: "All work items", payload: {} },
  ];
  const messages: Record<string, string> = {
    "space_ui.no_group": "无",
    "space_ui.all_work_items": "全部工作项",
    "issue.priority.high": "高",
  };
  const t = (key: string) => messages[key] ?? key;
  const localized = localizeGroupColumns(groups, "state", t)!;
  assert.equal(localized[0], groups[0]);
  assert.equal(localized[0].name, "None");
  assert.equal(localized[0].payload, payload);
  assert.equal(localized[1].id, "None");
  assert.equal(localized[1].name, "无");
  assert.equal(localized[2].id, "All Issues");
  assert.equal(localized[2].name, "全部工作项");
  assert.equal(groups[1].name, "None");
  assert.equal(localizeGroupColumns([{ id: "high", name: "High", payload: {} }], "priority", t)![0].name, "高");
  assert.equal(localizeGroupColumns([{ id: "high", name: "High", payload: {} }], "labels", t)![0].name, "High");
  assert.equal(localizeGroupColumns(undefined, "state", t), undefined);
});
