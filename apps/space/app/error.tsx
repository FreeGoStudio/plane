/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// ui
import { useTranslation } from "@plane/i18n";
import { Button } from "@makeplane/propel/components/button";

const handleRetry = () => {
  window.location.reload();
};

function ErrorPage() {
  const { t } = useTranslation();

  return (
    <div className="grid h-screen place-items-center bg-surface-1 p-4">
      <div className="space-y-8 text-center">
        <div className="space-y-2">
          <h3 className="text-h6-semibold">{t("space_ui.crash_title")}</h3>
          <p className="mx-auto text-body-xs-regular text-secondary md:w-1/2">
            {t("space_ui.crash_help")}{" "}
            <a href="mailto:support@plane.so" className="text-accent-primary">
              support@plane.so
            </a>
            {" · "}
            <a href="https://forum.plane.so" target="_blank" className="text-accent-primary" rel="noopener noreferrer">
              {t("space_ui.forum")}
            </a>
          </p>
        </div>
        <div className="flex items-center justify-center gap-2">
          <Button variant="primary" size="md" stretch="auto" label={t("space_ui.refresh")} onClick={handleRetry} />
          {/* <Button variant="secondary" size="lg" onClick={() => {}}>
            Sign out
          </Button> */}
        </div>
      </div>
    </div>
  );
}

export default ErrorPage;
