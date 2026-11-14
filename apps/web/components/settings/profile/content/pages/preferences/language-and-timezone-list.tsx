/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import { SelectField } from "@makeplane/propel/components/select-field";
import { SUPPORTED_LANGUAGES, useTranslation } from "@plane/i18n";
import type { THomeDateOrder } from "@plane/types";
import { setToast } from "@plane/blocks/toast";
// components
import { TimezoneSelect } from "@/components/global/timezone-select";
import { StartOfWeekPreference } from "@/components/profile/start-of-week-preference";
import { SettingsControlItem } from "@/components/settings/control-item";
// hooks
import { useUser, useUserProfile } from "@/hooks/store/user";

export const ProfileSettingsLanguageAndTimezonePreferencesList = observer(
  function ProfileSettingsLanguageAndTimezonePreferencesList() {
    // store hooks
    const {
      data: user,
      updateCurrentUser,
      userProfile: { data: profile },
    } = useUser();
    const { updateUserProfile, updateUserTheme } = useUserProfile();
    // translation
    const { t } = useTranslation();

    const handleTimezoneChange = async (value: string) => {
      try {
        await updateCurrentUser({ user_timezone: value });
        setToast({
          title: "Success!",
          message: "Timezone updated successfully",
          type: "success",
        });
      } catch (_error) {
        setToast({
          title: "Error!",
          message: "Failed to update timezone",
          type: "error",
        });
      }
    };

    const handleLanguageChange = async (value: string) => {
      try {
        await updateUserProfile({ language: value });
        setToast({
          title: "Success!",
          message: "Language updated successfully",
          type: "success",
        });
      } catch (_error) {
        setToast({
          title: "Error!",
          message: "Failed to update language",
          type: "error",
        });
      }
    };

    const handleDateOrderChange = async (homeDateOrder: THomeDateOrder) => {
      try {
        await updateUserTheme({ homeDateOrder });
      } catch (_error) {
        setToast({ type: "error", title: t("home.date_display.save_error") });
      }
    };

    return (
      <div className="flex flex-col gap-y-1">
        <SettingsControlItem
          title={t("timezone")}
          description={t("timezone_setting")}
          control={
            <TimezoneSelect
              value={user?.user_timezone || "Asia/Kolkata"}
              onChange={handleTimezoneChange}
              label={t("timezone")}
              size="md"
              width="fit"
              className="max-w-72 [&_button]:max-w-full"
            />
          }
        />
        <SettingsControlItem
          title={t("language")}
          description={t("language_setting")}
          control={
            <SelectField<string>
              aria-label={t("language")}
              size="md"
              width="fit"
              options={SUPPORTED_LANGUAGES}
              value={profile?.language ?? null}
              onValueChange={(value) => {
                if (value !== null) void handleLanguageChange(value);
              }}
              placeholder={t("language")}
            />
          }
        />
        <SettingsControlItem
          title={t("home.date_display.title")}
          description={t("home.date_display.description")}
          control={
            <SelectField<THomeDateOrder>
              aria-label={t("home.date_display.title")}
              size="md"
              width="fit"
              options={(["locale", "ymd", "mdy", "dmy"] as const).map((value) => ({
                value,
                label: t(`home.date_display.${value}`),
              }))}
              value={profile?.theme?.homeDateOrder ?? "locale"}
              onValueChange={(value) => {
                if (value !== null) void handleDateOrderChange(value);
              }}
            />
          }
        />
        <StartOfWeekPreference
          option={{
            title: t("account_settings.start_of_week.title"),
            description: t("account_settings.start_of_week.description"),
          }}
        />
      </div>
    );
  }
);
