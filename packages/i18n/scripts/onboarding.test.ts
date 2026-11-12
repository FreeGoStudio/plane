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
test("onboarding and workspace messages resolve in both languages and preserve interpolated user content", async () => {
  for (const locale of ["zh-CN", "en"] as const) {
    // The shared instance must finish one language before the next assertion set.
    // oxlint-disable-next-line no-await-in-loop
    await setLanguage(locale);
    for (const key of keys)
      assert.notEqual(translate(key, { name: "用户 原名", email: "User@example.com", current: 2, total: 5 }), key, key);
    assert.ok(translate("workspace_ui.remove_member_description", { name: "成员 Original" }).includes("成员 Original"));
    const welcome = translate("onboarding_ui.welcome", { name: "用户 原名" });
    assert.ok(welcome.includes("用户 原名"));
    assert.ok(
      translate("onboarding_ui.switch_account_description", { email: "User@example.com" }).includes("User@example.com")
    );
    assert.equal(
      translate("onboarding_ui.step_progress", { current: 2, total: 5 }),
      locale === "zh-CN" ? "第 2 步，共 5 步" : "Step 2 of 5"
    );
    for (const role of ["guest", "member", "admin"])
      assert.notEqual(translate(`role_details.${role}.title`), `role_details.${role}.title`);
    for (let i = 0; i < 5; i++)
      assert.notEqual(translate(`onboarding_ui.use_case_${i}`), `onboarding_ui.use_case_${i}`);
  }
});
