/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import { observer } from "mobx-react";
import { useTheme } from "next-themes";
import { Button } from "@makeplane/propel/components/button";
// assets
import { AuthHeader } from "@/app/(all)/(home)/auth-header";
import InstanceFailureDarkImage from "@/app/assets/instance/instance-failure-dark.svg?url";
import InstanceFailureImage from "@/app/assets/instance/instance-failure.svg?url";

const handleRetry = () => {
  window.location.reload();
};

export const InstanceFailureView = observer(function InstanceFailureView() {
  const { t } = useTranslation();
  const { resolvedTheme } = useTheme();

  const instanceImage = resolvedTheme === "dark" ? InstanceFailureDarkImage : InstanceFailureImage;

  return (
    <>
      <AuthHeader />
      <div className="mt-10 flex w-full flex-grow flex-col items-center justify-center py-6">
        <div className="relative flex w-full max-w-[22.5rem] flex-col gap-6">
          <div className="relative flex flex-col items-center justify-center space-y-4">
            <img src={instanceImage} alt={t("admin_access.failure_image")} />
            <h3 className="text-center text-h4-medium text-on-color">{t("admin_access.failure_title")}</h3>
            <p className="text-center text-body-sm-medium">{t("admin_access.failure_description")}</p>
          </div>
          <div className="flex justify-center">
            <Button variant="primary" size="md" stretch="auto" onClick={handleRetry} label={t("admin_access.retry")} />
          </div>
        </div>
      </div>
    </>
  );
});
