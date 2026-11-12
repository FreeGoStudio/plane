/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import { observer } from "mobx-react";
import { Logo } from "@plane/blocks/emoji-icon-picker";
// components
import { FilterSubmenu } from "@/components/common/filters/filter-submenu";
// hooks
import { useProject } from "@/hooks/store/use-project";

type Props = {
  appliedFilters: string[] | null;
  handleUpdate: (val: string) => void;
};

export const FilterProjects = observer(function FilterProjects(props: Props) {
  const { t } = useTranslation();
  const { appliedFilters, handleUpdate } = props;
  // store hooks
  const { getProjectById, joinedProjectIds } = useProject();
  // derived values
  const options = (joinedProjectIds ?? []).flatMap((projectId) => {
    const project = getProjectById(projectId);
    if (!project) return [];
    return [
      {
        value: project.id,
        label: project.name,
        icon: (
          <span className="grid size-4 shrink-0 place-items-center">
            <Logo logo={project.logo_props} size={12} />
          </span>
        ),
      },
    ];
  });

  return (
    <FilterSubmenu
      label={t("automations.global_automations.table.scope.project.label")}
      options={options}
      appliedFilters={appliedFilters}
      onToggle={handleUpdate}
      searchable
    />
  );
});
