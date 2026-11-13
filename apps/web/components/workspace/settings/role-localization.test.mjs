import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const constants = require("@plane/constants");
let locale = "zh-CN";
let editable = false;
const updates = [];
const dictionaries = Object.fromEntries(
  ["zh-CN", "en"].map((language) => [
    language,
    JSON.parse(
      readFileSync(new URL(`../../../../../packages/i18n/src/locales/${language}/common.json`, import.meta.url), "utf8")
    ),
  ])
);
const t = (key) => key.split(".").reduce((value, part) => value?.[part], dictionaries[locale]) ?? key;
const mocks = {
  "react/jsx-runtime": require("react/jsx-runtime"),
  "mobx-react": { observer: (component) => component },
  "react-hook-form": { useForm: () => ({ control: {}, formState: { errors: {} } }), Controller: "Controller" },
  "@plane/constants": constants,
  "@plane/i18n": { useTranslation: () => ({ t }) },
  "@plane/blocks/select": { Select: Object.assign(() => null, { Trigger: "Trigger" }) },
  "@/hooks/store/user": {
    useUser: () => ({ data: { id: "self" } }),
    useUserPermissions: () => ({
      allowPermissions: () => editable,
      getProjectRoleByWorkspaceSlugAndProjectId: () => 20,
    }),
  },
  "@/hooks/store/use-member": {
    useMember: () => ({
      workspace: {
        updateMember: (...args) => {
          updates.push(args);
          return Promise.resolve();
        },
        getWorkspaceMemberDetails: () => ({ role: 15 }),
      },
      project: {
        updateMemberRole: (...args) => {
          updates.push(args);
          return Promise.resolve();
        },
      },
    }),
  },
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
  if (node && typeof node === "object") return [node, ...flatten(node.props?.children)];
  return [node];
}
const workspace = load("./member-columns.tsx");
const project = load("../../project/settings/member-columns.tsx");
const { MemberHeaderColumn } = load("../../project/member-header-column.tsx");

test("workspace and project role labels and options follow locale while retaining role IDs", () => {
  for (locale of ["zh-CN", "en", "zh-CN"]) {
    const expected = locale === "zh-CN" ? ["访客", "成员", "管理员"] : ["Guest", "Member", "Admin"];
    for (const [index, role] of [5, 15, 20].entries()) {
      const props = {
        rowData: { member: { id: "other" }, role, original_role: role, is_active: true },
        workspaceSlug: "workspace",
        projectId: "project",
      };
      editable = false;
      assert.ok(flatten(workspace.AccountTypeColumn(props)).includes(expected[index]));
      editable = true;
      for (const component of [workspace.AccountTypeColumn, project.AccountTypeColumn]) {
        const controller = flatten(component(props)).find((node) => node?.type === "Controller");
        const tree = flatten(controller.props.render());
        assert.ok(tree.includes(expected[index]));
        const select = tree.find((node) => node?.props?.getOptionLabel);
        const options = select.props.getValues();
        assert.deepEqual(options.map(select.props.getOptionLabel), expected);
        assert.deepEqual(options.map(select.props.getOptionValue), ["5", "15", "20"]);
        select.props.onChange("15");
        const update = updates.pop();
        assert.deepEqual(update.at(-1), component === workspace.AccountTypeColumn ? { role: 15 } : 15);
      }
    }
  }
});

test("role sorting translates both directions without changing sort keys", () => {
  for (locale of ["zh-CN", "en"]) {
    const changes = [];
    const tree = flatten(
      MemberHeaderColumn({
        property: "role",
        displayFilters: {},
        handleDisplayFilterUpdate: (value) => changes.push(value),
      })
    );
    const items = tree.filter((node) => node?.type === "MenuItem");
    assert.deepEqual(
      items.map((node) => node.props.label),
      locale === "zh-CN" ? ["访客 → 管理员", "管理员 → 访客"] : ["Guest → Admin", "Admin → Guest"]
    );
    items.forEach((node) => node.props.onClick());
    assert.deepEqual(changes, [{ order_by: "role" }, { order_by: "-role" }]);
  }
});
