/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import { observer } from "mobx-react";
import { Controller, useForm } from "react-hook-form";
import { UsageOutline } from "@makeplane/propel/icons";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { InputField } from "@makeplane/propel/components/input-field";
import { Switch } from "@makeplane/propel/components/switch";
import type { IInstance, IInstanceAdmin } from "@plane/types";
// components
import { ControllerInput } from "@/components/common/controller-input";
import { setToast } from "@plane/blocks/toast";
// hooks
import { useInstance } from "@/hooks/store";

export interface IGeneralConfigurationForm {
  instance: IInstance;
  instanceAdmins: IInstanceAdmin[];
}

export const GeneralConfigurationForm = observer(function GeneralConfigurationForm(props: IGeneralConfigurationForm) {
  const { t } = useTranslation();
  const { instance, instanceAdmins } = props;
  // hooks
  const { updateInstanceInfo } = useInstance();

  // form data
  const {
    handleSubmit,
    control,
    reset,
    formState: { errors, isDirty, isSubmitting },
  } = useForm<Partial<IInstance>>({
    defaultValues: {
      instance_name: instance?.instance_name,
      is_telemetry_enabled: instance?.is_telemetry_enabled,
    },
  });

  const onSubmit = async (formData: Partial<IInstance>) => {
    const payload: Partial<IInstance> = { ...formData };

    try {
      await updateInstanceInfo(payload);
      // the saved values become the new baseline, so Save disables again until the next edit
      reset(formData);
      setToast({
        type: "success",
        title: t("admin_ui.success"),
        message: t("admin_ui.updated"),
      });
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="space-y-8">
      <div className="space-y-4">
        <div className="text-body-md-medium text-primary">{t("admin_ui.details")}</div>
        <div className="grid-col grid w-full grid-cols-1 items-center justify-between gap-8 md:grid-cols-2 lg:grid-cols-3">
          <ControllerInput
            key="instance_name"
            name="instance_name"
            control={control}
            type="text"
            label={t("admin_ui.name")}
            placeholder={t("admin_ui.name_placeholder")}
            error={Boolean(errors.instance_name)}
            required
          />

          <InputField
            id="email"
            name="email"
            type="email"
            size="lg"
            orientation="vertical"
            label={t("admin_ui.email")}
            value={instanceAdmins[0]?.user_detail?.email ?? ""}
            placeholder={t("admin_ui.admin_email")}
            autoComplete="on"
            disabled
          />

          <InputField
            id="instance_id"
            name="instance_id"
            type="text"
            size="lg"
            orientation="vertical"
            label={t("admin_ui.instance_id")}
            value={instance.instance_id}
            disabled
          />
        </div>
      </div>

      <div className="space-y-6">
        <div className="border-b border-subtle pb-1.5 text-body-md-medium text-primary">{t("admin_ui.telemetry")}</div>
        <div className="flex items-center gap-14">
          <div className="flex grow items-center gap-4">
            <div className="shrink-0">
              <div className="flex size-11 items-center justify-center rounded-lg bg-layer-1">
                <UsageOutline className="size-5 text-tertiary" />
              </div>
            </div>
            <div className="grow">
              <div className="text-body-sm-medium leading-5 text-primary">{t("admin_ui.telemetry_enable")}</div>
              <div className="text-body-xs-regular leading-5 text-tertiary">
                {t("admin_ui.telemetry_description")}{" "}
                <a
                  href="https://developers.plane.so/self-hosting/telemetry"
                  target="_blank"
                  className="text-accent-primary hover:underline"
                  rel="noreferrer"
                >
                  {t("admin_ui.telemetry_policy")}
                </a>
              </div>
            </div>
          </div>
          <div className={`shrink-0 ${isSubmitting && "opacity-70"}`}>
            <Controller
              control={control}
              name="is_telemetry_enabled"
              render={({ field: { value, onChange } }) => (
                <Switch
                  aria-label={t("admin_ui.telemetry_enable")}
                  checked={value ?? false}
                  onCheckedChange={onChange}
                  size="sm"
                  disabled={isSubmitting}
                />
              )}
            />
          </div>
        </div>
      </div>

      <div>
        <Button
          variant="primary"
          size="md"
          stretch="auto"
          onClick={() => {
            void handleSubmit(onSubmit)();
          }}
          loading={isSubmitting}
          disabled={!isDirty}
          label={isSubmitting ? t("admin_ui.saving") : t("admin_ui.save_changes")}
        />
      </div>
    </div>
  );
});
