/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TIssueActivity } from "@plane/types";

export const getRelationActivityMessageKey = (activity: TIssueActivity | undefined): string | undefined => {
  if (!activity) return;

  switch (activity.field) {
    case "blocking":
      return activity.old_value === "" ? "work_item_activity.blocking_added" : "work_item_activity.blocking_removed";
    case "blocked_by":
      return activity.old_value === ""
        ? "work_item_activity.blocked_by_added"
        : "work_item_activity.blocked_by_removed";
    case "duplicate":
      return activity.old_value === "" ? "work_item_activity.duplicate_added" : "work_item_activity.duplicate_removed";
    case "relates_to":
      return activity.old_value === ""
        ? "work_item_activity.relates_to_added"
        : "work_item_activity.relates_to_removed";
  }

  return;
};
