/** Read at request time so changing the UI language takes effect without reloading. */
export function getRequestLanguage(): string | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    const language = window.localStorage.getItem("userLanguage");
    if (language) return language;
  } catch {
    // Browsers may disallow storage; the document still tracks the active language.
  }
  return document.documentElement.lang || "zh-CN";
}
