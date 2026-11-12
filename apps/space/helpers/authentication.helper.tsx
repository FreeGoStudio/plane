/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TTranslationStore } from "@plane/i18n";
import { Link } from "react-router";
// helpers
import { SUPPORT_EMAIL } from "@plane/constants";

export enum EPageTypes {
  INIT = "INIT",
  PUBLIC = "PUBLIC",
  NON_AUTHENTICATED = "NON_AUTHENTICATED",
  ONBOARDING = "ONBOARDING",
  AUTHENTICATED = "AUTHENTICATED",
}

export enum EErrorAlertType {
  BANNER_ALERT = "BANNER_ALERT",
  TOAST_ALERT = "TOAST_ALERT",
  INLINE_FIRST_NAME = "INLINE_FIRST_NAME",
  INLINE_EMAIL = "INLINE_EMAIL",
  INLINE_PASSWORD = "INLINE_PASSWORD",
  INLINE_EMAIL_CODE = "INLINE_EMAIL_CODE",
}

export enum EAuthenticationErrorCodes {
  // Global
  INSTANCE_NOT_CONFIGURED = "5000",
  INVALID_EMAIL = "5005",
  EMAIL_REQUIRED = "5010",
  SIGNUP_DISABLED = "5015",
  // Password strength
  INVALID_PASSWORD = "5020",
  PASSWORD_TOO_WEAK = "5021",
  PASSWORD_TOO_SHORT = "5022",
  SMTP_NOT_CONFIGURED = "5025",
  // Sign Up
  USER_ALREADY_EXIST = "5030",
  AUTHENTICATION_FAILED_SIGN_UP = "5035",
  REQUIRED_EMAIL_PASSWORD_SIGN_UP = "5040",
  INVALID_EMAIL_SIGN_UP = "5045",
  INVALID_EMAIL_MAGIC_SIGN_UP = "5050",
  MAGIC_SIGN_UP_EMAIL_CODE_REQUIRED = "5055",
  // Sign In
  BOT_USER_LOGIN_FORBIDDEN = "5017",
  USER_ACCOUNT_DEACTIVATED = "5019",
  USER_DOES_NOT_EXIST = "5060",
  AUTHENTICATION_FAILED_SIGN_IN = "5065",
  REQUIRED_EMAIL_PASSWORD_SIGN_IN = "5070",
  INVALID_EMAIL_SIGN_IN = "5075",
  INVALID_EMAIL_MAGIC_SIGN_IN = "5080",
  MAGIC_SIGN_IN_EMAIL_CODE_REQUIRED = "5085",
  // Both Sign in and Sign up for magic
  INVALID_MAGIC_CODE_SIGN_IN = "5090",
  INVALID_MAGIC_CODE_SIGN_UP = "5092",
  EXPIRED_MAGIC_CODE_SIGN_IN = "5095",
  EXPIRED_MAGIC_CODE_SIGN_UP = "5097",
  EMAIL_CODE_ATTEMPT_EXHAUSTED_SIGN_IN = "5100",
  EMAIL_CODE_ATTEMPT_EXHAUSTED_SIGN_UP = "5102",
  // Oauth
  OAUTH_NOT_CONFIGURED = "5104",
  GOOGLE_NOT_CONFIGURED = "5105",
  GITHUB_NOT_CONFIGURED = "5110",
  GITLAB_NOT_CONFIGURED = "5111",
  GOOGLE_OAUTH_PROVIDER_ERROR = "5115",
  GITHUB_OAUTH_PROVIDER_ERROR = "5120",
  GITLAB_OAUTH_PROVIDER_ERROR = "5121",
  // Reset Password
  INVALID_PASSWORD_TOKEN = "5125",
  EXPIRED_PASSWORD_TOKEN = "5130",
  // Change password
  INCORRECT_OLD_PASSWORD = "5135",
  MISSING_PASSWORD = "5138",
  INVALID_NEW_PASSWORD = "5140",
  // set password
  PASSWORD_ALREADY_SET = "5145",
  // Admin
  ADMIN_ALREADY_EXIST = "5150",
  REQUIRED_ADMIN_EMAIL_PASSWORD_FIRST_NAME = "5155",
  INVALID_ADMIN_EMAIL = "5160",
  INVALID_ADMIN_PASSWORD = "5165",
  REQUIRED_ADMIN_EMAIL_PASSWORD = "5170",
  ADMIN_AUTHENTICATION_FAILED = "5175",
  ADMIN_USER_ALREADY_EXIST = "5180",
  ADMIN_USER_DOES_NOT_EXIST = "5185",
}

