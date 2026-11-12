/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import type { TEditorHookProps } from "@/types";
import { useEditor } from "../use-editor";

const state = vi.hoisted(() => ({ editor: null as unknown, locale: "en" }));
vi.mock("@plane/i18n", () => ({ useTranslation: () => ({ currentLocale: state.locale }) }));
vi.mock("@tiptap/react", () => ({
  useEditor: () => state.editor,
  useEditorState: () => ({ assets: [] }),
}));
vi.mock("@/extensions", () => ({ CoreEditorExtensions: () => [] }));
vi.mock("@/props", () => ({ CoreEditorProps: () => ({}) }));
vi.mock("@/helpers/editor-ref", () => ({ getEditorRefHelpers: () => ({}) }));

it("opens an initially unavailable editor and keeps language synchronization working", async () => {
  Reflect.set(globalThis, "IS_REACT_ACT_ENVIRONMENT", true);
  const container = document.createElement("div");
  const root = createRoot(container);
  const dispatch = vi.fn();
  const setMeta = vi.fn(() => ({ localeTransaction: true }));
  const editor = { isDestroyed: false, commands: {}, state: { tr: { setMeta } }, view: { dispatch } };
  const props = { fileHandler: {}, forwardedRef: { current: null } } as unknown as TEditorHookProps;
  function Harness() {
    const result = useEditor(props);
    return createElement("div", null, result ? "ready" : "loading");
  }

  try {
    state.editor = null;
    state.locale = "en";
    await act(() => root.render(createElement(Harness)));
    expect(container.textContent).toBe("loading");
    expect(dispatch).not.toHaveBeenCalled();

    state.editor = editor;
    await act(() => root.render(createElement(Harness)));
    expect(container.textContent).toBe("ready");
    expect(setMeta).toHaveBeenLastCalledWith("locale", "en");

    state.locale = "zh-CN";
    await act(() => root.render(createElement(Harness)));
    expect(setMeta).toHaveBeenLastCalledWith("locale", "zh-CN");
    expect(dispatch).toHaveBeenCalledTimes(2);

    state.editor = null;
    await act(() => root.render(createElement(Harness)));
    expect(container.textContent).toBe("loading");
    expect(dispatch).toHaveBeenCalledTimes(2);
  } finally {
    await act(() => root.unmount());
    Reflect.deleteProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT");
  }
});
