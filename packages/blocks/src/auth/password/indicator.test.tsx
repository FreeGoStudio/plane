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
  expect(screen.queryByText("至少 1 个特殊字符")).toBeNull();
  rerender(
    <TranslationProvider>
      <PasswordStrengthIndicator password="a quiet walk through the garden" isFocused />
    </TranslationProvider>
  );
  expect(screen.getByText("密码强度较高")).toBeTruthy();
  await act(() => setLanguage("en"));
  expect(screen.getByText("Password is strong")).toBeTruthy();
  expect(screen.queryByText("Min 1 upper-case letter")).toBeNull();
});

it.each([
  "abcdefgh",
  "ABCDEFGH",
  "83472961",
  "!@#$%^&*",
  "a quiet walk through the garden",
  "带有中文的密码短语",
  "x".repeat(64),
])("accepts the length criterion without character composition requirements: %s", async (password) => {
  const { getPasswordStrength, getPasswordCriteria } = await import("@plane/utils");
  const { E_PASSWORD_STRENGTH } = await import("@plane/constants");
  expect(getPasswordStrength(password)).toBe(E_PASSWORD_STRENGTH.STRENGTH_VALID);
  expect(getPasswordCriteria(password)).toEqual([{ key: "length", label: "Min 8 characters", isValid: true }]);
});

it("retains empty and short password validation", async () => {
  const { getPasswordStrength } = await import("@plane/utils");
  const { E_PASSWORD_STRENGTH } = await import("@plane/constants");
  expect(getPasswordStrength("")).toBe(E_PASSWORD_STRENGTH.EMPTY);
  expect(getPasswordStrength("Ab1!xyz")).toBe(E_PASSWORD_STRENGTH.LENGTH_NOT_VALID);
});
