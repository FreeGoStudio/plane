/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import { useCallback, useEffect, useRef, useState } from "react";
import { observer } from "mobx-react";
import { useTheme } from "next-themes";
import useSWR from "swr";
// plane internal packages
import { Switch } from "@makeplane/propel/components/switch";
import type { TInstanceConfigurationKeys, TInstanceAuthenticationModes } from "@plane/types";
import { cn, resolveGeneralTheme } from "@plane/utils";
// components
import { PageWrapper } from "@/components/common/page-wrapper";
import { AuthenticationMethodCard } from "@/components/authentication/authentication-method-card";
import { Skeleton } from "@plane/blocks/skeleton";
import { setPromiseToast, setToast } from "@plane/blocks/toast";
// helpers
import { canDisableAuthMethod } from "@/helpers/authentication";
// hooks
import { useAuthenticationModes } from "@/hooks/oauth";
import { useInstance } from "@/hooks/store";
// types
import type { Route } from "./+types/page";

const InstanceAuthenticationPage = observer(function InstanceAuthenticationPage(_props: Route.ComponentProps) {
  // theme
  const { resolvedTheme: resolvedThemeAdmin } = useTheme();
  const resolvedTheme = resolveGeneralTheme(resolvedThemeAdmin);
  // Ref to store authentication modes for validation (avoids circular dependency)
  const authenticationModesRef = useRef<TInstanceAuthenticationModes[]>([]);
  // state
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const { t } = useTranslation();
  // store hooks
  const { fetchInstanceConfigurations, formattedConfig, updateInstanceConfigurations } = useInstance();
  // derived values
  const enableSignUpConfig = formattedConfig?.ENABLE_SIGNUP ?? "";

  useSWR("INSTANCE_CONFIGURATIONS", () => fetchInstanceConfigurations());

  // Create updateConfig with validation - uses authenticationModesRef for current modes
  const updateConfig = useCallback(
    (key: TInstanceConfigurationKeys, value: string): void => {
      // Check if trying to disable (value === "0")
      if (value === "0") {
        // Check if this key is an authentication method key
        const currentAuthModes = authenticationModesRef.current;
        const isAuthMethodKey = currentAuthModes.some((method) => method.enabledConfigKey === key);

        // Only validate if this is an authentication method key
        if (isAuthMethodKey) {
          const canDisable = canDisableAuthMethod(key, currentAuthModes, formattedConfig);

          if (!canDisable) {
            setToast({
              type: "error",
              title: t("admin_settings.cannot_disable"),
              message: t("admin_settings.one_method"),
            });
            return;
          }
        }
      }

      // Proceed with the update
      setIsSubmitting(true);

      const payload = {
        [key]: value,
      };

      const updateConfigPromise = updateInstanceConfigurations(payload);

      setPromiseToast(updateConfigPromise, {
        loading: t("admin_settings.saving_config"),
        success: {
          title: t("admin_settings.success"),
          message: () => t("admin_settings.saved_config"),
        },
        error: {
          title: t("admin_settings.error"),
          message: () => t("admin_settings.save_failed"),
        },
      });

      void updateConfigPromise
        .then(() => {
          setIsSubmitting(false);
          return undefined;
        })
        .catch((err) => {
          console.error(err);
          setIsSubmitting(false);
        });
    },
    [formattedConfig, updateInstanceConfigurations, t]
  );

  // Get authentication modes - this will use updateConfig which includes validation
  const authenticationModes = useAuthenticationModes({
    disabled: isSubmitting,
    updateConfig,
    resolvedTheme,
  });

  // Update ref with latest authentication modes (updateConfig reads it only from event handlers)
  useEffect(() => {
    authenticationModesRef.current = authenticationModes;
  }, [authenticationModes]);

  return (
    <PageWrapper
      header={{
        title: t("admin_settings.auth_title"),
        description: t("admin_settings.auth_description"),
      }}
    >
      {formattedConfig ? (
        <div className="space-y-3">
          <div className="flex w-full items-start justify-between gap-4 rounded-lg border border-subtle bg-layer-2 px-4 py-3 md:items-center md:gap-8">
            <div className="flex min-w-0 grow items-center gap-4">
              <div className="min-w-0 grow">
                <div className="pb-1 text-body-sm-medium text-primary">{t("admin_settings.allow_signup")}</div>
                <div className="text-body-xs-regular leading-5 text-tertiary">{t("admin_settings.invite_only")}</div>
              </div>
            </div>
            <div className={cn("shrink-0", { "opacity-70": isSubmitting })}>
              <div className="flex items-center gap-4">
                <Switch
                  aria-label={t("admin_settings.allow_signup")}
                  checked={Boolean(parseInt(enableSignUpConfig))}
                  onCheckedChange={() => {
                    if (Boolean(parseInt(enableSignUpConfig)) === true) {
                      updateConfig("ENABLE_SIGNUP", "0");
                    } else {
                      updateConfig("ENABLE_SIGNUP", "1");
                    }
                  }}
                  size="sm"
                  disabled={isSubmitting}
                />
              </div>
            </div>
          </div>
          <h3 className="pt-3 text-h6-medium text-primary">{t("admin_settings.available_methods")}</h3>
          {authenticationModes.map((method) => (
            <AuthenticationMethodCard
              key={method.key}
              name={method.name}
              description={method.description}
              icon={method.icon}
              config={method.config}
              disabled={isSubmitting}
              unavailable={method.unavailable}
            />
          ))}
        </div>
      ) : (
        <Skeleton className="space-y-10">
          <Skeleton.Item height="50px" width="75%" />
          <Skeleton.Item height="50px" width="75%" />
          <Skeleton.Item height="50px" width="40%" />
          <Skeleton.Item height="50px" width="40%" />
          <Skeleton.Item height="50px" width="20%" />
        </Skeleton>
      )}
    </PageWrapper>
  );
});

export const meta: Route.MetaFunction = () => [{ title: "Authentication Settings - Plane Web" }];

export default InstanceAuthenticationPage;
