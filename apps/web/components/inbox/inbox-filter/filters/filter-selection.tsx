/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import { observer } from "mobx-react";
// hooks
import { useLabel } from "@/hooks/store/use-label";
import { useMember } from "@/hooks/store/use-member";
// local imports
import { FilterDate } from "./date";
import { FilterLabels } from "./labels";
import { FilterMember } from "./members";
import { FilterPriority } from "./priority";
import { FilterStatus } from "./status";

export const InboxIssueFilterSelection = observer(function InboxIssueFilterSelection() {
  const { t } = useTranslation();
  // hooks
  const {
    project: { projectMemberIds },
  } = useMember();
  const { projectLabels } = useLabel();

  return (
    <>
      {/* status */}
      <FilterStatus />
      {/* Priority */}
      <FilterPriority />
      {/* assignees */}
      <FilterMember filterKey="assignees" label={t("assignees")} memberIds={projectMemberIds ?? []} />
      {/* Created By */}
      <FilterMember filterKey="created_by" label={t("common.created_by")} memberIds={projectMemberIds ?? []} />
      {/* Labels */}
      <FilterLabels labels={projectLabels ?? []} />
      {/* Created at */}
      <FilterDate filterKey="created_at" label={t("common.date_filter.created_date")} />
      {/* Updated at */}
      <FilterDate filterKey="updated_at" label={t("common.sort.updated_on")} />
    </>
  );
});
