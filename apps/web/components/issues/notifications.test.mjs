/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Scenarios intentionally share a mounted hook's memo cache while switching languages.
/* oxlint-disable no-await-in-loop */
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const root = new URL("../../../../", import.meta.url);
const i18nRequire = createRequire(new URL("packages/i18n/package.json", root));
const { createInstance } = i18nRequire("i18next");
const ICU = i18nRequire("i18next-icu");
const locales = new URL("packages/i18n/src/locales/", root);
const namespaces = ["common", "work-item", "update"];
const dictionaries = Object.fromEntries(
  ["en", "zh-CN", "zh-TW"].map((locale) => [
    locale,
    Object.fromEntries(
      namespaces.map((namespace) => [
        namespace,
        JSON.parse(readFileSync(new URL(`${locale}/${namespace}.json`, locales), "utf8")),
      ])
    ),
  ])
);

async function harness() {
  const i18n = createInstance();
  await i18n.use(ICU.default ?? ICU).init({
    lng: "zh-CN",
    fallbackLng: false,
    resources: dictionaries,
    ns: namespaces,
    defaultNS: "common",
    fallbackNS: namespaces,
  });
  let t = i18n.getFixedT("zh-CN");
  let fail = false;
  const toasts = [];
  const pendingToasts = [];
  const calls = [];
  const memos = [];
  let cursor = 0;
  let dropOptions;
  let route = { workspaceSlug: "team", projectId: "project", cycleId: "cycle" };
  const operation =
    (name) =>
    (...args) => {
      calls.push({ name, args });
      if (fail) throw new Error("Operation failed");
      return Promise.resolve();
    };
  const detail = {
    attachment: {
      createAttachment: operation("upload"),
      removeAttachment: operation("removeAttachment"),
      getAttachmentsUploadStatusByIssueId: () => [],
    },
    reaction: { getReactionsByIssueId: () => ({}), reactionsByUser: () => [], getReactionById: () => undefined },
    commentReaction: {
      getCommentReactionsByCommentId: () => ({}),
      commentReactionsByUser: () => [],
      getCommentReactionById: () => undefined,
    },
    createReaction: operation("createReaction"),
    removeReaction: operation("removeReaction"),
    createCommentReaction: operation("createCommentReaction"),
    removeCommentReaction: operation("removeCommentReaction"),
    issue: { getIssueById: () => ({}) },
  };
  const memo = (fn, deps) => {
    const slot = cursor++;
    if (!memos[slot] || deps.some((value, index) => !Object.is(value, memos[slot].deps[index]))) {
      memos[slot] = { deps, value: fn() };
    }
    return memos[slot].value;
  };
  const mocks = {
    react: { useMemo: memo, useCallback: (fn, deps) => memo(() => fn, deps), useState: (value) => [value, () => {}] },
    "next/navigation": { useParams: () => route },
    "@/hooks/use-issue-layout-store": { useIssueStoreType: () => "PROJECT" },
    "@/hooks/use-file-size": { useFileSize: () => ({ maxFileSize: 10 * 1024 * 1024 }) },
    "./helper": { useAttachmentOperations: () => ({ operations: {} }) },
    "react-dropzone": {
      useDropzone: (options) => {
        dropOptions = options;
        return { getRootProps: () => ({}), getInputProps: () => ({}), open: () => {} };
      },
    },
    "react/jsx-runtime": require("react/jsx-runtime"),
    "mobx-react": { observer: (component) => component },
    "@plane/i18n": { useTranslation: () => ({ t }), translate: (...args) => t(...args) },
    "@plane/blocks/toast": {
      setToast: (value) => toasts.push(value),
      setPromiseToast: (promise, options) => {
        toasts.push({ type: "loading", title: options.loading });
        pendingToasts.push(
          promise.then(
            (value) =>
              toasts.push({ type: "success", title: options.success.title, message: options.success.message(value) }),
            (error) => toasts.push({ type: "error", title: options.error.title, message: options.error.message(error) })
          )
        );
      },
    },
    "@plane/types": { EIssueServiceType: { ISSUES: "ISSUES" }, EFileAssetType: {} },
    "@plane/utils": { cn: () => "", formatTextList: () => "" },
    "@/hooks/store/use-issue-detail": { useIssueDetail: () => detail },
    "@/hooks/store/use-member": { useMember: () => ({ getUserDetails: () => ({}) }) },
    "@/hooks/store/use-project": { useProject: () => ({ getProjectById: () => ({}) }) },
    "@/hooks/store/use-editor-asset": { useEditorAsset: () => ({}) },
    "@/hooks/store/user": { useUser: () => ({ data: { id: "user" } }) },
  };
  mocks.react.default = mocks.react;
  return {
    toasts,
    setRoute: (value) => {
      route = value;
    },
    drop: (...args) => dropOptions.onDrop(...args),
    calls,
    detail,
    t: (...args) => t(...args),
    setFailure: (value) => {
      fail = value;
    },
    switchLanguage: async (locale) => {
      await i18n.changeLanguage(locale);
      t = i18n.getFixedT(locale);
    },
    render: (fn, ...args) => {
      cursor = 0;
      return fn(...args);
    },
    flush: async () => {
      await Promise.all(pendingToasts);
      await new Promise((resolve) => setImmediate(resolve));
    },
    load: (path) => {
      const source = readFileSync(new URL(`apps/web/${path}`, root), "utf8");
      const code = ts.transpileModule(source, {
        compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
      }).outputText;
      const exports = {};
      new Function("exports", "require", code)(
        exports,
        (name) => mocks[name] ?? new Proxy({}, { get: (_, key) => String(key) })
      );
      return exports;
    },
  };
}

