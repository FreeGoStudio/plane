/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import { ISSUE_PRIORITIES } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { PriorityIcon } from "@plane/blocks/icons";
import type { TIssuePriorities } from "@plane/types";
// components
import { FilterSubmenu } from "@/components/common/filters/filter-submenu";
// hooks
import { useProjectInbox } from "@/hooks/store/use-project-inbox";

export const FilterPriority = observer(function FilterPriority() {
  // hooks
  const { t } = useTranslation();
  const priorityOptions = ISSUE_PRIORITIES.map((priority) => ({
    value: priority.key,
    label: t(priority.key),
    icon: <PriorityIcon priority={priority.key} className="h-3.5 w-3.5" />,
  }));
  const { inboxFilters, handleInboxIssueFilters } = useProjectInbox();
  // derived values
  const filterValue = inboxFilters?.priority || [];

  const handleToggle = (value: TIssuePriorities) =>
    handleInboxIssueFilters(
      "priority",
      filterValue.includes(value) ? filterValue.filter((v) => v !== value) : [...filterValue, value]
    );

  return (
    <FilterSubmenu
      label={t("common.priority")}
      options={priorityOptions}
      appliedFilters={filterValue}
      onToggle={handleToggle}
    />
  );
});
