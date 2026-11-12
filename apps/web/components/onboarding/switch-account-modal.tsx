/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import { useState } from "react";

import { useTheme } from "next-themes";
// ui
import { ConfirmDialog } from "@plane/blocks/dialog";
import { setToast } from "@plane/blocks/toast";
// hooks
import { useUser } from "@/hooks/store/user";
import { useAppRouter } from "@/hooks/use-app-router";

type Props = {
  isOpen: boolean;
  onClose: () => void;
};

export function SwitchAccountModal(props: Props) {
  const { t } = useTranslation();
  const { isOpen, onClose } = props;
  // states
  const [switchingAccount, setSwitchingAccount] = useState(false);
  // router
  const router = useAppRouter();
  // store hooks
  const { data: userData, signOut } = useUser();

  const { setTheme } = useTheme();

  const handleClose = () => {
    setSwitchingAccount(false);
    onClose();
  };

  const handleSwitchAccount = async () => {
    setSwitchingAccount(true);

    try {
      await signOut();
      setTheme("system");
      router.push("/");
      handleClose();
    } catch {
      setToast({
        type: "error",
        title: t("error"),
        message: t("auth.sign_out.toast.error.message"),
      });
    } finally {
      setSwitchingAccount(false);
    }
  };

  return (
    <ConfirmDialog
      isOpen={isOpen}
      handleClose={handleClose}
      handleSubmit={handleSwitchAccount}
      isSubmitting={switchingAccount}
      variant="primary"
      title={t("onboarding_ui.switch_account")}
      content={userData?.email ? t("onboarding_ui.switch_account_description", { email: userData.email }) : null}
      primaryButtonText={{ loading: t("onboarding_ui.switching"), default: t("onboarding_ui.switch_account") }}
    />
  );
}
