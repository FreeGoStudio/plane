/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import Link from "next/link";
import { Controller, useForm } from "react-hook-form";
// plane imports
import { ROLE, EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { getUserDisplayName, useTranslation } from "@plane/i18n";
import { DeactivatedUserOutline, DeleteOutline, MoreHorizontalOutline } from "@makeplane/propel/icons";
import { Avatar } from "@makeplane/propel/components/avatar";
import { Badge } from "@makeplane/propel/components/badge";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@makeplane/propel/components/menu";
import { setToast } from "@plane/blocks/toast";
import type { IUser, IWorkspaceMember } from "@plane/types";
// plane ui
import { Select } from "@plane/blocks/select";
// helpers
import { getFileURL } from "@plane/utils";
// hooks
import { useMember } from "@/hooks/store/use-member";
import { useUser, useUserPermissions } from "@/hooks/store/user";

export interface RowData {
  member: IWorkspaceMember;
  role: EUserPermissions;
  is_active: boolean;
}

type NameProps = {
  rowData: RowData;
  workspaceSlug: string;
  isAdmin: boolean;
  currentUser: IUser | undefined;
  setRemoveMemberModal: (rowData: RowData) => void;
};

type TRoleOption = { key: EUserPermissions; label: string };

const ROLE_OPTIONS: TRoleOption[] = Object.entries(ROLE).map(([key, label]) => ({
  key: Number(key) as EUserPermissions,
  label,
}));

type AccountTypeProps = {
  rowData: RowData;
  workspaceSlug: string;
};

export function NameColumn(props: NameProps) {
  const { rowData, workspaceSlug, isAdmin, currentUser, setRemoveMemberModal } = props;
  // plane hooks
  const { t } = useTranslation();
  // derived values
  const { avatar_url, id } = rowData.member;
  const isSuspended = rowData.is_active === false;

  return (
    <div className="group relative">
      <div className="flex w-72 items-center justify-between gap-x-4 gap-y-2">
        <div className="flex min-w-0 flex-1 items-center gap-x-2 gap-y-2 overflow-hidden">
          {isSuspended ? (
            <span className="flex shrink-0 rounded-full bg-layer-1">
              <DeactivatedUserOutline className="size-6 text-placeholder" />
            </span>
          ) : (
            <Link href={`/${workspaceSlug}/profile/${id}`} className="flex shrink-0">
              <Avatar size="sm" src={getFileURL(avatar_url ?? "")} alt={getUserDisplayName(rowData.member)} />
            </Link>
          )}
          <span className="truncate">{getUserDisplayName(rowData.member)}</span>
        </div>

        {!isSuspended && (isAdmin || id === currentUser?.id) && (
          <div className="opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100 has-[[data-popup-open]]:opacity-100">
            <Menu>
              <MenuTrigger
                render={
                  <IconButton
                    variant="ghost"
                    size="sm"
                    aria-label={t("aria_labels.common.more_actions")}
                    icon={<Icon icon={MoreHorizontalOutline} />}
                  />
                }
              />
              <MenuContent side="bottom" align="end">
                <MenuItem
                  icon={<Icon icon={DeleteOutline} />}
                  label={id === currentUser?.id ? t("leave") : t("remove")}
                  onClick={() => setRemoveMemberModal(rowData)}
                />
              </MenuContent>
            </Menu>
          </div>
        )}
      </div>
    </div>
  );
}

export const AccountTypeColumn = observer(function AccountTypeColumn(props: AccountTypeProps) {
  const { t } = useTranslation();
  const { rowData, workspaceSlug } = props;
  // form info
  const { control } = useForm();
  // store hooks
  const { allowPermissions } = useUserPermissions();

  const {
    workspace: { updateMember },
  } = useMember();
  const { data: currentUser } = useUser();

  // derived values
  const isCurrentUser = currentUser?.id === rowData.member.id;
  const isAdminRole = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);
  const isRoleNonEditable = isCurrentUser || !isAdminRole;
  const isSuspended = rowData.is_active === false;

  return (
    <>
      {isSuspended ? (
        <div className="flex w-32">
          <Badge variant="neutral" size="sm" label={t("workspace_ui.suspended")} />
        </div>
      ) : isRoleNonEditable ? (
        <div className="flex w-32">
          <span>{t(`role_details.${ROLE[rowData.role].toLowerCase()}.title`)}</span>
        </div>
      ) : (
        <Controller
          name="role"
          control={control}
          rules={{ required: t("onboarding_ui.this_field_is_required") }}
          render={() => (
            <div className="w-32">
              <Select<TRoleOption>
                value={ROLE_OPTIONS.find((role) => role.key === rowData.role) ?? null}
                onChange={(val) => {
                  if (!workspaceSlug) return;
                  updateMember(workspaceSlug.toString(), rowData.member.id, {
                    role: Number(val) as EUserPermissions,
                  }).catch((err: unknown) => {
                    const error = err as { error?: string | string[] };
                    const errorString = Array.isArray(error?.error) ? error.error[0] : error?.error;

                    setToast({
                      type: "error",
                      title: t("error"),
                      message:
                        errorString ?? t("workspace_ui.an_error_occurred_while_updating_member_role_please_try_again"),
                    });
                  });
                }}
                getValues={() => ROLE_OPTIONS}
                getOptionValue={(role) => String(role.key)}
                getOptionLabel={(role) => t(`role_details.${role.label.toLowerCase()}.title`)}
                showSearch={false}
                pinSelected={false}
              >
                <Select.Trigger<TRoleOption> variant="select-ghost-md">
                  <span className="min-w-0 flex-1 truncate text-left">
                    {t(`role_details.${ROLE[rowData.role].toLowerCase()}.title`)}
                  </span>
                </Select.Trigger>
              </Select>
            </div>
          )}
        />
      )}
    </>
  );
});
