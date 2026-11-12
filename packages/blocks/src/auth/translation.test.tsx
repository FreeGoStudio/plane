import { act, renderHook } from "@testing-library/react";
import { expect, it } from "vitest";
import { setLanguage, TranslationProvider, useTranslation } from "@plane/i18n";

it("keeps the translator stable across renders and updates it when language changes", async () => {
  await setLanguage("zh-CN");
  const { result, rerender } = renderHook(() => useTranslation(), { wrapper: TranslationProvider });
  const chinese = result.current.t;
  expect(chinese("common.or")).toBe("或");
  rerender();
  expect(result.current.t).toBe(chinese);
  await act(() => setLanguage("en"));
  expect(result.current.t("common.or")).toBe("or");
  expect(result.current.t).not.toBe(chinese);
});
