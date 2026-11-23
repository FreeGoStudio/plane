/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";

import { observer } from "mobx-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
// plane imports
import { AnchorButton } from "@makeplane/propel/components/anchor-button";
import { Button } from "@makeplane/propel/components/button";
import { EmptyStateDetailed } from "@plane/blocks/empty-state";
// components
import { LogoSpinner } from "@/components/common/logo-spinner";
// constants
import { WORKSPACE_INVITATION } from "@plane/constants";
// helpers
import { EPageTypes } from "@/helpers/authentication.helper";
// hooks
import { useUser } from "@/hooks/store/user";
import { useAppRouter } from "@/hooks/use-app-router";
// wrappers
import { AuthenticationWrapper } from "@/lib/wrappers/authentication-wrapper";
import { WorkspaceService } from "@/services/workspace.service";
// services

// service initialization
const workspaceService = new WorkspaceService();

function WorkspaceInvitationPage() {
  const { t } = useTranslation();

  // router
  const router = useAppRouter();
  // query params
  const searchParams = useSearchParams();
  const invitation_id = searchParams.get("invitation_id");
  const slug = searchParams.get("slug");
  const token = searchParams.get("token");
  const hasInvitationParams = !!(invitation_id && slug && token);
  // store hooks
  const { data: currentUser } = useUser();

  const { data: invitationDetail, error } = useSWR(
    hasInvitationParams && WORKSPACE_INVITATION(invitation_id!),
    hasInvitationParams ? () => workspaceService.getWorkspaceInvitation(slug!, invitation_id!) : null
  );

  const handleAccept = () => {
    if (!invitationDetail) return;
    workspaceService
      .joinWorkspace(invitationDetail.workspace.slug, invitationDetail.id, {
        accepted: true,
        token: token,
      })
      .then(() => {
        if (invitationDetail.email === currentUser?.email) {
          router.push(`/${invitationDetail.workspace.slug}`);
        } else {
          router.push("/");
        }
        return undefined;
      })
      .catch((err: unknown) => console.error(err));
  };

  const handleReject = () => {
    if (!invitationDetail || !token) return;
    void workspaceService
      .joinWorkspace(invitationDetail.workspace.slug, invitationDetail.id, {
        accepted: false,
        token: token,
      })
      .then(() => {
        router.push("/");
        return undefined;
      })
      .catch((err: unknown) => console.error(err));
  };

  return (
    <AuthenticationWrapper pageType={EPageTypes.PUBLIC}>
      <div className="flex h-full w-full flex-col items-center justify-center px-3">
        {!hasInvitationParams ? (
          <EmptyStateDetailed
            align="center"
            assetKey="invalid-link"
            title="This invitation link is incomplete."
            description="Open the complete invitation link shared with you, or ask your workspace admin for a new link."
            customButton={
              <Button
                variant="primary"
                size="lg"
                stretch="auto"
                label="Continue to home"
                nativeButton={false}
                render={<Link href="/" />}
              />
            }
          />
        ) : invitationDetail && !invitationDetail.responded_at ? (
          error ? (
            <EmptyStateDetailed
              align="center"
              assetKey="invalid-link"
              assetClassName="size-40"
              title="INVITATION NOT FOUND"
            />
          ) : (
            <EmptyStateDetailed
              align="center"
              assetKey="inbox"
              title={t("web_ui.dynamic_you_have_been_invited_to_value0", { value0: invitationDetail.workspace.name })}
              description={t(
                "web_ui.your_workspace_is_where_you_ll_create_projects_collaborate_on_your_work_items_and_organize"
              )}
              actions={[
                { label: "Accept", variant: "primary", onClick: handleAccept },
                { label: "Ignore", variant: "secondary", onClick: handleReject },
              ]}
            />
          )
        ) : error || invitationDetail?.responded_at ? (
          invitationDetail?.accepted ? (
            <EmptyStateDetailed
              align="center"
              assetKey="project"
              title={t("web_ui.dynamic_you_are_already_a_member_of_value0", {
                value0: invitationDetail.workspace.name,
              })}
              description={t(
                "web_ui.your_workspace_is_where_you_ll_create_projects_collaborate_on_your_work_items_and_organize"
              )}
              customButton={
                <Button
                  variant="primary"
                  size="lg"
                  stretch="auto"
                  label="Continue to home"
                  nativeButton={false}
                  render={<Link href="/" />}
                />
              }
            />
          ) : (
            <EmptyStateDetailed
              align="center"
              assetKey="invalid-link"
              title={t("web_ui.this_invitation_link_is_not_active_anymore")}
              description={t(
                "web_ui.your_workspace_is_where_you_ll_create_projects_collaborate_on_your_work_items_and_organize"
              )}
              customButton={
                <div className="flex flex-col items-center gap-4">
                  <Button
                    variant="primary"
                    size="lg"
                    stretch="auto"
                    label={!currentUser ? "Sign in to continue" : "Continue to home"}
                    nativeButton={false}
                    render={<Link href="/" />}
                  />
                  <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2">
                    <AnchorButton
                      variant="secondary"
                      size="md"
                      href="https://forum.plane.so"
                      external
                      label="Join our community of active creators"
                    />
                    <AnchorButton
                      variant="secondary"
                      size="md"
                      render={<Link href="/" />}
                      label="Or start from an empty project"
                    />
                  </div>
                </div>
              }
            />
          )
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <LogoSpinner />
          </div>
        )}
      </div>
    </AuthenticationWrapper>
  );
}

export default observer(WorkspaceInvitationPage);
