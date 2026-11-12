/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import { DownloadOutline } from "@makeplane/propel/icons";
// plane imports
import { Icon } from "@makeplane/propel/components/icon";
import { ToolbarButton } from "@makeplane/propel/elements/toolbar";
import { Tooltip } from "@makeplane/propel/components/tooltip";

type Props = {
  src: string;
};

export function ImageDownloadAction(props: Props) {
  const { t } = useTranslation();
  const { src } = props;

  return (
    <Tooltip label={t("editor_ui.download")}>
      <ToolbarButton
        type="button"
        size="sm"
        labeled={false}
        onClick={() => window.open(src, "_blank")}
        aria-label={t("editor_ui.download_image")}
      >
        <Icon icon={DownloadOutline} />
      </ToolbarButton>
    </Tooltip>
  );
}