test("attachment upload and deletion notifications follow language across success and failure", async () => {
  const h = await harness();
  const { useAttachmentOperations } = h.load("components/issues/issue-detail-widgets/attachments/helper.tsx");
  const file = { name: "notes.txt" };
  for (const locale of ["zh-CN", "en", "zh-CN"]) {
    await h.switchLanguage(locale);
    const { operations } = h.render(useAttachmentOperations, "team", "project", "item");
    h.setFailure(false);
    await operations.create(file);
    await h.flush();
    assert.equal(h.toasts.at(-2).title, h.t("editor_ui.uploading"));
    assert.equal(h.toasts.at(-1).message, h.t("file_upload.success", { fileName: h.t("common.attachment") }));
    assert.deepEqual(h.calls.at(-1).args, ["team", "project", "item", file]);
    await operations.remove("attachment");
    assert.equal(h.toasts.at(-1).message, h.t("entity.remove.success", { entity: h.t("common.attachment") }));
    assert.deepEqual(h.calls.at(-1).args, ["team", "project", "item", "attachment"]);
    // Upload failures are asynchronous, as with the real attachment store.
    const upload = h.detail.attachment.createAttachment;
    h.detail.attachment.createAttachment = () => Promise.reject(new Error("Upload rejected"));
    const failed = h.render(useAttachmentOperations, "team", "project", "item");
    await assert.rejects(failed.operations.create(file), /Upload rejected/);
    await h.flush();
    assert.equal(h.toasts.at(-1).type, "error");
    assert.equal(h.toasts.at(-1).message, h.t("attachment.error"));
    h.detail.attachment.createAttachment = upload;
    h.setFailure(true);
    await operations.remove("attachment");
    assert.equal(h.toasts.at(-1).message, h.t("entity.remove.failed", { entity: h.t("common.attachment") }));
  }
});

test("work item and both comment reaction entry points translate success and error notifications", async () => {
  const cases = [
    ["components/issues/issue-detail/reactions/issue.tsx", "IssueReaction"],
    ["components/issues/issue-detail/reactions/issue-comment.tsx", "IssueCommentReaction"],
    ["components/issues/issue-detail/issue-activity/helper.tsx", "useWorkItemCommentOperations"],
  ];
  for (const [path, exportName] of cases) {
    const h = await harness();
    const component = h.load(path)[exportName];
    for (const locale of ["zh-CN", "en"]) {
      await h.switchLanguage(locale);
      const isHook = exportName.startsWith("use");
      const result = isHook
        ? h.render(component, "team", "project", "item")
        : h.render(component, {
            workspaceSlug: "team",
            projectId: "project",
            issueId: "item",
            commentId: "comment",
            currentUser: { id: "user" },
          });
      const create = isHook
        ? () => result.addCommentReaction("comment", "128077")
        : () => result.props.children.props.addReactionButton.props.onChange("128077");
      for (const fails of [false, true]) {
        h.setFailure(fails);
        await create();
        await h.flush();
        assert.equal(h.toasts.at(-1).type, fails ? "error" : "success");
        assert.equal(h.toasts.at(-1).message, h.t(`updates.reaction.create.${fails ? "error" : "success"}.message`));
        assert.deepEqual(h.calls.at(-1).args, [
          "team",
          "project",
          exportName === "IssueReaction" ? "item" : "comment",
          "128077",
        ]);
      }
      if (isHook) {
        for (const fails of [false, true]) {
          h.setFailure(fails);
          await result.deleteCommentReaction("comment", "128077");
          assert.equal(h.toasts.at(-1).message, h.t(`updates.reaction.remove.${fails ? "error" : "success"}.message`));
        }
      } else {
        const reactions = exportName === "IssueReaction" ? h.detail.reaction : h.detail.commentReaction;
        const getter = exportName === "IssueReaction" ? "reactionsByUser" : "commentReactionsByUser";
        reactions[getter] = () => [{ reaction: "128077" }];
        const selected = h.render(component, {
          workspaceSlug: "team",
          projectId: "project",
          issueId: "item",
          commentId: "comment",
          currentUser: { id: "user" },
        });
        for (const fails of [false, true]) {
          h.setFailure(fails);
          selected.props.children.props.onReactionClick("👍");
          await h.flush();
          assert.equal(h.toasts.at(-1).message, h.t(`updates.reaction.remove.${fails ? "error" : "success"}.message`));
        }
        reactions[getter] = () => [];
      }
    }
  }
});

