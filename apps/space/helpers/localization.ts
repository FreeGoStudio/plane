import type { TTranslationStore } from "@plane/i18n";
import type { IGroupByColumn } from "@plane/types";

/** Translate only system groups. State, cycle, module, label and member names belong to users. */
export function localizeGroupColumns(
  columns: IGroupByColumn[] | undefined,
  groupBy: string | null | undefined,
  t: TTranslationStore["t"]
): IGroupByColumn[] | undefined {
  return columns?.map((column) => {
    if (column.id === "All Issues") return { ...column, name: t("space_ui.all_work_items") };
    if (column.id === "None") return { ...column, name: t("space_ui.no_group") };
    if (groupBy === "priority" && ["urgent", "high", "medium", "low", "none"].includes(column.id)) {
      return { ...column, name: t(`issue.priority.${column.id}`) };
    }
    return column;
  });
}
