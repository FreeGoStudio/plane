import type { ReactElement } from "react";
import { Trans, useTranslation } from "react-i18next";

/** Translates a complete sentence while keeping links and user content as React nodes. */
export function LocalizedText({
  messageKey,
  components = {},
  values = {},
}: {
  messageKey: string;
  components?: Record<string, ReactElement>;
  values?: Record<string, unknown>;
}) {
  const { t } = useTranslation();
  return <Trans t={t} i18nKey={messageKey} components={components} values={values} />;
}
