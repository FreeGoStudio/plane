/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { useUserProfile } from "@/hooks/store/user";
import { formatHomeDate, getHomeGreetingPeriod } from "@/helpers/home-datetime";

// plane types
import { useTranslation } from "@plane/i18n";
import type { IUser } from "@plane/types";
// plane ui
// hooks
import { useCurrentTime } from "@/hooks/use-current-time";

export interface IUserGreetingsView {
  user: IUser;
}

export const UserGreetingsView = observer(function UserGreetingsView(props: IUserGreetingsView) {
  const { user } = props;
  // current time hook
  const { currentTime } = useCurrentTime();
  // store hooks
  const { t, currentLocale } = useTranslation();
  const { data: profile } = useUserProfile();

  const greeting = getHomeGreetingPeriod(currentTime, user.user_timezone);
  const date = formatHomeDate(currentTime, currentLocale, user.user_timezone, profile?.theme?.homeDateOrder);

  return (
    <div className="my-6 flex flex-col items-center">
      <h2 className="text-center text-h4-semibold">
        {t(`home.greetings.${greeting}`, { name: [user.first_name, user.last_name].filter(Boolean).join(" ") })}
      </h2>
      <h5 className="flex items-center gap-2 font-medium text-placeholder">
        <div>{greeting === "morning" ? "🌤️" : greeting === "afternoon" ? "🌥️" : "🌙️"}</div>
        <div>{date}</div>
      </h5>
    </div>
  );
});