export type TAuthErrorInfo = {
  type: EErrorAlertType;
  code: EAuthenticationErrorCodes;
  title: string;
  message: React.ReactNode;
};

const getErrorCodeMessages = (
  t: TTranslationStore["t"]
): {
  [key in EAuthenticationErrorCodes]: { title: string; message: (email?: string) => React.ReactNode };
} => ({
  // global
  [EAuthenticationErrorCodes.INSTANCE_NOT_CONFIGURED]: {
    title: t("auth_errors.instance_not_configured"),
    message: () => t("auth_errors.instance_not_configured_message"),
  },
  [EAuthenticationErrorCodes.SIGNUP_DISABLED]: {
    title: t("auth_errors.sign_up_disabled"),
    message: () => t("auth_errors.sign_up_disabled_message"),
  },
  [EAuthenticationErrorCodes.INVALID_PASSWORD]: {
    title: t("auth_errors.invalid_password"),
    message: () => t("auth_errors.invalid_password_message"),
  },
  [EAuthenticationErrorCodes.PASSWORD_TOO_SHORT]: {
    title: "Password is too short",
    message: () => "Use at least 15 characters. A longer passphrase is recommended.",
  },
  [EAuthenticationErrorCodes.PASSWORD_TOO_WEAK]: {
    title: "Password not allowed",
    message: () => "This password is common, compromised, or matches your account. Choose a different passphrase.",
  },
  [EAuthenticationErrorCodes.SMTP_NOT_CONFIGURED]: {
    title: t("auth_errors.smtp_not_configured"),
    message: () => t("auth_errors.smtp_not_configured_message"),
  },

  // email check in both sign up and sign in
  [EAuthenticationErrorCodes.INVALID_EMAIL]: {
    title: t("auth_errors.invalid_email"),
    message: () => t("auth_errors.invalid_email_message"),
  },
  [EAuthenticationErrorCodes.EMAIL_REQUIRED]: {
    title: t("auth_errors.email_required"),
    message: () => t("auth_errors.email_required_message"),
  },

  // sign up
  [EAuthenticationErrorCodes.USER_ALREADY_EXIST]: {
    title: t("auth_errors.user_already_exists"),
    message: (email = undefined) => (
      <div>
        <Link
          className="font-medium underline underline-offset-4 transition-all hover:font-bold"
          to={`/sign-in${email ? `?email=${encodeURIComponent(email)}` : ``}`}
        >
          {t("auth_errors.account_registered")}
        </Link>
      </div>
    ),
  },
  [EAuthenticationErrorCodes.REQUIRED_EMAIL_PASSWORD_SIGN_UP]: {
    title: t("auth_errors.email_and_password_required"),
    message: () => t("auth_errors.email_and_password_required_message"),
  },
  [EAuthenticationErrorCodes.AUTHENTICATION_FAILED_SIGN_UP]: {
    title: t("auth_errors.authentication_failed"),
    message: () => t("auth_errors.authentication_failed_message"),
  },
  [EAuthenticationErrorCodes.INVALID_EMAIL_SIGN_UP]: {
    title: t("auth_errors.invalid_email"),
    message: () => t("auth_errors.invalid_email_message"),
  },
  [EAuthenticationErrorCodes.MAGIC_SIGN_UP_EMAIL_CODE_REQUIRED]: {
    title: t("auth_errors.email_and_code_required"),
    message: () => t("auth_errors.email_and_code_required_message"),
  },
  [EAuthenticationErrorCodes.INVALID_EMAIL_MAGIC_SIGN_UP]: {
    title: t("auth_errors.invalid_email"),
    message: () => t("auth_errors.invalid_email_message"),
  },

  // sign in
  [EAuthenticationErrorCodes.BOT_USER_LOGIN_FORBIDDEN]: {
    title: t("auth_errors.sign_in_not_allowed"),
    message: () => t("auth_errors.personal_account"),
  },
  [EAuthenticationErrorCodes.USER_ACCOUNT_DEACTIVATED]: {
    title: t("auth_errors.user_account_deactivated"),
    message: () => t("auth_errors.deactivated_contact", { contact: SUPPORT_EMAIL || t("admin_access.administrator") }),
  },

  [EAuthenticationErrorCodes.USER_DOES_NOT_EXIST]: {
    title: t("auth_errors.user_does_not_exist"),
    message: (email = undefined) => (
      <div>
        <Link
          className="font-medium underline underline-offset-4 transition-all hover:font-bold"
          to={`/${email ? `?email=${encodeURIComponent(email)}` : ``}`}
        >
          {t("auth_errors.account_missing")}
        </Link>
      </div>
    ),
  },
  [EAuthenticationErrorCodes.REQUIRED_EMAIL_PASSWORD_SIGN_IN]: {
    title: t("auth_errors.email_and_password_required"),
    message: () => t("auth_errors.email_and_password_required_message"),
  },
  [EAuthenticationErrorCodes.AUTHENTICATION_FAILED_SIGN_IN]: {
    title: t("auth_errors.authentication_failed"),
    message: () => t("auth_errors.authentication_failed_message"),
  },
  [EAuthenticationErrorCodes.INVALID_EMAIL_SIGN_IN]: {
    title: t("auth_errors.invalid_email"),
    message: () => t("auth_errors.invalid_email_message"),
  },
  [EAuthenticationErrorCodes.MAGIC_SIGN_IN_EMAIL_CODE_REQUIRED]: {
    title: t("auth_errors.email_and_code_required"),
    message: () => t("auth_errors.email_and_code_required_message"),
  },
  [EAuthenticationErrorCodes.INVALID_EMAIL_MAGIC_SIGN_IN]: {
    title: t("auth_errors.invalid_email"),
    message: () => t("auth_errors.invalid_email_message"),
  },

  // Both Sign in and Sign up
  [EAuthenticationErrorCodes.INVALID_MAGIC_CODE_SIGN_IN]: {
    title: t("auth_errors.authentication_failed"),
    message: () => t("auth_errors.invalid_magic_code_message"),
  },
  [EAuthenticationErrorCodes.INVALID_MAGIC_CODE_SIGN_UP]: {
    title: t("auth_errors.authentication_failed"),
    message: () => t("auth_errors.invalid_magic_code_message"),
  },
  [EAuthenticationErrorCodes.EXPIRED_MAGIC_CODE_SIGN_IN]: {
    title: t("auth_errors.expired_magic_code"),
    message: () => t("auth_errors.expired_magic_code_message"),
  },
  [EAuthenticationErrorCodes.EXPIRED_MAGIC_CODE_SIGN_UP]: {
    title: t("auth_errors.expired_magic_code"),
    message: () => t("auth_errors.expired_magic_code_message"),
  },
  [EAuthenticationErrorCodes.EMAIL_CODE_ATTEMPT_EXHAUSTED_SIGN_IN]: {
    title: t("auth_errors.expired_magic_code"),
    message: () => t("auth_errors.expired_magic_code_message"),
  },
  [EAuthenticationErrorCodes.EMAIL_CODE_ATTEMPT_EXHAUSTED_SIGN_UP]: {
    title: t("auth_errors.expired_magic_code"),
    message: () => t("auth_errors.expired_magic_code_message"),
  },

  // Oauth
  [EAuthenticationErrorCodes.OAUTH_NOT_CONFIGURED]: {
    title: t("auth_errors.oauth_not_configured"),
    message: () => t("auth_errors.oauth_not_configured_message"),
  },
  [EAuthenticationErrorCodes.GOOGLE_NOT_CONFIGURED]: {
    title: t("auth_errors.google_not_configured"),
    message: () => t("auth_errors.google_not_configured_message"),
  },
  [EAuthenticationErrorCodes.GITHUB_NOT_CONFIGURED]: {
    title: t("auth_errors.github_not_configured"),
    message: () => t("auth_errors.github_not_configured_message"),
  },
  [EAuthenticationErrorCodes.GITLAB_NOT_CONFIGURED]: {
    title: t("auth_errors.gitlab_not_configured"),
    message: () => t("auth_errors.gitlab_not_configured_message"),
  },
  [EAuthenticationErrorCodes.GOOGLE_OAUTH_PROVIDER_ERROR]: {
    title: t("auth_errors.google_oauth_provider_error"),
    message: () => t("auth_errors.google_oauth_provider_error_message"),
  },
  [EAuthenticationErrorCodes.GITHUB_OAUTH_PROVIDER_ERROR]: {
    title: t("auth_errors.github_oauth_provider_error"),
    message: () => t("auth_errors.github_oauth_provider_error_message"),
  },
  [EAuthenticationErrorCodes.GITLAB_OAUTH_PROVIDER_ERROR]: {
    title: t("auth_errors.gitlab_oauth_provider_error"),
    message: () => t("auth_errors.gitlab_oauth_provider_error_message"),
  },

  // Reset Password
  [EAuthenticationErrorCodes.INVALID_PASSWORD_TOKEN]: {
    title: t("auth_errors.invalid_password_token"),
    message: () => t("auth_errors.invalid_password_token_message"),
  },
  [EAuthenticationErrorCodes.EXPIRED_PASSWORD_TOKEN]: {
    title: t("auth_errors.expired_password_token"),
    message: () => t("auth_errors.expired_password_token_message"),
  },

  // Change password
  [EAuthenticationErrorCodes.MISSING_PASSWORD]: {
    title: t("auth_errors.password_required"),
    message: () => t("auth_errors.password_required_message"),
  },
  [EAuthenticationErrorCodes.INCORRECT_OLD_PASSWORD]: {
    title: t("auth_errors.incorrect_old_password"),
    message: () => t("auth_errors.incorrect_old_password_message"),
  },
  [EAuthenticationErrorCodes.INVALID_NEW_PASSWORD]: {
    title: t("auth_errors.invalid_new_password"),
    message: () => t("auth_errors.invalid_new_password_message"),
  },

  // set password
  [EAuthenticationErrorCodes.PASSWORD_ALREADY_SET]: {
    title: t("auth_errors.password_already_set"),
    message: () => t("auth_errors.password_already_set_message"),
  },

  // admin
  [EAuthenticationErrorCodes.ADMIN_ALREADY_EXIST]: {
    title: t("auth_errors.admin_already_exists"),
    message: () => t("auth_errors.admin_already_exists_message"),
  },
  [EAuthenticationErrorCodes.REQUIRED_ADMIN_EMAIL_PASSWORD_FIRST_NAME]: {
    title: t("auth_errors.email_password_and_first_name_required"),
    message: () => t("auth_errors.email_password_and_first_name_required_message"),
  },
  [EAuthenticationErrorCodes.INVALID_ADMIN_EMAIL]: {
    title: t("auth_errors.invalid_admin_email"),
    message: () => t("auth_errors.invalid_admin_email_message"),
  },
  [EAuthenticationErrorCodes.INVALID_ADMIN_PASSWORD]: {
    title: t("auth_errors.invalid_admin_password"),
    message: () => t("auth_errors.invalid_admin_password_message"),
  },
  [EAuthenticationErrorCodes.REQUIRED_ADMIN_EMAIL_PASSWORD]: {
    title: t("auth_errors.email_and_password_required"),
    message: () => t("auth_errors.email_and_password_required_message"),
  },
  [EAuthenticationErrorCodes.ADMIN_AUTHENTICATION_FAILED]: {
    title: t("auth_errors.authentication_failed"),
    message: () => t("auth_errors.authentication_failed_message"),
  },
  [EAuthenticationErrorCodes.ADMIN_USER_ALREADY_EXIST]: {
    title: t("auth_errors.admin_user_already_exists"),
    message: () => (
      <div>
        <Link className="font-medium underline underline-offset-4 transition-all hover:font-bold" to={`/admin`}>
          {t("auth_errors.admin_registered")}
        </Link>
      </div>
    ),
  },
  [EAuthenticationErrorCodes.ADMIN_USER_DOES_NOT_EXIST]: {
    title: t("auth_errors.admin_user_does_not_exist"),
    message: () => (
      <div>
        <Link className="font-medium underline underline-offset-4 transition-all hover:font-bold" to={`/admin`}>
          {t("auth_errors.admin_missing")}
        </Link>
      </div>
    ),
  },
});

