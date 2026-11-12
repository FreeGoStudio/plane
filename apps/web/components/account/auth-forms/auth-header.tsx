/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import useSWR from "swr";
import { WorkspaceAvatar } from "@makeplane/propel/components/workspace-avatar";
import { useTranslation } from "@plane/i18n";
import type { IWorkspaceMemberInvitation } from "@plane/types";
import { getFileURL } from "@plane/utils";
// components
import { LogoSpinner } from "@/components/common/logo-spinner";
// helpers
import { EAuthModes, EAuthSteps } from "@/helpers/authentication.helper";
// services
import { WorkspaceService } from "@/services/workspace.service";

type TAuthHeader = {
  workspaceSlug: string | undefined;
  invitationId: string | undefined;
  invitationEmail: string | undefined;
  authMode: EAuthModes;
  currentAuthStep: EAuthSteps;
};

const Titles = {
  [EAuthModes.SIGN_IN]: {
    [EAuthSteps.EMAIL]: {
      header: "auth.common.tagline",
      subHeader: "auth.common.welcome_back",
    },
    [EAuthSteps.PASSWORD]: {
      header: "auth.common.tagline",
      subHeader: "auth.common.welcome_back",
    },
    [EAuthSteps.UNIQUE_CODE]: {
      header: "auth.common.tagline",
      subHeader: "auth.common.welcome_back",
    },
  },
  [EAuthModes.SIGN_UP]: {
    [EAuthSteps.EMAIL]: {
      header: "auth.common.tagline",
      subHeader: "auth.common.create_account_heading",
    },
    [EAuthSteps.PASSWORD]: {
      header: "auth.common.tagline",
      subHeader: "auth.common.create_account_heading",
    },
    [EAuthSteps.UNIQUE_CODE]: {
      header: "auth.common.tagline",
      subHeader: "auth.common.create_account_heading",
    },
  },
};

const workSpaceService = new WorkspaceService();

export const AuthHeader = observer(function AuthHeader(props: TAuthHeader) {
  const { workspaceSlug, invitationId, invitationEmail, authMode, currentAuthStep } = props;
  // plane imports
  const { t } = useTranslation();

  const { data: invitation, isLoading } = useSWR(
    workspaceSlug && invitationId ? `WORKSPACE_INVITATION_${workspaceSlug}_${invitationId}` : null,
    async () => workspaceSlug && invitationId && workSpaceService.getWorkspaceInvitation(workspaceSlug, invitationId),
    {
      revalidateOnFocus: false,
      shouldRetryOnError: false,
    }
  );

  const getHeaderSubHeader = (
    step: EAuthSteps,
    mode: EAuthModes,
    workspaceInvitation: IWorkspaceMemberInvitation | undefined,
    email: string | undefined
  ) => {
    if (workspaceInvitation && email && workspaceInvitation.email === email && workspaceInvitation.workspace) {
      const workspace = workspaceInvitation.workspace;
      return {
        header: (
          <div className="relative inline-flex items-center gap-2">
            {t("common.join")}{" "}
            <WorkspaceAvatar size="xl" src={getFileURL(workspace?.logo_url ?? "")} alt={workspace?.name} aria-hidden />{" "}
            {workspace.name}
          </div>
        ),
        subHeader: mode == EAuthModes.SIGN_UP ? t("auth.sign_up.header.label") : t("auth.sign_in.header.label"),
      };
    }

    return { header: t(Titles[mode][step].header), subHeader: t(Titles[mode][step].subHeader) };
  };

  const { header, subHeader } = getHeaderSubHeader(currentAuthStep, authMode, invitation || undefined, invitationEmail);

  if (isLoading)
    return (
      <div className="flex h-full w-full items-center justify-center">
        <LogoSpinner />
      </div>
    );

  return <AuthHeaderBase subHeader={subHeader} header={header} />;
});

type TAuthHeaderBase = {
  header: React.ReactNode;
  subHeader: string;
};

export function AuthHeaderBase(props: TAuthHeaderBase) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-h4-semibold text-primary">{props.header}</span>
      <span className="text-h4-semibold text-placeholder">{props.subHeader}</span>
    </div>
  );
}
