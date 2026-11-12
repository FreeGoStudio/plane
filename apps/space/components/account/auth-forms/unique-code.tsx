/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import React, { useEffect, useState } from "react";
import { CloseCircleOutline, TickCircleOutline } from "@makeplane/propel/icons";
// plane imports
import { API_BASE_URL } from "@plane/constants";
import { Button } from "@makeplane/propel/components/button";
import { AuthService } from "@plane/services";
import { Input } from "@makeplane/propel/components/input";
// hooks
import useTimer from "@/hooks/use-timer";
// types
import { EAuthModes } from "@/types/auth";

// services
const authService = new AuthService();

type TAuthUniqueCodeForm = {
  mode: EAuthModes;
  email: string;
  nextPath: string | undefined;
  handleEmailClear: () => void;
  generateEmailUniqueCode: (email: string) => Promise<{ code: string } | undefined>;
};

type TUniqueCodeFormValues = {
  email: string;
  code: string;
};

const defaultValues: TUniqueCodeFormValues = {
  email: "",
  code: "",
};

export function AuthUniqueCodeForm(props: TAuthUniqueCodeForm) {
  const { t } = useTranslation();
  const { mode, email, nextPath, handleEmailClear, generateEmailUniqueCode } = props;
  // derived values
  const defaultResetTimerValue = 5;
  // states
  const [uniqueCodeFormData, setUniqueCodeFormData] = useState<TUniqueCodeFormValues>({ ...defaultValues, email });
  const [isRequestingNewCode, setIsRequestingNewCode] = useState(false);
  const [csrfToken, setCsrfToken] = useState<string | undefined>(undefined);
  const [isSubmitting, setIsSubmitting] = useState(false);
  // timer
  const { timer: resendTimerCode, setTimer: setResendCodeTimer } = useTimer(0);

  const handleFormChange = (key: keyof TUniqueCodeFormValues, value: string) =>
    setUniqueCodeFormData((prev) => ({ ...prev, [key]: value }));

  const generateNewCode = async (recipientEmail: string) => {
    try {
      setIsRequestingNewCode(true);
      const uniqueCode = await generateEmailUniqueCode(recipientEmail);
      setResendCodeTimer(defaultResetTimerValue);
      handleFormChange("code", uniqueCode?.code || "");
      setIsRequestingNewCode(false);
    } catch {
      setResendCodeTimer(0);
      console.error("Error while requesting new code");
      setIsRequestingNewCode(false);
    }
  };

  useEffect(() => {
    if (csrfToken === undefined)
      authService.requestCSRFToken().then((data) => data?.csrf_token && setCsrfToken(data.csrf_token));
  }, [csrfToken]);

  const isRequestNewCodeDisabled = isRequestingNewCode || resendTimerCode > 0;
  const isButtonDisabled = isRequestingNewCode || !uniqueCodeFormData.code || isSubmitting;

  return (
    <form
      className="mt-5 space-y-4"
      method="POST"
      action={`${API_BASE_URL}/auth/spaces/${mode === EAuthModes.SIGN_IN ? "magic-sign-in" : "magic-sign-up"}/`}
      onSubmit={() => setIsSubmitting(true)}
      onError={() => setIsSubmitting(false)}
    >
      <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
      <input type="hidden" value={uniqueCodeFormData.email} name="email" />
      <input type="hidden" value={nextPath} name="next_path" />
      <div className="space-y-1">
        <label className="text-body-xs-medium text-tertiary" htmlFor="email">
          {t("space_ui.email")}
        </label>
        <div className="relative flex h-10 items-center rounded-md border border-subtle bg-surface-1 px-3 [&_input]:disable-autofill-style">
          <Input
            id="email"
            name="email"
            type="email"
            size="xl"
            value={uniqueCodeFormData.email}
            onChange={(e) => handleFormChange("email", e.target.value)}
            placeholder="name@company.com"
            autoComplete="off"
            disabled
          />
          {uniqueCodeFormData.email.length > 0 && (
            <button
              type="button"
              aria-label={t("space_ui.clear_email")}
              className="absolute right-3 hover:cursor-pointer"
              onClick={handleEmailClear}
              tabIndex={-1}
            >
              <CloseCircleOutline className="h-5 w-5 text-placeholder" />
            </button>
          )}
        </div>
      </div>

      <div className="space-y-1">
        <label className="text-body-xs-medium text-tertiary" htmlFor="code">
          {t("space_ui.code")}
        </label>
        <div className="relative flex h-10 items-center rounded-md border border-subtle bg-surface-1 pr-12 pl-3 [&_input]:disable-autofill-style">
          <Input
            id="code"
            name="code"
            size="xl"
            value={uniqueCodeFormData.code}
            onChange={(e) => handleFormChange("code", e.target.value)}
            placeholder="123456"
            autoComplete="off"
            // oxlint-disable-next-line jsx-a11y/no-autofocus -- sole primary field of a dedicated auth step; matches standard sign-in flows
            autoFocus
          />
        </div>
        <div className="flex w-full items-center justify-between px-1 pt-1 text-caption-sm-regular">
          <p className="flex items-center gap-1 font-medium text-success-primary">
            <TickCircleOutline height={12} width={12} />
            {t("space_ui.paste_code")}
          </p>
          <button
            type="button"
            onClick={() => generateNewCode(uniqueCodeFormData.email)}
            className={`${
              isRequestNewCodeDisabled
                ? "text-placeholder"
                : "font-medium text-accent-secondary hover:text-accent-secondary"
            }`}
            disabled={isRequestNewCodeDisabled}
          >
            {resendTimerCode > 0
              ? t("space_ui.resend_seconds", { seconds: resendTimerCode })
              : isRequestingNewCode
                ? t("space_ui.request_code")
                : t("space_ui.resend")}
          </button>
        </div>
      </div>

      <div className="space-y-2.5">
        <Button
          type="submit"
          variant="primary"
          size="lg"
          stretch="full"
          disabled={isButtonDisabled}
          loading={isSubmitting && !isRequestingNewCode}
          label={isRequestingNewCode ? t("space_ui.sending_code") : t("space_ui.continue")}
        />
      </div>
    </form>
  );
}
