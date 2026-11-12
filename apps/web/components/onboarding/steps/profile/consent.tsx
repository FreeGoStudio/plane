/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import { Checkbox } from "@makeplane/propel/components/checkbox";

type Props = {
  isChecked: boolean;
  handleChange: (checked: boolean) => void;
};

export function MarketingConsent({ isChecked, handleChange }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex w-full justify-center">
      <Checkbox
        label={t("onboarding_ui.i_agree_to_plane_marketing_communications")}
        checked={isChecked}
        onCheckedChange={(checked) => handleChange(checked)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            handleChange(!isChecked);
          }
        }}
      />
    </div>
  );
}
