/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { CalendarOutline, LeadOutline } from "@makeplane/propel/icons";
// Plane imports
import { MODULE_STATUS, EUserPermissions, EUserPermissionsLevel, IS_FAVORITE_MENU_OPEN } from "@plane/constants";
import { useLocalStorage } from "@plane/hooks";
import { useTranslation } from "@plane/i18n";
import { setPromiseToast, setToast } from "@plane/blocks/toast";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import type { IModule } from "@plane/types";
import { FavoriteStar } from "@plane/blocks/common";
import { DateRangeSelect } from "@plane/blocks/property-select";
import { renderFormattedPayloadDate, getDate } from "@plane/utils";
// components
import { ModuleQuickActions } from "@/components/modules";
import { ModuleStatusDropdown } from "@/components/modules/module-status-dropdown";
// hooks
import { useMember } from "@/hooks/store/use-member";
import { useModule } from "@/hooks/store/use-module";
import { useUserPermissions, useUserProfile } from "@/hooks/store/user";
import { ButtonAvatars } from "../dropdowns/member/avatar";

type Props = {
  moduleId: string;
  moduleDetails: IModule;
  parentRef: React.RefObject<HTMLDivElement | null>;
};

export const ModuleListItemAction = observer(function ModuleListItemAction(props: Props) {
  const { moduleId, moduleDetails, parentRef } = props;
  // router
  const { workspaceSlug, projectId } = useParams();
  //   store hooks
  const { allowPermissions } = useUserPermissions();
  const { addModuleToFavorites, removeModuleFromFavorites, updateModuleDetails } = useModule();
  const { getUserDetails } = useMember();
  const { data: userProfile } = useUserProfile();

  const { t } = useTranslation();

  // local storage
  const { setValue: toggleFavoriteMenu, storedValue } = useLocalStorage<boolean>(IS_FAVORITE_MENU_OPEN, false);
  // derived values

  const moduleStatus = MODULE_STATUS.find((status) => status.value === moduleDetails.status);
  const isEditingAllowed = allowPermissions(
    [EUserPermissions.ADMIN, EUserPermissions.MEMBER],
    EUserPermissionsLevel.PROJECT
  );
  const isDisabled = !isEditingAllowed || !!moduleDetails?.archived_at;
  const renderIcon = Boolean(moduleDetails.start_date) || Boolean(moduleDetails.target_date);

  // handlers
  const handleAddToFavorites = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    e.preventDefault();
    if (!workspaceSlug || !projectId) return;

    const addToFavoritePromise = addModuleToFavorites(workspaceSlug.toString(), projectId.toString(), moduleId).then(
      () => {
        // open favorites menu if closed
        if (!storedValue) toggleFavoriteMenu(true);

        return undefined;
      }
    );

    setPromiseToast(addToFavoritePromise, {
      loading: t("project_ui.adding_module_to_favorites"),
      success: {
        title: t("success"),
        message: () => t("project_ui.module_added_to_favorites"),
      },
      error: {
        title: t("error"),
        message: () => t("project_ui.couldn_t_add_the_module_to_favorites_please_try_again"),
      },
    });
  };

  const handleRemoveFromFavorites = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    e.preventDefault();
    if (!workspaceSlug || !projectId) return;

    const removeFromFavoritePromise = removeModuleFromFavorites(
      workspaceSlug.toString(),
      projectId.toString(),
      moduleId
    );

    setPromiseToast(removeFromFavoritePromise, {
      loading: t("project_ui.removing_module_from_favorites"),
      success: {
        title: t("success"),
        message: () => t("project_ui.module_removed_from_favorites"),
      },
      error: {
        title: t("error"),
        message: () => t("project_ui.couldn_t_remove_the_module_from_favorites_please_try_again"),
      },
    });
  };

  const handleModuleDetailsChange = async (payload: Partial<IModule>) => {
    if (!workspaceSlug || !projectId) return;

    await updateModuleDetails(workspaceSlug.toString(), projectId.toString(), moduleId, payload)
      .then(() => {
        setToast({
          type: "success",
          title: t("success"),
          message: t("project_ui.module_updated_successfully"),
        });

        return undefined;
      })
      .catch((err) => {
        setToast({
          type: "error",
          title: t("error"),
          message: err?.detail ?? t("project_ui.module_could_not_be_updated_please_try_again"),
        });
      });
  };

  const moduleLeadDetails = moduleDetails.lead_id ? getUserDetails(moduleDetails.lead_id) : undefined;

  return (
    <>
      <DateRangeSelect
        variant="pill-sm"
        className="max-w-none"
        value={{
          from: getDate(moduleDetails.start_date) ?? null,
          to: getDate(moduleDetails.target_date) ?? null,
        }}
        onChange={(range) => {
          void handleModuleDetailsChange({
            start_date: range.from ? renderFormattedPayloadDate(range.from) : null,
            target_date: range.to ? renderFormattedPayloadDate(range.to) : null,
          });
        }}
        mergeDates
        placeholder={`${t("start_date")} - ${t("end_date")}`}
        weekStartsOn={userProfile?.start_of_the_week}
        disabled={isDisabled}
        icon={renderIcon ? undefined : <CalendarOutline aria-hidden="true" />}
      />

      {moduleStatus && (
        <ModuleStatusDropdown
          isDisabled={isDisabled}
          moduleDetails={moduleDetails}
          handleModuleDetailsChange={handleModuleDetailsChange}
        />
      )}

      {/* sized like the sm icon buttons beside it so the lead, star and menu sit on one even rhythm */}
      <span className="grid size-6 shrink-0 cursor-default place-items-center">
        {moduleLeadDetails ? (
          <ButtonAvatars showTooltip={false} userIds={moduleLeadDetails?.id} />
        ) : (
          <Tooltip label={t("workspace_projects.card.no_lead")}>
            <LeadOutline className="size-4 shrink-0 text-tertiary" />
          </Tooltip>
        )}
      </span>

      {isEditingAllowed && !moduleDetails.archived_at && (
        <FavoriteStar
          onClick={(e) => {
            if (moduleDetails.is_favorite) handleRemoveFromFavorites(e);
            else handleAddToFavorites(e);
          }}
          selected={moduleDetails.is_favorite}
        />
      )}
      {workspaceSlug && projectId && (
        <div className="hidden md:flex">
          <ModuleQuickActions
            parentRef={parentRef}
            moduleId={moduleId}
            projectId={projectId.toString()}
            workspaceSlug={workspaceSlug.toString()}
            size="sm"
          />
        </div>
      )}
    </>
  );
});
