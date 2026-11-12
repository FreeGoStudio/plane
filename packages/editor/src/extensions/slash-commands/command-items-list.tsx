/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { translate as t } from "@plane/i18n";
import {
  ChatOutline,
  CodeOutline,
  H1Outline,
  H2Outline,
  H3Outline,
  H4Outline,
  H5Outline,
  H6Outline,
  ImageOutline,
  ListOutline,
  MinusSquareOutline,
  NumberedListOutline,
  QuoteOutline,
  ReactionOutline,
  TableEditorOutline,
  TextOutline,
  ToDoOutline,
} from "@makeplane/propel/icons";
// constants
import { COLORS_LIST } from "@/constants/common";
// helpers
import {
  insertTableCommand,
  toggleBlockquote,
  toggleBulletList,
  toggleOrderedList,
  toggleTaskList,
  toggleHeading,
  toggleTextColor,
  toggleBackgroundColor,
  insertImage,
  insertCallout,
  setText,
  openEmojiPicker,
} from "@/helpers/editor-commands";
// plane editor extensions
import { coreEditorAdditionalSlashCommandOptions } from "@/extensions/additional-slash-command-options";
// types
import type { CommandProps, ISlashCommandItem, TSlashCommandSectionKeys } from "@/types";
// local types
import type { TExtensionProps, TSlashCommandAdditionalOption } from "./root";

export type TSlashCommandSection = {
  key: TSlashCommandSectionKeys;
  title?: string;
  items: ISlashCommandItem[];
};

