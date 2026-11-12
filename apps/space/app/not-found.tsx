/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane imports
import { useTranslation } from "@plane/i18n";
import { EmptyStateDetailed } from "@plane/blocks/empty-state";

function NotFound() {
  const { t } = useTranslation();
  return (
    <div className="h-screen w-screen bg-surface-1 p-4">
      <EmptyStateDetailed
        align="center"
        assetKey="error-404"
        assetClassName="size-40"
        title={t("space_ui.not_found")}
        description={t("space_ui.check_url")}
      />
    </div>
  );
}

export default NotFound;