test("unavailable quick actions read the current language and translate the action name", async () => {
  const h = await harness();
  const { handleOptionalAction } = h.load("components/issues/issue-layouts/quick-action-dropdowns/helper.tsx");
  for (const locale of ["zh-CN", "en", "zh-CN"]) {
    await h.switchLanguage(locale);
    handleOptionalAction(undefined, h.t("issue.notifications.remove_from_cycle"));
    assert.equal(h.toasts.at(-1).title, h.t("issue.notifications.action_unavailable"));
    assert.equal(
      h.toasts.at(-1).message,
      h.t("issue.notifications.action_not_implemented", {
        actionName: h.t("issue.notifications.remove_from_cycle"),
      })
    );
  }
  let received;
  handleOptionalAction(
    (value) => {
      received = value;
    },
    "Archive",
    true
  );
  assert.equal(received, true);
});

test("new notification keys exist in every locale, preserve parameters, and render in Chinese", async () => {
  const source = dictionaries.en["work-item"].issue.notifications;
  for (const dir of readdirSync(locales, { withFileTypes: true }).filter((entry) => entry.isDirectory())) {
    const target = JSON.parse(readFileSync(new URL(`${dir.name}/work-item.json`, locales), "utf8")).issue.notifications;
    assert.deepEqual(Object.keys(target).toSorted(), Object.keys(source).toSorted(), dir.name);
    for (const [key, value] of Object.entries(target)) {
      assert.deepEqual(value.match(/\{\w+\}/g) ?? [], source[key].match(/\{\w+\}/g) ?? [], `${dir.name}:${key}`);
      if (dir.name !== "en") assert.notEqual(value, source[key], `${dir.name}:${key}`);
    }
  }
  const h = await harness();
  for (const locale of ["zh-CN", "zh-TW"]) {
    await h.switchLanguage(locale);
    for (const key of Object.keys(source)) {
      const text = h.t(`issue.notifications.${key}`, { actionName: h.t("archive"), limit: 50 });
      assert.match(text, /[\u3400-\u9fff]/);
      assert.doesNotMatch(text, /\{\w+\}|issue\.notifications/);
    }
  }
  await h.switchLanguage("en");
  assert.equal(h.t("issue.add.cycle.success", { count: 1 }), "Work item added to the cycle successfully.");
  assert.equal(h.t("issue.add.cycle.success", { count: 2 }), "Work items added to the cycle successfully.");
});

