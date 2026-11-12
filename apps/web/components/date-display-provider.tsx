/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { observer } from "mobx-react";
import { useTranslation } from "@plane/i18n";
import { DateDisplayProvider } from "@plane/utils";
import { useUser, useUserProfile } from "@/hooks/store/user";

export const UserDateDisplayProvider = observer(function UserDateDisplayProvider({
  children,
}: {
  children: ReactNode;
}) {
  const { currentLocale } = useTranslation();
  const { data: user } = useUser();
  const { data: profile } = useUserProfile();
  return (
    <DateDisplayProvider locale={currentLocale} order={profile?.theme?.homeDateOrder} timeZone={user?.user_timezone}>
      {children}
    </DateDisplayProvider>
  );
});
