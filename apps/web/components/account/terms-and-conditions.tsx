/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React from "react";
import { observer } from "mobx-react";
import { useTranslation } from "@plane/i18n";
import Link from "next/link";
import { EAuthModes } from "@plane/constants";

interface TermsAndConditionsProps {
  authType?: EAuthModes;
}

// Constants for better maintainability
const LEGAL_LINKS = {
  termsOfService: "https://plane.so/legals/terms-and-conditions",
  privacyPolicy: "https://plane.so/legals/privacy-policy",
} as const;

const MESSAGES = {
  [EAuthModes.SIGN_UP]: "space_ui.signup_terms",
  [EAuthModes.SIGN_IN]: "space_ui.signin_terms",
} as const;

// Reusable link component to reduce duplication
function LegalLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link href={href} className="text-secondary" target="_blank" rel="noopener noreferrer">
      <span className="text-body-xs-medium underline hover:cursor-pointer">{children}</span>
    </Link>
  );
}

export const TermsAndConditions = observer(function TermsAndConditions({
  authType = EAuthModes.SIGN_IN,
}: TermsAndConditionsProps) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center justify-center">
      <p className="text-center text-body-xs-regular whitespace-pre-line text-tertiary">
        {t(MESSAGES[authType])} <LegalLink href={LEGAL_LINKS.termsOfService}>{t("space_ui.terms")}</LegalLink>
        {" · "}
        <LegalLink href={LEGAL_LINKS.privacyPolicy}>{t("space_ui.privacy")}</LegalLink>
      </p>
    </div>
  );
});
