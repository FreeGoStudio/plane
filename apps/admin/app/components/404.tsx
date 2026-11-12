/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import { Link } from "react-router";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { EmptyStateDetailed } from "@plane/blocks/empty-state";

function PageNotFound() {
  const { t } = useTranslation();
  return (
    <div className="h-screen w-full overflow-hidden bg-surface-1 p-4">
      <EmptyStateDetailed
        align="center"
        assetKey="error-404"
        assetClassName="size-40"
        title={t("admin_access.not_found_title")}
        description={t("admin_access.not_found_description")}
        customButton={
          <Button
            variant="primary"
            size="lg"
            stretch="auto"
            nativeButton={false}
            render={<Link to="/general/" />}
            label={t("admin_access.general_settings")}
          />
        }
      />
    </div>
  );
}

export default PageNotFound;
