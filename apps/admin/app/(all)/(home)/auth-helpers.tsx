/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TTranslationStore } from "@plane/i18n";
import Link from "next/link";
// plane packages
import type { TAdminAuthErrorInfo } from "@plane/constants";
import { SUPPORT_EMAIL, EAdminAuthErrorCodes } from "@plane/constants";

export enum EErrorAlertType {
  BANNER_ALERT = "BANNER_ALERT",
  INLINE_FIRST_NAME = "INLINE_FIRST_NAME",
  INLINE_EMAIL = "INLINE_EMAIL",
  INLINE_PASSWORD = "INLINE_PASSWORD",
  INLINE_EMAIL_CODE = "INLINE_EMAIL_CODE",
}

export const authErrorHandler = (
  errorCode: EAdminAuthErrorCodes,
  t: TTranslationStore["t"]
): TAdminAuthErrorInfo | undefined => {
  const errorCodeMessages: Record<EAdminAuthErrorCodes, { title: string; message: React.ReactNode }> = {
    [EAdminAuthErrorCodes.ADMIN_ALREADY_EXIST]: {
      title: t("admin_access.admin_exists"),
      message: t("admin_access.error_admin_already_exist"),
    },
    [EAdminAuthErrorCodes.REQUIRED_ADMIN_EMAIL_PASSWORD_FIRST_NAME]: {
      title: t("admin_access.required_fields"),
      message: t("admin_access.error_required_email_password_first_name"),
    },
    [EAdminAuthErrorCodes.INVALID_ADMIN_EMAIL]: {
      title: t("admin_access.invalid_email"),
      message: t("admin_access.error_invalid_email"),
    },
    [EAdminAuthErrorCodes.INVALID_ADMIN_PASSWORD]: {
      title: t("admin_access.invalid_password"),
      message: t("admin_access.error_invalid_password"),
    },
    [EAdminAuthErrorCodes.REQUIRED_ADMIN_EMAIL_PASSWORD]: {
      title: t("admin_access.required_fields"),
      message: t("admin_access.error_required_email_password"),
    },
    [EAdminAuthErrorCodes.ADMIN_AUTHENTICATION_FAILED]: {
      title: t("admin_access.auth_failed"),
      message: t("admin_access.error_authentication_failed"),
    },
    [EAdminAuthErrorCodes.ADMIN_USER_ALREADY_EXIST]: {
      title: t("admin_access.admin_exists"),
      message: (
        <Link className="font-medium underline underline-offset-4 transition-all hover:font-bold" href="/admin">
          {t("admin_access.admin_exists_sign_in")}
        </Link>
      ),
    },
    [EAdminAuthErrorCodes.ADMIN_USER_DOES_NOT_EXIST]: {
      title: t("admin_access.admin_missing"),
      message: (
        <Link className="font-medium underline underline-offset-4 transition-all hover:font-bold" href="/admin">
          {t("admin_access.admin_missing_sign_in")}
        </Link>
      ),
    },
    [EAdminAuthErrorCodes.ADMIN_USER_DEACTIVATED]: {
      title: t("admin_access.deactivated"),
      message: t("admin_access.deactivated_help", { contact: SUPPORT_EMAIL || t("admin_access.administrator") }),
    },
  };
  const bannerAlertErrorCodes = [
    EAdminAuthErrorCodes.ADMIN_ALREADY_EXIST,
    EAdminAuthErrorCodes.REQUIRED_ADMIN_EMAIL_PASSWORD_FIRST_NAME,
    EAdminAuthErrorCodes.INVALID_ADMIN_EMAIL,
    EAdminAuthErrorCodes.INVALID_ADMIN_PASSWORD,
    EAdminAuthErrorCodes.REQUIRED_ADMIN_EMAIL_PASSWORD,
    EAdminAuthErrorCodes.ADMIN_AUTHENTICATION_FAILED,
    EAdminAuthErrorCodes.ADMIN_USER_ALREADY_EXIST,
    EAdminAuthErrorCodes.ADMIN_USER_DOES_NOT_EXIST,
    EAdminAuthErrorCodes.ADMIN_USER_DEACTIVATED,
  ];

  if (bannerAlertErrorCodes.includes(errorCode))
    return {
      type: EErrorAlertType.BANNER_ALERT,
      code: errorCode,
      title: errorCodeMessages[errorCode]?.title || t("admin_access.error"),
      message: errorCodeMessages[errorCode]?.message || t("admin_access.generic_error"),
    };

  return undefined;
};
