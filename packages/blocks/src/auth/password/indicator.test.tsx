import { act, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { setLanguage, TranslationProvider } from "@plane/i18n";
import { PasswordStrengthIndicator } from "./indicator";

it("renders password criteria and strength in the selected language", async () => {
  await setLanguage("zh-CN");
  const { rerender } = render(
    <TranslationProvider>
      <PasswordStrengthIndicator password="abc" isFocused />
    </TranslationProvider>
  );
  expect(screen.getByText("密码太短")).toBeTruthy();
  expect(screen.getByText("至少 8 个字符")).toBeTruthy();
  expect(screen.getByText("至少 1 个特殊字符")).toBeTruthy();
  rerender(
    <TranslationProvider>
      <PasswordStrengthIndicator password="StrongPassword1!" isFocused />
    </TranslationProvider>
  );
  expect(screen.getByText("密码强度较高")).toBeTruthy();
  await act(() => setLanguage("en"));
  expect(screen.getByText("Password is strong")).toBeTruthy();
  expect(screen.getByText("Min 1 upper-case letter")).toBeTruthy();
});
