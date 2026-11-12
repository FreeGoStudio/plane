/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane imports
import { useTranslation } from "@plane/i18n";
import { EmptyStateDetailed } from "@plane/blocks/empty-state";

export function SomethingWentWrongError() {
  const { t } = useTranslation();
  return (
    <div className="grid min-h-screen w-full place-items-center bg-surface-1 p-6">
      <EmptyStateDetailed
        align="center"
        assetKey="server-error"
        assetClassName="size-40"
        title={t("space_ui.generic_error")}
        description={t("space_ui.board_missing")}
      />
    </div>
  );
}
