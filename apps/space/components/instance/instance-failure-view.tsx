/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import { useTheme } from "next-themes";
import { Button } from "@makeplane/propel/components/button";
// assets
import InstanceFailureDarkImage from "@/app/assets/instance/instance-failure-dark.svg?url";
import InstanceFailureImage from "@/app/assets/instance/instance-failure.svg?url";

const handleRetry = () => {
  window.location.reload();
};

export function InstanceFailureView() {
  const { t } = useTranslation();
  const { resolvedTheme } = useTheme();

  const instanceImage = resolvedTheme === "dark" ? InstanceFailureDarkImage : InstanceFailureImage;

  return (
    <div className="relative container mx-auto flex h-screen items-center justify-center overflow-x-hidden overflow-y-auto px-5">
      <div className="relative w-auto max-w-2xl space-y-8 py-10">
        <div className="relative flex flex-col items-center justify-center space-y-4">
          <img src={instanceImage} alt={t("space_ui.instance_image")} />
          <h3 className="text-h4-medium text-on-color">{t("space_ui.instance_failed")}</h3>
          <p className="text-center text-body-sm-medium">
            {t("space_ui.instance_details_failed")}
            <br />
            {t("space_ui.connectivity")}
          </p>
        </div>
        <div className="flex justify-center">
          <Button variant="primary" size="md" stretch="auto" label={t("space_ui.retry")} onClick={handleRetry} />
        </div>
      </div>
    </div>
  );
}
