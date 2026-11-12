/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import { useState } from "react";
// ui
import { ConfirmDialog } from "@plane/blocks/dialog";
import { setToast } from "@plane/blocks/toast";
// hooks
import { useModule } from "@/hooks/store/use-module";
import { useAppRouter } from "@/hooks/use-app-router";

type Props = {
  workspaceSlug: string;
  projectId: string;
  moduleId: string;
  handleClose: () => void;
  isOpen: boolean;
  onSubmit?: () => Promise<void>;
};

export function ArchiveModuleModal(props: Props) {
  const { t } = useTranslation();
  const { workspaceSlug, projectId, moduleId, isOpen, handleClose } = props;
  // router
  const router = useAppRouter();
  // states
  const [isArchiving, setIsArchiving] = useState(false);
  // store hooks
  const { getModuleNameById, archiveModule } = useModule();

  const moduleName = getModuleNameById(moduleId);

  const onClose = () => {
    setIsArchiving(false);
    handleClose();
  };

  const handleArchiveModule = async () => {
    setIsArchiving(true);
    try {
      await archiveModule(workspaceSlug, projectId, moduleId);
      setToast({
        type: "success",
        title: t("issue.archive.success.label"),
        message: t("issue.archive.success.message"),
      });
      onClose();
      router.push(`/${workspaceSlug}/projects/${projectId}/modules`);
    } catch {
      setToast({
        type: "error",
        title: t("error"),
        message: t("project_ui.module_could_not_be_archived_please_try_again"),
      });
    } finally {
      setIsArchiving(false);
    }
  };

  return (
    <ConfirmDialog
      isOpen={isOpen}
      handleClose={onClose}
      handleSubmit={handleArchiveModule}
      isSubmitting={isArchiving}
      variant="primary"
      title={t("project_ui.archive_module_title", { name: moduleName })}
      content={t("project_ui.are_you_sure_you_want_to_archive_the_module_all_your_archives_can_be_restored_later")}
      primaryButtonText={{ loading: t("project_ui.archiving"), default: t("project_ui.archive") }}
      secondaryButtonText={t("project_ui.cancel")}
    />
  );
}
