/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import type { Editor } from "@tiptap/core";
import { TableMap } from "@tiptap/pm/tables";
import {
  ArrowDownOutline,
  CloseOutline,
  CopyOutline,
  DeleteOutline,
  ToggleFilled,
  TopArrowOutline,
} from "@makeplane/propel/icons";
import { Icon } from "@makeplane/propel/components/icon";
import { MenuItemContent, MenuItemTitle, MenuItemTrailing, MenuSeparator } from "@makeplane/propel/elements/menu";
// extensions
import type { ISvgIcons } from "@plane/blocks/icons";
import { FloatingMenuItem } from "@/components/menus/floating-menu/root";
import { findTable, getSelectedRows } from "@/extensions/table/table/utilities/helpers";
// local imports
import { duplicateRows } from "../actions";
import { TableDragHandleDropdownColorSelector } from "../color-selector";

const DROPDOWN_ITEMS: {
  key: string;
  label: string;
  icon: React.FC<React.SVGProps<SVGSVGElement>> | React.FC<ISvgIcons>;
  action: (editor: Editor) => void;
}[] = [
  {
    key: "insert-above",
    label: "editor_controls.insert_above",
    icon: TopArrowOutline,
    action: (editor) => editor.chain().focus().addRowBefore().run(),
  },
  {
    key: "insert-below",
    label: "editor_controls.insert_below",
    icon: ArrowDownOutline,
    action: (editor) => editor.chain().focus().addRowAfter().run(),
  },
  {
    key: "duplicate",
    label: "editor_controls.duplicate",
    icon: CopyOutline,
    action: (editor) => {
      const table = findTable(editor.state.selection);
      if (!table) return;

      const tableMap = TableMap.get(table.node);
      let tr = editor.state.tr;
      const selectedRows = getSelectedRows(editor.state.selection, tableMap);
      tr = duplicateRows(table, selectedRows, tr);
      editor.view.dispatch(tr);
    },
  },
  {
    key: "clear-contents",
    label: "editor_controls.clear_contents",
    icon: CloseOutline,
    action: (editor) => editor.chain().focus().clearSelectedCells().run(),
  },
  {
    key: "delete",
    label: "editor_controls.delete",
    icon: DeleteOutline,
    action: (editor) => editor.chain().focus().deleteRow().run(),
  },
];

type Props = {
  editor: Editor;
  onClose: () => void;
};

export function RowOptionsDropdown(props: Props) {
  const { t } = useTranslation();
  const { editor, onClose } = props;

  return (
    <>
      <FloatingMenuItem
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          editor.chain().focus().toggleHeaderRow().run();
          onClose();
        }}
      >
        <MenuItemContent>
          <MenuItemTitle>{t("editor_controls.header_row")}</MenuItemTitle>
        </MenuItemContent>
        <MenuItemTrailing>
          <Icon icon={ToggleFilled} tint="secondary" />
        </MenuItemTrailing>
      </FloatingMenuItem>
      <MenuSeparator render={<hr />} />
      <TableDragHandleDropdownColorSelector editor={editor} onSelect={onClose} />
      {DROPDOWN_ITEMS.map((item) => (
        <FloatingMenuItem
          key={item.key}
          type="button"
          variant={item.key === "delete" ? "danger" : "neutral"}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            item.action(editor);
            onClose();
          }}
        >
          <Icon icon={item.icon} />
          <MenuItemContent>
            <MenuItemTitle>{t(item.label)}</MenuItemTitle>
          </MenuItemContent>
        </FloatingMenuItem>
      ))}
    </>
  );
}
