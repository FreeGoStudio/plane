/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import useSWR from "swr";
import { Switch } from "@makeplane/propel/components/switch";
// components
import { PageWrapper } from "@/components/common/page-wrapper";
import { Skeleton } from "@plane/blocks/skeleton";
import { setToast } from "@plane/blocks/toast";
// hooks
import { useInstance } from "@/hooks/store";
// types
import type { Route } from "./+types/page";
// local
import { InstanceEmailForm } from "./email-config-form";

const InstanceEmailPage = observer(function InstanceEmailPage(_props: Route.ComponentProps) {
  const { t } = useTranslation();
  // store
  const { fetchInstanceConfigurations, formattedConfig, disableEmail } = useInstance();

  const { isLoading } = useSWR("INSTANCE_CONFIGURATIONS", () => fetchInstanceConfigurations());

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSMTPEnabled, setIsSMTPEnabled] = useState(false);

  const handleToggle = async () => {
    if (isSMTPEnabled) {
      setIsSubmitting(true);
      try {
        await disableEmail();
        setIsSMTPEnabled(false);
        setToast({
          title: t("admin_email.disabled_title"),
          message: t("admin_email.disabled_message"),
          type: "success",
        });
      } catch (_error) {
        setToast({
          title: t("admin_email.disable_error_title"),
          message: t("admin_email.disable_error_message"),
          type: "error",
        });
      } finally {
        setIsSubmitting(false);
      }
      return;
    }
    setIsSMTPEnabled(true);
  };
  useEffect(() => {
    if (formattedConfig) {
      setIsSMTPEnabled(formattedConfig.ENABLE_SMTP === "1");
    }
  }, [formattedConfig]);

  return (
    <PageWrapper
      header={{
        title: t("admin_email.title"),
        description: (
          <>
            {t("admin_email.description")}
            <div className="text-body-xs-regular text-tertiary">
              {t("admin_email.setup_hint")}
              <span className="text-danger-primary">{t("admin_email.misconfiguration")}</span>
            </div>
          </>
        ),
        actions: isLoading ? (
          <Skeleton>
            <Skeleton.Item width="24px" height="16px" className="rounded-full" />
          </Skeleton>
        ) : (
          <Switch
            aria-label={t("admin_email.enable")}
            checked={isSMTPEnabled}
            onCheckedChange={handleToggle}
            size="sm"
            disabled={isSubmitting}
          />
        ),
      }}
    >
      {isSMTPEnabled && !isLoading && (
        <>
          {formattedConfig ? (
            <InstanceEmailForm config={formattedConfig} />
          ) : (
            <Skeleton className="space-y-10">
              <Skeleton.Item height="50px" width="75%" />
              <Skeleton.Item height="50px" width="75%" />
              <Skeleton.Item height="50px" width="40%" />
              <Skeleton.Item height="50px" width="40%" />
              <Skeleton.Item height="50px" width="20%" />
            </Skeleton>
          )}
        </>
      )}
    </PageWrapper>
  );
});

export const meta: Route.MetaFunction = () => [{ title: "Email Settings - God Mode" }];

export default InstanceEmailPage;
