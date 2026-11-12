/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
// icons
import { HideOutline, ShowOutline } from "@makeplane/propel/icons";
// plane internal packages
import { API_BASE_URL, E_PASSWORD_STRENGTH } from "@plane/constants";
import { Button } from "@makeplane/propel/components/button";
import { Checkbox } from "@makeplane/propel/components/checkbox";
import { InputField } from "@makeplane/propel/components/input-field";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { PasswordStrengthIndicator } from "@plane/blocks/auth";
import { Banner } from "@makeplane/propel/components/banner";
import { getPasswordStrength, validatePersonName, validateCompanyName } from "@plane/utils";
// components
import { AuthHeader } from "@/app/(all)/(home)/auth-header";
import { FormHeader } from "./form-header";
// hooks
import { useCsrfToken } from "@/hooks/use-csrf-token";

// error codes
enum EErrorCodes {
  INSTANCE_NOT_CONFIGURED = "INSTANCE_NOT_CONFIGURED",
  ADMIN_ALREADY_EXIST = "ADMIN_ALREADY_EXIST",
  REQUIRED_EMAIL_PASSWORD_FIRST_NAME = "REQUIRED_EMAIL_PASSWORD_FIRST_NAME",
  INVALID_EMAIL = "INVALID_EMAIL",
  INVALID_PASSWORD = "INVALID_PASSWORD",
  USER_ALREADY_EXISTS = "USER_ALREADY_EXISTS",
}

type TError = {
  type: EErrorCodes | undefined;
  message: string | undefined;
};

// form data
type TFormData = {
  first_name: string;
  last_name: string;
  email: string;
  company_name: string;
  password: string;
  confirm_password?: string;
  is_telemetry_enabled: boolean;
};

const defaultFromData: TFormData = {
  first_name: "",
  last_name: "",
  email: "",
  company_name: "",
  password: "",
  is_telemetry_enabled: true,
};