export const authErrorHandler = (
  errorCode: EAuthenticationErrorCodes,
  t: TTranslationStore["t"],
  email?: string
): TAuthErrorInfo | undefined => {
  const errorCodeMessages = getErrorCodeMessages(t);
  const bannerAlertErrorCodes = [
    EAuthenticationErrorCodes.INSTANCE_NOT_CONFIGURED,
    EAuthenticationErrorCodes.INVALID_EMAIL,
    EAuthenticationErrorCodes.EMAIL_REQUIRED,
    EAuthenticationErrorCodes.SIGNUP_DISABLED,
    EAuthenticationErrorCodes.INVALID_PASSWORD,
    EAuthenticationErrorCodes.PASSWORD_TOO_SHORT,
    EAuthenticationErrorCodes.PASSWORD_TOO_WEAK,
    EAuthenticationErrorCodes.SMTP_NOT_CONFIGURED,
    EAuthenticationErrorCodes.USER_ALREADY_EXIST,
    EAuthenticationErrorCodes.AUTHENTICATION_FAILED_SIGN_UP,
    EAuthenticationErrorCodes.REQUIRED_EMAIL_PASSWORD_SIGN_UP,
    EAuthenticationErrorCodes.INVALID_EMAIL_SIGN_UP,
    EAuthenticationErrorCodes.INVALID_EMAIL_MAGIC_SIGN_UP,
    EAuthenticationErrorCodes.MAGIC_SIGN_UP_EMAIL_CODE_REQUIRED,
    EAuthenticationErrorCodes.USER_DOES_NOT_EXIST,
    EAuthenticationErrorCodes.AUTHENTICATION_FAILED_SIGN_IN,
    EAuthenticationErrorCodes.REQUIRED_EMAIL_PASSWORD_SIGN_IN,
    EAuthenticationErrorCodes.INVALID_EMAIL_SIGN_IN,
    EAuthenticationErrorCodes.INVALID_EMAIL_MAGIC_SIGN_IN,
    EAuthenticationErrorCodes.MAGIC_SIGN_IN_EMAIL_CODE_REQUIRED,
    EAuthenticationErrorCodes.INVALID_MAGIC_CODE_SIGN_IN,
    EAuthenticationErrorCodes.INVALID_MAGIC_CODE_SIGN_UP,
    EAuthenticationErrorCodes.EXPIRED_MAGIC_CODE_SIGN_IN,
    EAuthenticationErrorCodes.EXPIRED_MAGIC_CODE_SIGN_UP,
    EAuthenticationErrorCodes.EMAIL_CODE_ATTEMPT_EXHAUSTED_SIGN_IN,
    EAuthenticationErrorCodes.EMAIL_CODE_ATTEMPT_EXHAUSTED_SIGN_UP,
    EAuthenticationErrorCodes.OAUTH_NOT_CONFIGURED,
    EAuthenticationErrorCodes.GOOGLE_NOT_CONFIGURED,
    EAuthenticationErrorCodes.GITHUB_NOT_CONFIGURED,
    EAuthenticationErrorCodes.GITLAB_NOT_CONFIGURED,
    EAuthenticationErrorCodes.GOOGLE_OAUTH_PROVIDER_ERROR,
    EAuthenticationErrorCodes.GITHUB_OAUTH_PROVIDER_ERROR,
    EAuthenticationErrorCodes.GITLAB_OAUTH_PROVIDER_ERROR,
    EAuthenticationErrorCodes.INVALID_PASSWORD_TOKEN,
    EAuthenticationErrorCodes.EXPIRED_PASSWORD_TOKEN,
    EAuthenticationErrorCodes.INCORRECT_OLD_PASSWORD,
    EAuthenticationErrorCodes.INVALID_NEW_PASSWORD,
    EAuthenticationErrorCodes.PASSWORD_ALREADY_SET,
    EAuthenticationErrorCodes.ADMIN_ALREADY_EXIST,
    EAuthenticationErrorCodes.REQUIRED_ADMIN_EMAIL_PASSWORD_FIRST_NAME,
    EAuthenticationErrorCodes.INVALID_ADMIN_EMAIL,
    EAuthenticationErrorCodes.INVALID_ADMIN_PASSWORD,
    EAuthenticationErrorCodes.REQUIRED_ADMIN_EMAIL_PASSWORD,
    EAuthenticationErrorCodes.ADMIN_AUTHENTICATION_FAILED,
    EAuthenticationErrorCodes.ADMIN_USER_ALREADY_EXIST,
    EAuthenticationErrorCodes.ADMIN_USER_DOES_NOT_EXIST,
    EAuthenticationErrorCodes.BOT_USER_LOGIN_FORBIDDEN,
    EAuthenticationErrorCodes.USER_ACCOUNT_DEACTIVATED,
  ];

  if (bannerAlertErrorCodes.includes(errorCode))
    return {
      type: EErrorAlertType.BANNER_ALERT,
      code: errorCode,
      title: errorCodeMessages[errorCode]?.title || t("admin_access.error"),
      message: errorCodeMessages[errorCode]?.message(email) || t("admin_access.generic_error"),
    };

  return undefined;
};
