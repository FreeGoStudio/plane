/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";

type Props = {
  isSignUp?: boolean;
};

export function TermsAndConditions(props: Props) {
  const { t } = useTranslation();
  const { isSignUp = false } = props;
  return (
    <span className="flex items-center justify-center py-6">
      <p className="text-center text-body-xs-regular whitespace-pre-line text-secondary">
        {isSignUp ? t("space_ui.signup_terms") : t("space_ui.signin_terms")}{" "}
        <a href="https://plane.so/legals/terms-and-conditions" target="_blank" rel="noopener noreferrer">
          <span className="text-body-xs-medium underline hover:cursor-pointer">{t("space_ui.terms")}</span>
        </a>{" "}
        {" · "}
        <a href="https://plane.so/legals/privacy-policy" target="_blank" rel="noopener noreferrer">
          <span className="text-body-xs-medium underline hover:cursor-pointer">{t("space_ui.privacy")}</span>
        </a>
      </p>
    </span>
  );
}
