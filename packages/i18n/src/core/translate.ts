import { i18nInstance } from "./instance";

/** Read the current language when a non-React editor callback runs, not at module initialization. */
export function translate(key: string, params?: Record<string, unknown>): string {
  const value = params === undefined ? i18nInstance.t(key) : i18nInstance.t(key, params);
  return typeof value === "string"
    ? value
    : typeof value === "number" || typeof value === "boolean"
      ? String(value)
      : key;
}