export const getSlashCommandFilteredSections =
  (args: TExtensionProps) =>
  ({ query }: { query: string }): TSlashCommandSection[] => {
    const { additionalOptions: externalAdditionalOptions, disabledExtensions, flaggedExtensions } = args;
    const SLASH_COMMAND_SECTIONS: TSlashCommandSection[] = [
      {
        key: "general",
        items: [
          {
            commandKey: "text",
            key: "text",
            title: t("editor_ui.text"),
            description: t("editor_ui.plain_text_description"),
            searchTerms: ["p", "paragraph"],
            icon: <TextOutline className="size-3.5" />,
            command: ({ editor, range }) => setText(editor, range),
          },
          {
            commandKey: "h1",
            key: "h1",
            title: t("editor_ui.h1"),
            description: t("editor_ui.large_heading"),
            searchTerms: ["title", "big", "large"],
            icon: <H1Outline className="size-3.5" />,
            command: ({ editor, range }) => toggleHeading(editor, 1, range),
          },
          {
            commandKey: "h2",
            key: "h2",
            title: t("editor_ui.h2"),
            description: t("editor_ui.medium_heading"),
            searchTerms: ["subtitle", "medium"],
            icon: <H2Outline className="size-3.5" />,
            command: ({ editor, range }) => toggleHeading(editor, 2, range),
          },
          {
            commandKey: "h3",
            key: "h3",
            title: t("editor_ui.h3"),
            description: t("editor_ui.small_heading"),
            searchTerms: ["subtitle", "small"],
            icon: <H3Outline className="size-3.5" />,
            command: ({ editor, range }) => toggleHeading(editor, 3, range),
          },
          {
            commandKey: "h4",
            key: "h4",
            title: t("editor_ui.h4"),
            description: t("editor_ui.small_heading"),
            searchTerms: ["subtitle", "small"],
            icon: <H4Outline className="size-3.5" />,
            command: ({ editor, range }) => toggleHeading(editor, 4, range),
          },
          {
            commandKey: "h5",
            key: "h5",
            title: t("editor_ui.h5"),
            description: t("editor_ui.small_heading"),
            searchTerms: ["subtitle", "small"],
            icon: <H5Outline className="size-3.5" />,
            command: ({ editor, range }) => toggleHeading(editor, 5, range),
          },
          {
            commandKey: "h6",
            key: "h6",
            title: t("editor_ui.h6"),
            description: t("editor_ui.small_heading"),
            searchTerms: ["subtitle", "small"],
            icon: <H6Outline className="size-3.5" />,
            command: ({ editor, range }) => toggleHeading(editor, 6, range),
          },

          {
            commandKey: "numbered-list",
            key: "numbered-list",
            title: t("editor_ui.numbered_list"),
            description: t("editor_ui.numbered_list_description"),
            searchTerms: ["ordered"],
            icon: <NumberedListOutline className="size-3.5" />,
            command: ({ editor, range }) => toggleOrderedList(editor, range),
          },
          {
            commandKey: "bulleted-list",
            key: "bulleted-list",
            title: t("editor_ui.bulleted_list"),
            description: t("editor_ui.bulleted_list_description"),
            searchTerms: ["unordered", "point"],
            icon: <ListOutline className="size-3.5" />,
            command: ({ editor, range }) => toggleBulletList(editor, range),
          },
          {
            commandKey: "to-do-list",
            key: "to-do-list",
            title: t("editor_ui.todo_list"),
            description: t("editor_ui.todo_list_description"),
            searchTerms: ["todo", "task", "list", "check", "checkbox"],
            icon: <ToDoOutline className="size-3.5" />,
            command: ({ editor, range }) => toggleTaskList(editor, range),
          },
          {
            commandKey: "table",
            key: "table",
            title: t("editor_ui.table"),
            description: t("editor_ui.table_description"),
            searchTerms: ["table", "cell", "db", "data", "tabular"],
            icon: <TableEditorOutline className="size-3.5" />,
            command: ({ editor, range }) => insertTableCommand(editor, range),
          },
          {
            commandKey: "quote",
            key: "quote",
            title: t("editor_ui.quote"),
            description: t("editor_ui.quote_description"),
            searchTerms: ["blockquote"],
            icon: <QuoteOutline className="size-3.5" />,
            command: ({ editor, range }) => toggleBlockquote(editor, range),
          },
          {
            commandKey: "code",
            key: "code",
            title: t("editor_ui.code"),
            description: t("editor_ui.code_description"),
            searchTerms: ["codeblock"],
            icon: <CodeOutline className="size-3.5" />,
            command: ({ editor, range }) => editor.chain().focus().deleteRange(range).toggleCodeBlock().run(),
          },
          {
            commandKey: "callout",
            key: "callout",
            title: t("editor_ui.callout"),
            icon: <ChatOutline className="size-3.5" />,
            description: t("editor_ui.callout_description"),
            searchTerms: ["callout", "comment", "message", "info", "alert"],
            command: ({ editor, range }: CommandProps) => insertCallout(editor, range),
          },
          {
            commandKey: "divider",
            key: "divider",
            title: t("editor_ui.divider"),
            description: t("editor_ui.divider_description"),
            searchTerms: ["line", "divider", "horizontal", "rule", "separate"],
            icon: <MinusSquareOutline className="size-3.5" />,
            command: ({ editor, range }) => editor.chain().focus().deleteRange(range).setHorizontalRule().run(),
          },
          {
            commandKey: "emoji",
            key: "emoji",
            title: t("editor_ui.emoji"),
            description: t("editor_ui.emoji_description"),
            searchTerms: ["emoji", "icons", "reaction", "emoticon", "emotags"],
            icon: <ReactionOutline className="size-3.5" />,
            command: ({ editor, range }) => {
              openEmojiPicker(editor, range);
            },
          },
        ],
      },
      {
        key: "text-colors",
        title: t("editor_ui.colors"),
        items: [
          {
            commandKey: "text-color",
            key: "text-color-default",
            title: t("editor_ui.default"),
            description: t("editor_ui.change_color"),
            searchTerms: ["color", "text", "default"],
            icon: <TextOutline className="size-3.5 text-primary" />,
            command: ({ editor, range }) => toggleTextColor(undefined, editor, range),
          },
          ...COLORS_LIST.map(
            (color) =>
              ({
                commandKey: "text-color",
                key: `text-color-${color.key}`,
                title: t(`editor_controls.colors.${color.key}`),
                description: t("editor_ui.change_color"),
                searchTerms: ["color", "text", color.label],

                icon: (
                  <TextOutline
                    className="size-3.5"
                    style={{
                      color: color.textColor,
                    }}
                  />
                ),

                command: ({ editor, range }) => toggleTextColor(color.key, editor, range),
              }) as ISlashCommandItem
          ),
        ],
      },
      {
        key: "background-colors",
        title: t("editor_ui.background_colors"),
        items: [
          {
            commandKey: "background-color",
            key: "background-color-default",
            title: t("editor_ui.default_background"),
            description: t("editor_ui.change_background"),
            searchTerms: ["color", "bg", "background", "default"],
            icon: <TextOutline className="size-3.5" />,
            iconContainerStyle: {
              borderRadius: "4px",
              backgroundColor: "var(--background-color-surface-1)",
              border: "1px solid var(--border-color-strong)",
            },
            command: ({ editor, range }) => toggleTextColor(undefined, editor, range),
          },
          ...COLORS_LIST.map(
            (color) =>
              ({
                commandKey: "background-color",
                key: `background-color-${color.key}`,
                title: t(`editor_controls.colors.${color.key}`),
                description: t("editor_ui.change_background"),
                searchTerms: ["color", "bg", "background", color.label],
                icon: <TextOutline className="size-3.5" />,

                iconContainerStyle: {
                  borderRadius: "4px",
                  backgroundColor: color.backgroundColor,
                },

                command: ({ editor, range }) => toggleBackgroundColor(color.key, editor, range),
              }) as ISlashCommandItem
          ),
        ],
      },
    ];

    const internalAdditionalOptions: TSlashCommandAdditionalOption[] = [];
    if (!disabledExtensions?.includes("image")) {
      internalAdditionalOptions.push({
        commandKey: "image",
        key: "image",
        title: t("editor_ui.image"),
        icon: <ImageOutline className="size-3.5" />,
        description: t("editor_ui.image_description"),
        searchTerms: ["img", "photo", "picture", "media", "upload"],
        command: ({ editor, range }: CommandProps) => insertImage({ editor, event: "insert", range }),
        section: "general",
        pushAfter: "code",
      });
    }

    [
      ...internalAdditionalOptions,
      ...(externalAdditionalOptions ?? []),
      ...coreEditorAdditionalSlashCommandOptions({
        disabledExtensions,
        flaggedExtensions,
      }),
    ]?.forEach((item) => {
      const sectionToPushTo = SLASH_COMMAND_SECTIONS.find((s) => s.key === item.section) ?? SLASH_COMMAND_SECTIONS[0];
      const itemIndexToPushAfter = sectionToPushTo.items.findIndex((i) => i.commandKey === item.pushAfter);
      if (itemIndexToPushAfter !== -1) {
        sectionToPushTo.items.splice(itemIndexToPushAfter + 1, 0, item);
      } else {
        sectionToPushTo.items.push(item);
      }
    });

    const filteredSlashSections = SLASH_COMMAND_SECTIONS.map((section) => ({
      key: section.key,
      title: section.title,
      items: section.items.filter((item) => {
        if (typeof query !== "string") return;

        const lowercaseQuery = query.toLowerCase();
        return (
          item.title.toLowerCase().includes(lowercaseQuery) ||
          item.description.toLowerCase().includes(lowercaseQuery) ||
          item.searchTerms.some((term) => term.toLowerCase().includes(lowercaseQuery))
        );
      }),
    }));

    return filteredSlashSections.filter((s) => s.items.length !== 0);
  };
