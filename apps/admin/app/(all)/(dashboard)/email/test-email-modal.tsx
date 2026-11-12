/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import { useState } from "react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { InputField } from "@makeplane/propel/components/input-field";
import { InstanceService } from "@plane/services";

type Props = {
  isOpen: boolean;
  handleClose: () => void;
};

enum ESendEmailSteps {
  SEND_EMAIL = "SEND_EMAIL",
  SUCCESS = "SUCCESS",
  FAILED = "FAILED",
}

const instanceService = new InstanceService();

export function SendTestEmailModal(props: Props) {
  const { t } = useTranslation();
  const { isOpen, handleClose } = props;

  // state
  const [receiverEmail, setReceiverEmail] = useState("");
  const [sendEmailStep, setSendEmailStep] = useState<ESendEmailSteps>(ESendEmailSteps.SEND_EMAIL);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  // reset state
  const resetState = () => {
    setReceiverEmail("");
    setSendEmailStep(ESendEmailSteps.SEND_EMAIL);
    setIsLoading(false);
    setError("");
  };

  const handleSubmit = async (e: React.MouseEvent<HTMLButtonElement, MouseEvent>) => {
    e.preventDefault();

    setIsLoading(true);
    await instanceService
      .sendTestEmail(receiverEmail)
      .then(() => {
        setSendEmailStep(ESendEmailSteps.SUCCESS);
        return;
      })
      .catch((err) => {
        setError(err?.error || t("admin_email.send_failed"));
        setSendEmailStep(ESendEmailSteps.FAILED);
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  return (
    <Dialog
      open={isOpen}
      // The legacy Headless UI dialog closed on outside click and Escape (critic C2): keep both.
      onOpenChange={(open) => {
        if (!open) handleClose();
      }}
      // Reset once the close animation has finished so the content does not flip while fading out.
      onOpenChangeComplete={(open) => {
        if (!open) resetState();
      }}
    >
      <DialogContent size="md">
        <DialogMain>
          <DialogHeader>
            <DialogHeading>
              <DialogTitle>
                {sendEmailStep === ESendEmailSteps.SEND_EMAIL
                  ? t("admin_email.test")
                  : sendEmailStep === ESendEmailSteps.SUCCESS
                    ? t("admin_email.sent_title")
                    : t("admin_email.failed_title")}
              </DialogTitle>
            </DialogHeading>
          </DialogHeader>
          <DialogBody>
            {sendEmailStep === ESendEmailSteps.SEND_EMAIL && (
              <InputField
                id="receiver_email"
                type="email"
                size="lg"
                orientation="vertical"
                label={t("admin_email.recipient")}
                value={receiverEmail}
                onChange={(e) => setReceiverEmail(e.target.value)}
                placeholder={t("admin_email.recipient")}
                autoComplete="email"
                tabIndex={0}
              />
            )}
            {sendEmailStep === ESendEmailSteps.SUCCESS && (
              <div className="flex flex-col gap-y-4 text-body-xs-regular">
                <p>{t("admin_email.sent_message", { email: receiverEmail })}</p>
                <p>{t("admin_email.retry_hint")}</p>
              </div>
            )}
            {sendEmailStep === ESendEmailSteps.FAILED && <div className="text-body-xs-regular">{error}</div>}
          </DialogBody>
        </DialogMain>
        <DialogActions>
          <Button
            variant="secondary"
            size="md"
            stretch="auto"
            onClick={handleClose}
            tabIndex={0}
            label={sendEmailStep === ESendEmailSteps.SEND_EMAIL ? t("cancel") : t("close")}
          />
          {sendEmailStep === ESendEmailSteps.SEND_EMAIL && (
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              loading={isLoading}
              onClick={handleSubmit}
              tabIndex={0}
              label={isLoading ? t("admin_email.sending") : t("admin_email.send")}
            />
          )}
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
}
