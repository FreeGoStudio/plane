/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import type { Editor } from "@tiptap/core";
// plane imports
import { Collapsible } from "@makeplane/propel/components/collapsible";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/elements/icon-button";
import { MenuLabel, MenuLabelTitle } from "@makeplane/propel/elements/menu";
import { DeactivatedOutline, PaletteOutline } from "@makeplane/propel/icons";
// constants
import { COLORS_LIST } from "@/constants/common";
import { CORE_EXTENSIONS } from "@/constants/extension";

// TODO: implement text color selector

type Props = {
  editor: Editor;
  onSelect: (color: string | null) => void;
};

const handleBackgroundColorChange = (editor: Editor, color: string | null) => {
  editor
    .chain()
    .focus()
    .updateAttributes(CORE_EXTENSIONS.TABLE_CELL, {
      background: color,
    })
    .run();
};

// const handleTextColorChange = (editor: Editor, color: string | null) => {
//   editor
//     .chain()
//     .focus()
//     .updateAttributes(CORE_EXTENSIONS.TABLE_CELL, {
//       textColor: color,
//     })
//     .run();
// };

export function TableDragHandleDropdownColorSelector(props: Props) {
  const { t } = useTranslation();
  const { editor, onSelect } = props;

  return (
    <Collapsible defaultOpen hug icon={<Icon icon={PaletteOutline} />} trigger={t("editor_controls.color")}>
      <div className="pb-2">
        {/* <div className="space-y-1.5">
          <p className="text-11 text-tertiary font-semibold">{t("editor_controls.text_colors")}</p>
          <div className="flex items-center flex-wrap gap-2">
            {COLORS_LIST.map((color) => (
              <button
                key={color.key}
                type="button"
                className="flex-shrink-0 size-6 rounded-sm border-[0.5px] border-strong-1 hover:opacity-60 transition-opacity"
                style={{
                  backgroundColor: color.textColor,
                }}
                onClick={() => handleTextColorChange(editor, color.textColor)}
              />
            ))}
            <button
              type="button"
              className="flex-shrink-0 size-6 grid place-items-center rounded-sm text-tertiary border-[0.5px] border-strong-1 hover:bg-layer-1 transition-colors"
              onClick={() => handleTextColorChange(editor, null)}
            >
              <Ban className="size-4" />
            </button>
          </div>
        </div> */}
        <div role="group" aria-label={t("editor_controls.background_colors")}>
          <MenuLabel>
            <MenuLabelTitle>{t("editor_controls.background_colors")}</MenuLabelTitle>
          </MenuLabel>
          <div className="flex flex-wrap items-center gap-2 px-2 pt-1">
            {COLORS_LIST.map((color) => (
              <button
                key={color.key}
                type="button"
                aria-label={t("editor_controls.color_background_label", {
                  color: t(`editor_controls.colors.${color.key}`),
                })}
                className="size-6 shrink-0 cursor-pointer rounded-sm border-xs border-subtle transition-opacity outline-none hover:opacity-60 focus-visible:ring-2 focus-visible:ring-accent-strong focus-visible:ring-offset-1"
                style={{
                  backgroundColor: color.backgroundColor,
                }}
                onClick={() => {
                  handleBackgroundColorChange(editor, color.backgroundColor);
                  onSelect(color.backgroundColor);
                }}
              />
            ))}
            <IconButton
              type="button"
              variant="secondary"
              size="sm"
              aria-label={t("editor_controls.clear_background_color")}
              onClick={() => {
                handleBackgroundColorChange(editor, null);
                onSelect(null);
              }}
            >
              <Icon icon={DeactivatedOutline} />
            </IconButton>
          </div>
        </div>
      </div>
    </Collapsible>
  );
}
