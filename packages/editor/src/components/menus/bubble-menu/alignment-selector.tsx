/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import type { Editor } from "@tiptap/core";
import type { ComponentType, SVGProps } from "react";
import { AlignCenterOutline, AlignLeftOutline, AlignRightOutline } from "@makeplane/propel/icons";
// plane imports
import { Icon } from "@makeplane/propel/components/icon";
import { ToolbarButton, ToolbarGroup } from "@makeplane/propel/elements/toolbar";
// components
import { TextAlignItem } from "@/components/menus";
// types
import type { TEditorCommands } from "@/types";
import type { EditorStateType } from "./root";

type Props = {
  editor: Editor;
  editorState: EditorStateType;
};

export function TextAlignmentSelector(props: Props) {
  const { t } = useTranslation();
  const { editor, editorState } = props;
  const menuItem = TextAlignItem(editor);

  const textAlignmentOptions: {
    itemKey: TEditorCommands;
    renderKey: string;
    label: string;
    icon: ComponentType<SVGProps<SVGSVGElement>>;
    command: () => void;
    isActive: () => boolean;
  }[] = [
    {
      itemKey: "text-align",
      renderKey: "text-align-left",
      label: t("editor_ui.align_left"),
      icon: AlignLeftOutline,
      command: () =>
        menuItem.command({
          alignment: "left",
        }),
      isActive: () => editorState.left,
    },
    {
      itemKey: "text-align",
      renderKey: "text-align-center",
      label: t("editor_ui.align_center"),
      icon: AlignCenterOutline,
      command: () =>
        menuItem.command({
          alignment: "center",
        }),
      isActive: () => editorState.center,
    },
    {
      itemKey: "text-align",
      renderKey: "text-align-right",
      label: t("editor_ui.align_right"),
      icon: AlignRightOutline,
      command: () =>
        menuItem.command({
          alignment: "right",
        }),
      isActive: () => editorState.right,
    },
  ];
  if (editorState.code) return null;

  return (
    <ToolbarGroup role="group" aria-label={t("editor_ui.text_alignment")}>
      {textAlignmentOptions.map((item) => (
        <ToolbarButton
          key={item.renderKey}
          type="button"
          size="sm"
          labeled={false}
          aria-label={item.label}
          aria-pressed={item.isActive()}
          data-pressed={item.isActive() ? "" : undefined}
          onClick={(e) => {
            e.stopPropagation();
            item.command();
          }}
        >
          <Icon icon={item.icon} />
        </ToolbarButton>
      ))}
    </ToolbarGroup>
  );
}
