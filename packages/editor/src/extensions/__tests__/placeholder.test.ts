/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { setLanguage, translate as t } from "@plane/i18n";
import { Editor } from "@tiptap/core";
import { StarterKit } from "@tiptap/starter-kit";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { CustomPlaceholderExtension } from "../placeholder";

let editor: Editor;
const createEditor = (content: string, showPlaceholderOnEmpty = false) => {
  editor = new Editor({
    element: document.createElement("div"),
    content,
    extensions: [StarterKit, CustomPlaceholderExtension({ placeholder: "Add comment", showPlaceholderOnEmpty })],
  });
  return editor;
};
const placeholders = () =>
  [...editor.view.dom.querySelectorAll("[data-placeholder]")].map((element) =>
    element.getAttribute("data-placeholder")
  );

beforeEach(async () => {
  await setLanguage("en");
});

it("refreshes a sticky placeholder in place when switching from Chinese to English", async () => {
  await setLanguage("zh-CN");
  editor = new Editor({
    element: document.createElement("div"),
    content: "<p></p>",
    extensions: [
      StarterKit,
      CustomPlaceholderExtension({ placeholder: () => t("stickies.placeholder"), showPlaceholderOnEmpty: true }),
    ],
  });
  const original = editor.getJSON();
  const selection = editor.state.selection.toJSON();
  expect(placeholders()).toEqual(["点击此处输入"]);
  await setLanguage("en");
  editor.view.dispatch(editor.state.tr.setMeta("locale", "en"));
  expect(placeholders()).toEqual(["click to type here"]);
  expect(editor.getJSON()).toEqual(original);
  expect(editor.state.selection.toJSON()).toEqual(selection);
});
it("refreshes the comment placeholder without changing the document or selection", async () => {
  await setLanguage("zh-CN");
  editor = new Editor({
    element: document.createElement("div"),
    content: "<p></p>",
    extensions: [
      StarterKit,
      CustomPlaceholderExtension({
        placeholder: () => t("issue.comments.placeholder"),
        showPlaceholderOnEmpty: true,
      }),
    ],
  });
  const original = editor.getJSON();
  const selection = editor.state.selection.toJSON();
  expect(placeholders()).toEqual([t("issue.comments.placeholder")]);
  await setLanguage("en");
  editor.view.dispatch(editor.state.tr.setMeta("locale", "en"));
  expect(placeholders()).toEqual(["Add comment"]);
  expect(editor.getJSON()).toEqual(original);
  expect(editor.state.selection.toJSON()).toEqual(selection);
});

afterEach(() => editor.destroy());

describe("CustomPlaceholderExtension", () => {
  it("shows the placeholder again once typed text is deleted", () => {
    createEditor("<p></p>", true);
    editor.commands.insertContentAt(1, "abc");
    expect(placeholders()).toEqual([]);
    editor.commands.deleteRange({ from: 1, to: 4 });
    expect(placeholders()).toEqual(["Add comment"]);
  });

  it("clears the placeholder from an empty line the caret has left", () => {
    createEditor("<p>first</p><p></p><p>third</p>");
    editor.commands.setTextSelection(8);
    expect(placeholders()).toEqual(["Add comment"]);
    editor.commands.setTextSelection(2);
    expect(placeholders()).toEqual([]);
  });

  it("labels an empty heading with its level", () => {
    createEditor("<h2></h2>");
    editor.commands.setTextSelection(1);
    expect(placeholders()).toEqual(["Heading 2"]);
  });
});

it("refreshes translated headings without modifying the document or selection", async () => {
  createEditor("<h2></h2><p>用户原文 English</p>");
  editor.commands.setTextSelection(1);
  const original = editor.getJSON();
  const selection = editor.state.selection.toJSON();
  await setLanguage("zh-CN");
  editor.view.dispatch(editor.state.tr.setMeta("locale", "zh-CN"));
  expect(placeholders()).toEqual(["2 级标题"]);
  expect(editor.getJSON()).toEqual(original);
  expect(editor.state.selection.toJSON()).toEqual(selection);
  await setLanguage("en");
  editor.view.dispatch(editor.state.tr.setMeta("locale", "en"));
  expect(placeholders()).toEqual(["Heading 2"]);
});
