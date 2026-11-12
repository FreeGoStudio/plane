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
  expect(screen.getByText("至少 15 个字符")).toBeTruthy();
  expect(screen.queryByText("至少 1 个特殊字符")).toBeNull();
  rerender(
    <TranslationProvider>
      <PasswordStrengthIndicator password="a quiet walk through the garden" isFocused />
    </TranslationProvider>
  );
  expect(screen.getByText("已满足长度要求")).toBeTruthy();
  await act(() => setLanguage("en"));
  expect(screen.getByText("Length requirement met")).toBeTruthy();
  expect(screen.queryByText("Min 1 upper-case letter")).toBeNull();
});

it.each([
  "abcdefghijklmno",
  "ABCDEFGHIJKLMNO",
  "834729618362947",
  "!@#$%^&*[]~`+=?",
  "a quiet walk through the garden",
  "这是一段超过十五个字符的中文密码短语",
  "x".repeat(64),
])("accepts the length criterion without character composition requirements: %s", async (password) => {
  const { getPasswordStrength, getPasswordCriteria } = await import("@plane/utils");
  const { E_PASSWORD_STRENGTH } = await import("@plane/constants");
  expect(getPasswordStrength(password)).toBe(E_PASSWORD_STRENGTH.STRENGTH_VALID);
  expect(getPasswordCriteria(password)).toEqual([{ key: "length", label: "Min 15 characters", isValid: true }]);
});

it("retains empty and short password validation", async () => {
  const { getPasswordStrength } = await import("@plane/utils");
  const { E_PASSWORD_STRENGTH } = await import("@plane/constants");
  expect(getPasswordStrength("")).toBe(E_PASSWORD_STRENGTH.EMPTY);
  expect(getPasswordStrength("Ab1!xyz")).toBe(E_PASSWORD_STRENGTH.LENGTH_NOT_VALID);
});

it.each(["x".repeat(14), "😀".repeat(14), "e\u0301".repeat(14)])(
  "rejects fewer than 15 normalized Unicode characters",
  async (password) => {
    const { getPasswordStrength } = await import("@plane/utils");
    const { E_PASSWORD_STRENGTH } = await import("@plane/constants");
    expect(getPasswordStrength(password)).toBe(E_PASSWORD_STRENGTH.LENGTH_NOT_VALID);
  }
);

it.each(["😀".repeat(15), "e\u0301".repeat(15), "  spaces in a long passphrase  "])(
  "accepts Unicode and spaces: %s",
  async (password) => {
    const { getPasswordStrength } = await import("@plane/utils");
    const { E_PASSWORD_STRENGTH } = await import("@plane/constants");
    expect(getPasswordStrength(password)).toBe(E_PASSWORD_STRENGTH.STRENGTH_VALID);
  }
);
