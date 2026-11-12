import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { test } from "node:test";
import ts from "typescript";
import { setLanguage } from "../src/core/set-language";
import { translate } from "../src/core/translate";

const root = path.resolve(import.meta.dirname, "../../../apps/web/components/onboarding");
const keys = new Set<string>();
function scan(directory: string) {
  for (const item of fs.readdirSync(directory, { withFileTypes: true })) {
    const filename = path.join(directory, item.name);
    if (item.isDirectory()) scan(filename);
    else if (filename.endsWith(".tsx")) {
      const source = ts.createSourceFile(
        filename,
        fs.readFileSync(filename, "utf8"),
        ts.ScriptTarget.Latest,
        true,
        ts.ScriptKind.TSX
      );
      function visit(node: ts.Node) {
        if (
          ts.isCallExpression(node) &&
          node.expression.getText(source) === "t" &&
          node.arguments[0] &&
          ts.isStringLiteral(node.arguments[0])
        )
          keys.add(node.arguments[0].text);
        ts.forEachChild(node, visit);
      }
      visit(source);
    }
  }
}
scan(root);
scan(path.resolve(root, "../workspace/settings"));
scan(path.resolve(root, "../workspace/views"));
for (const section of ["project", "project-states", "cycles", "modules"]) scan(path.resolve(root, "..", section));
test("web workflow messages resolve in both languages and preserve interpolated user content", async () => {
  for (const locale of ["zh-CN", "en"] as const) {
    // The shared instance must finish one language before the next assertion set.
    // oxlint-disable-next-line no-await-in-loop
    await setLanguage(locale);
    const unresolved = [...keys].filter(
      (key) =>
        translate(key, {
          name: "用户 原名",
          email: "User@example.com",
          current: 2,
          total: 5,
          count: 2,
          entity: "项目",
          feature: "周期",
        }) === key
    );
    assert.deepEqual(unresolved, []);
    assert.ok(translate("workspace_ui.remove_member_description", { name: "成员 Original" }).includes("成员 Original"));
    for (const key of [
      "delete_cycle_confirmation",
      "delete_module_confirmation",
      "delete_state_confirmation",
      "archive_project_title",
      "restore_project_title",
      "join_project_confirmation",
    ]) {
      assert.ok(translate(`project_ui.${key}`, { name: "名称 Original <保留>" }).includes("名称 Original <保留>"));
    }
    assert.equal(
      translate("project_ui.work_item_count", { count: 1 }),
      locale === "zh-CN" ? "1 个工作项" : "1 work item"
    );
    assert.equal(
      translate("project_ui.work_item_count", { count: 2 }),
      locale === "zh-CN" ? "2 个工作项" : "2 work items"
    );
    const welcome = translate("onboarding_ui.welcome", { name: "用户 原名" });
    assert.ok(welcome.includes("用户 原名"));
    assert.ok(
      translate("onboarding_ui.switch_account_description", { email: "User@example.com" }).includes("User@example.com")
    );
    assert.equal(
      translate("onboarding_ui.step_progress", { current: 2, total: 5, count: 2, entity: "项目", feature: "周期" }),
      locale === "zh-CN" ? "第 2 步，共 5 步" : "Step 2 of 5"
    );
    for (const role of ["guest", "member", "admin"])
      assert.notEqual(translate(`role_details.${role}.title`), `role_details.${role}.title`);
    for (let i = 0; i < 5; i++)
      assert.notEqual(translate(`onboarding_ui.use_case_${i}`), `onboarding_ui.use_case_${i}`);
  }
});
