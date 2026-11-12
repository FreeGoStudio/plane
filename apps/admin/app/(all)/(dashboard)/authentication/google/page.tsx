/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import { useState } from "react";
import { observer } from "mobx-react";
import useSWR from "swr";
import { Switch } from "@makeplane/propel/components/switch";
// assets
import GoogleLogo from "@/app/assets/logos/google-logo.svg?url";
// components
import { AuthenticationMethodCard } from "@/components/authentication/authentication-method-card";
import { PageWrapper } from "@/components/common/page-wrapper";
import { Skeleton } from "@plane/blocks/skeleton";
import { setPromiseToast } from "@plane/blocks/toast";
// hooks
import { useInstance } from "@/hooks/store";
// types
import type { Route } from "./+types/page";
// local
import { InstanceGoogleConfigForm } from "./form";

const InstanceGoogleAuthenticationPage = observer(function InstanceGoogleAuthenticationPage(
  _props: Route.ComponentProps
) {
  const { t } = useTranslation();
  // store
  const { fetchInstanceConfigurations, formattedConfig, updateInstanceConfigurations } = useInstance();
  // state
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  // config
  const enableGoogleConfig = formattedConfig?.IS_GOOGLE_ENABLED ?? "";

  useSWR("INSTANCE_CONFIGURATIONS", () => fetchInstanceConfigurations());

  const updateConfig = async (key: "IS_GOOGLE_ENABLED", value: string) => {
    setIsSubmitting(true);

    const payload = {
      [key]: value,
    };

    const updateConfigPromise = updateInstanceConfigurations(payload);

    setPromiseToast(updateConfigPromise, {
      loading: t("admin_settings.saving_config"),
      success: {
        title: t("admin_settings.config_saved"),
        message: () => t("admin_settings.auth_state", { provider: "Google", enabled: value === "1" ? "yes" : "no" }),
      },
      error: {
        title: t("admin_settings.error"),
        message: () => t("admin_settings.save_failed"),
      },
    });

    await updateConfigPromise
      .then(() => {
        setIsSubmitting(false);
        return undefined;
      })
      .catch((err) => {
        console.error(err);
        setIsSubmitting(false);
      });
  };
  return (
    <PageWrapper
      title={t("admin_settings.provider_title", { provider: "Google" })}
      customHeader={
        <AuthenticationMethodCard
          name="Google"
          description={t("admin_settings.social_description", { provider: "Google" })}
          icon={<img src={GoogleLogo} height={24} width={24} alt="Google" />}
          config={
            <Switch
              aria-label={t("admin_settings.enable_auth", { provider: "Google" })}
              checked={Boolean(parseInt(enableGoogleConfig))}
              onCheckedChange={() => {
                if (Boolean(parseInt(enableGoogleConfig)) === true) {
                  updateConfig("IS_GOOGLE_ENABLED", "0");
                } else {
                  updateConfig("IS_GOOGLE_ENABLED", "1");
                }
              }}
              size="sm"
              disabled={isSubmitting || !formattedConfig}
            />
          }
          disabled={isSubmitting || !formattedConfig}
          withBorder={false}
        />
      }
    >
      {formattedConfig ? (
        <InstanceGoogleConfigForm config={formattedConfig} />
      ) : (
        <Skeleton className="space-y-8">
          <Skeleton.Item height="50px" width="25%" />
          <Skeleton.Item height="50px" />
          <Skeleton.Item height="50px" />
          <Skeleton.Item height="50px" />
          <Skeleton.Item height="50px" width="50%" />
        </Skeleton>
      )}
    </PageWrapper>
  );
});

export const meta: Route.MetaFunction = () => [{ title: "Plane" }];

export default InstanceGoogleAuthenticationPage;