export function InstanceSetupForm() {
  const { t } = useTranslation();
  // search params
  const searchParams = useSearchParams();
  const firstNameParam = searchParams?.get("first_name") || undefined;
  const lastNameParam = searchParams?.get("last_name") || undefined;
  const companyParam = searchParams?.get("company") || undefined;
  const emailParam = searchParams?.get("email") || undefined;
  // only set when the API redirects back after a failed setup; otherwise the default (enabled) applies
  const telemetryParam = searchParams?.get("is_telemetry_enabled");
  const isTelemetryEnabledParam = telemetryParam ? telemetryParam === "True" : undefined;
  const errorCode = searchParams?.get("error_code") || undefined;
  const errorMessage = searchParams?.get("error_message") || undefined;
  // state
  const [showPassword, setShowPassword] = useState({
    password: false,
    retypePassword: false,
  });
  const csrfToken = useCsrfToken();
  const [formData, setFormData] = useState<TFormData>(defaultFromData);
  const [isPasswordInputFocused, setIsPasswordInputFocused] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRetryPasswordInputFocused, setIsRetryPasswordInputFocused] = useState(false);

  const handleShowPassword = (key: keyof typeof showPassword) =>
    setShowPassword((prev) => ({ ...prev, [key]: !prev[key] }));

  const handleFormChange = (key: keyof TFormData, value: string | boolean) =>
    setFormData((prev) => ({ ...prev, [key]: value }));

  useEffect(() => {
    if (firstNameParam) setFormData((prev) => ({ ...prev, first_name: firstNameParam }));
    if (lastNameParam) setFormData((prev) => ({ ...prev, last_name: lastNameParam }));
    if (companyParam) setFormData((prev) => ({ ...prev, company_name: companyParam }));
    if (emailParam) setFormData((prev) => ({ ...prev, email: emailParam }));
    if (isTelemetryEnabledParam !== undefined)
      setFormData((prev) => ({ ...prev, is_telemetry_enabled: isTelemetryEnabledParam }));
  }, [firstNameParam, lastNameParam, companyParam, emailParam, isTelemetryEnabledParam]);

  // derived values
  const errorData: TError = useMemo(() => {
    if (errorCode && errorMessage) {
      switch (errorCode) {
        case EErrorCodes.INSTANCE_NOT_CONFIGURED:
          return {
            type: EErrorCodes.INSTANCE_NOT_CONFIGURED,
            message: t("admin_access.error_instance_not_configured"),
          };
        case EErrorCodes.ADMIN_ALREADY_EXIST:
          return { type: EErrorCodes.ADMIN_ALREADY_EXIST, message: t("admin_access.error_admin_already_exist") };
        case EErrorCodes.REQUIRED_EMAIL_PASSWORD_FIRST_NAME:
          return {
            type: EErrorCodes.REQUIRED_EMAIL_PASSWORD_FIRST_NAME,
            message: t("admin_access.error_required_email_password_first_name"),
          };
        case EErrorCodes.INVALID_EMAIL:
          return { type: EErrorCodes.INVALID_EMAIL, message: t("admin_access.error_invalid_email") };
        case EErrorCodes.INVALID_PASSWORD:
          return { type: EErrorCodes.INVALID_PASSWORD, message: t("admin_access.error_invalid_password") };
        case EErrorCodes.USER_ALREADY_EXISTS:
          return { type: EErrorCodes.USER_ALREADY_EXISTS, message: t("admin_access.error_user_already_exists") };
        default:
          return { type: undefined, message: undefined };
      }
    } else return { type: undefined, message: undefined };
  }, [errorCode, errorMessage, t]);

  const isButtonDisabled = useMemo(
    () =>
      isSubmitting ||
      !csrfToken ||
      !formData.first_name ||
      !formData.email ||
      !formData.password ||
      getPasswordStrength(formData.password) !== E_PASSWORD_STRENGTH.STRENGTH_VALID ||
      formData.password !== formData.confirm_password,
    [csrfToken, formData.confirm_password, formData.email, formData.first_name, formData.password, isSubmitting]
  );

  const password = formData?.password ?? "";
  const confirmPassword = formData?.confirm_password ?? "";
  const renderPasswordMatchError = !isRetryPasswordInputFocused || confirmPassword.length >= password.length;

  return (
    <>
      <AuthHeader />
      <div className="mt-10 flex w-full flex-grow flex-col items-center justify-center py-6">
        <div className="relative flex w-full max-w-[22.5rem] flex-col gap-6">
          <FormHeader heading={t("admin_access.setup_title")} subHeading={t("admin_access.setup_description")} />
          {errorData.type &&
            errorData?.message &&
            ![EErrorCodes.INVALID_EMAIL, EErrorCodes.INVALID_PASSWORD].includes(errorData.type) && (
              <Banner placement="inline" variant="danger" description={errorData?.message} />
            )}
          <form
            className="space-y-4"
            method="POST"
            action={`${API_BASE_URL}/api/instances/admins/sign-up/`}
            onSubmit={() => setIsSubmitting(true)}
            onError={() => setIsSubmitting(false)}
          >
            <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
            <input type="hidden" name="is_telemetry_enabled" value={formData.is_telemetry_enabled ? "True" : "False"} />

            <div className="flex flex-col items-center gap-4 sm:flex-row">
              <div className="w-full">
                <InputField
                  size="xl"
                  id="first_name"
                  name="first_name"
                  type="text"
                  placeholder={t("admin_access.first_name_placeholder")}
                  value={formData.first_name}
                  onChange={(e) => {
                    const validation = validatePersonName(e.target.value);
                    if (validation === true || e.target.value === "") {
                      handleFormChange("first_name", e.target.value);
                    }
                  }}
                  autoComplete="off"
                  // oxlint-disable-next-line jsx-a11y/no-autofocus -- first field of the one-time instance setup page
                  autoFocus
                  maxLength={50}
                  orientation="vertical"
                  label={t("admin_access.first_name")}
                  required
                />
              </div>
              <div className="w-full">
                <InputField
                  size="xl"
                  id="last_name"
                  name="last_name"
                  type="text"
                  placeholder={t("admin_access.last_name_placeholder")}
                  value={formData.last_name}
                  onChange={(e) => {
                    const validation = validatePersonName(e.target.value);
                    if (validation === true || e.target.value === "") {
                      handleFormChange("last_name", e.target.value);
                    }
                  }}
                  autoComplete="off"
                  maxLength={50}
                  orientation="vertical"
                  label={t("admin_access.last_name")}
                  required
                />
              </div>
            </div>

            <InputField
              size="xl"
              id="email"
              name="email"
              type="email"
              placeholder="name@company.com"
              value={formData.email}
              onChange={(e) => handleFormChange("email", e.target.value)}
              aria-invalid={errorData.type === EErrorCodes.INVALID_EMAIL}
              autoComplete="off"
              orientation="vertical"
              label={t("admin_access.email")}
              required
              error={errorData.type === EErrorCodes.INVALID_EMAIL && errorData.message ? errorData.message : undefined}
            />

            <InputField
              size="xl"
              id="company_name"
              name="company_name"
              type="text"
              placeholder={t("admin_access.company")}
              value={formData.company_name}
              onChange={(e) => {
                const validation = validateCompanyName(e.target.value, false);
                if (validation === true || e.target.value === "") {
                  handleFormChange("company_name", e.target.value);
                }
              }}
              maxLength={80}
              orientation="vertical"
              label={t("admin_access.company")}
              required
            />

            <div className="w-full space-y-1">
              <InputField
                size="xl"
                id="password"
                name="password"
                type={showPassword.password ? "text" : "password"}
                placeholder={t("admin_access.new_password")}
                value={formData.password}
                onChange={(e) => handleFormChange("password", e.target.value)}
                aria-invalid={errorData.type === EErrorCodes.INVALID_PASSWORD}
                onFocus={() => setIsPasswordInputFocused(true)}
                onBlur={() => setIsPasswordInputFocused(false)}
                autoComplete="new-password"
                orientation="vertical"
                label={t("admin_access.set_password")}
                required
                error={
                  errorData.type === EErrorCodes.INVALID_PASSWORD && errorData.message ? errorData.message : undefined
                }
                endIcon={
                  <IconButton
                    type="button"
                    variant="ghost"
                    size="sm"
                    aria-label={
                      showPassword.password ? t("admin_access.hide_password") : t("admin_access.show_password")
                    }
                    aria-pressed={showPassword.password}
                    icon={<Icon icon={showPassword.password ? HideOutline : ShowOutline} />}
                    onClick={() => handleShowPassword("password")}
                  />
                }
              />
              <PasswordStrengthIndicator password={formData.password} isFocused={isPasswordInputFocused} />
            </div>

            <div className="w-full space-y-1">
              <InputField
                size="xl"
                type={showPassword.retypePassword ? "text" : "password"}
                id="confirm_password"
                name="confirm_password"
                value={formData.confirm_password}
                onChange={(e) => handleFormChange("confirm_password", e.target.value)}
                placeholder={t("admin_access.confirm_password")}
                onFocus={() => setIsRetryPasswordInputFocused(true)}
                onBlur={() => setIsRetryPasswordInputFocused(false)}
                autoComplete="new-password"
                orientation="vertical"
                label={t("admin_access.confirm_password")}
                required
                endIcon={
                  <IconButton
                    type="button"
                    variant="ghost"
                    size="sm"
                    aria-label={
                      showPassword.retypePassword ? t("admin_access.hide_password") : t("admin_access.show_password")
                    }
                    aria-pressed={showPassword.retypePassword}
                    icon={<Icon icon={showPassword.retypePassword ? HideOutline : ShowOutline} />}
                    onClick={() => handleShowPassword("retypePassword")}
                  />
                }
              />
              {!!formData.confirm_password &&
                formData.password !== formData.confirm_password &&
                renderPasswordMatchError && (
                  <span className="text-body-xs-regular text-danger-primary">
                    {t("admin_access.password_mismatch")}
                  </span>
                )}
            </div>

            <div className="relative flex gap-2">
              <div>
                <Checkbox
                  id="is_telemetry_enabled"
                  aria-label={t("admin_access.telemetry")}
                  onCheckedChange={(checked) => handleFormChange("is_telemetry_enabled", checked)}
                  checked={formData.is_telemetry_enabled}
                />
              </div>
              <label className="cursor-pointer text-body-xs-medium text-tertiary" htmlFor="is_telemetry_enabled">
                {t("admin_access.telemetry_description")}{" "}
                <a
                  href="https://developers.plane.so/self-hosting/telemetry"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 text-body-xs-medium text-accent-primary hover:underline"
                >
                  {t("admin_access.learn_more")}
                </a>
              </label>
            </div>

            <div className="py-2">
              <Button
                type="submit"
                variant="primary"
                size="lg"
                stretch="full"
                disabled={isButtonDisabled}
                loading={isSubmitting}
                label={t("admin_access.continue")}
              />
            </div>
          </form>
        </div>
      </div>
    </>
  );
}
