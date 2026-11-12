/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// helpers
import { useTranslation } from "@plane/i18n";
import { EAuthModes } from "@/types/auth";

type TAuthHeader = {
  authMode: EAuthModes;
};

type TAuthHeaderContent = {
  header: string;
  subHeader: string;
};

type TAuthHeaderDetails = {
  [mode in EAuthModes]: TAuthHeaderContent;
};

export function AuthHeader(props: TAuthHeader) {
  const { t } = useTranslation();
  const { authMode } = props;
  const Titles: TAuthHeaderDetails = {
    [EAuthModes.SIGN_IN]: {
      header: t("space_ui.login_title"),
      subHeader: t("space_ui.login_subtitle"),
    },
    [EAuthModes.SIGN_UP]: {
      header: t("space_ui.signup_title"),
      subHeader: t("space_ui.signup_subtitle"),
    },
  };

  const getHeaderSubHeader = (mode: EAuthModes | null): TAuthHeaderContent => {
    if (mode) {
      return Titles[mode];
    }

    return {
      header: t("space_ui.comment_title"),
      subHeader: t("space_ui.comment_subtitle"),
    };
  };

  const { header, subHeader } = getHeaderSubHeader(authMode);

  return (
    <>
      <div className="flex flex-col gap-1">
        <span className="text-h4-semibold text-primary">{header}</span>
        <span className="text-h4-semibold text-placeholder">{subHeader}</span>
      </div>
    </>
  );
}
