/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { useTheme } from "next-themes";
import { AppearanceOutline, MoonOutline } from "@makeplane/propel/icons";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";

export const NavbarTheme = observer(function NavbarTheme() {
  const { t } = useTranslation();
  // states
  const [appTheme, setAppTheme] = useState("light");
  // theme
  const { setTheme, resolvedTheme } = useTheme();

  const handleTheme = () => {
    setTheme(appTheme === "light" ? "dark" : "light");
  };

  useEffect(() => {
    if (!resolvedTheme) return;
    setAppTheme(resolvedTheme);
  }, [resolvedTheme]);

  return (
    <IconButton
      size="md"
      variant="ghost"
      aria-label={appTheme === "light" ? t("space_ui.dark_theme") : t("space_ui.light_theme")}
      onClick={handleTheme}
      icon={<Icon icon={appTheme === "light" ? MoonOutline : AppearanceOutline} />}
    />
  );
});