test("work item toast fields contain no hardcoded English and their translation keys resolve", () => {
  const resources = Object.fromEntries(
    ["en", "zh-CN"].map((locale) => [
      locale,
      readdirSync(new URL(`${locale}/`, locales))
        .filter((name) => name.endsWith(".json"))
        .map((name) => JSON.parse(readFileSync(new URL(`${locale}/${name}`, locales), "utf8"))),
    ])
  );
  const findings = [];
  const scan = (url) => {
    for (const entry of readdirSync(url, { withFileTypes: true })) {
      const path = new URL(entry.name + (entry.isDirectory() ? "/" : ""), url);
      if (entry.isDirectory()) {
        scan(path);
        continue;
      }
      if (!/\.tsx?$/.test(entry.name)) continue;
      const tree = ts.createSourceFile(
        path.pathname,
        readFileSync(path, "utf8"),
        ts.ScriptTarget.Latest,
        true,
        ts.ScriptKind.TSX
      );
      const checkExpression = (node) => {
        if (ts.isCallExpression(node) && ["t", "translate"].includes(node.expression.getText(tree))) {
          const arg = node.arguments[0];
          if (arg && ts.isStringLiteral(arg)) {
            for (const [locale, namespaceResources] of Object.entries(resources)) {
              const resolved = namespaceResources
                .map((dict) => arg.text.split(".").reduce((value, part) => value?.[part], dict))
                .find((value) => typeof value === "string");
              if (!resolved) findings.push(`${path.pathname}: missing ${locale} key ${arg.text}`);
            }
          }
          return;
        }
        if (
          (ts.isStringLiteral(node) ||
            ts.isNoSubstitutionTemplateLiteral(node) ||
            ts.isTemplateHead(node) ||
            ts.isTemplateMiddle(node) ||
            ts.isTemplateTail(node)) &&
          /[a-zA-Z]{3}/.test(node.text)
        ) {
          findings.push(`${path.pathname}: ${node.text}`);
        }
        ts.forEachChild(node, checkExpression);
      };
      const inspectOptions = (node) => {
        if (ts.isPropertyAssignment(node) && ["title", "message", "loading"].includes(node.name.getText(tree))) {
          checkExpression(node.initializer);
        } else ts.forEachChild(node, inspectOptions);
      };
      const visit = (node) => {
        if (ts.isCallExpression(node) && ["setToast", "setPromiseToast"].includes(node.expression.getText(tree))) {
          node.arguments.filter(ts.isObjectLiteralExpression).forEach(inspectOptions);
        }
        ts.forEachChild(node, visit);
      };
      visit(tree);
    }
  };
  scan(new URL("apps/web/components/issues/", root));
  assert.deepEqual(findings, []);
});

test("attachment rejection messages preserve the file count rule and configured size limit", async () => {
  const h = await harness();
  const { IssueAttachmentActionButton } = h.load(
    "components/issues/issue-detail-widgets/attachments/quick-action-button.tsx"
  );
  for (const locale of ["zh-CN", "en"]) {
    await h.switchLanguage(locale);
    h.render(IssueAttachmentActionButton, { workspaceSlug: "team", projectId: "project", issueId: "item" });
    h.drop([], [{ file: {} }, { file: {} }]);
    assert.equal(h.toasts.at(-1).message, h.t("attachment.only_one_file_allowed"));
    h.drop([], [{ file: {} }]);
    assert.equal(h.toasts.at(-1).message, h.t("attachment.file_size_limit", { size: 10 }));
    assert.match(h.toasts.at(-1).message, /10/);
  }
});

function findSubmit(node) {
  if (Array.isArray(node)) return node.map(findSubmit).find(Boolean);
  if (!node || typeof node !== "object") return undefined;
  return node.props?.handleOnSubmit ?? findSubmit(node.props?.children);
}

test("list and kanban additions identify the cycle or module in localized success and failure messages", async () => {
  for (const layout of ["list", "kanban"]) {
    const h = await harness();
    const { HeaderGroupByCard } = h.load(`components/issues/issue-layouts/${layout}/headers/group-by-card.tsx`);
    for (const locale of ["zh-CN", "en"]) {
      await h.switchLanguage(locale);
      for (const entity of ["cycle", "module"]) {
        h.setRoute({ workspaceSlug: "team", projectId: "project", [`${entity}Id`]: "container" });
        let fail = false;
        let submitted;
        const tree = h.render(HeaderGroupByCard, {
          groupID: "All Issues",
          groupBy: null,
          title: "All work items",
          count: 3,
          canEditProperties: () => false,
          disableIssueCreation: true,
          selectionHelpers: { isGroupSelected: () => "empty" },
          isExpanded: true,
          addIssuesToView: async (ids) => {
            submitted = ids;
            if (fail) throw new Error("Add failed");
          },
        });
        const submit = findSubmit(tree);
        assert.equal(typeof submit, "function");
        await submit([{ id: "one" }, { id: "two" }]);
        assert.deepEqual(submitted, ["one", "two"]);
        assert.equal(
          h.toasts.at(-1).message,
          entity === "module" ? h.t("issue.notifications.module_added") : h.t("issue.add.cycle.success", { count: 2 })
        );
        fail = true;
        await submit([{ id: "one" }]);
        assert.equal(h.toasts.at(-1).message, h.t(`issue.notifications.${entity}_add_failed`));
      }
    }
  }
});
